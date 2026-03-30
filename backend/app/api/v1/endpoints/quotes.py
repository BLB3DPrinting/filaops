"""
Quote Management Endpoints - Community Edition

Manual quote creation and management for small businesses.
Supports creating quotes, updating status, and converting to sales orders.
"""
from datetime import datetime
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, status, Query, UploadFile, File
from fastapi.responses import StreamingResponse, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.logging_config import get_logger
from app.api.v1.endpoints.auth import get_current_user
from app.services import quote_service
from pydantic import BaseModel, Field

logger = get_logger(__name__)

router = APIRouter(prefix="/quotes", tags=["Quotes"])


# ============================================================================
# SCHEMAS (Community Edition - Manual Quotes)
# ============================================================================

class QuoteLineCreate(BaseModel):
    """Schema for a line item when creating/updating a multi-line quote"""
    product_id: Optional[int] = Field(None, description="Link to product")
    product_name: str = Field(..., max_length=255, description="Product/item name")
    quantity: int = Field(1, ge=1, le=10000, description="Quantity")
    unit_price: Decimal = Field(..., ge=0, description="Price per unit")
    material_type: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=1000)


class QuoteLineResponse(BaseModel):
    """Response schema for a quote line item"""
    id: int
    line_number: int
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    quantity: int
    unit_price: Decimal
    discount_percent: Optional[Decimal] = None
    total: Decimal
    material_type: Optional[str] = None
    color: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class ManualQuoteCreate(BaseModel):
    """Schema for creating a manual quote"""
    product_id: Optional[int] = Field(None, description="Link to product with BOM")
    product_name: Optional[str] = Field(None, max_length=255, description="Product/item name (required if no lines)")
    description: Optional[str] = Field(None, max_length=1000, description="Product description")
    quantity: Optional[int] = Field(None, ge=1, le=10000, description="Quantity (required if no lines)")
    unit_price: Optional[Decimal] = Field(None, ge=0, description="Price per unit (required if no lines)")

    # Multi-line items (if provided, header product fields are ignored)
    lines: Optional[List[QuoteLineCreate]] = Field(None, description="Line items for multi-product quotes")

    # Customer info
    customer_id: Optional[int] = Field(None, description="Link to customer record (users table)")
    customer_name: Optional[str] = Field(None, max_length=200)
    customer_email: Optional[str] = Field(None, max_length=255)

    # Optional details
    material_type: Optional[str] = Field("PLA", max_length=50)
    color: Optional[str] = Field(None, max_length=50)

    # Tax (if not provided, will use company settings default)
    apply_tax: Optional[bool] = Field(None, description="Whether to apply tax (uses company settings if None)")
    tax_rate_id: Optional[int] = Field(None, description="Specific TaxRate id to apply (overrides apply_tax lookup)")

    # Shipping
    shipping_cost: Optional[Decimal] = Field(None, ge=0, description="Shipping cost")

    # Notes
    customer_notes: Optional[str] = Field(None, max_length=1000)
    admin_notes: Optional[str] = Field(None, max_length=1000)

    # Validity
    valid_days: int = Field(30, ge=1, le=365, description="Days until quote expires")


class ManualQuoteUpdate(BaseModel):
    """Schema for updating a quote"""
    product_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    quantity: Optional[int] = Field(None, ge=1, le=10000)
    unit_price: Optional[Decimal] = Field(None, ge=0)

    # Multi-line items (replaces all existing lines when provided)
    lines: Optional[List[QuoteLineCreate]] = Field(None, description="Updated line items (replaces existing)")

    customer_id: Optional[int] = Field(None, description="Link to customer record")
    customer_name: Optional[str] = Field(None, max_length=200)
    customer_email: Optional[str] = Field(None, max_length=255)

    material_type: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=50)

    # Tax
    apply_tax: Optional[bool] = Field(None, description="Whether to apply tax")

    # Shipping cost
    shipping_cost: Optional[Decimal] = Field(None, ge=0, description="Shipping cost")

    customer_notes: Optional[str] = Field(None, max_length=1000)
    admin_notes: Optional[str] = Field(None, max_length=1000)

    # Shipping address
    shipping_name: Optional[str] = Field(None, max_length=200)
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=50)
    shipping_zip: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field(None, max_length=100)
    shipping_phone: Optional[str] = Field(None, max_length=30)


class QuoteStatusUpdate(BaseModel):
    """Schema for updating quote status"""
    status: str = Field(..., description="New status: pending, approved, rejected, accepted, cancelled")
    rejection_reason: Optional[str] = Field(None, max_length=500)
    admin_notes: Optional[str] = Field(None, max_length=1000)


class QuoteListItem(BaseModel):
    """Quote list item response"""
    id: int
    quote_number: str
    product_id: Optional[int] = None
    product_name: Optional[str]
    quantity: int
    unit_price: Optional[Decimal]
    subtotal: Optional[Decimal]
    tax_rate: Optional[Decimal]
    tax_amount: Optional[Decimal]
    shipping_cost: Optional[Decimal] = None
    total_price: Decimal
    discount_percent: Optional[Decimal] = None
    status: str
    customer_id: Optional[int]
    customer_name: Optional[str]
    customer_email: Optional[str]
    material_type: Optional[str]
    color: Optional[str]
    has_image: bool = False
    line_count: int = 0
    created_at: datetime
    expires_at: datetime
    sales_order_id: Optional[int]

    model_config = {"from_attributes": True}


class QuoteDetail(QuoteListItem):
    """Full quote detail response"""
    description: Optional[str] = None  # May not exist on legacy quotes
    customer_notes: Optional[str]
    admin_notes: Optional[str]
    rejection_reason: Optional[str]

    # Line items (empty for legacy single-item quotes)
    lines: List[QuoteLineResponse] = []

    # Shipping
    shipping_name: Optional[str]
    shipping_address_line1: Optional[str]
    shipping_address_line2: Optional[str]
    shipping_city: Optional[str]
    shipping_state: Optional[str]
    shipping_zip: Optional[str]
    shipping_country: Optional[str]
    shipping_phone: Optional[str]

    updated_at: datetime
    approved_at: Optional[datetime]
    converted_at: Optional[datetime]


class QuoteStatsResponse(BaseModel):
    """Quote statistics for dashboard"""
    total: int
    pending: int
    approved: int
    accepted: int
    rejected: int
    converted: int
    expired: int
    total_value: Decimal
    pending_value: Decimal


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/", response_model=List[QuoteListItem])
async def list_quotes(
    status: Optional[str] = Query(None, description="Filter by status"),
    search: Optional[str] = Query(None, description="Search by quote number, product name, or customer"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all quotes with optional filtering"""
    return quote_service.list_quotes(db, status_filter=status, search=search, skip=skip, limit=limit)


@router.get("/stats", response_model=QuoteStatsResponse)
async def get_quote_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get quote statistics for dashboard"""
    return quote_service.get_quote_stats(db)


@router.get("/{quote_id}", response_model=QuoteDetail)
async def get_quote(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get quote details"""
    return quote_service.get_quote_detail(db, quote_id)


@router.post("/", response_model=QuoteDetail, status_code=status.HTTP_201_CREATED)
async def create_quote(
    request: ManualQuoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new manual quote"""
    quote = quote_service.create_quote(db, request, current_user.id)
    logger.info(f"Quote {quote.quote_number} created by user {current_user.email}")
    return quote


@router.patch("/{quote_id}", response_model=QuoteDetail)
async def update_quote(
    quote_id: int,
    request: ManualQuoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update quote details"""
    quote = quote_service.update_quote(db, quote_id, request)
    logger.info(f"Quote {quote.quote_number} updated by user {current_user.email}")
    return quote


@router.patch("/{quote_id}/status", response_model=QuoteDetail)
async def update_quote_status(
    quote_id: int,
    request: QuoteStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update quote status (approve, reject, cancel, accept)"""
    quote = quote_service.update_quote_status(db, quote_id, request, current_user.id)
    logger.info(f"Quote {quote.quote_number} status updated by {current_user.email}")
    return quote


@router.post("/{quote_id}/convert", status_code=status.HTTP_201_CREATED)
async def convert_quote_to_order(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Convert an accepted/approved quote to a sales order"""
    result = quote_service.convert_quote_to_order(db, quote_id)
    logger.info(f"Quote {quote_id} converted to order {result['order_number']} by {current_user.email}")
    return result


@router.delete("/{quote_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quote(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a quote (only if not converted)"""
    quote_number = quote_service.delete_quote(db, quote_id)
    logger.info(f"Quote {quote_number} deleted by {current_user.email}")


# ============================================================================
# QUOTE IMAGE ENDPOINTS
# ============================================================================

@router.post("/{quote_id}/image")
async def upload_quote_image(
    quote_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload an image for a quote (product photo/render)"""
    content = await file.read()
    result = quote_service.upload_quote_image(db, quote_id, content, file.filename, file.content_type)
    logger.info(f"Image uploaded for quote {quote_id} by {current_user.email}")
    return result


@router.get("/{quote_id}/image")
async def get_quote_image(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the image for a quote"""
    image_data = quote_service.get_quote_image(db, quote_id)
    return Response(
        content=image_data["image_data"],
        media_type=image_data["mime_type"],
        headers={
            "Content-Disposition": f'inline; filename="{image_data["filename"]}"'
        }
    )


@router.delete("/{quote_id}/image")
async def delete_quote_image(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete the image for a quote"""
    quote_service.delete_quote_image(db, quote_id)
    logger.info(f"Image deleted for quote {quote_id} by {current_user.email}")
    return {"message": "Image deleted"}


# ============================================================================
# PDF GENERATION
# ============================================================================

@router.get("/{quote_id}/pdf")
async def generate_quote_pdf(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a PDF for a quote using ReportLab with company logo, image, and tax"""
    pdf_buffer = quote_service.generate_quote_pdf(db, quote_id)

    # Get quote number for filename
    quote = quote_service.get_quote_detail(db, quote_id)

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{quote.quote_number}.pdf"'
        }
    )
