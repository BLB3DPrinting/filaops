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