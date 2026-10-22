"""
Tests for open production orders as incoming supply (print-batch plan S0b).

Behind ``MRP_OPEN_PO_SUPPLY`` (default off), MRP, supply netting and the item
demand summary all add what open production orders still have to make, using
one status set and date rule from ``services/open_supply.py``.

Covers:
- The shared function: status set, remainder, date rule, ordering, flag off
- MRP end to end: a shortage covered by an open order is not planned again on
  the next run; partial orders contribute only the remainder; cancelled,
  complete, short and scrapped orders contribute nothing
- Flag off: planned orders and all three helpers are unchanged
- The three helpers report the same incoming quantity for the same data

Run with:
    cd backend
    pytest tests/services/test_open_supply.py -v
"""
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.core.settings import get_settings
from app.models.mrp import PlannedOrder
from app.models.purchase_order import PurchaseOrderLine
from app.services import open_supply
from app.services.item_demand import get_incoming_supply, get_item_demand_summary
from app.services.mrp import MRPService
from app.services.supply_netting import (
    get_projected_available,
    get_projected_available_bulk,
)


@pytest.fixture
def flag_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "MRP_OPEN_PO_SUPPLY", True)


@pytest.fixture
def flag_off(monkeypatch):
    monkeypatch.setattr(get_settings(), "MRP_OPEN_PO_SUPPLY", False)


@pytest.fixture
def make_order(make_production_order):
    """Production order factory with the completed quantity as a keyword."""

    def _factory(product, quantity=10, completed=0, status="released", **kwargs):
        return make_production_order(
            product_id=product.id,
            quantity=quantity,
            status=status,
            quantity_completed=completed,
            **kwargs,
        )

    return _factory


def _make_open_po_line(db, make_vendor, make_purchase_order, product, quantity, status="ordered"):
    po = make_purchase_order(vendor_id=make_vendor().id, status=status)
    db.add(PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product.id,
        line_number=1,
        quantity_ordered=Decimal(str(quantity)),
        quantity_received=Decimal("0"),
        unit_cost=Decimal("1.00"),
        line_total=Decimal(str(quantity)),
    ))
    db.flush()
    return po


# =============================================================================
# The shared function
# =============================================================================

class TestOpenSupplyFunction:

    def test_flag_off_returns_nothing_without_querying(self, flag_off):
        db = MagicMock()
        assert open_supply.get_open_production_supply(db, [1, 2]) == {}
        assert open_supply.get_open_production_supply_qty(db, [1, 2]) == {}
        db.query.assert_not_called()

    def test_flag_on_without_products_does_not_query(self, flag_on):
        db = MagicMock()
        assert open_supply.get_open_production_supply(db, []) == {}
        db.query.assert_not_called()

    @pytest.mark.parametrize("status", ["draft", "released", "scheduled", "in_progress"])
    def test_open_statuses_count(self, db, make_product, make_order, flag_on, status):
        part = make_product(procurement_type="make")
        make_order(part, quantity=10, status=status)

        supply = open_supply.get_open_production_supply(db, [part.id])

        assert [s.quantity for s in supply[part.id]] == [Decimal("10")]
        assert supply[part.id][0].status == status

    @pytest.mark.parametrize("status", [
        "complete", "completed", "short", "cancelled", "scrapped",
        "on_hold", "qc_hold", "closed",
    ])
    def test_other_statuses_contribute_nothing(self, db, make_product, make_order, flag_on, status):
        part = make_product(procurement_type="make")
        make_order(part, quantity=10, status=status)

        assert open_supply.get_open_production_supply(db, [part.id]) == {}

    def test_only_the_remainder_counts(self, db, make_product, make_order, flag_on):
        part = make_product(procurement_type="make")
        make_order(part, quantity=10, completed=4, status="in_progress")

        qty = open_supply.get_open_production_supply_qty(db, [part.id])

        assert qty == {part.id: Decimal("6")}

    @pytest.mark.parametrize("completed", [10, 12])
    def test_fully_or_over_completed_order_contributes_nothing(
        self, db, make_product, make_order, flag_on, completed
    ):
        part = make_product(procurement_type="make")
        make_order(part, quantity=10, completed=completed, status="in_progress")

        assert open_supply.get_open_production_supply(db, [part.id]) == {}

    def test_orders_for_other_products_are_ignored(self, db, make_product, make_order, flag_on):
        part = make_product(procurement_type="make")
        other = make_product(procurement_type="make")
        make_order(other, quantity=10)

        assert open_supply.get_open_production_supply(db, [part.id]) == {}

    def test_order_linked_to_a_sales_order_is_committed_not_supply(
        self, db, make_product, make_order, make_sales_order, flag_on
    ):
        part = make_product(procurement_type="make")
        sale = make_sales_order(product_id=part.id, quantity=10)
        make_order(part, quantity=10, sales_order_id=sale.id)

        assert open_supply.get_open_production_supply(db, [part.id]) == {}

    def test_date_is_scheduled_end_then_due_date_then_today(
        self, db, make_product, make_order, flag_on
    ):
        part = make_product(procurement_type="make")
        today = date.today()
        scheduled = make_order(
            part, due_date=today + timedelta(days=9),
            scheduled_end=datetime.combine(today + timedelta(days=3), datetime.min.time()),
        )
        due_only = make_order(part, due_date=today + timedelta(days=5))
        undated = make_order(part)

        supply = open_supply.get_open_production_supply(db, [part.id], today=today)

        dates = {s.production_order_id: s.expected_date for s in supply[part.id]}
        assert dates[scheduled.id] == today + timedelta(days=3)  # scheduled_end wins
        assert dates[due_only.id] == today + timedelta(days=5)
        assert dates[undated.id] == today

    def test_supply_is_listed_earliest_first(self, db, make_product, make_order, flag_on):
        part = make_product(procurement_type="make")
        today = date.today()
        late = make_order(part, due_date=today + timedelta(days=8))
        early = make_order(part, due_date=today + timedelta(days=2))

        supply = open_supply.get_open_production_supply(db, [part.id])

        assert [s.production_order_id for s in supply[part.id]] == [early.id, late.id]


# =============================================================================
# MRP end to end
# =============================================================================

def _plan_demand_for_part(db, make_product, make_bom, make_sales_order, monkeypatch, demand=10):
    """A made part (own BOM) needed by a confirmed sales order of its parent."""
    monkeypatch.setattr(get_settings(), "INCLUDE_SALES_ORDERS_IN_MRP", True)
    fg = make_product(item_type="finished_good", procurement_type="make", has_bom=True)
    part = make_product(
        item_type="component", procurement_type="make", has_bom=True, name=f"Part {uuid.uuid4().hex[:6]}"
    )
    raw = make_product(item_type="supply", unit="G", is_raw_material=True)
    make_bom(product_id=fg.id, lines=[
        {"component_id": part.id, "quantity": Decimal("1"), "unit": "EA"},
    ])
    make_bom(product_id=part.id, lines=[
        {"component_id": raw.id, "quantity": Decimal("5"), "unit": "G"},
    ])
    make_sales_order(
        product_id=fg.id, quantity=demand, status="confirmed", order_type="quote_based",
        estimated_completion_date=datetime.now(timezone.utc) + timedelta(days=5),
    )
    return part


def _planned_quantity(db, part):
    orders = db.query(PlannedOrder).filter(
        PlannedOrder.product_id == part.id,
        PlannedOrder.status == "planned",
    ).all()
    return sum((o.quantity for o in orders), Decimal("0"))


class TestMrpOpenProductionSupply:

    def _run(self, db):
        result = MRPService(db).run_mrp(planning_horizon_days=30, user_id=1)
        assert result.errors == []
        return result

    def test_covered_shortage_is_not_replanned_on_next_run(
        self, db, make_product, make_bom, make_sales_order, make_order, flag_on, monkeypatch
    ):
        part = _plan_demand_for_part(db, make_product, make_bom, make_sales_order, monkeypatch)

        self._run(db)
        assert _planned_quantity(db, part) == Decimal("10")  # nothing is making it yet

        make_order(part, quantity=10, status="released", due_date=date.today() + timedelta(days=5))
        self._run(db)

        assert _planned_quantity(db, part) == Decimal("0")

    def test_in_progress_and_draft_orders_cover_the_shortage_too(
        self, db, make_product, make_bom, make_sales_order, make_order, flag_on, monkeypatch
    ):
        part = _plan_demand_for_part(db, make_product, make_bom, make_sales_order, monkeypatch)
        make_order(part, quantity=6, status="in_progress")
        make_order(part, quantity=4, status="draft")

        self._run(db)

        assert _planned_quantity(db, part) == Decimal("0")

    def test_partly_completed_order_covers_only_its_remainder(
        self, db, make_product, make_bom, make_sales_order, make_order, flag_on, monkeypatch
    ):
        part = _plan_demand_for_part(db, make_product, make_bom, make_sales_order, monkeypatch)
        make_order(part, quantity=10, completed=4, status="in_progress")

        self._run(db)

        assert _planned_quantity(db, part) == Decimal("4")  # 10 needed - (10 - 4) coming

    @pytest.mark.parametrize("status", ["cancelled", "complete", "short", "scrapped"])
    def test_closed_out_orders_cover_nothing(
        self, db, make_product, make_bom, make_sales_order, make_order, flag_on, monkeypatch, status
    ):
        part = _plan_demand_for_part(db, make_product, make_bom, make_sales_order, monkeypatch)
        make_order(part, quantity=10, status=status)

        self._run(db)

        assert _planned_quantity(db, part) == Decimal("10")

    def test_order_made_for_a_sales_order_does_not_cover_other_demand(
        self, db, make_product, make_bom, make_sales_order, make_order, flag_on, monkeypatch
    ):
        # The part is needed by sale B (through its parent's BOM) and is also sold
        # loose on sale A, which has its own production order. MRP leaves sale A
        # out of demand, so that order's output is committed to A and must not
        # also cover B.
        part = _plan_demand_for_part(db, make_product, make_bom, make_sales_order, monkeypatch)
        sale_a = make_sales_order(
            product_id=part.id, quantity=10, status="confirmed", order_type="quote_based",
            estimated_completion_date=datetime.now(timezone.utc) + timedelta(days=5),
        )
        make_order(part, quantity=10, status="released", sales_order_id=sale_a.id)

        self._run(db)

        assert _planned_quantity(db, part) == Decimal("10")

    def test_flag_off_planned_orders_are_unchanged(
        self, db, make_product, make_bom, make_sales_order, make_order, flag_off, monkeypatch
    ):
        part = _plan_demand_for_part(db, make_product, make_bom, make_sales_order, monkeypatch)
        make_order(part, quantity=10, status="released", due_date=date.today() + timedelta(days=5))
        make_order(part, quantity=10, completed=4, status="in_progress")

        self._run(db)

        # Open orders stay invisible, exactly as before: the full shortage is planned.
        assert _planned_quantity(db, part) == Decimal("10")


# =============================================================================
# The three helpers agree
# =============================================================================

def _three_way(db, product):
    """Incoming quantity for `product` as MRP, supply netting (single and bulk)
    and the item demand summary each report it."""
    mrp = MRPService(db)._get_incoming_supply([product.id]).get(product.id, Decimal("0"))
    single = get_projected_available(db, product.id).incoming_qty
    bulk = get_projected_available_bulk(db, [product.id])[product.id].incoming_qty
    detail_sum = sum((i.quantity for i in get_incoming_supply(db, product.id)), Decimal("0"))
    summary = get_item_demand_summary(db, product.id).quantities.incoming
    return mrp, single, bulk, detail_sum, summary


class TestHelpersAgree:

    def _data(self, db, make_product, make_order, make_vendor, make_purchase_order, make_sales_order):
        part = make_product(procurement_type="make")
        _make_open_po_line(db, make_vendor, make_purchase_order, part, 7)
        make_order(part, quantity=10, completed=3, status="in_progress")        # 7
        make_order(part, quantity=5, status="released")                         # 5
        make_order(part, quantity=4, status="scheduled")                        # 4
        make_order(part, quantity=2, status="draft")                            # 2
        make_order(part, quantity=100, status="cancelled")
        make_order(part, quantity=100, status="complete")
        make_order(part, quantity=100, completed=100, status="in_progress")
        sale = make_sales_order(product_id=part.id, quantity=100)
        make_order(part, quantity=100, status="released", sales_order_id=sale.id)  # committed to a sale
        return part

    def test_flag_on_all_report_the_same_quantity(
        self, db, make_product, make_order, make_vendor, make_purchase_order, make_sales_order, flag_on
    ):
        part = self._data(db, make_product, make_order, make_vendor, make_purchase_order, make_sales_order)

        # 7 on the purchase order + 7 + 5 + 4 + 2 still to make
        assert _three_way(db, part) == (Decimal("25"),) * 5

    def test_flag_off_all_report_only_the_purchase_order(
        self, db, make_product, make_order, make_vendor, make_purchase_order, make_sales_order, flag_off
    ):
        part = self._data(db, make_product, make_order, make_vendor, make_purchase_order, make_sales_order)

        assert _three_way(db, part) == (Decimal("7"),) * 5

    def test_item_demand_lists_production_orders_by_expected_date(
        self, db, make_product, make_order, make_vendor, make_purchase_order, flag_on
    ):
        part = make_product(procurement_type="make")
        today = date.today()
        po = _make_open_po_line(db, make_vendor, make_purchase_order, part, 7)
        po.expected_date = today + timedelta(days=4)
        late = make_order(part, quantity=5, due_date=today + timedelta(days=9))
        early = make_order(part, quantity=2, due_date=today + timedelta(days=1))
        db.flush()

        incoming = get_incoming_supply(db, part.id)

        assert [(i.type, i.reference_id) for i in incoming] == [
            ("production_order", early.id),
            ("purchase_order", po.id),
            ("production_order", late.id),
        ]
        assert incoming[0].vendor is None
        assert incoming[0].reference_code == early.code
        assert incoming[0].expected_date == today + timedelta(days=1)

    def test_supply_netting_keeps_purchase_order_details_separate(
        self, db, make_product, make_order, make_vendor, make_purchase_order, flag_on
    ):
        part = make_product(procurement_type="make")
        po = _make_open_po_line(db, make_vendor, make_purchase_order, part, 7)
        order = make_order(part, quantity=5)

        avail = get_projected_available(db, part.id)

        # `details` is dereferenced as purchase orders by its consumers
        assert [d.purchase_order_id for d in avail.details] == [po.id]
        assert [d.production_order_id for d in avail.production_details] == [order.id]
        assert avail.incoming_qty == Decimal("12")
        assert avail.projected == avail.available + Decimal("12")
