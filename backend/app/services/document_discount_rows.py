"""What a quote, order or invoice document prints for descriptions and discounts.

Kept apart from the PDF builders so the rows are tested on their own and every
document prints the same rows in the same order:

    Items total            (only when a discount exists)
    Line discounts         -x.xx
    <quote discount label> -x.xx
    Subtotal

Amounts come from the stored record, which discount_math computed, so the
printed rows add up to the stored subtotal exactly.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable, Iterable, Optional

from app.services import discount_math

MINUS = "−"


def has_line_discount(line) -> bool:
    return bool(getattr(line, "discount_type", None)) and (getattr(line, "discount_amount", None) or 0) > 0


def line_gross(line) -> Decimal:
    """The amount column for a line: its total before its own discount."""
    if has_line_discount(line):
        return discount_math.to_money(line.total) + discount_math.to_money(line.discount_amount)
    return discount_math.to_money(line.total)


def line_discount_text(line) -> Optional[str]:
    if not has_line_discount(line):
        return None
    return line.discount_label or discount_math.default_discount_label(
        line.discount_type, line.discount_value
    )


def document_discount_label(doc) -> str:
    return (
        getattr(doc, "discount_label", None)
        or discount_math.default_discount_label(
            getattr(doc, "discount_type", None), getattr(doc, "discount_value", None)
        )
        or "Discount"
    )


def summary_rows(
    lines: Iterable,
    doc,
    *,
    items_gross_fallback: Decimal,
) -> list[tuple[str, Decimal]]:
    """Discount rows between the items and the subtotal, as (label, signed amount).

    Returns an empty list when nothing is discounted, so documents made before
    discounts existed print exactly what they printed before.
    """
    lines = list(lines)
    line_discounts = sum(
        (discount_math.to_money(line.discount_amount) for line in lines if has_line_discount(line)),
        Decimal("0.00"),
    )
    doc_discount = discount_math.to_money(getattr(doc, "discount_amount", None))
    if line_discounts <= 0 and doc_discount <= 0:
        return []

    items_gross = (
        sum((line_gross(line) for line in lines), Decimal("0.00"))
        if lines
        else discount_math.to_money(items_gross_fallback)
    )
    rows: list[tuple[str, Decimal]] = [("Items total", items_gross)]
    if line_discounts > 0:
        rows.append(("Line discounts", -line_discounts))
    if doc_discount > 0:
        rows.append((document_discount_label(doc), -doc_discount))
    return rows


def format_signed(amount: Decimal, fmt: Callable[[Decimal], str]) -> str:
    """``fmt`` the absolute value, with a real minus sign for negatives."""
    if amount < 0:
        return f"{MINUS}{fmt(-amount)}"
    return fmt(amount)


def description_html(text: Optional[str], esc: Callable[[str], str]) -> Optional[str]:
    """Escaped description with its line breaks kept, for a ReportLab Paragraph."""
    if not text or not text.strip():
        return None
    return "<br/>".join(esc(part) for part in text.strip().splitlines())
