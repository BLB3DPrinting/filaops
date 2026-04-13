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
    get_material_requirements,
    machine_has_enclosure,
    is_machine_compatible,
)

router = APIRouter()


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
    Returns list of conflicting operations with their PO codes and times.
    """
    from app.services.resource_scheduling import find_conflicts

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
            "operation_id": op.id,
            "operation_code": op.operation_code,
            "production_order_code": po.code if po else None,
            "po_code": po.code if po else None,
            "scheduled_start": op.scheduled_start.isoformat() if op.scheduled_start else None,
            "scheduled_end": op.scheduled_end.isoformat() if op.scheduled_end else None,
        })

    return {"conflicts": conflicts}

