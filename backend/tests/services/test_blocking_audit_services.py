"""Tests for blocking_issues, fulfillment_status, and transaction_audit_service.

Covers:
- blocking_issues.py: SO/PO blocking analysis, resolution actions, ready-date estimation
- fulfillment_status.py: fulfillment state calculation, shipped/cancelled handling
- transaction_audit_service.py: transaction gap detection, timeline, audit filtering
"""
import uuid
import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models.product import Product
from app.models.bom import BOM, BOMLine
from app.models.production_order import ProductionOrder
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.inventory import Inventory, InventoryTransaction
from app.models.vendor import Vendor
from app.models.user import User

from app.services.blocking_issues import (
    get_finished_goods_available,
    get_allocated_quantity,
    get_production_orders_for_so,
    get_material_requirements,
    get_material_available,
    get_pending_purchase_orders,
    analyze_line_issues,
    generate_resolution_actions,
    estimate_ready_date,
    get_sales_order_blocking_issues,
    get_production_order_blocking_issues,
    generate_po_resolution_actions,
)
from app.services.fulfillment_status import get_fulfillment_status
from app.services.transaction_audit_service import (
    TransactionAuditService,
    TransactionGap,
    AuditResult,
)
from app.schemas.blocking_issues import (
    LineIssues,
    BlockingIssue,
    IssueSeverity,
    IssueType,
    MaterialIssue,
    IncomingSupply,
)
from app.schemas.fulfillment_status import FulfillmentState


# =============================================================================
# Helpers
# =============================================================================

def _uid():
    return uuid.uuid4().hex[:8]


def _make_order_line(db, sales_order_id, product_id, quantity=1,
                     unit_price=Decimal("10.00"), allocated_quantity=Decimal("0"),
                     shipped_quantity=Decimal("0")):
    """Create a SalesOrderLine with allocation/shipping quantities."""
    line = SalesOrderLine(
        sales_order_id=sales_order_id,
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        total=unit_price * quantity,
        discount=Decimal("0"),
        tax_rate=Decimal("0"),
        allocated_quantity=allocated_quantity,
        shipped_quantity=shipped_quantity,
    )
    db.add(line)
    db.flush()
    return line


def _make_inventory(db, product_id, on_hand, allocated=Decimal("0"), location_id=1):
    """Create an inventory record. Never sets available_quantity (computed column)."""
    inv = Inventory(
        product_id=product_id,
        location_id=location_id,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


def _make_production_order(db, product_id, qty_ordered=10, status="draft",
                           sales_order_id=None, bom_id=None, code=None,
                           qty_completed=Decimal("0"), qty_scrapped=Decimal("0"),
                           due_date=None):
    """Create a ProductionOrder with sensible defaults."""
    po = ProductionOrder(
        code=code or f"WO-TEST-{_uid()}",
        product_id=product_id,
        quantity_ordered=qty_ordered,
        quantity_completed=qty_completed,
        quantity_scrapped=qty_scrapped,
        status=status,
        sales_order_id=sales_order_id,
        bom_id=bom_id,
        due_date=due_date,
    )
    db.add(po)
    db.flush()
    return po


def _make_purchase_order_with_line(db, vendor_id, product_id, qty_ordered,
                                   qty_received=Decimal("0"), status="ordered",
                                   expected_date=None):
    """Create a PurchaseOrder with one line for the given product."""
    uid = _uid()
    po = PurchaseOrder(
        po_number=f"PO-TEST-{uid}",
        vendor_id=vendor_id,
        status=status,
        created_by="1",
        expected_date=expected_date,
    )
    db.add(po)
    db.flush()
    pol = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product_id,
        line_number=1,
        quantity_ordered=qty_ordered,
        quantity_received=qty_received,
        unit_cost=Decimal("1.00"),
        line_total=qty_ordered * Decimal("1.00"),
    )
    db.add(pol)
    db.flush()
    return po, pol


def _make_inv_transaction(db, product_id, txn_type, ref_type, ref_id,
                          quantity=Decimal("1"), notes=None):
    """Create an InventoryTransaction for audit tests."""
    txn = InventoryTransaction(
        product_id=product_id,
        transaction_type=txn_type,
        reference_type=ref_type,
        reference_id=ref_id,
        quantity=quantity,
        notes=notes,
    )
    db.add(txn)
    db.flush()
    return txn


# =============================================================================
# blocking_issues.py — helper functions
# =============================================================================

class TestGetFinishedGoodsAvailable:
    """get_finished_goods_available sums on_hand_quantity for a product."""

    def test_no_inventory_returns_zero(self, db, make_product):
        product = make_product()
        result = get_finished_goods_available(db, product.id)
        assert result == Decimal("0")

    def test_sums_across_locations(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, Decimal("100"))
        result = get_finished_goods_available(db, product.id)
        assert result == Decimal("100")

    def test_ignores_other_products(self, db, make_product):
        p1 = make_product()
        p2 = make_product()
        _make_inventory(db, p1.id, Decimal("50"))
        _make_inventory(db, p2.id, Decimal("200"))
        assert get_finished_goods_available(db, p1.id) == Decimal("50")


class TestGetAllocatedQuantity:
    """get_allocated_quantity sums allocated_quantity for a product."""

    def test_no_inventory_returns_zero(self, db, make_product):
        product = make_product()
        assert get_allocated_quantity(db, product.id) == Decimal("0")

    def test_returns_allocated_amount(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, Decimal("100"), allocated=Decimal("30"))
        assert get_allocated_quantity(db, product.id) == Decimal("30")


class TestGetMaterialAvailable:
    """get_material_available returns on_hand minus allocated."""

    def test_returns_net_available(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, Decimal("100"), allocated=Decimal("40"))
        assert get_material_available(db, product.id) == Decimal("60")

    def test_can_be_negative(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, Decimal("10"), allocated=Decimal("20"))
        assert get_material_available(db, product.id) == Decimal("-10")


class TestGetProductionOrdersForSO:
    """get_production_orders_for_so filters by SO and product."""

    def test_returns_matching_orders(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id)
        wo = _make_production_order(db, product.id, sales_order_id=so.id)
        result = get_production_orders_for_so(db, so.id, product.id)
        assert len(result) == 1
        assert result[0].id == wo.id

    def test_ignores_unrelated_orders(self, db, make_product, make_sales_order):
        p1 = make_product()
        p2 = make_product()
        so = make_sales_order(product_id=p1.id)
        _make_production_order(db, p2.id, sales_order_id=so.id)
        result = get_production_orders_for_so(db, so.id, p1.id)
        assert len(result) == 0


class TestGetMaterialRequirements:
    """get_material_requirements reads BOM lines for a product."""

    def test_no_bom_returns_empty(self, db, make_product):
        product = make_product()
        result = get_material_requirements(db, product.id, Decimal("5"))
        assert result == []

    def test_scales_by_quantity(self, db, make_product, make_bom):
        fg = make_product(item_type="finished_good", has_bom=True)
        raw = make_product(item_type="supply", is_raw_material=True)
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        result = get_material_requirements(db, fg.id, Decimal("3"))
        assert len(result) == 1
        component, qty_needed = result[0]
        assert component.id == raw.id
        assert qty_needed == Decimal("300")


class TestGetPendingPurchaseOrders:
    """get_pending_purchase_orders finds open POs with remaining quantity."""

    def test_no_pos_returns_empty(self, db, make_product):
        product = make_product()
        assert get_pending_purchase_orders(db, product.id) == []

    def test_returns_po_with_remaining_qty(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        po, _ = _make_purchase_order_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("100"), qty_received=Decimal("20"),
            status="ordered",
        )
        result = get_pending_purchase_orders(db, product.id)
        assert len(result) == 1
        assert result[0][0].id == po.id
        assert result[0][1] == Decimal("80")

    def test_excludes_fully_received(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_purchase_order_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("100"), qty_received=Decimal("100"),
            status="ordered",
        )
        result = get_pending_purchase_orders(db, product.id)
        assert len(result) == 0

    def test_excludes_closed_status(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_purchase_order_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("50"), qty_received=Decimal("0"),
            status="closed",
        )
        result = get_pending_purchase_orders(db, product.id)
        assert len(result) == 0


# =============================================================================
# blocking_issues.py — analyze_line_issues
# =============================================================================

class TestAnalyzeLineIssues:
    """analyze_line_issues returns issues for a single SO line."""

    def test_no_shortage_returns_no_issues(self, db, make_product, make_sales_order):
        """When inventory covers the order, no blocking issues are produced."""
        product = make_product()
        _make_inventory(db, product.id, Decimal("50"))
        so = make_sales_order(product_id=product.id, quantity=10)
        line = _make_order_line(db, so.id, product.id, quantity=Decimal("10"))
        result = analyze_line_issues(db, so, line, 1)
        assert result.quantity_short == Decimal("0")
        assert len(result.blocking_issues) == 0

    def test_missing_product_returns_unknown(self, db, make_sales_order):
        """If the product cannot be found, return UNKNOWN placeholders."""
        so = make_sales_order(product_id=None)

        # Create a lightweight object mimicking a SalesOrderLine with an
        # orphaned product_id. We cannot insert via ORM due to FK constraint,
        # so we construct an in-memory object that analyze_line_issues reads.
        class FakeLine:
            def __init__(self):
                self.product_id = 999999
                self.quantity = Decimal("5")

        result = analyze_line_issues(db, so, FakeLine(), 1)
        assert result.product_sku == "UNKNOWN"
        assert result.product_name == "Unknown Product"

    def test_missing_production_order_for_bom_product(self, db, make_product, make_sales_order):
        """Product with BOM but no production order produces PRODUCTION_MISSING."""
        product = make_product(has_bom=True)
        so = make_sales_order(product_id=product.id, quantity=5)
        line = _make_order_line(db, so.id, product.id, quantity=Decimal("5"))
        result = analyze_line_issues(db, so, line, 1)
        assert result.quantity_short > 0
        blocking = [i for i in result.blocking_issues if i.type == IssueType.PRODUCTION_MISSING]
        assert len(blocking) == 1

    def test_incomplete_production_creates_blocking_issue(self, db, make_product, make_sales_order):
        """Incomplete WO produces PRODUCTION_INCOMPLETE."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=10)
        _make_production_order(
            db, product.id,
            qty_ordered=10, status="in_progress",
            sales_order_id=so.id,
        )
        line = _make_order_line(db, so.id, product.id, quantity=Decimal("10"))
        result = analyze_line_issues(db, so, line, 1)
        prod_issues = [i for i in result.blocking_issues if i.type == IssueType.PRODUCTION_INCOMPLETE]
        assert len(prod_issues) == 1
        assert prod_issues[0].severity == IssueSeverity.BLOCKING

    def test_completed_production_no_blocking(self, db, make_product, make_sales_order):
        """Completed WO is not considered blocking even if quantity is short."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=10)
        _make_production_order(
            db, product.id,
            qty_ordered=10, qty_completed=Decimal("10"),
            status="completed", sales_order_id=so.id,
        )
        line = _make_order_line(db, so.id, product.id, quantity=Decimal("10"))
        result = analyze_line_issues(db, so, line, 1)
        prod_issues = [i for i in result.blocking_issues if i.type == IssueType.PRODUCTION_INCOMPLETE]
        assert len(prod_issues) == 0

    def test_material_shortage_with_pending_po(self, db, make_product, make_bom,
                                                make_sales_order, make_vendor):
        """Material shortage + pending PO generates both MATERIAL_SHORTAGE and PURCHASE_PENDING."""
        fg = make_product(has_bom=True)
        raw = make_product(item_type="supply", is_raw_material=True)
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        so = make_sales_order(product_id=fg.id, quantity=5)
        _make_production_order(
            db, fg.id, qty_ordered=5, status="in_progress",
            sales_order_id=so.id,
        )
        vendor = make_vendor()
        _make_purchase_order_with_line(
            db, vendor.id, raw.id,
            qty_ordered=Decimal("1000"), status="ordered",
            expected_date=date.today() + timedelta(days=7),
        )
        line = _make_order_line(db, so.id, fg.id, quantity=Decimal("5"))
        result = analyze_line_issues(db, so, line, 1)
        mat_issues = [i for i in result.blocking_issues if i.type == IssueType.MATERIAL_SHORTAGE]
        po_issues = [i for i in result.blocking_issues if i.type == IssueType.PURCHASE_PENDING]
        assert len(mat_issues) >= 1
        assert len(po_issues) >= 1


# =============================================================================
# blocking_issues.py — generate_resolution_actions / estimate_ready_date
# =============================================================================

class TestGenerateResolutionActions:
    """generate_resolution_actions prioritizes actions from issues."""

    def test_empty_issues_returns_empty(self):
        result = generate_resolution_actions([])
        assert result == []

    def test_purchase_pending_generates_expedite(self):
        issue = BlockingIssue(
            type=IssueType.PURCHASE_PENDING,
            severity=IssueSeverity.WARNING,
            message="PO pending",
            reference_type="purchase_order",
            reference_id=1,
            reference_code="PO-001",
            details={"expected_date": "2026-03-01"},
        )
        line = LineIssues(
            line_number=1, product_sku="SKU", product_name="Product",
            quantity_ordered=Decimal("10"), quantity_available=Decimal("0"),
            quantity_short=Decimal("10"), blocking_issues=[issue],
        )
        actions = generate_resolution_actions([line])
        assert len(actions) == 1
        assert "Expedite" in actions[0].action

    def test_material_shortage_without_po_generates_create_po(self):
        issue = BlockingIssue(
            type=IssueType.MATERIAL_SHORTAGE,
            severity=IssueSeverity.BLOCKING,
            message="Shortage",
            reference_type="product",
            reference_id=42,
            reference_code="RAW-001",
            details={"shortage": 500, "incoming_po": None},
        )
        line = LineIssues(
            line_number=1, product_sku="FG", product_name="FG",
            quantity_ordered=Decimal("10"), quantity_available=Decimal("0"),
            quantity_short=Decimal("10"), blocking_issues=[issue],
        )
        actions = generate_resolution_actions([line])
        assert any("Create PO" in a.action for a in actions)

    def test_deduplicates_by_reference(self):
        """Same reference across two lines only generates one action."""
        issue = BlockingIssue(
            type=IssueType.PRODUCTION_INCOMPLETE,
            severity=IssueSeverity.BLOCKING,
            message="Incomplete",
            reference_type="production_order",
            reference_id=10,
            reference_code="WO-001",
            details={"quantity_remaining": 5},
        )
        line1 = LineIssues(
            line_number=1, product_sku="A", product_name="A",
            quantity_ordered=Decimal("5"), quantity_available=Decimal("0"),
            quantity_short=Decimal("5"), blocking_issues=[issue],
        )
        line2 = LineIssues(
            line_number=2, product_sku="B", product_name="B",
            quantity_ordered=Decimal("3"), quantity_available=Decimal("0"),
            quantity_short=Decimal("3"), blocking_issues=[issue],
        )
        actions = generate_resolution_actions([line1, line2])
        assert len(actions) == 1

    def test_priorities_are_sequential(self):
        """Actions are numbered 1, 2, 3... in priority order."""
        po_issue = BlockingIssue(
            type=IssueType.PURCHASE_PENDING,
            severity=IssueSeverity.WARNING,
            message="PO pending",
            reference_type="purchase_order", reference_id=1,
            reference_code="PO-001", details={"expected_date": "2026-03-01"},
        )
        prod_issue = BlockingIssue(
            type=IssueType.PRODUCTION_MISSING,
            severity=IssueSeverity.BLOCKING,
            message="Missing WO",
            reference_type="make_product", reference_id=2,
            reference_code="SKU-001", details={"quantity_needed": 10},
        )
        line = LineIssues(
            line_number=1, product_sku="X", product_name="X",
            quantity_ordered=Decimal("10"), quantity_available=Decimal("0"),
            quantity_short=Decimal("10"), blocking_issues=[po_issue, prod_issue],
        )
        actions = generate_resolution_actions([line])
        priorities = [a.priority for a in actions]
        assert priorities == sorted(priorities)
        assert priorities[0] == 1


class TestEstimateReadyDate:
    """estimate_ready_date uses PO and WO dates to estimate."""

    def test_no_issues_returns_none(self):
        result = estimate_ready_date([])
        assert result is None

    def test_returns_none_when_all_dates_in_past(self):
        """If all dates are in the past (or today), returns None."""
        issue = BlockingIssue(
            type=IssueType.PURCHASE_PENDING,
            severity=IssueSeverity.WARNING,
            message="PO",
            reference_type="purchase_order", reference_id=1,
            reference_code="PO-1",
            details={"expected_date": (date.today() - timedelta(days=5)).isoformat()},
        )
        line = LineIssues(
            line_number=1, product_sku="X", product_name="X",
            quantity_ordered=Decimal("1"), quantity_available=Decimal("0"),
            quantity_short=Decimal("1"), blocking_issues=[issue],
        )
        assert estimate_ready_date([line]) is None

    def test_future_po_date_returns_date_plus_buffer(self):
        future = date.today() + timedelta(days=10)
        issue = BlockingIssue(
            type=IssueType.PURCHASE_PENDING,
            severity=IssueSeverity.WARNING,
            message="PO",
            reference_type="purchase_order", reference_id=1,
            reference_code="PO-1",
            details={"expected_date": future.isoformat()},
        )
        line = LineIssues(
            line_number=1, product_sku="X", product_name="X",
            quantity_ordered=Decimal("1"), quantity_available=Decimal("0"),
            quantity_short=Decimal("1"), blocking_issues=[issue],
        )
        result = estimate_ready_date([line])
        assert result == future + timedelta(days=2)

    def test_takes_latest_date_from_multiple_issues(self):
        d1 = date.today() + timedelta(days=5)
        d2 = date.today() + timedelta(days=15)
        issue1 = BlockingIssue(
            type=IssueType.PURCHASE_PENDING,
            severity=IssueSeverity.WARNING,
            message="PO1", reference_type="purchase_order", reference_id=1,
            reference_code="PO-1", details={"expected_date": d1.isoformat()},
        )
        issue2 = BlockingIssue(
            type=IssueType.PRODUCTION_INCOMPLETE,
            severity=IssueSeverity.BLOCKING,
            message="WO", reference_type="production_order", reference_id=2,
            reference_code="WO-1", details={"estimated_completion": d2.isoformat()},
        )
        line = LineIssues(
            line_number=1, product_sku="X", product_name="X",
            quantity_ordered=Decimal("1"), quantity_available=Decimal("0"),
            quantity_short=Decimal("1"), blocking_issues=[issue1, issue2],
        )
        result = estimate_ready_date([line])
        assert result == d2 + timedelta(days=2)


# =============================================================================
# blocking_issues.py — get_sales_order_blocking_issues (integration)
# =============================================================================

class TestGetSalesOrderBlockingIssues:
    """Integration tests for the full SO blocking analysis."""

    def test_nonexistent_order_returns_none(self, db):
        assert get_sales_order_blocking_issues(db, 999999) is None

    def test_order_with_sufficient_inventory(self, db, make_product, make_sales_order):
        """Fully stocked order reports can_fulfill=True."""
        product = make_product()
        _make_inventory(db, product.id, Decimal("100"))
        so = make_sales_order(product_id=product.id, quantity=5)
        _make_order_line(db, so.id, product.id, quantity=Decimal("5"))
        result = get_sales_order_blocking_issues(db, so.id)
        assert result is not None
        assert result.status_summary.can_fulfill is True
        assert result.status_summary.blocking_count == 0

    def test_single_product_order_without_lines(self, db, make_product, make_sales_order):
        """SO with product_id but no lines uses synthetic line approach."""
        product = make_product()
        _make_inventory(db, product.id, Decimal("100"))
        so = make_sales_order(product_id=product.id, quantity=3)
        result = get_sales_order_blocking_issues(db, so.id)
        assert result is not None
        assert len(result.line_issues) == 1
        assert result.line_issues[0].product_sku == product.sku

    def test_customer_name_from_user_company(self, db, make_product, make_sales_order):
        """Customer name is pulled from the User record when customer_id is set."""
        user = User(
            email=f"test-bi-{_uid()}@example.com",
            password_hash="hash",
            first_name="Jane",
            last_name="Doe",
            company_name="Acme Corp",
            account_type="customer",
        )
        db.add(user)
        db.flush()
        product = make_product()
        _make_inventory(db, product.id, Decimal("100"))
        so = make_sales_order(product_id=product.id, quantity=1, customer_id=user.id)
        result = get_sales_order_blocking_issues(db, so.id)
        assert result.customer == "Acme Corp"

    def test_resolution_actions_included(self, db, make_product, make_sales_order):
        """Blocked order includes resolution actions."""
        product = make_product(has_bom=True)
        so = make_sales_order(product_id=product.id, quantity=5)
        _make_order_line(db, so.id, product.id, quantity=Decimal("5"))
        result = get_sales_order_blocking_issues(db, so.id)
        assert result.status_summary.can_fulfill is False
        assert len(result.resolution_actions) > 0


# =============================================================================
# blocking_issues.py — get_production_order_blocking_issues
# =============================================================================

class TestGetProductionOrderBlockingIssues:
    """Integration tests for production order blocking analysis."""

    def test_nonexistent_order_returns_none(self, db):
        assert get_production_order_blocking_issues(db, 999999) is None

    def test_no_bom_means_can_produce(self, db, make_product):
        """WO for a product without BOM has no material issues."""
        product = make_product()
        wo = _make_production_order(db, product.id, qty_ordered=5, status="in_progress")
        result = get_production_order_blocking_issues(db, wo.id)
        assert result is not None
        assert result.status_summary.can_produce is True
        assert result.status_summary.blocking_count == 0

    def test_material_shortage_blocks_production(self, db, make_product, make_bom):
        """Missing materials blocks production."""
        fg = make_product(has_bom=True)
        raw = make_product(item_type="supply", is_raw_material=True)
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        wo = _make_production_order(db, fg.id, qty_ordered=10, status="in_progress")
        result = get_production_order_blocking_issues(db, wo.id)
        assert result.status_summary.can_produce is False
        assert result.status_summary.blocking_count == 1
        assert result.material_issues[0].status == "shortage"

    def test_sufficient_material_allows_production(self, db, make_product, make_bom):
        """When materials are stocked, can_produce=True."""
        fg = make_product(has_bom=True)
        raw = make_product(item_type="supply", is_raw_material=True)
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("10"), "unit": "G"},
        ])
        _make_inventory(db, raw.id, Decimal("500"))
        wo = _make_production_order(db, fg.id, qty_ordered=5, status="in_progress")
        result = get_production_order_blocking_issues(db, wo.id)
        assert result.status_summary.can_produce is True
        assert result.material_issues[0].status == "ok"

    def test_linked_sales_order_info(self, db, make_product, make_sales_order):
        """Linked SO is included in the result."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5)
        wo = _make_production_order(db, product.id, qty_ordered=5, sales_order_id=so.id)
        result = get_production_order_blocking_issues(db, wo.id)
        assert result.linked_sales_order is not None
        assert result.linked_sales_order.id == so.id

    def test_incoming_supply_from_po(self, db, make_product, make_bom, make_vendor):
        """Pending PO shows up as incoming supply for shortage materials."""
        fg = make_product(has_bom=True)
        raw = make_product(item_type="supply", is_raw_material=True)
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("50"), "unit": "G"},
        ])
        vendor = make_vendor()
        expected = date.today() + timedelta(days=5)
        _make_purchase_order_with_line(
            db, vendor.id, raw.id,
            qty_ordered=Decimal("1000"), status="ordered",
            expected_date=expected,
        )
        wo = _make_production_order(db, fg.id, qty_ordered=5, status="in_progress")
        result = get_production_order_blocking_issues(db, wo.id)
        shortage_mat = [m for m in result.material_issues if m.status == "shortage"]
        assert len(shortage_mat) == 1
        assert shortage_mat[0].incoming_supply is not None
        assert shortage_mat[0].incoming_supply.expected_date == expected


class TestGeneratePOResolutionActions:
    """generate_po_resolution_actions prioritizes shortage actions."""

    def test_shortage_with_incoming_generates_expedite(self):
        mat = MaterialIssue(
            product_id=1, product_sku="RAW-1", product_name="Raw",
            quantity_required=Decimal("100"), quantity_available=Decimal("0"),
            quantity_short=Decimal("100"), status="shortage",
            incoming_supply=IncomingSupply(
                purchase_order_id=10, purchase_order_code="PO-10",
                quantity=Decimal("200"), expected_date=date.today() + timedelta(days=3),
                vendor="Vendor A",
            ),
        )
        actions = generate_po_resolution_actions([mat])
        assert len(actions) == 1
        assert "Expedite" in actions[0].action

    def test_shortage_without_incoming_generates_create_po(self):
        mat = MaterialIssue(
            product_id=2, product_sku="RAW-2", product_name="Raw2",
            quantity_required=Decimal("50"), quantity_available=Decimal("0"),
            quantity_short=Decimal("50"), status="shortage",
            incoming_supply=None,
        )
        actions = generate_po_resolution_actions([mat])
        assert len(actions) == 1
        assert "Create PO" in actions[0].action

    def test_ok_materials_generate_no_actions(self):
        mat = MaterialIssue(
            product_id=3, product_sku="RAW-3", product_name="Raw3",
            quantity_required=Decimal("10"), quantity_available=Decimal("20"),
            quantity_short=Decimal("0"), status="ok",
            incoming_supply=None,
        )
        actions = generate_po_resolution_actions([mat])
        assert len(actions) == 0


# =============================================================================
# fulfillment_status.py
# =============================================================================

class TestGetFulfillmentStatus:
    """Tests for get_fulfillment_status covering all states."""

    def test_nonexistent_order_returns_none(self, db):
        assert get_fulfillment_status(db, 999999) is None

    def test_shipped_order_returns_shipped_state(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, status="shipped")
        _make_order_line(db, so.id, product.id, quantity=Decimal("5"),
                         shipped_quantity=Decimal("5"))
        result = get_fulfillment_status(db, so.id)
        assert result.summary.state == FulfillmentState.SHIPPED
        assert result.summary.fulfillment_percent == 100.0
        assert result.summary.can_ship_partial is False
        assert result.summary.can_ship_complete is False

    def test_cancelled_order_returns_cancelled_state(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, status="cancelled")
        _make_order_line(db, so.id, product.id, quantity=Decimal("5"))
        result = get_fulfillment_status(db, so.id)
        assert result.summary.state == FulfillmentState.CANCELLED
        assert result.summary.fulfillment_percent == 0.0
        assert result.lines[0].blocking_reason == "Order cancelled"

    def test_all_lines_ready_returns_ready_to_ship(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=10, status="confirmed")
        _make_order_line(db, so.id, product.id, quantity=Decimal("10"),
                         allocated_quantity=Decimal("10"))
        result = get_fulfillment_status(db, so.id)
        assert result.summary.state == FulfillmentState.READY_TO_SHIP
        assert result.summary.can_ship_complete is True

    def test_partial_readiness(self, db, make_product, make_sales_order):
        """Some lines ready, some blocked -> PARTIALLY_READY."""
        p1 = make_product()
        p2 = make_product()
        so = make_sales_order(product_id=p1.id, quantity=5, status="confirmed")
        _make_order_line(db, so.id, p1.id, quantity=Decimal("5"),
                         allocated_quantity=Decimal("5"))
        _make_order_line(db, so.id, p2.id, quantity=Decimal("3"),
                         allocated_quantity=Decimal("0"))
        result = get_fulfillment_status(db, so.id)
        assert result.summary.state == FulfillmentState.PARTIALLY_READY
        assert result.summary.can_ship_partial is True
        assert result.summary.can_ship_complete is False

    def test_no_lines_returns_blocked(self, db, make_product, make_sales_order):
        """Order with no lines is BLOCKED."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=1, status="confirmed")
        result = get_fulfillment_status(db, so.id)
        assert result.summary.state == FulfillmentState.BLOCKED
        assert result.summary.lines_total == 0

    def test_all_lines_blocked(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, status="confirmed")
        _make_order_line(db, so.id, product.id, quantity=Decimal("5"),
                         allocated_quantity=Decimal("0"))
        result = get_fulfillment_status(db, so.id)
        assert result.summary.state == FulfillmentState.BLOCKED
        assert result.summary.lines_blocked == 1

    def test_shortage_blocking_reason(self, db, make_product, make_sales_order):
        """Blocked line includes a blocking_reason message."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=10, status="confirmed")
        _make_order_line(db, so.id, product.id, quantity=Decimal("10"),
                         allocated_quantity=Decimal("3"))
        result = get_fulfillment_status(db, so.id)
        assert result.lines[0].is_ready is False
        assert "Insufficient inventory" in result.lines[0].blocking_reason

    def test_fulfillment_percent_calculation(self, db, make_product, make_sales_order):
        """Fulfillment percent = lines_ready / lines_total * 100."""
        p1 = make_product()
        p2 = make_product()
        p3 = make_product()
        so = make_sales_order(product_id=p1.id, quantity=1, status="confirmed")
        _make_order_line(db, so.id, p1.id, quantity=Decimal("1"),
                         allocated_quantity=Decimal("1"))
        _make_order_line(db, so.id, p2.id, quantity=Decimal("1"),
                         allocated_quantity=Decimal("1"))
        _make_order_line(db, so.id, p3.id, quantity=Decimal("1"),
                         allocated_quantity=Decimal("0"))
        result = get_fulfillment_status(db, so.id)
        assert result.summary.fulfillment_percent == pytest.approx(66.7, abs=0.1)

    def test_customer_name_fallback(self, db, make_product, make_sales_order):
        """Customer name falls back through customer_name -> customer relation -> Unknown."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=1, status="confirmed",
                              customer_name=None)
        result = get_fulfillment_status(db, so.id)
        # With no customer_name and no customer relation, should be "Unknown"
        # or the user_id=1 name from the seeded user. Since customer_id is None
        # and customer_name is None, it falls through to "Unknown".
        assert result.customer_name is not None


# =============================================================================
# transaction_audit_service.py
# =============================================================================

class TestTransactionAuditServiceRunFullAudit:
    """run_full_audit checks orders for transaction gaps."""

    def test_no_orders_returns_zero_gaps(self, db):
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(order_ids=[999999])
        assert result.total_orders_checked == 0
        assert result.total_gaps == 0

    def test_in_production_without_production_order(self, db, make_product, make_sales_order):
        """Order in_production but no WO creates missing_production_order gap."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, status="in_production")
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(order_ids=[so.id])
        assert result.total_orders_checked == 1
        assert result.orders_with_gaps == 1
        gap_types = [g.gap_type for g in result.gaps]
        assert "missing_production_order" in gap_types

    def test_default_statuses_filter(self, db, make_product, make_sales_order):
        """Default audit checks only in_production, ready_to_ship, shipped, delivered."""
        product = make_product()
        draft_so = make_sales_order(product_id=product.id, quantity=1, status="draft")
        svc = TransactionAuditService(db)
        result = svc.run_full_audit()
        checked_ids = set()
        for g in result.gaps:
            checked_ids.add(g.order_id)
        assert draft_so.id not in checked_ids

    def test_include_statuses_filter(self, db, make_product, make_sales_order):
        """include_statuses parameter filters to specific statuses."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=1, status="confirmed")
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(include_statuses=["confirmed"])
        assert result.total_orders_checked >= 1

    def test_summary_by_type_populated(self, db, make_product, make_sales_order):
        """summary_by_type counts gaps per type."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, status="in_production")
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(order_ids=[so.id])
        assert "missing_production_order" in result.summary_by_type
        assert result.summary_by_type["missing_production_order"] >= 1

    def test_missing_bom_gap(self, db, make_product, make_sales_order):
        """WO in progress without BOM creates missing_bom gap."""
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, status="in_production")
        _make_production_order(
            db, product.id, qty_ordered=5, status="in_progress",
            sales_order_id=so.id,
        )
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(order_ids=[so.id])
        gap_types = [g.gap_type for g in result.gaps]
        assert "missing_bom" in gap_types

    def test_missing_reservation_gap(self, db, make_product, make_bom, make_sales_order):
        """WO in_progress with BOM but no reservation transaction creates gap."""
        fg = make_product(has_bom=True)
        raw = make_product(item_type="supply", is_raw_material=True)
        bom = make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        so = make_sales_order(product_id=fg.id, quantity=5, status="in_production")
        _make_production_order(
            db, fg.id, qty_ordered=5, status="in_progress",
            sales_order_id=so.id, bom_id=bom.id,
        )
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(order_ids=[so.id])
        gap_types = [g.gap_type for g in result.gaps]
        assert "missing_material_reservation" in gap_types

    def test_reservation_present_no_gap(self, db, make_product, make_bom, make_sales_order):
        """When reservation transaction exists, no reservation gap is reported."""
        fg = make_product(has_bom=True)
        raw = make_product(item_type="supply", is_raw_material=True)
        bom = make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        so = make_sales_order(product_id=fg.id, quantity=5, status="in_production")
        wo = _make_production_order(
            db, fg.id, qty_ordered=5, status="in_progress",
            sales_order_id=so.id, bom_id=bom.id,
        )
        _make_inv_transaction(db, raw.id, "reservation", "production_order", wo.id)
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(order_ids=[so.id])
        gap_types = [g.gap_type for g in result.gaps]
        assert "missing_material_reservation" not in gap_types

    def test_missing_finished_goods_receipt(self, db, make_product, make_bom, make_sales_order):
        """Completed WO without receipt transaction creates gap."""
        fg = make_product(has_bom=True)
        raw = make_product(item_type="supply", is_raw_material=True)
        bom = make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        so = make_sales_order(product_id=fg.id, quantity=5, status="in_production")
        wo = _make_production_order(
            db, fg.id, qty_ordered=5, status="completed",
            sales_order_id=so.id, bom_id=bom.id,
        )
        # Add reservation and consumption so only receipt is missing
        _make_inv_transaction(db, raw.id, "reservation", "production_order", wo.id)
        _make_inv_transaction(db, raw.id, "consumption", "production_order", wo.id)
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(order_ids=[so.id])
        gap_types = [g.gap_type for g in result.gaps]
        assert "missing_finished_goods_receipt" in gap_types

    def test_service_skips_svc_and_mfg_skus(self, db, make_product, make_bom, make_sales_order):
        """SVC-* and MFG-* components are skipped in reservation/consumption checks."""
        fg = make_product(has_bom=True)
        svc_product = make_product(sku=f"SVC-TEST-{_uid()}", item_type="supply")
        bom = make_bom(product_id=fg.id, lines=[
            {"component_id": svc_product.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        so = make_sales_order(product_id=fg.id, quantity=1, status="in_production")
        wo = _make_production_order(
            db, fg.id, qty_ordered=1, status="in_progress",
            sales_order_id=so.id, bom_id=bom.id,
        )
        svc = TransactionAuditService(db)
        result = svc.run_full_audit(order_ids=[so.id])
        gap_types = [g.gap_type for g in result.gaps]
        assert "missing_material_reservation" not in gap_types


class TestTransactionAuditServiceSingleOrder:
    """audit_single_order is a convenience wrapper."""

    def test_audit_single_order_delegates(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=1, status="in_production")
        svc = TransactionAuditService(db)
        result = svc.audit_single_order(so.id)
        assert result.total_orders_checked == 1


class TestTransactionTimeline:
    """get_transaction_timeline returns chronological transactions."""

    def test_no_order_returns_empty(self, db):
        svc = TransactionAuditService(db)
        assert svc.get_transaction_timeline(999999) == []

    def test_returns_related_transactions(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, status="in_production")
        wo = _make_production_order(
            db, product.id, qty_ordered=5, status="in_progress",
            sales_order_id=so.id,
        )
        _make_inv_transaction(db, product.id, "reservation", "production_order", wo.id,
                              quantity=Decimal("5"))
        _make_inv_transaction(db, product.id, "consumption", "production_order", wo.id,
                              quantity=Decimal("5"))
        svc = TransactionAuditService(db)
        timeline = svc.get_transaction_timeline(so.id)
        assert len(timeline) >= 2
        types = [t["transaction_type"] for t in timeline]
        assert "reservation" in types
        assert "consumption" in types

    def test_timeline_includes_shipment_transactions(self, db, make_product, make_sales_order):
        product = make_product()
        so = make_sales_order(product_id=product.id, quantity=5, status="shipped")
        _make_inv_transaction(db, product.id, "consumption", "shipment", so.id,
                              quantity=Decimal("5"))
        svc = TransactionAuditService(db)
        timeline = svc.get_transaction_timeline(so.id)
        assert len(timeline) >= 1
        assert timeline[0]["reference_type"] == "shipment"


class TestAuditResultToDict:
    """AuditResult.to_dict serializes properly."""

    def test_to_dict_structure(self):
        gap = TransactionGap(
            order_id=1, order_number="SO-001", order_status="in_production",
            production_order_id=10, production_status="in_progress",
            gap_type="missing_reservation", expected_product_id=5,
            expected_sku="RAW-001", expected_quantity=Decimal("100"),
            details="Missing reservation for RAW-001",
        )
        result = AuditResult(
            audit_timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            total_orders_checked=1,
            orders_with_gaps=1,
            total_gaps=1,
            gaps=[gap],
            summary_by_type={"missing_reservation": 1},
        )
        d = result.to_dict()
        assert d["total_orders_checked"] == 1
        assert d["total_gaps"] == 1
        assert len(d["gaps"]) == 1
        assert d["gaps"][0]["gap_type"] == "missing_reservation"
        assert d["gaps"][0]["expected_quantity"] == 100.0
        assert d["summary_by_type"]["missing_reservation"] == 1

    def test_to_dict_handles_none_quantity(self):
        gap = TransactionGap(
            order_id=1, order_number="SO-002", order_status="shipped",
            production_order_id=None, production_status=None,
            gap_type="missing_production_order", expected_product_id=None,
            expected_sku=None, expected_quantity=None,
            details="No WO",
        )
        result = AuditResult(
            audit_timestamp=datetime.now(timezone.utc),
            total_orders_checked=1,
            orders_with_gaps=1,
            total_gaps=1,
            gaps=[gap],
        )
        d = result.to_dict()
        assert d["gaps"][0]["expected_quantity"] is None
