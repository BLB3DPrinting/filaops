"""
Unit tests for Quote Conversion Service

Tests verify:
1. Quote status validation
2. Quote expiration handling
3. Sales order number generation
4. Production order code generation
5. Complete quote-to-order conversion
6. Error handling

Run with:
    cd C:\repos\filaops-v3-clean\backend
    pytest tests/unit/test_quote_service.py -v
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch

from app.services.quote_conversion_service import (
    generate_sales_order_number,
    generate_production_order_code,
    convert_portal_quote_to_order,
    ConversionResult,
    ShippingInfo,
)


# ============================================================================
# Sales Order Number Generation Tests
# ============================================================================

class TestGenerateSalesOrderNumber:
    """Test sales order number generation"""

    def test_first_order_of_year(self):
        """Should generate SO-YYYY-001 for first order"""
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        result = generate_sales_order_number(db)

        year = datetime.now(timezone.utc).year
        assert result == f"SO-{year}-001"

    def test_increments_existing_orders(self):
        """Should increment from last order"""
        db = MagicMock()

        last_order = Mock()
        year = datetime.now(timezone.utc).year
        last_order.order_number = f"SO-{year}-042"

        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = last_order

        result = generate_sales_order_number(db)

        assert result == f"SO-{year}-043"


# ============================================================================
# Production Order Code Generation Tests
# ============================================================================

class TestGenerateProductionOrderCode:
    """Test production order code generation"""

    def test_first_po_of_year(self):
        """Should generate PO-YYYY-001 for first PO"""
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        result = generate_production_order_code(db)

        year = datetime.now(timezone.utc).year
        assert result == f"PO-{year}-001"

    def test_increments_existing_pos(self):
        """Should increment from last PO"""
        db = MagicMock()

        last_po = Mock()
        year = datetime.now(timezone.utc).year
        last_po.code = f"PO-{year}-099"

        db.query.return_value.filter.return_value.order_by.return_value.first.return_value = last_po

        result = generate_production_order_code(db)

        assert result == f"PO-{year}-100"


# ============================================================================
# Quote Conversion Tests
# ============================================================================

class TestConvertQuoteToOrder:
    """Test quote-to-order conversion"""

    def test_rejects_non_accepted_quote(self):
        """Should reject quotes not in accepted/approved status"""
        db = MagicMock()

        quote = Mock()
        quote.status = "draft"

        result = convert_portal_quote_to_order(quote, db)

        assert result.success is False
        assert "status must be 'accepted' or 'approved'" in result.error_message

    def test_rejects_expired_quote(self):
        """Should reject expired quotes"""
        db = MagicMock()

        quote = Mock()
        quote.status = "accepted"
        quote.is_expired = True

        result = convert_portal_quote_to_order(quote, db)

        assert result.success is False
        assert "expired" in result.error_message

    def test_rejects_already_converted_quote(self):
        """Should reject quotes already converted to SO"""
        db = MagicMock()

        quote = Mock()
        quote.status = "accepted"
        quote.is_expired = False
        quote.sales_order_id = 123

        result = convert_portal_quote_to_order(quote, db)

        assert result.success is False
        assert "already converted" in result.error_message


# ============================================================================
# Shipping Info Tests
# ============================================================================

class TestShippingInfo:
    """Test ShippingInfo dataclass"""

    def test_default_country(self):
        """Should default to USA for country"""
        info = ShippingInfo()
        assert info.shipping_country == "USA"

    def test_full_shipping_info(self):
        """Should store all shipping fields"""
        info = ShippingInfo(
            shipping_name="Test Customer",
            shipping_address_line1="123 Main St",
            shipping_city="Anytown",
            shipping_state="CA",
            shipping_zip="12345",
            shipping_carrier="USPS",
            shipping_service="Priority",
            shipping_cost=Decimal("9.99"),
        )

        assert info.shipping_name == "Test Customer"
        assert info.shipping_city == "Anytown"
        assert info.shipping_cost == Decimal("9.99")


# ============================================================================
# Conversion Result Tests
# ============================================================================

class TestConversionResult:
    """Test ConversionResult dataclass"""

    def test_success_result(self):
        """Should store success result with all objects"""
        quote = Mock()
        product = Mock()
        bom = Mock()
        sales_order = Mock()
        production_order = Mock()

        result = ConversionResult(
            success=True,
            quote=quote,
            product=product,
            bom=bom,
            sales_order=sales_order,
            production_order=production_order,
        )

        assert result.success is True
        assert result.error_message is None

    def test_failure_result(self):
        """Should store failure result with error message"""
        quote = Mock()

        result = ConversionResult(
            success=False,
            quote=quote,
            error_message="Something went wrong",
        )

        assert result.success is False
        assert result.error_message == "Something went wrong"
        assert result.product is None


# ============================================================================
# Smoke Test
# ============================================================================

def test_quote_service_smoke():
    """Quick smoke test for quote service"""
    # Test ShippingInfo creation
    info = ShippingInfo()
    assert info.shipping_country == "USA"

    # Test ConversionResult creation
    result = ConversionResult(success=False, quote=None, error_message="test")
    assert result.success is False

    print("\n  Quote service smoke test passed!")


if __name__ == "__main__":
    test_quote_service_smoke()
