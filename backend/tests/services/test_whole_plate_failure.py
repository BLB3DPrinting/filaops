"""
Whole-plate failure and zero-good close (print-batch plan stage S6).

A plate of 8 parts that all fail used to leave no trace in the books:
complete_operation flipped the operation to 'complete' (quantity_completed = 0)
*before* asking scrap_service to cap the scrap, the cap became "what was
completed" (0), the ScrapError was swallowed, and no ScrapRecord and no
DR 5020 Scrap / CR 1210 WIP entry was posted.

These tests run the real completion, scrap, inventory and GL services (no
mocks) so they pin what lands in the ledger, not just that a function was
called.
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.models.inventory import Inventory, InventoryTransaction
from app.models.production_order import (
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
    ScrapRecord,
)
from app.models.scrap_reason import ScrapReason
from app.services import operation_status
from app.services import production_order_service as svc
from app.services.operation_status import OperationError
from app.services.scrap_service import ScrapError

GRAMS_PER_PIECE = Decimal("15")
FILAMENT_COST_PER_GRAM = Decimal("0.02")
REASON_CODE = "whole_plate_test"


# =============================================================================
# Builders
# =============================================================================

@pytest.fixture
def scrap_reason(db):
    reason = db.query(ScrapReason).filter(ScrapReason.code == REASON_CODE).first()
    if not reason:
        reason = ScrapReason(
            code=REASON_CODE,
            name="Whole plate test",
            description="Whole-plate failure tests",
            active=True,
        )
        db.add(reason)
        db.flush()
    return reason


@pytest.fixture
def plate(db, make_product, make_production_order, location, scrap_reason):
    """An 8-piece order with one running PRINT operation and a filament row.

    Returns a builder so a test can ask for another order (different quantity,
    sales-order link) with the same wiring.
    """

    def _build(quantity=8, sales_order_id=None, status="in_progress", work_center_id=1):
        filament = make_product(
            item_type="supply",
            unit="G",
            cost_method="average",
            average_cost=FILAMENT_COST_PER_GRAM,
            is_raw_material=True,
            name=f"Filament {uuid.uuid4().hex[:6]}",
        )
        part = make_product(
            item_type="finished_good",
            unit="EA",
            cost_method="standard",
            standard_cost=Decimal("1.00"),
            procurement_type="make",
        )
        db.add(Inventory(
            product_id=filament.id,
            location_id=location.id,
            on_hand_quantity=Decimal("5000"),
            allocated_quantity=Decimal("0"),
        ))
        order = make_production_order(
            product_id=part.id,
            status=status,
            quantity=quantity,
            quantity_completed=0,
            quantity_scrapped=0,
            sales_order_id=sales_order_id,
        )
        op = ProductionOrderOperation(
            production_order_id=order.id,
            work_center_id=work_center_id,
            sequence=10,
            operation_code="PRINT",
            operation_name="Print",
            status="running",
            actual_start=datetime.now(timezone.utc) - timedelta(minutes=45),
            planned_setup_minutes=Decimal("0"),
            planned_run_minutes=Decimal("60"),
            quantity_completed=Decimal("0"),
            quantity_scrapped=Decimal("0"),
        )
        db.add(op)
        db.flush()
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=filament.id,
            quantity_required=GRAMS_PER_PIECE * quantity,
            unit="G",
            quantity_allocated=Decimal("0"),
            quantity_consumed=Decimal("0"),
            status="pending",
        )
        db.add(mat)
        db.flush()
        return order, op, mat, filament

    return _build


def _complete(db, order, op, *, good, scrapped, reason=REASON_CODE):
    return operation_status.complete_operation(
        db,
        order.id,
        op.id,
        quantity_completed=Decimal(str(good)),
        quantity_scrapped=Decimal(str(scrapped)),
        scrap_reason=reason if scrapped else None,
    )


def _scrap_entries(db, order):
    """Journal entries that are scrap postings for this order (touch 5020)."""
    return (
        db.query(GLJournalEntry)
        .join(GLJournalEntryLine, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id)
        .join(GLAccount, GLJournalEntryLine.account_id == GLAccount.id)
        .filter(
            GLJournalEntry.source_type == "production_order",
            GLJournalEntry.source_id == order.id,
            GLAccount.account_code == "5020",
        )
        .distinct()
        .all()
    )


def _totals_by_account(entry):
    """{account_code: (debits, credits)} for one journal entry."""
    totals = {}
    for line in entry.lines:
        code = line.account.account_code
        debit, credit = totals.get(code, (Decimal("0"), Decimal("0")))
        totals[code] = (
            debit + (line.debit_amount or Decimal("0")),
            credit + (line.credit_amount or Decimal("0")),
        )
    return totals


def _wip_balance(db, order):
    """Net DR - CR on 1210 across every entry posted for this order."""
    lines = (
        db.query(GLJournalEntryLine)
        .join(GLJournalEntry, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id)
        .join(GLAccount, GLJournalEntryLine.account_id == GLAccount.id)
        .filter(
            GLJournalEntry.source_type == "production_order",
            GLJournalEntry.source_id == order.id,
            GLAccount.account_code == "1210",
        )
        .all()
    )
    return sum(
        (
            (line.debit_amount or Decimal("0")) - (line.credit_amount or Decimal("0"))
            for line in lines
        ),
        Decimal("0"),
    )


# =============================================================================
# Bug 1 — the scrap cap is computed before the status flip
# =============================================================================

class TestWholePlateFailurePostsScrap:
    """0 good / 8 scrapped: the whole plate is lost and the books must say so."""

    def test_scrap_records_are_posted(self, db, plate):
        order, op, mat, filament = plate(quantity=8)

        _, scrap_result = _complete(db, order, op, good=0, scrapped=8)

        assert scrap_result is not None
        records = db.query(ScrapRecord).filter(
            ScrapRecord.production_order_id == order.id
        ).all()
        assert len(records) == 1
        assert records[0].product_id == filament.id
        assert records[0].quantity == GRAMS_PER_PIECE * 8  # the whole plate's filament
        assert records[0].scrap_reason_code == REASON_CODE
        assert records[0].journal_entry_id is not None

    def test_one_dr_5020_cr_1210_entry_is_posted(self, db, plate):
        order, op, _, _ = plate(quantity=8)

        _, scrap_result = _complete(db, order, op, good=0, scrapped=8)

        entries = _scrap_entries(db, order)
        assert len(entries) == 1
        assert entries[0].entry_number == scrap_result["journal_entry_number"]
        totals = _totals_by_account(entries[0])
        scrap_dr, scrap_cr = totals["5020"]
        wip_dr, wip_cr = totals["1210"]
        assert scrap_dr > 0 and scrap_cr == 0
        assert wip_cr > 0 and wip_dr == 0
        assert scrap_dr == wip_cr
        # At least the plate's filament: 120 g at $0.02/g
        assert scrap_dr >= GRAMS_PER_PIECE * 8 * FILAMENT_COST_PER_GRAM

    def test_quantities_and_status_after_whole_plate_failure(self, db, plate):
        order, op, _, _ = plate(quantity=8)

        result_op, _ = _complete(db, order, op, good=0, scrapped=8)

        db.refresh(order)
        assert result_op.status == "complete"
        assert result_op.quantity_completed == Decimal("0")
        assert result_op.quantity_scrapped == Decimal("8")
        assert order.quantity_completed == Decimal("0")
        assert order.quantity_scrapped == Decimal("8")
        assert order.status == "short"

    def test_planned_filament_is_still_consumed_once(self, db, plate):
        order, op, mat, filament = plate(quantity=8)

        _complete(db, order, op, good=0, scrapped=8)

        db.refresh(mat)
        assert mat.status == "consumed"
        consumption = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == order.id,
            InventoryTransaction.transaction_type == "consumption",
        ).all()
        assert len(consumption) == 1


class TestPartialFailureUnchanged:
    """6 good / 2 scrapped already worked; it must keep working the same way."""

    def test_scrap_is_posted_for_the_two_failed_pieces(self, db, plate):
        order, op, _, filament = plate(quantity=8)

        result_op, scrap_result = _complete(db, order, op, good=6, scrapped=2)

        records = db.query(ScrapRecord).filter(
            ScrapRecord.production_order_id == order.id
        ).all()
        assert len(records) == 1
        assert records[0].quantity == GRAMS_PER_PIECE * 2
        entries = _scrap_entries(db, order)
        assert len(entries) == 1
        assert entries[0].entry_number == scrap_result["journal_entry_number"]
        totals = _totals_by_account(entries[0])
        assert totals["5020"][0] == totals["1210"][1] > 0

    def test_quantities_and_status(self, db, plate):
        order, op, _, _ = plate(quantity=8)

        result_op, _ = _complete(db, order, op, good=6, scrapped=2)

        db.refresh(order)
        assert result_op.quantity_completed == Decimal("6")
        assert result_op.quantity_scrapped == Decimal("2")
        assert order.quantity_completed == Decimal("6")
        assert order.quantity_scrapped == Decimal("2")
        assert order.status == "short"

    def test_all_good_posts_no_scrap(self, db, plate):
        order, op, _, _ = plate(quantity=8)

        _, scrap_result = _complete(db, order, op, good=8, scrapped=0)

        assert scrap_result is None
        assert _scrap_entries(db, order) == []
        assert db.query(ScrapRecord).filter(
            ScrapRecord.production_order_id == order.id
        ).count() == 0


def _add_finish_op(db, order):
    """A pending FINISH step after the PRINT step."""
    finish = ProductionOrderOperation(
        production_order_id=order.id,
        work_center_id=1,
        sequence=20,
        operation_code="FINISH",
        operation_name="Finish",
        status="pending",
        planned_setup_minutes=Decimal("0"),
        planned_run_minutes=Decimal("10"),
        quantity_completed=Decimal("0"),
        quantity_scrapped=Decimal("0"),
    )
    db.add(finish)
    db.flush()
    return finish


class TestScrapLaborUsesActualRunMinutes:
    """Scrap is now posted before the status flip; its labor must still be
    costed on the run time the operator reported, not the plan."""

    def test_scrap_labor_follows_actual_minutes(self, db, plate, make_work_center):
        wc = make_work_center(machine_rate_per_hour=Decimal("60"))
        order, op, _, _ = plate(quantity=8, work_center_id=wc.id)

        # Planned 60 min; the run actually took 120. Labor on 2 of 8 pieces:
        # 2 h x $60/h x 2/8 = $30.00 (it would be $15.00 on the plan).
        _, scrap_result = operation_status.complete_operation(
            db, order.id, op.id,
            quantity_completed=Decimal("6"),
            quantity_scrapped=Decimal("2"),
            scrap_reason=REASON_CODE,
            actual_run_minutes=120,
        )

        assert scrap_result["labor_cost"] == pytest.approx(30.0)
        assert scrap_result["material_cost"] == pytest.approx(0.6)  # 30 g at $0.02
        assert op.actual_run_minutes == 120

    def test_failed_scrap_leaves_the_run_minutes_alone(self, db, plate):
        order, op, _, _ = plate(quantity=8)
        assert op.actual_run_minutes is None

        with pytest.raises(OperationError):
            _complete(db, order, op, good=0, scrapped=8, reason="no_such_reason")

        assert op.actual_run_minutes is None


class TestDownstreamOperationsAfterScrap:
    @pytest.mark.parametrize("good,scrapped", [(4, 4), (2, 6)])
    def test_good_pieces_still_go_to_the_next_operation(self, db, plate, good, scrapped):
        order, op, _, _ = plate(quantity=8)
        finish = _add_finish_op(db, order)

        _complete(db, order, op, good=good, scrapped=scrapped)

        db.refresh(finish)
        db.refresh(order)
        assert finish.status == "pending"
        assert order.status == "in_progress"
        assert order.quantity_completed == Decimal(good)
        assert order.quantity_scrapped == Decimal(scrapped)

    def test_nothing_left_skips_the_next_operation(self, db, plate):
        order, op, _, _ = plate(quantity=8)
        finish = _add_finish_op(db, order)

        _complete(db, order, op, good=0, scrapped=8)

        db.refresh(finish)
        db.refresh(order)
        assert finish.status == "skipped"
        assert order.status == "short"
        assert len(_scrap_entries(db, order)) == 1


class TestFailingScrapPostSurfaces:
    """A scrap post that cannot happen must fail the call, not vanish."""

    def test_unknown_scrap_reason_fails_the_completion(self, db, plate):
        order, op, mat, _ = plate(quantity=8)

        with pytest.raises(OperationError) as exc_info:
            _complete(db, order, op, good=0, scrapped=8, reason="no_such_reason")

        assert exc_info.value.status_code == 400
        assert "no_such_reason" in exc_info.value.message
        # Nothing was half-done: the operation is still running and the
        # filament was not consumed.
        db.refresh(op)
        db.refresh(mat)
        db.refresh(order)
        assert op.status == "running"
        assert mat.status == "pending"
        assert order.quantity_scrapped == Decimal("0")
        assert db.query(ScrapRecord).filter(
            ScrapRecord.production_order_id == order.id
        ).count() == 0

    def test_scrap_service_error_status_code_is_kept(self, db, plate):
        order, op, _, _ = plate(quantity=8)

        with patch(
            "app.services.scrap_service.process_operation_scrap",
            side_effect=ScrapError("ledger unavailable", 409),
        ):
            with pytest.raises(OperationError) as exc_info:
                _complete(db, order, op, good=6, scrapped=2)

        assert exc_info.value.status_code == 409
        assert "ledger unavailable" in exc_info.value.message
        db.refresh(op)
        assert op.status == "running"


# =============================================================================
# Bug 2 — a zero-good order closes as scrapped
# =============================================================================

class TestCloseScrappedProductionOrder:
    def _lose_whole_plate(self, db, plate, **kwargs):
        order, op, mat, filament = plate(**kwargs)
        _complete(db, order, op, good=0, scrapped=order.quantity_ordered)
        db.refresh(order)
        assert order.status == "short" and order.quantity_completed == 0
        return order

    def test_closes_as_scrapped_and_keeps_the_sales_order_link(
        self, db, plate, make_product, make_sales_order
    ):
        sold = make_product(item_type="finished_good", unit="EA", selling_price=Decimal("5.00"))
        so = make_sales_order(product_id=sold.id, quantity=8)
        order = self._lose_whole_plate(db, plate, quantity=8, sales_order_id=so.id)

        closed = svc.close_scrapped_production_order(
            db, order.id, "test@filaops.dev", user_id=1, notes="Plate came off the bed",
        )

        assert closed.status == "scrapped"
        assert closed.sales_order_id == so.id
        assert closed.quantity_completed == Decimal("0")
        assert closed.quantity_scrapped == Decimal("8")
        assert closed.scrapped_at is not None
        assert "Plate came off the bed" in (closed.notes or "")

    def test_no_finished_goods_are_received(self, db, plate):
        order = self._lose_whole_plate(db, plate, quantity=8)

        svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        receipts = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == order.id,
            InventoryTransaction.transaction_type == "receipt",
        ).count()
        assert receipts == 0

    def test_wip_nets_to_zero_with_the_residual_swept(self, db, plate):
        order = self._lose_whole_plate(db, plate, quantity=8)
        # The scrap entry credited 1210; the filament consumption is still
        # un-journaled, so WIP is negative until the close posts the sweep.
        assert _wip_balance(db, order) < 0

        svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        assert _wip_balance(db, order) == Decimal("0")
        unjournaled = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == order.id,
            InventoryTransaction.transaction_type == "consumption",
            InventoryTransaction.journal_entry_id.is_(None),
        ).count()
        assert unjournaled == 0

    def test_releases_remaining_reservations(self, db, plate, location):
        order, op, mat, filament = plate(quantity=8)
        # A reservation the order still holds (as release would have left it).
        inv = db.query(Inventory).filter(
            Inventory.product_id == filament.id,
            Inventory.location_id == location.id,
        ).one()
        inv.allocated_quantity = Decimal("120")
        db.add(InventoryTransaction(
            product_id=filament.id,
            location_id=location.id,
            transaction_type="reservation",
            quantity=Decimal("120"),
            reference_type="production_order",
            reference_id=order.id,
            cost_per_unit=FILAMENT_COST_PER_GRAM,
            created_at=datetime.now(timezone.utc),
        ))
        db.flush()
        _complete(db, order, op, good=0, scrapped=8)

        svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        db.refresh(inv)
        assert inv.allocated_quantity == Decimal("0")

    def test_rejects_an_order_that_is_not_short(self, db, plate):
        order, _, _, _ = plate(quantity=8)  # in_progress

        with pytest.raises(HTTPException) as exc_info:
            svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        assert exc_info.value.status_code == 400
        assert "short" in str(exc_info.value.detail).lower()

    def test_rejects_an_order_with_good_units(self, db, plate):
        order, op, _, _ = plate(quantity=8)
        _complete(db, order, op, good=6, scrapped=2)
        db.refresh(order)

        with pytest.raises(HTTPException) as exc_info:
            svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        assert exc_info.value.status_code == 400
        assert "accept" in str(exc_info.value.detail).lower()

    def test_rejects_a_short_order_with_nothing_scrapped(self, db, plate):
        order, _, _, _ = plate(quantity=8, status="short")

        with pytest.raises(HTTPException) as exc_info:
            svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        assert exc_info.value.status_code == 400
        assert "cancel" in str(exc_info.value.detail).lower()

    def test_rejects_closing_twice(self, db, plate):
        order = self._lose_whole_plate(db, plate, quantity=8)
        svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        with pytest.raises(HTTPException) as exc_info:
            svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        assert exc_info.value.status_code == 400

    def test_unknown_order_is_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            svc.close_scrapped_production_order(db, 999999, "test@filaops.dev", user_id=1)

        assert exc_info.value.status_code == 404

    def test_accept_short_still_refuses_zero_good_and_points_at_the_new_path(self, db, plate):
        order = self._lose_whole_plate(db, plate, quantity=8)

        with pytest.raises(HTTPException) as exc_info:
            svc.accept_short_production_order(db, order.id, "test@filaops.dev", user_id=1)

        assert exc_info.value.status_code == 400
        assert "no units" in str(exc_info.value.detail).lower()
        assert "scrapped" in str(exc_info.value.detail).lower()


class TestScrapFirstThenCompleteStillWorks:
    """The print-batch plan's interim ordering: scrap the running operation,
    then complete it with 0 good and nothing further scrapped."""

    def test_posts_once_and_closes_as_scrapped(self, db, plate):
        from app.services.scrap_service import process_operation_scrap

        order, op, _, _ = plate(quantity=8)
        process_operation_scrap(
            db=db, po_id=order.id, op_id=op.id,
            quantity_scrapped=8, scrap_reason_code=REASON_CODE,
        )

        _, scrap_result = operation_status.complete_operation(
            db, order.id, op.id,
            quantity_completed=Decimal("0"),
            quantity_scrapped=Decimal("0"),
        )

        db.refresh(order)
        assert scrap_result is None
        assert order.status == "short"
        assert order.quantity_scrapped == Decimal("8")
        assert len(_scrap_entries(db, order)) == 1

        closed = svc.close_scrapped_production_order(db, order.id, "test@filaops.dev", user_id=1)

        assert closed.status == "scrapped"
        assert _wip_balance(db, order) == Decimal("0")


class TestAcceptShortWithGoodUnitsUnchanged:
    """6 good / 2 scrapped still accepts short and receipts the 6 good ones."""

    def test_receipts_completed_quantity_and_completes(self, db, plate):
        order, op, _, _ = plate(quantity=8)
        _complete(db, order, op, good=6, scrapped=2)
        db.refresh(order)
        assert order.status == "short"

        accepted = svc.accept_short_production_order(
            db, order.id, "test@filaops.dev", user_id=1,
        )

        assert accepted.status == "complete"
        receipt = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == order.id,
            InventoryTransaction.transaction_type == "receipt",
        ).one()
        assert receipt.quantity == Decimal("6")
        # Scrap (2 of 8) credited 1210, the 6 receipts and the consumption
        # moved the rest: WIP ends at zero, as it did before this change.
        assert _wip_balance(db, order) == Decimal("0")


# =============================================================================
# HTTP
# =============================================================================

class TestCloseScrappedEndpoint:
    def test_post_close_scrapped_returns_the_scrapped_order(self, client, db, plate):
        order, op, _, _ = plate(quantity=8)
        _complete(db, order, op, good=0, scrapped=8)

        resp = client.post(
            f"/api/v1/production-orders/{order.id}/close-scrapped",
            json={"notes": "Whole plate failed"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "scrapped"
        assert body["id"] == order.id

    def test_post_close_scrapped_on_a_running_order_is_400(self, client, db, plate):
        order, _, _, _ = plate(quantity=8)

        resp = client.post(f"/api/v1/production-orders/{order.id}/close-scrapped")

        assert resp.status_code == 400

    def test_post_close_scrapped_needs_a_staff_login(self, unauthed_client, db, plate):
        order, _, _, _ = plate(quantity=8)

        resp = unauthed_client.post(f"/api/v1/production-orders/{order.id}/close-scrapped")

        assert resp.status_code in (401, 403)


class TestScrappedOrdersAreNotActive:
    """A scrapped order is finished: it must not sit in the active queue or
    count as overdue because its due date has passed."""

    def test_schedule_summary_ignores_scrapped_orders(self, db, make_product, make_production_order):
        before = svc.get_schedule_summary(db)
        part = make_product()
        yesterday = date.today() - timedelta(days=1)
        make_production_order(
            product_id=part.id, status="scrapped", quantity=8,
            quantity_scrapped=8, due_date=yesterday,
        )
        make_production_order(
            product_id=part.id, status="scrapped", quantity=8,
            quantity_scrapped=8, due_date=date.today(),
        )

        after = svc.get_schedule_summary(db)

        assert "scrapped" not in after["by_status"]
        assert after["overdue"] == before["overdue"]
        assert after["due_today"] == before["due_today"]
        assert after["total_active"] == before["total_active"]

    def test_production_queue_ignores_scrapped_orders(
        self, client, db, make_product, make_production_order
    ):
        before = client.get("/api/v1/admin/fulfillment/queue").json()
        part = make_product()
        make_production_order(
            product_id=part.id, status="scrapped", quantity=8, quantity_scrapped=8, priority=1,
        )

        after = client.get("/api/v1/admin/fulfillment/queue").json()

        assert after["stats"]["total_active"] == before["stats"]["total_active"]
        assert after["stats"]["urgent_count"] == before["stats"]["urgent_count"]


class TestScrappedIsAKnownStatus:
    def test_status_config_lists_scrapped_and_short_can_reach_it(self):
        from app.core.status_config import (
            ProductionOrderStatus,
            get_allowed_production_order_transitions,
            is_valid_production_order_transition,
        )

        assert ProductionOrderStatus.SCRAPPED.value == "scrapped"
        assert "scrapped" in get_allowed_production_order_transitions("short")
        assert is_valid_production_order_transition("short", "scrapped")
        assert get_allowed_production_order_transitions("scrapped") == []

    def test_status_transitions_endpoint_reports_scrapped(self, client):
        resp = client.get("/api/v1/production-orders/status-transitions")

        assert resp.status_code == 200
        data = resp.json()
        assert "scrapped" in data["statuses"]
        assert data["transitions"]["scrapped"]["is_terminal"] is True
