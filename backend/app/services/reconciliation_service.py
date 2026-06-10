"""
Inventory reconciliation report (HARD-4b).

Computes, per Inventory row, the divergence between:
  - stored ``Inventory.on_hand_quantity``  (the running balance maintained by
    inventory_ledger.post)
  - Σ(InventoryTransaction.quantity) filtered to the item's epoch

EPOCH SEMANTICS
---------------
``Inventory.baseline_timestamp`` (added by migration 086) anchors the epoch.

  NULL baseline  → item has never been physically counted.  The report sums
                   ALL non-excluded transactions from the dawn of time and
                   classifies the item as ``uncounted``.

  Non-NULL       → item has been counted at least once.  Only transactions
                   with ``created_at >= baseline_timestamp`` are summed.

SIGN CONVENTION (HARD-4a)
--------------------------
inventory_ledger.post() writes SIGNED quantities: positive = stock in,
negative = stock out.  So ``Σ(quantity)`` IS the expected on-hand for the
epoch.  Pre-4a rows used mixed conventions (positive magnitudes); the plan
documents abs() as the migration-safe reader fix.  However, for
RECONCILIATION the meaningful comparison is:

    drift = stored_on_hand − ledger_sum_for_epoch

A non-zero drift for a fully-4a-posted item means a SET-style write happened
outside the poster.  The absolute value of drift signals how far off counts
are without requiring ABS() on the sum — callers see both stored_on_hand and
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
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.models.inventory import Inventory, InventoryTransaction
from app.models.product import Product
from app.logging_config import get_logger

logger = get_logger(__name__)


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
    ledger_sum: Decimal          # Σ(quantity) for the epoch (may be 0 if no txns)
    drift: Decimal               # stored_on_hand − ledger_sum

    # Epoch anchor
    baseline_timestamp: Optional[datetime]  # None → uncounted

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
        db: SQLAlchemy session (read-only — no writes).
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

    # Index by (product_id, location_id) → list of (quantity, created_at)
    from collections import defaultdict
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

            # Sum only transactions at-or-after the baseline
            ledger_sum = Decimal("0")
            for qty, created_at in txns_for_item:
                if created_at is None:
                    continue
                # Normalise created_at tz
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
