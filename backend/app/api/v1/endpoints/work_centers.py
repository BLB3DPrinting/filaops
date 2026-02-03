"""
Work Centers API Endpoints

CRUD operations for work centers and resources (machines).
Uses work_center_service for business logic (ARCHITECT-003).
"""
from fastapi import APIRouter, HTTPException, Depends, status
from typing import Optional, List
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.manufacturing import Resource
from app.models.work_center import WorkCenter
from app.api.v1.deps import get_current_user
from app.models.user import User
from app.schemas.manufacturing import (
    WorkCenterCreate,
    WorkCenterUpdate,
    WorkCenterResponse,
    WorkCenterListResponse,
    ResourceCreate,
    ResourceUpdate,
    ResourceResponse,
    ResourceStatus,
)
from app.services import work_center_service

router = APIRouter()
logger = get_logger(__name__)


# ============================================================================
# Work Center CRUD
# ============================================================================

@router.get("/", response_model=List[WorkCenterListResponse])
async def list_work_centers(
    center_type: Optional[str] = None,
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all work centers.

    - **center_type**: Filter by type (machine, station, labor)
    - **active_only**: Only return active work centers
    """
    work_centers = work_center_service.list_work_centers(
        db, center_type=center_type, active_only=active_only
    )

    return [
        WorkCenterListResponse(
            id=wc.id,
            code=wc.code,
            name=wc.name,
            center_type=wc.center_type,
            capacity_hours_per_day=wc.capacity_hours_per_day,
            total_rate_per_hour=Decimal(str(
                float(wc.machine_rate_per_hour or 0)
                + float(wc.labor_rate_per_hour or 0)
                + float(wc.overhead_rate_per_hour or 0)
            )),
            resource_count=len([r for r in wc.resources if r.is_active]),
            is_bottleneck=wc.is_bottleneck,
            is_active=wc.is_active,
        )
        for wc in work_centers
    ]


@router.post("/", response_model=WorkCenterResponse, status_code=status.HTTP_201_CREATED)
async def create_work_center(
    data: WorkCenterCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new work center."""
    wc = work_center_service.create_work_center(db, data=data.model_dump())
    return _build_work_center_response(wc)


@router.get("/{wc_id}", response_model=WorkCenterResponse)
async def get_work_center(
    wc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a work center by ID."""
    wc = work_center_service.get_work_center(db, wc_id)
    return _build_work_center_response(wc)


@router.put("/{wc_id}", response_model=WorkCenterResponse)
async def update_work_center(
    wc_id: int,
    data: WorkCenterUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a work center."""
    wc = work_center_service.update_work_center(
        db, wc_id, data=data.model_dump(exclude_unset=True)
    )
    return _build_work_center_response(wc)


@router.delete("/{wc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_work_center(
    wc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a work center (soft delete - marks as inactive)."""
    work_center_service.delete_work_center(db, wc_id)


# ============================================================================
# Resources (Machines) CRUD
# ============================================================================

@router.get("/{wc_id}/resources", response_model=List[ResourceResponse])
async def list_resources(
    wc_id: int,
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all resources for a work center."""
    resources, wc = work_center_service.list_resources(db, wc_id, active_only=active_only)
    return [_build_resource_response(r, wc) for r in resources]


@router.post("/{wc_id}/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    wc_id: int,
    data: ResourceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new resource (machine) in a work center."""
    resource, wc = work_center_service.create_resource(db, wc_id, data=data.model_dump())
    return _build_resource_response(resource, wc)


@router.get("/resources/{resource_id}", response_model=ResourceResponse)
async def get_resource(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a resource by ID."""
    resource = work_center_service.get_resource(db, resource_id)
    return _build_resource_response(resource, resource.work_center)


@router.put("/resources/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: int,
    data: ResourceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a resource."""
    resource, wc = work_center_service.update_resource(
        db, resource_id, data=data.model_dump(exclude_unset=True)
    )
    return _build_resource_response(resource, wc)


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a resource."""
    work_center_service.delete_resource(db, resource_id)


@router.patch("/resources/{resource_id}/status")
async def update_resource_status(
    resource_id: int,
    new_status: ResourceStatus,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Quick update of resource status."""
    return work_center_service.update_resource_status(db, resource_id, new_status.value)


# ============================================================================
# Printers linked to Work Center
# ============================================================================

@router.get("/{wc_id}/printers")
async def list_work_center_printers(
    wc_id: int,
    active_only: bool = True,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List printers assigned to a work center.

    Returns basic printer info for display in the work center card.
    """
    return work_center_service.list_work_center_printers(db, wc_id, active_only=active_only)


# ============================================================================
# Helper Functions
# ============================================================================

def _build_work_center_response(wc: WorkCenter) -> WorkCenterResponse:
    """Build a work center response object."""
    total_rate = (
        float(wc.machine_rate_per_hour or 0) +
        float(wc.labor_rate_per_hour or 0) +
        float(wc.overhead_rate_per_hour or 0)
    )
    resource_count = len([r for r in wc.resources if r.is_active]) if wc.resources else 0

    return WorkCenterResponse(
        id=wc.id,
        code=wc.code,
        name=wc.name,
        description=wc.description,
        center_type=wc.center_type,
        capacity_hours_per_day=wc.capacity_hours_per_day,
        capacity_units_per_hour=wc.capacity_units_per_hour,
        machine_rate_per_hour=wc.machine_rate_per_hour,
        labor_rate_per_hour=wc.labor_rate_per_hour,
        overhead_rate_per_hour=wc.overhead_rate_per_hour,
        is_bottleneck=wc.is_bottleneck,
        scheduling_priority=wc.scheduling_priority,
        is_active=wc.is_active,
        created_at=wc.created_at,
        updated_at=wc.updated_at,
        resource_count=resource_count,
        total_rate_per_hour=Decimal(str(total_rate)),
    )


def _build_resource_response(r: Resource, wc: WorkCenter) -> ResourceResponse:
    """Build a resource response object."""
    return ResourceResponse(
        id=r.id,
        work_center_id=r.work_center_id,
        code=r.code,
        name=r.name,
        machine_type=r.machine_type,
        serial_number=r.serial_number,
        bambu_device_id=r.bambu_device_id,
        bambu_ip_address=r.bambu_ip_address,
        capacity_hours_per_day=r.capacity_hours_per_day,
        status=r.status,
        is_active=r.is_active,
        work_center_code=wc.code if wc else None,
        work_center_name=wc.name if wc else None,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


# ============================================================================
# Bambu Print Suite Sync (kept inline — tightly coupled to config)
# ============================================================================

BAMBU_PRINTERS = {
    "SERIAL_NUMBER_HERE": {
        "name": "Printer-1",
        "model": "P1S",
        "ip": "192.168.1.100",
        "access_code": "12345678",
    },
}


@router.post("/sync-bambu")
async def sync_bambu_printers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Sync printers from Bambu Print Suite configuration.

    Creates or updates resources in the FDM-POOL work center
    based on the known printer configuration.
    """
    fdm_pool = db.query(WorkCenter).filter(WorkCenter.code == "FDM-POOL").first()
    if not fdm_pool:
        raise HTTPException(
            status_code=404,
            detail="FDM-POOL work center not found. Create it first."
        )

    created = []
    updated = []
    skipped = []

    for serial, printer_info in BAMBU_PRINTERS.items():
        existing = db.query(Resource).filter(
            Resource.serial_number == serial
        ).first()

        if existing:
            changed = False
            if existing.name != printer_info["name"]:
                existing.name = printer_info["name"]
                changed = True
            if existing.machine_type != printer_info["model"]:
                existing.machine_type = printer_info["model"]
                changed = True
            if existing.bambu_ip_address != printer_info["ip"]:
                existing.bambu_ip_address = printer_info["ip"]
                changed = True
            if existing.work_center_id != fdm_pool.id:
                existing.work_center_id = fdm_pool.id
                changed = True

            if changed:
                existing.updated_at = datetime.now(timezone.utc)
                updated.append(printer_info["name"])
            else:
                skipped.append(printer_info["name"])
        else:
            resource = Resource(
                work_center_id=fdm_pool.id,
                code=f"PRINTER-{serial[-6:]}",
                name=printer_info["name"],
                machine_type=printer_info["model"],
                serial_number=serial,
                bambu_device_id=f"PRINTER-{serial[-6:]}",
                bambu_ip_address=printer_info["ip"],
                capacity_hours_per_day=Decimal("20"),
                status="available",
                is_active=True,
            )
            db.add(resource)
            created.append(printer_info["name"])

    db.commit()

    active_printers = len(created) + len(updated) + len(skipped)
    new_capacity = Decimal(str(active_printers * 20))
    if fdm_pool.capacity_hours_per_day != new_capacity:
        fdm_pool.capacity_hours_per_day = new_capacity
        fdm_pool.updated_at = datetime.now(timezone.utc)
        db.commit()

    logger.info(f"Bambu sync: created={created}, updated={updated}, skipped={skipped}")

    return {
        "success": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "total_printers": active_printers,
        "pool_capacity_hours": float(new_capacity),
    }
