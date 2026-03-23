"""
Bill of Materials models
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Date, ForeignKey, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base

class BOM(Base):
    """Bill of Materials model - matches boms table"""
    __tablename__ = "boms"

    id = Column(Integer, primary_key=True, index=True)

    # Product reference
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)

    # BOM identifiers
    code = Column(String(50), nullable=True)  # BOM code
    name = Column(String(255), nullable=True)  # BOM name

    # BOM details
    version = Column(Integer, nullable=True, default=1)  # Integer version in DB
    revision = Column(String(10), nullable=True)  # Revision string
    active = Column(Boolean, default=True, nullable=False)  # 'active' not 'is_active'

    # Costs
    total_cost = Column(Numeric(18, 4), nullable=True)

    # Manufacturing
    assembly_time_minutes = Column(Integer, nullable=True)
    effective_date = Column(Date, nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    product = relationship("Product", back_populates="boms", foreign_keys=[product_id])
    lines = relationship("BOMLine", back_populates="bom", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<BOM {self.product.sku if self.product else 'N/A'} v{self.version}>"


class BOMLine(Base):
    """BOM Line model - matches bom_lines table"""
    __tablename__ = "bom_lines"
    __table_args__ = (
        UniqueConstraint("bom_id", "component_id", name="uq_bom_lines_bom_component"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # References
    bom_id = Column(Integer, ForeignKey('boms.id'), nullable=False)
    component_id = Column(Integer, ForeignKey('products.id'), nullable=False)

    # Line details
    sequence = Column(Integer, nullable=True)  # 'sequence' not 'line_number'
    quantity = Column(Numeric(18, 4), nullable=False)
    unit = Column(String(20), default='EA', nullable=False)  # Explicit UOM: EA, kg, HR, m, etc.

    # Consumption stage - when should this item be consumed?
    # 'production' = consume at complete_print (filament, raw materials)
    # 'shipping' = consume at buy_label (boxes, packaging)
    consume_stage = Column(String(20), default='production', nullable=False)

    # Cost-only flag: if True, this line is for costing only and won't allocate inventory
    # Use for overhead, machine time, labor items
    is_cost_only = Column(Boolean, default=False, nullable=False)

    # Scrap/waste
    scrap_factor = Column(Numeric(5, 2), default=0, nullable=True)  # 'scrap_factor' not 'scrap_percentage'

    # Notes
    notes = Column(Text, nullable=True)

    # Relationships
    bom = relationship("BOM", back_populates="lines")
    component = relationship("Product", foreign_keys=[component_id])

    def __repr__(self):
        return f"<BOMLine {self.bom.product.sku if self.bom and self.bom.product else 'N/A'}-{self.sequence}>"
