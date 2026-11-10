"""
Item Cost Service — standard-cost calculation and recosting for items.

Extracted verbatim from item_service.py (DEBT-1 D1-B mechanical split).
item_service re-exports these names for backward compatibility.
"""
from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models import Product, BOM, BOMLine
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.services.bom_management_service import recalculate_bom_cost
from app.services.cost_basis import (
    cost_per_stock_unit,
    standard_cost_from_stock_cost,
    uses_standard_cost,
)

logger = get_logger(__name__)


def _is_per_unit(quantity_per) -> bool:
    """Whether a routing material is used per unit made (not per batch or order).

    Routing cost counts only per-unit materials (``RoutingOperation.material_cost``).
    An unset value means per unit.
    """
    return not quantity_per or str(quantity_per).strip().lower() == "unit"


def _costed_bom(db: Session, item_id: int) -> Optional[BOM]:
    """The one active BOM costing reads for an item: highest version, then newest."""
    return (
        db.query(BOM)
        .filter(BOM.product_id == item_id, BOM.active.is_(True))
        .order_by(desc(func.coalesce(BOM.version, 0)), desc(BOM.id))
        .first()
    )


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

    # An item can have more than one active BOM or routing. Take the highest
    # version, then the newest, so the choice is the same on every run and
    # cost_dependencies can make the same one.
    bom = _costed_bom(db, item.id)

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
        .order_by(desc(Routing.version), desc(Routing.id))
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
                        if _is_per_unit(mat.quantity_per) and mat.extended_cost and mat.extended_cost > 0:
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
        # The result becomes the item's standard_cost, which is per PURCHASE
        # unit ($/KG). average_cost and last_cost are per STOCK unit ($/G), so
        # the fallbacks are scaled up; copying them straight across wrote a
        # per-gram figure into a per-KG field.
        if item.standard_cost and item.standard_cost > 0:
            purchase_cost = float(item.standard_cost)
        elif item.average_cost:
            purchase_cost = float(standard_cost_from_stock_cost(item, item.average_cost))
        elif item.last_cost:
            purchase_cost = float(standard_cost_from_stock_cost(item, item.last_cost))

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


def components_first(
    item_ids: list[int], dependencies: dict[int, set[int]]
) -> tuple[list[int], set[int]]:
    """Order ``item_ids`` so each item comes after the items it is built from.

    ``dependencies`` maps an item id to the ids of its direct components.
    Components that are not in ``item_ids`` are ignored. Items are taken in
    the order given, and each item's components are placed ahead of it.

    Returns the ordered ids and the circular ids: every item that is built,
    directly or through other items, from itself. The members of one circle
    cannot be ordered against each other; they are returned together, in the
    order given, after everything else they are built from.
    """
    position = {item_id: index for index, item_id in enumerate(item_ids)}

    def components_of(item_id: int) -> list[int]:
        """The item's components that are part of this run, in the given order."""
        return sorted(
            (c for c in dependencies.get(item_id, ()) if c in position),
            key=position.__getitem__,
        )

    # Tarjan's strongly-connected-components walk. It closes a group of items
    # only after every group that group is built from, which is the order
    # wanted here, and a group of more than one item is a circle. An explicit
    # stack stands in for recursion: a long chain of sub-assemblies must not
    # run into Python's recursion limit.
    ordered: list[int] = []
    circular: set[int] = set()
    visit_number: dict[int, int] = {}
    lowest_reached: dict[int, int] = {}
    open_items: list[int] = []
    is_open: set[int] = set()

    def start(item_id: int) -> tuple[int, Iterator[int]]:
        """Number an item, mark it open, and return it with its components."""
        visit_number[item_id] = lowest_reached[item_id] = len(visit_number)
        open_items.append(item_id)
        is_open.add(item_id)
        return item_id, iter(components_of(item_id))

    for root in item_ids:
        if root in visit_number:
            continue
        walk = [start(root)]
        while walk:
            item_id, components = walk[-1]
            for component_id in components:
                if component_id not in visit_number:
                    walk.append(start(component_id))
                    break
                if component_id in is_open:
                    lowest_reached[item_id] = min(
                        lowest_reached[item_id], visit_number[component_id]
                    )
            else:
                walk.pop()
                if walk:
                    parent_id = walk[-1][0]
                    lowest_reached[parent_id] = min(
                        lowest_reached[parent_id], lowest_reached[item_id]
                    )
                if lowest_reached[item_id] == visit_number[item_id]:
                    # Nothing below reaches back above this item: it and the
                    # items opened after it form one closed group.
                    group = []
                    while True:
                        member = open_items.pop()
                        is_open.discard(member)
                        group.append(member)
                        if member == item_id:
                            break
                    if len(group) > 1 or item_id in dependencies.get(item_id, ()):
                        circular.update(group)
                    ordered.extend(sorted(group, key=position.__getitem__))

    return ordered, circular


def _costed_per_product(rows) -> dict[int, int]:
    """Pick one BOM or routing per product: the one with the highest rank.

    ``rows`` yields ``(row id, product id, rank)``. Returns ``{row id: product id}``
    for the picked rows. The ranks mirror the ``order_by`` that
    ``calculate_item_cost`` uses, so the row picked here is the row it costs.
    """
    best: dict[int, tuple] = {}
    for row_id, product_id, rank in rows:
        if product_id not in best or rank > best[product_id][0]:
            best[product_id] = (rank, row_id)
    return {row_id: product_id for product_id, (_, row_id) in best.items()}


def cost_dependencies(
    db: Session, items_by_id: dict[int, Product]
) -> tuple[dict[int, set[int]], set[int]]:
    """Map each item in the run to the items in the run its standard cost is built from.

    ``calculate_item_cost`` reads a component's stored cost from two places:
    the lines of the item's costed BOM, and the per-unit materials on the
    active operations of its costed routing (per-batch and per-order
    materials are not part of the unit cost). An item can have several active
    BOMs or routings. Costing reads one of each (highest version, then
    newest), and the same one is read here.

    Only what the item's standard cost really depends on is an edge, because
    an edge costing does not act on could turn a real dependency in the other
    direction into a false circle:

    * a routing material counts only when the routing reads its standard cost.
      A component priced at a stored average or last cost is not affected by
      its own recost;
    * a BOM line whose component the routing prices that way does not count
      either. Costing lets the routing own that material and takes the BOM
      line back out of the item's cost.

    Returns ``(dependencies, items with such a BOM line)``. For the second
    set the stored BOM total still includes the line, so it has to be worked
    out again once every cost in the run has settled.
    """
    dependencies: dict[int, set[int]] = {item_id: set() for item_id in items_by_id}
    routing_owned: dict[int, set[int]] = {item_id: set() for item_id in items_by_id}

    costed_routings = _costed_per_product(
        (routing_id, product_id, (version, routing_id))
        for routing_id, product_id, version in db.query(
            Routing.id, Routing.product_id, Routing.version
        )
        .filter(Routing.is_active.is_(True))
        .all()
    )
    routing_rows = (
        db.query(
            RoutingOperation.routing_id,
            RoutingOperationMaterial.component_id,
            RoutingOperationMaterial.quantity_per,
            RoutingOperationMaterial.quantity,
        )
        .join(
            RoutingOperationMaterial,
            RoutingOperationMaterial.routing_operation_id == RoutingOperation.id,
        )
        .filter(RoutingOperation.is_active.is_(True))
        .all()
    )
    for routing_id, component_id, quantity_per, quantity in routing_rows:
        product_id = costed_routings.get(routing_id)
        component = items_by_id.get(component_id)
        if product_id not in dependencies or component is None or not _is_per_unit(quantity_per):
            continue
        if uses_standard_cost(component):
            dependencies[product_id].add(component_id)
        elif (quantity or 0) > 0 and (cost_per_stock_unit(component) or 0) > 0:
            routing_owned[product_id].add(component_id)

    costed_boms = _costed_per_product(
        (bom_id, product_id, (version or 0, bom_id))
        for bom_id, product_id, version in db.query(BOM.id, BOM.product_id, BOM.version)
        .filter(BOM.active.is_(True))
        .all()
    )
    bom_rows = (
        db.query(BOMLine.bom_id, BOMLine.component_id)
        .join(BOM, BOM.id == BOMLine.bom_id)
        .filter(BOM.active.is_(True))
        .all()
    )
    bom_totals_to_refresh: set[int] = set()
    for bom_id, component_id in bom_rows:
        product_id = costed_boms.get(bom_id)
        if product_id not in dependencies or component_id not in items_by_id:
            continue
        if component_id in routing_owned[product_id]:
            bom_totals_to_refresh.add(product_id)
        else:
            dependencies[product_id].add(component_id)

    return dependencies, bom_totals_to_refresh


def recost_all_items(
    db: Session,
    *,
    item_type: str | None = None,
    category_id: int | None = None,
    cost_source_filter: str | None = None,
) -> dict:
    """
    Recost all items matching filters.

    Items are costed components first, so an assembly whose BOM uses a
    sub-assembly is priced from the standard cost that sub-assembly has
    just been given, and one run is enough. A routing prices a component
    by its cost method, so there a sub-assembly that has an average or
    last cost is priced at that cost, not at its new standard cost.

    Returns dict with: updated, skipped, items (list of results), and
    circular_skus (items built from themselves, which cannot be ordered).
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

    # An assembly is priced from the stored cost of its direct components, so
    # a sub-assembly has to be recosted before the items built from it.
    items_by_id = {item.id: item for item in items}
    dependencies, bom_totals_to_refresh = cost_dependencies(db, items_by_id)
    order, circular_ids = components_first([item.id for item in items], dependencies)
    circular_skus = sorted(items_by_id[item_id].sku for item_id in circular_ids)
    if circular_skus:
        logger.warning(
            "Recost all: %d items are built from themselves, directly or "
            "through other items, so their costs depend on the order they were "
            "costed in: %s",
            len(circular_skus),
            ", ".join(circular_skus),
        )

    updated = 0
    skipped = 0
    results = []

    for item in (items_by_id[item_id] for item_id in order):
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

    # A BOM line the routing owns is not part of the order, so that item's
    # stored BOM total may have been worked out before the component was
    # recosted. Work those totals out again now every cost has settled.
    for item_id in bom_totals_to_refresh:
        bom = _costed_bom(db, item_id)
        if bom is not None:
            bom.total_cost = recalculate_bom_cost(bom, db)

    db.commit()

    logger.info(f"Recost all: {updated} items updated, {skipped} skipped")

    return {
        "updated": updated,
        "skipped": skipped,
        "items": results,
        "circular_skus": circular_skus,
    }
