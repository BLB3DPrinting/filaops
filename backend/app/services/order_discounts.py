"""Keep sales-order line and order discounts applied when an order is repriced.

Line edits, removals and close-short rebuild totals from the lines. Without
these helpers a discount carried from the quote would silently fall off the
order (and so off the invoice) at the first edit. Percent discounts are
recomputed on the new amounts; fixed amounts are kept but capped.
"""
from __future__ import annotations

from decimal import Decimal

from app.services import discount_math
from app.services.discount_math import LineInput


def reprice_line(line, quantity, unit_price) -> None:
    """Set ``line.total`` (and its discount amount) for a new quantity/price."""
    if not getattr(line, "discount_type", None):
        # Undiscounted lines keep their exact historical rounding.
        line.total = (Decimal(str(quantity)) * Decimal(str(unit_price))).quantize(Decimal("0.01"))
        return
    result = discount_math.compute_line(
        LineInput(
            quantity=Decimal(str(quantity)),
            unit_price=Decimal(str(unit_price)),
            discount_type=getattr(line, "discount_type", None),
            discount_value=getattr(line, "discount_value", None),
        )
    )
    line.total = result.net
    if getattr(line, "discount_type", None):
        line.discount_amount = result.discount


def apply_order_discount(order, items_total: Decimal) -> Decimal:
    """Return the order subtotal after its own discount; updates ``discount_amount``."""
    if not getattr(order, "discount_type", None):
        return items_total
    disc, subtotal = discount_math.apply_document_discount(
        items_total, order.discount_type, order.discount_value
    )
    order.discount_amount = disc
    return subtotal
