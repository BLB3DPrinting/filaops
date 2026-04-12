"""
Resource scheduling service with conflict detection.

Handles scheduling operations on resources and detecting time conflicts.
Enforces operation sequencing and material/printer compatibility.
"""
from datetime import datetime, timezone
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

from app.models.production_order import ProductionOrderOperation
from app.models.manufacturing import RoutingOperation

# Terminal statuses don't block scheduling
TERMINAL_STATUSES = ['complete', 'skipped', 'cancelled']


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
    is_printer: bool = False
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

    if exclude_operation_id:
        query = query.filter(ProductionOrderOperation.id != exclude_operation_id)

    return query.all()


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

    Looks at scheduled operations and finds the first gap of sufficient duration.

    Args:
        db: Database session
        resource_id: Resource or printer ID to check
        duration_minutes: Required duration in minutes
        after: Start searching after this time (defaults to now)
        is_printer: True if checking a printer

    Returns:
        datetime: Start time of next available slot
    """
    from datetime import timedelta

    if after is None:
        after = datetime.now(timezone.utc)

    # Choose the correct column based on resource type
    if is_printer:
        id_filter = ProductionOrderOperation.printer_id == resource_id
    else:
        id_filter = ProductionOrderOperation.resource_id == resource_id

    # Get all scheduled ops on this resource starting from 'after'
    scheduled_ops = db.query(ProductionOrderOperation).filter(
        id_filter,
        ProductionOrderOperation.status.notin_(TERMINAL_STATUSES),
        ProductionOrderOperation.scheduled_end.isnot(None),
        ProductionOrderOperation.scheduled_end > after
    ).order_by(ProductionOrderOperation.scheduled_start).all()

    if not scheduled_ops:
        # No scheduled ops - can start immediately
        return after

    # DB columns are TIMESTAMP WITHOUT TIME ZONE, so values come back naive.
    # Treat them as UTC to allow arithmetic with tz-aware `after`.
    def _as_utc(dt):
        if dt is not None and dt.tzinfo is None and after.tzinfo is not None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    # Check if there's a gap before the first scheduled op
    first_op = scheduled_ops[0]
    if first_op.scheduled_start:
        gap_before_first = (_as_utc(first_op.scheduled_start) - after).total_seconds() / 60
        if gap_before_first >= duration_minutes:
            return after

    # Look for gaps between scheduled operations
    for i in range(len(scheduled_ops) - 1):
        current_op = scheduled_ops[i]
        next_op = scheduled_ops[i + 1]

        if current_op.scheduled_end and next_op.scheduled_start:
            gap_start = _as_utc(current_op.scheduled_end)
            gap_duration = (_as_utc(next_op.scheduled_start) - gap_start).total_seconds() / 60
            if gap_duration >= duration_minutes:
                return max(gap_start, after)

    # No gap found - schedule after the last operation
    last_op = scheduled_ops[-1]
    if last_op.scheduled_end:
        return max(_as_utc(last_op.scheduled_end), after)

    # Fallback: start 1 hour from now
    return after + timedelta(hours=1)


def check_predecessor_scheduling(
    db: Session,
    operation: ProductionOrderOperation,
    scheduled_start: datetime,
) -> Optional[str]:
    """
    Check that predecessor operations are scheduled/complete before this one.

    Rules:
    - All lower-sequence operations on the same PO must be either:
      a) In a terminal status (complete, skipped, cancelled), OR
      b) Scheduled to end before this operation's start time
    - If the routing_operation has can_overlap=True, the predecessor's
      scheduled_end may overlap with this operation's scheduled_start.

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

    for pred in predecessors:
        # Terminal statuses are fine - predecessor is done
        if pred.status in TERMINAL_STATUSES:
            continue

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
                    f"is scheduled until {pred_end.isoformat()}, "
                    f"which is after the requested start time {start.isoformat()}"
                )

    return None


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
    2. Predecessor operations are scheduled/complete first

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
    """
    # Check for conflicts using the appropriate column
    conflicts = find_conflicts(
        db=db,
        resource_id=resource_id,
        start_time=scheduled_start,
        end_time=scheduled_end,
        exclude_operation_id=operation.id,
        is_printer=is_printer
    )

    if conflicts:
        return False, conflicts

    # Check predecessor sequencing
    seq_error = check_predecessor_scheduling(db, operation, scheduled_start)
    if seq_error:
        # Return as a special "sequence_error" — caller should handle differently
        # We store the error message on a fake operation-like object for the API layer
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


class SequenceError(Exception):
    """Raised when operation scheduling violates sequence constraints."""
    pass
