"""Quality Plan schemas (#784)."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

_SEVERITIES = ("minor", "major", "critical")


class QualityPlanCharacteristicInput(BaseModel):
    """One characteristic to inspect under a plan."""
    code: Optional[str] = Field(
        None, max_length=50, description="Stable per-plan key for SPC series (rename-proof)"
    )
    characteristic: str = Field(..., max_length=100)
    nominal: Optional[Decimal] = None
    lower_limit: Optional[Decimal] = Field(None, description="Lower spec limit (LSL)")
    upper_limit: Optional[Decimal] = Field(None, description="Upper spec limit (USL)")
    unit: Optional[str] = Field(None, max_length=20)
    sequence: Optional[int] = Field(None, description="Display order; defaults to input order")
    severity: Optional[str] = Field(None, description="minor | major | critical")
    routing_operation_id: Optional[int] = Field(
        None, description="Optional routing step this characteristic is inspected at"
    )

    @model_validator(mode="after")
    def _validate(self):
        if self.severity is not None and self.severity not in _SEVERITIES:
            raise ValueError(f"severity must be one of {', '.join(_SEVERITIES)}")
        if (
            self.lower_limit is not None
            and self.upper_limit is not None
            and self.lower_limit > self.upper_limit
        ):
            raise ValueError("lower_limit cannot be greater than upper_limit")
        return self


class QualityPlanCharacteristicResponse(BaseModel):
    id: int
    code: Optional[str] = None
    characteristic: str
    nominal: Optional[Decimal] = None
    lower_limit: Optional[Decimal] = None
    upper_limit: Optional[Decimal] = None
    unit: Optional[str] = None
    sequence: int
    severity: Optional[str] = None
    routing_operation_id: Optional[int] = None

    class Config:
        from_attributes = True


class QualityPlanCreate(BaseModel):
    product_id: Optional[int] = Field(None, description="null for a reusable template")
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=200)
    version: int = 1
    revision: str = Field("1.0", max_length=20)
    is_active: bool = True
    is_template: bool = False
    effective_date: Optional[date] = None
    notes: Optional[str] = None
    characteristics: List[QualityPlanCharacteristicInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _scope(self):
        # A template has no product; a product-specific plan must name one.
        if self.is_template and self.product_id is not None:
            raise ValueError("a template plan must not have a product_id")
        if not self.is_template and self.product_id is None:
            raise ValueError(
                "a product plan requires a product_id (or set is_template=true)"
            )
        return self


class QualityPlanUpdate(BaseModel):
    product_id: Optional[int] = Field(
        None, description="Reassign the plan's product, or clear it (with is_template) to make a template"
    )
    code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=200)
    version: Optional[int] = None
    revision: Optional[str] = Field(None, max_length=20)
    is_active: Optional[bool] = None
    is_template: Optional[bool] = None
    effective_date: Optional[date] = None
    notes: Optional[str] = None
    # When provided, REPLACES the plan's characteristics wholesale.
    characteristics: Optional[List[QualityPlanCharacteristicInput]] = None


class QualityPlanResponse(BaseModel):
    id: int
    product_id: Optional[int] = None
    code: str
    name: str
    version: int
    revision: str
    is_active: bool
    is_template: bool
    effective_date: Optional[date] = None
    notes: Optional[str] = None
    characteristics: List[QualityPlanCharacteristicResponse] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
