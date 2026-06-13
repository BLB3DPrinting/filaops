"""
API tests for SCHED-7 — /api/v1/maintenance-windows + scheduler board windows.

Covers:
- POST create (201), validation (400 on overlap / bad machine selector)
- GET list with machine filter
- POST /{id}/cancel and /{id}/complete (MaintenanceLog linked)
- GET /scheduling/board includes per-lane windows
- auth required (401 unauthenticated)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.printer import Printer


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _make_printer(db, *, status: str = "idle") -> Printer:
    uid = _uid()
    p = Printer(
        code=f"PRT-{uid}",
        name=f"Printer {uid}",
        model="X1C",
        brand="bambulab",
        status=status,
        active=True,
    )
    db.add(p)
    db.flush()
    return p


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class TestMaintenanceWindowEndpoints:
    def test_create_and_list(self, client, db):
        printer = _make_printer(db)
        start = _now() + timedelta(days=1)
        end = start + timedelta(hours=2)

        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(start),
                "ends_at": _iso(end),
                "reason": "PM service",
            },
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["printer_id"] == printer.id
        assert body["resource_id"] is None
        assert body["status"] == "scheduled"
        assert body["reason"] == "PM service"
        window_id = body["id"]

        res = client.get(f"/api/v1/maintenance-windows?printer_id={printer.id}")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert data["items"][0]["id"] == window_id

    def test_create_rejects_overlap(self, client, db):
        printer = _make_printer(db)
        start = _now() + timedelta(days=1)
        end = start + timedelta(hours=2)
        payload = {
            "printer_id": printer.id,
            "starts_at": _iso(start),
            "ends_at": _iso(end),
        }
        assert client.post("/api/v1/maintenance-windows", json=payload).status_code == 201

        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(start + timedelta(minutes=30)),
                "ends_at": _iso(end + timedelta(hours=1)),
            },
        )
        assert res.status_code == 400
        assert "Overlaps" in res.json()["detail"]

    def test_create_rejects_missing_machine(self, client):
        start = _now() + timedelta(days=1)
        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "starts_at": _iso(start),
                "ends_at": _iso(start + timedelta(hours=1)),
            },
        )
        assert res.status_code == 400
        assert "Exactly one" in res.json()["detail"]

    def test_cancel_window(self, client, db):
        printer = _make_printer(db)
        start = _now() + timedelta(days=1)
        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(start),
                "ends_at": _iso(start + timedelta(hours=1)),
            },
        )
        window_id = res.json()["id"]

        res = client.post(f"/api/v1/maintenance-windows/{window_id}/cancel")
        assert res.status_code == 200
        assert res.json()["status"] == "cancelled"

        # Cancelling again → 400
        res = client.post(f"/api/v1/maintenance-windows/{window_id}/cancel")
        assert res.status_code == 400

    def test_cancel_unknown_window_404(self, client):
        res = client.post("/api/v1/maintenance-windows/99999999/cancel")
        assert res.status_code == 404

    def test_complete_window_links_log(self, client, db):
        printer = _make_printer(db)
        start = _now() - timedelta(hours=1)
        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(start),
                "ends_at": _iso(start + timedelta(hours=2)),
                "reason": "Lube rails",
            },
        )
        window_id = res.json()["id"]
        next_due = _now() + timedelta(days=60)

        res = client.post(
            f"/api/v1/maintenance-windows/{window_id}/complete",
            json={
                "maintenance_type": "routine",
                "next_due_at": _iso(next_due),
                "notes": "done",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "completed"
        assert body["maintenance_log_id"] is not None

        # The linked log is reachable via the existing maintenance endpoint
        res = client.get(f"/api/v1/maintenance/{body['maintenance_log_id']}")
        assert res.status_code == 200
        log = res.json()
        assert log["printer_id"] == printer.id
        assert log["description"] == "Lube rails"

    def test_requires_auth(self, unauthed_client):
        res = unauthed_client.get("/api/v1/maintenance-windows")
        assert res.status_code in (401, 403)


class TestSchedulerBoardWindows:
    def test_board_includes_lane_windows(self, client, db):
        printer = _make_printer(db)
        start = _now() + timedelta(hours=2)
        end = start + timedelta(hours=2)
        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(start),
                "ends_at": _iso(end),
                "reason": "Nozzle swap",
            },
        )
        assert res.status_code == 201
        window_id = res.json()["id"]

        window_start = _now() - timedelta(hours=1)
        window_end = _now() + timedelta(hours=24)
        res = client.get(
            "/api/v1/scheduling/board",
            params={
                "start_date": _iso(window_start),
                "end_date": _iso(window_end),
            },
        )
        assert res.status_code == 200, res.text
        board = res.json()

        lane = next(
            (x for x in board["lanes"] if x["key"] == f"printer-{printer.id}"), None
        )
        assert lane is not None, "printer lane missing from board"
        assert "windows" in lane
        ids = [w["id"] for w in lane["windows"]]
        assert window_id in ids
        block = next(w for w in lane["windows"] if w["id"] == window_id)
        assert block["reason"] == "Nozzle swap"
        assert block["status"] == "scheduled"
        assert set(block.keys()) == {"id", "starts_at", "ends_at", "reason", "status"}

    def test_board_excludes_out_of_range_windows(self, client, db):
        printer = _make_printer(db)
        far = _now() + timedelta(days=30)
        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(far),
                "ends_at": _iso(far + timedelta(hours=1)),
            },
        )
        assert res.status_code == 201

        res = client.get(
            "/api/v1/scheduling/board",
            params={
                "start_date": _iso(_now()),
                "end_date": _iso(_now() + timedelta(days=1)),
            },
        )
        assert res.status_code == 200
        lane = next(
            (x for x in res.json()["lanes"] if x["key"] == f"printer-{printer.id}"),
            None,
        )
        assert lane is not None
        assert lane["windows"] == []

    def test_board_excludes_completed_and_cancelled_windows(self, client, db):
        """CR #733: a window completed EARLY must release its lane
        immediately — only blocking (scheduled/in_progress) windows render
        on the board; completed/cancelled are history."""
        printer = _make_printer(db)
        # Active window, completed early (well before its scheduled ends_at)
        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(_now() - timedelta(hours=1)),
                "ends_at": _iso(_now() + timedelta(hours=6)),
            },
        )
        assert res.status_code == 201
        completed_id = res.json()["id"]
        assert (
            client.post(
                f"/api/v1/maintenance-windows/{completed_id}/complete", json={}
            ).status_code
            == 200
        )

        # Future window, cancelled
        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(_now() + timedelta(hours=8)),
                "ends_at": _iso(_now() + timedelta(hours=9)),
            },
        )
        cancelled_id = res.json()["id"]
        assert (
            client.post(
                f"/api/v1/maintenance-windows/{cancelled_id}/cancel"
            ).status_code
            == 200
        )

        res = client.get(
            "/api/v1/scheduling/board",
            params={
                "start_date": _iso(_now() - timedelta(hours=2)),
                "end_date": _iso(_now() + timedelta(hours=12)),
            },
        )
        assert res.status_code == 200
        lane = next(
            (x for x in res.json()["lanes"] if x["key"] == f"printer-{printer.id}"),
            None,
        )
        assert lane is not None
        assert lane["windows"] == []

    def test_board_sync_flips_printer_status(self, client, db):
        """Lazy seam: hitting the board flips a printer inside an active window."""
        printer = _make_printer(db, status="idle")
        res = client.post(
            "/api/v1/maintenance-windows",
            json={
                "printer_id": printer.id,
                "starts_at": _iso(_now() - timedelta(minutes=10)),
                "ends_at": _iso(_now() + timedelta(hours=1)),
            },
        )
        assert res.status_code == 201

        res = client.get(
            "/api/v1/scheduling/board",
            params={
                "start_date": _iso(_now() - timedelta(hours=1)),
                "end_date": _iso(_now() + timedelta(hours=12)),
            },
        )
        assert res.status_code == 200
        lane = next(
            (x for x in res.json()["lanes"] if x["key"] == f"printer-{printer.id}"),
            None,
        )
        assert lane is not None
        assert lane["status"] == "maintenance"
        assert lane["windows"][0]["status"] == "in_progress"
