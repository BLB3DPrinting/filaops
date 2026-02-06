"""
Extended MRP planning tests — covers uncovered lines in app/services/mrp.py.

Focus areas (by uncovered line ranges):
- Sales Order demand inclusion (lines 220-289)
- MRP run failure handling (lines 343-348)
- Sub-assembly cascading (lines 321-323)
- Shipping material requirements (lines 862-931)
- Sales orders within horizon filtering (lines 951-1004)
- Supply/demand timeline (lines 1187-1329)
- Purchase/production order creation from planned orders (lines 1083-1088, 1127-1128, 1142-1143)
- Planned order date logic for sub-assembly cascading (lines 719-734)

Run with:
    cd backend
    pytest tests/services/test_mrp_planning.py -v
"""
import uuid
import pytest
from unittest.mock import patch
from decimal import Decimal
from datetime import date, timedelta, datetime, timezone

from app.services.mrp import (
    MRPService, convert_uom,
    ComponentRequirement, NetRequirement, MRPResult,
)
from app.models.mrp import MRPRun, PlannedOrder
from app.models.bom import BOM, BOMLine
from app.models.inventory import Inventory
from app.models.production_order import ProductionOrder
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.sales_order import SalesOrder, SalesOrderLine


def _uid():
    """Short unique suffix."""
    return uuid.uuid4().hex[:8]


# =============================================================================
# Helper to create a production order
# =============================================================================

def _make_production_order(db, product, *, quantity=10, status="released", due_days=7, completed=0):
    """Insert a ProductionOrder directly."""
    po = ProductionOrder(
        code=f"PO-TEST-{_uid()}",
        product_id=product.id,
        quantity_ordered=Decimal(str(quantity)),
        quantity_completed=Decimal(str(completed)),
        quantity_scrapped=Decimal("0"),
        status=status,
        source="manual",
        due_date=date.today() + timedelta(days=due_days),
    )
    db.add(po)
    db.flush()
    return po


def _make_mrp_run(db):
    """Insert an MRPRun record and return it."""
    run = MRPRun(
        run_date=datetime.now(timezone.utc),
        planning_horizon_days=30,
        status="running",
    )
    db.add(run)
    db.flush()
    return run


def _make_planned_order(db, product, *, order_type="purchase", status="planned", quantity=100):
    """Insert a PlannedOrder directly."""
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


def _make_sales_order(db, product, *, order_type="quote_based", status="confirmed",
                      quantity=5, days_ago=0):
    """Insert a SalesOrder directly."""
    uid = _uid()
    so = SalesOrder(
        order_number=f"SO-TEST-{uid}",
        user_id=1,
        product_id=product.id if order_type == "quote_based" else None,
        product_name=product.name if product else f"Test {uid}",
        quantity=quantity,
        material_type="PLA",
        unit_price=Decimal("10.00"),
        total_price=Decimal(str(10 * quantity)),
        grand_total=Decimal(str(10 * quantity)),
        status=status,
        order_type=order_type,
        estimated_completion_date=datetime.now(timezone.utc) - timedelta(days=days_ago),
    )
    db.add(so)
    db.flush()
    return so


def _make_inventory(db, product_id, on_hand, allocated=0, location_id=1):
    """Insert an Inventory record."""
    inv = Inventory(
        product_id=product_id,
        location_id=location_id,
        on_hand_quantity=Decimal(str(on_hand)),
        allocated_quantity=Decimal(str(allocated)),
    )
    db.add(inv)
    db.flush()
    return inv


# =============================================================================
# Sales Order demand in MRP (lines 220-289)
# =============================================================================

class TestMrpSalesOrderDemand:
    """Test sales order inclusion in MRP run (INCLUDE_SALES_ORDERS_IN_MRP)."""

    def test_quote_based_sales_orders_generate_demand(self, db, make_product, make_bom):
        """Quote-based sales orders explode BOMs and create demand."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(item_type="supply", unit="G", is_raw_material=True)
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        _make_sales_order(db, fg, order_type="quote_based", quantity=3)

        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = True
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = False

            svc = MRPService(db)
            result = svc.run_mrp(planning_horizon_days=30, user_id=1)

        assert result.components_analyzed >= 1
        assert result.errors == []

    def test_line_item_sales_orders_generate_demand(self, db, make_product, make_bom):
        """Line-item sales orders explode BOMs per line."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(item_type="supply", unit="EA", is_raw_material=True)
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("2"), "unit": "EA"},
        ])

        so = _make_sales_order(db, fg, order_type="line_item", quantity=1)
        # Add a line item
        sol = SalesOrderLine(
            sales_order_id=so.id,
            product_id=fg.id,
            quantity=Decimal("4"),
            unit_price=Decimal("10.00"),
            total=Decimal("40.00"),
        )
        db.add(sol)
        db.flush()

        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = True
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = False

            svc = MRPService(db)
            result = svc.run_mrp(planning_horizon_days=30, user_id=1)

        assert result.components_analyzed >= 1

    def test_sales_order_error_gracefully_handled(self, db, make_product):
        """Errors processing sales orders append to result.errors but do not break MRP."""
        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = True
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = False

            svc = MRPService(db)
            # Patch the method to raise an exception
            with patch.object(svc, "_get_sales_orders_within_horizon", side_effect=RuntimeError("boom")):
                result = svc.run_mrp(planning_horizon_days=30, user_id=1)

        assert any("Sales Orders" in e for e in result.errors)
        # MRP still completed (graceful degradation)
        run = db.query(MRPRun).get(result.run_id)
        assert run.status == "completed"

    def test_cancelled_sales_orders_excluded_from_horizon(self, db, make_product):
        """Cancelled sales orders are excluded from the horizon query."""
        fg = make_product(item_type="finished_good", unit="EA")
        _make_sales_order(db, fg, status="cancelled", quantity=10)

        svc = MRPService(db)
        horizon = date.today() + timedelta(days=30)
        orders = svc._get_sales_orders_within_horizon(horizon)

        so_ids = [o.id for o in orders]
        # We cannot guarantee our cancelled order id, but it should not appear
        for o in orders:
            assert o.status != "cancelled"


# =============================================================================
# MRP run failure handling (lines 343-348)
# =============================================================================

class TestMrpRunFailure:
    """Test that MRP run records failure status on exception."""

    def test_run_mrp_records_failure_on_exception(self, db, make_product):
        """If an exception occurs mid-run, the MRPRun is marked as failed."""
        svc = MRPService(db)

        with patch.object(svc, "_get_production_orders", side_effect=RuntimeError("db crash")):
            with pytest.raises(RuntimeError, match="db crash"):
                svc.run_mrp(planning_horizon_days=30, user_id=1)

        # The MRPRun record should exist and be in 'failed' status
        failed_runs = db.query(MRPRun).filter(MRPRun.status == "failed").all()
        assert len(failed_runs) >= 1
        latest = failed_runs[-1]
        assert "db crash" in latest.error_message


# =============================================================================
# Sub-assembly cascading (lines 316-323, 719-734)
# =============================================================================

class TestSubAssemblyCascading:
    """Test MRP_ENABLE_SUB_ASSEMBLY_CASCADING for date cascading."""

    def test_sub_assembly_cascading_adjusts_dates(self, db, make_product, make_bom):
        """With sub-assembly cascading, sub-assembly due dates are computed from parent."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        sub = make_product(
            item_type="component", procurement_type="make",
            has_bom=True, unit="EA", lead_time_days=5,
        )
        raw = make_product(item_type="supply", unit="EA", is_raw_material=True)

        # FG -> sub -> raw
        make_bom(product_id=fg.id, lines=[
            {"component_id": sub.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        make_bom(product_id=sub.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("10"), "unit": "EA"},
        ])

        _make_production_order(db, fg, quantity=5, due_days=20)

        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = False
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = True

            svc = MRPService(db)
            result = svc.run_mrp(planning_horizon_days=30, user_id=1)

        assert result.shortages_found >= 1
        assert result.planned_orders_created >= 1

    def test_cascading_due_date_not_in_past(self, db, make_product, make_bom):
        """Cascaded due dates are capped at today if they would be in the past."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        sub = make_product(
            item_type="component", procurement_type="make",
            has_bom=True, unit="EA", lead_time_days=30,
        )
        raw = make_product(item_type="supply", unit="EA", is_raw_material=True)

        make_bom(product_id=fg.id, lines=[
            {"component_id": sub.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        make_bom(product_id=sub.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("1"), "unit": "EA"},
        ])

        # Due in 2 days, but sub has 30 day lead time -> due_date would be negative
        _make_production_order(db, fg, quantity=1, due_days=2)

        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = False
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = True

            svc = MRPService(db)
            result = svc.run_mrp(planning_horizon_days=30, user_id=1)

        # All planned orders should have start_date >= today
        planned = db.query(PlannedOrder).filter(
            PlannedOrder.mrp_run_id == result.run_id,
        ).all()
        for po in planned:
            assert po.start_date >= date.today()
            assert po.due_date >= date.today()


# =============================================================================
# Generate planned orders — sub-assembly cascading date path (lines 715-748)
# =============================================================================

class TestGeneratePlannedOrdersCascading:
    """Test generate_planned_orders with parent_due_date for sub-assembly cascading."""

    def _make_shortage(self, product, shortage_qty, has_bom=False, lead_time_days=7, min_order_qty=None):
        return NetRequirement(
            product_id=product.id,
            product_sku=product.sku,
            product_name=product.name,
            gross_quantity=shortage_qty,
            on_hand_quantity=Decimal("0"),
            allocated_quantity=Decimal("0"),
            available_quantity=Decimal("0"),
            incoming_quantity=Decimal("0"),
            safety_stock=Decimal("0"),
            net_shortage=shortage_qty,
            lead_time_days=lead_time_days,
            has_bom=has_bom,
            min_order_qty=min_order_qty,
        )

    def test_production_order_with_parent_due_date(self, db, make_product):
        """Sub-assembly production order uses parent_due_date for scheduling."""
        sub = make_product(
            item_type="component", unit="EA",
            procurement_type="make", has_bom=True, lead_time_days=5,
        )
        mrp_run = _make_mrp_run(db)
        shortage = self._make_shortage(sub, Decimal("20"), has_bom=True, lead_time_days=5)

        parent_due = date.today() + timedelta(days=20)

        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = True

            svc = MRPService(db)
            orders = svc.generate_planned_orders(
                [shortage], int(mrp_run.id), user_id=1, parent_due_date=parent_due,
            )

        assert len(orders) == 1
        order = orders[0]
        assert order.order_type == "production"
        # Due date should be parent_due - (lead_time + buffer)
        expected_due = parent_due - timedelta(days=5 + 1)
        assert order.due_date == expected_due

    def test_purchase_order_ignores_parent_due_date(self, db, make_product):
        """Purchase orders use standard date logic even with parent_due_date."""
        raw = make_product(item_type="supply", unit="EA", is_raw_material=True)
        mrp_run = _make_mrp_run(db)
        shortage = self._make_shortage(raw, Decimal("50"), has_bom=False, lead_time_days=7)

        parent_due = date.today() + timedelta(days=20)

        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = True

            svc = MRPService(db)
            orders = svc.generate_planned_orders(
                [shortage], int(mrp_run.id), user_id=1, parent_due_date=parent_due,
            )

        assert len(orders) == 1
        assert orders[0].order_type == "purchase"
        # Purchase orders use the default 2-week due date, not parent_due_date
        assert orders[0].due_date == date.today() + timedelta(days=14)

    def test_cascading_start_date_clamped_to_today(self, db, make_product):
        """Start dates that would be in the past are capped to today."""
        sub = make_product(
            item_type="component", unit="EA",
            procurement_type="make", has_bom=True, lead_time_days=10,
        )
        mrp_run = _make_mrp_run(db)
        shortage = self._make_shortage(sub, Decimal("5"), has_bom=True, lead_time_days=10)

        # Parent due in 5 days, sub lead time 10 days -> computed due = 5 - 11 < 0 -> capped
        parent_due = date.today() + timedelta(days=5)

        with patch("app.services.mrp.settings") as mock_settings:
            mock_settings.MRP_ENABLE_SUB_ASSEMBLY_CASCADING = True

            svc = MRPService(db)
            orders = svc.generate_planned_orders(
                [shortage], int(mrp_run.id), user_id=1, parent_due_date=parent_due,
            )

        assert len(orders) == 1
        order = orders[0]
        assert order.start_date >= date.today()
        assert order.due_date >= order.start_date


# =============================================================================
# Shipping material requirements (lines 862-931)
# =============================================================================

class TestShippingMaterialRequirements:
    """Test _get_shipping_material_requirements."""

    def test_shipping_materials_from_quote_based_order(self, db, make_product):
        """Shipping stage BOM lines are picked up for quote-based SOs."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        box = make_product(item_type="supply", unit="EA", name="Shipping Box")

        bom = BOM(product_id=fg.id, name="BOM-ship-test", active=True)
        db.add(bom)
        db.flush()

        # Shipping-stage BOM line
        line = BOMLine(
            bom_id=bom.id, component_id=box.id,
            quantity=Decimal("1"), unit="EA",
            consume_stage="shipping", is_cost_only=False,
            sequence=10,
        )
        db.add(line)
        db.flush()

        so = _make_sales_order(db, fg, order_type="quote_based", quantity=3)
        horizon = date.today() + timedelta(days=30)

        svc = MRPService(db)
        reqs = svc._get_shipping_material_requirements([so], horizon)

        assert len(reqs) == 1
        assert reqs[0].product_id == box.id
        assert reqs[0].gross_quantity == Decimal("3")
        assert reqs[0].source_demand_type == "sales_order_shipping"

    def test_shipping_materials_from_line_item_order(self, db, make_product):
        """Line-item orders also pick up shipping materials."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        box = make_product(item_type="supply", unit="EA", name="Box LI")

        bom = BOM(product_id=fg.id, name="BOM-ship-li", active=True)
        db.add(bom)
        db.flush()

        line = BOMLine(
            bom_id=bom.id, component_id=box.id,
            quantity=Decimal("2"), unit="EA",
            consume_stage="shipping", is_cost_only=False,
            sequence=10,
        )
        db.add(line)
        db.flush()

        so = _make_sales_order(db, fg, order_type="line_item", quantity=1)
        sol = SalesOrderLine(
            sales_order_id=so.id, product_id=fg.id,
            quantity=Decimal("6"), unit_price=Decimal("10"), total=Decimal("60"),
        )
        db.add(sol)
        db.flush()

        horizon = date.today() + timedelta(days=30)
        svc = MRPService(db)
        reqs = svc._get_shipping_material_requirements([so], horizon)

        assert len(reqs) == 1
        # 6 units * 2 boxes each = 12
        assert reqs[0].gross_quantity == Decimal("12")

    def test_cancelled_order_skipped(self, db, make_product):
        """Cancelled sales orders are skipped for shipping materials."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        box = make_product(item_type="supply", unit="EA")

        bom = BOM(product_id=fg.id, name="BOM-skip-cancel", active=True)
        db.add(bom)
        db.flush()

        line = BOMLine(
            bom_id=bom.id, component_id=box.id,
            quantity=Decimal("1"), unit="EA",
            consume_stage="shipping", is_cost_only=False,
            sequence=10,
        )
        db.add(line)
        db.flush()

        so = _make_sales_order(db, fg, status="cancelled", quantity=5)
        horizon = date.today() + timedelta(days=30)

        svc = MRPService(db)
        reqs = svc._get_shipping_material_requirements([so], horizon)

        assert len(reqs) == 0

    def test_cost_only_lines_skipped(self, db, make_product):
        """BOM lines with is_cost_only=True are not included in shipping materials."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        overhead = make_product(item_type="service", unit="EA")

        bom = BOM(product_id=fg.id, name="BOM-cost-only", active=True)
        db.add(bom)
        db.flush()

        line = BOMLine(
            bom_id=bom.id, component_id=overhead.id,
            quantity=Decimal("1"), unit="EA",
            consume_stage="shipping", is_cost_only=True,
            sequence=10,
        )
        db.add(line)
        db.flush()

        so = _make_sales_order(db, fg, order_type="quote_based", quantity=1)
        horizon = date.today() + timedelta(days=30)

        svc = MRPService(db)
        reqs = svc._get_shipping_material_requirements([so], horizon)

        assert len(reqs) == 0

    def test_shipping_materials_with_scrap_factor(self, db, make_product):
        """Scrap factor on shipping BOM line increases quantity."""
        fg = make_product(item_type="finished_good", unit="EA", has_bom=True)
        box = make_product(item_type="supply", unit="EA")

        bom = BOM(product_id=fg.id, name="BOM-scrap-ship", active=True)
        db.add(bom)
        db.flush()

        line = BOMLine(
            bom_id=bom.id, component_id=box.id,
            quantity=Decimal("1"), unit="EA",
            consume_stage="shipping", is_cost_only=False,
            scrap_factor=Decimal("10"),  # 10%
            sequence=10,
        )
        db.add(line)
        db.flush()

        so = _make_sales_order(db, fg, order_type="quote_based", quantity=10)
        horizon = date.today() + timedelta(days=30)

        svc = MRPService(db)
        reqs = svc._get_shipping_material_requirements([so], horizon)

        assert len(reqs) == 1
        # 10 * 1 * 1.1 = 11
        assert reqs[0].gross_quantity == Decimal("11.0")

    def test_no_bom_no_shipping_materials(self, db, make_product):
        """Product without a BOM returns no shipping materials."""
        fg = make_product(item_type="finished_good", unit="EA")
        so = _make_sales_order(db, fg, order_type="quote_based", quantity=3)
        horizon = date.today() + timedelta(days=30)

        svc = MRPService(db)
        reqs = svc._get_shipping_material_requirements([so], horizon)

        assert len(reqs) == 0


# =============================================================================
# Sales orders within horizon (lines 951-1004)
# =============================================================================

class TestSalesOrdersWithinHorizon:
    """Test _get_sales_orders_within_horizon filtering logic."""

    def test_excludes_orders_with_linked_production_orders(self, db, make_product):
        """Orders that already have a linked ProductionOrder are excluded."""
        fg = make_product(item_type="finished_good", unit="EA")
        so = _make_sales_order(db, fg, status="confirmed", quantity=5)

        # Link a production order to this SO
        _make_production_order(db, fg, quantity=5, status="released")
        po = db.query(ProductionOrder).filter(
            ProductionOrder.product_id == fg.id,
        ).first()
        po.sales_order_id = so.id
        db.flush()

        horizon = date.today() + timedelta(days=30)
        svc = MRPService(db)
        orders = svc._get_sales_orders_within_horizon(horizon)

        so_ids = [o.id for o in orders]
        assert so.id not in so_ids

    def test_line_item_order_with_products_included(self, db, make_product):
        """Line-item orders with product lines are included."""
        fg = make_product(item_type="finished_good", unit="EA")
        so = _make_sales_order(db, fg, order_type="line_item", quantity=1)
        sol = SalesOrderLine(
            sales_order_id=so.id, product_id=fg.id,
            quantity=Decimal("2"), unit_price=Decimal("10"), total=Decimal("20"),
        )
        db.add(sol)
        db.flush()

        horizon = date.today() + timedelta(days=30)
        svc = MRPService(db)
        orders = svc._get_sales_orders_within_horizon(horizon)

        so_ids = [o.id for o in orders]
        assert so.id in so_ids

    def test_line_item_order_without_products_excluded(self, db, make_product):
        """Line-item orders with no product lines are excluded."""
        fg = make_product(item_type="finished_good", unit="EA")
        so = _make_sales_order(db, fg, order_type="line_item", quantity=1)
        # No lines added

        horizon = date.today() + timedelta(days=30)
        svc = MRPService(db)
        orders = svc._get_sales_orders_within_horizon(horizon)

        so_ids = [o.id for o in orders]
        assert so.id not in so_ids

    def test_quote_based_without_product_excluded(self, db):
        """Quote-based order without product_id is excluded."""
        uid = _uid()
        so = SalesOrder(
            order_number=f"SO-NOPROD-{uid}",
            user_id=1,
            product_id=None,
            product_name="No product",
            quantity=1,
            material_type="PLA",
            unit_price=Decimal("10"),
            total_price=Decimal("10"),
            grand_total=Decimal("10"),
            status="confirmed",
            order_type="quote_based",
            estimated_completion_date=datetime.now(timezone.utc),
        )
        db.add(so)
        db.flush()

        horizon = date.today() + timedelta(days=30)
        svc = MRPService(db)
        orders = svc._get_sales_orders_within_horizon(horizon)

        so_ids = [o.id for o in orders]
        assert so.id not in so_ids


# =============================================================================
# Supply/Demand Timeline (lines 1187-1329)
# =============================================================================

class TestSupplyDemandTimeline:
    """Test get_supply_demand_timeline."""

    def test_timeline_for_product_with_no_events(self, db, make_product):
        """Product with no supply/demand shows only on-hand entry."""
        product = make_product(item_type="supply", unit="EA")
        _make_inventory(db, product.id, on_hand=100)

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        assert timeline["product_id"] == product.id
        assert timeline["product_sku"] == product.sku
        assert timeline["current_on_hand"] == Decimal("100")
        assert len(timeline["entries"]) >= 1
        assert timeline["entries"][0]["entry_type"] == "on_hand"
        assert timeline["entries"][0]["running_balance"] == Decimal("100")

    def test_timeline_includes_purchase_order_supply(self, db, make_product, make_vendor, make_purchase_order):
        """Open PO lines appear as supply events."""
        product = make_product(item_type="supply", unit="EA")
        _make_inventory(db, product.id, on_hand=50)

        vendor = make_vendor()
        po = make_purchase_order(
            vendor_id=vendor.id, status="ordered",
            expected_date=date.today() + timedelta(days=5),
        )
        po_line = PurchaseOrderLine(
            purchase_order_id=po.id, product_id=product.id,
            line_number=1,
            quantity_ordered=Decimal("100"), quantity_received=Decimal("0"),
            unit_cost=Decimal("1"), line_total=Decimal("100"),
        )
        db.add(po_line)
        db.flush()

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        supply_events = [e for e in timeline["entries"] if e["entry_type"] == "supply"]
        assert len(supply_events) >= 1
        po_supply = [s for s in supply_events if s["source_type"] == "purchase_order"]
        assert len(po_supply) >= 1
        assert po_supply[0]["quantity"] == Decimal("100")

    def test_timeline_includes_planned_order_supply(self, db, make_product):
        """Planned orders appear as supply events in the timeline."""
        product = make_product(item_type="supply", unit="EA")
        _make_inventory(db, product.id, on_hand=10)
        _make_planned_order(db, product, quantity=200)

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        supply_events = [e for e in timeline["entries"] if e["entry_type"] == "supply"]
        planned_events = [s for s in supply_events if s["source_type"] == "planned_order"]
        assert len(planned_events) >= 1
        assert planned_events[0]["quantity"] == Decimal("200")

    def test_timeline_shortage_date_detection(self, db, make_product):
        """Timeline detects projected shortage date based on safety stock."""
        product = make_product(
            item_type="supply", unit="EA", safety_stock=Decimal("50"),
        )
        # On hand is 10, safety stock is 50 -> immediate shortage
        _make_inventory(db, product.id, on_hand=10)

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        # Since on-hand (10) < safety_stock (50), shortage date should be today
        assert timeline["projected_shortage_date"] is not None
        assert timeline["projected_shortage_date"] == date.today()

    def test_timeline_no_shortage_when_sufficient(self, db, make_product):
        """No shortage date when inventory exceeds safety stock."""
        product = make_product(
            item_type="supply", unit="EA", safety_stock=Decimal("5"),
        )
        _make_inventory(db, product.id, on_hand=1000)

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        assert timeline["projected_shortage_date"] is None

    def test_timeline_nonexistent_product_raises(self, db):
        """Non-existent product raises ValueError."""
        svc = MRPService(db)
        with pytest.raises(ValueError, match="not found"):
            svc.get_supply_demand_timeline(999999)

    def test_timeline_days_of_supply_none_when_no_demand(self, db, make_product):
        """Days of supply is None when there is no demand."""
        product = make_product(item_type="supply", unit="EA")
        _make_inventory(db, product.id, on_hand=100)

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        assert timeline["days_of_supply"] is None

    def test_timeline_no_inventory(self, db, make_product):
        """Product with no inventory record shows zero balances."""
        product = make_product(item_type="supply", unit="EA")

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        assert timeline["current_on_hand"] == Decimal("0")
        assert timeline["current_available"] == Decimal("0")

    def test_timeline_allocated_reduces_available(self, db, make_product):
        """Allocated inventory reduces available balance in the timeline."""
        product = make_product(item_type="supply", unit="EA")
        _make_inventory(db, product.id, on_hand=100, allocated=30)

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        assert timeline["current_on_hand"] == Decimal("100")
        assert timeline["current_available"] == Decimal("70")

    def test_timeline_partial_po_receipt(self, db, make_product, make_vendor, make_purchase_order):
        """Partially received PO line shows only remaining incoming."""
        product = make_product(item_type="supply", unit="EA")
        _make_inventory(db, product.id, on_hand=0)

        vendor = make_vendor()
        po = make_purchase_order(
            vendor_id=vendor.id, status="partially_received",
            expected_date=date.today() + timedelta(days=3),
        )
        po_line = PurchaseOrderLine(
            purchase_order_id=po.id, product_id=product.id,
            line_number=1,
            quantity_ordered=Decimal("100"), quantity_received=Decimal("40"),
            unit_cost=Decimal("1"), line_total=Decimal("100"),
        )
        db.add(po_line)
        db.flush()

        svc = MRPService(db)
        timeline = svc.get_supply_demand_timeline(product.id, days_ahead=30)

        po_supply = [
            e for e in timeline["entries"]
            if e["entry_type"] == "supply" and e["source_type"] == "purchase_order"
        ]
        assert len(po_supply) >= 1
        assert po_supply[0]["quantity"] == Decimal("60")  # 100 - 40


# =============================================================================
# Create PO from planned order (lines 1083-1088, 1127-1128)
# =============================================================================

class TestCreatePurchaseOrderFromPlanned:
    """Test _create_purchase_order."""

    def _cleanup_purchase_orders(self, db):
        """Remove leftover POs to avoid po_number collision."""
        from sqlalchemy import text
        year = datetime.now(timezone.utc).year
        pattern = f"PO-{year}-%"
        db.execute(text(
            "UPDATE material_lots SET purchase_order_id = NULL "
            "WHERE purchase_order_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :pattern)"
        ), {"pattern": pattern})
        db.execute(text(
            "UPDATE planned_orders SET converted_to_po_id = NULL "
            "WHERE converted_to_po_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :pattern)"
        ), {"pattern": pattern})
        db.execute(text(
            "DELETE FROM purchase_order_lines WHERE purchase_order_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :pattern)"
        ), {"pattern": pattern})
        db.execute(text(
            "DELETE FROM purchase_order_documents WHERE purchase_order_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :pattern)"
        ), {"pattern": pattern})
        db.execute(text(
            "DELETE FROM purchase_orders WHERE po_number LIKE :pattern"
        ), {"pattern": pattern})
        db.commit()

    def test_creates_po_with_correct_totals(self, db, make_product, make_vendor):
        """Created PO has correct subtotal and total_amount."""
        self._cleanup_purchase_orders(db)

        product = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("5.00"),
        )
        vendor = make_vendor()
        planned = _make_planned_order(db, product, quantity=20)

        svc = MRPService(db)
        po_id = svc._create_purchase_order(planned, vendor.id, user_id=1)

        po = db.query(PurchaseOrder).get(po_id)
        assert po.subtotal == Decimal("100.0000")  # 20 * 5.00
        assert po.total_amount == Decimal("100.0000")

    def test_po_number_increments(self, db, make_product, make_vendor):
        """Successive POs get incrementing numbers."""
        self._cleanup_purchase_orders(db)

        product = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("1.00"),
        )
        vendor = make_vendor()

        planned1 = _make_planned_order(db, product, quantity=10)
        planned2 = _make_planned_order(db, product, quantity=10)

        svc = MRPService(db)
        po_id1 = svc._create_purchase_order(planned1, vendor.id, user_id=1)
        po_id2 = svc._create_purchase_order(planned2, vendor.id, user_id=1)

        po1 = db.query(PurchaseOrder).get(po_id1)
        po2 = db.query(PurchaseOrder).get(po_id2)

        num1 = int(po1.po_number.split("-")[2])
        num2 = int(po2.po_number.split("-")[2])
        assert num2 == num1 + 1


# =============================================================================
# Create MO from planned order (lines 1129-1171, 1142-1143)
# =============================================================================

class TestCreateProductionOrderFromPlanned:
    """Test _create_production_order."""

    def test_creates_mo_with_bom(self, db, make_product, make_bom):
        """MO references the active BOM."""
        fg = make_product(
            item_type="finished_good", unit="EA",
            procurement_type="make", has_bom=True,
        )
        raw = make_product(item_type="supply", unit="EA")
        bom = make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("1"), "unit": "EA"},
        ])

        planned = _make_planned_order(db, fg, order_type="production", quantity=30)

        svc = MRPService(db)
        mo_id = svc._create_production_order(planned, user_id=1)

        mo = db.query(ProductionOrder).get(mo_id)
        assert mo is not None
        assert mo.product_id == fg.id
        assert mo.bom_id == bom.id
        assert mo.quantity_ordered == Decimal("30")
        assert mo.source == "mrp_planned"

    def test_creates_mo_without_bom(self, db, make_product):
        """MO without active BOM sets bom_id to None."""
        fg = make_product(
            item_type="finished_good", unit="EA",
            procurement_type="make", has_bom=True,
        )
        planned = _make_planned_order(db, fg, order_type="production", quantity=5)

        svc = MRPService(db)
        mo_id = svc._create_production_order(planned, user_id=1)

        mo = db.query(ProductionOrder).get(mo_id)
        assert mo is not None
        assert mo.bom_id is None

    def test_mo_code_increments(self, db, make_product):
        """Successive MOs get incrementing codes."""
        fg = make_product(
            item_type="finished_good", unit="EA",
            procurement_type="make", has_bom=True,
        )
        planned1 = _make_planned_order(db, fg, order_type="production", quantity=1)
        planned2 = _make_planned_order(db, fg, order_type="production", quantity=1)

        svc = MRPService(db)
        mo_id1 = svc._create_production_order(planned1, user_id=1)
        mo_id2 = svc._create_production_order(planned2, user_id=1)

        mo1 = db.query(ProductionOrder).get(mo_id1)
        mo2 = db.query(ProductionOrder).get(mo_id2)

        num1 = int(mo1.code.split("-")[2])
        num2 = int(mo2.code.split("-")[2])
        assert num2 == num1 + 1


# =============================================================================
# MRPResult and DataClass basics
# =============================================================================

class TestMRPDataClasses:
    """Test MRP data classes."""

    def test_mrp_result_defaults(self):
        """MRPResult has correct default values."""
        result = MRPResult(run_id=1)
        assert result.run_id == 1
        assert result.orders_processed == 0
        assert result.components_analyzed == 0
        assert result.shortages_found == 0
        assert result.planned_orders_created == 0
        assert result.requirements == []
        assert result.errors == []

    def test_component_requirement_defaults(self):
        """ComponentRequirement has correct default values."""
        req = ComponentRequirement(
            product_id=1,
            product_sku="TEST",
            product_name="Test",
            bom_level=0,
            gross_quantity=Decimal("100"),
        )
        assert req.scrap_factor == Decimal("0")
        assert req.parent_product_id is None
        assert req.source_demand_type is None

    def test_net_requirement_defaults(self):
        """NetRequirement has correct default values."""
        nr = NetRequirement(
            product_id=1,
            product_sku="TEST",
            product_name="Test",
            gross_quantity=Decimal("100"),
            on_hand_quantity=Decimal("0"),
            allocated_quantity=Decimal("0"),
            available_quantity=Decimal("0"),
            incoming_quantity=Decimal("0"),
            safety_stock=Decimal("0"),
            net_shortage=Decimal("100"),
            lead_time_days=7,
        )
        assert nr.item_type == "component"
        assert nr.has_bom is False
        assert nr.unit_cost == Decimal("0")
        assert nr.reorder_point is None
        assert nr.min_order_qty is None
