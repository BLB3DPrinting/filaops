"""Tests for resource_scheduling.py — scheduling + conflict detection."""
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.maintenance_window_service import create_window
from app.services.resource_scheduling import (
    MaintenanceWindowConflictError,
    SequenceError,
    get_resource_schedule,
    find_conflicts,
    find_running_operations,
    check_predecessor_scheduling,
    check_resource_available_now,
    find_next_available_slot,
    schedule_operation,
    schedule_operations_together,
)
from app.models.production_order import ProductionOrderOperation
from app.models.manufacturing import Resource, Routing, RoutingOperation
from app.models.printer import Printer


def _uid():
    return uuid.uuid4().hex[:6]


def _make_resource(db, work_center_id):
    """Create a Resource linked to a work center."""
    uid = _uid()
    r = Resource(
        work_center_id=work_center_id,
        code=f"RES-{uid}",
        name=f"Test Resource {uid}",
        status="available",
    )
    db.add(r)
    db.flush()
    return r


def _make_printer(db, work_center_id):
    """Create a Printer linked to a work center."""
    uid = _uid()
    p = Printer(
        code=f"PRT-{uid}",
        name=f"Test Printer {uid}",
        model="X1C",
        brand="bambulab",
        work_center_id=work_center_id,
        status="idle",
    )
    db.add(p)
    db.flush()
    return p


def _make_operation(db, wo_id, work_center_id, sequence=10, status="pending", **kwargs):
    """Create a ProductionOrderOperation."""
    op = ProductionOrderOperation(
        production_order_id=wo_id,
        work_center_id=work_center_id,
        sequence=sequence,
        operation_name=kwargs.pop("operation_name", f"Op-{sequence}"),
        planned_run_minutes=kwargs.pop("planned_run_minutes", 60),
        status=status,
        **kwargs,
    )
    db.add(op)
    db.flush()
    return op


class TestGetResourceSchedule:
    def test_empty_when_no_operations(self, db, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        result = get_resource_schedule(db, res.id)
        assert result == []

    def test_returns_scheduled_operations(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        op = _make_operation(
            db, wo.id, wc.id, status="queued",
            resource_id=res.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        result = get_resource_schedule(db, res.id)
        assert len(result) >= 1
        assert any(r.id == op.id for r in result)

    def test_excludes_terminal_statuses(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        _make_operation(
            db, wo.id, wc.id, status="complete",
            resource_id=res.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        result = get_resource_schedule(db, res.id)
        assert result == []

    def test_filters_by_date_range(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        _make_operation(
            db, wo.id, wc.id, status="queued",
            resource_id=res.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        # Query for a future range that doesn't overlap
        result = get_resource_schedule(
            db, res.id,
            start_date=now + timedelta(hours=2),
            end_date=now + timedelta(hours=3),
        )
        assert result == []

    def test_printer_mode(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        _make_operation(
            db, wo.id, wc.id, status="queued",
            printer_id=prt.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        result = get_resource_schedule(db, prt.id, is_printer=True)
        assert len(result) >= 1


class TestFindConflicts:
    def test_no_conflicts_on_empty(self, db, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        now = datetime.now(timezone.utc)
        result = find_conflicts(db, res.id, now, now + timedelta(hours=1))
        assert result == []

    def test_detects_overlap(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        _make_operation(
            db, wo.id, wc.id, status="queued",
            resource_id=res.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=2),
        )
        conflicts = find_conflicts(
            db, res.id,
            now + timedelta(hours=1),
            now + timedelta(hours=3),
        )
        assert len(conflicts) >= 1

    def test_exclude_operation_id(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        op = _make_operation(
            db, wo.id, wc.id, status="queued",
            resource_id=res.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=2),
        )
        conflicts = find_conflicts(
            db, res.id,
            now, now + timedelta(hours=1),
            exclude_operation_id=op.id,
        )
        assert conflicts == []

    def test_printer_conflicts(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        _make_operation(
            db, wo.id, wc.id, status="queued",
            printer_id=prt.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=2),
        )
        conflicts = find_conflicts(
            db, prt.id,
            now, now + timedelta(hours=1),
            is_printer=True,
        )
        assert len(conflicts) >= 1


class TestFindRunningOperations:
    def test_empty_when_none_running(self, db, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        result = find_running_operations(db, res.id)
        assert result == []

    def test_finds_running(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        _make_operation(db, wo.id, wc.id, status="running", resource_id=res.id)
        result = find_running_operations(db, res.id)
        assert len(result) >= 1

    def test_excludes_by_id(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        op = _make_operation(db, wo.id, wc.id, status="running", resource_id=res.id)
        result = find_running_operations(db, res.id, exclude_operation_id=op.id)
        assert result == []

    def test_printer_mode(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        _make_operation(db, wo.id, wc.id, status="running", printer_id=prt.id)
        result = find_running_operations(db, prt.id, is_printer=True)
        assert len(result) >= 1


class TestCheckResourceAvailableNow:
    def test_available_when_no_running(self, db, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        available, blocking = check_resource_available_now(db, res.id)
        assert available is True
        assert blocking is None

    def test_not_available_when_running(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        _make_operation(db, wo.id, wc.id, status="running", resource_id=res.id)
        available, blocking = check_resource_available_now(db, res.id)
        assert available is False
        assert blocking is not None

    def test_printer_mode(self, db, make_work_center):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        available, blocking = check_resource_available_now(db, prt.id, is_printer=True)
        assert available is True


class TestFindNextAvailableSlot:
    def test_immediate_when_no_ops(self, db, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        now = datetime.now(timezone.utc)
        slot = find_next_available_slot(db, res.id, duration_minutes=60, after=now)
        assert slot == now

    def test_gap_before_first_op(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        # Use naive datetimes — DB columns are TIMESTAMP WITHOUT TIME ZONE
        now = datetime.now(timezone.utc)
        _make_operation(
            db, wo.id, wc.id, status="queued",
            resource_id=res.id,
            scheduled_start=now + timedelta(hours=3),
            scheduled_end=now + timedelta(hours=4),
        )
        slot = find_next_available_slot(db, res.id, duration_minutes=60, after=now)
        assert slot == now

    def test_after_last_op(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        _make_operation(
            db, wo.id, wc.id, status="queued",
            resource_id=res.id,
            scheduled_start=now - timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=1),
        )
        slot = find_next_available_slot(db, res.id, duration_minutes=120, after=now)
        assert slot >= now + timedelta(hours=1) - timedelta(seconds=1)

    def test_default_after_is_now(self, db, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        slot = find_next_available_slot(db, res.id, duration_minutes=60)
        # Should be approximately now (the function uses utcnow internally)
        assert slot is not None

    def test_finds_gap_between_ops(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        # Op 1: now to now+1h
        _make_operation(
            db, wo.id, wc.id, sequence=10, status="queued",
            resource_id=res.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        # Op 2: now+3h to now+4h (gap of 2h between them)
        _make_operation(
            db, wo.id, wc.id, sequence=20, status="queued",
            resource_id=res.id,
            scheduled_start=now + timedelta(hours=3),
            scheduled_end=now + timedelta(hours=4),
        )
        # Looking for 90 min slot — should find the 2h gap
        slot = find_next_available_slot(db, res.id, duration_minutes=90, after=now)
        # Should be at or after end of first op
        assert slot >= now + timedelta(hours=1) - timedelta(seconds=1)
        # Should be before start of second op
        assert slot < now + timedelta(hours=3)

    def test_printer_mode(self, db, make_work_center):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        now = datetime.now(timezone.utc)
        slot = find_next_available_slot(db, prt.id, duration_minutes=60, after=now, is_printer=True)
        assert slot == now


class TestScheduleOperation:
    def test_successful_schedule(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        op = _make_operation(db, wo.id, wc.id)
        now = datetime.now(timezone.utc)
        success, conflicts = schedule_operation(
            db, op, res.id,
            now, now + timedelta(hours=1),
        )
        assert success is True
        assert conflicts == []
        assert op.scheduled_start == now
        assert op.status == "queued"
        assert op.resource_id == res.id

    def test_conflict_prevents_schedule(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        now = datetime.now(timezone.utc)
        _make_operation(
            db, wo.id, wc.id, status="queued",
            resource_id=res.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=2),
        )
        op2 = _make_operation(db, wo.id, wc.id, sequence=20)
        success, conflicts = schedule_operation(
            db, op2, res.id,
            now + timedelta(hours=1),
            now + timedelta(hours=3),
        )
        assert success is False
        assert len(conflicts) >= 1

    def test_printer_schedule(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        wo = make_production_order(product_id=product.id)
        op = _make_operation(db, wo.id, wc.id)
        now = datetime.now(timezone.utc)
        success, conflicts = schedule_operation(
            db, op, prt.id,
            now, now + timedelta(hours=1),
            is_printer=True,
        )
        assert success is True
        assert op.printer_id == prt.id
        assert op.resource_id is None


def _assert_unscheduled(op):
    """The operation looks exactly as ``_make_operation`` created it."""
    assert op.printer_id is None
    assert op.resource_id is None
    assert op.scheduled_start is None
    assert op.scheduled_end is None
    assert op.status == "pending"


class TestFindConflictsExclusion:
    """``exclude_operation_id`` and ``exclude_operation_ids`` (S3 co-booking)."""

    @staticmethod
    def _three_overlapping_ops(db, make_product, make_production_order, make_work_center):
        """Three queued ops on one resource, each on its own PO, all in [now, now+2h]."""
        wc = make_work_center()
        res = _make_resource(db, wc.id)
        product = make_product()
        now = datetime.now(timezone.utc)
        ops = []
        for seq in (10, 20, 30):
            wo = make_production_order(product_id=product.id)
            ops.append(_make_operation(
                db, wo.id, wc.id, sequence=seq, status="queued",
                resource_id=res.id,
                scheduled_start=now,
                scheduled_end=now + timedelta(hours=2),
            ))
        return res, now, ops

    def test_no_exclusion_arguments_behaves_as_before(
        self, db, make_product, make_production_order, make_work_center
    ):
        res, now, ops = self._three_overlapping_ops(db, make_product, make_production_order, make_work_center)
        window = (now, now + timedelta(hours=1))

        # Regression: nothing excluded -> every overlapping op is reported
        conflicts = find_conflicts(db, res.id, *window)
        assert {c.id for c in conflicts} == {op.id for op in ops}

        # Positional call shape used by existing callers:
        # (db, resource_id, start, end, exclude_operation_id)
        conflicts = find_conflicts(db, res.id, *window, ops[0].id)
        assert {c.id for c in conflicts} == {ops[1].id, ops[2].id}

    def test_exclude_operation_ids_excludes_every_member(
        self, db, make_product, make_production_order, make_work_center
    ):
        res, now, ops = self._three_overlapping_ops(db, make_product, make_production_order, make_work_center)
        conflicts = find_conflicts(
            db, res.id, now, now + timedelta(hours=1),
            exclude_operation_ids=[ops[0].id, ops[1].id],
        )
        assert [c.id for c in conflicts] == [ops[2].id]

    def test_exclude_operation_id_and_ids_combine(
        self, db, make_product, make_production_order, make_work_center
    ):
        res, now, ops = self._three_overlapping_ops(db, make_product, make_production_order, make_work_center)
        conflicts = find_conflicts(
            db, res.id, now, now + timedelta(hours=1),
            exclude_operation_id=ops[0].id,
            exclude_operation_ids={ops[1].id},
        )
        assert [c.id for c in conflicts] == [ops[2].id]

    def test_empty_exclude_operation_ids_excludes_nothing(
        self, db, make_product, make_production_order, make_work_center
    ):
        res, now, ops = self._three_overlapping_ops(db, make_product, make_production_order, make_work_center)
        conflicts = find_conflicts(
            db, res.id, now, now + timedelta(hours=1),
            exclude_operation_ids=[],
        )
        assert {c.id for c in conflicts} == {op.id for op in ops}


class TestScheduleOperationsTogether:
    """S3: several operations booked as ONE block on one printer or resource."""

    @staticmethod
    def _members(db, make_production_order, work_center_id, product_id, count=3):
        """``count`` pending, unscheduled ops, each on its own production order."""
        ops = []
        for _ in range(count):
            wo = make_production_order(product_id=product_id)
            ops.append(_make_operation(db, wo.id, work_center_id))
        return ops

    @staticmethod
    def _window():
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        return start, start + timedelta(hours=3)

    def test_books_three_operations_on_one_printer(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        ops = self._members(db, make_production_order, wc.id, product.id)
        start, end = self._window()

        success, conflicts = schedule_operations_together(
            db, ops, prt.id, start, end, is_printer=True,
        )

        assert success is True
        assert conflicts == []
        for op in ops:
            assert op.printer_id == prt.id
            assert op.resource_id is None
            assert op.scheduled_start == start
            assert op.scheduled_end == end
            assert op.status == "queued"
        # The block is visible on the printer's schedule
        scheduled = get_resource_schedule(db, prt.id, is_printer=True)
        assert {o.id for o in scheduled} == {op.id for op in ops}

    def test_resource_mode_sets_resource_and_clears_printer(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center(center_type="machine")
        res = _make_resource(db, wc.id)
        product = make_product()
        ops = self._members(db, make_production_order, wc.id, product.id, count=2)
        start, end = self._window()

        success, conflicts = schedule_operations_together(db, ops, res.id, start, end)

        assert success is True
        assert conflicts == []
        for op in ops:
            assert op.resource_id == res.id
            assert op.printer_id is None
            assert op.status == "queued"

    def test_fourth_operation_conflicts_with_the_block(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        ops = self._members(db, make_production_order, wc.id, product.id)
        start, end = self._window()
        assert schedule_operations_together(db, ops, prt.id, start, end, is_printer=True) == (True, [])

        wo4 = make_production_order(product_id=product.id)
        op4 = _make_operation(db, wo4.id, wc.id)
        success, conflicts = schedule_operation(
            db, op4, prt.id,
            start + timedelta(hours=1), end + timedelta(hours=1),
            is_printer=True,
        )

        assert success is False
        assert {c.id for c in conflicts} == {op.id for op in ops}
        _assert_unscheduled(op4)

    def test_second_block_into_same_window_conflicts(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        first = self._members(db, make_production_order, wc.id, product.id)
        start, end = self._window()
        assert schedule_operations_together(db, first, prt.id, start, end, is_printer=True) == (True, [])

        second = self._members(db, make_production_order, wc.id, product.id, count=2)
        success, conflicts = schedule_operations_together(
            db, second, prt.id, start + timedelta(hours=2), end + timedelta(hours=2), is_printer=True,
        )

        assert success is False
        assert {c.id for c in conflicts} == {op.id for op in first}
        for op in second:
            _assert_unscheduled(op)

    def test_maintenance_window_raises_and_writes_nothing(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        ops = self._members(db, make_production_order, wc.id, product.id)
        start, end = self._window()
        create_window(
            db,
            printer_id=prt.id,
            starts_at=start + timedelta(minutes=30),
            ends_at=start + timedelta(minutes=90),
        )

        with pytest.raises(MaintenanceWindowConflictError) as exc_info:
            schedule_operations_together(db, ops, prt.id, start, end, is_printer=True)

        assert len(exc_info.value.windows) == 1
        for op in ops:
            _assert_unscheduled(op)

    def test_predecessor_violation_aborts_the_whole_call(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        clean = self._members(db, make_production_order, wc.id, product.id, count=2)
        # Third member: its own PO has an unscheduled predecessor (sequence 10)
        wo3 = make_production_order(product_id=product.id)
        predecessor = _make_operation(db, wo3.id, wc.id, sequence=10)
        blocked = _make_operation(db, wo3.id, wc.id, sequence=20)
        members = clean + [blocked]
        start, end = self._window()

        with pytest.raises(SequenceError):
            schedule_operations_together(db, members, prt.id, start, end, is_printer=True)

        # Nothing written: not the member that failed, and not the two that
        # passed their own checks before it.
        for op in members:
            _assert_unscheduled(op)
        _assert_unscheduled(predecessor)
        assert find_conflicts(db, prt.id, start, end, is_printer=True) == []

    def test_empty_member_list_is_rejected(self, db, make_work_center):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        start, end = self._window()
        with pytest.raises(ValueError):
            schedule_operations_together(db, [], prt.id, start, end, is_printer=True)

    def test_in_block_predecessor_already_scheduled_is_rejected(
        self, db, make_product, make_production_order, make_work_center
    ):
        """Both sequences of one PO in the block. The predecessor's OLD window
        ends before the block, so a check against stored data would pass, but
        the block would then give both operations the same window."""
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        start, end = self._window()
        wo = make_production_order(product_id=product.id)
        earlier = _make_operation(
            db, wo.id, wc.id, sequence=10, status="queued",
            printer_id=prt.id,
            scheduled_start=start - timedelta(hours=3),
            scheduled_end=start - timedelta(hours=1),
        )
        later = _make_operation(db, wo.id, wc.id, sequence=20)
        other = self._members(db, make_production_order, wc.id, product.id, count=1)

        with pytest.raises(SequenceError):
            schedule_operations_together(
                db, [earlier, later] + other, prt.id, start, end, is_printer=True,
            )

        # The predecessor keeps its original booking; nothing else is written
        assert earlier.scheduled_start == start - timedelta(hours=3)
        assert earlier.scheduled_end == start - timedelta(hours=1)
        assert earlier.status == "queued"
        _assert_unscheduled(later)
        for op in other:
            _assert_unscheduled(op)

    def test_in_block_predecessor_allowed_when_routing_can_overlap(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        prt = _make_printer(db, wc.id)
        product = make_product()
        overlap_op = _make_overlap_routing_op(db, product.id, wc.id)
        wo = make_production_order(product_id=product.id)
        first = _make_operation(db, wo.id, wc.id, sequence=10)
        second = _make_operation(db, wo.id, wc.id, sequence=20, routing_operation_id=overlap_op.id)
        start, end = self._window()

        success, conflicts = schedule_operations_together(
            db, [first, second], prt.id, start, end, is_printer=True,
        )

        assert (success, conflicts) == (True, [])
        for op in (first, second):
            assert op.printer_id == prt.id
            assert op.scheduled_start == start
            assert op.scheduled_end == end
            assert op.status == "queued"


def _make_overlap_routing_op(db, product_id, work_center_id):
    """A RoutingOperation with can_overlap=True, on a throwaway routing."""
    routing = Routing(
        product_id=product_id, code=f"RTG-{_uid()}", name="Overlap routing",
        is_active=True, version=1,
    )
    db.add(routing)
    db.flush()
    routing_op = RoutingOperation(
        routing_id=routing.id, work_center_id=work_center_id, sequence=20,
        operation_code="PRINT", operation_name="Print",
        run_time_minutes=Decimal("60"), setup_time_minutes=Decimal("0"),
        can_overlap=True,
    )
    db.add(routing_op)
    db.flush()
    return routing_op


class TestCheckPredecessorSchedulingInBlock:
    """``in_block_ids`` on check_predecessor_scheduling (S3 co-booking)."""

    def test_default_behaviour_unchanged(self, db, make_product, make_production_order, make_work_center):
        wc = make_work_center()
        product = make_product()
        wo = make_production_order(product_id=product.id)
        pred = _make_operation(db, wo.id, wc.id, sequence=10)
        op = _make_operation(db, wo.id, wc.id, sequence=20)
        start = datetime.now(timezone.utc) + timedelta(hours=1)

        # Unscheduled predecessor blocks
        assert "must be scheduled" in check_predecessor_scheduling(db, op, start)

        # Predecessor ending before the start is fine
        pred.status = "queued"
        pred.scheduled_start = start - timedelta(hours=2)
        pred.scheduled_end = start - timedelta(hours=1)
        db.flush()
        assert check_predecessor_scheduling(db, op, start) is None

    def test_in_block_predecessor_rejected_even_when_its_old_window_fits(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        product = make_product()
        wo = make_production_order(product_id=product.id)
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        pred = _make_operation(
            db, wo.id, wc.id, sequence=10, status="queued",
            scheduled_start=start - timedelta(hours=2),
            scheduled_end=start - timedelta(hours=1),
        )
        op = _make_operation(db, wo.id, wc.id, sequence=20)

        assert check_predecessor_scheduling(db, op, start) is None
        error = check_predecessor_scheduling(db, op, start, in_block_ids={pred.id})
        assert error is not None
        assert "same block" in error

    def test_in_block_predecessor_allowed_with_can_overlap(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        product = make_product()
        overlap_op = _make_overlap_routing_op(db, product.id, wc.id)
        wo = make_production_order(product_id=product.id)
        pred = _make_operation(db, wo.id, wc.id, sequence=10)  # unscheduled
        op = _make_operation(db, wo.id, wc.id, sequence=20, routing_operation_id=overlap_op.id)
        start = datetime.now(timezone.utc) + timedelta(hours=1)

        # Outside a block an unscheduled predecessor still blocks, overlap or not
        assert "must be scheduled" in check_predecessor_scheduling(db, op, start)
        # Inside the block it will be scheduled by the same write
        assert check_predecessor_scheduling(db, op, start, in_block_ids={pred.id}) is None
