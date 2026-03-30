"""
SQLAlchemy models for customer quotes and uploaded files

Handles quote requests, file uploads, and approval workflow
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Numeric, BigInteger, Boolean,
    DateTime, Date, ForeignKey, LargeBinary, func
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class Quote(Base):
    """
    Customer quote request for 3D printing

    Stores quote details, pricing, and approval workflow
    """
    __tablename__ = "quotes"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # User & Reference
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    quote_number = Column(String(50), unique=True, nullable=False, index=True)

    # Product Details
    product_name = Column(String(255), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    material_type = Column(String(50), nullable=True)  # PLA_BASIC, PLA_MATTE, PETG_HF, etc. (optional for admin quotes)
    color = Column(String(30), nullable=True)  # Color code: BLK, WHT, CHARCOAL, etc.
    finish = Column(String(50), default="standard")  # standard, smooth, painted
    
    # G-code file path (for production)
    gcode_file_path = Column(String(500), nullable=True)

    # Pricing (from Bambu Suite quoter)
    material_grams = Column(Numeric(10, 2), nullable=True)
    print_time_hours = Column(Numeric(10, 2), nullable=True)
    unit_price = Column(Numeric(10, 2), nullable=True)
    subtotal = Column(Numeric(10, 2), nullable=True)  # unit_price * quantity
    tax_rate = Column(Numeric(5, 4), nullable=True)  # e.g., 0.0825 for 8.25%
    tax_amount = Column(Numeric(10, 2), nullable=True)  # calculated tax
    tax_name = Column(String(100), nullable=True)  # human-readable snapshot, e.g. "GST 5%"
    total_price = Column(Numeric(10, 2), nullable=False)  # subtotal + tax (or just subtotal if no tax)
    margin_percent = Column(Numeric(5, 2), nullable=True)

    # Quote Image (product photo/render)
    image_data = Column(LargeBinary, nullable=True)
    image_filename = Column(String(255), nullable=True)
    image_mime_type = Column(String(100), nullable=True)

    # File Metadata
    file_format = Column(String(10), nullable=False)  # .3mf, .stl
    file_size_bytes = Column(BigInteger, nullable=False)
    dimensions_x = Column(Numeric(10, 2), nullable=True)  # mm
    dimensions_y = Column(Numeric(10, 2), nullable=True)  # mm
    dimensions_z = Column(Numeric(10, 2), nullable=True)  # mm

    # Workflow Status
    status = Column(String(50), nullable=False, default="pending", index=True)
    # Status values: pending, approved, rejected, accepted, expired, converted, cancelled
    approval_method = Column(String(50), nullable=True)  # auto, manual, customer
    approved_by = Column(Integer, nullable=True)  # Admin user ID
    approved_at = Column(DateTime(timezone=False), nullable=True)
    rejection_reason = Column(String(500), nullable=True)

    # Auto-Approval Flags
    auto_approved = Column(Boolean, nullable=False, default=False)
    auto_approve_eligible = Column(Boolean, nullable=False, default=False)
    requires_review_reason = Column(String(255), nullable=True)

    # Rush Order
    rush_level = Column(String(20), default="standard")  # standard, rush, super_rush, urgent
    requested_delivery_date = Column(Date, nullable=True)

    # Customer Notes
    customer_notes = Column(String(1000), nullable=True)
    admin_notes = Column(String(1000), nullable=True)
    internal_notes = Column(String(1000), nullable=True)  # Internal processing notes
    
    # Customer Contact (for portal quotes where user_id is generic)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # Link to customer record
    customer_email = Column(String(255), nullable=True)  # Email for quote follow-up
    customer_name = Column(String(200), nullable=True)   # Name if not logged in

    # Shipping Address (captured when quote is accepted)
    shipping_name = Column(String(200), nullable=True)
    shipping_address_line1 = Column(String(255), nullable=True)
    shipping_address_line2 = Column(String(255), nullable=True)
    shipping_city = Column(String(100), nullable=True)
    shipping_state = Column(String(50), nullable=True)
    shipping_zip = Column(String(20), nullable=True)
    shipping_country = Column(String(100), nullable=True, default="USA")
    shipping_phone = Column(String(30), nullable=True)

    # Shipping Selection (from EasyPost)
    shipping_rate_id = Column(String(100), nullable=True)  # EasyPost rate ID
    shipping_carrier = Column(String(50), nullable=True)   # USPS, UPS, FedEx
    shipping_service = Column(String(100), nullable=True)  # Priority, Ground, etc.
    shipping_cost = Column(Numeric(10, 2), nullable=True)  # Selected shipping cost

    # Conversion to Order
    sales_order_id = Column(Integer, nullable=True)
    converted_at = Column(DateTime(timezone=False), nullable=True)

    # Auto-Created Product (when quote is accepted)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=False), nullable=False)

    # Relationships
    user = relationship("User", back_populates="quotes", foreign_keys=[user_id])
    customer = relationship("User", foreign_keys=[customer_id])  # Link to customer record (optional)
    files = relationship("QuoteFile", back_populates="quote", cascade="all, delete-orphan")
    sales_order = relationship("SalesOrder", back_populates="quote", uselist=False)
    product = relationship("Product", back_populates="quotes")  # Auto-created custom product
    materials = relationship("QuoteMaterial", back_populates="quote", cascade="all, delete-orphan")  # Multi-material breakdown
    lines = relationship("QuoteLine", back_populates="quote", cascade="all, delete-orphan",
                         order_by="QuoteLine.line_number")  # Multi-line-item support

    # Customer discount (from PRO price level, snapshotted at quote creation)
    discount_percent = Column(Numeric(5, 2), nullable=True)

    def __repr__(self):
        return f"<Quote(id={self.id}, number={self.quote_number}, status={self.status}, price=${self.total_price})>"

    @property
    def is_expired(self) -> bool:
        """Check if quote has expired"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires = self.expires_at.replace(tzinfo=None) if self.expires_at and self.expires_at.tzinfo else self.expires_at
        return now > expires

    @property
    def has_image(self) -> bool:
        """Check if quote has an image attached"""
        return self.image_data is not None

    @property
    def is_auto_approvable(self) -> bool:
        """
        Check if quote meets auto-approval criteria

        Auto-approve if:
        1. Total price < $50
        2. File size < 100MB
        3. If ABS/ASA: dimensions < 200x200x100mm
        """
        # Price check
        if self.total_price >= 50:
            return False

        # File size check (100MB)
        if self.file_size_bytes > 100 * 1024 * 1024:
            return False

        # ABS/ASA dimension check
        if self.material_type in ['ABS', 'ASA']:
            if (self.dimensions_x and self.dimensions_x > 200) or \
               (self.dimensions_y and self.dimensions_y > 200) or \
               (self.dimensions_z and self.dimensions_z > 100):
                return False

        return True

    @classmethod
    def generate_quote_number(cls, year: int = None) -> str:
        """
        Generate next quote number in format Q-YYYY-NNN

        Args:
            year: Year for quote (default: current year)

        Returns:
            Quote number like 'Q-2024-001'
        """
        if year is None:
            year = datetime.now(timezone.utc).year

        # This will be implemented in the endpoint to query the database
        # for the last quote number of the year
        return f"Q-{year}-001"  # Placeholder


class QuoteFile(Base):
    """
    Uploaded 3D model file associated with a quote

    Stores file metadata and processing status
    """
    __tablename__ = "quote_files"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Quote Reference
    quote_id = Column(Integer, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True)

    # File Information
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), unique=True, nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    file_format = Column(String(10), nullable=False)  # .3mf, .stl
    mime_type = Column(String(100), nullable=False)

    # File Validation
    is_valid = Column(Boolean, nullable=False, default=True)
    validation_errors = Column(String(1000), nullable=True)

    # File Hash (for deduplication)
    file_hash = Column(String(64), nullable=False, index=True)  # SHA256

    # Metadata from file
    model_name = Column(String(255), nullable=True)
    vertex_count = Column(Integer, nullable=True)  # For STL files
    triangle_count = Column(Integer, nullable=True)  # For STL files

    # Bambu Suite Processing
    bambu_file_id = Column(String(100), nullable=True)  # ID in Bambu Suite
    processed = Column(Boolean, nullable=False, default=False)
    processing_error = Column(String(500), nullable=True)

    # Timestamps
    uploaded_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())
    processed_at = Column(DateTime(timezone=False), nullable=True)

    # Relationships
    quote = relationship("Quote", back_populates="files")

    def __repr__(self):
        return f"<QuoteFile(id={self.id}, filename={self.original_filename}, format={self.file_format})>"

    @property
    def file_size_mb(self) -> float:
        """Get file size in megabytes"""
        return self.file_size_bytes / (1024 * 1024)


class QuoteMaterial(Base):
    """
    Per-material breakdown for multi-material/multi-color quotes.

    For multi-color 3MF prints (using AMS), this stores each filament slot's
    material type, color, and weight. This enables accurate BOM creation
    with separate inventory tracking per material.

    For single-color quotes, there will be one QuoteMaterial row with
    the total weight.
    """
    __tablename__ = "quote_materials"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Quote Reference
    quote_id = Column(Integer, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True)

    # Slot Information (for multi-material)
    slot_number = Column(Integer, nullable=False, default=1)  # 1-indexed AMS slot
    is_primary = Column(Boolean, nullable=False, default=False)  # Primary/main color

    # Material Information
    material_type = Column(String(50), nullable=False)  # PLA_BASIC, PETG_HF, etc.
    color_code = Column(String(30), nullable=True)  # BLK, WHT, CHARCOAL, etc.
    color_name = Column(String(100), nullable=True)  # "Black", "White", etc.
    color_hex = Column(String(7), nullable=True)  # #000000, #FFFFFF, etc.

    # Weight (from slicer)
    material_grams = Column(Numeric(10, 2), nullable=False)  # Weight in grams for this slot

    # Timestamps
    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())

    # Relationships
    quote = relationship("Quote", back_populates="materials")

    def __repr__(self):
        return f"<QuoteMaterial(id={self.id}, slot={self.slot_number}, material={self.material_type}, color={self.color_code}, grams={self.material_grams})>"


class QuoteLine(Base):
    """
    Line item in a multi-product quote.

    Each line represents one product with its own quantity, price, and optional
    material/color. The quote header holds customer info, tax, shipping, and status.

    For legacy single-item quotes (no lines), the header-level product fields
    are used instead. The service layer checks len(quote.lines) to decide.
    """
    __tablename__ = "quote_lines"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)

    line_number = Column(Integer, nullable=False, default=1)
    product_name = Column(String(255), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Numeric(10, 2), nullable=False)
    discount_percent = Column(Numeric(5, 2), nullable=True)
    total = Column(Numeric(10, 2), nullable=False)  # quantity * unit_price (after discount)

    material_type = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    notes = Column(String(1000), nullable=True)

    created_at = Column(DateTime(timezone=False), nullable=False, server_default=func.now())

    # Relationships
    quote = relationship("Quote", back_populates="lines")
    product = relationship("Product")

    def __repr__(self):
        return f"<QuoteLine(id={self.id}, line={self.line_number}, product={self.product_name}, qty={self.quantity})>"
