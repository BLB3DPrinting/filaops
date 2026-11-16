"""
Migration 107: purchase units, item units and line units settled.

The migration's functions take a connection, so they are run here against real
rows inside the test transaction. The test database already holds the standard
units, which is what migration 106 leaves.
"""
import importlib.util
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from app.models.bom import BOMLine
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.product_unit import ProductUnit
from app.models.production_order import ProductionOrderOperation, ProductionOrderOperationMaterial
from app.models.purchase_order import PurchaseOrderLine
from app.models.uom import UnitOfMeasure
from app.services import unit_conversion as uc

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "107_settle_item_and_line_units.py"
)


@pytest.fixture(scope="module")
def migration():
    """Load migration 107 as a module."""
    spec = importlib.util.spec_from_file_location("migration_107", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db, migration):
    """Plan and apply the way upgrade() does, and return the plan."""
    db.flush()
    bind = db.connection()
    planned = migration.plan(migration.read_state(bind))
    migration.apply(bind, planned)
    db.expire_all()
    return planned


def _report(migration, planned):
    return "\n".join(line for _level, line in migration.report_lines(planned))


def _lines_about(migration, planned, *words):
    """The report lines that hold every one of ``words``."""
    return [line for _level, line in migration.report_lines(planned) if all(word in line for word in words)]


def _item_units(db, item):
    return {
        row.unit_code: (row.stock_units_per_unit, row.units_per_stock_unit)
        for row in db.query(ProductUnit).filter(ProductUnit.product_id == item.id)
    }


def _comparable(state):
    """A state without the ids a projection cannot know."""
    return {
        key: sorted(
            ({k: v for k, v in row.items() if k not in ("id", "base_unit_id")} for row in rows),
            key=lambda row: sorted((k, str(v)) for k, v in row.items()),
        )
        for key, rows in state.items()
    }


@pytest.fixture
def filament(make_product):
    """Gram-stocked filament the way the item form saved it: bought by the EA, size 1000."""
    def _make(**values):
        values = {"item_type": "material", "unit": "G", "purchase_uom": "EA", "purchase_factor": D("1000"), **values}
        return make_product(**values)
    return _make


@pytest.fixture
def routing_material(db, make_product, make_work_center):
    """A routing material line for ``component``."""
    def _make(component, quantity="37", unit="EA"):
        made = make_product()
        routing = Routing(product_id=made.id, code=f"RT-{made.id}", name="Routing", is_active=True)
        db.add(routing)
        db.flush()
        step = RoutingOperation(routing_id=routing.id, work_center_id=make_work_center().id, operation_code="PRINT",
                                operation_name="Print", sequence=10, run_time_minutes=D("30"))
        db.add(step)
        db.flush()
        material = RoutingOperationMaterial(routing_operation_id=step.id, component_id=component.id,
                                            quantity=D(quantity), unit=unit, scrap_factor=D("0"))
        db.add(material)
        db.flush()
        return routing, material
    return _make


@pytest.fixture
def order_rows(db, make_product, make_production_order, make_work_center):
    """One production order material row per status, for ``component``."""
    def _make(component, statuses, unit="EA", quantity="50"):
        order = make_production_order(product_id=make_product().id, quantity=1)
        step = ProductionOrderOperation(
            production_order_id=order.id, routing_operation_id=None, work_center_id=make_work_center().id,
            sequence=10, operation_code="PRINT", operation_name="Print",
            planned_setup_minutes=D("0"), planned_run_minutes=D("10"), status="pending",
        )
        db.add(step)
        db.flush()
        rows = {}
        for status in statuses:
            rows[status] = ProductionOrderOperationMaterial(
                production_order_operation_id=step.id, component_id=component.id,
                quantity_required=D(quantity), unit=unit, status=status,
            )
            db.add(rows[status])
        db.flush()
        return order, rows
    return _make


def _bom_line(db, make_product, make_bom, component, quantity="50", unit="EA"):
    bom = make_bom(product_id=make_product().id,
                   lines=[{"component_id": component.id, "quantity": D(quantity), "unit": unit}])
    return bom, db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()


class TestFrozenCopies:
    def test_the_spellings_match_the_module(self, migration):
        assert migration._SPELLINGS == uc.UNIT_SPELLINGS

    def test_the_pack_kind_matches_the_module(self, migration):
        assert migration._PACK == uc.PACK


class TestPurchaseUnits:
    def test_gram_filament_bought_by_the_each_of_1000_becomes_kg(self, db, migration, filament):
        item = filament()
        planned = _run(db, migration)
        assert (item.unit, item.purchase_uom, item.purchase_factor) == ("G", "KG", D("1000"))
        assert _item_units(db, item) == {}
        assert _lines_about(migration, planned, "purchase unit EA -> KG", item.sku)

    def test_a_supply_linked_to_a_material_type_counts_as_a_material(self, db, migration, filament):
        """The test for a material is the one the code uses today: the item type, or a material type."""
        from app.models.material import MaterialType

        kind = MaterialType(code=f"MT-{uuid.uuid4().hex[:12]}", name="Test PLA",
                            base_material="PLA", density=D("1.24"), base_price_per_kg=D("20"))
        db.add(kind)
        db.flush()
        item = filament(item_type="supply", material_type_id=kind.id)
        _run(db, migration)
        assert item.purchase_uom == "KG"

    def test_the_ones_migration_105_left_are_marked(self, db, migration, filament, make_vendor,
                                                    make_purchase_order):
        """105 changed only materials whose purchase orders were in KG and never in EA."""
        never_bought, bought_by_the_each, bought_by_the_kilo = filament(), filament(), filament()

        def line(item, unit, status="received"):
            order = make_purchase_order(vendor_id=make_vendor().id, status=status)
            db.add(PurchaseOrderLine(
                purchase_order_id=order.id, line_number=1, product_id=item.id,
                quantity_ordered=D("1"), quantity_received=D("0"), purchase_unit=unit,
                unit_cost=D("20"), line_total=D("20"),
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
            ))
            db.flush()
            return order

        line(bought_by_the_each, "EA")
        line(bought_by_the_kilo, "KG")
        planned = _run(db, migration)

        assert {item.purchase_uom for item in (never_bought, bought_by_the_each, bought_by_the_kilo)} == {"KG"}
        marked = {sku: reason for _id, sku, reason in planned["purchase_units"]}
        assert marked[never_bought.sku] == "no_kg_lines"
        assert marked[bought_by_the_each.sku] == "ea_lines"
        assert marked[bought_by_the_kilo.sku] is None
        report = _report(migration, planned)
        assert "migration 105 left" in report

    def test_an_open_purchase_order_line_in_ea_on_gram_filament_is_left_and_listed(
            self, db, migration, filament, make_vendor, make_purchase_order):
        item = filament()
        order = make_purchase_order(vendor_id=make_vendor().id, status="ordered")
        line = PurchaseOrderLine(
            purchase_order_id=order.id, line_number=3, product_id=item.id,
            quantity_ordered=D("2"), quantity_received=D("0"), purchase_unit="EA",
            unit_cost=D("20"), line_total=D("40"),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        db.add(line)
        planned = _run(db, migration)
        assert line.purchase_unit == "EA"
        assert _lines_about(migration, planned, "LEFT", f"{order.po_number} line 3", "receiving refuses")

    def test_filament_of_another_size_is_not_given_kg(self, db, migration, filament):
        item = filament(purchase_factor=D("750"))
        _run(db, migration)
        assert item.purchase_uom == "EA"

    def test_a_part_stocked_in_grams_is_not_a_material(self, db, migration, make_product):
        item = make_product(item_type="component", unit="G", purchase_uom="EA", purchase_factor=D("1000"))
        _run(db, migration)
        assert item.purchase_uom == "EA"


class TestItemUnits:
    def test_gram_filament_bought_by_the_each_of_750_gets_each_as_its_own_unit(self, db, migration, filament):
        item = filament(purchase_factor=D("750"))
        _run(db, migration)
        assert _item_units(db, item) == {"EA": (D("750"), None)}
        assert uc.stock_units_per(db, item, "EA") == D("750")

    def test_a_pack_of_12_gets_a_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {"BOX": (D("12"), None)}
        assert _lines_about(migration, planned, "1 BOX = 12 EA", item.sku)

    def test_a_purchase_unit_the_table_converts_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="supply", unit="G", purchase_uom="KG", purchase_factor=D("1000"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        assert item.sku not in _report(migration, planned)

    def test_a_size_of_one_is_listed_and_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("1"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        assert _lines_about(migration, planned, "NO SIZE", "a size of 1", item.sku)

    def test_no_size_is_listed_and_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=None)
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        assert _lines_about(migration, planned, "NO SIZE", "no size", item.sku)

    def test_an_unknown_purchase_unit_is_listed_and_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="CRATE", purchase_factor=D("40"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        assert _lines_about(migration, planned, "NO SIZE", "CRATE", "not in the unit table", item.sku)

    def test_an_item_that_already_has_the_row_is_skipped(self, db, migration, make_product):
        same = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        other = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        db.add(ProductUnit(product_id=same.id, unit_code="BOX", stock_units_per_unit=D("12")))
        db.add(ProductUnit(product_id=other.id, unit_code="BOX", stock_units_per_unit=D("10")))
        planned = _run(db, migration)
        assert _item_units(db, same) == {"BOX": (D("12"), None)}
        assert _item_units(db, other) == {"BOX": (D("10"), None)}
        report = _report(migration, planned)
        assert same.sku not in report
        assert _lines_about(migration, planned, "KEPT", other.sku, "1 BOX = 10 EA", "12")

    def test_a_row_typed_the_other_way_round_is_compared_by_its_size(self, db, migration, make_product):
        """1 EA = 0.25 BOX is the same size as a BOX of 4."""
        item = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("4"))
        db.add(ProductUnit(product_id=item.id, unit_code="BOX", units_per_stock_unit=D("0.25")))
        planned = _run(db, migration)
        assert item.sku not in _report(migration, planned)


class TestLines:
    def test_an_ea_line_on_gram_filament_becomes_g(self, db, migration, make_product, make_bom, filament):
        _, line = _bom_line(db, make_product, make_bom, filament(purchase_uom="KG"))
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("G", D("50"))
        assert "BOM line" in _report(migration, planned)

    def test_it_becomes_g_also_when_the_item_has_ea_as_its_own_unit(self, db, migration, make_product, make_bom,
                                                                    filament):
        item = filament(purchase_factor=D("750"))
        _, line = _bom_line(db, make_product, make_bom, item)
        _run(db, migration)
        assert (line.unit, line.quantity) == ("G", D("50"))
        assert _item_units(db, item) == {"EA": (D("750"), None)}

    def test_a_routing_material_in_ea_on_gram_filament_becomes_g(self, db, migration, filament, routing_material):
        _, material = routing_material(filament(purchase_uom="KG"))
        _run(db, migration)
        assert (material.unit, material.quantity) == ("G", D("37"))

    def test_open_production_order_rows_are_settled_and_consumed_ones_left(self, db, migration, filament,
                                                                           order_rows):
        order, rows = order_rows(filament(purchase_uom="KG"),
                                 ("pending", "allocated", "error", "consumed", "returned"))
        planned = _run(db, migration)
        assert {status: row.unit for status, row in rows.items()} == {
            "pending": "G", "allocated": "G", "error": "G", "consumed": "EA", "returned": "EA",
        }
        assert {row.quantity_required for row in rows.values()} == {D("50")}
        # The row whose consumption had failed is named, so someone can go back to it.
        assert _lines_about(migration, planned, "had failed", order.code)

    def test_an_ea_line_on_a_part_stocked_by_the_metre_becomes_m(self, db, migration, make_product, make_bom):
        tube = make_product(item_type="component", unit="M", purchase_uom="M")
        _, line = _bom_line(db, make_product, make_bom, tube, quantity="2")
        _run(db, migration)
        assert (line.unit, line.quantity) == ("M", D("2"))

    def test_an_ea_line_on_a_kg_stocked_material_is_left_with_both_readings(self, db, migration, make_product,
                                                                            make_bom):
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        bom, line = _bom_line(db, make_product, make_bom, pellets)
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("EA", D("50"))
        (listed,) = _lines_about(migration, planned, "LEFT", pellets.sku)
        assert "cost takes 1 EA as 1 G" in listed
        assert "planning takes 1 EA as 1 KG" in listed
        assert f"BOM {bom.id}" in listed

    def test_an_ea_line_on_a_metre_part_bought_by_the_each_of_10_is_left(self, db, migration, make_product,
                                                                         make_bom):
        tube = make_product(item_type="component", unit="M", purchase_uom="EA", purchase_factor=D("10"))
        _, line = _bom_line(db, make_product, make_bom, tube, quantity="2")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("EA", D("2"))
        (listed,) = _lines_about(migration, planned, "LEFT", tube.sku)
        assert "cost takes 1 EA as 10 M" in listed
        assert "planning takes 1 EA as 1 M" in listed
        assert "1 EA = 10 M" in listed

    def test_a_kg_line_on_a_material_stocked_by_the_each_is_left(self, db, migration, make_product, make_bom):
        spool = make_product(item_type="material", unit="EA", purchase_uom="EA")
        _, line = _bom_line(db, make_product, make_bom, spool, quantity="0.25", unit="KG")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("KG", D("0.25"))
        (listed,) = _lines_about(migration, planned, "LEFT", spool.sku)
        assert "cost takes 1 KG as 1000 G" in listed
        assert "planning takes 1 KG as 1 EA" in listed

    def test_a_box_line_on_an_item_bought_by_the_box_of_12_is_left(self, db, migration, make_product, make_bom):
        screws = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        _, line = _bom_line(db, make_product, make_bom, screws, quantity="1", unit="BOX")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("BOX", D("1"))
        (listed,) = _lines_about(migration, planned, "LEFT", screws.sku)
        assert "cost takes 1 BOX as 12 EA" in listed
        assert "planning takes 1 BOX as 1 EA" in listed

    def test_a_routing_material_is_costed_as_the_bare_number(self, db, migration, make_product, routing_material):
        """A routing material's cost never looks at its unit."""
        screws = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        routing, material = routing_material(screws, quantity="1", unit="BOX")
        planned = _run(db, migration)
        assert material.unit == "BOX"
        (listed,) = _lines_about(migration, planned, "LEFT", screws.sku)
        assert "cost takes 1 BOX as 1 EA" in listed
        assert routing.code in listed

    def test_a_kg_line_on_gram_filament_is_left_and_not_listed(self, db, migration, make_product, make_bom,
                                                               filament):
        item = filament(purchase_uom="KG")
        _, line = _bom_line(db, make_product, make_bom, item, quantity="0.05", unit="KG")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("KG", D("0.05"))
        assert item.sku not in _report(migration, planned)

    def test_a_line_in_a_code_the_table_does_not_know_is_not_touched(self, db, migration, make_product, make_bom,
                                                                     filament):
        """Migration 106 lists those. Nothing can be said about what such a line means."""
        item = filament(purchase_uom="KG")
        _, line = _bom_line(db, make_product, make_bom, item, unit="SCOOP")
        planned = _run(db, migration)
        assert line.unit == "SCOOP"
        assert item.sku not in _report(migration, planned)

    def test_lines_left_for_one_item_and_unit_share_a_report_line(self, db, migration, make_product, make_bom):
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        for _ in range(3):
            _bom_line(db, make_product, make_bom, pellets)
        planned = _run(db, migration)
        (listed,) = _lines_about(migration, planned, "LEFT", pellets.sku)
        assert "3 BOM line(s)" in listed


class TestShape:
    def test_a_second_run_changes_nothing(self, db, migration, make_product, make_bom, filament):
        item = filament()
        _bom_line(db, make_product, make_bom, item)
        make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        _bom_line(db, make_product, make_bom, pellets)

        first = _run(db, migration)
        assert migration.changes(first) > 0
        again = _run(db, migration)
        # A line that is left is listed again; nothing is written.
        assert migration.changes(again) == 0
        assert _lines_about(migration, again, "LEFT", pellets.sku)

    def test_nothing_to_do_says_so(self, migration):
        empty = migration.plan({key: [] for key in (
            "units", "items", "bom_lines", "routing_lines", "order_lines", "po_lines", "item_units",
            "po_line_units")})
        assert migration.changes(empty) == 0
        assert migration.report_lines(empty) == [
            (logging.INFO, "107: purchase units, item units and line units needed no change")
        ]

    def test_the_projection_is_what_the_database_holds_afterwards(self, db, migration, make_product, make_bom,
                                                                  filament, routing_material, order_rows):
        """Every kind of change the plan can hold goes through the comparison."""
        plain, spool = filament(), filament(purchase_factor=D("750"))
        _bom_line(db, make_product, make_bom, plain)
        routing_material(spool)
        order_rows(plain, ("pending", "error", "consumed"))
        make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("1"))
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        _bom_line(db, make_product, make_bom, pellets)
        db.flush()

        bind = db.connection()
        before = migration.read_state(bind)
        planned = migration.plan(before)
        for name in ("purchase_units", "item_units", "lines", "left", "no_item_unit"):
            assert planned[name], name
        projected = migration.project(before, planned)
        migration.apply(bind, planned)

        assert _comparable(projected) == _comparable(migration.read_state(bind))

    def test_planning_writes_nothing(self, db, migration, make_product, make_bom, filament):
        item = filament()
        _, line = _bom_line(db, make_product, make_bom, item)
        db.flush()
        bind = db.connection()
        state = migration.read_state(bind)
        migration.project(state, migration.plan(state))
        db.expire_all()
        assert (item.purchase_uom, line.unit) == ("EA", "EA")
        assert _item_units(db, item) == {}

    def test_it_reads_a_table_with_two_spellings_of_a_code_as_the_application_does(self, db, migration,
                                                                                   make_product, make_bom,
                                                                                   filament):
        """A switched-off row does not make a unit known."""
        db.add(UnitOfMeasure(code="SCOOP", name="Scoop", symbol="scoop", uom_class="pack",
                             to_base_factor=D("1"), active=False))
        item = filament(purchase_uom="KG")
        _, line = _bom_line(db, make_product, make_bom, item, unit="SCOOP")
        _run(db, migration)
        assert line.unit == "SCOOP"
