"""Shared sales tax calculation helpers.

This module keeps Core's built-in tax logic conservative and provider-neutral.
External providers such as QuickBooks, Avalara, or TaxJar can later implement
the same inputs while preserving the stored quote/order/invoice tax snapshots.
"""
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional


CENT = Decimal("0.01")


class ShippingChargeType(str, Enum):
    """Supported shipping charge semantics for tax calculation."""

    SELLER_BILLED_DELIVERY = "seller_billed_delivery"
    USPS_POSTAGE = "usps_postage"
    THIRD_PARTY_FREIGHT = "third_party_freight"


@dataclass(frozen=True)
class SalesTaxResult:
    taxable_base: Decimal
    tax_amount: Decimal
    shipping_taxable: bool


_STATE_ALIASES = {
    "INDIANA": "IN",
}

_SHIPPING_TAXABLE_STATES = {
    "IN",
}


def _as_decimal(value: Optional[Decimal]) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _normalize_state(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().upper()
    return _STATE_ALIASES.get(normalized, normalized)


def is_shipping_taxable(
    *,
    ship_to_state: Optional[str],
    seller_state: Optional[str] = None,
    shipping_charge_type: ShippingChargeType = ShippingChargeType.SELLER_BILLED_DELIVERY,
) -> bool:
    """Return whether shipping should be included in the taxable base."""
    if shipping_charge_type != ShippingChargeType.SELLER_BILLED_DELIVERY:
        return False

    state = _normalize_state(ship_to_state) or _normalize_state(seller_state)
    return state in _SHIPPING_TAXABLE_STATES


def calculate_sales_tax(
    *,
    subtotal: Decimal,
    tax_rate: Optional[Decimal],
    shipping_cost: Optional[Decimal] = None,
    ship_to_state: Optional[str] = None,
    seller_state: Optional[str] = None,
    shipping_charge_type: ShippingChargeType = ShippingChargeType.SELLER_BILLED_DELIVERY,
) -> SalesTaxResult:
    """Calculate tax from line subtotal plus any jurisdiction-taxable shipping."""
    subtotal_amount = _as_decimal(subtotal)
    shipping_amount = _as_decimal(shipping_cost)
    rate = _as_decimal(tax_rate)
    shipping_taxable = is_shipping_taxable(
        ship_to_state=ship_to_state,
        seller_state=seller_state,
        shipping_charge_type=shipping_charge_type,
    )

    taxable_base = subtotal_amount
    if shipping_taxable:
        taxable_base += shipping_amount

    tax_amount = (
        (taxable_base * rate).quantize(CENT)
        if tax_rate is not None
        else Decimal("0")
    )
    return SalesTaxResult(
        taxable_base=taxable_base.quantize(CENT),
        tax_amount=tax_amount,
        shipping_taxable=shipping_taxable,
    )
