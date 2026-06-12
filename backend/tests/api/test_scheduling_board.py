"""
API tests for GET /api/v1/scheduling/board (SCHED-5 Gantt view).

Covers:
- 401 unauthenticated
- 422 inverted window
- lanes include machine-type resources and printers
- operations land in the correct lane (resource_id vs printer_id)
- window filtering (ops outside the window excluded)
- utilization is clipped to the window
- unscheduled queue lists orders with unscheduled non-terminal ops,
  including the first unscheduled op as the modal click target
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.manufacturing import Resource
from app.models.printer import Printer
from app.models.production_order import ProductionOrder, ProductionOrderOperation


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_machine_resource(db, work_center_id) -> Resource:
    r = Resource(
        code=f"MCH-{_uid()}",
        name=f"Machine {_uid()}",
        work_center_id=work_center_id,
        status="available",
        is_active=True,
    )
    db.add(r)
    db.flush()
    return r


def _make_printer(db) -> Printer:
    p = Printer(
        code=f"PRT-{_uid()}",
        name=f"Printer {_uid()}",
        model="P1S",
        brand="bambulab",
        status="idle",
        active=True,
    )
    db.add(p)
    db.flush()
    return p


def _make_wo(db, product_id, status="released") -> ProductionOrder:
    wo = ProductionOrder(
        code=f"WO-{_uid()}",
        product_id=product_id,
        quantity_ordered=Decimal("5"),
        status=status,
        priority=2,
        source="manual",
    )
    db.add(wo)
    db.flush()
    return wo


def _make_op(
    db,
    wo_id,
    work_center_id,
    *,
    resource_id=None,
    printer_id=None,
    start=None,
    end=None,
    status="queued",
    sequence=10,
) -> ProductionOrderOperation:
    op = ProductionOrderOperation(
        production_order_id=wo_id,
        work_center_id=work_center_id,
        sequence=sequence,
        operation_code=f"OP-{_uid()}",
        operation_name="Print",
        planned_setup_minutes=Decimal("0"),
        planned_run_minutes=Decimal("60"),
        status=status,
        resource_id=resource_id,
        printer_id=printer_id,
        scheduled_start=start,
        scheduled_end=end,
    )
    db.add(op)
    db.flush()
    return op


def _window():
    start = datetime(2026, 6, 15, 0, 0, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def _board(client, start, end):
    resp = client.get(
        "/api/v1/scheduling/board",
        params={"start_date": start.isoformat(), "end_date": end.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class TestSchedulingBoardEndpoint:

    def test_unauthenticated_returns_401(self, unauthed_client):
        start, end = _window()
        resp = unauthed_client.get(
            "/api/v1/scheduling/board",
            params={"start_date": start.isoformat(), "end_date": end.isoformat()},
        )
        assert resp.status_code == 401

    def test_inverted_window_returns_422(self, client):
        start, end = _window()
        resp = client.get(
            "/api/v1/scheduling/board",
            params={"start_date": end.isoformat(), "end_date": start.isoformat()},
        )
        assert resp.status_code == 422

    def test_lanes_include_machine_resources_and_printers(
        self, client, db, make_work_center
    ):
        wc = make_work_center(center_type="machine")
        resource = _make_machine_resource(db, wc.id)
        printer = _make_printer(db)

        start, end = _window()
        data = _board(client, start, end)

        keys = {lane["key"] for lane in data["lanes"]}
        assert f"resource-{resource.id}" in keys
        assert f"printer-{printer.id}" in keys
        kinds = {lane["key"]: lane["kind"] for lane in data["lanes"]}
        assert kinds[f"resource-{resource.id}"] == "resource"
        assert kinds[f"printer-{printer.id}"] == "printer"

    def test_ops_land_in_correct_lane(
        self, client, db, make_work_center, make_product
    ):
        wc = make_work_center(center_type="machine")
        resource = _make_machine_resource(db, wc.id)
        printer = _make_printer(db)
        product = make_product()
        wo = _make_wo(db, product.id)

        start, end = _window()
        op_res = _make_op(
            db, wo.id, wc.id,
            resource_id=resource.id,
            start=start + timedelta(hours=2),
            end=start + timedelta(hours=5),
        )
        op_prt = _make_op(
            db, wo.id, wc.id,
            printer_id=printer.id,
            start=start + timedelta(hours=6),
            end=start + timedelta(hours=8),
            sequence=20,
        )

        data = _board(client, start, end)
        by_key = {lane["key"]: lane for lane in data["lanes"]}

        res_ops = {o["id"] for o in by_key[f"resource-{resource.id}"]["operations"]}
        prt_ops = {o["id"] for o in by_key[f"printer-{printer.id}"]["operations"]}
        assert op_res.id in res_ops
        assert op_prt.id in prt_ops
        assert op_res.id not in prt_ops

        block = next(
            o for o in by_key[f"resource-{resource.id}"]["operations"]
            if o["id"] == op_res.id
        )
        assert block["production_order_code"] == wo.code
        assert block["status"] == "queued"

    def test_window_excludes_outside_ops(
        self, client, db, make_work_center, make_product
    ):
        wc = make_work_center(center_type="machine")
        resource = _make_machine_resource(db, wc.id)
        product = make_product()
        wo = _make_wo(db, product.id)

        start, end = _window()
        # Entirely before the window
        op_before = _make_op(
            db, wo.id, wc.id,
            resource_id=resource.id,
            start=start - timedelta(hours=10),
            end=start - timedelta(hours=8),
        )
        # Straddles the window start — must be included
        op_straddle = _make_op(
            db, wo.id, wc.id,
            resource_id=resource.id,
            start=start - timedelta(hours=1),
            end=start + timedelta(hours=1),
            sequence=20,
        )

        data = _board(client, start, end)
        by_key = {lane["key"]: lane for lane in data["lanes"]}
        ids = {o["id"] for o in by_key[f"resource-{resource.id}"]["operations"]}
        assert op_straddle.id in ids
        assert op_before.id not in ids

    def test_utilization_clipped_to_window(
        self, client, db, make_work_center, make_product
    ):
        wc = make_work_center(center_type="machine")
        resource = _make_machine_resource(db, wc.id)
        product = make_product()
        wo = _make_wo(db, product.id)

        start, end = _window()  # 24h window
        # 6h inside the window (2h of it spills past the end and is clipped)
        _make_op(
            db, wo.id, wc.id,
            resource_id=resource.id,
            start=end - timedelta(hours=4),
            end=end + timedelta(hours=2),
        )

        data = _board(client, start, end)
        lane = next(
            ln for ln in data["lanes"] if ln["key"] == f"resource-{resource.id}"
        )
        # 4 clipped hours / 24 = 16.7%
        assert lane["utilization_percent"] == 16.7

    def test_unscheduled_queue(self, client, db, make_work_center, make_product):
        wc = make_work_center(center_type="machine")
        product = make_product()
        wo = _make_wo(db, product.id, status="released")
        op1 = _make_op(db, wo.id, wc.id, status="pending", sequence=10)
        _make_op(db, wo.id, wc.id, status="pending", sequence=20)
        # Terminal op without schedule must NOT count
        _make_op(db, wo.id, wc.id, status="complete", sequence=30)

        start, end = _window()
        data = _board(client, start, end)

        entry = next(
            (
                u for u in data["unscheduled"]
                if u["production_order_id"] == wo.id
            ),
            None,
        )
        assert entry is not None
        assert entry["production_order_code"] == wo.code
        assert entry["unscheduled_operation_count"] == 2
        assert entry["first_unscheduled_operation"]["id"] == op1.id

    def test_draft_orders_not_in_unscheduled_queue(
        self, client, db, make_work_center, make_product
    ):
        wc = make_work_center(center_type="machine")
        product = make_product()
        wo = _make_wo(db, product.id, status="draft")
        _make_op(db, wo.id, wc.id, status="pending")

        start, end = _window()
        data = _board(client, start, end)
        ids = {u["production_order_id"] for u in data["unscheduled"]}
        assert wo.id not in ids
