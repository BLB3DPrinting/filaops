"""
Product model - unified item management for products, components, and supplies
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Text, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class Product(Base):
    """
    Unified item model for all inventory-tracked items:
    - finished_good: Products sold to customers
    - component: Parts used in BOMs (e.g., inserts, hardware)
    - supply: Consumables (e.g., filament, packaging)
    - service: Non-physical items (e.g., machine time)
    """
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    legacy_sku = Column(String(50), nullable=True, index=True)  # Old SKU for Squarespace mapping
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Unit of Measure - THREE FIELDS for proper cost handling
    # See docs/AI_DIRECTIVE_UOM_COSTS.md for complete documentation.
    #
    # - unit: Storage/consumption unit (G for filament, EA for hardware)
    # - purchase_uom: Purchasing unit (KG for filament, BOX for hardware)
    # - purchase_factor: Conversion (1 purchase_uom = X unit). REQUIRED if purchase_uom != unit.
    #
    # Example: Filament
    #   unit='G', purchase_uom='KG', purchase_factor=1000
    #   Purchase: 3 KG @ $20/KG
    #   Transaction: 3000 G @ $0.02/G = $60 total
    #
    unit = Column(String(20), default='EA')  # Storage/consumption unit
    purchase_uom = Column(String(20), default='EA')  # Purchase unit
    purchase_factor = Column(Numeric(18, 6), nullable=True,
                             comment='Conversion: 1 purchase_uom = X unit. E.g., 1000 for KG->G')

    # Item classification
    item_type = Column(String(20), default='finished_good', nullable=False)  # finished_good, component, supply, service
    procurement_type = Column(String(20), default='buy', nullable=False)  # 'make', 'buy', 'make_or_buy'
    category_id = Column(Integer, ForeignKey("item_categories.id"), nullable=True)

    # Material link (for supply items that are materials/filament)
    # When set, this product represents a specific material+color combo
    material_type_id = Column(Integer, ForeignKey("material_types.id"), nullable=True)
    color_id = Column(Integer, ForeignKey("colors.id"), nullable=True)

    # Cost tracking
    cost_method = Column(String(20), default='average')  # fifo, average, standard
    standard_cost = Column(Numeric(18, 4), nullable=True)  # For standard costing
    average_cost = Column(Numeric(18, 4), nullable=True)  # Running average
    last_cost = Column(Numeric(18, 4), nullable=True)  # Most recent purchase cost

    # Pricing
    selling_price = Column(Numeric(18, 4), nullable=True)

    # Physical properties (dimensions in imperial units)
    weight_oz = Column(Numeric(8, 2), nullable=True)  # Weight in ounces
    length_in = Column(Numeric(8, 2), nullable=True)  # Length in inches
    width_in = Column(Numeric(8, 2), nullable=True)  # Width in inches
    height_in = Column(Numeric(8, 2), nullable=True)  # Height in inches

    # Purchasing & Inventory Management
    lead_time_days = Column(Integer, nullable=True)  # Supplier lead time
    min_order_qty = Column(Numeric(10, 2), nullable=True)  # Minimum order quantity
    reorder_point = Column(Numeric(10, 2), nullable=True)  # When to reorder (for stocked items)
    safety_stock = Column(Numeric(18, 4), default=0)  # MRP safety stock buffer
    preferred_vendor_id = Column(Integer, ForeignKey('vendors.id', ondelete='SET NULL'), nullable=True, index=True)

    # Stocking policy: determines how inventory is managed
    # - 'stocked': Keep minimum on hand, reorder at reorder_point (proactive)
    # - 'on_demand': Only order when MRP shows demand (reactive)
    stocking_policy = Column(String(20), default='on_demand', nullable=False)

    # Identifiers
    upc = Column(String(50), nullable=True)  # UPC/barcode

    # Product type
    type = Column(String(20), default='standard', nullable=False)  # 'standard' | 'custom'

    # 3D Printing
    gcode_file_path = Column(String(500), nullable=True)  # Path to GCODE file

    # Product Image
    image_url = Column(String(500), nullable=True)  # URL to product image

    # Visibility & Sales Channels
    is_public = Column(Boolean, default=True)  # Show on public storefront?
    sales_channel = Column(String(20), default='public')  # 'public' | 'b2b' | 'internal'
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='SET NULL'), nullable=True, index=True)  # Restrict to specific customer (B2B)

    # Flags
    is_raw_material = Column(Boolean, default=False)
    has_bom = Column(Boolean, default=False)
    track_lots = Column(Boolean, default=False)
    track_serials = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    # External IDs
    woocommerce_product_id = Column(BigInteger, nullable=True)
    squarespace_product_id = Column(String(50), nullable=True)  # Squarespace product ID

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    boms = relationship("BOM", back_populates="product", foreign_keys="BOM.product_id")
    inventory_items = relationship("Inventory", back_populates="product")
    production_orders = relationship("ProductionOrder", back_populates="product")
    quotes = relationship("Quote", back_populates="product")  # For auto-created custom products
    item_category = relationship("ItemCategory", back_populates="products")
    routings = relationship("Routing", back_populates="product")

    # Spool tracking (for filament/materials)
    spools = relationship("MaterialSpool", back_populates="product")
    
    # Material relationships (for supply items that are materials)
    material_type = relationship("MaterialType", foreign_keys=[material_type_id])
    color = relationship("Color", foreign_keys=[color_id])

    def __repr__(self):
        return f"<Product {self.sku}: {self.name}>"
