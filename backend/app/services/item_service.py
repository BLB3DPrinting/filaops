"""
Item Service — CRUD and business logic for items and categories.

Items extends Products with inventory info, categories, reorder logic,
and pricing. Extracted from items.py (ARCHITECT-003).

DEBT-1 D1-B split: cost recalculation lives in item_cost_service,
duplication in item_duplicate_service, CSV import in item_import_service.
All historical public names remain importable from this module via the
re-export block at the bottom.
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models import Product, ItemCategory, Inventory, BOM, BOMLine
from app.models.manufacturing import Routing
from app.core.utils import get_or_404, check_unique_or_400
from app.core.uom_config import DEFAULT_MATERIAL_UOM, get_default_material_sku_prefix

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Inline UOM Conversion (fallback when database UOM table is empty)
# ---------------------------------------------------------------------------

UOM_CONVERSIONS = {
    # Mass conversions (to KG)
    "G": {"base": "KG", "factor": Decimal("0.001")},
    "KG": {"base": "KG", "factor": Decimal("1")},
    "LB": {"base": "KG", "factor": Decimal("0.453592")},
    "OZ": {"base": "KG", "factor": Decimal("0.0283495")},
    # Length conversions (to M)
    "MM": {"base": "M", "factor": Decimal("0.001")},
    "CM": {"base": "M", "factor": Decimal("0.01")},
    "M": {"base": "M", "factor": Decimal("1")},
    "IN": {"base": "M", "factor": Decimal("0.0254")},
    "FT": {"base": "M", "factor": Decimal("0.3048")},
    # Volume conversions (to L)
    "ML": {"base": "L", "factor": Decimal("0.001")},
    "L": {"base": "L", "factor": Decimal("1")},
    # Count units (no conversion)
    "EA": {"base": "EA", "factor": Decimal("1")},
    "PK": {"base": "PK", "factor": Decimal("1")},
    "BOX": {"base": "BOX", "factor": Decimal("1")},
    "ROLL": {"base": "ROLL", "factor": Decimal("1")},
}


def convert_uom_inline(quantity: Decimal, from_unit: str, to_unit: str) -> Decimal:
    """
    Convert quantity using inline conversion factors (no database lookup).
    Used as fallback when database UOM table is empty.
    """
    from_unit = (from_unit or "EA").upper().strip()
    to_unit = (to_unit or "EA").upper().strip()

    if from_unit == to_unit:
        return quantity

    from_info = UOM_CONVERSIONS.get(from_unit)
    to_info = UOM_CONVERSIONS.get(to_unit)

    if not from_info or not to_info:
        return quantity  # Unknown unit, return as-is

    if from_info["base"] != to_info["base"]:
        return quantity  # Incompatible bases

    # Convert: from_unit -> base -> to_unit
    quantity_in_base = quantity * from_info["factor"]
    quantity_in_target = quantity_in_base / to_info["factor"]

    return quantity_in_target


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------


def list_categories(
    db: Session,
    *,
    include_inactive: bool = False,
    parent_id: int | None = None,
) -> list[ItemCategory]:
    """List item categories with optional filters."""
    query = db.query(ItemCategory)

    if not include_inactive:
        query = query.filter(ItemCategory.is_active.is_(True))

    if parent_id is not None:
        query = query.filter(ItemCategory.parent_id == parent_id)

    return query.order_by(ItemCategory.sort_order, ItemCategory.name).all()


def get_category_tree(db: Session) -> list[dict]:
    """
    Get categories as a nested tree structure.

    Returns list of dicts with: id, code, name, description, is_active, children.
    """
    categories = (
        db.query(ItemCategory)
        .filter(ItemCategory.is_active.is_(True))
        .order_by(ItemCategory.sort_order, ItemCategory.name)
        .all()
    )

    def build_tree(parent_id: int | None = None) -> list[dict]:
        nodes = []
        for cat in categories:
            if cat.parent_id == parent_id:
                nodes.append(
                    {
                        "id": cat.id,
                        "code": cat.code,
                        "name": cat.name,
                        "description": cat.description,
                        "is_active": cat.is_active,
                        "children": build_tree(cat.id),
                    }
                )
        return nodes

    return build_tree(None)


def get_category(db: Session, category_id: int) -> ItemCategory:
    """Get category by ID or raise 404."""
    return get_or_404(db, ItemCategory, category_id, "Category not found")


def create_category(
    db: Session,
    *,
    code: str,
    name: str,
    parent_id: int | None = None,
    description: str | None = None,
    sort_order: int | None = None,
    is_active: bool = True,
) -> ItemCategory:
    """Create a new item category."""
    check_unique_or_400(db, ItemCategory, "code", code.upper())

    if parent_id:
        if not db.query(ItemCategory).filter(ItemCategory.id == parent_id).first():
            raise HTTPException(status_code=400, detail="Parent category not found")

    category = ItemCategory(
        code=code.upper(),
        name=name,
        parent_id=parent_id,
        description=description,
        sort_order=sort_order or 0,
        is_active=is_active,
    )

    db.add(category)
    db.commit()
    db.refresh(category)

    logger.info(f"Created category: {category.code}")
    return category


def update_category(
    db: Session,
    category_id: int,
    *,
    code: str | None = None,
    name: str | None = None,
    parent_id: int | None = ...,  # Use ... as sentinel for "not provided"
    description: str | None = None,
    sort_order: int | None = None,
    is_active: bool | None = None,
) -> ItemCategory:
    """Update an item category."""
    category = get_or_404(db, ItemCategory, category_id, "Category not found")

    if code and code.upper() != category.code:
        check_unique_or_400(
            db, ItemCategory, "code", code.upper(), exclude_id=category_id
        )
        category.code = code.upper()

    if name is not None:
        category.name = name

    if parent_id is not ...:
        if parent_id == category_id:
            raise HTTPException(
                status_code=400, detail="Category cannot be its own parent"
            )
        if parent_id:
            if not db.query(ItemCategory).filter(ItemCategory.id == parent_id).first():
                raise HTTPException(status_code=400, detail="Parent category not found")
        category.parent_id = parent_id

    if description is not None:
        category.description = description

    if sort_order is not None:
        category.sort_order = sort_order

    if is_active is not None:
        category.is_active = is_active

    category.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(category)

    logger.info(f"Updated category: {category.code}")
    return category


def delete_category(db: Session, category_id: int) -> dict:
    """
    Soft delete (deactivate) a category.

    Raises HTTPException if category has active children or items.
    """
    category = get_or_404(db, ItemCategory, category_id, "Category not found")

    children = (
        db.query(ItemCategory)
        .filter(ItemCategory.parent_id == category_id, ItemCategory.is_active.is_(True))
        .count()
    )
    if children > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete category with {children} active child categories",
        )

    items = (
        db.query(Product)
        .filter(Product.category_id == category_id, Product.active.is_(True))
        .count()
    )
    if items > 0:
        raise HTTPException(
            status_code=400, detail=f"Cannot delete category with {items} active items"
        )

    category.is_active = False
    category.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Deleted (deactivated) category: {category.code}")
    return {"message": f"Category {category.code} deleted"}


def get_category_and_descendants(db: Session, category_id: int) -> list[int]:
    """
    Get a category ID and all its descendant category IDs.
    Used for filtering items by category hierarchy.
    """
    result = [category_id]

    children = (
        db.query(ItemCategory.id)
        .filter(ItemCategory.parent_id == category_id)
        .all()
    )

    for (child_id,) in children:
        result.extend(get_category_and_descendants(db, child_id))

    return result


# ---------------------------------------------------------------------------
# Item CRUD
# ---------------------------------------------------------------------------


def list_items(
    db: Session,
    *,
    item_type: str | None = None,
    procurement_type: str | None = None,
    category_id: int | None = None,
    search: str | None = None,
    active_only: bool = True,
    needs_reorder: bool = False,
    exclude_variants: bool = True,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """
    List items with filtering and pagination.

    Returns (items_list_data, total_count) where items_list_data is a list of dicts
    containing item info with inventory summary.
    """
    query = db.query(Product)

    if active_only:
        query = query.filter(Product.active.is_(True))

    if exclude_variants:
        query = query.filter(Product.parent_product_id.is_(None))

    if item_type:
        if item_type == "filament":
            query = query.filter(Product.material_type_id.isnot(None))
        elif item_type == "material":
            query = query.filter(
                or_(
                    Product.item_type == "material",
                    Product.material_type_id.isnot(None),
                )
            )
        else:
            query = query.filter(Product.item_type == item_type)

    if procurement_type:
        query = query.filter(Product.procurement_type == procurement_type)

    if category_id:
        category_ids = get_category_and_descendants(db, category_id)
        query = query.filter(Product.category_id.in_(category_ids))

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                Product.sku.ilike(search_pattern),
                Product.name.ilike(search_pattern),
                Product.upc.ilike(search_pattern),
            )
        )

    total = query.count()

    query = query.options(joinedload(Product.item_category))
    items = query.order_by(Product.sku).offset(offset).limit(limit).all()

    item_ids = [item.id for item in items]

    # Batch inventory query — one query for all items
    on_hand_map: dict[int, float] = {}
    if item_ids:
        inv_rows = (
            db.query(
                Inventory.product_id,
                func.coalesce(func.sum(Inventory.on_hand_quantity), 0).label("on_hand"),
            )
            .filter(Inventory.product_id.in_(item_ids))
            .group_by(Inventory.product_id)
            .all()
        )
        on_hand_map = {r.product_id: float(r.on_hand) for r in inv_rows}

    # Batch allocation query — replicate get_allocated_quantity() for all items
    alloc_map: dict[int, float] = {}
    if item_ids:
        from app.models.production_order import ProductionOrder

        bom_lines_sub = (
            db.query(
                BOMLine.component_id,
                BOMLine.bom_id,
                BOMLine.quantity,
            )
            .filter(BOMLine.component_id.in_(item_ids))
            .subquery()
        )

        boms_sub = (
            db.query(
                BOM.product_id,
                bom_lines_sub.c.component_id,
                bom_lines_sub.c.quantity,
            )
            .join(bom_lines_sub, BOM.id == bom_lines_sub.c.bom_id)
            .filter(BOM.active.is_(True))
            .subquery()
        )

        alloc_rows = (
            db.query(
                boms_sub.c.component_id,
                func.coalesce(
                    func.sum(
                        (
                            ProductionOrder.quantity_ordered
                            - func.coalesce(ProductionOrder.quantity_completed, 0)
                            - func.coalesce(ProductionOrder.quantity_scrapped, 0)
                        )
                        * boms_sub.c.quantity
                    ),
                    0,
                ).label("allocated"),
            )
            .select_from(ProductionOrder)
            .join(boms_sub, ProductionOrder.product_id == boms_sub.c.product_id)
            .filter(
                ProductionOrder.status.in_(
                    ["draft", "released", "scheduled", "in_progress"]
                )
            )
            .group_by(boms_sub.c.component_id)
            .all()
        )
        alloc_map = {r.component_id: float(r.allocated) for r in alloc_rows}

    # Batch BOM existence query
    bom_ids: set[int] = set()
    if item_ids:
        bom_rows = (
            db.query(BOM.product_id)
            .filter(BOM.product_id.in_(item_ids), BOM.active.is_(True))
            .distinct()
            .all()
        )
        bom_ids = {r.product_id for r in bom_rows}

    # Batch routing existence query
    routing_ids: set[int] = set()
    if item_ids:
        routing_rows = (
            db.query(Routing.product_id)
            .filter(Routing.product_id.in_(item_ids), Routing.is_active.is_(True))
            .distinct()
            .all()
        )
        routing_ids = {r.product_id for r in routing_rows}

    # Batch variant count query for templates — active variants only, so
    # soft-deleted variants don't inflate the count or roll up to live templates.
    variant_count_map: dict[int, int] = {}
    template_ids = [item.id for item in items if item.is_template]
    if template_ids:
        vc_rows = (
            db.query(
                Product.parent_product_id,
                func.count(Product.id).label("cnt"),
            )
            .filter(
                Product.parent_product_id.in_(template_ids),
                Product.active.is_(True),
            )
            .group_by(Product.parent_product_id)
            .all()
        )
        variant_count_map = {r.parent_product_id: r.cnt for r in vc_rows}

    # Variant inventory rollup for templates (Workstream A — display only).
    # Templates carry no inventory of their own today; surface child variants'
    # combined stock so the template row reflects what's actually available.
    # Maps are keyed by template_id; absence = "no rollup eligible" (None to UI).
    # Symmetry with variant_count_map: only active variants contribute.
    variants_on_hand_map: dict[int, float] = {}
    variants_available_map: dict[int, float] = {}
    if template_ids:
        # Pre-filter subquery: only active variants under our templates.
        # Reused as the join target for both inventory and allocation rollups,
        # mirroring the alloc_map shape (component pre-filter before BOM/PO joins).
        active_variants_sub = (
            db.query(
                Product.id.label("variant_id"),
                Product.parent_product_id.label("parent_id"),
            )
            .filter(
                Product.parent_product_id.in_(template_ids),
                Product.active.is_(True),
            )
            .subquery()
        )

        # Sum on-hand grouped by parent (outerjoin so active variants without
        # Inventory rows still anchor the template at 0, not None).
        v_inv_rows = (
            db.query(
                active_variants_sub.c.parent_id,
                func.coalesce(func.sum(Inventory.on_hand_quantity), 0).label("on_hand"),
            )
            .select_from(active_variants_sub)
            .outerjoin(
                Inventory, Inventory.product_id == active_variants_sub.c.variant_id
            )
            .group_by(active_variants_sub.c.parent_id)
            .all()
        )
        variants_on_hand_map = {r.parent_id: float(r.on_hand) for r in v_inv_rows}

        # Allocations: pre-filter BOMLine to active-variant component_ids first,
        # then join PO/BOM. Mirrors the per-item alloc_map shape — narrows the
        # cross-join surface before the aggregate.
        # ProductionOrder is already imported above (line 365); list_items() always
        # exits early if items is empty, and item_ids is non-empty whenever
        # template_ids is non-empty, so the earlier import has already executed.
        v_bom_lines_sub = (
            db.query(
                BOMLine.component_id,
                BOMLine.bom_id,
                BOMLine.quantity,
            )
            .join(
                active_variants_sub,
                BOMLine.component_id == active_variants_sub.c.variant_id,
            )
            .subquery()
        )

        v_boms_sub = (
            db.query(
                BOM.product_id,
                v_bom_lines_sub.c.component_id,
                v_bom_lines_sub.c.quantity,
            )
            .join(v_bom_lines_sub, BOM.id == v_bom_lines_sub.c.bom_id)
            .filter(BOM.active.is_(True))
            .subquery()
        )

        v_alloc_rows = (
            db.query(
                Product.parent_product_id.label("parent_id"),
                func.coalesce(
                    func.sum(
                        (
                            ProductionOrder.quantity_ordered
                            - func.coalesce(ProductionOrder.quantity_completed, 0)
                            - func.coalesce(ProductionOrder.quantity_scrapped, 0)
                        )
                        * v_boms_sub.c.quantity
                    ),
                    0,
                ).label("allocated"),
            )
            .select_from(ProductionOrder)
            .join(v_boms_sub, ProductionOrder.product_id == v_boms_sub.c.product_id)
            .join(Product, Product.id == v_boms_sub.c.component_id)
            .filter(
                ProductionOrder.status.in_(
                    ["draft", "released", "scheduled", "in_progress"]
                )
            )
            .group_by(Product.parent_product_id)
            .all()
        )
        v_alloc_map = {r.parent_id: float(r.allocated) for r in v_alloc_rows}

        # available = on_hand - allocated, only for templates with rollup data
        for parent_id, on_hand in variants_on_hand_map.items():
            variants_available_map[parent_id] = on_hand - v_alloc_map.get(parent_id, 0.0)

    result = []
    for item in items:
        on_hand = on_hand_map.get(item.id, 0.0)
        allocated = alloc_map.get(item.id, 0.0)

        is_material = item.material_type_id is not None
        reorder_point = float(item.reorder_point) if item.reorder_point else None
        if is_material and reorder_point:
            reorder_point = reorder_point * 1000

        available = on_hand - allocated
        is_stocked = item.stocking_policy == "stocked"
        item_needs_reorder = (
            is_stocked and reorder_point is not None and on_hand <= reorder_point
        )

        if needs_reorder and not item_needs_reorder:
            continue

        result.append(
            {
                "id": item.id,
                "sku": item.sku,
                "name": item.name,
                "item_type": item.item_type or "finished_good",
                "procurement_type": item.procurement_type or "buy",
                "category_id": item.category_id,
                "category_name": item.item_category.name if item.item_category else None,
                "unit": item.unit,
                "standard_cost": item.standard_cost,
                "average_cost": item.average_cost,
                "selling_price": item.selling_price,
                "active": item.active,
                "on_hand_qty": on_hand,
                "available_qty": available,
                "reorder_point": reorder_point,
                "stocking_policy": item.stocking_policy or "on_demand",
                "needs_reorder": item_needs_reorder,
                "description": item.description,
                "image_url": item.image_url,
                "has_bom": item.has_bom or item.id in bom_ids,
                "has_routing": item.id in routing_ids,
                "gcode_file_path": item.gcode_file_path,
                "parent_product_id": item.parent_product_id,
                "is_template": item.is_template,
                "variant_count": variant_count_map.get(item.id, 0),
                "variants_on_hand_qty": variants_on_hand_map.get(item.id) if item.is_template else None,
                "variants_available_qty": variants_available_map.get(item.id) if item.is_template else None,
            }
        )

    return result, total


def get_item_stats(db: Session) -> dict:
    """
    Lightweight item statistics — type counts and reorder alerts.

    Uses GROUP BY queries instead of loading all items with inventory data.
    """
    type_counts = (
        db.query(Product.item_type, func.count(Product.id))
        .filter(Product.active.is_(True), Product.parent_product_id.is_(None))
        .group_by(Product.item_type)
        .all()
    )

    # Count items below reorder point (outerjoin so products with no inventory = 0 on-hand)
    reorder_subq = (
        db.query(Product.id)
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .filter(
            Product.active.is_(True),
            Product.parent_product_id.is_(None),
            Product.stocking_policy == "stocked",
            Product.reorder_point.isnot(None),
        )
        .group_by(Product.id, Product.reorder_point)
        .having(
            func.coalesce(func.sum(Inventory.on_hand_quantity), 0)
            <= Product.reorder_point
        )
        .subquery()
    )
    reorder_count = db.query(func.count()).select_from(reorder_subq).scalar() or 0

    total = sum(c for _, c in type_counts)
    by_type = {t or "finished_good": c for t, c in type_counts}

    return {
        "total": total,
        "finished_goods": by_type.get("finished_good", 0),
        "components": by_type.get("component", 0),
        "packaging": by_type.get("packaging", 0),
        "supplies": by_type.get("supply", 0),
        "materials": by_type.get("material", 0),
        "needs_reorder": reorder_count,
    }


def get_item(db: Session, item_id: int) -> Product:
    """Get item by ID or raise 404."""
    item = (
        db.query(Product)
        .options(joinedload(Product.item_category))
        .filter(Product.id == item_id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
    return item


def get_item_by_sku(db: Session, sku: str) -> Product:
    """Get item by SKU or raise 404."""
    item = (
        db.query(Product)
        .options(joinedload(Product.item_category))
        .filter(Product.sku == sku.upper())
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail=f"Item with SKU '{sku}' not found")
    return item


def generate_item_sku(db: Session, item_type: str) -> str:
    """Generate a sequential SKU for the given item type."""
    item_type_prefix = {
        "finished_good": "FG",
        "component": "COMP",
        "packaging": "PKG",
        "supply": "SUP",
        "service": "SRV",
        "material": get_default_material_sku_prefix(),
    }.get(item_type, "ITM")

    existing_skus = (
        db.query(Product.sku).filter(Product.sku.like(f"{item_type_prefix}-%")).all()
    )

    max_num = 0
    for (sku,) in existing_skus:
        try:
            parts = sku.split("-")
            if len(parts) >= 2:
                num = int(parts[-1])
                max_num = max(max_num, num)
        except (ValueError, IndexError):
            pass

    new_num = max_num + 1
    return f"{item_type_prefix}-{new_num:03d}"


PACKAGING_PHYSICAL_FIELDS = ("weight_oz", "length_in", "width_in", "height_in")
PACKAGING_PHYSICAL_DETAIL = (
    "Packaging items require weight_oz, length_in, width_in, and height_in."
)


def _item_type_value(item_type: object) -> str:
    if hasattr(item_type, "value"):
        return item_type.value
    return str(item_type)


def _physical_value_present(value: object) -> bool:
    return value is not None and value != ""


def _validate_packaging_physical_metadata(
    data: dict,
    *,
    existing_item: Product | None = None,
) -> None:
    item_type = data.get(
        "item_type",
        existing_item.item_type if existing_item is not None else "finished_good",
    )
    if _item_type_value(item_type) != "packaging":
        return

    missing = []
    for field in PACKAGING_PHYSICAL_FIELDS:
        value = data[field] if field in data else getattr(existing_item, field, None)
        if not _physical_value_present(value):
            missing.append(field)

    if missing:
        raise HTTPException(status_code=400, detail=PACKAGING_PHYSICAL_DETAIL)


def create_item(db: Session, *, data: dict) -> Product:
    """
    Create a new item (product).

    data keys: sku, name, description, unit, item_type, procurement_type,
    category_id, standard_cost, selling_price, reorder_point, etc.
    """
    sku = data.get("sku")
    item_type = data.get("item_type", "finished_good")
    if hasattr(item_type, "value"):
        item_type = item_type.value

    _validate_packaging_physical_metadata({**data, "item_type": item_type})

    if not sku or sku.strip() == "":
        data["sku"] = generate_item_sku(db, item_type)
    else:
        data["sku"] = sku.upper()

    check_unique_or_400(db, Product, "sku", data["sku"])

    if data.get("category_id"):
        if not db.query(ItemCategory).filter(ItemCategory.id == data["category_id"]).first():
            raise HTTPException(status_code=400, detail="Category not found")

    # Auto-configure UOM for materials
    if item_type == "material":
        if not data.get("unit"):
            data["unit"] = DEFAULT_MATERIAL_UOM.unit
        if not data.get("purchase_uom"):
            data["purchase_uom"] = DEFAULT_MATERIAL_UOM.purchase_uom
        if not data.get("purchase_factor"):
            data["purchase_factor"] = DEFAULT_MATERIAL_UOM.purchase_factor
        data["is_raw_material"] = True
    else:
        if not data.get("unit"):
            data["unit"] = "EA"
        if not data.get("purchase_uom"):
            data["purchase_uom"] = data.get("unit", "EA")

    # Convert enums to values
    for enum_field in ["item_type", "procurement_type", "cost_method", "stocking_policy"]:
        if enum_field in data and data[enum_field] and hasattr(data[enum_field], "value"):
            data[enum_field] = data[enum_field].value

    # Handle Pydantic alias: schema uses is_active, model uses active
    data.pop("is_active", None)
    data["active"] = True
    item = Product(**data)
    db.add(item)
    db.commit()
    db.refresh(item)

    logger.info(f"Created item: {item.sku}")
    return item


def update_item(db: Session, item_id: int, *, data: dict) -> Product:
    """Update an item."""
    item = get_item(db, item_id)

    if "sku" in data and data["sku"] and data["sku"].upper() != item.sku:
        check_unique_or_400(db, Product, "sku", data["sku"].upper(), exclude_id=item_id)
        data["sku"] = data["sku"].upper()

    if "category_id" in data and data["category_id"] and data["category_id"] != item.category_id:
        if not db.query(ItemCategory).filter(ItemCategory.id == data["category_id"]).first():
            raise HTTPException(status_code=400, detail="Category not found")

    # Handle unit change with inventory conversion
    old_unit = item.unit
    if "unit" in data and data["unit"] and data["unit"].upper() != (old_unit or "").upper():
        new_unit = data["unit"].upper().strip()
        old_unit_normalized = (old_unit or "EA").upper().strip()

        if old_unit_normalized != new_unit:
            from app.services.uom_service import convert_quantity_safe

            inventory_records = (
                db.query(Inventory).filter(Inventory.product_id == item.id).all()
            )

            if inventory_records:
                test_qty = Decimal("1")
                _, can_convert = convert_quantity_safe(
                    db, test_qty, old_unit_normalized, new_unit
                )

                if not can_convert:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Cannot change unit from {old_unit} to {new_unit}. "
                            f"Units are incompatible."
                        ),
                    )

                for inv in inventory_records:
                    if inv.on_hand_quantity and inv.on_hand_quantity > 0:
                        converted_qty, success = convert_quantity_safe(
                            db, inv.on_hand_quantity, old_unit_normalized, new_unit
                        )
                        if success:
                            inv.on_hand_quantity = converted_qty

                    if inv.allocated_quantity and inv.allocated_quantity > 0:
                        converted_allocated, success = convert_quantity_safe(
                            db, inv.allocated_quantity, old_unit_normalized, new_unit
                        )
                        if success:
                            inv.allocated_quantity = converted_allocated

                    inv.updated_at = datetime.now(timezone.utc)

                logger.info(
                    f"Converted {len(inventory_records)} inventory records for {item.sku} "
                    f"from {old_unit} to {new_unit}"
                )

    # Convert enums to values
    for enum_field in ["item_type", "procurement_type", "cost_method", "stocking_policy"]:
        if enum_field in data and data[enum_field] and hasattr(data[enum_field], "value"):
            data[enum_field] = data[enum_field].value

    _validate_packaging_physical_metadata(data, existing_item=item)

    if "is_active" in data:
        data["active"] = data.pop("is_active")

    for field, value in data.items():
        setattr(item, field, value)

    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)

    logger.info(f"Updated item: {item.sku}")
    return item


def delete_item(db: Session, item_id: int) -> dict:
    """
    Soft delete an item.

    Raises HTTPException if item has inventory on hand or active BOMs.
    """
    item = get_item(db, item_id)

    inv = (
        db.query(func.sum(Inventory.on_hand_quantity))
        .filter(Inventory.product_id == item_id)
        .scalar()
    )
    if inv and float(inv) > 0:
        raise HTTPException(
            status_code=400, detail=f"Cannot delete item with {inv} units on hand"
        )

    bom_count = (
        db.query(BOM)
        .filter(BOM.product_id == item_id, BOM.active.is_(True))
        .count()
    )
    if bom_count > 0:
        raise HTTPException(
            status_code=400, detail=f"Cannot delete item used in {bom_count} active BOMs"
        )

    item.active = False
    item.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Deleted (deactivated) item: {item.sku}")
    return {"message": f"Item {item.sku} deleted"}


# ---------------------------------------------------------------------------
# Item Response Builder
# ---------------------------------------------------------------------------


def build_item_response_data(item: Product, db: Session) -> dict:
    """Build full item response data with inventory and BOM info."""
    inv = (
        db.query(
            func.coalesce(func.sum(Inventory.on_hand_quantity), 0).label("on_hand"),
            func.coalesce(func.sum(Inventory.allocated_quantity), 0).label("allocated"),
        )
        .filter(Inventory.product_id == item.id)
        .first()
    )

    on_hand = float(inv.on_hand) if inv else 0
    allocated = float(inv.allocated) if inv else 0

    bom_count = (
        db.query(BOM)
        .filter(BOM.product_id == item.id, BOM.active.is_(True))
        .count()
    )

    has_active_routing = (
        db.query(Routing.id)
        .filter(Routing.product_id == item.id, Routing.is_active.is_(True))
        .first()
    ) is not None

    return {
        "id": item.id,
        "sku": item.sku,
        "name": item.name,
        "description": item.description,
        "unit": item.unit,
        "item_type": item.item_type or "finished_good",
        "procurement_type": item.procurement_type or "buy",
        "category_id": item.category_id,
        "cost_method": item.cost_method or "average",
        "standard_cost": item.standard_cost,
        "average_cost": item.average_cost,
        "last_cost": item.last_cost,
        "selling_price": item.selling_price,
        "weight_oz": item.weight_oz,
        "length_in": item.length_in,
        "width_in": item.width_in,
        "height_in": item.height_in,
        "lead_time_days": item.lead_time_days,
        "min_order_qty": item.min_order_qty,
        "reorder_point": item.reorder_point,
        "upc": item.upc,
        "legacy_sku": item.legacy_sku,
        "active": item.active,
        "is_raw_material": item.is_raw_material,
        "track_lots": item.track_lots,
        "track_serials": item.track_serials,
        "category_name": item.item_category.name if item.item_category else None,
        "category_path": item.item_category.full_path if item.item_category else None,
        "on_hand_qty": on_hand,
        "available_qty": on_hand - allocated,
        "allocated_qty": allocated,
        "has_bom": item.has_bom or bom_count > 0,
        "bom_count": bom_count,
        "has_routing": has_active_routing,
        "gcode_file_path": item.gcode_file_path,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


# ---------------------------------------------------------------------------
# Low Stock
# ---------------------------------------------------------------------------


def get_low_stock_items(
    db: Session,
    *,
    include_zero_reorder: bool = False,
    include_mrp_shortages: bool = True,
    limit: int = 100,
) -> dict:
    """
    Get items below reorder point or with MRP shortages.

    Returns dict with: items, count, summary.
    """
    items_dict: dict[int, dict] = {}

    # 1. Get STOCKED items below reorder point
    query = (
        db.query(Product, Inventory)
        .outerjoin(Inventory, Product.id == Inventory.product_id)
        .filter(
            Product.active.is_(True),
            Product.stocking_policy == "stocked",
            Product.reorder_point.isnot(None),
            or_(Product.procurement_type != "make", Product.procurement_type.is_(None)),
        )
    )

    if not include_zero_reorder:
        query = query.filter(Product.reorder_point > 0)

    query = query.filter(
        or_(
            Inventory.available_quantity <= Product.reorder_point,
            Inventory.id.is_(None),
        )
    )

    results = query.limit(limit).all()

    for product, inventory in results:
        available = float(inventory.available_quantity) if inventory else 0
        on_hand = float(inventory.on_hand_quantity) if inventory else 0
        reorder_point = float(product.reorder_point) if product.reorder_point else 0
        shortfall = reorder_point - available

        items_dict[product.id] = {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "item_type": product.item_type,
            "procurement_type": product.procurement_type or "buy",
            "stocking_policy": product.stocking_policy or "on_demand",
            "unit": product.unit,
            "category_name": product.item_category.name if product.item_category else None,
            "on_hand_qty": on_hand,
            "available_qty": available,
            "reorder_point": reorder_point,
            "shortfall": shortfall,
            "mrp_shortage": 0,
            "cost": float(product.standard_cost or product.average_cost or 0),
            "preferred_vendor_id": product.preferred_vendor_id,
            "shortage_source": "reorder_point",
        }

    # 2. Get MRP shortages (imported inline to avoid circular imports)
    if include_mrp_shortages:
        _add_mrp_shortages(db, items_dict, limit)

    items = list(items_dict.values())
    items.sort(key=lambda x: x["shortfall"], reverse=True)
    items = items[:limit]

    critical_count = sum(1 for i in items if i["available_qty"] <= 0)
    urgent_count = sum(
        1
        for i in items
        if i["reorder_point"]
        and 0 < i["available_qty"] <= i["reorder_point"] * 0.5
    )
    low_count = sum(
        1
        for i in items
        if i["reorder_point"] and i["available_qty"] > i["reorder_point"] * 0.5
    )
    mrp_shortage_count = sum(1 for i in items if i["mrp_shortage"] > 0)
    total_shortfall_value = sum(i["shortfall"] * i["cost"] for i in items)

    return {
        "items": items,
        "count": len(items),
        "summary": {
            "total_items_low": len(items),
            "critical_count": critical_count,
            "urgent_count": urgent_count,
            "low_count": low_count,
            "mrp_shortage_count": mrp_shortage_count,
            "total_shortfall_value": total_shortfall_value,
        },
    }


def _add_mrp_shortages(db: Session, items_dict: dict, limit: int) -> None:
    """Add MRP shortage info to items_dict. Modifies items_dict in place."""
    from app.models.sales_order import SalesOrder, SalesOrderLine
    from app.models.production_order import ProductionOrder
    from app.services.mrp import MRPService, ComponentRequirement

    # Get active sales orders that don't have linked production orders
    so_ids_with_po = (
        db.query(ProductionOrder.sales_order_id)
        .filter(ProductionOrder.sales_order_id.isnot(None))
        .distinct()
    )

    active_orders = (
        db.query(SalesOrder)
        .filter(
            SalesOrder.status.notin_(["cancelled", "completed", "delivered"]),
            ~SalesOrder.id.in_(so_ids_with_po),
        )
        .all()
    )

    mrp_service = MRPService(db)
    all_requirements = []

    for order in active_orders:
        if order.order_type == "line_item":
            lines = (
                db.query(SalesOrderLine)
                .filter(SalesOrderLine.sales_order_id == order.id)
                .all()
            )
            for line in lines:
                if line.product_id:
                    try:
                        requirements = mrp_service.explode_bom(
                            product_id=line.product_id,
                            quantity=Decimal(str(line.quantity)),
                            source_demand_type="sales_order",
                            source_demand_id=order.id,
                        )
                        all_requirements.extend(requirements)
                    except Exception:
                        continue
        elif order.order_type == "quote_based" and order.product_id:
            try:
                requirements = mrp_service.explode_bom(
                    product_id=order.product_id,
                    quantity=Decimal(str(order.quantity)),
                    source_demand_type="sales_order",
                    source_demand_id=order.id,
                )
                all_requirements.extend(requirements)
            except Exception:
                continue

    # Also get demand from active Production Orders
    active_pos = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.status.in_(["draft", "released", "in_progress"]))
        .all()
    )

    for po in active_pos:
        if po.product_id:
            try:
                remaining_qty = Decimal(str(po.quantity_ordered or 0)) - Decimal(
                    str(po.quantity_completed or 0)
                )
                if remaining_qty > 0:
                    requirements = mrp_service.explode_bom(
                        product_id=po.product_id,
                        quantity=remaining_qty,
                        source_demand_type="production_order",
                        source_demand_id=po.id,
                    )
                    all_requirements.extend(requirements)
            except Exception:
                continue

    # Aggregate requirements by product_id
    aggregated_requirements: dict = {}
    for req in all_requirements:
        key = req.product_id
        if key not in aggregated_requirements:
            aggregated_requirements[key] = {
                "product_id": req.product_id,
                "product_sku": req.product_sku,
                "product_name": req.product_name,
                "gross_quantity": req.gross_quantity,
                "bom_level": req.bom_level,
            }
        else:
            aggregated_requirements[key]["gross_quantity"] += req.gross_quantity

    if aggregated_requirements:
        component_reqs = []
        for req_data in aggregated_requirements.values():
            component_reqs.append(
                ComponentRequirement(
                    product_id=int(req_data["product_id"]),
                    product_sku=str(req_data["product_sku"]),
                    product_name=str(req_data["product_name"]),
                    bom_level=int(req_data["bom_level"]),
                    gross_quantity=Decimal(str(req_data["gross_quantity"])),
                )
            )

        net_requirements = mrp_service.calculate_net_requirements(component_reqs)

        for net_req in net_requirements:
            if net_req.net_shortage > 0:
                product_id = net_req.product_id
                mrp_shortage = float(net_req.net_shortage)

                if product_id in items_dict:
                    items_dict[product_id]["mrp_shortage"] = mrp_shortage
                    items_dict[product_id]["shortfall"] = max(
                        items_dict[product_id]["shortfall"], mrp_shortage
                    )
                    items_dict[product_id]["shortage_source"] = "both"
                else:
                    product = db.query(Product).filter(Product.id == product_id).first()
                    if product and product.active and product.procurement_type != "make":
                        inv = (
                            db.query(
                                func.coalesce(
                                    func.sum(Inventory.on_hand_quantity), 0
                                ).label("on_hand"),
                                func.coalesce(
                                    func.sum(Inventory.allocated_quantity), 0
                                ).label("allocated"),
                            )
                            .filter(Inventory.product_id == product_id)
                            .first()
                        )

                        on_hand = float(inv.on_hand) if inv else 0
                        allocated = float(inv.allocated) if inv else 0
                        available = on_hand - allocated

                        items_dict[product_id] = {
                            "id": product.id,
                            "sku": product.sku,
                            "name": product.name,
                            "item_type": product.item_type,
                            "procurement_type": product.procurement_type or "buy",
                            "stocking_policy": product.stocking_policy or "on_demand",
                            "unit": product.unit,
                            "category_name": (
                                product.item_category.name
                                if product.item_category
                                else None
                            ),
                            "on_hand_qty": on_hand,
                            "available_qty": available,
                            "reorder_point": (
                                float(product.reorder_point)
                                if product.reorder_point
                                else None
                            ),
                            "shortfall": mrp_shortage,
                            "mrp_shortage": mrp_shortage,
                            "cost": float(
                                product.standard_cost or product.average_cost or 0
                            ),
                            "preferred_vendor_id": product.preferred_vendor_id,
                            "shortage_source": "mrp",
                        }


# ---------------------------------------------------------------------------
# Bulk Update
# ---------------------------------------------------------------------------


def bulk_update_items(
    db: Session,
    *,
    item_ids: list[int],
    category_id: int | None = None,
    item_type: str | None = None,
    procurement_type: str | None = None,
    is_active: bool | None = None,
) -> dict:
    """Bulk update multiple items at once."""
    if not item_ids:
        raise HTTPException(status_code=400, detail="No items specified")

    if category_id and category_id != 0:
        if not db.query(ItemCategory).filter(ItemCategory.id == category_id).first():
            raise HTTPException(status_code=400, detail="Category not found")

    updated = 0
    errors = []

    valid_item_types = ["finished_good", "component", "packaging", "supply", "service", "material"]
    valid_proc_types = ["make", "buy", "make_or_buy"]

    for item_id in item_ids:
        item = db.query(Product).filter(Product.id == item_id).first()
        if not item:
            errors.append({"item_id": item_id, "error": "Item not found"})
            continue

        try:
            if category_id is not None:
                if category_id == 0:
                    item.category_id = None
                else:
                    item.category_id = category_id

            if item_type is not None:
                item_type_value = item_type
                if hasattr(item_type_value, "value"):
                    item_type_value = item_type_value.value
                if item_type_value in valid_item_types:
                    _validate_packaging_physical_metadata(
                        {"item_type": item_type_value},
                        existing_item=item,
                    )
                    item.item_type = item_type_value
                else:
                    raise ValueError(f"Invalid item_type: {item_type_value}")

            if procurement_type is not None:
                proc_type_value = procurement_type
                if hasattr(proc_type_value, "value"):
                    proc_type_value = proc_type_value.value
                if proc_type_value in valid_proc_types:
                    item.procurement_type = proc_type_value
                else:
                    raise ValueError(f"Invalid procurement_type: {proc_type_value}")

            if is_active is not None:
                item.active = is_active

            item.updated_at = datetime.now(timezone.utc)
            updated += 1
        except Exception as e:
            errors.append({"item_id": item_id, "error": str(e)})

    db.commit()

    logger.info(f"Bulk update: {updated} items updated, {len(errors)} errors")

    return {
        "message": f"{updated} items updated",
        "updated_count": updated,
        "error_count": len(errors),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Suggest Prices
# ---------------------------------------------------------------------------


def get_price_candidates(
    db: Session,
    *,
    item_type: str | None = None,
    category_id: int | None = None,
) -> list[dict]:
    """Return items eligible for price suggestions (excludes materials/supplies).

    Lightweight query — no inventory joins. Returns cost data for
    client-side margin calculation.
    """
    query = (
        db.query(Product)
        .filter(
            Product.active.is_(True),
            Product.standard_cost > 0,
            Product.item_type.notin_(["material", "supply"]),
            Product.material_type_id.is_(None),
        )
    )

    if item_type:
        query = query.filter(Product.item_type == item_type)

    if category_id:
        cat_ids = get_category_and_descendants(db, category_id)
        query = query.filter(Product.category_id.in_(cat_ids))

    items = query.order_by(Product.sku).all()

    return [
        {
            "id": item.id,
            "sku": item.sku,
            "name": item.name,
            "item_type": item.item_type or "finished_good",
            "standard_cost": float(item.standard_cost),
            "current_selling_price": float(item.selling_price) if item.selling_price is not None else None,
        }
        for item in items
    ]


def apply_suggested_prices(
    db: Session,
    items: list[dict],
) -> dict:
    """Apply selected suggested selling prices. Returns summary with old/new."""
    updated = 0
    skipped = 0
    results = []

    # Batch-fetch all products to avoid N+1
    item_ids = [entry["id"] for entry in items if "id" in entry]
    products = db.query(Product).filter(Product.id.in_(item_ids)).all()
    products_by_id = {p.id: p for p in products}

    # Excluded types (defense in depth — candidates endpoint already filters)
    excluded_types = {"material", "supply"}

    for entry in items:
        product = products_by_id.get(entry["id"])
        if not product:
            skipped += 1
            continue

        # Enforce same exclusion as get_price_candidates
        if (product.item_type in excluded_types) or product.material_type_id is not None:
            skipped += 1
            continue

        new_price = entry.get("selling_price")
        if new_price is None:
            skipped += 1
            continue

        old_price = float(product.selling_price) if product.selling_price is not None else None

        # Skip no-op writes
        if old_price is not None and abs(old_price - float(new_price)) < 0.0001:
            skipped += 1
            continue

        product.selling_price = new_price
        product.updated_at = datetime.now(timezone.utc)
        updated += 1

        results.append({
            "id": product.id,
            "sku": product.sku,
            "old_price": old_price,
            "new_price": float(new_price),
        })

    db.commit()

    logger.info(f"Apply suggested prices: {updated} updated, {skipped} skipped")

    return {
        "updated": updated,
        "skipped": skipped,
        "items": results,
    }


# ---------------------------------------------------------------------------
# Backward-compatibility re-exports (DEBT-1 D1-B mechanical split)
#
# item_service keeps its full historical public surface; new code should
# import from the focused modules directly. Placed at the bottom so the
# focused modules can resolve item_service helpers at call time.
# ---------------------------------------------------------------------------
from app.services.bom_management_service import (  # noqa: E402, F401
    recalculate_bom_cost,
)
from app.services.item_cost_service import (  # noqa: E402, F401
    calculate_item_cost,
    recost_all_items,
    recost_item,
)
from app.services.item_duplicate_service import (  # noqa: E402, F401
    duplicate_item,
)
from app.services.item_import_service import (  # noqa: E402, F401
    _COST_COLUMNS,
    _DESCRIPTION_COLUMNS,
    _NAME_COLUMNS,
    _PRICE_COLUMNS,
    _PURCHASE_UOM_COLUMNS,
    _SKU_COLUMNS,
    _UNIT_COLUMNS,
    _get_best_price_from_row,
    _get_category_id_from_row,
    _get_csv_column_value,
    _get_upc_from_row,
    _normalize_import_item_type,
    _parse_price,
    _strip_html,
    _update_category_from_row,
    import_items_from_csv,
)
