"""
Tests for the inventory reconciliation report (HARD-4b).

Scenarios:
  1. Item with NULL baseline → sums ALL transactions, shows as uncounted.
  2. Item with a baseline_timestamp → sums ONLY post-baseline transactions.
  3. Item with deliberate drift (stored_on_hand != ledger_sum).
  4. location_id IS NULL transactions are excluded from sums.
  5. requires_approval=True (pending) rows are excluded from sums.
  6. drifted_only filter.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from app.models.inventory import Inventory, InventoryTransaction
from app.services.inventory_ledger import get_or_create_inventory_row
from app.services.reconciliation_service import get_reconciliation_report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_inventory(db, product, location, on_hand: Decimal, baseline_ts=None):
    """Create an Inventory row directly (bypassing the poster to simulate drift)."""
    inv = Inventory(
        product_id=product.id,
        location_id=location.id,
        on_hand_quantity=on_hand,
        allocated_quantity=Decimal("0"),
        baseline_timestamp=baseline_ts,
    )
    db.add(inv)
    db.flush()
    return inv


def _make_txn(db, product, location_id, quantity: Decimal, created_at=None, requires_approval=False):
    """Write a raw InventoryTransaction without touching on_hand (simulates pre-4a rows)."""
    txn = InventoryTransaction(
        product_id=product.id,
        location_id=location_id,
        transaction_type="adjustment",
        quantity=quantity,
        created_at=created_at or datetime.now(timezone.utc),
        requires_approval=requires_approval,
    )
    db.add(txn)
    db.flush()
    return txn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestNullBaseline:
    """NULL baseline: sums ALL transactions, classified as uncounted."""

    def test_sums_all_transactions(self, db, make_product, location):
        product = make_product()
        _make_inventory(db, product, location, Decimal("0"))

        # Three transactions at different times
        t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t1 = datetime(2026, 3, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 6, 1, tzinfo=timezone.utc)
        _make_txn(db, product, location.id, Decimal("100"), created_at=t0)
        _make_txn(db, product, location.id, Decimal("-30"), created_at=t1)
        _make_txn(db, product, location.id, Decimal("50"), created_at=t2)

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.is_counted is False
        assert row.baseline_timestamp is None
        assert row.ledger_sum == Decimal("120")  # 100 - 30 + 50

    def test_zero_transactions_gives_ledger_zero(self, db, make_product, location):
        product = make_product()
        _make_inventory(db, product, location, Decimal("50"))

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.ledger_sum == Decimal("0")
        assert row.drift == Decimal("50")  # stored 50, ledger 0


class TestBaselinedItem:
    """Non-NULL baseline: only post-baseline transactions count."""

    def test_pre_baseline_transactions_excluded(self, db, make_product, location):
        product = make_product()
        baseline_ts = datetime(2026, 4, 1, tzinfo=timezone.utc)

        _make_inventory(db, product, location, Decimal("80"), baseline_ts=baseline_ts)

        # Pre-baseline (should be ignored)
        _make_txn(db, product, location.id, Decimal("500"), created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        # Post-baseline (should be counted)
        _make_txn(db, product, location.id, Decimal("80"), created_at=datetime(2026, 5, 1, tzinfo=timezone.utc))

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.is_counted is True
        assert row.ledger_sum == Decimal("80")  # only post-baseline

    def test_exactly_at_baseline_included(self, db, make_product, location):
        product = make_product()
        baseline_ts = datetime(2026, 4, 1, tzinfo=timezone.utc)

        _make_inventory(db, product, location, Decimal("20"), baseline_ts=baseline_ts)
        # Created exactly AT baseline_ts — should be included (>=)
        _make_txn(db, product, location.id, Decimal("20"), created_at=baseline_ts)

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.ledger_sum == Decimal("20")
        assert row.drift == Decimal("0")


class TestDrift:
    """Deliberate drift: stored_on_hand != ledger_sum."""

    def test_positive_drift_phantom_stock(self, db, make_product, location):
        """Stored is higher than ledger → phantom stock."""
        product = make_product()
        _make_inventory(db, product, location, Decimal("140"))  # stored

        _make_txn(db, product, location.id, Decimal("100"))  # ledger says +100
        _make_txn(db, product, location.id, Decimal("-8"))    # ledger says -8 → net 92

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.stored_on_hand == Decimal("140")
        assert row.ledger_sum == Decimal("92")
        assert row.drift == Decimal("48")
        assert row.has_drift is True

    def test_negative_drift_missing_transactions(self, db, make_product, location):
        """Stored is lower than ledger → unrecorded consumption."""
        product = make_product()
        _make_inventory(db, product, location, Decimal("50"))  # stored

        _make_txn(db, product, location.id, Decimal("100"))
        # ledger says net 100, stored only 50

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.drift == Decimal("-50")

    def test_no_drift_when_balanced(self, db, make_product, location):
        product = make_product()
        _make_inventory(db, product, location, Decimal("70"))

        _make_txn(db, product, location.id, Decimal("100"))
        _make_txn(db, product, location.id, Decimal("-30"))

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.drift == Decimal("0")
        assert row.has_drift is False


class TestLocationNullExclusion:
    """Transactions with location_id IS NULL (untracked spool-weight rows) must be excluded."""

    def test_null_location_txn_excluded(self, db, make_product, location):
        product = make_product()
        _make_inventory(db, product, location, Decimal("100"))

        # This transaction has location_id=None → must NOT be summed
        _make_txn(db, product, None, Decimal("999"))
        # This one has a real location → included
        _make_txn(db, product, location.id, Decimal("100"))

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.ledger_sum == Decimal("100")  # 999 excluded, only 100 counted
        assert row.drift == Decimal("0")


class TestApprovalExclusion:
    """requires_approval=True rows not yet approved must be excluded."""

    def test_pending_approval_row_excluded(self, db, make_product, location):
        product = make_product()
        _make_inventory(db, product, location, Decimal("50"))

        # Approved row → included
        _make_txn(db, product, location.id, Decimal("50"), requires_approval=False)
        # Pending row → excluded (on_hand not yet affected)
        _make_txn(db, product, location.id, Decimal("-200"), requires_approval=True)

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.ledger_sum == Decimal("50")
        assert row.drift == Decimal("0")


class TestDriftedOnlyFilter:
    """drifted_only=True excludes balanced items."""

    def test_balanced_items_excluded(self, db, make_product, location):
        drifted = make_product()
        balanced = make_product()

        _make_inventory(db, drifted, location, Decimal("100"))
        _make_txn(db, drifted, location.id, Decimal("50"))  # drift=50

        _make_inventory(db, balanced, location, Decimal("75"))
        _make_txn(db, balanced, location.id, Decimal("75"))  # drift=0

        report = get_reconciliation_report(db, drifted_only=True)
        ids = {r.product_id for r in report}

        assert drifted.id in ids
        assert balanced.id not in ids
