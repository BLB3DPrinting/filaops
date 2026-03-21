"""
Item Service — CRUD and business logic for items and categories.

Items extends Products with inventory info, categories, reorder logic,
CSV import, and cost recalculation. Extracted from items.py (ARCHITECT-003).
"""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import or_, func
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models import Product, ItemCategory, Inventory, BOM, BOMLine
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.core.utils import get_or_404, check_unique_or_400
from app.core.uom_config import DEFAULT_MATERIAL_UOM, get_default_material_sku_prefix
from app.services.bom_management_service import recalculate_bom_cost

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
        .filter(Product.active.is_(True))
        .group_by(Product.item_type)
        .all()
    )

    # Count items below reorder point (outerjoin so products with no inventory = 0 on-hand)
    reorder_subq = (
        db.query(Product.id)
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .filter(
            Product.active.is_(True),
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

    valid_item_types = ["finished_good", "component", "supply", "service", "material"]
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

    if bom:
        cost_source = "manufactured"
        bom_id = bom.id
        bom_cost_decimal = recalculate_bom_cost(bom, db)
        bom.total_cost = bom_cost_decimal  # Keep BOM total_cost in sync
        bom_cost = float(bom_cost_decimal)

        routing = (
            db.query(Routing)
            .filter(Routing.product_id == item.id, Routing.is_active.is_(True))
            .first()
        )
        if routing and routing.total_cost:
            routing_cost = float(routing.total_cost)
            routing_id = routing.id

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
# CSV Import Column Mappings
# ---------------------------------------------------------------------------

# Marketplace column mappings for SKU
_SKU_COLUMNS = [
    "sku", "SKU", "Sku", "product_sku", "Product SKU", "product-sku",
    "Variant SKU", "variant_sku", "variant-sku", "VariantSKU",
    "SKU Code", "sku_code", "sku-code", "SKUCode",
    "ASIN", "asin", "Amazon ASIN",
    "Product Code", "product_code", "product-code",
    "Item SKU", "item_sku", "item-sku",
    "Product ID", "product_id", "product-id",
]

# Marketplace column mappings for Name
_NAME_COLUMNS = [
    "name", "Name", "product_name", "Product Name", "product-name",
    "title", "Title", "Product Title", "product-title",
    "Variant Title", "variant_title", "variant-title", "VariantTitle",
    "Product Title", "product_title", "product-title", "ProductTitle",
    "Item Name", "item_name", "item-name",
]

# Marketplace column mappings for Description
_DESCRIPTION_COLUMNS = [
    "description", "Description", "product_description", "Product Description",
    "Body (HTML)", "body_html", "Body", "body", "Body HTML",
    "Short Description", "short_description", "short-description", "Short description",
    "Long Description", "long_description", "long-description",
    "Product Description", "product-description",
    "Item Description", "item_description",
]

# Marketplace column mappings for Price
_PRICE_COLUMNS = [
    "selling_price", "Selling Price", "selling-price",
    "price", "Price",
    "Variant Price", "variant_price", "variant-price", "VariantPrice",
    "Variant Compare At Price", "variant_compare_at_price", "variant-compare-at-price",
    "Sale price", "sale_price", "sale-price", "Sale Price",
    "Regular price", "regular_price", "regular-price", "Regular Price",
    "Unit Price", "unit_price", "unit-price", "UnitPrice",
    "Retail Price", "retail_price", "retail-price",
    "List Price", "list_price", "list-price",
]

# Marketplace column mappings for Cost
_COST_COLUMNS = [
    "standard_cost", "Standard Cost", "standard-cost",
    "cost", "Cost",
    "Variant Cost", "variant_cost", "variant-cost", "VariantCost",
    "Wholesale Price", "wholesale_price", "wholesale-price",
    "Cost Price", "cost_price", "cost-price", "CostPrice",
    "Purchase PPU", "purchase_ppu", "purchase-ppu",
    "Item Subtotal", "item_subtotal",
    "Purchase Cost", "purchase_cost", "purchase-cost",
    "Unit Cost", "unit_cost", "unit-cost",
    "Wholesale Cost", "wholesale_cost",
]

# UOM column mappings
_UNIT_COLUMNS = [
    "unit", "Unit", "UOM", "uom", "Unit of Measure", "unit_of_measure",
]

_PURCHASE_UOM_COLUMNS = [
    "purchase_uom", "Purchase UOM", "purchase_unit", "Purchase Unit",
    "buying_unit", "Buying Unit", "order_unit", "Order Unit",
]


def _get_csv_column_value(row: dict, possible_names: list[str]) -> str:
    """Get value from CSV row using case-insensitive column name matching."""
    for col in possible_names:
        if row.get(col, "").strip():
            return row.get(col, "").strip()
    return ""


def _parse_price(price_str: str) -> float | None:
    """Parse price string, removing currency symbols."""
    if not price_str:
        return None
    price_clean = (
        price_str.replace("$", "")
        .replace(",", "")
        .replace("€", "")
        .replace("£", "")
        .strip()
    )
    try:
        return float(price_clean)
    except ValueError:
        return None


def _strip_html(text: str) -> str:
    """Strip HTML tags from text."""
    import re

    if "<" in text and ">" in text:
        return re.sub(r"<[^>]+>", "", text).strip()
    return text


def import_items_from_csv(
    db: Session,
    *,
    file_content: bytes,
    update_existing: bool = False,
    default_item_type: str = "finished_good",
    default_category_id: int | None = None,
) -> dict:
    """
    Import items from CSV file content.

    Returns dict with keys: total_rows, created, updated, skipped, errors, warnings.
    """
    from app.services.product_uom_service import get_recommended_uoms, validate_product_uoms

    try:
        text = file_content.decode("utf-8")
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")

    if text.startswith("\ufeff"):
        text = text[1:]

    reader = csv.DictReader(io.StringIO(text))

    result = {
        "total_rows": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "warnings": [],
    }

    for row_num, row in enumerate(reader, start=2):
        result["total_rows"] += 1

        try:
            # Find SKU
            sku = _get_csv_column_value(row, _SKU_COLUMNS).upper()
            if not sku:
                result["errors"].append({
                    "row": row_num,
                    "error": "SKU is required",
                })
                result["skipped"] += 1
                continue

            # Find name
            name = _get_csv_column_value(row, _NAME_COLUMNS)
            if not name:
                result["errors"].append({
                    "row": row_num,
                    "error": "Name is required",
                    "sku": sku,
                })
                result["skipped"] += 1
                continue

            # Check if exists
            existing = db.query(Product).filter(Product.sku == sku).first()

            if existing:
                # Protect seeded example items
                if existing.sku.startswith("SEED-EXAMPLE-"):
                    result["errors"].append({
                        "row": row_num,
                        "error": f"SKU '{sku}' is a seeded example item",
                        "sku": sku,
                    })
                    result["skipped"] += 1
                    continue

                if not update_existing:
                    result["skipped"] += 1
                    continue

                # Update existing
                existing.name = name

                # Update description
                desc = _get_csv_column_value(row, _DESCRIPTION_COLUMNS)
                if desc:
                    existing.description = _strip_html(desc)

                # Update unit
                unit_value = _get_csv_column_value(row, _UNIT_COLUMNS).upper()
                if unit_value:
                    existing.unit = unit_value

                # Update purchase_uom
                purchase_uom_value = _get_csv_column_value(
                    row, _PURCHASE_UOM_COLUMNS
                ).upper()
                if purchase_uom_value:
                    existing.purchase_uom = purchase_uom_value

                # Update item type
                item_type_raw = (
                    row.get("item_type", "")
                    or row.get("Item Type", "")
                    or row.get("Type", "")
                ).strip()
                if item_type_raw:
                    item_type_map = {
                        "simple": "finished_good",
                        "variable": "finished_good",
                        "finished_good": "finished_good",
                        "component": "component",
                        "supply": "supply",
                        "service": "service",
                        "material": "material",
                        "filament": "material",
                        "raw_material": "material",
                    }
                    existing.item_type = item_type_map.get(
                        item_type_raw.lower(), existing.item_type
                    )

                # Update category
                _update_category_from_row(db, existing, row, default_category_id)

                # Update cost
                cost_str = _get_csv_column_value(row, _COST_COLUMNS)
                cost = _parse_price(cost_str)
                if cost is not None:
                    existing.standard_cost = cost

                # Update price
                price_str = _get_best_price_from_row(row)
                price = _parse_price(price_str)
                if price is not None:
                    existing.selling_price = price

                # Update reorder point
                if row.get("reorder_point"):
                    try:
                        existing.reorder_point = float(row["reorder_point"])
                    except ValueError:
                        pass

                # Update UPC
                upc = _get_upc_from_row(row)
                if upc:
                    existing.upc = upc

                existing.updated_at = datetime.now(timezone.utc)

                # Validate UOM configuration
                is_valid, warning_msg = validate_product_uoms(db, existing)
                if not is_valid:
                    result["warnings"].append({
                        "row": row_num,
                        "sku": sku,
                        "warning": warning_msg,
                    })

                result["updated"] += 1

            else:
                # Create new item
                desc = _get_csv_column_value(row, _DESCRIPTION_COLUMNS)
                description = _strip_html(desc) if desc else None

                price_str = _get_best_price_from_row(row)
                selling_price = _parse_price(price_str)

                cost_str = _get_csv_column_value(row, _COST_COLUMNS)
                standard_cost = _parse_price(cost_str)

                # Handle category
                final_category_id = _get_category_id_from_row(
                    db, row, default_category_id
                )

                # Get unit from CSV
                unit_value = _get_csv_column_value(row, _UNIT_COLUMNS).upper()
                purchase_uom_value = _get_csv_column_value(
                    row, _PURCHASE_UOM_COLUMNS
                ).upper()

                # Auto-detect UOMs based on SKU/category if not provided
                if not purchase_uom_value or not unit_value:
                    recommended_purchase, recommended_unit, is_material = (
                        get_recommended_uoms(db, sku=sku, category_id=final_category_id)
                    )
                    if not purchase_uom_value:
                        purchase_uom_value = recommended_purchase
                    if not unit_value and is_material:
                        unit_value = recommended_unit

                final_unit = unit_value or "EA"
                final_purchase_uom = purchase_uom_value or final_unit

                # Get item type
                item_type_str = (
                    row.get("item_type", "")
                    or row.get("Item Type", "")
                    or ""
                ).strip() or default_item_type

                # Get reorder point
                reorder_point = None
                if row.get("reorder_point"):
                    try:
                        reorder_point = float(row["reorder_point"])
                    except ValueError:
                        pass

                # Get UPC
                upc = _get_upc_from_row(row)

                item = Product(
                    sku=sku,
                    name=name,
                    description=description,
                    unit=final_unit,
                    purchase_uom=final_purchase_uom,
                    item_type=item_type_str,
                    category_id=final_category_id,
                    standard_cost=standard_cost,
                    selling_price=selling_price,
                    reorder_point=reorder_point,
                    upc=upc,
                    active=True,
                )
                db.add(item)
                db.flush()

                # Validate UOM configuration
                is_valid, warning_msg = validate_product_uoms(db, item)
                if not is_valid:
                    result["warnings"].append({
                        "row": row_num,
                        "sku": sku,
                        "warning": warning_msg,
                    })

                result["created"] += 1

        except Exception as e:
            result["errors"].append({
                "row": row_num,
                "error": str(e),
                "sku": row.get("sku", ""),
            })
            result["skipped"] += 1

    db.commit()

    logger.info(
        f"CSV import complete: {result['created']} created, "
        f"{result['updated']} updated, {result['skipped']} skipped, "
        f"{len(result['warnings'])} UOM warnings"
    )

    return result


def _get_best_price_from_row(row: dict) -> str:
    """Get the best price from CSV row, preferring sale price."""
    for col in _PRICE_COLUMNS:
        value = row.get(col, "").strip()
        if value:
            # Prefer sale price if available (WooCommerce)
            if "sale" in col.lower():
                return value
    # Return first found as fallback
    return _get_csv_column_value(row, _PRICE_COLUMNS)


def _get_upc_from_row(row: dict) -> str | None:
    """Get UPC/barcode from CSV row."""
    upc_cols = [
        "upc", "UPC", "barcode", "Barcode", "EAN", "GTIN",
        "Product Code", "product_code", "ASIN", "asin",
    ]
    value = _get_csv_column_value(row, upc_cols)
    return value if value else None


def _update_category_from_row(
    db: Session, product: Product, row: dict, default_category_id: int | None
) -> None:
    """Update product category from CSV row data."""
    # Try category_id first (numeric)
    category_id_raw = (
        row.get("category_id", "")
        or row.get("Category ID", "")
        or row.get("category-id", "")
    ).strip()
    if category_id_raw:
        try:
            product.category_id = int(category_id_raw)
            return
        except ValueError:
            pass

    # Try category name
    category_name_raw = (
        row.get("Category", "")
        or row.get("category", "")
        or row.get("Categories", "")
        or row.get("Product Category", "")
        or row.get("Type", "")
        or row.get("Product Type", "")
    ).strip()

    if category_name_raw:
        # Handle WooCommerce comma-separated categories (take first)
        if "," in category_name_raw:
            category_name_raw = category_name_raw.split(",")[0].strip()

        # Try to find category by name
        category = (
            db.query(ItemCategory)
            .filter(ItemCategory.name.ilike(f"%{category_name_raw}%"))
            .first()
        )
        if category:
            product.category_id = category.id


def _get_category_id_from_row(
    db: Session, row: dict, default_category_id: int | None
) -> int | None:
    """Get category ID from CSV row data."""
    # Try category_id first (numeric)
    category_id_raw = (
        row.get("category_id", "")
        or row.get("Category ID", "")
        or row.get("category-id", "")
    ).strip()
    if category_id_raw:
        try:
            return int(category_id_raw)
        except ValueError:
            pass

    # Try category name
    category_name_raw = (
        row.get("Category", "")
        or row.get("category", "")
        or row.get("Categories", "")
        or row.get("Product Category", "")
        or row.get("Type", "")
        or row.get("Product Type", "")
    ).strip()

    if category_name_raw:
        if "," in category_name_raw:
            category_name_raw = category_name_raw.split(",")[0].strip()

        category = (
            db.query(ItemCategory)
            .filter(ItemCategory.name.ilike(f"%{category_name_raw}%"))
            .first()
        )
        if category:
            return category.id

    return default_category_id


# --- Duplicate Item ---

def duplicate_item(
    db: Session,
    source_item_id: int,
    *,
    new_sku: str,
    new_name: str,
    bom_line_overrides: list[dict] | None = None,
) -> dict:
    """
    Duplicate a product: clone all fields with a new SKU/name,
    copy the active BOM (if any), and apply component overrides.

    Returns dict with: id, sku, name, has_bom, bom_id, message
    """
    source = get_item(db, source_item_id)

    # Validate new SKU uniqueness
    new_sku_upper = new_sku.upper().strip()
    if not new_sku_upper:
        raise HTTPException(status_code=400, detail="SKU cannot be blank")
    new_name_clean = new_name.strip()
    if not new_name_clean:
        raise HTTPException(status_code=400, detail="Name cannot be blank")
    check_unique_or_400(db, Product, "sku", new_sku_upper)

    # Fields to exclude from copy:
    # - Identity: id, sku, name, timestamps
    # - External IDs: woocommerce, squarespace, legacy_sku, upc (unique per item)
    # - Purchase history: average_cost, last_cost (no history for new item)
    # - Per-variant assets: gcode_file_path, image_url (different per color/variant)
    # - B2B restriction: customer_id (new item starts unrestricted)
    EXCLUDE_FIELDS = {
        "id", "sku", "name", "created_at", "updated_at",
        "woocommerce_product_id", "squarespace_product_id",
        "legacy_sku", "upc",
        "average_cost", "last_cost",
        "gcode_file_path", "image_url",
        "customer_id",
    }

    # Clone product fields
    clone_data = {}
    for col in Product.__table__.columns:
        if col.name not in EXCLUDE_FIELDS:
            clone_data[col.name] = getattr(source, col.name)

    clone_data["sku"] = new_sku_upper
    clone_data["name"] = new_name_clean
    clone_data["has_bom"] = False  # Will be set True if BOM is copied

    new_item = Product(**clone_data)
    db.add(new_item)
    db.flush()  # Get the new item's ID

    # Copy active BOM if source has one
    bom_id = None
    active_bom = (
        db.query(BOM)
        .filter(BOM.product_id == source.id, BOM.active.is_(True))
        .first()
    )

    if active_bom:
        new_bom = BOM(
            product_id=new_item.id,
            code=f"{new_sku_upper}-BOM"[:50],
            name=f"BOM for {new_item.name}"[:255],
            version=1,
            revision=active_bom.revision,
            assembly_time_minutes=active_bom.assembly_time_minutes,
            effective_date=active_bom.effective_date,
            notes=f"Duplicated from {source.sku}",
            active=True,
        )
        db.add(new_bom)
        db.flush()

        # Build override lookup: original_component_id -> new_component_id
        # NOTE: Keyed by component_id, so if the same component appears on
        # multiple BOM lines, ALL instances get swapped. This is intentional
        # for color variants (swap every instance of "PLA Red" to "PLA Blue").
        override_map = {}
        if bom_line_overrides:
            for ov in bom_line_overrides:
                orig_id = ov.get("original_component_id")
                new_id = ov.get("new_component_id")
                if orig_id and new_id:
                    # Validate new component exists
                    if not db.query(Product).filter(Product.id == new_id).first():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Override component ID {new_id} not found"
                        )
                    override_map[orig_id] = new_id

        # Copy lines with overrides
        source_lines = (
            db.query(BOMLine)
            .filter(BOMLine.bom_id == active_bom.id)
            .order_by(BOMLine.sequence)
            .all()
        )
        for line in source_lines:
            component_id = override_map.get(line.component_id, line.component_id)
            new_line = BOMLine(
                bom_id=new_bom.id,
                component_id=component_id,
                quantity=line.quantity,
                unit=line.unit,
                sequence=line.sequence,
                consume_stage=line.consume_stage,
                is_cost_only=line.is_cost_only,
                scrap_factor=line.scrap_factor,
                notes=line.notes,
            )
            db.add(new_line)

        db.flush()
        new_bom.total_cost = recalculate_bom_cost(new_bom, db)
        new_item.has_bom = True
        bom_id = new_bom.id

    # Copy active routing if source has one
    routing_id = None
    active_routing = (
        db.query(Routing)
        .filter(Routing.product_id == source.id, Routing.is_active.is_(True))
        .first()
    )

    if active_routing:
        new_routing = Routing(
            product_id=new_item.id,
            code=f"RTG-{new_sku_upper}"[:50],
            name=f"Routing for {new_item.name}"[:200],
            is_template=False,
            version=1,
            revision="1.0",
            is_active=True,
            effective_date=active_routing.effective_date,
            notes=f"Duplicated from {source.sku}",
        )
        db.add(new_routing)
        db.flush()

        # Copy operations — track old_id -> new_id for predecessor remapping
        op_id_map: dict[int, int] = {}
        source_ops = (
            db.query(RoutingOperation)
            .filter(RoutingOperation.routing_id == active_routing.id)
            .order_by(RoutingOperation.sequence)
            .all()
        )

        for op in source_ops:
            new_op = RoutingOperation(
                routing_id=new_routing.id,
                work_center_id=op.work_center_id,
                sequence=op.sequence,
                operation_code=op.operation_code,
                operation_name=op.operation_name,
                description=op.description,
                setup_time_minutes=op.setup_time_minutes,
                run_time_minutes=op.run_time_minutes,
                wait_time_minutes=op.wait_time_minutes,
                move_time_minutes=op.move_time_minutes,
                runtime_source=op.runtime_source,
                slicer_file_path=op.slicer_file_path,
                units_per_cycle=op.units_per_cycle,
                scrap_rate_percent=op.scrap_rate_percent,
                labor_rate_override=op.labor_rate_override,
                machine_rate_override=op.machine_rate_override,
                can_overlap=op.can_overlap,
                is_active=op.is_active,
                # predecessor_operation_id set in second pass below
            )
            db.add(new_op)
            db.flush()
            op_id_map[op.id] = new_op.id

            # Copy operation materials with component overrides
            for mat in op.materials:
                component_id = override_map.get(mat.component_id, mat.component_id) if active_bom else mat.component_id
                new_mat = RoutingOperationMaterial(
                    routing_operation_id=new_op.id,
                    component_id=component_id,
                    quantity=mat.quantity,
                    quantity_per=mat.quantity_per,
                    unit=mat.unit,
                    scrap_factor=mat.scrap_factor,
                    is_cost_only=mat.is_cost_only,
                    is_optional=mat.is_optional,
                    notes=mat.notes,
                )
                db.add(new_mat)

        # Second pass: remap predecessor_operation_id references
        for old_op in source_ops:
            if old_op.predecessor_operation_id and old_op.predecessor_operation_id in op_id_map:
                new_op_id = op_id_map[old_op.id]
                db.query(RoutingOperation).filter(
                    RoutingOperation.id == new_op_id
                ).update({
                    "predecessor_operation_id": op_id_map[old_op.predecessor_operation_id]
                })

        db.flush()
        new_routing.recalculate_totals()
        routing_id = new_routing.id

    db.commit()
    db.refresh(new_item)

    # Build summary message
    parts = [f"Duplicated from {source.sku}"]
    if active_bom:
        parts.append(f"with BOM ({len(source_lines)} lines)")
    if active_routing:
        parts.append(f"routing ({len(source_ops)} operations)")
    if not active_bom and not active_routing:
        parts.append("(no BOM or routing)")

    return {
        "id": new_item.id,
        "sku": new_item.sku,
        "name": new_item.name,
        "has_bom": new_item.has_bom,
        "bom_id": bom_id,
        "routing_id": routing_id,
        "message": " ".join(parts),
    }
