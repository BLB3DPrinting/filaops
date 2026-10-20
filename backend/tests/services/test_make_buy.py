"""
Make-vs-buy by routing materials, behind MRP_ROUTING_MAKE_BUY (print-batch plan S0).

Covers app/services/make_buy.py and every gate that calls it:
- MRPService.generate_planned_orders (planned order_type)
- MRPService.run_mrp sub-assembly due-date cascade gate
- requirement_explosion recursion gates
- GET /api/v1/mrp/planned-orders/dry-run-diff

Run with:
    cd backend
    pytest tests/services/test_make_buy.py -v
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.settings import Settings, get_settings
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.mrp import MRPRun, PlannedOrder
from app.models.production_order import ProductionOrder
from app.services import make_buy
from app.services.mrp import ComponentRequirement, MRPService, NetRequirement
from app.services.requirement_explosion import explode_requirements


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def routing_flag(monkeypatch):
    """Set MRP_ROUTING_MAKE_BUY on the shared Settings object for one test."""

    def _set(enabled: bool):
        monkeypatch.setattr(get_settings(), "MRP_ROUTING_MAKE_BUY", enabled)

    return _set


def _make_routing(
    db,
    make_work_center,
    product,
    component,
    *,
    qty=Decimal("37"),
    unit="G",
    is_cost_only=False,
    is_active=True,
):
    """Routing with one PRINT operation carrying one material (Intake's shape)."""
    wc = make_work_center()
    routing = Routing(
        product_id=product.id,
        code=f"RT-{uuid.uuid4().hex[:8]}",
        name=f"Routing {product.sku}",
        is_active=is_active,
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

    mat = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=component.id,
        quantity=qty,
        unit=unit,
        scrap_factor=Decimal("0"),
        is_cost_only=is_cost_only,
    )
    db.add(mat)
    db.flush()
    return routing


def _mrp_run(db):
    run = MRPRun(
        run_date=datetime.now(timezone.utc),
        planning_horizon_days=30,
        status="running",
    )
    db.add(run)
    db.flush()
    return run


def _shortage(product, qty=Decimal("10")):
    return NetRequirement(
        product_id=product.id,
        product_sku=product.sku,
        product_name=product.name,
        gross_quantity=qty,
        on_hand_quantity=Decimal("0"),
        allocated_quantity=Decimal("0"),
        available_quantity=Decimal("0"),
        incoming_quantity=Decimal("0"),
        safety_stock=Decimal("0"),
        net_shortage=qty,
        lead_time_days=7,
        has_bom=bool(product.has_bom),
    )


def _planned_order(db, product, *, order_type, status="planned"):
    order = PlannedOrder(
        order_type=order_type,
        product_id=product.id,
        quantity=Decimal("5"),
        due_date=date.today() + timedelta(days=14),
        start_date=date.today(),
        status=status,
        source_demand_type="mrp_calculation",
        created_at=datetime.now(timezone.utc),
    )
    db.add(order)
    db.flush()
    return order


def _plan(db, product):
    """Run generate_planned_orders for one shortage and return the planned order."""
    orders = MRPService(db).generate_planned_orders([_shortage(product)], int(_mrp_run(db).id))
    assert len(orders) == 1
    return orders[0]


@pytest.fixture
def filament(make_product):
    return make_product(item_type="supply", unit="G", is_raw_material=True, procurement_type="buy")


@pytest.fixture
def routing_only_part(db, make_product, make_work_center, filament):
    """Intake-shaped part: procurement_type make, no BOM, filament on the PRINT step."""
    part = make_product(item_type="component", procurement_type="make", has_bom=False)
    _make_routing(db, make_work_center, part, filament)
    return part


# ---------------------------------------------------------------------------
# The rule itself
# ---------------------------------------------------------------------------

class TestRule:
    def test_flag_declared_off_by_default(self):
        assert Settings.model_fields["MRP_ROUTING_MAKE_BUY"].default is False

    def test_routing_only_part_is_made(self, db, routing_only_part):
        decision = make_buy.decide_make_buy(db, routing_only_part)
        assert decision.is_made is True
        assert decision.reason == make_buy.REASON_ROUTING_MATERIALS
        assert decision.order_type == "production"

    def test_bom_part_is_made(self, db, make_product):
        part = make_product(item_type="component", procurement_type="make", has_bom=True)
        decision = make_buy.decide_make_buy(db, part)
        assert decision.is_made is True
        assert decision.reason == make_buy.REASON_BOM

    def test_buy_overrides_bom_and_routing(self, db, make_product, make_work_center, filament):
        part = make_product(item_type="component", procurement_type="buy", has_bom=True)
        _make_routing(db, make_work_center, part, filament)
        decision = make_buy.decide_make_buy(db, part)
        assert decision.is_made is False
        assert decision.reason == make_buy.REASON_BUY_OVERRIDE
        assert decision.order_type == "purchase"

    def test_make_alone_is_not_a_trigger(self, db, make_product):
        """The item form defaults every new item to 'make'; that must not plan production."""
        part = make_product(item_type="component", procurement_type="make", has_bom=False)
        decision = make_buy.decide_make_buy(db, part)
        assert decision.is_made is False
        assert decision.reason == make_buy.REASON_NO_MAKE_SOURCE

    def test_cost_only_material_does_not_count(self, db, make_product, make_work_center, filament):
        part = make_product(item_type="component", procurement_type="make", has_bom=False)
        _make_routing(db, make_work_center, part, filament, is_cost_only=True)
        assert make_buy.has_routing_materials(db, part.id) is False
        assert make_buy.decide_make_buy(db, part).is_made is False

    def test_inactive_routing_does_not_count(self, db, make_product, make_work_center, filament):
        part = make_product(item_type="component", procurement_type="make", has_bom=False)
        _make_routing(db, make_work_center, part, filament, is_active=False)
        assert make_buy.has_routing_materials(db, part.id) is False
        assert make_buy.decide_make_buy(db, part).is_made is False

    def test_is_made_follows_the_flag(self, db, routing_only_part, routing_flag):
        routing_flag(False)
        assert make_buy.is_made(db, routing_only_part) is False
        routing_flag(True)
        assert make_buy.is_made(db, routing_only_part) is True


# ---------------------------------------------------------------------------
# Gate 1: generate_planned_orders
# ---------------------------------------------------------------------------

class TestGeneratePlannedOrders:
    def test_routing_only_part_plans_as_purchase_with_flag_off(self, db, routing_only_part, routing_flag):
        routing_flag(False)
        assert _plan(db, routing_only_part).order_type == "purchase"

    def test_routing_only_part_plans_as_production_with_flag_on(self, db, routing_only_part, routing_flag):
        routing_flag(True)
        assert _plan(db, routing_only_part).order_type == "production"

    def test_buy_with_routing_still_plans_as_purchase(
        self, db, make_product, make_work_center, filament, routing_flag
    ):
        routing_flag(True)
        part = make_product(item_type="component", procurement_type="buy", has_bom=False)
        _make_routing(db, make_work_center, part, filament)
        assert _plan(db, part).order_type == "purchase"

    def test_make_without_bom_or_routing_plans_as_purchase(self, db, make_product, routing_flag):
        routing_flag(True)
        part = make_product(item_type="component", procurement_type="make", has_bom=False)
        assert _plan(db, part).order_type == "purchase"

    def test_bom_part_still_plans_as_production(self, db, make_product, routing_flag):
        routing_flag(True)
        part = make_product(item_type="component", procurement_type="make", has_bom=True)
        assert _plan(db, part).order_type == "production"


# ---------------------------------------------------------------------------
# Gate 3: requirement explosion recursion
# ---------------------------------------------------------------------------

class TestExplosionRecursion:
    @pytest.fixture
    def assembly(self, make_product, make_bom, routing_only_part):
        """Assembly with a BOM calling for 2 of the routing-only part."""
        fg = make_product(item_type="finished_good", procurement_type="make", has_bom=True)
        make_bom(product_id=fg.id, lines=[
            {"component_id": routing_only_part.id, "quantity": Decimal("2"), "unit": "EA"},
        ])
        return fg

    def test_flag_off_stops_at_the_routing_only_component(
        self, db, assembly, routing_only_part, routing_flag
    ):
        routing_flag(False)
        reqs = explode_requirements(db, assembly.id, Decimal("3"))
        assert [r.product_id for r in reqs] == [routing_only_part.id]
        assert reqs[0].gross_quantity == Decimal("6")

    def test_flag_on_recurses_into_the_routing_only_component(
        self, db, assembly, routing_only_part, filament, routing_flag
    ):
        routing_flag(True)
        reqs = explode_requirements(db, assembly.id, Decimal("3"))
        by_product = {r.product_id: r for r in reqs}
        assert set(by_product) == {routing_only_part.id, filament.id}
        assert by_product[routing_only_part.id].gross_quantity == Decimal("6")
        assert by_product[filament.id].gross_quantity == Decimal("222")  # 6 parts x 37 g
        assert by_product[filament.id].bom_level == 1


# ---------------------------------------------------------------------------
# Gate 2: run_mrp sub-assembly cascade
# ---------------------------------------------------------------------------

class TestNetRequirementIsMade:
    """calculate_net_requirements fills the field the cascade gate reads."""

    def _requirement(self, product):
        return ComponentRequirement(
            product_id=product.id,
            product_sku=product.sku,
            product_name=product.name,
            bom_level=1,
            gross_quantity=Decimal("4"),
        )

    def test_flag_off_mirrors_has_bom(self, db, routing_only_part, routing_flag):
        routing_flag(False)
        [net] = MRPService(db).calculate_net_requirements([self._requirement(routing_only_part)])
        assert net.has_bom is False
        assert net.is_made is False

    def test_flag_on_counts_routing_materials(self, db, routing_only_part, routing_flag):
        routing_flag(True)
        [net] = MRPService(db).calculate_net_requirements([self._requirement(routing_only_part)])
        assert net.has_bom is False
        assert net.is_made is True


class TestCascadeGate:
    """FG -> sub-assembly (BOM) -> routing-only part (lead 3 days) -> filament,
    run through run_mrp with MRP_ENABLE_SUB_ASSEMBLY_CASCADING on.

    Only the order type is asserted. The cascaded due date cannot be observed
    here: explode_requirements tags every requirement with the top-level
    product as parent_product_id, so run_mrp never finds a parent requirement
    to take a due date from (pre-existing, reported separately).
    """

    @pytest.fixture
    def demand(self, db, make_product, make_bom, make_work_center, filament):
        fg = make_product(item_type="finished_good", procurement_type="make", has_bom=True)
        sub = make_product(item_type="component", procurement_type="make", has_bom=True)
        part = make_product(
            item_type="component", procurement_type="make", has_bom=False, lead_time_days=3,
        )
        make_bom(product_id=fg.id, lines=[
            {"component_id": sub.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        make_bom(product_id=sub.id, lines=[
            {"component_id": part.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        _make_routing(db, make_work_center, part, filament)

        po = ProductionOrder(
            code=f"PO-TEST-{uuid.uuid4().hex[:8]}",
            product_id=fg.id,
            quantity_ordered=Decimal("2"),
            quantity_completed=Decimal("0"),
            quantity_scrapped=Decimal("0"),
            status="released",
            source="manual",
            due_date=date.today() + timedelta(days=20),
        )
        db.add(po)
        db.flush()
        return part

    def _run(self, db):
        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = False
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = True
            result = MRPService(db).run_mrp(planning_horizon_days=30, user_id=1)
        assert result.errors == []
        return result

    def _planned_for(self, db, result, product):
        orders = db.query(PlannedOrder).filter(
            PlannedOrder.mrp_run_id == result.run_id,
            PlannedOrder.product_id == product.id,
        ).all()
        assert len(orders) == 1
        return orders[0]

    def test_flag_off_part_is_a_purchase_on_the_default_date(self, db, demand, routing_flag):
        routing_flag(False)
        order = self._planned_for(db, self._run(db), demand)
        assert order.order_type == "purchase"
        assert order.due_date == date.today() + timedelta(days=14)

    def test_flag_on_part_is_production(self, db, demand, routing_flag):
        routing_flag(True)
        order = self._planned_for(db, self._run(db), demand)
        assert order.order_type == "production"
        assert order.start_date >= date.today()
        assert order.due_date >= order.start_date


# ---------------------------------------------------------------------------
# Dry-run diff
# ---------------------------------------------------------------------------

class TestDryRunDiff:
    def test_lists_products_whose_type_would_change(
        self, db, make_product, make_work_center, filament, routing_only_part
    ):
        planned = _planned_order(db, routing_only_part, order_type="purchase")
        firmed = _planned_order(db, routing_only_part, order_type="purchase", status="firmed")

        bought_bom = make_product(item_type="component", procurement_type="buy", has_bom=True)
        _planned_order(db, bought_bom, order_type="production")

        _planned_order(db, filament, order_type="purchase")  # unchanged either way

        cancelled_part = make_product(item_type="component", procurement_type="make", has_bom=False)
        _make_routing(db, make_work_center, cancelled_part, filament)
        _planned_order(db, cancelled_part, order_type="purchase", status="cancelled")

        report = make_buy.make_buy_dry_run_diff(db)
        changes = {c["product_id"]: c for c in report["changes"]}

        assert report["flag_enabled"] is False
        assert report["statuses"] == ["planned", "firmed"]
        assert report["total_changes"] == len(report["changes"])

        assert changes[routing_only_part.id]["current_order_type"] == "purchase"
        assert changes[routing_only_part.id]["proposed_order_type"] == "production"
        assert changes[routing_only_part.id]["reason"] == make_buy.REASON_ROUTING_MATERIALS
        assert changes[routing_only_part.id]["planned_order_ids"] == [planned.id, firmed.id]
        assert changes[routing_only_part.id]["product_sku"] == routing_only_part.sku

        assert changes[bought_bom.id]["current_order_type"] == "production"
        assert changes[bought_bom.id]["proposed_order_type"] == "purchase"
        assert changes[bought_bom.id]["reason"] == make_buy.REASON_BUY_OVERRIDE

        assert filament.id not in changes
        assert cancelled_part.id not in changes

    def test_writes_nothing(self, db, routing_only_part):
        order = _planned_order(db, routing_only_part, order_type="purchase")
        make_buy.make_buy_dry_run_diff(db)
        db.refresh(order)
        assert order.order_type == "purchase"
        assert order.status == "planned"

    def test_endpoint_returns_the_diff(self, db, client, routing_only_part):
        order = _planned_order(db, routing_only_part, order_type="purchase")

        resp = client.get("/api/v1/mrp/planned-orders/dry-run-diff")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["flag_enabled"] is False
        assert body["planned_orders_checked"] >= 1
        changes = {c["product_id"]: c for c in body["changes"]}
        assert changes[routing_only_part.id]["proposed_order_type"] == "production"
        assert changes[routing_only_part.id]["reason"] == "routing_materials"
        assert order.id in changes[routing_only_part.id]["planned_order_ids"]

        db.refresh(order)
        assert order.order_type == "purchase"

    def test_endpoint_requires_auth(self, unauthed_client):
        resp = unauthed_client.get("/api/v1/mrp/planned-orders/dry-run-diff")
        assert resp.status_code == 401
