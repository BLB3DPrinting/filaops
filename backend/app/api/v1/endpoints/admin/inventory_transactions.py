"""
Admin Inventory Transaction Endpoints

Provides admin interface for creating and managing inventory transactions:
- Receipts (PO receiving, manual receipts)
- Issues (production consumption, manual issues)
- Transfers (location-to-location)
- Adjustments (cycle counts, corrections)

Business logic lives in ``app.services.inventory_transaction_service``.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.api.v1.deps import get_current_staff_user
from app.services import inventory_transaction_service as svc

router = APIRouter(prefix="/inventory/transactions", tags=["Admin - Inventory"])


# ============================================================================
# SCHEMAS
# ============================================================================

class TransactionCreate(BaseModel):
    """Create inventory transaction request"""
    product_id: int
    location_id: Optional[int] = None
    transaction_type: str  # receipt, issue, transfer, adjustment
    quantity: Decimal
    cost_per_unit: Optional[Decimal] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    lot_number: Optional[str] = None
    serial_number: Optional[str] = None
    notes: Optional[str] = None
    to_location_id: Optional[int] = None


class TransactionResponse(BaseModel):
    """Inventory transaction response"""
    id: int
    product_id: int
    product_sku: str
    product_name: str
    product_unit: Optional[str] = None
    material_type_id: Optional[int] = None
    location_id: Optional[int]
    location_name: Optional[str]
    transaction_type: str
    quantity: Decimal
    unit: Optional[str] = None
    cost_per_unit: Optional[Decimal]
    total_cost: Optional[Decimal]
    reference_type: Optional[str]
    reference_id: Optional[int]
    lot_number: Optional[str]
    serial_number: Optional[str]
    notes: Optional[str]
    created_at: datetime
    created_by: Optional[str]
    to_location_id: Optional[int]
    to_location_name: Optional[str]


# ============================================================================
# BATCH SCHEMAS
# ============================================================================

class BatchItemUpdate(BaseModel):
    """Single item in a batch update"""
    product_id: int
    counted_quantity: Decimal
    reason: str


class BatchUpdateRequest(BaseModel):
    """Batch inventory update request for cycle counting"""
    items: List[BatchItemUpdate]
    location_id: Optional[int] = None
    count_reference: Optional[str] = None


class BatchUpdateResult(BaseModel):
    """Result of a single item update in batch"""
    product_id: int
    product_sku: str
    product_name: str
    previous_quantity: Decimal
    counted_quantity: Decimal
    variance: Decimal
    transaction_id: Optional[int] = None
    journal_entry_id: Optional[int] = None
    success: bool
    error: Optional[str] = None


class BatchUpdateResponse(BaseModel):
    """Batch update response"""
    total_items: int
    successful: int
    failed: int
    results: List[BatchUpdateResult]
    count_reference: Optional[str]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/adjustment-reasons")
async def list_adjustment_reasons(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """List all adjustment reasons for dropdown selection."""
    from app.models.adjustment_reason import AdjustmentReason

    query = db.query(AdjustmentReason)
    if not include_inactive:
        query = query.filter(AdjustmentReason.active.is_(True))
    reasons = query.order_by(AdjustmentReason.sequence).all()

    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "description": r.description,
            "active": r.active,
            "sequence": r.sequence,
        }
        for r in reasons
    ]


@router.get("", response_model=List[TransactionResponse])
async def list_transactions(
    product_id: Optional[int] = Query(None, description="Filter by product"),
    transaction_type: Optional[str] = Query(None, description="Filter by type"),
    location_id: Optional[int] = Query(None, description="Filter by location"),
    reference_type: Optional[str] = Query(None, description="Filter by reference type"),
    reference_id: Optional[int] = Query(None, description="Filter by reference ID"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """List inventory transactions with filters.

    SINGLE SOURCE OF TRUTH: Returns stored total_cost and unit directly.
    See docs/AI_DIRECTIVE_UOM_COSTS.md - UI displays these values with NO client-side math.
    """
    rows = svc.list_transactions(
        db,
        product_id=product_id,
        transaction_type=transaction_type,
        location_id=location_id,
        reference_type=reference_type,
        reference_id=reference_id,
        limit=limit,
        offset=offset,
    )
    return [TransactionResponse(**row) for row in rows]


@router.post("", response_model=TransactionResponse, status_code=201)
async def create_transaction(
    request: TransactionCreate,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Create an inventory transaction."""
    try:
        result = svc.create_transaction(
            db,
            product_id=request.product_id,
            transaction_type=request.transaction_type,
            quantity=request.quantity,
            created_by=current_admin.email,
            location_id=request.location_id,
            cost_per_unit=request.cost_per_unit,
            reference_type=request.reference_type,
            reference_id=request.reference_id,
            lot_number=request.lot_number,
            serial_number=request.serial_number,
            notes=request.notes,
            to_location_id=request.to_location_id,
        )
    except ValueError as e:
        detail = str(e)
        status = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status, detail=detail)

    txn = result["transaction"]
    product = result["product"]
    location = result["location"]
    to_location = result["to_location"]

    return TransactionResponse(
        id=txn.id,
        product_id=txn.product_id,
        product_sku=product.sku,
        product_name=product.name,
        product_unit=product.unit,
        location_id=txn.location_id,
        location_name=location.name,
        transaction_type=result["original_type"],
        quantity=txn.quantity,
        cost_per_unit=txn.cost_per_unit,
        total_cost=result["response_total_cost"],
        reference_type=txn.reference_type,
        reference_id=txn.reference_id,
        lot_number=txn.lot_number,
        serial_number=txn.serial_number,
        notes=txn.notes,
        created_at=txn.created_at,
        created_by=txn.created_by,
        to_location_id=request.to_location_id if request.transaction_type == "transfer" else None,
        to_location_name=to_location.name if to_location else None,
    )


@router.get("/locations")
async def list_locations(
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """List all inventory locations."""
    return svc.list_locations(db)


@router.post("/batch", response_model=BatchUpdateResponse, status_code=200)
async def batch_update_inventory(
    request: BatchUpdateRequest,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Batch update inventory quantities for cycle counting.

    This endpoint accepts a list of items with their counted quantities
    and creates adjustment transactions for each item where the count
    differs from the current on-hand quantity.
    """
    try:
        result = svc.batch_update_inventory(
            db,
            items=[
                {
                    "product_id": item.product_id,
                    "counted_quantity": item.counted_quantity,
                    "reason": item.reason,
                }
                for item in request.items
            ],
            location_id=request.location_id,
            count_reference=request.count_reference,
            admin_id=current_admin.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return BatchUpdateResponse(
        total_items=result["total_items"],
        successful=result["successful"],
        failed=result["failed"],
        results=[BatchUpdateResult(**r) for r in result["results"]],
        count_reference=result["count_reference"],
    )


@router.get("/inventory-summary")
async def get_inventory_summary(
    location_id: Optional[int] = Query(None, description="Filter by location"),
    category_id: Optional[int] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search by SKU or name"),
    show_zero: bool = Query(False, description="Include items with zero quantity"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Get inventory summary for cycle counting."""
    return svc.get_inventory_summary(
        db,
        location_id=location_id,
        category_id=category_id,
        search=search,
        show_zero=show_zero,
        limit=limit,
        offset=offset,
    )
