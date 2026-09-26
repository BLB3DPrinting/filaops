"""
Tax Rate CRUD endpoints.

GET  /tax-rates          → list active rates (staff: admin or operator)
GET  /tax-rates/{id}     → single rate (staff: admin or operator)
POST /tax-rates          → create (admin only)
PATCH /tax-rates/{id}   → update (admin only)
DELETE /tax-rates/{id}  → soft-delete (admin only)

rate_percent (8.25) ↔ rate (0.0825) conversion follows the same pattern
as CompanySettings tax fields.
"""
from decimal import Decimal
from typing import Optional, List

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.api.v1.deps import get_current_admin_user, get_current_staff_user
from app.services import tax_rate_service

# SEC-409: every route here is staff-only (admin or operator). A plain login is
# not enough, because anyone can self-register a customer account. Writes are
# admin-only.
router = APIRouter(
    prefix="/tax-rates",
    tags=["Tax Rates"],
    dependencies=[Depends(get_current_staff_user)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TaxRateResponse(BaseModel):
    id: int
    name: str
    rate: Decimal
    rate_percent: float  # computed: rate * 100 for display
    description: Optional[str] = None
    is_default: bool
    is_active: bool

    model_config = {"from_attributes": True}

    @classmethod
    def from_model(cls, m) -> "TaxRateResponse":
        return cls(
            id=m.id,
            name=m.name,
            rate=m.rate,
            rate_percent=round(float(m.rate) * 100, 4),
            description=m.description,
            is_default=m.is_default,
            is_active=m.is_active,
        )


class TaxRateCreate(BaseModel):
    name: str = Field(..., max_length=100)
    rate_percent: float = Field(..., ge=0, le=100, description="e.g. 8.25 for 8.25%")
    description: Optional[str] = Field(None, max_length=500)
    is_default: bool = False


class TaxRateUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    rate_percent: Optional[float] = Field(None, ge=0, le=100)
    description: Optional[str] = Field(None, max_length=500)
    is_default: Optional[bool] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=List[TaxRateResponse])
async def list_tax_rates(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """List active tax rates. Pass include_inactive=true to see all."""
    rates = tax_rate_service.list_tax_rates(db, active_only=not include_inactive)
    return [TaxRateResponse.from_model(r) for r in rates]


@router.get("/{tax_rate_id}", response_model=TaxRateResponse)
async def get_tax_rate(
    tax_rate_id: int,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    rate = tax_rate_service.get_tax_rate(db, tax_rate_id)
    return TaxRateResponse.from_model(rate)


@router.post("", response_model=TaxRateResponse, status_code=status.HTTP_201_CREATED)
async def create_tax_rate(
    data: TaxRateCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    rate = tax_rate_service.create_tax_rate(
        db,
        name=data.name,
        rate=Decimal(str(data.rate_percent / 100)),
        description=data.description,
        is_default=data.is_default,
    )
    return TaxRateResponse.from_model(rate)


@router.patch("/{tax_rate_id}", response_model=TaxRateResponse)
async def update_tax_rate(
    tax_rate_id: int,
    data: TaxRateUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    kwargs = {}
    if data.name is not None:
        kwargs["name"] = data.name
    if data.rate_percent is not None:
        kwargs["rate"] = Decimal(str(data.rate_percent / 100))
    if data.description is not None:
        kwargs["description"] = data.description
    if data.is_default is not None:
        kwargs["is_default"] = data.is_default
    rate = tax_rate_service.update_tax_rate(db, tax_rate_id, **kwargs)
    return TaxRateResponse.from_model(rate)


@router.delete("/{tax_rate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tax_rate(
    tax_rate_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    tax_rate_service.delete_tax_rate(db, tax_rate_id)
