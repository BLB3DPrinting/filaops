"""Invoice models for tracking billing and payments."""
from sqlalchemy import (
    Column, Integer, String, Numeric, Date, DateTime, ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(20), unique=True, nullable=False, index=True)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=True, index=True)
    customer_id = Column(Integer, nullable=True, index=True)
    customer_name = Column(String(200), nullable=True)
    customer_email = Column(String(200), nullable=True)
    customer_company = Column(String(200), nullable=True)

    # Billing address (snapshot)
    bill_to_line1 = Column(String(200), nullable=True)
    bill_to_city = Column(String(100), nullable=True)
    bill_to_state = Column(String(50), nullable=True)
    bill_to_zip = Column(String(20), nullable=True)

    # Terms and dates
    payment_terms = Column(String(20), nullable=False)
    due_date = Column(Date, nullable=False)

    # Amounts
    subtotal = Column(Numeric(12, 2), nullable=False)
    discount_amount = Column(Numeric(12, 2), server_default="0")
    tax_rate = Column(Numeric(5, 4), server_default="0")
    tax_amount = Column(Numeric(12, 2), server_default="0")
    shipping_amount = Column(Numeric(12, 2), server_default="0")
    total = Column(Numeric(12, 2), nullable=False)

    # Status: draft, sent, paid, overdue, cancelled
    status = Column(String(20), nullable=False, server_default="draft", index=True)

    # Payment
    amount_paid = Column(Numeric(12, 2), server_default="0")
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_method = Column(String(20), nullable=True)
    payment_reference = Column(String(200), nullable=True)

    # External integration
    external_invoice_id = Column(String(100), nullable=True)
    external_invoice_url = Column(String(500), nullable=True)
    external_provider = Column(String(20), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    pdf_path = Column(String(500), nullable=True)

    # Relationships
    lines = relationship("InvoiceLine", back_populates="invoice", cascade="all, delete-orphan")
    sales_order = relationship("SalesOrder", backref="invoices")

    def __repr__(self):
        return f"<Invoice(id={self.id}, number='{self.invoice_number}', status='{self.status}')>"


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, nullable=True)
    sku = Column(String(50), nullable=True)
    description = Column(String(200), nullable=False)
    quantity = Column(Numeric(12, 4), nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    base_price = Column(Numeric(12, 2), nullable=True)
    discount_percent = Column(Numeric(5, 2), nullable=True)
    line_total = Column(Numeric(12, 2), nullable=False)

    # Relationships
    invoice = relationship("Invoice", back_populates="lines")
