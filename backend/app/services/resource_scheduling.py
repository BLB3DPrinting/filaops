"""
Resource scheduling service with conflict detection.

Handles scheduling operations on resources and detecting time conflicts.
Enforces operation sequencing and material/printer compatibility.

SCHED-7: maintenance windows are busy time. ``find_window_conflicts`` is a
PARALLEL check to ``find_conflicts`` (which keeps returning only
ProductionOrderOperation rows — its return type is a public contract used
by several endpoints). ``schedule_operation`` consults both and raises
``MaintenanceWindowConflictError`` for window overlaps;
``find_next_available_slot`` skips over windows when hunting for gaps.

S3 (print batches): ``schedule_operations_together`` books several
operations as ONE block on one printer or resource. ``find_conflicts`` is
run once with the whole member set excluded (``exclude_operation_ids``) so
members are never reported as conflicts of each other; maintenance windows
are checked once and predecessors for every member, and nothing is written
unless every check passes.

Editing ONE member of such a block: ``find_block_siblings`` derives the
block from the operation's STORED window (never from anything a client
sends) and ``resolve_edit_slot`` decides whether the proposed slot is the
block's own slot. Only then are the siblings not conflicts; any other slot
is a real move of that one member, and overlapping the block partly is a
genuine conflict. ``schedule_operation`` and the reschedule / live-conflict
endpoints all go through it so they agree.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import FrozenSet, Iterable, Optional, List, Tuple
from sqlalchemy.orm import Session

from app.models.maintenance import WINDOW_BLOCKING_STATUSES, MaintenanceWindow
from app.models.production_order import ProductionOrderOperation
from app.models.manufacturing import RoutingOperation

# Terminal statuses don't block scheduling
TERMINAL_STATUSES = ['complete', 'skipped', 'cancelled']

# The scheduler's datetime inputs work in whole minutes and a browser round
# trip cannot reproduce microseconds, so a block booked at 10:00:37.5 comes
# back from the modal as 10:00:00. A request whose start AND end are each
# less than this far from the block's own are a request for that slot.
SLOT_MATCH_TOLERANCE = timedelta(minutes=1)


def get_resource_schedule(
    db: Session,
    resource_id: int,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    is_printer: bool = False
) -> List[ProductionOrderOperation]:
    """
    Get scheduled operations for a resource or printer within date range.

    Args:
        db: Database session
        resource_id: Resource or printer ID to check
        start_date: Optional filter - operations ending after this time
        end_date: Optional filter - operations starting before this time
        is_printer: True if checking a printer

    Returns:
        List of operations scheduled on this resource/printer
    """
    # Choose the correct column based on resource type
    if is_printer:
        id_filter = ProductionOrderOperation.printer_id == resource_id
    else:
        id_filter = ProductionOrderOperation.resource_id == resource_id

    query = db.query(ProductionOrderOperation).filter(
        id_filter,
        ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
        ProductionOrderOperation.scheduled_start.isnot(None),
        ProductionOrderOperation.scheduled_end.isnot(None)
    )

    if start_date:
        query = query.filter(ProductionOrderOperation.scheduled_end > start_date)
    if end_date:
        query = query.filter(ProductionOrderOperation.scheduled_start < end_date)

    return query.order_by(ProductionOrderOperation.scheduled_start).all()


def find_conflicts(
    db: Session,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_operation_id: Optional[int] = None,
    is_printer: bool = False,
    exclude_operation_ids: Optional[Iterable[int]] = None,
) -> List[ProductionOrderOperation]:
    """
    Find operations that conflict with proposed time range.

    Two operations conflict if:
    - Same resource/printer
    - Time ranges overlap: (start1 < end2) AND (start2 < end1)
    - Neither in terminal status

    Args:
        db: Database session
        resource_id: Resource or printer ID to check
        start_time: Proposed start
        end_time: Proposed end
        exclude_operation_id: Operation to exclude (for rescheduling)
        is_printer: True if checking printer conflicts (uses printer_id column)
        exclude_operation_ids: Further operations to exclude, e.g. every
            member of a block being booked together (S3). Combined with
            ``exclude_operation_id``; ``None`` entries are ignored. Omitted,
            behaviour is unchanged.

    Returns:
        List of conflicting operations
    """
    # Choose the correct column based on resource type
    if is_printer:
        id_filter = ProductionOrderOperation.printer_id == resource_id
    else:
        id_filter = ProductionOrderOperation.resource_id == resource_id

    query = db.query(ProductionOrderOperation).filter(
        id_filter,
        ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
        ProductionOrderOperation.scheduled_start.isnot(None),
        ProductionOrderOperation.scheduled_end.isnot(None),
        # Overlap condition
        ProductionOrderOperation.scheduled_start < end_time,
        ProductionOrderOperation.scheduled_end > start_time
    )

    # One exclusion set: the single id (rescheduling) plus any block members.
    # A None id would turn the whole NOT IN predicate NULL and hide every
    # conflict, so unflushed operations are dropped rather than passed on.
    excluded = {op_id for op_id in (exclude_operation_ids or ()) if op_id is not None}
    if exclude_operation_id:
        excluded.add(exclude_operation_id)
    if excluded:
        query = query.filter(ProductionOrderOperation.id.notin_(excluded))

    return query.all()


def _naive_utc(dt: datetime) -> datetime:
    """Stored windows are naive UTC; bring a possibly aware value to match."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _stored_machine(operation: ProductionOrderOperation) -> Optional[Tuple[bool, int]]:
    """The machine an operation is booked on as ``(is_printer, id)``, if any.

    Printers and Resources have separate id spaces, so the kind is part of
    the identity (printer 3 and resource 3 are different machines).
    """
    if operation.printer_id is not None:
        return True, operation.printer_id
    if operation.resource_id is not None:
        return False, operation.resource_id
    return None


def find_block_siblings(
    db: Session,
    operation: ProductionOrderOperation,
) -> List[ProductionOrderOperation]:
    """
    Other operations co-booked with ``operation`` (print batches, S3/S4).

    The block is derived from the operation's STORED schedule: non-terminal
    operations on the same machine (same kind and id) with exactly the same
    ``scheduled_start`` and ``scheduled_end``. This is the same definition
    the scheduler board uses to draw one block. It is deliberately computed
    here, from the database, so callers never have to accept a list of ids
    from a client.

    Returns ``[]`` for an operation with no stored machine or window, and
    for an ordinary solo operation.
    """
    machine = _stored_machine(operation)
    if machine is None or operation.scheduled_start is None or operation.scheduled_end is None:
        return []
    is_printer, machine_id = machine
    if is_printer:
        machine_filter = ProductionOrderOperation.printer_id == machine_id
    else:
        machine_filter = ProductionOrderOperation.resource_id == machine_id

    return (
        db.query(ProductionOrderOperation)
        .filter(
            machine_filter,
            ProductionOrderOperation.id != operation.id,
            ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
            ProductionOrderOperation.scheduled_start == _naive_utc(operation.scheduled_start),
            ProductionOrderOperation.scheduled_end == _naive_utc(operation.scheduled_end),
        )
        .order_by(ProductionOrderOperation.id)
        .all()
    )


@dataclass(frozen=True)
class EditSlot:
    """The slot to validate (and write) when ONE operation is edited.

    ``start_time`` / ``end_time`` are what the caller asked for, unless the
    request was for the operation's own co-booked block slot, in which case
    they are that block's exact stored window. ``exclude_ids`` are the
    operations ``find_conflicts`` must ignore: the operation itself and, for
    the block's own slot only, its siblings.
    """

    start_time: datetime
    end_time: datetime
    exclude_ids: FrozenSet[int]


def resolve_edit_slot(
    db: Session,
    operation: ProductionOrderOperation,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
    is_printer: bool = False,
) -> EditSlot:
    """
    Decide what editing ``operation`` into the given slot may ignore.

    Semantics for an operation that is co-booked with others:

    - Same machine and the block's own window (within ``SLOT_MATCH_TOLERANCE``
      on both ends): nothing is moving. The siblings are not conflicts and
      the block's exact stored window is returned so a minute-truncated
      request cannot shift the member out of step with its siblings.
    - Any other window or machine: a real move of this one member (it leaves
      the block). Its siblings stay put and are NOT excluded, so overlapping
      the block partly is a genuine conflict with them.

    Operations without siblings (the ordinary case) only ever exclude
    themselves and keep the requested window untouched.

    The siblings come from ``find_block_siblings`` (stored state); no caller
    supplies ids.
    """
    own = {operation.id} if operation.id is not None else set()
    unchanged = EditSlot(start_time, end_time, frozenset(own))

    if _stored_machine(operation) != (is_printer, resource_id):
        return unchanged
    if operation.scheduled_start is None or operation.scheduled_end is None:
        return unchanged
    stored_start = _naive_utc(operation.scheduled_start)
    stored_end = _naive_utc(operation.scheduled_end)
    if (
        abs(_naive_utc(start_time) - stored_start) >= SLOT_MATCH_TOLERANCE
        or abs(_naive_utc(end_time) - stored_end) >= SLOT_MATCH_TOLERANCE
    ):
        return unchanged

    siblings = find_block_siblings(db, operation)
    if not siblings:
        return unchanged

    def _like(proposed: datetime, stored: datetime) -> datetime:
        # Same awareness as the request, so downstream comparisons behave
        return stored.replace(tzinfo=timezone.utc) if proposed.tzinfo is not None else stored

    return EditSlot(
        _like(start_time, stored_start),
        _like(end_time, stored_end),
        frozenset(own | {s.id for s in siblings}),
    )


def find_window_conflicts(
    db: Session,
    resource_id: int,
    start_time: datetime,
    end_time: datetime,
    is_printer: bool = False,
) -> List[MaintenanceWindow]:
    """
    Find maintenance windows that conflict with a proposed time range (SCHED-7).

    Parallel to ``find_conflicts`` (which only returns operations — its
    return type is a public contract). A window conflicts when it targets
    the same machine, is blocking (scheduled / in_progress), and overlaps:
    (window.starts_at < end_time) AND (window.ends_at > start_time).

    Args:
        db: Database session
        resource_id: Resource or printer ID to check
        start_time: Proposed start
        end_time: Proposed end
        is_printer: True if checking a printer (uses printer_id column)

    Returns:
        List of conflicting MaintenanceWindow rows
    """
    if is_printer:
        id_filter = MaintenanceWindow.printer_id == resource_id
    else:
        id_filter = MaintenanceWindow.resource_id == resource_id

    # Window columns are naive UTC; normalize aware inputs before comparing.
    def _naive(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    return (
        db.query(MaintenanceWindow)
        .filter(
            id_filter,
            MaintenanceWindow.status.in_(WINDOW_BLOCKING_STATUSES),
            MaintenanceWindow.starts_at < _naive(end_time),
            MaintenanceWindow.ends_at > _naive(start_time),
        )
        .order_by(MaintenanceWindow.starts_at)
        .all()
    )


def find_running_operations(
    db: Session,
    resource_id: int,
    exclude_operation_id: Optional[int] = None,
    is_printer: bool = False
) -> List[ProductionOrderOperation]:
    """
    Find operations currently running on a resource or printer.

    Args:
        db: Database session
        resource_id: Resource or printer ID to check
        exclude_operation_id: Operation to exclude
        is_printer: True if checking a printer

    Returns:
        List of running operations
    """
    # Choose the correct column based on resource type
    if is_printer:
        id_filter = ProductionOrderOperation.printer_id == resource_id
    else:
        id_filter = ProductionOrderOperation.resource_id == resource_id

    query = db.query(ProductionOrderOperation).filter(
        id_filter,
        ProductionOrderOperation.status == 'running'
    )

    if exclude_operation_id:
        query = query.filter(ProductionOrderOperation.id != exclude_operation_id)

    return query.all()


def check_resource_available_now(
    db: Session,
    resource_id: int,
    is_printer: bool = False
) -> Tuple[bool, Optional[ProductionOrderOperation]]:
    """
    Check if resource or printer is available to start work now.

    Args:
        db: Database session
        resource_id: Resource or printer ID to check
        is_printer: True if checking a printer

    Returns:
        Tuple of (is_available, blocking_operation)
    """
    running = find_running_operations(db, resource_id, is_printer=is_printer)
    if running:
        return False, running[0]
    return True, None


def find_next_available_slot(
    db: Session,
    resource_id: int,
    duration_minutes: int,
    after: datetime = None,
    is_printer: bool = False
) -> datetime:
    """
    Find the next available time slot on a resource or printer.

    Busy time = scheduled operations PLUS blocking maintenance windows
    (SCHED-7). Returns the start of the first gap of sufficient duration.

    Args:
        db: Database session
        resource_id: Resource or printer ID to check
        duration_minutes: Required duration in minutes
        after: Start searching after this time (defaults to now)
        is_printer: True if checking a printer

    Returns:
        datetime: Start time of next available slot
    """
    if after is None:
        after = datetime.now(timezone.utc)

    # Choose the correct column based on resource type
    if is_printer:
        id_filter = ProductionOrderOperation.printer_id == resource_id
        window_filter = MaintenanceWindow.printer_id == resource_id
    else:
        id_filter = ProductionOrderOperation.resource_id == resource_id
        window_filter = MaintenanceWindow.resource_id == resource_id

    # DB columns are TIMESTAMP WITHOUT TIME ZONE, so values come back naive.
    # Treat them as UTC to allow arithmetic with tz-aware `after`.
    def _as_utc(dt):
        if dt is not None and dt.tzinfo is None and after.tzinfo is not None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    # Naive variant of `after` for SQL comparisons against naive columns
    after_naive = (
        after.astimezone(timezone.utc).replace(tzinfo=None)
        if after.tzinfo is not None
        else after
    )

    # Get all scheduled ops on this resource still relevant after 'after'
    scheduled_ops = db.query(ProductionOrderOperation).filter(
        id_filter,
        ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
        ProductionOrderOperation.scheduled_end.isnot(None),
        ProductionOrderOperation.scheduled_end > after_naive
    ).order_by(ProductionOrderOperation.scheduled_start).all()

    # Blocking maintenance windows still relevant after 'after'
    windows = (
        db.query(MaintenanceWindow)
        .filter(
            window_filter,
            MaintenanceWindow.status.in_(WINDOW_BLOCKING_STATUSES),
            MaintenanceWindow.ends_at > after_naive,
        )
        .all()
    )

    # Merge ops + windows into one sorted busy-interval sweep
    intervals = []
    for op in scheduled_ops:
        if op.scheduled_start and op.scheduled_end:
            intervals.append((_as_utc(op.scheduled_start), _as_utc(op.scheduled_end)))
    for w in windows:
        intervals.append((_as_utc(w.starts_at), _as_utc(w.ends_at)))
    intervals.sort(key=lambda pair: pair[0])

    cursor = after
    for busy_start, busy_end in intervals:
        if busy_start > cursor:
            gap_minutes = (busy_start - cursor).total_seconds() / 60
            if gap_minutes >= duration_minutes:
                return cursor
        if busy_end > cursor:
            cursor = busy_end

    return cursor


def check_predecessor_scheduling(
    db: Session,
    operation: ProductionOrderOperation,
    scheduled_start: datetime,
    in_block_ids: Optional[Iterable[int]] = None,
) -> Optional[str]:
    """
    Check that predecessor operations are scheduled/complete before this one.

    Rules:
    - All lower-sequence operations on the same PO must be either:
      a) In a terminal status (complete, skipped, cancelled), OR
      b) Scheduled to end before this operation's start time
    - If the routing_operation has can_overlap=True, the predecessor's
      scheduled_end may overlap with this operation's scheduled_start.
    - A predecessor in ``in_block_ids`` is being booked together with this
      operation as one block (S3), so it will get this operation's window:
      its stored schedule is not consulted, and it is rejected unless
      can_overlap=True.

    Args:
        db: Database session
        operation: Operation about to be scheduled
        scheduled_start: Its proposed start
        in_block_ids: Ids of operations booked together with ``operation``
            as one block. Omitted, behaviour is unchanged.

    Returns:
        None if OK, or an error message string describing the violation.
    """
    # Get all sibling operations on the same PO with lower sequence
    predecessors = db.query(ProductionOrderOperation).filter(
        ProductionOrderOperation.production_order_id == operation.production_order_id,
        ProductionOrderOperation.sequence < operation.sequence,
        ProductionOrderOperation.id != operation.id,
    ).order_by(ProductionOrderOperation.sequence).all()

    if not predecessors:
        return None

    # Check if this operation allows overlap via routing
    can_overlap = False
    if operation.routing_operation_id:
        routing_op = db.get(RoutingOperation, operation.routing_operation_id)
        if routing_op and routing_op.can_overlap:
            can_overlap = True

    block = {op_id for op_id in (in_block_ids or ()) if op_id is not None}

    for pred in predecessors:
        # Terminal statuses are fine - predecessor is done
        if pred.status in TERMINAL_STATUSES:
            continue

        # In-block predecessor: it will share this operation's window, so
        # its stored schedule (if any) is about to be overwritten. Same
        # window means overlap, which only the routing can allow.
        if pred.id in block:
            if can_overlap:
                continue
            return (
                f"Operation {pred.sequence} ({pred.operation_name or pred.operation_code}) "
                f"is in the same block and must finish before this operation can start"
            )

        # Predecessor must be scheduled
        if not pred.scheduled_end:
            return (
                f"Operation {pred.sequence} ({pred.operation_name or pred.operation_code}) "
                f"must be scheduled before operation {operation.sequence}"
            )

        # Predecessor must end before this operation starts (unless overlap allowed)
        if not can_overlap:
            # Normalize timezone for comparison
            pred_end = pred.scheduled_end
            start = scheduled_start
            if pred_end.tzinfo is None and start.tzinfo is not None:
                pred_end = pred_end.replace(tzinfo=timezone.utc)
            elif pred_end.tzinfo is not None and start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)

            if pred_end > start:
                return (
                    f"Operation {pred.sequence} ({pred.operation_name or pred.operation_code}) "
                    f"must finish before this operation can start"
                )

    return None


def get_earliest_start_after_predecessors(
    db: Session,
    operation: ProductionOrderOperation,
    after: datetime,
) -> datetime:
    """
    Return the earliest datetime this operation can start, respecting
    predecessor scheduled_end times.

    Takes the max of `after` and the latest scheduled_end among all
    lower-sequence operations on the same PO that are not yet in a
    terminal status.
    """
    predecessors = db.query(ProductionOrderOperation).filter(
        ProductionOrderOperation.production_order_id == operation.production_order_id,
        ProductionOrderOperation.sequence < operation.sequence,
        ProductionOrderOperation.id != operation.id,
        ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
        ProductionOrderOperation.scheduled_end.isnot(None),
    ).all()

    earliest = after
    for pred in predecessors:
        pred_end = pred.scheduled_end
        # Normalize timezone — DB stores naive UTC, after may be tz-aware
        if pred_end.tzinfo is None and earliest.tzinfo is not None:
            pred_end = pred_end.replace(tzinfo=timezone.utc)
        elif pred_end.tzinfo is not None and earliest.tzinfo is None:
            earliest = earliest.replace(tzinfo=timezone.utc)
        if pred_end > earliest:
            earliest = pred_end

    return earliest


def check_successor_scheduling(
    db: Session,
    operation: ProductionOrderOperation,
    scheduled_end: datetime,
    in_block_ids: Optional[Iterable[int]] = None,
) -> Optional[List["ProductionOrderOperation"]]:
    """
    Check that moving this operation's end time doesn't violate any SUCCESSOR's
    existing scheduled start.

    A successor is any higher-sequence sibling on the same PO that:
    - Is NOT in a terminal status, AND
    - Has an existing scheduled_start set (is already scheduled), AND
    - Its scheduled_start < our new scheduled_end  (i.e. we'd push past it)

    A successor in ``in_block_ids`` is co-booked with this operation (S3) and
    shares its window by design: it was accepted into the block under its
    routing's ``can_overlap`` rule, so keeping the block's slot is not a
    violation. Omitted, behaviour is unchanged.

    Returns:
        None if no violations, or a list of impacted successor operations.

    Note: this is a WARNING surface — the endpoint converts these into a 400
    with successor conflict details + earliest_valid_start so the operator can
    fix the successor scheduling order.
    """
    successors = db.query(ProductionOrderOperation).filter(
        ProductionOrderOperation.production_order_id == operation.production_order_id,
        ProductionOrderOperation.sequence > operation.sequence,
        ProductionOrderOperation.id != operation.id,
        ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
        ProductionOrderOperation.scheduled_start.isnot(None),
    ).order_by(ProductionOrderOperation.sequence).all()

    block = {op_id for op_id in (in_block_ids or ()) if op_id is not None}

    violated: List[ProductionOrderOperation] = []
    for succ in successors:
        if succ.id in block:
            continue
        succ_start = succ.scheduled_start
        end = scheduled_end
        # Normalize timezone — DB stores naive UTC, caller may pass tz-aware
        if succ_start.tzinfo is None and end.tzinfo is not None:
            succ_start = succ_start.replace(tzinfo=timezone.utc)
        elif succ_start.tzinfo is not None and end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end > succ_start:
            violated.append(succ)

    return violated if violated else None


def schedule_operation(
    db: Session,
    operation: ProductionOrderOperation,
    resource_id: int,
    scheduled_start: datetime,
    scheduled_end: datetime,
    is_printer: bool = False
) -> Tuple[bool, List[ProductionOrderOperation]]:
    """
    Schedule an operation on a resource with conflict and sequence validation.

    Validates:
    1. No time conflicts with other operations on the same resource
    2. No overlap with blocking maintenance windows (SCHED-7)
    3. Predecessor operations are scheduled/complete first

    Args:
        db: Database session
        operation: Operation to schedule
        resource_id: Target resource/printer ID
        scheduled_start: Start time
        scheduled_end: End time
        is_printer: True if resource_id refers to a printer

    Returns:
        Tuple of (success, conflicts_or_errors)
        - If success=True, operation was scheduled
        - If success=False, conflicts contains blocking operations

    Raises:
        MaintenanceWindowConflictError: range overlaps a blocking
            maintenance window (carries ``.windows``)
        SequenceError: predecessor sequencing violated
    """
    # Editing one member of a co-booked block: its own slot is not a conflict
    # with the siblings, any other slot is a real move (see resolve_edit_slot).
    # For an ordinary operation this is the same window with only itself
    # excluded.
    slot = resolve_edit_slot(
        db, operation, resource_id, scheduled_start, scheduled_end, is_printer,
    )
    scheduled_start, scheduled_end = slot.start_time, slot.end_time

    # Check for conflicts using the appropriate column
    conflicts = find_conflicts(
        db=db,
        resource_id=resource_id,
        start_time=scheduled_start,
        end_time=scheduled_end,
        is_printer=is_printer,
        exclude_operation_ids=slot.exclude_ids,
    )

    if conflicts:
        return False, conflicts

    # Maintenance windows are busy time (SCHED-7). Raised as a typed error
    # rather than mixed into the conflicts list, which only carries
    # ProductionOrderOperation rows by contract.
    window_conflicts = find_window_conflicts(
        db=db,
        resource_id=resource_id,
        start_time=scheduled_start,
        end_time=scheduled_end,
        is_printer=is_printer,
    )
    if window_conflicts:
        raise MaintenanceWindowConflictError(window_conflicts)

    # Check predecessor sequencing
    seq_error = check_predecessor_scheduling(db, operation, scheduled_start)
    if seq_error:
        raise SequenceError(seq_error)

    # Schedule the operation - use proper foreign key columns
    if is_printer:
        operation.printer_id = resource_id
        operation.resource_id = None  # Clear resource_id when using printer
    else:
        operation.resource_id = resource_id
        operation.printer_id = None  # Clear printer_id when using resource

    operation.scheduled_start = scheduled_start
    operation.scheduled_end = scheduled_end
    operation.status = 'queued'  # Move from pending to queued

    db.flush()

    return True, []


def schedule_operations_together(
    db: Session,
    operations: Iterable[ProductionOrderOperation],
    resource_id: int,
    scheduled_start: datetime,
    scheduled_end: datetime,
    is_printer: bool = False
) -> Tuple[bool, List[ProductionOrderOperation]]:
    """
    Schedule several operations as ONE block on a resource (S3, print batches).

    A print plate often runs parts from several production orders at once.
    The members share one window on one printer/resource, so they must not
    be reported as conflicts of each other: ``find_conflicts`` runs once
    with the whole member set excluded. Otherwise the validation is the
    same as ``schedule_operation``:

    1. No time conflicts with operations outside the block on the same resource
    2. No overlap with blocking maintenance windows (SCHED-7)
    3. Predecessor operations are scheduled/complete first — checked for
       EVERY member before anything is written. A predecessor that is
       itself a member will share the window, so it is judged as in-block
       (rejected unless the routing allows overlap) rather than by its
       stored schedule, which the block is about to overwrite.

    All-or-nothing: every check runs before the first write, so a failed
    check leaves every member untouched.

    Args:
        db: Database session
        operations: Operations to book together (at least one, flushed)
        resource_id: Target resource/printer ID
        scheduled_start: Start time of the block
        scheduled_end: End time of the block
        is_printer: True if resource_id refers to a printer

    Returns:
        Tuple of (success, conflicts)
        - If success=True, every member was scheduled
        - If success=False, conflicts contains blocking operations and no
          member was modified

    Raises:
        ValueError: ``operations`` is empty
        MaintenanceWindowConflictError: range overlaps a blocking
            maintenance window (carries ``.windows``)
        SequenceError: predecessor sequencing violated for any member
    """
    members = list(operations)
    if not members:
        raise ValueError("schedule_operations_together needs at least one operation")
    member_ids = {op.id for op in members}

    # One conflict query for the whole block: members only conflict with
    # operations outside the block.
    conflicts = find_conflicts(
        db=db,
        resource_id=resource_id,
        start_time=scheduled_start,
        end_time=scheduled_end,
        is_printer=is_printer,
        exclude_operation_ids=member_ids,
    )

    if conflicts:
        return False, conflicts

    # Maintenance windows are busy time (SCHED-7), checked once for the block.
    window_conflicts = find_window_conflicts(
        db=db,
        resource_id=resource_id,
        start_time=scheduled_start,
        end_time=scheduled_end,
        is_printer=is_printer,
    )
    if window_conflicts:
        raise MaintenanceWindowConflictError(window_conflicts)

    # Every member's predecessors, before any write. A predecessor inside
    # the block shares this window, so it is checked as in-block.
    for operation in members:
        seq_error = check_predecessor_scheduling(
            db, operation, scheduled_start, in_block_ids=member_ids,
        )
        if seq_error:
            raise SequenceError(seq_error)

    # Same fields schedule_operation writes, on every member
    for operation in members:
        if is_printer:
            operation.printer_id = resource_id
            operation.resource_id = None  # Clear resource_id when using printer
        else:
            operation.resource_id = resource_id
            operation.printer_id = None  # Clear printer_id when using resource

        operation.scheduled_start = scheduled_start
        operation.scheduled_end = scheduled_end
        operation.status = 'queued'  # Move from pending to queued

    db.flush()

    return True, []


class SequenceError(Exception):
    """Raised when operation scheduling violates sequence constraints."""
    pass


class MaintenanceWindowConflictError(Exception):
    """Raised when a proposed schedule overlaps a blocking maintenance window.

    ``windows`` carries the conflicting MaintenanceWindow rows so callers
    can surface them with a ``type: "maintenance"`` discriminator.
    """

    def __init__(self, windows: List[MaintenanceWindow]):
        self.windows = windows
        first = windows[0]
        super().__init__(
            f"Overlaps maintenance window "
            f"{first.starts_at:%Y-%m-%d %H:%M}–{first.ends_at:%H:%M} UTC"
            + (f" ({first.reason})" if first.reason else "")
        )
