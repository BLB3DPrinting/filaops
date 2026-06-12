"""
Dispatch Service — suggest-and-confirm engine.  SCHED-1.

Two public functions:
- ``get_dispatch_suggestions(db, printer_id=None)`` — ZERO writes.
  For each idle+available printer (skips status="maintenance") rank
  candidate work and return the top suggestion + up to 2 runners-up.

- ``dispatch_operation(db, operation_id, printer_id, user)`` — single
  write.  Validates via the existing scheduling engine, then calls
  ``schedule_operation`` to commit the assignment.

Status semantics after assign
------------------------------
``schedule_operation()`` (resource_scheduling.py) sets the operation
status to ``'queued'`` — meaning: assigned to a specific printer and
time slot, materials allocated, ready to run, but NOT yet started.
The printer operator starts it via the existing operation-status
endpoint (POST /production-orders/{id}/operations/{op_id}/start).
This is intentional: assigning ≠ starting.  The PO status is left
untouched here; it transitions to ``in_progress`` when the first
operation actually starts.

Maintenance awareness (SCHED-7)
-------------------------------
Real maintenance windows come first:

- A printer inside an ACTIVE blocking window is excluded from
  suggestions entirely (same treatment as status="maintenance").
- A job whose estimated duration would overlap an UPCOMING window gets
  a ``maintenance_warning`` naming the window start — warn, never
  silently skip; the operator decides.

When no windows exist for the printer, the original heuristic stays as
fallback: compare the latest ``MaintenanceLog.next_due_at`` against
``now + estimated_duration``.

Default duration
----------------
``DEFAULT_DURATION_MINUTES = 120`` (2 hours) is used when an operation
has no ``planned_run_minutes`` and no routing back-reference with time
data.  This constant is intentional and documented; callers may pass
an explicit duration.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from datetime import date
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.maintenance import MaintenanceLog
from app.models.printer import Printer
from app.models.production_order import ProductionOrder, ProductionOrderOperation
from app.schemas.dispatch import (
    AssignResponse,
    DispatchSuggestion,
    DispatchSuggestionsResponse,
    PrinterDispatchResult,
    PrinterInfo,
)
from app.services.maintenance_window_service import (
    get_active_window,
    get_next_window_overlapping,
)
from app.services.resource_compatibility_service import is_machine_compatible
from app.services.resource_scheduling import (
    MaintenanceWindowConflictError as MaintenanceWindowConflictError,  # re-exported
    SequenceError as SequenceError,  # re-exported for callers (endpoint catches it)
    check_predecessor_scheduling,
    schedule_operation,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Fall-back duration (minutes) when no routing/planned time data exists.
DEFAULT_DURATION_MINUTES: int = 120

#: How many runners-up to include per printer.
MAX_RUNNERS_UP: int = 2

#: Printer statuses that make a printer ineligible for dispatch.
SKIP_STATUSES: frozenset[str] = frozenset({"maintenance"})

#: Production order statuses whose operations are candidates for dispatch.
DISPATCHABLE_ORDER_STATUSES: frozenset[str] = frozenset({"released"})

#: Operation statuses that are candidates (not yet assigned to a resource).
DISPATCHABLE_OP_STATUSES: frozenset[str] = frozenset({"pending"})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_utc() -> datetime:
    """Return current UTC time (tz-aware)."""
    return datetime.now(timezone.utc)


def _get_idle_printers(db: Session, printer_id: Optional[int] = None) -> List[Printer]:
    """
    Return printers eligible for dispatch.

    Eligibility: active=True AND status NOT IN SKIP_STATUSES.
    Optionally filter to a single printer_id.

    Note: "idle" in the printer model means the printer is not running a job.
    We match status values 'idle', 'offline', and None (unknown) — any status
    except explicit 'maintenance'.  If the printer is offline we still surface
    suggestions so the operator can pre-assign; the actual job won't start
    until connectivity returns.
    """
    # status.notin_(SKIP_STATUSES) excludes NULLs in SQL — printers with
    # status=None (newly registered, unknown) would be silently skipped.
    # We want to include them (they may be online but un-polled).
    # Use explicit OR to keep NULL-status printers in scope.
    query = db.query(Printer).filter(
        Printer.active.is_(True),
        or_(
            Printer.status.is_(None),
            Printer.status.notin_(SKIP_STATUSES),
        ),
    )
    if printer_id is not None:
        query = query.filter(Printer.id == printer_id)
    return query.all()


def _get_operation_duration_minutes(op: ProductionOrderOperation) -> int:
    """
    Best-available estimated duration for an operation (minutes).

    Priority:
    1. planned_setup_minutes + planned_run_minutes on the PO operation row
       (copied from routing when the WO was released).
    2. DEFAULT_DURATION_MINUTES (documented constant, not a silent magic number).
    """
    setup = float(op.planned_setup_minutes or 0)
    run = float(op.planned_run_minutes or 0)
    total = setup + run
    return int(total) if total > 0 else DEFAULT_DURATION_MINUTES


def _get_maintenance_warning(
    db: Session,
    printer: Printer,
    duration_minutes: int,
) -> Optional[str]:
    """
    Return a maintenance warning string when the job would collide with
    maintenance, else None.

    Order of authority (SCHED-7):
    1. Real maintenance windows — if a blocking window overlaps
       [now, now + duration], warn naming the window start.
    2. Heuristic fallback — latest MaintenanceLog.next_due_at before
       now + duration (kept for installs with no windows scheduled).
    """
    now = _now_utc()
    job_end_aware = now + timedelta(minutes=duration_minutes)

    window = get_next_window_overlapping(
        db, printer_id=printer.id, start=now, end=job_end_aware
    )
    if window is not None:
        label = window.reason or "maintenance"
        return (
            f"Maintenance window ({label}) starts "
            f"{window.starts_at:%Y-%m-%d %H:%M} UTC — "
            f"before this job would finish"
        )

    return _get_next_due_warning(db, printer, duration_minutes)


def _get_next_due_warning(
    db: Session,
    printer: Printer,
    duration_minutes: int,
) -> Optional[str]:
    """
    Heuristic fallback: warn if the printer's latest next_due_at falls
    before now + duration, else None.
    """
    latest_log: Optional[MaintenanceLog] = (
        db.query(MaintenanceLog)
        .filter(MaintenanceLog.printer_id == printer.id)
        .order_by(MaintenanceLog.performed_at.desc())
        .first()
    )
    if latest_log is None or latest_log.next_due_at is None:
        return None

    job_end = _now_utc() + timedelta(minutes=duration_minutes)

    # MaintenanceLog.next_due_at is stored as naive UTC (DateTime, no tz).
    next_due = latest_log.next_due_at
    if next_due.tzinfo is None:
        next_due = next_due.replace(tzinfo=timezone.utc)

    if next_due <= job_end:
        return (
            f"Maintenance due {next_due.strftime('%Y-%m-%d %H:%M UTC')} — "
            f"before this job would finish"
        )
    return None


def _predecessors_satisfied(
    db: Session,
    op: ProductionOrderOperation,
) -> bool:
    """
    Return True if all predecessors of *op* within its PO are in terminal
    status or have a scheduled_end before now.

    We reuse ``check_predecessor_scheduling`` with a proposed start of now.
    Any non-None return means predecessors block this op.
    """
    error = check_predecessor_scheduling(db, op, _now_utc())
    return error is None


def _build_why(order: ProductionOrder, is_fifo: bool) -> List[str]:
    """Build the human-readable rank-factor list for a suggestion."""
    factors: List[str] = []

    # Priority factor (1 = highest)
    if order.priority == 1:
        factors.append("priority 1 (highest)")
    else:
        factors.append(f"priority {order.priority}")

    # Due-date factor
    if order.due_date is not None:
        factors.append(f"due {order.due_date.isoformat()}")
    else:
        factors.append("no due date")

    # FIFO marker — present for all candidates, the label helps the operator
    # understand they came from oldest-first within same priority+due
    if is_fifo:
        factors.append("FIFO")

    return factors


def _rank_candidates(
    db: Session,
    printer: Printer,
) -> List[tuple[ProductionOrderOperation, ProductionOrder]]:
    """
    Build and sort the ranked list of (op, order) candidates for *printer*.

    Ranking: priority ASC (1 first), due_date ASC NULLs last, created_at ASC.
    Filters:
    - Order must be in DISPATCHABLE_ORDER_STATUSES.
    - Op must be in DISPATCHABLE_OP_STATUSES (pending, not yet queued/running).
    - Op's work center must match one of the work center IDs associated with
      this printer (via Printer.work_center_id).
    - All predecessors within the PO must be satisfied.
    - is_machine_compatible must be True.
    """
    # Build base query: released POs joined to pending ops.
    # We filter ops that are not yet assigned (printer_id IS NULL AND resource_id IS NULL)
    # so we don't suggest already-scheduled work.
    rows = (
        db.query(ProductionOrderOperation, ProductionOrder)
        .join(
            ProductionOrder,
            ProductionOrderOperation.production_order_id == ProductionOrder.id,
        )
        .filter(
            ProductionOrder.status.in_(DISPATCHABLE_ORDER_STATUSES),
            ProductionOrderOperation.status.in_(DISPATCHABLE_OP_STATUSES),
            # Not already scheduled
            ProductionOrderOperation.scheduled_start.is_(None),
            ProductionOrderOperation.printer_id.is_(None),
        )
        .order_by(
            # Nulls last for due_date: use CASE or Python sort
            ProductionOrder.priority.asc(),
            ProductionOrder.created_at.asc(),
        )
        .all()
    )

    # Work-center filter: printer.work_center_id (nullable) constrains which
    # ops can run on this printer.  If the printer has no work center set, we
    # accept any op (fallback for un-configured printers).
    printer_wc_id: Optional[int] = printer.work_center_id

    # Python-side sort for due_date NULLs-last (SQL portability) plus
    # stable multi-key sort: priority ASC, due_date ASC (NULLs last), created_at ASC.
    #
    # DB stores created_at as TIMESTAMP WITHOUT TIME ZONE (naive UTC).
    # Use a naive sentinel so we never get tz-aware vs naive comparison errors.
    _far_future = date(9999, 12, 31)
    _epoch_naive = datetime.min  # naive — matches DB column type

    def _sort_key(row: tuple) -> tuple:
        op, order = row
        due = order.due_date if order.due_date is not None else _far_future
        raw_created = order.created_at or _epoch_naive
        # Normalise: strip tz from aware datetimes so comparison is always naive
        created = raw_created.replace(tzinfo=None) if getattr(raw_created, "tzinfo", None) else raw_created
        return (order.priority, due, created)

    rows.sort(key=_sort_key)

    candidates: list[tuple[ProductionOrderOperation, ProductionOrder]] = []
    for op, order in rows:
        # Work-center match
        if printer_wc_id is not None and op.work_center_id != printer_wc_id:
            continue

        # Material-machine compatibility
        is_compat, _reason = is_machine_compatible(db, printer, order)
        if not is_compat:
            continue

        # Predecessor gate
        if not _predecessors_satisfied(db, op):
            continue

        candidates.append((op, order))

    return candidates


def _make_suggestion(
    db: Session,
    op: ProductionOrderOperation,
    order: ProductionOrder,
    printer: Printer,
    is_fifo: bool,
) -> DispatchSuggestion:
    duration = _get_operation_duration_minutes(op)
    maint_warning = _get_maintenance_warning(db, printer, duration)

    return DispatchSuggestion(
        production_order_id=order.id,
        production_order_code=order.code,
        product_name=order.product.name if order.product else "N/A",
        operation_id=op.id,
        operation_code=op.operation_code,
        operation_name=op.operation_name,
        quantity=str(order.quantity_ordered),
        due_date=order.due_date,
        priority=order.priority,
        estimated_duration_minutes=duration,
        why=_build_why(order, is_fifo),
        maintenance_warning=maint_warning,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_dispatch_suggestions(
    db: Session,
    printer_id: Optional[int] = None,
) -> DispatchSuggestionsResponse:
    """
    For each idle+available printer, rank candidate work and return the top
    suggestion + up to MAX_RUNNERS_UP runners-up.

    ZERO writes.  Safe to call as frequently as the polling cadence requires.

    Args:
        db: Database session (read-only usage — no flush/commit).
        printer_id: If provided, only consider this specific printer.

    Returns:
        DispatchSuggestionsResponse with one PrinterDispatchResult per
        eligible printer.
    """
    printers = _get_idle_printers(db, printer_id=printer_id)
    results: List[PrinterDispatchResult] = []

    for printer in printers:
        # SCHED-7: a printer inside an active maintenance window is not
        # dispatchable, regardless of its status field (the lazy status
        # sync may not have run yet).
        if get_active_window(db, printer_id=printer.id) is not None:
            continue

        candidates = _rank_candidates(db, printer)

        printer_info = PrinterInfo(
            id=printer.id,
            code=printer.code,
            name=printer.name,
            model=printer.model,
            status=printer.status,
        )

        if not candidates:
            results.append(
                PrinterDispatchResult(
                    printer=printer_info,
                    top_suggestion=None,
                    runners_up=[],
                )
            )
            continue

        # First candidate is FIFO (relative to sorted order) — only the first
        # gets the "FIFO" label in why[]; the others just show their factors.
        top_op, top_order = candidates[0]
        top = _make_suggestion(db, top_op, top_order, printer, is_fifo=True)

        runners: List[DispatchSuggestion] = []
        for op, order in candidates[1 : 1 + MAX_RUNNERS_UP]:
            runners.append(_make_suggestion(db, op, order, printer, is_fifo=False))

        results.append(
            PrinterDispatchResult(
                printer=printer_info,
                top_suggestion=top,
                runners_up=runners,
            )
        )

    return DispatchSuggestionsResponse(
        results=results,
        generated_at=_now_utc(),
    )


def dispatch_operation(
    db: Session,
    operation_id: int,
    printer_id: int,
    user,
) -> AssignResponse:
    """
    Commit an assignment: validate compatibility + conflicts via the existing
    engine, then call ``schedule_operation(now → now+duration)``.

    This is the only write path in the dispatch service.

    Args:
        db: Database session.  Caller is responsible for commit/rollback.
        operation_id: ProductionOrderOperation.id to assign.
        printer_id: Printer.id to assign to.
        user: Authenticated user (for future audit trail; not written here).

    Returns:
        AssignResponse with scheduled times and the resulting operation status.

    Raises:
        ValueError: If the operation or printer is not found, if the printer
            is not eligible (maintenance status), if the operation is not in
            a dispatchable status, or if material-machine compatibility fails.
        SequenceError: If predecessor operations would be violated.
        MaintenanceWindowConflictError: If the proposed slot overlaps a
            blocking maintenance window (SCHED-7).
        RuntimeError: If schedule_operation reports a conflict.
    """
    op: Optional[ProductionOrderOperation] = db.get(
        ProductionOrderOperation, operation_id
    )
    if op is None:
        raise ValueError(f"Operation {operation_id} not found")

    if op.status not in DISPATCHABLE_OP_STATUSES:
        raise ValueError(
            f"Operation {operation_id} has status '{op.status}'; "
            f"only {sorted(DISPATCHABLE_OP_STATUSES)} can be dispatched"
        )

    printer: Optional[Printer] = db.get(Printer, printer_id)
    if printer is None:
        raise ValueError(f"Printer {printer_id} not found")

    if not printer.active:
        raise ValueError(
            f"Printer {printer.code} (id={printer_id}) is inactive "
            f"and cannot accept new assignments"
        )

    if printer.status in SKIP_STATUSES:
        raise ValueError(
            f"Printer {printer.code} has status '{printer.status}' "
            f"and cannot accept new assignments"
        )

    # SCHED-7: active maintenance window blocks assignment even if the
    # printer's status field hasn't been flipped yet.
    active_window = get_active_window(db, printer_id=printer.id)
    if active_window is not None:
        raise ValueError(
            f"Printer {printer.code} is in a maintenance window until "
            f"{active_window.ends_at:%Y-%m-%d %H:%M} UTC "
            f"and cannot accept new assignments"
        )

    # Load the production order
    order: Optional[ProductionOrder] = db.get(
        ProductionOrder, op.production_order_id
    )
    if order is None:
        raise ValueError(
            f"Production order not found for operation {operation_id}"
        )

    if order.status not in DISPATCHABLE_ORDER_STATUSES:
        raise ValueError(
            f"Production order {order.code} has status '{order.status}'; "
            f"only {sorted(DISPATCHABLE_ORDER_STATUSES)} orders can be dispatched"
        )

    # Material-machine compatibility check
    is_compat, reason = is_machine_compatible(db, printer, order)
    if not is_compat:
        raise ValueError(
            f"Printer {printer.code} is not compatible with order {order.code}: {reason}"
        )

    # Calculate times
    duration = _get_operation_duration_minutes(op)
    now = _now_utc()
    scheduled_start = now
    scheduled_end = now + timedelta(minutes=duration)

    # Delegate to the existing scheduling engine.
    # schedule_operation handles:
    #   1. Conflict detection (raises SequenceError if predecessor violated;
    #      returns (False, conflicts) if time conflict)
    #   2. Sets op.printer_id, op.scheduled_start, op.scheduled_end
    #   3. Sets op.status = 'queued'
    success, conflicts = schedule_operation(
        db=db,
        operation=op,
        resource_id=printer_id,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        is_printer=True,
    )

    if not success:
        conflict_codes = [
            f"op#{c.id}({c.operation_code or c.operation_name or '?'})"
            for c in conflicts
        ]
        raise RuntimeError(
            f"Scheduling conflict on printer {printer.code}: "
            f"{', '.join(conflict_codes)}"
        )

    # schedule_operation calls db.flush() but not commit — caller commits.
    db.flush()

    return AssignResponse(
        operation_id=op.id,
        printer_id=printer.id,
        printer_code=printer.code,
        production_order_code=order.code,
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        operation_status=op.status,  # 'queued' per schedule_operation semantics
    )
