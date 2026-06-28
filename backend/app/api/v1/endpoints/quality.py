"""
Quality Management API endpoints.

Provides dashboard data: inspection queue, quality metrics,
recent inspections, and scrap analysis.
"""
from fastapi import APIRouter, Depends, Query
from typing import List
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.services import quality_service as svc
from app.services.quality_policy import get_quality_policy
from app.schemas.quality import (
    InspectionQueueResponse,
    QualityMetricsResponse,
    QualityPolicyResponse,
    RecentInspectionItem,
    ScrapSummaryItem,
)

router = APIRouter()


@router.get("/policy", response_model=QualityPolicyResponse)
def get_policy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the company's QC rigor configuration (the selectable "dial").

    The UI reads this to decide whether to show QC surfaces at all and, when on,
    whether to run the simple (basic) or plan-driven (full) experience. Readable
    by any authenticated user; changing it is an admin action via
    PUT /system/settings/quality_mode.
    """
    policy = get_quality_policy(db)
    return QualityPolicyResponse(
        mode=policy.mode.value,
        gate_action=policy.gate_action.value,
        gate_close=policy.gate_close,
        surfaces_enabled=policy.surfaces_enabled,
        plan_driven=policy.plan_driven,
        gates_close=policy.gates_close,
    )


@router.get("/inspection-queue", response_model=InspectionQueueResponse)
def get_inspection_queue(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get production orders awaiting QC inspection.

    Returns orders with qc_status 'pending' or 'in_progress',
    sorted by priority (highest first) then due date (earliest first).
    """
    return svc.get_inspection_queue(db, limit=limit, offset=offset)


@router.get("/metrics", response_model=QualityMetricsResponse)
def get_quality_metrics(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get aggregate quality metrics for the given period.

    Returns first-pass yield, scrap rate, inspection counts, and
    total scrap cost for the specified number of days.
    """
    return svc.get_quality_metrics(db, days=days)


@router.get("/recent-inspections", response_model=List[RecentInspectionItem])
def get_recent_inspections(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get recently completed QC inspections, newest first.
    """
    return svc.get_recent_inspections(db, limit=limit)


@router.get("/scrap-summary", response_model=List[ScrapSummaryItem])
def get_scrap_summary(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get scrap breakdown grouped by reason for the given period.
    """
    return svc.get_scrap_summary(db, days=days)
