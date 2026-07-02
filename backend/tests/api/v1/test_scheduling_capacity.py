"""Tests for the capacity/auto-schedule plane (#857 G1/G3/G4/G5/G8).

These endpoints previously read ProductionOrder-level scheduled_* columns that
the operation-scheduling path never populates, so a machine booked solid via
the scheduler modal reported zero utilization and auto-schedule double-booked
it. They now read the same operation-level bookings (plus blocking maintenance
windows) the rest of the scheduling engine uses.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.core import plugin_registry
from app.models.maintenance import MaintenanceWindow
from app.models.manufacturing import Resource
from app.models.production_order import ProductionOrderOperation

BASE_URL = "/api/v1/scheduling"


def _uid():
    return uuid.uuid4().hex[:6]


def _make_resource(db, work_center_id, status="available"):
    resource = Resource(
        work_center_id=work_center_id,
        code=f"RES-{_uid()}",
        name=f"Test Resource {_uid()}",
        status=status,
        is_active=True,
    )
    db.add(resource)
    db.flush()
    return resource


def _make_operation(db, production_order_id, work_center_id, sequence=10, status="queued", **kwargs):
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


def _tomorrow_midnight():
    """Deterministic all-future anchor (naive UTC, matching the columns)."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _z(dt):
    """Serialize as a Z-suffixed (tz-aware) ISO timestamp — the client
    convention that previously TypeError'd these endpoints (#857 G4)."""
    return dt.isoformat() + "Z"


class TestCapacityCheck:
    """POST /scheduling/capacity/check"""

    def test_operation_booking_conflicts(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """An op-level booking must be visible to the capacity check — and
        Z-suffixed timestamps must not 500 (G1 + G4)."""
        wc = make_work_center()
        resource = _make_resource(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        t0 = _tomorrow_midnight()
        _make_operation(
            db, po.id, wc.id,
            resource_id=resource.id,
            scheduled_start=t0, scheduled_end=t0 + timedelta(hours=4),
        )
        db.flush()

        response = client.post(
            f"{BASE_URL}/capacity/check",
            json={
                "resource_id": resource.id,
                "start_time": _z(t0 + timedelta(hours=1)),
                "end_time": _z(t0 + timedelta(hours=2)),
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["has_capacity"] is False
        assert data["conflicts"][0]["type"] == "operation"
        assert data["conflicts"][0]["order_code"] == po.code

    def test_free_machine_has_capacity(self, client, db, make_work_center):
        wc = make_work_center()
        resource = _make_resource(db, wc.id)
        t0 = _tomorrow_midnight()
        response = client.post(
            f"{BASE_URL}/capacity/check",
            json={
                "resource_id": resource.id,
                "start_time": _z(t0),
                "end_time": _z(t0 + timedelta(hours=2)),
            },
        )
        assert response.status_code == 200
        assert response.json()["has_capacity"] is True

    def test_printer_lane_conflicts(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Printer bookings live in a separate ID space — is_printer=True must
        find them (the old query cross-compared printer ids to resource ids)."""
        from app.models.printer import Printer

        wc = make_work_center()
        printer = Printer(
            code=f"PRT-{_uid()}", name="Test Printer", model="X1C",
            brand="bambulab", work_center_id=wc.id, status="idle",
        )
        db.add(printer)
        db.flush()
        po = make_production_order(product_id=make_product().id)
        t0 = _tomorrow_midnight()
        _make_operation(
            db, po.id, wc.id,
            printer_id=printer.id,
            scheduled_start=t0, scheduled_end=t0 + timedelta(hours=4),
        )
        db.flush()

        response = client.post(
            f"{BASE_URL}/capacity/check",
            json={
                "resource_id": printer.id,
                "start_time": _z(t0),
                "end_time": _z(t0 + timedelta(hours=1)),
                "is_printer": True,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["has_capacity"] is False

    def test_maintenance_window_conflicts(self, client, db, make_work_center):
        """A blocking maintenance window is busy time (the old read ignored it)."""
        wc = make_work_center()
        resource = _make_resource(db, wc.id)
        t0 = _tomorrow_midnight()
        db.add(MaintenanceWindow(
            resource_id=resource.id,
            starts_at=t0, ends_at=t0 + timedelta(hours=3),
            status="scheduled", reason="Nozzle swap",
        ))
        db.flush()

        response = client.post(
            f"{BASE_URL}/capacity/check",
            json={
                "resource_id": resource.id,
                "start_time": _z(t0 + timedelta(hours=1)),
                "end_time": _z(t0 + timedelta(hours=2)),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_capacity"] is False
        assert data["conflicts"][0]["type"] == "maintenance"


class TestAvailableSlots:
    """GET /scheduling/capacity/available-slots"""

    def test_gaps_around_op_booking(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center()
        resource = _make_resource(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        t0 = _tomorrow_midnight()
        _make_operation(
            db, po.id, wc.id,
            resource_id=resource.id,
            scheduled_start=t0 + timedelta(hours=8),
            scheduled_end=t0 + timedelta(hours=16),
        )
        db.flush()

        response = client.get(
            f"{BASE_URL}/capacity/available-slots",
            params={
                "resource_id": resource.id,
                "start_date": _z(t0),
                "end_date": _z(t0 + timedelta(hours=24)),
                "duration_hours": 2.0,
            },
        )
        assert response.status_code == 200, response.text
        slots = response.json()
        assert len(slots) == 2
        assert slots[0]["duration_hours"] == pytest.approx(8.0)
        assert slots[1]["duration_hours"] == pytest.approx(8.0)


class TestMachineAvailability:
    """GET /scheduling/capacity/machine-availability"""

    def test_op_booking_drives_utilization(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """A modal-scheduled op must show up as utilization (was always 0%)."""
        wc = make_work_center()
        resource = _make_resource(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        t0 = _tomorrow_midnight()
        _make_operation(
            db, po.id, wc.id,
            resource_id=resource.id,
            scheduled_start=t0, scheduled_end=t0 + timedelta(hours=4),
        )
        db.flush()

        response = client.get(
            f"{BASE_URL}/capacity/machine-availability",
            params={
                "start_date": _z(t0),
                "end_date": _z(t0 + timedelta(hours=8)),
                "work_center_id": wc.id,
            },
        )
        assert response.status_code == 200, response.text
        row = next(r for r in response.json() if r["resource_id"] == resource.id)
        assert row["scheduled_hours"] == pytest.approx(4.0)
        assert row["utilization_percent"] == pytest.approx(50.0)
        assert row["scheduled_order_count"] == 1


class TestAutoSchedule:
    """POST /scheduling/auto-schedule (PRO-gated feature: production_advanced)"""

    @pytest.fixture(autouse=True)
    def _license(self):
        plugin_registry.set_features(["production_advanced"])
        yield
        plugin_registry.reset()

    def test_unlicensed_returns_403(self, client, db, make_product, make_production_order):
        plugin_registry.reset()
        po = make_production_order(product_id=make_product().id)
        db.flush()
        response = client.post(f"{BASE_URL}/auto-schedule", params={"order_id": po.id})
        assert response.status_code == 403

    def test_slots_after_existing_op_booking(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Auto-schedule must not overlap an operation-level booking (G1/G5 —
        the old read saw order-level columns nothing populates)."""
        wc = make_work_center()
        resource = _make_resource(db, wc.id)
        busy_po = make_production_order(product_id=make_product().id)
        t0 = _tomorrow_midnight()
        busy_end = t0 + timedelta(hours=4)
        _make_operation(
            db, busy_po.id, wc.id,
            resource_id=resource.id,
            scheduled_start=t0, scheduled_end=busy_end,
        )
        target_po = make_production_order(product_id=make_product().id)
        db.flush()

        response = client.post(
            f"{BASE_URL}/auto-schedule",
            params={
                "order_id": target_po.id,
                "preferred_start": _z(t0),
                "work_center_id": wc.id,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        scheduled_start = datetime.fromisoformat(data["scheduled_start"])
        assert scheduled_start >= busy_end

    def test_skips_maintenance_window(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Auto-schedule must not book over a blocking maintenance window (G5)."""
        wc = make_work_center()
        resource = _make_resource(db, wc.id)
        t0 = _tomorrow_midnight()
        window_end = t0 + timedelta(hours=5)
        db.add(MaintenanceWindow(
            resource_id=resource.id,
            starts_at=t0, ends_at=window_end,
            status="scheduled", reason="Belt tensioning",
        ))
        po = make_production_order(product_id=make_product().id)
        db.flush()

        response = client.post(
            f"{BASE_URL}/auto-schedule",
            params={
                "order_id": po.id,
                "preferred_start": _z(t0),
                "work_center_id": wc.id,
            },
        )
        assert response.status_code == 200, response.text
        scheduled_start = datetime.fromisoformat(response.json()["scheduled_start"])
        assert scheduled_start >= window_end

    def test_duration_from_operation_planned_minutes(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """With no estimated_time_minutes, duration comes from the routing's
        planned minutes, not the 2h default (G3)."""
        wc = make_work_center()
        _make_resource(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        t0 = _tomorrow_midnight()
        _make_operation(
            db, po.id, wc.id, sequence=10, status="pending",
            planned_run_minutes=300, planned_setup_minutes=60,
        )
        db.flush()

        response = client.post(
            f"{BASE_URL}/auto-schedule",
            params={
                "order_id": po.id,
                "preferred_start": _z(t0),
                "work_center_id": wc.id,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        start = datetime.fromisoformat(data["scheduled_start"])
        end = datetime.fromisoformat(data["scheduled_end"])
        assert (end - start) == timedelta(hours=6)  # 300 + 60 minutes

    def test_no_slot_returns_409(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """No slot inside the window is a 409, not a 404 — the frontend treats
        404 as 'PRO plugin not installed' (G8)."""
        wc = make_work_center()
        resource = _make_resource(db, wc.id)
        busy_po = make_production_order(product_id=make_product().id)
        t0 = _tomorrow_midnight()
        _make_operation(
            db, busy_po.id, wc.id,
            resource_id=resource.id,
            scheduled_start=t0, scheduled_end=t0 + timedelta(days=8),
        )
        target_po = make_production_order(product_id=make_product().id)
        db.flush()

        response = client.post(
            f"{BASE_URL}/auto-schedule",
            params={
                "order_id": target_po.id,
                "preferred_start": _z(t0),
                "work_center_id": wc.id,
            },
        )
        assert response.status_code == 409, response.text
