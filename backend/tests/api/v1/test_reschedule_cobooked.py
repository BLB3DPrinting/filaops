"""
Rescheduling ONE member of a co-booked block (print batches, S3/S4).

Operations booked into one window on one machine
(``resource_scheduling.schedule_operations_together``) are one plate run.
Editing a single member must not see its block siblings as conflicts when
the member keeps the block's slot, but moving it anywhere else is a real
move of that one member:

- unchanged slot            -> success, nothing moves
- different free window     -> success, siblings stay put (un-co-books it)
- overlaps the block partly -> a genuine conflict with the siblings
- an unrelated operation    -> still a conflict, and a client-sent id list
                               can never hide it (the server derives the
                               sibling set from the stored window)

POST /api/v1/production-orders/{id}/operations/{op_id}/reschedule
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.manufacturing import Routing, RoutingOperation
from app.models.printer import Printer
from app.models.production_order import ProductionOrderOperation
from app.services.resource_scheduling import schedule_operations_together

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
        active=True,
    )
    db.add(printer)
    db.flush()
    return printer


def _make_operation(db, production_order_id, work_center_id, **kwargs):
    operation = ProductionOrderOperation(
        production_order_id=production_order_id,
        work_center_id=work_center_id,
        sequence=kwargs.pop("sequence", 10),
        operation_code=kwargs.pop("operation_code", "PRINT"),
        operation_name=kwargs.pop("operation_name", "Print"),
        planned_run_minutes=kwargs.pop("planned_run_minutes", 60),
        status=kwargs.pop("status", "queued"),
        **kwargs,
    )
    db.add(operation)
    db.flush()
    return operation


def _book_block(db, make_product, make_production_order, work_center_id, printer, start, end, count):
    """``count`` queued ops, each on its own PO, sharing one window on one printer.

    Returns ``[(production_order, operation), ...]``.
    """
    product = make_product()
    members = []
    for _ in range(count):
        po = make_production_order(product_id=product.id)
        op = _make_operation(
            db, po.id, work_center_id,
            printer_id=printer.id,
            scheduled_start=start,
            scheduled_end=end,
        )
        members.append((po, op))
    return members


def _reschedule(client, po, op, **body):
    return client.post(f"{BASE_URL}/{po.id}/operations/{op.id}/reschedule", json=body)


def _window(op):
    return (op.scheduled_start, op.scheduled_end)


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


@pytest.fixture
def start():
    # Whole seconds: the happy-path windows are exactly representable in JSON.
    return (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)


class TestUnchangedSlotOfACobookedMember:
    @pytest.mark.parametrize("siblings", [2, 3])
    def test_saving_the_unchanged_slot_succeeds(
        self, client, db, make_product, make_production_order, make_work_center,
        start, siblings,
    ):
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        end = start + timedelta(hours=3)
        members = _book_block(
            db, make_product, make_production_order, wc.id, printer, start, end, siblings + 1,
        )
        db.commit()
        (po, op) = members[0]
        before = {m.id: _window(m) for _, m in members}

        resp = _reschedule(
            client, po, op,
            resource_id=printer.id, is_printer=True,
            scheduled_start=start.isoformat(), scheduled_end=end.isoformat(),
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True, data
        # Nothing moved: the whole block still shares its window and printer
        db.expire_all()
        for _, member in members:
            refreshed = db.get(ProductionOrderOperation, member.id)
            assert _window(refreshed) == before[member.id]
            assert refreshed.printer_id == printer.id
            assert refreshed.status == "queued"

    def test_a_minute_truncated_save_of_a_sub_minute_block_keeps_the_block_intact(
        self, client, db, make_product, make_production_order, make_work_center,
    ):
        """The scheduler modal works in whole minutes and a browser round trip
        cannot reproduce microseconds, so a block booked at 10:00:37.5 comes
        back as 10:00:00. That is still a request for the block's own slot:
        it must succeed and write the block's exact window, not shift the
        member out of step with its siblings."""
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        start = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(second=37, microsecond=500000)
        end = start + timedelta(hours=3)
        members = _book_block(
            db, make_product, make_production_order, wc.id, printer, start, end, 3,
        )
        db.commit()
        (po, op) = members[0]
        stored = (_naive(start), _naive(end))

        resp = _reschedule(
            client, po, op,
            resource_id=printer.id, is_printer=True,
            scheduled_start=start.replace(second=0, microsecond=0).isoformat(),
            scheduled_end=end.replace(second=0, microsecond=0).isoformat(),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True, resp.json()
        db.expire_all()
        for _, member in members:
            assert _window(db.get(ProductionOrderOperation, member.id)) == stored


class TestTwoOperationsOfOneOrderInTheSameBlock:
    """A block can hold two operations of ONE production order when the later
    one's routing allows overlap (S3). They share the block's window by
    design, so neither the predecessor nor the successor sequence check may
    treat that shared window as a violation when the block's own slot is
    saved unchanged."""

    @staticmethod
    def _overlapping_pair(db, make_product, make_production_order, make_work_center, start, end):
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        product = make_product()
        routing = Routing(
            product_id=product.id, code=f"RTG-{_uid()}", name="Overlap routing",
            is_active=True, version=1,
        )
        db.add(routing)
        db.flush()
        routing_op = RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id, sequence=20,
            operation_code="PRINT", operation_name="Print",
            run_time_minutes=Decimal("60"), setup_time_minutes=Decimal("0"),
            can_overlap=True,
        )
        db.add(routing_op)
        db.flush()
        po = make_production_order(product_id=product.id)
        ops = [
            _make_operation(db, po.id, wc.id, sequence=10),
            _make_operation(db, po.id, wc.id, sequence=20, routing_operation_id=routing_op.id),
        ]
        success, conflicts = schedule_operations_together(
            db, ops, printer.id, start, end, is_printer=True,
        )
        assert (success, conflicts) == (True, [])
        return po, printer, ops

    @pytest.mark.parametrize("which", [0, 1], ids=["earlier-sequence", "later-sequence"])
    def test_saving_the_unchanged_slot_succeeds(
        self, client, db, make_product, make_production_order, make_work_center, start, which,
    ):
        end = start + timedelta(hours=3)
        po, printer, ops = self._overlapping_pair(
            db, make_product, make_production_order, make_work_center, start, end,
        )
        db.commit()

        resp = _reschedule(
            client, po, ops[which],
            resource_id=printer.id, is_printer=True,
            scheduled_start=start.isoformat(), scheduled_end=end.isoformat(),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True, resp.json()
        db.expire_all()
        for op in ops:
            assert _window(db.get(ProductionOrderOperation, op.id)) == (_naive(start), _naive(end))

    def test_moving_the_earlier_one_past_the_later_one_still_violates_the_sequence(
        self, client, db, make_product, make_production_order, make_work_center, start,
    ):
        end = start + timedelta(hours=3)
        po, printer, ops = self._overlapping_pair(
            db, make_product, make_production_order, make_work_center, start, end,
        )
        db.commit()

        resp = _reschedule(
            client, po, ops[0],
            resource_id=printer.id, is_printer=True,
            scheduled_start=(end + timedelta(hours=1)).isoformat(),
            scheduled_end=(end + timedelta(hours=4)).isoformat(),
        )

        data = resp.json()
        assert data["success"] is False
        assert data["conflict_type"] == "successor"


class TestMovingOneMemberOfACobookedBlock:
    def test_move_to_a_free_window_leaves_the_siblings_in_place(
        self, client, db, make_product, make_production_order, make_work_center, start,
    ):
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        end = start + timedelta(hours=3)
        members = _book_block(
            db, make_product, make_production_order, wc.id, printer, start, end, 3,
        )
        db.commit()
        (po, moved) = members[0]
        siblings = [m for _, m in members[1:]]

        new_start = end + timedelta(hours=1)
        new_end = new_start + timedelta(hours=3)
        resp = _reschedule(
            client, po, moved,
            resource_id=printer.id, is_printer=True,
            scheduled_start=new_start.isoformat(), scheduled_end=new_end.isoformat(),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True, resp.json()
        db.expire_all()
        moved = db.get(ProductionOrderOperation, moved.id)
        assert _window(moved) == (_naive(new_start), _naive(new_end))
        for sibling in siblings:
            sibling = db.get(ProductionOrderOperation, sibling.id)
            assert _window(sibling) == (_naive(start), _naive(end))
            assert sibling.printer_id == printer.id

    def test_move_to_another_printer_at_the_same_time_leaves_the_siblings_in_place(
        self, client, db, make_product, make_production_order, make_work_center, start,
    ):
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        other_printer = _make_printer(db, wc.id)
        end = start + timedelta(hours=3)
        members = _book_block(
            db, make_product, make_production_order, wc.id, printer, start, end, 3,
        )
        db.commit()
        (po, moved) = members[0]

        resp = _reschedule(
            client, po, moved,
            resource_id=other_printer.id, is_printer=True,
            scheduled_start=start.isoformat(), scheduled_end=end.isoformat(),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["success"] is True, resp.json()
        db.expire_all()
        assert db.get(ProductionOrderOperation, moved.id).printer_id == other_printer.id
        for _, sibling in members[1:]:
            assert db.get(ProductionOrderOperation, sibling.id).printer_id == printer.id

    @pytest.mark.parametrize(
        "shift, longer",
        [
            (timedelta(minutes=30), timedelta(0)),   # slides over the block
            (timedelta(0), timedelta(minutes=30)),   # same start, runs longer
            (timedelta(minutes=-30), timedelta(0)),  # slides in from before
        ],
        ids=["shifted-later", "same-start-longer", "shifted-earlier"],
    )
    def test_a_window_overlapping_the_block_partly_conflicts_with_the_siblings(
        self, client, db, make_product, make_production_order, make_work_center,
        start, shift, longer,
    ):
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        end = start + timedelta(hours=3)
        members = _book_block(
            db, make_product, make_production_order, wc.id, printer, start, end, 3,
        )
        db.commit()
        (po, moved) = members[0]
        sibling_ids = {m.id for _, m in members[1:]}

        resp = _reschedule(
            client, po, moved,
            resource_id=printer.id, is_printer=True,
            scheduled_start=(start + shift).isoformat(),
            scheduled_end=(end + shift + longer).isoformat(),
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is False
        assert data["conflict_type"] == "resource"
        # The member itself is never reported; its siblings genuinely are
        assert {c["operation_id"] for c in data["conflicts"]} == sibling_ids
        db.expire_all()
        assert _window(db.get(ProductionOrderOperation, moved.id)) == (_naive(start), _naive(end))


class TestUnrelatedOperationsStillConflict:
    def test_moving_into_an_unrelated_operations_window_fails(
        self, client, db, make_product, make_production_order, make_work_center, start,
    ):
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        end = start + timedelta(hours=3)
        members = _book_block(
            db, make_product, make_production_order, wc.id, printer, start, end, 3,
        )
        stranger_po = make_production_order(product_id=make_product().id)
        busy_start = end + timedelta(hours=2)
        stranger = _make_operation(
            db, stranger_po.id, wc.id,
            printer_id=printer.id,
            scheduled_start=busy_start,
            scheduled_end=busy_start + timedelta(hours=2),
        )
        db.commit()
        (po, moved) = members[0]

        resp = _reschedule(
            client, po, moved,
            resource_id=printer.id, is_printer=True,
            scheduled_start=busy_start.isoformat(),
            scheduled_end=(busy_start + timedelta(hours=2)).isoformat(),
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is False
        assert data["conflict_type"] == "resource"
        assert [c["operation_id"] for c in data["conflicts"]] == [stranger.id]

    def test_the_unchanged_slot_still_conflicts_with_an_unrelated_double_booking(
        self, client, db, make_product, make_production_order, make_work_center, start,
    ):
        """Only the member's own block is waved through: an unrelated
        operation that overlaps the block's window is still a conflict."""
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        end = start + timedelta(hours=3)
        members = _book_block(
            db, make_product, make_production_order, wc.id, printer, start, end, 3,
        )
        stranger_po = make_production_order(product_id=make_product().id)
        stranger = _make_operation(
            db, stranger_po.id, wc.id,
            printer_id=printer.id,
            scheduled_start=start + timedelta(hours=1),
            scheduled_end=end + timedelta(hours=1),
        )
        db.commit()
        (po, op) = members[0]

        resp = _reschedule(
            client, po, op,
            resource_id=printer.id, is_printer=True,
            scheduled_start=start.isoformat(), scheduled_end=end.isoformat(),
        )

        data = resp.json()
        assert data["success"] is False
        assert [c["operation_id"] for c in data["conflicts"]] == [stranger.id]

    @pytest.mark.parametrize(
        "extra_field, as_list",
        [("exclude_operation_ids", True), ("exclude_operation_id", False), ("sibling_ids", True)],
    )
    def test_a_client_cannot_exclude_an_unrelated_operation_by_id(
        self, client, db, make_product, make_production_order, make_work_center,
        start, extra_field, as_list,
    ):
        wc = make_work_center()
        printer = _make_printer(db, wc.id)
        end = start + timedelta(hours=3)
        members = _book_block(
            db, make_product, make_production_order, wc.id, printer, start, end, 2,
        )
        stranger_po = make_production_order(product_id=make_product().id)
        busy_start = end + timedelta(hours=2)
        stranger = _make_operation(
            db, stranger_po.id, wc.id,
            printer_id=printer.id,
            scheduled_start=busy_start,
            scheduled_end=busy_start + timedelta(hours=2),
        )
        db.commit()
        (po, moved) = members[0]
        claimed = [stranger.id] if as_list else stranger.id

        resp = _reschedule(
            client, po, moved,
            resource_id=printer.id, is_printer=True,
            scheduled_start=busy_start.isoformat(),
            scheduled_end=(busy_start + timedelta(hours=2)).isoformat(),
            **{extra_field: claimed},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is False
        assert [c["operation_id"] for c in data["conflicts"]] == [stranger.id]
        db.expire_all()
        assert _window(db.get(ProductionOrderOperation, moved.id)) == (_naive(start), _naive(end))
