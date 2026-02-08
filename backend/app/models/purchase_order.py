"""
Purchase Order models for purchasing module
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, Numeric, ForeignKey, Date
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base


class PurchaseOrder(Base):
    """Purchase Order header model"""
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)

    # PO Number - auto-generated (PO-2025-001)
    po_number = Column(String(50), unique=True, nullable=False, index=True)

    # Vendor reference
    vendor_id = Column(Integer, ForeignKey('vendors.id'), nullable=False, index=True)

    # Status workflow: draft -> ordered -> shipped -> received -> closed
    # Also: cancelled
    status = Column(String(50), default="draft", nullable=False)

    # Dates
    order_date = Column(Date, nullable=True)  # When placed with vendor
    expected_date = Column(Date, nullable=True)  # Expected delivery
    shipped_date = Column(Date, nullable=True)  # When vendor shipped
    received_date = Column(Date, nullable=True)  # When we received

    # Shipping/tracking
    tracking_number = Column(String(200), nullable=True)
    carrier = Column(String(100), nullable=True)  # UPS, FedEx, etc.

    # Financials
    subtotal = Column(Numeric(18, 4), default=0, nullable=False)
    tax_amount = Column(Numeric(18, 4), default=0, nullable=False)
    shipping_cost = Column(Numeric(18, 4), default=0, nullable=False)
    total_amount = Column(Numeric(18, 4), default=0, nullable=False)

    # Payment
    payment_method = Column(String(100), nullable=True)  # Card, Check, etc.
    payment_reference = Column(String(200), nullable=True)  # Last 4, check #, etc.

    # Document storage (Google Drive links, etc.)
    document_url = Column(String(1000), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Audit
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    vendor = relationship("Vendor", backref="purchase_orders")
    lines = relationship("PurchaseOrderLine", back_populates="purchase_order", cascade="all, delete-orphan")
    documents = relationship("PurchaseOrderDocument", back_populates="purchase_order", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<PurchaseOrder {self.po_number}: {self.status}>"


class PurchaseOrderLine(Base):
    """Purchase Order line item model"""
    __tablename__ = "purchase_order_lines"

    id = Column(Integer, primary_key=True, index=True)

    # Parent PO
    purchase_order_id = Column(Integer, ForeignKey('purchase_orders.id', ondelete='CASCADE'), nullable=False, index=True)

    # Product reference
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, index=True)

    # Line number for ordering
    line_number = Column(Integer, nullable=False)

    # Quantities
    quantity_ordered = Column(Numeric(18, 4), nullable=False)
    quantity_received = Column(Numeric(18, 4), default=0, nullable=False)
    
    # Unit of Measure - the unit the item is purchased in (may differ from product's default unit)
    purchase_unit = Column(String(20), nullable=True)  # e.g., 'G', 'KG', 'EA', 'LB'

    # Pricing
    unit_cost = Column(Numeric(18, 4), nullable=False)
    line_total = Column(Numeric(18, 4), nullable=False)  # quantity * unit_cost

    # Notes for this line
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    purchase_order = relationship("PurchaseOrder", back_populates="lines")
    product = relationship("Product")

    def __repr__(self):
        return f"<PurchaseOrderLine {self.line_number}: {self.quantity_ordered}>"

