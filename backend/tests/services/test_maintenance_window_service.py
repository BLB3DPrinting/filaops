"""
Tests for SCHED-7 — maintenance windows.

Covers (per plan):
- service CRUD: create validation (XOR machine, range, overlap rejection),
  list filters, cancel, complete → MaintenanceLog written + linked
- engine: find_window_conflicts; find_next_available_slot skips windows;
  schedule_operation raises MaintenanceWindowConflictError
- dispatch: printers in an active window are excluded; jobs overlapping an
  upcoming window get maintenance_warning (window beats next_due_at
  heuristic); assign blocked during an active window
- status auto-flip: sync_printer_maintenance_status flips idle→maintenance
  while active and maintenance→idle after the window ends; never touches
  printing/offline printers
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.maintenance import MaintenanceLog, MaintenanceWindow
from app.models.manufacturing import Resource
from app.models.printer import Printer
from app.models.production_order import ProductionOrder, ProductionOrderOperation
from app.services.dispatch_service import (
    dispatch_operation,
    get_dispatch_suggestions,
)
from app.services.maintenance_window_service import (
    cancel_window,
    complete_window,
    create_window,
    get_active_window,
    list_windows,
    sync_printer_maintenance_status,
)
from app.services.resource_scheduling import (
    MaintenanceWindowConflictError,
    find_next_available_slot,
    find_window_conflicts,
    schedule_operation,
)


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> datetime:
    """Naive UTC now (matches DB column convention)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_printer(db, *, status: str = "idle", work_center_id=None) -> Printer:
    uid = _uid()
    p = Printer(
        code=f"PRT-{uid}",
        name=f"Printer {uid}",
        model="X1C",
        brand="bambulab",
        status=status,
        active=True,
        work_center_id=work_center_id,
    )
    db.add(p)
    db.flush()
    return p


def _make_resource(db, work_center_id) -> Resource:
    uid = _uid()
    r = Resource(
        work_center_id=work_center_id,
        code=f"RES-{uid}",
        name=f"Resource {uid}",
        status="available",
        is_active=True,
    )
    db.add(r)
    db.flush()
    return r


def _make_wo(db, product_id: int, *, status: str = "released") -> ProductionOrder:
    uid = _uid()
    wo = ProductionOrder(
        code=f"WO-{uid}",
        product_id=product_id,
        quantity_ordered=Decimal("10"),
        status=status,
        priority=3,
        source="manual",
    )
    db.add(wo)
    db.flush()
    return wo


def _make_op(
    db,
    wo_id: int,
    work_center_id: int,
    *,
    sequence: int = 10,
    status: str = "pending",
    planned_run_minutes: float = 60.0,
) -> ProductionOrderOperation:
    op = ProductionOrderOperation(
        production_order_id=wo_id,
        work_center_id=work_center_id,
        sequence=sequence,
        operation_code=f"OP-{_uid()}",
        operation_name="Print",
        planned_setup_minutes=Decimal("0"),
        planned_run_minutes=Decimal(str(planned_run_minutes)),
        status=status,
    )
    db.add(op)
    db.flush()
    return op


# ---------------------------------------------------------------------------
# Service CRUD
# ---------------------------------------------------------------------------


class TestCreateWindow:
    def test_create_printer_window(self, db):
        printer = _make_printer(db)
        start = _now() + timedelta(hours=2)
        end = start + timedelta(hours=1)

        w = create_window(
            db,
            printer_id=printer.id,
            starts_at=start,
            ends_at=end,
            reason="Nozzle swap",
            created_by="tester@example.com",
        )

        assert w.id is not None
        assert w.printer_id == printer.id
        assert w.resource_id is None
        assert w.status == "scheduled"
        assert w.reason == "Nozzle swap"
        assert w.created_by == "tester@example.com"

    def test_create_resource_window(self, db, make_work_center):
        wc = make_work_center(center_type="machine")
        resource = _make_resource(db, wc.id)
        start = _now() + timedelta(hours=2)

        w = create_window(
            db,
            resource_id=resource.id,
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        assert w.resource_id == resource.id
        assert w.printer_id is None

    def test_requires_exactly_one_machine(self, db, make_work_center):
        printer = _make_printer(db)
        wc = make_work_center(center_type="machine")
        resource = _make_resource(db, wc.id)
        start = _now() + timedelta(hours=1)
        end = start + timedelta(hours=1)

        with pytest.raises(ValueError, match="Exactly one"):
            create_window(db, starts_at=start, ends_at=end)

        with pytest.raises(ValueError, match="Exactly one"):
            create_window(
                db,
                printer_id=printer.id,
                resource_id=resource.id,
                starts_at=start,
                ends_at=end,
            )

    def test_rejects_unknown_machine(self, db):
        start = _now() + timedelta(hours=1)
        with pytest.raises(ValueError, match="not found"):
            create_window(
                db, printer_id=99999999, starts_at=start, ends_at=start + timedelta(hours=1)
            )

    def test_rejects_inverted_range(self, db):
        printer = _make_printer(db)
        start = _now() + timedelta(hours=2)
        with pytest.raises(ValueError, match="after starts_at"):
            create_window(
                db, printer_id=printer.id, starts_at=start, ends_at=start
            )

    def test_rejects_overlap_on_same_machine(self, db):
        printer = _make_printer(db)
        start = _now() + timedelta(hours=2)
        end = start + timedelta(hours=2)
        create_window(db, printer_id=printer.id, starts_at=start, ends_at=end)

        # Overlapping the middle of the existing window
        with pytest.raises(ValueError, match="Overlaps existing"):
            create_window(
                db,
                printer_id=printer.id,
                starts_at=start + timedelta(minutes=30),
                ends_at=end + timedelta(hours=1),
            )

    def test_overlap_allowed_on_other_machine(self, db):
        printer_a = _make_printer(db)
        printer_b = _make_printer(db)
        start = _now() + timedelta(hours=2)
        end = start + timedelta(hours=2)
        create_window(db, printer_id=printer_a.id, starts_at=start, ends_at=end)

        w = create_window(db, printer_id=printer_b.id, starts_at=start, ends_at=end)
        assert w.id is not None

    def test_overlap_allowed_with_cancelled_window(self, db):
        printer = _make_printer(db)
        start = _now() + timedelta(hours=2)
        end = start + timedelta(hours=2)
        w1 = create_window(db, printer_id=printer.id, starts_at=start, ends_at=end)
        cancel_window(db, w1.id)

        w2 = create_window(db, printer_id=printer.id, starts_at=start, ends_at=end)
        assert w2.id != w1.id

    def test_adjacent_windows_do_not_overlap(self, db):
        """Back-to-back windows (end == next start) are allowed."""
        printer = _make_printer(db)
        start = _now() + timedelta(hours=2)
        mid = start + timedelta(hours=1)
        create_window(db, printer_id=printer.id, starts_at=start, ends_at=mid)
        w = create_window(
            db, printer_id=printer.id, starts_at=mid, ends_at=mid + timedelta(hours=1)
        )
        assert w.id is not None


class TestListWindows:
    def test_list_by_machine_and_range(self, db):
        printer_a = _make_printer(db)
        printer_b = _make_printer(db)
        base = _now() + timedelta(days=1)

        w_a = create_window(
            db, printer_id=printer_a.id, starts_at=base, ends_at=base + timedelta(hours=1)
        )
        create_window(
            db,
            printer_id=printer_b.id,
            starts_at=base,
            ends_at=base + timedelta(hours=1),
        )

        items = list_windows(db, printer_id=printer_a.id)
        assert [w.id for w in items] == [w_a.id]

        # Range filter excludes a window entirely outside the range
        items = list_windows(
            db,
            printer_id=printer_a.id,
            start=base + timedelta(hours=2),
            end=base + timedelta(hours=3),
        )
        assert items == []

    def test_finished_windows_hidden_by_default(self, db):
        printer = _make_printer(db)
        base = _now() + timedelta(days=1)
        w = create_window(
            db, printer_id=printer.id, starts_at=base, ends_at=base + timedelta(hours=1)
        )
        cancel_window(db, w.id)

        assert list_windows(db, printer_id=printer.id) == []
        finished = list_windows(db, printer_id=printer.id, include_finished=True)
        assert [x.id for x in finished] == [w.id]


class TestCancelComplete:
    def test_cancel_scheduled_window(self, db):
        printer = _make_printer(db)
        base = _now() + timedelta(days=1)
        w = create_window(
            db, printer_id=printer.id, starts_at=base, ends_at=base + timedelta(hours=1)
        )
        cancelled = cancel_window(db, w.id)
        assert cancelled.status == "cancelled"

    def test_cancel_active_window_restores_printer(self, db):
        printer = _make_printer(db, status="idle")
        w = create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() - timedelta(minutes=10),
            ends_at=_now() + timedelta(hours=1),
        )
        sync_printer_maintenance_status(db)
        db.refresh(printer)
        assert printer.status == "maintenance"
        assert w.status == "in_progress"

        cancel_window(db, w.id)
        db.refresh(printer)
        assert printer.status == "idle"

    def test_complete_writes_and_links_maintenance_log(self, db):
        printer = _make_printer(db, status="idle")
        next_due = _now() + timedelta(days=30)
        w = create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() - timedelta(minutes=90),
            ends_at=_now() + timedelta(minutes=30),
            reason="Belt tensioning",
        )
        sync_printer_maintenance_status(db)

        completed = complete_window(
            db,
            w.id,
            maintenance_type="repair",
            performed_by="tech@example.com",
            next_due_at=next_due,
            notes="replaced belt",
        )

        assert completed.status == "completed"
        assert completed.maintenance_log_id is not None
        log = db.get(MaintenanceLog, completed.maintenance_log_id)
        assert log.printer_id == printer.id
        assert log.maintenance_type == "repair"
        assert log.description == "Belt tensioning"
        assert log.performed_by == "tech@example.com"
        assert log.next_due_at == next_due
        # Elapsed downtime ≈ 90 minutes (early completion clips to now)
        assert 85 <= log.downtime_minutes <= 95
        assert log.notes == "replaced belt"

        # Printer restored
        db.refresh(printer)
        assert printer.status == "idle"

    def test_complete_resource_window_skips_log(self, db, make_work_center):
        """maintenance_logs requires a printer; resource windows just close."""
        wc = make_work_center(center_type="machine")
        resource = _make_resource(db, wc.id)
        w = create_window(
            db,
            resource_id=resource.id,
            starts_at=_now() - timedelta(minutes=30),
            ends_at=_now() + timedelta(minutes=30),
        )
        completed = complete_window(db, w.id)
        assert completed.status == "completed"
        assert completed.maintenance_log_id is None

    def test_complete_twice_rejected(self, db):
        printer = _make_printer(db)
        base = _now() + timedelta(days=1)
        w = create_window(
            db, printer_id=printer.id, starts_at=base, ends_at=base + timedelta(hours=1)
        )
        complete_window(db, w.id)
        with pytest.raises(ValueError, match="cannot be completed"):
            complete_window(db, w.id)
        with pytest.raises(ValueError, match="cannot be cancelled"):
            cancel_window(db, w.id)


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


class TestEngineIntegration:
    def test_find_window_conflicts_printer(self, db):
        printer = _make_printer(db)
        base = _now() + timedelta(hours=4)
        w = create_window(
            db,
            printer_id=printer.id,
            starts_at=base,
            ends_at=base + timedelta(hours=2),
        )

        hits = find_window_conflicts(
            db,
            resource_id=printer.id,
            start_time=base + timedelta(minutes=30),
            end_time=base + timedelta(hours=3),
            is_printer=True,
        )
        assert [x.id for x in hits] == [w.id]

        # Non-overlapping range → no conflicts
        assert (
            find_window_conflicts(
                db,
                resource_id=printer.id,
                start_time=base + timedelta(hours=2),
                end_time=base + timedelta(hours=3),
                is_printer=True,
            )
            == []
        )

        # Cancelled windows never block
        cancel_window(db, w.id)
        assert (
            find_window_conflicts(
                db,
                resource_id=printer.id,
                start_time=base,
                end_time=base + timedelta(hours=1),
                is_printer=True,
            )
            == []
        )

    def test_find_next_available_slot_skips_window(self, db, make_work_center):
        wc = make_work_center(center_type="machine")
        resource = _make_resource(db, wc.id)
        after = datetime.now(timezone.utc) + timedelta(hours=1)

        window_start = after + timedelta(minutes=30)
        window_end = window_start + timedelta(hours=2)
        create_window(
            db,
            resource_id=resource.id,
            starts_at=window_start,
            ends_at=window_end,
        )

        # 60-minute job can't fit in the 30-minute gap before the window —
        # the suggested slot must land at the window's end.
        slot = find_next_available_slot(
            db, resource.id, duration_minutes=60, after=after
        )
        assert slot == window_end.replace(tzinfo=timezone.utc)

        # A 20-minute job fits before the window
        slot = find_next_available_slot(
            db, resource.id, duration_minutes=20, after=after
        )
        assert slot == after

    def test_find_next_available_slot_skips_window_printer(self, db):
        printer = _make_printer(db)
        after = datetime.now(timezone.utc) + timedelta(hours=1)
        window_end = after + timedelta(hours=3)
        create_window(
            db, printer_id=printer.id, starts_at=after, ends_at=window_end
        )

        slot = find_next_available_slot(
            db, printer.id, duration_minutes=60, after=after, is_printer=True
        )
        assert slot == window_end.replace(tzinfo=timezone.utc)

    def test_schedule_operation_raises_on_window_overlap(
        self, db, make_product, make_work_center
    ):
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, work_center_id=wc.id)
        wo = _make_wo(db, product.id)
        op = _make_op(db, wo.id, wc.id)

        start = datetime.now(timezone.utc) + timedelta(hours=1)
        create_window(
            db,
            printer_id=printer.id,
            starts_at=start,
            ends_at=start + timedelta(hours=2),
        )

        with pytest.raises(MaintenanceWindowConflictError) as exc_info:
            schedule_operation(
                db=db,
                operation=op,
                resource_id=printer.id,
                scheduled_start=start + timedelta(minutes=15),
                scheduled_end=start + timedelta(minutes=75),
                is_printer=True,
            )
        assert len(exc_info.value.windows) == 1
        # Operation untouched
        assert op.scheduled_start is None
        assert op.status == "pending"

    def test_schedule_operation_ok_outside_window(
        self, db, make_product, make_work_center
    ):
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, work_center_id=wc.id)
        wo = _make_wo(db, product.id)
        op = _make_op(db, wo.id, wc.id)

        start = datetime.now(timezone.utc) + timedelta(hours=1)
        create_window(
            db,
            printer_id=printer.id,
            starts_at=start + timedelta(hours=5),
            ends_at=start + timedelta(hours=6),
        )

        success, conflicts = schedule_operation(
            db=db,
            operation=op,
            resource_id=printer.id,
            scheduled_start=start,
            scheduled_end=start + timedelta(hours=1),
            is_printer=True,
        )
        assert success is True
        assert conflicts == []


# ---------------------------------------------------------------------------
# Dispatch integration
# ---------------------------------------------------------------------------


class TestDispatchIntegration:
    def test_printer_in_active_window_excluded(
        self, db, make_product, make_work_center
    ):
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id)

        create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() - timedelta(minutes=10),
            ends_at=_now() + timedelta(hours=1),
        )

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        assert all(r.printer.id != printer.id for r in resp.results)

    def test_upcoming_window_yields_warning(
        self, db, make_product, make_work_center
    ):
        """A 60-min job overlapping a window starting in 30 min gets warned."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id, planned_run_minutes=60.0)

        window_start = _now() + timedelta(minutes=30)
        create_window(
            db,
            printer_id=printer.id,
            starts_at=window_start,
            ends_at=window_start + timedelta(hours=1),
            reason="filter swap",
        )

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        assert len(resp.results) == 1
        suggestion = resp.results[0].top_suggestion
        assert suggestion is not None
        assert suggestion.maintenance_warning is not None
        assert "Maintenance window" in suggestion.maintenance_warning
        assert "filter swap" in suggestion.maintenance_warning

    def test_far_future_window_no_warning(
        self, db, make_product, make_work_center
    ):
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id, planned_run_minutes=60.0)

        create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() + timedelta(days=7),
            ends_at=_now() + timedelta(days=7, hours=2),
        )

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        suggestion = resp.results[0].top_suggestion
        assert suggestion is not None
        assert suggestion.maintenance_warning is None

    def test_window_warning_beats_next_due_heuristic(
        self, db, make_product, make_work_center
    ):
        """When a real window overlaps, the warning names the window (not next_due)."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id, planned_run_minutes=60.0)

        # Heuristic would fire (next_due in 10 minutes)...
        log = MaintenanceLog(
            printer_id=printer.id,
            maintenance_type="routine",
            performed_at=_now() - timedelta(days=30),
            next_due_at=_now() + timedelta(minutes=10),
        )
        db.add(log)
        db.flush()

        # ...but the real window takes precedence in the message.
        create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() + timedelta(minutes=30),
            ends_at=_now() + timedelta(minutes=90),
        )

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        warning = resp.results[0].top_suggestion.maintenance_warning
        assert warning is not None
        assert "Maintenance window" in warning

    def test_heuristic_fallback_without_windows(
        self, db, make_product, make_work_center
    ):
        """No windows → original next_due_at heuristic still warns."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id, planned_run_minutes=60.0)

        log = MaintenanceLog(
            printer_id=printer.id,
            maintenance_type="routine",
            performed_at=_now() - timedelta(days=30),
            next_due_at=_now() + timedelta(minutes=10),
        )
        db.add(log)
        db.flush()

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        warning = resp.results[0].top_suggestion.maintenance_warning
        assert warning is not None
        assert "Maintenance due" in warning

    def test_assign_blocked_during_active_window(
        self, db, make_product, make_work_center
    ):
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        wo = _make_wo(db, product.id)
        op = _make_op(db, wo.id, wc.id)

        create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() - timedelta(minutes=5),
            ends_at=_now() + timedelta(hours=1),
        )

        with pytest.raises(ValueError, match="maintenance window"):
            dispatch_operation(db, op.id, printer.id, user=None)


# ---------------------------------------------------------------------------
# Status auto-flip (lazy sync)
# ---------------------------------------------------------------------------


class TestStatusSync:
    def test_active_window_flips_idle_printer(self, db):
        printer = _make_printer(db, status="idle")
        w = create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() - timedelta(minutes=5),
            ends_at=_now() + timedelta(hours=1),
        )

        changed = sync_printer_maintenance_status(db)
        assert changed is True
        db.refresh(printer)
        db.refresh(w)
        assert printer.status == "maintenance"
        assert w.status == "in_progress"

        # Idempotent: second run is a no-op
        assert sync_printer_maintenance_status(db) is False

    def test_never_overwrites_printing_printer(self, db):
        printer = _make_printer(db, status="printing")
        w = create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() - timedelta(minutes=5),
            ends_at=_now() + timedelta(hours=1),
        )

        sync_printer_maintenance_status(db)
        db.refresh(printer)
        db.refresh(w)
        assert printer.status == "printing"  # untouched
        assert w.status == "in_progress"  # window state still advances

    def test_never_overwrites_offline_printer(self, db):
        printer = _make_printer(db, status="offline")
        create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() - timedelta(minutes=5),
            ends_at=_now() + timedelta(hours=1),
        )
        sync_printer_maintenance_status(db)
        db.refresh(printer)
        assert printer.status == "offline"

    def test_expired_window_flips_back_to_idle(self, db):
        printer = _make_printer(db, status="idle")
        w = MaintenanceWindow(
            printer_id=printer.id,
            starts_at=_now() - timedelta(hours=2),
            ends_at=_now() - timedelta(minutes=5),
            status="in_progress",
        )
        db.add(w)
        printer.status = "maintenance"
        db.flush()

        changed = sync_printer_maintenance_status(db)
        assert changed is True
        db.refresh(printer)
        db.refresh(w)
        assert printer.status == "idle"
        # Window awaits explicit complete/cancel — elapsed ≠ done
        assert w.status == "in_progress"

    def test_no_flip_back_when_second_window_active(self, db):
        printer = _make_printer(db, status="maintenance")
        db.add(
            MaintenanceWindow(
                printer_id=printer.id,
                starts_at=_now() - timedelta(hours=3),
                ends_at=_now() - timedelta(hours=2),
                status="in_progress",
            )
        )
        db.add(
            MaintenanceWindow(
                printer_id=printer.id,
                starts_at=_now() - timedelta(minutes=10),
                ends_at=_now() + timedelta(hours=1),
                status="in_progress",
            )
        )
        db.flush()

        sync_printer_maintenance_status(db)
        db.refresh(printer)
        assert printer.status == "maintenance"

    def test_active_window_recorded_by_get_active_window(self, db):
        printer = _make_printer(db)
        w = create_window(
            db,
            printer_id=printer.id,
            starts_at=_now() - timedelta(minutes=5),
            ends_at=_now() + timedelta(hours=1),
        )
        active = get_active_window(db, printer_id=printer.id)
        assert active is not None and active.id == w.id

        # Outside the window → None
        assert (
            get_active_window(
                db, printer_id=printer.id, at=_now() + timedelta(hours=2)
            )
            is None
        )
