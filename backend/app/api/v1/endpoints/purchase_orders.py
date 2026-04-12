"""
Purchase Orders API Endpoints

Uses purchase_order_service for business logic (ARCHITECT-003).
"""
from fastapi import APIRouter, Depends, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from typing import Annotated, Optional
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.deps import get_pagination_params
from app.schemas.purchasing import (
    PurchaseOrderCreate,
    PurchaseOrderUpdate,
    PurchaseOrderListResponse,
    PurchaseOrderResponse,
    POLineCreate,
    POLineUpdate,
    POLineResponse,
    POStatusUpdate,
    ReceivePORequest,
    ReceivePOResponse,
)
from app.schemas.common import PaginationParams, ListResponse, PaginationMeta
from app.schemas.purchasing_event import (
    PurchasingEventCreate,
    PurchasingEventResponse,
    PurchasingEventListResponse,
)
from app.services import purchase_order_service

router = APIRouter()
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Response Builders
# ---------------------------------------------------------------------------

def _build_po_list_item(po) -> PurchaseOrderListResponse:
    """Build a list-view response for a PO."""
    return PurchaseOrderListResponse(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        vendor_name=po.vendor.name if po.vendor else "Unknown",
        status=po.status,
        order_date=po.order_date,
        expected_date=po.expected_date,
        received_date=po.received_date,
        total_amount=po.total_amount,
        line_count=len(po.lines),
        created_at=po.created_at,
    )


def _build_po_line_response(line) -> POLineResponse:
    """Build a response for a single PO line."""
    return POLineResponse(
        id=line.id,
        line_number=line.line_number,
        product_id=line.product_id,
        product_sku=line.product.sku if line.product else None,
        product_name=line.product.name if line.product else None,
        product_unit=line.product.unit if line.product else None,
        quantity_ordered=line.quantity_ordered,
        quantity_received=line.quantity_received,
        unit_cost=line.unit_cost,
        purchase_unit=line.purchase_unit,
        line_total=line.line_total,
        notes=line.notes,
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def _build_po_response(po) -> PurchaseOrderResponse:
    """Build a full detail response for a PO."""
    return PurchaseOrderResponse(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        vendor_name=po.vendor.name if po.vendor else None,
        status=po.status,
        order_date=po.order_date,
        expected_date=po.expected_date,
        shipped_date=po.shipped_date,
        received_date=po.received_date,
        tracking_number=po.tracking_number,
        carrier=po.carrier,
        subtotal=po.subtotal,
        tax_amount=po.tax_amount,
        shipping_cost=po.shipping_cost,
        total_amount=po.total_amount,
        payment_method=po.payment_method,
        payment_reference=po.payment_reference,
        document_url=po.document_url,
        notes=po.notes,
        created_by=po.created_by,
        created_at=po.created_at,
        updated_at=po.updated_at,
        lines=[_build_po_line_response(line) for line in po.lines],
    )


def _build_event_response(event) -> PurchasingEventResponse:
    """Build a response for a purchasing event."""
    user_name = None
    if event.user_id and event.user:
        user_name = event.user.full_name

    return PurchasingEventResponse(
        id=event.id,
        purchase_order_id=event.purchase_order_id,
        user_id=event.user_id,
        user_name=user_name,
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        old_value=event.old_value,
        new_value=event.new_value,
        event_date=event.event_date,
        metadata_key=event.metadata_key,
        metadata_value=event.metadata_value,
        created_at=event.created_at,
    )


# ============================================================================
# Purchase Order CRUD
# ============================================================================

@router.get("/", response_model=ListResponse[PurchaseOrderListResponse])
async def list_purchase_orders(
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
    status: Optional[str] = Query(None, description="Filter by status (draft, ordered, shipped, received, closed, cancelled)"),
    vendor_id: Optional[int] = Query(None, description="Filter by vendor ID"),
    search: Optional[str] = Query(None, description="Search by PO number"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List purchase orders with pagination"""
    pos, total = purchase_order_service.list_purchase_orders(
        db,
        status=status,
        vendor_id=vendor_id,
        search=search,
        offset=pagination.offset,
        limit=pagination.limit,
    )

    return ListResponse(
        items=[_build_po_list_item(po) for po in pos],
        pagination=PaginationMeta(
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
            returned=len(pos),
        ),
    )


@router.get("/{po_id}", response_model=PurchaseOrderResponse)
async def get_purchase_order(
    po_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get purchase order details by ID"""
    po = purchase_order_service.get_purchase_order(db, po_id)
    return _build_po_response(po)


@router.post("/", response_model=PurchaseOrderResponse, status_code=201)
async def create_purchase_order(
    request: PurchaseOrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new purchase order"""
    data = {
        "vendor_id": request.vendor_id,
        "order_date": request.order_date,
        "expected_date": request.expected_date,
        "tracking_number": request.tracking_number,
        "carrier": request.carrier,
        "tax_amount": request.tax_amount,
        "shipping_cost": request.shipping_cost,
        "payment_method": request.payment_method,
        "payment_reference": request.payment_reference,
        "document_url": request.document_url,
        "notes": request.notes,
    }
    lines_data = [
        {
            "product_id": line.product_id,
            "quantity_ordered": line.quantity_ordered,
            "unit_cost": line.unit_cost,
            "purchase_unit": line.purchase_unit,
            "notes": line.notes,
        }
        for line in request.lines
    ]

    po = purchase_order_service.create_purchase_order(
        db,
        data=data,
        lines_data=lines_data,
        created_by=current_user.email,
        user_id=current_user.id,
    )

    # Reload with relationships for response
    po = purchase_order_service.get_purchase_order(db, po.id)
    return _build_po_response(po)


@router.put("/{po_id}", response_model=PurchaseOrderResponse)
async def update_purchase_order(
    po_id: int,
    request: PurchaseOrderUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a purchase order"""
    update_data = request.model_dump(exclude_unset=True)
    purchase_order_service.update_purchase_order(db, po_id, data=update_data)

    po = purchase_order_service.get_purchase_order(db, po_id)
    return _build_po_response(po)


@router.post("/{po_id}/lines", response_model=PurchaseOrderResponse)
async def add_po_line(
    po_id: int,
    request: POLineCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a line to a purchase order"""
    line_data = {
        "product_id": request.product_id,
        "quantity_ordered": request.quantity_ordered,
        "unit_cost": request.unit_cost,
        "purchase_unit": request.purchase_unit,
        "notes": request.notes,
    }
    purchase_order_service.add_po_line(db, po_id, data=line_data)

    po = purchase_order_service.get_purchase_order(db, po_id)
    return _build_po_response(po)


@router.put("/{po_id}/lines/{line_id}", response_model=PurchaseOrderResponse)
async def update_po_line(
    po_id: int,
    line_id: int,
    request: POLineUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a line on a purchase order"""
    update_data = {
        "quantity_ordered": request.quantity_ordered,
        "unit_cost": request.unit_cost,
        "notes": request.notes,
    }
    purchase_order_service.update_po_line(db, po_id, line_id, data=update_data)

    po = purchase_order_service.get_purchase_order(db, po_id)
    return _build_po_response(po)


@router.delete("/{po_id}/lines/{line_id}")
async def delete_po_line(
    po_id: int,
    line_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a line from a purchase order"""
    return purchase_order_service.delete_po_line(db, po_id, line_id)


# ============================================================================
# Status Management
# ============================================================================

@router.post("/{po_id}/status", response_model=PurchaseOrderResponse)
async def update_po_status(
    po_id: int,
    request: POStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update PO status with transition validation"""
    purchase_order_service.update_po_status(
        db,
        po_id,
        new_status=request.status.value,
        tracking_number=request.tracking_number,
        carrier=request.carrier,
        user_id=current_user.id,
    )

    po = purchase_order_service.get_purchase_order(db, po_id)
    return _build_po_response(po)


# ============================================================================
# Receiving
# ============================================================================

@router.post("/{po_id}/receive", response_model=ReceivePOResponse)
async def receive_purchase_order(
    po_id: int,
    request: ReceivePORequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Receive items from a purchase order"""
    lines_data = []
    for item in request.lines:
        line_dict = {
            "line_id": item.line_id,
            "quantity_received": item.quantity_received,
            "lot_number": item.lot_number,
            "vendor_lot_number": getattr(item, "vendor_lot_number", None),
            "create_spools": item.create_spools if hasattr(item, "create_spools") else False,
        }
        if hasattr(item, "spools") and item.spools:
            line_dict["spools"] = [
                {
                    "weight_g": s.weight_g,
                    "spool_number": getattr(s, "spool_number", None),
                    "supplier_lot_number": getattr(s, "supplier_lot_number", None),
                    "expiry_date": getattr(s, "expiry_date", None),
                    "notes": getattr(s, "notes", None),
                }
                for s in item.spools
            ]

        lines_data.append(line_dict)

    result = purchase_order_service.receive_purchase_order(
        db,
        po_id,
        lines=lines_data,
        location_id=request.location_id,
        received_date=request.received_date,
        user_id=current_user.id,
        user_email=current_user.email,
    )

    return ReceivePOResponse(
        po_number=result["po_number"],
        lines_received=result["lines_received"],
        total_quantity=result["total_quantity"],
        inventory_updated=result["inventory_updated"],
        transactions_created=result["transactions_created"],
        spools_created=result["spools_created"],
        material_lots_created=result["material_lots_created"],
    )


# ============================================================================
# File Upload
# ============================================================================

@router.post("/{po_id}/upload")
async def upload_po_document(
    po_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a document for a purchase order (invoice, receipt, etc.)"""
    file_content = await file.read()

    return purchase_order_service.upload_po_document(
        db,
        po_id,
        file_content=file_content,
        filename=file.filename or "document",
        content_type=file.content_type or "application/octet-stream",
    )


# ============================================================================
# Delete
# ============================================================================

@router.delete("/{po_id}")
async def delete_purchase_order(
    po_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a purchase order (draft only)"""
    return purchase_order_service.delete_purchase_order(db, po_id)


# ============================================================================
# Event Timeline
# ============================================================================

@router.get("/{po_id}/events", response_model=PurchasingEventListResponse)
async def list_po_events(
    po_id: int,
    limit: int = Query(default=50, ge=1, le=200, description="Max events to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List activity events for a purchase order"""
    events, total = purchase_order_service.list_po_events(
        db, po_id, limit=limit, offset=offset,
    )

    return PurchasingEventListResponse(
        items=[_build_event_response(event) for event in events],
        total=total,
    )


@router.post("/{po_id}/events", response_model=PurchasingEventResponse, status_code=201)
async def add_po_event(
    po_id: int,
    request: PurchasingEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a manual event to a purchase order (typically a note)"""
    event = purchase_order_service.add_po_event(
        db,
        po_id,
        event_type=request.event_type.value,
        title=request.title,
        description=request.description,
        old_value=request.old_value,
        new_value=request.new_value,
        event_date=request.event_date,
        metadata_key=request.metadata_key,
        metadata_value=request.metadata_value,
        user_id=current_user.id,
    )

    return _build_event_response(event)


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------

@router.get("/{po_id}/pdf")
async def download_po_pdf(
    po_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate and download a PDF for a purchase order."""
    po = purchase_order_service.get_purchase_order(db, po_id)
    pdf_buffer = purchase_order_service.generate_po_pdf(db, po_id, po=po)

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{po.po_number}.pdf"'
        },
    )
