"""
Unit of Measure (UOM) Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from decimal import Decimal


class UOMBase(BaseModel):
    """Base UOM fields"""
    code: str = Field(..., min_length=1, max_length=10, description="Unit code (e.g., KG, G, LB)")
    name: str = Field(..., max_length=50, description="Full name (e.g., Kilogram)")
    symbol: Optional[str] = Field(None, max_length=10, description="Display symbol (e.g., kg)")
    uom_class: str = Field(..., min_length=1, max_length=20, description="Unit class (quantity, weight, length, time)")
    to_base_factor: Decimal = Field(1, description="Factor to convert to base unit")


class UOMCreate(UOMBase):
    """Create a new unit: a pack (no factor), or a weight, length, area, volume or time unit with its factor"""
    to_base_factor: Optional[Decimal] = Field(
        None, description="How many of the kind's base unit one of this is. Required except for a pack."
    )
    base_unit_code: Optional[str] = Field(None, description="The kind's base unit (KG, M, M2, L, HR). Optional.")


class UOMUpdate(BaseModel):
    """Update an existing UOM"""
    name: Optional[str] = Field(None, max_length=50)
    symbol: Optional[str] = Field(None, max_length=10)
    to_base_factor: Optional[Decimal] = None
    active: Optional[bool] = None


class UOMResponse(UOMBase):
    """UOM response with full details"""
    id: int
    base_unit_id: Optional[int] = None
    base_unit_code: Optional[str] = None
    active: bool

    class Config:
        from_attributes = True


class UOMListResponse(BaseModel):
    """Simplified UOM for list/dropdown"""
    id: int
    code: str
    name: str
    symbol: Optional[str] = None
    uom_class: str

    class Config:
        from_attributes = True


class UOMClassResponse(BaseModel):
    """UOM class with its units"""
    uom_class: str
    units: List[UOMListResponse]


class ConvertRequest(BaseModel):
    """Request to convert a quantity"""
    quantity: Decimal = Field(..., ge=0)
    from_unit: str = Field(..., description="Source unit code")
    to_unit: str = Field(..., description="Target unit code")


class ConvertResponse(BaseModel):
    """Conversion result"""
    original_quantity: Decimal
    original_unit: str
    converted_quantity: Decimal
    converted_unit: str
    conversion_factor: Decimal
