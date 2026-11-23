"""Money columns for a sales order made from a quote by the portal/payment path.

``quote_conversion_service`` used to copy ``quote.total_price`` (which already
holds tax and shipping) into the order's ``total_price`` (the order subtotal),
store zero tax, and then add shipping again. The order, and the invoice made
from it, charged more than the quote the customer accepted.

The order now carries the quote's own numbers:

- subtotal (after line and quote discounts) -> ``SalesOrder.total_price``
- discount amount -> ``SalesOrder.discount_amount`` (with the type/value/label)
- tax amount, rate and name -> the same columns on the order
- shipping -> ``SalesOrder.shipping_cost``
- ``grand_total`` = subtotal + tax + shipping, which equals the quote total

Tax is recomputed only when the caller ships somewhere other than the quote
says (a different shipping cost or ship-to state) and the quote carries a tax
rate, using the same tax calculator the portal accept uses.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.company_settings import CompanySettings
from app.services import discount_math
from app.services.tax_calculation_service import calculate_sales_tax

ZERO = discount_math.ZERO


@dataclass(frozen=True)
class OrderMoney:
    unit_price: Decimal
    subtotal: Decimal
    tax_amount: Decimal
    tax_rate: Optional[Decimal]
    tax_name: Optional[str]
    shipping_cost: Decimal
    grand_total: Decimal

    def order_columns(self) -> dict:
        """Keyword arguments for ``SalesOrder(...)``."""
        return {
            "unit_price": self.unit_price,
            "total_price": self.subtotal,
            "tax_amount": self.tax_amount,
            "tax_rate": self.tax_rate,
            "tax_name": self.tax_name,
            "is_taxable": self.tax_rate is not None,
            "shipping_cost": self.shipping_cost,
            "grand_total": self.grand_total,
        }


def _stored_subtotal(quote) -> tuple[Decimal, Decimal, Decimal]:
    """``(subtotal, tax, shipping)`` as the quote stored them.

    A quote saved before ``subtotal`` was filled in has only ``total_price``;
    its subtotal is the total less tax and shipping. If that comes out below
    zero the stored parts can't be trusted, so the whole total is the subtotal,
    as ``sales_order_service.convert_quote_to_sales_order`` already does.
    """
    tax = discount_math.to_money(quote.tax_amount)
    shipping = discount_math.to_money(quote.shipping_cost)
    if quote.subtotal is not None:
        return discount_math.to_money(quote.subtotal), tax, shipping
    total = discount_math.to_money(quote.total_price)
    inferred = total - tax - shipping
    if inferred < ZERO:
        return total, ZERO, ZERO
    return inferred, tax, shipping


def _unit_price(quote, subtotal: Decimal) -> Decimal:
    if quote.unit_price is not None:
        return discount_math.to_money(quote.unit_price)
    quantity = Decimal(str(quote.quantity or 1))
    gross = subtotal + discount_math.to_money(quote.discount_amount)
    return discount_math.to_money(gross / quantity)


def order_money_from_quote(
    db: Session,
    quote,
    *,
    shipping_cost: Optional[Decimal] = None,
    ship_to_state: Optional[str] = None,
) -> OrderMoney:
    """The order's money columns for ``quote``.

    ``shipping_cost`` / ``ship_to_state`` are the caller's overrides; ``None``
    means "as the quote says".
    """
    subtotal, tax, shipping = _stored_subtotal(quote)

    if shipping_cost is not None:
        new_shipping = discount_math.to_money(shipping_cost)
    else:
        new_shipping = shipping
    state = ship_to_state or quote.shipping_state
    destination_changed = new_shipping != shipping or (state or None) != (quote.shipping_state or None)

    if destination_changed and quote.tax_rate is not None:
        settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
        tax = discount_math.to_money(
            calculate_sales_tax(
                subtotal=subtotal,
                tax_rate=quote.tax_rate,
                shipping_cost=new_shipping,
                ship_to_state=state,
                seller_state=settings.company_state if settings else None,
            ).tax_amount
        )

    return OrderMoney(
        unit_price=_unit_price(quote, subtotal),
        subtotal=subtotal,
        tax_amount=tax,
        tax_rate=quote.tax_rate,
        tax_name=getattr(quote, "tax_name", None),
        shipping_cost=new_shipping,
        grand_total=subtotal + tax + new_shipping,
    )
