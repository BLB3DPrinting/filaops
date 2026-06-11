"""Tests for operation scheduling helper endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.printer import Printer
from app.models.production_order import ProductionOrderOperation


BASE_URL = "/api/v1/production-orders"


def _uid():
    return uuid.uuid4().hex[:6]


def _make_printer(db, work_center_id):
    uid = _uid()
    printer = Printer(
        code=f"PRT-{uid}",
        name=f"Test Printer {uid}",
        model="X1C",
        brand="bambulab",
        work_center_id=work_center_id,
        status="idle",
    )
    db.add(printer)
    db.flush()
    return printer


def _make_operation(db, production_order_id, work_center_id, sequence=10, status="pending", **kwargs):
    operation = ProductionOrderOperation(
        production_order_id=production_order_id,
        work_center_id=work_center_id,
        sequence=sequence,
        operation_name=kwargs.pop("operation_name", f"Op-{sequence}"),
        planned_run_minutes=kwargs.pop("planned_run_minutes", 60),
        status=status,
        **kwargs,
    )
    db.add(operation)
    db.flush()
    return operation


class TestNextAvailableSlotEndpoint:
    def test_occupied_printer_uses_printer_schedule(self, client, db, make_product, make_production_order, make_work_center):
        work_center = make_work_center()
        printer = _make_printer(db, work_center.id)
        product = make_product()
        production_order = make_production_order(product_id=product.id)

        now = datetime.now(timezone.utc).replace(microsecond=0)
        busy_until = now + timedelta(hours=2)
        _make_operation(
            db,
            production_order.id,
            work_center.id,
            status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=busy_until,
        )
        db.flush()

        response = client.post(
            f"{BASE_URL}/resources/next-available",
            json={
                "resource_id": printer.id,
                "duration_minutes": 60,
                "is_printer": True,
                "after": now.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()

        next_available = datetime.fromisoformat(data["next_available"])
        assert next_available >= busy_until

    def test_next_available_requires_auth(self, unauthed_client):
        response = unauthed_client.post(
            f"{BASE_URL}/resources/next-available",
            json={
                "resource_id": 1,
                "duration_minutes": 60,
                "is_printer": True,
            },
        )

        assert response.status_code == 401


class TestScheduleOperationPredecessorResponse:
    """Verify predecessor violation returns earliest_valid_start >= predecessor end."""

    def test_predecessor_violation_returns_earliest_valid_start(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """
        Scheduling OP020 while OP010 isn't finished should return:
          success=False, conflict_type="predecessor",
          earliest_valid_start >= OP010's scheduled_end.
        """
        work_center = make_work_center()
        printer = _make_printer(db, work_center.id)
        product = make_product()
        po = make_production_order(product_id=product.id)

        now = datetime.now(timezone.utc).replace(microsecond=0)
        pred_end = now + timedelta(hours=3)

        # OP010 — predecessor, already scheduled (queued), ends in 3 hours
        pred_op = _make_operation(
            db,
            po.id,
            work_center.id,
            sequence=10,
            status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=pred_end,
        )
        assert pred_op.id  # flush succeeded

        # OP020 — the op we want to schedule too early
        op = _make_operation(
            db,
            po.id,
            work_center.id,
            sequence=20,
            status="pending",
        )

        # Try to schedule OP020 starting NOW — before OP010 ends
        response = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/schedule",
            json={
                "resource_id": printer.id,
                "is_printer": True,
                "scheduled_start": now.isoformat(),
                "scheduled_end": (now + timedelta(hours=1)).isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["conflict_type"] == "predecessor"
        assert data["earliest_valid_start"] is not None

        # earliest_valid_start must be >= the predecessor's scheduled_end
        earliest = datetime.fromisoformat(data["earliest_valid_start"])
        assert earliest >= pred_end.replace(tzinfo=None) or earliest >= pred_end

    def test_predecessor_violation_next_available_start_present(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """next_available_start must be present and >= earliest_valid_start."""
        work_center = make_work_center()
        printer = _make_printer(db, work_center.id)
        product = make_product()
        po = make_production_order(product_id=product.id)

        now = datetime.now(timezone.utc).replace(microsecond=0)
        pred_end = now + timedelta(hours=2)

        _make_operation(
            db,
            po.id,
            work_center.id,
            sequence=10,
            status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=pred_end,
        )

        op = _make_operation(
            db,
            po.id,
            work_center.id,
            sequence=20,
            status="pending",
        )

        response = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/schedule",
            json={
                "resource_id": printer.id,
                "is_printer": True,
                "scheduled_start": now.isoformat(),
                "scheduled_end": (now + timedelta(hours=1)).isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["next_available_start"] is not None

        earliest = datetime.fromisoformat(data["earliest_valid_start"])
        next_avail = datetime.fromisoformat(data["next_available_start"])
        # next_available_start must be at or after the predecessor end
        # (normalise tz for comparison)
        def _naive(dt):
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        assert _naive(next_avail) >= _naive(earliest)

    def test_resource_conflict_uses_resource_conflict_type(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Pure resource conflict (no predecessors) uses conflict_type='resource'."""
        work_center = make_work_center()
        printer = _make_printer(db, work_center.id)
        product = make_product()

        # Two separate POs so there's no predecessor relationship
        po1 = make_production_order(product_id=product.id)
        po2 = make_production_order(product_id=product.id)

        now = datetime.now(timezone.utc).replace(microsecond=0)
        # Occupy the printer for 2 hours on PO1
        _make_operation(
            db,
            po1.id,
            work_center.id,
            sequence=10,
            status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=2),
        )

        # Single op on PO2 — no predecessors
        op2 = _make_operation(
            db,
            po2.id,
            work_center.id,
            sequence=10,
            status="pending",
        )

        # Try to schedule PO2's op in the same window
        response = client.post(
            f"{BASE_URL}/{po2.id}/operations/{op2.id}/schedule",
            json={
                "resource_id": printer.id,
                "is_printer": True,
                "scheduled_start": now.isoformat(),
                "scheduled_end": (now + timedelta(hours=1)).isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["conflict_type"] == "resource"
        # No predecessor constraint
        assert data.get("earliest_valid_start") is None