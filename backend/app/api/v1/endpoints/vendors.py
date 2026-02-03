"""
Vendors API Endpoints

Uses vendor_service for business logic (ARCHITECT-003).
"""
from fastapi import APIRouter, Depends
from typing import Annotated, Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.deps import get_pagination_params
from app.models.user import User
from app.schemas.purchasing import (
    VendorCreate,
    VendorUpdate,
    VendorListResponse,
    VendorResponse,
)
from app.schemas.common import PaginationParams, ListResponse, PaginationMeta
from app.services import vendor_service

router = APIRouter()


# ============================================================================
# Vendor CRUD
# ============================================================================

@router.get("/", response_model=ListResponse[VendorListResponse])
async def list_vendors(
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
    search: Optional[str] = None,
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all vendors with pagination

    - **search**: Search by name, code, or contact
    - **active_only**: Only show active vendors
    - **offset**: Number of records to skip (default: 0)
    - **limit**: Maximum records to return (default: 50, max: 500)
    """
    vendors, total, po_counts = vendor_service.list_vendors(
        db,
        search=search,
        active_only=active_only,
        offset=pagination.offset,
        limit=pagination.limit,
    )

    result = [
        VendorListResponse(
            id=v.id,
            code=v.code,
            name=v.name,
            contact_name=v.contact_name,
            email=v.email,
            phone=v.phone,
            city=v.city,
            state=v.state,
            payment_terms=v.payment_terms,
            is_active=v.is_active,
            po_count=po_counts.get(v.id, 0),
        )
        for v in vendors
    ]

    return ListResponse(
        items=result,
        pagination=PaginationMeta(
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
            returned=len(result),
        ),
    )


@router.get("/{vendor_id}", response_model=VendorResponse)
async def get_vendor(
    vendor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get vendor details by ID"""
    return vendor_service.get_vendor(db, vendor_id)


@router.post("/", response_model=VendorResponse, status_code=201)
async def create_vendor(
    request: VendorCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new vendor"""
    return vendor_service.create_vendor(db, data=request.model_dump())


@router.put("/{vendor_id}", response_model=VendorResponse)
async def update_vendor(
    vendor_id: int,
    request: VendorUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a vendor"""
    return vendor_service.update_vendor(
        db, vendor_id, data=request.model_dump(exclude_unset=True)
    )


@router.get("/{vendor_id}/metrics")
async def get_vendor_metrics(
    vendor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get vendor performance metrics

    Returns:
    - Total PO count
    - Total spend
    - Average lead time (days from ordered to received)
    - On-time delivery percentage
    - Recent POs
    """
    return vendor_service.get_vendor_metrics(db, vendor_id)


@router.delete("/{vendor_id}")
async def delete_vendor(
    vendor_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a vendor (soft delete - marks as inactive)

    Will fail if vendor has associated purchase orders
    """
    return vendor_service.delete_vendor(db, vendor_id)
