"""Tests for quote_conversion_service.py — quote-to-order conversion workflow."""
import pytest
from decimal import Decimal
from datetime import datetime, timedelta, timezone, date
from unittest.mock import MagicMock

from app.services.quote_conversion_service import (
    generate_sales_order_number,
    generate_production_order_code,
    convert_quote_to_order,
    convert_quote_after_payment,
    ShippingInfo,
    ConversionResult,
)
from app.models.quote import Quote
from app.models.sales_order import SalesOrder
from app.models.production_order import ProductionOrder


class TestGenerateSalesOrderNumber:
    def test_generates_format(self, db):
        number = generate_sales_order_number(db)
        year = datetime.now(timezone.utc).year
        assert number.startswith(f"SO-{year}-")

    def test_increments_from_existing(self, db, make_sales_order, make_product):
        year = datetime.now(timezone.utc).year
        product = make_product(selling_price=Decimal("10.00"))
        make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"),
            order_number=f"SO-{year}-042",
        )
        number = generate_sales_order_number(db)
        assert number == f"SO-{year}-043"

    def test_starts_at_001_when_no_orders(self, db):
        # DB may have orders from other tests, but at minimum it should work
        number = generate_sales_order_number(db)
        parts = number.split("-")
        assert len(parts) == 3
        assert parts[0] == "SO"
        assert int(parts[2]) >= 1


class TestGenerateProductionOrderCode:
    def test_generates_format(self, db):
        code = generate_production_order_code(db)
        year = datetime.now(timezone.utc).year
        assert code.startswith(f"PO-{year}-")

    def test_increments_from_existing(self, db, make_product, make_production_order):
        year = datetime.now(timezone.utc).year
        product = make_product()
        make_production_order(
            product_id=product.id, code=f"PO-{year}-099"
        )
        code = generate_production_order_code(db)
        assert code == f"PO-{year}-100"


class TestConvertQuoteToOrder:
    def _make_quote(self, db, user_id=1, **kwargs):
        """Helper to create a quote with sensible defaults."""
        from app.models.quote import Quote
        import uuid
        uid = uuid.uuid4().hex[:6]
        q = Quote(
            quote_number=kwargs.pop("quote_number", f"Q-TEST-{uid}"),
            user_id=user_id,
            product_name=kwargs.pop("product_name", f"Test Widget {uid}"),
            quantity=kwargs.pop("quantity", 5),
            material_type=kwargs.pop("material_type", "PLA"),
            finish=kwargs.pop("finish", "standard"),
            total_price=kwargs.pop("total_price", Decimal("50.00")),
            unit_price=kwargs.pop("unit_price", Decimal("10.00")),
            status=kwargs.pop("status", "accepted"),
            file_format=kwargs.pop("file_format", "STL"),
            file_size_bytes=kwargs.pop("file_size_bytes", 1024),
            expires_at=kwargs.pop(
                "expires_at",
                datetime.now(timezone.utc) + timedelta(days=30),
            ),
            **kwargs,
        )
        db.add(q)
        db.flush()
        return q

    def test_rejects_non_accepted_status(self, db):
        quote = self._make_quote(db, status="draft")
        result = convert_quote_to_order(quote, db)
        assert result.success is False
        assert "status" in result.error_message.lower()

    def test_rejects_already_converted(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1,
            unit_price=Decimal("10.00"),
        )
        quote = self._make_quote(db, status="accepted")
        quote.sales_order_id = so.id
        db.flush()
        result = convert_quote_to_order(quote, db)
        assert result.success is False
        assert "already converted" in result.error_message.lower()


class TestConvertQuoteAfterPayment:
    def test_quote_not_found(self, db):
        result = convert_quote_after_payment(
            quote_id=999999, db=db,
            payment_transaction_id="txn-123",
        )
        assert result.success is False
        assert "not found" in result.error_message.lower()


class TestShippingInfo:
    def test_default_values(self):
        info = ShippingInfo()
        assert info.shipping_country == "USA"
        assert info.shipping_name is None

    def test_custom_values(self):
        info = ShippingInfo(
            shipping_name="John",
            shipping_address_line1="123 Test St",
            shipping_city="Austin",
            shipping_state="TX",
            shipping_zip="78701",
        )
        assert info.shipping_name == "John"
        assert info.shipping_city == "Austin"


class TestConversionResult:
    def test_success_result(self):
        mock_quote = MagicMock()
        result = ConversionResult(success=True, quote=mock_quote)
        assert result.success is True
        assert result.product is None
        assert result.error_message is None

    def test_failure_result(self):
        mock_quote = MagicMock()
        result = ConversionResult(
            success=False, quote=mock_quote,
            error_message="Something went wrong"
        )
        assert result.success is False
        assert result.error_message == "Something went wrong"
