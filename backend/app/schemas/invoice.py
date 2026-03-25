"""Invoice Pydantic schemas."""
from pydantic import BaseModel
from typing import Optional, List
from datetime import date, datetime
from decimal import Decimal


class InvoiceLineResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    sku: Optional[str] = None
    description: str
    quantity: Decimal
    unit_price: Decimal
    base_price: Optional[Decimal] = None
    discount_percent: Optional[Decimal] = None
    line_total: Decimal

    class Config:
        from_attributes = True


class InvoiceCreate(BaseModel):
    sales_order_id: int


class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    amount_paid: Optional[Decimal] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None


class InvoiceResponse(BaseModel):
    id: int
    invoice_number: str
    sales_order_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_company: Optional[str] = None
    bill_to_line1: Optional[str] = None
    bill_to_city: Optional[str] = None
    bill_to_state: Optional[str] = None
    bill_to_zip: Optional[str] = None
    payment_terms: str
    due_date: date
    subtotal: Decimal
    discount_amount: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    shipping_amount: Decimal = Decimal("0")
    total: Decimal
    status: str
    amount_paid: Decimal = Decimal("0")
    paid_at: Optional[datetime] = None
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    external_invoice_id: Optional[str] = None
    external_invoice_url: Optional[str] = None
    external_provider: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    sent_at: Optional[datetime] = None
    pdf_path: Optional[str] = None
    lines: List[InvoiceLineResponse] = []
    order_number: Optional[str] = None
    amount_due: Decimal = Decimal("0")

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    id: int
    invoice_number: str
    sales_order_id: Optional[int] = None
    order_number: Optional[str] = None
    customer_name: Optional[str] = None
    customer_company: Optional[str] = None
    payment_terms: str
    due_date: date
    total: Decimal
    amount_paid: Decimal = Decimal("0")
    amount_due: Decimal = Decimal("0")
    status: str
    created_at: datetime
    sent_at: Optional[datetime] = None

    class Config:
        from_attributes = True
