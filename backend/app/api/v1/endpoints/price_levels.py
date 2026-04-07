"""
Price Level CRUD endpoints.

GET    /price-levels        → list (admin + operator)
POST   /price-levels        → create (admin only)
PATCH  /price-levels/{id}  → update (admin only)
DELETE /price-levels/{id}  → deactivate (admin only)

Customer assignment is a PRO feature handled by filaops-pro via
/api/v1/pro/catalogs/price-levels/{id}/assign.
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.deps import get_current_admin_user
from app.schemas.price_level import PriceLevelCreate, PriceLevelUpdate, PriceLevelResponse
from app.services import price_level_service

router = APIRouter(prefix="/price-levels", tags=["Price Levels"])


@router.get("", response_model=List[PriceLevelResponse])
def list_price_levels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return price_level_service.list_price_levels(db)


@router.post("", response_model=PriceLevelResponse, status_code=201)
def create_price_level(
    data: PriceLevelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    return price_level_service.create_price_level(db, data)


@router.patch("/{price_level_id}", response_model=PriceLevelResponse)
def update_price_level(
    price_level_id: int,
    data: PriceLevelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    return price_level_service.update_price_level(db, price_level_id, data)


@router.delete("/{price_level_id}", response_model=PriceLevelResponse)
def deactivate_price_level(
    price_level_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    return price_level_service.deactivate_price_level(db, price_level_id)
