"""
Tests for the consolidated buy list service and endpoint (HARD-7).

Coverage:
- Multi-order demand aggregation for a shared component
- Netting against on-hand + incoming open POs
- Safety-stock floor applied correctly
- Suggested qty respects min_order_qty
- Zero-shortage component excluded from results
- Endpoint: 401 when unauthenticated, 200 when authenticated
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from app.models.inventory import Inventory
from app.models.purchase_order import PurchaseOrderLine
from app.services.buy_list_service import get_buy_list


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_inventory(db, product_id: int, on_hand: Decimal, allocated: Decimal = Decimal("0")):
    inv = Inventory(
        product_id=product_id,
        location_id=1,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


_po_line_counter = [0]


def _add_po_line(db, po, product_id: int, qty_ordered: Decimal, qty_received: Decimal = Decimal("0")):
    _po_line_counter[0] += 1
    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product_id,
        line_number=_po_line_counter[0],
        quantity_ordered=qty_ordered,
        quantity_received=qty_received,
        unit_cost=Decimal("1.00"),
        line_total=qty_ordered * Decimal("1.00"),
    )
    db.add(line)
    db.flush()
    return line


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

class TestBuyListDemandAggregation:
    """Multi-order demand is summed per component."""

    def test_two_orders_sharing_component_aggregates_demand(
        self, db, make_product, make_bom, make_production_order
    ):
        """Two production orders exploding to the same component are summed."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(
            item_type="supply", unit="EA", standard_cost=Decimal("2.00")
        )
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("3"), "unit": "EA"}],
        )

        # No inventory — everything is short
        make_production_order(product_id=fg.id, status="released", quantity=4)
        make_production_order(product_id=fg.id, status="released", quantity=6)

        result = get_buy_list(db)

        short_ids = {item.product_id for item in result.items}
        assert comp.id in short_ids, "Component should appear on the buy list"

        item = next(i for i in result.items if i.product_id == comp.id)
        # Gross = 3 * (4 + 6) = 30
        assert item.gross_demand == Decimal("30"), (
            f"Expected gross_demand=30, got {item.gross_demand}"
        )
        assert item.net_shortage == Decimal("30")

    def test_sales_order_and_production_order_aggregate(
        self, db, make_product, make_bom, make_production_order, make_sales_order
    ):
        """SO and WO exploding to the same component are aggregated."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(
            item_type="supply", unit="EA", standard_cost=Decimal("1.00")
        )
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("2"), "unit": "EA"}],
        )

        # A quote-based sales order with product_id
        make_sales_order(
            product_id=fg.id, quantity=5, status="confirmed",
            order_type="quote_based",
        )
        # A production order
        make_production_order(product_id=fg.id, status="released", quantity=3)

        result = get_buy_list(db)
        item = next((i for i in result.items if i.product_id == comp.id), None)
        assert item is not None
        # Gross = 2*(5+3) = 16
        assert item.gross_demand == Decimal("16")


class TestNettingLogic:
    """Netting: on-hand, allocated, and incoming open-PO supply."""

    def test_on_hand_covers_demand_component_excluded(
        self, db, make_product, make_bom, make_production_order
    ):
        """If on-hand alone covers demand the component is NOT on the buy list."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(item_type="supply", unit="EA")
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("5"), "unit": "EA"}],
        )
        make_production_order(product_id=fg.id, status="released", quantity=2)
        # demand = 10 units; stock = 100
        _add_inventory(db, comp.id, Decimal("100"))

        result = get_buy_list(db)
        ids = {i.product_id for i in result.items}
        assert comp.id not in ids

    def test_incoming_po_covers_shortage(
        self, db, make_product, make_bom, make_production_order, make_purchase_order,
        make_vendor
    ):
        """An open PO that covers the gap means the component is NOT short."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(item_type="supply", unit="EA")
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("10"), "unit": "EA"}],
        )
        make_production_order(product_id=fg.id, status="released", quantity=1)
        # demand = 10; on-hand = 3; incoming = 7 → projected = 10 → not short
        _add_inventory(db, comp.id, Decimal("3"))
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        _add_po_line(db, po, comp.id, Decimal("7"))

        result = get_buy_list(db)
        ids = {i.product_id for i in result.items}
        assert comp.id not in ids, "Incoming PO should cover the gap"

    def test_partial_incoming_leaves_remainder_short(
        self, db, make_product, make_bom, make_production_order, make_purchase_order,
        make_vendor
    ):
        """Incoming PO covers part; remainder shows as net_shortage."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(item_type="supply", unit="EA", standard_cost=Decimal("5.00"))
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("20"), "unit": "EA"}],
        )
        make_production_order(product_id=fg.id, status="released", quantity=1)
        # demand = 20; on-hand = 0; incoming = 8 → projected = 8 → short = 12
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        _add_po_line(db, po, comp.id, Decimal("10"), qty_received=Decimal("2"))

        result = get_buy_list(db)
        item = next((i for i in result.items if i.product_id == comp.id), None)
        assert item is not None
        assert item.net_shortage == Decimal("12")
        assert item.incoming_qty == Decimal("8")


class TestSafetyStockFloor:
    """Safety stock is added to the netting equation."""

    def test_safety_stock_increases_shortage(
        self, db, make_product, make_bom, make_production_order
    ):
        """Safety stock of N means we need N extra units beyond gross demand."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("1.00"),
            safety_stock=Decimal("5"),
        )
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("10"), "unit": "EA"}],
        )
        make_production_order(product_id=fg.id, status="released", quantity=1)
        # demand = 10; on-hand = 8; projected = 8
        # net = max(0, 10 - 8 + 5) = 7
        _add_inventory(db, comp.id, Decimal("8"))

        result = get_buy_list(db)
        item = next((i for i in result.items if i.product_id == comp.id), None)
        assert item is not None
        assert item.net_shortage == Decimal("7"), (
            f"Expected net_shortage=7 (safety_stock=5), got {item.net_shortage}"
        )


class TestMinOrderQty:
    """Suggested qty is max(net_shortage, min_order_qty)."""

    def test_min_order_qty_floors_suggested_qty(
        self, db, make_product, make_bom, make_production_order
    ):
        """If shortage < min_order_qty, suggested_qty = min_order_qty."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("2.00"),
            min_order_qty=Decimal("50"),
        )
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("3"), "unit": "EA"}],
        )
        make_production_order(product_id=fg.id, status="released", quantity=1)
        # demand = 3; on-hand = 0; shortage = 3 < min_order_qty = 50
        result = get_buy_list(db)
        item = next((i for i in result.items if i.product_id == comp.id), None)
        assert item is not None
        assert item.net_shortage == Decimal("3")
        assert item.suggested_qty == Decimal("50"), (
            f"Expected suggested_qty=50 (min_order_qty), got {item.suggested_qty}"
        )

    def test_shortage_exceeds_min_order_qty(
        self, db, make_product, make_bom, make_production_order
    ):
        """If shortage > min_order_qty, suggested_qty = shortage."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("1.00"),
            min_order_qty=Decimal("10"),
        )
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("100"), "unit": "EA"}],
        )
        make_production_order(product_id=fg.id, status="released", quantity=1)
        result = get_buy_list(db)
        item = next((i for i in result.items if i.product_id == comp.id), None)
        assert item is not None
        assert item.suggested_qty == Decimal("100")


class TestZeroShortageExclusion:
    """Components with no shortage are excluded."""

    def test_fully_covered_component_not_in_results(
        self, db, make_product, make_bom, make_production_order
    ):
        """A component fully covered by on-hand does not appear."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(item_type="supply", unit="EA")
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("1"), "unit": "EA"}],
        )
        make_production_order(product_id=fg.id, status="released", quantity=5)
        _add_inventory(db, comp.id, Decimal("1000"))

        result = get_buy_list(db)
        assert all(i.product_id != comp.id for i in result.items)


class TestDraftIncomingVisibility:
    """Draft PO incoming quantity is surfaced in summary and detail."""

    def test_draft_po_counted_in_incoming_and_summary(
        self, db, make_product, make_bom, make_production_order, make_purchase_order,
        make_vendor
    ):
        """Draft POs appear in incoming_details and contribute to summary.draft_incoming_qty."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(
            item_type="supply", unit="EA", standard_cost=Decimal("3.00")
        )
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("20"), "unit": "EA"}],
        )
        make_production_order(product_id=fg.id, status="released", quantity=1)
        # Draft PO covers 5 of the 20 needed → comp still short by 15
        vendor = make_vendor()
        draft_po = make_purchase_order(vendor_id=vendor.id, status="draft")
        _add_po_line(db, draft_po, comp.id, Decimal("5"))

        result = get_buy_list(db)
        item = next((i for i in result.items if i.product_id == comp.id), None)
        assert item is not None
        assert item.net_shortage == Decimal("15")
        # Draft supply should be visible in details
        draft_details = [d for d in item.incoming_details if d.status == "draft"]
        assert len(draft_details) == 1
        assert draft_details[0].quantity == Decimal("5")
        # Summary tracks draft supply
        assert result.summary.draft_incoming_qty >= Decimal("5")


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------

class TestBuyListEndpoint:
    """Endpoint auth and basic response shape."""

    def test_unauthenticated_returns_401(self, unauthed_client):
        response = unauthed_client.get("/api/v1/buy-list")
        assert response.status_code == 401

    def test_authenticated_returns_200(self, client):
        response = client.get("/api/v1/buy-list")
        assert response.status_code == 200
        body = response.json()
        assert "summary" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_vendor_filter_accepted(self, client):
        """vendor_id filter is accepted without error (may return empty list)."""
        response = client.get("/api/v1/buy-list?vendor_id=9999")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []


# ---------------------------------------------------------------------------
# Phase-B sweep: Finding 3 — buy-list netting must not double-count allocations
# ---------------------------------------------------------------------------

class TestBuyListNoDoubleCount:
    """
    Regression: open WOs that created allocations must not cause double-counting.

    Scenario:
    - Component C has on_hand=100, allocated=60 (by an open WO).
    - The same open WO also generates gross_demand=60 for C via BOM explosion.
    - Old formula: net = gross − (on_hand − allocated + incoming) + ss
                       = 60 − (100 − 60 + 0) + 0 = 60 − 40 = 20  ← WRONG
    - Fixed formula: net = gross − (on_hand + incoming) + ss
                        = 60 − (100 + 0) + 0 = 0  ← covered, not on buy list
    """

    def test_component_reserved_by_open_wo_not_double_shorted(
        self, db, make_product, make_bom, make_production_order
    ):
        """An open WO's allocations must not generate a false shortage.

        If on_hand fully covers gross demand and the allocations are already
        captured inside gross_demand, net_shortage must be zero and the
        component must NOT appear on the buy list.
        """
        from app.models.inventory import Inventory as InvModel

        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(item_type="supply", unit="EA", standard_cost=Decimal("1.00"))
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("3"), "unit": "EA"}],
        )

        # Open WO for 10 units → gross_demand for comp = 30
        make_production_order(product_id=fg.id, status="released", quantity=10)

        # on_hand=30, allocated=30 (represents the reservations the WO created)
        # available = 30 − 30 = 0, but on_hand alone covers the demand
        inv = InvModel(
            product_id=comp.id,
            location_id=1,
            on_hand_quantity=Decimal("30"),
            allocated_quantity=Decimal("30"),
        )
        db.add(inv)
        db.flush()

        result = get_buy_list(db)
        ids = {item.product_id for item in result.items}
        assert comp.id not in ids, (
            "Component whose WO-driven allocations match on_hand must NOT appear "
            "on the buy list (double-count regression)"
        )

    def test_component_reserved_by_wo_in_gross_demand_shortage_correct(
        self, db, make_product, make_bom, make_production_order
    ):
        """When on_hand is genuinely insufficient (even ignoring allocations),
        the shortage is computed against on_hand + incoming — not available."""
        from app.models.inventory import Inventory as InvModel

        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        comp = make_product(item_type="supply", unit="EA", standard_cost=Decimal("2.00"))
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": comp.id, "quantity": Decimal("5"), "unit": "EA"}],
        )

        # Open WO for 10 → gross_demand = 50
        make_production_order(product_id=fg.id, status="released", quantity=10)

        # on_hand=30, allocated=30 → available=-0 but on_hand < demand
        # Fixed: shortage = max(0, 50 − 30) = 20  (not 50 − 0 = 50)
        inv = InvModel(
            product_id=comp.id,
            location_id=1,
            on_hand_quantity=Decimal("30"),
            allocated_quantity=Decimal("30"),
        )
        db.add(inv)
        db.flush()

        result = get_buy_list(db)
        item = next((i for i in result.items if i.product_id == comp.id), None)
        assert item is not None, "Component with genuine shortage must appear on buy list"
        assert item.net_shortage == Decimal("20"), (
            f"Expected net_shortage=20 (50 − 30), got {item.net_shortage}"
        )
