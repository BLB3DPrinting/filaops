"""
Schemas for the unit endpoints any staff account can read: the unit table, and
the units one item can be entered in.
"""
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class UnitRow(BaseModel):
    """A unit in the unit table."""
    code: str
    name: str
    symbol: Optional[str] = None
    kind: str = Field(..., description="weight, length, area, volume, quantity, time or pack")
    is_standard: bool = Field(..., description="One of the units every install has, with an exact factor")


class ItemUnitRow(BaseModel):
    """A unit an item can be entered in, and how many stock units one of it is."""
    unit_code: str
    name: str
    kind: Optional[str] = None
    stock_units_per_unit: Decimal
    source: str = Field(..., description="stock (the stock unit), table (the unit table) or item (the item's own)")
    is_purchase_unit: bool


class ItemOwnUnit(BaseModel):
    """One of the item's own units, with its size as it was typed."""
    unit_code: str
    stock_units_per_unit: Optional[Decimal] = None
    units_per_stock_unit: Optional[Decimal] = None


class ItemUnitsResponse(BaseModel):
    """Everything a unit picker for one item needs."""
    item_id: int
    sku: str
    stock_unit: str
    purchase_unit: Optional[str] = None
    stock_unit_locked: bool
    stock_unit_locked_reason: Optional[str] = None
    units: List[ItemUnitRow]
    own_units: List[ItemOwnUnit]


class ItemUnitSize(BaseModel):
    """The size of one of an item's own units. Give exactly one."""
    stock_units_per_unit: Optional[Decimal] = Field(None, gt=0, description="1 BOX = 12 EA: 12")
    units_per_stock_unit: Optional[Decimal] = Field(None, gt=0, description="1 EA = 750 G, on the G unit: 750")
