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

from app.models.bom import BOMLine
from app.models.purchase_order import PurchaseOrderLine
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
    """A state without the ids a projection cannot know."""
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


class TestUnitCodes:
    def test_item_codes_are_tidied(self, db, migration, make_product):
        gram = make_product(unit=" g ", purchase_uom="kg")
        each = make_product(unit="pcs", purchase_uom="Pack")
        _run(db, migration)
        assert (gram.unit, gram.purchase_uom) == ("G", "KG")
        assert (each.unit, each.purchase_uom) == ("EA", "PK")

    def test_an_unknown_code_is_listed_and_left(self, db, migration, make_product):
        odd = make_product(unit="widget", purchase_uom="widget")
        planned = _run(db, migration)
        assert (odd.unit, odd.purchase_uom) == ("widget", "widget")
        assert "with the unit 'widget', which is not in the unit table" in _report(migration, planned)

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

        def line(status):
            order = make_purchase_order(vendor_id=make_vendor().id, status=status)
            row = PurchaseOrderLine(
                purchase_order_id=order.id, line_number=1, product_id=item.id,
                quantity_ordered=D("1"), quantity_received=D("0"), purchase_unit="kg",
                unit_cost=D("20"), line_total=D("20"),
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            )
            db.add(row)
            db.flush()
            return row

        still_open, closed = line("ordered"), line("received")
        _run(db, migration)
        assert (still_open.purchase_unit, closed.purchase_unit) == ("KG", "kg")


class TestShape:
    def test_a_second_run_changes_nothing(self, db, migration, make_product):
        _unit_table(db, _EXAMPLE_DATA_UNITS)
        make_product(unit="pcs")
        _run(db, migration)
        again = _run(db, migration)
        assert migration.report_lines(again) == [
            (logging.INFO, "106: the unit table and unit codes needed no change")
        ]

    def test_the_projection_is_what_the_database_holds_afterwards(self, db, migration, make_product, make_bom):
        ids = _unit_table(db, _EXAMPLE_DATA_UNITS + [("kg", "weight", None, "1")])
        db.add(UnitOfMeasure(code="BOX", name="Box", symbol="box", uom_class="quantity",
                             base_unit_id=ids["EA"], to_base_factor=D("12")))
        made, part = make_product(unit="pcs"), make_product(unit=" g ", purchase_uom="widget")
        make_bom(product_id=made.id, lines=[{"component_id": part.id, "quantity": D("5"), "unit": "Kg"}])
        db.flush()

        bind = db.connection()
        before = migration.read_state(bind)
        planned = migration.plan(before)
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
