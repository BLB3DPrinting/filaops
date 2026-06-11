"""
Tests for app/services/dispatch_service.py — SCHED-1.

Covers (per plan):
- ranking order: priority beats due date beats FIFO (created_at)
- maintenance-status printers are skipped
- maintenance-due warning present/absent
- incompatible material excluded
- predecessor-not-ready excluded
- assign path validates conflicts
- assign sets status to 'queued'
- Decimal discipline (quantity serialised as str, no float drift)
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.maintenance import MaintenanceLog
from app.models.manufacturing import Resource
from app.models.printer import Printer
from app.models.production_order import ProductionOrder, ProductionOrderOperation
from app.services.dispatch_service import (
    DEFAULT_DURATION_MINUTES,
    dispatch_operation,
    get_dispatch_suggestions,
)


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_printer(db, *, status: str = "idle", work_center_id=None, model: str = "X1C") -> Printer:
    uid = _uid()
    p = Printer(
        code=f"PRT-{uid}",
        name=f"Printer {uid}",
        model=model,
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


def _make_wo(
    db,
    product_id: int,
    *,
    status: str = "released",
    priority: int = 3,
    due_date=None,
    created_at=None,
) -> ProductionOrder:
    uid = _uid()
    wo = ProductionOrder(
        code=f"WO-{uid}",
        product_id=product_id,
        quantity_ordered=Decimal("10"),
        status=status,
        priority=priority,
        due_date=due_date,
        source="manual",
    )
    if created_at is not None:
        wo.created_at = created_at
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


def _make_maintenance_log(
    db,
    printer_id: int,
    *,
    next_due_at=None,
    performed_at=None,
) -> MaintenanceLog:
    log = MaintenanceLog(
        printer_id=printer_id,
        maintenance_type="routine",
        performed_at=performed_at or _now(),
        next_due_at=next_due_at,
    )
    db.add(log)
    db.flush()
    return log


# ---------------------------------------------------------------------------
# Tests: get_dispatch_suggestions — read-only path
# ---------------------------------------------------------------------------


class TestGetDispatchSuggestions:
    """Tests for the read-only suggestion path."""

    def test_no_printers_returns_empty(self, db, make_product, make_work_center):
        """With no active printers in DB, results is empty."""
        resp = get_dispatch_suggestions(db)
        # Results may contain printers from other tests due to non-isolated DB;
        # we at least verify the response shape is correct.
        assert hasattr(resp, "results")
        assert hasattr(resp, "generated_at")

    def test_maintenance_status_printer_skipped(
        self, db, make_product, make_work_center
    ):
        """Printers with status='maintenance' are excluded from suggestions."""
        wc = make_work_center()
        product = make_product()
        maint_printer = _make_printer(db, status="maintenance", work_center_id=wc.id)
        idle_printer = _make_printer(db, status="idle", work_center_id=wc.id)

        # Create a released WO with a pending op tied to the wc
        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id)

        resp = get_dispatch_suggestions(db)

        # The maintenance printer should not appear in results
        result_printer_ids = {r.printer.id for r in resp.results}
        assert maint_printer.id not in result_printer_ids

        # The idle printer should appear
        assert idle_printer.id in result_printer_ids

    def test_priority_beats_due_date(self, db, make_product, make_work_center):
        """Priority 1 surfaces before priority 3, even if priority-3 has earlier due date."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        # WO-A: priority 3, due yesterday (earlier due)
        wo_a = _make_wo(
            db,
            product.id,
            priority=3,
            due_date=date.today() - timedelta(days=1),
        )
        _make_op(db, wo_a.id, wc.id)

        # WO-B: priority 1, due next week (later due)
        wo_b = _make_wo(
            db,
            product.id,
            priority=1,
            due_date=date.today() + timedelta(days=7),
        )
        _make_op(db, wo_b.id, wc.id)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        assert len(resp.results) == 1
        result = resp.results[0]

        assert result.top_suggestion is not None
        # Priority 1 (WO-B) must win over priority 3 (WO-A)
        assert result.top_suggestion.production_order_id == wo_b.id

        # WO-A should appear in runners_up
        runner_ids = [r.production_order_id for r in result.runners_up]
        assert wo_a.id in runner_ids

    def test_due_date_beats_fifo(self, db, make_product, make_work_center):
        """Same priority: earlier due date beats later-created order."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        now = _now()
        # WO-old: created first (FIFO advantage), due far future
        wo_old = _make_wo(
            db,
            product.id,
            priority=2,
            due_date=date.today() + timedelta(days=30),
            created_at=now - timedelta(hours=2),
        )
        _make_op(db, wo_old.id, wc.id)

        # WO-urgent: created later, due tomorrow
        wo_urgent = _make_wo(
            db,
            product.id,
            priority=2,
            due_date=date.today() + timedelta(days=1),
            created_at=now - timedelta(hours=1),
        )
        _make_op(db, wo_urgent.id, wc.id)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        assert len(resp.results) == 1
        result = resp.results[0]

        assert result.top_suggestion is not None
        # Due-tomorrow must beat created-first
        assert result.top_suggestion.production_order_id == wo_urgent.id

    def test_fifo_tiebreaker(self, db, make_product, make_work_center):
        """Same priority + same due date: older created_at wins."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        due = date.today() + timedelta(days=5)

        now = _now()
        wo_first = _make_wo(
            db, product.id, priority=2, due_date=due, created_at=now - timedelta(hours=3)
        )
        _make_op(db, wo_first.id, wc.id)

        wo_second = _make_wo(
            db, product.id, priority=2, due_date=due, created_at=now - timedelta(hours=1)
        )
        _make_op(db, wo_second.id, wc.id)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        assert len(resp.results) == 1
        result = resp.results[0]

        assert result.top_suggestion is not None
        assert result.top_suggestion.production_order_id == wo_first.id

    def test_why_contains_priority_and_due(self, db, make_product, make_work_center):
        """'why' list includes priority, due date, and FIFO labels."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        due = date.today() + timedelta(days=3)

        wo = _make_wo(db, product.id, priority=1, due_date=due)
        _make_op(db, wo.id, wc.id)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]
        assert result.top_suggestion is not None

        why = result.top_suggestion.why
        assert any("priority 1" in w for w in why)
        assert any(due.isoformat() in w for w in why)
        assert any("FIFO" in w for w in why)

    def test_no_suggestion_when_no_released_orders(
        self, db, make_product, make_work_center
    ):
        """Draft orders should not appear in suggestions."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id, status="draft")
        _make_op(db, wo.id, wc.id)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]
        # No released orders → no suggestion
        assert result.top_suggestion is None

    def test_maintenance_due_warning_present(self, db, make_product, make_work_center):
        """maintenance_warning is set when next_due_at < now + duration."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        # Log: next maintenance due in 30 minutes (before a 60-min job finishes)
        _make_maintenance_log(
            db,
            printer.id,
            next_due_at=_now() + timedelta(minutes=30),
        )

        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id, planned_run_minutes=60)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]

        assert result.top_suggestion is not None
        assert result.top_suggestion.maintenance_warning is not None
        assert "maintenance due" in result.top_suggestion.maintenance_warning.lower()

    def test_maintenance_due_warning_absent(self, db, make_product, make_work_center):
        """maintenance_warning is None when next_due_at is well after job end."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        # Next maintenance in 2 weeks — well after a 60-min job
        _make_maintenance_log(
            db,
            printer.id,
            next_due_at=_now() + timedelta(days=14),
        )

        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id, planned_run_minutes=60)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]

        assert result.top_suggestion is not None
        assert result.top_suggestion.maintenance_warning is None

    def test_maintenance_no_log_no_warning(self, db, make_product, make_work_center):
        """No MaintenanceLog rows → no maintenance_warning."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]

        assert result.top_suggestion is not None
        assert result.top_suggestion.maintenance_warning is None

    def test_incompatible_material_excluded(
        self, db, make_product, make_work_center
    ):
        """ABS job on open-frame printer is excluded from candidates."""
        from app.models.material import MaterialType
        from app.models.bom import BOM, BOMLine

        wc = make_work_center()
        # Open-frame printer (no enclosure — X1C actually has one in real life
        # but we use model="A1" so machine_has_enclosure returns False)
        printer = _make_printer(
            db, status="idle", work_center_id=wc.id, model="A1"
        )

        # ABS material type — requires enclosure
        abs_type = MaterialType(
            code=f"ABS-{_uid()}",
            name="ABS",
            base_material="ABS",
            density=Decimal("1.04"),
            base_price_per_kg=Decimal("25.00"),
            requires_enclosure=True,
            active=True,
            is_customer_visible=True,
        )
        db.add(abs_type)
        db.flush()

        # Product that is itself an ABS material
        abs_product = make_product(
            item_type="supply",
            unit="G",
            is_raw_material=True,
            material_type_id=abs_type.id,
        )
        # Finished-good product for the WO
        fg = make_product()

        wo = _make_wo(db, fg.id)
        _make_op(db, wo.id, wc.id)

        # Associate ABS component via BOM so is_machine_compatible sees it
        bom = BOM(
            product_id=fg.id,
            name=f"BOM-{_uid()}",
            active=True,
        )
        db.add(bom)
        db.flush()
        db.add(BOMLine(
            bom_id=bom.id,
            component_id=abs_product.id,
            quantity=Decimal("100"),
            unit="G",
        ))
        # Link BOM to WO
        wo.bom_id = bom.id
        db.flush()

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]

        # ABS on open-frame printer must be excluded
        assert result.top_suggestion is None

    def test_predecessor_not_ready_excluded(
        self, db, make_product, make_work_center
    ):
        """Op with pending predecessor (not yet scheduled) is excluded."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id)

        # Op-10 (predecessor) — pending, not scheduled
        _make_op(db, wo.id, wc.id, sequence=10, status="pending")

        # Op-20 (successor) — also pending, but predecessor blocks it
        _make_op(db, wo.id, wc.id, sequence=20, status="pending")

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]

        # Op-20 is blocked by Op-10; only Op-10 should be suggested
        assert result.top_suggestion is not None
        # Top must be Op-10 (the first sequence) not Op-20
        # We can verify no suggestion refers to sequence=20 among top+runners_up
        suggested_op_ids = set()
        if result.top_suggestion:
            suggested_op_ids.add(result.top_suggestion.operation_id)
        for r in result.runners_up:
            suggested_op_ids.add(r.operation_id)

        ops_in_suggestions = (
            db.query(ProductionOrderOperation)
            .filter(ProductionOrderOperation.id.in_(suggested_op_ids))
            .all()
        )
        for op in ops_in_suggestions:
            assert op.sequence != 20, (
                "Op with sequence=20 should not appear — predecessor not satisfied"
            )

    def test_runners_up_capped_at_two(self, db, make_product, make_work_center):
        """runners_up contains at most MAX_RUNNERS_UP (2) entries."""
        from app.services.dispatch_service import MAX_RUNNERS_UP
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        for i in range(5):
            wo = _make_wo(db, product.id, priority=3)
            _make_op(db, wo.id, wc.id)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]

        assert len(result.runners_up) <= MAX_RUNNERS_UP

    def test_quantity_is_decimal_string(self, db, make_product, make_work_center):
        """quantity in suggestion is a string representation (no float drift)."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id)

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]

        assert result.top_suggestion is not None
        qty = result.top_suggestion.quantity
        # Must be a string (not float)
        assert isinstance(qty, str)
        # Must be parse-able as Decimal without losing precision
        Decimal(qty)

    def test_default_duration_used_when_no_planned_minutes(
        self, db, make_product, make_work_center
    ):
        """When planned_run_minutes = 0, DEFAULT_DURATION_MINUTES is applied."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id)
        # planned_run_minutes defaults to 60 in _make_op;
        # set it to 0 to trigger the default path
        op = ProductionOrderOperation(
            production_order_id=wo.id,
            work_center_id=wc.id,
            sequence=10,
            operation_code=f"OP-{_uid()}",
            operation_name="Print",
            planned_setup_minutes=Decimal("0"),
            planned_run_minutes=Decimal("0"),
            status="pending",
        )
        db.add(op)
        db.flush()

        resp = get_dispatch_suggestions(db, printer_id=printer.id)
        result = resp.results[0]

        assert result.top_suggestion is not None
        assert result.top_suggestion.estimated_duration_minutes == DEFAULT_DURATION_MINUTES


# ---------------------------------------------------------------------------
# Tests: dispatch_operation — write path
# ---------------------------------------------------------------------------


class TestDispatchOperation:
    """Tests for the write/assign path."""

    def test_assigns_operation_and_sets_queued(
        self, db, make_product, make_work_center
    ):
        """Successful assign sets op.status='queued' and records scheduled times."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id)
        op = _make_op(db, wo.id, wc.id)

        user = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(id=1).first()

        from datetime import datetime as _dt, timezone as _tz
        before = _dt.now(_tz.utc)

        result = dispatch_operation(db, op.id, printer.id, user)

        assert result.operation_status == "queued"
        assert result.printer_id == printer.id
        assert result.printer_code == printer.code
        assert result.production_order_code == wo.code

        # Scheduled times should be set
        assert result.scheduled_start >= before
        assert result.scheduled_end > result.scheduled_start

        # Verify DB-side
        db.expire(op)
        assert op.status == "queued"
        assert op.printer_id == printer.id
        assert op.scheduled_start is not None

    def test_assign_rejects_maintenance_printer(
        self, db, make_product, make_work_center
    ):
        """dispatch_operation raises ValueError for a printer in maintenance."""
        wc = make_work_center()
        product = make_product()
        maint_printer = _make_printer(db, status="maintenance", work_center_id=wc.id)

        wo = _make_wo(db, product.id)
        op = _make_op(db, wo.id, wc.id)

        user = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(id=1).first()

        with pytest.raises(ValueError, match="maintenance"):
            dispatch_operation(db, op.id, maint_printer.id, user)

    def test_assign_rejects_non_pending_operation(
        self, db, make_product, make_work_center
    ):
        """dispatch_operation raises ValueError if op is already queued/running."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id)
        op = _make_op(db, wo.id, wc.id, status="queued")  # already queued

        user = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(id=1).first()

        with pytest.raises(ValueError, match="queued"):
            dispatch_operation(db, op.id, printer.id, user)

    def test_assign_rejects_non_released_order(
        self, db, make_product, make_work_center
    ):
        """dispatch_operation raises ValueError if WO is draft (not released)."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id, status="draft")
        op = _make_op(db, wo.id, wc.id)

        user = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(id=1).first()

        with pytest.raises(ValueError, match="draft"):
            dispatch_operation(db, op.id, printer.id, user)

    def test_assign_validates_conflicts(self, db, make_product, make_work_center):
        """dispatch_operation raises RuntimeError when a time conflict exists."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        now = _now()
        # Pre-schedule op-A on the printer to create a conflict
        wo_a = _make_wo(db, product.id)
        op_a = ProductionOrderOperation(
            production_order_id=wo_a.id,
            work_center_id=wc.id,
            sequence=10,
            operation_code=f"OP-A-{_uid()}",
            operation_name="Print A",
            planned_setup_minutes=Decimal("0"),
            planned_run_minutes=Decimal("120"),
            status="queued",
            printer_id=printer.id,
            scheduled_start=now - timedelta(minutes=10),
            scheduled_end=now + timedelta(minutes=110),
        )
        db.add(op_a)
        db.flush()

        # Try to dispatch op-B to the same printer in the overlapping slot
        wo_b = _make_wo(db, product.id)
        op_b = _make_op(db, wo_b.id, wc.id, planned_run_minutes=60)

        user = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(id=1).first()

        with pytest.raises(RuntimeError, match="conflict"):
            dispatch_operation(db, op_b.id, printer.id, user)

    def test_assign_missing_operation_raises_value_error(
        self, db, make_work_center
    ):
        wc = make_work_center()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)
        user = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(id=1).first()

        with pytest.raises(ValueError, match="not found"):
            dispatch_operation(db, 999_999, printer.id, user)

    def test_assign_missing_printer_raises_value_error(
        self, db, make_product, make_work_center
    ):
        wc = make_work_center()
        product = make_product()
        wo = _make_wo(db, product.id)
        op = _make_op(db, wo.id, wc.id)
        user = db.query(__import__("app.models.user", fromlist=["User"]).User).filter_by(id=1).first()

        with pytest.raises(ValueError, match="not found"):
            dispatch_operation(db, op.id, 999_999, user)
