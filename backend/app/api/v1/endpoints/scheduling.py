"""
Scheduling and Capacity Management Endpoints

Provides endpoints for:
- Checking machine capacity and availability
- Finding available time slots
- Auto-scheduling production orders
"""
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from app.db.session import get_db
from app.models.production_order import ProductionOrder
from app.models.manufacturing import Resource
from app.models.work_center import WorkCenter
from app.models.print_job import PrintJob
from app.schemas.scheduling import (
    CapacityCheckRequest,
    CapacityCheckResponse,
    AvailableSlotResponse,
    MachineAvailabilityResponse,
)
from app.api.v1.deps import get_current_user
from app.core.features import require_tier, Tier
from app.models.user import User
from app.services.resource_compatibility_service import (
    is_machine_compatible,
)

router = APIRouter()


@router.get("/board")
async def get_scheduler_board(
    start_date: datetime = Query(..., description="Window start (ISO 8601)"),
    end_date: datetime = Query(..., description="Window end (ISO 8601)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SCHED-5: One-call payload for the Scheduler (Gantt) view.

    Returns every machine lane (machine-type Resources + Printers) with the
    operations scheduled on it inside the window, plus the unscheduled-orders
    work queue. Operations may be scheduled against either a Resource
    (scheduler modal path, op.resource_id) or a Printer (dispatch path,
    op.printer_id) — the two are distinct models with no FK between them, so
    lanes are keyed "resource-{id}" / "printer-{id}".

    Read-only; one query per concern (no per-lane N+1).
    """
    from sqlalchemy.orm import joinedload

    from app.models.maintenance import WINDOW_BLOCKING_STATUSES, MaintenanceWindow
    from app.models.printer import Printer
    from app.models.production_order import ProductionOrderOperation
    from app.services.maintenance_window_service import (
        sync_printer_maintenance_status,
    )
    from app.services.resource_scheduling import TERMINAL_STATUSES

    # SCHED-7 lazy seam: the board is one of the two surfaces that display
    # printer status, so it advances window state / flips printer status
    # before painting (see maintenance_window_service docstring).
    if sync_printer_maintenance_status(db):
        db.commit()

    # Scheduled_* columns are timezone-naive UTC, but values still in the
    # session identity map (or from other DBs) may carry tzinfo. Normalize
    # BOTH the window and every op timestamp to naive UTC so Python-side
    # clipping never mixes aware and naive datetimes.
    def _naive_utc(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    start_date = _naive_utc(start_date)
    end_date = _naive_utc(end_date)

    if end_date <= start_date:
        raise HTTPException(status_code=422, detail="end_date must be after start_date")

    window_hours = (end_date - start_date).total_seconds() / 3600

    # --- Lanes -----------------------------------------------------------
    resources = (
        db.query(Resource)
        .join(WorkCenter, Resource.work_center_id == WorkCenter.id)
        .filter(
            Resource.is_active.is_(True),
            WorkCenter.center_type == "machine",
        )
        .order_by(WorkCenter.code, Resource.code)
        .all()
    )
    printers = db.query(Printer).order_by(Printer.code).all()

    # --- Scheduled operations in window (single query) --------------------
    ops = (
        db.query(ProductionOrderOperation)
        .options(
            joinedload(ProductionOrderOperation.production_order)
            .joinedload(ProductionOrder.product)
        )
        .filter(
            ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
            ProductionOrderOperation.scheduled_start.isnot(None),
            ProductionOrderOperation.scheduled_end.isnot(None),
            ProductionOrderOperation.scheduled_start < end_date,
            ProductionOrderOperation.scheduled_end > start_date,
            or_(
                ProductionOrderOperation.resource_id.isnot(None),
                ProductionOrderOperation.printer_id.isnot(None),
            ),
        )
        .order_by(ProductionOrderOperation.scheduled_start)
        .all()
    )

    def _op_block(op) -> dict:
        po = op.production_order
        return {
            "id": op.id,
            "operation_code": op.operation_code,
            "operation_name": op.operation_name,
            "sequence": op.sequence,
            "status": op.status,
            # Normalize through _naive_utc so every serialized timestamp is a
            # naive-UTC string, matching the window echo and the frontend's
            # parseDateTime convention (appends 'Z' to naive strings).
            "scheduled_start": _naive_utc(op.scheduled_start).isoformat(),
            "scheduled_end": _naive_utc(op.scheduled_end).isoformat(),
            "planned_setup_minutes": (
                str(op.planned_setup_minutes)
                if op.planned_setup_minutes is not None
                else "0"
            ),
            "planned_run_minutes": (
                str(op.planned_run_minutes)
                if op.planned_run_minutes is not None
                else "0"
            ),
            "production_order_id": po.id if po else None,
            "production_order_code": po.code if po else None,
            "production_order_status": po.status if po else None,
            "product_name": po.product.name if po and po.product else None,
            "quantity": float(po.quantity_ordered) if po else None,
        }

    ops_by_lane: dict[str, list] = {}
    for op in ops:
        if op.printer_id is not None:
            key = f"printer-{op.printer_id}"
        else:
            key = f"resource-{op.resource_id}"
        ops_by_lane.setdefault(key, []).append(op)

    # --- Maintenance windows in window (single query, SCHED-7) -------------
    # Only blocking windows (scheduled / in_progress) render as blocks —
    # the same statuses the engine treats as busy time. A window completed
    # early must release its lane immediately, not ghost-block until its
    # scheduled ends_at; completed windows are history (MaintenanceLog).
    windows = (
        db.query(MaintenanceWindow)
        .filter(
            MaintenanceWindow.status.in_(WINDOW_BLOCKING_STATUSES),
            MaintenanceWindow.starts_at < end_date,
            MaintenanceWindow.ends_at > start_date,
        )
        .order_by(MaintenanceWindow.starts_at)
        .all()
    )

    windows_by_lane: dict[str, list] = {}
    for w in windows:
        if w.printer_id is not None:
            key = f"printer-{w.printer_id}"
        else:
            key = f"resource-{w.resource_id}"
        windows_by_lane.setdefault(key, []).append(w)

    def _window_block(w) -> dict:
        return {
            "id": w.id,
            "starts_at": _naive_utc(w.starts_at).isoformat(),
            "ends_at": _naive_utc(w.ends_at).isoformat(),
            "reason": w.reason,
            "status": w.status,
        }

    def _lane(kind: str, obj, work_center_code: Optional[str]) -> dict:
        key = f"{kind}-{obj.id}"
        lane_ops = ops_by_lane.get(key, [])
        # Utilization = scheduled time clipped to the window / window length
        busy_hours = 0.0
        for op in lane_ops:
            clip_start = max(_naive_utc(op.scheduled_start), start_date)
            clip_end = min(_naive_utc(op.scheduled_end), end_date)
            busy_hours += max(0.0, (clip_end - clip_start).total_seconds() / 3600)
        utilization = (busy_hours / window_hours * 100) if window_hours > 0 else 0.0
        return {
            "key": key,
            "kind": kind,
            "id": obj.id,
            "code": obj.code,
            "name": obj.name,
            "status": obj.status or "unknown",
            "work_center_code": work_center_code,
            "utilization_percent": round(min(utilization, 100.0), 1),
            "operations": [_op_block(op) for op in lane_ops],
            "windows": [_window_block(w) for w in windows_by_lane.get(key, [])],
        }

    lanes = [
        _lane("resource", r, r.work_center.code if r.work_center else None)
        for r in resources
    ]
    lanes += [_lane("printer", p, None) for p in printers]

    # --- Unscheduled work queue (single query) -----------------------------
    unscheduled_ops = (
        db.query(ProductionOrderOperation)
        .options(
            joinedload(ProductionOrderOperation.production_order)
            .joinedload(ProductionOrder.product)
        )
        .join(
            ProductionOrder,
            ProductionOrderOperation.production_order_id == ProductionOrder.id,
        )
        .filter(
            ProductionOrder.status.in_(["released", "scheduled", "in_progress"]),
            ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
            ProductionOrderOperation.scheduled_start.is_(None),
        )
        .order_by(
            ProductionOrder.priority,
            ProductionOrder.due_date.asc().nullslast(),
            ProductionOrderOperation.sequence,
        )
        .all()
    )

    unscheduled_by_po: dict[int, dict] = {}
    for op in unscheduled_ops:
        po = op.production_order
        if po.id not in unscheduled_by_po:
            unscheduled_by_po[po.id] = {
                "production_order_id": po.id,
                "production_order_code": po.code,
                "production_order_status": po.status,
                "product_name": po.product.name if po.product else None,
                "quantity": float(po.quantity_ordered or 0),
                "priority": po.priority,
                "due_date": po.due_date.isoformat() if po.due_date else None,
                "unscheduled_operation_count": 0,
                # First unscheduled op (lowest sequence) — click target for
                # the scheduler modal.
                "first_unscheduled_operation": _op_unscheduled_block(op),
            }
        unscheduled_by_po[po.id]["unscheduled_operation_count"] += 1

    return {
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "lanes": lanes,
        "unscheduled": list(unscheduled_by_po.values()),
    }


def _op_unscheduled_block(op) -> dict:
    """Minimal operation payload the OperationSchedulerModal needs."""
    return {
        "id": op.id,
        "operation_code": op.operation_code,
        "operation_name": op.operation_name,
        "sequence": op.sequence,
        "status": op.status,
        "planned_setup_minutes": (
            str(op.planned_setup_minutes)
            if op.planned_setup_minutes is not None
            else "0"
        ),
        "planned_run_minutes": (
            str(op.planned_run_minutes)
            if op.planned_run_minutes is not None
            else "0"
        ),
    }


@router.post("/capacity/check", response_model=CapacityCheckResponse)
async def check_capacity(
    request: CapacityCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check if a machine has capacity for a production order at a given time.
    
    Returns conflicts if any exist.
    """
    resource = db.query(Resource).filter(Resource.id == request.resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    start_time = request.start_time
    end_time = request.end_time

    # Get all scheduled orders for this resource
    # Find orders assigned to this resource via print_jobs or assigned_to
    scheduled_orders = db.query(ProductionOrder).join(
        PrintJob, ProductionOrder.id == PrintJob.production_order_id, isouter=True
    ).filter(
        and_(
            or_(
                PrintJob.printer_id == request.resource_id,
                ProductionOrder.assigned_to == resource.code,
            ),
            ProductionOrder.status.in_(["released", "in_progress"]),
            ProductionOrder.scheduled_start.isnot(None),
            ProductionOrder.scheduled_end.isnot(None),
        )
    ).all()

    conflicts = []
    for order in scheduled_orders:
        if not order.scheduled_start or not order.scheduled_end:
            continue
        
        order_start = order.scheduled_start
        order_end = order.scheduled_end
        
        # Check for overlap
        if start_time < order_end and end_time > order_start:
            conflicts.append({
                "order_id": order.id,
                "order_code": order.code,
                "start_time": order_start.isoformat(),
                "end_time": order_end.isoformat(),
                "product_name": order.product.name if order.product else "N/A",
            })

    return CapacityCheckResponse(
        resource_id=request.resource_id,
        resource_code=resource.code,
        resource_name=resource.name,
        start_time=start_time.isoformat(),
        end_time=end_time.isoformat(),
        has_capacity=len(conflicts) == 0,
        conflicts=conflicts,
    )


@router.get("/capacity/available-slots", response_model=List[AvailableSlotResponse])
async def get_available_slots(
    resource_id: int = Query(..., description="Resource ID"),
    start_date: datetime = Query(..., description="Start date for search"),
    end_date: datetime = Query(..., description="End date for search"),
    duration_hours: float = Query(2.0, description="Required duration in hours"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Find available time slots for a resource within a date range.
    
    Returns list of available slots that can accommodate the required duration.
    """
    resource = db.query(Resource).filter(Resource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    # Get all scheduled orders for this resource
    scheduled_orders = db.query(ProductionOrder).join(
        PrintJob, ProductionOrder.id == PrintJob.production_order_id, isouter=True
    ).filter(
        and_(
            or_(
                PrintJob.printer_id == resource_id,
                ProductionOrder.assigned_to == resource.code,
            ),
            ProductionOrder.status.in_(["released", "in_progress"]),
            ProductionOrder.scheduled_start.isnot(None),
            ProductionOrder.scheduled_end.isnot(None),
            ProductionOrder.scheduled_start >= start_date,
            ProductionOrder.scheduled_start <= end_date,
        )
    ).order_by(ProductionOrder.scheduled_start).all()

    # Build list of busy periods
    busy_periods = []
    for order in scheduled_orders:
        if order.scheduled_start and order.scheduled_end:
            busy_periods.append((order.scheduled_start, order.scheduled_end))

    # Find gaps between busy periods
    available_slots = []
    current_time = start_date

    # Sort busy periods by start time
    busy_periods.sort(key=lambda x: x[0])

    for busy_start, busy_end in busy_periods:
        # Check if there's a gap before this busy period
        gap_start = current_time
        gap_end = busy_start

        if gap_end > gap_start:
            gap_duration = (gap_end - gap_start).total_seconds() / 3600
            if gap_duration >= duration_hours:
                available_slots.append({
                    "start_time": gap_start.isoformat(),
                    "end_time": gap_end.isoformat(),
                    "duration_hours": gap_duration,
                })

        # Move current time to after this busy period
        current_time = max(current_time, busy_end)

    # Check for gap after last busy period
    if current_time < end_date:
        gap_duration = (end_date - current_time).total_seconds() / 3600
        if gap_duration >= duration_hours:
            available_slots.append({
                "start_time": current_time.isoformat(),
                "end_time": end_date.isoformat(),
                "duration_hours": gap_duration,
            })

    return available_slots


@router.get("/capacity/machine-availability", response_model=List[MachineAvailabilityResponse])
async def get_machine_availability(
    start_date: datetime = Query(..., description="Start date"),
    end_date: datetime = Query(..., description="End date"),
    work_center_id: Optional[int] = Query(None, description="Filter by work center"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get availability status for all machines in a date range.
    
    Shows capacity utilization and available time for each machine.
    """
    query = db.query(Resource).filter(Resource.is_active == True)  # noqa: E712
    
    if work_center_id:
        query = query.filter(Resource.work_center_id == work_center_id)
    else:
        # Only machine-type work centers
        query = query.join(WorkCenter).filter(WorkCenter.center_type == "machine")

    resources = query.all()

    result = []
    for resource in resources:
        # Get scheduled orders for this resource
        scheduled_orders = db.query(ProductionOrder).join(
            PrintJob, ProductionOrder.id == PrintJob.production_order_id, isouter=True
        ).filter(
            and_(
                or_(
                    PrintJob.printer_id == resource.id,
                    ProductionOrder.assigned_to == resource.code,
                ),
                ProductionOrder.status.in_(["released", "in_progress"]),
                ProductionOrder.scheduled_start.isnot(None),
                ProductionOrder.scheduled_end.isnot(None),
                ProductionOrder.scheduled_start >= start_date,
                ProductionOrder.scheduled_start <= end_date,
            )
        ).all()

        # Calculate total scheduled time
        total_scheduled_hours = 0
        for order in scheduled_orders:
            if order.scheduled_start and order.scheduled_end:
                duration = (order.scheduled_end - order.scheduled_start).total_seconds() / 3600
                total_scheduled_hours += duration

        # Calculate total available time
        total_hours = (end_date - start_date).total_seconds() / 3600
        available_hours = total_hours - total_scheduled_hours
        utilization_percent = (total_scheduled_hours / total_hours * 100) if total_hours > 0 else 0

        result.append({
            "resource_id": resource.id,
            "resource_code": resource.code,
            "resource_name": resource.name,
            "work_center_id": resource.work_center_id,
            "work_center_code": resource.work_center.code if resource.work_center else None,
            "status": resource.status,
            "total_hours": total_hours,
            "scheduled_hours": total_scheduled_hours,
            "available_hours": max(0, available_hours),
            "utilization_percent": round(utilization_percent, 1),
            "scheduled_order_count": len(scheduled_orders),
        })

    return result


@router.post("/auto-schedule")
@require_tier(Tier.PRO)
async def auto_schedule_order(
    order_id: int = Query(..., description="Production order ID"),
    preferred_start: Optional[datetime] = Query(None, description="Preferred start time"),
    work_center_id: Optional[int] = Query(None, description="Preferred work center"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Automatically find the best available slot for a production order.
    
    KEY FEATURE: Material-Machine Compatibility Aware Scheduling
    
    Considers:
    - Material-machine compatibility (e.g., ABS/ASA only on enclosed printers)
    - Machine availability
    - Due dates
    - Priorities
    - Preferred start time
    
    Automatically filters out incompatible machines before scheduling.
    """
    order = db.query(ProductionOrder).filter(ProductionOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Production order not found")

    # Estimate duration
    estimated_hours = order.estimated_time_minutes / 60 if order.estimated_time_minutes else 2.0

    # Determine search window
    search_start = preferred_start if preferred_start else datetime.now(timezone.utc)
    search_start = search_start.replace(minute=0, second=0, microsecond=0)
    search_end = search_start + timedelta(days=7)  # Search 7 days ahead

    # If order has due date, limit search to before due date
    if order.due_date:
        due_datetime = datetime.combine(order.due_date, datetime.min.time())
        if due_datetime < search_end:
            search_end = due_datetime

    # Get available machines
    query = db.query(Resource).filter(Resource.is_active == True)  # noqa: E712
    if work_center_id:
        query = query.filter(Resource.work_center_id == work_center_id)
    else:
        query = query.join(WorkCenter).filter(WorkCenter.center_type == "machine")

    resources = query.filter(
        Resource.status.in_(["available", "idle"])
    ).all()

    best_slot = None
    best_resource = None
    best_score = float("inf")  # Lower is better

    for resource in resources:
        # KEY FEATURE: Check material-machine compatibility
        is_compatible, reason = is_machine_compatible(db, resource, order)
        if not is_compatible:
            # Skip incompatible machines (e.g., ABS/ASA on non-enclosed printers)
            continue
        
        # Get scheduled orders for this resource
        scheduled_orders = db.query(ProductionOrder).join(
            PrintJob, ProductionOrder.id == PrintJob.production_order_id, isouter=True
        ).filter(
            and_(
                or_(
                    PrintJob.printer_id == resource.id,
                    ProductionOrder.assigned_to == resource.code,
                ),
                ProductionOrder.status.in_(["released", "in_progress"]),
                ProductionOrder.scheduled_start.isnot(None),
                ProductionOrder.scheduled_end.isnot(None),
                ProductionOrder.scheduled_start >= search_start,
                ProductionOrder.scheduled_start <= search_end,
            )
        ).order_by(ProductionOrder.scheduled_start).all()

        # Build busy periods
        busy_periods = []
        for scheduled_order in scheduled_orders:
            if scheduled_order.scheduled_start and scheduled_order.scheduled_end:
                busy_periods.append((scheduled_order.scheduled_start, scheduled_order.scheduled_end))

        # Find first available slot
        candidate_start = search_start
        for busy_start, busy_end in sorted(busy_periods):
            # Check if candidate fits before this busy period
            candidate_end = candidate_start + timedelta(hours=estimated_hours)
            if candidate_end <= busy_start:
                # Found a slot!
                score = (candidate_start - search_start).total_seconds() / 3600  # Hours from preferred start
                if score < best_score:
                    best_slot = candidate_start
                    best_resource = resource
                    best_score = score
                break

            # Move candidate to after this busy period
            candidate_start = busy_end + timedelta(minutes=15)  # 15 min buffer

        # Check if slot exists after all busy periods
        if candidate_start < search_end:
            candidate_end = candidate_start + timedelta(hours=estimated_hours)
            if candidate_end <= search_end:
                score = (candidate_start - search_start).total_seconds() / 3600
                if score < best_score:
                    best_slot = candidate_start
                    best_resource = resource
                    best_score = score

    if not best_slot or not best_resource:
        # Check if it's a compatibility issue
        incompatible_machines = []
        for resource in resources:
            is_compatible, reason = is_machine_compatible(db, resource, order)
            if not is_compatible:
                incompatible_machines.append(f"{resource.code}: {reason}")
        
        if incompatible_machines:
            detail = f"No compatible machines found. Material requirements: {', '.join(incompatible_machines)}"
        else:
            detail = "No available slots found. All compatible machines are fully scheduled."
        
        raise HTTPException(
            status_code=404,
            detail=detail
        )

    # Schedule the order
    scheduled_end = best_slot + timedelta(hours=estimated_hours)
    order.scheduled_start = best_slot
    order.scheduled_end = scheduled_end
    order.assigned_to = best_resource.code

    db.commit()
    db.refresh(order)

    return {
        "order_id": order.id,
        "order_code": order.code,
        "resource_id": best_resource.id,
        "resource_code": best_resource.code,
        "resource_name": best_resource.name,
        "scheduled_start": best_slot.isoformat(),
        "scheduled_end": scheduled_end.isoformat(),
    }


@router.get("/resource-conflicts")
async def get_resource_conflicts(
    resource_id: int = Query(..., description="Resource or printer ID"),
    start: str = Query(..., description="Start time (ISO 8601)"),
    end: str = Query(..., description="End time (ISO 8601)"),
    is_printer: bool = Query(False, description="True if resource is a printer"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check for scheduling conflicts on a resource/printer in a time range.

    Used by the frontend's live conflict checker to warn before submitting.
    Returns list of conflicting operations with their PO codes and times,
    plus maintenance-window conflicts (SCHED-7) discriminated by
    ``type: "maintenance"`` (operations carry ``type: "operation"``).
    """
    from app.services.resource_scheduling import (
        find_conflicts,
        find_window_conflicts,
    )

    # Parse ISO timestamps (handle trailing Z for UTC)
    try:
        start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_time = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="Invalid ISO 8601 timestamp for 'start' or 'end'"
        )

    conflicting_ops = find_conflicts(
        db=db,
        resource_id=resource_id,
        start_time=start_time,
        end_time=end_time,
        is_printer=is_printer,
    )

    conflicts = []
    for op in conflicting_ops:
        po = op.production_order
        conflicts.append({
            "type": "operation",
            "operation_id": op.id,
            "operation_code": op.operation_code,
            "production_order_code": po.code if po else None,
            "po_code": po.code if po else None,
            "scheduled_start": op.scheduled_start.isoformat() if op.scheduled_start else None,
            "scheduled_end": op.scheduled_end.isoformat() if op.scheduled_end else None,
        })

    # Maintenance windows — shaped so the existing ConflictAlert renders
    # them without changes ("Maintenance window - <reason> (start – end)").
    conflicting_windows = find_window_conflicts(
        db=db,
        resource_id=resource_id,
        start_time=start_time,
        end_time=end_time,
        is_printer=is_printer,
    )
    for w in conflicting_windows:
        conflicts.append({
            "type": "maintenance",
            "window_id": w.id,
            "operation_id": None,
            "operation_code": w.reason or "Scheduled downtime",
            "production_order_code": "Maintenance window",
            "po_code": "Maintenance window",
            "scheduled_start": w.starts_at.isoformat(),
            "scheduled_end": w.ends_at.isoformat(),
        })

    return {"conflicts": conflicts}

