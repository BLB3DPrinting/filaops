"""Portal/payment quote-to-order conversion keeps the quote's money.

Before the fix, ``convert_portal_quote_to_order`` put the quote total (tax and
shipping included) into the order subtotal, stored zero tax and added
shipping a second time, so the order and its invoice charged more than the
customer accepted.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest

from app.services import quote_conversion_service
from app.services.invoice_service import create_invoice
from app.services.quote_conversion_service import (
    ShippingInfo,
    convert_portal_quote_to_order,
    convert_quote_after_payment,
)
from app.services.quote_order_money import order_money_from_quote


def _quote_ns(**kwargs):
    values = dict(
        quantity=5,
        unit_price=Decimal("20.00"),
        subtotal=Decimal("90.00"),
        discount_amount=Decimal("10.00"),
        tax_rate=None,
        tax_name=None,
        tax_amount=None,
        shipping_cost=Decimal("8.50"),
        shipping_state="TX",
        total_price=Decimal("98.50"),
    )
    values.update(kwargs)
    return SimpleNamespace(**values)


class TestOrderMoneyFromQuote:
    def test_uses_stored_subtotal_tax_and_shipping(self):
        quote = _quote_ns(
            tax_rate=Decimal("0.0825"),
            tax_amount=Decimal("7.43"),
            total_price=Decimal("105.93"),
        )
        money = order_money_from_quote(None, quote)
        assert money.subtotal == Decimal("90.00")
        assert money.tax_amount == Decimal("7.43")
        assert money.shipping_cost == Decimal("8.50")
        assert money.grand_total == quote.total_price
        assert money.unit_price == Decimal("20.00")

    def test_order_columns_map_subtotal_to_total_price(self):
        money = order_money_from_quote(None, _quote_ns())
        cols = money.order_columns()
        assert cols["total_price"] == Decimal("90.00")
        assert cols["grand_total"] == Decimal("98.50")
        assert cols["is_taxable"] is False

    def test_legacy_quote_without_subtotal_is_inferred(self):
        quote = _quote_ns(
            subtotal=None,
            discount_amount=None,
            tax_amount=Decimal("4.00"),
            total_price=Decimal("112.50"),
        )
        money = order_money_from_quote(None, quote)
        assert money.subtotal == Decimal("100.00")
        assert money.grand_total == Decimal("112.50")

    def test_legacy_quote_with_inconsistent_parts_uses_total_as_subtotal(self):
        quote = _quote_ns(
            subtotal=None,
            tax_amount=Decimal("50.00"),
            total_price=Decimal("20.00"),
        )
        money = order_money_from_quote(None, quote)
        assert money.subtotal == Decimal("20.00")
        assert money.tax_amount == Decimal("0.00")
        assert money.shipping_cost == Decimal("0.00")
        assert money.grand_total == Decimal("20.00")

    def test_unit_price_fallback_is_pre_discount(self):
        money = order_money_from_quote(None, _quote_ns(unit_price=None))
        # (90 subtotal + 10 discount) / 5
        assert money.unit_price == Decimal("20.00")

    def test_shipping_override_without_tax_rate_keeps_stored_tax(self):
        quote = _quote_ns(tax_amount=Decimal("3.00"))
        money = order_money_from_quote(None, quote, shipping_cost=Decimal("12.00"))
        assert money.shipping_cost == Decimal("12.00")
        assert money.tax_amount == Decimal("3.00")
        assert money.grand_total == Decimal("105.00")

    def test_zero_shipping_override_is_honoured(self):
        money = order_money_from_quote(None, _quote_ns(), shipping_cost=Decimal("0"))
        assert money.shipping_cost == Decimal("0.00")
        assert money.grand_total == Decimal("90.00")

    def test_new_destination_recomputes_tax_on_the_subtotal(self, db):
        quote = _quote_ns(
            tax_rate=Decimal("0.10"),
            tax_amount=Decimal("9.00"),
            total_price=Decimal("107.50"),
        )
        money = order_money_from_quote(db, quote, shipping_cost=Decimal("15.00"))
        assert money.shipping_cost == Decimal("15.00")
        # Tax is never charged on more than subtotal + shipping, and the
        # subtotal is never replaced by the quote total.
        assert Decimal("9.00") <= money.tax_amount <= Decimal("10.50")
        assert money.grand_total == Decimal("90.00") + money.tax_amount + Decimal("15.00")


class TestPortalConversionTotals:
    def _make_quote(self, db, make_product, make_bom, **kwargs):
        from app.models.quote import Quote

        product = make_product(
            item_type="finished_good",
            procurement_type="make",
            selling_price=Decimal("20.00"),
        )
        make_bom(product_id=product.id)
        uid = uuid.uuid4().hex[:6]
        values = dict(
            quote_number=f"Q-MONEY-{uid}",
            user_id=1,
            product_id=product.id,
            product_name=f"Money Widget {uid}",
            quantity=5,
            material_type="PLA",
            finish="standard",
            unit_price=Decimal("20.00"),
            discount_type="percent",
            discount_value=Decimal("10"),
            discount_label="Repeat customer",
            discount_amount=Decimal("10.00"),
            subtotal=Decimal("90.00"),
            tax_rate=Decimal("0.0825"),
            tax_name="TX 8.25%",
            tax_amount=Decimal("7.43"),
            shipping_cost=Decimal("8.50"),
            shipping_state="TX",
            total_price=Decimal("105.93"),
            status="accepted",
            file_format="STL",
            file_size_bytes=1024,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        values.update(kwargs)
        quote = Quote(**values)
        db.add(quote)
        db.flush()
        return quote

    @pytest.fixture(autouse=True)
    def _valid_bom(self, monkeypatch):
        monkeypatch.setattr(
            quote_conversion_service,
            "validate_quote_for_bom",
            lambda _quote, _db: (True, "Valid"),
        )

    def test_order_matches_quote(self, db, make_product, make_bom):
        quote = self._make_quote(db, make_product, make_bom)
        result = convert_portal_quote_to_order(quote, db)

        assert result.success is True, result.error_message
        order = result.sales_order
        assert order.total_price == Decimal("90.00")
        assert order.tax_amount == Decimal("7.43")
        assert order.tax_rate == Decimal("0.0825")
        assert order.tax_name == "TX 8.25%"
        assert order.shipping_cost == Decimal("8.50")
        assert order.grand_total == Decimal("105.93")
        assert order.grand_total == quote.total_price
        assert order.discount_type == "percent"
        assert order.discount_value == Decimal("10")
        assert order.discount_label == "Repeat customer"
        assert order.discount_amount == Decimal("10.00")
        assert order.unit_price == Decimal("20.00")

    def test_untaxed_quote_does_not_add_shipping_twice(self, db, make_product, make_bom):
        quote = self._make_quote(
            db, make_product, make_bom,
            tax_rate=None, tax_name=None, tax_amount=None,
            total_price=Decimal("98.50"),
        )
        result = convert_portal_quote_to_order(quote, db)

        assert result.success is True, result.error_message
        order = result.sales_order
        assert order.total_price == Decimal("90.00")
        assert order.tax_amount == Decimal("0.00")
        assert order.shipping_cost == Decimal("8.50")
        assert order.grand_total == Decimal("98.50")

    def test_shipping_override_changes_shipping_only(self, db, make_product, make_bom):
        quote = self._make_quote(
            db, make_product, make_bom,
            tax_rate=None, tax_name=None, tax_amount=None,
            total_price=Decimal("98.50"),
        )
        result = convert_portal_quote_to_order(
            quote, db, shipping=ShippingInfo(shipping_cost=Decimal("12.00"))
        )

        assert result.success is True, result.error_message
        order = result.sales_order
        assert order.total_price == Decimal("90.00")
        assert order.shipping_cost == Decimal("12.00")
        assert order.grand_total == Decimal("102.00")

    def test_after_payment_invoice_matches_quote(self, db, make_product, make_bom):
        quote = self._make_quote(db, make_product, make_bom)
        result = convert_quote_after_payment(
            quote_id=quote.id, db=db, payment_transaction_id="txn-money-1",
        )

        assert result.success is True, result.error_message
        order = result.sales_order
        assert order.status == "confirmed"
        assert order.grand_total == Decimal("105.93")

        invoice = create_invoice(db, order.id)
        assert invoice.subtotal == Decimal("100.00")
        assert invoice.discount_amount == Decimal("10.00")
        assert invoice.tax_amount == Decimal("7.43")
        assert invoice.shipping_amount == Decimal("8.50")
        assert invoice.total == Decimal("105.93")
