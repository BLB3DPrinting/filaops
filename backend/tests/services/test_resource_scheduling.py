"""Tests for resource_scheduling.py — scheduling + conflict detection."""
import pytest
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.resource_scheduling import (
    get_resource_schedule,
    find_conflicts,
    find_running_operations,
    check_resource_available_now,
    find_next_available_slot,
    schedule_operation,
)
from app.models.production_order import ProductionOrderOperation
from app.models.manufacturing import Resource
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
        now = datetime.utcnow()
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
        now = datetime.utcnow()
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
        now = datetime.utcnow()
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
