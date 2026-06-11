"""
Tests for SCHED-2: reschedule and unschedule operation endpoints.

POST /api/v1/production-orders/{id}/operations/{op_id}/reschedule
POST /api/v1/production-orders/{id}/operations/{op_id}/unschedule

Coverage:
- reschedule validates conflicts excluding self
- predecessor violation surfaces with earliest_valid_start
- successor violation surfaces with per-successor earliest_valid_start
- unschedule only works for pre-start statuses
- audit notes written on both actions
- endpoints require authentication (401 when not logged in)
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.printer import Printer
from app.models.production_order import ProductionOrderOperation

BASE_URL = "/api/v1/production-orders"


def _uid():
    return uuid.uuid4().hex[:6]


def _make_printer(db, work_center_id, status="idle"):
    uid = _uid()
    printer = Printer(
        code=f"PRT-{uid}",
        name=f"Test Printer {uid}",
        model="X1C",
        brand="bambulab",
        work_center_id=work_center_id,
        status=status,
        active=True,
    )
    db.add(printer)
    db.flush()
    return printer


def _make_operation(db, production_order_id, work_center_id, sequence=10, status="pending", **kwargs):
    operation = ProductionOrderOperation(
        production_order_id=production_order_id,
        work_center_id=work_center_id,
        sequence=sequence,
        operation_code=kwargs.pop("operation_code", f"OP-{sequence}"),
        operation_name=kwargs.pop("operation_name", f"Op-{sequence}"),
        planned_run_minutes=kwargs.pop("planned_run_minutes", 60),
        status=status,
        **kwargs,
    )
    db.add(operation)
    db.flush()
    return operation


# ---------------------------------------------------------------------------
# Authentication guard
# ---------------------------------------------------------------------------

class TestRescheduleAuth:
    def test_reschedule_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/1/operations/1/reschedule",
            json={"scheduled_start": datetime.now(timezone.utc).isoformat()},
        )
        assert resp.status_code == 401

    def test_unschedule_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/1/operations/1/unschedule")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Reschedule — happy path
# ---------------------------------------------------------------------------

class TestRescheduleHappy:
    def test_reschedule_move_to_new_start(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Rescheduling an already-queued op to a new start time succeeds."""
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        op = _make_operation(
            db, po.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        db.commit()

        new_start = now + timedelta(hours=4)
        resp = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/reschedule",
            json={
                "resource_id": printer.id,
                "is_printer": True,
                "scheduled_start": new_start.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["operation_id"] == op.id
        assert "scheduled_start" in data

    def test_reschedule_writes_audit_note(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Rescheduling appends a timestamped note to production order notes."""
        from app.models.production_order import ProductionOrder

        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        op = _make_operation(
            db, po.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        db.commit()

        new_start = now + timedelta(hours=6)
        resp = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/reschedule",
            json={
                "resource_id": printer.id,
                "is_printer": True,
                "scheduled_start": new_start.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text

        db.expire_all()
        refreshed_po = db.get(ProductionOrder, po.id)
        assert refreshed_po.notes is not None
        assert "rescheduled" in refreshed_po.notes.lower()


# ---------------------------------------------------------------------------
# Reschedule — conflict: excludes self
# ---------------------------------------------------------------------------

class TestRescheduleExcludesSelf:
    def test_rescheduling_to_same_slot_does_not_self_conflict(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """
        Rescheduling op to the same time slot on the same printer must not
        report a conflict with itself.  (exclude_operation_id must be passed.)
        """
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        op = _make_operation(
            db, po.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        db.commit()

        # "Reschedule" to the same slot — should succeed (no self-conflict)
        resp = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/reschedule",
            json={
                "resource_id": printer.id,
                "is_printer": True,
                "scheduled_start": now.isoformat(),
                "scheduled_end": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

    def test_reschedule_into_another_ops_slot_returns_conflict(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """
        Moving op into a slot occupied by a DIFFERENT op on the same printer
        must return success=False with conflict_type="resource".
        """
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        po2 = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        # op1 on printer, scheduled 1h from now
        op1 = _make_operation(
            db, po.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer.id,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=2),
        )

        # op2 on po2 — initially pending
        op2 = _make_operation(
            db, po2.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        db.commit()

        # Try to move op2 into op1's slot
        resp = client.post(
            f"{BASE_URL}/{po2.id}/operations/{op2.id}/reschedule",
            json={
                "resource_id": printer.id,
                "is_printer": True,
                "scheduled_start": (now + timedelta(hours=1)).isoformat(),
                "scheduled_end": (now + timedelta(hours=2)).isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is False
        assert data["conflict_type"] == "resource"
        assert len(data["conflicts"]) > 0
        assert data["conflicts"][0]["operation_id"] == op1.id


# ---------------------------------------------------------------------------
# Reschedule — predecessor violation
# ---------------------------------------------------------------------------

class TestReschedulePredecessorViolation:
    def test_predecessor_violation_returns_earliest_valid_start(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """
        Rescheduling OP020 to start before OP010 ends returns conflict_type=predecessor
        and earliest_valid_start >= pred scheduled_end.
        """
        wc = make_work_center()
        printer_a = _make_printer(db, wc.id)
        printer_b = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        pred_end = now + timedelta(hours=3)

        # OP010 — predecessor, scheduled on printer_a
        _make_operation(
            db, po.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer_a.id,
            scheduled_start=now,
            scheduled_end=pred_end,
        )

        # OP020 — needs to start BEFORE pred_end → predecessor violation
        op2 = _make_operation(
            db, po.id, wc.id,
            sequence=20, status="queued",
            printer_id=printer_b.id,
            scheduled_start=pred_end,
            scheduled_end=pred_end + timedelta(hours=1),
        )
        db.commit()

        # Try to move OP020 to start 1h from now (before pred ends at +3h)
        too_early = now + timedelta(hours=1)
        resp = client.post(
            f"{BASE_URL}/{po.id}/operations/{op2.id}/reschedule",
            json={
                "resource_id": printer_b.id,
                "is_printer": True,
                "scheduled_start": too_early.isoformat(),
                "scheduled_end": (too_early + timedelta(hours=1)).isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is False
        assert data["conflict_type"] == "predecessor"
        # earliest_valid_start is present and >= pred_end
        assert data["earliest_valid_start"] is not None
        evs = datetime.fromisoformat(data["earliest_valid_start"])
        if evs.tzinfo is None:
            evs = evs.replace(tzinfo=timezone.utc)
        assert evs >= pred_end


# ---------------------------------------------------------------------------
# Reschedule — successor violation
# ---------------------------------------------------------------------------

class TestRescheduleSuccessorViolation:
    def test_successor_violation_surfaces_with_earliest_valid_start(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """
        Moving OP010 later so it now overlaps OP020's existing scheduled_start
        returns conflict_type=successor with per-successor earliest_valid_start.
        """
        wc = make_work_center()
        printer_a = _make_printer(db, wc.id)
        printer_b = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        # OP010 — currently scheduled 0→1h on printer_a
        op1 = _make_operation(
            db, po.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer_a.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )

        # OP020 — successor, scheduled 1h→2h on printer_b
        op2 = _make_operation(
            db, po.id, wc.id,
            sequence=20, status="queued",
            printer_id=printer_b.id,
            scheduled_start=now + timedelta(hours=1),
            scheduled_end=now + timedelta(hours=2),
        )
        db.commit()

        # Try to move OP010 to 0.5h→1.5h — its new end (1.5h) > OP020 start (1h)
        new_start = now + timedelta(minutes=30)
        new_end = now + timedelta(hours=1, minutes=30)
        resp = client.post(
            f"{BASE_URL}/{po.id}/operations/{op1.id}/reschedule",
            json={
                "resource_id": printer_a.id,
                "is_printer": True,
                "scheduled_start": new_start.isoformat(),
                "scheduled_end": new_end.isoformat(),
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is False
        assert data["conflict_type"] == "successor"
        assert len(data["successor_conflicts"]) > 0
        sc = data["successor_conflicts"][0]
        assert sc["operation_id"] == op2.id
        # earliest_valid_start for the successor == our proposed new_end
        assert sc["earliest_valid_start"] is not None
        evs = datetime.fromisoformat(sc["earliest_valid_start"])
        if evs.tzinfo is None:
            evs = evs.replace(tzinfo=timezone.utc)
        assert evs == new_end


# ---------------------------------------------------------------------------
# Unschedule — happy path
# ---------------------------------------------------------------------------

class TestUnscheduleHappy:
    def test_unschedule_queued_op_returns_to_pending(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Unscheduling a queued op clears times + resource and returns to pending."""
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        op = _make_operation(
            db, po.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        db.commit()

        resp = client.post(f"{BASE_URL}/{po.id}/operations/{op.id}/unschedule")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True

        db.expire_all()
        db.refresh(op)
        assert op.status == "pending"
        assert op.scheduled_start is None
        assert op.scheduled_end is None
        assert op.printer_id is None
        assert op.resource_id is None

    def test_unschedule_pending_op_succeeds(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Unscheduling a pending (already unscheduled) op also succeeds."""
        wc = make_work_center()
        po = make_production_order(product_id=make_product().id)

        op = _make_operation(db, po.id, wc.id, sequence=10, status="pending")
        db.commit()

        resp = client.post(f"{BASE_URL}/{po.id}/operations/{op.id}/unschedule")
        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True

    def test_unschedule_writes_audit_note(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        """Unscheduling appends a timestamped note to production order notes."""
        from app.models.production_order import ProductionOrder

        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        op = _make_operation(
            db, po.id, wc.id,
            sequence=10, status="queued",
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        db.commit()

        resp = client.post(f"{BASE_URL}/{po.id}/operations/{op.id}/unschedule")
        assert resp.status_code == 200, resp.text

        db.expire_all()
        refreshed_po = db.get(ProductionOrder, po.id)
        assert refreshed_po.notes is not None
        assert "unscheduled" in refreshed_po.notes.lower()


# ---------------------------------------------------------------------------
# Unschedule — blocked on started / finished ops
# ---------------------------------------------------------------------------

class TestUnschedulePreStartOnly:
    @pytest.mark.parametrize("bad_status", ["running", "complete", "cancelled", "skipped"])
    def test_unschedule_blocks_non_pre_start_statuses(
        self, client, db, make_product, make_production_order, make_work_center, bad_status
    ):
        """Unschedule must be rejected for ops that have started or finished."""
        wc = make_work_center()
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        op = _make_operation(
            db, po.id, wc.id,
            sequence=10, status=bad_status,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        db.commit()

        resp = client.post(f"{BASE_URL}/{po.id}/operations/{op.id}/unschedule")
        assert resp.status_code == 400, f"Expected 400 for status={bad_status}, got {resp.status_code}"

    @pytest.mark.parametrize("bad_status", ["running", "complete", "cancelled", "skipped"])
    def test_reschedule_blocks_non_pre_start_statuses(
        self, client, db, make_product, make_production_order, make_work_center, bad_status
    ):
        """Reschedule must also be rejected for ops that have started or finished."""
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        po = make_production_order(product_id=make_product().id)
        now = datetime.now(timezone.utc).replace(microsecond=0)

        op = _make_operation(
            db, po.id, wc.id,
            sequence=10, status=bad_status,
            printer_id=printer.id,
            scheduled_start=now,
            scheduled_end=now + timedelta(hours=1),
        )
        db.commit()

        new_start = now + timedelta(hours=4)
        resp = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/reschedule",
            json={
                "resource_id": printer.id,
                "is_printer": True,
                "scheduled_start": new_start.isoformat(),
            },
        )
        assert resp.status_code == 400, f"Expected 400 for status={bad_status}, got {resp.status_code}"


# ---------------------------------------------------------------------------
# Not found guards
# ---------------------------------------------------------------------------

class TestRescheduleNotFound:
    def test_reschedule_unknown_po(self, client):
        resp = client.post(
            f"{BASE_URL}/999999/operations/1/reschedule",
            json={"scheduled_start": datetime.now(timezone.utc).isoformat()},
        )
        assert resp.status_code == 404

    def test_unschedule_unknown_po(self, client):
        resp = client.post(f"{BASE_URL}/999999/operations/1/unschedule")
        assert resp.status_code == 404
