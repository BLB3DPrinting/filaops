"""
Consolidated Buy List endpoint — HARD-7.

GET /buy-list        — returns the live, computed-on-demand buy list.

Staff-only (same dependency as all MRP endpoints post-HARD-1).
ZERO writes — pure read.  Never calls run_mrp.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_staff_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.buy_list import BuyListResponse
from app.services.buy_list_service import get_buy_list

router = APIRouter(
    prefix="/buy-list",
    tags=["buy-list"],
    dependencies=[Depends(get_current_staff_user)],
)


@router.get("", response_model=BuyListResponse)
async def read_buy_list(
    vendor_id: Optional[int] = Query(
        default=None,
        description="Filter to a single preferred vendor (by vendor ID).",
    ),
    _current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
) -> BuyListResponse:
    """
    Return the consolidated buy list.

    Computes gross component demand across **all** open sales orders and open
    production orders, nets against on-hand + on-order + safety stock, and
    returns only the components that are still short.

    Per the HARD-7 three-layer design this is always computed fresh — there is
    no stored MRP run artifact to go stale.

    ### Response
    - **summary** — counts + total estimated buy value + draft-PO transparency
    - **items** — one row per short component, sorted by preferred vendor then
      earliest need; includes incoming PO detail with status labels so operators
      can see uncommitted (draft) supply for what it is.

    ### Create PO
    Use the existing PO creation endpoint with the suggested vendor and qty
    from this response.  The frontend buy-list page provides a per-row
    "Create PO" button that pre-fills vendor + suggested qty into the
    POCreateModal.
    """
    return get_buy_list(db, vendor_id=vendor_id)
