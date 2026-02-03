"""
Work Center Service — CRUD for work centers and resources.

Extracted from work_centers.py (ARCHITECT-003).
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models.manufacturing import Resource
from app.models.work_center import WorkCenter
from app.models.printer import Printer
from app.core.utils import get_or_404, check_unique_or_400

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Work Center CRUD
# ---------------------------------------------------------------------------


def list_work_centers(
    db: Session,
    *,
    center_type: str | None = None,
    active_only: bool = True,
) -> list[WorkCenter]:
    """List work centers with eagerly-loaded resources."""
    query = db.query(WorkCenter).options(joinedload(WorkCenter.resources))

    if center_type:
        query = query.filter(WorkCenter.center_type == center_type)
    if active_only:
        query = query.filter(WorkCenter.is_active.is_(True))

    return query.order_by(WorkCenter.scheduling_priority.desc(), WorkCenter.name).all()


def get_work_center(db: Session, wc_id: int) -> WorkCenter:
    """Get work center by ID with resources, or raise 404."""
    wc = (
        db.query(WorkCenter)
        .options(joinedload(WorkCenter.resources))
        .filter(WorkCenter.id == wc_id)
        .first()
    )
    if not wc:
        raise HTTPException(status_code=404, detail="Work center not found")
    return wc


def create_work_center(db: Session, *, data: dict) -> WorkCenter:
    """Create a new work center."""
    check_unique_or_400(db, WorkCenter, "code", data["code"])

    # Convert enum to string value if present
    if "center_type" in data and hasattr(data["center_type"], "value"):
        data["center_type"] = data["center_type"].value

    wc = WorkCenter(**data)
    db.add(wc)
    db.commit()
    db.refresh(wc)

    logger.info(f"Created work center: {wc.code}")
    return wc


def update_work_center(db: Session, wc_id: int, *, data: dict) -> WorkCenter:
    """Update a work center."""
    wc = get_or_404(db, WorkCenter, wc_id, "Work center not found")

    if "code" in data and data["code"] != wc.code:
        check_unique_or_400(db, WorkCenter, "code", data["code"])

    for field, value in data.items():
        if field == "center_type" and value and hasattr(value, "value"):
            value = value.value
        setattr(wc, field, value)

    wc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(wc)

    logger.info(f"Updated work center: {wc.code}")
    return wc


def delete_work_center(db: Session, wc_id: int) -> None:
    """Soft-delete a work center."""
    wc = get_or_404(db, WorkCenter, wc_id, "Work center not found")
    wc.is_active = False
    wc.updated_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"Deactivated work center: {wc.code}")


# ---------------------------------------------------------------------------
# Resource (Machine) CRUD
# ---------------------------------------------------------------------------


def list_resources(
    db: Session,
    wc_id: int,
    *,
    active_only: bool = True,
) -> tuple[list[Resource], WorkCenter]:
    """List resources for a work center. Returns (resources, work_center)."""
    wc = get_or_404(db, WorkCenter, wc_id, "Work center not found")

    query = db.query(Resource).filter(Resource.work_center_id == wc_id)
    if active_only:
        query = query.filter(Resource.is_active.is_(True))

    return query.order_by(Resource.code).all(), wc


def get_resource(db: Session, resource_id: int) -> Resource:
    """Get resource by ID with work center loaded, or raise 404."""
    resource = (
        db.query(Resource)
        .options(joinedload(Resource.work_center))
        .filter(Resource.id == resource_id)
        .first()
    )
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")
    return resource


def create_resource(db: Session, wc_id: int, *, data: dict) -> tuple[Resource, WorkCenter]:
    """Create a new resource in a work center. Returns (resource, work_center)."""
    wc = get_or_404(db, WorkCenter, wc_id, "Work center not found")

    # Convert enum to string value if present
    if "status" in data and hasattr(data["status"], "value"):
        data["status"] = data["status"].value

    # Remove work_center_id from data — it's set explicitly from the URL path
    data.pop("work_center_id", None)

    resource = Resource(work_center_id=wc_id, **data)
    db.add(resource)
    db.commit()
    db.refresh(resource)

    logger.info(f"Created resource: {resource.code} in {wc.code}")
    return resource, wc


def update_resource(db: Session, resource_id: int, *, data: dict) -> tuple[Resource, WorkCenter]:
    """Update a resource. Returns (resource, work_center)."""
    resource = get_resource(db, resource_id)

    new_work_center = None
    if "work_center_id" in data and data["work_center_id"] != resource.work_center_id:
        new_work_center = get_or_404(
            db, WorkCenter, data["work_center_id"], "Target work center not found"
        )

    for field, value in data.items():
        if field == "status" and value and hasattr(value, "value"):
            value = value.value
        setattr(resource, field, value)

    resource.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(resource)

    wc = new_work_center if new_work_center else resource.work_center
    logger.info(f"Updated resource: {resource.code}")
    return resource, wc


def delete_resource(db: Session, resource_id: int) -> None:
    """Soft-delete a resource (mark as inactive)."""
    resource = get_or_404(db, Resource, resource_id, "Resource not found")
    resource.is_active = False
    resource.updated_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"Deactivated resource: {resource.code}")


def update_resource_status(db: Session, resource_id: int, new_status: str) -> dict:
    """Quick-update resource status."""
    resource = get_or_404(db, Resource, resource_id, "Resource not found")
    old_status = resource.status
    resource.status = new_status
    resource.updated_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"Resource {resource.code} status: {old_status} -> {new_status}")
    return {"id": resource_id, "status": new_status}


# ---------------------------------------------------------------------------
# Printers linked to work center
# ---------------------------------------------------------------------------


def list_work_center_printers(db: Session, wc_id: int, *, active_only: bool = True) -> list[dict]:
    """List printers assigned to a work center."""
    get_or_404(db, WorkCenter, wc_id, "Work center not found")

    query = db.query(Printer).filter(Printer.work_center_id == wc_id)
    if active_only:
        query = query.filter(Printer.active.is_(True))

    printers = query.order_by(Printer.code).all()

    return [
        {
            "id": p.id,
            "code": p.code,
            "name": p.name,
            "model": p.model,
            "brand": p.brand,
            "status": p.status,
            "ip_address": p.ip_address,
            "active": p.active,
        }
        for p in printers
    ]
