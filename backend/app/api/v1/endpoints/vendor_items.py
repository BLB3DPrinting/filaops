"""
Vendor Items API Endpoints

Manage vendor SKU mappings for invoice parsing memory:
- CRUD operations for vendor item mappings
- Search across all vendors
- Product suggestion endpoint
"""
from typing import Optional, List
from decimal import Decimal
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.purchase_order_document import VendorItem
from app.api.v1.deps import get_current_staff_user
from app.models.user import User
from app.schemas.purchasing import (
    VendorItemCreate,
    VendorItemUpdate,
    VendorItemResponse,
)

# SEC-407: every vendor-item route is staff-only (admin or operator). They
# share the /purchase-orders prefix and hold supplier SKU mappings and costs
# used by invoice parsing; a self-registered customer must not read or edit
# them.
router = APIRouter(dependencies=[Depends(get_current_staff_user)])
logger = get_logger(__name__)


def _vendor_item_to_response(item: VendorItem) -> VendorItemResponse:
    """Convert VendorItem model to response schema with joined product info."""
    return VendorItemResponse(
        id=item.id,
        vendor_id=item.vendor_id,
        vendor_sku=item.vendor_sku,
        vendor_description=item.vendor_description,
        product_id=item.product_id,
        default_unit_cost=Decimal(item.default_unit_cost) if item.default_unit_cost else None,
        default_purchase_unit=item.default_purchase_unit,
        notes=item.notes,
        last_seen_at=item.last_seen_at,
        times_ordered=item.times_ordered or 0,
        created_at=item.created_at,
        updated_at=item.updated_at,
        product_sku=item.product.sku if item.product else None,
        product_name=item.product.name if item.product else None,
    )


@router.get("/vendors/{vendor_id}/items", response_model=List[VendorItemResponse])
async def list_vendor_items(
    vendor_id: int,
    unmapped_only: bool = Query(False, description="Only show items without product mapping"),
    search: Optional[str] = Query(None, description="Search by vendor SKU or description"),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    List all SKU mappings for a vendor.

    Use this to see what vendor SKUs have been encountered and how they're mapped
    to internal products.
    """
    # Verify vendor exists
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    query = db.query(VendorItem).filter(VendorItem.vendor_id == vendor_id)

    if unmapped_only:
        query = query.filter(VendorItem.product_id.is_(None))

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                VendorItem.vendor_sku.ilike(search_pattern),
                VendorItem.vendor_description.ilike(search_pattern),
            )
        )

    # Order by most recently seen
    query = query.order_by(VendorItem.last_seen_at.desc().nullslast())

    items = query.options(joinedload(VendorItem.product)).offset(offset).limit(limit).all()

    return [_vendor_item_to_response(item) for item in items]


@router.post("/vendors/{vendor_id}/items", response_model=VendorItemResponse, status_code=201)
async def create_vendor_item(
    vendor_id: int,
    request: VendorItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Create a new vendor SKU mapping.

    Maps a vendor's SKU/part number to an internal product for future invoice parsing.
    """
    # Verify vendor exists
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    # Check for duplicate vendor_sku
    existing = db.query(VendorItem).filter(
        VendorItem.vendor_id == vendor_id,
        VendorItem.vendor_sku == request.vendor_sku,
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Vendor SKU '{request.vendor_sku}' already exists for this vendor"
        )

    # Verify product exists if provided
    if request.product_id:
        product = db.query(Product).filter(Product.id == request.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

    item = VendorItem(
        vendor_id=vendor_id,
        vendor_sku=request.vendor_sku,
        vendor_description=request.vendor_description,
        product_id=request.product_id,
        default_unit_cost=str(request.default_unit_cost) if request.default_unit_cost else None,
        default_purchase_unit=request.default_purchase_unit,
        notes=request.notes,
        last_seen_at=datetime.now(timezone.utc),
        times_ordered=0,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    # Load relationship
    if item.product_id:
        _ = item.product

    logger.info(f"Created vendor item mapping: {vendor.name} / {request.vendor_sku}")
    return _vendor_item_to_response(item)


@router.get("/vendors/{vendor_id}/items/{item_id}", response_model=VendorItemResponse)
async def get_vendor_item(
    vendor_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Get a specific vendor item mapping."""
    item = db.query(VendorItem).options(
        joinedload(VendorItem.product)
    ).filter(
        VendorItem.id == item_id,
        VendorItem.vendor_id == vendor_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    return _vendor_item_to_response(item)


@router.put("/vendors/{vendor_id}/items/{item_id}", response_model=VendorItemResponse)
async def update_vendor_item(
    vendor_id: int,
    item_id: int,
    request: VendorItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Update a vendor item mapping.

    Typically used to map/remap a vendor SKU to a different product.
    """
    item = db.query(VendorItem).filter(
        VendorItem.id == item_id,
        VendorItem.vendor_id == vendor_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    # Verify product exists if provided
    if request.product_id is not None:
        if request.product_id:
            product = db.query(Product).filter(Product.id == request.product_id).first()
            if not product:
                raise HTTPException(status_code=404, detail="Product not found")

    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'default_unit_cost' and value is not None:
            setattr(item, field, str(value))
        else:
            setattr(item, field, value)

    db.commit()
    db.refresh(item)

    # Load relationship
    if item.product_id:
        _ = item.product

    logger.info(f"Updated vendor item mapping: {item_id}")
    return _vendor_item_to_response(item)


@router.delete("/vendors/{vendor_id}/items/{item_id}", status_code=204)
async def delete_vendor_item(
    vendor_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Delete a vendor item mapping."""
    item = db.query(VendorItem).filter(
        VendorItem.id == item_id,
        VendorItem.vendor_id == vendor_id,
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Vendor item not found")

    db.delete(item)
    db.commit()

    logger.info(f"Deleted vendor item mapping: {item_id}")
    return None


@router.get("/vendor-items/search", response_model=List[VendorItemResponse])
async def search_vendor_items(
    q: str = Query(..., min_length=1, description="Search query"),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor"),
    unmapped_only: bool = Query(False, description="Only show unmapped items"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Search vendor items across all vendors.

    Useful for finding if a SKU has been seen before from any vendor.
    """
    search_pattern = f"%{q}%"

    query = db.query(VendorItem).filter(
        or_(
            VendorItem.vendor_sku.ilike(search_pattern),
            VendorItem.vendor_description.ilike(search_pattern),
        )
    )

    if vendor_id:
        query = query.filter(VendorItem.vendor_id == vendor_id)

    if unmapped_only:
        query = query.filter(VendorItem.product_id.is_(None))

    items = query.options(
        joinedload(VendorItem.product),
        joinedload(VendorItem.vendor),
    ).order_by(VendorItem.times_ordered.desc()).limit(limit).all()

    return [_vendor_item_to_response(item) for item in items]


@router.post("/vendor-items/suggest-match")
async def suggest_product_match(
    vendor_sku: str = Query(..., description="Vendor SKU to match"),
    vendor_description: Optional[str] = Query(None, description="Vendor description for fuzzy matching"),
    limit: int = Query(5, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Get product suggestions for a vendor SKU.

    Returns potential matches based on:
    1. Exact SKU match from other vendors
    2. Fuzzy SKU similarity
    3. Description similarity (if provided)
    """
    suggestions = []

    # 1. Check if this vendor SKU is mapped by another vendor
    existing_mappings = db.query(VendorItem).filter(
        VendorItem.vendor_sku == vendor_sku,
        VendorItem.product_id.isnot(None),
    ).options(joinedload(VendorItem.product)).limit(5).all()

    for mapping in existing_mappings:
        if mapping.product:
            suggestions.append({
                "product_id": mapping.product.id,
                "product_sku": mapping.product.sku,
                "product_name": mapping.product.name,
                "match_type": "exact_vendor_sku",
                "confidence": "high",
                "source": f"Mapped by vendor {mapping.vendor_id}",
            })

    # 2. Search products by SKU similarity
    sku_pattern = f"%{vendor_sku}%"
    similar_products = db.query(Product).filter(
        Product.sku.ilike(sku_pattern),
        Product.active.is_(True),
    ).limit(limit).all()

    for product in similar_products:
        if not any(s["product_id"] == product.id for s in suggestions):
            suggestions.append({
                "product_id": product.id,
                "product_sku": product.sku,
                "product_name": product.name,
                "match_type": "sku_similarity",
                "confidence": "medium",
                "source": "SKU pattern match",
            })

    # 3. Search by description if provided
    if vendor_description and len(suggestions) < limit:
        words = vendor_description.split()[:3]  # First 3 words
        for word in words:
            if len(word) >= 3:  # Skip short words
                desc_pattern = f"%{word}%"
                name_matches = db.query(Product).filter(
                    Product.name.ilike(desc_pattern),
                    Product.active.is_(True),
                ).limit(5).all()

                for product in name_matches:
                    if not any(s["product_id"] == product.id for s in suggestions):
                        suggestions.append({
                            "product_id": product.id,
                            "product_sku": product.sku,
                            "product_name": product.name,
                            "match_type": "description_similarity",
                            "confidence": "low",
                            "source": f"Name contains '{word}'",
                        })
                        if len(suggestions) >= limit:
                            break

    return {
        "vendor_sku": vendor_sku,
        "suggestions": suggestions[:limit],
    }


@router.post("/vendor-items/bulk-update-last-seen")
async def bulk_update_last_seen(
    items: List[dict],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Bulk update last_seen_at and increment times_ordered for vendor items.

    Called after parsing an invoice to update usage stats.

    Request body: [{"vendor_id": 1, "vendor_sku": "ABC123"}, ...]
    """
    updated_count = 0
    now = datetime.now(timezone.utc)

    for item_data in items:
        vendor_id = item_data.get("vendor_id")
        vendor_sku = item_data.get("vendor_sku")

        if vendor_id and vendor_sku:
            result = db.query(VendorItem).filter(
                VendorItem.vendor_id == vendor_id,
                VendorItem.vendor_sku == vendor_sku,
            ).update({
                VendorItem.last_seen_at: now,
                VendorItem.times_ordered: VendorItem.times_ordered + 1,
            })
            updated_count += result

    db.commit()

    return {"updated_count": updated_count}
