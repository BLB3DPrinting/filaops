"""
API endpoint for closing a production order that made nothing as scrapped.

Lives apart from production_orders.py, which is past the DEBT-1 size limit and
must not take on new responsibilities.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_staff_user, get_db
from app.api.v1.endpoints.production_orders import build_production_order_response
from app.models import User
from app.schemas.production_order import CloseScrappedRequest, ProductionOrderResponse
from app.services import production_order_service

router = APIRouter()


@router.post("/{order_id}/close-scrapped", response_model=ProductionOrderResponse)
def close_scrapped(
    order_id: int,
    request: Optional[CloseScrappedRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
) -> ProductionOrderResponse:
    """Close a short order with nothing completed and everything scrapped.

    A whole-plate failure leaves the order short with zero completed, which
    accept-short refuses. This moves it to the terminal 'scrapped' status,
    keeps its sales-order link, releases what it still reserves and sweeps the
    leftover WIP to 5200. Nothing is received into inventory.
    """
    order = production_order_service.close_scrapped_production_order(
        db,
        order_id,
        user_email=current_user.email,
        user_id=current_user.id,
        notes=request.notes if request else None,
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)
