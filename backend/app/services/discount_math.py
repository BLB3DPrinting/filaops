"""Shared discount and document-total math for quotes, sales orders and invoices.

Every screen, stored record and PDF that shows a quote, order or invoice total
computes it here, so the stored total always equals the printed one.

Order of operations (each displayed step rounded to cents, half up):

1. line gross     = quantity x unit price
2. line discount  = percent of the line gross, or a fixed amount capped at it
3. items total    = sum of (line gross - line discount)
4. doc discount   = percent of the items total, or a fixed amount capped at it
5. subtotal       = items total - doc discount
6. tax            = computed by the caller on the subtotal (tax_calculation_service)
7. total          = subtotal + tax + shipping

A missing discount (no type, or no value) is a zero discount, so records made
before discounts existed compute exactly as they did.

Pure functions only: no database access and no ORM imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
HUNDRED = Decimal("100")

DISCOUNT_PERCENT = "percent"
DISCOUNT_AMOUNT = "amount"
DISCOUNT_TYPES = (DISCOUNT_PERCENT, DISCOUNT_AMOUNT)


def to_money(value) -> Decimal:
    """Round a value to cents, half up. ``None`` is zero."""
    if value is None:
        return ZERO
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def validate_discount(discount_type: Optional[str], discount_value) -> None:
    """Raise ``ValueError`` when a discount type/value pair is not usable.

    Both empty is valid (no discount). A value with no type, a type with no
    value, an unknown type, a negative value, or a percent above 100 is not.
    """
    if discount_type in (None, "") and discount_value is None:
        return
    if discount_type not in DISCOUNT_TYPES:
        raise ValueError(f"discount_type must be one of {', '.join(DISCOUNT_TYPES)}")
    if discount_value is None:
        raise ValueError("discount_value is required when discount_type is set")
    value = Decimal(str(discount_value))
    if value < 0:
        raise ValueError("discount_value cannot be negative")
    if discount_type == DISCOUNT_PERCENT and value > HUNDRED:
        raise ValueError("a percent discount cannot be more than 100")


def discount_amount(base, discount_type: Optional[str], discount_value) -> Decimal:
    """Money taken off ``base`` by one discount, in cents, never more than ``base``."""
    base_money = to_money(base)
    if not discount_type or discount_value is None or base_money <= 0:
        return ZERO
    value = Decimal(str(discount_value))
    if value <= 0:
        return ZERO
    if discount_type == DISCOUNT_PERCENT:
        amount = to_money(base_money * value / HUNDRED)
    elif discount_type == DISCOUNT_AMOUNT:
        amount = to_money(value)
    else:
        return ZERO
    return min(amount, base_money)


def default_discount_label(discount_type: Optional[str], discount_value) -> Optional[str]:
    """Label used on documents when the user gave none, e.g. ``"10% discount"``."""
    if not discount_type or discount_value is None:
        return None
    value = Decimal(str(discount_value))
    if discount_type == DISCOUNT_PERCENT:
        text = format(value.normalize(), "f")
        return f"{text}% discount"
    return "Discount"


@dataclass(frozen=True)
class LineInput:
    quantity: Decimal
    unit_price: Decimal
    discount_type: Optional[str] = None
    discount_value: Optional[Decimal] = None


@dataclass(frozen=True)
class LineResult:
    gross: Decimal
    discount: Decimal
    net: Decimal


@dataclass(frozen=True)
class DocumentTotals:
    lines: list[LineResult] = field(default_factory=list)
    items_gross: Decimal = ZERO      # sum of line gross amounts
    line_discounts: Decimal = ZERO   # sum of line discounts
    items_total: Decimal = ZERO      # items_gross - line_discounts
    discount: Decimal = ZERO         # document-level discount
    subtotal: Decimal = ZERO         # items_total - discount


def compute_line(line: LineInput) -> LineResult:
    gross = to_money(Decimal(str(line.quantity)) * Decimal(str(line.unit_price)))
    disc = discount_amount(gross, line.discount_type, line.discount_value)
    return LineResult(gross=gross, discount=disc, net=gross - disc)


def compute_document(
    lines: Iterable[LineInput],
    discount_type: Optional[str] = None,
    discount_value=None,
) -> DocumentTotals:
    """Steps 1-5 of the order of operations for a whole quote, order or invoice."""
    results = [compute_line(line) for line in lines]
    items_gross = sum((r.gross for r in results), ZERO)
    line_discounts = sum((r.discount for r in results), ZERO)
    items_total = items_gross - line_discounts
    doc_discount = discount_amount(items_total, discount_type, discount_value)
    return DocumentTotals(
        lines=results,
        items_gross=items_gross,
        line_discounts=line_discounts,
        items_total=items_total,
        discount=doc_discount,
        subtotal=items_total - doc_discount,
    )


def apply_document_discount(items_total, discount_type: Optional[str], discount_value) -> tuple[Decimal, Decimal]:
    """Return ``(discount, subtotal)`` for a document whose items total is known."""
    items = to_money(items_total)
    disc = discount_amount(items, discount_type, discount_value)
    return disc, items - disc
