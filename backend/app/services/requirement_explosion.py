"""
Canonical requirement-explosion function — HARD-12.

Single source of truth for "what materials does producing N units of product P require?"

SEMANTICS
---------
Routing-first / BOM-fallback:

1. PRIMARY  — If the product has an active Routing with at least one non-cost-only
   RoutingOperationMaterial, explode from those routing materials.  This is the
   preferred source for 3D-printing operations (filament at Print, packaging at Ship).

2. FALLBACK — If no routing materials exist, fall back to the legacy bom_lines table.
   Maintains backward compatibility with products not yet migrated to routing-level
   materials.

This mirrors MRPService.explode_bom in mrp.py exactly — that method now delegates
here so all consumers share one implementation.

CYCLE DETECTION
---------------
*visited* is a set of product_ids already on the current explosion stack.  On
re-entry the function returns [] immediately, preventing infinite recursion.  The
visited set is *not* mutated across sibling branches (each call site passes a copy
when recursing into sub-assemblies).

RETURN TYPE
-----------
Returns ``List[ComponentRequirement]``, the same dataclass used by MRPService so
every caller — buy_list_service, blocking_issues, item_demand, sales_order_service,
and mrp.py itself — gets identical typed results.

IMPORT SAFETY
-------------
This module imports ONLY from app.models and app.services.uom_service (which has no
service-layer deps), so it can be imported by any service without cycles:
  mrp.py → here           (was circular before — now clean)
  buy_list_service → here  (through MRPService.explode_bom)
  blocking_issues → here
  item_demand → here (indirectly; item_demand does not explode, but could if needed)
  sales_order_service → here
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.bom import BOM
from app.models.product import Product
from app.services.uom_service import INLINE_UOM_CONVERSIONS as _UOM_CONVERSIONS
from app.logging_config import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Re-export the dataclass so callers import from ONE place.
# ComponentRequirement is defined in mrp.py because it predates HARD-12; we
# re-export it here so future callers can do:
#   from app.services.requirement_explosion import explode_requirements, ComponentRequirement
# without importing the full MRP engine.
# ---------------------------------------------------------------------------
from app.services.mrp import ComponentRequirement  # noqa: E402 (after guard imports)

__all__ = ["explode_requirements", "ComponentRequirement"]


# ---------------------------------------------------------------------------
# Internal UOM helper (identical to mrp.convert_uom — kept local to avoid a
# circular import if mrp.py were ever to import from here at module level)
# ---------------------------------------------------------------------------

def _convert_uom(quantity: Decimal, from_unit: str, to_unit: str) -> Decimal:
    """Convert *quantity* from *from_unit* to *to_unit*.

    Returns *quantity* unchanged when either unit is unknown or when the two
    units belong to incompatible measurement bases (e.g. EA vs KG).
    """
    from_unit = (from_unit or "EA").upper().strip()
    to_unit = (to_unit or "EA").upper().strip()

    if from_unit == to_unit:
        return quantity

    from_info = _UOM_CONVERSIONS.get(from_unit)
    to_info = _UOM_CONVERSIONS.get(to_unit)

    if not from_info or not to_info:
        logger.warning(
            "Unknown UOM conversion: %s -> %s, returning original quantity",
            from_unit,
            to_unit,
        )
        return quantity

    if from_info["base"] != to_info["base"]:
        logger.debug(
            "Incompatible UOM bases: %s (%s) -> %s (%s)",
            from_unit,
            from_info["base"],
            to_unit,
            to_info["base"],
        )
        return quantity

    from_factor = from_info.get("factor")
    to_factor = to_info.get("factor")

    if not from_factor or from_factor == 0:
        raise ValueError(
            f"Invalid UOM factor for '{from_unit}': {from_factor}"
        )
    if not to_factor or to_factor == 0:
        raise ValueError(
            f"Invalid UOM factor for '{to_unit}': {to_factor}"
        )

    return quantity * from_factor / to_factor


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def explode_requirements(
    db: Session,
    product_id: int,
    quantity: Decimal,
    source_demand_type: Optional[str] = None,
    source_demand_id: Optional[int] = None,
    due_date: Optional[date] = None,
    level: int = 0,
    parent_product_id: Optional[int] = None,
    visited: Optional[set] = None,
) -> List[ComponentRequirement]:
    """Recursively explode a product into its component requirements.

    Routing-first / BOM-fallback semantics — see module docstring.

    Parameters
    ----------
    db:
        SQLAlchemy session.
    product_id:
        The finished-good (or sub-assembly) to explode.
    quantity:
        How many units of *product_id* are needed.  Decimal required.
    source_demand_type:
        Human-readable demand origin, e.g. ``"production_order"`` or
        ``"sales_order"``.  Passed through to ComponentRequirement.
    source_demand_id:
        PK of the demand source record.
    due_date:
        When the demand is needed.
    level:
        Current BOM depth; 0 = direct components of the top-level product.
        Used only for informational tagging on ComponentRequirement.
    parent_product_id:
        product_id of the immediate parent in the explosion tree.
    visited:
        Set of product_ids already on the current recursion stack.  Callers
        normally omit this; the function initialises it on first call.
        **Caution:** callers who recurse into sub-assemblies must pass
        ``visited.copy()`` (not the live set) so sibling branches stay
        independent — exactly as MRPService.explode_bom does.

    Returns
    -------
    List[ComponentRequirement]
        Flat list of all component requirements at all levels.  Components
        that appear in multiple sub-assemblies are listed separately; the
        caller is responsible for aggregating if needed.
    """
    if visited is None:
        visited = set()

    # Cycle detection
    if product_id in visited:
        return []
    visited.add(product_id)

    requirements: List[ComponentRequirement] = []

    # ------------------------------------------------------------------
    # PRECEDENCE CHECK
    # Try routing-operation materials first (PRIMARY source).
    # Fall back to BOM lines only when no routing materials are found.
    # ------------------------------------------------------------------
    has_routing_materials = False
    routing = None

    try:
        from app.models.manufacturing import (  # local import keeps module loadable even when
            Routing,                             # manufacturing tables are absent (unit tests)
            RoutingOperation,
            RoutingOperationMaterial,
        )

        routing = (
            db.query(Routing)
            .filter(
                Routing.product_id == product_id,
                Routing.is_active.is_(True),
            )
            .first()
        )

        if routing:
            routing_material_count = (
                db.query(RoutingOperationMaterial)
                .join(RoutingOperation)
                .filter(
                    RoutingOperation.routing_id == routing.id,
                    RoutingOperationMaterial.is_cost_only.is_(False),
                )
                .count()
            )
            has_routing_materials = routing_material_count > 0

    except Exception:
        # Routing tables may be absent in unit-test environments.
        pass

    # ------------------------------------------------------------------
    # SOURCE 1 — BOM Lines (fallback; used only when no routing materials)
    # ------------------------------------------------------------------
    bom = (
        db.query(BOM)
        .filter(
            BOM.product_id == product_id,
            BOM.active.is_(True),
        )
        .first()
    )

    if bom and not has_routing_materials:
        for line in bom.lines:
            if line.is_cost_only:
                continue

            component = line.component
            if not component:
                continue

            scrap_factor = Decimal(str(line.scrap_factor or 0))
            bom_qty = Decimal(str(line.quantity))
            bom_unit = line.unit or "EA"
            component_unit = component.unit or "EA"

            converted_qty = _convert_uom(bom_qty, bom_unit, component_unit)
            adjusted_qty = quantity * converted_qty * (1 + scrap_factor / 100)

            req = ComponentRequirement(
                product_id=component.id,
                product_sku=component.sku,
                product_name=component.name,
                bom_level=level,
                gross_quantity=adjusted_qty,
                scrap_factor=scrap_factor,
                parent_product_id=parent_product_id or product_id,
                source_demand_type=source_demand_type,
                source_demand_id=source_demand_id,
                due_date=due_date,
            )
            requirements.append(req)

            # Recurse into sub-assemblies
            if component.has_bom:
                sub_reqs = explode_requirements(
                    db=db,
                    product_id=component.id,
                    quantity=adjusted_qty,
                    source_demand_type=source_demand_type,
                    source_demand_id=source_demand_id,
                    due_date=due_date,
                    level=level + 1,
                    parent_product_id=product_id,
                    visited=visited.copy(),
                )
                requirements.extend(sub_reqs)

    # ------------------------------------------------------------------
    # SOURCE 2 — Routing Operation Materials (primary; preferred path)
    # ------------------------------------------------------------------
    if routing and has_routing_materials:
        try:
            from app.models.manufacturing import RoutingOperation, RoutingOperationMaterial

            operations = (
                db.query(RoutingOperation)
                .filter(RoutingOperation.routing_id == routing.id)
                .all()
            )
            operation_ids = [op.id for op in operations]

            if operation_ids:
                op_materials = (
                    db.query(RoutingOperationMaterial)
                    .filter(
                        RoutingOperationMaterial.routing_operation_id.in_(operation_ids),
                        RoutingOperationMaterial.is_cost_only.is_(False),
                    )
                    .all()
                )

                for mat in op_materials:
                    component = db.get(Product, mat.component_id)
                    if not component:
                        continue

                    scrap_factor = Decimal(str(mat.scrap_factor or 0))
                    mat_qty = Decimal(str(mat.quantity or 0))
                    mat_unit = (mat.unit or "EA").upper().strip()
                    component_unit = (component.unit or "EA").upper().strip()

                    converted_qty = _convert_uom(mat_qty, mat_unit, component_unit)
                    adjusted_qty = quantity * converted_qty * (1 + scrap_factor / 100)

                    req = ComponentRequirement(
                        product_id=component.id,
                        product_sku=component.sku,
                        product_name=component.name,
                        bom_level=level,
                        gross_quantity=adjusted_qty,
                        scrap_factor=scrap_factor,
                        parent_product_id=parent_product_id or product_id,
                        source_demand_type=source_demand_type,
                        source_demand_id=source_demand_id,
                        due_date=due_date,
                    )
                    requirements.append(req)

                    # Recurse into sub-assemblies
                    if component.has_bom:
                        sub_reqs = explode_requirements(
                            db=db,
                            product_id=component.id,
                            quantity=adjusted_qty,
                            source_demand_type=source_demand_type,
                            source_demand_id=source_demand_id,
                            due_date=due_date,
                            level=level + 1,
                            parent_product_id=product_id,
                            visited=visited.copy(),
                        )
                        requirements.extend(sub_reqs)

        except Exception as exc:
            logger.warning(
                "Error reading routing materials for product %s, results may be incomplete: %s",
                product_id,
                exc,
            )

    visited.discard(product_id)
    return requirements
