"""
Traceability Models - Serial Numbers, Material Lots, and Lot Consumption

Supports tiered traceability for B2B compliance:
- NONE: No tracking (B2C default)
- LOT: Batch tracking only (know which material batch used)
- SERIAL: Individual part tracking (each unit has unique ID)
- FULL: LOT + SERIAL + Certificate of Conformance (FDA/ISO ready)

For recalls:
- LOT level: "Recall all products using lot #PLA-2025-0042"
- SERIAL level: "Recall serial numbers SN-20251205-0001 through 0015"
"""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, Date, ForeignKey,
    Text, Boolean, Index
)
from sqlalchemy.orm import relationship

from app.db.base import Base


# =============================================================================
# TRACEABILITY LEVEL ENUM (stored as string for flexibility)
# =============================================================================
# NONE = No traceability (B2C default)
# LOT = Track material batches only
# SERIAL = Track individual units
# FULL = LOT + SERIAL + CoC generation


class SerialNumber(Base):
    """
    Individual unit tracking for finished goods.

    Generated when production order completes for products requiring serial tracking.
    Format: {prefix}YYYYMMDD-XXXX (e.g., SN-20251205-0001). The prefix is the
    shop-wide Company Settings value (app.services.serial_prefix).

    Links back to:
    - Production order (how it was made)
    - Material lots consumed (what went into it)
    - Sales order line (who bought it)
    """
    __tablename__ = "serial_numbers"

    id = Column(Integer, primary_key=True, index=True)

    # Serial number (unique identifier)
    serial_number = Column(String(50), unique=True, nullable=False, index=True)

    # What product is this?
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    # How was it made?
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)

    # Status: manufactured, in_stock, sold, shipped, returned, scrapped
    status = Column(String(30), default='manufactured', nullable=False, index=True)

    # Quality
    qc_passed = Column(Boolean, default=True, nullable=False)
    qc_date = Column(DateTime, nullable=True)
    qc_notes = Column(Text, nullable=True)

    # Sale tracking (populated when sold)
    sales_order_id = Column(Integer, ForeignKey("sales_orders.id"), nullable=True, index=True)
    sales_order_line_id = Column(Integer, ForeignKey("sales_order_lines.id"), nullable=True)
    sold_at = Column(DateTime, nullable=True)

    # Shipping tracking
    shipped_at = Column(DateTime, nullable=True)
    tracking_number = Column(String(100), nullable=True)

    # Return/warranty tracking
    returned_at = Column(DateTime, nullable=True)
    return_reason = Column(Text, nullable=True)

    # Timestamps
    manufactured_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    product = relationship("Product")
    production_order = relationship("ProductionOrder")
    sales_order = relationship("SalesOrder")
    lot_consumptions = relationship("ProductionLotConsumption", back_populates="serial_number")

    # Indexes for recall queries
    __table_args__ = (
        Index('ix_serial_product_status', 'product_id', 'status'),
        Index('ix_serial_manufactured_date', 'manufactured_at'),
    )

    def __repr__(self):
        return f"<SerialNumber {self.serial_number} ({self.status})>"

    @classmethod
    def generate_serial(cls, prefix: str, date: datetime = None) -> str:
        """
        Build the serial stem for a given prefix and date.

        Format: {prefix}YYYYMMDD- (caller appends the sequence, e.g. 0001).
        Pass the shop's configured prefix from
        app.services.serial_prefix.get_serial_prefix().

        Note: The sequence number must be determined by querying
        existing serials for that stem in the calling code.
        """
        if date is None:
            date = datetime.now(timezone.utc)
        date_str = date.strftime("%Y%m%d")
        return f"{prefix}{date_str}-"  # Caller appends sequence


class MaterialLot(Base):
    """
    Batch tracking for raw materials (filament, packaging, etc.).

    Created when materials are received from vendors.
    Tracks quantity remaining and links to production orders that consumed it.

    Format: {MATERIAL_CODE}-{YYYY}-{XXXX} (e.g., PLA-BLK-2025-0042)
    """
    __tablename__ = "material_lots"

    id = Column(Integer, primary_key=True, index=True)

    # Lot identifier (unique)
    lot_number = Column(String(100), unique=True, nullable=False, index=True)

    # What material is this?
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)

    # Where did it come from?
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True, index=True)
    purchase_order_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=True)
    vendor_lot_number = Column(String(100), nullable=True)  # Vendor's lot number

    # Quantities (in product's unit - usually kg for filament)
    quantity_received = Column(Numeric(12, 4), nullable=False)
    quantity_consumed = Column(Numeric(12, 4), default=0, nullable=False)
    quantity_scrapped = Column(Numeric(12, 4), default=0, nullable=False)
    quantity_adjusted = Column(Numeric(12, 4), default=0, nullable=False)  # Inventory adjustments

    @property
    def quantity_remaining(self) -> Decimal:
        """Calculate remaining quantity in lot."""
        return (
            self.quantity_received
            - self.quantity_consumed
            - self.quantity_scrapped
            + self.quantity_adjusted
        )

    # Status: active, depleted, quarantine, expired, recalled
    status = Column(String(30), default='active', nullable=False, index=True)

    # Quality/Compliance
    certificate_of_analysis = Column(Text, nullable=True)  # CoA data or file path
    coa_file_path = Column(String(500), nullable=True)
    inspection_status = Column(String(30), default='pending')  # pending, passed, failed, waived

    # Expiration tracking
    manufactured_date = Column(Date, nullable=True)  # When vendor made it
    expiration_date = Column(Date, nullable=True, index=True)
    received_date = Column(Date, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Cost tracking (for FIFO costing)
    unit_cost = Column(Numeric(10, 4), nullable=True)  # Cost per unit when received

    # Storage location
    location = Column(String(100), nullable=True)  # Shelf/bin location

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    product = relationship("Product")
    vendor = relationship("Vendor")
    purchase_order = relationship("PurchaseOrder")
    consumptions = relationship("ProductionLotConsumption", back_populates="material_lot")

    # Indexes for FIFO and recall queries
    __table_args__ = (
        Index('ix_lot_product_status', 'product_id', 'status'),
        Index('ix_lot_received_date', 'received_date'),
        Index('ix_lot_expiration', 'expiration_date'),
    )

    def __repr__(self):
        return f"<MaterialLot {self.lot_number} ({self.status}, {self.quantity_remaining} remaining)>"

    @classmethod
    def generate_lot_number(cls, material_code: str, year: int = None) -> str:
        """
        Generate lot number prefix for a material.

        Format: {MATERIAL_CODE}-{YYYY}-

        Note: The sequence number must be determined by querying
        existing lots for that material/year in the calling code.
        """
        if year is None:
            year = datetime.now(timezone.utc).year
        return f"{material_code}-{year}-"  # Caller appends sequence


class ProductionLotConsumption(Base):
    """
    Links production orders to the material lots they consumed.

    This is the key table for recall traceability:
    - Forward: "What material lots went into serial number X?"
    - Reverse: "What products used material lot Y?"

    Created when production starts and materials are reserved/consumed.
    """
    __tablename__ = "production_lot_consumptions"

    id = Column(Integer, primary_key=True, index=True)

    # The production order
    production_order_id = Column(Integer, ForeignKey("production_orders.id"), nullable=False, index=True)

    # The material lot consumed
    material_lot_id = Column(Integer, ForeignKey("material_lots.id"), nullable=False, index=True)

    # Optional: link to specific serial number (for FULL traceability)
    serial_number_id = Column(Integer, ForeignKey("serial_numbers.id"), nullable=True, index=True)

    # BOM line this consumption satisfies
    bom_line_id = Column(Integer, ForeignKey("bom_lines.id"), nullable=True)

    # Quantity consumed from this lot (in lot's unit)
    quantity_consumed = Column(Numeric(12, 4), nullable=False)

    # When was it consumed?
    consumed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    production_order = relationship("ProductionOrder")
    material_lot = relationship("MaterialLot", back_populates="consumptions")
    serial_number = relationship("SerialNumber", back_populates="lot_consumptions")

    # Index for recall queries
    __table_args__ = (
        Index('ix_consumption_lot_production', 'material_lot_id', 'production_order_id'),
    )

    def __repr__(self):
        return f"<ProductionLotConsumption PO:{self.production_order_id} Lot:{self.material_lot_id} Qty:{self.quantity_consumed}>"


class CustomerTraceabilityProfile(Base):
    """
    Customer-level traceability requirements.

    Allows setting traceability level per customer (e.g., medical device customers
    require FULL traceability while B2C retail customers need NONE).

    Can also store customer-specific compliance requirements like:
    - Required certifications
    - CoC template preferences
    - Retention periods
    """
    __tablename__ = "customer_traceability_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # Which customer?
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False, index=True)

    # Traceability level: none, lot, serial, full
    traceability_level = Column(String(20), default='none', nullable=False)

    # Compliance requirements
    requires_coc = Column(Boolean, default=False)  # Certificate of Conformance
    requires_coa = Column(Boolean, default=False)  # Certificate of Analysis (material certs)
    requires_first_article = Column(Boolean, default=False)  # First Article Inspection

    # Document retention (days)
    record_retention_days = Column(Integer, default=2555)  # ~7 years default

    # Customer-specific lot/serial prefix (optional)
    custom_serial_prefix = Column(String(20), nullable=True)  # e.g., "ACME-"; not used yet: serials take the shop-wide prefix

    # Compliance standards
    compliance_standards = Column(String(255), nullable=True)  # e.g., "ISO 13485, FDA 21 CFR 820"

    # Notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationship
    user = relationship("User")

    def __repr__(self):
        return f"<CustomerTraceabilityProfile user:{self.user_id} level:{self.traceability_level}>"
