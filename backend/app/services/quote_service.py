"""
Quote Service — CRUD, status management, conversion, images, and PDF generation.

Extracted from quotes.py (ARCHITECT-003).
"""
import io
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import Integer, cast, desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.company_settings import CompanySettings
from app.models.quote import Quote, QuoteLine
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.user import User

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper: Generate Quote Number
# ---------------------------------------------------------------------------

def generate_quote_number(db: Session) -> str:
    """Generate next quote number in format Q-YYYY-NNNNNN (zero-padded).

    Uses DB-side numeric extraction to avoid loading all quote numbers into Python.
    """
    year = datetime.now(timezone.utc).year
    prefix = f"Q-{year}-"

    # DB-side max: strip prefix, cast remainder to integer, find max
    max_seq = db.query(
        func.max(
            cast(func.replace(Quote.quote_number, prefix, ''), Integer)
        )
    ).filter(
        Quote.quote_number.like(f"{prefix}%")
    ).scalar() or 0

    next_seq = max_seq + 1
    return f"{prefix}{next_seq:06d}"


# ---------------------------------------------------------------------------
# List / Stats
# ---------------------------------------------------------------------------

def list_quotes(
    db: Session,
    *,
    status_filter: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Quote]:
    """List all quotes with optional filtering."""
    from sqlalchemy.orm import selectinload

    query = db.query(Quote).options(
        selectinload(Quote.lines)
    ).order_by(desc(Quote.created_at), desc(Quote.id))

    if status_filter:
        query = query.filter(Quote.status == status_filter)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Quote.quote_number.ilike(search_term)) |
            (Quote.product_name.ilike(search_term)) |
            (Quote.customer_name.ilike(search_term)) |
            (Quote.customer_email.ilike(search_term))
        )

    quotes = query.offset(skip).limit(limit).all()

    # Add line_count for each quote
    results = []
    for q in quotes:
        q.line_count = len(q.lines) if q.lines else (1 if q.product_name else 0)
        results.append(q)
    return results


def get_quote_stats(db: Session) -> dict:
    """Get quote statistics for dashboard."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    total = db.query(Quote).count()
    pending = db.query(Quote).filter(Quote.status == "pending").count()
    approved = db.query(Quote).filter(Quote.status == "approved").count()
    accepted = db.query(Quote).filter(Quote.status == "accepted").count()
    rejected = db.query(Quote).filter(Quote.status == "rejected").count()
    converted = db.query(Quote).filter(Quote.status == "converted").count()
    expired = db.query(Quote).filter(
        Quote.status.in_(["pending", "approved"]),
        Quote.expires_at < now
    ).count()

    total_value = db.query(func.sum(Quote.total_price)).scalar() or Decimal("0")
    pending_value = db.query(func.sum(Quote.total_price)).filter(
        Quote.status == "pending"
    ).scalar() or Decimal("0")

    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "accepted": accepted,
        "rejected": rejected,
        "converted": converted,
        "expired": expired,
        "total_value": total_value,
        "pending_value": pending_value,
    }


# ---------------------------------------------------------------------------
# Single Quote Detail
# ---------------------------------------------------------------------------

def get_quote_detail(db: Session, quote_id: int) -> Quote:
    """Fetch quote with lines or 404."""
    from sqlalchemy.orm import joinedload

    quote = db.query(Quote).options(
        joinedload(Quote.lines)
    ).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )
    quote.line_count = len(quote.lines) if quote.lines else (1 if quote.product_name else 0)
    return quote


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

def _resolve_tax(db: Session, subtotal: Decimal, request, company_settings) -> tuple:
    """Resolve tax using three-tier fallback. Returns (tax_rate, tax_amount, tax_name)."""
    from app.services.tax_rate_service import get_tax_rate as _get_tr, get_default_tax_rate

    apply_tax = request.apply_tax
    if apply_tax is None and company_settings:
        apply_tax = company_settings.tax_enabled

    tax_rate_id = getattr(request, "tax_rate_id", None)
    if tax_rate_id:
        tr = _get_tr(db, tax_rate_id)
        return tr.rate, subtotal * tr.rate, tr.name
    elif apply_tax:
        default_tr = get_default_tax_rate(db)
        if default_tr:
            return default_tr.rate, subtotal * default_tr.rate, default_tr.name
        elif company_settings and company_settings.tax_rate:
            return company_settings.tax_rate, subtotal * company_settings.tax_rate, company_settings.tax_name
    return None, None, None


def _get_customer_discount(db: Session, customer_id: int) -> Optional[Decimal]:
    """Look up customer's price level discount (PRO feature, graceful degradation)."""
    from app.services.customer_service import get_customer_discount_percent
    return get_customer_discount_percent(db, customer_id)


def create_quote(db: Session, request, user_id: int) -> Quote:
    """Create a new manual quote.

    ``request`` is expected to be a ``ManualQuoteCreate`` Pydantic model.
    Supports both single-item (header fields) and multi-line (request.lines) quotes.
    """
    quote_number = generate_quote_number(db)
    expires_at = datetime.now(timezone.utc) + timedelta(days=request.valid_days)

    has_lines = getattr(request, "lines", None) and len(request.lines) > 0

    # Validate: reject explicitly empty lines array
    if getattr(request, "lines", None) is not None and len(request.lines) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lines array cannot be empty"
        )

    # Validate: either lines or header-level product fields must be provided
    if not has_lines:
        if not request.product_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either 'lines' or 'product_name' + 'unit_price' must be provided"
            )
        if request.unit_price is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="unit_price is required for single-item quotes"
            )

    # Validate customer_id if provided
    if request.customer_id:
        customer = db.query(User).filter(
            User.id == request.customer_id,
            User.account_type == "customer"
        ).first()
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid customer_id - customer not found"
            )

    # Look up customer discount (PRO price level)
    discount_percent = None
    if request.customer_id:
        discount_percent = _get_customer_discount(db, request.customer_id)

    # Calculate subtotal — from lines or header
    if has_lines:
        subtotal = Decimal("0")
        for line in request.lines:
            line_price = Decimal(str(line.unit_price)).quantize(Decimal("0.01"))
            if discount_percent and discount_percent > 0:
                line_price = (line_price * (Decimal("1") - discount_percent / Decimal("100"))).quantize(Decimal("0.01"))
            subtotal += line_price * line.quantity
        # Use first line's product for header-level backward compat
        header_product_name = request.lines[0].product_name
        header_product_id = request.lines[0].product_id
        header_quantity = sum(line.quantity for line in request.lines)
        header_unit_price = None  # Multi-line: no single unit price
    else:
        unit_price = request.unit_price
        quantity = request.quantity or 1
        if discount_percent and discount_percent > 0:
            unit_price = (unit_price * (Decimal("1") - discount_percent / Decimal("100"))).quantize(Decimal("0.01"))
        subtotal = unit_price * quantity
        header_product_name = request.product_name
        header_product_id = request.product_id
        header_quantity = quantity
        header_unit_price = unit_price

    # Get company settings for tax
    company_settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()

    # Resolve tax
    tax_rate, tax_amount, tax_name = _resolve_tax(db, subtotal, request, company_settings)
    total_price = subtotal + (tax_amount or Decimal("0"))

    # Add shipping cost
    shipping_cost = request.shipping_cost or Decimal("0")
    total_price = total_price + shipping_cost

    # Validate material exists if color provided (single-item only)
    effective_material_type = request.material_type or "PLA"
    if not has_lines and request.color:
        from app.services.material_service import get_material_product
        material_product = get_material_product(db, effective_material_type, request.color)
        if not material_product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Material not found: {effective_material_type} in {request.color}. "
                    f"Check available materials at /api/v1/materials/combinations"
                )
            )

    quote = Quote(
        quote_number=quote_number,
        user_id=user_id,
        product_id=header_product_id,
        product_name=header_product_name,
        quantity=header_quantity,
        unit_price=header_unit_price,
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        tax_name=tax_name,
        discount_percent=discount_percent,
        shipping_cost=shipping_cost if shipping_cost > 0 else None,
        total_price=total_price,
        material_type=effective_material_type if not has_lines else None,
        color=request.color if not has_lines else None,
        customer_id=request.customer_id,
        customer_name=request.customer_name,
        customer_email=request.customer_email,
        customer_notes=request.customer_notes,
        admin_notes=request.admin_notes,
        status="pending",
        file_format="manual",
        file_size_bytes=0,
        expires_at=expires_at,
    )

    db.add(quote)
    db.flush()  # Get quote.id for line items

    # Create line items
    if has_lines:
        for idx, line_data in enumerate(request.lines, start=1):
            line_price = Decimal(str(line_data.unit_price)).quantize(Decimal("0.01"))
            line_discount = None
            if discount_percent and discount_percent > 0:
                line_price = (line_price * (Decimal("1") - discount_percent / Decimal("100"))).quantize(Decimal("0.01"))
                line_discount = discount_percent
            line = QuoteLine(
                quote_id=quote.id,
                product_id=line_data.product_id,
                line_number=idx,
                product_name=line_data.product_name,
                quantity=line_data.quantity,
                unit_price=line_price,
                discount_percent=line_discount,
                total=(line_price * line_data.quantity).quantize(Decimal("0.01")),
                material_type=line_data.material_type,
                color=line_data.color,
                notes=line_data.notes,
            )
            db.add(line)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quote number collision, please retry"
        )
    db.refresh(quote)
    quote.line_count = len(quote.lines) if quote.lines else (1 if quote.product_name else 0)

    line_count = len(request.lines) if has_lines else 1
    logger.info(f"Quote {quote_number} created by user {user_id} ({line_count} line(s))")
    return quote


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------

def update_quote(db: Session, quote_id: int, request) -> Quote:
    """Update quote details.

    ``request`` is expected to be a ``ManualQuoteUpdate`` Pydantic model.
    """
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    # Don't allow editing converted quotes
    if quote.status == "converted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot edit a converted quote"
        )

    # Validate customer_id if provided
    if request.customer_id is not None:
        if request.customer_id:  # Not zero/null
            customer = db.query(User).filter(
                User.id == request.customer_id,
                User.account_type == "customer"
            ).first()
            if not customer:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid customer_id - customer not found"
                )

    # Validate material/color combo if either is being changed
    update_data = request.model_dump(exclude_unset=True)
    if "material_type" in update_data or "color" in update_data:
        effective_material = update_data.get("material_type") or quote.material_type or "PLA"
        effective_color = update_data.get("color") or quote.color
        if effective_color:
            from app.services.material_service import get_material_product
            material_product = get_material_product(db, effective_material, effective_color)
            if not material_product:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Material not found: {effective_material} in {effective_color}. "
                        f"Check available materials at /api/v1/materials/combinations"
                    )
                )

    # Handle lines update — replace all existing lines
    lines_data = update_data.pop("lines", None)

    # Update fields (exclude apply_tax as it's not a model field)
    apply_tax = update_data.pop("apply_tax", None)
    shipping_cost_updated = "shipping_cost" in update_data

    for field, value in update_data.items():
        setattr(quote, field, value)

    # If lines provided, replace all existing lines and recalculate from them
    if lines_data is not None:
        # Reject empty lines array (would crash on index access)
        if len(lines_data) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="lines array cannot be empty"
            )

        # Delete existing lines
        for existing_line in list(quote.lines):
            db.delete(existing_line)

        # Look up customer discount
        discount_percent = None
        if quote.customer_id:
            discount_percent = _get_customer_discount(db, quote.customer_id)
        quote.discount_percent = discount_percent

        # Create new lines
        subtotal = Decimal("0")
        for idx, line_data in enumerate(lines_data, start=1):
            ld = line_data if isinstance(line_data, dict) else line_data.model_dump()
            line_price = Decimal(str(ld["unit_price"])).quantize(Decimal("0.01"))
            line_discount = None
            if discount_percent and discount_percent > 0:
                line_price = (line_price * (Decimal("1") - discount_percent / Decimal("100"))).quantize(Decimal("0.01"))
                line_discount = discount_percent
            line_total = (line_price * ld["quantity"]).quantize(Decimal("0.01"))
            subtotal += line_total

            line = QuoteLine(
                quote_id=quote.id,
                product_id=ld.get("product_id"),
                line_number=idx,
                product_name=ld["product_name"],
                quantity=ld["quantity"],
                unit_price=line_price,
                discount_percent=line_discount,
                total=line_total,
                material_type=ld.get("material_type"),
                color=ld.get("color"),
                notes=ld.get("notes"),
            )
            db.add(line)

        # Update header from lines
        quote.product_name = lines_data[0]["product_name"] if isinstance(lines_data[0], dict) else lines_data[0].product_name
        quote.quantity = sum(ld["quantity"] if isinstance(ld, dict) else ld.quantity for ld in lines_data)
        quote.unit_price = None
        quote.subtotal = subtotal

        # Resolve tax (respect apply_tax toggle during multi-line edit)
        company_settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
        shipping = quote.shipping_cost or Decimal("0")
        if apply_tax is not None:
            if apply_tax:
                tax_rate, tax_amount, tax_name = _resolve_tax(db, subtotal, request, company_settings)
                quote.tax_rate = tax_rate
                quote.tax_amount = tax_amount
                quote.tax_name = tax_name
                quote.total_price = subtotal + (tax_amount or Decimal("0")) + shipping
            else:
                quote.tax_rate = None
                quote.tax_amount = None
                quote.total_price = subtotal + shipping
        elif quote.tax_rate:
            quote.tax_amount = subtotal * quote.tax_rate
            quote.total_price = subtotal + quote.tax_amount + shipping
        else:
            quote.total_price = subtotal + shipping

    # Recalculate pricing for single-item updates (only if no lines provided)
    elif request.unit_price is not None or request.quantity is not None or apply_tax is not None or shipping_cost_updated:
        unit_price = request.unit_price if request.unit_price is not None else quote.unit_price
        quantity = request.quantity if request.quantity is not None else quote.quantity
        subtotal = unit_price * quantity
        quote.subtotal = subtotal
        shipping = quote.shipping_cost or Decimal("0")

        # Handle tax calculation
        if apply_tax is not None:
            if apply_tax:
                company_settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
                if company_settings and company_settings.tax_rate:
                    quote.tax_rate = company_settings.tax_rate
                    quote.tax_amount = subtotal * company_settings.tax_rate
                    quote.total_price = subtotal + quote.tax_amount + shipping
                else:
                    quote.tax_rate = None
                    quote.tax_amount = None
                    quote.total_price = subtotal + shipping
            else:
                quote.tax_rate = None
                quote.tax_amount = None
                quote.total_price = subtotal + shipping
        else:
            if quote.tax_rate:
                quote.tax_amount = subtotal * quote.tax_rate
                quote.total_price = subtotal + quote.tax_amount + shipping
            else:
                quote.total_price = subtotal + shipping

    quote.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(quote)
    quote.line_count = len(quote.lines) if quote.lines else (1 if quote.product_name else 0)

    logger.info(f"Quote {quote.quote_number} updated")
    return quote


# ---------------------------------------------------------------------------
# Status Transition
# ---------------------------------------------------------------------------

def update_quote_status(db: Session, quote_id: int, request, current_user_id: int) -> Quote:
    """Update quote status (approve, reject, cancel, accept).

    ``request`` is expected to be a ``QuoteStatusUpdate`` Pydantic model.
    """
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    allowed_statuses = ["pending", "approved", "rejected", "accepted", "cancelled"]
    if request.status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Allowed: {', '.join(allowed_statuses)}"
        )

    # Validate status transitions
    if quote.status == "converted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change status of a converted quote"
        )

    old_status = quote.status
    quote.status = request.status

    if request.status == "approved":
        quote.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
        quote.approved_by = current_user_id
        quote.approval_method = "manual"

    if request.status == "rejected":
        quote.rejection_reason = request.rejection_reason

    if request.admin_notes:
        quote.admin_notes = request.admin_notes

    quote.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(quote)

    logger.info(f"Quote {quote.quote_number} status changed from {old_status} to {request.status}")
    return quote


# ---------------------------------------------------------------------------
# Convert to Sales Order
# ---------------------------------------------------------------------------

def convert_quote_to_order(db: Session, quote_id: int) -> dict:
    """Convert an accepted/approved quote to a sales order.

    Multi-line quotes create a SalesOrder with order_type="line_item" and
    one SalesOrderLine per QuoteLine. Single-item quotes use the existing
    header-only order_type="quote_based" flow.
    """
    from sqlalchemy.orm import joinedload

    quote = db.query(Quote).options(
        joinedload(Quote.lines)
    ).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    if quote.status not in ["approved", "accepted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quote must be approved or accepted to convert. Current status: {quote.status}"
        )

    if quote.sales_order_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quote already converted to order {quote.sales_order_id}"
        )

    if quote.expires_at.replace(tzinfo=None) < datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Quote has expired"
        )

    # Generate order number
    year = datetime.now(timezone.utc).year
    order_prefix = f"SO-{year}-"
    max_seq = db.query(
        func.max(cast(func.replace(SalesOrder.order_number, order_prefix, ''), Integer))
    ).filter(SalesOrder.order_number.like(f"{order_prefix}%")).scalar() or 0
    order_number = f"{order_prefix}{max_seq + 1:04d}"

    subtotal = quote.subtotal or (quote.unit_price * quote.quantity if quote.unit_price else quote.total_price)
    tax = quote.tax_amount or Decimal("0")
    shipping = quote.shipping_cost or Decimal("0")

    # Resolve shipping address (quote → customer fallback)
    shipping_address_line1 = quote.shipping_address_line1
    shipping_address_line2 = quote.shipping_address_line2
    shipping_city = quote.shipping_city
    shipping_state = quote.shipping_state
    shipping_zip = quote.shipping_zip
    shipping_country = quote.shipping_country
    customer_phone = quote.shipping_phone

    if not shipping_address_line1 and quote.customer_id:
        customer = db.query(User).filter(User.id == quote.customer_id).first()
        if customer:
            shipping_address_line1 = customer.shipping_address_line1
            shipping_address_line2 = customer.shipping_address_line2
            shipping_city = customer.shipping_city
            shipping_state = customer.shipping_state
            shipping_zip = customer.shipping_zip
            shipping_country = customer.shipping_country
            if not customer_phone:
                customer_phone = customer.phone

    has_lines = quote.lines and len(quote.lines) > 0

    sales_order = SalesOrder(
        order_number=order_number,
        quote_id=quote.id,
        user_id=quote.user_id,
        order_type="line_item" if has_lines else "quote_based",
        source="portal",
        product_id=quote.product_id if not has_lines else None,
        product_name=quote.product_name,
        quantity=quote.quantity,
        material_type=quote.material_type or "PLA",
        finish=quote.finish or "standard",
        unit_price=quote.unit_price,
        total_price=subtotal,
        tax_amount=tax,
        tax_rate=quote.tax_rate,
        shipping_cost=shipping,
        grand_total=subtotal + tax + shipping,
        status="pending",
        payment_status="pending",
        rush_level=quote.rush_level or "standard",
        customer_notes=quote.customer_notes,
        customer_id=quote.customer_id,
        customer_name=quote.customer_name,
        customer_email=quote.customer_email,
        customer_phone=customer_phone,
        shipping_address_line1=shipping_address_line1,
        shipping_address_line2=shipping_address_line2,
        shipping_city=shipping_city,
        shipping_state=shipping_state,
        shipping_zip=shipping_zip,
        shipping_country=shipping_country or "USA",
    )

    db.add(sales_order)
    db.flush()

    # Create SalesOrderLines for multi-line quotes
    if has_lines:
        # Validate: ck_sol_product_or_material requires product_id to be set
        missing = [ql.product_name for ql in quote.lines if not ql.product_id]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot convert: line(s) missing product link: {', '.join(missing)}. "
                       "Edit the quote and select a product from the catalog for each line."
            )

        for ql in quote.lines:
            # unit_price is already net (discount applied), so discount=0
            sol = SalesOrderLine(
                sales_order_id=sales_order.id,
                product_id=ql.product_id,
                quantity=ql.quantity,
                unit_price=ql.unit_price,
                discount=Decimal("0"),
                total=ql.total,
                notes=ql.notes,
            )
            db.add(sol)

    # Update quote
    quote.status = "converted"
    quote.sales_order_id = sales_order.id
    quote.converted_at = datetime.now(timezone.utc)
    quote.updated_at = datetime.now(timezone.utc)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order number collision, please retry"
        )
    db.refresh(sales_order)

    logger.info(f"Quote {quote.quote_number} converted to order {order_number} ({len(quote.lines)} lines)")

    return {
        "message": f"Quote converted to order {order_number}",
        "order_id": sales_order.id,
        "order_number": order_number,
    }


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def delete_quote(db: Session, quote_id: int) -> str:
    """Delete a quote (only if not converted). Returns quote_number for logging."""
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    if quote.status == "converted":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a converted quote"
        )

    quote_number = quote.quote_number
    db.delete(quote)
    db.commit()

    return quote_number


# ---------------------------------------------------------------------------
# Image Upload / Get / Delete
# ---------------------------------------------------------------------------

def upload_quote_image(
    db: Session,
    quote_id: int,
    content: bytes,
    filename: str,
    content_type: str,
) -> dict:
    """Save image data for a quote."""
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"]
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed: PNG, JPEG, GIF, WebP"
        )

    # Limit file size (5MB for product images)
    max_size = 5 * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size: 5MB"
        )

    quote.image_data = content
    quote.image_filename = filename
    quote.image_mime_type = content_type
    quote.updated_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Image uploaded for quote {quote.quote_number}")
    return {"message": "Image uploaded successfully", "filename": filename}


def get_quote_image(db: Session, quote_id: int) -> dict:
    """Return image data or 404."""
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    if not quote.image_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No image uploaded for this quote"
        )

    return {
        "image_data": quote.image_data,
        "mime_type": quote.image_mime_type or "image/png",
        "filename": quote.image_filename or "quote_image.png",
    }


def delete_quote_image(db: Session, quote_id: int) -> str:
    """Clear image data. Returns quote_number for logging."""
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    quote.image_data = None
    quote.image_filename = None
    quote.image_mime_type = None
    quote.updated_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Image deleted for quote {quote.quote_number}")
    return quote.quote_number


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------

def generate_quote_pdf(db: Session, quote_id: int) -> io.BytesIO:
    """Generate a professional B2B quote PDF using ReportLab.

    Layout: branded header bar, two-column info block (company | quote details),
    clean line-item table with alternating rows, totals section, and footer with
    validity + terms consolidated on one page.
    """
    from xml.sax.saxutils import escape as _xml_escape

    def esc(value: str | None) -> str:
        return _xml_escape(value) if value else ""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
        HRFlowable,
    )

    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quote {quote_id} not found"
        )

    company_settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()

    # -- Currency formatting --
    _CURRENCY_SYMBOLS = {
        "USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$",
        "GBP": "\u00a3", "EUR": "\u20ac", "CHF": "CHF\u00a0",
        "SEK": "kr\u00a0", "NOK": "kr\u00a0", "DKK": "kr\u00a0",
        "BRL": "R$", "MXN": "MX$", "INR": "\u20b9",
        "JPY": "\u00a5", "CNY": "\u00a5", "KRW": "\u20a9",
        "SGD": "S$", "HKD": "HK$", "SAR": "SAR\u00a0",
        "AED": "AED\u00a0", "ZAR": "R",
    }
    _currency = (company_settings.currency_code if company_settings and company_settings.currency_code else "USD")
    _sym = _CURRENCY_SYMBOLS.get(_currency, f"{_currency}\u00a0")

    def _fmt(amount: float) -> str:
        return f"{_sym}{amount:,.2f}"

    # -- Brand colors --
    BRAND_DARK = colors.HexColor('#0f172a')    # slate-900
    BRAND_ACCENT = colors.HexColor('#2563eb')  # blue-600
    BRAND_BORDER = colors.HexColor('#e2e8f0')  # slate-200
    BRAND_MUTED = colors.HexColor('#64748b')   # slate-500
    ROW_STRIPE = colors.HexColor('#f1f5f9')    # slate-100

    # -- PDF setup --
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer, pagesize=letter,
        topMargin=0.4 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    page_width = doc.width  # usable width (tracks margin config above)

    # -- Styles --
    styles = getSampleStyleSheet()
    s_normal = styles['Normal']

    s_quote_label = ParagraphStyle(
        'QuoteLabel', parent=s_normal,
        fontSize=28, fontName='Helvetica-Bold',
        textColor=BRAND_DARK, spaceAfter=2,
    )
    s_section = ParagraphStyle(
        'Section', parent=s_normal,
        fontSize=8, fontName='Helvetica-Bold',
        textColor=BRAND_MUTED, spaceBefore=4, spaceAfter=4,
    )
    s_company_name = ParagraphStyle(
        'CompanyName', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
    )
    s_detail = ParagraphStyle(
        'Detail', parent=s_normal,
        fontSize=9, textColor=BRAND_MUTED, leading=13,
    )
    s_detail_right = ParagraphStyle(
        'DetailRight', parent=s_detail, alignment=TA_RIGHT,
    )
    s_customer_name = ParagraphStyle(
        'CustomerName', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
    )
    s_total_label = ParagraphStyle(
        'TotalLabel', parent=s_normal,
        fontSize=14, fontName='Helvetica-Bold', textColor=BRAND_DARK,
        alignment=TA_RIGHT,
    )
    s_total_value = ParagraphStyle(
        'TotalValue', parent=s_normal,
        fontSize=14, fontName='Helvetica-Bold', textColor=BRAND_ACCENT,
        alignment=TA_RIGHT,
    )
    s_footer = ParagraphStyle(
        'Footer', parent=s_normal,
        fontSize=8, textColor=BRAND_MUTED, leading=11,
    )
    s_footer_center = ParagraphStyle(
        'FooterCenter', parent=s_footer, alignment=TA_CENTER,
    )
    s_validity = ParagraphStyle(
        'Validity', parent=s_normal,
        fontSize=9, fontName='Helvetica-Bold', textColor=BRAND_DARK,
        backColor=colors.HexColor('#eff6ff'),  # blue-50
        borderPadding=10,
    )
    s_notes = ParagraphStyle(
        'Notes', parent=s_normal,
        fontSize=9, textColor=BRAND_DARK, leading=13,
        borderPadding=9,
        backColor=ROW_STRIPE,
    )

    content = []

    # ================================================================
    # HEADER — Logo + Company info (left) | Quote number + date (right)
    # ================================================================
    company_lines = []
    if company_settings:
        if company_settings.company_name:
            company_lines.append(Paragraph(esc(company_settings.company_name), s_company_name))
        addr_parts = []
        if company_settings.company_address_line1:
            addr_parts.append(esc(company_settings.company_address_line1))
        city_state = ""
        if company_settings.company_city:
            city_state = esc(company_settings.company_city)
        if company_settings.company_state:
            city_state += f", {esc(company_settings.company_state)}"
        if company_settings.company_zip:
            city_state += f" {esc(company_settings.company_zip)}"
        if city_state:
            addr_parts.append(city_state)
        if company_settings.company_phone:
            addr_parts.append(esc(company_settings.company_phone))
        if company_settings.company_email:
            addr_parts.append(esc(company_settings.company_email))
        if addr_parts:
            company_lines.append(Paragraph("<br/>".join(addr_parts), s_detail))

    # Left side: logo + company
    left_header = []
    if company_settings and company_settings.logo_data:
        try:
            logo_buffer = io.BytesIO(company_settings.logo_data)
            logo_img = Image(logo_buffer, width=1.2 * inch, height=1.2 * inch)
            logo_img.hAlign = 'LEFT'
            logo_row = Table(
                [[logo_img, company_lines]],
                colWidths=[1.4 * inch, 2.4 * inch],
            )
            logo_row.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            left_header.append(logo_row)
        except Exception:
            left_header.extend(company_lines)
    else:
        left_header.extend(company_lines)

    # Right side: QUOTE label, number, then dates
    s_quote_number_right = ParagraphStyle(
        'QuoteNumberRight', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
        alignment=TA_RIGHT,
    )
    right_header = [
        Paragraph("QUOTE", s_quote_label),
        Paragraph(esc(quote.quote_number), s_quote_number_right),
        Spacer(1, 6),
        Paragraph(f"Date: {quote.created_at.strftime('%B %d, %Y')}", s_detail_right),
    ]
    if quote.expires_at:
        right_header.append(
            Paragraph(f"Valid until: {quote.expires_at.strftime('%B %d, %Y')}", s_detail_right)
        )

    header_table = Table(
        [[left_header, right_header]],
        colWidths=[page_width * 0.55, page_width * 0.45],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    content.append(header_table)
    content.append(Spacer(1, 0.15 * inch))
    content.append(HRFlowable(width="100%", thickness=1, color=BRAND_BORDER))
    content.append(Spacer(1, 0.2 * inch))

    # ================================================================
    # CUSTOMER + QUOTE IMAGE (two-column if image exists)
    # ================================================================
    customer_block = [
        Paragraph("PREPARED FOR", s_section),
        Paragraph(esc(quote.customer_name or 'N/A'), s_customer_name),
    ]
    if quote.customer_email:
        customer_block.append(Paragraph(esc(quote.customer_email), s_detail))

    if quote.image_data:
        try:
            img_buffer = io.BytesIO(quote.image_data)
            quote_img = Image(img_buffer, width=1.8 * inch, height=1.8 * inch)
            quote_img.hAlign = 'RIGHT'
            cust_table = Table(
                [[customer_block, quote_img]],
                colWidths=[page_width - 2.2 * inch, 2.2 * inch],
            )
            cust_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ]))
            content.append(cust_table)
        except Exception:
            for item in customer_block:
                content.append(item)
    else:
        for item in customer_block:
            content.append(item)

    content.append(Spacer(1, 0.25 * inch))

    # ================================================================
    # LINE ITEMS TABLE
    # ================================================================
    if not hasattr(quote, '_sa_instance_state') or not quote.lines:
        db.refresh(quote)

    has_lines = quote.lines and len(quote.lines) > 0

    # Check if any line has material info — hide column if all N/A
    show_material = False
    if has_lines:
        for ql in quote.lines:
            if ql.material_type or ql.color:
                show_material = True
                break
    else:
        if quote.material_type or quote.color:
            show_material = True

    # Table cell styles — light header text, clear data hierarchy
    th = ParagraphStyle('TH', parent=s_normal, fontSize=7, fontName='Helvetica', textColor=BRAND_MUTED)
    th_right = ParagraphStyle('THRight', parent=th, alignment=TA_RIGHT)
    td = ParagraphStyle('TD', parent=s_normal, fontSize=9, textColor=BRAND_DARK)
    td_right = ParagraphStyle('TDRight', parent=td, alignment=TA_RIGHT)
    td_bold = ParagraphStyle('TDBold', parent=td, fontName='Helvetica-Bold')
    td_bold_right = ParagraphStyle('TDBoldRight', parent=td_bold, alignment=TA_RIGHT)
    td_muted = ParagraphStyle('TDMuted', parent=td, textColor=BRAND_MUTED, fontSize=8)
    td_muted_right = ParagraphStyle('TDMutedRight', parent=td_muted, alignment=TA_RIGHT)
    td_strike = ParagraphStyle('TDStrike', parent=td_muted_right, fontSize=8)  # for list price
    td_discount = ParagraphStyle('TDDiscount', parent=s_normal, fontSize=8, textColor=colors.HexColor('#16a34a'), alignment=TA_RIGHT)  # green

    # Determine if discount columns should show
    has_discount = False
    if quote.discount_percent and float(quote.discount_percent) > 0:
        has_discount = True
    if has_lines:
        for ql in quote.lines:
            if ql.discount_percent and float(ql.discount_percent) > 0:
                has_discount = True
                break

    # Build headers based on what columns are needed
    headers = [Paragraph('#', th), Paragraph('ITEM', th)]
    if show_material:
        headers.append(Paragraph('MATERIAL', th))
    headers.append(Paragraph('QTY', th_right))
    if has_discount:
        headers.extend([
            Paragraph('LIST PRICE', th_right),
            Paragraph('DISCOUNT', th_right),
        ])
    headers.extend([
        Paragraph('UNIT PRICE', th_right),
        Paragraph('AMOUNT', th_right),
    ])

    # Column widths — adaptive based on which columns are shown
    if show_material and has_discount:
        col_widths = [0.25 * inch, 1.5 * inch, 0.9 * inch, 0.4 * inch, 0.8 * inch, 0.7 * inch, 0.8 * inch, 0.8 * inch]
    elif has_discount:
        col_widths = [0.25 * inch, 2.2 * inch, 0.45 * inch, 0.85 * inch, 0.75 * inch, 0.9 * inch, 0.9 * inch]
    elif show_material:
        col_widths = [0.3 * inch, 2.3 * inch, 1.3 * inch, 0.6 * inch, 1.0 * inch, 1.0 * inch]
    else:
        col_widths = [0.3 * inch, 3.4 * inch, 0.6 * inch, 1.1 * inch, 1.1 * inch]

    table_data = [headers]
    line_num = 0

    # Helper to compute list price from discounted price + discount percent
    def _list_price(discounted_price: float, discount_pct: float) -> float:
        if discount_pct and discount_pct > 0 and discount_pct < 100:
            return discounted_price / (1.0 - discount_pct / 100.0)
        return discounted_price

    if has_lines:
        subtotal = Decimal("0")
        for ql in quote.lines:
            line_num += 1
            mat_desc = esc(ql.material_type or '')
            if ql.color:
                mat_desc += f" {esc(ql.color)}" if mat_desc else esc(ql.color)
            line_total = float(ql.total)
            subtotal += ql.total

            disc_pct = float(ql.discount_percent or quote.discount_percent or 0)
            unit_price_f = float(ql.unit_price)
            list_price_f = _list_price(unit_price_f, disc_pct)

            row = [
                Paragraph(str(line_num), td_muted),
                Paragraph(esc(ql.product_name or 'Item'), td),
            ]
            if show_material:
                row.append(Paragraph(mat_desc or '\u2014', td_muted))
            row.append(Paragraph(str(ql.quantity), td_right))
            if has_discount:
                row.append(Paragraph(_fmt(list_price_f), td_strike))
                if disc_pct > 0:
                    row.append(Paragraph(f'\u2212{disc_pct:.0f}%', td_discount))
                else:
                    row.append(Paragraph('\u2014', td_muted_right))
            row.extend([
                Paragraph(_fmt(unit_price_f), td_right),
                Paragraph(_fmt(line_total), td_bold_right),
            ])
            table_data.append(row)
        subtotal = float(subtotal)
    else:
        line_num = 1
        material_desc = esc(quote.material_type or '')
        if quote.color:
            material_desc += f" {esc(quote.color)}"
        subtotal = float(quote.subtotal) if quote.subtotal else float(quote.unit_price or 0) * quote.quantity

        disc_pct = float(quote.discount_percent or 0)
        unit_price_f = float(quote.unit_price or 0)
        list_price_f = _list_price(unit_price_f, disc_pct)

        row = [
            Paragraph('1', td_muted),
            Paragraph(esc(quote.product_name or 'Custom Item'), td),
        ]
        if show_material:
            row.append(Paragraph(material_desc or '\u2014', td_muted))
        row.append(Paragraph(str(quote.quantity), td_right))
        if has_discount:
            row.append(Paragraph(_fmt(list_price_f), td_strike))
            if disc_pct > 0:
                row.append(Paragraph(f'\u2212{disc_pct:.0f}%', td_discount))
            else:
                row.append(Paragraph('\u2014', td_muted_right))
        row.extend([
            Paragraph(_fmt(unit_price_f), td_right),
            Paragraph(_fmt(subtotal), td_bold_right),
        ])
        table_data.append(row)

    items_table = Table(table_data, colWidths=col_widths)

    # Build table style — light header, alternating stripes
    ts = [
        # Header row — light background, muted text (not dark/white)
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),  # slate-50
        ('LINEBELOW', (0, 0), (-1, 0), 1, BRAND_BORDER),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        # Data rows
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        # Subtle row separators
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, BRAND_BORDER),
        # Alignment
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    # Alternating row stripes
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            ts.append(('BACKGROUND', (0, i), (-1, i), ROW_STRIPE))

    items_table.setStyle(TableStyle(ts))
    content.append(items_table)
    content.append(Spacer(1, 0.15 * inch))

    # ================================================================
    # TOTALS — right-aligned summary block
    # ================================================================
    totals_data = []

    totals_data.append([
        Paragraph('Subtotal', td_muted_right),
        Paragraph(_fmt(subtotal), td_right),
    ])

    if quote.discount_percent and float(quote.discount_percent) > 0:
        totals_data.append([
            Paragraph(f'Discount ({float(quote.discount_percent):.0f}%)', td_muted_right),
            Paragraph('Applied per line', td_muted_right),
        ])

    if quote.tax_rate and quote.tax_amount:
        tax_percent = float(quote.tax_rate) * 100
        tax_name = "Sales Tax"
        if company_settings and company_settings.tax_name:
            tax_name = esc(company_settings.tax_name)
        totals_data.append([
            Paragraph(f'{tax_name} ({tax_percent:.2f}%)', td_muted_right),
            Paragraph(_fmt(float(quote.tax_amount)), td_right),
        ])

    if quote.shipping_cost and float(quote.shipping_cost) > 0:
        totals_data.append([
            Paragraph('Shipping', td_muted_right),
            Paragraph(_fmt(float(quote.shipping_cost)), td_right),
        ])

    # Total row
    totals_data.append([
        Paragraph('Total Due', s_total_label),
        Paragraph(_fmt(float(quote.total_price or 0)), s_total_value),
    ])

    totals_width = 3.0 * inch
    spacer_width = page_width - totals_width
    totals_table = Table(
        [[Spacer(spacer_width, 1), Table(
            totals_data,
            colWidths=[1.6 * inch, 1.4 * inch],
            style=TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LINEABOVE', (0, -1), (-1, -1), 1.5, BRAND_DARK),
                ('TOPPADDING', (0, -1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, -1), (-1, -1), 4),
            ]),
        )]],
        colWidths=[spacer_width, totals_width],
    )
    totals_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    content.append(totals_table)
    content.append(Spacer(1, 0.3 * inch))

    # ================================================================
    # NOTES (if any)
    # ================================================================
    if quote.customer_notes:
        content.append(Paragraph("NOTES", s_section))
        content.append(Paragraph(esc(quote.customer_notes), s_notes))
        content.append(Spacer(1, 0.2 * inch))

    # ================================================================
    # VALIDITY BANNER
    # ================================================================
    if quote.expires_at:
        content.append(Paragraph(
            f"This quote is valid until <b>{quote.expires_at.strftime('%B %d, %Y')}</b>. "
            "To accept, please contact us referencing your quote number.",
            s_validity,
        ))
        content.append(Spacer(1, 0.2 * inch))

    # ================================================================
    # TERMS & CONDITIONS (compact)
    # ================================================================
    if company_settings and company_settings.quote_terms:
        content.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER))
        content.append(Spacer(1, 0.1 * inch))
        content.append(Paragraph("TERMS &amp; CONDITIONS", s_section))
        content.append(Paragraph(esc(company_settings.quote_terms), s_footer))
        content.append(Spacer(1, 0.15 * inch))

    # ================================================================
    # FOOTER
    # ================================================================
    content.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER))
    content.append(Spacer(1, 0.1 * inch))
    if company_settings and company_settings.quote_footer:
        content.append(Paragraph(esc(company_settings.quote_footer), s_footer_center))
    else:
        content.append(Paragraph("Thank you for your business!", s_footer_center))

    # Build PDF
    doc.build(content)
    pdf_buffer.seek(0)
    return pdf_buffer
