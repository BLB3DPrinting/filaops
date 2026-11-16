"""Unit tests for quote discount-line rules (no database needed)."""
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.endpoints.quotes import QuoteLineCreate
from app.services.quote_line_rules import (
    check_line_price,
    line_discount_percent,
    lines_subtotal,
    validate_quote_lines,
)


def _line(unit_price, quantity=1, product_id=None):
    return SimpleNamespace(
        unit_price=Decimal(str(unit_price)),
        quantity=quantity,
        product_id=product_id,
    )


class TestCheckLinePrice:
    def test_negative_price_allowed_without_product(self):
        check_line_price(None, Decimal("-5.00"))

    def test_negative_price_rejected_with_product(self):
        with pytest.raises(ValueError):
            check_line_price(12, Decimal("-0.01"))

    def test_zero_and_positive_prices_allowed_with_product(self):
        check_line_price(12, Decimal("0"))
        check_line_price(12, Decimal("19.99"))


class TestLineDiscountPercent:
    def test_quote_discount_applies_to_product_lines(self):
        line = SimpleNamespace(product_id=3, discount_percent=None)
        assert line_discount_percent(line, Decimal("10")) == 10.0

    def test_quote_discount_never_applies_to_product_less_lines(self):
        discount_line = SimpleNamespace(product_id=None, discount_percent=None)
        assert line_discount_percent(discount_line, Decimal("10")) == 0.0

    def test_line_own_discount_wins(self):
        line = SimpleNamespace(product_id=3, discount_percent=Decimal("25"))
        assert line_discount_percent(line, Decimal("10")) == 25.0

    def test_no_discounts_gives_zero(self):
        line = SimpleNamespace(product_id=3, discount_percent=None)
        assert line_discount_percent(line, None) == 0.0


class TestLinesSubtotal:
    def test_discount_line_reduces_subtotal(self):
        lines = [_line("20.00", quantity=2, product_id=1), _line("-5.00")]
        assert lines_subtotal(lines) == Decimal("35.00")

    def test_accepts_dict_lines(self):
        lines = [
            {"unit_price": "10.00", "quantity": 3, "product_id": 1},
            {"unit_price": "-4.00", "quantity": 1, "product_id": None},
        ]
        assert lines_subtotal(lines) == Decimal("26.00")

    def test_customer_discount_applies_to_product_lines_only(self):
        lines = [_line("100.00", product_id=1), _line("-10.00")]
        # 100.00 less 10% = 90.00; the -10.00 discount line is not reduced.
        assert lines_subtotal(lines, Decimal("10")) == Decimal("80.00")


class TestValidateQuoteLines:
    def test_valid_discount_passes(self):
        validate_quote_lines([_line("50.00", product_id=1), _line("-20.00")])

    def test_discount_equal_to_subtotal_passes(self):
        validate_quote_lines([_line("20.00", product_id=1), _line("-20.00")])

    def test_discount_larger_than_subtotal_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_quote_lines([_line("20.00", product_id=1), _line("-25.00")])
        assert exc_info.value.status_code == 400
        assert "cannot exceed" in exc_info.value.detail

    def test_negative_product_line_rejected(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_quote_lines([_line("-5.00", product_id=1)])
        assert exc_info.value.status_code == 400


class TestQuoteLineCreateSchema:
    def test_negative_fee_line_accepted(self):
        line = QuoteLineCreate(product_name="Multi-buy discount", unit_price=Decimal("-5.00"))
        assert line.unit_price == Decimal("-5.00")
        assert line.product_id is None

    def test_negative_product_line_rejected(self):
        with pytest.raises(ValidationError):
            QuoteLineCreate(product_id=7, product_name="Widget", unit_price=Decimal("-1.00"))

    def test_positive_product_line_accepted(self):
        line = QuoteLineCreate(product_id=7, product_name="Widget", unit_price=Decimal("1.00"))
        assert line.unit_price == Decimal("1.00")
