"""Tests for state-aware sales tax calculation helpers."""
from decimal import Decimal

from app.services.tax_calculation_service import (
    ShippingChargeType,
    calculate_sales_tax,
)


def test_indiana_seller_billed_shipping_is_taxable():
    """Indiana taxes seller-billed delivery charges for taxable goods."""
    result = calculate_sales_tax(
        subtotal=Decimal("100.00"),
        tax_rate=Decimal("0.07"),
        shipping_cost=Decimal("10.00"),
        ship_to_state="IN",
    )

    assert result.taxable_base == Decimal("110.00")
    assert result.tax_amount == Decimal("7.70")
    assert result.shipping_taxable is True


def test_non_indiana_shipping_keeps_existing_subtotal_tax_behavior():
    """States without a shipping rule keep shipping outside the taxable base."""
    result = calculate_sales_tax(
        subtotal=Decimal("100.00"),
        tax_rate=Decimal("0.07"),
        shipping_cost=Decimal("10.00"),
        ship_to_state="OH",
    )

    assert result.taxable_base == Decimal("100.00")
    assert result.tax_amount == Decimal("7.00")
    assert result.shipping_taxable is False


def test_indiana_separately_stated_usps_postage_is_not_taxable():
    """Indiana separately stated actual USPS postage is not taxable."""
    result = calculate_sales_tax(
        subtotal=Decimal("100.00"),
        tax_rate=Decimal("0.07"),
        shipping_cost=Decimal("10.00"),
        ship_to_state="IN",
        shipping_charge_type=ShippingChargeType.USPS_POSTAGE,
    )

    assert result.taxable_base == Decimal("100.00")
    assert result.tax_amount == Decimal("7.00")
    assert result.shipping_taxable is False
