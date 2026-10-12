"""
Maintenance API Endpoints

Provides CRUD operations for printer maintenance logging and tracking.
Freemium feature: Basic maintenance logging and scheduling.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.maintenance import MaintenanceLog
from app.models.printer import Printer
from app.api.v1.deps import get_current_staff_user
from app.models.user import User
from app.schemas.maintenance import (
    MaintenanceType,
    MaintenanceLogCreate,
    MaintenanceLogUpdate,
    MaintenanceLogResponse,
    MaintenanceLogListResponse,
    PrinterMaintenanceDue,
    MaintenanceDueResponse,
)

# SEC-409: every route here is staff-only (admin or operator). A plain login is
# not enough, because anyone can self-register a customer account.
router = APIRouter(dependencies=[Depends(get_current_staff_user)])
logger = get_logger(__name__)


def _maintenance_to_response(log: MaintenanceLog) -> MaintenanceLogResponse:
    """Convert MaintenanceLog model to response schema"""
    return MaintenanceLogResponse(
        id=log.id,
        printer_id=log.printer_id,
        maintenance_type=MaintenanceType(log.maintenance_type),
        description=log.description,
        performed_by=log.performed_by,
        performed_at=log.performed_at,
        next_due_at=log.next_due_at,
        cost=log.cost,
        downtime_minutes=log.downtime_minutes,
        parts_used=log.parts_used,
        notes=log.notes,
        created_at=log.created_at,
    )


# ============================================================================
# Maintenance Log CRUD
# ============================================================================

@router.get("/", response_model=MaintenanceLogListResponse)
async def list_maintenance_logs(
    printer_id: Optional[int] = None,
    maintenance_type: Optional[MaintenanceType] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    List all maintenance logs with filtering and pagination

    - **printer_id**: Filter by specific printer
    - **maintenance_type**: Filter by type (routine, repair, calibration, cleaning)
    - **start_date**: Filter logs from this date
    - **end_date**: Filter logs until this date
    """
    query = db.query(MaintenanceLog)

    if printer_id:
        query = query.filter(MaintenanceLog.printer_id == printer_id)

    if maintenance_type:
        query = query.filter(MaintenanceLog.maintenance_type == maintenance_type.value)

    if start_date:
        query = query.filter(MaintenanceLog.performed_at >= start_date)

    if end_date:
        query = query.filter(MaintenanceLog.performed_at <= end_date)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    logs = query.order_by(desc(MaintenanceLog.performed_at)).offset(offset).limit(page_size).all()

    return MaintenanceLogListResponse(
        items=[_maintenance_to_response(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/due", response_model=MaintenanceDueResponse)
async def get_maintenance_due(
    days_ahead: int = Query(7, ge=1, le=90, description="Check for maintenance due within this many days"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Get printers that are due for maintenance

    Returns printers with:
    - Overdue maintenance (next_due_at in the past)
    - Upcoming maintenance (next_due_at within next N days)
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    future_date = now + timedelta(days=days_ahead)

    # Get all active printers
    printers = db.query(Printer).filter(Printer.active.is_(True)).all()

    printers_due = []
    total_overdue = 0
    total_due_soon = 0

    for printer in printers:
        # Get the most recent maintenance log for this printer
        latest_log = db.query(MaintenanceLog).filter(
            MaintenanceLog.printer_id == printer.id
        ).order_by(desc(MaintenanceLog.performed_at)).first()

        if latest_log and latest_log.next_due_at:
            # Calculate days overdue (positive = overdue, negative = future)
            days_diff = (now - latest_log.next_due_at).days

            # Include if overdue or due soon
            if latest_log.next_due_at <= future_date:
                printers_due.append(PrinterMaintenanceDue(
                    printer_id=printer.id,
                    printer_code=printer.code,
                    printer_name=printer.name,
                    last_maintenance_date=latest_log.performed_at,
                    next_due_date=latest_log.next_due_at,
                    days_overdue=days_diff,
                    last_maintenance_type=MaintenanceType(latest_log.maintenance_type),
                ))

                if days_diff > 0:
                    total_overdue += 1
                else:
                    total_due_soon += 1

    # Sort by most overdue first
    printers_due.sort(key=lambda x: x.days_overdue if x.days_overdue else 0, reverse=True)

    return MaintenanceDueResponse(
        printers=printers_due,
        total_overdue=total_overdue,
        total_due_soon=total_due_soon,
    )


@router.get("/{log_id}", response_model=MaintenanceLogResponse)
async def get_maintenance_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Get a single maintenance log by ID"""
    log = db.query(MaintenanceLog).filter(MaintenanceLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Maintenance log not found")
    return _maintenance_to_response(log)


# ============================================================================
# Printer-specific Maintenance
# ============================================================================

@router.get("/printers/{printer_id}/maintenance", response_model=MaintenanceLogListResponse)
async def list_printer_maintenance(
    printer_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """List all maintenance logs for a specific printer"""
    # Verify printer exists
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    query = db.query(MaintenanceLog).filter(MaintenanceLog.printer_id == printer_id)

    # Get total count
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    logs = query.order_by(desc(MaintenanceLog.performed_at)).offset(offset).limit(page_size).all()

    return MaintenanceLogListResponse(
        items=[_maintenance_to_response(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/printers/{printer_id}/maintenance", response_model=MaintenanceLogResponse)
async def create_maintenance_log(
    printer_id: int,
    data: MaintenanceLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Add a maintenance log entry for a printer

    Records maintenance performed and optionally schedules next maintenance.
    """
    # Verify printer exists
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer not found")

    log = MaintenanceLog(
        printer_id=printer_id,
        maintenance_type=data.maintenance_type.value,
        description=data.description,
        performed_by=data.performed_by,
        performed_at=data.performed_at,
        next_due_at=data.next_due_at,
        cost=data.cost,
        downtime_minutes=data.downtime_minutes,
        parts_used=data.parts_used,
        notes=data.notes,
        created_at=datetime.now(timezone.utc),
    )

    db.add(log)
    db.commit()
    db.refresh(log)

    logger.info(
        f"Created maintenance log {log.id} for printer {printer.code}: "
        f"{data.maintenance_type.value} by {data.performed_by}"
    )

    return _maintenance_to_response(log)


@router.put("/{log_id}", response_model=MaintenanceLogResponse)
async def update_maintenance_log(
    log_id: int,
    data: MaintenanceLogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Update an existing maintenance log"""
    log = db.query(MaintenanceLog).filter(MaintenanceLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Maintenance log not found")

    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "maintenance_type" and value:
            value = value.value if hasattr(value, "value") else value
        setattr(log, field, value)

    db.commit()
    db.refresh(log)

    logger.info(f"Updated maintenance log {log.id}")
    return _maintenance_to_response(log)


@router.delete("/{log_id}")
async def delete_maintenance_log(
    log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """Delete a maintenance log"""
    log = db.query(MaintenanceLog).filter(MaintenanceLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Maintenance log not found")

    db.delete(log)
    db.commit()

    logger.info(f"Deleted maintenance log {log_id}")
    return {"message": f"Maintenance log {log_id} deleted successfully"}
