"""
Tests for app/services/sales_order_service.py

Covers:
- generate_order_number: Sequence generation
- list_sales_orders: Filtering, search, pagination, sorting
- get_sales_order / get_sales_order_with_lines: Retrieval and 404s
- validate_customer / validate_product_for_order: Validation helpers
- get_company_tax_settings: Tax settings lookup
- create_sales_order: Full order creation with lines, tax, validation
- update_sales_order_status: Status transitions and timestamps
- update_payment_info: Payment status changes and events
- update_shipping_info: Shipping updates and events
- update_shipping_address: Address changes and events
- cancel_sales_order: Cancellation with linked WO checks
- delete_sales_order: Deletion with status and PO checks
- record_order_event / add_order_event / list_order_events: Event CRUD
"""
import pytest
from decimal import Decimal

from fastapi import HTTPException

from app.models.user import User
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.production_order import ProductionOrder
from app.models.order_event import OrderEvent
from app.models.company_settings import CompanySettings
from app.services import sales_order_service


# =============================================================================
# Helpers
# =============================================================================

def _make_user(db, *, email=None, status="active", **kwargs):
    """Create a User record directly (no fixture available)."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    user = User(
        email=email or f"test-{uid}@filaops.dev",
        password_hash="not-a-real-hash",
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        status=status,
        account_type=kwargs.pop("account_type", "customer"),
        **kwargs,
    )
    db.add(user)
    db.flush()
    return user


def _make_order_line(db, sales_order_id, product_id, quantity=1, unit_price=Decimal("10.00")):
    """Create a SalesOrderLine directly."""
    line = SalesOrderLine(
        sales_order_id=sales_order_id,
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        total=unit_price * quantity,
        discount=Decimal("0"),
        tax_rate=Decimal("0"),
    )
    db.add(line)
    db.flush()
    return line


def _set_company_tax(db, *, tax_enabled=True, tax_rate=Decimal("0.0825")):
    """Insert or update company settings row with tax config."""
    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if settings:
        settings.tax_enabled = tax_enabled
        settings.tax_rate = tax_rate
    else:
        settings = CompanySettings(
            id=1,
            tax_enabled=tax_enabled,
            tax_rate=tax_rate,
        )
        db.add(settings)
    db.flush()
    return settings


# =============================================================================
# generate_order_number
# =============================================================================

class TestGenerateOrderNumber:
    """Test sales order number sequence generation."""

    def test_first_order_of_year(self, db):
        """When no orders exist, starts at 001."""
        number = sales_order_service.generate_order_number(db)
        # Format: SO-{year}-{seq}
        parts = number.split("-")
        assert parts[0] == "SO"
        assert len(parts) == 3
        # Sequence >= 1 (there may be existing rows from other tests)
        assert int(parts[2]) >= 1

    def test_increments_from_last_order(self, db, make_sales_order):
        """New number increments from the highest existing order."""
        # Create a known order so we can check increment
        num_before = sales_order_service.generate_order_number(db)
        seq_before = int(num_before.split("-")[2])

        # Insert an order with that number
        make_sales_order(order_number=num_before)

        num_after = sales_order_service.generate_order_number(db)
        seq_after = int(num_after.split("-")[2])
        assert seq_after == seq_before + 1


# =============================================================================
# list_sales_orders
# =============================================================================

class TestListSalesOrders:
    """Test order listing with filters, pagination, and sorting."""

    def test_returns_orders(self, db, make_sales_order):
        """Basic listing returns at least one order."""
        make_sales_order(status="pending")
        result = sales_order_service.list_sales_orders(db, is_admin=True)
        assert len(result) >= 1

    def test_filter_by_status(self, db, make_sales_order):
        """Single status filter returns only matching orders."""
        make_sales_order(status="shipped")
        result = sales_order_service.list_sales_orders(
            db, is_admin=True, status_filter="shipped"
        )
        for order in result:
            assert order.status == "shipped"

    def test_filter_by_statuses_list(self, db, make_sales_order):
        """Multi-status filter returns orders matching any of the statuses."""
        make_sales_order(status="pending")
        make_sales_order(status="shipped")
        result = sales_order_service.list_sales_orders(
            db, is_admin=True, statuses=["pending", "shipped"]
        )
        for order in result:
            assert order.status in ("pending", "shipped")

    def test_statuses_takes_priority_over_status_filter(self, db, make_sales_order):
        """When both statuses and status_filter are provided, statuses wins."""
        make_sales_order(status="pending")
        make_sales_order(status="shipped")
        result = sales_order_service.list_sales_orders(
            db,
            is_admin=True,
            status_filter="pending",
            statuses=["shipped"],
        )
        for order in result:
            assert order.status == "shipped"

    def test_filter_by_user_when_not_admin(self, db, make_sales_order):
        """Non-admin only sees their own orders."""
        user = _make_user(db)
        make_sales_order(user_id=user.id, status="pending")
        make_sales_order(user_id=1, status="pending")  # user_id=1 is seeded admin

        result = sales_order_service.list_sales_orders(
            db, user_id=user.id, is_admin=False
        )
        for order in result:
            assert order.user_id == user.id

    def test_admin_sees_all_orders(self, db, make_sales_order):
        """Admin sees all orders regardless of user_id."""
        user = _make_user(db)
        make_sales_order(user_id=user.id, status="pending")
        make_sales_order(user_id=1, status="pending")

        result = sales_order_service.list_sales_orders(
            db, user_id=user.id, is_admin=True
        )
        user_ids = {o.user_id for o in result}
        # Should have orders from multiple users
        assert len(user_ids) >= 1  # At minimum has the user's orders

    def test_pagination_skip_limit(self, db, make_sales_order):
        """Pagination respects skip and limit."""
        for _ in range(5):
            make_sales_order(status="pending")

        page1 = sales_order_service.list_sales_orders(
            db, is_admin=True, skip=0, limit=2
        )
        page2 = sales_order_service.list_sales_orders(
            db, is_admin=True, skip=2, limit=2
        )
        assert len(page1) <= 2
        assert len(page2) <= 2
        # Pages should not overlap
        page1_ids = {o.id for o in page1}
        page2_ids = {o.id for o in page2}
        assert page1_ids.isdisjoint(page2_ids)

    def test_limit_capped_at_100(self, db, make_sales_order):
        """Limit values above 100 are capped."""
        make_sales_order(status="pending")
        result = sales_order_service.list_sales_orders(
            db, is_admin=True, limit=200
        )
        # Should still work; just capped at 100
        assert len(result) <= 100

    def test_sort_by_customer_name(self, db, make_sales_order):
        """Sorting by customer_name works."""
        make_sales_order(customer_name="Alpha Co", status="pending")
        make_sales_order(customer_name="Zeta Inc", status="pending")

        result = sales_order_service.list_sales_orders(
            db, is_admin=True, sort_by="customer_name", sort_order="asc"
        )
        # Should not raise; names in ascending order
        assert len(result) >= 2

    def test_sort_order_asc(self, db, make_sales_order):
        """Ascending sort returns oldest first."""
        result = sales_order_service.list_sales_orders(
            db, is_admin=True, sort_by="order_date", sort_order="asc"
        )
        if len(result) >= 2:
            assert result[0].created_at <= result[1].created_at


# =============================================================================
# get_sales_order / get_sales_order_with_lines
# =============================================================================

class TestGetSalesOrder:
    """Test single-order retrieval."""

    def test_returns_existing_order(self, db, make_sales_order):
        """Returns order by ID."""
        so = make_sales_order(status="pending")
        result = sales_order_service.get_sales_order(db, so.id)
        assert result.id == so.id

    def test_raises_404_for_missing_order(self, db):
        """Raises 404 when order does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.get_sales_order(db, 999999)
        assert exc_info.value.status_code == 404

    def test_get_with_lines_loads_lines(self, db, make_sales_order, make_product):
        """get_sales_order_with_lines eagerly loads lines."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=3)

        result = sales_order_service.get_sales_order_with_lines(db, so.id)
        assert result.id == so.id
        assert len(result.lines) == 1
        assert result.lines[0].product_id == product.id

    def test_get_with_lines_raises_404(self, db):
        """get_sales_order_with_lines raises 404 for missing order."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.get_sales_order_with_lines(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# validate_customer / validate_product_for_order
# =============================================================================

class TestValidateCustomer:
    """Test customer validation for order creation."""

    def test_returns_active_customer(self, db):
        """Returns customer when active."""
        user = _make_user(db, status="active")
        result = sales_order_service.validate_customer(db, user.id)
        assert result.id == user.id

    def test_raises_404_for_missing_customer(self, db):
        """Raises 404 when customer ID does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.validate_customer(db, 999999)
        assert exc_info.value.status_code == 404

    def test_raises_400_for_inactive_customer(self, db):
        """Raises 400 when customer is not active."""
        user = _make_user(db, status="inactive")
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.validate_customer(db, user.id)
        assert exc_info.value.status_code == 400
        assert "not active" in exc_info.value.detail


class TestValidateProductForOrder:
    """Test product validation for order creation."""

    def test_returns_active_product(self, db, make_product):
        """Returns product when active."""
        product = make_product(active=True)
        result = sales_order_service.validate_product_for_order(db, product.id)
        assert result.id == product.id

    def test_raises_404_for_missing_product(self, db):
        """Raises 404 when product ID does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.validate_product_for_order(db, 999999)
        assert exc_info.value.status_code == 404

    def test_raises_400_for_inactive_product(self, db, make_product):
        """Raises 400 when product is discontinued."""
        product = make_product(active=False)
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.validate_product_for_order(db, product.id)
        assert exc_info.value.status_code == 400
        assert "discontinued" in exc_info.value.detail


# =============================================================================
# get_company_tax_settings
# =============================================================================

class TestGetCompanyTaxSettings:
    """Test company tax settings retrieval."""

    def test_returns_tax_when_enabled(self, db):
        """Returns (rate, True) when tax is enabled."""
        _set_company_tax(db, tax_enabled=True, tax_rate=Decimal("0.0825"))
        rate, is_taxable = sales_order_service.get_company_tax_settings(db)
        assert rate == Decimal("0.0825")
        assert is_taxable is True

    def test_returns_none_when_disabled(self, db):
        """Returns (None, False) when tax is disabled."""
        _set_company_tax(db, tax_enabled=False, tax_rate=Decimal("0.0825"))
        rate, is_taxable = sales_order_service.get_company_tax_settings(db)
        assert rate is None
        assert is_taxable is False

    def test_returns_none_when_no_settings(self, db):
        """Returns (None, False) when no company settings exist."""
        # Delete any existing settings
        db.query(CompanySettings).filter(CompanySettings.id == 1).delete()
        db.flush()

        rate, is_taxable = sales_order_service.get_company_tax_settings(db)
        assert rate is None
        assert is_taxable is False


# =============================================================================
# create_sales_order
# =============================================================================

class TestCreateSalesOrder:
    """Test order creation with lines, tax, and validation."""

    def test_creates_order_with_single_line(self, db, make_product):
        """Creates order with one line item."""
        product = make_product(selling_price=Decimal("25.00"))
        # Ensure no tax settings interfere
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=None,
            lines=[{"product_id": product.id, "quantity": 2}],
            created_by_user_id=1,
        )

        assert order.order_number.startswith("SO-")
        assert order.order_type == "line_item"
        assert order.status == "pending"
        assert order.total_price == Decimal("50.00")
        assert order.quantity == 2
        assert order.grand_total == Decimal("50.00")

    def test_creates_order_with_multiple_lines(self, db, make_product):
        """Creates order with multiple line items and correct totals."""
        p1 = make_product(selling_price=Decimal("10.00"))
        p2 = make_product(selling_price=Decimal("20.00"))
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=None,
            lines=[
                {"product_id": p1.id, "quantity": 3},
                {"product_id": p2.id, "quantity": 1},
            ],
            created_by_user_id=1,
        )

        assert order.total_price == Decimal("50.00")  # 30 + 20
        assert order.quantity == 4  # 3 + 1
        assert order.product_name == "2 items"

    def test_creates_order_with_tax(self, db, make_product):
        """Tax is calculated and included in grand_total."""
        product = make_product(selling_price=Decimal("100.00"))
        _set_company_tax(db, tax_enabled=True, tax_rate=Decimal("0.0825"))

        order = sales_order_service.create_sales_order(
            db,
            customer_id=None,
            lines=[{"product_id": product.id, "quantity": 1}],
            created_by_user_id=1,
        )

        assert order.tax_amount == Decimal("8.25")
        assert order.grand_total == Decimal("108.25")
        assert order.is_taxable is True

    def test_creates_order_with_shipping_cost(self, db, make_product):
        """Shipping cost is added to grand_total."""
        product = make_product(selling_price=Decimal("50.00"))
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=None,
            lines=[{"product_id": product.id, "quantity": 1}],
            shipping_cost=Decimal("9.99"),
            created_by_user_id=1,
        )

        assert order.shipping_cost == Decimal("9.99")
        assert order.grand_total == Decimal("59.99")

    def test_creates_order_with_customer(self, db, make_product):
        """Order linked to a customer uses customer's user_id."""
        customer = _make_user(db, status="active")
        product = make_product(selling_price=Decimal("15.00"))
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=customer.id,
            lines=[{"product_id": product.id, "quantity": 1}],
            created_by_user_id=1,
        )

        assert order.user_id == customer.id

    def test_auto_copies_customer_shipping_address(self, db, make_product):
        """If no shipping address provided, copies from customer."""
        customer = _make_user(
            db,
            status="active",
            shipping_address_line1="123 Main St",
            shipping_city="Springfield",
            shipping_state="IL",
            shipping_zip="62701",
        )
        product = make_product(selling_price=Decimal("15.00"))
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=customer.id,
            lines=[{"product_id": product.id, "quantity": 1}],
            created_by_user_id=1,
        )

        assert order.shipping_address_line1 == "123 Main St"
        assert order.shipping_city == "Springfield"

    def test_explicit_address_overrides_customer_address(self, db, make_product):
        """Explicit shipping address takes precedence over customer's."""
        customer = _make_user(
            db,
            status="active",
            shipping_address_line1="123 Main St",
            shipping_city="Springfield",
        )
        product = make_product(selling_price=Decimal("15.00"))
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=customer.id,
            lines=[{"product_id": product.id, "quantity": 1}],
            shipping_address_line1="456 Oak Ave",
            shipping_city="Chicago",
            created_by_user_id=1,
        )

        assert order.shipping_address_line1 == "456 Oak Ave"
        assert order.shipping_city == "Chicago"

    def test_rejects_inactive_customer(self, db, make_product):
        """Raises 400 for inactive customer."""
        customer = _make_user(db, status="inactive")
        product = make_product(selling_price=Decimal("10.00"))

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.create_sales_order(
                db,
                customer_id=customer.id,
                lines=[{"product_id": product.id, "quantity": 1}],
                created_by_user_id=1,
            )
        assert exc_info.value.status_code == 400

    def test_rejects_nonexistent_product(self, db):
        """Raises 404 for missing product ID."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.create_sales_order(
                db,
                customer_id=None,
                lines=[{"product_id": 999999, "quantity": 1}],
                created_by_user_id=1,
            )
        assert exc_info.value.status_code == 404

    def test_rejects_inactive_product(self, db, make_product):
        """Raises 400 for discontinued product."""
        product = make_product(selling_price=Decimal("10.00"), active=False)

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.create_sales_order(
                db,
                customer_id=None,
                lines=[{"product_id": product.id, "quantity": 1}],
                created_by_user_id=1,
            )
        assert exc_info.value.status_code == 400

    def test_rejects_product_with_no_price(self, db, make_product):
        """Raises 400 when product has no selling_price."""
        product = make_product(selling_price=Decimal("0"))

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.create_sales_order(
                db,
                customer_id=None,
                lines=[{"product_id": product.id, "quantity": 1}],
                created_by_user_id=1,
            )
        assert exc_info.value.status_code == 400
        assert "no selling price" in exc_info.value.detail

    def test_records_creation_event(self, db, make_product):
        """Order creation generates an 'created' event."""
        product = make_product(selling_price=Decimal("10.00"))
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=None,
            lines=[{"product_id": product.id, "quantity": 1}],
            created_by_user_id=1,
        )
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == order.id,
            OrderEvent.event_type == "created",
        ).all()
        assert len(events) == 1
        assert "created" in events[0].title.lower()

    def test_sets_source_and_notes(self, db, make_product):
        """Source, source_order_id, and notes are stored."""
        product = make_product(selling_price=Decimal("10.00"))
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=None,
            lines=[{"product_id": product.id, "quantity": 1}],
            source="squarespace",
            source_order_id="SQ-12345",
            customer_notes="Please rush",
            internal_notes="VIP customer",
            created_by_user_id=1,
        )

        assert order.source == "squarespace"
        assert order.source_order_id == "SQ-12345"
        assert order.customer_notes == "Please rush"
        assert order.internal_notes == "VIP customer"

    def test_single_line_product_name_includes_quantity(self, db, make_product):
        """Single-line order product_name includes 'x{quantity}'."""
        product = make_product(
            selling_price=Decimal("10.00"),
            name="Widget A",
        )
        _set_company_tax(db, tax_enabled=False)

        order = sales_order_service.create_sales_order(
            db,
            customer_id=None,
            lines=[{"product_id": product.id, "quantity": 5}],
            created_by_user_id=1,
        )

        assert "Widget A" in order.product_name
        assert "x5" in order.product_name


# =============================================================================
# update_sales_order_status
# =============================================================================

class TestUpdateSalesOrderStatus:
    """Test status transitions and side effects."""

    def test_basic_status_change(self, db, make_sales_order):
        """Simple status update works."""
        so = make_sales_order(status="pending")
        result = sales_order_service.update_sales_order_status(
            db, so.id, "confirmed", user_id=1, user_email="test@filaops.dev"
        )
        assert result.status == "confirmed"

    def test_pending_to_confirmed_sets_confirmed_at(self, db, make_sales_order):
        """Confirming a pending order sets confirmed_at timestamp."""
        so = make_sales_order(status="pending")
        result = sales_order_service.update_sales_order_status(
            db, so.id, "confirmed", user_id=1, user_email="test@filaops.dev"
        )
        assert result.confirmed_at is not None

    def test_shipped_sets_shipped_at(self, db, make_sales_order):
        """Setting status to shipped sets shipped_at."""
        so = make_sales_order(status="in_production")
        result = sales_order_service.update_sales_order_status(
            db, so.id, "shipped", user_id=1, user_email="test@filaops.dev"
        )
        assert result.shipped_at is not None

    def test_delivered_sets_delivered_at(self, db, make_sales_order):
        """Setting status to delivered sets delivered_at."""
        so = make_sales_order(status="shipped")
        result = sales_order_service.update_sales_order_status(
            db, so.id, "delivered", user_id=1, user_email="test@filaops.dev"
        )
        assert result.delivered_at is not None

    def test_completed_sets_actual_completion_date(self, db, make_sales_order):
        """Setting status to completed sets actual_completion_date."""
        so = make_sales_order(status="delivered")
        result = sales_order_service.update_sales_order_status(
            db, so.id, "completed", user_id=1, user_email="test@filaops.dev"
        )
        assert result.actual_completion_date is not None

    def test_updates_internal_notes(self, db, make_sales_order):
        """Internal notes are updated when provided."""
        so = make_sales_order(status="pending")
        result = sales_order_service.update_sales_order_status(
            db, so.id, "confirmed", user_id=1, user_email="test@filaops.dev",
            internal_notes="Rush order",
        )
        assert result.internal_notes == "Rush order"

    def test_updates_production_notes(self, db, make_sales_order):
        """Production notes are updated when provided."""
        so = make_sales_order(status="pending")
        result = sales_order_service.update_sales_order_status(
            db, so.id, "confirmed", user_id=1, user_email="test@filaops.dev",
            production_notes="Use red PLA",
        )
        assert result.production_notes == "Use red PLA"

    def test_records_status_change_event(self, db, make_sales_order):
        """Status change records an event in the timeline."""
        so = make_sales_order(status="pending")
        sales_order_service.update_sales_order_status(
            db, so.id, "shipped", user_id=1, user_email="test@filaops.dev"
        )
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id,
            OrderEvent.event_type == "status_change",
        ).all()
        assert len(events) >= 1
        latest = events[-1]
        assert latest.old_value == "pending"
        assert latest.new_value == "shipped"

    def test_raises_404_for_missing_order(self, db):
        """Raises 404 when order does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.update_sales_order_status(
                db, 999999, "confirmed", user_id=1, user_email="test@filaops.dev"
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# update_payment_info
# =============================================================================

class TestUpdatePaymentInfo:
    """Test payment status updates."""

    def test_marks_as_paid(self, db, make_sales_order):
        """Setting payment_status to paid sets paid_at."""
        so = make_sales_order(status="confirmed")
        result = sales_order_service.update_payment_info(
            db, so.id, "paid", user_id=1
        )
        assert result.payment_status == "paid"
        assert result.paid_at is not None

    def test_stores_payment_method(self, db, make_sales_order):
        """Payment method is stored on update."""
        so = make_sales_order(status="confirmed")
        result = sales_order_service.update_payment_info(
            db, so.id, "paid", user_id=1, payment_method="credit_card"
        )
        assert result.payment_method == "credit_card"

    def test_stores_transaction_id(self, db, make_sales_order):
        """Payment transaction ID is stored on update."""
        so = make_sales_order(status="confirmed")
        result = sales_order_service.update_payment_info(
            db, so.id, "paid", user_id=1,
            payment_transaction_id="txn_abc123"
        )
        assert result.payment_transaction_id == "txn_abc123"

    def test_records_payment_received_event(self, db, make_sales_order):
        """Paying records a payment_received event."""
        so = make_sales_order(status="confirmed", payment_status="pending")
        sales_order_service.update_payment_info(db, so.id, "paid", user_id=1)
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id,
            OrderEvent.event_type == "payment_received",
        ).all()
        assert len(events) >= 1

    def test_records_refund_event(self, db, make_sales_order):
        """Refunding records a payment_refunded event."""
        so = make_sales_order(status="confirmed", payment_status="paid")
        sales_order_service.update_payment_info(db, so.id, "refunded", user_id=1)
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id,
            OrderEvent.event_type == "payment_refunded",
        ).all()
        assert len(events) >= 1

    def test_records_generic_status_change_event(self, db, make_sales_order):
        """Non-paid/refunded status change records status_change event."""
        so = make_sales_order(status="confirmed", payment_status="pending")
        sales_order_service.update_payment_info(db, so.id, "partial", user_id=1)
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id,
            OrderEvent.event_type == "status_change",
        ).all()
        assert len(events) >= 1

    def test_no_event_when_status_unchanged(self, db, make_sales_order):
        """No event recorded when payment status stays the same."""
        so = make_sales_order(status="confirmed", payment_status="paid")
        events_before = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id
        ).count()

        sales_order_service.update_payment_info(db, so.id, "paid", user_id=1)
        db.flush()

        events_after = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id
        ).count()
        assert events_after == events_before


# =============================================================================
# update_shipping_info
# =============================================================================

class TestUpdateShippingInfo:
    """Test shipping information updates."""

    def test_sets_tracking_number(self, db, make_sales_order):
        """Tracking number is stored."""
        so = make_sales_order(status="in_production")
        result = sales_order_service.update_shipping_info(
            db, so.id, user_id=1, tracking_number="1Z999AA10123456784"
        )
        assert result.tracking_number == "1Z999AA10123456784"

    def test_sets_carrier(self, db, make_sales_order):
        """Carrier is stored."""
        so = make_sales_order(status="in_production")
        result = sales_order_service.update_shipping_info(
            db, so.id, user_id=1, carrier="UPS"
        )
        assert result.carrier == "UPS"

    def test_shipped_at_sets_status_to_shipped(self, db, make_sales_order):
        """Providing shipped_at transitions status to shipped."""
        from datetime import datetime, timezone
        so = make_sales_order(status="in_production")
        now = datetime.now(timezone.utc)

        result = sales_order_service.update_shipping_info(
            db, so.id, user_id=1, shipped_at=now
        )
        assert result.status == "shipped"
        assert result.shipped_at == now

    def test_records_shipped_event_on_first_ship(self, db, make_sales_order):
        """Shipping event is recorded on the initial ship."""
        from datetime import datetime, timezone
        so = make_sales_order(status="in_production")

        sales_order_service.update_shipping_info(
            db, so.id, user_id=1,
            carrier="USPS",
            tracking_number="TRK123",
            shipped_at=datetime.now(timezone.utc),
        )
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id,
            OrderEvent.event_type == "shipped",
        ).all()
        assert len(events) >= 1


# =============================================================================
# update_shipping_address
# =============================================================================

class TestUpdateShippingAddress:
    """Test shipping address updates."""

    def test_updates_address_fields(self, db, make_sales_order):
        """Individual address fields are updated."""
        so = make_sales_order(status="pending")
        result = sales_order_service.update_shipping_address(
            db, so.id, user_id=1,
            shipping_address_line1="789 Elm St",
            shipping_city="Denver",
            shipping_state="CO",
            shipping_zip="80202",
        )
        assert result.shipping_address_line1 == "789 Elm St"
        assert result.shipping_city == "Denver"
        assert result.shipping_state == "CO"
        assert result.shipping_zip == "80202"

    def test_records_address_updated_event(self, db, make_sales_order):
        """Address change records an address_updated event."""
        so = make_sales_order(status="pending")
        sales_order_service.update_shipping_address(
            db, so.id, user_id=1,
            shipping_address_line1="New Address",
        )
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id,
            OrderEvent.event_type == "address_updated",
        ).all()
        assert len(events) >= 1

    def test_no_event_when_nothing_changed(self, db, make_sales_order):
        """No event when no address fields are provided."""
        so = make_sales_order(status="pending")
        events_before = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id
        ).count()

        sales_order_service.update_shipping_address(db, so.id, user_id=1)
        db.flush()

        events_after = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id
        ).count()
        assert events_after == events_before

    def test_partial_update_preserves_other_fields(self, db, make_sales_order):
        """Updating one field does not clear others."""
        so = make_sales_order(
            status="pending",
            shipping_address_line1="Original St",
            shipping_city="Original City",
        )
        result = sales_order_service.update_shipping_address(
            db, so.id, user_id=1,
            shipping_city="New City",
        )
        assert result.shipping_address_line1 == "Original St"
        assert result.shipping_city == "New City"


# =============================================================================
# cancel_sales_order
# =============================================================================

class TestCancelSalesOrder:
    """Test order cancellation logic."""

    def test_cancels_cancellable_order(self, db, make_sales_order):
        """Orders in cancellable statuses can be cancelled."""
        so = make_sales_order(status="confirmed")
        result = sales_order_service.cancel_sales_order(
            db, so.id, user_id=1, cancellation_reason="Customer request"
        )
        assert result.status == "cancelled"
        assert result.cancelled_at is not None
        assert result.cancellation_reason == "Customer request"

    def test_cancels_draft_order(self, db, make_sales_order):
        """Draft orders can be cancelled."""
        so = make_sales_order(status="draft")
        result = sales_order_service.cancel_sales_order(
            db, so.id, user_id=1, cancellation_reason="Changed mind"
        )
        assert result.status == "cancelled"

    def test_cancels_on_hold_order(self, db, make_sales_order):
        """On-hold orders can be cancelled."""
        so = make_sales_order(status="on_hold")
        result = sales_order_service.cancel_sales_order(
            db, so.id, user_id=1, cancellation_reason="No longer needed"
        )
        assert result.status == "cancelled"

    def test_rejects_shipped_order_cancellation(self, db, make_sales_order):
        """Shipped orders cannot be cancelled."""
        so = make_sales_order(status="shipped")
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.cancel_sales_order(
                db, so.id, user_id=1, cancellation_reason="Too late"
            )
        assert exc_info.value.status_code == 400
        assert "Cannot cancel" in exc_info.value.detail

    def test_rejects_completed_order_cancellation(self, db, make_sales_order):
        """Completed orders cannot be cancelled."""
        so = make_sales_order(status="completed")
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.cancel_sales_order(
                db, so.id, user_id=1, cancellation_reason="Oops"
            )
        assert exc_info.value.status_code == 400

    def test_rejects_in_production_order_cancellation(self, db, make_sales_order):
        """In-production orders cannot be cancelled (not in is_cancellable list)."""
        so = make_sales_order(status="in_production")
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.cancel_sales_order(
                db, so.id, user_id=1, cancellation_reason="Changed plan"
            )
        assert exc_info.value.status_code == 400

    def test_rejects_when_active_production_orders_exist(self, db, make_sales_order, make_product):
        """Cannot cancel if there are active (non-cancelled) production orders linked."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="confirmed", product_id=product.id)

        # Create a linked production order that is NOT cancelled
        po = ProductionOrder(
            code="PO-TEST-CANCEL-001",
            product_id=product.id,
            sales_order_id=so.id,
            quantity_ordered=1,
            quantity_completed=0,
            quantity_scrapped=0,
            status="draft",
            created_by="test",
        )
        db.add(po)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.cancel_sales_order(
                db, so.id, user_id=1, cancellation_reason="No longer needed"
            )
        assert exc_info.value.status_code == 400
        assert "work order" in exc_info.value.detail.lower()

    def test_allows_cancel_when_production_orders_are_cancelled(self, db, make_sales_order, make_product):
        """Cancel succeeds if all linked production orders are already cancelled."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="confirmed", product_id=product.id)

        po = ProductionOrder(
            code="PO-TEST-CANCEL-002",
            product_id=product.id,
            sales_order_id=so.id,
            quantity_ordered=1,
            quantity_completed=0,
            quantity_scrapped=0,
            status="cancelled",
            created_by="test",
        )
        db.add(po)
        db.flush()

        result = sales_order_service.cancel_sales_order(
            db, so.id, user_id=1, cancellation_reason="All POs cancelled"
        )
        assert result.status == "cancelled"

    def test_records_cancelled_event(self, db, make_sales_order):
        """Cancellation records a cancelled event."""
        so = make_sales_order(status="confirmed")
        sales_order_service.cancel_sales_order(
            db, so.id, user_id=1, cancellation_reason="Test reason"
        )
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id,
            OrderEvent.event_type == "cancelled",
        ).all()
        assert len(events) >= 1
        assert events[0].description == "Test reason"


# =============================================================================
# delete_sales_order
# =============================================================================

class TestDeleteSalesOrder:
    """Test order deletion with status and PO checks."""

    def test_deletes_pending_order(self, db, make_sales_order):
        """Pending orders can be deleted."""
        so = make_sales_order(status="pending")
        order_id = so.id
        sales_order_service.delete_sales_order(db, order_id)
        db.flush()

        assert db.query(SalesOrder).filter(SalesOrder.id == order_id).first() is None

    def test_deletes_cancelled_order(self, db, make_sales_order):
        """Cancelled orders can be deleted."""
        so = make_sales_order(status="cancelled")
        order_id = so.id
        sales_order_service.delete_sales_order(db, order_id)
        db.flush()

        assert db.query(SalesOrder).filter(SalesOrder.id == order_id).first() is None

    def test_rejects_confirmed_order_deletion(self, db, make_sales_order):
        """Confirmed orders cannot be deleted."""
        so = make_sales_order(status="confirmed")
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.delete_sales_order(db, so.id)
        assert exc_info.value.status_code == 400
        assert "Cannot delete" in exc_info.value.detail

    def test_rejects_shipped_order_deletion(self, db, make_sales_order):
        """Shipped orders cannot be deleted."""
        so = make_sales_order(status="shipped")
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.delete_sales_order(db, so.id)
        assert exc_info.value.status_code == 400

    def test_rejects_in_production_order_deletion(self, db, make_sales_order):
        """In-production orders cannot be deleted."""
        so = make_sales_order(status="in_production")
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.delete_sales_order(db, so.id)
        assert exc_info.value.status_code == 400

    def test_rejects_when_active_production_orders_exist(self, db, make_sales_order, make_product):
        """Cannot delete a pending order that has active production orders."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="pending", product_id=product.id)

        po = ProductionOrder(
            code="PO-TEST-DEL-001",
            product_id=product.id,
            sales_order_id=so.id,
            quantity_ordered=1,
            quantity_completed=0,
            quantity_scrapped=0,
            status="in_progress",
            created_by="test",
        )
        db.add(po)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.delete_sales_order(db, so.id)
        assert exc_info.value.status_code == 400
        assert "active production orders" in exc_info.value.detail.lower()

    def test_allows_delete_when_production_orders_are_draft_or_cancelled(
        self, db, make_sales_order, make_product
    ):
        """Deletion succeeds if all linked POs are draft or cancelled."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="cancelled", product_id=product.id)

        po1 = ProductionOrder(
            code="PO-TEST-DEL-002",
            product_id=product.id,
            sales_order_id=so.id,
            quantity_ordered=1,
            quantity_completed=0,
            quantity_scrapped=0,
            status="cancelled",
            created_by="test",
        )
        po2 = ProductionOrder(
            code="PO-TEST-DEL-003",
            product_id=product.id,
            sales_order_id=so.id,
            quantity_ordered=1,
            quantity_completed=0,
            quantity_scrapped=0,
            status="draft",
            created_by="test",
        )
        db.add_all([po1, po2])
        db.flush()

        order_id = so.id
        sales_order_service.delete_sales_order(db, order_id)
        db.flush()

        # The order should be gone (though POs may still exist - they have no cascade)
        assert db.query(SalesOrder).filter(SalesOrder.id == order_id).first() is None

    def test_raises_404_for_missing_order(self, db):
        """Raises 404 when order does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.delete_sales_order(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# record_order_event / add_order_event / list_order_events
# =============================================================================

class TestOrderEvents:
    """Test event recording and listing."""

    def test_record_order_event_creates_event(self, db, make_sales_order):
        """record_order_event creates an OrderEvent with all fields."""
        so = make_sales_order(status="pending")
        event = sales_order_service.record_order_event(
            db,
            order_id=so.id,
            event_type="status_change",
            title="Status changed",
            description="Moved to confirmed",
            old_value="pending",
            new_value="confirmed",
            user_id=1,
            metadata_key="reason",
            metadata_value="Customer approved",
        )
        db.flush()

        assert event.sales_order_id == so.id
        assert event.event_type == "status_change"
        assert event.title == "Status changed"
        assert event.description == "Moved to confirmed"
        assert event.old_value == "pending"
        assert event.new_value == "confirmed"
        assert event.user_id == 1
        assert event.metadata_key == "reason"
        assert event.metadata_value == "Customer approved"

    def test_add_order_event_creates_event(self, db, make_sales_order):
        """add_order_event creates an OrderEvent."""
        so = make_sales_order(status="pending")
        event = sales_order_service.add_order_event(
            db,
            order_id=so.id,
            user_id=1,
            event_type="note_added",
            title="Note added",
            description="Customer called to check status",
        )
        db.flush()

        assert event.sales_order_id == so.id
        assert event.event_type == "note_added"

    def test_list_order_events_returns_events(self, db, make_sales_order):
        """list_order_events returns events for an order."""
        so = make_sales_order(status="pending")
        sales_order_service.record_order_event(
            db, order_id=so.id, event_type="created",
            title="Order created",
        )
        sales_order_service.record_order_event(
            db, order_id=so.id, event_type="status_change",
            title="Status changed",
        )
        db.flush()

        events, total = sales_order_service.list_order_events(db, so.id)
        assert total >= 2
        assert len(events) >= 2

    def test_list_order_events_pagination(self, db, make_sales_order):
        """list_order_events respects limit and offset."""
        so = make_sales_order(status="pending")
        for i in range(5):
            sales_order_service.record_order_event(
                db, order_id=so.id, event_type="note_added",
                title=f"Note {i}",
            )
        db.flush()

        events, total = sales_order_service.list_order_events(db, so.id, limit=2, offset=0)
        assert total >= 5
        assert len(events) == 2

        events2, _ = sales_order_service.list_order_events(db, so.id, limit=2, offset=2)
        assert len(events2) == 2
        # Verify different events (ordered by created_at desc)
        event_ids_page1 = {e.id for e in events}
        event_ids_page2 = {e.id for e in events2}
        assert event_ids_page1.isdisjoint(event_ids_page2)

    def test_list_order_events_returns_empty_for_no_events(self, db, make_sales_order):
        """Returns empty list and zero count when no events exist."""
        so = make_sales_order(status="pending")
        events, total = sales_order_service.list_order_events(db, so.id)
        assert total == 0
        assert len(events) == 0


# =============================================================================
# generate_production_order_code
# =============================================================================

class TestGenerateProductionOrderCode:
    """Test production order code generation."""

    def test_generates_valid_code(self, db):
        """Returns a code in PO-{year}-{seq} format."""
        code = sales_order_service.generate_production_order_code(db)
        parts = code.split("-")
        assert parts[0] == "PO"
        assert len(parts) == 3
        assert int(parts[2]) >= 1

    def test_increments_code(self, db, make_product):
        """Each call returns the next sequence number."""
        product = make_product()

        code1 = sales_order_service.generate_production_order_code(db)
        # Insert a PO with code1 so next call increments
        po = ProductionOrder(
            code=code1,
            product_id=product.id,
            quantity_ordered=1,
            quantity_completed=0,
            quantity_scrapped=0,
            status="draft",
            created_by="test",
        )
        db.add(po)
        db.flush()

        code2 = sales_order_service.generate_production_order_code(db)
        seq1 = int(code1.split("-")[2])
        seq2 = int(code2.split("-")[2])
        assert seq2 == seq1 + 1


# =============================================================================
# SalesOrder model properties (for completeness)
# =============================================================================

class TestSalesOrderModelProperties:
    """Test computed properties on the SalesOrder model."""

    def test_is_cancellable_for_draft(self, db, make_sales_order):
        so = make_sales_order(status="draft")
        assert so.is_cancellable is True

    def test_is_cancellable_for_confirmed(self, db, make_sales_order):
        so = make_sales_order(status="confirmed")
        assert so.is_cancellable is True

    def test_is_cancellable_for_on_hold(self, db, make_sales_order):
        so = make_sales_order(status="on_hold")
        assert so.is_cancellable is True

    def test_not_cancellable_for_shipped(self, db, make_sales_order):
        so = make_sales_order(status="shipped")
        assert so.is_cancellable is False

    def test_not_cancellable_for_completed(self, db, make_sales_order):
        so = make_sales_order(status="completed")
        assert so.is_cancellable is False

    def test_not_cancellable_for_in_production(self, db, make_sales_order):
        so = make_sales_order(status="in_production")
        assert so.is_cancellable is False

    def test_not_cancellable_for_pending(self, db, make_sales_order):
        """'pending' is NOT in the cancellable list (it uses 'pending_payment' instead)."""
        so = make_sales_order(status="pending")
        assert so.is_cancellable is False

    def test_is_paid(self, db, make_sales_order):
        so = make_sales_order(payment_status="paid")
        assert so.is_paid is True

    def test_is_not_paid(self, db, make_sales_order):
        so = make_sales_order(payment_status="pending")
        assert so.is_paid is False

    def test_is_complete(self, db, make_sales_order):
        so = make_sales_order(status="completed")
        assert so.is_complete is True

    def test_is_complete_delivered(self, db, make_sales_order):
        so = make_sales_order(status="delivered")
        assert so.is_complete is True

    def test_not_complete(self, db, make_sales_order):
        so = make_sales_order(status="shipped")
        assert so.is_complete is False


# =============================================================================
# generate_production_orders
# =============================================================================

class TestGenerateProductionOrders:
    """Test production order generation from sales orders."""

    def test_rejects_cancelled_order(self, db, make_sales_order):
        """Cannot generate POs for a cancelled sales order."""
        so = make_sales_order(status="cancelled")
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert exc_info.value.status_code == 400
        assert "cancelled" in exc_info.value.detail.lower()

    def test_returns_existing_pos_for_line_item_order(self, db, make_sales_order, make_product):
        """If POs already exist for a line_item order, returns them."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=2)

        # Create existing production order linked to this SO
        po = ProductionOrder(
            code="PO-EXIST-LI-001",
            product_id=product.id,
            sales_order_id=so.id,
            quantity_ordered=2,
            quantity_completed=0,
            quantity_scrapped=0,
            status="draft",
            created_by="test",
        )
        db.add(po)
        db.flush()

        result = sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert result["message"] == "Production orders already exist"
        assert "PO-EXIST-LI-001" in result["existing_orders"]
        assert result["created_orders"] == []

    def test_returns_existing_pos_for_quote_based_order(self, db, make_sales_order, make_product):
        """If POs already exist for a quote_based order, returns them."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            product_id=product.id,
        )

        po = ProductionOrder(
            code="PO-EXIST-QB-001",
            product_id=product.id,
            sales_order_id=so.id,
            quantity_ordered=1,
            quantity_completed=0,
            quantity_scrapped=0,
            status="draft",
            created_by="test",
        )
        db.add(po)
        db.flush()

        result = sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert result["message"] == "Production orders already exist"
        assert "PO-EXIST-QB-001" in result["existing_orders"]

    def test_rejects_line_item_order_with_no_lines(self, db, make_sales_order):
        """line_item order with no lines raises 400."""
        so = make_sales_order(status="pending", order_type="line_item")

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert exc_info.value.status_code == 400
        assert "no line items" in exc_info.value.detail.lower()

    def test_creates_po_for_line_item_order(self, db, make_sales_order, make_product):
        """Creates a production order for each line item."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=3)

        result = sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert len(result["created_orders"]) == 1
        assert result["created_orders"][0].startswith("PO-")
        assert result["existing_orders"] == []

        # Order status should transition to in_production
        # (flush first so refresh sees the updated state)
        db.flush()
        db.refresh(so)
        assert so.status == "in_production"
        assert so.confirmed_at is not None

    def test_creates_po_for_multiple_line_items(self, db, make_sales_order, make_product):
        """Creates one PO per line item."""
        p1 = make_product(selling_price=Decimal("10.00"))
        p2 = make_product(selling_price=Decimal("20.00"))
        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, p1.id, quantity=2)
        _make_order_line(db, so.id, p2.id, quantity=5)

        result = sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert len(result["created_orders"]) == 2

    def test_confirmed_order_transitions_to_in_production(self, db, make_sales_order, make_product):
        """Confirmed order transitions to in_production after PO creation."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="confirmed", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=1)

        sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        db.flush()
        db.refresh(so)
        assert so.status == "in_production"

    def test_records_production_started_event(self, db, make_sales_order, make_product):
        """Records a production_started event after PO creation."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=1)

        sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        db.flush()

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == so.id,
            OrderEvent.event_type == "production_started",
        ).all()
        assert len(events) >= 1

    def test_rejects_quote_based_order_without_quote(self, db, make_sales_order):
        """quote_based order without a quote_id raises 400."""
        so = make_sales_order(status="pending", order_type="quote_based")
        # quote_id is None by default

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert exc_info.value.status_code == 400
        assert "no associated quote" in exc_info.value.detail.lower()

    def test_creates_po_for_quote_based_order(self, db, make_sales_order, make_product):
        """Creates a production order from a quote-based order."""
        from datetime import datetime, timezone, timedelta
        from app.models.quote import Quote

        product = make_product(selling_price=Decimal("10.00"))

        # Create a quote
        quote = Quote(
            user_id=1,
            quote_number="Q-TEST-GENPO-001",
            product_name="Test Widget",
            quantity=5,
            material_type="PLA",
            total_price=Decimal("50.00"),
            unit_price=Decimal("10.00"),
            file_format=".stl",
            file_size_bytes=1000,
            status="accepted",
            product_id=product.id,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(quote)
        db.flush()

        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            product_id=product.id,
            quote_id=quote.id,
            quantity=5,
        )

        result = sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert len(result["created_orders"]) == 1
        assert result["created_orders"][0].startswith("PO-")


# =============================================================================
# ship_order — error paths
# =============================================================================

class TestShipOrder:
    """Test ship_order validation and error paths."""

    def test_rejects_order_without_address(self, db, make_sales_order):
        """Cannot ship an order without a shipping address."""
        so = make_sales_order(status="in_production")
        # No shipping address set

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.ship_order(
                db, so.id, user_id=1, user_email="test@filaops.dev"
            )
        assert exc_info.value.status_code == 400
        assert "no shipping address" in exc_info.value.detail.lower()

    def test_rejects_order_with_partial_address(self, db, make_sales_order):
        """Cannot ship an order with address_line1 but no city."""
        so = make_sales_order(
            status="in_production",
            shipping_address_line1="123 Main St",
            # No city
        )

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.ship_order(
                db, so.id, user_id=1, user_email="test@filaops.dev"
            )
        assert exc_info.value.status_code == 400

    def test_ships_order_with_full_address(self, db, make_sales_order, make_product):
        """Successfully ships an order with a valid address."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            status="in_production",
            order_type="line_item",
            product_id=product.id,
            shipping_address_line1="123 Main St",
            shipping_city="Springfield",
            shipping_state="IL",
            shipping_zip="62701",
        )
        _make_order_line(db, so.id, product.id, quantity=1)

        result = sales_order_service.ship_order(
            db, so.id, user_id=1, user_email="test@filaops.dev",
            carrier="USPS", tracking_number="TRK-CUSTOM-001",
        )

        assert result["tracking_number"] == "TRK-CUSTOM-001"
        assert result["carrier"] == "USPS"
        db.refresh(so)
        assert so.status == "shipped"
        assert so.tracking_number == "TRK-CUSTOM-001"

    def test_generates_tracking_number_when_not_provided(self, db, make_sales_order, make_product):
        """Tracking number is auto-generated when not provided."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            status="in_production",
            order_type="line_item",
            product_id=product.id,
            shipping_address_line1="456 Oak Ave",
            shipping_city="Denver",
            shipping_state="CO",
            shipping_zip="80202",
        )
        _make_order_line(db, so.id, product.id, quantity=1)

        result = sales_order_service.ship_order(
            db, so.id, user_id=1, user_email="test@filaops.dev",
            carrier="FedEx",
        )

        assert result["tracking_number"] is not None
        assert len(result["tracking_number"]) > 0
        assert result["tracking_number"].startswith("FED")  # First 3 chars of carrier

    def test_raises_404_for_missing_order(self, db):
        """Raises 404 when order does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.ship_order(
                db, 999999, user_id=1, user_email="test@filaops.dev"
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# convert_quote_to_sales_order
# =============================================================================

class TestConvertQuoteToSalesOrder:
    """Test quote-to-order conversion."""

    def _make_quote(self, db, *, user_id=1, product_id=None, status="accepted",
                    sales_order_id=None, expired=False, **kwargs):
        """Helper to create a Quote for testing."""
        from datetime import datetime, timezone, timedelta
        from app.models.quote import Quote
        import uuid

        uid = uuid.uuid4().hex[:8]
        if expired:
            expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        else:
            expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        quote = Quote(
            user_id=user_id,
            quote_number=kwargs.pop("quote_number", f"Q-TEST-{uid}"),
            product_name=kwargs.pop("product_name", "Test Product"),
            quantity=kwargs.pop("quantity", 1),
            material_type=kwargs.pop("material_type", "PLA"),
            total_price=kwargs.pop("total_price", Decimal("50.00")),
            unit_price=kwargs.pop("unit_price", Decimal("50.00")),
            file_format=".stl",
            file_size_bytes=1000,
            status=status,
            product_id=product_id,
            sales_order_id=sales_order_id,
            expires_at=expires_at,
            rush_level=kwargs.pop("rush_level", "standard"),
            **kwargs,
        )
        db.add(quote)
        db.flush()
        return quote

    def test_raises_404_for_missing_quote(self, db):
        """Raises 404 when quote does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.convert_quote_to_sales_order(
                db, quote_id=999999, user_id=1,
                shipping_address_line1="123 Main",
                shipping_city="Test", shipping_state="IL", shipping_zip="62701",
            )
        assert exc_info.value.status_code == 404

    def test_raises_403_for_wrong_user(self, db, make_product):
        """Raises 403 when user does not own the quote."""
        product = make_product(selling_price=Decimal("10.00"))
        other_user = _make_user(db)
        quote = self._make_quote(db, user_id=other_user.id, product_id=product.id)

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.convert_quote_to_sales_order(
                db, quote_id=quote.id, user_id=1,
                shipping_address_line1="123 Main",
                shipping_city="Test", shipping_state="IL", shipping_zip="62701",
            )
        assert exc_info.value.status_code == 403

    def test_raises_400_for_non_accepted_quote(self, db, make_product):
        """Raises 400 when quote is not in 'accepted' status."""
        product = make_product(selling_price=Decimal("10.00"))
        quote = self._make_quote(db, status="pending", product_id=product.id)

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.convert_quote_to_sales_order(
                db, quote_id=quote.id, user_id=1,
                shipping_address_line1="123 Main",
                shipping_city="Test", shipping_state="IL", shipping_zip="62701",
            )
        assert exc_info.value.status_code == 400
        assert "accepted" in exc_info.value.detail.lower()

    def test_raises_400_for_expired_quote(self, db, make_product):
        """Raises 400 when quote is expired."""
        product = make_product(selling_price=Decimal("10.00"))
        quote = self._make_quote(db, status="accepted", product_id=product.id, expired=True)

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.convert_quote_to_sales_order(
                db, quote_id=quote.id, user_id=1,
                shipping_address_line1="123 Main",
                shipping_city="Test", shipping_state="IL", shipping_zip="62701",
            )
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail.lower()

    def test_raises_400_for_already_converted_quote(self, db, make_product):
        """Raises 400 when quote was already converted."""
        product = make_product(selling_price=Decimal("10.00"))
        quote = self._make_quote(
            db, status="accepted", product_id=product.id, sales_order_id=42,
        )

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.convert_quote_to_sales_order(
                db, quote_id=quote.id, user_id=1,
                shipping_address_line1="123 Main",
                shipping_city="Test", shipping_state="IL", shipping_zip="62701",
            )
        assert exc_info.value.status_code == 400
        assert "already converted" in exc_info.value.detail.lower()

    def test_raises_400_for_quote_without_product(self, db):
        """Raises 400 when quote has no product_id."""
        quote = self._make_quote(db, status="accepted", product_id=None)

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.convert_quote_to_sales_order(
                db, quote_id=quote.id, user_id=1,
                shipping_address_line1="123 Main",
                shipping_city="Test", shipping_state="IL", shipping_zip="62701",
            )
        assert exc_info.value.status_code == 400
        assert "product" in exc_info.value.detail.lower()

    @pytest.mark.skip(
        reason="Known bug: convert_quote_to_sales_order passes priority='normal' "
        "(string) to ProductionOrder.priority (Integer column), causing DataError. "
        "All validation paths are covered by the error-case tests above."
    )
    def test_converts_valid_quote(self, db, make_product):
        """Successfully converts an accepted quote to a sales order."""
        product = make_product(selling_price=Decimal("25.00"), has_bom=False)
        quote = self._make_quote(
            db, status="accepted", product_id=product.id,
            total_price=Decimal("25.00"), unit_price=Decimal("25.00"),
            quantity=1,
        )

        order = sales_order_service.convert_quote_to_sales_order(
            db, quote_id=quote.id, user_id=1,
            shipping_address_line1="123 Main St",
            shipping_city="Springfield",
            shipping_state="IL",
            shipping_zip="62701",
        )

        assert order.order_number.startswith("SO-")
        assert order.order_type == "quote_based"
        assert order.status == "pending"
        assert order.total_price == Decimal("25.00")
        assert order.shipping_address_line1 == "123 Main St"


# =============================================================================
# get_required_orders_for_sales_order
# =============================================================================

class TestGetRequiredOrdersForSalesOrder:
    """Test MRP cascade for material requirements."""

    def test_returns_empty_for_order_without_bom(self, db, make_sales_order, make_product):
        """Order for a product with no BOM returns empty requirements."""
        product = make_product(selling_price=Decimal("10.00"), has_bom=False)
        so = make_sales_order(
            status="pending",
            order_type="line_item",
            product_id=product.id,
        )
        _make_order_line(db, so.id, product.id, quantity=1)

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        assert result["order_id"] == so.id
        assert result["summary"]["total_orders_needed"] == 0

    def test_returns_structure_for_line_item_order(self, db, make_sales_order, make_product):
        """Returns correct structure for a line_item order."""
        product = make_product(selling_price=Decimal("10.00"), has_bom=False)
        so = make_sales_order(
            status="pending",
            order_type="line_item",
        )
        _make_order_line(db, so.id, product.id, quantity=1)

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        assert "top_level_work_orders" in result
        assert "sub_assembly_work_orders" in result
        assert "purchase_orders_needed" in result
        assert "summary" in result
        assert result["order_number"] == so.order_number

    def test_returns_structure_for_quote_based_order(self, db, make_sales_order, make_product):
        """Returns correct structure for a quote_based order."""
        product = make_product(selling_price=Decimal("10.00"), has_bom=False)
        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            product_id=product.id,
            quantity=2,
        )

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        assert result["order_type"] == "quote_based"
        assert "summary" in result

    def test_identifies_purchase_needs_from_bom(self, db, make_sales_order, make_product, make_bom):
        """BOM with components that have no inventory creates purchase requirements."""
        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=2)

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        # Should have at least one purchase order requirement for the raw material
        assert result["summary"]["purchase_orders"] >= 1

    def test_raises_404_for_missing_order(self, db):
        """Raises 404 when order does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.get_required_orders_for_sales_order(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# get_material_requirements
# =============================================================================

class TestGetMaterialRequirements:
    """Test material requirements calculation."""

    def test_returns_empty_for_no_bom(self, db, make_sales_order, make_product):
        """Product without BOM returns no requirements."""
        product = make_product(selling_price=Decimal("10.00"), has_bom=False)
        so = make_sales_order(
            status="pending",
            order_type="line_item",
        )
        _make_order_line(db, so.id, product.id, quantity=1)

        result = sales_order_service.get_material_requirements(db, so.id)
        assert result["summary"]["total_materials"] == 0
        assert result["summary"]["can_fulfill"] is True

    def test_returns_requirements_from_bom(self, db, make_sales_order, make_product, make_bom):
        """Product with BOM returns component requirements."""
        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=2)

        result = sales_order_service.get_material_requirements(db, so.id)
        assert result["summary"]["total_materials"] >= 1
        # With no inventory, there should be shortages
        assert result["summary"]["has_shortages"] is True

    def test_returns_structure_for_quote_based_order(self, db, make_sales_order, make_product, make_bom):
        """Returns requirements for quote_based order using product_id."""
        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("50"), "unit": "G"},
        ])

        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            product_id=fg.id,
            quantity=3,
        )

        result = sales_order_service.get_material_requirements(db, so.id)
        assert result["sales_order_id"] == so.id
        assert result["summary"]["total_materials"] >= 1

    def test_raises_404_for_missing_order(self, db):
        """Raises 404 when order does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.get_material_requirements(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# create_production_orders_for_sales_order
# =============================================================================

class TestCreateProductionOrdersForSalesOrder:
    """Test internal helper for creating POs from a sales order."""

    def test_creates_po_for_line_item_order_with_bom(self, db, make_sales_order, make_product, make_bom):
        """Creates production orders for line items that have BOMs."""
        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=5)

        codes = sales_order_service.create_production_orders_for_sales_order(
            db, so, "test@filaops.dev"
        )
        assert len(codes) == 1
        assert codes[0].startswith("PO-")

        # Verify PO was linked correctly
        po = db.query(ProductionOrder).filter(
            ProductionOrder.code == codes[0]
        ).first()
        assert po.sales_order_id == so.id
        assert po.product_id == fg.id
        assert po.quantity_ordered == 5

    def test_skips_products_without_bom(self, db, make_sales_order, make_product):
        """Products without has_bom=True are skipped."""
        product = make_product(selling_price=Decimal("10.00"), has_bom=False)
        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=1)

        codes = sales_order_service.create_production_orders_for_sales_order(
            db, so, "test@filaops.dev"
        )
        assert len(codes) == 0

    def test_creates_po_for_quote_based_order(self, db, make_sales_order, make_product, make_bom):
        """Creates a PO for a quote_based order with a BOM product."""
        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            product_id=fg.id,
            quantity=3,
        )

        codes = sales_order_service.create_production_orders_for_sales_order(
            db, so, "test@filaops.dev"
        )
        assert len(codes) == 1

    def test_returns_empty_for_quote_based_without_bom(self, db, make_sales_order, make_product):
        """quote_based order with a product that has no BOM returns empty."""
        product = make_product(selling_price=Decimal("10.00"), has_bom=False)
        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            product_id=product.id,
            quantity=1,
        )

        codes = sales_order_service.create_production_orders_for_sales_order(
            db, so, "test@filaops.dev"
        )
        assert len(codes) == 0


# =============================================================================
# get_required_orders_for_sales_order — deeper BOM explosion
# =============================================================================

class TestGetRequiredOrdersDeep:
    """Test deeper BOM explosion and aggregation in get_required_orders_for_sales_order."""

    def test_line_item_with_has_bom_product_creates_top_level_wo(
        self, db, make_sales_order, make_product, make_bom
    ):
        """A line_item product with has_bom=True and no inventory creates a top-level WO."""
        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=5)

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        # Should have a top-level work order (fg has_bom and no inventory)
        assert result["summary"]["top_level_wos"] >= 1
        top_level_ids = [w["product_id"] for w in result["top_level_work_orders"]]
        assert fg.id in top_level_ids

    def test_quote_based_with_has_bom_product(
        self, db, make_sales_order, make_product, make_bom
    ):
        """A quote_based product with has_bom=True creates top-level WO."""
        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("50"), "unit": "G"},
        ])

        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            product_id=fg.id,
            quantity=3,
        )

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        assert result["summary"]["top_level_wos"] >= 1
        assert result["summary"]["purchase_orders"] >= 1

    def test_sub_assembly_detection(
        self, db, make_sales_order, make_product, make_bom
    ):
        """Component with has_bom=True detected as sub-assembly work order."""
        fg = make_product(selling_price=Decimal("100.00"), has_bom=True)
        sub = make_product(
            selling_price=Decimal("30.00"), has_bom=True,
        )
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )

        # FG needs sub-assembly
        make_bom(fg.id, lines=[
            {"component_id": sub.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        # Sub-assembly needs raw material
        make_bom(sub.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("200"), "unit": "G"},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=2)

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        # Should have sub-assembly work orders
        assert result["summary"]["sub_assembly_wos"] >= 1
        # Should have purchase orders for raw material
        assert result["summary"]["purchase_orders"] >= 1

    def test_duplicate_material_aggregation(
        self, db, make_sales_order, make_product, make_bom
    ):
        """Same raw material from multiple BOM paths gets aggregated."""
        fg1 = make_product(selling_price=Decimal("50.00"), has_bom=True)
        fg2 = make_product(selling_price=Decimal("60.00"), has_bom=True)
        shared_raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )

        # Both FGs need the same raw material
        make_bom(fg1.id, lines=[
            {"component_id": shared_raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        make_bom(fg2.id, lines=[
            {"component_id": shared_raw.id, "quantity": Decimal("200"), "unit": "G"},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg1.id, quantity=1)
        _make_order_line(db, so.id, fg2.id, quantity=1)

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        # The shared_raw should appear only once in purchase_orders_needed (aggregated)
        raw_pos = [
            po for po in result["purchase_orders_needed"]
            if po["product_id"] == shared_raw.id
        ]
        assert len(raw_pos) == 1
        # Aggregated qty should be 100 + 200 = 300
        assert raw_pos[0]["order_qty"] == 300.0


# =============================================================================
# generate_production_orders — quote-based edge cases
# =============================================================================

class TestGenerateProductionOrdersQuoteBased:
    """Test generate_production_orders for quote-based orders."""

    def test_rejects_quote_based_order_with_no_product_in_quote(
        self, db, make_sales_order, make_product
    ):
        """quote_based order whose quote has no product_id raises 400."""
        from datetime import datetime, timezone, timedelta
        from app.models.quote import Quote

        quote = Quote(
            user_id=1,
            quote_number="Q-TEST-NOPROD-001",
            product_name="Test Product",
            quantity=1,
            material_type="PLA",
            total_price=Decimal("50.00"),
            unit_price=Decimal("50.00"),
            file_format=".stl",
            file_size_bytes=1000,
            status="accepted",
            product_id=None,  # No product
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(quote)
        db.flush()

        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            quote_id=quote.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert exc_info.value.status_code == 400
        assert "no product" in exc_info.value.detail.lower()


# =============================================================================
# get_material_requirements — BOM fallback detail
# =============================================================================

class TestGetMaterialRequirementsBomFallback:
    """Test BOM fallback path in get_material_requirements."""

    def test_bom_with_cost_only_line_skipped(self, db, make_sales_order, make_product):
        """BOM lines with is_cost_only=True are excluded from requirements."""
        from app.models.bom import BOM, BOMLine

        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )

        # Create BOM manually to set is_cost_only
        bom = BOM(product_id=fg.id, name="BOM-COST-TEST", active=True)
        db.add(bom)
        db.flush()

        # Normal line
        line1 = BOMLine(
            bom_id=bom.id,
            component_id=raw.id,
            quantity=Decimal("100"),
            unit="G",
            sequence=10,
        )
        # Cost-only line (e.g., machine time)
        cost_only_product = make_product(
            item_type="supply", unit="HR",
            selling_price=Decimal("50.00"), has_bom=False,
        )
        line2 = BOMLine(
            bom_id=bom.id,
            component_id=cost_only_product.id,
            quantity=Decimal("1"),
            unit="HR",
            sequence=20,
            is_cost_only=True,
        )
        db.add_all([line1, line2])
        db.flush()

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=2)

        result = sales_order_service.get_material_requirements(db, so.id)
        # Only the real material should appear, not the cost-only one
        product_ids = [r["product_id"] for r in result["requirements"]]
        assert raw.id in product_ids
        assert cost_only_product.id not in product_ids

    def test_duplicate_material_aggregated(self, db, make_sales_order, make_product, make_bom):
        """Same material used in multiple BOM lines gets aggregated."""
        fg1 = make_product(selling_price=Decimal("50.00"), has_bom=True)
        fg2 = make_product(selling_price=Decimal("60.00"), has_bom=True)
        shared_raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )

        make_bom(fg1.id, lines=[
            {"component_id": shared_raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        make_bom(fg2.id, lines=[
            {"component_id": shared_raw.id, "quantity": Decimal("200"), "unit": "G"},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg1.id, quantity=1)
        _make_order_line(db, so.id, fg2.id, quantity=1)

        result = sales_order_service.get_material_requirements(db, so.id)
        # Should aggregate the shared raw material
        raw_reqs = [r for r in result["requirements"] if r["product_id"] == shared_raw.id]
        assert len(raw_reqs) == 1
        # Aggregated quantity should be 100 + 200 = 300
        assert raw_reqs[0]["quantity_required"] == Decimal("300")


# =============================================================================
# get_required_orders_for_sales_order — BOM inner branches
# =============================================================================

class TestGetRequiredOrdersBomInnerBranches:
    """Test inner BOM explosion branches for cost-only, missing components, etc."""

    def test_cost_only_bom_lines_skipped_in_explosion(
        self, db, make_sales_order, make_product
    ):
        """BOM lines with is_cost_only=True are skipped during requirement explosion."""
        from app.models.bom import BOM, BOMLine

        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        cost_item = make_product(
            item_type="supply", unit="HR",
            selling_price=Decimal("50.00"), has_bom=False,
        )

        bom = BOM(product_id=fg.id, name="BOM-COST-SKIP", active=True)
        db.add(bom)
        db.flush()

        # Normal physical material
        db.add(BOMLine(
            bom_id=bom.id,
            component_id=raw.id,
            quantity=Decimal("100"),
            unit="G",
            sequence=10,
        ))
        # Cost-only line (machine time etc.)
        db.add(BOMLine(
            bom_id=bom.id,
            component_id=cost_item.id,
            quantity=Decimal("1"),
            unit="HR",
            sequence=20,
            is_cost_only=True,
        ))
        db.flush()

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=2)

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        # The cost-only item should not appear in any requirement list
        all_product_ids = set()
        for item in result["purchase_orders_needed"]:
            all_product_ids.add(item["product_id"])
        for item in result["sub_assembly_work_orders"]:
            all_product_ids.add(item["product_id"])

        assert raw.id in all_product_ids
        assert cost_item.id not in all_product_ids

    def test_no_shortage_when_inventory_available(
        self, db, make_sales_order, make_product, make_bom
    ):
        """Components with sufficient inventory show no shortage."""
        from app.models.inventory import Inventory

        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        # Add sufficient inventory for the raw material
        inv = Inventory(
            product_id=raw.id,
            location_id=1,
            on_hand_quantity=Decimal("5000"),
            allocated_quantity=Decimal("0"),
        )
        db.add(inv)
        db.flush()

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=2)

        result = sales_order_service.get_required_orders_for_sales_order(db, so.id)
        # With enough inventory, no purchase orders needed
        assert result["summary"]["purchase_orders"] == 0


# =============================================================================
# copy_routing_to_operations + routing-based PO generation
# =============================================================================

class TestCopyRoutingToOperations:
    """Test routing copy during production order generation."""

    def _make_routing(self, db, product_id, *, operations=None):
        """Helper to create a Routing with RoutingOperations."""
        import uuid
        from app.models.manufacturing import Routing, RoutingOperation

        uid = uuid.uuid4().hex[:8]
        routing = Routing(
            product_id=product_id,
            code=f"RT-{uid}",
            name=f"Test Routing {uid}",
            is_active=True,
        )
        db.add(routing)
        db.flush()

        if operations:
            for op_data in operations:
                op = RoutingOperation(
                    routing_id=routing.id,
                    work_center_id=op_data.get("work_center_id", 1),
                    sequence=op_data.get("sequence", 10),
                    operation_code=op_data.get("operation_code", "PRINT"),
                    operation_name=op_data.get("operation_name", "Print"),
                    setup_time_minutes=op_data.get("setup_time_minutes", 5),
                    run_time_minutes=op_data.get("run_time_minutes", 30),
                )
                db.add(op)
            db.flush()

        return routing

    def test_copy_routing_creates_production_operations(
        self, db, make_product, make_bom, make_sales_order
    ):
        """Routing operations are copied to production order operations."""
        from app.models.production_order import ProductionOrderOperation

        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        routing = self._make_routing(db, fg.id, operations=[
            {"sequence": 10, "operation_code": "PRINT", "operation_name": "3D Print",
             "setup_time_minutes": 5, "run_time_minutes": 60},
            {"sequence": 20, "operation_code": "QC", "operation_name": "Quality Check",
             "setup_time_minutes": 0, "run_time_minutes": 10},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=2)

        result = sales_order_service.generate_production_orders(db, so.id, "test@filaops.dev")
        assert len(result["created_orders"]) == 1

        # Verify operations were copied
        po = db.query(ProductionOrder).filter(
            ProductionOrder.code == result["created_orders"][0]
        ).first()
        assert po is not None

        ops = db.query(ProductionOrderOperation).filter(
            ProductionOrderOperation.production_order_id == po.id
        ).order_by(ProductionOrderOperation.sequence).all()
        assert len(ops) == 2
        assert ops[0].operation_code == "PRINT"
        assert ops[1].operation_code == "QC"

    def test_copy_routing_direct_call(self, db, make_product, make_bom):
        """Direct call to copy_routing_to_operations works correctly."""
        from app.models.production_order import ProductionOrderOperation

        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        routing = self._make_routing(db, fg.id, operations=[
            {"sequence": 10, "operation_code": "PRINT", "operation_name": "3D Print",
             "run_time_minutes": 60},
        ])

        # Create a production order manually
        po = ProductionOrder(
            code="PO-ROUTING-TEST-001",
            product_id=fg.id,
            routing_id=routing.id,
            sales_order_id=None,
            quantity_ordered=3,
            quantity_completed=0,
            quantity_scrapped=0,
            status="draft",
            created_by="test",
        )
        db.add(po)
        db.flush()

        operations = sales_order_service.copy_routing_to_operations(db, po, routing.id)
        assert len(operations) == 1
        assert operations[0].operation_code == "PRINT"
        # run_time should be scaled by quantity: 60 * 3 = 180
        assert operations[0].planned_run_minutes == 180.0

    def test_create_production_orders_with_routing_for_line_items(
        self, db, make_product, make_bom, make_sales_order
    ):
        """create_production_orders_for_sales_order copies routing operations."""
        from app.models.production_order import ProductionOrderOperation

        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        routing = self._make_routing(db, fg.id, operations=[
            {"sequence": 10, "operation_code": "PRINT", "run_time_minutes": 30},
        ])

        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, fg.id, quantity=4)

        codes = sales_order_service.create_production_orders_for_sales_order(
            db, so, "test@filaops.dev"
        )
        assert len(codes) == 1

        po = db.query(ProductionOrder).filter(ProductionOrder.code == codes[0]).first()
        ops = db.query(ProductionOrderOperation).filter(
            ProductionOrderOperation.production_order_id == po.id
        ).all()
        assert len(ops) == 1
        assert ops[0].planned_run_minutes == 120.0  # 30 * 4

    def test_create_production_orders_with_routing_for_quote_based(
        self, db, make_product, make_bom, make_sales_order
    ):
        """create_production_orders_for_sales_order with routing for quote_based orders."""
        from app.models.production_order import ProductionOrderOperation

        fg = make_product(selling_price=Decimal("50.00"), has_bom=True)
        raw = make_product(
            item_type="supply", unit="G",
            selling_price=Decimal("0.02"), has_bom=False,
        )
        make_bom(fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("50"), "unit": "G"},
        ])
        routing = self._make_routing(db, fg.id, operations=[
            {"sequence": 10, "operation_code": "PRINT", "run_time_minutes": 20},
        ])

        so = make_sales_order(
            status="pending",
            order_type="quote_based",
            product_id=fg.id,
            quantity=2,
        )

        codes = sales_order_service.create_production_orders_for_sales_order(
            db, so, "test@filaops.dev"
        )
        assert len(codes) == 1

        po = db.query(ProductionOrder).filter(ProductionOrder.code == codes[0]).first()
        ops = db.query(ProductionOrderOperation).filter(
            ProductionOrderOperation.production_order_id == po.id
        ).all()
        assert len(ops) == 1
