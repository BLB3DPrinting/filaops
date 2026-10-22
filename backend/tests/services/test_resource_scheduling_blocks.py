"""
Editing ONE member of a co-booked block (print batches, S3/S4).

``resource_scheduling.find_block_siblings`` derives, from the operation's
STORED window, the operations booked into the same slot on the same machine.
``resolve_edit_slot`` decides which of them the conflict check may ignore
when that operation is edited, and ``schedule_operation`` uses it.

Semantics under test:

- keep the block's slot (to the minute)  -> siblings are not conflicts, and
  the exact stored window is what gets validated and written
- any other window / machine             -> a real move of that one member:
  siblings are conflicts wherever they overlap and are never touched
- an operation without a stored slot, or a solo operation, behaves exactly
  as before
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.manufacturing import Resource
from app.models.printer import Printer
from app.models.production_order import ProductionOrderOperation
from app.services.resource_scheduling import (
    check_successor_scheduling,
    find_block_siblings,
    resolve_edit_slot,
    schedule_operation,
    schedule_operations_together,
)


def _uid():
    return uuid.uuid4().hex[:6]


def _make_printer(db, work_center_id, **kwargs):
    uid = _uid()
    printer = Printer(
        code=f"PRT-{uid}",
        name=f"Test Printer {uid}",
        model="X1C",
        brand="bambulab",
        work_center_id=work_center_id,
        status="idle",
        **kwargs,
    )
    db.add(printer)
    db.flush()
    return printer


def _make_resource(db, work_center_id, **kwargs):
    uid = _uid()
    resource = Resource(
        work_center_id=work_center_id,
        code=f"RES-{uid}",
        name=f"Test Resource {uid}",
        status="available",
        **kwargs,
    )
    db.add(resource)
    db.flush()
    return resource


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


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


class _Block:
    """Three ops (own PO each) booked together on one printer."""

    def __init__(self, db, make_product, make_production_order, make_work_center, count=3):
        self.db = db
        self.wc = make_work_center()
        self.printer = _make_printer(db, self.wc.id)
        self.product = make_product()
        self.make_production_order = make_production_order
        self.start = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
        self.end = self.start + timedelta(hours=3)
        self.members = []
        for _ in range(count):
            wo = make_production_order(product_id=self.product.id)
            self.members.append(_make_operation(db, wo.id, self.wc.id))
        success, conflicts = schedule_operations_together(
            db, self.members, self.printer.id, self.start, self.end, is_printer=True,
        )
        assert (success, conflicts) == (True, [])

    @property
    def member(self):
        return self.members[0]

    @property
    def siblings(self):
        return self.members[1:]

    def make_other_op(self, **kwargs):
        wo = self.make_production_order(product_id=self.product.id)
        return _make_operation(self.db, wo.id, self.wc.id, **kwargs)


def _block(db, make_product, make_production_order, make_work_center, count=3):
    return _Block(db, make_product, make_production_order, make_work_center, count)


class TestFindBlockSiblings:
    def test_returns_the_other_members_of_the_block(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)

        siblings = find_block_siblings(db, b.member)

        assert {s.id for s in siblings} == {s.id for s in b.siblings}

    def test_a_solo_operation_has_no_siblings(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center, count=1)

        assert find_block_siblings(db, b.member) == []

    def test_an_unscheduled_operation_has_no_siblings(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        pending = b.make_other_op()

        assert find_block_siblings(db, pending) == []

    def test_terminal_operations_are_not_siblings(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        b.siblings[0].status = "complete"
        b.siblings[1].status = "cancelled"
        db.flush()

        assert find_block_siblings(db, b.member) == []

    def test_a_running_sibling_still_counts(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        b.siblings[0].status = "running"
        db.flush()

        assert {s.id for s in find_block_siblings(db, b.member)} == {s.id for s in b.siblings}

    def test_a_different_window_on_the_same_printer_is_not_a_sibling(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center, count=1)
        same_start = b.make_other_op(
            status="queued", printer_id=b.printer.id,
            scheduled_start=b.start, scheduled_end=b.end + timedelta(minutes=1),
        )
        same_end = b.make_other_op(
            status="queued", printer_id=b.printer.id,
            scheduled_start=b.start - timedelta(minutes=1), scheduled_end=b.end,
        )

        assert find_block_siblings(db, b.member) == []
        assert find_block_siblings(db, same_start) == []
        assert find_block_siblings(db, same_end) == []

    def test_the_same_window_on_another_printer_is_not_a_sibling(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center, count=1)
        other_printer = _make_printer(db, b.wc.id)
        b.make_other_op(
            status="queued", printer_id=other_printer.id,
            scheduled_start=b.start, scheduled_end=b.end,
        )

        assert find_block_siblings(db, b.member) == []

    def test_a_printer_and_a_resource_with_the_same_id_are_different_machines(
        self, db, make_product, make_production_order, make_work_center
    ):
        """Printers and Resources have separate id spaces: printer 9 and
        resource 9 in one window are two machines, not one block."""
        wc = make_work_center()
        forced_id = 900_000 + int(_uid(), 16) % 90_000
        printer = _make_printer(db, wc.id, id=forced_id)
        resource = _make_resource(db, wc.id, id=forced_id)
        assert printer.id == resource.id
        product = make_product()
        start = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
        end = start + timedelta(hours=2)
        on_printer = _make_operation(
            db, make_production_order(product_id=product.id).id, wc.id, status="queued",
            printer_id=printer.id, scheduled_start=start, scheduled_end=end,
        )
        on_resource = _make_operation(
            db, make_production_order(product_id=product.id).id, wc.id, status="queued",
            resource_id=resource.id, scheduled_start=start, scheduled_end=end,
        )

        assert find_block_siblings(db, on_printer) == []
        assert find_block_siblings(db, on_resource) == []

    def test_resource_blocks_are_found_too(
        self, db, make_product, make_production_order, make_work_center
    ):
        wc = make_work_center(center_type="machine")
        resource = _make_resource(db, wc.id)
        product = make_product()
        ops = [
            _make_operation(db, make_production_order(product_id=product.id).id, wc.id)
            for _ in range(3)
        ]
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        assert schedule_operations_together(db, ops, resource.id, start, start + timedelta(hours=2)) == (True, [])

        assert {s.id for s in find_block_siblings(db, ops[0])} == {ops[1].id, ops[2].id}


class TestResolveEditSlot:
    def test_a_solo_operation_only_excludes_itself_and_keeps_the_window(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center, count=1)
        proposed = (b.start + timedelta(minutes=30), b.end + timedelta(minutes=30))

        slot = resolve_edit_slot(db, b.member, b.printer.id, *proposed, is_printer=True)

        assert slot.exclude_ids == {b.member.id}
        assert (slot.start_time, slot.end_time) == proposed

    def test_the_blocks_own_slot_excludes_every_sibling(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)

        slot = resolve_edit_slot(db, b.member, b.printer.id, b.start, b.end, is_printer=True)

        assert slot.exclude_ids == {m.id for m in b.members}

    def test_another_window_excludes_only_the_member(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        proposed = (b.start + timedelta(minutes=30), b.end + timedelta(minutes=30))

        slot = resolve_edit_slot(db, b.member, b.printer.id, *proposed, is_printer=True)

        assert slot.exclude_ids == {b.member.id}
        assert (slot.start_time, slot.end_time) == proposed

    def test_another_machine_excludes_only_the_member(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        other = _make_printer(db, b.wc.id)

        slot = resolve_edit_slot(db, b.member, other.id, b.start, b.end, is_printer=True)

        assert slot.exclude_ids == {b.member.id}

    def test_the_blocks_window_on_a_resource_with_the_blocks_printer_id_is_another_machine(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)

        slot = resolve_edit_slot(db, b.member, b.printer.id, b.start, b.end, is_printer=False)

        assert slot.exclude_ids == {b.member.id}

    def test_a_minute_truncated_request_snaps_to_the_blocks_exact_window(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        exact_start = b.start.replace(second=37, microsecond=250000)
        exact_end = b.end.replace(second=37, microsecond=250000)
        for m in b.members:
            m.scheduled_start, m.scheduled_end = exact_start, exact_end
        db.flush()

        slot = resolve_edit_slot(
            db, b.member, b.printer.id,
            exact_start.replace(second=0, microsecond=0),
            exact_end.replace(second=0, microsecond=0),
            is_printer=True,
        )

        assert slot.exclude_ids == {m.id for m in b.members}
        # Aware in, aware out: the exact stored window, not the truncated request
        assert slot.start_time == exact_start
        assert slot.end_time == exact_end

    def test_naive_requests_get_naive_windows_back(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)

        slot = resolve_edit_slot(
            db, b.member, b.printer.id, _naive(b.start), _naive(b.end), is_printer=True,
        )

        assert slot.exclude_ids == {m.id for m in b.members}
        assert slot.start_time.tzinfo is None and slot.end_time.tzinfo is None

    def test_the_slot_match_is_less_than_a_minute_on_both_ends(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        just_inside = timedelta(seconds=59)
        a_minute = timedelta(seconds=60)

        inside = resolve_edit_slot(
            db, b.member, b.printer.id, b.start + just_inside, b.end - just_inside, is_printer=True,
        )
        start_out = resolve_edit_slot(
            db, b.member, b.printer.id, b.start + a_minute, b.end, is_printer=True,
        )
        end_out = resolve_edit_slot(
            db, b.member, b.printer.id, b.start, b.end - a_minute, is_printer=True,
        )

        assert inside.exclude_ids == {m.id for m in b.members}
        assert start_out.exclude_ids == {b.member.id}
        assert end_out.exclude_ids == {b.member.id}

    def test_an_unscheduled_operation_only_excludes_itself(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        pending = b.make_other_op()

        slot = resolve_edit_slot(db, pending, b.printer.id, b.start, b.end, is_printer=True)

        assert slot.exclude_ids == {pending.id}
        assert (slot.start_time, slot.end_time) == (b.start, b.end)


class TestScheduleOperationOnACobookedMember:
    def test_rescheduling_to_the_unchanged_slot_succeeds_and_moves_nothing(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)

        success, conflicts = schedule_operation(
            db, b.member, b.printer.id, b.start, b.end, is_printer=True,
        )

        assert (success, conflicts) == (True, [])
        for m in b.members:
            assert (m.scheduled_start, m.scheduled_end) == (b.start, b.end)
            assert m.printer_id == b.printer.id
            assert m.status == "queued"

    def test_moving_one_member_to_a_free_window_leaves_the_siblings(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        new_start = b.end + timedelta(hours=1)
        new_end = new_start + timedelta(hours=3)

        success, conflicts = schedule_operation(
            db, b.member, b.printer.id, new_start, new_end, is_printer=True,
        )

        assert (success, conflicts) == (True, [])
        assert (b.member.scheduled_start, b.member.scheduled_end) == (new_start, new_end)
        for s in b.siblings:
            assert (s.scheduled_start, s.scheduled_end) == (b.start, b.end)
        # and the member is no longer a sibling of the block
        assert find_block_siblings(db, b.member) == []
        assert {s.id for s in find_block_siblings(db, b.siblings[0])} == {b.siblings[1].id}

    def test_partial_overlap_with_the_block_is_a_conflict_with_the_siblings(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)

        success, conflicts = schedule_operation(
            db, b.member, b.printer.id,
            b.start + timedelta(minutes=30), b.end + timedelta(minutes=30), is_printer=True,
        )

        assert success is False
        assert {c.id for c in conflicts} == {s.id for s in b.siblings}
        assert (b.member.scheduled_start, b.member.scheduled_end) == (b.start, b.end)

    def test_an_unrelated_operation_in_the_window_is_still_a_conflict(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center)
        stranger = b.make_other_op(
            status="queued", printer_id=b.printer.id,
            scheduled_start=b.end + timedelta(hours=1),
            scheduled_end=b.end + timedelta(hours=3),
        )

        success, conflicts = schedule_operation(
            db, b.member, b.printer.id,
            b.end + timedelta(hours=2), b.end + timedelta(hours=4), is_printer=True,
        )

        assert success is False
        assert [c.id for c in conflicts] == [stranger.id]

    def test_a_solo_operation_is_unchanged(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center, count=1)
        shifted = (b.start + timedelta(minutes=30), b.end + timedelta(minutes=30))

        success, conflicts = schedule_operation(db, b.member, b.printer.id, *shifted, is_printer=True)

        assert (success, conflicts) == (True, [])
        assert (b.member.scheduled_start, b.member.scheduled_end) == shifted


class TestCheckSuccessorSchedulingInBlock:
    """``in_block_ids`` on check_successor_scheduling (mirrors the predecessor check)."""

    def test_a_successor_sharing_the_window_is_a_violation_by_default(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center, count=1)
        later = _make_operation(
            db, b.member.production_order_id, b.wc.id, sequence=20, status="queued",
            printer_id=b.printer.id, scheduled_start=b.start, scheduled_end=b.end,
        )

        violated = check_successor_scheduling(db, b.member, b.end)

        assert [s.id for s in violated] == [later.id]

    def test_a_successor_in_the_same_block_is_not_a_violation(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center, count=1)
        later = _make_operation(
            db, b.member.production_order_id, b.wc.id, sequence=20, status="queued",
            printer_id=b.printer.id, scheduled_start=b.start, scheduled_end=b.end,
        )

        assert check_successor_scheduling(db, b.member, b.end, in_block_ids={later.id}) is None

    def test_in_block_ids_do_not_hide_other_successors(
        self, db, make_product, make_production_order, make_work_center
    ):
        b = _block(db, make_product, make_production_order, make_work_center, count=1)
        in_block = _make_operation(
            db, b.member.production_order_id, b.wc.id, sequence=20, status="queued",
            printer_id=b.printer.id, scheduled_start=b.start, scheduled_end=b.end,
        )
        elsewhere = _make_operation(
            db, b.member.production_order_id, b.wc.id, sequence=30, status="queued",
            printer_id=b.printer.id,
            scheduled_start=b.start + timedelta(hours=1), scheduled_end=b.end + timedelta(hours=1),
        )

        violated = check_successor_scheduling(db, b.member, b.end, in_block_ids={in_block.id})

        assert [s.id for s in violated] == [elsewhere.id]
