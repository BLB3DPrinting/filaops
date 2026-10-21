"""
Production order quantity change — keep an order's unstarted operations and
its material reservations in step with ``quantity_ordered``.

Used by ``split_production_order`` (print-batch plan, S2). The parent keeps
``remaining`` units, so every operation that has not started yet must plan
``remaining`` units' minutes and material, and the reservation ledger must
hold ``remaining`` units' worth. Without this, completing the parent consumes
the original quantity's filament on top of what the child consumes.

Operations already queued, running or complete are left alone: their
schedule and their material requirement reflect work that is committed.
"""
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import ProductionOrder, ProductionOrderOperation
from app.models.inventory import InventoryTransaction
from app.models.manufacturing import RoutingOperationMaterial

logger = get_logger(__name__)

# Operations that have not been started. Same rule as
# refresh_production_order_routing, which may replace exactly these.
UNSTARTED_OPERATION_STATUSES = ("pending", "cancelled")

# Units that are counted, not measured: a requirement is rounded up to a whole one.
COUNTED_UNITS = ("EA", "EACH", "PCS", "UNIT", "BOX", "BOXES")


def round_up_counted_units(quantity: Decimal, unit: Optional[str]) -> Decimal:
    """A requirement in a counted unit is a whole number of pieces: round up.
    Measured units (grams, millilitres) are returned as they are."""
    if (unit or "").upper() in COUNTED_UNITS:
        return Decimal(math.ceil(quantity))
    return quantity


def required_quantity_for_routing_material(
    rom: RoutingOperationMaterial,
    order_quantity: Union[int, Decimal],
) -> Decimal:
    """How much of ``rom`` an order of ``order_quantity`` units needs.

    The routing material's own rule (per unit or per batch, scrap factor
    included), rounded up to a whole piece for counted units. This is the one
    rule for materialising a routing material onto an order, used when the
    operations are first copied and again when the order's quantity changes.
    ``order_quantity`` is the order's exact quantity: it may be fractional.
    """
    qty_required = rom.calculate_required_quantity(order_quantity)
    return round_up_counted_units(qty_required, rom.unit)


def rescale_unstarted_operations(
    db: Session,
    order: ProductionOrder,
    original_quantity: Union[int, Decimal],
) -> List[ProductionOrderOperation]:
    """Recompute planned minutes and material requirements of the order's
    unstarted operations for its current ``quantity_ordered``.

    An operation linked to its routing operation is recomputed from the
    routing (run time per unit, each material's own quantity rule). One
    without a routing link is scaled by ``quantity_ordered / original_quantity``.
    Material rows already consumed are never touched. Both quantities are
    exact: a fractional order is not truncated to whole pieces.

    Returns the operations that were recomputed.
    """
    original_quantity = Decimal(str(original_quantity))
    new_quantity = Decimal(str(order.quantity_ordered))
    if original_quantity <= 0 or new_quantity == original_quantity:
        return []
    ratio = new_quantity / original_quantity

    rescaled: List[ProductionOrderOperation] = []
    for op in order.operations:
        if op.status not in UNSTARTED_OPERATION_STATUSES:
            continue

        rop = op.routing_operation
        if rop is not None:
            op.planned_run_minutes = Decimal(str(rop.run_time_minutes or 0)) * new_quantity
        else:
            op.planned_run_minutes = Decimal(str(op.planned_run_minutes or 0)) * ratio

        for mat in op.materials:
            if mat.status == "consumed":
                continue
            rom = mat.routing_material
            if rom is not None:
                mat.quantity_required = required_quantity_for_routing_material(rom, new_quantity)
            else:
                mat.quantity_required = round_up_counted_units(
                    Decimal(str(mat.quantity_required or 0)) * ratio, mat.unit
                )

        rescaled.append(op)

    if rescaled:
        logger.info(
            "Rescaled %d unstarted operation(s) of %s from %s to %s units",
            len(rescaled), order.code, original_quantity, new_quantity,
        )
    return rescaled


def release_excess_reservations(
    db: Session,
    order: ProductionOrder,
    created_by: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Bring the order's reservations down to what its material rows require.

    The mirror image of ``reserve_production_materials``' top-up: for each
    component, the net reserved quantity in the ledger (reservations minus
    releases) is compared with the requirement, and only the excess is
    released, as one ``reservation_release`` ledger row plus the matching
    decrease of the inventory record's allocated quantity. Components that
    are not over-reserved are left as they are. The op-material rows'
    ``quantity_allocated`` is then redistributed from the net reserved
    quantity, so no row shows more allocated than it requires.

    Returns one record per component that had reservation released.
    """
    # Imported here: inventory_service does not import this module, and the
    # ledger helpers it shares with the reservation path stay in one place.
    from app.services.inventory_service import (
        _get_net_reserved_by_component,
        _get_reservation_requirements,
        _sync_op_material_allocation,
        get_effective_cost_per_inventory_unit,
        get_or_create_default_location,
        get_or_create_inventory,
    )

    net_reserved = _get_net_reserved_by_component(db, order.id)
    if not net_reserved:
        return []

    requirements = _get_reservation_requirements(db, order)
    location = get_or_create_default_location(db)
    releases: List[Dict[str, Any]] = []

    for component_id, req in requirements.items():
        reserved = net_reserved.get(component_id, Decimal("0"))
        required = Decimal(str(req["quantity"]))
        excess = reserved - required
        if excess <= Decimal("0"):
            continue

        component = req["component"]
        component_unit = req["unit"]

        inventory = get_or_create_inventory(db, component_id, location.id)
        current_allocated = Decimal(str(inventory.allocated_quantity))
        inventory.allocated_quantity = max(Decimal("0"), current_allocated - excess)
        inventory.updated_at = datetime.now(timezone.utc)

        unit_cost = get_effective_cost_per_inventory_unit(component)
        db.add(InventoryTransaction(
            product_id=component_id,
            location_id=location.id,
            transaction_type="reservation_release",
            quantity=excess,
            reference_type="production_order",
            reference_id=order.id,
            notes=(
                f"Released excess reservation for PO#{order.code}: "
                f"{excess} {component_unit} of {component.name} "
                f"(requirement now {required}, net reserved was {reserved})"
            ),
            cost_per_unit=unit_cost,
            total_cost=excess * unit_cost if unit_cost else None,
            unit=component_unit,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        ))
        net_reserved[component_id] = required

        releases.append({
            "product_id": component_id,
            "product_sku": component.sku,
            "quantity_released": float(excess),
            "required": float(required),
            "unit": component_unit,
        })
        logger.info(
            "Released %s %s of %s over-reserved on PO#%s (requirement now %s)",
            excess, component_unit, component.sku, order.code, required,
        )

    # Redistribute what is still reserved across the op-material rows, so a
    # row whose requirement shrank no longer shows the old allocation.
    for component_id in requirements:
        qty_net = net_reserved.get(component_id, Decimal("0"))
        if qty_net > Decimal("0"):
            _sync_op_material_allocation(db, order, component_id, qty_net)

    return releases
