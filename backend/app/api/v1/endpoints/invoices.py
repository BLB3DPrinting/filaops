"""Invoice API endpoints."""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.models.user import User
from app.models.sales_order import SalesOrder
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate, InvoiceResponse, InvoiceListResponse
from app.services import invoice_service

router = APIRouter(prefix="/invoices", tags=["Invoices"])


def _build_invoice_response(invoice, db) -> dict:
    """Build InvoiceResponse dict from Invoice model."""
    order_number = None
    if invoice.sales_order_id:
        order = db.query(SalesOrder).filter(SalesOrder.id == invoice.sales_order_id).first()
        order_number = order.order_number if order else None

    amount_due = float(invoice.total - (invoice.amount_paid or 0))

    return {
        **{c.name: getattr(invoice, c.name) for c in invoice.__table__.columns},
        "lines": [
            {c.name: getattr(line, c.name) for c in line.__table__.columns}
            for line in invoice.lines
        ],
        "order_number": order_number,
        "amount_due": amount_due,
    }


@router.post("", response_model=InvoiceResponse)
def create_invoice(
    data: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoice = invoice_service.create_invoice(db, data.sales_order_id)
    return _build_invoice_response(invoice, db)


@router.get("", response_model=list[InvoiceListResponse])
def list_invoices(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoices = invoice_service.list_invoices(
        db, status=status, customer_search=search, limit=limit, offset=offset,
    )
    results = []
    for inv in invoices:
        order_number = None
        if inv.sales_order_id:
            order = db.query(SalesOrder).filter(SalesOrder.id == inv.sales_order_id).first()
            order_number = order.order_number if order else None
        results.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "sales_order_id": inv.sales_order_id,
            "order_number": order_number,
            "customer_name": inv.customer_name,
            "customer_company": inv.customer_company,
            "payment_terms": inv.payment_terms,
            "due_date": inv.due_date,
            "total": inv.total,
            "amount_paid": inv.amount_paid or 0,
            "amount_due": float(inv.total - (inv.amount_paid or 0)),
            "status": inv.status,
            "created_at": inv.created_at,
            "sent_at": inv.sent_at,
        })
    return results


@router.get("/summary")
def invoice_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    return invoice_service.get_invoice_summary(db)


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoice = invoice_service.get_invoice(db, invoice_id)
    return _build_invoice_response(invoice, db)


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(
    invoice_id: int,
    data: InvoiceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    if data.amount_paid is not None and data.payment_method:
        invoice = invoice_service.record_payment(
            db, invoice_id,
            amount=data.amount_paid,
            method=data.payment_method,
            reference=data.payment_reference,
        )
    else:
        invoice = invoice_service.get_invoice(db, invoice_id)
        if data.status:
            invoice.status = data.status
            db.commit()
            db.refresh(invoice)
    return _build_invoice_response(invoice, db)


@router.get("/{invoice_id}/pdf")
def download_invoice_pdf(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    pdf_buffer = invoice_service.generate_invoice_pdf(db, invoice_id)
    invoice = invoice_service.get_invoice(db, invoice_id)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{invoice.invoice_number}.pdf"'
        },
    )


@router.post("/{invoice_id}/send", response_model=InvoiceResponse)
def send_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    invoice = invoice_service.mark_sent(db, invoice_id)
    return _build_invoice_response(invoice, db)
