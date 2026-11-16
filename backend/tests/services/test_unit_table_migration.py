"""
Migration 106: the standard units with exact factors, and unit codes tidied.

The migration's functions take a connection, so they are run here against real
rows inside the test transaction. The test database starts with the standard
units already in it, so a test that needs an older table empties it first.
"""
import importlib.util
import logging
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models.bom import BOMLine
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.product_unit import ProductUnit
from app.models.production_order import ProductionOrderOperation, ProductionOrderOperationMaterial
from app.models.purchase_order import PurchaseOrderLine
from app.models.purchase_order_document import VendorItem
from app.models.uom import UnitOfMeasure
from app.services import unit_conversion as uc

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "106_unit_table_and_item_units.py"
)

# What the setup wizard's example data has written until now.
_EXAMPLE_DATA_UNITS = [
    ("EA", "quantity", None, "1"), ("KG", "weight", None, "1"), ("M", "length", None, "1"),
    ("HR", "time", None, "1"), ("G", "weight", "KG", "0.001"), ("LB", "weight", "KG", "0.453592"),
    ("OZ", "weight", "KG", "0.0283495"), ("CM", "length", "M", "0.01"), ("MM", "length", "M", "0.001"),
    ("FT", "length", "M", "0.3048"), ("IN", "length", "M", "0.0254"), ("MIN", "time", "HR", "0.01666667"),
]


@pytest.fixture(scope="module")
def migration():
    """Load migration 106 as a module."""
    spec = importlib.util.spec_from_file_location("migration_106", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _unit_table(db, rows):
    """Replace the unit table with ``(code, kind, base code, factor)`` rows."""
    db.query(UnitOfMeasure).delete()
    db.flush()
    ids = {}
    for code, kind, base, factor in rows:
        row = UnitOfMeasure(code=code, name=code, symbol=code.lower(), uom_class=kind,
                            base_unit_id=ids.get(base), to_base_factor=D(factor))
        db.add(row)
        db.flush()
        ids[code] = row.id
    return ids


def _run(db, migration):
    """Plan and apply the way upgrade() does, and return the plan."""
    db.flush()
    bind = db.connection()
    planned = migration.plan(migration.read_state(bind))
    migration.apply(bind, planned)
    db.expire_all()
    uc.forget_units(db)
    return planned


def _units(db):
    return {u.code: u for u in db.query(UnitOfMeasure).all()}


def _report(migration, planned):
    return "\n".join(line for _level, line in migration.report_lines(planned))


def _comparable(state):
    """A state without the ids a projection cannot know. A unit's base is compared by its code."""
    return {
        key: sorted(
            ({k: v for k, v in row.items() if k not in ("id", "base_unit_id")} for row in rows),
            key=lambda row: sorted((k, str(v)) for k, v in row.items()),
        )
        for key, rows in state.items()
    }


class TestFrozenCopies:
    def test_the_units_match_the_module(self, migration):
        frozen = [(c, n, s, k, b, D(f)) for c, n, s, k, b, f in migration._STANDARD_UNITS]
        assert frozen == [tuple(unit) for unit in uc.STANDARD_UNITS]

    def test_the_spellings_match_the_module(self, migration):
        assert migration._SPELLINGS == uc.UNIT_SPELLINGS
        assert migration.tidy_code(" Packs ") == uc.normalize_unit_code(" Packs ") == "PK"


class TestUnitTable:
    def test_an_empty_table_gets_all_27(self, db, migration):
        _unit_table(db, [])
        planned = _run(db, migration)
        units = _units(db)
        assert len(units) == 27
        assert D(str(units["OZ"].to_base_factor)) == D("0.028349523125")
        assert units["G"].base_unit_id == units["KG"].id
        assert units["BOX"].uom_class == "pack" and units["BOX"].base_unit_id is None
        assert "added 27 standard unit(s)" in _report(migration, planned)

    def test_the_example_data_table_is_made_exact(self, db, migration):
        _unit_table(db, _EXAMPLE_DATA_UNITS)
        planned = _run(db, migration)
        units = _units(db)
        assert len(units) == 27
        assert D(str(units["LB"].to_base_factor)) == D("0.45359237")
        assert D(str(units["OZ"].to_base_factor)) == D("0.028349523125")
        assert uc.physical_factor(db, "LB", "G") == D("453.59237")
        report = _report(migration, planned)
        assert "LB factor made exact: 0.453592 -> 0.45359237" in report
        assert "added 15 standard unit(s)" in report

    def test_minutes_are_left_as_the_install_has_them(self, db, migration):
        _unit_table(db, _EXAMPLE_DATA_UNITS)
        _run(db, migration)
        assert D(str(_units(db)["MIN"].to_base_factor)) == D("0.01666667")

    def test_a_unit_the_install_added_is_kept(self, db, migration):
        ids = _unit_table(db, _EXAMPLE_DATA_UNITS)
        db.add(UnitOfMeasure(code="YD", name="Yard", symbol="yd", uom_class="length",
                             base_unit_id=ids["M"], to_base_factor=D("0.9144")))
        _run(db, migration)
        assert D(str(_units(db)["YD"].to_base_factor)) == D("0.9144")

    def test_a_pack_filed_as_a_counting_unit_is_left_and_listed(self, db, migration):
        ids = _unit_table(db, _EXAMPLE_DATA_UNITS)
        db.add(UnitOfMeasure(code="BOX", name="Box", symbol="box", uom_class="quantity",
                             base_unit_id=ids["EA"], to_base_factor=D("12")))
        planned = _run(db, migration)
        box = _units(db)["BOX"]
        assert (box.uom_class, D(str(box.to_base_factor))) == ("quantity", D("12"))
        assert uc.physical_factor(db, "BOX", "EA") == D("12")
        assert "LEFT unit BOX: this install has it as a quantity unit (factor 12)" in _report(migration, planned)

    def test_a_standard_code_filed_under_another_kind_is_left_and_listed(self, db, migration):
        rows = [row for row in _EXAMPLE_DATA_UNITS if row[0] != "OZ"]
        _unit_table(db, rows + [("L", "volume", None, "1"), ("OZ", "volume", "L", "0.0295735")])
        planned = _run(db, migration)
        ounce = _units(db)["OZ"]
        assert (ounce.uom_class, D(str(ounce.to_base_factor))) == ("volume", D("0.0295735"))
        assert "LEFT unit OZ: this install has it as a volume unit" in _report(migration, planned)

    def test_two_spellings_keep_the_upper_case_row(self, db, migration):
        _unit_table(db, _EXAMPLE_DATA_UNITS + [("kg", "weight", None, "1")])
        planned = _run(db, migration)
        units = _units(db)
        assert units["KG"].active is True and units["kg"].active is False
        assert "unit 'kg' is the same code as KG and was switched off" in _report(migration, planned)

    def test_a_lone_lower_case_code_is_rewritten(self, db, migration):
        rows = [row for row in _EXAMPLE_DATA_UNITS if row[0] != "CM"]
        _unit_table(db, rows + [("cm", "length", "M", "0.01")])
        _run(db, migration)
        units = _units(db)
        assert "cm" not in units and units["CM"].active is True

    def test_a_standard_unit_that_was_switched_off_is_switched_on(self, db, migration):
        _unit_table(db, _EXAMPLE_DATA_UNITS)
        db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "LB").update({"active": False})
        planned = _run(db, migration)
        assert _units(db)["LB"].active is True
        assert "standard unit LB was switched off and is switched on again" in _report(migration, planned)

    def test_hours_and_minutes_are_never_changed(self, db, migration):
        _unit_table(db, _EXAMPLE_DATA_UNITS)
        db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "HR").update({"active": False})
        _run(db, migration)
        assert _units(db)["HR"].active is False

    def test_a_table_measured_from_another_base_is_left_and_listed(self, db, migration):
        """Grams as the base and a kilogram of 1000: rebasing them would break the install's own units."""
        _unit_table(db, [("EA", "quantity", None, "1"), ("G", "weight", None, "1"),
                         ("KG", "weight", "G", "1000"), ("TONNE", "weight", "G", "1000000")])
        planned = _run(db, migration)
        units = _units(db)
        assert D(str(units["G"].to_base_factor)) == D("1")
        assert D(str(units["KG"].to_base_factor)) == D("1000")
        assert D(str(units["TONNE"].to_base_factor)) == D("1000000")
        assert uc.physical_factor(db, "TONNE", "KG") == D("1000")
        report = _report(migration, planned)
        assert "LEFT unit KG: its factor 1000 is not a rounding of the exact 1" in report
        # A standard pound beside those rows would make 1 LB convert to 0.45 G.
        assert not {"LB", "OZ", "MG"} & set(units)
        assert "NOT ADDED MG, LB, OZ: this install measures weight from another base unit" in report
        with pytest.raises(uc.UnitConversionError):
            uc.physical_factor(db, "LB", "G")
        # The other kinds are filled as usual.
        assert {"M", "CM2", "ML", "BOX"} <= set(units)

    def test_another_base_is_seen_when_the_row_in_use_is_a_second_spelling(self, db, migration):
        """An active kg of 1000 beside a switched-off KG of 1: the row in use decides."""
        _unit_table(db, [("EA", "quantity", None, "1"), ("kg", "weight", None, "1000")])
        db.add(UnitOfMeasure(code="KG", name="Old kilogram", symbol="kg", uom_class="weight",
                             to_base_factor=D("1"), active=False))
        planned = _run(db, migration)
        units = _units(db)
        assert not {"G", "MG", "LB", "OZ"} & set(units)
        assert D(str(units["kg"].to_base_factor)) == D("1000") and units["KG"].active is False
        assert "NOT ADDED G, MG, LB, OZ: this install measures weight from another base unit" in _report(
            migration, planned)

    def test_nothing_is_hung_on_a_base_unit_filed_under_another_kind(self, db, migration):
        """KG as a counting unit: a gram added with KG as its base could never convert to it."""
        _unit_table(db, [("EA", "quantity", None, "1"), ("KG", "quantity", "EA", "1")])
        planned = _run(db, migration)
        units = _units(db)
        assert units["KG"].uom_class == "quantity"
        assert not {"G", "MG", "LB", "OZ"} & set(units)
        assert {"M", "CM", "L", "ML", "BOX"} <= set(units)
        report = _report(migration, planned)
        assert "LEFT unit KG: this install has it as a quantity unit" in report
        assert "NOT ADDED G, MG, LB, OZ: their base unit KG is filed here under another kind" in report

    def test_an_hour_is_not_added_beside_a_minute_on_its_own_scale(self, db, migration):
        """A minute of 1 is this install's base for time: an hour of 1 beside it would equal a minute."""
        _unit_table(db, [("EA", "quantity", None, "1"), ("MIN", "time", None, "1")])
        planned = _run(db, migration)
        units = _units(db)
        assert "HR" not in units
        assert D(str(units["MIN"].to_base_factor)) == D("1")
        report = _report(migration, planned)
        assert "LEFT unit MIN: its factor 1 is not a rounding of the exact 0.016666666666667" in report
        assert "NOT ADDED HR: this install measures time from another base unit" in report

    def test_a_missing_minute_is_added_beside_a_standard_hour(self, db, migration):
        _unit_table(db, [("EA", "quantity", None, "1"), ("HR", "time", None, "1")])
        _run(db, migration)
        assert uc.physical_factor(db, "HR", "MIN").quantize(D("0.001")) == D("60.000")

    def test_standard_units_are_not_added_to_a_kind_of_the_installs_own_units(self, db, migration):
        """Only a TONNE of 1 under weight: nothing says what one TONNE is in KG, so no KG of 1 is put beside it."""
        _unit_table(db, [("EA", "quantity", None, "1"), ("TONNE", "weight", None, "1")])
        planned = _run(db, migration)
        units = _units(db)
        assert not {"KG", "G", "MG", "LB", "OZ"} & set(units)
        assert D(str(units["TONNE"].to_base_factor)) == D("1")
        assert {"M", "CM", "L", "ML", "HR", "BOX"} <= set(units)
        assert (
            "NOT ADDED KG, G, MG, LB, OZ: the weight units here are this install's own (TONNE)"
            in _report(migration, planned)
        )

    def test_a_standard_unit_filed_under_another_kind_does_not_stand_in_for_that_kind(self, db, migration):
        """OZ filed as the only volume unit: its factor says nothing about litres."""
        _unit_table(db, [("EA", "quantity", None, "1"), ("OZ", "volume", None, "1")])
        planned = _run(db, migration)
        units = _units(db)
        assert not {"L", "ML"} & set(units)
        assert "NOT ADDED L, ML: the volume units here are this install's own (OZ)" in _report(migration, planned)

    def test_each_is_not_assumed_beside_the_installs_own_counting_units(self, db, migration):
        """Only a DOZEN of 1: an EA of 1 beside it would make a dozen convert to one each."""
        _unit_table(db, [("DOZEN", "quantity", None, "1")])
        planned = _run(db, migration)
        units = _units(db)
        assert "EA" not in units
        assert D(str(units["DOZEN"].to_base_factor)) == D("1")
        with pytest.raises(uc.UnitConversionError):
            uc.physical_factor(db, "DOZEN", "EA")
        report = _report(migration, planned)
        assert "NOT ADDED EA: the counting units here are this install's own (DOZEN)" in report
        assert "add EA under Units" in report

    def test_each_is_added_to_a_table_with_no_counting_units(self, db, migration):
        _unit_table(db, [("KG", "weight", None, "1")])
        _run(db, migration)
        assert _units(db)["EA"].active is True

    def test_a_switched_off_spelling_does_not_speak_for_a_code_that_has_a_row_in_use(self, db, migration):
        """An active KG filed as a pack beside a switched-off kg of weight: conversions use the pack row."""
        _unit_table(db, [("EA", "quantity", None, "1"), ("KG", "pack", None, "1")])
        db.add(UnitOfMeasure(code="kg", name="Old kilogram", symbol="kg", uom_class="weight",
                             to_base_factor=D("1"), active=False))
        planned = _run(db, migration)
        units = _units(db)
        assert not {"G", "MG", "LB", "OZ"} & set(units)
        assert units["KG"].uom_class == "pack" and units["kg"].active is False
        assert "LEFT unit KG: this install has it as a pack unit" in _report(migration, planned)

    def test_a_rounded_factor_in_a_kind_on_another_base_is_not_corrected(self, db, migration):
        _unit_table(db, [("EA", "quantity", None, "1"), ("G", "weight", None, "1"),
                         ("KG", "weight", "G", "1000"), ("LB", "weight", "G", "0.453592")])
        _run(db, migration)
        assert D(str(_units(db)["LB"].to_base_factor)) == D("0.453592")

    def test_a_switched_off_standard_row_in_lower_case_is_renamed_and_switched_on(self, db, migration):
        """Otherwise the units added after it would find no base, and a second run would rename it."""
        _unit_table(db, [("EA", "quantity", None, "1"), ("kg", "weight", None, "1")])
        db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "kg").update({"active": False})
        first = _run(db, migration)
        units = _units(db)
        assert "kg" not in units and units["KG"].active is True
        assert units["G"].base_unit_id == units["KG"].id
        assert units["LB"].base_unit_id == units["KG"].id
        assert migration.changes(first) > 0
        assert migration.changes(_run(db, migration)) == 0

    def test_the_row_in_use_is_kept_when_the_upper_case_row_is_switched_off(self, db, migration, make_product):
        ids = _unit_table(db, _EXAMPLE_DATA_UNITS + [("yd", "length", "M", "0.9144")])
        db.add(UnitOfMeasure(code="YD", name="Old yard", symbol="yd", uom_class="length",
                             base_unit_id=ids["M"], to_base_factor=D("1"), active=False))
        cloth = make_product(unit="yd")
        planned = _run(db, migration)
        units = _units(db)
        assert units["yd"].active is True and units["YD"].active is False
        assert cloth.unit == "YD"
        assert uc.physical_factor(db, "YD", "M") == D("0.9144")
        assert "LEFT unit YD: the row in use is spelled 'yd'" in _report(migration, planned)

    def test_an_installs_own_unit_named_like_a_spelling_is_kept(self, db, migration, make_product):
        """An install with its own PACK unit of 12 keeps it; ``pack`` is not rewritten to PK."""
        ids = _unit_table(db, _EXAMPLE_DATA_UNITS)
        db.add(UnitOfMeasure(code="PACK", name="Pack", symbol="pack", uom_class="quantity",
                             base_unit_id=ids["EA"], to_base_factor=D("12")))
        washers = make_product(unit="EA", purchase_uom="pack")
        _run(db, migration)
        assert washers.purchase_uom == "PACK"
        assert uc.physical_factor(db, washers.purchase_uom, "EA") == D("12")

    def test_an_installs_own_unit_that_is_switched_off_is_listed_not_rewritten(self, db, migration, make_product):
        """A switched-off PACK is still that install's unit. Items in it are not moved onto PK."""
        ids = _unit_table(db, _EXAMPLE_DATA_UNITS)
        db.add(UnitOfMeasure(code="PACK", name="Pack", symbol="pack", uom_class="quantity",
                             base_unit_id=ids["EA"], to_base_factor=D("12"), active=False))
        washers = make_product(unit="EA", purchase_uom="pack")
        planned = _run(db, migration)
        assert washers.purchase_uom == "pack"
        report = _report(migration, planned)
        assert "item(s) with the purchase unit 'pack', which is switched off in the unit table" in report
        assert washers.sku in report


class TestUnitCodes:
    def test_item_codes_are_tidied(self, db, migration, make_product):
        gram = make_product(unit=" g ", purchase_uom="kg")
        each = make_product(unit="pcs", purchase_uom="Pack")
        _run(db, migration)
        assert (gram.unit, gram.purchase_uom) == ("G", "KG")
        assert (each.unit, each.purchase_uom) == ("EA", "PK")

    def test_an_unknown_code_is_listed_with_its_item_and_left(self, db, migration, make_product):
        odd = make_product(unit="widget", purchase_uom="widget")
        planned = _run(db, migration)
        assert (odd.unit, odd.purchase_uom) == ("widget", "widget")
        lines = [line for line in _report(migration, planned).splitlines() if "'widget'" in line]
        assert any("item(s) with the stock unit 'widget', which is not in the unit table" in line
                   and odd.sku in line for line in lines)
        assert any("item(s) with the purchase unit 'widget'" in line and odd.sku in line for line in lines)

    def test_a_code_whose_unit_is_switched_off_says_so(self, db, migration, make_product):
        ids = _unit_table(db, _EXAMPLE_DATA_UNITS)
        db.add(UnitOfMeasure(code="REEL", name="Reel", symbol="reel", uom_class="length",
                             base_unit_id=ids["M"], to_base_factor=D("50"), active=False))
        wire = make_product(unit="reel")
        planned = _run(db, migration)
        assert wire.unit == "reel"
        assert "'reel', which is switched off in the unit table" in _report(migration, planned)

    def test_more_rows_than_fit_are_counted_not_dropped(self, migration):
        names = [f"SKU-{number}" for number in range(40)]
        planned = {"units": {name: [] for name in (
            "add", "fix", "reactivate", "rename", "switch_off", "conflicts", "odd_factors", "spellings_left",
            "not_added")},
            "codes": [], "unknown": {("items", "unit", "zz"): {"off": False, "rows": names}},
            "no_unit": [], "no_purchase_unit": []}
        line = migration.report_lines(planned)[0][1]
        assert "LEFT 40 item(s)" in line and "SKU-24" in line and "SKU-25" not in line and "and 15 more" in line

    def test_an_item_with_no_unit_gets_each(self, db, migration, make_product):
        blank = make_product()
        db.execute(text("UPDATE products SET unit = NULL, purchase_uom = NULL WHERE id = :id"), {"id": blank.id})
        planned = _run(db, migration)
        assert (blank.unit, blank.purchase_uom) == ("EA", "EA")
        assert f"item {blank.sku} had no unit and is set to EA" in _report(migration, planned)

    def test_an_item_with_no_purchase_unit_gets_its_stock_unit(self, db, migration, make_product):
        gram = make_product(unit="G")
        db.execute(text("UPDATE products SET purchase_uom = '  ' WHERE id = :id"), {"id": gram.id})
        _run(db, migration)
        assert gram.purchase_uom == "G"

    def test_bom_line_codes_are_tidied(self, db, migration, make_product, make_bom):
        made, part = make_product(), make_product(item_type="material", unit="G")
        bom = make_bom(product_id=made.id, lines=[{"component_id": part.id, "quantity": D("50"), "unit": "grams"}])
        _run(db, migration)
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        assert (line.unit, line.quantity) == ("G", D("50"))

    def test_only_open_purchase_order_lines_are_tidied(self, db, migration, make_product, make_vendor,
                                                       make_purchase_order):
        item = make_product(unit="G", purchase_uom="KG")

        def line(status, unit="kg", number=1):
            order = make_purchase_order(vendor_id=make_vendor().id, status=status)
            row = PurchaseOrderLine(
                purchase_order_id=order.id, line_number=number, product_id=item.id,
                quantity_ordered=D("1"), quantity_received=D("0"), purchase_unit=unit,
                unit_cost=D("20"), line_total=D("20"),
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.flush()
            return order, row

        (_, still_open), (_, closed) = line("ordered"), line("received")
        odd_order, odd = line("ordered", unit="zz", number=7)
        planned = _run(db, migration)
        assert (still_open.purchase_unit, closed.purchase_unit) == ("KG", "kg")
        # A line left alone is named by its order and its line number, not its row id.
        assert odd.purchase_unit == "zz"
        assert f"{odd_order.po_number} line 7" in _report(migration, planned)

    def test_routing_material_codes_are_tidied(self, db, migration, make_product, make_work_center):
        made, part = make_product(), make_product(item_type="material", unit="G")
        routing = Routing(product_id=made.id, code=f"RT-{made.id}", name="Routing", is_active=True)
        db.add(routing)
        db.flush()
        step = RoutingOperation(routing_id=routing.id, work_center_id=make_work_center().id, operation_code="PRINT",
                                operation_name="Print", sequence=10, run_time_minutes=D("30"))
        db.add(step)
        db.flush()
        material = RoutingOperationMaterial(routing_operation_id=step.id, component_id=part.id,
                                            quantity=D("37"), unit="kg", scrap_factor=D("0"))
        db.add(material)
        _run(db, migration)
        assert (material.unit, material.quantity) == ("KG", D("37"))

    def test_vendor_item_codes_are_tidied(self, db, migration, make_product, make_vendor):
        item = make_product()
        listing = VendorItem(vendor_id=make_vendor().id, vendor_sku=f"V-{item.id}", product_id=item.id,
                             default_purchase_unit="pcs")
        db.add(listing)
        _run(db, migration)
        assert listing.default_purchase_unit == "EA"

    def test_only_material_rows_not_yet_consumed_are_tidied(self, db, migration, make_product,
                                                            make_production_order, make_work_center):
        made, part = make_product(), make_product(item_type="material", unit="G")
        order = make_production_order(product_id=made.id, quantity=1)
        step = ProductionOrderOperation(
            production_order_id=order.id, routing_operation_id=None, work_center_id=make_work_center().id,
            sequence=10, operation_code="PRINT", operation_name="Print",
            planned_setup_minutes=D("0"), planned_run_minutes=D("10"), status="pending",
        )
        db.add(step)
        db.flush()
        rows = {}
        for status in ("pending", "allocated", "error", "consumed", "returned"):
            rows[status] = ProductionOrderOperationMaterial(
                production_order_operation_id=step.id, component_id=part.id,
                quantity_required=D("50"), unit="g", status=status,
            )
            db.add(rows[status])
        _run(db, migration)
        assert {status: row.unit for status, row in rows.items()} == {
            "pending": "G", "allocated": "G", "error": "G", "consumed": "g", "returned": "g",
        }


class TestItemUnitTable:
    """The table the model builds, which the migration creates with the same constraints."""

    def _refused(self, db, product, **values):
        with pytest.raises(IntegrityError):
            with db.begin_nested():
                db.add(ProductUnit(product_id=product.id, **values))
                db.flush()

    def test_a_size_either_way_round_is_accepted(self, db, make_product):
        item = make_product()
        db.add(ProductUnit(product_id=item.id, unit_code="BOX", stock_units_per_unit=D("12")))
        db.add(ProductUnit(product_id=item.id, unit_code="G", units_per_stock_unit=D("750")))
        db.flush()

    def test_both_sizes_or_neither_are_refused(self, db, make_product):
        item = make_product()
        self._refused(db, item, unit_code="BOX", stock_units_per_unit=D("12"), units_per_stock_unit=D("1"))
        self._refused(db, item, unit_code="BOX")

    def test_a_size_of_zero_is_refused(self, db, make_product):
        self._refused(db, make_product(), unit_code="BOX", stock_units_per_unit=D("0"))

    def test_a_code_that_is_not_tidy_is_refused(self, db, make_product):
        item = make_product()
        self._refused(db, item, unit_code="box", stock_units_per_unit=D("12"))
        self._refused(db, item, unit_code=" BOX", stock_units_per_unit=D("12"))

    def test_a_second_row_for_the_same_unit_is_refused(self, db, make_product):
        item = make_product()
        db.add(ProductUnit(product_id=item.id, unit_code="BOX", stock_units_per_unit=D("12")))
        db.flush()
        self._refused(db, item, unit_code="BOX", stock_units_per_unit=D("10"))

    def test_the_migration_creates_the_same_constraints(self, db, migration):
        """Names the model declares, checked against the migration's own text."""
        source = _MIGRATION_PATH.read_text(encoding="utf-8")
        for constraint in ProductUnit.__table__.constraints:
            if constraint.name:
                assert constraint.name in source, constraint.name


class TestShape:
    def test_a_second_run_changes_nothing(self, db, migration, make_product):
        _unit_table(db, _EXAMPLE_DATA_UNITS)
        make_product(unit="pcs")
        make_product(unit="widget")
        first = _run(db, migration)
        assert migration.changes(first) > 0
        again = _run(db, migration)
        # A code that is left is listed again; nothing is written.
        assert migration.changes(again) == 0

    def test_nothing_to_do_says_so(self, migration):
        empty = {"units": {name: [] for name in (
            "add", "fix", "reactivate", "rename", "switch_off", "conflicts", "odd_factors", "spellings_left",
            "not_added")},
            "codes": [], "unknown": {}, "no_unit": [], "no_purchase_unit": []}
        assert migration.report_lines(empty) == [
            (logging.INFO, "106: the unit table and unit codes needed no change")
        ]

    def test_the_projection_is_what_the_database_holds_afterwards(self, db, migration, make_product, make_bom):
        """Every kind of change the plan can hold goes through the comparison."""
        rows = [row for row in _EXAMPLE_DATA_UNITS if row[0] != "CM"]
        ids = _unit_table(db, rows + [("kg", "weight", None, "1"), ("cm", "length", "M", "0.01")])
        db.add(UnitOfMeasure(code="BOX", name="Box", symbol="box", uom_class="quantity",
                             base_unit_id=ids["EA"], to_base_factor=D("12")))
        db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "LB").update({"active": False})
        made, part = make_product(unit="pcs"), make_product(unit=" g ", purchase_uom="widget")
        blank, half = make_product(), make_product(unit="G")
        db.execute(text("UPDATE products SET unit = NULL, purchase_uom = NULL WHERE id = :id"), {"id": blank.id})
        db.execute(text("UPDATE products SET purchase_uom = '' WHERE id = :id"), {"id": half.id})
        make_bom(product_id=made.id, lines=[{"component_id": part.id, "quantity": D("5"), "unit": "Kg"}])
        db.flush()

        bind = db.connection()
        before = migration.read_state(bind)
        planned = migration.plan(before)
        for name in ("add", "fix", "reactivate", "rename", "switch_off", "conflicts"):
            assert planned["units"][name], name
        assert planned["codes"] and planned["unknown"] and planned["no_unit"] and planned["no_purchase_unit"]
        projected = migration.project(before, planned)
        migration.apply(bind, planned)

        assert _comparable(projected) == _comparable(migration.read_state(bind))

    def test_planning_writes_nothing(self, db, migration, make_product):
        _unit_table(db, _EXAMPLE_DATA_UNITS)
        item = make_product(unit="pcs")
        db.flush()
        bind = db.connection()
        state = migration.read_state(bind)
        migration.project(state, migration.plan(state))
        db.expire_all()
        assert item.unit == "pcs"
        assert D(str(_units(db)["LB"].to_base_factor)) == D("0.453592")
