"""
Tests for the inventory reconciliation report (HARD-4b) and baseline
posting (HARD-4c).

Scenarios:
  1. Item with NULL baseline -> sums ALL transactions, shows as uncounted.
  2. Item with a baseline_timestamp -> sums ONLY post-baseline transactions.
  3. Item with deliberate drift (stored_on_hand != ledger_sum).
  4. location_id IS NULL transactions are excluded from sums.
  5. requires_approval=True (pending) rows are excluded from sums.
  6. drifted_only filter.
  7. post_reconciliation_baseline posts exactly one ledger row (non-zero delta).
  8. post_reconciliation_baseline stamps baseline_timestamp atomically.
  9. post_reconciliation_baseline creates a balanced GL journal entry.
 10. Recount (second baseline) updates baseline_timestamp.
 11. Zero-delta count stamps baseline_timestamp without writing a ledger row.
 12. baseline_to_stored stamps with zero-delta row (no ledger write).
 13. Report shows item as counted+clean after a matching count.
 14. Uncounted item is unaffected by another item's baseline.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.inventory import Inventory, InventoryTransaction
from app.services.reconciliation_service import (
    BASELINE_TO_STORED_CONFIRM_TOKEN,
    baseline_to_stored,
    get_reconciliation_report,
    post_reconciliation_baseline,
)


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
# HARD-4b: Reconciliation Report Tests
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
        # Created exactly AT baseline_ts -- should be included (>=)
        _make_txn(db, product, location.id, Decimal("20"), created_at=baseline_ts)

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.ledger_sum == Decimal("20")
        assert row.drift == Decimal("0")


class TestDrift:
    """Deliberate drift: stored_on_hand != ledger_sum."""

    def test_positive_drift_phantom_stock(self, db, make_product, location):
        """Stored is higher than ledger -> phantom stock."""
        product = make_product()
        _make_inventory(db, product, location, Decimal("140"))  # stored

        _make_txn(db, product, location.id, Decimal("100"))  # ledger says +100
        _make_txn(db, product, location.id, Decimal("-8"))    # ledger says -8 -> net 92

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.stored_on_hand == Decimal("140")
        assert row.ledger_sum == Decimal("92")
        assert row.drift == Decimal("48")
        assert row.has_drift is True

    def test_negative_drift_missing_transactions(self, db, make_product, location):
        """Stored is lower than ledger -> unrecorded consumption."""
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

        # This transaction has location_id=None -> must NOT be summed
        _make_txn(db, product, None, Decimal("999"))
        # This one has a real location -> included
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

        # Approved row -> included
        _make_txn(db, product, location.id, Decimal("50"), requires_approval=False)
        # Pending row -> excluded (on_hand not yet affected)
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


# ---------------------------------------------------------------------------
# HARD-4c: Baseline Posting Tests
# ---------------------------------------------------------------------------

class TestPostReconciliationBaseline:
    """post_reconciliation_baseline core behaviour."""

    def test_posts_exactly_one_ledger_row_nonzero_delta(self, db, make_product, location):
        """Non-zero delta posts exactly one InventoryTransaction row."""
        product = make_product(standard_cost=Decimal("2.00"))
        # Seed inventory via ledger to get a known stored value
        from app.services.inventory_ledger import post as ledger_post
        ledger_post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("100"),
        )
        # Stored is now 100; count says 110 -> delta = +10
        before_count = (
            db.query(InventoryTransaction)
            .filter(InventoryTransaction.product_id == product.id)
            .count()
        )

        txn = post_reconciliation_baseline(
            db,
            product_id=product.id,
            location_id=location.id,
            counted_qty=Decimal("110"),
            user="test@example.com",
        )

        after_count = (
            db.query(InventoryTransaction)
            .filter(InventoryTransaction.product_id == product.id)
            .count()
        )

        assert txn is not None
        assert after_count == before_count + 1, "exactly one ledger row added"
        assert txn.transaction_type == "reconciliation"
        assert txn.reason_code == "reconciliation_baseline"
        assert Decimal(str(txn.quantity)) == Decimal("10")  # delta +10

    def test_stamps_baseline_timestamp_atomically(self, db, make_product, location):
        """baseline_timestamp is set in the same flush as the ledger row."""
        product = make_product()
        from app.services.inventory_ledger import post as ledger_post
        ledger_post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("50"),
        )

        txn = post_reconciliation_baseline(
            db,
            product_id=product.id,
            location_id=location.id,
            counted_qty=Decimal("60"),
            user="counter@example.com",
        )

        inv = (
            db.query(Inventory)
            .filter(
                Inventory.product_id == product.id,
                Inventory.location_id == location.id,
            )
            .first()
        )
        assert inv is not None
        assert inv.baseline_timestamp is not None
        assert txn is not None
        # Baseline timestamp should equal the transaction's created_at (or very close)
        # They are set to the same 'now' inside the service
        assert abs((inv.baseline_timestamp - txn.created_at).total_seconds()) < 1

    def test_gl_entry_is_balanced(self, db, make_product, location):
        """GL journal entry DR == CR for both overage and shortage."""
        from app.models.accounting import GLJournalEntry, GLJournalEntryLine
        from app.services.inventory_ledger import post as ledger_post
        from decimal import Decimal as D

        product = make_product(
            item_type="finished_good",
            standard_cost=D("5.00"),
        )
        ledger_post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=D("100"),
        )

        # Overage: count says 120, stored 100, delta +20, cost = 20 * 5 = 100
        txn = post_reconciliation_baseline(
            db,
            product_id=product.id,
            location_id=location.id,
            counted_qty=D("120"),
            user="counter@example.com",
        )

        assert txn is not None
        assert txn.journal_entry_id is not None

        je = db.get(GLJournalEntry, txn.journal_entry_id)
        assert je is not None
        lines = (
            db.query(GLJournalEntryLine)
            .filter(GLJournalEntryLine.journal_entry_id == je.id)
            .all()
        )
        total_dr = sum(line.debit_amount or D("0") for line in lines)
        total_cr = sum(line.credit_amount or D("0") for line in lines)
        assert abs(total_dr - total_cr) <= D("0.01"), (
            f"Journal entry not balanced: DR={total_dr} CR={total_cr}"
        )

    def test_recount_updates_baseline_timestamp(self, db, make_product, location):
        """A second count updates baseline_timestamp to the new count time."""
        from app.services.inventory_ledger import post as ledger_post

        product = make_product()
        ledger_post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("100"),
        )

        post_reconciliation_baseline(
            db,
            product_id=product.id,
            location_id=location.id,
            counted_qty=Decimal("100"),  # zero delta -- baseline stamped
            user="counter@example.com",
        )
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.product_id == product.id,
                Inventory.location_id == location.id,
            )
            .first()
        )
        first_ts = inv.baseline_timestamp
        assert first_ts is not None

        import time
        time.sleep(0.01)  # ensure timestamp advances

        post_reconciliation_baseline(
            db,
            product_id=product.id,
            location_id=location.id,
            counted_qty=Decimal("95"),
            user="counter@example.com",
            notes="second count",
        )
        db.refresh(inv)
        second_ts = inv.baseline_timestamp
        assert second_ts is not None
        assert second_ts >= first_ts

    def test_zero_delta_stamps_baseline_no_ledger_row(self, db, make_product, location):
        """Zero delta: baseline_timestamp is stamped but no ledger row is written."""
        from app.services.inventory_ledger import post as ledger_post

        product = make_product()
        ledger_post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("75"),
        )
        before_count = (
            db.query(InventoryTransaction)
            .filter(InventoryTransaction.product_id == product.id)
            .count()
        )

        result = post_reconciliation_baseline(
            db,
            product_id=product.id,
            location_id=location.id,
            counted_qty=Decimal("75"),  # exact match -> delta 0
            user="counter@example.com",
        )

        after_count = (
            db.query(InventoryTransaction)
            .filter(InventoryTransaction.product_id == product.id)
            .count()
        )
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.product_id == product.id,
                Inventory.location_id == location.id,
            )
            .first()
        )

        assert result is None, "no transaction for zero delta"
        assert after_count == before_count, "no ledger row added"
        assert inv.baseline_timestamp is not None, "baseline still stamped"

    def test_float_counted_qty_raises_type_error(self, db, make_product, location):
        """float counted_qty is rejected with TypeError."""
        product = make_product()
        with pytest.raises(TypeError, match="Decimal"):
            post_reconciliation_baseline(
                db,
                product_id=product.id,
                location_id=location.id,
                counted_qty=100.0,  # float -- should raise
                user="counter@example.com",
            )

    def test_negative_counted_qty_raises_value_error(self, db, make_product, location):
        """Negative counted_qty is rejected."""
        product = make_product()
        with pytest.raises(ValueError, match=">= 0"):
            post_reconciliation_baseline(
                db,
                product_id=product.id,
                location_id=location.id,
                counted_qty=Decimal("-1"),
                user="counter@example.com",
            )


class TestReportAfterBaseline:
    """Report reflects counted status correctly after baseline posting."""

    def test_report_shows_item_as_counted_after_count(self, db, make_product, location):
        """After a count entry, item is_counted=True and has_drift=False (exact count)."""
        from app.services.inventory_ledger import post as ledger_post

        product = make_product()
        ledger_post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("200"),
        )

        post_reconciliation_baseline(
            db,
            product_id=product.id,
            location_id=location.id,
            counted_qty=Decimal("200"),  # exact match
            user="counter@example.com",
        )

        report = get_reconciliation_report(db)
        row = next((r for r in report if r.product_id == product.id), None)

        assert row is not None
        assert row.is_counted is True
        assert row.has_drift is False

    def test_uncounted_item_unaffected_by_another_items_baseline(
        self, db, make_product, location
    ):
        """Counting one item does NOT change another item's uncounted status."""
        from app.services.inventory_ledger import post as ledger_post

        counted_product = make_product()
        uncounted_product = make_product()

        for p in (counted_product, uncounted_product):
            ledger_post(
                db, product_id=p.id, location_id=location.id,
                transaction_type="receipt", quantity_delta=Decimal("50"),
            )

        post_reconciliation_baseline(
            db,
            product_id=counted_product.id,
            location_id=location.id,
            counted_qty=Decimal("50"),
            user="counter@example.com",
        )

        report = get_reconciliation_report(db)
        counted_row = next((r for r in report if r.product_id == counted_product.id), None)
        uncounted_row = next((r for r in report if r.product_id == uncounted_product.id), None)

        assert counted_row is not None and counted_row.is_counted is True
        assert uncounted_row is not None and uncounted_row.is_counted is False


class TestBaselineToStored:
    """baseline_to_stored: stamps timestamp, no ledger writes."""

    def test_stamps_baseline_with_zero_delta_no_ledger_row(self, db, make_product, location):
        """baseline_to_stored stamps baseline_timestamp; no InventoryTransaction written."""
        from app.services.inventory_ledger import post as ledger_post

        product = make_product()
        ledger_post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("30"),
        )
        before_count = (
            db.query(InventoryTransaction)
            .filter(InventoryTransaction.product_id == product.id)
            .count()
        )

        baseline_to_stored(
            db,
            product_id=product.id,
            location_id=location.id,
            user="admin@example.com",
            confirm=BASELINE_TO_STORED_CONFIRM_TOKEN,
        )

        after_count = (
            db.query(InventoryTransaction)
            .filter(InventoryTransaction.product_id == product.id)
            .count()
        )
        inv = (
            db.query(Inventory)
            .filter(
                Inventory.product_id == product.id,
                Inventory.location_id == location.id,
            )
            .first()
        )

        assert after_count == before_count, "no ledger row written by fallback"
        assert inv.baseline_timestamp is not None, "baseline_timestamp stamped"

    def test_wrong_confirm_token_raises(self, db, make_product, location):
        """Wrong confirm token raises ValueError."""
        product = make_product()
        with pytest.raises(ValueError, match="BASELINE_TO_STORED"):
            baseline_to_stored(
                db,
                product_id=product.id,
                location_id=location.id,
                user="admin@example.com",
                confirm="wrong-token",
            )


class TestZeroCostGLEntry:
    """Regression: product with standard_cost=0 must NOT fall through to average_cost."""

    def test_zero_standard_cost_uses_zero_not_average(self, db, make_product, location):
        """
        A product with standard_cost=Decimal("0") and average_cost=Decimal("5")
        must post a GL entry priced at 0, not 5.

        The old ``or`` chain treated Decimal("0") as falsy and wrongly fell
        through to average_cost, posting an incorrect GL amount.
        """
        from app.models.accounting import GLJournalEntry, GLJournalEntryLine
        from app.services.inventory_ledger import post as ledger_post

        product = make_product(
            standard_cost=Decimal("0"),
            average_cost=Decimal("5.00"),
        )
        # Seed 100 units so a count of 110 gives delta +10
        ledger_post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("100"),
        )

        txn = post_reconciliation_baseline(
            db,
            product_id=product.id,
            location_id=location.id,
            counted_qty=Decimal("110"),  # delta +10
            user="counter@example.com",
        )

        # With standard_cost=0 the GL total_cost = 10 * 0 = 0, so no entry is written
        # (the service skips the GL block when total_cost == 0).
        # Crucially it must NOT use average_cost=5 (which would give total_cost=50).
        assert txn is not None

        if txn.journal_entry_id is not None:
            je = db.get(GLJournalEntry, txn.journal_entry_id)
            assert je is not None
            lines = (
                db.query(GLJournalEntryLine)
                .filter(GLJournalEntryLine.journal_entry_id == je.id)
                .all()
            )
            total_dr = sum(line.debit_amount or Decimal("0") for line in lines)
            # If a GL entry was posted it must be for 0-cost math (total_cost=0),
            # meaning no lines with non-zero amounts.
            assert total_dr == Decimal("0"), (
                f"Expected zero-cost GL (standard_cost=0) but got DR={total_dr}; "
                "average_cost fallthrough regression detected."
            )
        # If journal_entry_id is None the service correctly skipped the GL block
        # because total_cost was 0 — that is the expected happy path.
