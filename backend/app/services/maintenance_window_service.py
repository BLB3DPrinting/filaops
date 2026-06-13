"""
Maintenance Window Service (SCHED-7).

Planned maintenance as a first-class time block the scheduler respects.

Standalone functions, ``db: Session`` first param (ARCHITECT-003 pattern).
Callers own commit/rollback; this module only flushes.

Time conventions
----------------
All window bounds are stored as naive UTC (matching every DateTime in the
schema). Public functions accept aware or naive datetimes and normalize
via ``_naive_utc`` before comparing or persisting.

Status auto-flip (lazy sync)
----------------------------
There is no reliable background poll seam for printer status: the MQTT
monitor only covers connected Bambu printers and overwrites status from
gcode telemetry. So ``sync_printer_maintenance_status(db)`` is called
lazily from the two surfaces that display status (dispatch suggestions and
the scheduler board). It:

- advances ``scheduled`` windows whose start has passed to ``in_progress``
  and flips the printer to 'maintenance' (only from 'idle'/'available' —
  never overwrites offline/printing/error), recording the prior status on
  the window (``prior_printer_status``);
- when an ``in_progress`` window's end has passed, flips the printer back
  to its recorded prior status ('idle' if none was recorded; only from
  'maintenance', and only when no other blocking window is active). The
  window itself stays ``in_progress`` until the operator explicitly
  completes or cancels it — elapsed time is not proof the work was done.

Resource (non-printer) windows block scheduling but do not auto-flip
Resource.status — resources have no live status poll to fight with, and
the Gantt renders the window block either way.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.maintenance import (
    WINDOW_BLOCKING_STATUSES,
    MaintenanceLog,
    MaintenanceWindow,
)
from app.models.manufacturing import Resource
from app.models.printer import Printer

#: Printer statuses we may overwrite when a window opens/closes.
_FLIPPABLE_STATUSES = ("idle", "available")


def _naive_utc(dt: datetime) -> datetime:
    """Normalize aware or naive datetime to naive UTC."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _machine_filter(printer_id: Optional[int], resource_id: Optional[int]):
    """Column filter for the window's target machine."""
    if printer_id is not None:
        return MaintenanceWindow.printer_id == printer_id
    return MaintenanceWindow.resource_id == resource_id


def create_window(
    db: Session,
    *,
    printer_id: Optional[int] = None,
    resource_id: Optional[int] = None,
    starts_at: datetime,
    ends_at: datetime,
    reason: Optional[str] = None,
    created_by: Optional[str] = None,
) -> MaintenanceWindow:
    """
    Create a planned maintenance window.

    Raises:
        ValueError: machine selector invalid, machine missing, bad range,
            or overlap with an existing blocking window on the same machine.
    """
    if (printer_id is None) == (resource_id is None):
        raise ValueError("Exactly one of printer_id or resource_id must be set")

    # Race: the overlap check below is read-then-insert — two concurrent
    # creates for the same machine could both see "no overlap" and both
    # insert, persisting overlapping windows. Serialize per machine by
    # taking a row lock (SELECT ... FOR UPDATE) on the target Printer /
    # Resource BEFORE the overlap check, so the second transaction waits
    # for the first to commit and then sees its window. Same pattern as
    # the HARD-8 PO row lock in purchase_order_service.receive path.
    if printer_id is not None:
        machine = (
            db.query(Printer)
            .filter(Printer.id == printer_id)
            .with_for_update()
            .first()
        )
        if machine is None:
            raise ValueError(f"Printer {printer_id} not found")
    else:
        machine = (
            db.query(Resource)
            .filter(Resource.id == resource_id)
            .with_for_update()
            .first()
        )
        if machine is None:
            raise ValueError(f"Resource {resource_id} not found")

    starts_at = _naive_utc(starts_at)
    ends_at = _naive_utc(ends_at)
    if ends_at <= starts_at:
        raise ValueError("ends_at must be after starts_at")

    overlap = (
        db.query(MaintenanceWindow)
        .filter(
            _machine_filter(printer_id, resource_id),
            MaintenanceWindow.status.in_(WINDOW_BLOCKING_STATUSES),
            MaintenanceWindow.starts_at < ends_at,
            MaintenanceWindow.ends_at > starts_at,
        )
        .first()
    )
    if overlap is not None:
        raise ValueError(
            f"Overlaps existing maintenance window #{overlap.id} "
            f"({overlap.starts_at:%Y-%m-%d %H:%M}–{overlap.ends_at:%H:%M} UTC)"
        )

    window = MaintenanceWindow(
        printer_id=printer_id,
        resource_id=resource_id,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=reason,
        status="scheduled",
        created_by=created_by,
    )
    db.add(window)
    db.flush()
    return window


def list_windows(
    db: Session,
    *,
    printer_id: Optional[int] = None,
    resource_id: Optional[int] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    include_finished: bool = False,
) -> List[MaintenanceWindow]:
    """
    List maintenance windows, optionally by machine and/or time range.

    By default only blocking (scheduled / in_progress) windows are
    returned; ``include_finished=True`` adds completed and cancelled.
    """
    query = db.query(MaintenanceWindow)
    if printer_id is not None:
        query = query.filter(MaintenanceWindow.printer_id == printer_id)
    if resource_id is not None:
        query = query.filter(MaintenanceWindow.resource_id == resource_id)
    if not include_finished:
        query = query.filter(MaintenanceWindow.status.in_(WINDOW_BLOCKING_STATUSES))
    if start is not None:
        query = query.filter(MaintenanceWindow.ends_at > _naive_utc(start))
    if end is not None:
        query = query.filter(MaintenanceWindow.starts_at < _naive_utc(end))
    return query.order_by(MaintenanceWindow.starts_at).all()


def cancel_window(db: Session, window_id: int) -> MaintenanceWindow:
    """
    Cancel a scheduled or in-progress window.

    If the window was active and had flipped its printer to 'maintenance',
    the printer is restored to its recorded prior status (only from
    'maintenance'; 'idle' if no prior status was recorded).
    """
    window = db.get(MaintenanceWindow, window_id)
    if window is None:
        raise ValueError(f"Maintenance window {window_id} not found")
    if window.status not in WINDOW_BLOCKING_STATUSES:
        raise ValueError(
            f"Window {window_id} is '{window.status}' and cannot be cancelled"
        )

    was_in_progress = window.status == "in_progress"
    window.status = "cancelled"
    db.flush()

    if was_in_progress and window.printer_id is not None:
        _restore_printer_status(db, window)
    return window


def complete_window(
    db: Session,
    window_id: int,
    *,
    maintenance_type: str = "routine",
    performed_by: Optional[str] = None,
    next_due_at: Optional[datetime] = None,
    cost=None,
    notes: Optional[str] = None,
) -> MaintenanceWindow:
    """
    Complete a window: writes a MaintenanceLog entry (printer windows only —
    maintenance_logs.printer_id is NOT NULL so resource windows just close),
    links it via maintenance_log_id, and restores the printer status.

    next_due_at follows the existing convention (operator-supplied on the
    log; the /maintenance/due endpoint reads the latest log's next_due_at).
    Downtime is recorded as the elapsed window time (clipped to now for
    early completion).
    """
    window = db.get(MaintenanceWindow, window_id)
    if window is None:
        raise ValueError(f"Maintenance window {window_id} not found")
    if window.status not in WINDOW_BLOCKING_STATUSES:
        raise ValueError(
            f"Window {window_id} is '{window.status}' and cannot be completed"
        )

    now = _now_naive()
    was_in_progress = window.status == "in_progress" or window.starts_at <= now

    if window.printer_id is not None:
        actual_end = min(now, window.ends_at)
        downtime_minutes = max(
            0, int((actual_end - window.starts_at).total_seconds() // 60)
        )
        log = MaintenanceLog(
            printer_id=window.printer_id,
            maintenance_type=maintenance_type,
            description=window.reason,
            performed_by=performed_by,
            performed_at=now,
            next_due_at=_naive_utc(next_due_at) if next_due_at is not None else None,
            cost=cost,
            downtime_minutes=downtime_minutes,
            notes=notes,
            created_at=now,
        )
        db.add(log)
        db.flush()
        window.maintenance_log_id = log.id

    window.status = "completed"
    db.flush()

    if was_in_progress and window.printer_id is not None:
        _restore_printer_status(db, window)
    return window


def get_active_window(
    db: Session,
    *,
    printer_id: Optional[int] = None,
    resource_id: Optional[int] = None,
    at: Optional[datetime] = None,
) -> Optional[MaintenanceWindow]:
    """Return the blocking window covering instant ``at`` (default now), if any."""
    moment = _naive_utc(at) if at is not None else _now_naive()
    return (
        db.query(MaintenanceWindow)
        .filter(
            _machine_filter(printer_id, resource_id),
            MaintenanceWindow.status.in_(WINDOW_BLOCKING_STATUSES),
            MaintenanceWindow.starts_at <= moment,
            MaintenanceWindow.ends_at > moment,
        )
        .order_by(MaintenanceWindow.starts_at)
        .first()
    )


def get_next_window_overlapping(
    db: Session,
    *,
    printer_id: int,
    start: datetime,
    end: datetime,
) -> Optional[MaintenanceWindow]:
    """
    Earliest blocking window on the printer overlapping [start, end).
    Used by dispatch to warn when a job would collide with an upcoming window.
    """
    return (
        db.query(MaintenanceWindow)
        .filter(
            MaintenanceWindow.printer_id == printer_id,
            MaintenanceWindow.status.in_(WINDOW_BLOCKING_STATUSES),
            MaintenanceWindow.starts_at < _naive_utc(end),
            MaintenanceWindow.ends_at > _naive_utc(start),
        )
        .order_by(MaintenanceWindow.starts_at)
        .first()
    )


def _restore_printer_status(db: Session, window: MaintenanceWindow) -> None:
    """Flip the printer back to the status recorded when the window flipped
    it ('idle' if somehow unrecorded) — only from 'maintenance', and only
    when no other blocking window is currently active (never clobbers
    offline/printing/error)."""
    if window.printer_id is None:
        return
    printer = db.get(Printer, window.printer_id)
    if printer is None or printer.status != "maintenance":
        return
    if get_active_window(db, printer_id=window.printer_id) is not None:
        return
    printer.status = window.prior_printer_status or "idle"
    db.flush()


def sync_printer_maintenance_status(db: Session) -> bool:
    """
    Lazy status sync — see module docstring for the seam rationale.

    Returns True when anything changed (caller decides whether to commit).
    """
    now = _now_naive()
    changed = False

    # 1) Activate: scheduled windows whose start has passed → in_progress;
    #    flip idle/available printers to 'maintenance'. Also re-flip printers
    #    whose window is already in_progress but whose status got reverted
    #    (e.g. MQTT telemetry wrote 'idle' mid-window after a reconnect).
    active_windows = (
        db.query(MaintenanceWindow)
        .filter(
            MaintenanceWindow.status.in_(WINDOW_BLOCKING_STATUSES),
            MaintenanceWindow.starts_at <= now,
            MaintenanceWindow.ends_at > now,
        )
        .all()
    )
    for window in active_windows:
        if window.status == "scheduled":
            window.status = "in_progress"
            changed = True
        if window.printer_id is not None:
            printer = db.get(Printer, window.printer_id)
            if printer is not None and printer.status in _FLIPPABLE_STATUSES:
                # Record what we are overwriting so flip-out can restore it
                # exactly ('available' must come back as 'available', not
                # 'idle'). Keep the first recording — a telemetry revert
                # mid-window (e.g. MQTT wrote 'idle') must not clobber the
                # originally observed status.
                if window.prior_printer_status is None:
                    window.prior_printer_status = printer.status
                printer.status = "maintenance"
                changed = True

    # 2) Expire: in_progress windows whose end has passed → restore the
    #    printer (window status is left for explicit complete/cancel).
    expired_windows = (
        db.query(MaintenanceWindow)
        .filter(
            MaintenanceWindow.status == "in_progress",
            MaintenanceWindow.ends_at <= now,
            MaintenanceWindow.printer_id.isnot(None),
        )
        .all()
    )
    for window in expired_windows:
        printer = db.get(Printer, window.printer_id)
        if printer is None or printer.status != "maintenance":
            continue
        if get_active_window(db, printer_id=window.printer_id, at=now) is not None:
            continue
        printer.status = window.prior_printer_status or "idle"
        changed = True

    if changed:
        db.flush()
    return changed
