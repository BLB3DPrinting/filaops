"""
Inventory Locations Management API

Uses location_service for business logic (ARCHITECT-003).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.models.user import User
from app.services import location_service
from app.services.location_service import _UNSET

router = APIRouter(prefix="/locations", tags=["locations"])


class LocationCreate(BaseModel):
    code: str
    name: str
    type: Optional[str] = "warehouse"
    parent_id: Optional[int] = None


class LocationUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    parent_id: Optional[int] = None
    active: Optional[bool] = None


class LocationResponse(BaseModel):
    id: int
    code: Optional[str]
    name: str
    type: Optional[str]
    parent_id: Optional[int]
    active: Optional[bool]

    class Config:
        from_attributes = True


def _location_dict(loc) -> dict:
    return {
        "id": loc.id,
        "code": loc.code,
        "name": loc.name,
        "type": loc.type,
        "parent_id": loc.parent_id,
        "active": loc.active,
    }


@router.get("")
async def list_locations(
    include_inactive: bool = False,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """List all inventory locations"""
    locations = location_service.list_locations(db, include_inactive=include_inactive)
    return [_location_dict(loc) for loc in locations]


@router.get("/{location_id}")
async def get_location(
    location_id: int,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Get a single location by ID"""
    location = location_service.get_location(db, location_id)
    return _location_dict(location)


@router.post("")
async def create_location(
    location: LocationCreate,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Create a new inventory location"""
    new_location = location_service.create_location(
        db,
        code=location.code,
        name=location.name,
        type=location.type,
        parent_id=location.parent_id,
    )
    return _location_dict(new_location)


@router.put("/{location_id}")
async def update_location(
    location_id: int,
    location: LocationUpdate,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Update an inventory location"""
    # Use model_fields_set to distinguish "not provided" from explicit None
    update_kwargs = {}
    if "code" in location.model_fields_set:
        update_kwargs["code"] = location.code
    if "name" in location.model_fields_set:
        update_kwargs["name"] = location.name
    if "type" in location.model_fields_set:
        update_kwargs["type"] = location.type
    if "parent_id" in location.model_fields_set:
        update_kwargs["parent_id"] = location.parent_id
    else:
        update_kwargs["parent_id"] = _UNSET
    if "active" in location.model_fields_set:
        update_kwargs["active"] = location.active

    updated = location_service.update_location(
        db,
        location_id,
        **update_kwargs,
    )
    return _location_dict(updated)


@router.delete("/{location_id}")
async def delete_location(
    location_id: int,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Soft delete (deactivate) an inventory location"""
    return location_service.delete_location(db, location_id)
