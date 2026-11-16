"""
Migration 107: purchase units, item units and line units settled.

The migration's functions take a connection, so they are run here against real
rows inside the test transaction. The test database already holds the standard
units, which is what migration 106 leaves. It may hold other rows too, so a
report is always searched for the SKU the test made.
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

_VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def migration():
    """Load migration 107 as a module."""
    return _load("migration_107", "107_settle_item_and_line_units.py")


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


def _unit(db, code, kind, factor="1", base=None, active=True):
    """Add a unit of the install's own to the unit table."""
    base_id = db.query(UnitOfMeasure.id).filter(UnitOfMeasure.code == base).scalar() if base else None
    row = UnitOfMeasure(code=code, name=code.title(), symbol=code.lower(), uom_class=kind,
                        base_unit_id=base_id, to_base_factor=D(factor), active=active)
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def filament(make_product):
    """Gram-stocked filament the way the item form saved it: bought by the EA, size 1000."""
    def _make(**values):
        values = {"item_type": "material", "unit": "G", "purchase_uom": "EA", "purchase_factor": D("1000"), **values}
        return make_product(**values)
    return _make


@pytest.fixture
def purchase_line(db, make_vendor, make_purchase_order):
    """A purchase order line for ``item`` in ``unit``, on an order with ``status``."""
    def _make(item, unit, status="received", number=1):
        order = make_purchase_order(vendor_id=make_vendor().id, status=status)
        line = PurchaseOrderLine(
            purchase_order_id=order.id, line_number=number, product_id=item.id,
            quantity_ordered=D("1"), quantity_received=D("0"), purchase_unit=unit,
            unit_cost=D("20"), line_total=D("20"),
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )
        db.add(line)
        db.flush()
        return order, line
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


@pytest.fixture
def bom_line(db, make_product, make_bom):
    """A BOM with one line for ``component``."""
    def _make(component, quantity="50", unit="EA"):
        bom = make_bom(product_id=make_product().id,
                       lines=[{"component_id": component.id, "quantity": D(quantity), "unit": unit}])
        return bom, db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
    return _make


class TestFrozenCopies:
    def test_the_spellings_match_the_module(self, migration):
        assert migration._SPELLINGS == uc.UNIT_SPELLINGS

    def test_the_pack_kind_matches_the_module(self, migration):
        assert migration._PACK == uc.PACK

    def test_the_counted_units_match_the_order_sizing_code(self, migration):
        from app.services.production_order_quantity_change import COUNTED_UNITS

        assert migration._COUNTED_UNITS == COUNTED_UNITS

    def test_the_cost_classes_match_the_table_cost_converts_with(self, migration):
        """Cost converts by itself only between units that share a base in the inline table."""
        from app.services.uom_service import INLINE_UOM_CONVERSIONS

        by_base = {}
        for code, info in INLINE_UOM_CONVERSIONS.items():
            by_base.setdefault(info["base"], set()).add(code)
        classes = {frozenset(codes) for codes in by_base.values() if len(codes) > 1}
        assert set(migration._COST_CLASSES) == classes

    def test_a_purchase_order_unit_is_read_as_migration_105_read_it(self, migration):
        older = _load("migration_105", "105_repair_flipped_standard_cost.py")
        assert migration._COUNT_SYNONYMS_105 == older._COUNT_SYNONYMS


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

    def test_the_item_type_is_read_in_any_case_and_not_trimmed_as_the_application_reads_it(self, db, migration,
                                                                                         filament):
        capital, padded = filament(item_type="Material"), filament(item_type=" material ")
        _run(db, migration)
        assert (capital.purchase_uom, padded.purchase_uom) == ("KG", "EA")

    def test_the_ones_migration_105_does_not_change_are_marked(self, db, migration, filament, purchase_line):
        """105 changed only materials whose purchase orders were in KG and never in EA."""
        never_bought, by_the_each, by_the_kilo, blank_unit, spelled_out, capital = (
            filament(), filament(), filament(), filament(), filament(), filament(item_type="Material"))
        purchase_line(by_the_each, "EA")
        purchase_line(by_the_each, "KG")
        purchase_line(by_the_kilo, "kg")
        purchase_line(blank_unit, "")
        purchase_line(blank_unit, "KG")
        purchase_line(spelled_out, "KILOGRAM")
        planned = _run(db, migration)

        every = (never_bought, by_the_each, by_the_kilo, blank_unit, spelled_out, capital)
        assert {item.purchase_uom for item in every} == {"KG"}
        reason = {sku: why for _id, sku, why in planned["purchase_units"]}
        assert reason[never_bought.sku] == "no_kg_lines"
        assert reason[by_the_each.sku] == "ea_lines"
        assert reason[by_the_kilo.sku] is None
        # 105 read a blank unit as EA, and knew no spelling of KG.
        assert reason[blank_unit.sku] == "ea_lines"
        assert reason[spelled_out.sku] == "no_kg_lines"
        # 105 looked for the item type in lower case only, so it never saw this one.
        assert reason[capital.sku] is None

        (in_ea,) = _lines_about(migration, planned, "migration 105", "when it has purchase order lines in EA")
        (no_kg,) = _lines_about(migration, planned, "migration 105", "when it has no purchase order lines in KG")
        assert by_the_each.sku in in_ea and blank_unit.sku in in_ea
        assert never_bought.sku in no_kg and spelled_out.sku in no_kg
        for line in (in_ea, no_kg):
            assert by_the_kilo.sku not in line and capital.sku not in line

    def test_an_open_purchase_order_line_in_ea_on_gram_filament_is_left_and_listed(self, db, migration, filament,
                                                                                  purchase_line):
        item = filament()
        order, line = purchase_line(item, "EA", status="ordered", number=3)
        planned = _run(db, migration)
        assert line.purchase_unit == "EA"
        (listed,) = _lines_about(migration, planned, "LEFT", "open purchase order line", "receiving refuses")
        assert f"{order.po_number} line 3 ({item.sku})" in listed
        assert "a unit of weight (KG or G)" in listed

    def test_so_is_one_on_a_spool_that_stays_bought_by_the_each(self, db, migration, filament, purchase_line):
        """The list is every gram-stocked material, not only the ones whose purchase unit changed."""
        spool = filament(purchase_factor=D("750"))
        order, line = purchase_line(spool, "EA", status="ordered")
        closed_order, _ = purchase_line(spool, "EA", status="received")
        planned = _run(db, migration)
        assert (spool.purchase_uom, line.purchase_unit) == ("EA", "EA")
        (listed,) = _lines_about(migration, planned, "LEFT", "open purchase order line")
        assert f"{order.po_number} line 1 ({spool.sku})" in listed
        assert closed_order.po_number not in listed

    def test_filament_of_another_size_is_not_given_kg(self, db, migration, filament):
        item = filament(purchase_factor=D("750"))
        _run(db, migration)
        assert item.purchase_uom == "EA"

    def test_a_part_stocked_in_grams_is_not_a_material(self, db, migration, make_product):
        item = make_product(item_type="component", unit="G", purchase_uom="EA", purchase_factor=D("1000"))
        _run(db, migration)
        assert item.purchase_uom == "EA"

    def test_without_a_kilogram_of_1000_grams_the_material_is_left_and_listed(self, db, migration, filament):
        """It then gets the EA of 1000 G as a unit of its own, like any other pack."""
        db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "KG").update({"active": False})
        item = filament()
        planned = _run(db, migration)
        assert item.purchase_uom == "EA"
        assert _lines_about(migration, planned, "LEFT", "does not hold a KG of 1000 G", item.sku)
        assert _item_units(db, item) == {"EA": (D("1000"), None)}


class TestItemUnits:
    def test_gram_filament_bought_by_the_each_of_750_gets_each_as_its_own_unit(self, db, migration, filament):
        item = filament(purchase_factor=D("750"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {"EA": (D("750"), None)}
        assert uc.stock_units_per(db, item, "EA") == D("750")
        assert _lines_about(migration, planned, "1 EA = 750 G", item.sku)

    def test_a_pack_of_12_gets_a_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {"BOX": (D("12"), None)}
        assert _lines_about(migration, planned, "1 BOX = 12 EA", item.sku)

    def test_one_pack_bought_in_another_gets_a_row_too(self, db, migration, make_product):
        """Two packs are the same kind, and the unit table still cannot convert them."""
        item = make_product(item_type="component", unit="BOX", purchase_uom="CASE", purchase_factor=D("4"))
        _run(db, migration)
        assert _item_units(db, item) == {"CASE": (D("4"), None)}

    def test_a_purchase_unit_the_table_converts_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="supply", unit="G", purchase_uom="KG", purchase_factor=D("1000"))
        stale = make_product(item_type="supply", unit="G", purchase_uom="KG", purchase_factor=D("1"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {} and _item_units(db, stale) == {}
        # Cost converts KG to G by itself, so a stale size on such an item is not a disagreement.
        report = _report(migration, planned)
        assert item.sku not in report and stale.sku not in report

    def test_a_size_of_one_is_listed_and_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("1"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        assert _lines_about(migration, planned, "NO SIZE", "a size of 1", "how many EA are in one BOX", item.sku)

    def test_no_size_is_listed_and_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=None)
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        assert _lines_about(migration, planned, "NO SIZE", "they hold no size", item.sku)

    def test_a_size_too_large_to_record_is_listed_and_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="BOX",
                            purchase_factor=D("10000000000"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        assert _lines_about(migration, planned, "NO SIZE", "10000000000, is too large to record", item.sku)

    def test_an_unknown_purchase_unit_is_listed_and_gets_no_row(self, db, migration, make_product):
        item = make_product(item_type="component", unit="EA", purchase_uom="CRATE", purchase_factor=D("40"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        (listed,) = _lines_about(migration, planned, "NO SIZE", item.sku)
        assert "their purchase unit CRATE is not in the unit table. Add CRATE under Units" in listed

    def test_an_unknown_stock_unit_is_named_as_the_stock_unit_and_nobody_is_told_to_change_it(
            self, db, migration, make_product):
        """Changing an item's stock unit rescales its stock."""
        item = make_product(item_type="component", unit="CRATE", purchase_uom="BOX", purchase_factor=D("40"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        (listed,) = _lines_about(migration, planned, "NO SIZE", item.sku)
        assert "their stock unit CRATE is not in the unit table. Add CRATE under Units" in listed
        assert "change" not in listed.lower()

    def test_a_purchase_unit_that_is_switched_off_is_said_to_be_switched_off(self, db, migration, make_product):
        _unit(db, "SCOOP", "pack", active=False)
        item = make_product(item_type="component", unit="EA", purchase_uom="SCOOP", purchase_factor=D("5"))
        planned = _run(db, migration)
        assert _item_units(db, item) == {}
        (listed,) = _lines_about(migration, planned, "NO SIZE", item.sku)
        assert "their purchase unit SCOOP is switched off in the unit table" in listed
        assert "Add SCOOP" not in listed

    def test_an_item_that_already_has_the_row_is_skipped(self, db, migration, make_product):
        same = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        other = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        db.add(ProductUnit(product_id=same.id, unit_code="BOX", stock_units_per_unit=D("12")))
        db.add(ProductUnit(product_id=other.id, unit_code="BOX", stock_units_per_unit=D("10")))
        planned = _run(db, migration)
        assert _item_units(db, same) == {"BOX": (D("12"), None)}
        assert _item_units(db, other) == {"BOX": (D("10"), None)}
        assert same.sku not in _report(migration, planned)
        assert _lines_about(migration, planned, "KEPT", other.sku, "1 BOX = 10 EA", "says 12")

    def test_a_row_typed_the_other_way_round_is_compared_by_its_size(self, db, migration, make_product):
        """1 EA = 0.25 BOX is a BOX of 4, and 1 EA = 0.0833333333 BOX is a BOX of 12 to six places."""
        exact = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("4"))
        rounded = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        db.add(ProductUnit(product_id=exact.id, unit_code="BOX", units_per_stock_unit=D("0.25")))
        db.add(ProductUnit(product_id=rounded.id, unit_code="BOX", units_per_stock_unit=D("0.0833333333")))
        planned = _run(db, migration)
        report = _report(migration, planned)
        assert exact.sku not in report and rounded.sku not in report

    def test_a_size_that_disagrees_with_the_unit_table_is_listed_and_nothing_is_changed(self, db, migration,
                                                                                       make_product):
        """An install's own DOZEN of 12 EA. Receiving converts through it; cost uses the item's size."""
        _unit(db, "DOZEN", "quantity", factor="12", base="EA")
        agrees = make_product(item_type="component", unit="EA", purchase_uom="DOZEN", purchase_factor=D("12"))
        differs = make_product(item_type="component", unit="EA", purchase_uom="DOZEN", purchase_factor=D("10"))
        none = make_product(item_type="component", unit="EA", purchase_uom="DOZEN", purchase_factor=None)
        planned = _run(db, migration)
        for item in (agrees, differs, none):
            assert _item_units(db, item) == {}
        assert agrees.sku not in _report(migration, planned)
        (says_ten,) = _lines_about(migration, planned, "DIFFERENT SIZES", differs.sku)
        assert "the unit table says 1 DOZEN = 12 EA, and these items say 10" in says_ten
        (says_nothing,) = _lines_about(migration, planned, "DIFFERENT SIZES", none.sku)
        assert "these items hold no size" in says_nothing
        ours = {agrees.sku, differs.sku, none.sku}
        assert not [entry for entry in planned["item_units"] if entry[1] in ours]


class TestLinesRewritten:
    def test_an_ea_line_on_gram_filament_becomes_g(self, db, migration, bom_line, filament):
        item = filament(purchase_uom="KG")
        _, line = bom_line(item)
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("G", D("50"))
        assert ("bom_lines", line.id, "EA", "G") in planned["lines"]
        (said,) = _lines_about(migration, planned, "BOM line(s) in EA", "now say G")
        assert "the fulfilment queue already took the number as G" in said
        # A BOM line's requirement was never rounded, so nothing is said about rounding.
        assert "rounded" not in said

    def test_on_filament_that_was_bought_by_the_each_of_1000_the_bom_page_figure_is_named(self, db, migration,
                                                                                         bom_line, filament):
        item = filament()
        _, line = bom_line(item)
        planned = _run(db, migration)
        assert (item.purchase_uom, line.unit) == ("KG", "G")
        assert planned["lines_on_changed_materials"] >= 1
        assert _lines_about(migration, planned, "The BOM page showed each EA on them as 1000 G needed")

    def test_a_routing_material_in_ea_on_gram_filament_becomes_g(self, db, migration, filament, routing_material):
        _, material = routing_material(filament(purchase_uom="KG"))
        planned = _run(db, migration)
        assert (material.unit, material.quantity) == ("G", D("37"))
        (said,) = _lines_about(migration, planned, "routing material line(s) in EA", "now say G")
        assert "no longer rounded up to a whole number" in said

    def test_open_production_order_rows_are_settled_and_consumed_ones_left(self, db, migration, filament,
                                                                           order_rows):
        item = filament(purchase_uom="KG")
        order, rows = order_rows(item, ("pending", "allocated", "error", "consumed", "returned"))
        planned = _run(db, migration)
        assert {status: row.unit for status, row in rows.items()} == {
            "pending": "G", "allocated": "G", "error": "G", "consumed": "EA", "returned": "EA",
        }
        assert {row.quantity_required for row in rows.values()} == {D("50")}
        # The row whose consumption had failed is named, with its order's status and both things
        # that can happen next: it is taken up at order completion or shipment, or never.
        (failed,) = _lines_about(migration, planned, "had failed to be consumed", order.code)
        assert item.sku in failed and "Its order is draft." in failed
        assert "takes a failed row up again when the production order is completed" in failed
        assert "deducted twice" in failed
        assert "nothing takes the row up again" in failed and "correct the item's stock by hand" in failed

    def test_a_routing_line_and_an_order_row_on_a_spool_with_an_each_size_become_g_and_are_named(
            self, db, migration, filament, routing_material, order_rows):
        """No reader takes these by the spool's size: cost and planning both take the number as grams.

        A BOM line on the same item is left, because the BOM page reads it as 750 G.
        """
        spool = filament(purchase_factor=D("750"))
        routing, material = routing_material(spool, quantity="37")
        order, rows = order_rows(spool, ("pending", "error"), quantity="37")
        planned = _run(db, migration)

        assert (material.unit, material.quantity) == ("G", D("37"))
        assert {status: (row.unit, row.quantity_required) for status, row in rows.items()} == {
            "pending": ("G", D("37")), "error": ("G", D("37")),
        }
        assert _item_units(db, spool) == {"EA": (D("750"), None)}
        # Each is named, in case a line did mean that many spools.
        (routing_check,) = _lines_about(migration, planned, "CHECK", "routing material line(s)", spool.sku)
        assert "for which the item says 1 EA = 750 G" in routing_check
        assert f"routing {routing.code} material {material.id}" in routing_check
        assert "If a line meant that many of the item, change its quantity" in routing_check
        (order_check,) = _lines_about(migration, planned, "CHECK", "production order material row(s)", spool.sku)
        assert "CHECK 2 of those" in order_check and order.code in order_check
        assert _lines_about(migration, planned, "had failed to be consumed", order.code, spool.sku)
        assert not _lines_about(migration, planned, "LEFT", spool.sku)

    def test_a_routing_line_in_ea_on_a_part_with_an_each_size_of_its_own_is_still_left(
            self, db, migration, make_product, routing_material):
        """The plan rewrites a material's line whatever its own units; a part with EA of its own is left."""
        tube = make_product(item_type="component", unit="M", purchase_uom="EA", purchase_factor=D("10"))
        _, material = routing_material(tube, quantity="2")
        planned = _run(db, migration)
        assert (material.unit, material.quantity) == ("EA", D("2"))
        assert _lines_about(migration, planned, "LEFT", "routing material line(s)", tube.sku, "1 EA = 10 M")
        assert not _lines_about(migration, planned, "CHECK", tube.sku)

    def test_an_ea_line_on_a_part_stocked_by_the_metre_becomes_m(self, db, migration, make_product, bom_line):
        tube = make_product(item_type="component", unit="M", purchase_uom="M")
        _, line = bom_line(tube, quantity="2")
        _run(db, migration)
        assert (line.unit, line.quantity) == ("M", D("2"))

    def test_an_ea_line_on_a_part_stocked_by_the_box_becomes_box_and_is_still_rounded(self, db, migration,
                                                                                      make_product,
                                                                                      routing_material):
        """BOX is one of the units a requirement is rounded up for, so nothing changes there."""
        carton = make_product(item_type="component", unit="BOX", purchase_uom="BOX")
        _, material = routing_material(carton, quantity="1")
        planned = _run(db, migration)
        assert material.unit == "BOX"
        (said,) = _lines_about(migration, planned, "routing material line(s) in EA", "now say BOX")
        assert "rounded" not in said


class TestLinesLeft:
    def test_a_bom_line_in_ea_on_a_spool_with_an_each_size_of_its_own_is_left(self, db, migration, bom_line,
                                                                              filament):
        """The BOM page's needed and shortage figures already read 1 EA on it as the spool's 750 G."""
        spool = filament(purchase_factor=D("750"))
        _, line = bom_line(spool, quantity="1")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("EA", D("1"))
        assert _item_units(db, spool) == {"EA": (D("750"), None)}
        assert not [entry for entry in planned["lines"] if entry[:2] == ("bom_lines", line.id)]
        (listed,) = _lines_about(migration, planned, "LEFT", "BOM line(s)", spool.sku)
        assert "cost takes 1 EA as 1 G" in listed
        assert "the BOM page's needed and shortage figures take 1 EA as 750 G" in listed
        assert "planning takes 1 EA as 1 G" in listed
        assert f"{spool.sku} has EA as a unit of its own: 1 EA = 750 G." in listed
        assert "If the line means that, leave it." in listed
        assert "change the line's unit to G" in listed

    def test_an_ea_line_on_filament_with_a_hand_made_each_size_is_left(self, db, migration, bom_line, filament):
        item = filament(purchase_uom="KG")
        db.add(ProductUnit(product_id=item.id, unit_code="EA", stock_units_per_unit=D("250")))
        _, line = bom_line(item)
        planned = _run(db, migration)
        assert line.unit == "EA"
        assert _lines_about(migration, planned, "LEFT", item.sku, "1 EA = 250 G")

    def test_an_ea_line_on_a_kg_stocked_material_is_left_with_every_reading(self, db, migration, make_product,
                                                                            bom_line):
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        bom, line = bom_line(pellets)
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("EA", D("50"))
        (listed,) = _lines_about(migration, planned, "LEFT", pellets.sku)
        assert "cost takes 1 EA as 1 G" in listed
        assert "the BOM page's needed and shortage figures take 1 EA as 1 KG" in listed
        assert "planning takes 1 EA as 1 KG" in listed
        assert "no stock is reserved for it and completing or shipping the order fails" in listed
        assert "the fulfilment queue reserves and consumes 1 EA as 1 KG" in listed
        # Changing the unit alone would turn 50 read as grams into 50 KG.
        assert "change the line's unit to KG and enter its quantity in KG" in listed
        assert f"BOM {bom.id} line {line.id}" in listed

    def test_an_ea_line_on_a_metre_part_bought_by_the_each_of_10_is_left(self, db, migration, make_product,
                                                                         bom_line):
        tube = make_product(item_type="component", unit="M", purchase_uom="EA", purchase_factor=D("10"))
        _, line = bom_line(tube, quantity="2")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("EA", D("2"))
        (listed,) = _lines_about(migration, planned, "LEFT", tube.sku)
        assert f"cost takes 1 EA as 10 M (1 M in the cost roll-up, if {tube.sku} has a BOM of its own)" in listed
        assert "planning takes 1 EA as 1 M" in listed
        assert f"{tube.sku} has EA as a unit of its own: 1 EA = 10 M." in listed

    def test_an_ea_line_is_left_when_the_purchase_size_gives_ea_a_meaning_but_got_no_row(
            self, db, migration, make_product, bom_line):
        """A size too large to record makes no unit of the item's own, and cost still reads the line by it."""
        tube = make_product(item_type="component", unit="M", purchase_uom="EA", purchase_factor=D("10000000000"))
        _, line = bom_line(tube, quantity="2")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("EA", D("2"))
        assert _item_units(db, tube) == {}
        (listed,) = _lines_about(migration, planned, "LEFT", "BOM line(s)", tube.sku)
        assert "cost takes 1 EA as 10000000000 M" in listed
        assert f"{tube.sku} is bought by the EA, and its purchase size says 1 EA = 10000000000 M." in listed
        assert _lines_about(migration, planned, "NO SIZE", "too large to record", tube.sku)

    def test_an_ea_line_on_a_part_with_a_hand_made_each_size_is_left(self, db, migration, make_product, bom_line):
        tube = make_product(item_type="component", unit="M", purchase_uom="M")
        db.add(ProductUnit(product_id=tube.id, unit_code="EA", stock_units_per_unit=D("3")))
        _, line = bom_line(tube, quantity="2")
        planned = _run(db, migration)
        assert line.unit == "EA"
        assert _lines_about(migration, planned, "LEFT", tube.sku, "1 EA = 3 M")

    def test_a_size_reached_through_another_unit_names_the_unit_the_item_has(self, db, migration, make_product,
                                                                             bom_line):
        """Cable stocked by the each and bought by the M of 2. A line in CM converts through its M."""
        cable = make_product(item_type="component", unit="EA", purchase_uom="M", purchase_factor=D("2"))
        _, line = bom_line(cable, quantity="30", unit="CM")
        planned = _run(db, migration)
        assert line.unit == "CM"
        (listed,) = _lines_about(migration, planned, "LEFT", cable.sku)
        assert f"{cable.sku} has M as a unit of its own, which makes 1 CM = 0.02 EA." in listed
        assert "has CM as a unit of its own" not in listed

    def test_an_ea_line_on_a_part_stocked_by_the_roll_is_left_because_rounding_would_stop(
            self, db, migration, make_product, routing_material):
        """A requirement in EA is rounded up for a production order; one in ROLL is not."""
        tape = make_product(item_type="component", unit="ROLL", purchase_uom="ROLL")
        _, material = routing_material(tape, quantity="0.3")
        planned = _run(db, migration)
        assert (material.unit, material.quantity) == ("EA", D("0.3"))
        (listed,) = _lines_about(migration, planned, "LEFT", tape.sku)
        assert "cost takes 1 EA as 1 ROLL" in listed
        assert "It was not rewritten for you because a requirement in EA is rounded up" in listed
        assert "change the line's unit to ROLL and enter its quantity in ROLL" in listed

    def test_a_kg_line_on_a_material_stocked_by_the_each_is_left(self, db, migration, make_product, bom_line):
        spool = make_product(item_type="material", unit="EA", purchase_uom="EA")
        _, line = bom_line(spool, quantity="0.25", unit="KG")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("KG", D("0.25"))
        (listed,) = _lines_about(migration, planned, "LEFT", spool.sku)
        assert "cost turns 1 KG into 1000 G and prices it per KG" in listed
        assert "not a real figure for an item stocked by the EA" in listed
        assert "planning takes 1 KG as 1 EA" in listed

    def test_a_box_line_on_an_item_bought_by_the_box_of_12_is_left(self, db, migration, make_product, bom_line):
        screws = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        _, line = bom_line(screws, quantity="1", unit="BOX")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("BOX", D("1"))
        (listed,) = _lines_about(migration, planned, "LEFT", screws.sku)
        assert "cost takes 1 BOX as 12 EA" in listed
        assert "planning takes 1 BOX as 1 EA" in listed
        assert "the fulfilment queue reserves and consumes 1 BOX as 1 EA" in listed

    def test_a_routing_material_is_costed_as_the_bare_number(self, db, migration, make_product, routing_material):
        """A routing material's cost never looks at its unit."""
        screws = make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        routing, material = routing_material(screws, quantity="1", unit="BOX")
        planned = _run(db, migration)
        assert material.unit == "BOX"
        (listed,) = _lines_about(migration, planned, "LEFT", screws.sku)
        assert "cost takes 1 BOX as 1 EA" in listed
        assert "a production order made from it keeps the unit" in listed
        assert f"routing {routing.code} material {material.id}" in listed

    def test_a_production_order_row_left_is_named_by_its_order(self, db, migration, make_product, order_rows):
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        order, rows = order_rows(pellets, ("pending",))
        planned = _run(db, migration)
        assert rows["pending"].unit == "EA"
        (listed,) = _lines_about(migration, planned, "LEFT", "production order material row(s)", pellets.sku)
        assert "no stock is reserved for it and consuming it fails" in listed
        assert f"order {order.code} material row {rows['pending'].id}" in listed

    def test_a_kg_line_on_gram_filament_is_left_and_not_listed(self, db, migration, bom_line, filament):
        item = filament(purchase_uom="KG")
        _, line = bom_line(item, quantity="0.05", unit="KG")
        planned = _run(db, migration)
        assert (line.unit, line.quantity) == ("KG", D("0.05"))
        assert item.sku not in _report(migration, planned)

    def test_a_line_in_a_code_the_table_does_not_know_is_not_touched(self, db, migration, bom_line, filament):
        """Migration 106 lists those. Nothing can be said about what such a line means."""
        item = filament(purchase_uom="KG")
        _, line = bom_line(item, unit="SCOOP")
        planned = _run(db, migration)
        assert line.unit == "SCOOP"
        assert item.sku not in _report(migration, planned)

    def test_a_line_in_a_unit_that_is_switched_off_is_not_touched_either(self, db, migration, bom_line, filament):
        """A switched-off row does not make a unit known. Were it read as known, the line would be listed."""
        _unit(db, "SCOOP", "pack", active=False)
        item = filament(purchase_uom="KG")
        _, line = bom_line(item, unit="SCOOP")
        planned = _run(db, migration)
        assert line.unit == "SCOOP"
        assert item.sku not in _report(migration, planned)

    def test_of_two_spellings_of_a_code_the_upper_case_row_is_the_one_read(self, db, migration, bom_line,
                                                                           filament):
        """As the application reads the table. Read the other way, SCOOP would be a weight that converts."""
        _unit(db, "Scoop", "weight", factor="0.05", base="KG")
        _unit(db, "SCOOP", "pack")
        item = filament(purchase_uom="KG")
        _, line = bom_line(item, unit="SCOOP")
        planned = _run(db, migration)
        assert line.unit == "SCOOP"
        assert _lines_about(migration, planned, "LEFT", "BOM line(s) in SCOOP", item.sku)

    def test_a_line_with_no_unit_at_all_is_listed(self, db, migration, bom_line, filament):
        item = filament(purchase_uom="KG")
        bom, line = bom_line(item, unit="")
        planned = _run(db, migration)
        assert line.unit == ""
        (listed,) = _lines_about(migration, planned, "LEFT", "BOM line(s) with no unit at all")
        assert f"BOM {bom.id} line {line.id}" in listed
        assert "Open each line and pick its unit." in listed

    def test_lines_left_for_one_item_and_unit_share_a_report_line(self, db, migration, make_product, bom_line):
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        for _ in range(3):
            bom_line(pellets)
        planned = _run(db, migration)
        (listed,) = _lines_about(migration, planned, "LEFT", pellets.sku)
        assert "LEFT 3 BOM line(s)" in listed


class TestShape:
    def test_a_second_run_changes_nothing(self, db, migration, make_product, bom_line, filament):
        item = filament()
        bom_line(item)
        make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        bom_line(pellets)
        spool = filament(purchase_factor=D("750"))
        bom_line(spool)

        first = _run(db, migration)
        assert migration.changes(first) > 0
        again = _run(db, migration)
        # A line that is left is listed again; nothing is written.
        assert migration.changes(again) == 0
        assert _lines_about(migration, again, "LEFT", pellets.sku)
        assert _lines_about(migration, again, "LEFT", spool.sku)

    def test_nothing_to_do_says_so(self, migration):
        empty = migration.plan({key: [] for key in migration._STATE_KEYS})
        assert migration.changes(empty) == 0
        assert migration.report_lines(empty) == [
            (logging.INFO, "107: purchase units, item units and line units needed no change")
        ]

    def test_the_projection_is_what_the_database_holds_afterwards(self, db, migration, make_product, bom_line,
                                                                  filament, routing_material, order_rows):
        """Every kind of change the plan can hold goes through the comparison."""
        plain, spool = filament(), filament(purchase_factor=D("750"))
        bom_line(plain)
        routing_material(spool)
        routing_material(filament(purchase_uom="KG"))
        order_rows(plain, ("pending", "error", "consumed"))
        make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("12"))
        make_product(item_type="component", unit="EA", purchase_uom="BOX", purchase_factor=D("1"))
        pellets = make_product(item_type="material", unit="KG", purchase_uom="KG")
        bom_line(pellets)
        db.flush()

        bind = db.connection()
        before = migration.read_state(bind)
        planned = migration.plan(before)
        for name in ("purchase_units", "item_units", "lines", "failed_rows", "left", "no_item_unit"):
            assert planned[name], name
        assert {key for key, _id, _old, _new in planned["lines"]} == {"bom_lines", "routing_lines", "order_lines"}
        projected = migration.project(before, planned)
        migration.apply(bind, planned)

        assert _comparable(projected) == _comparable(migration.read_state(bind))

    def test_planning_writes_nothing(self, db, migration, bom_line, filament):
        item = filament()
        _, line = bom_line(item)
        db.flush()
        bind = db.connection()
        state = migration.read_state(bind)
        migration.project(state, migration.plan(state))
        db.expire_all()
        assert (item.purchase_uom, line.unit) == ("EA", "EA")
        assert _item_units(db, item) == {}

    def test_a_factor_longer_than_28_digits_does_not_stop_the_report(self, migration):
        """Two unit rows 30 orders of magnitude apart. The numbers are absurd; the upgrade must not stop."""
        state = {key: [] for key in migration._STATE_KEYS}
        state["units"] = [
            {"id": 1, "code": "EA", "uom_class": "quantity", "to_base_factor": D("0.000000000000001"),
             "active": True},
            {"id": 2, "code": "LOT", "uom_class": "quantity", "to_base_factor": D("1000000000000000"),
             "active": True},
        ]
        state["items"] = [{"id": 1, "sku": "FAR-APART", "unit": "EA", "purchase_uom": "LOT",
                           "purchase_factor": D("12"), "item_type": "component", "material_type_id": None}]
        planned = migration.plan(state)
        (level, line), = migration.report_lines(planned)
        assert "DIFFERENT SIZES" in line and "FAR-APART" in line
