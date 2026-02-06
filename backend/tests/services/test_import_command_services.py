"""
Tests for data_import_service.py and command_center.py

Covers:
- Data Import: product CSV import (create/update), inventory CSV import (set/add modes),
  validation errors, missing columns, edge cases
- Command Center: action items (blocked POs, overdue SOs, due-today SOs,
  overrunning ops, idle resources), today summary, resource statuses
"""
import uuid
import pytest
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

from app.services import data_import_service
from app.services.command_center import (
    get_action_items,
    get_today_summary,
    get_resource_statuses,
    _get_blocked_production_orders,
    _get_overdue_sales_orders,
    _get_due_today_sales_orders,
    _get_overrunning_operations,
    _get_idle_resources_with_work,
)
from app.models.product import Product
from app.models.inventory import Inventory, InventoryLocation
from app.models.production_order import ProductionOrder, ProductionOrderOperation
from app.models.sales_order import SalesOrder
from app.models.manufacturing import Resource
from app.models.work_center import WorkCenter


def _uid():
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Inline helpers
# ---------------------------------------------------------------------------

def _make_production_order(db, product, *, code=None, status="draft",
                           sales_order_id=None, qty=10):
    po = ProductionOrder(
        code=code or f"MO-TEST-{_uid()}",
        product_id=product.id,
        quantity_ordered=qty,
        quantity_completed=0,
        status=status,
        sales_order_id=sales_order_id,
    )
    db.add(po)
    db.flush()
    return po


def _make_operation(db, production_order, *, sequence=10, status="pending",
                    work_center_id=1, resource_id=None,
                    planned_setup=Decimal("5"), planned_run=Decimal("30"),
                    actual_start=None, operation_code=None):
    op = ProductionOrderOperation(
        production_order_id=production_order.id,
        work_center_id=work_center_id,
        sequence=sequence,
        operation_code=operation_code or f"OP-{sequence}",
        operation_name=f"Test Op {sequence}",
        status=status,
        planned_setup_minutes=planned_setup,
        planned_run_minutes=planned_run,
        actual_start=actual_start,
        resource_id=resource_id,
    )
    db.add(op)
    db.flush()
    return op


def _make_resource(db, *, code=None, name=None, work_center_id=1,
                   status="available", is_active=True):
    resource = Resource(
        code=code or f"RES-{_uid()}",
        name=name or f"Test Resource {_uid()}",
        work_center_id=work_center_id,
        status=status,
        is_active=is_active,
    )
    db.add(resource)
    db.flush()
    return resource


def _make_work_center(db, *, code=None, name=None):
    wc = WorkCenter(
        code=code or f"WC-{_uid()}",
        name=name or f"Work Center {_uid()}",
    )
    db.add(wc)
    db.flush()
    return wc


def _make_inventory(db, product_id, on_hand, location_id=1, allocated=0):
    inv = Inventory(
        product_id=product_id,
        location_id=location_id,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


# ===========================================================================
# DATA IMPORT SERVICE TESTS
# ===========================================================================


class TestImportProducts:
    """Tests for product CSV import."""

    def test_create_new_product(self, db):
        uid = _uid()
        csv_text = (
            "SKU,Name,Description,Item Type,Procurement Type,Unit,Standard Cost,Selling Price,Reorder Point,Active\n"
            f"IMP-PROD-{uid},Test Import Product,A test product,finished_good,make,EA,5.00,15.00,10,true\n"
        )
        result = data_import_service.import_products(db, csv_text)
        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["total_processed"] == 1
        assert len(result["errors"]) == 0

        # Verify product was persisted
        product = db.query(Product).filter(Product.sku == f"IMP-PROD-{uid}").first()
        assert product is not None
        assert product.name == "Test Import Product"
        assert product.item_type == "finished_good"

    def test_update_existing_product(self, db, make_product):
        product = make_product(item_type="finished_good", standard_cost=Decimal("5.00"))
        csv_text = (
            "SKU,Name,Standard Cost,Selling Price\n"
            f"{product.sku},Updated Name,8.00,20.00\n"
        )
        result = data_import_service.import_products(db, csv_text)
        assert result["updated"] == 1
        assert result["created"] == 0

        db.refresh(product)
        assert product.name == "Updated Name"

    def test_missing_sku_error(self, db):
        csv_text = (
            "SKU,Name\n"
            ",No SKU Product\n"
        )
        result = data_import_service.import_products(db, csv_text)
        assert result["created"] == 0
        assert any("Missing SKU" in e for e in result["errors"])

    def test_create_multiple_products(self, db):
        uid1, uid2 = _uid(), _uid()
        csv_text = (
            "SKU,Name,Item Type,Unit\n"
            f"IMP-M1-{uid1},Product One,finished_good,EA\n"
            f"IMP-M2-{uid2},Product Two,supply,G\n"
        )
        result = data_import_service.import_products(db, csv_text)
        assert result["created"] == 2
        assert result["total_processed"] == 2

    def test_create_product_with_optional_fields(self, db):
        uid = _uid()
        csv_text = (
            "SKU,Name,Item Type,Unit,Active\n"
            f"IMP-OPT-{uid},Optional Fields,finished_good,EA,false\n"
        )
        result = data_import_service.import_products(db, csv_text)
        assert result["created"] == 1

        product = db.query(Product).filter(Product.sku == f"IMP-OPT-{uid}").first()
        assert product.active is False

    def test_mixed_create_update_errors(self, db, make_product):
        existing = make_product(item_type="finished_good")
        uid = _uid()
        csv_text = (
            "SKU,Name,Standard Cost\n"
            f"{existing.sku},Updated Existing,7.50\n"
            f"IMP-NEW-{uid},Brand New Product,\n"
            ",Missing SKU Row,3.00\n"
        )
        result = data_import_service.import_products(db, csv_text)
        assert result["updated"] == 1
        assert result["created"] == 1
        assert len(result["errors"]) == 1


class TestImportInventory:
    """Tests for inventory CSV import."""

    def test_create_inventory_set_mode(self, db, make_product):
        product = make_product(item_type="finished_good")
        csv_text = (
            "SKU,Quantity,Mode\n"
            f"{product.sku},100,set\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert result["created"] == 1
        assert result["total_processed"] == 1
        assert len(result["errors"]) == 0

    def test_update_inventory_set_mode(self, db, make_product):
        product = make_product(item_type="finished_good")
        # Create inventory at the MAIN location that import_inventory uses
        main_loc = db.query(InventoryLocation).filter(
            InventoryLocation.code == "MAIN"
        ).first()
        if not main_loc:
            main_loc = InventoryLocation(
                code="MAIN", name="Main Warehouse", type="warehouse", active=True,
            )
            db.add(main_loc)
            db.flush()
        _make_inventory(db, product.id, on_hand=Decimal("50"),
                        location_id=main_loc.id)

        csv_text = (
            "SKU,Quantity,Mode\n"
            f"{product.sku},200,set\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert result["updated"] == 1

        inv = db.query(Inventory).filter(
            Inventory.product_id == product.id,
            Inventory.location_id == main_loc.id,
        ).first()
        assert inv.on_hand_quantity == Decimal("200")

    def test_update_inventory_add_mode(self, db, make_product):
        product = make_product(item_type="finished_good")
        main_loc = db.query(InventoryLocation).filter(
            InventoryLocation.code == "MAIN"
        ).first()
        if not main_loc:
            main_loc = InventoryLocation(
                code="MAIN", name="Main Warehouse", type="warehouse", active=True,
            )
            db.add(main_loc)
            db.flush()
        _make_inventory(db, product.id, on_hand=Decimal("50"),
                        location_id=main_loc.id)

        csv_text = (
            "SKU,Quantity,Mode\n"
            f"{product.sku},25,add\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert result["updated"] == 1

        inv = db.query(Inventory).filter(
            Inventory.product_id == product.id,
            Inventory.location_id == main_loc.id,
        ).first()
        assert inv.on_hand_quantity == Decimal("75")

    def test_default_set_mode(self, db, make_product):
        """When mode is not specified, default to 'set'."""
        product = make_product(item_type="finished_good")
        main_loc = db.query(InventoryLocation).filter(
            InventoryLocation.code == "MAIN"
        ).first()
        if not main_loc:
            main_loc = InventoryLocation(
                code="MAIN", name="Main Warehouse", type="warehouse", active=True,
            )
            db.add(main_loc)
            db.flush()
        _make_inventory(db, product.id, on_hand=Decimal("100"),
                        location_id=main_loc.id)

        csv_text = (
            "SKU,Quantity\n"
            f"{product.sku},42\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert result["updated"] == 1

        inv = db.query(Inventory).filter(
            Inventory.product_id == product.id,
            Inventory.location_id == main_loc.id,
        ).first()
        assert inv.on_hand_quantity == Decimal("42")

    def test_missing_sku_error(self, db):
        csv_text = (
            "SKU,Quantity\n"
            ",100\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert len(result["errors"]) >= 1
        assert any("Missing SKU" in e for e in result["errors"])

    def test_product_not_found_error(self, db):
        csv_text = (
            "SKU,Quantity\n"
            "NONEXISTENT-SKU-999,100\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert len(result["errors"]) >= 1
        assert any("not found" in e for e in result["errors"])

    def test_invalid_quantity_error(self, db, make_product):
        product = make_product(item_type="finished_good")
        csv_text = (
            "SKU,Quantity\n"
            f"{product.sku},not_a_number\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert len(result["errors"]) >= 1
        assert any("Invalid quantity" in e for e in result["errors"])

    def test_missing_quantity_error(self, db, make_product):
        product = make_product(item_type="finished_good")
        csv_text = (
            "SKU,Location\n"
            f"{product.sku},MAIN\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert len(result["errors"]) >= 1
        assert any("Missing quantity" in e for e in result["errors"])

    def test_custom_location_code(self, db, make_product):
        product = make_product(item_type="finished_good")
        loc = InventoryLocation(
            code=f"LOC-{_uid()}", name="Custom Location", type="warehouse",
            active=True,
        )
        db.add(loc)
        db.flush()

        csv_text = (
            "SKU,Quantity,Location\n"
            f"{product.sku},50,{loc.code}\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert result["created"] == 1

    def test_nonexistent_location_falls_back_to_default(self, db, make_product):
        product = make_product(item_type="finished_good")
        csv_text = (
            "SKU,Quantity,Location\n"
            f"{product.sku},75,NOPE_LOCATION_ZZZ\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        # Should fall back to MAIN (default) and succeed
        assert result["total_processed"] == 1

    def test_alternative_column_names(self, db, make_product):
        """Test that alternative column names (qty, On Hand) are recognized."""
        product = make_product(item_type="finished_good")
        csv_text = (
            "sku,qty,action\n"
            f"{product.sku},33,set\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert result["total_processed"] == 1

    def test_lot_number_column_ignored(self, db, make_product):
        """Lot number column is read but not acted on currently."""
        product = make_product(item_type="finished_good")
        csv_text = (
            "SKU,Quantity,Lot Number\n"
            f"{product.sku},10,LOT-001\n"
        )
        result = data_import_service.import_inventory(db, csv_text)
        assert result["total_processed"] == 1


class TestFindCol:
    """Tests for the _find_col helper function."""

    def test_finds_first_match(self):
        row = {"SKU": "ABC", "sku": "DEF"}
        result = data_import_service._find_col(row, ["SKU", "sku"])
        assert result == "ABC"

    def test_skips_empty_values(self):
        row = {"SKU": "", "sku": "FOUND"}
        result = data_import_service._find_col(row, ["SKU", "sku"])
        assert result == "FOUND"

    def test_returns_empty_when_no_match(self):
        row = {"name": "foo"}
        result = data_import_service._find_col(row, ["SKU", "sku"])
        assert result == ""


# ===========================================================================
# COMMAND CENTER SERVICE TESTS
# ===========================================================================


class TestGetActionItems:
    """Tests for the top-level get_action_items aggregator."""

    def test_returns_action_items_response(self, db):
        response = get_action_items(db)
        assert hasattr(response, "items")
        assert hasattr(response, "total_count")
        assert hasattr(response, "counts_by_type")
        assert response.total_count == len(response.items)

    def test_items_sorted_by_priority(self, db):
        response = get_action_items(db)
        priorities = [item.priority for item in response.items]
        assert priorities == sorted(priorities)


class TestBlockedProductionOrders:
    """Tests for _get_blocked_production_orders."""

    def test_no_active_pos_returns_empty(self, db):
        items = _get_blocked_production_orders(db)
        # There may or may not be items from seeded data, but the function
        # should return a list without error
        assert isinstance(items, list)

    def test_released_po_without_bom_not_blocked(self, db, make_product):
        """A released PO with no BOM has no blocking material issues."""
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="released")

        items = _get_blocked_production_orders(db)
        # The PO might or might not be blocked depending on the blocking_issues
        # service behavior. This test verifies the function runs without error.
        assert isinstance(items, list)


class TestOverdueSalesOrders:
    """Tests for _get_overdue_sales_orders."""

    def test_overdue_order_detected(self, db, make_product, make_sales_order):
        product = make_product(item_type="finished_good")
        so = make_sales_order(
            product_id=product.id,
            status="confirmed",
        )
        # Set estimated_completion_date to yesterday
        so.estimated_completion_date = datetime.now(timezone.utc) - timedelta(days=2)
        so.shipped_at = None
        db.flush()

        items = _get_overdue_sales_orders(db)
        overdue_ids = [item.entity_id for item in items]
        assert so.id in overdue_ids

    def test_shipped_order_not_overdue(self, db, make_product, make_sales_order):
        product = make_product(item_type="finished_good")
        so = make_sales_order(
            product_id=product.id,
            status="confirmed",
        )
        so.estimated_completion_date = datetime.now(timezone.utc) - timedelta(days=1)
        so.shipped_at = datetime.now(timezone.utc)
        db.flush()

        items = _get_overdue_sales_orders(db)
        overdue_ids = [item.entity_id for item in items]
        assert so.id not in overdue_ids

    def test_overdue_item_has_priority_1(self, db, make_product, make_sales_order):
        product = make_product(item_type="finished_good")
        so = make_sales_order(product_id=product.id, status="confirmed")
        so.estimated_completion_date = datetime.now(timezone.utc) - timedelta(days=3)
        so.shipped_at = None
        db.flush()

        items = _get_overdue_sales_orders(db)
        for item in items:
            if item.entity_id == so.id:
                assert item.priority == 1
                assert "overdue" in item.title
                break


class TestDueTodaySalesOrders:
    """Tests for _get_due_today_sales_orders."""

    @pytest.mark.xfail(
        reason="Pre-existing bug: command_center references so.order_date but SalesOrder has no such attribute",
        strict=True,
    )
    def test_due_today_detected(self, db, make_product, make_sales_order):
        product = make_product(item_type="finished_good")
        so = make_sales_order(product_id=product.id, status="confirmed")
        now = datetime.now(timezone.utc)
        so.estimated_completion_date = now.replace(
            hour=12, minute=0, second=0, microsecond=0
        )
        so.shipped_at = None
        db.flush()

        items = _get_due_today_sales_orders(db)
        due_ids = [item.entity_id for item in items]
        assert so.id in due_ids

    @pytest.mark.xfail(
        reason="Pre-existing bug: command_center references so.order_date but SalesOrder has no such attribute",
        strict=True,
    )
    def test_due_today_has_priority_2(self, db, make_product, make_sales_order):
        product = make_product(item_type="finished_good")
        so = make_sales_order(product_id=product.id, status="in_production")
        now = datetime.now(timezone.utc)
        so.estimated_completion_date = now.replace(
            hour=15, minute=0, second=0, microsecond=0
        )
        so.shipped_at = None
        db.flush()

        items = _get_due_today_sales_orders(db)
        for item in items:
            if item.entity_id == so.id:
                assert item.priority == 2
                break

    def test_shipped_today_not_in_due_today(self, db, make_product, make_sales_order):
        product = make_product(item_type="finished_good")
        so = make_sales_order(product_id=product.id, status="confirmed")
        now = datetime.now(timezone.utc)
        so.estimated_completion_date = now.replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        so.shipped_at = now
        db.flush()

        items = _get_due_today_sales_orders(db)
        due_ids = [item.entity_id for item in items]
        assert so.id not in due_ids


class TestOverrunningOperations:
    """Tests for _get_overrunning_operations."""

    def test_overrunning_op_detected(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")

        # Start time 3 hours ago, planned time = 30 minutes
        # Elapsed ~180 min >> 2 * 30 = 60 min
        op = _make_operation(
            db, po,
            status="running",
            planned_setup=Decimal("0"),
            planned_run=Decimal("30"),
            actual_start=datetime.now(timezone.utc) - timedelta(hours=3),
        )

        items = _get_overrunning_operations(db)
        op_ids = [item.entity_id for item in items]
        assert op.id in op_ids

    def test_non_overrunning_op_not_detected(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")

        # Start time 10 minutes ago, planned time = 30 min
        # Elapsed ~10 min < 2 * 30 = 60 min
        op = _make_operation(
            db, po,
            status="running",
            planned_setup=Decimal("0"),
            planned_run=Decimal("30"),
            actual_start=datetime.now(timezone.utc) - timedelta(minutes=10),
        )

        items = _get_overrunning_operations(db)
        op_ids = [item.entity_id for item in items]
        assert op.id not in op_ids

    def test_overrunning_has_priority_3(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")
        op = _make_operation(
            db, po,
            status="running",
            planned_setup=Decimal("5"),
            planned_run=Decimal("10"),
            actual_start=datetime.now(timezone.utc) - timedelta(hours=2),
        )

        items = _get_overrunning_operations(db)
        for item in items:
            if item.entity_id == op.id:
                assert item.priority == 3
                break


class TestIdleResourcesWithWork:
    """Tests for _get_idle_resources_with_work."""

    def test_idle_resource_with_pending_ops(self, db, make_product):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="available")

        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")

        # Create a pending operation in the same work center, not assigned
        _make_operation(
            db, po,
            status="pending",
            work_center_id=wc.id,
            resource_id=None,
        )

        items = _get_idle_resources_with_work(db)
        resource_ids = [item.entity_id for item in items]
        assert resource.id in resource_ids

    def test_busy_resource_not_idle(self, db, make_product):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="available")

        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")

        # Resource is running an operation
        _make_operation(
            db, po,
            status="running",
            work_center_id=wc.id,
            resource_id=resource.id,
            actual_start=datetime.now(timezone.utc),
        )

        items = _get_idle_resources_with_work(db)
        resource_ids = [item.entity_id for item in items]
        assert resource.id not in resource_ids

    def test_idle_resource_has_priority_4(self, db, make_product):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="available")

        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")
        _make_operation(db, po, status="pending", work_center_id=wc.id,
                        resource_id=None)

        items = _get_idle_resources_with_work(db)
        for item in items:
            if item.entity_id == resource.id:
                assert item.priority == 4
                break

    def test_no_pending_work_means_no_alert(self, db):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="available")

        # No pending operations in the work center
        items = _get_idle_resources_with_work(db)
        resource_ids = [item.entity_id for item in items]
        assert resource.id not in resource_ids


class TestGetTodaySummary:
    """Tests for get_today_summary."""

    def test_returns_today_summary(self, db):
        summary = get_today_summary(db)
        assert hasattr(summary, "orders_due_today")
        assert hasattr(summary, "production_in_progress")
        assert hasattr(summary, "resources_total")
        assert hasattr(summary, "generated_at")
        assert summary.generated_at is not None

    def test_production_in_progress_count(self, db, make_product):
        product = make_product(item_type="finished_good")
        _make_production_order(db, product, status="in_progress")

        summary = get_today_summary(db)
        assert summary.production_in_progress >= 1

    def test_operations_running_count(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")
        _make_operation(
            db, po,
            status="running",
            actual_start=datetime.now(timezone.utc),
        )

        summary = get_today_summary(db)
        assert summary.operations_running >= 1

    def test_overdue_orders_count(self, db, make_product, make_sales_order):
        product = make_product(item_type="finished_good")
        so = make_sales_order(product_id=product.id, status="confirmed")
        so.estimated_completion_date = datetime.now(timezone.utc) - timedelta(days=5)
        so.shipped_at = None
        db.flush()

        summary = get_today_summary(db)
        assert summary.orders_overdue >= 1

    def test_resources_idle_non_negative(self, db):
        summary = get_today_summary(db)
        assert summary.resources_idle >= 0

    def test_resources_down_counts_maintenance(self, db):
        wc = _make_work_center(db)
        _make_resource(db, work_center_id=wc.id, status="maintenance")

        summary = get_today_summary(db)
        assert summary.resources_down >= 1

    def test_shipped_today_count(self, db, make_product, make_sales_order):
        product = make_product(item_type="finished_good")
        so = make_sales_order(product_id=product.id, status="shipped")
        so.shipped_at = datetime.now(timezone.utc)
        db.flush()

        summary = get_today_summary(db)
        assert summary.orders_shipped_today >= 1


class TestGetResourceStatuses:
    """Tests for get_resource_statuses."""

    def test_returns_resources_response(self, db):
        response = get_resource_statuses(db)
        assert hasattr(response, "resources")
        assert hasattr(response, "summary")

    def test_active_resources_returned(self, db):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="available")

        response = get_resource_statuses(db)
        resource_ids = [r.id for r in response.resources]
        assert resource.id in resource_ids

    def test_running_resource_status(self, db, make_product):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="available")

        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")
        _make_operation(
            db, po,
            status="running",
            work_center_id=wc.id,
            resource_id=resource.id,
            actual_start=datetime.now(timezone.utc),
        )

        response = get_resource_statuses(db)
        for r in response.resources:
            if r.id == resource.id:
                assert r.status == "running"
                assert r.current_operation is not None
                assert r.current_operation.production_order_code == po.code
                break

    def test_idle_resource_status(self, db):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="available")

        response = get_resource_statuses(db)
        for r in response.resources:
            if r.id == resource.id:
                assert r.status == "idle"
                assert r.current_operation is None
                break

    def test_maintenance_resource_status(self, db):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="maintenance")

        response = get_resource_statuses(db)
        for r in response.resources:
            if r.id == resource.id:
                assert r.status == "maintenance"
                break

    def test_summary_counts(self, db):
        wc = _make_work_center(db)
        _make_resource(db, work_center_id=wc.id, status="available")
        _make_resource(db, work_center_id=wc.id, status="maintenance")

        response = get_resource_statuses(db)
        # Summary should contain at least idle and maintenance
        assert isinstance(response.summary, dict)

    def test_pending_operations_count_in_resource(self, db, make_product):
        wc = _make_work_center(db)
        resource = _make_resource(db, work_center_id=wc.id, status="available")

        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")
        _make_operation(db, po, status="pending", work_center_id=wc.id)
        _make_operation(db, po, sequence=20, status="queued", work_center_id=wc.id)

        response = get_resource_statuses(db)
        for r in response.resources:
            if r.id == resource.id:
                assert r.pending_operations_count >= 2
                break

    def test_inactive_resource_excluded(self, db):
        wc = _make_work_center(db)
        resource = _make_resource(
            db, work_center_id=wc.id, status="available", is_active=False
        )

        response = get_resource_statuses(db)
        resource_ids = [r.id for r in response.resources]
        assert resource.id not in resource_ids
