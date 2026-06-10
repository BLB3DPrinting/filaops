"""
Inventory reconciliation report and baseline posting (HARD-4b + HARD-4c).

RECONCILIATION REPORT
---------------------
Computes, per Inventory row, the divergence between:
  - stored ``Inventory.on_hand_quantity``  (the running balance maintained by
    inventory_ledger.post)
  - Sigma(InventoryTransaction.quantity) filtered to the item's epoch

EPOCH SEMANTICS
---------------
``Inventory.baseline_timestamp`` (added by migration 086) anchors the epoch.

  NULL baseline  -> item has never been physically counted.  The report sums
                   ALL non-excluded transactions from the dawn of time and
                   classifies the item as ``uncounted``.

  Non-NULL       -> item has been counted at least once.  Only transactions
                   with ``created_at >= baseline_timestamp`` are summed.

SIGN CONVENTION (HARD-4a)
--------------------------
inventory_ledger.post() writes SIGNED quantities: positive = stock in,
negative = stock out.  So ``Sigma(quantity)`` IS the expected on-hand for the
epoch.  Pre-4a rows used mixed conventions (positive magnitudes); the plan
documents abs() as the migration-safe reader fix.  However, for
RECONCILIATION the meaningful comparison is:

    drift = stored_on_hand - ledger_sum

A non-zero drift for a fully-4a-posted item means a SET-style write happened
outside the poster.  The absolute value of drift signals how far off counts
are without requiring ABS() on the sum -- callers see both stored_on_hand and
ledger_sum so they can interpret the sign themselves.

EXCLUSIONS
----------
Rows with ``location_id IS NULL`` are excluded from sums.  These are
untracked spool-weight adjustment rows documented in PR #690 (HARD-4a).
``requires_approval=True`` rows that have NOT been approved are pending
transactions that have not yet affected on_hand; excluding them keeps the
math honest (the poster also skips on_hand mutation for those rows).

OUTPUT
------
One ``ReconciliationItem`` per Inventory row that has a matching Product.
Rows with no transaction history for their epoch return ledger_sum = 0 and
drift = stored_on_hand.

BASELINE POSTING (HARD-4c)
--------------------------
``post_reconciliation_baseline`` records a physical count result:

  1. Acquires a FOR UPDATE lock on the Inventory row (via the canonical
     poster's get_or_create_inventory_row) so the stored quantity read and
     the ledger write are atomic under a single row lock.
  2. Computes ``delta = counted_qty - stored_at_lock_time``.
  3. For non-zero delta: posts through ``inventory_ledger.post`` with
     ``transaction_type="reconciliation"`` (a SIGNED_TYPE in the poster)
     and ``reason_code="reconciliation_baseline"``.  GL treatment: identical
     to cycle-count variance (DR/CR 1200 Inventory vs 5030 Inventory
     Adjustment) via TransactionService.cycle_count_adjustment's GL logic.
  4. For zero delta: skips the ledger post (poster rejects zero) but still
     stamps ``Inventory.baseline_timestamp`` -- the count happened, even if
     it found no variance.
  5. Stamps ``Inventory.baseline_timestamp`` to the transaction's
     ``created_at`` timestamp (or NOW for zero-delta) IN THE SAME FLUSH,
     so the epoch anchor and the ledger row are atomically consistent.

EXPLICIT FALLBACK (dev/test/first-install only)
------------------------------------------------
``baseline_to_stored`` stamps ``baseline_timestamp`` to NOW with delta=0.
No ledger row is written (nothing changed -- the stored value is accepted
as the baseline).  The caller MUST supply ``confirm="BASELINE_TO_STORED"``
to prevent silent invocation.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.inventory import Inventory, InventoryTransaction
from app.models.product import Product
from app.logging_config import get_logger

logger = get_logger(__name__)

# Confirmation token required by baseline_to_stored.
BASELINE_TO_STORED_CONFIRM_TOKEN = "BASELINE_TO_STORED"


@dataclass
class ReconciliationItem:
    """One row in the reconciliation report."""

    # Identity
    inventory_id: int
    product_id: int
    sku: str
    name: str
    location_id: int
    location_name: Optional[str]

    # Quantities (Decimal; sign-correct from the poster)
    stored_on_hand: Decimal
    ledger_sum: Decimal          # Sigma(quantity) for the epoch (may be 0 if no txns)
    drift: Decimal               # stored_on_hand - ledger_sum

    # Epoch anchor
    baseline_timestamp: Optional[datetime]  # None -> uncounted

    # Derived
    is_counted: bool  # False when baseline_timestamp IS NULL

    @property
    def has_drift(self) -> bool:
        return self.drift != Decimal("0")


def get_reconciliation_report(
    db: Session,
    *,
    drifted_only: bool = False,
) -> List[ReconciliationItem]:
    """
    Compute the inventory reconciliation report.

    Args:
        db: SQLAlchemy session (read-only -- no writes).
        drifted_only: when True, return only rows where drift != 0.

    Returns:
        List of ReconciliationItem, one per Inventory row with a product.
        Sorted by abs(drift) descending so the worst offenders are first.
    """
    # ------------------------------------------------------------------
    # Step 1: pull all inventory rows with product data
    # ------------------------------------------------------------------
    from app.models.inventory import InventoryLocation

    inv_rows = (
        db.query(
            Inventory,
            Product,
            InventoryLocation.name.label("location_name"),
        )
        .join(Product, Inventory.product_id == Product.id)
        .outerjoin(InventoryLocation, Inventory.location_id == InventoryLocation.id)
        .all()
    )

    if not inv_rows:
        return []

    # ------------------------------------------------------------------
    # Step 2: build a single aggregation query for all (product, location)
    # pairs that appear in our inventory set.
    # We run one query instead of N to keep this O(1) DB round-trips.
    # ------------------------------------------------------------------
    # We need per-(product_id, location_id, epoch) sums.  Because the
    # epoch varies per row we cannot push the epoch filter into a single
    # SQL GROUP BY.  Strategy: pull all non-excluded transaction rows for
    # the products we care about, then aggregate in Python.  Transaction
    # tables in typical deployments are small enough for this to be fine;
    # if they grow large the natural optimisation is a partial index on
    # (product_id, location_id, created_at).

    product_ids = [r.Inventory.product_id for r in inv_rows]

    # Fetch: only rows with a non-NULL location AND not pending-approval.
    txn_rows = (
        db.query(
            InventoryTransaction.product_id,
            InventoryTransaction.location_id,
            InventoryTransaction.quantity,
            InventoryTransaction.created_at,
        )
        .filter(
            InventoryTransaction.product_id.in_(product_ids),
            InventoryTransaction.location_id.isnot(None),   # exclude untracked spool-weight rows
            InventoryTransaction.requires_approval.is_(False),  # exclude unapproved pending rows
        )
        .all()
    )

    # Index by (product_id, location_id) -> list of (quantity, created_at)
    txn_index: dict[tuple, list] = defaultdict(list)
    for row in txn_rows:
        txn_index[(row.product_id, row.location_id)].append(
            (Decimal(str(row.quantity)), row.created_at)
        )

    # ------------------------------------------------------------------
    # Step 3: assemble report rows
    # ------------------------------------------------------------------
    report: List[ReconciliationItem] = []

    for r in inv_rows:
        inv = r.Inventory
        prod = r.Product

        stored = Decimal(str(inv.on_hand_quantity or 0))
        baseline_ts = inv.baseline_timestamp
        is_counted = baseline_ts is not None

        key = (inv.product_id, inv.location_id)
        txns_for_item = txn_index.get(key, [])

        if is_counted:
            # Ensure baseline_ts is timezone-aware for comparison
            if baseline_ts.tzinfo is None:
                baseline_ts = baseline_ts.replace(tzinfo=timezone.utc)

            # Sum only transactions STRICTLY AFTER the baseline.
            # The epoch opening balance is baseline_on_hand (the physically
            # counted quantity snapshotted at the moment of the last baseline).
            # For rows that have baseline_on_hand NULL (pre-4c baselines or
            # rows created before this column was added), we fall back to
            # summing transactions at-or-after the baseline (old formula).
            baseline_on_hand = (
                Decimal(str(inv.baseline_on_hand))
                if inv.baseline_on_hand is not None
                else None
            )

            if baseline_on_hand is not None:
                # New formula: opening_balance + post-baseline movement
                post_baseline_sum = Decimal("0")
                for qty, created_at in txns_for_item:
                    if created_at is None:
                        continue
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    # Strictly AFTER the baseline timestamp to avoid double-
                    # counting the baseline transaction itself (which already
                    # is captured in baseline_on_hand).
                    if created_at > baseline_ts:
                        post_baseline_sum += qty
                ledger_sum = baseline_on_hand + post_baseline_sum
            else:
                # Legacy fallback: at-or-after (old behaviour pre-4c)
                ledger_sum = Decimal("0")
                for qty, created_at in txns_for_item:
                    if created_at is None:
                        continue
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                    if created_at >= baseline_ts:
                        ledger_sum += qty
        else:
            # NULL baseline: sum ALL transactions
            ledger_sum = sum(
                (qty for qty, _ in txns_for_item),
                Decimal("0"),
            )

        drift = stored - ledger_sum

        item = ReconciliationItem(
            inventory_id=inv.id,
            product_id=prod.id,
            sku=prod.sku,
            name=prod.name,
            location_id=inv.location_id,
            location_name=r.location_name,
            stored_on_hand=stored,
            ledger_sum=ledger_sum,
            drift=drift,
            baseline_timestamp=inv.baseline_timestamp,
            is_counted=is_counted,
        )
        report.append(item)

    if drifted_only:
        report = [r for r in report if r.has_drift]

    # Sort: worst absolute drift first, then uncounted last within each tier
    report.sort(key=lambda r: (-abs(r.drift), r.is_counted, r.sku))

    logger.debug(
        "Reconciliation report: %d rows total, %d drifted, %d uncounted",
        len(report),
        sum(1 for r in report if r.has_drift),
        sum(1 for r in report if not r.is_counted),
    )

    return report


# ---------------------------------------------------------------------------
# HARD-4c: baseline posting
# ---------------------------------------------------------------------------

def post_reconciliation_baseline(
    db: Session,
    *,
    product_id: int,
    location_id: int,
    counted_qty: Decimal,
    user: str,
    notes: Optional[str] = None,
) -> InventoryTransaction | None:
    """Post a reconciliation_baseline transaction and stamp the epoch.

    This is the physical-count entry point for HARD-4c.  The function:

      1. Acquires a FOR UPDATE lock on the Inventory row so the read of
         ``stored`` and the ledger write are serialised under one lock.
      2. Computes ``delta = counted_qty - stored_at_lock_time``.
      3. If delta != 0: posts through inventory_ledger.post with
         transaction_type="reconciliation" and
         reason_code="reconciliation_baseline", then creates the matching
         GL journal entry (DR/CR 1200 Inventory vs 5030 Inventory
         Adjustment, by delta sign -- identical to cycle-count variance).
      4. Whether or not delta is zero, stamps
         ``Inventory.baseline_timestamp`` to the transaction timestamp
         (or NOW for zero-delta) in the SAME flush.

    The session is NOT committed here -- that is the caller's responsibility.

    Args:
        db: SQLAlchemy session.
        product_id: Product to count.
        location_id: Location being counted.
        counted_qty: Physically counted quantity (Decimal, >= 0).
        user: Staff username / email for audit trail.
        notes: Optional operator note (e.g. "shelf count 2026-06-10").

    Returns:
        The InventoryTransaction row if a ledger post was made (delta != 0),
        or None if delta was zero (baseline_timestamp still stamped).

    Raises:
        TypeError: if counted_qty is a float.
        ValueError: if counted_qty is negative.
    """
    if isinstance(counted_qty, float):
        raise TypeError(
            "post_reconciliation_baseline requires Decimal counted_qty, got float"
        )
    counted_qty = Decimal(str(counted_qty))
    if counted_qty < 0:
        raise ValueError(f"counted_qty must be >= 0, got {counted_qty}")

    # --- Step 1: lock the inventory row and read stored qty ---
    from app.services.inventory_ledger import get_or_create_inventory_row

    inventory = get_or_create_inventory_row(db, product_id, location_id)
    stored = Decimal(str(inventory.on_hand_quantity or 0))

    delta = counted_qty - stored

    now = datetime.now(timezone.utc)
    txn: InventoryTransaction | None = None

    if delta != 0:
        # --- Step 2: post the ledger row ---
        from app.services.inventory_ledger import post as ledger_post
        from app.models.product import Product as ProductModel
        from app.services.transaction_service import TransactionService

        txn = ledger_post(
            db,
            product_id=product_id,
            location_id=location_id,
            transaction_type="reconciliation",
            quantity_delta=delta,
            reason_code="reconciliation_baseline",
            notes=notes or f"Physical count: {counted_qty}",
            created_by=user,
        )
        # Use the transaction's created_at as the epoch anchor.
        now = txn.created_at  # type: ignore[assignment]

        # --- Step 3: post GL entry (cycle-count variance semantics) ---
        product = db.get(ProductModel, product_id)
        if product is not None:
            unit_cost = (
                product.standard_cost
                if product.standard_cost is not None
                else (
                    product.average_cost
                    if product.average_cost is not None
                    else Decimal("0")
                )
            )
            total_cost = abs(delta) * unit_cost

            # Map product type to inventory account (mirrors cycle_count_adjustment)
            inv_account = "1200"
            if product.item_type == "finished_good":
                inv_account = "1220"
            elif product.item_type == "packaging":
                inv_account = "1230"

            if total_cost > 0:
                # overage (delta > 0): DR Inventory, CR Inv Adjustment
                # shortage (delta < 0): DR Inv Adjustment, CR Inventory
                if delta > 0:
                    je_lines = [
                        (inv_account, total_cost, "DR"),
                        ("5030", total_cost, "CR"),
                    ]
                else:
                    je_lines = [
                        ("5030", total_cost, "DR"),
                        (inv_account, total_cost, "CR"),
                    ]

                svc = TransactionService(db)
                je = svc.create_journal_entry(
                    description=f"Reconciliation baseline: {notes or 'physical count'}",
                    lines=je_lines,
                    source_type="adjustment",
                )
                txn.journal_entry_id = je.id

        logger.info(
            "Reconciliation baseline posted for product %s @ location %s: "
            "stored=%s counted=%s delta=%s by %s",
            product_id, location_id, stored, counted_qty, delta, user,
        )
    else:
        logger.info(
            "Reconciliation baseline: product %s @ location %s stored=%s "
            "matches count (delta=0) — no ledger row written, baseline stamped by %s",
            product_id, location_id, stored, user,
        )

    # --- Step 4: stamp baseline_timestamp + baseline_on_hand atomically ---
    # baseline_on_hand captures the physically counted quantity as the epoch
    # opening balance.  The reconciliation report uses:
    #   drift = stored - (baseline_on_hand + sum(post-baseline transactions))
    # so zero-delta counts correctly show drift=0 immediately after counting.
    inventory.baseline_timestamp = now
    inventory.baseline_on_hand = counted_qty
    db.flush()

    return txn


def baseline_to_stored(
    db: Session,
    *,
    product_id: int,
    location_id: int,
    user: str,
    confirm: str,
) -> None:
    """Stamp baseline_timestamp to NOW with zero delta (no ledger write).

    This is the EXPLICIT FALLBACK for dev/test/first-install scenarios where
    the stored on-hand value is accepted as the physical-count baseline
    without an actual count event.  Requires ``confirm="BASELINE_TO_STORED"``
    to prevent silent invocation.

    NO ledger row is written (delta = 0, nothing to record).  Only
    ``Inventory.baseline_timestamp`` is stamped.

    EXECUTION GATE: this function only stamps -- it does NOT execute any
    data repair against a real database.  Running the fallback against a
    production database requires explicit owner sign-off documented outside
    this call.

    Args:
        db: SQLAlchemy session.
        product_id: Product to baseline.
        location_id: Location to baseline.
        user: Staff username / email for audit trail.
        confirm: Must equal "BASELINE_TO_STORED" -- prevents accidental calls.

    Raises:
        ValueError: if confirm token is wrong.
    """
    if confirm != BASELINE_TO_STORED_CONFIRM_TOKEN:
        raise ValueError(
            f"Confirmation token required: pass confirm={BASELINE_TO_STORED_CONFIRM_TOKEN!r}"
        )

    from app.services.inventory_ledger import get_or_create_inventory_row

    inventory = get_or_create_inventory_row(db, product_id, location_id)
    stored = Decimal(str(inventory.on_hand_quantity or 0))
    now = datetime.now(timezone.utc)
    inventory.baseline_timestamp = now
    # Set baseline_on_hand to stored so the reconciliation report correctly
    # shows drift=0 immediately after the fallback.
    inventory.baseline_on_hand = stored
    db.flush()

    logger.info(
        "baseline_to_stored: stamped product %s @ location %s to %s (on_hand=%s) "
        "by %s (no ledger row written)",
        product_id, location_id, now.isoformat(), stored, user,
    )
