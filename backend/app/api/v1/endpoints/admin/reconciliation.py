"""
Admin: Inventory Reconciliation Report endpoint (HARD-4b).

GET /api/v1/admin/inventory/reconciliation
  Returns one row per Inventory record comparing stored on_hand against
  the transaction-ledger sum for the item's epoch.

  Query params:
    drifted_only (bool, default False): return only items where
      stored_on_hand != ledger_sum.

Staff-gated: uses the same router-level dependency as mrp.py (post-#683).
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.services.reconciliation_service import (
    ReconciliationItem,
    get_reconciliation_report,
)

router = APIRouter(
    prefix="/inventory/reconciliation",
    tags=["Admin - Inventory Reconciliation"],
    dependencies=[Depends(get_current_staff_user)],
)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class ReconciliationItemSchema(BaseModel):
    inventory_id: int
    product_id: int
    sku: str
    name: str
    location_id: int
    location_name: Optional[str]

    stored_on_hand: float
    ledger_sum: float
    drift: float

    baseline_timestamp: Optional[datetime]
    is_counted: bool
    has_drift: bool

    model_config = {"from_attributes": True}


class ReconciliationReportSchema(BaseModel):
    items: List[ReconciliationItemSchema]
    total_items: int
    drifted_items: int
    uncounted_items: int


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("", response_model=ReconciliationReportSchema)
def get_inventory_reconciliation(
    drifted_only: bool = Query(
        False,
        description="Return only items where stored on_hand diverges from ledger sum",
    ),
    db: Session = Depends(get_db),
):
    """
    Inventory reconciliation report — the operator's counting work queue.

    Each row compares the stored ``on_hand_quantity`` against the sum of
    transaction-ledger quantities for the item's epoch:

    - Items with a ``baseline_timestamp`` sum only transactions at-or-after
      that timestamp (post-count history).
    - Items with ``baseline_timestamp = null`` sum ALL transactions and are
      shown as **uncounted** — they belong at the top of the physical-count
      queue.

    ``drift = stored_on_hand - ledger_sum``.  Non-zero drift means the stored
    balance diverged from what the ledger recorded — likely a SET-style write
    outside the canonical poster, a pre-4a legacy write, or unrecorded
    physical movement (scrap/remake).  Drift direction matters:

    - positive drift → stored is higher than ledger (phantom stock)
    - negative drift → stored is lower (consumed but not recorded)
    """
    service_rows = get_reconciliation_report(db, drifted_only=drifted_only)

    items = [
        ReconciliationItemSchema(
            inventory_id=r.inventory_id,
            product_id=r.product_id,
            sku=r.sku,
            name=r.name,
            location_id=r.location_id,
            location_name=r.location_name,
            stored_on_hand=float(r.stored_on_hand),
            ledger_sum=float(r.ledger_sum),
            drift=float(r.drift),
            baseline_timestamp=r.baseline_timestamp,
            is_counted=r.is_counted,
            has_drift=r.has_drift,
        )
        for r in service_rows
    ]

    all_rows = get_reconciliation_report(db) if drifted_only else service_rows

    return ReconciliationReportSchema(
        items=items,
        total_items=len(all_rows) if drifted_only else len(items),
        drifted_items=sum(1 for r in (all_rows if drifted_only else service_rows) if r.has_drift),
        uncounted_items=sum(1 for r in all_rows if not r.is_counted),
    )
