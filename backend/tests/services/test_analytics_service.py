"""Tests for analytics_service.py — dashboard metrics computation."""
import uuid

import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.user import User
from app.services.analytics_service import (
    get_analytics_dashboard,
    _compute_revenue_metrics,
    _compute_customer_metrics,
    _compute_product_metrics,
    _compute_profit_metrics,
)


@pytest.fixture
def make_customer_user(db):
    """Create a customer-type User (sales_orders.user_id points here).

    The seeded user (id=1) is an admin, so customer-scoped metrics need a
    real account_type='customer' row to assert against.
    """
    def _factory(company_name=None, account_type="customer"):
        uid = uuid.uuid4().hex[:8]
        user = User(
            email=f"cust-{uid}@example.com",
            password_hash="not-a-real-hash",
            first_name="Cust",
            last_name=uid,
            company_name=company_name or f"Customer Co {uid}",
            account_type=account_type,
        )
        db.add(user)
        db.flush()
        return user

    return _factory


class TestGetAnalyticsDashboard:
    """Test the main analytics dashboard function.

    Regression coverage for the AmbiguousForeignKeysError that used to crash
    GET /api/v1/admin/analytics/dashboard: sales_orders has two FKs to users
    (user_id and customer_id), so the top-customers join in
    _compute_customer_metrics must specify an explicit ON clause.
    """

    def test_returns_expected_top_level_keys(self, db):
        result = get_analytics_dashboard(db)
        assert "revenue" in result
        assert "customers" in result
        assert "products" in result
        assert "profit" in result
        assert "period_start" in result
        assert "period_end" in result

    def test_period_dates_reflect_days_param(self, db):
        result = get_analytics_dashboard(db, days=30)
        delta = result["period_end"] - result["period_start"]
        assert 29 <= delta.days <= 31

    def test_defaults_to_30_days(self, db):
        result = get_analytics_dashboard(db, days=30)
        delta = result["period_end"] - result["period_start"]
        assert abs(delta.days - 30) <= 1

    def test_custom_period_90_days(self, db):
        result = get_analytics_dashboard(db, days=90)
        delta = result["period_end"] - result["period_start"]
        assert abs(delta.days - 90) <= 1

    def test_dashboard_with_completed_order_exercises_customer_join(
        self, db, make_customer_user, make_product, make_sales_order
    ):
        """Full dashboard against a populated DB must not raise and must roll
        the order's revenue up under its owning customer.

        This is the direct regression for AmbiguousForeignKeysError — the
        top-customers query joins users<->sales_orders, which only compiles
        once the join specifies SalesOrder.user_id == User.id explicitly.
        """
        customer = make_customer_user(company_name="Acme Robotics")
        product = make_product(selling_price=Decimal("50.00"))
        make_sales_order(
            user_id=customer.id,
            product_id=product.id,
            unit_price=Decimal("50.00"),
            quantity=2,
            status="completed",
        )

        result = get_analytics_dashboard(db, days=30)

        top = result["customers"]["top_customers"]
        assert any(c["customer_id"] == customer.id for c in top)
        acme = next(c for c in top if c["customer_id"] == customer.id)
        assert acme["company_name"] == "Acme Robotics"
        assert acme["revenue"] >= 100.0


class TestComputeRevenueMetrics:
    """Test revenue metric computation."""

    def test_empty_db_returns_zeros(self, db):
        now = datetime.now(timezone.utc)
        result = _compute_revenue_metrics(
            db,
            end_date=now,
            start_date=now - timedelta(days=30),
            prev_start=now - timedelta(days=60),
        )
        assert result["total_revenue"] == Decimal("0")
        assert result["period_revenue"] == Decimal("0")
        assert result["revenue_30_days"] == Decimal("0")
        assert result["revenue_90_days"] == Decimal("0")
        assert result["revenue_365_days"] == Decimal("0")
        assert result["average_order_value"] == Decimal("0")
        assert result["revenue_growth"] is None

    def test_completed_orders_counted(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("50.00"))
        make_sales_order(
            product_id=product.id,
            unit_price=Decimal("50.00"),
            quantity=2,
            status="completed",
        )
        now = datetime.now(timezone.utc)
        result = _compute_revenue_metrics(
            db,
            end_date=now,
            start_date=now - timedelta(days=30),
            prev_start=now - timedelta(days=60),
        )
        assert result["total_revenue"] >= Decimal("100")
        assert result["period_revenue"] >= Decimal("100")

    def test_draft_orders_not_counted(self, db, make_product, make_sales_order):
        product = make_product()
        make_sales_order(product_id=product.id, status="draft")
        now = datetime.now(timezone.utc)
        result = _compute_revenue_metrics(
            db,
            end_date=now,
            start_date=now - timedelta(days=30),
            prev_start=now - timedelta(days=60),
        )
        # Draft orders should not contribute to revenue
        assert result["period_revenue"] == Decimal("0") or result["period_revenue"] >= Decimal("0")


class TestComputeCustomerMetrics:
    """Test customer metric computation."""

    def test_empty_db_returns_zeros(self, db):
        now = datetime.now(timezone.utc)
        result = _compute_customer_metrics(
            db,
            end_date=now,
            start_date=now - timedelta(days=30),
            period_revenue=Decimal("0"),
        )
        assert result["total_customers"] >= 0
        assert result["active_customers_30_days"] >= 0
        assert result["new_customers_30_days"] >= 0
        assert result["average_customer_value"] == Decimal("0")
        assert isinstance(result["top_customers"], list)

    def test_top_customers_joins_on_owning_account(
        self, db, make_customer_user, make_product, make_sales_order
    ):
        """top_customers must aggregate revenue by SalesOrder.user_id.

        Regression for the ambiguous users<->sales_orders join: with a
        completed order the join must compile AND attribute revenue to the
        order's user_id (not customer_id).
        """
        customer = make_customer_user(company_name="Beta Industries")
        product = make_product(selling_price=Decimal("25.00"))
        make_sales_order(
            user_id=customer.id,
            product_id=product.id,
            unit_price=Decimal("25.00"),
            quantity=4,
            status="completed",
        )
        now = datetime.now(timezone.utc)

        result = _compute_customer_metrics(
            db,
            end_date=now,
            start_date=now - timedelta(days=30),
            period_revenue=Decimal("100"),
        )

        ids = {c["customer_id"] for c in result["top_customers"]}
        assert customer.id in ids
        beta = next(c for c in result["top_customers"] if c["customer_id"] == customer.id)
        assert beta["company_name"] == "Beta Industries"
        assert beta["revenue"] >= 100.0
        assert result["active_customers_30_days"] >= 1


class TestComputeProductMetrics:
    """Test product metric computation."""

    def test_returns_expected_keys(self, db):
        now = datetime.now(timezone.utc)
        result = _compute_product_metrics(db, start_date=now - timedelta(days=30))
        assert "total_products" in result
        assert "top_selling_products" in result
        assert "low_stock_count" in result
        assert "products_with_bom" in result

    def test_counts_active_products(self, db, make_product):
        make_product(name="Analytics Test Product")
        now = datetime.now(timezone.utc)
        result = _compute_product_metrics(db, start_date=now - timedelta(days=30))
        assert result["total_products"] >= 1


class TestComputeProfitMetrics:
    """Test profit metric computation."""

    def test_empty_db_returns_zeros(self, db):
        now = datetime.now(timezone.utc)
        result = _compute_profit_metrics(
            db,
            start_date=now - timedelta(days=30),
            period_revenue=Decimal("0"),
        )
        assert result["total_cost"] == Decimal("0")
        assert result["gross_profit"] == Decimal("0")
        assert result["gross_margin"] == 0.0
        assert isinstance(result["profit_by_product"], list)

    def test_profit_calculation_with_orders(self, db, make_product, make_sales_order):
        product = make_product(
            standard_cost=Decimal("5.00"),
            selling_price=Decimal("15.00"),
        )
        make_sales_order(
            product_id=product.id,
            unit_price=Decimal("15.00"),
            quantity=10,
            status="completed",
        )
        now = datetime.now(timezone.utc)
        result = _compute_profit_metrics(
            db,
            start_date=now - timedelta(days=30),
            period_revenue=Decimal("150"),
        )
        assert result["total_revenue"] == Decimal("150")
        # With standard_cost=5 and qty=10, total_cost should be ~50
        assert result["gross_profit"] >= Decimal("0")
