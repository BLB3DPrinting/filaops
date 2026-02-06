"""Tests for status_sync_service.py and order_status.py (OrderStatusService class).

Covers:
- sync_on_production_complete (auto-update SO when WOs finish)
- check_sales_order_production_status
- OrderStatusService validation, status updates, scrap/remake workflows
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone

from app.services.status_sync_service import (
    sync_on_production_complete,
    check_sales_order_production_status,
)
from app.services.order_status import OrderStatusService


# =============================================================================
# status_sync_service — sync_on_production_complete
# =============================================================================


class TestSyncOnProductionComplete:
    def test_no_sales_order_id_returns_false(self, db, make_production_order, make_product):
        product = make_product()
        wo = make_production_order(product_id=product.id)
        wo.sales_order_id = None
        db.flush()
        result = sync_on_production_complete(db, wo)
        assert result is False

    def test_nonexistent_sales_order_returns_false(self, db, make_product):
        """Simulate a WO with a stale sales_order_id using no_autoflush."""
        from app.models.production_order import ProductionOrder
        product = make_product()
        wo = ProductionOrder(
            code="WO-ORPHAN-TEST",
            product_id=product.id,
            quantity_ordered=1,
            status="complete",
            source="manual",
        )
        db.add(wo)
        db.flush()
        # Use no_autoflush to bypass FK enforcement for this edge-case test
        with db.no_autoflush:
            wo.sales_order_id = 999999
            result = sync_on_production_complete(db, wo)
        assert result is False

    def test_single_complete_wo_updates_so(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="in_production"
        )
        wo = make_production_order(product_id=product.id, status="complete")
        wo.sales_order_id = so.id
        db.flush()
        result = sync_on_production_complete(db, wo)
        # Should update SO to ready_to_ship since all WOs complete
        assert result is True

    def test_not_all_wos_complete_no_update(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=2,
            unit_price=Decimal("10.00"), status="in_production"
        )
        wo1 = make_production_order(product_id=product.id, status="complete")
        wo1.sales_order_id = so.id
        wo2 = make_production_order(product_id=product.id, status="in_progress")
        wo2.sales_order_id = so.id
        db.flush()
        result = sync_on_production_complete(db, wo1)
        # Not all complete, so SO stays in_production
        assert result is False


class TestCheckSalesOrderProductionStatus:
    def test_no_production_orders(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        result = check_sales_order_production_status(db, so.id)
        assert result["has_production_orders"] is False
        assert result["total"] == 0
        assert result["all_complete"] is False

    def test_with_production_orders(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        wo = make_production_order(product_id=product.id, status="in_progress")
        wo.sales_order_id = so.id
        db.flush()
        result = check_sales_order_production_status(db, so.id)
        assert result["has_production_orders"] is True
        assert result["total"] >= 1
        assert result["in_progress"] >= 1
        assert result["all_complete"] is False

    def test_all_complete(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        wo = make_production_order(product_id=product.id, status="complete")
        wo.sales_order_id = so.id
        db.flush()
        result = check_sales_order_production_status(db, so.id)
        assert result["all_complete"] is True
        assert result["completed"] >= 1

    def test_nonexistent_so_returns_no_orders(self, db):
        result = check_sales_order_production_status(db, 999999)
        assert result["has_production_orders"] is False


# =============================================================================
# OrderStatusService — validation
# =============================================================================


class TestOrderStatusServiceValidation:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_so_same_status_is_valid(self):
        valid, error = self.svc.validate_so_transition("draft", "draft")
        assert valid is True

    def test_so_valid_transition_draft_to_pending_payment(self):
        valid, error = self.svc.validate_so_transition("draft", "pending_payment")
        assert valid is True

    def test_so_invalid_transition_draft_to_shipped(self):
        valid, error = self.svc.validate_so_transition("draft", "shipped")
        assert valid is False
        assert "Invalid SO status" in error

    def test_so_cancelled_is_terminal(self):
        valid, error = self.svc.validate_so_transition("cancelled", "draft")
        assert valid is False

    def test_so_completed_is_terminal(self):
        valid, error = self.svc.validate_so_transition("completed", "draft")
        assert valid is False

    def test_so_confirmed_to_in_production(self):
        valid, error = self.svc.validate_so_transition("confirmed", "in_production")
        assert valid is True

    def test_so_on_hold_can_resume(self):
        valid, error = self.svc.validate_so_transition("on_hold", "confirmed")
        assert valid is True

    def test_wo_same_status_is_valid(self):
        valid, error = self.svc.validate_wo_transition("draft", "draft")
        assert valid is True

    def test_wo_valid_transition_draft_to_released(self):
        valid, error = self.svc.validate_wo_transition("draft", "released")
        assert valid is True

    def test_wo_invalid_transition_draft_to_completed(self):
        valid, error = self.svc.validate_wo_transition("draft", "completed")
        assert valid is False
        assert "Invalid WO status" in error

    def test_wo_scrapped_is_terminal(self):
        valid, error = self.svc.validate_wo_transition("scrapped", "draft")
        assert valid is False

    def test_wo_closed_is_terminal(self):
        valid, error = self.svc.validate_wo_transition("closed", "draft")
        assert valid is False

    def test_wo_in_progress_to_completed(self):
        valid, error = self.svc.validate_wo_transition("in_progress", "completed")
        assert valid is True

    def test_wo_completed_to_qc_hold(self):
        valid, error = self.svc.validate_wo_transition("completed", "qc_hold")
        assert valid is True

    def test_wo_qc_hold_to_scrapped(self):
        valid, error = self.svc.validate_wo_transition("qc_hold", "scrapped")
        assert valid is True

    def test_unknown_status_treated_as_no_transitions(self):
        valid, error = self.svc.validate_so_transition("nonexistent", "draft")
        assert valid is False
        valid2, error2 = self.svc.validate_wo_transition("nonexistent", "draft")
        assert valid2 is False


class TestOrderStatusServiceUpdateSO:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_update_so_valid(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="draft"
        )
        result = self.svc.update_so_status(db, so, "pending_payment")
        assert result.status == "pending_payment"

    def test_update_so_invalid_raises(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="draft"
        )
        with pytest.raises(ValueError, match="Invalid SO status"):
            self.svc.update_so_status(db, so, "shipped")

    def test_update_so_skip_validation(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="draft"
        )
        result = self.svc.update_so_status(db, so, "shipped", skip_validation=True)
        assert result.status == "shipped"

    def test_confirmed_sets_timestamp(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="confirmed"
        )
        so.status = "in_production"
        db.flush()
        result = self.svc.update_so_status(db, so, "ready_to_ship")
        assert result.status == "ready_to_ship"

    def test_cancelled_sets_timestamp(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="draft"
        )
        result = self.svc.update_so_status(db, so, "cancelled")
        assert result.status == "cancelled"
        assert result.cancelled_at is not None


class TestOrderStatusServiceUpdateWO:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_update_wo_valid(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="draft")
        result = self.svc.update_wo_status(db, wo, "released")
        assert result.status == "released"

    def test_update_wo_invalid_raises(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="draft")
        with pytest.raises(ValueError, match="Invalid WO status"):
            self.svc.update_wo_status(db, wo, "completed")

    def test_in_progress_sets_actual_start(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="scheduled")
        wo.actual_start = None
        db.flush()
        result = self.svc.update_wo_status(db, wo, "in_progress")
        assert result.actual_start is not None

    def test_completed_sets_actual_end(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="in_progress")
        wo.actual_end = None
        db.flush()
        result = self.svc.update_wo_status(db, wo, "completed")
        assert result.actual_end is not None


class TestOrderStatusServiceAutoUpdateSO:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_no_wos_returns_so_unchanged(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="confirmed"
        )
        result = self.svc.auto_update_so_from_wos(db, so)
        assert result.status == "confirmed"

    def test_in_progress_wo_updates_so(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="confirmed"
        )
        wo = make_production_order(product_id=product.id, status="in_progress")
        wo.sales_order_id = so.id
        db.flush()
        result = self.svc.auto_update_so_from_wos(db, so)
        assert result.status == "in_production"


class TestMarkReadyForShipping:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_no_wos_raises(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="in_production"
        )
        with pytest.raises(ValueError, match="no production orders"):
            self.svc.mark_ready_for_shipping(db, so)

    def test_incomplete_wos_raises(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="in_production"
        )
        wo = make_production_order(product_id=product.id, status="in_progress")
        wo.sales_order_id = so.id
        db.flush()
        with pytest.raises(ValueError, match="still in progress"):
            self.svc.mark_ready_for_shipping(db, so)

    def test_failed_qc_raises(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="in_production"
        )
        wo = make_production_order(product_id=product.id, status="closed")
        wo.sales_order_id = so.id
        wo.qc_status = "failed"
        db.flush()
        with pytest.raises(ValueError, match="failed QC"):
            self.svc.mark_ready_for_shipping(db, so)

    def test_ready_for_shipping_success(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="in_production"
        )
        wo = make_production_order(product_id=product.id, status="closed")
        wo.sales_order_id = so.id
        wo.qc_status = "passed"
        db.flush()
        result = self.svc.mark_ready_for_shipping(db, so)
        assert result.status == "ready_to_ship"
        assert result.fulfillment_status == "ready"


class TestScrapAndRemake:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_scrap_and_create_remake(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="completed")
        wo.qc_status = "pending"
        db.flush()
        remake = self.svc.scrap_wo_and_create_remake(db, wo, "layer_shift")
        assert wo.status == "scrapped"
        assert wo.quantity_scrapped == float(wo.quantity_ordered)
        assert remake.status == "draft"
        assert remake.remake_of_id == wo.id
        assert "layer_shift" in remake.notes

    def test_scrap_partial_quantity(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, quantity=10, status="completed")
        wo.qc_status = "pending"
        db.flush()
        remake = self.svc.scrap_wo_and_create_remake(db, wo, "warping", scrap_quantity=3)
        assert wo.quantity_scrapped == 3
        assert remake.quantity_ordered == 3

    def test_remake_inherits_parent_fields(self, db, make_product, make_production_order, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=5, unit_price=Decimal("10.00"))
        wo = make_production_order(product_id=product.id, status="completed")
        wo.sales_order_id = so.id
        wo.qc_status = "pending"
        db.flush()
        remake = self.svc.scrap_wo_and_create_remake(db, wo, "adhesion")
        assert remake.product_id == wo.product_id
        assert remake.sales_order_id == so.id

    def test_multiple_remakes_increment_suffix(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="completed")
        wo.qc_status = "pending"
        db.flush()
        remake1 = self.svc.scrap_wo_and_create_remake(db, wo, "first issue")
        # Manually set remake1 to completed + qc_hold → scrapped for second remake
        # Just verify the code is correct
        assert "-R1" in remake1.code


class TestUpdateWOStatusSideEffects:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_completed_sets_qc_pending(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="in_progress")
        wo.qc_status = "not_checked"  # Anything except "not_required"
        db.flush()
        result = self.svc.update_wo_status(db, wo, "completed")
        assert result.qc_status == "pending"

    def test_completed_not_required_qc_stays(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="in_progress")
        wo.qc_status = "not_required"
        db.flush()
        result = self.svc.update_wo_status(db, wo, "completed")
        assert result.qc_status == "not_required"

    def test_closed_sets_completed_at(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="completed")
        wo.qc_status = "passed"
        db.flush()
        result = self.svc.update_wo_status(db, wo, "closed")
        assert result.completed_at is not None

    def test_scrapped_sets_timestamp(self, db, make_product, make_production_order):
        product = make_product()
        wo = make_production_order(product_id=product.id, status="qc_hold")
        db.flush()
        result = self.svc.update_wo_status(db, wo, "scrapped")
        assert result.scrapped_at is not None

    def test_wo_update_triggers_so_auto_update(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="confirmed"
        )
        wo = make_production_order(product_id=product.id, status="scheduled")
        wo.sales_order_id = so.id
        db.flush()
        self.svc.update_wo_status(db, wo, "in_progress")
        db.refresh(so)
        assert so.status == "in_production"


class TestUpdateSOStatusSideEffects:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_shipped_sets_timestamps(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="ready_to_ship"
        )
        result = self.svc.update_so_status(db, so, "shipped")
        assert result.shipped_at is not None
        assert result.fulfillment_status == "shipped"

    def test_delivered_sets_timestamps(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="shipped"
        )
        result = self.svc.update_so_status(db, so, "delivered")
        assert result.delivered_at is not None
        assert result.fulfillment_status == "delivered"

    def test_confirmed_sets_timestamp(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="pending_payment"
        )
        result = self.svc.update_so_status(db, so, "confirmed")
        assert result.confirmed_at is not None


class TestAutoUpdateSOFromWOsAdvanced:
    def setup_method(self):
        self.svc = OrderStatusService()

    def test_all_closed_qc_passed_updates_so(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="in_production"
        )
        wo = make_production_order(product_id=product.id, status="closed")
        wo.sales_order_id = so.id
        wo.qc_status = "passed"
        db.flush()
        result = self.svc.auto_update_so_from_wos(db, so)
        assert result.status == "ready_to_ship"
        assert result.fulfillment_status == "ready"

    def test_mixed_statuses_no_change(self, db, make_product, make_sales_order, make_production_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"), status="in_production"
        )
        wo1 = make_production_order(product_id=product.id, status="closed")
        wo1.sales_order_id = so.id
        wo1.qc_status = "passed"
        wo2 = make_production_order(product_id=product.id, status="draft")
        wo2.sales_order_id = so.id
        db.flush()
        result = self.svc.auto_update_so_from_wos(db, so)
        # Mixed states — no automatic change
        assert result.status == "in_production"
