"""
Item Cost Service — standard-cost calculation and recosting for items.

Extracted verbatim from item_service.py (DEBT-1 D1-B mechanical split).
item_service re-exports these names for backward compatibility.
"""
from datetime import datetime, timezone

from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models import Product, BOM
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.services.bom_management_service import recalculate_bom_cost

logger = get_logger(__name__)


def calculate_item_cost(item: Product, db: Session) -> dict:
    """
    Calculate standard cost for an item.

    Returns a dict with: bom_id, bom_cost, routing_id, routing_cost,
    purchase_cost, total_cost, cost_source.
    """
    bom_cost = 0.0
    routing_cost = 0.0
    purchase_cost = 0.0
    bom_id = None
    routing_id = None
    cost_source = None

    bom = (
        db.query(BOM)
        .filter(BOM.product_id == item.id, BOM.active.is_(True))
        .first()
    )

    # Check for active routing (independent of BOM — variant items may
    # have a routing with materials but no BOM)
    routing = (
        db.query(Routing)
        .options(
            joinedload(Routing.operations)
            .joinedload(RoutingOperation.work_center),
            joinedload(Routing.operations)
            .joinedload(RoutingOperation.materials)
            .joinedload(RoutingOperationMaterial.component),
        )
        .filter(Routing.product_id == item.id, Routing.is_active.is_(True))
        .order_by(desc(Routing.version))
        .first()
    )

    if bom or routing:
        cost_source = "manufactured"

        if bom:
            bom_id = bom.id

        # Collect component IDs costed via routing operations to avoid
        # double-counting the same material in both BOM and routing.
        # Design: if a component_id is on routing, ALL BOM lines with
        # that component are excluded (routing owns that material fully).
        # This matches override_map behavior in duplicate_item().
        routing_material_ids = set()
        if routing:
            routing.recalculate_totals()
            routing_cost = float(routing.total_cost) if routing.total_cost else 0.0
            routing_id = routing.id
            for op in routing.operations:
                if op.is_active:
                    for mat in op.materials:
                        # Only include per-unit materials — batch/order are
                        # excluded from material_cost so must not exclude
                        # the matching BOM line either (would lose the cost)
                        is_per_unit = not mat.quantity_per or str(mat.quantity_per).strip().lower() == "unit"
                        if is_per_unit and mat.extended_cost and mat.extended_cost > 0:
                            routing_material_ids.add(mat.component_id)

        # BOM cost calculation (only if BOM exists)
        if bom:
            # Always store full BOM cost (what the BOM page shows)
            full_bom_cost = recalculate_bom_cost(bom, db)
            bom.total_cost = full_bom_cost

            # For item STD cost, subtract routing-owned material costs from
            # the full BOM to avoid double-counting. Uses only_component_ids
            # to compute just the overlap — components are already in the
            # SQLAlchemy session cache from the first call.
            if routing_material_ids:
                overlap_cost = recalculate_bom_cost(
                    bom, db, only_component_ids=routing_material_ids
                )
                bom_cost = float(full_bom_cost - overlap_cost)
            else:
                bom_cost = float(full_bom_cost)

        total_cost = bom_cost + routing_cost
    else:
        cost_source = "purchased"
        if item.standard_cost and item.standard_cost > 0:
            purchase_cost = float(item.standard_cost)
        elif item.average_cost:
            purchase_cost = float(item.average_cost)
        elif item.last_cost:
            purchase_cost = float(item.last_cost)

        total_cost = purchase_cost

    return {
        "bom_id": bom_id,
        "bom_cost": bom_cost,
        "routing_id": routing_id,
        "routing_cost": routing_cost,
        "purchase_cost": purchase_cost,
        "total_cost": total_cost,
        "cost_source": cost_source,
    }


def recost_item(db: Session, item_id: int) -> dict:
    """Recost a single item and return the result."""
    # Function-level import avoids a circular import with item_service,
    # which re-exports this module's public functions.
    from app.services.item_service import get_item

    item = get_item(db, item_id)
    cost_data = calculate_item_cost(item, db)

    old_cost = float(item.standard_cost) if item.standard_cost else 0
    item.standard_cost = cost_data["total_cost"]
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)

    logger.info(
        f"Recost item {item.sku}: ${old_cost:.4f} -> ${cost_data['total_cost']:.4f}"
    )

    return {
        "id": item.id,
        "sku": item.sku,
        "name": item.name,
        "old_cost": old_cost,
        "new_cost": cost_data["total_cost"],
        "cost_source": cost_data["cost_source"],
        "bom_id": cost_data["bom_id"],
        "bom_cost": cost_data["bom_cost"],
        "routing_id": cost_data["routing_id"],
        "routing_cost": cost_data["routing_cost"],
        "purchase_cost": cost_data["purchase_cost"],
        "message": f"Standard cost updated: ${old_cost:.4f} -> ${cost_data['total_cost']:.4f}",
    }


def recost_all_items(
    db: Session,
    *,
    item_type: str | None = None,
    category_id: int | None = None,
    cost_source_filter: str | None = None,
) -> dict:
    """
    Recost all items matching filters.

    Returns dict with: updated, skipped, items (list of results).
    """
    # Function-level import avoids a circular import with item_service,
    # which re-exports this module's public functions.
    from app.services.item_service import get_category_and_descendants

    query = db.query(Product).filter(Product.active.is_(True))

    if item_type:
        query = query.filter(Product.item_type == item_type)

    if category_id:
        category_ids = get_category_and_descendants(db, category_id)
        query = query.filter(Product.category_id.in_(category_ids))

    items = query.all()

    updated = 0
    skipped = 0
    results = []

    for item in items:
        cost_data = calculate_item_cost(item, db)

        if cost_source_filter and cost_data["cost_source"] != cost_source_filter:
            continue

        if cost_data["total_cost"] == 0:
            skipped += 1
            continue

        old_cost = float(item.standard_cost) if item.standard_cost else 0
        item.standard_cost = cost_data["total_cost"]
        item.updated_at = datetime.now(timezone.utc)
        updated += 1

        results.append(
            {
                "id": item.id,
                "sku": item.sku,
                "old_cost": old_cost,
                "new_cost": cost_data["total_cost"],
                "cost_source": cost_data["cost_source"],
                "bom_cost": cost_data["bom_cost"],
                "routing_cost": cost_data["routing_cost"],
                "purchase_cost": cost_data["purchase_cost"],
            }
        )

    db.commit()

    logger.info(f"Recost all: {updated} items updated, {skipped} skipped")

    return {
        "updated": updated,
        "skipped": skipped,
        "items": results,
    }
