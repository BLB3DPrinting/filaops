"""
Material management models for quote-to-order workflow

Handles material types, colors, and inventory tracking for 3D printing materials.
Designed to support FDM filaments now, with extensibility for resin/powder later.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, 
    ForeignKey, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class MaterialType(Base):
    """
    Material type definitions (e.g., PLA Basic, PLA Matte, PETG-HF, ASA)
    
    These are the options customers see in the first dropdown.
    Each has specific print properties and pricing.
    """
    __tablename__ = "material_types"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Identification
    code = Column(String(50), unique=True, nullable=False, index=True)  # PLA_BASIC, PLA_MATTE, PETG_HF
    name = Column(String(100), nullable=False)  # "PLA Basic", "PLA Matte"
    
    # Base material category (for print settings inheritance)
    base_material = Column(String(20), nullable=False, index=True)  # PLA, PETG, ABS, ASA, TPU
    
    # Process type (for future expansion)
    process_type = Column(String(20), nullable=False, default='FDM')  # FDM, RESIN, SLS
    
    # Physical properties
    density = Column(Numeric(6, 4), nullable=False)  # g/cm³ (e.g., 1.24 for PLA)
    
    # Print settings
    volumetric_flow_limit = Column(Numeric(6, 2), nullable=True)  # mm³/s max flow rate
    nozzle_temp_min = Column(Integer, nullable=True)  # °C
    nozzle_temp_max = Column(Integer, nullable=True)  # °C
    bed_temp_min = Column(Integer, nullable=True)  # °C
    bed_temp_max = Column(Integer, nullable=True)  # °C
    requires_enclosure = Column(Boolean, default=False)  # ABS/ASA need enclosure
    filament_diameter = Column(Numeric(4, 2), nullable=False, default=1.75, server_default="1.75")  # mm (1.75 or 2.85)
    
    # Pricing
    base_price_per_kg = Column(Numeric(10, 2), nullable=False)  # Base cost from supplier
    price_multiplier = Column(Numeric(4, 2), default=1.0)  # Quote price multiplier vs PLA
    
    # Customer-facing
    description = Column(Text, nullable=True)  # "Matte finish, same strength as standard PLA"
    strength_rating = Column(Integer, nullable=True)  # 1-10 relative strength
    is_customer_visible = Column(Boolean, default=True)  # Show in portal dropdown
    display_order = Column(Integer, default=100)  # Sort order in dropdown
    
    # Status
    active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    material_colors = relationship("MaterialColor", back_populates="material_type", cascade="all, delete-orphan")
    inventory_items = relationship("MaterialInventory", back_populates="material_type")
    
    def __repr__(self):
        return f"<MaterialType {self.code}: {self.name}>"


class Color(Base):
    """
    Color definitions used across material types
    
    Colors are shared but not all colors available for all materials.
    MaterialColor junction table defines valid combinations.
    """
    __tablename__ = "colors"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Identification
    code = Column(String(30), unique=True, nullable=False, index=True)  # BLK, WHT, CHARCOAL
    name = Column(String(100), nullable=False)  # "Black", "Charcoal", "Mystic Magenta"
    
    # Display
    hex_code = Column(String(7), nullable=True)  # #000000 (nullable for multi-colors)
    hex_code_secondary = Column(String(7), nullable=True)  # For dual-color silks
    
    # Customer-facing
    display_order = Column(Integer, default=100)
    is_customer_visible = Column(Boolean, default=True)
    
    # Status
    active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    material_colors = relationship("MaterialColor", back_populates="color", cascade="all, delete-orphan")
    inventory_items = relationship("MaterialInventory", back_populates="color")
    
    def __repr__(self):
        return f"<Color {self.code}: {self.name}>"


class MaterialColor(Base):
    """
    Junction table: which colors are available for which material types
    
    Example: PLA Silk only has Gold, Mint, Champagne, White
             PLA Basic has 30+ colors
    """
    __tablename__ = "material_colors"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Foreign keys
    material_type_id = Column(Integer, ForeignKey("material_types.id", ondelete="CASCADE"), nullable=False)
    color_id = Column(Integer, ForeignKey("colors.id", ondelete="CASCADE"), nullable=False)
    
    # This specific combination
    is_customer_visible = Column(Boolean, default=True)  # Can hide specific combos
    display_order = Column(Integer, default=100)
    
    # Status
    active = Column(Boolean, default=True)
    
    # Relationships
    material_type = relationship("MaterialType", back_populates="material_colors")
    color = relationship("Color", back_populates="material_colors")
    
    # Unique constraint: one entry per material-color combo
    __table_args__ = (
        UniqueConstraint('material_type_id', 'color_id', name='uq_material_color'),
        Index('ix_material_colors_lookup', 'material_type_id', 'color_id'),
    )
    
    def __repr__(self):
        return f"<MaterialColor {self.material_type_id}-{self.color_id}>"


class MaterialInventory(Base):
    """
    Actual inventory: what material+color combinations you have in stock
    
    Links to the Product table for SKU, cost tracking, and BOM integration.
    This is what the BOM service uses to find the right material product.
    """
    __tablename__ = "material_inventory"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Material specification
    material_type_id = Column(Integer, ForeignKey("material_types.id"), nullable=False, index=True)
    color_id = Column(Integer, ForeignKey("colors.id"), nullable=False, index=True)
    
    # Link to Product table (for BOM, inventory tracking)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    
    # Direct SKU reference (in case product not yet created)
    sku = Column(String(50), nullable=False, unique=True, index=True)  # MAT-FDM-PLABASIC-BLK
    
    # Inventory status
    in_stock = Column(Boolean, default=True)  # Quick flag for dropdown filtering
    quantity_kg = Column(Numeric(10, 3), default=0)  # Current stock in kg
    reorder_point_kg = Column(Numeric(10, 3), default=1.0)  # Alert when below this
    
    # Costing (actual costs, may differ from MaterialType.base_price_per_kg)
    cost_per_kg = Column(Numeric(10, 2), nullable=True)  # What you actually paid
    last_purchase_date = Column(DateTime, nullable=True)
    last_purchase_price = Column(Numeric(10, 2), nullable=True)
    
    # Supplier info
    preferred_vendor = Column(String(100), nullable=True)
    vendor_sku = Column(String(100), nullable=True)  # Vendor's part number
    
    # Status
    active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    material_type = relationship("MaterialType", back_populates="inventory_items")
    color = relationship("Color", back_populates="inventory_items")
    product = relationship("Product", backref="material_inventory")
    
    # Unique constraint: one inventory entry per material-color combo
    __table_args__ = (
        UniqueConstraint('material_type_id', 'color_id', name='uq_material_inventory'),
        Index('ix_material_inventory_lookup', 'material_type_id', 'color_id'),
        Index('ix_material_inventory_stock', 'in_stock', 'active'),
    )
    
    def __repr__(self):
        return f"<MaterialInventory {self.sku}: {self.quantity_kg}kg>"
    
    @property
    def needs_reorder(self) -> bool:
        """Check if inventory is below reorder point"""
        return self.quantity_kg < self.reorder_point_kg
    
    @property
    def display_name(self) -> str:
        """Human-readable name combining material and color"""
        if self.material_type and self.color:
            return f"{self.material_type.name} - {self.color.name}"
        return self.sku
