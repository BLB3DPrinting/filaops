"""
API tests for GET /api/v1/scheduling/resource-conflicts (the scheduler
modal's live conflict check).

The modal passes ``operation_id`` while editing an already-scheduled
operation so the check agrees with the reschedule endpoint:

- the operation never conflicts with its own stored slot
- when the proposed slot is the slot of the co-booked block it belongs to,
  the block's siblings are not conflicts either (S3/S4 print batches)
- everything else is reported as before

The sibling set is derived by the server from the stored window. The
endpoint accepts a single ``operation_id`` (the operation being edited) and
no list of ids to exclude.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.printer import Printer
from app.models.production_order import ProductionOrderOperation

URL = "/api/v1/scheduling/resource-conflicts"


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
        sequence=10,
        operation_code="PRINT",
        operation_name="Print",
        planned_run_minutes=60,
        status="queued",
        **kwargs,
    )
    db.add(operation)
    db.flush()
    return operation


class _Scene:
    """A printer with a 3-member block plus (optionally) an unrelated op."""

    def __init__(self, db, make_product, make_production_order, make_work_center, members=3):
        self.wc = make_work_center()
        self.printer = _make_printer(db, self.wc.id)
        self.start = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0)
        self.end = self.start + timedelta(hours=3)
        product = make_product()
        self.members = [
            _make_operation(
                db, make_production_order(product_id=product.id).id, self.wc.id,
                printer_id=self.printer.id,
                scheduled_start=self.start, scheduled_end=self.end,
            )
            for _ in range(members)
        ]
        self.db = db
        self.product = product
        self.make_production_order = make_production_order

    @property
    def member(self):
        return self.members[0]

    @property
    def sibling_ids(self):
        return {m.id for m in self.members[1:]}

    def add_stranger(self, start, end):
        return _make_operation(
            self.db, self.make_production_order(product_id=self.product.id).id, self.wc.id,
            printer_id=self.printer.id, scheduled_start=start, scheduled_end=end,
        )


@pytest.fixture
def scene(db, make_product, make_production_order, make_work_center):
    return _Scene(db, make_product, make_production_order, make_work_center)


def _check(client, scene, start, end, **extra):
    params = {
        "resource_id": scene.printer.id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "is_printer": "true",
        **extra,
    }
    resp = client.get(URL, params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["conflicts"]


def _ids(conflicts):
    return {c["operation_id"] for c in conflicts if c["type"] == "operation"}


class TestWithoutAnOperationId:
    def test_the_whole_block_is_reported_as_before(self, client, db, scene):
        db.commit()

        conflicts = _check(client, scene, scene.start, scene.end)

        assert _ids(conflicts) == {m.id for m in scene.members}


class TestEditingAnOperation:
    def test_a_solo_operation_does_not_conflict_with_its_own_slot(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        solo = _Scene(db, make_product, make_production_order, make_work_center, members=1)
        db.commit()

        conflicts = _check(client, solo, solo.start, solo.end, operation_id=solo.member.id)

        assert conflicts == []

    def test_a_solo_operation_does_not_conflict_with_a_slot_overlapping_its_own(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        solo = _Scene(db, make_product, make_production_order, make_work_center, members=1)
        db.commit()

        conflicts = _check(
            client, solo,
            solo.start + timedelta(minutes=15), solo.end + timedelta(minutes=15),
            operation_id=solo.member.id,
        )

        assert conflicts == []

    def test_the_unchanged_slot_of_a_cobooked_member_has_no_conflicts(self, client, db, scene):
        db.commit()

        conflicts = _check(client, scene, scene.start, scene.end, operation_id=scene.member.id)

        assert conflicts == []

    def test_a_minute_truncated_copy_of_the_blocks_slot_has_no_conflicts(self, client, db, scene):
        exact = scene.start.replace(second=37)
        for m in scene.members:
            m.scheduled_start = exact
            m.scheduled_end = exact + timedelta(hours=3)
        db.commit()

        conflicts = _check(
            client, scene,
            exact.replace(second=0), (exact + timedelta(hours=3)).replace(second=0),
            operation_id=scene.member.id,
        )

        assert conflicts == []

    def test_a_partial_overlap_with_the_block_reports_the_siblings(self, client, db, scene):
        db.commit()

        conflicts = _check(
            client, scene,
            scene.start + timedelta(minutes=30), scene.end + timedelta(minutes=30),
            operation_id=scene.member.id,
        )

        assert _ids(conflicts) == scene.sibling_ids

    def test_a_free_window_has_no_conflicts(self, client, db, scene):
        db.commit()

        conflicts = _check(
            client, scene,
            scene.end + timedelta(hours=1), scene.end + timedelta(hours=4),
            operation_id=scene.member.id,
        )

        assert conflicts == []

    def test_an_unrelated_operation_in_the_unchanged_slot_is_still_reported(self, client, db, scene):
        stranger = scene.add_stranger(scene.start + timedelta(hours=1), scene.end + timedelta(hours=1))
        db.commit()

        conflicts = _check(client, scene, scene.start, scene.end, operation_id=scene.member.id)

        assert _ids(conflicts) == {stranger.id}

    def test_a_non_member_operation_id_does_not_waive_the_block(self, client, db, scene):
        """Only the edited operation's OWN block is waived: naming an
        operation that is not in the block does not hide the block."""
        stranger = scene.add_stranger(scene.end + timedelta(hours=2), scene.end + timedelta(hours=4))
        db.commit()

        conflicts = _check(client, scene, scene.start, scene.end, operation_id=stranger.id)

        assert _ids(conflicts) == {m.id for m in scene.members}

    def test_an_unknown_operation_id_is_a_plain_check(self, client, db, scene):
        db.commit()

        conflicts = _check(client, scene, scene.start, scene.end, operation_id=2_000_000_000)

        assert _ids(conflicts) == {m.id for m in scene.members}


class TestNoClientSuppliedExclusionList:
    @pytest.mark.parametrize("param", ["exclude_operation_ids", "exclude_operation_id", "sibling_ids"])
    def test_a_list_of_ids_cannot_hide_operations(self, client, db, scene, param):
        stranger = scene.add_stranger(scene.end + timedelta(hours=2), scene.end + timedelta(hours=4))
        db.commit()

        conflicts = _check(
            client, scene, stranger.scheduled_start, stranger.scheduled_end,
            operation_id=scene.member.id, **{param: stranger.id},
        )

        assert _ids(conflicts) == {stranger.id}
