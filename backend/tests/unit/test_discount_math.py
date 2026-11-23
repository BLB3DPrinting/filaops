"""Shared discount math (app/services/discount_math.py)."""
from decimal import Decimal

import pytest

from app.services import discount_math as dm
from app.services.discount_math import LineInput
from app.services.tax_calculation_service import calculate_sales_tax


def D(value):
    return Decimal(value)


class TestGoldenQuote:
    """Real quote: 2 x $42.56, 10% quote discount, 7% tax."""

    def test_golden_numbers(self):
        doc = dm.compute_document(
            [LineInput(quantity=D("2"), unit_price=D("42.56"))],
            discount_type="percent",
            discount_value=D("10"),
        )
        assert doc.items_gross == D("85.12")
        assert doc.discount == D("8.51")
        assert doc.subtotal == D("76.61")

        tax = calculate_sales_tax(subtotal=doc.subtotal, tax_rate=D("0.07")).tax_amount
        assert tax == D("5.36")
        assert doc.subtotal + tax == D("81.97")


class TestDiscountAmount:
    def test_no_discount_is_zero(self):
        assert dm.discount_amount(D("50.00"), None, None) == D("0.00")
        assert dm.discount_amount(D("50.00"), "percent", None) == D("0.00")
        assert dm.discount_amount(D("50.00"), None, D("5")) == D("0.00")

    def test_percent_rounds_half_up_to_cents(self):
        # 10% of 0.25 = 0.025 -> 0.03 (half up), not 0.02 (half even)
        assert dm.discount_amount(D("0.25"), "percent", D("10")) == D("0.03")

    def test_fixed_amount(self):
        assert dm.discount_amount(D("50.00"), "amount", D("7.50")) == D("7.50")

    def test_fixed_amount_capped_at_base(self):
        assert dm.discount_amount(D("5.00"), "amount", D("7.50")) == D("5.00")

    def test_hundred_percent(self):
        assert dm.discount_amount(D("12.34"), "percent", D("100")) == D("12.34")

    def test_zero_base(self):
        assert dm.discount_amount(D("0"), "percent", D("10")) == D("0.00")


class TestComputeDocument:
    def test_order_of_operations(self):
        doc = dm.compute_document(
            [
                LineInput(D("2"), D("10.00"), "percent", D("10")),  # 20.00 - 2.00
                LineInput(D("1"), D("30.00"), "amount", D("5")),    # 30.00 - 5.00
                LineInput(D("3"), D("1.00")),                        # 3.00
            ],
            discount_type="amount",
            discount_value=D("4.00"),
        )
        assert [r.net for r in doc.lines] == [D("18.00"), D("25.00"), D("3.00")]
        assert doc.items_gross == D("53.00")
        assert doc.line_discounts == D("7.00")
        assert doc.items_total == D("46.00")
        assert doc.discount == D("4.00")
        assert doc.subtotal == D("42.00")

    def test_quote_percent_applies_after_line_discounts(self):
        doc = dm.compute_document(
            [LineInput(D("1"), D("100.00"), "amount", D("20"))],
            discount_type="percent",
            discount_value=D("10"),
        )
        # 10% of 80.00, not of 100.00
        assert doc.discount == D("8.00")
        assert doc.subtotal == D("72.00")

    def test_no_discounts_matches_plain_sum(self):
        doc = dm.compute_document([LineInput(D("3"), D("19.99")), LineInput(D("1"), D("0.01"))])
        assert doc.subtotal == D("59.98")
        assert doc.discount == D("0.00")


class TestValidate:
    @pytest.mark.parametrize("dtype,value", [(None, None), ("percent", D("10")), ("amount", D("0")), ("percent", D("100"))])
    def test_valid(self, dtype, value):
        dm.validate_discount(dtype, value)

    @pytest.mark.parametrize(
        "dtype,value",
        [("bogus", D("1")), ("percent", None), (None, D("5")), ("amount", D("-1")), ("percent", D("100.01"))],
    )
    def test_invalid(self, dtype, value):
        with pytest.raises(ValueError):
            dm.validate_discount(dtype, value)


def test_default_labels():
    assert dm.default_discount_label("percent", D("10.00")) == "10% discount"
    assert dm.default_discount_label("percent", D("12.5")) == "12.5% discount"
    assert dm.default_discount_label("amount", D("5")) == "Discount"
    assert dm.default_discount_label(None, None) is None
