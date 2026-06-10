"""
Admin: Reservation Reconciliation endpoint (HARD-5).

GET  /api/v1/admin/inventory/reservations/reconciliation
     Returns the allocation drift report (stored vs ledger-derived allocated_quantity)
     and the stranded-allocation list for every inventory row.

POST /api/v1/admin/inventory/reservations/repair/{production_order_id}
     Release stranded allocations for a specific terminal/deleted production order.
     Staff-gated, requires explicit confirmation via request body.

Both endpoints are staff-gated via the router-level dependency.
"""
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.services.reservation_reconciliation_service import (
    get_allocation_reconciliation_report,
    release_stranded_allocations,
)

router = APIRouter(
    prefix="/inventory/reservations",
    tags=["Admin - Reservation Reconciliation"],
    dependencies=[Depends(get_current_staff_user)],
)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class AllocationDriftItemSchema(BaseModel):
    inventory_id: int
    product_id: int
    sku: str
    name: str
    location_id: int
    location_name: Optional[str]

    on_hand: float
    stored_allocated: float
    ledger_allocated: float
    drift: float

    has_drift: bool
    stored_available: float
    ledger_available: float

    model_config = {"from_attributes": True}


class StrandedAllocationItemSchema(BaseModel):
    production_order_id: int
    production_order_code: str
    status: str
    product_id: int
    sku: str
    name: str
    location_id: int
    net_reserved: float
    stranded_reason: str
    completed_at: Optional[datetime]
    cancelled_at: Optional[datetime]

    model_config = {"from_attributes": True}


class AllocationReconciliationReportSchema(BaseModel):
    drift_items: List[AllocationDriftItemSchema]
    stranded_items: List[StrandedAllocationItemSchema]

    total_inventory_rows: int
    drifted_rows: int
    stranded_po_count: int
    total_stranded_quantity: float
    generated_at: datetime


class RepairRequestSchema(BaseModel):
    confirm: bool = Field(
        ...,
        description="Must be true to confirm the repair action.",
    )
    reason: str = Field(
        default="Staff-initiated stranded allocation release",
        description="Human-readable reason recorded in the audit transaction.",
        max_length=500,
    )


class ReleaseResultItemSchema(BaseModel):
    product_id: int
    sku: str
    name: str
    location_id: int
    quantity_released: float
    old_allocated: float
    new_allocated: float


class RepairResultSchema(BaseModel):
    production_order_id: int
    production_order_code: Optional[str]
    releases: List[ReleaseResultItemSchema]
    total_released_items: int
    errors: List[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/reconciliation", response_model=AllocationReconciliationReportSchema)
def get_reservation_reconciliation(
    drifted_only: bool = Query(
        False,
        description=(
            "Return only inventory rows where stored allocated_quantity diverges "
            "from the ledger-derived sum."
        ),
    ),
    db: Session = Depends(get_db),
):
    """
    Reservation / allocation reconciliation report.

    Returns two sections:

    **drift_items** — per-inventory-row comparison of stored ``allocated_quantity``
    vs the sum derived from reservation/reservation_release ledger rows.
    A non-zero drift means the lump-sum column diverged from the audit trail.

    **stranded_items** — production orders in a terminal state (complete, cancelled,
    closed) or deleted, that still have a positive net reservation in the ledger.
    These permanently reduce available quantity and poison MRP until repaired.

    Use the ``POST /repair/{production_order_id}`` endpoint to release a specific
    stranded allocation after explicit staff confirmation.
    """
    report = get_allocation_reconciliation_report(db, drifted_only=drifted_only)

    all_report = (
        get_allocation_reconciliation_report(db)
        if drifted_only
        else report
    )

    drift_schemas = [
        AllocationDriftItemSchema(
            inventory_id=d.inventory_id,
            product_id=d.product_id,
            sku=d.sku,
            name=d.name,
            location_id=d.location_id,
            location_name=d.location_name,
            on_hand=float(d.on_hand),
            stored_allocated=float(d.stored_allocated),
            ledger_allocated=float(d.ledger_allocated),
            drift=float(d.drift),
            has_drift=d.has_drift,
            stored_available=float(d.stored_available),
            ledger_available=float(d.ledger_available),
        )
        for d in report.drift_items
    ]

    stranded_schemas = [
        StrandedAllocationItemSchema(
            production_order_id=s.production_order_id,
            production_order_code=s.production_order_code,
            status=s.status,
            product_id=s.product_id,
            sku=s.sku,
            name=s.name,
            location_id=s.location_id,
            net_reserved=float(s.net_reserved),
            stranded_reason=s.stranded_reason,
            completed_at=s.completed_at,
            cancelled_at=s.cancelled_at,
        )
        for s in report.stranded_items
    ]

    return AllocationReconciliationReportSchema(
        drift_items=drift_schemas,
        stranded_items=stranded_schemas,
        total_inventory_rows=all_report.total_inventory_rows,
        drifted_rows=all_report.drifted_rows,
        stranded_po_count=all_report.stranded_po_count,
        total_stranded_quantity=float(all_report.total_stranded_quantity),
        generated_at=report.generated_at,
    )


@router.post(
    "/repair/{production_order_id}",
    response_model=RepairResultSchema,
)
def repair_stranded_allocations(
    production_order_id: int = Path(
        ...,
        description="Production order ID whose stranded allocations to release.",
    ),
    body: RepairRequestSchema = ...,
    current_user=Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Release stranded allocations for a specific production order.

    **This is a destructive, irreversible action.**  Calling this endpoint
    decreases ``Inventory.allocated_quantity`` by the net reservation quantity
    for the specified production order and writes a ``reservation_release``
    audit transaction.

    Guards:
    - ``confirm`` must be ``true`` in the request body.
    - The production order must be in a terminal state
      (``complete``, ``completed``, ``cancelled``, ``closed``) or deleted.
    - Live (non-terminal) orders are rejected — cancel or complete the order
      first.

    Idempotent: if the PO already has no net reservation, returns an empty
    releases list (no error).
    """
    if not body.confirm:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=(
                "You must set confirm=true to release stranded allocations. "
                "This action is irreversible."
            ),
        )

    released_by = getattr(current_user, "email", str(current_user))

    result = release_stranded_allocations(
        db=db,
        production_order_id=production_order_id,
        released_by=released_by,
        reason=body.reason,
    )

    # Commit only if no errors (partial-failure stays rolled back)
    if not result["errors"]:
        db.commit()
    else:
        db.rollback()

    return RepairResultSchema(
        production_order_id=result["production_order_id"],
        production_order_code=result.get("production_order_code"),
        releases=[ReleaseResultItemSchema(**r) for r in result["releases"]],
        total_released_items=result["total_released_items"],
        errors=result["errors"],
    )
