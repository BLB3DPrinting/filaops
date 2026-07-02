"""
Scheduling and Capacity Management Endpoints

Provides endpoints for:
- Checking machine capacity and availability
- Finding available time slots
- Auto-scheduling production orders
"""
from datetime import datetime, timezone, timedelta
from math import ceil
from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.session import get_db
from app.models.production_order import ProductionOrder
from app.models.manufacturing import Resource
from app.models.printer import Printer
from app.models.work_center import WorkCenter
from app.schemas.scheduling import (
    CapacityCheckRequest,
    CapacityCheckResponse,
    ConflictInfo,
    AvailableSlotResponse,
    MachineAvailabilityResponse,
)
from app.api.v1.deps import get_current_user
from app.core.licensing_gate import require_feature
from app.models.user import User
from app.services.resource_compatibility_service import (
    is_machine_compatible,
)
from app.services.resource_scheduling import (
    TERMINAL_STATUSES,
    MaintenanceWindowConflictError,
    SequenceError,
    find_conflicts,
    find_next_available_slot,
    find_window_conflicts,
    get_resource_schedule,
    schedule_operation,
)

router = APIRouter()


def _naive_utc(dt: datetime) -> datetime:
    """Normalize to naive UTC — scheduling columns are TIMESTAMP WITHOUT TIME
    ZONE holding UTC, so aware request datetimes must be converted before any
    Python-side comparison (naive-vs-aware comparison raises TypeError)."""
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _resolve_machine(db: Session, machine_id: int, is_printer: bool):
    """Fetch the Resource or Printer a capacity question is about (404 if absent).

    Resources and Printers are distinct models with separate ID spaces — they
    must never be cross-compared (the old capacity queries joined
    PrintJob.printer_id against Resource.id, matching only on coincidence)."""
    if is_printer:
        machine = db.query(Printer).filter(Printer.id == machine_id).first()
        if not machine:
            raise HTTPException(status_code=404, detail="Printer not found")
    else:
        machine = db.query(Resource).filter(Resource.id == machine_id).first()
        if not machine:
            raise HTTPException(status_code=404, detail="Resource not found")
    return machine


def _busy_intervals(
    db: Session,
    machine_id: int,
    start: datetime,
    end: datetime,
    is_printer: bool,
) -> List[Tuple[datetime, datetime]]:
    """All busy time on a machine in [start, end): scheduled operations plus
    blocking maintenance windows, as naive-UTC (start, end) pairs sorted by
    start. Interval-overlap windowing, so work already running at `start` is
    included (a start-based filter would hide it and allow double-booking)."""
    intervals: List[Tuple[datetime, datetime]] = []
    for op in get_resource_schedule(
        db, machine_id, start_date=start, end_date=end, is_printer=is_printer
    ):
        intervals.append(
            (_naive_utc(op.scheduled_start), _naive_utc(op.scheduled_end))
        )
    for w in find_window_conflicts(
        db, resource_id=machine_id, start_time=start, end_time=end, is_printer=is_printer
    ):
        intervals.append((_naive_utc(w.starts_at), _naive_utc(w.ends_at)))
    intervals.sort(key=lambda pair: pair[0])
    return intervals


def _merged_hours(intervals: List[Tuple[datetime, datetime]]) -> float:
    """Total hours covered by the union of (start, end) intervals (overlaps
    counted once). Input must be sorted by start."""
    total = 0.0
    cursor: Optional[datetime] = None
    for s, e in intervals:
        if cursor is None or s > cursor:
            total += (e - s).total_seconds() / 3600
            cursor = e
        elif e > cursor:
            total += (e - cursor).total_seconds() / 3600
            cursor = e
    return total


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

    Busy time is what the scheduler actually books: ProductionOrderOperation
    rows (the modal/dispatch write path) plus blocking maintenance windows —
    NOT the order-level scheduled_* columns, which the operation path never
    populates (#857 G1).
    """
    machine = _resolve_machine(db, request.resource_id, request.is_printer)
    start_time = _naive_utc(request.start_time)
    end_time = _naive_utc(request.end_time)
    if end_time <= start_time:
        raise HTTPException(status_code=422, detail="end_time must be after start_time")

    conflicts: List[ConflictInfo] = []
    for op in find_conflicts(
        db,
        resource_id=request.resource_id,
        start_time=start_time,
        end_time=end_time,
        is_printer=request.is_printer,
    ):
        po = op.production_order
        conflicts.append(ConflictInfo(
            type="operation",
            order_id=po.id if po else None,
            order_code=po.code if po else None,
            operation_id=op.id,
            operation_code=op.operation_code,
            start_time=op.scheduled_start.isoformat(),
            end_time=op.scheduled_end.isoformat(),
            product_name=po.product.name if po and po.product else "N/A",
        ))

    for w in find_window_conflicts(
        db,
        resource_id=request.resource_id,
        start_time=start_time,
        end_time=end_time,
        is_printer=request.is_printer,
    ):
        conflicts.append(ConflictInfo(
            type="maintenance",
            order_id=None,
            order_code=None,
            start_time=w.starts_at.isoformat(),
            end_time=w.ends_at.isoformat(),
            product_name=w.reason or "Scheduled downtime",
        ))

    return CapacityCheckResponse(
        resource_id=request.resource_id,
        resource_code=machine.code,
        resource_name=machine.name,
        start_time=start_time.isoformat(),
        end_time=end_time.isoformat(),
        has_capacity=len(conflicts) == 0,
        conflicts=conflicts,
    )


@router.get("/capacity/available-slots", response_model=List[AvailableSlotResponse])
async def get_available_slots(
    resource_id: int = Query(..., description="Resource or printer ID"),
    start_date: datetime = Query(..., description="Start date for search"),
    end_date: datetime = Query(..., description="End date for search"),
    duration_hours: float = Query(2.0, description="Required duration in hours"),
    is_printer: bool = Query(False, description="True if resource_id is a printer"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Find available time slots for a machine within a date range.

    Gaps are computed against real bookings — scheduled operations plus
    blocking maintenance windows (#857 G1) — not the vestigial order-level
    scheduled_* columns.
    """
    _resolve_machine(db, resource_id, is_printer)
    start_date = _naive_utc(start_date)
    end_date = _naive_utc(end_date)
    if end_date <= start_date:
        raise HTTPException(status_code=422, detail="end_date must be after start_date")

    busy_periods = _busy_intervals(db, resource_id, start_date, end_date, is_printer)

    # Find gaps between busy periods
    available_slots = []
    current_time = start_date

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

    Utilization is derived from real bookings — scheduled operations, clipped
    to the window (#857 G1) — and available time additionally excludes
    blocking maintenance windows.
    """
    start_date = _naive_utc(start_date)
    end_date = _naive_utc(end_date)
    if end_date <= start_date:
        raise HTTPException(status_code=422, detail="end_date must be after start_date")

    query = db.query(Resource).filter(Resource.is_active == True)  # noqa: E712

    if work_center_id:
        query = query.filter(Resource.work_center_id == work_center_id)
    else:
        # Only machine-type work centers
        query = query.join(WorkCenter).filter(WorkCenter.center_type == "machine")

    resources = query.all()

    total_hours = (end_date - start_date).total_seconds() / 3600

    result = []
    for resource in resources:
        ops = get_resource_schedule(
            db, resource.id, start_date=start_date, end_date=end_date, is_printer=False
        )

        # Clip each booking to the window (an op overlapping the boundary only
        # consumes the in-window part — mirrors the board's utilization math).
        op_intervals = []
        for op in ops:
            clip_start = max(_naive_utc(op.scheduled_start), start_date)
            clip_end = min(_naive_utc(op.scheduled_end), end_date)
            if clip_end > clip_start:
                op_intervals.append((clip_start, clip_end))
        op_intervals.sort(key=lambda pair: pair[0])
        total_scheduled_hours = _merged_hours(op_intervals)

        # Available time also excludes blocking maintenance windows — a machine
        # in maintenance is not available even though no work is scheduled.
        window_intervals = []
        for w in find_window_conflicts(
            db, resource_id=resource.id, start_time=start_date, end_time=end_date,
            is_printer=False,
        ):
            clip_start = max(_naive_utc(w.starts_at), start_date)
            clip_end = min(_naive_utc(w.ends_at), end_date)
            if clip_end > clip_start:
                window_intervals.append((clip_start, clip_end))
        busy_union = sorted(op_intervals + window_intervals, key=lambda pair: pair[0])
        available_hours = total_hours - _merged_hours(busy_union)

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
            "scheduled_order_count": len({op.production_order_id for op in ops}),
        })

    return result


@router.post(
    "/auto-schedule",
    # Auth runs FIRST so an anonymous request gets 401 (not authenticated) — it
    # must not learn that this is a PRO-gated feature. FastAPI caches identical
    # sub-dependencies per request, so the current_user param below does not
    # re-execute get_current_user.
    dependencies=[
        Depends(get_current_user),
        Depends(require_feature("production_advanced")),
    ],
)
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

    # Estimate duration: quote-derived estimate when present, else the routing's
    # planned minutes (already quantity-scaled by copy_routing_to_operations) —
    # WOs generated from sales orders never set estimated_time_minutes, so the
    # bare 2h default sized every routing-driven job wrong (#857 G3).
    if order.estimated_time_minutes:
        estimated_hours = order.estimated_time_minutes / 60
    else:
        planned_minutes = sum(
            float(op.planned_setup_minutes or 0) + float(op.planned_run_minutes or 0)
            for op in order.operations
            if op.status not in TERMINAL_STATUSES
        )
        estimated_hours = planned_minutes / 60 if planned_minutes > 0 else 2.0

    # Determine search window. Naive UTC throughout — the scheduling columns
    # are naive UTC and mixing aware/naive datetimes raises TypeError (#857 G5).
    search_start = _naive_utc(preferred_start) if preferred_start else _naive_utc(
        datetime.now(timezone.utc)
    )
    # Round UP to the next whole hour — flooring would move the search (and the
    # resulting booking) earlier than the requested/current time.
    rounded_start = search_start.replace(minute=0, second=0, microsecond=0)
    if rounded_start != search_start:
        rounded_start += timedelta(hours=1)
    search_start = rounded_start
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

        # Delegate the gap search to the same engine the scheduler modal uses:
        # busy time = scheduled operations + blocking maintenance windows, with
        # interval-overlap semantics and a monotonic cursor. The previous
        # hand-rolled loop read order-level columns nothing populates, ignored
        # maintenance windows, hid already-running work behind a start-based
        # filter, and could walk its cursor backward on nested busy periods —
        # all double-booking paths (#857 G1/G5).
        slot = find_next_available_slot(
            db,
            resource_id=resource.id,
            # Round UP: truncating would accept a gap shorter than the actual
            # scheduled duration (candidate_end uses the exact hours).
            duration_minutes=ceil(estimated_hours * 60),
            after=search_start,
            is_printer=False,
        )
        candidate_end = slot + timedelta(hours=estimated_hours)
        if candidate_end > search_end:
            continue  # No fit inside the window on this machine

        score = (slot - search_start).total_seconds() / 3600
        if score < best_score:
            best_slot = slot
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

        # 409, not 404: the order exists — there is no slot. 404 is reserved for
        # missing routes/entities and the frontend treats it as "PRO plugin not
        # installed" (#857 G8).
        raise HTTPException(
            status_code=409,
            detail=detail
        )

    scheduled_end = best_slot + timedelta(hours=estimated_hours)

    # Persist the booking on the operation plane — the plane every conflict /
    # capacity read uses. Writing only the order-level columns would leave this
    # booking invisible to the next capacity check or auto-schedule call
    # (self-double-booking). Ops are placed back-to-back in sequence order
    # inside the validated gap; schedule_operation re-validates conflicts,
    # maintenance windows, and predecessor sequencing per op.
    schedulable_ops = [
        op for op in sorted(order.operations, key=lambda o: o.sequence)
        if op.status not in TERMINAL_STATUSES and op.scheduled_start is None
    ]
    if schedulable_ops:
        # Per-op share of the whole-order estimate, proportional to planned
        # minutes (identical to planned minutes when the estimate came from
        # them); an even split when no op carries planned time. Totals exactly
        # estimated_hours, the size find_next_available_slot validated.
        total_planned = sum(
            float(op.planned_setup_minutes or 0) + float(op.planned_run_minutes or 0)
            for op in schedulable_ops
        )
        cursor = best_slot
        try:
            for op in schedulable_ops:
                planned = float(op.planned_setup_minutes or 0) + float(op.planned_run_minutes or 0)
                if total_planned > 0:
                    share_hours = estimated_hours * (planned / total_planned)
                else:
                    share_hours = estimated_hours / len(schedulable_ops)
                op_end = cursor + timedelta(hours=share_hours)
                ok, op_conflicts = schedule_operation(
                    db, op, best_resource.id, cursor, op_end, is_printer=False
                )
                if not ok:
                    codes = ", ".join(
                        c.production_order.code if c.production_order else str(c.id)
                        for c in op_conflicts
                    )
                    raise HTTPException(
                        status_code=409,
                        detail=f"Slot was taken while scheduling: conflicts with {codes}",
                    )
                cursor = op_end
        except (SequenceError, MaintenanceWindowConflictError) as e:
            raise HTTPException(status_code=409, detail=str(e))
    # else: routing-less order — no operation rows exist to book; the order-
    # level columns below are the only representation (matching how such
    # orders are scheduled everywhere else).

    # Order-level envelope kept for legacy readers (PO detail/list responses,
    # CompleteOrderModal display).
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

