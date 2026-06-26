"""Quality Plan API endpoints (#784) — CRUD for per-product inspection plans."""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.quality_plan import (
    QualityPlanCreate,
    QualityPlanResponse,
    QualityPlanUpdate,
)
from app.services import quality_plan_service as svc

router = APIRouter()


@router.get("", response_model=List[QualityPlanResponse])
def list_plans(
    product_id: Optional[int] = Query(None, description="Filter to one product"),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List quality plans, optionally filtered by product."""
    return svc.list_quality_plans(
        db, product_id=product_id, include_inactive=include_inactive
    )


@router.post("", response_model=QualityPlanResponse, status_code=201)
def create_plan(
    body: QualityPlanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a quality plan with its characteristics."""
    return svc.create_quality_plan(db, body)


@router.get("/{plan_id}", response_model=QualityPlanResponse)
def get_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return svc.get_quality_plan(db, plan_id)


@router.patch("/{plan_id}", response_model=QualityPlanResponse)
def update_plan(
    plan_id: int,
    body: QualityPlanUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update header fields; a provided ``characteristics`` list replaces them all."""
    return svc.update_quality_plan(db, plan_id, body)


@router.delete("/{plan_id}", response_model=QualityPlanResponse)
def deactivate_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: deactivate the plan (no hard delete — it may be referenced)."""
    return svc.deactivate_quality_plan(db, plan_id)
