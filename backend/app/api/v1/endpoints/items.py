"""
Items API Endpoints - Unified item management for products, components, supplies, and services

Uses item_service for business logic (ARCHITECT-003).
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Query
from typing import List, Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user
from app.schemas.item import (
    ItemType,
    ProcurementType,
    ItemCategoryCreate,
    ItemCategoryUpdate,
    ItemCategoryResponse,
    ItemCategoryTreeNode,
    ItemCreate,
    ItemUpdate,
    ItemListResponse,
    ItemResponse,
    ItemCSVImportResult,
    ItemBulkUpdateRequest,
    MaterialItemCreate,
)
from app.schemas.item_demand import ItemDemandSummary
from app.services.item_demand import get_item_demand_summary
from app.services import item_service

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response Builders
# ---------------------------------------------------------------------------


def _build_category_response(cat) -> ItemCategoryResponse:
    """Build category response from model."""
    return ItemCategoryResponse(
        id=cat.id,
        code=cat.code,
        name=cat.name,
        parent_id=cat.parent_id,
        description=cat.description,
        sort_order=cat.sort_order,
        is_active=cat.is_active,
        parent_name=cat.parent.name if cat.parent else None,
        full_path=cat.full_path,
        created_at=cat.created_at,
        updated_at=cat.updated_at,
    )


def _build_item_response(item, db: Session) -> ItemResponse:
    """Build full item response with inventory and BOM info."""
    data = item_service.build_item_response_data(item, db)
    return ItemResponse(
        id=data["id"],
        sku=data["sku"],
        name=data["name"],
        description=data["description"],
        unit=data["unit"],
        item_type=ItemType(data["item_type"]) if data["item_type"] else ItemType.FINISHED_GOOD,
        procurement_type=ProcurementType(data["procurement_type"]) if data["procurement_type"] else ProcurementType.BUY,
        category_id=data["category_id"],
        cost_method=data["cost_method"],
        standard_cost=data["standard_cost"],
        average_cost=data["average_cost"],
        last_cost=data["last_cost"],
        selling_price=data["selling_price"],
        weight_oz=data["weight_oz"],
        length_in=data["length_in"],
        width_in=data["width_in"],
        height_in=data["height_in"],
        lead_time_days=data["lead_time_days"],
        min_order_qty=data["min_order_qty"],
        reorder_point=data["reorder_point"],
        upc=data["upc"],
        legacy_sku=data["legacy_sku"],
        active=data["active"],
        is_raw_material=data["is_raw_material"],
        track_lots=data["track_lots"],
        track_serials=data["track_serials"],
        category_name=data["category_name"],
        category_path=data["category_path"],
        on_hand_qty=data["on_hand_qty"],
        available_qty=data["available_qty"],
        allocated_qty=data["allocated_qty"],
        has_bom=data["has_bom"],
        bom_count=data["bom_count"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


# ============================================================================
# Item Categories
# ============================================================================


@router.get("/categories", response_model=List[ItemCategoryResponse])
async def list_categories(
    include_inactive: bool = False,
    parent_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """List all item categories"""
    categories = item_service.list_categories(
        db, include_inactive=include_inactive, parent_id=parent_id
    )
    return [_build_category_response(cat) for cat in categories]


@router.get("/categories/tree", response_model=List[ItemCategoryTreeNode])
async def get_category_tree(db: Session = Depends(get_db)):
    """Get categories as a nested tree structure"""
    tree_data = item_service.get_category_tree(db)

    def convert_to_tree_node(node_data: dict) -> ItemCategoryTreeNode:
        return ItemCategoryTreeNode(
            id=node_data["id"],
            code=node_data["code"],
            name=node_data["name"],
            description=node_data["description"],
            is_active=node_data["is_active"],
            children=[convert_to_tree_node(child) for child in node_data["children"]],
        )

    return [convert_to_tree_node(node) for node in tree_data]


@router.post("/categories", response_model=ItemCategoryResponse, status_code=201)
async def create_category(
    request: ItemCategoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new item category"""
    category = item_service.create_category(
        db,
        code=request.code,
        name=request.name,
        parent_id=request.parent_id,
        description=request.description,
        sort_order=request.sort_order,
        is_active=request.is_active if request.is_active is not None else True,
    )
    return _build_category_response(category)


@router.get("/categories/{category_id}", response_model=ItemCategoryResponse)
async def get_category(category_id: int, db: Session = Depends(get_db)):
    """Get a specific category by ID"""
    category = item_service.get_category(db, category_id)
    return _build_category_response(category)


@router.patch("/categories/{category_id}", response_model=ItemCategoryResponse)
async def update_category(
    category_id: int,
    request: ItemCategoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing category"""
    update_data = request.model_dump(exclude_unset=True)

    # Use ... as sentinel for "not provided" on parent_id
    parent_id_arg = update_data.pop("parent_id", ...)

    category = item_service.update_category(
        db,
        category_id,
        parent_id=parent_id_arg,
        **update_data,
    )
    return _build_category_response(category)


@router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft delete a category (set is_active=False)"""
    return item_service.delete_category(db, category_id)


# ============================================================================
# Items (Products with extended fields)
# ============================================================================


@router.get("", response_model=dict)
async def list_items(
    item_type: Optional[str] = Query(None, description="Filter by item type"),
    procurement_type: Optional[str] = Query(None, description="Filter by procurement type"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search SKU or name"),
    active_only: bool = Query(True, description="Only show active items"),
    needs_reorder: bool = Query(False, description="Only show items below reorder point"),
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List items with filtering and pagination"""
    items_data, total = item_service.list_items(
        db,
        item_type=item_type,
        procurement_type=procurement_type,
        category_id=category_id,
        search=search,
        active_only=active_only,
        needs_reorder=needs_reorder,
        limit=limit,
        offset=offset,
    )

    # Convert dicts to ItemListResponse
    result = [
        ItemListResponse(
            id=item["id"],
            sku=item["sku"],
            name=item["name"],
            item_type=item["item_type"],
            procurement_type=item["procurement_type"],
            category_id=item["category_id"],
            category_name=item["category_name"],
            unit=item["unit"],
            standard_cost=item["standard_cost"],
            average_cost=item["average_cost"],
            selling_price=item["selling_price"],
            suggested_price=item["suggested_price"],
            active=item["active"],
            on_hand_qty=item["on_hand_qty"],
            available_qty=item["available_qty"],
            reorder_point=item["reorder_point"],
            stocking_policy=item["stocking_policy"],
            needs_reorder=item["needs_reorder"],
        )
        for item in items_data
    ]

    return {"total": total, "items": result}


@router.post("", response_model=ItemResponse, status_code=201)
async def create_item(
    request: ItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new item"""
    data = request.model_dump()
    item = item_service.create_item(db, data=data)
    return _build_item_response(item, db)


@router.post("/material", response_model=ItemResponse, status_code=201)
async def create_material_item(
    request: MaterialItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a material item (shortcut for supply items with material_type/color).

    Automatically sets item_type='supply', procurement_type='buy', unit='G'.
    SKU is auto-generated as: MAT-{material_type_code}-{color_code}
    """
    from app.services.material_service import (
        create_material_product,
        get_material_type,
        get_color,
        MaterialNotFoundError,
        ColorNotFoundError,
    )
    from app.models import Product, Inventory
    from app.models.inventory import InventoryLocation
    from app.models.item_category import ItemCategory

    # Validate material type and color exist
    try:
        material_type = get_material_type(db, request.material_type_code)
        color = get_color(db, request.color_code)
    except MaterialNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ColorNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check if product already exists
    sku = f"MAT-{material_type.code}-{color.code}"
    existing = db.query(Product).filter(Product.sku == sku).first()
    if existing:
        # Update existing product
        if request.cost_per_kg is not None:
            existing.standard_cost = request.cost_per_kg
        if request.selling_price is not None:
            existing.selling_price = request.selling_price
        if request.category_id is not None:
            existing.category_id = request.category_id

        # Update initial inventory if provided
        # initial_qty_kg is in KG per schema; inventory stores in grams (product unit=G)
        if request.initial_qty_kg and request.initial_qty_kg > 0:
            from decimal import Decimal as D
            qty_grams = request.initial_qty_kg * D("1000")

            inventory = (
                db.query(Inventory)
                .filter(Inventory.product_id == existing.id)
                .first()
            )
            if inventory:
                inventory.on_hand_quantity = qty_grams
            else:
                location = (
                    db.query(InventoryLocation)
                    .filter(InventoryLocation.code == "MAIN")
                    .first()
                )
                if not location:
                    location = InventoryLocation(
                        name="Main Warehouse", code="MAIN", type="warehouse"
                    )
                    db.add(location)
                    db.flush()

                inventory = Inventory(
                    product_id=existing.id,
                    location_id=location.id,
                    on_hand_quantity=qty_grams,
                    allocated_quantity=0,
                )
                db.add(inventory)

        db.commit()
        db.refresh(existing)
        logger.info(f"Updated existing material item: {existing.sku}")
        return _build_item_response(existing, db)

    # Create new material product
    product = create_material_product(
        db,
        material_type_code=request.material_type_code,
        color_code=request.color_code,
        commit=False,
    )

    if request.cost_per_kg is not None:
        product.standard_cost = request.cost_per_kg

    if request.selling_price is not None:
        product.selling_price = request.selling_price

    if request.category_id:
        category = (
            db.query(ItemCategory).filter(ItemCategory.id == request.category_id).first()
        )
        if not category:
            raise HTTPException(
                status_code=400, detail=f"Category {request.category_id} not found"
            )
        product.category_id = request.category_id
    else:
        materials_category = (
            db.query(ItemCategory)
            .filter(ItemCategory.code.ilike("%MATERIAL%"))
            .first()
        )
        if materials_category:
            product.category_id = materials_category.id

    # initial_qty_kg is in KG per schema; inventory stores in grams (product unit=G)
    if request.initial_qty_kg and request.initial_qty_kg > 0:
        from decimal import Decimal as D
        qty_grams = request.initial_qty_kg * D("1000")

        inventory = (
            db.query(Inventory).filter(Inventory.product_id == product.id).first()
        )
        if inventory:
            inventory.on_hand_quantity = qty_grams

    db.commit()
    db.refresh(product)

    logger.info(f"Created material item: {product.sku}")

    return _build_item_response(product, db)


# ============================================================================
# Low Stock / Reorder Alerts
# ============================================================================


@router.get("/low-stock")
async def get_low_stock_items(
    include_zero_reorder: bool = False,
    include_mrp_shortages: bool = Query(True, description="Include MRP shortages"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Get items that are below their reorder point OR have shortages from active orders."""
    return item_service.get_low_stock_items(
        db,
        include_zero_reorder=include_zero_reorder,
        include_mrp_shortages=include_mrp_shortages,
        limit=limit,
    )


@router.get("/{item_id}/demand-summary", response_model=ItemDemandSummary)
async def get_demand_summary(item_id: int, db: Session = Depends(get_db)):
    """Get demand summary for an inventory item."""
    summary = get_item_demand_summary(db, item_id)

    if summary is None:
        raise HTTPException(status_code=404, detail=f"Item {item_id} not found")

    return summary


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, db: Session = Depends(get_db)):
    """Get a specific item by ID"""
    item = item_service.get_item(db, item_id)
    return _build_item_response(item, db)


@router.get("/sku/{sku}", response_model=ItemResponse)
async def get_item_by_sku(sku: str, db: Session = Depends(get_db)):
    """Get a specific item by SKU"""
    item = item_service.get_item_by_sku(db, sku)
    return _build_item_response(item, db)


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    request: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing item"""
    data = request.model_dump(exclude_unset=True)
    item = item_service.update_item(db, item_id, data=data)
    return _build_item_response(item, db)


@router.delete("/{item_id}")
async def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft delete an item (set active=False)"""
    return item_service.delete_item(db, item_id)


# ============================================================================
# Bulk Operations
# ============================================================================


@router.post("/import", response_model=ItemCSVImportResult)
async def import_items_csv(
    file: UploadFile = File(...),
    update_existing: bool = Query(False, description="Update items if SKU exists"),
    default_item_type: str = Query("finished_good", description="Default item type"),
    default_category_id: Optional[int] = Query(None, description="Default category"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import items from CSV file"""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    content = await file.read()

    result = item_service.import_items_from_csv(
        db,
        file_content=content,
        update_existing=update_existing,
        default_item_type=default_item_type,
        default_category_id=default_category_id,
    )

    return ItemCSVImportResult(
        total_rows=result["total_rows"],
        created=result["created"],
        updated=result["updated"],
        skipped=result["skipped"],
        errors=result["errors"],
        warnings=result.get("warnings", []),
    )


@router.post("/bulk-update")
async def bulk_update_items(
    request: ItemBulkUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk update multiple items at once"""
    try:
        return item_service.bulk_update_items(
            db,
            item_ids=request.item_ids,
            category_id=request.category_id,
            item_type=request.item_type.value if request.item_type and hasattr(request.item_type, "value") else request.item_type,
            procurement_type=request.procurement_type.value if request.procurement_type and hasattr(request.procurement_type, "value") else request.procurement_type,
            is_active=request.is_active,
        )
    except HTTPException:
        raise
    except Exception:
        logger.error("Bulk update failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Bulk update failed. Check server logs for details.")


# ============================================================================
# Recost Operations
# ============================================================================


@router.post("/recost-all")
async def recost_all_items(
    item_type: Optional[str] = Query(None, description="Filter by item type"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    cost_source: Optional[str] = Query(None, description="Filter: 'manufactured' or 'purchased'"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recost all items matching filters."""
    return item_service.recost_all_items(
        db,
        item_type=item_type,
        category_id=category_id,
        cost_source_filter=cost_source,
    )


@router.post("/{item_id}/recost")
async def recost_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Recost a single item."""
    return item_service.recost_item(db, item_id)
