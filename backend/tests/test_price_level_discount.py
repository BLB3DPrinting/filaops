"""Tests for sales order price level auto-apply (PRO graceful degradation)."""
from decimal import Decimal

from app.services.customer_service import get_customer_discount_percent as _get_customer_discount_percent


class TestPriceLevelLookup:
    """Test _get_customer_discount_percent with graceful degradation."""

    def test_returns_none_when_pro_tables_missing(self, db):
        """When PRO is not installed, lookup returns None (tables don't exist)."""
        result = _get_customer_discount_percent(db, customer_id=999)
        assert result is None

    def test_returns_none_for_nonexistent_customer(self, db):
        """Customer without price level returns None."""
        result = _get_customer_discount_percent(db, customer_id=0)
        assert result is None

    def test_return_type_is_decimal_or_none(self, db):
        """Return type should be Decimal or None, never raise."""
        result = _get_customer_discount_percent(db, customer_id=1)
        assert result is None or isinstance(result, Decimal)
