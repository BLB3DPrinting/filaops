"""
Dispatch endpoints — suggest-and-confirm engine.  SCHED-1.

Routes:
  GET  /api/v1/dispatch/suggestions  — ranked suggestions for idle printers
  POST /api/v1/dispatch/assign       — commit an assignment

Both routes are staff-gated (admin or operator) following the pattern
established in mrp.py (``get_current_staff_user`` dependency on the router).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_staff_user, get_db
from app.models.user import User
from app.schemas.dispatch import AssignRequest, AssignResponse, DispatchSuggestionsResponse
from app.services.dispatch_service import dispatch_operation, get_dispatch_suggestions
from app.services.resource_scheduling import SequenceError

router = APIRouter(
    prefix="/dispatch",
    tags=["dispatch"],
    dependencies=[Depends(get_current_staff_user)],
)


@router.get("/suggestions", response_model=DispatchSuggestionsResponse)
async def get_suggestions(
    printer_id: Optional[int] = Query(
        None,
        description="Filter to a single printer (by Printer.id). "
        "Omit to get suggestions for all idle printers.",
    ),
    db: Session = Depends(get_db),
) -> DispatchSuggestionsResponse:
    """
    Return ranked dispatch suggestions for idle, available printers.

    For each eligible printer (active, not in maintenance status), returns:
    - ``top_suggestion``: the highest-priority candidate operation
    - ``runners_up``: up to 2 alternative candidates

    Each suggestion carries:
    - Order / operation details (code, product, qty, due date, priority)
    - ``why``: human-readable rank factors so the operator can trust the ranking
    - ``maintenance_warning``: non-null when maintenance is due before the job
      would finish (the operator decides whether to proceed)

    ZERO writes — safe to poll frequently.
    """
    return get_dispatch_suggestions(db, printer_id=printer_id)


@router.post("/assign", response_model=AssignResponse, status_code=200)
async def assign_operation(
    request: AssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_staff_user),
) -> AssignResponse:
    """
    Commit a dispatch assignment.

    Validates:
    1. Operation exists and is in ``pending`` status.
    2. Printer exists and is not in maintenance status.
    3. Material-machine compatibility (e.g. ABS requires enclosed printer).
    4. No scheduling conflicts via the existing conflict-detection engine.
    5. Predecessor operations are satisfied (sequence constraints).

    On success: sets ``operation.status = 'queued'``, records
    ``scheduled_start = now`` and ``scheduled_end = now + estimated_duration``.

    Status note: ``queued`` means assigned to a specific printer + time slot,
    ready to run, but NOT yet started.  The operator starts it via the
    operation-status endpoint.
    """
    try:
        result = dispatch_operation(
            db=db,
            operation_id=request.operation_id,
            printer_id=request.printer_id,
            user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except SequenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    db.commit()
    return result
