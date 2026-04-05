"""Invoice service -- create, list, pay, PDF generation."""
import io
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import Integer, cast, desc, func
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.company_settings import CompanySettings
from app.models.invoice import Invoice, InvoiceLine
from app.models.product import Product
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.user import User

logger = get_logger(__name__)


# ============================================================================
# Invoice Number Generation
# ============================================================================

def _generate_invoice_number(db: Session) -> str:
    """Generate next invoice number: INV-YYYY-NNN.

    Derives sequence from MAX existing invoice number for the current year.
    Uses the invoice_prefix from CompanySettings if available.
    Uses regex filter to ensure only simple format values are considered
    (same pattern as generate_customer_number in customer_service.py).
    """
    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    prefix = (settings.invoice_prefix if settings and settings.invoice_prefix else "INV")
    year = date.today().year
    full_prefix = f"{prefix}-{year}-"

    # Find max sequence for this year using regex filter
    max_seq = (
        db.query(
            func.max(
                cast(
                    func.replace(Invoice.invoice_number, full_prefix, ""),
                    Integer,
                )
            )
        )
        .filter(
            Invoice.invoice_number.like(f"{full_prefix}%"),
            Invoice.invoice_number.op("~")(rf"^{prefix}-{year}-\d+$"),
        )
        .scalar()
    ) or 0

    return f"{full_prefix}{max_seq + 1:03d}"


# ============================================================================
# Due Date Calculation
# ============================================================================

def _calculate_due_date(payment_terms: str, from_date: Optional[date] = None) -> date:
    """Calculate invoice due date from payment terms.

    Normalizes term strings before lookup so that "net_30", "net-30", and
    "Net 30" all resolve identically to the canonical short-form keys.
    """
    base = from_date or date.today()
    # Normalize: lowercase, collapse separators, strip whitespace
    normalized = (payment_terms or "").strip().lower().replace(" ", "").replace("_", "").replace("-", "")
    terms_days = {
        "cod": 0,
        "prepay": 0,
        "prepaid": 0,
        "cardonfile": 0,
        "net15": 15,
        "net30": 30,
        "net60": 60,
    }
    days = terms_days.get(normalized, 0)
    return base + timedelta(days=days)


# ============================================================================
# Create Invoice
# ============================================================================

def create_invoice(db: Session, sales_order_id: int) -> Invoice:
    """Generate an invoice from a confirmed sales order.

    Snapshots customer info and line items from the SO.
    Only allows invoicing orders in confirmed/in_production/ready_to_ship/
    shipped/delivered/completed status. Prevents duplicate invoices per SO.
    Handles both multi-line orders (SalesOrderLine) and single-product
    orders (quote-based, fields on SalesOrder itself).
    """
    order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")

    allowed_statuses = (
        "confirmed", "in_production", "ready_to_ship",
        "shipped", "delivered", "completed",
    )
    if order.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot invoice order in '{order.status}' status",
        )

    # Check for existing invoice on this SO (prevent duplicates)
    existing = db.query(Invoice).filter(
        Invoice.sales_order_id == sales_order_id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Invoice {existing.invoice_number} already exists for this order",
        )

    # Get customer info from User record
    customer = None
    if order.user_id:
        customer = db.query(User).filter(User.id == order.user_id).first()

    # Payment terms: use customer's payment_terms if the column exists
    # (migration 069 is on a separate branch), else default to "cod"
    payment_terms = getattr(customer, "payment_terms", None) or "cod" if customer else "cod"
    due_date = _calculate_due_date(payment_terms)

    invoice_number = _generate_invoice_number(db)

    # Get order lines for multi-line orders
    order_lines = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.sales_order_id == order.id)
        .all()
    )

    # Calculate subtotal from lines
    subtotal = Decimal("0")
    invoice_lines = []

    if order_lines:
        # Multi-line order (marketplace / manual multi-item)
        for ol in order_lines:
            product = None
            if ol.product_id:
                product = db.query(Product).filter(Product.id == ol.product_id).first()

            sku = product.sku if product else ""
            description = product.name if product else "Item"
            base_price = product.selling_price if product else ol.unit_price
            line_total = ol.quantity * ol.unit_price

            invoice_lines.append(InvoiceLine(
                product_id=ol.product_id,
                sku=sku,
                description=description,
                quantity=ol.quantity,
                unit_price=ol.unit_price,
                base_price=base_price if base_price != ol.unit_price else None,
                discount_percent=ol.discount if ol.discount else None,
                line_total=line_total,
            ))
            subtotal += line_total
    else:
        # Single-product order (quote-based)
        product = None
        if order.product_id:
            product = db.query(Product).filter(Product.id == order.product_id).first()
        sku = product.sku if product else ""
        description = order.product_name or (product.name if product else "Item")
        unit_price = order.unit_price or Decimal("0")
        quantity = Decimal(str(order.quantity or 1))
        line_total = quantity * unit_price

        invoice_lines.append(InvoiceLine(
            product_id=order.product_id,
            sku=sku,
            description=description,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        ))
        subtotal = line_total

    tax_rate = order.tax_rate or Decimal("0")
    tax_amount = order.tax_amount or Decimal("0")
    shipping = order.shipping_cost or Decimal("0")
    total = subtotal + tax_amount + shipping

    # Build customer name from order or User record
    customer_name = order.customer_name or (
        f"{customer.first_name or ''} {customer.last_name or ''}".strip()
        if customer else None
    )

    invoice = Invoice(
        invoice_number=invoice_number,
        sales_order_id=order.id,
        customer_id=order.user_id,
        customer_name=customer_name,
        customer_email=order.customer_email or (customer.email if customer else None),
        customer_company=customer.company_name if customer else None,
        bill_to_line1=customer.billing_address_line1 if customer else None,
        bill_to_city=customer.billing_city if customer else None,
        bill_to_state=customer.billing_state if customer else None,
        bill_to_zip=customer.billing_zip if customer else None,
        payment_terms=payment_terms,
        due_date=due_date,
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        shipping_amount=shipping,
        total=total,
    )

    db.add(invoice)
    db.flush()

    for il in invoice_lines:
        il.invoice_id = invoice.id
        db.add(il)

    db.commit()
    db.refresh(invoice)
    return invoice


# ============================================================================
# Record Payment
# ============================================================================

def record_payment(
    db: Session,
    invoice_id: int,
    amount: Decimal,
    method: str,
    reference: Optional[str] = None,
) -> Invoice:
    """Record a payment against an invoice.

    When total amount paid reaches or exceeds the invoice total,
    the invoice is automatically marked as paid.
    """
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status in ("paid", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot record payment on {invoice.status} invoice",
        )

    new_paid = (invoice.amount_paid or Decimal("0")) + amount
    invoice.amount_paid = new_paid
    invoice.payment_method = method
    invoice.payment_reference = reference

    if new_paid >= invoice.total:
        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(invoice)
    return invoice


# ============================================================================
# List / Query
# ============================================================================

def list_invoices(
    db: Session,
    status: Optional[str] = None,
    customer_search: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[Invoice]:
    """List invoices with optional status and customer search filters.

    Special status value 'overdue' returns sent invoices past their due date.
    """
    query = db.query(Invoice).order_by(desc(Invoice.created_at))

    if status and status != "all":
        if status == "overdue":
            query = query.filter(
                Invoice.status == "sent",
                Invoice.due_date < date.today(),
            )
        else:
            query = query.filter(Invoice.status == status)

    if customer_search:
        search = f"%{customer_search}%"
        query = query.filter(
            (Invoice.customer_name.ilike(search))
            | (Invoice.customer_company.ilike(search))
            | (Invoice.customer_email.ilike(search))
            | (Invoice.invoice_number.ilike(search))
        )

    return query.offset(offset).limit(limit).all()


def get_invoice(db: Session, invoice_id: int) -> Invoice:
    """Get a single invoice by ID."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def get_overdue_invoices(db: Session) -> list[Invoice]:
    """Get invoices past due_date still in 'sent' status."""
    return (
        db.query(Invoice)
        .filter(
            Invoice.status == "sent",
            Invoice.due_date < date.today(),
        )
        .order_by(Invoice.due_date)
        .all()
    )


def get_invoice_summary(db: Session) -> dict:
    """Get summary stats for dashboard widget.

    Returns overdue invoice count and total accounts receivable.
    """
    overdue_count = (
        db.query(func.count(Invoice.id))
        .filter(Invoice.status == "sent", Invoice.due_date < date.today())
        .scalar()
    ) or 0

    total_ar = (
        db.query(func.sum(Invoice.total - Invoice.amount_paid))
        .filter(Invoice.status.in_(["draft", "sent"]))
        .scalar()
    ) or Decimal("0")

    return {
        "overdue_count": overdue_count,
        "total_ar": float(total_ar),
    }


def mark_sent(db: Session, invoice_id: int) -> Invoice:
    """Mark an invoice as sent (draft -> sent transition)."""
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft invoices can be sent")
    invoice.status = "sent"
    invoice.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(invoice)
    return invoice


# ============================================================================
# PDF Generation
# ============================================================================

def generate_invoice_pdf(db: Session, invoice_id: int) -> io.BytesIO:
    """Generate a professional B2B invoice PDF using ReportLab.

    Layout mirrors generate_quote_pdf(): branded header, HR separator,
    two-column Bill To / Invoice Details block, clean line-items table
    with alternating rows, totals block, and payment terms footer.
    """
    from xml.sax.saxutils import escape as _xml_escape

    def esc(value) -> str:
        return _xml_escape(str(value)) if value else ""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
        HRFlowable, KeepTogether,
    )

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()

    # Resolve linked sales order once — used for phone and order number.
    # Note: invoice.customer_id stores order.user_id (a User PK, not Customer PK),
    # so we look up phone from SalesOrder.customer_phone instead.
    _linked_so = None
    if invoice.sales_order_id:
        _linked_so = db.query(SalesOrder).filter(SalesOrder.id == invoice.sales_order_id).first()
    customer_phone = _linked_so.customer_phone if _linked_so else None
    order_number = _linked_so.order_number if _linked_so else None

    # -- Currency formatting --
    _CURRENCY_SYMBOLS = {
        "USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$",
        "GBP": "\u00a3", "EUR": "\u20ac", "CHF": "CHF\u00a0",
        "SEK": "kr\u00a0", "NOK": "kr\u00a0", "DKK": "kr\u00a0",
        "BRL": "R$", "MXN": "MX$", "INR": "\u20b9",
        "JPY": "\u00a5", "CNY": "\u00a5", "KRW": "\u20a9",
        "SGD": "S$", "HKD": "HK$", "ZAR": "R",
    }
    _currency = (settings.currency_code if settings and settings.currency_code else "USD")
    _sym = _CURRENCY_SYMBOLS.get(_currency, f"{_currency}\u00a0")

    def _fmt(amount) -> str:
        value = Decimal(str(amount or "0")).quantize(Decimal("0.01"))
        return f"{_sym}{value:,.2f}"

    # -- Brand colors (matches quote PDF) --
    BRAND_DARK = colors.HexColor('#0f172a')
    BRAND_ACCENT = colors.HexColor('#2563eb')
    BRAND_BORDER = colors.HexColor('#e2e8f0')
    BRAND_MUTED = colors.HexColor('#64748b')
    ROW_STRIPE = colors.HexColor('#f1f5f9')

    # -- PDF document --
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer, pagesize=letter,
        topMargin=0.4 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    page_width = doc.width

    # -- Styles --
    styles = getSampleStyleSheet()
    s_normal = styles['Normal']

    s_doc_label = ParagraphStyle(
        'InvLabel', parent=s_normal,
        fontSize=28, fontName='Helvetica-Bold', textColor=BRAND_DARK, spaceAfter=2,
    )
    s_section = ParagraphStyle(
        'InvSection', parent=s_normal,
        fontSize=8, fontName='Helvetica-Bold', textColor=BRAND_MUTED,
        spaceBefore=4, spaceAfter=4,
    )
    s_company_name = ParagraphStyle(
        'InvCompany', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
    )
    s_detail = ParagraphStyle(
        'InvDetail', parent=s_normal,
        fontSize=9, textColor=BRAND_MUTED, leading=13,
    )
    s_detail_right = ParagraphStyle(
        'InvDetailRight', parent=s_detail, alignment=TA_RIGHT,
    )
    s_inv_number_right = ParagraphStyle(
        'InvNumberRight', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
        alignment=TA_RIGHT,
    )
    s_customer_name = ParagraphStyle(
        'InvCustName', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
    )
    s_total_label = ParagraphStyle(
        'InvTotalLabel', parent=s_normal,
        fontSize=14, fontName='Helvetica-Bold', textColor=BRAND_DARK,
        alignment=TA_RIGHT,
    )
    s_total_value = ParagraphStyle(
        'InvTotalValue', parent=s_normal,
        fontSize=14, fontName='Helvetica-Bold', textColor=BRAND_ACCENT,
        alignment=TA_RIGHT,
    )
    s_terms_box = ParagraphStyle(
        'InvTermsBox', parent=s_normal,
        fontSize=9, textColor=BRAND_DARK, leading=13,
        backColor=colors.HexColor('#eff6ff'),
        borderPadding=10,
    )
    s_footer = ParagraphStyle(
        'InvFooter', parent=s_normal,
        fontSize=8, textColor=BRAND_MUTED, leading=11,
    )
    s_footer_center = ParagraphStyle(
        'InvFooterCenter', parent=s_footer, alignment=TA_CENTER,
    )

    # Table cell styles
    th = ParagraphStyle('InvTH', parent=s_normal, fontSize=7, fontName='Helvetica', textColor=BRAND_MUTED)
    th_right = ParagraphStyle('InvTHRight', parent=th, alignment=TA_RIGHT)
    td = ParagraphStyle('InvTD', parent=s_normal, fontSize=9, textColor=BRAND_DARK)
    td_right = ParagraphStyle('InvTDRight', parent=td, alignment=TA_RIGHT)
    td_bold = ParagraphStyle('InvTDBold', parent=td, fontName='Helvetica-Bold')
    td_bold_right = ParagraphStyle('InvTDBoldRight', parent=td_bold, alignment=TA_RIGHT)
    td_muted = ParagraphStyle('InvTDMuted', parent=td, textColor=BRAND_MUTED, fontSize=8)
    td_muted_right = ParagraphStyle('InvTDMutedRight', parent=td_muted, alignment=TA_RIGHT)

    content = []

    # ================================================================
    # HEADER — Logo + Company (left) | INVOICE + number/dates (right)
    # ================================================================
    company_lines = []
    if settings:
        if settings.company_name:
            company_lines.append(Paragraph(esc(settings.company_name), s_company_name))
        addr_parts = []
        if settings.company_address_line1:
            addr_parts.append(esc(settings.company_address_line1))
        city_state = ""
        if settings.company_city:
            city_state = esc(settings.company_city)
        if settings.company_state:
            city_state += f", {esc(settings.company_state)}"
        if settings.company_zip:
            city_state += f" {esc(settings.company_zip)}"
        if city_state:
            addr_parts.append(city_state)
        if settings.company_phone:
            addr_parts.append(esc(settings.company_phone))
        if settings.company_email:
            addr_parts.append(esc(settings.company_email))
        if addr_parts:
            company_lines.append(Paragraph("<br/>".join(addr_parts), s_detail))

    left_header = []
    if settings and settings.logo_data:
        try:
            logo_buffer = io.BytesIO(settings.logo_data)
            logo_img = Image(logo_buffer, width=1.2 * inch, height=1.2 * inch)
            logo_img.hAlign = 'LEFT'
            logo_row = Table(
                [[logo_img, company_lines]],
                colWidths=[1.4 * inch, 2.4 * inch],
            )
            logo_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
            left_header.append(logo_row)
        except Exception:
            left_header.extend(company_lines)
    else:
        left_header.extend(company_lines)

    right_header = [
        Paragraph("INVOICE", s_doc_label),
        Paragraph(esc(invoice.invoice_number), s_inv_number_right),
        Spacer(1, 6),
        Paragraph(
            f"Date: {invoice.created_at.strftime('%B %d, %Y')}" if invoice.created_at else "Date: —",
            s_detail_right,
        ),
        Paragraph(
            f"Due: {invoice.due_date.strftime('%B %d, %Y')}" if invoice.due_date else "Due: —",
            s_detail_right,
        ),
        Paragraph(f"Terms: {esc(invoice.payment_terms.upper())}", s_detail_right),
    ]
    if order_number:
        right_header.append(Paragraph(f"Order: {esc(order_number)}", s_detail_right))

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
    # BILL TO | (spacer right column — could add Ship To later)
    # ================================================================
    bill_lines = [Paragraph("BILL TO", s_section)]
    if invoice.customer_name:
        bill_lines.append(Paragraph(esc(invoice.customer_name), s_customer_name))
    if invoice.customer_company:
        bill_lines.append(Paragraph(esc(invoice.customer_company), s_detail))
    if invoice.bill_to_line1:
        bill_lines.append(Paragraph(esc(invoice.bill_to_line1), s_detail))
    city_state_zip = ""
    if invoice.bill_to_city:
        city_state_zip = esc(invoice.bill_to_city)
    if invoice.bill_to_state:
        city_state_zip += f", {esc(invoice.bill_to_state)}"
    if invoice.bill_to_zip:
        city_state_zip += f" {esc(invoice.bill_to_zip)}"
    if city_state_zip:
        bill_lines.append(Paragraph(city_state_zip, s_detail))
    if customer_phone:
        bill_lines.append(Paragraph(esc(customer_phone), s_detail))
    if invoice.customer_email:
        bill_lines.append(Paragraph(esc(invoice.customer_email), s_detail))

    bill_table = Table(
        [[bill_lines, ""]],
        colWidths=[page_width * 0.5, page_width * 0.5],
    )
    bill_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    content.append(bill_table)
    content.append(Spacer(1, 0.25 * inch))

    # ================================================================
    # LINE ITEMS TABLE
    # ================================================================
    lines = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).order_by(InvoiceLine.id).all()

    table_data = [[
        Paragraph('#', th),
        Paragraph('SKU', th),
        Paragraph('DESCRIPTION', th),
        Paragraph('QTY', th_right),
        Paragraph('UNIT PRICE', th_right),
        Paragraph('AMOUNT', th_right),
    ]]

    for i, line in enumerate(lines, 1):
        qty_val = float(line.quantity)
        qty_str = str(int(qty_val)) if qty_val == int(qty_val) else f"{qty_val:g}"
        table_data.append([
            Paragraph(str(i), td_muted),
            Paragraph(esc(line.sku or "—"), td_muted),
            Paragraph(esc(line.description), td),
            Paragraph(qty_str, td_right),
            Paragraph(_fmt(line.unit_price), td_right),
            Paragraph(_fmt(line.line_total), td_bold_right),
        ])

    items_table = Table(
        table_data,
        colWidths=[0.25 * inch, 1.1 * inch, 2.75 * inch, 0.5 * inch, 1.0 * inch, 1.0 * inch],
    )
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('LINEBELOW', (0, 0), (-1, 0), 1, BRAND_BORDER),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, BRAND_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            ts.append(('BACKGROUND', (0, i), (-1, i), ROW_STRIPE))
    items_table.setStyle(TableStyle(ts))
    content.append(items_table)
    content.append(Spacer(1, 0.15 * inch))

    # ================================================================
    # TOTALS — right-aligned summary block (same pattern as quote PDF)
    # ================================================================
    totals_data = []
    totals_data.append([
        Paragraph('Subtotal', td_muted_right),
        Paragraph(_fmt(invoice.subtotal), td_right),
    ])
    if invoice.discount_amount and Decimal(str(invoice.discount_amount or "0")) > 0:
        totals_data.append([
            Paragraph('Discount', td_muted_right),
            Paragraph(f'−{_fmt(invoice.discount_amount)}', td_muted_right),
        ])
    if invoice.tax_amount and Decimal(str(invoice.tax_amount or "0")) > 0:
        tax_label = "Sales Tax"
        if settings and settings.tax_name:
            tax_label = esc(settings.tax_name)
        if invoice.tax_rate and Decimal(str(invoice.tax_rate or "0")) > 0:
            tax_label += f" ({Decimal(str(invoice.tax_rate)) * 100:.2f}%)"
        totals_data.append([
            Paragraph(tax_label, td_muted_right),
            Paragraph(_fmt(invoice.tax_amount), td_right),
        ])
    if invoice.shipping_amount and Decimal(str(invoice.shipping_amount or "0")) > 0:
        totals_data.append([
            Paragraph('Shipping', td_muted_right),
            Paragraph(_fmt(invoice.shipping_amount), td_right),
        ])
    totals_data.append([
        Paragraph('Total Due', s_total_label),
        Paragraph(_fmt(invoice.total), s_total_value),
    ])
    if invoice.amount_paid and Decimal(str(invoice.amount_paid or "0")) > 0:
        balance = Decimal(str(invoice.total or "0")) - Decimal(str(invoice.amount_paid or "0"))
        totals_data.append([
            Paragraph('Amount Paid', td_muted_right),
            Paragraph(_fmt(invoice.amount_paid), td_right),
        ])
        totals_data.append([
            Paragraph('Balance Due', s_total_label),
            Paragraph(_fmt(balance), s_total_value),
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
    # PAYMENT TERMS — generated verbiage + optional company override
    # ================================================================
    _TERMS_VERBIAGE = {
        "cod": (
            "Payment is due upon delivery. Please ensure payment is prepared "
            "and ready at the time your order arrives."
        ),
        "prepaid": (
            "Payment is due prior to shipment. Production will begin upon "
            "confirmation of payment."
        ),
        "net_15": (
            f"Payment is due within 15 days of the invoice date. "
            f"Please remit payment by "
            f"{invoice.due_date.strftime('%B %d, %Y') if invoice.due_date else 'the due date shown above'}."
        ),
        "net_30": (
            f"Payment is due within 30 days of the invoice date. "
            f"Please remit payment by "
            f"{invoice.due_date.strftime('%B %d, %Y') if invoice.due_date else 'the due date shown above'}."
        ),
        "net_60": (
            f"Payment is due within 60 days of the invoice date. "
            f"Please remit payment by "
            f"{invoice.due_date.strftime('%B %d, %Y') if invoice.due_date else 'the due date shown above'}."
        ),
    }
    # Aliases map legacy codes used by _calculate_due_date() to canonical keys
    _TERMS_ALIASES = {
        "prepay": "prepaid",
        "net15": "net_15",
        "net30": "net_30",
        "net60": "net_60",
    }
    terms_key = (invoice.payment_terms or "").strip().lower().replace(" ", "_").replace("-", "_")
    terms_key = _TERMS_ALIASES.get(terms_key, terms_key)
    terms_verbiage = _TERMS_VERBIAGE.get(terms_key)
    if not terms_verbiage:
        due_str = invoice.due_date.strftime('%B %d, %Y') if invoice.due_date else "the due date shown above"
        terms_verbiage = f"Payment is due by {due_str}."

    # Append company invoice_terms — raw (no pre-escape), esc() runs once at render below
    if settings and settings.invoice_terms:
        terms_verbiage += f" {settings.invoice_terms}"

    content.append(KeepTogether([
        HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER),
        Spacer(1, 0.1 * inch),
        Paragraph("PAYMENT TERMS", s_section),
        Paragraph(esc(terms_verbiage), s_terms_box),
        Spacer(1, 0.2 * inch),
    ]))

    # ================================================================
    # FOOTER
    # ================================================================
    content.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER))
    content.append(Spacer(1, 0.1 * inch))
    footer_text = (settings.quote_footer if settings and settings.quote_footer else None)
    if footer_text:
        content.append(Paragraph(esc(footer_text), s_footer_center))
    else:
        company_name = esc(settings.company_name) if settings and settings.company_name else "us"
        content.append(Paragraph(
            f"Thank you for your business with {company_name}. "
            "Questions? Please contact us and reference your invoice number.",
            s_footer_center,
        ))

    doc.build(content)
    pdf_buffer.seek(0)
    return pdf_buffer
