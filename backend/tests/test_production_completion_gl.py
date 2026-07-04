"""
Tests for the #880 production-completion GL poster.

Covers:
- production_gl_service.create_production_completion_gl_entry (the sweep
  poster: DR 1210 / CR 1200|1230|5100, DR 1220 / CR 1210, 5200 variance)
- its two call sites (process_production_completion via
  complete_production_order, and accept_short_production_order)
- sweep idempotency (re-run no-op; per-op consumption + completion posts
  each transaction exactly once)
- the load-bearing "no source-existence check" contract: a prior scrap
  journal entry with the SAME source_type/source_id must NOT block the
  completion entry, and the S term makes 1210 net to zero
- abs() valuation of legacy positive-quantity consumption rows
- component-aware credits (packaging -> 1230, SVC- labor -> 5100)
- the GL-health counter on the accounting dashboard
- the backfill script (dry-run, backup-marker gate, apply -> manifest ->
  rollback round-trip)

All tests are delta-based with per-run unique fixtures (uuid SKUs/codes
from the conftest factories) because filaops_test accumulates state.
"""
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.models.inventory import InventoryTransaction
from app.services import inventory_service
from app.services.production_gl_service import (
    create_production_completion_gl_entry,
)
from app.services.transaction_service import TransactionService

# Make backend/scripts importable for the backfill-script tests.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import backfill_production_completion_gl as backfill  # noqa: E402


# =============================================================================
# Helpers
# =============================================================================

def _location(db):
    return inventory_service.get_or_create_default_location(db)


def _seed_stock(db, product, qty, cost):
    """Give a product on-hand stock so consumption is not held for approval."""
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="receipt",
        quantity=Decimal(str(qty)),
        reference_type="test_seed",
        reference_id=0,
        cost_per_unit=Decimal(str(cost)),
    )


def _consume(db, product, po, qty, cost):
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="consumption",
        quantity=Decimal(str(qty)),
        reference_type="production_order",
        reference_id=po.id,
        cost_per_unit=Decimal(str(cost)),
    )


def _receive_fg(db, product, po, qty, cost):
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="receipt",
        quantity=Decimal(str(qty)),
        reference_type="production_order",
        reference_id=po.id,
        cost_per_unit=Decimal(str(cost)),
    )


def _completion_entries(db, po):
    return db.query(GLJournalEntry).filter(
        GLJournalEntry.source_type == "production_order",
        GLJournalEntry.source_id == po.id,
        GLJournalEntry.description.like("Production completion%"),
    ).all()


def _je_net(db, je):
    """account_code -> net (DR - CR) for one journal entry."""
    net = defaultdict(lambda: Decimal("0"))
    rows = (
        db.query(
            GLAccount.account_code,
            GLJournalEntryLine.debit_amount,
            GLJournalEntryLine.credit_amount,
        )
        .join(GLJournalEntryLine, GLJournalEntryLine.account_id == GLAccount.id)
        .filter(GLJournalEntryLine.journal_entry_id == je.id)
        .all()
    )
    for code, debit, credit in rows:
        net[code] += Decimal(str(debit or 0)) - Decimal(str(credit or 0))
    return net


def _wip_net_across_po_entries(db, po):
    """Net 1210 (DR - CR) across ALL non-voided entries for this PO."""
    rows = (
        db.query(GLJournalEntryLine.debit_amount, GLJournalEntryLine.credit_amount)
        .join(GLJournalEntry, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id)
        .join(GLAccount, GLJournalEntryLine.account_id == GLAccount.id)
        .filter(
            GLJournalEntry.source_type == "production_order",
            GLJournalEntry.source_id == po.id,
            GLJournalEntry.status != "voided",
            GLAccount.account_code == "1210",
        )
        .all()
    )
    total = Decimal("0")
    for debit, credit in rows:
        total += Decimal(str(debit or 0)) - Decimal(str(credit or 0))
    return total


def _po_txns(db, po, types=("consumption", "receipt")):
    return db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.reference_id == po.id,
        InventoryTransaction.transaction_type.in_(types),
    ).all()


# =============================================================================
# The poster
# =============================================================================

class TestCompletionGLPoster:

    def test_posts_basic_completion_entry_and_links_txns(
        self, db, make_product, make_production_order
    ):
        raw = make_product(item_type="supply", average_cost=Decimal("0.50"))
        fg = make_product(item_type="finished_good", average_cost=Decimal("2.00"))
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=5)

        _seed_stock(db, raw, 100, "0.50")
        _consume(db, raw, po, 10, "0.50")       # 5.00 materials
        _receive_fg(db, fg, po, 5, "2.00")      # 10.00 FG

        je = create_production_completion_gl_entry(db, po)

        assert je is not None
        assert je.description == f"Production completion for PO#{po.code}"
        assert je.source_type == "production_order"
        assert je.source_id == po.id
        assert je.status == "posted"
        assert je.entry_date == date.today()

        net = _je_net(db, je)
        # DR 1210 5.00 / CR 1200 5.00; DR 1220 10 / CR 1210 10;
        # V = 10 - 5 = +5 -> DR 1210 5 / CR 5200 5  => 1210 nets to zero.
        assert net["1210"] == Decimal("0")
        assert net["1200"] == Decimal("-5.00")
        assert net["1220"] == Decimal("10.00")
        assert net["5200"] == Decimal("-5.00")

        # Every swept transaction is linked to the entry.
        for txn in _po_txns(db, po):
            assert txn.journal_entry_id == je.id

    def test_rerun_is_noop(self, db, make_product, make_production_order):
        raw = make_product(item_type="supply")
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)

        _seed_stock(db, raw, 10, "1.00")
        _consume(db, raw, po, 2, "1.00")
        _receive_fg(db, fg, po, 1, "3.00")

        first = create_production_completion_gl_entry(db, po)
        assert first is not None

        second = create_production_completion_gl_entry(db, po)
        assert second is None
        assert len(_completion_entries(db, po)) == 1

    def test_no_sweepable_rows_returns_none(self, db, make_product, make_production_order):
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)
        assert create_production_completion_gl_entry(db, po) is None
        assert _completion_entries(db, po) == []

    def test_prior_scrap_je_does_not_block_and_s_term_zeroes_wip(
        self, db, make_product, make_production_order
    ):
        """LOAD-BEARING: scrap journal entries share source_type=
        'production_order' AND the same source_id. The poster must not use a
        source-existence idempotency check, or a mid-order scrap would
        silently suppress the completion entry. The S term must offset the
        scrap entry's 1210 credit so WIP nets to exactly zero for the PO."""
        raw = make_product(item_type="supply", average_cost=Decimal("0.50"))
        fg = make_product(item_type="finished_good", average_cost=Decimal("2.00"))
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=4)

        _seed_stock(db, raw, 50, "0.50")
        _consume(db, raw, po, 20, "0.50")       # M = 10.00

        # Mid-order operation scrap: DR 5020 / CR 1210 for 1.00, with
        # source_type='production_order' and source_id=po.id.
        ts = TransactionService(db)
        _, scrap_je, _ = ts.scrap_materials(
            production_order_id=po.id,
            operation_sequence=10,
            product_id=raw.id,
            quantity=Decimal("2"),
            unit_cost=Decimal("0.50"),
            reason_code="TEST-SCRAP",
            user_id=1,
        )
        assert scrap_je is not None
        assert scrap_je.source_type == "production_order"
        assert scrap_je.source_id == po.id

        _receive_fg(db, fg, po, 4, "2.00")      # FG = 8.00

        je = create_production_completion_gl_entry(db, po)

        # The completion entry posted DESPITE the existing scrap entry.
        assert je is not None
        assert je.id != scrap_je.id

        # S = 1.00, V = FG + S - M = 8 + 1 - 10 = -1 -> DR 5200 1 / CR 1210 1
        net = _je_net(db, je)
        assert net["1200"] == Decimal("-10.00")
        assert net["1220"] == Decimal("8.00")
        assert net["5200"] == Decimal("1.00")

        # WIP nets to exactly zero across scrap + completion entries.
        assert _wip_net_across_po_entries(db, po) == Decimal("0")

        # The scrap entry and its transaction link are untouched.
        db.refresh(scrap_je)
        assert scrap_je.status == "posted"

        # Re-run posts nothing (double-post is the highest-severity failure).
        assert create_production_completion_gl_entry(db, po) is None
        assert len(_completion_entries(db, po)) == 1

    def test_zero_consumption_completion_posts_fg_against_variance(
        self, db, make_product, make_production_order
    ):
        fg = make_product(item_type="finished_good", average_cost=Decimal("2.50"))
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=4)

        _receive_fg(db, fg, po, 4, "2.50")      # FG = 10.00, no consumption

        je = create_production_completion_gl_entry(db, po)

        assert je is not None
        net = _je_net(db, je)
        # Net effect DR 1220 / CR 5200; the 1210 legs cancel exactly.
        assert net["1220"] == Decimal("10.00")
        assert net["5200"] == Decimal("-10.00")
        assert net["1210"] == Decimal("0")
        assert net["1200"] == Decimal("0")

    def test_legacy_positive_quantity_consumption_valued_with_abs(
        self, db, make_product, make_production_order
    ):
        """Pre-HARD-4a rows store positive magnitudes for consumption (live
        txn ids 129/130). abs(qty) x cost_per_unit must value them correctly
        instead of flipping the sign."""
        raw = make_product(item_type="supply")
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)

        legacy = InventoryTransaction(
            product_id=raw.id,
            location_id=_location(db).id,
            transaction_type="consumption",
            quantity=Decimal("3"),          # POSITIVE legacy sign
            cost_per_unit=Decimal("0.10"),
            total_cost=None,                # force the abs(qty) x cpu path
            reference_type="production_order",
            reference_id=po.id,
        )
        db.add(legacy)
        db.flush()

        _receive_fg(db, fg, po, 1, "1.00")

        je = create_production_completion_gl_entry(db, po)

        assert je is not None
        net = _je_net(db, je)
        assert net["1200"] == Decimal("-0.30")
        # V = 1.00 - 0.30 = +0.70 credit to 5200
        assert net["5200"] == Decimal("-0.70")
        assert net["1210"] == Decimal("0")
        assert legacy.journal_entry_id == je.id

    def test_packaging_component_credits_1230(
        self, db, make_product, make_production_order
    ):
        raw = make_product(item_type="supply")
        box = make_product(item_type="packaging")
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=2)

        _seed_stock(db, raw, 100, "0.50")
        _seed_stock(db, box, 10, "1.50")
        _consume(db, raw, po, 10, "0.50")       # 5.00 -> CR 1200
        _consume(db, box, po, 2, "1.50")        # 3.00 -> CR 1230
        _receive_fg(db, fg, po, 2, "5.00")      # 10.00

        je = create_production_completion_gl_entry(db, po)

        assert je is not None
        net = _je_net(db, je)
        assert net["1200"] == Decimal("-5.00")
        assert net["1230"] == Decimal("-3.00")
        assert net["1220"] == Decimal("10.00")
        # V = 10 - 8 = +2 -> CR 5200
        assert net["5200"] == Decimal("-2.00")
        assert net["1210"] == Decimal("0")

    def test_svc_labor_row_credits_5100(
        self, db, make_product, make_production_order
    ):
        import uuid
        raw = make_product(item_type="supply")
        labor = make_product(
            sku=f"SVC-LABOR-{uuid.uuid4().hex[:8]}", item_type="service"
        )
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)

        _seed_stock(db, raw, 100, "0.50")
        _seed_stock(db, labor, 10, "5.00")
        _consume(db, raw, po, 4, "0.50")        # 2.00 -> CR 1200
        _consume(db, labor, po, 1, "5.00")      # 5.00 -> CR 5100
        _receive_fg(db, fg, po, 1, "8.00")      # 8.00

        je = create_production_completion_gl_entry(db, po)

        assert je is not None
        net = _je_net(db, je)
        assert net["1200"] == Decimal("-2.00")
        assert net["5100"] == Decimal("-5.00")
        assert net["1220"] == Decimal("8.00")
        # V = 8 - 7 = +1 -> CR 5200
        assert net["5200"] == Decimal("-1.00")
        assert net["1210"] == Decimal("0")

    def test_held_rows_are_not_swept(self, db, make_product, make_production_order):
        """A held (requires_approval, unapproved) consumption never touched
        on_hand — it must not enter the completion entry."""
        raw = make_product(item_type="supply")
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)

        held = InventoryTransaction(
            product_id=raw.id,
            location_id=_location(db).id,
            transaction_type="consumption",
            quantity=Decimal("-5"),
            cost_per_unit=Decimal("1.00"),
            reference_type="production_order",
            reference_id=po.id,
            requires_approval=True,          # pending approval, never applied
        )
        db.add(held)
        db.flush()

        _receive_fg(db, fg, po, 1, "2.00")

        je = create_production_completion_gl_entry(db, po)
        assert je is not None
        net = _je_net(db, je)
        assert net["1200"] == Decimal("0")      # held row excluded
        assert net["1220"] == Decimal("2.00")
        assert held.journal_entry_id is None


# =============================================================================
# Call sites
# =============================================================================

class TestCompletionCallSites:

    def test_bulk_complete_posts_and_links(
        self, db, make_product, make_production_order, make_bom
    ):
        """complete_production_order -> process_production_completion ->
        poster. BOM-backflush consumption + FG receipt end in ONE entry."""
        from app.services.production_order_execution_service import (
            complete_production_order,
        )

        raw = make_product(
            item_type="supply", unit="G", cost_method="average",
            average_cost=Decimal("0.02"),
        )
        fg = make_product(
            item_type="finished_good", cost_method="average",
            average_cost=Decimal("2.50"),
        )
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        _seed_stock(db, raw, 10000, "0.02")

        po = make_production_order(product_id=fg.id, status="in_progress", quantity=5)

        completed = complete_production_order(
            db, po.id, "tester@filaops.dev", quantity_good=5
        )
        assert completed.status == "complete"

        entries = _completion_entries(db, po)
        assert len(entries) == 1
        net = _je_net(db, entries[0])
        # 500 G x 0.02 = 10.00 consumed; FG 5 x 2.50 = 12.50; V = +2.50
        assert net["1200"] == Decimal("-10.00")
        assert net["1220"] == Decimal("12.50")
        assert net["5200"] == Decimal("-2.50")
        assert net["1210"] == Decimal("0")

        for txn in _po_txns(db, po):
            assert txn.journal_entry_id == entries[0].id

    def test_per_op_consume_then_completion_posts_exactly_once(
        self, db, make_product, make_production_order
    ):
        """Consumption posted earlier (per-operation path) plus the
        completion receipt are swept into ONE entry, and a re-run posts
        nothing — each transaction is journaled exactly once."""
        raw = make_product(item_type="supply", average_cost=Decimal("0.50"))
        fg = make_product(
            item_type="finished_good", cost_method="average",
            average_cost=Decimal("2.00"),
        )
        # No BOM, no routing rows: process_production_completion consumes
        # nothing new, mirroring an order fully consumed per-op.
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=5)

        _seed_stock(db, raw, 100, "0.50")
        per_op_txn = _consume(db, raw, po, 10, "0.50")   # the "per-op" row

        inventory_service.process_production_completion(
            db=db, production_order=po,
            quantity_completed=Decimal("5"), created_by="tester@filaops.dev",
        )

        entries = _completion_entries(db, po)
        assert len(entries) == 1
        je = entries[0]

        # Both the earlier per-op consumption and the new FG receipt are
        # linked to the single entry.
        assert per_op_txn.journal_entry_id == je.id
        for txn in _po_txns(db, po):
            assert txn.journal_entry_id == je.id

        # Second sweep finds nothing.
        assert create_production_completion_gl_entry(db, po) is None
        assert len(_completion_entries(db, po)) == 1

    def test_accept_short_posts_completion_entry(
        self, db, make_product, make_production_order
    ):
        from app.services.production_order_execution_service import (
            accept_short_production_order,
        )

        fg = make_product(
            item_type="finished_good", cost_method="average",
            average_cost=Decimal("2.00"),
        )
        po = make_production_order(product_id=fg.id, status="short", quantity=5)
        po.quantity_completed = 3
        db.flush()

        accepted = accept_short_production_order(
            db, po.id, "tester@filaops.dev", user_id=1
        )
        assert accepted.status == "complete"

        entries = _completion_entries(db, po)
        assert len(entries) == 1
        net = _je_net(db, entries[0])
        # 3 of 5 produced at effective cost 2.00 -> FG 6.00, no consumption.
        assert net["1220"] == Decimal("6.00")
        assert net["5200"] == Decimal("-6.00")
        assert net["1210"] == Decimal("0")

        for txn in _po_txns(db, po):
            assert txn.journal_entry_id == entries[0].id


# =============================================================================
# GL-health counter on the accounting dashboard
# =============================================================================

class TestUnjournaledCounter:

    def test_dashboard_counts_unjournaled_production_txns(
        self, client, db, make_product, make_production_order
    ):
        baseline = client.get("/api/v1/admin/accounting/dashboard").json()[
            "unjournaled_txn_count"
        ]

        raw = make_product(item_type="supply")
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)
        _seed_stock(db, raw, 10, "1.00")
        _consume(db, raw, po, 2, "1.00")
        _receive_fg(db, fg, po, 1, "3.00")

        after = client.get("/api/v1/admin/accounting/dashboard").json()[
            "unjournaled_txn_count"
        ]
        assert after == baseline + 2

        # Held rows are NOT drift (on_hand never moved).
        other = make_product(item_type="supply")
        held = InventoryTransaction(
            product_id=other.id,
            location_id=_location(db).id,
            transaction_type="consumption",
            quantity=Decimal("-5"),
            cost_per_unit=Decimal("1.00"),
            reference_type="production_order",
            reference_id=po.id,
            requires_approval=True,
        )
        db.add(held)
        db.flush()
        assert client.get("/api/v1/admin/accounting/dashboard").json()[
            "unjournaled_txn_count"
        ] == baseline + 2

        # Posting the completion entry brings the counter back down.
        create_production_completion_gl_entry(db, po)
        assert client.get("/api/v1/admin/accounting/dashboard").json()[
            "unjournaled_txn_count"
        ] == baseline


# =============================================================================
# Backfill script
# =============================================================================

def _fresh_marker(tmp_path):
    marker = tmp_path / "pg_dump.marker"
    marker.write_text("backup taken")
    return marker


class TestBackfillScript:

    def _make_unjournaled_po(self, db, make_product, make_production_order,
                             completed_at=None):
        raw = make_product(item_type="supply")
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="complete", quantity=2)
        if completed_at is not None:
            po.completed_at = completed_at
            db.flush()
        _seed_stock(db, raw, 100, "0.50")
        _consume(db, raw, po, 10, "0.50")       # 5.00
        _receive_fg(db, fg, po, 2, "4.00")      # 8.00
        return po

    def test_dry_run_prints_and_writes_nothing(
        self, db, make_product, make_production_order, tmp_path
    ):
        po = self._make_unjournaled_po(db, make_product, make_production_order)

        lines = []
        previews = backfill.run_dry_run(db, po_ids=[po.id], out=lines.append)

        assert len(previews) == 1
        output = "\n".join(lines)
        assert f"PO#{po.code}" in output
        assert "M_mat" in output
        assert "DRY RUN" in output

        # Nothing posted, nothing linked.
        assert _completion_entries(db, po) == []
        for txn in _po_txns(db, po):
            assert txn.journal_entry_id is None
        # No stray files in tmp_path (dry-run writes no manifest).
        assert list(tmp_path.iterdir()) == []

    def test_apply_refuses_without_backup_marker(
        self, db, make_product, make_production_order, tmp_path
    ):
        po = self._make_unjournaled_po(db, make_product, make_production_order)
        manifest = tmp_path / "manifest.json"

        with pytest.raises(backfill.BackupMarkerError):
            backfill.run_apply(db, str(manifest), backup_marker=None,
                               po_ids=[po.id])

        assert _completion_entries(db, po) == []
        assert not manifest.exists()

    def test_apply_refuses_stale_backup_marker(
        self, db, make_product, make_production_order, tmp_path
    ):
        import os
        po = self._make_unjournaled_po(db, make_product, make_production_order)
        manifest = tmp_path / "manifest.json"
        marker = _fresh_marker(tmp_path)
        stale = datetime.now(timezone.utc) - timedelta(hours=25)
        os.utime(marker, (stale.timestamp(), stale.timestamp()))

        with pytest.raises(backfill.BackupMarkerError):
            backfill.run_apply(db, str(manifest), backup_marker=str(marker),
                               po_ids=[po.id])

        assert _completion_entries(db, po) == []
        assert not manifest.exists()

    def test_apply_manifest_rollback_roundtrip(
        self, db, make_product, make_production_order, tmp_path
    ):
        import json
        completed = datetime(2026, 6, 15, 12, 0, 0)
        po = self._make_unjournaled_po(
            db, make_product, make_production_order, completed_at=completed
        )
        marker = _fresh_marker(tmp_path)
        manifest_path = tmp_path / "manifest.json"

        # --- apply ---
        entries = backfill.run_apply(
            db, str(manifest_path), backup_marker=str(marker), po_ids=[po.id],
            out=lambda *_: None,
        )
        assert len(entries) == 1

        posted = _completion_entries(db, po)
        assert len(posted) == 1
        je = posted[0]
        # Backdated to the PO's completion date (owner decision).
        assert je.entry_date == date(2026, 6, 15)

        manifest = json.loads(manifest_path.read_text())
        assert manifest["entries"][0]["journal_entry_id"] == je.id
        assert manifest["entries"][0]["production_order_id"] == po.id

        # --- re-apply: sweep idempotency, posts nothing ---
        manifest2 = tmp_path / "manifest2.json"
        again = backfill.run_apply(
            db, str(manifest2), backup_marker=str(marker), po_ids=[po.id],
            out=lambda *_: None,
        )
        assert again == []
        assert len(_completion_entries(db, po)) == 1
        assert not manifest2.exists()

        # --- rollback: voids the entry and unlinks its transactions ---
        voided = backfill.run_rollback(db, str(manifest_path), out=lambda *_: None)
        assert voided == 1
        db.refresh(je)
        assert je.status == "voided"
        assert je.void_reason and "#880" in je.void_reason
        for txn in _po_txns(db, po):
            assert txn.journal_entry_id is None

        # --- re-apply after rollback re-posts cleanly ---
        manifest3 = tmp_path / "manifest3.json"
        reposted = backfill.run_apply(
            db, str(manifest3), backup_marker=str(marker), po_ids=[po.id],
            out=lambda *_: None,
        )
        assert len(reposted) == 1
        live = [
            e for e in _completion_entries(db, po) if e.status == "posted"
        ]
        assert len(live) == 1
        assert live[0].id != je.id
