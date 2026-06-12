"""
Maintenance Window Endpoints (SCHED-7)

CRUD-lite for planned maintenance time blocks:
  POST   /api/v1/maintenance-windows               — schedule a window
  GET    /api/v1/maintenance-windows               — list (by machine / range)
  POST   /api/v1/maintenance-windows/{id}/cancel   — cancel a window
  POST   /api/v1/maintenance-windows/{id}/complete — complete (writes MaintenanceLog)

Auth-gated with get_current_user, matching the sibling maintenance.py file.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.user import User
from app.schemas.maintenance_window import (
    MaintenanceWindowCompleteRequest,
    MaintenanceWindowCreate,
    MaintenanceWindowListResponse,
    MaintenanceWindowResponse,
)
from app.services import maintenance_window_service

router = APIRouter(
    prefix="/maintenance-windows",
    tags=["maintenance"],
)
logger = get_logger(__name__)


@router.post("", response_model=MaintenanceWindowResponse, status_code=201)
async def create_maintenance_window(
    data: MaintenanceWindowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Schedule a maintenance window on a printer or machine resource."""
    try:
        window = maintenance_window_service.create_window(
            db,
            printer_id=data.printer_id,
            resource_id=data.resource_id,
            starts_at=data.starts_at,
            ends_at=data.ends_at,
            reason=data.reason,
            created_by=current_user.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    db.refresh(window)
    logger.info(
        f"Scheduled maintenance window {window.id} "
        f"({'printer ' + str(window.printer_id) if window.printer_id else 'resource ' + str(window.resource_id)}) "
        f"{window.starts_at} – {window.ends_at}"
    )
    return window


@router.get("", response_model=MaintenanceWindowListResponse)
async def list_maintenance_windows(
    printer_id: Optional[int] = Query(None, description="Filter by printer"),
    resource_id: Optional[int] = Query(None, description="Filter by machine resource"),
    start: Optional[datetime] = Query(None, description="Only windows ending after this time"),
    end: Optional[datetime] = Query(None, description="Only windows starting before this time"),
    include_finished: bool = Query(
        False, description="Include completed and cancelled windows"
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List maintenance windows by machine and/or time range."""
    windows = maintenance_window_service.list_windows(
        db,
        printer_id=printer_id,
        resource_id=resource_id,
        start=start,
        end=end,
        include_finished=include_finished,
    )
    return MaintenanceWindowListResponse(items=windows, total=len(windows))


@router.post("/{window_id}/cancel", response_model=MaintenanceWindowResponse)
async def cancel_maintenance_window(
    window_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a scheduled or in-progress maintenance window."""
    try:
        window = maintenance_window_service.cancel_window(db, window_id)
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    db.commit()
    db.refresh(window)
    logger.info(f"Cancelled maintenance window {window_id}")
    return window


@router.post("/{window_id}/complete", response_model=MaintenanceWindowResponse)
async def complete_maintenance_window(
    window_id: int,
    data: MaintenanceWindowCompleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Complete a maintenance window.

    For printer windows this writes a MaintenanceLog entry (downtime from
    the window span, operator-supplied next_due_at) and links it via
    maintenance_log_id, closing the loop with the /maintenance/due
    endpoints. Resource windows just close (maintenance_logs requires a
    printer).
    """
    try:
        window = maintenance_window_service.complete_window(
            db,
            window_id,
            maintenance_type=data.maintenance_type.value,
            performed_by=data.performed_by or current_user.email,
            next_due_at=data.next_due_at,
            cost=data.cost,
            notes=data.notes,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    db.commit()
    db.refresh(window)
    logger.info(
        f"Completed maintenance window {window_id} "
        f"(log {window.maintenance_log_id})"
    )
    return window
