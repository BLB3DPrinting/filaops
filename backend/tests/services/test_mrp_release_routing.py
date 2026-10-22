"""
Releasing an MRP planned order creates a full production order, behind
MRP_RELEASE_COPIES_ROUTING (print-batch plan S1), and a planned order can be
released in part.

Covers:
- MRPService._create_production_order delegating to
  production_order_service.create_production_order (routing, operations,
  operation materials, reservations) when the flag is on, and behaving as
  before when it is off
- MRPService.release_planned_order with an optional ``quantity`` (production
  and purchase), including the remainder staying open
- POST /api/v1/mrp/planned-orders/{id}/release (422 on a bad quantity)

Run with:
    cd backend
    pytest tests/services/test_mrp_release_routing.py -v
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.settings import Settings, get_settings
from app.models.inventory import InventoryTransaction
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.mrp import PlannedOrder
from app.models.production_order import ProductionOrder
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.services.mrp import MRPService
from app.services.mrp_release import InvalidReleaseQuantity


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def release_flag(monkeypatch):
    """Set MRP_RELEASE_COPIES_ROUTING on the shared Settings object for one test."""

    def _set(enabled: bool):
        monkeypatch.setattr(get_settings(), "MRP_RELEASE_COPIES_ROUTING", enabled)

    return _set


@pytest.fixture
def filament(make_product):
    return make_product(item_type="supply", unit="G", is_raw_material=True, procurement_type="buy")


@pytest.fixture
def routing_only_part(db, make_product, make_work_center, filament):
    """Intake-shaped part: no BOM, a routing whose PRINT step carries 37 g per piece."""
    part = make_product(item_type="component", procurement_type="make", has_bom=False)
    wc = make_work_center()
    routing = Routing(
        product_id=part.id,
        code=f"RT-{uuid.uuid4().hex[:8]}",
        name=f"Routing {part.sku}",
        is_active=True,
    )
    db.add(routing)
    db.flush()
    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        operation_code="PRINT",
        operation_name="Print",
        sequence=10,
        run_time_minutes=Decimal("30"),
    )
    db.add(op)
    db.flush()
    db.add(RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=filament.id,
        quantity=Decimal("37"),
        unit="G",
        scrap_factor=Decimal("0"),
    ))
    db.flush()
    part.routing = routing
    return part


@pytest.fixture
def bom_part(db, make_product, make_bom):
    """BOM-only part: no routing, two of a component per piece."""
    part = make_product(item_type="finished_good", procurement_type="make", has_bom=True)
    component = make_product(item_type="supply", unit="EA")
    part.bom = make_bom(product_id=part.id, lines=[
        {"component_id": component.id, "quantity": Decimal("2"), "unit": "EA"},
    ])
    part.bom_component = component
    return part


def _planned(db, product, *, order_type="production", quantity=9, status="planned"):
    order = PlannedOrder(
        order_type=order_type,
        product_id=product.id,
        quantity=Decimal(str(quantity)),
        due_date=date.today() + timedelta(days=14),
        start_date=date.today(),
        status=status,
        source_demand_type="mrp_calculation",
        created_at=datetime.now(timezone.utc),
    )
    db.add(order)
    db.flush()
    return order


def _reserved(db, order_id, product_id):
    """Total quantity reserved for (production order, component) in the ledger."""
    rows = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.reference_id == order_id,
        InventoryTransaction.product_id == product_id,
        InventoryTransaction.transaction_type == "reservation",
    ).all()
    return sum((r.quantity for r in rows), Decimal("0"))


def _orders_for(db, product):
    return db.query(ProductionOrder).filter(ProductionOrder.product_id == product.id).all()


# ---------------------------------------------------------------------------
# The flag
# ---------------------------------------------------------------------------

def test_flag_declared_off_by_default():
    assert Settings.model_fields["MRP_RELEASE_COPIES_ROUTING"].default is False


# ---------------------------------------------------------------------------
# Flag on: the released order is a real production order
# ---------------------------------------------------------------------------

class TestReleaseWithFlagOn:
    def test_order_gets_routing_print_operation_materials_and_reservations(
        self, db, routing_only_part, filament, release_flag,
    ):
        release_flag(True)
        planned = _planned(db, routing_only_part, quantity=5)

        released, mo_id = MRPService(db).release_planned_order(planned.id, user_id=1)

        mo = db.get(ProductionOrder, mo_id)
        assert released.status == "released"
        assert released.converted_to_mo_id == mo.id
        assert mo.routing_id == routing_only_part.routing.id
        assert mo.status == "draft"
        assert mo.source == "mrp_planned"
        assert mo.quantity_ordered == Decimal("5")
        assert mo.due_date == planned.due_date
        assert mo.created_by == "1"
        assert str(planned.id) in mo.notes

        assert [op.operation_code for op in mo.operations] == ["PRINT"]
        print_op = mo.operations[0]
        assert print_op.status == "pending"
        assert print_op.planned_run_minutes == 150  # 30 min x 5 pieces

        assert len(print_op.materials) == 1
        material = print_op.materials[0]
        assert material.component_id == filament.id
        assert material.quantity_required == Decimal("185")  # 37 g x 5 pieces

        assert _reserved(db, mo.id, filament.id) == Decimal("185")
        assert material.quantity_allocated == Decimal("185")

    def test_bom_product_keeps_its_bom_and_reserves_the_bom_lines(self, db, bom_part, release_flag):
        release_flag(True)
        planned = _planned(db, bom_part, quantity=4)

        _, mo_id = MRPService(db).release_planned_order(planned.id, user_id=1)

        mo = db.get(ProductionOrder, mo_id)
        assert mo.bom_id == bom_part.bom.id
        assert mo.routing_id is None
        assert list(mo.operations) == []
        assert _reserved(db, mo.id, bom_part.bom_component.id) == Decimal("8")

    def test_product_with_neither_bom_nor_routing_still_releases(self, db, make_product, release_flag):
        release_flag(True)
        bare = make_product(item_type="finished_good", procurement_type="make")
        planned = _planned(db, bare, quantity=3)

        _, mo_id = MRPService(db).release_planned_order(planned.id)

        mo = db.get(ProductionOrder, mo_id)
        assert mo.bom_id is None
        assert mo.routing_id is None
        assert list(mo.operations) == []
        assert mo.quantity_ordered == Decimal("3")


# ---------------------------------------------------------------------------
# Flag off: exactly today's behaviour
# ---------------------------------------------------------------------------

class TestReleaseWithFlagOff:
    def test_routing_part_is_released_without_routing_operations_or_reservations(
        self, db, routing_only_part, filament, release_flag,
    ):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=5)

        _, mo_id = MRPService(db).release_planned_order(planned.id, user_id=1)

        mo = db.get(ProductionOrder, mo_id)
        assert mo.routing_id is None
        assert mo.bom_id is None
        assert list(mo.operations) == []
        assert _reserved(db, mo.id, filament.id) == Decimal("0")
        assert mo.source == "mrp_planned"
        assert mo.status == "draft"

    def test_bom_part_gets_bom_id_and_no_reservation(self, db, bom_part, release_flag):
        release_flag(False)
        planned = _planned(db, bom_part, quantity=4)

        _, mo_id = MRPService(db).release_planned_order(planned.id, user_id=1)

        mo = db.get(ProductionOrder, mo_id)
        assert mo.bom_id == bom_part.bom.id
        assert mo.routing_id is None
        assert _reserved(db, mo.id, bom_part.bom_component.id) == Decimal("0")


# ---------------------------------------------------------------------------
# Partial release
# ---------------------------------------------------------------------------

class TestPartialRelease:
    def test_release_8_of_9_leaves_a_1_piece_planned_order(self, db, routing_only_part, release_flag):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=9)

        released, mo_id = MRPService(db).release_planned_order(
            planned.id, user_id=1, quantity=Decimal("8"),
        )

        mo = db.get(ProductionOrder, mo_id)
        assert mo.quantity_ordered == Decimal("8")
        assert released.quantity == Decimal("1")
        assert released.status == "planned"
        assert released.released_at is None
        assert released.converted_to_mo_id is None
        assert f"production order id {mo_id}" in released.notes
        assert len(_orders_for(db, routing_only_part)) == 1

    def test_the_remainder_can_be_released_afterwards(self, db, routing_only_part, release_flag):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=9)
        svc = MRPService(db)

        _, first_id = svc.release_planned_order(planned.id, quantity=Decimal("8"))
        released, second_id = svc.release_planned_order(planned.id)

        assert released.status == "released"
        assert released.converted_to_mo_id == second_id
        assert db.get(ProductionOrder, first_id).quantity_ordered == Decimal("8")
        assert db.get(ProductionOrder, second_id).quantity_ordered == Decimal("1")

    def test_a_firmed_order_stays_firmed(self, db, routing_only_part, release_flag):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=9, status="firmed")

        released, _ = MRPService(db).release_planned_order(planned.id, quantity=Decimal("8"))

        assert released.status == "firmed"
        assert released.quantity == Decimal("1")

    def test_quantity_equal_to_the_plan_is_a_full_release(self, db, routing_only_part, release_flag):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=9)

        released, mo_id = MRPService(db).release_planned_order(planned.id, quantity=Decimal("9"))

        assert released.status == "released"
        assert released.quantity == Decimal("9")
        assert released.converted_to_mo_id == mo_id
        assert db.get(ProductionOrder, mo_id).quantity_ordered == Decimal("9")

    def test_with_the_flag_on_operations_and_reservations_follow_the_released_quantity(
        self, db, routing_only_part, filament, release_flag,
    ):
        release_flag(True)
        planned = _planned(db, routing_only_part, quantity=9)

        _, mo_id = MRPService(db).release_planned_order(planned.id, quantity=Decimal("8"))

        mo = db.get(ProductionOrder, mo_id)
        print_op = mo.operations[0]
        assert print_op.planned_run_minutes == 240  # 30 min x 8
        assert print_op.materials[0].quantity_required == Decimal("296")  # 37 g x 8
        assert _reserved(db, mo.id, filament.id) == Decimal("296")

    def test_a_purchase_can_be_released_in_part(self, db, make_product, make_vendor):
        item = make_product(item_type="supply", unit="EA", standard_cost=Decimal("2.50"))
        vendor = make_vendor()
        planned = _planned(db, item, order_type="purchase", quantity=50)

        released, po_id = MRPService(db).release_planned_order(
            planned.id, vendor_id=vendor.id, quantity=Decimal("20"),
        )

        po = db.get(PurchaseOrder, po_id)
        line = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == po.id).one()
        assert line.quantity_ordered == Decimal("20")
        assert line.line_total == Decimal("50.00")
        assert po.total_amount == Decimal("50.00")
        assert released.quantity == Decimal("30")
        assert released.status == "planned"
        assert released.converted_to_po_id is None

    @pytest.mark.parametrize("bad", ["0", "-1", "9.0001", "10"])
    def test_a_quantity_outside_zero_to_the_plan_is_rejected(
        self, db, routing_only_part, release_flag, bad,
    ):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=9)

        with pytest.raises(InvalidReleaseQuantity):
            MRPService(db).release_planned_order(planned.id, quantity=Decimal(bad))

        assert planned.quantity == Decimal("9")
        assert planned.status == "planned"
        assert _orders_for(db, routing_only_part) == []


# ---------------------------------------------------------------------------
# POST /api/v1/mrp/planned-orders/{id}/release
# ---------------------------------------------------------------------------

class TestReleaseEndpoint:
    @staticmethod
    def _url(planned):
        return f"/api/v1/mrp/planned-orders/{planned.id}/release"

    def test_partial_release_reports_what_was_released_and_what_is_left(
        self, db, client, routing_only_part, release_flag,
    ):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=9)

        resp = client.post(self._url(planned), json={"quantity": 8})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["created_production_order_id"] is not None
        assert Decimal(body["released_quantity"]) == Decimal("8")
        assert Decimal(body["remaining_quantity"]) == Decimal("1")
        db.refresh(planned)
        assert planned.status == "planned"
        assert planned.quantity == Decimal("1")

    def test_without_a_quantity_the_whole_plan_is_released(
        self, db, client, routing_only_part, release_flag,
    ):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=9)

        resp = client.post(self._url(planned), json={})

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert Decimal(body["released_quantity"]) == Decimal("9")
        assert Decimal(body["remaining_quantity"]) == Decimal("0")
        db.refresh(planned)
        assert planned.status == "released"

    @pytest.mark.parametrize("bad", [0, -1, 9.0001, 10, "eight"])
    def test_a_bad_quantity_is_a_422_and_changes_nothing(
        self, db, client, routing_only_part, release_flag, bad,
    ):
        release_flag(False)
        planned = _planned(db, routing_only_part, quantity=9)

        resp = client.post(self._url(planned), json={"quantity": bad})

        assert resp.status_code == 422, resp.text
        db.refresh(planned)
        assert planned.status == "planned"
        assert planned.quantity == Decimal("9")
        assert _orders_for(db, routing_only_part) == []

    def test_a_status_error_is_still_a_400(self, db, client, routing_only_part):
        planned = _planned(db, routing_only_part, quantity=9, status="released")

        resp = client.post(self._url(planned), json={"quantity": 5})

        assert resp.status_code == 400, resp.text
