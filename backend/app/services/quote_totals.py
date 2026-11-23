"""Quote line pricing and subtotal, on top of the shared discount math.

``quote_service`` calls these helpers when it creates or updates a quote, and
the quote preview endpoint calls ``preview_quote_totals`` so the quote screen
shows the same numbers the record stores and the PDF prints.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.product import Product
from app.services import discount_math
from app.services.discount_math import LineInput


def check_discount(discount_type: Optional[str], discount_value, where: str = "quote") -> None:
    """Turn an invalid discount into a 400 the API can show."""
    try:
        discount_math.validate_discount(discount_type, discount_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {where} discount: {exc}",
        ) from exc


def normalize_discount_type(discount_type: Optional[str], discount_value) -> tuple[Optional[str], Optional[Decimal]]:
    """Store "no discount" as NULLs, never as an empty string or a zero."""
    if not discount_type or discount_value is None:
        return None, None
    value = Decimal(str(discount_value))
    if value == 0:
        return None, None
    return discount_type, value


def apply_price_level(unit_price, product_id, price_level_percent) -> Decimal:
    """Unit price after the customer's price-level discount, rounded half up.

    Half up like every other money step in ``discount_math`` (and the quote
    form's offline estimate): a $2.01 item at 50% is $1.01, not $1.00.
    """
    price = discount_math.to_money(unit_price)
    if product_id and price_level_percent and price_level_percent > 0:
        price = discount_math.to_money(price * (Decimal("1") - Decimal(str(price_level_percent)) / Decimal("100")))
    return price


def product_description(db: Session, product_id: Optional[int]) -> Optional[str]:
    """The item's own Description, used as the default line description."""
    if not product_id:
        return None
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product or not product.description:
        return None
    return product.description


def build_line_values(
    db: Session,
    line: dict[str, Any],
    *,
    price_level_percent: Optional[Decimal],
) -> dict[str, Any]:
    """Column values for one QuoteLine from request data.

    ``line`` holds only the fields the client sent (``model_dump(exclude_unset=True)``
    for updates), so a missing ``description`` means "use the item's
    Description", while an empty one sent on purpose stays empty.
    """
    product_id = line.get("product_id")
    already_applied = line.get("price_level_percent_applied")
    if already_applied is not None:
        # A reopened line's price already includes the price-level discount it
        # was saved with. Applying the customer's level again would compound
        # it on every save, so keep the price and the percent it was saved with.
        unit_price = discount_math.to_money(line["unit_price"])
        line_price_level = Decimal(str(already_applied)) if product_id else None
    else:
        unit_price = apply_price_level(line["unit_price"], product_id, price_level_percent)
        line_price_level = price_level_percent if product_id else None
    discount_type, discount_value = normalize_discount_type(
        line.get("discount_type"), line.get("discount_value")
    )
    check_discount(discount_type, discount_value, where="line")
    result = discount_math.compute_line(
        LineInput(
            quantity=Decimal(str(line.get("quantity", 1))),
            unit_price=unit_price,
            discount_type=discount_type,
            discount_value=discount_value,
        )
    )
    if "description" in line:
        description = line.get("description") or None
    else:
        description = product_description(db, product_id)

    return {
        "product_id": product_id,
        "product_name": line["product_name"],
        "quantity": line.get("quantity", 1),
        "unit_price": unit_price,
        "discount_percent": (
            line_price_level if line_price_level and line_price_level > 0 else None
        ),
        "total": result.net,
        "description": description,
        "discount_type": discount_type,
        "discount_value": discount_value,
        "discount_label": (line.get("discount_label") or None) if discount_type else None,
        "discount_amount": result.discount if discount_type else None,
        "material_type": line.get("material_type"),
        "color": line.get("color"),
        "notes": line.get("notes"),
    }


def quote_subtotal_from_line_values(
    line_values: Iterable[dict[str, Any]],
    discount_type: Optional[str],
    discount_value,
) -> tuple[Decimal, Optional[Decimal]]:
    """``(subtotal, quote discount amount)`` for lines built by ``build_line_values``."""
    items_total = sum((Decimal(str(v["total"])) for v in line_values), Decimal("0"))
    disc, subtotal = discount_math.apply_document_discount(items_total, discount_type, discount_value)
    return subtotal, (disc if discount_type else None)


def quote_subtotal_from_lines(quote) -> Decimal:
    """Recompute a saved quote's line totals and subtotal from its lines.

    Used when only the quote discount (or tax/shipping) changes on update.
    Writes line ``total``/``discount_amount`` and ``quote.discount_amount``.
    """
    items_total = Decimal("0")
    for ql in quote.lines:
        result = discount_math.compute_line(
            LineInput(
                quantity=Decimal(str(ql.quantity)),
                unit_price=Decimal(str(ql.unit_price)),
                discount_type=ql.discount_type,
                discount_value=ql.discount_value,
            )
        )
        ql.total = result.net
        ql.discount_amount = result.discount if ql.discount_type else None
        items_total += result.net
    disc, subtotal = discount_math.apply_document_discount(
        items_total, quote.discount_type, quote.discount_value
    )
    quote.discount_amount = disc if quote.discount_type else None
    return subtotal


def single_item_subtotal(unit_price, quantity, discount_type, discount_value) -> tuple[Decimal, Optional[Decimal]]:
    """``(subtotal, discount)`` for a legacy single-item quote (no line rows)."""
    gross = discount_math.to_money(Decimal(str(unit_price)) * Decimal(str(quantity)))
    disc, subtotal = discount_math.apply_document_discount(gross, discount_type, discount_value)
    return subtotal, (disc if discount_type else None)


def preview_quote_totals(
    db: Session,
    *,
    lines: list[dict[str, Any]],
    discount_type: Optional[str],
    discount_value,
    price_level_percent: Optional[Decimal],
    tax_rate: Optional[Decimal],
    shipping_cost: Optional[Decimal],
    ship_to_state: Optional[str],
    seller_state: Optional[str],
) -> dict[str, Any]:
    """Every number the quote screen shows, computed exactly as a save would."""
    from app.services.tax_calculation_service import calculate_sales_tax

    discount_type, discount_value = normalize_discount_type(discount_type, discount_value)
    check_discount(discount_type, discount_value)
    line_values = [
        build_line_values(db, line, price_level_percent=price_level_percent) for line in lines
    ]
    items_gross = sum(
        (discount_math.to_money(Decimal(str(v["unit_price"])) * Decimal(str(v["quantity"]))) for v in line_values),
        Decimal("0"),
    )
    line_discounts = sum((v["discount_amount"] or Decimal("0") for v in line_values), Decimal("0"))
    subtotal, quote_discount = quote_subtotal_from_line_values(line_values, discount_type, discount_value)
    shipping = discount_math.to_money(shipping_cost)
    tax_amount = None
    if tax_rate is not None:
        tax_amount = calculate_sales_tax(
            subtotal=subtotal,
            tax_rate=tax_rate,
            shipping_cost=shipping,
            ship_to_state=ship_to_state,
            seller_state=seller_state,
        ).tax_amount
    return {
        "lines": [
            {
                "unit_price": v["unit_price"],
                "gross": discount_math.to_money(Decimal(str(v["unit_price"])) * Decimal(str(v["quantity"]))),
                "discount_amount": v["discount_amount"] or Decimal("0"),
                "total": v["total"],
                "description": v["description"],
            }
            for v in line_values
        ],
        "items_gross": items_gross,
        "line_discounts": line_discounts,
        "items_total": items_gross - line_discounts,
        "discount_amount": quote_discount or Decimal("0"),
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount or Decimal("0"),
        "shipping_cost": shipping,
        "total": subtotal + (tax_amount or Decimal("0")) + shipping,
    }


def preview_for_request(db: Session, request) -> dict[str, Any]:
    """Preview for a ``QuoteTotalsPreview`` request: the totals a save would store.

    Tax and the price-level discount are resolved the same way create/update
    resolve them, so the screen never shows a number the record won't have.
    """
    from app.models.company_settings import CompanySettings
    from app.models.quote import Quote
    from app.services.quote_service import _get_customer_discount, _resolve_tax

    quote = None
    if getattr(request, "quote_id", None):
        quote = db.query(Quote).filter(Quote.id == request.quote_id).first()
        if not quote:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quote not found")

    company_settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    # update_quote clears the customer on an explicit null and keeps it only
    # when the field is left out; preview the same way.
    if quote is not None and "customer_id" not in getattr(request, "model_fields_set", {"customer_id"}):
        customer_id = quote.customer_id
    else:
        customer_id = request.customer_id
    price_level = _get_customer_discount(db, customer_id) if customer_id else None

    if quote is None:
        # create_quote: _resolve_tax decides (a chosen rate wins).
        tax_rate, _amount, _name = _resolve_tax(db, Decimal("0"), request, company_settings)
    elif request.apply_tax is False:
        tax_rate = None  # update_quote: tax switched off
    elif request.apply_tax is None and request.tax_rate_id is None:
        tax_rate = quote.tax_rate  # update_quote: stored rate kept
    else:
        tax_rate, _amount, _name = _resolve_tax(db, Decimal("0"), request, company_settings)

    shipping_cost = request.shipping_cost
    if shipping_cost is None and quote is not None:
        shipping_cost = quote.shipping_cost
    ship_to_state = request.shipping_state or (quote.shipping_state if quote else None)

    # update_quote keeps the stored quote discount when the request leaves the
    # discount fields out, so the preview must too. An explicit null still
    # previews removing it.
    sent = request.model_fields_set
    discount_type = request.discount_type
    discount_value = request.discount_value
    if quote is not None:
        if "discount_type" not in sent:
            discount_type = quote.discount_type
        if "discount_value" not in sent:
            discount_value = quote.discount_value

    return preview_quote_totals(
        db,
        lines=[line.model_dump(exclude_unset=True) | {
            "product_id": line.product_id,
            "product_name": line.product_name,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
        } for line in request.lines],
        discount_type=discount_type,
        discount_value=discount_value,
        price_level_percent=price_level,
        tax_rate=tax_rate,
        shipping_cost=shipping_cost,
        ship_to_state=ship_to_state,
        seller_state=company_settings.company_state if company_settings else None,
    )


def order_discount_fields(source) -> dict[str, Any]:
    """Discount columns copied from a quote (or quote line) to its order counterpart."""
    return {
        "discount_type": getattr(source, "discount_type", None),
        "discount_value": getattr(source, "discount_value", None),
        "discount_label": getattr(source, "discount_label", None),
        "discount_amount": getattr(source, "discount_amount", None),
    }
