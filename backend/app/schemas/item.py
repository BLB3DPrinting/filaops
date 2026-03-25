"""
Item and Category Pydantic Schemas

Supports unified item management for:
- Finished goods (products sold to customers)
- Components (parts used in BOMs)
- Supplies (consumables like filament, packaging)
- Services (non-physical items like machine time)
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class ItemType(str, Enum):
    """Types of items in the system"""
    FINISHED_GOOD = "finished_good"  # Sellable products
    COMPONENT = "component"          # Parts used in assembly
    SUPPLY = "supply"                # Consumables and supplies
    SERVICE = "service"              # Non-physical services
    MATERIAL = "material"            # Raw materials (filament, sheet stock, etc.) - auto-configures UOM


class CostMethod(str, Enum):
    """Inventory costing methods"""
    FIFO = "fifo"
    AVERAGE = "average"
    STANDARD = "standard"


class ProcurementType(str, Enum):
    """How the item is obtained"""
    MAKE = "make"       # Manufactured in-house (has BOM/routing)
    BUY = "buy"         # Purchased from suppliers
    MAKE_OR_BUY = "make_or_buy"  # Can be either (flexible sourcing)


class StockingPolicy(str, Enum):
    """How inventory is managed for this item"""
    STOCKED = "stocked"       # Keep minimum on hand, reorder at reorder_point
    ON_DEMAND = "on_demand"   # Only order when MRP shows actual demand


# ============================================================================
# Item Category Schemas
# ============================================================================

class ItemCategoryBase(BaseModel):
    """Base category fields"""
    code: str = Field(..., min_length=1, max_length=50, description="Unique category code")
    name: str = Field(..., min_length=1, max_length=100, description="Category name")
    parent_id: Optional[int] = Field(None, description="Parent category ID for hierarchy")
    description: Optional[str] = Field(None, max_length=1000)
    sort_order: Optional[int] = Field(0, ge=0)
    is_active: Optional[bool] = Field(True)


class ItemCategoryCreate(ItemCategoryBase):
    """Create a new category"""
    pass


class ItemCategoryUpdate(BaseModel):
    """Update an existing category"""
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    parent_id: Optional[int] = None
    description: Optional[str] = Field(None, max_length=1000)
    sort_order: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None


class ItemCategoryResponse(ItemCategoryBase):
    """Category response with hierarchy info"""
    id: int
    parent_name: Optional[str] = None
    full_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ItemCategoryTreeNode(BaseModel):
    """Category with children for tree view"""
    id: int
    code: str
    name: str
    description: Optional[str] = None
    is_active: bool
    children: List["ItemCategoryTreeNode"] = []

    class Config:
        from_attributes = True


# Self-reference for tree nodes
ItemCategoryTreeNode.model_rebuild()


# ============================================================================
# Item (Product) Schemas
# ============================================================================

class ItemBase(BaseModel):
    """Base item fields"""
    sku: Optional[str] = Field(None, max_length=50, description="Unique SKU (auto-generated if not provided)")
    name: str = Field(..., min_length=1, max_length=255, description="Item name")
    description: Optional[str] = None
    
    # Unit of Measure - Two fields for proper cost handling
    # - unit: Storage/inventory unit (G for filament, EA for hardware)
    # - purchase_uom: Purchasing unit (KG for filament, EA for hardware)
    # Costs (standard_cost, etc.) are per PURCHASE unit
    unit: Optional[str] = Field("EA", max_length=20, description="Storage/inventory unit (G, EA, etc.)")
    purchase_uom: Optional[str] = Field("EA", max_length=20, description="Purchase unit - costs are per this unit (KG, EA, etc.)")

    # Classification
    item_type: ItemType = Field(ItemType.FINISHED_GOOD, description="Type of item")
    procurement_type: ProcurementType = Field(ProcurementType.BUY, description="How the item is procured")
    category_id: Optional[int] = Field(None, description="Category ID")

    # Costing
    cost_method: CostMethod = Field(CostMethod.AVERAGE, description="Costing method")
    standard_cost: Optional[Decimal] = Field(None, ge=0, decimal_places=6)
    selling_price: Optional[Decimal] = Field(None, ge=0, decimal_places=4)

    # Physical dimensions
    weight_oz: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    length_in: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    width_in: Optional[Decimal] = Field(None, ge=0, decimal_places=2)
    height_in: Optional[Decimal] = Field(None, ge=0, decimal_places=2)

    # Purchasing & Inventory
    lead_time_days: Optional[int] = Field(None, ge=0)
    min_order_qty: Optional[Decimal] = Field(None, ge=0)
    reorder_point: Optional[Decimal] = Field(None, ge=0, description="Reorder point (for stocked items)")
    stocking_policy: StockingPolicy = Field(StockingPolicy.ON_DEMAND, description="How inventory is managed")

    # Identifiers
    upc: Optional[str] = Field(None, max_length=50)
    legacy_sku: Optional[str] = Field(None, max_length=50)

    # Flags
    is_active: Optional[bool] = Field(True, alias="active")
    is_raw_material: Optional[bool] = Field(False)
    track_lots: Optional[bool] = Field(False)
    track_serials: Optional[bool] = Field(False)

    # Material link (for supply items that are filament/materials)
    material_type_id: Optional[int] = Field(None, description="Material type ID for material items")
    color_id: Optional[int] = Field(None, description="Color ID for material items")


class ItemCreate(ItemBase):
    """Create a new item"""
    pass


class MaterialItemCreate(BaseModel):
    """
    Shortcut for creating material items (filament).
    Automatically sets item_type=supply, procurement_type=buy, unit=kg.
    """
    material_type_code: str = Field(..., description="Material type code (e.g., PLA_BASIC)")
    color_code: str = Field(..., description="Color code (e.g., BLK)")
    cost_per_kg: Optional[Decimal] = Field(None, ge=0, description="Cost per kg (defaults to material base price)")
    selling_price: Optional[Decimal] = Field(None, ge=0, description="Selling price per kg")
    initial_qty_kg: Optional[Decimal] = Field(0, ge=0, description="Initial inventory quantity in kg")
    category_id: Optional[int] = Field(None, description="Category ID (defaults to Materials category)")


class ItemUpdate(BaseModel):
    """Update an existing item"""
    sku: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    unit: Optional[str] = Field(None, max_length=20)
    purchase_uom: Optional[str] = Field(None, max_length=20, description="Purchase unit - costs are per this unit")

    # Classification
    item_type: Optional[ItemType] = None
    procurement_type: Optional[ProcurementType] = None
    category_id: Optional[int] = None

    # Costing
    cost_method: Optional[CostMethod] = None
    standard_cost: Optional[Decimal] = Field(None, ge=0)
    selling_price: Optional[Decimal] = Field(None, ge=0)

    # Physical dimensions
    weight_oz: Optional[Decimal] = Field(None, ge=0)
    length_in: Optional[Decimal] = Field(None, ge=0)
    width_in: Optional[Decimal] = Field(None, ge=0)
    height_in: Optional[Decimal] = Field(None, ge=0)

    # Purchasing & Inventory
    lead_time_days: Optional[int] = Field(None, ge=0)
    min_order_qty: Optional[Decimal] = Field(None, ge=0)
    reorder_point: Optional[Decimal] = Field(None, ge=0)
    stocking_policy: Optional[StockingPolicy] = None

    # Identifiers
    upc: Optional[str] = Field(None, max_length=50)
    legacy_sku: Optional[str] = Field(None, max_length=50)

    # Flags
    is_active: Optional[bool] = Field(None, alias="active")
    is_raw_material: Optional[bool] = None
    track_lots: Optional[bool] = None
    track_serials: Optional[bool] = None

    # Image
    image_url: Optional[str] = Field(None, max_length=500, description="Product image URL")

    # Material link
    material_type_id: Optional[int] = None
    color_id: Optional[int] = None


class ItemListResponse(BaseModel):
    """Item list summary"""
    id: int
    sku: str
    name: str
    description: Optional[str] = None
    item_type: str
    procurement_type: str = "buy"
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    unit: Optional[str] = None
    purchase_uom: Optional[str] = None  # Purchase unit - costs are per this
    standard_cost: Optional[Decimal] = None
    average_cost: Optional[Decimal] = None
    selling_price: Optional[Decimal] = None
    active: bool
    on_hand_qty: Optional[Decimal] = None  # From inventory
    available_qty: Optional[Decimal] = None  # On hand - allocated
    reorder_point: Optional[Decimal] = None
    stocking_policy: str = "on_demand"  # stocked or on_demand
    needs_reorder: bool = False  # Only true for stocked items below reorder_point

    # Product image
    image_url: Optional[str] = Field(default=None, max_length=500)

    # BOM / Routing info
    has_bom: bool = False
    has_routing: bool = False

    # Material info (for filament items)
    material_type_id: Optional[int] = None
    color_id: Optional[int] = None
    material_type_code: Optional[str] = None
    color_code: Optional[str] = None

    # Variant info
    parent_product_id: Optional[int] = None
    is_template: bool = False
    variant_count: int = 0

    class Config:
        from_attributes = True


class ItemResponse(ItemBase):
    """Full item details"""
    id: int
    average_cost: Optional[Decimal] = None
    last_cost: Optional[Decimal] = None
    active: bool
    
    # Cost display helpers
    cost_per_storage_unit: Optional[Decimal] = None  # Calculated: standard_cost converted to $/storage_unit

    # Category info
    category_name: Optional[str] = None
    category_path: Optional[str] = None

    # Inventory summary
    on_hand_qty: Optional[Decimal] = None
    available_qty: Optional[Decimal] = None
    allocated_qty: Optional[Decimal] = None

    # BOM / Routing info
    has_bom: bool = False
    bom_count: int = 0
    has_routing: bool = False

    # Material info (for filament items)
    material_type_code: Optional[str] = None
    material_type_name: Optional[str] = None
    color_code: Optional[str] = None
    color_name: Optional[str] = None
    color_hex: Optional[str] = None

    # Variant info
    parent_product_id: Optional[int] = None
    is_template: bool = False
    variant_count: int = 0

    # Timestamps
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Bulk Operations
# ============================================================================

class ItemCSVImportRequest(BaseModel):
    """Settings for CSV import"""
    update_existing: bool = Field(False, description="Update items if SKU exists")
    default_item_type: ItemType = Field(ItemType.FINISHED_GOOD)
    default_category_id: Optional[int] = None


class ItemCSVImportResult(BaseModel):
    """Result of CSV import"""
    total_rows: int
    created: int
    updated: int
    skipped: int
    errors: List[dict] = []
    warnings: List[dict] = []  # UOM configuration warnings


class ItemBulkUpdateRequest(BaseModel):
    """Bulk update multiple items"""
    item_ids: List[int]
    category_id: Optional[int] = Field(None, description="Category ID (use 0 to clear category)")
    item_type: Optional[str] = Field(None, description="Item type: finished_good, component, supply, service")
    procurement_type: Optional[str] = Field(None, description="Procurement type: make, buy, make_or_buy")
    is_active: Optional[bool] = None


# --- Duplicate Item ---

class BOMLineOverride(BaseModel):
    """Override a BOM line's component during duplication."""
    original_component_id: int
    new_component_id: int


class DuplicateItemRequest(BaseModel):
    """Duplicate an existing item with a new SKU and name."""
    new_sku: str = Field(..., min_length=1, max_length=50, description="SKU for the new item")
    new_name: str = Field(..., min_length=1, max_length=255, description="Name for the new item")
    bom_line_overrides: List[BOMLineOverride] = Field(
        default_factory=list,
        description="Optional component swaps for BOM lines"
    )


class PriceApplyEntry(BaseModel):
    """Single item price to apply."""
    id: int
    selling_price: Decimal = Field(..., ge=0)


class ApplySuggestedPricesRequest(BaseModel):
    """Bulk apply suggested selling prices."""
    items: List[PriceApplyEntry]


# ============================================================================
# Variant Matrix
# ============================================================================

class VariantMaterialSelection(BaseModel):
    """A single material+color combo for variant creation."""
    material_type_id: int
    color_id: int


class VariantCreateRequest(BaseModel):
    """Create a single variant from a template product."""
    material_type_id: int
    color_id: int
    selling_price: Optional[Decimal] = None
    gcode_file_path: Optional[str] = None

    @field_validator("selling_price")
    @classmethod
    def selling_price_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("selling_price must not be negative")
        return v


class VariantBulkCreateRequest(BaseModel):
    """Bulk-create variants from MaterialColor selections."""
    selections: List[VariantMaterialSelection]

    @field_validator("selections")
    @classmethod
    def selections_non_empty(cls, v):
        if len(v) == 0:
            raise ValueError("selections must not be empty")
        return v


class VariantListResponse(BaseModel):
    """Summary of a variant for the matrix grid."""
    id: int
    sku: str
    name: str
    material_type_code: Optional[str] = None
    color_code: Optional[str] = None
    color_hex: Optional[str] = None
    standard_cost: Optional[Decimal] = None
    selling_price: Optional[Decimal] = None
    on_hand_qty: Optional[Decimal] = None
    active: bool = True

    class Config:
        from_attributes = True
