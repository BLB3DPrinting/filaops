"""
Canonical inventory posting (HARD-4a).

THE single function through which on-hand quantity changes. Before this
module, four writers mutated `Inventory.on_hand_quantity` with mutually
incompatible conventions (delta-subtract, SET-absolute, signed-add, and
SET-with-no-transaction), which produced confirmed drift between stored
on-hand and the transaction ledger in real databases.

Conventions enforced here:

- **Signed delta.** `quantity_delta > 0` increases stock, `< 0` decreases
  it. SET-style callers compute ``delta = new - current`` first.
- **Signed storage.** The InventoryTransaction row stores the SIGNED
  delta in `quantity`, so for rows written through this poster
  ``sum(quantity) == on_hand`` per product/location. (Historical rows
  written before HARD-4a store positive magnitudes with the sign implied
  by transaction_type; reconciliation across the boundary is HARD-4b's
  job, and HARD-4c repairs history.)
- **Decimal only.** Floats are rejected, not coerced — a float here means
  an upstream bug that would reintroduce penny drift.
- **Atomic.** The transaction row and the on_hand mutation happen
  together in the caller's session. The poster flushes (so the row gets
  an id) but never commits — transaction boundaries belong to callers.
- **Magnitude readers use abs().** `total_cost` is computed from
  ``abs(delta)``, and downstream aggregations (COGS, valuation reports)
  must use ``abs(quantity)`` so they work for both legacy and signed rows.

Policy (insufficient stock, approval workflows, allocation guards) lives
in the calling services — this module is mechanism only. The one policy
hook is `requires_approval`: when True the row is written for the
approval queue but on_hand is NOT mutated (HARD-11 builds the
approve/reject resolution flow on top of this).

`apply_held_transaction` is the approval-path helper: it acquires a
FOR UPDATE lock on the inventory row before mutating on_hand, eliminating
the concurrent-approval double-add race described in HARD-4a follow-up.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.inventory import Inventory, InventoryTransaction
from app.logging_config import get_logger

logger = get_logger(__name__)

# Direction-implied transaction types: the stored sign must match.
INCREASE_TYPES = frozenset({"receipt", "initial", "return", "production"})
DECREASE_TYPES = frozenset(
    {"issue", "consumption", "shipment", "scrap", "negative_adjustment"}
)
# Signed types: either direction is legitimate.
SIGNED_TYPES = frozenset({"adjustment", "reconciliation", "transfer"})

VALID_TYPES = INCREASE_TYPES | DECREASE_TYPES | SIGNED_TYPES


def get_or_create_inventory_row(
    db: Session, product_id: int, location_id: int
) -> Inventory:
    """Fetch the inventory row for (product, location), creating it at zero.

    The fetch takes a row lock (SELECT ... FOR UPDATE) so concurrent posts
    against the same row serialize instead of losing updates. The
    create-when-missing path has a benign first-post race: the inventory
    table has no unique constraint on (product_id, location_id) — a
    pre-existing schema gap shared by every legacy get_or_create helper —
    so adding the constraint plus a dedupe of existing data is HARD-4b/4c
    work, not this module's.
    """
    inventory = (
        db.query(Inventory)
        .filter(
            Inventory.product_id == product_id,
            Inventory.location_id == location_id,
        )
        .with_for_update()
        .first()
    )
    if not inventory:
        inventory = Inventory(
            product_id=product_id,
            location_id=location_id,
            on_hand_quantity=Decimal("0"),
            allocated_quantity=Decimal("0"),
        )
        db.add(inventory)
        db.flush()
    return inventory


def post(
    db: Session,
    *,
    product_id: int,
    location_id: int,
    transaction_type: str,
    quantity_delta: Decimal,
    cost_per_unit: Optional[Decimal] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    lot_number: Optional[str] = None,
    serial_number: Optional[str] = None,
    unit: Optional[str] = None,
    notes: Optional[str] = None,
    reason_code: Optional[str] = None,
    created_by: Optional[str] = None,
    requires_approval: bool = False,
    approval_reason: Optional[str] = None,
    approved_by: Optional[str] = None,
) -> InventoryTransaction:
    """
    Post an inventory movement: write the ledger row AND mutate on-hand.

    Args:
        quantity_delta: SIGNED Decimal. Positive increases stock, negative
            decreases it. Zero is rejected — skip the call instead.
        transaction_type: one of VALID_TYPES. Direction-implied types must
            agree with the delta's sign (receipt must be positive,
            consumption negative, ...); `adjustment`/`reconciliation`/
            `transfer` accept either sign.
        requires_approval: write the row for the approval queue WITHOUT
            touching on_hand. The approval flow re-posts on approve.

    Returns:
        The InventoryTransaction row (flushed, id assigned, not committed).

    Raises:
        TypeError: if quantity_delta or cost_per_unit is a float.
        ValueError: zero delta, unknown type, or sign/type mismatch.
    """
    if isinstance(quantity_delta, float) or isinstance(cost_per_unit, float):
        raise TypeError(
            "inventory_ledger.post requires Decimal quantities/costs, got float"
        )
    quantity_delta = Decimal(quantity_delta)

    if quantity_delta == 0:
        raise ValueError("Zero-quantity inventory posting — skip the call instead")

    if transaction_type not in VALID_TYPES:
        raise ValueError(
            f"Unknown transaction_type {transaction_type!r}; "
            f"expected one of {sorted(VALID_TYPES)}"
        )
    if transaction_type in INCREASE_TYPES and quantity_delta < 0:
        raise ValueError(
            f"{transaction_type} must increase stock; got delta {quantity_delta}"
        )
    if transaction_type in DECREASE_TYPES and quantity_delta > 0:
        raise ValueError(
            f"{transaction_type} must decrease stock; got delta {quantity_delta}"
        )

    inventory = get_or_create_inventory_row(db, product_id, location_id)

    total_cost = None
    if cost_per_unit is not None:
        total_cost = abs(quantity_delta) * Decimal(cost_per_unit)

    now = datetime.now(timezone.utc)
    transaction = InventoryTransaction(
        product_id=product_id,
        location_id=location_id,
        transaction_type=transaction_type,
        transaction_date=now.date(),
        quantity=quantity_delta,
        cost_per_unit=cost_per_unit,
        total_cost=total_cost,
        reference_type=reference_type,
        reference_id=reference_id,
        lot_number=lot_number,
        serial_number=serial_number,
        unit=unit,
        notes=notes,
        reason_code=reason_code,
        created_by=created_by,
        created_at=now,
        requires_approval=requires_approval,
        approval_reason=approval_reason,
        approved_by=approved_by,
        approved_at=now if approved_by else None,
    )
    db.add(transaction)

    if not requires_approval:
        inventory.on_hand_quantity = (
            Decimal(str(inventory.on_hand_quantity or 0)) + quantity_delta
        )
        inventory.updated_at = now
    else:
        logger.info(
            "Ledger row for product %s held for approval (delta %s) — "
            "on_hand not mutated",
            product_id,
            quantity_delta,
        )

    db.flush()
    return transaction


def apply_held_transaction(
    db: Session,
    transaction: "InventoryTransaction",
    approved_by: str,
    approval_reason: str,
) -> None:
    """Apply a held (requires_approval=True) transaction to on_hand.

    This is the canonical path for the approval endpoint. It acquires a
    FOR UPDATE lock on the inventory row via get_or_create_inventory_row
    BEFORE mutating on_hand, so concurrent approvals of the same held
    transaction serialize rather than double-applying the delta.

    Only rows written through inventory_ledger.post (HARD-4a, signed
    quantity) are applied here. Legacy held rows with positive-magnitude
    quantity are detected and skipped with a warning — HARD-11 resolves
    them with explicit direction information.

    Args:
        transaction: The InventoryTransaction row to apply. Must have
            requires_approval=True and approved_by=None (not yet applied).
        approved_by: Email or username of the approver.
        approval_reason: Human-readable reason for the approval.

    Raises:
        ValueError: if the transaction is not held, already approved, or
            the on_hand mutation would produce an obviously incorrect result.
    """
    if not transaction.requires_approval:
        raise ValueError(
            f"Transaction {transaction.id} does not require approval"
        )
    if transaction.approved_by is not None:
        raise ValueError(
            f"Transaction {transaction.id} is already approved by "
            f"{transaction.approved_by}"
        )

    # Acquire FOR UPDATE lock on the inventory row.  This serializes
    # concurrent inventory mutations for the same product/location pair.
    inventory = get_or_create_inventory_row(
        db, transaction.product_id, transaction.location_id
    )

    # Re-validate transaction state AFTER acquiring the lock.
    #
    # The pre-lock checks above catch the easy "obviously wrong" cases, but
    # there is a TOCTOU race: two concurrent approvals can both pass those
    # checks before either acquires the inventory lock.  Once the lock is
    # held, refresh the transaction from the database to pick up any state
    # change committed by the concurrent winner, then re-check.
    #
    # Without the refresh, Request B would read stale ORM state
    # (requires_approval=True) even after Request A's commit set it to
    # False, and would double-apply the delta.
    db.refresh(transaction)
    if not transaction.requires_approval:
        raise ValueError(
            f"Transaction {transaction.id} was approved concurrently "
            f"(race detected after acquiring inventory lock)"
        )
    if transaction.approved_by is not None:
        raise ValueError(
            f"Transaction {transaction.id} is already approved by "
            f"{transaction.approved_by} (concurrent approval)"
        )

    now = datetime.now(timezone.utc)
    transaction.requires_approval = False
    transaction.approved_by = approved_by
    transaction.approval_reason = approval_reason
    transaction.approved_at = now

    qty = Decimal(str(transaction.quantity))

    if qty < 0:
        # HARD-4a signed row: apply the delta.
        inventory.on_hand_quantity = (
            Decimal(str(inventory.on_hand_quantity or 0)) + qty
        )
        inventory.updated_at = now
        logger.info(
            "Applied held transaction %s for product %s (delta %s) "
            "approved by %s; new on_hand=%s",
            transaction.id,
            transaction.product_id,
            qty,
            approved_by,
            inventory.on_hand_quantity,
        )
    else:
        # Positive-magnitude row written before HARD-4a.  Direction cannot
        # be inferred safely here; leave on_hand untouched and log so
        # HARD-11 can resolve it.
        logger.warning(
            "Approved legacy held transaction %s with positive-magnitude "
            "quantity %s; on_hand NOT mutated (pre-HARD-4a rows need "
            "HARD-11 resolution).",
            transaction.id,
            qty,
        )

    db.flush()
