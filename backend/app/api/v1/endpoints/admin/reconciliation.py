"""
Admin: Inventory Reconciliation Report + Baseline endpoints (HARD-4b + HARD-4c).

GET  /api/v1/admin/inventory/reconciliation
  Returns one row per Inventory record comparing stored on_hand against
  the transaction-ledger sum for the item's epoch.

  Query params:
    drifted_only (bool, default False): return only items where
      stored_on_hand != ledger_sum.

POST /api/v1/admin/inventory/reconciliation/count
  Record a physical count for one (product_id, location_id) pair.
  Computes delta = counted_qty - stored, posts a reconciliation_baseline
  transaction through the canonical ledger, stamps baseline_timestamp, and
  creates the matching GL entry (cycle-count variance semantics).

POST /api/v1/admin/inventory/reconciliation/count/all-to-stored
  EXPLICIT FALLBACK: stamp baseline_timestamp to NOW with zero delta for
  every inventory row (or one row if product_id + location_id are supplied).
  Does NOT write ledger rows -- only stamps the epoch.
  Requires {"confirm": "BASELINE_TO_STORED"} in the request body.
  Labeled "Baseline to stored -- dev/test only" in the UI.

Staff-gated: uses the same router-level dependency as mrp.py (post-#683).
"""
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.models.user import User
from app.services.reconciliation_service import (
    BASELINE_TO_STORED_CONFIRM_TOKEN,
    baseline_to_stored,
    get_reconciliation_report,
    post_reconciliation_baseline,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/inventory/reconciliation",
    tags=["Admin - Inventory Reconciliation"],
    dependencies=[Depends(get_current_staff_user)],
)


# ---------------------------------------------------------------------------
# Response schemas
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


class CountEntryRequest(BaseModel):
    """Payload for a single physical count entry."""
    product_id: int = Field(..., description="Product being counted")
    location_id: int = Field(..., description="Inventory location being counted")
    counted_qty: float = Field(..., ge=0, description="Physically counted quantity (>= 0)")
    notes: Optional[str] = Field(None, max_length=500, description="Optional count note")


class CountEntryResponse(BaseModel):
    """Response from a count entry."""
    transaction_id: Optional[int] = Field(
        None, description="Ledger transaction id, or null if delta was zero"
    )
    delta: float = Field(..., description="Signed delta applied (counted - stored)")
    baseline_timestamp: datetime = Field(..., description="New epoch anchor")
    message: str


class FallbackRequest(BaseModel):
    """Payload for the explicit stored-as-baseline fallback."""
    confirm: str = Field(
        ...,
        description=(
            f'Must equal "{BASELINE_TO_STORED_CONFIRM_TOKEN}" to prevent '
            "accidental invocation"
        ),
    )
    product_id: Optional[int] = Field(
        None,
        description="Specific product to baseline (omit to process ALL inventory rows)",
    )
    location_id: Optional[int] = Field(
        None,
        description=(
            "Specific location to baseline (required when product_id is supplied)"
        ),
    )


class FallbackResponse(BaseModel):
    stamped_rows: int = Field(..., description="Number of inventory rows stamped")
    message: str


# ---------------------------------------------------------------------------
# GET: reconciliation report
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
    Inventory reconciliation report -- the operator's counting work queue.

    Each row compares the stored ``on_hand_quantity`` against the sum of
    transaction-ledger quantities for the item's epoch:

    - Items with a ``baseline_timestamp`` sum only transactions at-or-after
      that timestamp (post-count history).
    - Items with ``baseline_timestamp = null`` sum ALL transactions and are
      shown as **uncounted** -- they belong at the top of the physical-count
      queue.

    ``drift = stored_on_hand - ledger_sum``.  Non-zero drift means the stored
    balance diverged from what the ledger recorded -- likely a SET-style write
    outside the canonical poster, a pre-4a legacy write, or unrecorded
    physical movement (scrap/remake).  Drift direction matters:

    - positive drift -> stored is higher than ledger (phantom stock)
    - negative drift -> stored is lower (consumed but not recorded)
    """
    # Fetch once (unfiltered) so summary stats and filtered items share one DB round-trip.
    all_rows = get_reconciliation_report(db, drifted_only=False)
    service_rows = [r for r in all_rows if r.has_drift] if drifted_only else all_rows

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

    return ReconciliationReportSchema(
        items=items,
        total_items=len(all_rows),
        drifted_items=sum(1 for r in all_rows if r.has_drift),
        uncounted_items=sum(1 for r in all_rows if not r.is_counted),
    )


# ---------------------------------------------------------------------------
# POST: count entry (HARD-4c primary path)
# ---------------------------------------------------------------------------

@router.post("/count", response_model=CountEntryResponse)
def post_count_entry(
    body: CountEntryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    Record a physical count for one (product, location) pair.

    Posts a ``reconciliation_baseline`` transaction through the canonical
    inventory ledger and stamps ``Inventory.baseline_timestamp``.

    - Delta = counted_qty - stored_on_hand (computed under a row lock).
    - GL entry posted for cycle-count variance semantics (DR/CR 1200 vs 5030).
    - If delta == 0 the baseline_timestamp is still stamped (count happened).

    The row will appear as **clean** (not drifted, counted) in the
    reconciliation report after this call.
    """
    from decimal import Decimal as D
    from decimal import InvalidOperation

    try:
        counted = D(str(body.counted_qty))
    except InvalidOperation:
        raise HTTPException(status_code=422, detail="Invalid counted_qty value")

    try:
        txn = post_reconciliation_baseline(
            db,
            product_id=body.product_id,
            location_id=body.location_id,
            counted_qty=counted,
            user=current_user.email,
            notes=body.notes,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Re-read inventory for the response
    from app.models.inventory import Inventory
    inv = (
        db.query(Inventory)
        .filter(
            Inventory.product_id == body.product_id,
            Inventory.location_id == body.location_id,
        )
        .first()
    )
    if inv is None:
        raise HTTPException(status_code=500, detail="Inventory row missing after baseline post")

    # Re-derive delta from the transaction row (posted by service)
    actual_delta = D(str(txn.quantity)) if txn else D("0")

    db.commit()

    return CountEntryResponse(
        transaction_id=txn.id if txn else None,
        delta=float(actual_delta),
        baseline_timestamp=inv.baseline_timestamp,
        message=(
            f"Count recorded. Delta {float(actual_delta):+.4f} applied; "
            f"baseline stamped to {inv.baseline_timestamp.isoformat()}."
        ),
    )


# ---------------------------------------------------------------------------
# POST: explicit fallback ("baseline to stored")
# ---------------------------------------------------------------------------

@router.post("/count/all-to-stored", response_model=FallbackResponse)
def baseline_all_to_stored(
    body: FallbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
):
    """
    EXPLICIT FALLBACK (dev/test/first-install only).

    Stamps ``Inventory.baseline_timestamp`` to NOW for the specified row (or
    ALL rows if no product_id is given), using the CURRENT stored on-hand as
    the physical-count value.  No ledger rows are written.

    This action is intentionally labeled "Baseline to stored -- dev/test only"
    in the UI and requires:

      {"confirm": "BASELINE_TO_STORED"}

    ... in the request body.  Without this token the endpoint returns 422.

    EXECUTION GATE: Do NOT invoke this against a production database without
    explicit owner sign-off recorded outside this request.  The endpoint
    exists to repair dev/demo/test databases and to provide a first-install
    bootstrap -- running it in production silently discards pre-existing
    transaction history from the drift calculation.
    """
    if body.confirm != BASELINE_TO_STORED_CONFIRM_TOKEN:
        raise HTTPException(
            status_code=422,
            detail=f"confirm must equal {BASELINE_TO_STORED_CONFIRM_TOKEN!r}",
        )

    if body.product_id is not None:
        # Single-row mode
        if body.location_id is None:
            raise HTTPException(
                status_code=422,
                detail="location_id is required when product_id is supplied",
            )
        try:
            baseline_to_stored(
                db,
                product_id=body.product_id,
                location_id=body.location_id,
                user=current_user.email,
                confirm=body.confirm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        stamped = 1
    else:
        # All-rows mode
        from app.models.inventory import Inventory

        all_inv = db.query(Inventory).all()
        stamped = 0
        for inv in all_inv:
            try:
                baseline_to_stored(
                    db,
                    product_id=inv.product_id,
                    location_id=inv.location_id,
                    user=current_user.email,
                    confirm=body.confirm,
                )
                stamped += 1
            except Exception:
                logger.exception(
                    "baseline_to_stored failed for product_id=%s location_id=%s; "
                    "continuing batch",
                    inv.product_id,
                    inv.location_id,
                )

    db.commit()

    return FallbackResponse(
        stamped_rows=stamped,
        message=(
            f"Baseline-to-stored complete: {stamped} row(s) stamped. "
            "No ledger rows were written."
        ),
    )
