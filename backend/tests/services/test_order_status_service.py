"""Tests for order_status.py — status transition validation and workflow automation."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.services.order_status import OrderStatusService, order_status_service


class TestValidateSOTransition:
    """Sales Order status transition validation."""

    def test_same_status_always_valid(self):
        svc = OrderStatusService()
        ok, msg = svc.validate_so_transition("draft", "draft")
        assert ok is True
        assert msg == ""

    @pytest.mark.parametrize("from_s, to_s", [
        ("draft", "pending_payment"),
        ("draft", "cancelled"),
        ("pending_payment", "confirmed"),
        ("confirmed", "in_production"),
        ("in_production", "ready_to_ship"),
        ("ready_to_ship", "shipped"),
        ("shipped", "delivered"),
        ("delivered", "completed"),
    ])
    def test_valid_transitions(self, from_s, to_s):
        ok, msg = order_status_service.validate_so_transition(from_s, to_s)
        assert ok is True

    @pytest.mark.parametrize("from_s, to_s", [
        ("draft", "shipped"),
        ("cancelled", "draft"),
        ("completed", "draft"),
        ("shipped", "draft"),
        ("in_production", "pending_payment"),
    ])
    def test_invalid_transitions(self, from_s, to_s):
        ok, msg = order_status_service.validate_so_transition(from_s, to_s)
        assert ok is False
        assert "Invalid SO status transition" in msg

    def test_terminal_states_have_no_valid_transitions(self):
        for terminal in ["cancelled", "completed"]:
            assert order_status_service.VALID_SO_TRANSITIONS[terminal] == []

    def test_on_hold_can_resume(self):
        ok, _ = order_status_service.validate_so_transition("on_hold", "confirmed")
        assert ok is True
        ok, _ = order_status_service.validate_so_transition("on_hold", "cancelled")
        assert ok is True


class TestValidateWOTransition:
    """Production Order (WO) status transition validation."""

    def test_same_status_always_valid(self):
        ok, _ = order_status_service.validate_wo_transition("draft", "draft")
        assert ok is True

    @pytest.mark.parametrize("from_s, to_s", [
        ("draft", "released"),
        ("draft", "cancelled"),
        ("released", "scheduled"),
        ("scheduled", "in_progress"),
        ("in_progress", "completed"),
        ("completed", "closed"),
        ("completed", "qc_hold"),
        ("qc_hold", "scrapped"),
        ("qc_hold", "in_progress"),
    ])
    def test_valid_transitions(self, from_s, to_s):
        ok, _ = order_status_service.validate_wo_transition(from_s, to_s)
        assert ok is True

    @pytest.mark.parametrize("from_s, to_s", [
        ("draft", "completed"),
        ("scrapped", "draft"),
        ("closed", "released"),
    ])
    def test_invalid_transitions(self, from_s, to_s):
        ok, msg = order_status_service.validate_wo_transition(from_s, to_s)
        assert ok is False
        assert "Invalid WO status transition" in msg


class TestUpdateSOStatus:
    """Sales Order status update with side effects."""

    def test_update_so_to_confirmed_sets_timestamp(self, db, make_sales_order, make_product):
        product = make_product()
        so = make_sales_order(product_id=product.id, status="pending_payment")
        svc = OrderStatusService()
        updated = svc.update_so_status(db, so, "confirmed")
        assert updated.status == "confirmed"
        assert updated.confirmed_at is not None

    def test_update_so_to_shipped_sets_fulfillment(self, db, make_sales_order, make_product):
        product = make_product()
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        svc = OrderStatusService()
        updated = svc.update_so_status(db, so, "shipped")
        assert updated.status == "shipped"
        assert updated.fulfillment_status == "shipped"
        assert updated.shipped_at is not None

    def test_update_so_to_cancelled_sets_timestamp(self, db, make_sales_order, make_product):
        product = make_product()
        so = make_sales_order(product_id=product.id, status="draft")
        svc = OrderStatusService()
        updated = svc.update_so_status(db, so, "cancelled")
        assert updated.status == "cancelled"
        assert updated.cancelled_at is not None

    def test_invalid_transition_raises_value_error(self, db, make_sales_order, make_product):
        product = make_product()
        so = make_sales_order(product_id=product.id, status="draft")
        svc = OrderStatusService()
        with pytest.raises(ValueError, match="Invalid SO status transition"):
            svc.update_so_status(db, so, "shipped")

    def test_skip_validation_allows_any_transition(self, db, make_sales_order, make_product):
        product = make_product()
        so = make_sales_order(product_id=product.id, status="draft")
        svc = OrderStatusService()
        updated = svc.update_so_status(db, so, "shipped", skip_validation=True)
        assert updated.status == "shipped"


class TestUpdateWOStatus:
    """Production Order status update with side effects."""

    def test_update_wo_to_in_progress_sets_actual_start(self, db, make_product):
        from app.models.production_order import ProductionOrder
        product = make_product()
        wo = ProductionOrder(
            code="MO-TEST-001", product_id=product.id,
            quantity_ordered=10, status="scheduled",
        )
        db.add(wo)
        db.flush()
        svc = OrderStatusService()
        updated = svc.update_wo_status(db, wo, "in_progress")
        assert updated.status == "in_progress"
        assert updated.actual_start is not None

    def test_update_wo_to_completed_sets_actual_end(self, db, make_product):
        from app.models.production_order import ProductionOrder
        product = make_product()
        wo = ProductionOrder(
            code="MO-TEST-002", product_id=product.id,
            quantity_ordered=5, status="in_progress",
            actual_start=datetime.now(timezone.utc),
        )
        db.add(wo)
        db.flush()
        svc = OrderStatusService()
        updated = svc.update_wo_status(db, wo, "completed")
        assert updated.status == "completed"
        assert updated.actual_end is not None

    def test_invalid_wo_transition_raises(self, db, make_product):
        from app.models.production_order import ProductionOrder
        product = make_product()
        wo = ProductionOrder(
            code="MO-TEST-003", product_id=product.id,
            quantity_ordered=1, status="draft",
        )
        db.add(wo)
        db.flush()
        svc = OrderStatusService()
        with pytest.raises(ValueError, match="Invalid WO status transition"):
            svc.update_wo_status(db, wo, "completed")
