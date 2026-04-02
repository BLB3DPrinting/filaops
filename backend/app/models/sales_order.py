"""
Sales Order Model

Represents customer orders converted from approved quotes
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text, Boolean, CheckConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class SalesOrder(Base):
    """Sales Order - Customer order created from accepted quote"""
    __tablename__ = "sales_orders"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Note: unique constraint removed - database doesn't allow multiple NULLs in unique indexes
    # Business logic in quote conversion ensures one quote -> one order
    quote_id = Column(Integer, ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True, index=True)

    # Order Identification
    order_number = Column(String(50), unique=True, nullable=False, index=True)  # SO-2025-001

    # Order Type & Source (for hybrid architecture)
    order_type = Column(String(20), nullable=False, default='quote_based', index=True)
    # 'quote_based' = Single custom product from portal quote
    # 'line_item' = Multi-product order from marketplace (Squarespace/WooCommerce)

    source = Column(String(50), nullable=False, default='portal', index=True)
    # 'portal' | 'squarespace' | 'woocommerce' | 'manual'

    source_order_id = Column(String(255), nullable=True, index=True)
    # External order ID from marketplace (e.g., Squarespace order number)

    # Product Information (copied from quote)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    product_name = Column(String(255), nullable=True)
    quantity = Column(Integer, nullable=False)
    material_type = Column(String(50), nullable=False)  # PLA, PETG, ABS, ASA, TPU
    color = Column(String(50), nullable=True)  # Color from quote
    finish = Column(String(50), nullable=False, default="standard")  # standard, smooth, painted

    # Pricing (locked from quote at conversion time)
    unit_price = Column(Numeric(10, 2), nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    tax_amount = Column(Numeric(10, 2), nullable=True, default=0.00)
    tax_rate = Column(Numeric(5, 4), nullable=True)  # Tax rate at time of order (e.g., 0.0825)
    tax_name = Column(String(100), nullable=True)  # human-readable snapshot, e.g. "GST 5%"
    is_taxable = Column(Boolean, nullable=True, default=True)  # Whether tax applies
    shipping_cost = Column(Numeric(10, 2), nullable=True, default=0.00)
    grand_total = Column(Numeric(10, 2), nullable=False)  # total + tax + shipping

    # Order Status (Customer-Facing)
    # Lifecycle: draft → pending_payment → confirmed → in_production → ready_to_ship → shipped → delivered → completed
    # Alternative paths: payment_failed, partially_shipped, on_hold, cancelled
    # Status meanings:
    #   - draft: Order being created/edited
    #   - pending_payment: Submitted, awaiting payment
    #   - payment_failed: Payment declined, needs retry
    #   - confirmed: Payment received, ready for production planning
    #   - in_production: At least one WO is in progress
    #   - ready_to_ship: All WOs complete and QC passed, awaiting shipment
    #   - partially_shipped: Multi-line order with some items shipped
    #   - shipped: All items shipped
    #   - delivered: Carrier confirmed delivery
    #   - completed: Order fully closed
    #   - on_hold: Production/shipment paused
    #   - cancelled: Order terminated
    status = Column(String(50), nullable=False, default="draft", index=True)

    # Payment Status
    payment_status = Column(String(50), nullable=False, default="pending", index=True)
    # pending, paid, partial, refunded, cancelled
    payment_method = Column(String(50), nullable=True)  # credit_card, paypal, manual, cash, check
    payment_transaction_id = Column(String(255), nullable=True)
    paid_at = Column(DateTime, nullable=True)

    # Fulfillment Status (Internal - Shipping/Logistics)
    # Decouples production completion from shipping readiness
    # Values: pending, ready, picking, packing, shipped, delivered
    fulfillment_status = Column(String(50), nullable=False, default="pending", index=True)

    # Production Information
    rush_level = Column(String(20), nullable=False, default="standard")
    # standard, rush, super_rush, urgent
    estimated_completion_date = Column(DateTime, nullable=True)
    actual_completion_date = Column(DateTime, nullable=True)

    # Customer Information (for quote-based orders)
    customer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name = Column(String(200), nullable=True)
    customer_email = Column(String(255), nullable=True)
    customer_phone = Column(String(30), nullable=True)

    # Shipping Information
    shipping_address_line1 = Column(String(255), nullable=True)
    shipping_address_line2 = Column(String(255), nullable=True)
    shipping_city = Column(String(100), nullable=True)
    shipping_state = Column(String(50), nullable=True)
    shipping_zip = Column(String(20), nullable=True)
    shipping_country = Column(String(100), nullable=True, default="USA")

    tracking_number = Column(String(255), nullable=True)
    carrier = Column(String(100), nullable=True)  # USPS, FedEx, UPS
    shipped_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)

    # Notes
    customer_notes = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)
    production_notes = Column(Text, nullable=True)

    # Cancellation
    cancelled_at = Column(DateTime, nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Close Short (partial fulfillment accepted)
    closed_short = Column(Boolean, nullable=False, default=False)
    closed_short_at = Column(DateTime, nullable=True)
    close_short_reason = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)  # When external order was submitted for review

    # MRP Tracking (for Material Requirements Planning)
    mrp_status = Column(String(50), nullable=True, index=True)
    # Values: null (not processed), "pending", "processed", "error"
    mrp_run_id = Column(Integer, ForeignKey("mrp_runs.id", ondelete="SET NULL"), nullable=True, index=True)
    # Links to the MRP run that processed this order

    # Relationships
    user = relationship("User", back_populates="sales_orders", foreign_keys=[user_id])
    customer = relationship("User", foreign_keys=[customer_id])  # Customer record (optional)
    quote = relationship("Quote", back_populates="sales_order", uselist=False)
    product = relationship("Product", foreign_keys=[product_id])
    lines = relationship("SalesOrderLine", back_populates="sales_order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="sales_order", cascade="all, delete-orphan", order_by="Payment.payment_date.desc()")
    mrp_run = relationship("MRPRun", foreign_keys=[mrp_run_id])

    def __repr__(self):
        return f"<SalesOrder {self.order_number} - {self.status}>"

    @property
    def is_cancellable(self) -> bool:
        """Check if order can be cancelled"""
        return self.status in ["pending_confirmation", "draft", "pending_payment", "payment_failed", "confirmed", "on_hold"]

    @property
    def is_paid(self) -> bool:
        """Check if order is fully paid"""
        return self.payment_status == "paid"

    @property
    def can_start_production(self) -> bool:
        """Check if order can start production"""
        return (
            self.status == "confirmed" and
            self.payment_status in ["paid", "partial"]
        )
    
    @property
    def is_ready_to_ship(self) -> bool:
        """Check if order is ready for shipping"""
        return self.fulfillment_status == "ready" and self.status == "ready_to_ship"
    
    @property
    def is_complete(self) -> bool:
        """Check if order is fully complete"""
        return self.status in ["completed", "delivered"]


class SalesOrderLine(Base):
    """
    Sales Order Line - Individual line items for marketplace orders

    Used when order_type = 'line_item' (Squarespace, WooCommerce, manual multi-item orders)
    Each line represents one product with quantity and pricing
    """
    __tablename__ = "sales_order_lines"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign Keys
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    material_inventory_id = Column(Integer, ForeignKey("material_inventory.id"), nullable=True, index=True)

    # Line Details (matching actual database schema)
    quantity = Column(Numeric(10, 2), nullable=False)
    unit_price = Column(Numeric(10, 2), nullable=False)
    discount = Column(Numeric(10, 2), nullable=True, default=0)
    tax_rate = Column(Numeric(5, 2), nullable=True, default=0)
    tax_name = Column(String(100), nullable=True)  # human-readable snapshot
    total = Column(Numeric(10, 2), nullable=False)  # quantity * unit_price - discount + tax
    allocated_quantity = Column(Numeric(10, 2), nullable=True, default=0)
    shipped_quantity = Column(Numeric(10, 2), nullable=True, default=0)
    original_quantity = Column(Numeric(10, 2), nullable=True)  # Pre-edit quantity (NULL = never edited)

    # Notes
    notes = Column(Text, nullable=True)

    # Audit
    created_by = Column(Integer, nullable=True)

    # Relationships
    sales_order = relationship("SalesOrder", back_populates="lines")
    product = relationship("Product")
    material_inventory = relationship("MaterialInventory")

    # Note: The database schema uses 'total' not 'total_price', and doesn't have
    # line_number, product_sku, product_name, or created_at columns.
    # These are computed in the API layer when building responses.

    # Exactly one of product_id or material_inventory_id must be set
    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL AND material_inventory_id IS NULL) OR "
            "(product_id IS NULL AND material_inventory_id IS NOT NULL)",
            name="ck_sol_product_or_material",
        ),
    )

    def __repr__(self):
        return f"<SalesOrderLine SO-{self.sales_order_id if self.sales_order_id else 'N/A'}-{self.id}>"
