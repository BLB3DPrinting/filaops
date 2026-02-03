"""
Location Service — CRUD operations for inventory locations.

Extracted from admin/locations.py (ARCHITECT-003).
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.inventory import InventoryLocation
from app.core.utils import get_or_404, check_unique_or_400

# Sentinel to distinguish "not provided" from None (clear parent)
_UNSET = object()


def list_locations(db: Session, *, include_inactive: bool = False) -> list[InventoryLocation]:
    """List all inventory locations, optionally including inactive."""
    query = db.query(InventoryLocation)
    if not include_inactive:
        query = query.filter(InventoryLocation.active.is_(True))
    return query.order_by(InventoryLocation.code).all()


def get_location(db: Session, location_id: int) -> InventoryLocation:
    """Get a single location by ID or raise 404."""
    return get_or_404(db, InventoryLocation, location_id, "Location not found")


def _validate_parent(db: Session, parent_id: int | None, exclude_id: int | None = None) -> None:
    """Validate parent location exists, is active, and isn't self-referencing."""
    if parent_id is None:
        return
    if exclude_id is not None and parent_id == exclude_id:
        raise HTTPException(status_code=400, detail="A location cannot be its own parent")
    parent = db.query(InventoryLocation).filter(InventoryLocation.id == parent_id).first()
    if not parent:
        raise HTTPException(status_code=400, detail="Parent location not found")
    if not parent.active:
        raise HTTPException(status_code=400, detail="Parent location is inactive")


def create_location(
    db: Session,
    *,
    code: str,
    name: str,
    type: str | None = "warehouse",
    parent_id: int | None = None,
) -> InventoryLocation:
    """Create a new inventory location."""
    check_unique_or_400(db, InventoryLocation, "code", code)
    _validate_parent(db, parent_id)

    location = InventoryLocation(
        code=code,
        name=name,
        type=type,
        parent_id=parent_id,
        active=True,
    )
    db.add(location)
    db.commit()
    db.refresh(location)
    return location


def update_location(
    db: Session,
    location_id: int,
    *,
    code: str | None = None,
    name: str | None = None,
    type: str | None = None,
    parent_id: int | object = _UNSET,
    active: bool | None = None,
) -> InventoryLocation:
    """Update an inventory location.

    Pass parent_id=None to clear the parent; omit to leave unchanged.
    """
    location = get_or_404(db, InventoryLocation, location_id, "Location not found")

    if code is not None and code != location.code:
        check_unique_or_400(db, InventoryLocation, "code", code, exclude_id=location_id)
        location.code = code

    if name is not None:
        location.name = name
    if type is not None:
        location.type = type
    if parent_id is not _UNSET:
        if parent_id is not None:
            _validate_parent(db, parent_id, exclude_id=location_id)
        location.parent_id = parent_id
    if active is not None:
        location.active = active

    db.commit()
    db.refresh(location)
    return location


def delete_location(db: Session, location_id: int) -> dict:
    """Soft-delete (deactivate) a location."""
    location = get_or_404(db, InventoryLocation, location_id, "Location not found")

    if location.code == "MAIN":
        raise HTTPException(status_code=400, detail="Cannot delete the main warehouse")

    location.active = False
    db.commit()
    return {"message": "Location deactivated"}
