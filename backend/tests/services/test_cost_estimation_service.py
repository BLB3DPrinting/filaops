"""
Tests for app/services/cost_estimation_service.py

Covers:
- estimate_material_cost: Material cost from BOM components
- estimate_labor_cost: Labor cost from work center rates
- estimate_production_order_cost: Full estimation + order field population
- recalculate_actual_cost: Actual cost from consumed quantities / actual times
"""
import pytest
from decimal import Decimal

from app.models import ProductionOrder
from app.models.production_order import (
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.models.work_center import WorkCenter
from app.services import production_order_service as po_svc
from app.services.cost_estimation_service import (
    estimate_material_cost,
    estimate_labor_cost,
    estimate_production_order_cost,
    recalculate_actual_cost,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_order(db, product, *, quantity=10, status="draft"):
    code = po_svc.generate_production_order_code(db)
    order = ProductionOrder(
        code=code,
        product_id=product.id,
        quantity_ordered=quantity,
        quantity_completed=0,
        quantity_scrapped=0,
        source="manual",
        status=status,
        priority=3,
        created_by="test@filaops.dev",
    )
    db.add(order)
    db.flush()
    return order


def _add_operation(db, order, *, planned_run=60, planned_setup=0, actual_run=None, actual_setup=None, status="pending"):
    op = ProductionOrderOperation(
        production_order_id=order.id,
        work_center_id=1,
        sequence=10,
        operation_code="PRINT",
        operation_name="Print",
        planned_setup_minutes=planned_setup,
        planned_run_minutes=planned_run,
        actual_run_minutes=actual_run,
        actual_setup_minutes=actual_setup,
        status=status,
    )
    db.add(op)
    db.flush()
    return op


def _add_material(db, op, component, *, qty_required=500, qty_consumed=0, mat_status="pending"):
    mat = ProductionOrderOperationMaterial(
        production_order_operation_id=op.id,
        component_id=component.id,
        quantity_required=Decimal(str(qty_required)),
        unit="G",
        quantity_allocated=Decimal("0"),
        quantity_consumed=Decimal(str(qty_consumed)),
        status=mat_status,
    )
    db.add(mat)
    db.flush()
    return mat


# =============================================================================
# estimate_material_cost
# =============================================================================

class TestEstimateMaterialCost:
    def test_empty_order(self, db, finished_good):
        """Order with no operations returns zero."""
        order = _make_order(db, finished_good)
        assert estimate_material_cost(db, order) == Decimal("0")

    def test_uses_quantity_required(self, db, finished_good, raw_material):
        """Should price materials using quantity_required and effective cost."""
        order = _make_order(db, finished_good)
        op = _add_operation(db, order)
        _add_material(db, op, raw_material, qty_required=500)

        cost = estimate_material_cost(db, order)
        # raw_material: average_cost=0.02/G, qty=500G → 10.00
        assert cost == pytest.approx(Decimal("10"), abs=Decimal("0.01"))


# =============================================================================
# estimate_labor_cost
# =============================================================================

class TestEstimateLaborCost:
    def test_empty_order(self, db, finished_good):
        """Order with no operations returns zero."""
        order = _make_order(db, finished_good)
        assert estimate_labor_cost(order) == Decimal("0")

    def test_uses_planned_minutes(self, db, finished_good, raw_material):
        """Should calculate from planned_run_minutes + planned_setup_minutes."""
        wc = db.query(WorkCenter).filter(WorkCenter.id == 1).first()
        wc.labor_rate_per_hour = Decimal("30")
        wc.machine_rate_per_hour = Decimal("0")
        wc.overhead_rate_per_hour = Decimal("0")
        db.flush()

        order = _make_order(db, finished_good)
        _add_operation(db, order, planned_run=120, planned_setup=0)

        cost = estimate_labor_cost(order)
        # 120 min = 2 hours × $30/hr = $60
        assert cost == pytest.approx(Decimal("60"), abs=Decimal("0.01"))

    def test_falls_back_to_hourly_rate(self, db, finished_good):
        """When component rates are zero, uses simplified hourly_rate."""
        wc = db.query(WorkCenter).filter(WorkCenter.id == 1).first()
        wc.labor_rate_per_hour = Decimal("0")
        wc.machine_rate_per_hour = Decimal("0")
        wc.overhead_rate_per_hour = Decimal("0")
        wc.hourly_rate = Decimal("50")
        db.flush()

        order = _make_order(db, finished_good)
        _add_operation(db, order, planned_run=60)

        cost = estimate_labor_cost(order)
        # 60 min = 1 hour × $50/hr = $50
        assert cost == pytest.approx(Decimal("50"), abs=Decimal("0.01"))



# =============================================================================
# estimate_production_order_cost
# =============================================================================

class TestEstimateProductionOrderCost:
    def test_populates_order_fields(self, db, finished_good, raw_material):
        """Should set estimated_material_cost, estimated_labor_cost, estimated_total_cost."""
        wc = db.query(WorkCenter).filter(WorkCenter.id == 1).first()
        wc.labor_rate_per_hour = Decimal("25")
        wc.machine_rate_per_hour = Decimal("0")
        wc.overhead_rate_per_hour = Decimal("0")
        db.flush()

        order = _make_order(db, finished_good)
        op = _add_operation(db, order, planned_run=60)
        _add_material(db, op, raw_material, qty_required=500)

        result = estimate_production_order_cost(db, order)

        # Material: 500G × 0.02 = 10.00, Labor: 1hr × $25 = 25.00
        assert result["material_cost"] == pytest.approx(Decimal("10"), abs=Decimal("0.01"))
        assert result["labor_cost"] == pytest.approx(Decimal("25"), abs=Decimal("0.01"))
        assert result["total_cost"] == pytest.approx(Decimal("35"), abs=Decimal("0.01"))

        # Verify fields populated on order object
        assert order.estimated_material_cost == pytest.approx(Decimal("10"), abs=Decimal("0.01"))
        assert order.estimated_labor_cost == pytest.approx(Decimal("25"), abs=Decimal("0.01"))
        assert order.estimated_total_cost == pytest.approx(Decimal("35"), abs=Decimal("0.01"))


# =============================================================================
# recalculate_actual_cost
# =============================================================================

class TestRecalculateActualCost:
    def test_uses_consumed_qty_when_status_consumed(self, db, finished_good, raw_material):
        """Materials with status 'consumed' should use quantity_consumed."""
        order = _make_order(db, finished_good)
        op = _add_operation(db, order, actual_run=90)
        _add_material(
            db, op, raw_material,
            qty_required=500,
            qty_consumed=450,
            mat_status="consumed",
        )

        result = recalculate_actual_cost(db, order)
        # 450G × 0.02 = 9.00
        assert result["material_cost"] == pytest.approx(Decimal("9"), abs=Decimal("0.01"))

    def test_falls_back_to_required_when_pending(self, db, finished_good, raw_material):
        """Materials with status 'pending' should use quantity_required."""
        order = _make_order(db, finished_good)
        op = _add_operation(db, order, actual_run=60)
        _add_material(
            db, op, raw_material,
            qty_required=500,
            qty_consumed=0,
            mat_status="pending",
        )

        result = recalculate_actual_cost(db, order)
        # 500G × 0.02 = 10.00 (required, not consumed)
        assert result["material_cost"] == pytest.approx(Decimal("10"), abs=Decimal("0.01"))

    def test_zero_consumed_qty_with_consumed_status(self, db, finished_good, raw_material):
        """Edge case: status is 'consumed' but quantity_consumed is 0 (zero actual usage)."""
        order = _make_order(db, finished_good)
        op = _add_operation(db, order, actual_run=60)
        _add_material(
            db, op, raw_material,
            qty_required=500,
            qty_consumed=0,
            mat_status="consumed",
        )

        result = recalculate_actual_cost(db, order)
        # Status is consumed → uses quantity_consumed (0), so material cost = 0
        assert result["material_cost"] == Decimal("0")

    def test_uses_actual_run_minutes(self, db, finished_good):
        """Should prefer actual_run_minutes over planned when available."""
        wc = db.query(WorkCenter).filter(WorkCenter.id == 1).first()
        wc.labor_rate_per_hour = Decimal("30")
        wc.machine_rate_per_hour = Decimal("0")
        wc.overhead_rate_per_hour = Decimal("0")
        db.flush()

        order = _make_order(db, finished_good)
        _add_operation(db, order, planned_run=60, actual_run=Decimal("90"))

        result = recalculate_actual_cost(db, order)
        # 90 min = 1.5 hours × $30/hr = $45
        assert result["labor_cost"] == pytest.approx(Decimal("45"), abs=Decimal("0.01"))

    def test_populates_actual_fields(self, db, finished_good, raw_material):
        """Should set actual_material_cost, actual_labor_cost, actual_total_cost."""
        wc = db.query(WorkCenter).filter(WorkCenter.id == 1).first()
        wc.labor_rate_per_hour = Decimal("25")
        wc.machine_rate_per_hour = Decimal("0")
        wc.overhead_rate_per_hour = Decimal("0")
        db.flush()

        order = _make_order(db, finished_good)
        op = _add_operation(db, order, planned_run=60, actual_run=Decimal("120"))
        _add_material(
            db, op, raw_material,
            qty_required=500,
            qty_consumed=480,
            mat_status="consumed",
        )

        recalculate_actual_cost(db, order)

        assert order.actual_material_cost == pytest.approx(Decimal("9.60"), abs=Decimal("0.01"))
        assert order.actual_labor_cost == pytest.approx(Decimal("50"), abs=Decimal("0.01"))
        assert order.actual_total_cost == pytest.approx(Decimal("59.60"), abs=Decimal("0.01"))
