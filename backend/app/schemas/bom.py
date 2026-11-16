"""
Bill of Materials Pydantic Schemas
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import datetime, date
from decimal import Decimal


def tidy_unit_code(value: Optional[str]) -> Optional[str]:
    """Trim and upper-case a unit code that came with a request. Empty means "not given".

    Nothing is checked here. Whether the unit exists is decided where the line
    is saved, against the unit table (``app.services.line_units``): a list of
    codes written into a schema cannot know the units an install has added.
    """
    if value is None or value.strip() == '':
        return None
    return value.strip().upper()


# ============================================================================
# BOM Line Schemas
# ============================================================================

class BOMLineBase(BaseModel):
    """Base BOM line fields.

    The unit is not checked here, so a response can carry whatever a line
    holds. The request schemas below tidy it.
    """
    component_id: int = Field(..., description="Component product ID")
    quantity: Decimal = Field(..., gt=0, description="Required quantity")
    unit: Optional[str] = Field(None, max_length=20, description="Unit of measure (defaults to component's unit)")
    sequence: Optional[int] = Field(None, description="Line sequence/order")
    consume_stage: Literal["production", "shipping"] = Field("production", description="When to consume: 'production' or 'shipping'")
    is_cost_only: Optional[bool] = Field(False, description="If true, for costing only - no inventory allocation")
    scrap_factor: Optional[Decimal] = Field(0, ge=0, le=100, description="Scrap percentage")
    notes: Optional[str] = Field(None, max_length=1000)


class BOMLineCreate(BOMLineBase):
    """Create a new BOM line"""

    @field_validator('unit')
    @classmethod
    def tidy_unit(cls, v: Optional[str]) -> Optional[str]:
        """Tidy the unit code. The service checks it against the unit table."""
        return tidy_unit_code(v)


class BOMLineUpdate(BaseModel):
    """Update an existing BOM line"""
    component_id: Optional[int] = None
    quantity: Optional[Decimal] = Field(None, gt=0)
    unit: Optional[str] = Field(None, max_length=20)
    sequence: Optional[int] = None
    consume_stage: Optional[Literal["production", "shipping"]] = Field(None, description="When to consume: 'production' or 'shipping'")
    is_cost_only: Optional[bool] = None
    scrap_factor: Optional[Decimal] = Field(None, ge=0, le=100)
    notes: Optional[str] = Field(None, max_length=1000)

    @field_validator('unit')
    @classmethod
    def tidy_unit(cls, v: Optional[str]) -> Optional[str]:
        """Tidy the unit code. The service checks it against the unit table."""
        return tidy_unit_code(v)


class BOMLineResponse(BOMLineBase):
    """BOM line response with component details"""
    id: int
    bom_id: int
    # Component info (joined from products)
    component_sku: Optional[str] = None
    component_name: Optional[str] = None
    component_unit: Optional[str] = None
    component_cost: Optional[Decimal] = None
    component_cost_unit: Optional[str] = None
    line_cost: Optional[Decimal] = None  # quantity * component_cost
    qty_needed: Optional[float] = None
    is_material: Optional[bool] = None
    # Inventory info
    inventory_on_hand: Optional[float] = None
    inventory_available: Optional[float] = None
    is_available: Optional[bool] = None
    shortage: Optional[float] = None
    # Sub-assembly indicator (for MRP make vs buy)
    has_bom: Optional[bool] = None

    class Config:
        from_attributes = True


# ============================================================================
# BOM Schemas
# ============================================================================

class BOMBase(BaseModel):
    """Base BOM fields"""
    code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=255)
    version: Optional[int] = Field(1, ge=1)
    revision: Optional[str] = Field(None, max_length=10)
    assembly_time_minutes: Optional[int] = Field(None, ge=0)
    effective_date: Optional[date] = None
    notes: Optional[str] = None


class BOMCreate(BOMBase):
    """Create a new BOM"""
    product_id: int = Field(..., description="Product this BOM is for")
    lines: Optional[List[BOMLineCreate]] = Field(default_factory=list)


class BOMUpdate(BaseModel):
    """Update an existing BOM"""
    code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=255)
    version: Optional[int] = Field(None, ge=1)
    revision: Optional[str] = Field(None, max_length=10)
    active: Optional[bool] = None
    assembly_time_minutes: Optional[int] = Field(None, ge=0)
    effective_date: Optional[date] = None
    notes: Optional[str] = None


class BOMListResponse(BaseModel):
    """BOM list item (summary)"""
    id: int
    product_id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    version: Optional[int] = None
    revision: Optional[str] = None
    active: bool
    material_cost: Optional[Decimal] = None  # BOM component cost
    process_cost: Optional[Decimal] = None   # Routing process cost
    total_cost: Optional[Decimal] = None     # Combined total (material + process)
    line_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class BOMResponse(BOMBase):
    """Full BOM details with lines"""
    id: int
    product_id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    active: bool
    total_cost: Optional[Decimal] = None
    created_at: datetime
    lines: List[BOMLineResponse] = []

    class Config:
        from_attributes = True


# ============================================================================
# BOM Approval Schemas
# ============================================================================

class BOMApproveRequest(BaseModel):
    """Approve a BOM for production"""
    notes: Optional[str] = Field(None, max_length=1000)


class BOMRecalculateResponse(BaseModel):
    """Response after recalculating BOM costs"""
    bom_id: int
    previous_cost: Optional[Decimal]
    new_cost: Decimal
    line_costs: List[dict]


# ============================================================================
# Bulk Operations
# ============================================================================

class BOMBulkAddLinesRequest(BaseModel):
    """Add multiple lines to a BOM"""
    lines: List[BOMLineCreate]


class BOMCopyRequest(BaseModel):
    """Copy BOM to another product"""
    target_product_id: int
    include_lines: bool = True
    new_version: Optional[int] = None
