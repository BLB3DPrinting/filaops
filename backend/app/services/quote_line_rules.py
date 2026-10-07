"""
Validation rules for manual quote line items.

Quote lines normally carry a non-negative unit price. The one exception is a
*discount line*: a product-less (fee/service) line with a negative unit price,
for example "Multi-buy discount" at -5.00. Discount lines flow through to the
sales order and invoice like any other fee line.

Rules enforced here:
- A negative unit price is only allowed on lines without a product.
- The quote subtotal can never be negative (a discount can't exceed what it
  is discounting).

Kept in its own module so quote_service.py and the quotes endpoint can share
the rules without growing further.
"""
from decimal import Decimal
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status

_CENT = Decimal("0.01")

NEGATIVE_PRICE_PRODUCT_LINE_MESSAGE = (
    "Negative unit_price is only allowed on lines without a product "
    "(fee/discount lines)"
)


def _get(line: Any, key: str) -> Any:
    """Read a field from a line given as a dict or an attribute-style object."""
    if isinstance(line, dict):
        return line.get(key)
    return getattr(line, key, None)


def check_line_price(product_id: Optional[int], unit_price: Decimal) -> None:
    """Raise ValueError if a product line has a negative unit price.

    ValueError (not HTTPException) so it can be used inside Pydantic
    validators, where it surfaces as a 422.
    """
    if product_id is not None and Decimal(str(unit_price)) < 0:
        raise ValueError(NEGATIVE_PRICE_PRODUCT_LINE_MESSAGE)


def lines_subtotal(
    lines: Iterable[Any], discount_percent: Optional[Decimal] = None
) -> Decimal:
    """Net subtotal of quote lines, mirroring how quote totals are computed.

    The customer price-level discount applies to product lines only, so
    fee and discount lines are never reduced further.
    """
    subtotal = Decimal("0")
    for line in lines:
        price = Decimal(str(_get(line, "unit_price"))).quantize(_CENT)
        if _get(line, "product_id") and discount_percent and discount_percent > 0:
            price = (
                price * (Decimal("1") - discount_percent / Decimal("100"))
            ).quantize(_CENT)
        subtotal += (price * _get(line, "quantity")).quantize(_CENT)
    return subtotal


def validate_quote_lines(
    lines: Iterable[Any], discount_percent: Optional[Decimal] = None
) -> None:
    """Reject invalid discount usage. Call before changing any quote data."""
    lines = list(lines)
    for line in lines:
        try:
            check_line_price(_get(line, "product_id"), _get(line, "unit_price"))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    subtotal = lines_subtotal(lines, discount_percent)
    if subtotal < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Discounts cannot exceed the quote subtotal "
                f"(subtotal would be {subtotal})"
            ),
        )
