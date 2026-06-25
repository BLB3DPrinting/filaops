"""F3b (#808): the response builders serialize the model @property guards so the
UX next-action contract can PROJECT from them instead of re-deriving readiness."""
from decimal import Decimal

from app.api.v1.endpoints.sales_orders import build_sales_order_response
from app.api.v1.endpoints.production_orders import build_list_response


class TestSalesOrderResponseGuards:
    def test_serializes_guard_flags(self, db, make_sales_order, finished_good):
        so = make_sales_order(
            product_id=finished_good.id, status="confirmed", payment_status="paid"
        )
        resp = build_sales_order_response(so, db)
        assert resp.is_paid is True
        assert resp.can_start_production is True  # confirmed + paid
        assert resp.is_cancellable is True  # 'confirmed' is cancellable
        assert resp.is_ready_to_ship is False  # not ready_to_ship
        assert resp.is_complete is False

    def test_unpaid_pending_order_guards(self, db, make_sales_order, finished_good):
        so = make_sales_order(
            product_id=finished_good.id, status="pending", payment_status="pending"
        )
        resp = build_sales_order_response(so, db)
        assert resp.is_paid is False
        assert resp.can_start_production is False  # not confirmed
        assert resp.is_complete is False


class TestProductionListResponseGuards:
    def test_serializes_real_qc_status_and_guards(self, db, make_production_order, finished_good):
        # status='complete' + qc_status='pending' => ready for QC, not closable.
        po = make_production_order(
            product_id=finished_good.id,
            status="complete",
            qc_status="pending",
            quantity=5,
            quantity_completed=Decimal("5"),
        )
        resp = build_list_response(po, db)
        # Regression: qc_status used to default to "not_required" (never passed).
        assert resp.qc_status == "pending"
        assert resp.is_ready_for_qc is True
        assert resp.is_qc_required is True
        assert resp.can_close is False  # pending not in {passed, not_required, waived}

    def test_passed_qc_is_closable(self, db, make_production_order, finished_good):
        po = make_production_order(
            product_id=finished_good.id,
            status="complete",
            qc_status="passed",
            quantity=5,
            quantity_completed=Decimal("5"),
        )
        resp = build_list_response(po, db)
        assert resp.qc_status == "passed"
        assert resp.can_close is True
        assert resp.is_ready_for_qc is False  # qc no longer pending
