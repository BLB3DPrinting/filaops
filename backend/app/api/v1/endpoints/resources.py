"""
Resource scheduling API endpoints (API-403).

Handles:
- Get resource schedule
- Check for conflicts
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db, get_current_user
from app.models.manufacturing import Resource
from app.schemas.resource_scheduling import (
    ResourceScheduleResponse,
    ConflictCheckResponse,
    ConflictInfo,
    ScheduledOperationInfo,
)
from app.services.resource_scheduling import (
    get_resource_schedule,
    find_conflicts,
)

router = APIRouter()


@router.get(
    "/{resource_id}/schedule",
    response_model=ResourceScheduleResponse,
    summary="Get resource schedule"
)
def get_schedule(
    resource_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get scheduled operations for a resource.

    Args:
        resource_id: Resource to check
        start_date: Optional filter - operations ending after this time
        end_date: Optional filter - operations starting before this time

    Returns:
        List of operations scheduled on this resource
    """
    # Verify resource exists
    resource = db.get(Resource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    operations = get_resource_schedule(db, resource_id, start_date, end_date)

    return ResourceScheduleResponse(
        resource_id=resource_id,
        operations=[
            ScheduledOperationInfo(
                operation_id=op.id,
                production_order_id=op.production_order_id,
                production_order_code=op.production_order.code if op.production_order else None,
                operation_code=op.operation_code,
                operation_name=op.operation_name,
                scheduled_start=op.scheduled_start,
                scheduled_end=op.scheduled_end,
                status=op.status,
            )
            for op in operations
        ]
    )


@router.get(
    "/{resource_id}/conflicts",
    response_model=ConflictCheckResponse,
    summary="Check for scheduling conflicts"
)
def check_conflicts(
    resource_id: int,
    start: datetime,
    end: datetime,
    exclude_operation_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Check if a time range conflicts with existing scheduled operations.

    Args:
        resource_id: Resource to check
        start: Proposed start time
        end: Proposed end time
        exclude_operation_id: Operation to exclude (for rescheduling)

    Returns:
        Whether conflicts exist and list of conflicting operations
    """
    # Verify resource exists
    resource = db.get(Resource, resource_id)
    if not resource:
        raise HTTPException(status_code=404, detail="Resource not found")

    conflicts = find_conflicts(db, resource_id, start, end, exclude_operation_id)

    return ConflictCheckResponse(
        has_conflicts=len(conflicts) > 0,
        conflicts=[
            ConflictInfo(
                operation_id=op.id,
                production_order_id=op.production_order_id,
                production_order_code=op.production_order.code if op.production_order else None,
                operation_code=op.operation_code,
                scheduled_start=op.scheduled_start,
                scheduled_end=op.scheduled_end,
            )
            for op in conflicts
        ]
    )
