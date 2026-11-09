"""
Tests for app.services.cost_basis — the single rule for "cost per stock unit".

Today's cost contract:
  - standard_cost is per PURCHASE unit ($/KG)
  - average_cost and last_cost are per STOCK unit ($/G)

These are pure tests: no database, plain stand-in objects.
"""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.cost_basis import (
    cost_per_stock_unit,
    normalize_unit,
    purchase_line_for_stock_quantity,
    stock_units_per_purchase_unit,
)


def _product(**kw):
    base = dict(
        sku="TEST-SKU",
        unit="EA",
        purchase_uom="EA",
        purchase_factor=None,
        cost_method="average",
        standard_cost=None,
        average_cost=None,
        last_cost=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class TestNormalizeUnit:
    def test_uppercases_and_strips(self):
        assert normalize_unit(" kg ") == "KG"

    def test_none_defaults_to_ea(self):
        assert normalize_unit(None) == "EA"

    @pytest.mark.parametrize("code", ["pcs", "PCS", "pc", "each"])
    def test_count_synonyms_are_ea(self, code):
        assert normalize_unit(code) == "EA"


class TestStockUnitsPerPurchaseUnit:
    def test_same_unit_is_one(self):
        assert stock_units_per_purchase_unit(_product(unit="EA", purchase_uom="EA")) == Decimal("1")

    def test_same_unit_ignores_case(self):
        assert stock_units_per_purchase_unit(_product(unit="g", purchase_uom="G")) == Decimal("1")

    def test_kg_to_g_is_1000(self):
        p = _product(unit="G", purchase_uom="KG", purchase_factor=Decimal("1000"))
        assert stock_units_per_purchase_unit(p) == Decimal("1000")

    def test_same_class_wins_over_a_wrong_factor(self):
        """CSV import can leave G/KG items with purchase_factor=1; 1 KG is still 1000 G."""
        p = _product(unit="G", purchase_uom="KG", purchase_factor=Decimal("1"))
        assert stock_units_per_purchase_unit(p) == Decimal("1000")

    def test_lb_to_g_uses_class_conversion(self):
        p = _product(unit="G", purchase_uom="LB")
        assert stock_units_per_purchase_unit(p) == Decimal("453.592")

    def test_pack_uses_purchase_factor(self):
        p = _product(unit="EA", purchase_uom="BOX", purchase_factor=Decimal("12"))
        assert stock_units_per_purchase_unit(p) == Decimal("12")

    def test_material_saved_as_g_ea_1000_uses_factor(self):
        """The UI saves materials as G / EA / 1000."""
        p = _product(unit="G", purchase_uom="EA", purchase_factor=Decimal("1000"))
        assert stock_units_per_purchase_unit(p) == Decimal("1000")

    def test_pcs_and_ea_are_the_same_unit(self):
        assert stock_units_per_purchase_unit(_product(unit="pcs", purchase_uom="EA")) == Decimal("1")

    def test_unknown_pack_without_factor_is_none(self):
        assert stock_units_per_purchase_unit(_product(unit="EA", purchase_uom="BOX")) is None

    def test_zero_factor_is_treated_as_missing(self):
        p = _product(unit="EA", purchase_uom="BOX", purchase_factor=Decimal("0"))
        assert stock_units_per_purchase_unit(p) is None

    def test_missing_purchase_uom_means_stock_unit(self):
        assert stock_units_per_purchase_unit(_product(unit="G", purchase_uom=None)) == Decimal("1")


class TestCostPerStockUnit:
    def test_average_cost_is_already_per_stock_unit(self):
        """The double-division bug: average cost must NOT be divided by the factor."""
        p = _product(unit="G", purchase_uom="KG", purchase_factor=Decimal("1000"),
                     average_cost=Decimal("0.02"), standard_cost=Decimal("0.02"))
        assert cost_per_stock_unit(p) == Decimal("0.02")

    def test_last_cost_used_when_no_average(self):
        p = _product(unit="G", purchase_uom="KG", last_cost=Decimal("0.025"))
        assert cost_per_stock_unit(p) == Decimal("0.025")

    def test_standard_cost_is_converted_from_purchase_unit(self):
        """Never-received filament: only standard_cost ($/KG) exists."""
        p = _product(unit="G", purchase_uom="KG", purchase_factor=Decimal("1000"),
                     standard_cost=Decimal("20.00"))
        assert cost_per_stock_unit(p) == Decimal("0.02")

    def test_standard_method_converts_even_when_average_exists(self):
        p = _product(cost_method="standard", unit="G", purchase_uom="KG",
                     standard_cost=Decimal("20.00"), average_cost=Decimal("0.5"))
        assert cost_per_stock_unit(p) == Decimal("0.02")

    def test_standard_cost_with_pack_factor(self):
        p = _product(unit="EA", purchase_uom="BOX", purchase_factor=Decimal("12"),
                     standard_cost=Decimal("24.00"))
        assert cost_per_stock_unit(p) == Decimal("2")

    def test_standard_cost_g_ea_1000_material(self):
        p = _product(unit="G", purchase_uom="EA", purchase_factor=Decimal("1000"),
                     standard_cost=Decimal("22.99"))
        assert cost_per_stock_unit(p) == Decimal("0.02299")

    def test_standard_cost_same_unit_unchanged(self):
        p = _product(standard_cost=Decimal("5.00"))
        assert cost_per_stock_unit(p) == Decimal("5.00")

    def test_no_cost_is_none(self):
        assert cost_per_stock_unit(_product()) is None

    def test_none_method_defaults_to_average(self):
        p = _product(cost_method=None, average_cost=Decimal("3"))
        assert cost_per_stock_unit(p) == Decimal("3")

    def test_unconvertible_standard_cost_is_returned_unchanged_with_warning(self, caplog):
        """No pack size and no class conversion: the old pass-through is kept
        (the user has no screen to fix it yet) but says so in the log."""
        p = _product(sku="BOX-NO-FACTOR", unit="EA", purchase_uom="BOX",
                     standard_cost=Decimal("24.00"))
        with caplog.at_level("WARNING"):
            assert cost_per_stock_unit(p) == Decimal("24.00")
        assert "BOX-NO-FACTOR" in caplog.text


class TestPurchaseLineForStockQuantity:
    def test_filament_is_ordered_in_kg_at_cost_per_kg(self):
        """Audit C10: 5000 G planned at $20/KG must be a 5 KG line at $20, not 5000 at $20."""
        p = _product(unit="G", purchase_uom="KG", purchase_factor=Decimal("1000"),
                     standard_cost=Decimal("20.00"))
        qty, unit, unit_cost = purchase_line_for_stock_quantity(p, Decimal("5000"))
        assert (qty, unit, unit_cost) == (Decimal("5.0000"), "KG", Decimal("20.0000"))

    def test_received_filament_uses_average_cost_scaled_to_purchase_unit(self):
        p = _product(unit="G", purchase_uom="KG", purchase_factor=Decimal("1000"),
                     standard_cost=Decimal("0.0127"), average_cost=Decimal("0.0127"))
        qty, unit, unit_cost = purchase_line_for_stock_quantity(p, Decimal("250"))
        assert (qty, unit, unit_cost) == (Decimal("0.2500"), "KG", Decimal("12.7000"))

    def test_quantity_rounds_up_so_the_order_is_never_short(self):
        p = _product(unit="G", purchase_uom="KG", standard_cost=Decimal("20.00"))
        qty, _, _ = purchase_line_for_stock_quantity(p, Decimal("0.05"))
        assert qty == Decimal("0.0001")

    def test_same_unit_item_is_unchanged(self):
        p = _product(standard_cost=Decimal("5.00"))
        assert purchase_line_for_stock_quantity(p, Decimal("7")) == (
            Decimal("7.0000"), "EA", Decimal("5.0000"))

    def test_pack_without_a_size_is_ordered_in_the_stock_unit(self):
        p = _product(unit="EA", purchase_uom="BOX", average_cost=Decimal("2.00"))
        assert purchase_line_for_stock_quantity(p, Decimal("60")) == (
            Decimal("60.0000"), "EA", Decimal("2.0000"))

    def test_pack_with_a_size_is_still_ordered_in_the_stock_unit(self):
        """Receiving does not apply purchase_factor, so a "5 BOX" line would be
        received as 5 EA. Order 60 EA at the per-EA cost instead."""
        p = _product(unit="EA", purchase_uom="BOX", purchase_factor=Decimal("12"),
                     standard_cost=Decimal("24.00"))
        assert purchase_line_for_stock_quantity(p, Decimal("60")) == (
            Decimal("60.0000"), "EA", Decimal("2.0000"))

    def test_g_ea_1000_material_is_ordered_in_grams(self):
        """Receiving cannot convert EA to G for a material and would refuse the line."""
        p = _product(unit="G", purchase_uom="EA", purchase_factor=Decimal("1000"),
                     standard_cost=Decimal("20.00"))
        assert purchase_line_for_stock_quantity(p, Decimal("5000")) == (
            Decimal("5000.0000"), "G", Decimal("0.0200"))

    def test_unit_code_is_the_products_own(self):
        """A pcs item gets a PCS line, which receiving sees as equal to the product unit."""
        p = _product(unit="pcs", purchase_uom="EA", standard_cost=Decimal("0.0575"))
        assert purchase_line_for_stock_quantity(p, Decimal("100")) == (
            Decimal("100.0000"), "PCS", Decimal("0.0575"))

    def test_no_cost_gives_zero(self):
        p = _product(unit="G", purchase_uom="KG")
        qty, unit, unit_cost = purchase_line_for_stock_quantity(p, Decimal("1000"))
        assert (qty, unit, unit_cost) == (Decimal("1.0000"), "KG", Decimal("0.0000"))
