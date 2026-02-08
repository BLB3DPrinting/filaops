"""
Inventory models
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Date, ForeignKey, Text, Boolean, Computed
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base


class InventoryLocation(Base):
    """Inventory Location model - matches inventory_locations table"""
    __tablename__ = "inventory_locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=True)
    type = Column(String(50), nullable=True)  # warehouse, shelf, bin, etc.
    parent_id = Column(Integer, ForeignKey('inventory_locations.id'), nullable=True)
    active = Column(Boolean, default=True, nullable=True)

    # Self-referential relationship for hierarchy
    parent = relationship("InventoryLocation", remote_side=[id], backref="children")

    # Inventory in this location
    inventory_items = relationship("Inventory", back_populates="location")

    def __repr__(self):
        return f"<InventoryLocation {self.code}: {self.name}>"


class Inventory(Base):
    """Inventory model - matches inventory table"""
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, index=True)

    # References
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    location_id = Column(Integer, ForeignKey('inventory_locations.id'), nullable=False)

    # Quantities
    on_hand_quantity = Column(Numeric(10, 2), default=0, nullable=False)
    allocated_quantity = Column(Numeric(10, 2), default=0, nullable=False)
    # available_quantity is a computed column (on_hand - allocated)
    available_quantity = Column(Numeric(10, 2), Computed("on_hand_quantity - allocated_quantity"))

    # Metadata
    last_counted = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    product = relationship("Product", back_populates="inventory_items")
    location = relationship("InventoryLocation", back_populates="inventory_items")

    def __repr__(self):
        return f"<Inventory {self.product.sku if self.product else 'N/A'}: {self.available_quantity}>"


class InventoryTransaction(Base):
    """Inventory Transaction model - matches inventory_transactions table"""
    __tablename__ = "inventory_transactions"

    id = Column(Integer, primary_key=True, index=True)

    # References
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False)
    location_id = Column(Integer, ForeignKey('inventory_locations.id'), nullable=True)
    journal_entry_id = Column(Integer, ForeignKey('gl_journal_entries.id', ondelete='SET NULL'), nullable=True)

    # Transaction details
    transaction_type = Column(String(50), nullable=False)
    # receipt, shipment, adjustment, consumption, transfer, reservation, scrap

    reference_type = Column(String(50), nullable=True)
    # sales_order, purchase_order, production_order, print_job, adjustment

    reference_id = Column(Integer, nullable=True)

    # Quantities
    quantity = Column(Numeric(18, 4), nullable=False)

    # Tracking
    lot_number = Column(String(100), nullable=True)
    serial_number = Column(String(100), nullable=True)

    # Costs - SINGLE SOURCE OF TRUTH
    # cost_per_unit: Cost per unit in transaction's unit ($/G for materials, $/EA for discrete)
    # total_cost: Pre-calculated at creation time. UI displays this directly - NO client-side math.
    # See docs/AI_DIRECTIVE_UOM_COSTS.md for details.
    cost_per_unit = Column(Numeric(18, 4), nullable=True)
    total_cost = Column(Numeric(18, 4), nullable=True,
                        comment='Pre-calculated: quantity * cost_per_unit. UI displays directly.')
    
    # Unit of measure for quantity - STORED, not inferred from product
    unit = Column(String(20), nullable=True,
                  comment='Unit for quantity (G, EA, BOX). Stored at creation, not looked up.')

    # Notes
    notes = Column(Text, nullable=True)
    reason_code = Column(String(50), nullable=True)  # Links to adjustment_reasons.code

    # Negative Inventory Approval (for transactions that would cause negative inventory)
    requires_approval = Column(Boolean, default=False, nullable=False)
    approval_reason = Column(Text, nullable=True)
    approved_by = Column(String(100), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # Metadata
    # transaction_date: User-entered date when the transaction actually occurred
    # (e.g., when goods were physically received, not when entered in system)
    # Distinct from created_at which is always the system entry timestamp
    transaction_date = Column(Date, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(String(100), nullable=True)

    # Relationships
    location = relationship("InventoryLocation")
    product = relationship("Product")
    journal_entry = relationship("GLJournalEntry")

    def __repr__(self):
        return f"<InventoryTransaction {self.transaction_type}: {self.quantity}>"
