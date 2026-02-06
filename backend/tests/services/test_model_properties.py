"""
Tests for production order model properties and computed fields.

Covers:
- ProductionOrder: quantity, completion_percent, is_complete, is_scrapped,
  is_remake, is_qc_required, is_ready_for_qc, can_close, needs_remake,
  quantity_remaining, __repr__
- ProductionOrderOperation: is_complete, is_running, efficiency_percent, __repr__
- ProductionOrderMaterial: __repr__
- ProductionOrderOperationMaterial: quantity_remaining, is_fully_consumed,
  is_allocated, shortage_quantity, __repr__
- ScrapRecord: __repr__
"""
from datetime import datetime
from decimal import Decimal

import pytest

from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderMaterial,
    ProductionOrderOperationMaterial,
    ScrapRecord,
)


# ===========================================================================
# ProductionOrder properties
# ===========================================================================


class TestProductionOrderProperties:
    """Test computed @property attributes on ProductionOrder."""

    def test_quantity_alias(self, db, make_product, make_production_order):
        """quantity should be a legacy alias for quantity_ordered."""
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=25)
        assert po.quantity == po.quantity_ordered
        assert float(po.quantity) == 25.0

    def test_quantity_remaining_no_completion(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=10)
        assert po.quantity_remaining == 10.0

    def test_quantity_remaining_partial_completion(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=10, quantity_completed=Decimal("4"))
        assert po.quantity_remaining == 6.0

    def test_quantity_remaining_fully_completed(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=10, quantity_completed=Decimal("10"))
        assert po.quantity_remaining == 0.0

    def test_quantity_remaining_over_completed(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=5, quantity_completed=Decimal("7"))
        assert po.quantity_remaining == -2.0

    def test_completion_percent_zero_ordered(self, db, make_product, make_production_order):
        """If quantity_ordered is 0, completion_percent should be 0."""
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=0)
        assert po.completion_percent == 0

    def test_completion_percent_partial(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=10, quantity_completed=Decimal("3"))
        assert po.completion_percent == 30.0

    def test_completion_percent_full(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=10, quantity_completed=Decimal("10"))
        assert po.completion_percent == 100.0

    def test_completion_percent_rounding(self, db, make_product, make_production_order):
        """completion_percent should round to 1 decimal place."""
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=3, quantity_completed=Decimal("1"))
        # 1/3 * 100 = 33.333... rounded to 33.3
        assert po.completion_percent == 33.3

    def test_is_complete_true(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=5, quantity_completed=Decimal("5"))
        assert po.is_complete is True

    def test_is_complete_false(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=5, quantity_completed=Decimal("3"))
        assert po.is_complete is False

    def test_is_complete_over_completed(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, quantity=5, quantity_completed=Decimal("7"))
        assert po.is_complete is True

    def test_is_scrapped_by_status(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, status="scrapped")
        assert po.is_scrapped is True

    def test_is_scrapped_by_scrapped_at(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, status="draft", scrapped_at=datetime.utcnow())
        assert po.is_scrapped is True

    def test_is_scrapped_false(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, status="draft")
        assert po.is_scrapped is False

    def test_is_remake_true(self, db, make_product, make_production_order):
        product = make_product()
        original = make_production_order(product_id=product.id)
        remake = make_production_order(product_id=product.id, remake_of_id=original.id)
        assert remake.is_remake is True

    def test_is_remake_false(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id)
        assert po.is_remake is False

    def test_is_qc_required_true(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, qc_status="pending")
        assert po.is_qc_required is True

    def test_is_qc_required_false(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, qc_status="not_required")
        assert po.is_qc_required is False

    def test_is_ready_for_qc_true(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id, status="completed", qc_status="pending",
        )
        assert po.is_ready_for_qc is True

    def test_is_ready_for_qc_false_wrong_status(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id, status="in_progress", qc_status="pending",
        )
        assert po.is_ready_for_qc is False

    def test_is_ready_for_qc_false_wrong_qc_status(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id, status="completed", qc_status="passed",
        )
        assert po.is_ready_for_qc is False

    def test_can_close_with_passed_qc(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id,
            status="completed",
            qc_status="passed",
            quantity=5,
            quantity_completed=Decimal("5"),
        )
        assert po.can_close is True

    def test_can_close_with_not_required_qc(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id,
            status="completed",
            qc_status="not_required",
            quantity=5,
            quantity_completed=Decimal("5"),
        )
        assert po.can_close is True

    def test_can_close_with_waived_qc(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id,
            status="completed",
            qc_status="waived",
            quantity=5,
            quantity_completed=Decimal("5"),
        )
        assert po.can_close is True

    def test_can_close_false_not_completed(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id,
            status="in_progress",
            qc_status="passed",
            quantity=5,
            quantity_completed=Decimal("5"),
        )
        assert po.can_close is False

    def test_can_close_false_qc_failed(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id,
            status="completed",
            qc_status="failed",
            quantity=5,
            quantity_completed=Decimal("5"),
        )
        assert po.can_close is False

    def test_can_close_false_quantity_not_met(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id,
            status="completed",
            qc_status="passed",
            quantity=10,
            quantity_completed=Decimal("5"),
        )
        assert po.can_close is False

    def test_needs_remake_true(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id,
            status="scrapped",
            quantity_scrapped=Decimal("3"),
        )
        assert po.needs_remake is True

    def test_needs_remake_false_not_scrapped(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id, status="draft")
        assert po.needs_remake is False

    def test_needs_remake_false_zero_scrapped(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(
            product_id=product.id,
            status="scrapped",
            quantity_scrapped=Decimal("0"),
        )
        assert po.needs_remake is False

    def test_repr(self, db, make_product, make_production_order):
        product = make_product(sku="WIDG-001")
        po = make_production_order(product_id=product.id, quantity=10)
        # Force load the relationship
        db.refresh(po)
        r = repr(po)
        assert "ProductionOrder" in r
        assert po.code in r
        assert "WIDG-001" in r

    def test_repr_no_product(self, db, make_production_order):
        """__repr__ should handle missing product gracefully."""
        po = ProductionOrder(
            code="WO-NOPROD",
            product_id=999999,
            quantity_ordered=1,
            status="draft",
            source="manual",
        )
        # Don't add to DB; product relationship will be None
        r = repr(po)
        assert "N/A" in r


# ===========================================================================
# ProductionOrderOperation properties
# ===========================================================================


class TestProductionOrderOperationProperties:
    """Test computed properties on ProductionOrderOperation."""

    def test_is_complete_true(self, db, make_production_order, make_product, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="complete",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        assert op.is_complete is True

    def test_is_complete_false(self, db, make_production_order, make_product, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="pending",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        assert op.is_complete is False

    def test_is_running_true(self, db, make_production_order, make_product, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="running",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        assert op.is_running is True

    def test_is_running_false(self, db, make_production_order, make_product, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="complete",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        assert op.is_running is False

    def test_efficiency_percent_normal(self, db, make_production_order, make_product, make_work_center):
        """If planned=100 min and actual=80 min, efficiency=125% (faster than planned)."""
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="complete",
            planned_run_minutes=Decimal("100"),
            actual_run_minutes=Decimal("80"),
        )
        db.add(op)
        db.flush()

        assert op.efficiency_percent == 125.0

    def test_efficiency_percent_slow(self, db, make_production_order, make_product, make_work_center):
        """If planned=60 min and actual=120 min, efficiency=50%."""
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="complete",
            planned_run_minutes=Decimal("60"),
            actual_run_minutes=Decimal("120"),
        )
        db.add(op)
        db.flush()

        assert op.efficiency_percent == 50.0

    def test_efficiency_percent_no_planned(self, db, make_production_order, make_product, make_work_center):
        """Returns None if planned_run_minutes is 0 or None."""
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="complete",
            planned_run_minutes=Decimal("0"),
            actual_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        assert op.efficiency_percent is None

    def test_efficiency_percent_no_actual(self, db, make_production_order, make_product, make_work_center):
        """Returns None if actual_run_minutes is not set."""
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="pending",
            planned_run_minutes=Decimal("60"),
            actual_run_minutes=None,
        )
        db.add(op)
        db.flush()

        assert op.efficiency_percent is None

    def test_repr(self, db, make_production_order, make_product, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="3D Print",
            status="running",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        r = repr(op)
        assert "ProductionOrderOperation" in r
        assert "3D Print" in r
        assert "running" in r


# ===========================================================================
# ProductionOrderMaterial __repr__
# ===========================================================================


class TestProductionOrderMaterialRepr:
    """Test __repr__ for ProductionOrderMaterial."""

    def test_repr(self, db, make_product, make_production_order):
        product = make_product()
        substitute = make_product(name="Substitute Material")
        po = make_production_order(product_id=product.id)

        mat = ProductionOrderMaterial(
            production_order_id=po.id,
            original_product_id=product.id,
            original_quantity=Decimal("100"),
            substitute_product_id=substitute.id,
            planned_quantity=Decimal("100"),
            reason="Out of stock",
        )
        db.add(mat)
        db.flush()

        r = repr(mat)
        assert "ProductionOrderMaterial" in r
        assert str(product.id) in r
        assert str(substitute.id) in r


# ===========================================================================
# ProductionOrderOperationMaterial properties
# ===========================================================================


class TestProductionOrderOperationMaterialProperties:
    """Test computed properties on ProductionOrderOperationMaterial."""

    def test_quantity_remaining_full(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="pending",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Black")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("200"),
            quantity_consumed=Decimal("0"),
            unit="G",
        )
        db.add(mat)
        db.flush()

        assert mat.quantity_remaining == 200.0

    def test_quantity_remaining_partial(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="running",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Red")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("200"),
            quantity_consumed=Decimal("150"),
            unit="G",
        )
        db.add(mat)
        db.flush()

        assert mat.quantity_remaining == 50.0

    def test_is_fully_consumed_true(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="complete",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Blue")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("100"),
            quantity_consumed=Decimal("100"),
            unit="G",
        )
        db.add(mat)
        db.flush()

        assert mat.is_fully_consumed is True

    def test_is_fully_consumed_false(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="running",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Green")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("100"),
            quantity_consumed=Decimal("50"),
            unit="G",
        )
        db.add(mat)
        db.flush()

        assert mat.is_fully_consumed is False

    def test_is_allocated_when_allocated(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="running",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA White")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("100"),
            quantity_allocated=Decimal("100"),
            unit="G",
            status="allocated",
        )
        db.add(mat)
        db.flush()

        assert mat.is_allocated is True

    def test_is_allocated_when_consumed(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="complete",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Yellow")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("100"),
            quantity_consumed=Decimal("100"),
            unit="G",
            status="consumed",
        )
        db.add(mat)
        db.flush()

        assert mat.is_allocated is True

    def test_is_allocated_false_when_pending(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="pending",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Orange")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("100"),
            unit="G",
            status="pending",
        )
        db.add(mat)
        db.flush()

        assert mat.is_allocated is False

    def test_shortage_quantity_no_allocation(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="pending",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Pink")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("200"),
            quantity_allocated=Decimal("0"),
            unit="G",
        )
        db.add(mat)
        db.flush()

        assert mat.shortage_quantity == 200.0

    def test_shortage_quantity_partial(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="running",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Purple")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("200"),
            quantity_allocated=Decimal("150"),
            unit="G",
            status="allocated",
        )
        db.add(mat)
        db.flush()

        assert mat.shortage_quantity == 50.0

    def test_shortage_quantity_fully_allocated(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="running",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Teal")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("200"),
            quantity_allocated=Decimal("200"),
            unit="G",
            status="allocated",
        )
        db.add(mat)
        db.flush()

        assert mat.shortage_quantity == 0.0

    def test_shortage_quantity_over_allocated(self, db, make_product, make_production_order, make_work_center):
        """Over-allocation should not produce a negative shortage."""
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="running",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(name="PLA Silver")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("100"),
            quantity_allocated=Decimal("150"),
            unit="G",
            status="allocated",
        )
        db.add(mat)
        db.flush()

        assert mat.shortage_quantity == 0.0

    def test_repr(self, db, make_product, make_production_order, make_work_center):
        product = make_product()
        po = make_production_order(product_id=product.id)
        wc = make_work_center()

        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_name="Print",
            status="pending",
            planned_run_minutes=Decimal("60"),
        )
        db.add(op)
        db.flush()

        component = make_product(sku="MAT-BLK-001", name="Black PLA")
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=component.id,
            quantity_required=Decimal("370"),
            unit="G",
        )
        db.add(mat)
        db.flush()

        # Refresh to load relationships
        db.refresh(mat)
        r = repr(mat)
        assert "POOpMaterial" in r
        assert "370" in r
        assert "G" in r
        assert "pending" in r


# ===========================================================================
# ScrapRecord __repr__
# ===========================================================================


class TestScrapRecordRepr:
    """Test __repr__ for ScrapRecord."""

    def test_repr(self, db, make_product, make_production_order):
        product = make_product()
        po = make_production_order(product_id=product.id)

        scrap = ScrapRecord(
            production_order_id=po.id,
            product_id=product.id,
            quantity=Decimal("5"),
            unit_cost=Decimal("2.50"),
            total_cost=Decimal("12.50"),
        )
        db.add(scrap)
        db.flush()

        r = repr(scrap)
        assert "ScrapRecord" in r
        assert str(scrap.id) in r
        assert "5" in r
        assert "12.50" in r
