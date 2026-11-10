"""
Migration 105: repair standard costs a PO receipt rewrote per stock unit.

The migration's data functions take a connection, so they are run here against
real product rows inside the test transaction.
"""
import importlib.util
from decimal import Decimal
from pathlib import Path

import pytest

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "105_repair_flipped_standard_cost.py"
)


@pytest.fixture(scope="module")
def migration():
    """Load migration 105 as a module."""
    spec = importlib.util.spec_from_file_location("migration_105", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _filament(make_product, **kw):
    """A G / KG / 1000 material; keyword arguments set its costs."""
    base = dict(item_type="material", unit="G", purchase_uom="KG",
                purchase_factor=Decimal("1000"), is_raw_material=True)
    base.update(kw)
    return make_product(**base)


def _run(db, migration):
    """Run both data steps the way upgrade() does and return the repair report."""
    db.flush()
    bind = db.connection()
    migration.fix_material_purchase_units(bind)
    report = migration.repair_standard_costs(bind)
    db.expire_all()
    return report


class TestClassify:
    """The pure decision: what does this standard cost look like."""

    @pytest.mark.parametrize("standard, average, expected", [
        ("0.02", "0.02", "flipped"),
        ("0.0127", "0.0127", "flipped"),
        ("0.03", "0.02", "flipped"),
        ("20.00", "0.02", "ok"),
        ("24.99", "0.02", "ok"),
        ("0.6", "0.02", "ambiguous"),
        ("500", "0.02", "ambiguous"),
    ])
    def test_filament_cases(self, migration, standard, average, expected):
        """G stock bought by the KG: 1000 stock units per purchase unit."""
        assert migration.classify("G", "KG", Decimal("1000"), standard, average) == expected

    def test_missing_costs_are_skipped(self, migration):
        """No standard or no average cost: nothing to compare."""
        assert migration.classify("G", "KG", 1000, None, "0.02") == "skip"
        assert migration.classify("G", "KG", 1000, "20", None) == "skip"
        assert migration.classify("G", "KG", 1000, "20", "0") == "skip"

    def test_same_unit_is_skipped(self, migration):
        """Bought and stocked in EA: equal costs are correct, not flipped."""
        assert migration.classify("EA", "EA", None, "5", "5") == "skip"

    def test_small_pack_is_skipped(self, migration):
        """A box of 6 is too close to tell the two patterns apart."""
        assert migration.classify("EA", "BOX", 6, "2", "2") == "skip"

    def test_pack_without_a_size_is_skipped(self, migration):
        """No pack size: the units are unknown."""
        assert migration.classify("EA", "BOX", None, "2", "2") == "skip"

    def test_box_of_12_flipped(self, migration):
        """A box of 12 whose standard cost equals the per-each average is flipped."""
        assert migration.classify("EA", "BOX", 12, "2", "2") == "flipped"
        assert migration.classify("EA", "BOX", 12, "24", "2") == "ok"

    def test_class_conversion_wins_over_a_wrong_factor(self, migration):
        """G / KG with a factor of 1 is still 1000 G per KG."""
        assert migration.stock_units_per_purchase_unit("G", "KG", 1) == Decimal("1000")
        assert migration.classify("G", "KG", 1, "0.02", "0.02") == "flipped"


class TestRepairStandardCosts:
    """The data step against real product rows."""

    def test_flipped_filament_is_scaled_back_to_per_kg(self, db, make_product, migration):
        """standard 0.0200 with average 0.0200 becomes 20.00."""
        item = _filament(make_product, standard_cost=Decimal("0.02"),
                         average_cost=Decimal("0.02"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("20")
        assert item.average_cost == Decimal("0.02")
        entry = next(r for r in report["repaired"] if r["sku"] == item.sku)
        assert entry["new"] == Decimal("20.0000")

    def test_correct_filament_is_untouched(self, db, make_product, migration):
        """standard 20.00 with average 0.0200 is already per KG."""
        item = _filament(make_product, standard_cost=Decimal("20.00"),
                         average_cost=Decimal("0.02"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("20")
        assert item.sku not in {r["sku"] for r in report["repaired"]}

    def test_never_received_filament_is_untouched(self, db, make_product, migration):
        """No average cost yet: the standard cost is left as entered."""
        item = _filament(make_product, standard_cost=Decimal("22.99"))
        _run(db, migration)

        assert item.standard_cost == Decimal("22.99")

    def test_ambiguous_item_is_reported_and_untouched(self, db, make_product, migration):
        """A standard cost that fits neither pattern is listed, not changed."""
        item = _filament(make_product, standard_cost=Decimal("0.6"),
                         average_cost=Decimal("0.02"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("0.6")
        assert item.sku in {r["sku"] for r in report["ambiguous"]}

    def test_each_item_is_untouched(self, db, make_product, migration):
        """An EA / EA item with equal costs is correct and is not in scope."""
        item = make_product(item_type="component", standard_cost=Decimal("5"),
                            average_cost=Decimal("5"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("5")
        assert item.sku not in {r["sku"] for r in report["repaired"]}

    def test_running_twice_changes_nothing_more(self, db, make_product, migration):
        """Idempotent: the second run leaves the repaired value alone."""
        item = _filament(make_product, standard_cost=Decimal("0.0127"),
                         average_cost=Decimal("0.0127"))
        _run(db, migration)
        assert item.standard_cost == Decimal("12.7")

        second = _run(db, migration)
        assert item.standard_cost == Decimal("12.7")
        assert item.sku not in {r["sku"] for r in second["repaired"]}


class TestFixMaterialPurchaseUnits:
    """Materials the item form saved as G / EA / 1000."""

    def test_g_ea_1000_material_becomes_kg(self, db, make_product, migration):
        """Purchase unit EA becomes KG; factor and costs are unchanged."""
        item = make_product(item_type="material", unit="G", purchase_uom="EA",
                            purchase_factor=Decimal("1000"), is_raw_material=True,
                            standard_cost=Decimal("22.99"))
        _run(db, migration)

        assert item.purchase_uom == "KG"
        assert item.purchase_factor == Decimal("1000")
        assert item.standard_cost == Decimal("22.99")

    def test_flipped_g_ea_1000_material_is_also_repaired(self, db, make_product, migration):
        """Unit fixed first, then its per-gram standard cost is scaled back up."""
        item = make_product(item_type="material", unit="G", purchase_uom="EA",
                            purchase_factor=Decimal("1000"), is_raw_material=True,
                            standard_cost=Decimal("0.02"), average_cost=Decimal("0.02"))
        _run(db, migration)

        assert item.purchase_uom == "KG"
        assert item.standard_cost == Decimal("20")

    def test_non_material_bought_by_the_each_is_untouched(self, db, make_product, migration):
        """A supply stocked in G and bought by the EA is not a filament: leave it."""
        item = make_product(item_type="supply", unit="G", purchase_uom="EA",
                            purchase_factor=Decimal("1000"))
        _run(db, migration)

        assert item.purchase_uom == "EA"

    def test_material_with_another_factor_is_untouched(self, db, make_product, migration):
        """A 500 g spool bought by the EA is a real pack, not the form default."""
        item = make_product(item_type="material", unit="G", purchase_uom="EA",
                            purchase_factor=Decimal("500"), is_raw_material=True)
        _run(db, migration)

        assert item.purchase_uom == "EA"
