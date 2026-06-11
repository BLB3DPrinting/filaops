"""
API-level tests for the dispatch endpoints.  SCHED-1.

Covers:
- GET /api/v1/dispatch/suggestions returns 401 for unauthenticated requests
- GET /api/v1/dispatch/suggestions returns 200 for authenticated staff
- POST /api/v1/dispatch/assign returns 401 for unauthenticated requests
- POST /api/v1/dispatch/assign happy-path assigns operation (200)
- POST /api/v1/dispatch/assign 400 for maintenance-status printer
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.printer import Printer
from app.models.production_order import ProductionOrder, ProductionOrderOperation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _make_printer(db, *, status: str = "idle", work_center_id=None) -> Printer:
    p = Printer(
        code=f"PRT-{_uid()}",
        name=f"Printer {_uid()}",
        model="X1C",
        brand="bambulab",
        status=status,
        active=True,
        work_center_id=work_center_id,
    )
    db.add(p)
    db.flush()
    return p


def _make_wo(db, product_id: int, status: str = "released") -> ProductionOrder:
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


def _make_op(db, wo_id: int, work_center_id: int) -> ProductionOrderOperation:
    op = ProductionOrderOperation(
        production_order_id=wo_id,
        work_center_id=work_center_id,
        sequence=10,
        operation_code=f"OP-{_uid()}",
        operation_name="Print",
        planned_setup_minutes=Decimal("0"),
        planned_run_minutes=Decimal("60"),
        status="pending",
    )
    db.add(op)
    db.flush()
    return op


# ---------------------------------------------------------------------------
# GET /api/v1/dispatch/suggestions
# ---------------------------------------------------------------------------


class TestDispatchSuggestionsEndpoint:

    def test_unauthenticated_returns_401(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/dispatch/suggestions")
        assert resp.status_code == 401

    def test_authenticated_returns_200(self, client):
        resp = client.get("/api/v1/dispatch/suggestions")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        assert "generated_at" in data

    def test_with_printer_id_filter(self, client, db, make_product, make_work_center):
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id)

        resp = client.get(f"/api/v1/dispatch/suggestions?printer_id={printer.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert "results" in data
        # Should only have results for this specific printer (or empty)
        for result in data["results"]:
            assert result["printer"]["id"] == printer.id

    def test_suggestions_response_shape(self, client, db, make_product, make_work_center):
        """Response has expected schema fields."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id)
        _make_op(db, wo.id, wc.id)

        resp = client.get(f"/api/v1/dispatch/suggestions?printer_id={printer.id}")
        assert resp.status_code == 200
        data = resp.json()

        assert len(data["results"]) >= 1
        result = next(r for r in data["results"] if r["printer"]["id"] == printer.id)

        # Shape checks
        assert "printer" in result
        assert "top_suggestion" in result
        assert "runners_up" in result

        if result["top_suggestion"] is not None:
            ts = result["top_suggestion"]
            assert "production_order_code" in ts
            assert "product_name" in ts
            assert "operation_id" in ts
            assert "priority" in ts
            assert "why" in ts
            assert isinstance(ts["why"], list)
            assert "estimated_duration_minutes" in ts


# ---------------------------------------------------------------------------
# POST /api/v1/dispatch/assign
# ---------------------------------------------------------------------------


class TestDispatchAssignEndpoint:

    def test_unauthenticated_returns_401(self, unauthed_client):
        resp = unauthed_client.post(
            "/api/v1/dispatch/assign",
            json={"operation_id": 1, "printer_id": 1},
        )
        assert resp.status_code == 401

    def test_assign_happy_path_returns_200(
        self, client, db, make_product, make_work_center
    ):
        """Successful assign returns 200 with scheduled times and queued status."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id, status="released")
        op = _make_op(db, wo.id, wc.id)

        resp = client.post(
            "/api/v1/dispatch/assign",
            json={"operation_id": op.id, "printer_id": printer.id},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["operation_id"] == op.id
        assert data["printer_id"] == printer.id
        assert data["printer_code"] == printer.code
        assert data["production_order_code"] == wo.code
        assert data["operation_status"] == "queued"
        assert "scheduled_start" in data
        assert "scheduled_end" in data

    def test_assign_maintenance_printer_returns_400(
        self, client, db, make_product, make_work_center
    ):
        """Assigning to a maintenance-status printer returns 400."""
        wc = make_work_center()
        product = make_product()
        maint_printer = _make_printer(db, status="maintenance", work_center_id=wc.id)

        wo = _make_wo(db, product.id, status="released")
        op = _make_op(db, wo.id, wc.id)

        resp = client.post(
            "/api/v1/dispatch/assign",
            json={"operation_id": op.id, "printer_id": maint_printer.id},
        )
        assert resp.status_code == 400
        assert "maintenance" in resp.json()["detail"].lower()

    def test_assign_nonexistent_operation_returns_400(
        self, client, db, make_work_center
    ):
        wc = make_work_center()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        resp = client.post(
            "/api/v1/dispatch/assign",
            json={"operation_id": 999_999, "printer_id": printer.id},
        )
        assert resp.status_code == 400

    def test_assign_draft_order_returns_400(
        self, client, db, make_product, make_work_center
    ):
        """Draft production orders cannot be dispatched."""
        wc = make_work_center()
        product = make_product()
        printer = _make_printer(db, status="idle", work_center_id=wc.id)

        wo = _make_wo(db, product.id, status="draft")
        op = _make_op(db, wo.id, wc.id)

        resp = client.post(
            "/api/v1/dispatch/assign",
            json={"operation_id": op.id, "printer_id": printer.id},
        )
        assert resp.status_code == 400
