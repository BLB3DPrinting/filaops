"""
Quote Management Endpoints - Community Edition

Manual quote creation and management for small businesses.
Supports creating quotes, updating status, and converting to sales orders.
"""
import json
from datetime import datetime, timezone, timedelta
from inspect import isawaitable
from typing import Any, List, Optional
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, status, Query, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.config import settings
from app.models.product import Product
from app.models.quote import Quote, QuoteFile, QuoteMaterial
from app.models.user import User
from app.logging_config import get_logger
from app.api.v1.endpoints.auth import get_current_user
from app.services import quote_service
from app.services import bom_service
from app.services.file_storage import file_storage
from pydantic import BaseModel, Field, field_validator

logger = get_logger(__name__)

router = APIRouter(prefix="/quotes", tags=["Quotes"])
PORTAL_SNAPSHOT_MAX_BYTES = 32 * 1024


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
    # Optional defensively: legacy rows may have NULL until migration 083 backfills.
    # Migration 083 + model server_default + PRO route fix all ensure new rows are populated.
    expires_at: Optional[datetime] = None
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


class PortalQuoteResponse(BaseModel):
    """Customer-facing quote response for the public quoter."""
    id: int
    quote_id: int
    quote_number: str
    status: str
    requires_review: bool = False
    requires_review_reason: Optional[str] = None
    unit_price: Optional[Decimal] = None
    total_price: Decimal
    material_grams: Optional[Decimal] = None
    print_time_hours: Optional[Decimal] = None
    print_time_minutes: Optional[int] = None
    expires_at: datetime
    estimation_method: Optional[str] = None
    multi_material: Optional[dict[str, Any]] = None
    slot_requirements: list[dict[str, Any]] = []
    breakdown: dict[str, Any] = {}


class PortalShippingSelection(BaseModel):
    """Shipping/payment snapshot submitted by the public quote portal."""
    shipping_name: Optional[str] = Field(None, max_length=200)
    shipping_address_line1: str = Field(..., max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: str = Field(..., max_length=100)
    shipping_state: str = Field(..., max_length=50)
    shipping_zip: str = Field(..., max_length=20)
    shipping_country: Optional[str] = Field("US", max_length=100)
    shipping_phone: Optional[str] = Field(None, max_length=30)
    shipping_rate_id: Optional[str] = Field(None, max_length=100)
    shipping_carrier: Optional[str] = Field(None, max_length=50)
    shipping_service: Optional[str] = Field(None, max_length=100)
    shipping_cost: Optional[Decimal] = Field(None, ge=0)
    print_mode: Optional[str] = Field(None, max_length=20)
    adjusted_unit_price: Optional[Decimal] = Field(None, ge=0)
    multi_color_info: Optional[dict[str, Any]] = None
    pricing_snapshot: Optional[dict[str, Any]] = None
    component_snapshot: Optional[dict[str, Any]] = None
    packaging_snapshot: Optional[dict[str, Any]] = None
    shipping_snapshot: Optional[dict[str, Any]] = None
    artifact_snapshot: Optional[dict[str, Any]] = None
    slicer_diagnostics: Optional[dict[str, Any]] = None

    @field_validator(
        "pricing_snapshot",
        "component_snapshot",
        "packaging_snapshot",
        "shipping_snapshot",
        "artifact_snapshot",
        "slicer_diagnostics",
    )
    @classmethod
    def _limit_snapshot_size(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return value
        try:
            encoded = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Snapshot payload must be JSON serializable") from exc

        if len(encoded.encode("utf-8")) > PORTAL_SNAPSHOT_MAX_BYTES:
            raise ValueError("Snapshot payload must be 32KB or smaller")
        return value


class QuoteArchiveFile(BaseModel):
    """Read-only file metadata retained by Core after PRO downgrade."""
    id: int
    original_filename: str
    file_format: str
    file_size_bytes: int
    file_hash: str
    uploaded_at: datetime
    processed: bool = False
    processing_error: Optional[str] = None

    model_config = {"from_attributes": True}


class QuoteArchiveMaterial(BaseModel):
    """Read-only material snapshot retained by Core after PRO downgrade."""
    slot_number: int
    is_primary: bool
    material_type: str
    color_code: Optional[str] = None
    color_name: Optional[str] = None
    color_hex: Optional[str] = None
    material_grams: Decimal

    model_config = {"from_attributes": True}


class QuoteArchiveResponse(BaseModel):
    """Durable quote archive shape that does not require PRO tables."""
    quote: QuoteDetail
    files: list[QuoteArchiveFile] = Field(default_factory=list)
    materials: list[QuoteArchiveMaterial] = Field(default_factory=list)
    read_only: bool = True
    pro_actions_available: bool = False


class QuoteItemCreateResponse(BaseModel):
    """Response for staff-created Core item/product from a quote."""
    quote_id: int
    product_id: int
    product_sku: str
    product_name: str
    bom_id: Optional[int] = None
    already_created: bool = False


def _public_quoter_enabled() -> bool:
    return bool(getattr(settings, "ENABLE_PUBLIC_QUOTER", False))


def _require_public_quoter_enabled() -> None:
    if not _public_quoter_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public online quoter is disabled",
        )


def _is_staff_or_admin(current_user: User) -> bool:
    return bool(
        getattr(current_user, "is_admin", False)
        or getattr(current_user, "is_staff", False)
        or getattr(current_user, "account_type", None) in {"admin", "operator"}
    )


def _require_staff_or_admin(current_user: User) -> None:
    if not _is_staff_or_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or staff role required",
        )


def _customer_display_name(user: User) -> str:
    """Return a stable customer display name without inventing a new customer table."""
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name or user.company_name or user.email


def _portal_quote_or_404(db: Session, quote_id: int, current_user: User) -> Quote:
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    if quote.user_id != current_user.id and quote.customer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Quote does not belong to current customer")

    return quote


def _authorize_quote_archive_access(quote: Quote, current_user: User) -> None:
    if _is_staff_or_admin(current_user):
        return
    if quote.user_id == current_user.id or quote.customer_id == current_user.id:
        return
    raise HTTPException(status_code=403, detail="Quote does not belong to current customer")


def _portal_quote_payload(quote: Quote, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    extra = extra or {}
    print_time_hours = Decimal(str(quote.print_time_hours)) if quote.print_time_hours is not None else None
    return {
        "id": quote.id,
        "quote_id": quote.id,
        "quote_number": quote.quote_number,
        "status": quote.status,
        "requires_review": bool(quote.requires_review_reason),
        "requires_review_reason": quote.requires_review_reason,
        "unit_price": quote.unit_price,
        "total_price": quote.total_price,
        "material_grams": quote.material_grams,
        "print_time_hours": quote.print_time_hours,
        "print_time_minutes": int(float(print_time_hours) * 60) if print_time_hours is not None else None,
        "expires_at": quote.expires_at,
        "estimation_method": extra.get("estimation_method"),
        "multi_material": extra.get("multi_material"),
        "slot_requirements": extra.get("slot_requirements") or [],
        "breakdown": extra.get("breakdown") or {},
    }


def _safe_log_value(value: Any, max_length: int = 160) -> str:
    safe = repr(str(value or ""))[1:-1]
    return safe[:max_length]


def _normalize_portal_component_addon_ids(values: Optional[List[str]]) -> List[str]:
    """Normalize optional public add-on ids without interpreting private costs."""
    if values is None:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        for item in str(raw_value or "").split(","):
            addon_id = item.strip()
            if addon_id and addon_id not in seen:
                seen.add(addon_id)
                normalized.append(addon_id)
    return normalized


def _set_portal_quote_manual_review(quote: Quote, reason: str) -> None:
    quote.status = "pending"
    quote.approval_method = "manual"
    quote.auto_approved = False
    quote.auto_approve_eligible = False
    quote.unit_price = Decimal("0.00")
    quote.subtotal = Decimal("0.00")
    quote.total_price = Decimal("0.00")
    quote.material_grams = None
    quote.print_time_hours = None
    quote.requires_review_reason = reason


class _InvalidQuoteAutomationResult(Exception):
    """Raised when a PRO provider returns a payload Core cannot safely consume."""


async def _maybe_enrich_portal_quote(
    request: Request,
    *,
    db: Session,
    quote: Quote,
    stored_file: dict[str, Any],
    options: dict[str, Any],
) -> dict[str, Any]:
    """Let PRO enrich a Core-owned quote when PRO is installed and active."""
    provider = getattr(request.app.state, "quote_automation_provider", None)
    if provider is None:
        _set_portal_quote_manual_review(quote, "Automatic quote engine unavailable")
        return {}

    try:
        with db.begin_nested():
            result = provider(db=db, quote=quote, stored_file=stored_file, options=options)
            if isawaitable(result):
                result = await result
            if result is not None and not isinstance(result, dict):
                raise _InvalidQuoteAutomationResult
        return result or {}
    except _InvalidQuoteAutomationResult:
        _set_portal_quote_manual_review(quote, "Automatic quote engine unavailable")
        provider_name = getattr(provider, "__name__", type(provider).__name__)
        logger.warning(
            "Portal quote automation returned invalid payload from %r",
            _safe_log_value(provider_name),
        )
        return {}
    except HTTPException as exc:
        if exc.status_code >= 500:
            reason = "Automatic quote engine unavailable"
        else:
            reason = "Uploaded file requires manual review"
        _set_portal_quote_manual_review(quote, reason)
        logger.warning(
            "Portal quote automation failed for %r (%s)",
            _safe_log_value(stored_file.get("original_filename")),
            exc.status_code,
        )
        return {}
    except Exception:
        _set_portal_quote_manual_review(quote, "Automatic quote engine unavailable")
        logger.exception(
            "Portal quote automation crashed for %r",
            _safe_log_value(stored_file.get("original_filename")),
        )
        return {}


def _apply_portal_shipping(quote: Quote, current_user: User, payload: PortalShippingSelection) -> None:
    quote.shipping_name = payload.shipping_name or _customer_display_name(current_user)
    quote.shipping_address_line1 = payload.shipping_address_line1
    quote.shipping_address_line2 = payload.shipping_address_line2
    quote.shipping_city = payload.shipping_city
    quote.shipping_state = payload.shipping_state
    quote.shipping_zip = payload.shipping_zip
    quote.shipping_country = payload.shipping_country or "US"
    quote.shipping_phone = payload.shipping_phone
    quote.shipping_rate_id = payload.shipping_rate_id
    quote.shipping_carrier = payload.shipping_carrier
    quote.shipping_service = payload.shipping_service
    quote.shipping_cost = payload.shipping_cost
    if payload.adjusted_unit_price is not None:
        quote.unit_price = payload.adjusted_unit_price
        quote.subtotal = payload.adjusted_unit_price * quote.quantity
        quote.total_price = quote.subtotal + (quote.shipping_cost or Decimal("0"))
    elif quote.shipping_cost is not None:
        quote.total_price = (quote.subtotal or quote.total_price) + quote.shipping_cost

    current_user.shipping_address_line1 = payload.shipping_address_line1
    current_user.shipping_address_line2 = payload.shipping_address_line2
    current_user.shipping_city = payload.shipping_city
    current_user.shipping_state = payload.shipping_state
    current_user.shipping_zip = payload.shipping_zip
    current_user.shipping_country = payload.shipping_country or "US"
    if payload.shipping_phone:
        current_user.phone = payload.shipping_phone


def _fallback_shipping_snapshot(
    quote: Quote,
    payload: PortalShippingSelection,
) -> Optional[dict[str, Any]]:
    if not any([
        payload.shipping_rate_id,
        payload.shipping_carrier,
        payload.shipping_service,
        payload.shipping_cost is not None,
    ]):
        return None

    return {
        "source": "portal_accept",
        "rate_id": quote.shipping_rate_id,
        "carrier": quote.shipping_carrier,
        "service": quote.shipping_service,
        "cost": str(quote.shipping_cost) if quote.shipping_cost is not None else None,
        "ship_to": {
            "name": quote.shipping_name,
            "address_line1": quote.shipping_address_line1,
            "address_line2": quote.shipping_address_line2,
            "city": quote.shipping_city,
            "state": quote.shipping_state,
            "zip": quote.shipping_zip,
            "country": quote.shipping_country,
            "phone": quote.shipping_phone,
        },
    }


def _apply_portal_snapshots(quote: Quote, payload: PortalShippingSelection) -> None:
    if payload.pricing_snapshot is not None:
        quote.pricing_snapshot = payload.pricing_snapshot
    if payload.component_snapshot is not None:
        quote.component_snapshot = payload.component_snapshot
    if payload.packaging_snapshot is not None:
        quote.packaging_snapshot = payload.packaging_snapshot
    shipping_snapshot = payload.shipping_snapshot or _fallback_shipping_snapshot(quote, payload)
    if shipping_snapshot is not None:
        quote.shipping_snapshot = shipping_snapshot
    if payload.artifact_snapshot is not None:
        quote.artifact_snapshot = payload.artifact_snapshot
    if payload.slicer_diagnostics is not None:
        quote.slicer_diagnostics = payload.slicer_diagnostics


def _apply_portal_print_selection(
    db: Session,
    quote: Quote,
    payload: PortalShippingSelection,
) -> None:
    """Persist customer print-mode choices captured before checkout."""
    if payload.print_mode != "multi" or not payload.multi_color_info:
        return

    slot_colors = payload.multi_color_info.get("slot_colors") or []
    if not isinstance(slot_colors, list) or not slot_colors:
        return

    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    primary_slot = _coerce_int(payload.multi_color_info.get("primary_slot"))
    parsed_slots: list[dict[str, Any]] = []
    for slot in slot_colors:
        if not isinstance(slot, dict):
            continue

        try:
            slot_number = _coerce_int(slot.get("slot"))
            grams = Decimal(str(slot.get("weight_grams") or 0))
        except (TypeError, ValueError, InvalidOperation):
            continue

        if slot_number is None or slot_number < 1 or slot_number > 16 or grams < 0:
            continue

        color_code = str(slot.get("color_code") or "").strip()
        if not color_code:
            continue

        parsed_slots.append({
            "slot_number": slot_number,
            "is_primary": _coerce_bool(slot.get("is_primary")) or slot_number == primary_slot,
            "material_type": quote.material_type or "PLA_BASIC",
            "color_code": color_code,
            "color_name": slot.get("color_name"),
            "color_hex": slot.get("color_hex"),
            "material_grams": grams,
        })

    if not parsed_slots:
        return

    db.query(QuoteMaterial).filter(QuoteMaterial.quote_id == quote.id).delete(
        synchronize_session=False
    )

    quote.color = "MULTI_COLOR"
    for slot in parsed_slots:
        db.add(QuoteMaterial(
            quote_id=quote.id,
            **slot,
        ))


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



@router.post("/portal", response_model=PortalQuoteResponse, status_code=status.HTTP_201_CREATED)
async def create_portal_quote(
    request: Request,
    file: UploadFile = File(...),
    material: str = Form("PLA_BASIC"),
    color: Optional[str] = Form(None),
    quality: str = Form("standard"),
    infill: str = Form("20%"),
    quantity: int = Form(1, ge=1, le=10000),
    component_addon_ids: Optional[List[str]] = Form(None),
    customer_notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create one Core-owned quote for the public portal and optionally let PRO price it."""
    _require_public_quoter_enabled()
    try:
        stored_file = await file_storage.save_file(file, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    quote = Quote(
        user_id=current_user.id,
        quote_number=quote_service.generate_quote_number(db),
        product_name=stored_file["original_filename"],
        quantity=quantity,
        material_type=material,
        color=color,
        finish=quality,
        unit_price=Decimal("0.00"),
        subtotal=Decimal("0.00"),
        total_price=Decimal("0.00"),
        status="calculating",
        approval_method="auto",
        file_format=stored_file["file_format"],
        file_size_bytes=stored_file["file_size_bytes"],
        customer_id=current_user.id,
        customer_email=current_user.email,
        customer_name=_customer_display_name(current_user),
        customer_notes=customer_notes,
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=90),
    )
    db.add(quote)
    db.flush()

    db.add(QuoteFile(
        quote_id=quote.id,
        original_filename=stored_file["original_filename"],
        stored_filename=stored_file["stored_filename"],
        file_path=stored_file["file_path"],
        file_size_bytes=stored_file["file_size_bytes"],
        file_format=stored_file["file_format"],
        mime_type=stored_file["mime_type"],
        file_hash=stored_file["file_hash"],
    ))

    automation_options: dict[str, Any] = {
        "material_id": material,
        "color": color,
        "quality": quality,
        "infill": infill,
        "quantity": quantity,
        "customer_notes": customer_notes,
    }
    if component_addon_ids is not None:
        automation_options["component_addon_ids"] = (
            _normalize_portal_component_addon_ids(component_addon_ids)
        )

    extra = await _maybe_enrich_portal_quote(
        request,
        db=db,
        quote=quote,
        stored_file=stored_file,
        options=automation_options,
    )
    if customer_notes and not quote.requires_review_reason:
        quote.requires_review_reason = "Customer notes require manual review"
        quote.status = "pending"
        quote.approval_method = "manual"

    db.commit()
    db.refresh(quote)
    logger.info(f"Portal quote {quote.quote_number} created by {current_user.email}")
    return _portal_quote_payload(quote, extra)


@router.post("/portal/{quote_id}/accept")
async def accept_portal_quote(
    quote_id: int,
    payload: PortalShippingSelection,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Snapshot checkout selections and keep portal quotes approved until payment succeeds."""
    _require_public_quoter_enabled()
    quote = _portal_quote_or_404(db, quote_id, current_user)
    _apply_portal_shipping(quote, current_user, payload)
    _apply_portal_snapshots(quote, payload)
    _apply_portal_print_selection(db, quote, payload)

    requires_review = bool(quote.requires_review_reason)
    if requires_review:
        quote.status = "pending"
        quote.approval_method = "manual"
    else:
        quote.status = "approved"
        quote.approval_method = quote.approval_method or "auto"
        quote.approved_at = quote.approved_at or datetime.now(timezone.utc).replace(tzinfo=None)

    db.commit()
    db.refresh(quote)
    return {
        **_portal_quote_payload(quote),
        "requires_review": requires_review,
        "message": "Quote requires manual review" if requires_review else "Quote ready for checkout",
    }


@router.post("/portal/{quote_id}/checkout")
async def create_portal_quote_checkout(
    request: Request,
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a payment checkout session through an optional payment provider."""
    _require_public_quoter_enabled()
    quote = _portal_quote_or_404(db, quote_id, current_user)
    provider = getattr(request.app.state, "payment_checkout_provider", None)
    if provider is None:
        raise HTTPException(status_code=503, detail="Payment checkout provider is not configured")

    result = provider(db=db, quote=quote, current_user=current_user)
    if isawaitable(result):
        result = await result
    return result


@router.get("/{quote_id}/archive", response_model=QuoteArchiveResponse)
async def get_quote_archive(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Read-only Core archive for online quote data after PRO downgrade."""
    quote = quote_service.get_quote_detail(db, quote_id)
    _authorize_quote_archive_access(quote, current_user)
    files = (
        db.query(QuoteFile)
        .filter(QuoteFile.quote_id == quote_id)
        .order_by(QuoteFile.id)
        .all()
    )
    materials = (
        db.query(QuoteMaterial)
        .filter(QuoteMaterial.quote_id == quote_id)
        .order_by(QuoteMaterial.slot_number)
        .all()
    )
    return {
        "quote": quote,
        "files": files,
        "materials": materials,
        "read_only": True,
        "pro_actions_available": _public_quoter_enabled(),
    }


@router.post("/{quote_id}/create-item", response_model=QuoteItemCreateResponse)
async def create_item_from_quote(
    quote_id: int,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Staff action: create a Core item/product from an approved quote."""
    _require_staff_or_admin(current_user)
    quote = quote_service.get_quote_detail(db, quote_id)
    if quote.product_id:
        product = db.get(Product, quote.product_id)
        if not product:
            raise HTTPException(status_code=409, detail="Quote links to a missing product")
        bom = product.boms[0] if product.boms else None
        response.status_code = status.HTTP_200_OK
        return {
            "quote_id": quote.id,
            "product_id": product.id,
            "product_sku": product.sku,
            "product_name": product.name,
            "bom_id": bom.id if bom else None,
            "already_created": True,
        }

    if quote.status not in {"approved", "accepted", "converted"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quote must be approved, accepted, or converted before creating an item",
        )

    try:
        product, bom = bom_service.auto_create_product_and_bom(quote, db)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    response.status_code = status.HTTP_201_CREATED
    return {
        "quote_id": quote.id,
        "product_id": product.id,
        "product_sku": product.sku,
        "product_name": product.name,
        "bom_id": bom.id,
        "already_created": False,
    }


@router.get("/{quote_id}/files/{file_id}/download")
async def download_quote_file(
    quote_id: int,
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download a retained quote upload for authorized customers or staff."""
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    _authorize_quote_archive_access(quote, current_user)

    quote_file = (
        db.query(QuoteFile)
        .filter(QuoteFile.id == file_id, QuoteFile.quote_id == quote_id)
        .first()
    )
    if not quote_file:
        raise HTTPException(status_code=404, detail="Quote file not found")

    file_path = file_storage.get_file_path(quote_file.stored_filename)
    if not file_path or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Quote file not found")

    logger.info(
        "Quote file %s (%s, %s) downloaded from quote %s by user %s",
        quote_file.id,
        quote_file.original_filename,
        quote_file.mime_type,
        quote.id,
        current_user.id,
    )

    return FileResponse(
        path=file_path,
        media_type=quote_file.mime_type or "application/octet-stream",
        filename=quote_file.original_filename,
    )


@router.get("/{quote_id}/files", response_model=list[QuoteArchiveFile])
async def list_quote_files(
    quote_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List retained files attached to a quote."""
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    _authorize_quote_archive_access(quote, current_user)

    return (
        db.query(QuoteFile)
        .filter(QuoteFile.quote_id == quote_id)
        .order_by(QuoteFile.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.post("/{quote_id}/files", response_model=QuoteArchiveFile, status_code=status.HTTP_201_CREATED)
async def upload_quote_file(
    quote_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Staff action: attach a retained file to a manual or online quote."""
    _require_staff_or_admin(current_user)
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    try:
        file_info = await file_storage.save_file(file, user_id=current_user.id, quote_id=quote.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    quote_file = QuoteFile(
        quote_id=quote.id,
        original_filename=file_info["original_filename"],
        stored_filename=file_info["stored_filename"],
        file_path=file_info["file_path"],
        file_size_bytes=file_info["file_size_bytes"],
        file_format=file_info["file_format"],
        mime_type=file_info["mime_type"],
        file_hash=file_info["file_hash"],
    )
    db.add(quote_file)
    db.commit()
    db.refresh(quote_file)

    logger.info(
        "Quote file %s (%s, %s) uploaded to quote %s by user %s",
        quote_file.id,
        quote_file.original_filename,
        quote_file.mime_type,
        quote.id,
        current_user.id,
    )
    return quote_file


@router.delete("/{quote_id}/files/{file_id}")
async def delete_quote_file(
    quote_id: int,
    file_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Staff action: remove a retained file from a quote."""
    _require_staff_or_admin(current_user)
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    quote_file = (
        db.query(QuoteFile)
        .filter(QuoteFile.id == file_id, QuoteFile.quote_id == quote_id)
        .first()
    )
    if not quote_file:
        raise HTTPException(status_code=404, detail="Quote file not found")

    stored_filename = quote_file.stored_filename
    original_filename = quote_file.original_filename
    if not file_storage.delete_file(stored_filename):
        logger.error(
            "Failed to delete stored quote file %s for quote file %s on quote %s",
            stored_filename,
            file_id,
            quote.id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stored quote file could not be deleted",
        )

    db.delete(quote_file)
    db.commit()

    logger.info(
        "Quote file %s (%s) deleted from quote %s by user %s",
        file_id,
        original_filename,
        quote.id,
        current_user.id,
    )
    return {"message": "Quote file deleted"}


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
