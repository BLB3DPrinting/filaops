"""Tests for uom_service.py — UOM conversions and cost calculations."""
import pytest
from decimal import Decimal

from app.services.uom_service import (
    get_cost_reference_unit,
    convert_cost_for_unit,
    _convert_uom_inline,
    convert_quantity_safe,
    format_quantity_with_unit,
    format_conversion_note,
    get_product_consumption_uom,
    UOMConversionError,
    INLINE_UOM_CONVERSIONS,
)


class TestGetCostReferenceUnit:
    def test_grams_returns_kg(self):
        assert get_cost_reference_unit("G") == "KG"

    def test_kg_returns_kg(self):
        assert get_cost_reference_unit("KG") == "KG"

    def test_lb_returns_kg(self):
        assert get_cost_reference_unit("LB") == "KG"

    def test_mm_returns_m(self):
        assert get_cost_reference_unit("MM") == "M"

    def test_ea_returns_ea(self):
        assert get_cost_reference_unit("EA") == "EA"

    def test_none_defaults_to_ea(self):
        assert get_cost_reference_unit(None) == "EA"

    def test_unknown_returns_as_is(self):
        assert get_cost_reference_unit("SPOOL") == "SPOOL"

    def test_case_insensitive(self):
        assert get_cost_reference_unit("kg") == "KG"
        assert get_cost_reference_unit("Kg") == "KG"


class TestConvertCostForUnit:
    def test_none_cost_returns_none(self):
        assert convert_cost_for_unit(None, "KG", "G") is None

    def test_same_unit_returns_original(self):
        cost = Decimal("15.00")
        assert convert_cost_for_unit(cost, "KG", "KG") == cost

    def test_kg_to_g(self):
        # $15/KG → $0.015/G
        result = convert_cost_for_unit(Decimal("15.00"), "KG", "G")
        assert result == Decimal("0.015")

    def test_g_to_kg(self):
        # $0.015/G → $15/KG
        result = convert_cost_for_unit(Decimal("0.015"), "G", "KG")
        assert result == Decimal("15")

    def test_incompatible_units_returns_original(self):
        cost = Decimal("10.00")
        assert convert_cost_for_unit(cost, "KG", "M") == cost

    def test_unknown_unit_returns_original(self):
        cost = Decimal("10.00")
        assert convert_cost_for_unit(cost, "SPOOL", "G") == cost


class TestConvertUomInline:
    def test_same_unit(self):
        qty, ok = _convert_uom_inline(Decimal("100"), "G", "G")
        assert qty == Decimal("100")
        assert ok is True

    def test_g_to_kg(self):
        qty, ok = _convert_uom_inline(Decimal("1000"), "G", "KG")
        assert ok is True
        assert qty == Decimal("1")

    def test_kg_to_g(self):
        qty, ok = _convert_uom_inline(Decimal("1"), "KG", "G")
        assert ok is True
        assert qty == Decimal("1000")

    def test_mm_to_m(self):
        qty, ok = _convert_uom_inline(Decimal("1000"), "MM", "M")
        assert ok is True
        assert qty == Decimal("1")

    def test_incompatible_returns_false(self):
        qty, ok = _convert_uom_inline(Decimal("100"), "KG", "M")
        assert ok is False
        assert qty == Decimal("100")

    def test_unknown_unit_returns_false(self):
        qty, ok = _convert_uom_inline(Decimal("100"), "SPOOL", "G")
        assert ok is False


class TestConvertQuantitySafe:
    def test_same_unit_returns_true(self, db):
        qty, ok = convert_quantity_safe(db, Decimal("100"), "G", "G")
        assert ok is True
        assert qty == Decimal("100")

    def test_inline_fallback_g_to_kg(self, db):
        # No UOM records in test DB → falls back to inline conversion
        qty, ok = convert_quantity_safe(db, Decimal("3856"), "G", "KG")
        assert ok is True
        assert qty == Decimal("3.856")


class TestFormatQuantityWithUnit:
    def test_integer_quantity(self):
        assert format_quantity_with_unit(Decimal("5"), "EA") == "5 ea"

    def test_decimal_quantity(self):
        assert format_quantity_with_unit(Decimal("2.5"), "KG") == "2.5 kg"

    def test_strips_trailing_zeros(self):
        result = format_quantity_with_unit(Decimal("1.500"), "KG")
        assert result == "1.5 kg"


class TestFormatConversionNote:
    def test_basic_note(self):
        result = format_conversion_note(
            Decimal("225.23"), "G", Decimal("0.22523"), "KG"
        )
        assert "225.23 g" in result
        assert "0.22523 kg" in result

    def test_with_product_name(self):
        result = format_conversion_note(
            Decimal("100"), "G", Decimal("0.1"), "KG", product_name="PLA-BLACK"
        )
        assert "of PLA-BLACK" in result


class TestGetProductConsumptionUom:
    def test_raw_material_with_unit(self, db, raw_material):
        uom = get_product_consumption_uom(db, raw_material.id)
        assert uom == "G"

    def test_raw_material_without_unit_defaults_kg(self, db, make_product):
        product = make_product(
            item_type="supply", unit="EA", is_raw_material=True,
        )
        uom = get_product_consumption_uom(db, product.id)
        assert uom == "KG"

    def test_finished_good_uses_product_unit(self, db, finished_good):
        uom = get_product_consumption_uom(db, finished_good.id)
        assert uom == "EA"

    def test_nonexistent_product_returns_default(self, db):
        uom = get_product_consumption_uom(db, 999999)
        assert uom == "KG"

    def test_custom_default(self, db):
        uom = get_product_consumption_uom(db, 999999, default_unit="EA")
        assert uom == "EA"
