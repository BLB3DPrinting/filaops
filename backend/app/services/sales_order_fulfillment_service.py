"""
Sales Order Fulfillment Service — shipping, shipment GL posting, and legacy
fulfillment resolution (LEGACY-1).

Moved verbatim from sales_order_service.py (DEBT-1 D1-A mechanical split).
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.sales_order import SalesOrder
from app.models.inventory import InventoryTransaction
from app.services.sales_order_shared import (
    get_sales_order_with_lines,
    record_order_event,
)

logger = get_logger(__name__)

_SHIPMENT_COST_ACCOUNTS = {
    "shipment": ("5000", "1220"),
    "consumption": ("5010", "1230"),
}
_SHIPMENT_TRANSACTION_COST_TYPES = {
    "shipment": "shipment",
    "consumption": "consumption",
}
_NEGATIVE_SHIPMENT_ADJUSTMENT_TYPE = "negative_adjustment"
_MATERIAL_SHIPMENT_GL_UNSUPPORTED_MESSAGE = (
    "Shipment GL posting for material-backed sales orders needs raw-material account mapping"
)

# LEGACY-1: statuses where the order claims goods have left the building.
# Mirrors SHIPPED_ORDER_STATUSES in frontend/src/pages/admin/OrderDetail.jsx.
SHIPPED_ORDER_STATUSES = {"shipped", "delivered", "completed"}

# Full-ship correctness only. Partial / mixed-lot shipping is the separate
# #726 feature; until it lands, 'ready_to_ship' is the only shippable state.
# ship_order() and can_ship_reasons() both import this single constant so the
# UI preflight and the actual ship gate can never drift apart (#845/#846).
SHIPPABLE_STATUSES = frozenset({"ready_to_ship"})

# Order-level fulfillment_status values that count as shipment evidence.
# Grounded in order_status.py which sets "shipped"/"delivered" on those
# transitions; "fulfilled" is accepted defensively for older data.
_SHIPMENT_EVIDENCE_FULFILLMENT_STATUSES = {"shipped", "delivered", "fulfilled"}


def _has_material_backed_lines(order: "SalesOrder") -> bool:
    return any(
        (getattr(line, "line_type", None) or "").lower() == "material"
        or getattr(line, "material_inventory_id", None) is not None
        for line in (order.lines or [])
    )


# =============================================================================
# Shipping
# =============================================================================

def _create_shipment_gl_entry(
    db: Session,
    order: "SalesOrder",
    user_id: int,
    shipment_transactions: Optional[list[InventoryTransaction]] = None,
) -> None:
    """
    Create GL journal entry for a sales order shipment.

    DR COGS (5000), CR FG Inventory (1220) for shipped goods.
    DR Shipping Supplies (5010), CR Packaging Inventory (1230) for packaging.
    Uses the inventory transactions created by process_shipment() when provided.
    Skips lines with no cost set — no entry is created if total is zero.

    Called from ship_order() AFTER process_shipment() handles inventory
    transactions, so this only creates the accounting entry and links those
    inventory transactions to it.
    """
    from app.models.accounting import GLJournalEntry
    from app.services.payment_service import ensure_core_sales_accounts
    from app.services.transaction_service import TransactionService

    if _has_material_backed_lines(order):
        raise ValueError(_MATERIAL_SHIPMENT_GL_UNSUPPORTED_MESSAGE)

    existing = db.query(GLJournalEntry.id).filter(
        GLJournalEntry.source_type == "sales_order",
        GLJournalEntry.source_id == order.id,
        GLJournalEntry.status != "voided",
    ).first()
    if existing:
        return

    if shipment_transactions is None:
        shipment_transactions = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "sales_order",
            InventoryTransaction.reference_id == order.id,
            InventoryTransaction.transaction_type.in_([
                *_SHIPMENT_TRANSACTION_COST_TYPES,
                _NEGATIVE_SHIPMENT_ADJUSTMENT_TYPE,
            ]),
        ).all()

    # Whether there were any candidate shipment transactions BEFORE the
    # held-filter below. If there were, but they were all held for approval,
    # the goods were not relieved — and the line-cost fallback must NOT fire
    # (that would post COGS for unrelieved goods).
    had_candidate_transactions = bool(shipment_transactions)

    # Never post COGS for goods that weren't actually relieved: a short on a
    # finished good or packaging comes back as a held negative_adjustment
    # (requires_approval=True) with on_hand untouched. Exclude held txns — the
    # negative-inventory approval flow reposts the cost when it is applied (#838).
    shipment_transactions = [
        txn for txn in shipment_transactions
        if not getattr(txn, "requires_approval", False)
    ]

    def shipment_cost_type(txn: InventoryTransaction) -> str | None:
        if txn.transaction_type in _SHIPMENT_TRANSACTION_COST_TYPES:
            return _SHIPMENT_TRANSACTION_COST_TYPES[txn.transaction_type]
        if txn.transaction_type == _NEGATIVE_SHIPMENT_ADJUSTMENT_TYPE:
            if txn.product and txn.product.item_type == "packaging":
                return "consumption"
            return "shipment"
        return None

    unexpected_types = sorted({
        txn.transaction_type
        for txn in shipment_transactions
        if shipment_cost_type(txn) is None
    })
    if unexpected_types:
        raise ValueError(
            "Unexpected shipment transaction types for "
            f"SO#{order.order_number}: {', '.join(unexpected_types)}"
        )

    def txn_cost(txn: InventoryTransaction) -> Decimal:
        if txn.total_cost is not None:
            return Decimal(str(txn.total_cost or 0)).quantize(Decimal("0.01"))
        quantity = abs(Decimal(str(txn.quantity or 0)))
        unit_cost = Decimal(str(txn.cost_per_unit or 0))
        return (quantity * unit_cost).quantize(Decimal("0.01"))

    cost_by_transaction_type = {
        transaction_type: Decimal("0")
        for transaction_type in _SHIPMENT_COST_ACCOUNTS
    }
    for txn in shipment_transactions:
        cost_type = shipment_cost_type(txn)
        if cost_type is not None:
            cost_by_transaction_type[cost_type] += txn_cost(txn)

    if (
        cost_by_transaction_type["shipment"] <= 0
        and not shipment_transactions
        and not had_candidate_transactions
    ):
        for line in (order.lines or []):
            if not line.product_id or not line.product:
                continue
            product = line.product
            cost = product.standard_cost or product.average_cost or product.last_cost
            if not cost or cost <= 0:
                continue
            cost_by_transaction_type["shipment"] += Decimal(str(line.quantity)) * Decimal(str(cost))

    lines = []
    for transaction_type, amount in cost_by_transaction_type.items():
        if amount <= 0:
            continue
        debit_account, credit_account = _SHIPMENT_COST_ACCOUNTS[transaction_type]
        lines.extend([
            (debit_account, amount, "DR"),
            (credit_account, amount, "CR"),
        ])

    if not lines:
        return  # No costed items — skip GL entry

    ensure_core_sales_accounts(db)
    ts = TransactionService(db)
    journal_entry = ts.create_journal_entry(
        description=f"Shipment for SO#{order.order_number}",
        lines=lines,
        source_type="sales_order",
        source_id=order.id,
        user_id=user_id,
    )

    for txn in shipment_transactions:
        txn.journal_entry_id = journal_entry.id


def _candidate_product_ids(order: "SalesOrder") -> set[int]:
    """Product ids `order` would demand if shipped (no query — reads loaded lines)."""
    if order.lines:
        return {line.product_id for line in order.lines if line.product_id}
    if order.product_id:
        return {order.product_id}
    return set()


def _aggregate_shippable_demand(
    db: Session,
    order: "SalesOrder",
    *,
    existing_product_ids: Optional[set[int]] = None,
) -> dict[int, Decimal]:
    """Per-product FG demand for shipping `order`, summed across its lines.

    Two lines that share a product_id are summed into one entry. Lines whose
    Product row no longer exists are skipped — issue_shipped_goods does the
    same, so a deleted-product line must never 409 a shippable order.

    Single implementation shared by ship_order() (which locks each row before
    checking) and can_ship_reasons() (which reads a non-locking snapshot) —
    extracting this is what makes "exact parity between the two" a structural
    guarantee instead of something to remember to keep in sync (#845/#846).

    Pass `existing_product_ids` (pre-fetched once across many orders) to avoid
    a per-order Product existence query — see can_ship_reasons() batch usage.
    """
    candidate_ids = _candidate_product_ids(order)
    if existing_product_ids is None:
        from app.models.product import Product
        existing_ids = {
            pid for (pid,) in db.query(Product.id).filter(Product.id.in_(candidate_ids)).all()
        } if candidate_ids else set()
    else:
        existing_ids = candidate_ids & existing_product_ids

    demand_by_product: dict[int, Decimal] = {}
    if order.lines:
        for line in order.lines:
            if line.product_id and line.product_id in existing_ids:
                demand_by_product[line.product_id] = (
                    demand_by_product.get(line.product_id, Decimal("0"))
                    + Decimal(str(line.quantity))
                )
    elif order.product_id and order.product_id in existing_ids:
        demand_by_product[order.product_id] = Decimal(str(order.quantity or 1))

    return demand_by_product


def ship_order(
    db: Session,
    order_id: int,
    user_id: int,
    user_email: str,
    carrier: str = "USPS",
    service: Optional[str] = "Priority",
    tracking_number: Optional[str] = None,
) -> dict:
    """
    Ship an order - create label and process inventory.

    Args:
        order_id: Order to ship
        user_id: User shipping
        user_email: User email
        carrier: Shipping carrier
        service: Service level
        tracking_number: Optional pre-existing tracking number

    Returns:
        Dict with tracking info
    """
    import random
    import string
    from app.services.inventory_service import (
        process_shipment,
        get_or_create_default_location,
    )
    from app.services.inventory_ledger import get_or_create_inventory_row
    from app.services.event_service import record_shipping_event

    # Serialize concurrent ship attempts on this order (#838/MF4). Lock a plain
    # single-table row first — Postgres can't FOR UPDATE a collection join.
    locked = (
        db.query(SalesOrder)
        .filter(SalesOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if locked is None:
        raise HTTPException(status_code=404, detail="Sales order not found")

    # Ship-ready precondition, re-checked under the lock so a second concurrent
    # ship sees status='shipped' set by the first and 409s (TOCTOU guard).
    # 'ready_to_ship' is the status machine's gate for an order cleared to ship;
    # it blocks shipping draft/confirmed/in-production orders.
    if locked.status not in SHIPPABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Order {locked.order_number} cannot be shipped from status "
                f"{locked.status!r}; it must be 'ready_to_ship'."
            ),
        )

    # Re-load with lines (identity map returns the same locked row).
    order = get_sales_order_with_lines(db, order_id)

    # Validate shipping address
    if not order.shipping_address_line1 or not order.shipping_city:
        raise HTTPException(
            status_code=400,
            detail="Order has no shipping address. Please add one first."
        )
    if _has_material_backed_lines(order):
        raise HTTPException(
            status_code=400,
            detail=_MATERIAL_SHIPMENT_GL_UNSUPPORTED_MESSAGE,
        )

    # Block shipping unless every finished good can be fully relieved (#838/MF2).
    # A short would otherwise post COGS while the stock stays held pending
    # approval. Aggregate demand per product (so two lines of the same product
    # are summed), lock each FG row, and compare available (on_hand - allocated,
    # matching the relief gate). The row lock is held for the rest of this
    # transaction, so two orders racing the same FG row serialize here.
    _location = get_or_create_default_location(db)
    _demand_by_product = _aggregate_shippable_demand(db, order)

    for _product_id, _needed in _demand_by_product.items():
        _inv = get_or_create_inventory_row(db, _product_id, _location.id)
        _on_hand = Decimal(str(_inv.on_hand_quantity))
        _allocated = Decimal(str(_inv.allocated_quantity))
        _available = _on_hand - _allocated
        if _available < _needed:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Insufficient inventory to ship product {_product_id}: "
                    f"need {_needed}, available {_available} "
                    f"(on hand {_on_hand}, allocated {_allocated}). Restock or "
                    f"release the allocation before shipping."
                ),
            )

    # Generate tracking number if not provided
    if not tracking_number:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        carrier_prefix = carrier[:3].upper() if carrier else "SHP"
        tracking_number = f"{carrier_prefix}{date_part}{order_id:04d}{random_part}"

    # Update order
    order.tracking_number = tracking_number
    order.carrier = carrier
    order.shipped_at = datetime.now(timezone.utc)
    order.status = "shipped"
    order.updated_at = datetime.now(timezone.utc)

    # Process inventory transactions
    packaging_txns, issue_pairs = process_shipment(
        db=db,
        sales_order=order,
        created_by=user_email,
    )

    # Record per-line shipped quantity (full ship: the whole ordered qty left).
    # Absolute SET, not accumulate — re-ship is blocked by the status gate above,
    # and SET keeps shipped_quantity from drifting past the ordered quantity.
    # Skip held txns defensively; the availability pre-check means a finished
    # good is never held here.
    for line, txn in issue_pairs:
        if line is not None and not txn.requires_approval:
            line.shipped_quantity = Decimal(str(line.quantity))

    issue_txns = [txn for _, txn in issue_pairs]

    # Create GL journal entry for COGS and FG inventory relief
    _create_shipment_gl_entry(db, order, user_id, [*packaging_txns, *issue_txns])

    # Record order event
    record_order_event(
        db=db,
        order_id=order_id,
        event_type="shipped",
        title="Order shipped",
        description=f"Shipped via {carrier}" + (f" ({service})" if service else ""),
        user_id=user_id,
        metadata_key="tracking_number",
        metadata_value=tracking_number,
    )

    # Record shipping event
    record_shipping_event(
        db=db,
        sales_order_id=order_id,
        event_type="label_purchased",
        title="Shipping Label Created",
        description=f"Carrier: {carrier}" + (f", Service: {service}" if service else ""),
        tracking_number=tracking_number,
        carrier=carrier,
        user_id=user_id,
        source="manual",
    )

    # Trigger MRP recalculation if enabled
    try:
        from app.services.mrp_trigger_service import trigger_mrp_recalculation
        from app.core.settings import get_settings
        settings = get_settings()

        if settings.AUTO_MRP_ON_SHIPMENT:
            trigger_mrp_recalculation(db, order.id, reason="shipment")
    except Exception as e:
        logger.warning(
            f"MRP recalculation trigger failed after shipping order {order.id}: {str(e)}",
            exc_info=True
        )

    return {
        "message": "Order shipped successfully",
        "tracking_number": tracking_number,
        "carrier": carrier,
        "service": service,
        "shipped_at": order.shipped_at.isoformat(),
        "label_url": None,
    }


def can_ship_reasons(
    db: Session,
    order: "SalesOrder",
    *,
    location_id: Optional[int] = None,
    existing_product_ids: Optional[set[int]] = None,
    inventory_snapshot: Optional[dict[int, tuple[Decimal, Decimal]]] = None,
) -> dict:
    """Preflight: would ship_order() accept this order right now?

    Read-only — takes NO row lock and is safe to call from a GET. Checks the
    SAME conditions, in the SAME order, that ship_order() itself enforces
    (status -> address -> material-backed -> inventory), reusing the same
    SHIPPABLE_STATUSES constant and _aggregate_shippable_demand() helper, so a
    "can_ship: true" here means ship_order will not 400/409 a moment later for
    the same reason. It is a preflight, not a guarantee: ship_order() re-checks
    every one of these under a row lock at ship time, which is the only place
    a concurrent-order race is actually resolved (#838/MF4).

    Reasons are deliberately conservative (no raw on-hand/allocated numbers)
    to avoid exposing exact stock counts on a list view (#845/#846).

    Called with no optional args, this does its own queries (location lookup,
    existing-product check, one inventory read per product) — fine for a
    single order. A caller checking MANY orders (the AdminShipping batch
    endpoint) should pre-fetch `location_id`, `existing_product_ids`, and
    `inventory_snapshot` ONCE and pass them to every call, so the batch cost
    stays O(1) backend queries instead of O(orders).

    Returns {"can_ship": bool, "reasons": [str, ...]}.
    """
    from app.services.inventory_service import (
        get_inventory_snapshot,
        get_default_location,
    )

    reasons: list[str] = []

    if order.status not in SHIPPABLE_STATUSES:
        reasons.append(f"Order is {order.status!r}; it must be 'ready_to_ship' to ship.")
        # Every other check assumes a shippable order; nothing else is actionable yet.
        return {"can_ship": False, "reasons": reasons}

    if not order.shipping_address_line1 or not order.shipping_city:
        reasons.append("Order has no shipping address.")

    if _has_material_backed_lines(order):
        reasons.append(_MATERIAL_SHIPMENT_GL_UNSUPPORTED_MESSAGE)

    # Read-only: never create a warehouse from a preflight GET. Only resolve a
    # location when we'll actually query inventory ourselves (no snapshot given).
    if location_id is None and inventory_snapshot is None:
        default_loc = get_default_location(db)
        location_id = default_loc.id if default_loc else None

    demand_by_product = _aggregate_shippable_demand(
        db, order, existing_product_ids=existing_product_ids
    )
    for product_id, needed in demand_by_product.items():
        if inventory_snapshot is not None:
            on_hand, allocated = inventory_snapshot.get(
                product_id, (Decimal("0"), Decimal("0"))
            )
        elif location_id is None:
            # No warehouse exists yet → no stock anywhere.
            on_hand, allocated = Decimal("0"), Decimal("0")
        else:
            on_hand, allocated = get_inventory_snapshot(db, product_id, location_id)
        available = on_hand - allocated
        if available < needed:
            reasons.append(f"Insufficient inventory for product {product_id}.")

    return {"can_ship": not reasons, "reasons": reasons}


# =============================================================================
# Legacy Fulfillment Resolution (LEGACY-1)
# =============================================================================

def has_shipment_evidence(order: "SalesOrder") -> bool:
    """
    True when there is any recorded evidence that goods actually shipped.

    Evidence = order.shipped_at set, OR any line with shipped_quantity > 0,
    OR order.fulfillment_status in the shipped/delivered set.
    """
    if order.shipped_at is not None:
        return True
    if (order.fulfillment_status or "") in _SHIPMENT_EVIDENCE_FULFILLMENT_STATUSES:
        return True
    for line in (order.lines or []):
        if (line.shipped_quantity or Decimal("0")) > Decimal("0"):
            return True
    return False


def resolve_legacy_fulfillment(
    db: Session,
    order_id: int,
    action: str,
    user_email: str,
    user_id: Optional[int] = None,
) -> SalesOrder:
    """
    Resolve a legacy fulfillment mismatch on a brownfield order.

    Mismatch = order.status says shipped/delivered/completed, but there is
    NO shipment evidence (no shipped_at, no shipped quantities, fulfillment
    still pending). This happens on orders created before FilaOps recorded
    shipment data properly.

    Actions:
        close_out: accept the order as fulfilled — paperwork reconciliation
            only. Sets line shipped quantities, fulfillment_status, and
            shipped_at, and appends an audit note.

            DESIGN DECISION (owner, LEGACY-1): close_out posts NO inventory
            movements and NO GL entries. The goods physically left long ago;
            per the HARD-4c doctrine, current stock truth comes from the
            inventory ledger + cycle counts, not from retroactive paperwork.
            Backdating COGS/inventory relief here would corrupt both.

        reopen: production is already complete, so move the order back to
            ready_to_ship and let the normal Ship flow take over (which DOES
            post inventory + GL). Invoice/payment are left untouched.

    Raises 409 if the mismatch does not actually exist (re-validated
    server-side so stale UI cannot mutate healthy orders).
    """
    order = get_sales_order_with_lines(db, order_id)

    if order.status not in SHIPPED_ORDER_STATUSES or has_shipment_evidence(order):
        raise HTTPException(
            status_code=409,
            detail=(
                "No legacy fulfillment mismatch on this order: it is either "
                "not in a shipped/delivered/completed status or already has "
                "shipment evidence recorded."
            ),
        )

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")

    if action == "close_out":
        for line in (order.lines or []):
            line.shipped_quantity = line.quantity
        # Grounded enum: order_status.py uses "shipped"/"delivered" as the
        # shipped-evidence fulfillment statuses (there is no "fulfilled").
        order.fulfillment_status = (
            "delivered" if order.status == "delivered" else "shipped"
        )
        order.shipped_at = order.actual_completion_date or now
        audit_note = (
            f"Legacy fulfillment closed out by {user_email} on {date_str} "
            f"— no shipment record existed (no inventory or GL impact)"
        )
        event_title = "Legacy fulfillment closed out"
    elif action == "reopen":
        # Direct assignment (not the transition validator): completed →
        # ready_to_ship is intentionally outside the normal lifecycle; this
        # is an admin-gated data repair, and production is already complete.
        order.status = "ready_to_ship"
        order.fulfillment_status = "ready"
        audit_note = (
            f"Legacy fulfillment reopened (set to ready_to_ship) by "
            f"{user_email} on {date_str} — no shipment record existed; "
            f"ship through the normal flow"
        )
        event_title = "Legacy fulfillment reopened for shipping"
    else:
        raise HTTPException(
            status_code=400,
            detail="action must be 'close_out' or 'reopen'",
        )

    order.internal_notes = (
        f"{order.internal_notes}\n{audit_note}" if order.internal_notes else audit_note
    )
    order.updated_at = now

    record_order_event(
        db=db,
        order_id=order.id,
        event_type="legacy_fulfillment_resolved",
        title=event_title,
        description=audit_note,
        user_id=user_id,
        metadata_key="action",
        metadata_value=action,
    )

    return order
