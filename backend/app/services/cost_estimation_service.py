"""
Cost Estimation Service — Automated cost calculation for production orders.

Calculates estimated costs from BOM materials and routing operations using
actual work center rates (machine + labor + overhead) instead of hardcoded values.

Cost formula per production order:
  Material Cost = Σ(material_qty × cost_per_inventory_unit) across all operations
  Labor Cost = Σ(operation_minutes / 60 × work_center_hourly_rate) across all operations
  Total Cost = Material Cost + Labor Cost

Uses get_effective_cost_per_inventory_unit() for material pricing (single source of truth).
Uses work center rates (machine + labor + overhead) for labor/machine pricing.
"""
from decimal import Decimal

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import ProductionOrder
from app.services.inventory_service import get_effective_cost_per_inventory_unit

logger = get_logger(__name__)


def estimate_material_cost(db: Session, order: ProductionOrder) -> Decimal:
    """
    Calculate estimated material cost for a production order.

    Walks all operation materials and prices them using the product's
    effective cost per inventory unit (respects the product's configured
    cost method with proper UOM conversion).

    Returns:
        Total estimated material cost as Decimal.
    """
    total = Decimal("0")

    for op in order.operations:
        for mat in op.materials:
            if not mat.component:
                continue

            cost_per_unit = get_effective_cost_per_inventory_unit(mat.component)
            if cost_per_unit is None:
                cost_per_unit = Decimal("0")

            qty = mat.quantity_required or Decimal("0")
            total += Decimal(str(qty)) * cost_per_unit

    return total


def estimate_labor_cost(order: ProductionOrder) -> Decimal:
    """
    Calculate estimated labor cost for a production order.

    Uses the work center's component rates (machine + labor + overhead)
    for each operation. Falls back to the work center's simplified
    hourly_rate if component rates are all zero.

    Returns:
        Total estimated labor cost as Decimal.
    """
    total = Decimal("0")

    for op in order.operations:
        minutes = Decimal(str(op.planned_run_minutes or 0)) + Decimal(str(op.planned_setup_minutes or 0))
        hours = minutes / Decimal("60")

        wc = op.work_center
        if wc:
            # Use component rates if available
            machine = Decimal(str(wc.machine_rate_per_hour or 0))
            labor = Decimal(str(wc.labor_rate_per_hour or 0))
            overhead = Decimal(str(wc.overhead_rate_per_hour or 0))
            combined = machine + labor + overhead

            # Fall back to simplified hourly_rate if component rates are all zero
            if combined == Decimal("0"):
                combined = Decimal(str(wc.hourly_rate or 0))

            total += hours * combined
        # If no work center, cost is zero (don't use hardcoded fallback)

    return total


def estimate_production_order_cost(db: Session, order: ProductionOrder) -> dict:
    """
    Calculate and store estimated costs on a production order.

    Populates:
      - order.estimated_material_cost
      - order.estimated_labor_cost
      - order.estimated_total_cost

    Returns:
        Dict with material_cost, labor_cost, total_cost (all Decimal).
    """
    material_cost = estimate_material_cost(db, order)
    labor_cost = estimate_labor_cost(order)
    total_cost = material_cost + labor_cost

    order.estimated_material_cost = material_cost
    order.estimated_labor_cost = labor_cost
    order.estimated_total_cost = total_cost

    logger.info(
        "Estimated costs for %s: material=%s, labor=%s, total=%s",
        order.code, material_cost, labor_cost, total_cost,
    )

    return {
        "material_cost": material_cost,
        "labor_cost": labor_cost,
        "total_cost": total_cost,
    }


def recalculate_actual_cost(db: Session, order: ProductionOrder) -> dict:
    """
    Calculate actual costs from consumed quantities and actual times.

    Called after production completes. Uses actual_run_minutes and
    quantity_consumed where available, falling back to planned values.

    Populates:
      - order.actual_material_cost
      - order.actual_labor_cost
      - order.actual_total_cost

    Returns:
        Dict with material_cost, labor_cost, total_cost (all Decimal).
    """
    # Actual material cost — use consumed quantities
    material_cost = Decimal("0")
    for op in order.operations:
        for mat in op.materials:
            if not mat.component:
                continue

            cost_per_unit = get_effective_cost_per_inventory_unit(mat.component)
            if cost_per_unit is None:
                cost_per_unit = Decimal("0")

            # Use status field to determine if material was consumed
            qty = mat.quantity_consumed if mat.status == "consumed" else mat.quantity_required
            qty = Decimal(str(qty or 0))
            material_cost += qty * cost_per_unit

    # Actual labor cost — use actual run times
    labor_cost = Decimal("0")
    for op in order.operations:
        actual_minutes = op.actual_run_minutes if op.actual_run_minutes is not None else (op.planned_run_minutes or 0)
        setup_minutes = op.actual_setup_minutes if op.actual_setup_minutes is not None else (op.planned_setup_minutes or 0)
        minutes = Decimal(str(actual_minutes)) + Decimal(str(setup_minutes))
        hours = minutes / Decimal("60")

        wc = op.work_center
        if wc:
            machine = Decimal(str(wc.machine_rate_per_hour or 0))
            labor = Decimal(str(wc.labor_rate_per_hour or 0))
            overhead = Decimal(str(wc.overhead_rate_per_hour or 0))
            combined = machine + labor + overhead
            if combined == Decimal("0"):
                combined = Decimal(str(wc.hourly_rate or 0))
            labor_cost += hours * combined

    total_cost = material_cost + labor_cost

    order.actual_material_cost = material_cost
    order.actual_labor_cost = labor_cost
    order.actual_total_cost = total_cost

    logger.info(
        "Actual costs for %s: material=%s, labor=%s, total=%s",
        order.code, material_cost, labor_cost, total_cost,
    )

    return {
        "material_cost": material_cost,
        "labor_cost": labor_cost,
        "total_cost": total_cost,
    }
