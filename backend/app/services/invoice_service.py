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
    """Calculate invoice due date from payment terms."""
    base = from_date or date.today()
    terms_days = {
        "cod": 0,
        "prepay": 0,
        "card_on_file": 0,
        "net15": 15,
        "net30": 30,
    }
    days = terms_days.get(payment_terms, 0)
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
    """Generate a professional invoice PDF using ReportLab.

    Pattern mirrors generate_packing_slip_pdf() in sales_order_service.py.
    Includes company header, invoice details, bill-to address, line items
    table, totals breakdown, and payment instructions.
    """
    from xml.sax.saxutils import escape as _xml_escape

    def esc(value) -> str:
        """Escape user-provided text for ReportLab Paragraph XML."""
        return _xml_escape(str(value)) if value else ""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    )

    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "InvoiceTitle", parent=styles["Heading1"],
        fontSize=24, textColor=colors.HexColor("#2563eb"),
    )
    heading_style = ParagraphStyle(
        "InvoiceHeading", parent=styles["Heading2"],
        fontSize=12, textColor=colors.gray,
    )
    normal_style = styles["Normal"]

    content = []

    # ---- Company Header (same pattern as packing slip) ----
    if settings and settings.logo_data:
        try:
            logo_buffer = io.BytesIO(settings.logo_data)
            logo_img = Image(logo_buffer, width=1.5 * inch, height=1.5 * inch)
            logo_img.hAlign = "LEFT"
            company_info = []
            if settings.company_name:
                company_info.append(f"<b>{esc(settings.company_name)}</b>")
            if settings.company_address_line1:
                company_info.append(esc(settings.company_address_line1))
            if settings.company_city or settings.company_state:
                city_state = (
                    f"{esc(settings.company_city or '')}, "
                    f"{esc(settings.company_state or '')} "
                    f"{esc(settings.company_zip or '')}"
                ).strip(", ")
                company_info.append(city_state)
            if settings.company_phone:
                company_info.append(esc(settings.company_phone))
            if settings.company_email:
                company_info.append(esc(settings.company_email))
            header_data = [
                [logo_img, Paragraph("<br/>".join(company_info), normal_style)]
            ]
            header_table = Table(header_data, colWidths=[2 * inch, 4.5 * inch])
            header_table.setStyle(
                TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])
            )
            content.append(header_table)
            content.append(Spacer(1, 0.3 * inch))
        except Exception:
            # If logo fails, continue without it
            pass
    elif settings and settings.company_name:
        content.append(
            Paragraph(f"<b>{esc(settings.company_name)}</b>", title_style)
        )
        content.append(Spacer(1, 0.2 * inch))

    # ---- Title ----
    content.append(Paragraph("INVOICE", title_style))
    content.append(Spacer(1, 0.2 * inch))

    # ---- Invoice Info ----
    content.append(Paragraph("INVOICE DETAILS", heading_style))
    content.append(Spacer(1, 0.05 * inch))

    info_data = [
        ["Invoice Number:", esc(invoice.invoice_number)],
        [
            "Date:",
            invoice.created_at.strftime("%B %d, %Y") if invoice.created_at else "N/A",
        ],
        [
            "Due Date:",
            invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "N/A",
        ],
        ["Terms:", esc(invoice.payment_terms.upper())],
    ]
    if invoice.sales_order_id:
        order = db.query(SalesOrder).filter(
            SalesOrder.id == invoice.sales_order_id,
        ).first()
        if order:
            info_data.append(["Order:", esc(order.order_number)])

    info_table = Table(info_data, colWidths=[1.5 * inch, 4 * inch])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    content.append(info_table)
    content.append(Spacer(1, 0.2 * inch))

    # ---- Bill To ----
    content.append(Paragraph("BILL TO", heading_style))
    content.append(Spacer(1, 0.05 * inch))

    bill_parts = []
    if invoice.customer_name:
        bill_parts.append(f"<b>{esc(invoice.customer_name)}</b>")
    if invoice.customer_company:
        bill_parts.append(esc(invoice.customer_company))
    if invoice.bill_to_line1:
        bill_parts.append(esc(invoice.bill_to_line1))
    city_state_zip = ""
    if invoice.bill_to_city:
        city_state_zip += esc(invoice.bill_to_city)
    if invoice.bill_to_state:
        city_state_zip += f", {esc(invoice.bill_to_state)}"
    if invoice.bill_to_zip:
        city_state_zip += f" {esc(invoice.bill_to_zip)}"
    if city_state_zip:
        bill_parts.append(city_state_zip)
    if invoice.customer_email:
        bill_parts.append(esc(invoice.customer_email))

    content.append(
        Paragraph("<br/>".join(bill_parts) if bill_parts else "N/A", normal_style)
    )
    content.append(Spacer(1, 0.2 * inch))

    # ---- Line Items ----
    content.append(Paragraph("ITEMS", heading_style))
    content.append(Spacer(1, 0.1 * inch))

    table_data = [["SKU", "Description", "Qty", "Unit Price", "Total"]]
    lines = (
        db.query(InvoiceLine)
        .filter(InvoiceLine.invoice_id == invoice.id)
        .all()
    )
    for line in lines:
        qty_str = (
            str(int(line.quantity))
            if line.quantity == int(line.quantity)
            else str(line.quantity)
        )
        table_data.append([
            esc(line.sku or ""),
            esc(line.description),
            qty_str,
            f"${line.unit_price:,.2f}",
            f"${line.line_total:,.2f}",
        ])

    items_table = Table(
        table_data,
        colWidths=[1 * inch, 2.5 * inch, 0.7 * inch, 1.1 * inch, 1.2 * inch],
    )
    items_table.setStyle(TableStyle([
        # Header row - dark blue background
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        # Right-align numeric columns
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        # Alternating row backgrounds
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4f8")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    content.append(items_table)
    content.append(Spacer(1, 0.2 * inch))

    # ---- Totals ----
    totals_data = [
        ["Subtotal:", f"${invoice.subtotal:,.2f}"],
    ]
    if invoice.discount_amount and invoice.discount_amount > 0:
        totals_data.append(["Discount:", f"-${invoice.discount_amount:,.2f}"])
    if invoice.tax_amount and invoice.tax_amount > 0:
        tax_pct = (
            f" ({float(invoice.tax_rate) * 100:.2f}%)" if invoice.tax_rate else ""
        )
        totals_data.append([f"Tax{tax_pct}:", f"${invoice.tax_amount:,.2f}"])
    if invoice.shipping_amount and invoice.shipping_amount > 0:
        totals_data.append(["Shipping:", f"${invoice.shipping_amount:,.2f}"])
    totals_data.append(["Total Due:", f"${invoice.total:,.2f}"])
    if invoice.amount_paid and invoice.amount_paid > 0:
        balance = invoice.total - invoice.amount_paid
        totals_data.append(["Amount Paid:", f"${invoice.amount_paid:,.2f}"])
        totals_data.append(["Balance Due:", f"${balance:,.2f}"])

    totals_table = Table(totals_data, colWidths=[4.5 * inch, 2 * inch])
    totals_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ]))
    content.append(totals_table)
    content.append(Spacer(1, 0.3 * inch))

    # ---- Payment Instructions / Terms ----
    if settings and settings.invoice_terms:
        content.append(Paragraph("PAYMENT INSTRUCTIONS", heading_style))
        content.append(Spacer(1, 0.05 * inch))
        content.append(Paragraph(esc(settings.invoice_terms), normal_style))

    doc.build(content)
    pdf_buffer.seek(0)
    return pdf_buffer
