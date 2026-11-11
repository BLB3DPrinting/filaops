"""
unit_conversion: the one module that converts a quantity or a unit cost.

The worked cases of docs/UOM_CONVERSION_PLAN.md section 5 are tested here as
conversions. Nothing in this stage moves stock or changes a cost.
"""
import dataclasses
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.models.product_unit import ProductUnit
from app.models.uom import UnitOfMeasure
from app.services import unit_conversion as uc
from app.services.uom_service import UOMConversionError, convert_quantity_safe

# Appendix B of the plan, plus the two time units. code -> (kind, factor to the kind's base).
APPENDIX_B = {
    "KG": ("weight", "1"), "G": ("weight", "0.001"), "MG": ("weight", "0.000001"),
    "LB": ("weight", "0.45359237"), "OZ": ("weight", "0.028349523125"),
    "M": ("length", "1"), "CM": ("length", "0.01"), "MM": ("length", "0.001"),
    "IN": ("length", "0.0254"), "FT": ("length", "0.3048"),
    "M2": ("area", "1"), "CM2": ("area", "0.0001"), "MM2": ("area", "0.000001"),
    "IN2": ("area", "0.00064516"), "FT2": ("area", "0.09290304"),
    "L": ("volume", "1"), "ML": ("volume", "0.001"),
    "EA": ("quantity", "1"),
    "HR": ("time", "1"), "MIN": ("time", "0.016666666666667"),
    "BOX": ("pack", "1"), "PK": ("pack", "1"), "ROLL": ("pack", "1"), "SPOOL": ("pack", "1"),
    "SHEET": ("pack", "1"), "CASE": ("pack", "1"), "BAG": ("pack", "1"),
}


def _item_unit(db, product, code, *, per_unit=None, per_stock=None):
    """Give an item a unit of its own: per_unit is "1 BOX = 12 EA", per_stock is "1 EA = 750 G"."""
    row = ProductUnit(
        product_id=product.id,
        unit_code=code,
        stock_units_per_unit=per_unit,
        units_per_stock_unit=per_stock,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def filament_g(make_product):
    return make_product(item_type="material", unit="G", purchase_uom="KG", is_raw_material=True)


@pytest.fixture
def filament_kg(make_product):
    return make_product(item_type="material", unit="KG", purchase_uom="LB", is_raw_material=True)


@pytest.fixture
def screws(make_product):
    return make_product(item_type="supply", unit="EA", purchase_uom="BOX")


class TestStandardUnits:
    def test_the_list_is_appendix_b_plus_hours_and_minutes(self):
        found = {u.code: (u.kind, u.factor) for u in uc.STANDARD_UNITS}
        assert found == {code: (kind, D(factor)) for code, (kind, factor) in APPENDIX_B.items()}
        assert len(uc.STANDARD_UNITS) == 27

    def test_every_standard_unit_is_in_the_test_database(self, db):
        rows = {u.code: u for u in db.query(UnitOfMeasure).all()}
        for code, (kind, factor) in APPENDIX_B.items():
            assert rows[code].uom_class == kind
            assert D(str(rows[code].to_base_factor)) == D(factor)

    def test_ensure_standard_units_adds_nothing_twice(self, db):
        assert uc.ensure_standard_units(db) == 0


class TestNormalizeUnitCode:
    @pytest.mark.parametrize("typed, code", [
        (" g ", "G"), ("kg", "KG"), ("pcs", "EA"), ("PC", "EA"), ("each", "EA"), ("Unit", "EA"),
        ("units", "EA"), ("pack", "PK"), ("Packs", "PK"), ("grams", "G"), ("kilogram", "KG"),
        ("milligrams", "MG"), ("BOX", "BOX"), ("widget", "WIDGET"),
    ])
    def test_spellings(self, typed, code):
        assert uc.normalize_unit_code(typed) == code

    @pytest.mark.parametrize("missing", [None, "", "   "])
    def test_a_missing_code_is_not_guessed(self, missing):
        assert uc.normalize_unit_code(missing) == ""


class TestPhysicalFactor:
    @pytest.mark.parametrize("from_unit, to_unit, factor", [
        ("KG", "G", "1000"), ("G", "KG", "0.001"), ("LB", "G", "453.59237"),
        ("OZ", "G", "28.349523125"), ("LB", "KG", "0.45359237"), ("M2", "CM2", "10000"),
        ("L", "ML", "1000"), ("FT", "IN", "12"), ("G", "g", "1"), ("BOX", "box", "1"),
    ])
    def test_exact_factors(self, db, from_unit, to_unit, factor):
        assert uc.physical_factor(db, from_unit, to_unit) == D(factor)

    @pytest.mark.parametrize("from_unit, to_unit", [
        ("G", "ML"), ("G", "ZORK"), ("ZORK", "G"), ("BOX", "PK"), ("BOX", "EA"), ("EA", "BOX"),
        ("KG", ""),
    ])
    def test_refusals(self, db, from_unit, to_unit):
        with pytest.raises(uc.UnitConversionError):
            uc.physical_factor(db, from_unit, to_unit)

    def test_the_error_is_the_one_callers_already_catch(self):
        assert issubclass(uc.UnitConversionError, UOMConversionError)

    def test_the_old_converter_no_longer_converts_one_pack_to_another(self, db):
        # BOX and PK are both rows of kind "pack" with a stored factor of 1.
        assert convert_quantity_safe(db, D("5"), "BOX", "PK") == (D("5"), False)

    def test_the_unit_table_is_read_once_per_session(self, db):
        statements = []

        def record(conn, cursor, statement, parameters, context, executemany):
            if "units_of_measure" in statement:
                statements.append(statement)

        bind = db.get_bind()
        uc.forget_units(db)
        event.listen(bind, "before_cursor_execute", record)
        try:
            for _ in range(100):
                uc.physical_factor(db, "LB", "G")
        finally:
            event.remove(bind, "before_cursor_execute", record)
        assert len(statements) == 1

    def test_a_unit_added_in_the_session_is_seen(self, db):
        uc.physical_factor(db, "M", "CM")
        metre = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "M").one()
        db.add(UnitOfMeasure(code="YD", name="Yard", symbol="yd", uom_class="length",
                             base_unit_id=metre.id, to_base_factor=D("0.9144")))
        db.flush()
        assert uc.physical_factor(db, "YD", "M") == D("0.9144")

    def test_a_unit_changed_in_the_session_is_seen(self, db):
        assert uc.physical_factor(db, "LB", "G") == D("453.59237")
        pound = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "LB").one()
        pound.to_base_factor = D("0.5")
        db.flush()
        assert uc.physical_factor(db, "LB", "G") == D("500")
        pound.active = False
        db.flush()
        with pytest.raises(uc.UnitConversionError):
            uc.physical_factor(db, "LB", "G")

    def test_a_rolled_back_change_is_forgotten(self, db):
        pound = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "LB").one()
        pound.to_base_factor = D("0.5")
        db.flush()
        assert uc.physical_factor(db, "LB", "G") == D("500")
        db.rollback()
        assert uc.physical_factor(db, "LB", "G") == D("453.59237")

    def test_an_installs_own_unit_wins_over_a_spelling(self, db, screws):
        """``pack`` means PK, unless this install has a unit it calls PACK."""
        assert uc.require_known_unit(db, "pack") == "PK"
        each = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "EA").one()
        db.add(UnitOfMeasure(code="PACK", name="Pack of ten", symbol="pack", uom_class="quantity",
                             base_unit_id=each.id, to_base_factor=D("10")))
        db.flush()
        assert uc.require_known_unit(db, "pack") == "PACK"
        assert uc.physical_factor(db, "pack", "EA") == D("10")
        assert uc.to_stock(db, screws, D("5"), "Pack").quantity == D("50.000000")
        assert {unit.unit_code for unit in uc.units_for_item(db, screws)} == {"EA", "PACK"}


class TestLookupOrder:
    def test_1_the_stock_unit_is_one_even_when_the_table_does_not_know_it(self, db, make_product):
        odd = make_product(unit="WIDGET")
        assert uc.stock_units_per(db, odd, "widget") == D("1")

    def test_2_same_kind_uses_the_table(self, db, filament_g):
        assert uc.stock_units_per(db, filament_g, "KG") == D("1000")

    def test_2_wins_over_a_line_factor(self, db, filament_g):
        assert uc.stock_units_per(db, filament_g, "KG", line_factor=D("5")) == D("1000")

    def test_3_a_line_factor_serves_a_unit_the_item_has_no_size_for(self, db, screws):
        assert uc.stock_units_per(db, screws, "BOX", line_factor=D("12")) == D("12")

    def test_3_wins_over_the_item_unit(self, db, screws):
        _item_unit(db, screws, "BOX", per_unit=D("12"))
        assert uc.stock_units_per(db, screws, "BOX", line_factor=D("10")) == D("10")

    def test_3_a_line_factor_of_zero_is_refused_not_skipped(self, db, screws):
        _item_unit(db, screws, "BOX", per_unit=D("12"))
        with pytest.raises(uc.UnitConversionError):
            uc.stock_units_per(db, screws, "BOX", line_factor=D("0"))

    def test_4_the_item_unit(self, db, screws):
        _item_unit(db, screws, "BOX", per_unit=D("12"))
        assert uc.stock_units_per(db, screws, "BOX") == D("12")

    def test_4_another_unit_of_the_same_kind_goes_through_the_table(self, db, make_product):
        spool = make_product(item_type="material", unit="EA", purchase_uom="EA")
        _item_unit(db, spool, "G", per_stock=D("750"))
        assert uc.to_stock(db, spool, D("3"), "KG").quantity == D("4.000000")

    def test_5_otherwise_it_refuses(self, db, screws):
        with pytest.raises(uc.UnitConversionError):
            uc.stock_units_per(db, screws, "BOX")

    def test_an_item_with_no_stock_unit_is_refused(self, db):
        blank = SimpleNamespace(id=None, sku="NO-UNIT", unit=None, purchase_uom=None)
        with pytest.raises(uc.UnitConversionError):
            uc.stock_units_per(db, blank, "EA")


class TestSizeStoredEitherWay:
    def test_one_each_is_750_grams(self, db, make_product):
        spool = make_product(item_type="material", unit="EA", purchase_uom="EA")
        _item_unit(db, spool, "G", per_stock=D("750"))
        assert uc.to_stock(db, spool, D("3000"), "G").quantity == D("4.000000")
        assert uc.to_stock(db, spool, D("1000000"), "G").quantity == D("1333.333333")
        assert uc.from_stock(db, spool, D("4"), "G") == D("3000.000000")


class TestWorkedCases:
    def test_a_three_kg_of_gram_stocked_filament(self, db, filament_g):
        got = uc.to_stock(db, filament_g, D("3"), "KG")
        assert (got.quantity, got.unit, got.factor) == (D("3000.000000"), "G", D("1000"))
        assert (got.entered_quantity, got.entered_unit) == (D("3"), "KG")
        assert uc.unit_cost_to_stock(db, filament_g, D("12.67"), "KG") == D("0.01267000")
        assert uc.unit_cost_from_stock(db, filament_g, D("0.01267"), "KG") == D("12.67000000")

    def test_b_five_pounds_of_kg_stocked_filament(self, db, filament_kg):
        got = uc.to_stock(db, filament_kg, D("5"), "LB")
        assert (got.quantity, got.unit, got.factor) == (D("2.267962"), "KG", D("0.45359237"))

    def test_c_five_boxes_of_twelve(self, db, screws):
        _item_unit(db, screws, "BOX", per_unit=D("12"))
        assert uc.to_stock(db, screws, D("5"), "BOX").quantity == D("60.000000")
        assert uc.unit_cost_to_stock(db, screws, D("24.00"), "BOX") == D("2.00000000")
        assert uc.from_stock(db, screws, D("60"), "BOX") == D("5.000000")

    def test_d_one_sheet_of_600_cm2(self, db, make_product):
        sheet = make_product(item_type="supply", unit="CM2", purchase_uom="SHEET")
        _item_unit(db, sheet, "SHEET", per_unit=D("600"))
        assert uc.to_stock(db, sheet, D("1"), "SHEET").quantity == D("600.000000")
        assert uc.to_stock(db, sheet, D("20"), "CM2").quantity == D("20.000000")
        assert uc.unit_cost_to_stock(db, sheet, D("12.00"), "SHEET") == D("0.02000000")

    def test_e_the_same_sheet_bought_by_the_square_metre(self, db, make_product):
        sheet = make_product(item_type="supply", unit="CM2", purchase_uom="M2")
        assert uc.to_stock(db, sheet, D("0.06"), "M2").quantity == D("600.000000")
        assert uc.unit_cost_to_stock(db, sheet, D("200.00"), "M2") == D("0.02000000")

    def test_f_two_litres_of_resin(self, db, make_product):
        resin = make_product(item_type="material", unit="ML", purchase_uom="L")
        assert uc.to_stock(db, resin, D("2"), "L").quantity == D("2000.000000")
        assert uc.unit_cost_to_stock(db, resin, D("30.00"), "L") == D("0.03000000")

    def test_g_sixteen_ounces_counted(self, db, filament_g):
        assert uc.to_stock(db, filament_g, D("16"), "OZ").quantity == D("453.592370")

    def test_h_a_box_with_no_size_is_refused(self, db, screws):
        with pytest.raises(uc.UnitConversionError) as refused:
            uc.to_stock(db, screws, D("5"), "BOX")
        assert "Set how many EA are in one BOX" in str(refused.value)

    def test_i_millilitres_of_gram_filament_are_refused(self, db, filament_g):
        with pytest.raises(uc.UnitConversionError):
            uc.to_stock(db, filament_g, D("1"), "ML")

    def test_j_250_grams_of_kg_stocked_filament(self, db, filament_kg):
        assert uc.to_stock(db, filament_kg, D("250"), "G").quantity == D("0.250000")

    def test_a_movement_out_is_negative(self, db, filament_g):
        assert uc.to_stock(db, filament_g, D("-0.25"), "KG").quantity == D("-250.000000")


class TestStockQuantity:
    def test_only_to_stock_can_make_one(self):
        with pytest.raises(TypeError):
            uc.StockQuantity(D("1"), "EA", D("1"), D("1"), "EA")

    def test_one_cannot_be_copied_with_another_value(self, db, filament_g):
        made = uc.to_stock(db, filament_g, D("3"), "KG")
        with pytest.raises(TypeError):
            dataclasses.replace(made, quantity=D("999"))
        with pytest.raises(AttributeError):
            made.quantity = D("999")
        assert made.quantity == D("3000.000000")

    def test_two_of_the_same_conversion_are_equal(self, db, filament_g):
        first, second = uc.to_stock(db, filament_g, D("3"), "KG"), uc.to_stock(db, filament_g, D("3"), "kg")
        assert first == second and hash(first) == hash(second)
        assert first != uc.to_stock(db, filament_g, D("3000"), "G")


class TestUnitsForItem:
    def test_a_gram_stocked_item_offers_the_weight_units(self, db, filament_g):
        units = {u.unit_code: u for u in uc.units_for_item(db, filament_g)}
        assert set(units) == {"G", "KG", "MG", "LB", "OZ"}
        assert units["G"].source == "stock" and units["G"].stock_units_per_unit == D("1")
        assert units["KG"].source == "table" and units["KG"].stock_units_per_unit == D("1000")
        assert units["KG"].is_purchase_unit and not units["G"].is_purchase_unit

    def test_an_item_unit_is_offered_with_its_size(self, db, screws):
        _item_unit(db, screws, "BOX", per_unit=D("12"))
        units = {u.unit_code: u for u in uc.units_for_item(db, screws)}
        assert set(units) == {"EA", "BOX"}
        assert units["BOX"].source == "item" and units["BOX"].stock_units_per_unit == D("12")
        assert units["BOX"].is_purchase_unit


class TestKnownUnits:
    def test_require_known_unit_tidies_and_returns_the_code(self, db):
        assert uc.require_known_unit(db, " kg ") == "KG"
        assert uc.require_known_unit(db, "pcs") == "EA"

    def test_require_known_unit_refuses_an_unknown_code(self, db):
        with pytest.raises(uc.UnitConversionError) as refused:
            uc.require_known_unit(db, "reel")
        assert "REEL" in str(refused.value)

    def test_unit_kind(self, db):
        assert uc.unit_kind(db, "lb") == "weight"
        assert uc.unit_kind(db, "BOX") == "pack"
        assert uc.unit_kind(db, "reel") is None


class TestConvertOrKeep:
    def test_it_converts_what_the_table_converts(self, db):
        assert uc.convert_or_keep(db, D("2"), "KG", "G") == (D("2000"), True)

    def test_the_same_unit_is_already_converted(self, db):
        assert uc.convert_or_keep(db, D("2"), "ea", "EA") == (D("2"), True)

    def test_it_hands_the_number_back_when_it_cannot(self, db):
        assert uc.convert_or_keep(db, D("2"), "BOX", "EA") == (D("2"), False)
        assert uc.convert_or_keep(db, D("2"), "ZORK", "G") == (D("2"), False)
