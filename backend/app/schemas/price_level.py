"""Pydantic schemas for Price Levels"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class PriceLevelCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    discount_percent: Decimal = Field(..., ge=0, le=100, decimal_places=2)
    description: Optional[str] = None
    is_active: bool = True


class PriceLevelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    discount_percent: Optional[Decimal] = Field(None, ge=0, le=100, decimal_places=2)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class PriceLevelResponse(BaseModel):
    id: int
    name: str
    discount_percent: Decimal
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}
