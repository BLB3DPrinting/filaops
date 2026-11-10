"""
Migration 105: repair standard costs a PO receipt rewrote per stock unit.

The migration's data functions take a connection, so they are run here against
real product rows inside the test transaction.
"""
import importlib.util
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.purchase_order import PurchaseOrderLine

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
        ("0.0200", "0.02", "flipped"),
        ("20.00", "0.02", "ok"),
        ("24.99", "0.02", "ok"),
        ("0.03", "0.02", "ambiguous"),
        ("0.0201", "0.02", "ambiguous"),
        ("0.6", "0.02", "ambiguous"),
        ("500", "0.02", "ambiguous"),
    ])
    def test_filament_cases(self, migration, standard, average, expected):
        """G stock bought by the KG: 1000 stock units per purchase unit. Only a
        standard cost exactly equal to the average counts as flipped."""
        assert migration.classify("G", "KG", Decimal("1000"), standard, average) == expected

    def test_close_ratio_is_never_enough(self, migration):
        """10 stock units per purchase unit, standard $4, average $2: a ratio of
        2 is not the sync's signature, so the item is reported, not repaired."""
        assert migration.classify("EA", "BOX", 10, "4", "2") == "ambiguous"

    def test_missing_costs_are_skipped(self, migration):
        """No standard or no average cost: nothing to compare."""
        assert migration.classify("G", "KG", 1000, None, "0.02") == "skip"
        assert migration.classify("G", "KG", 1000, "20", None) == "skip"
        assert migration.classify("G", "KG", 1000, "20", "0") == "skip"

    def test_same_unit_is_skipped(self, migration):
        """Bought and stocked in EA: equal costs are correct, not flipped."""
        assert migration.classify("EA", "EA", None, "5", "5") == "skip"

    def test_small_pack_equal_costs_are_reported_not_repaired(self, migration):
        """A box of 6 at $2 could be a real, if stale, per-box price."""
        assert migration.classify("EA", "BOX", 6, "2", "2") == "ambiguous"
        assert migration.classify("EA", "BOX", 6, "12", "2") == "ok"

    def test_count_synonym_pair_is_skipped(self, migration):
        """pcs stocked, EA bought: the same unit, so equal costs are correct."""
        assert migration.classify("pcs", "EA", None, "0.0575", "0.0575") == "skip"

    def test_pack_without_a_size(self, migration):
        """No pack size: nothing can be computed. Equal costs are still reported
        for a manual check; different costs are passed over."""
        assert migration.classify("EA", "BOX", None, "2", "2") == "ambiguous"
        assert migration.classify("EA", "BOX", None, "24", "2") == "skip"

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

    def test_near_but_not_equal_is_reported_and_untouched(self, db, make_product, migration):
        """standard 0.0300 against average 0.0200 was not written by the sync."""
        item = _filament(make_product, standard_cost=Decimal("0.03"),
                         average_cost=Decimal("0.02"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("0.03")
        assert item.sku in {r["sku"] for r in report["ambiguous"]}

    def test_item_with_an_active_bom_is_reported_and_untouched(
        self, db, make_product, make_bom, migration,
    ):
        """The sync never wrote to items with their own BOM, so an equal value
        there has another cause: report it, do not scale it."""
        item = _filament(make_product, standard_cost=Decimal("0.02"),
                         average_cost=Decimal("0.02"))
        component = make_product(item_type="supply", unit="EA")
        make_bom(product_id=item.id, lines=[
            {"component_id": component.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        report = _run(db, migration)

        assert item.standard_cost == Decimal("0.02")
        entry = next(r for r in report["ambiguous"] if r["sku"] == item.sku)
        assert "BOM or routing" in entry["reason"]

    def test_pack_with_no_size_and_equal_costs_is_reported(self, db, make_product, migration):
        """A supply stocked in G and bought by the EA with no pack size: equal
        costs cannot be scaled, but they are listed with the reason."""
        item = make_product(item_type="supply", unit="g", purchase_uom="EA",
                            standard_cost=Decimal("0.022"), average_cost=Decimal("0.022"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("0.022")
        entry = next(r for r in report["ambiguous"] if r["sku"] == item.sku)
        assert "no pack size" in entry["reason"]

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
    """Materials saved as G / EA / 1000: the item form's default, or a shop
    that really buys a 1000 g spool by the each. Only the item's own purchase
    history says which."""

    @pytest.fixture
    def g_ea_material(self, make_product):
        """Factory for a G / EA / 1000 material."""
        def _make(**kw):
            base = dict(item_type="material", unit="G", purchase_uom="EA",
                        purchase_factor=Decimal("1000"), is_raw_material=True)
            base.update(kw)
            return make_product(**base)
        return _make

    @pytest.fixture
    def po_line(self, db, make_vendor, make_purchase_order):
        """Factory that adds one purchase-order line for an item in a given unit."""
        def _add(product, purchase_unit):
            po = make_purchase_order(vendor_id=make_vendor().id, status="received")
            line = PurchaseOrderLine(
                purchase_order_id=po.id, line_number=1, product_id=product.id,
                quantity_ordered=Decimal("1"), quantity_received=Decimal("1"),
                purchase_unit=purchase_unit, unit_cost=Decimal("20"),
                line_total=Decimal("20"),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(line)
            db.flush()
            return line
        return _add

    def _fix(self, db, migration):
        """Run step 1 alone and return its report."""
        db.flush()
        report = migration.fix_material_purchase_units(db.connection())
        db.expire_all()
        return report

    def test_bought_by_the_kg_becomes_kg(self, db, g_ea_material, po_line, migration):
        """Purchase-order lines in KG: the purchase unit becomes KG; factor and
        costs are unchanged."""
        item = g_ea_material(standard_cost=Decimal("22.99"))
        po_line(item, "KG")
        report = self._fix(db, migration)

        assert item.purchase_uom == "KG"
        assert item.purchase_factor == Decimal("1000")
        assert item.standard_cost == Decimal("22.99")
        assert item.sku in report["changed"]

    def test_no_purchase_history_is_left_and_reported(self, db, g_ea_material, migration):
        """Nothing says how it is bought: leave it and list it."""
        item = g_ea_material()
        report = self._fix(db, migration)

        assert item.purchase_uom == "EA"
        entry = next(r for r in report["left"] if r["sku"] == item.sku)
        assert "no purchase-order lines in KG" in entry["reason"]

    def test_bought_by_the_each_is_left_and_reported(self, db, g_ea_material, po_line, migration):
        """A shop that buys 1000 g spools by the each keeps EA, even with a KG line too."""
        item = g_ea_material()
        po_line(item, "EA")
        po_line(item, "KG")
        report = self._fix(db, migration)

        assert item.purchase_uom == "EA"
        entry = next(r for r in report["left"] if r["sku"] == item.sku)
        assert "lines in EA" in entry["reason"]

    def test_only_gram_lines_is_left(self, db, g_ea_material, po_line, migration):
        """Lines in G do not show the item is bought by the KG."""
        item = g_ea_material()
        po_line(item, "G")
        self._fix(db, migration)

        assert item.purchase_uom == "EA"

    def test_flipped_standard_cost_is_repaired_whatever_the_unit(
        self, db, g_ea_material, migration,
    ):
        """Step 2 reads the 1000 from the factor, so a per-gram standard cost is
        scaled back up even when the purchase unit stays EA."""
        item = g_ea_material(standard_cost=Decimal("0.02"), average_cost=Decimal("0.02"))
        _run(db, migration)

        assert item.purchase_uom == "EA"
        assert item.standard_cost == Decimal("20")

    def test_non_material_bought_by_the_each_is_out_of_scope(self, db, make_product, migration):
        """A supply stocked in G and bought by the EA is not a filament: not even listed."""
        item = make_product(item_type="supply", unit="G", purchase_uom="EA",
                            purchase_factor=Decimal("1000"))
        report = self._fix(db, migration)

        assert item.purchase_uom == "EA"
        assert item.sku not in {r["sku"] for r in report["left"]}

    def test_material_with_another_factor_is_out_of_scope(self, db, g_ea_material, migration):
        """A 500 g spool bought by the EA is a real pack, not the form default."""
        item = g_ea_material(purchase_factor=Decimal("500"))
        report = self._fix(db, migration)

        assert item.purchase_uom == "EA"
        assert item.sku not in {r["sku"] for r in report["left"]}

    def test_report_lines_name_each_item(self, migration):
        """The upgrade log lists what changed and what was left, with the reason."""
        lines = [message for _, message in migration.unit_report_lines({
            "changed": ["MAT-A"],
            "left": [{"sku": "MAT-B", "reason": "it has no purchase-order lines in KG"}],
        })]
        assert any("MAT-A" in m and "EA -> KG" in m for m in lines)
        assert any("MAT-B" in m and "no purchase-order lines in KG" in m for m in lines)
        assert lines[-1].endswith("1 left for a manual check")


class TestLastCostFallback:
    """An item with no average cost: Recost used to copy its last cost across."""

    def test_stock_cost_prefers_average_then_last(self, migration):
        """Average cost when there is one, else last cost, else nothing."""
        assert migration.stock_cost(Decimal("0.02"), Decimal("0.03")) == (Decimal("0.02"), "average")
        assert migration.stock_cost(None, Decimal("0.03")) == (Decimal("0.03"), "last")
        assert migration.stock_cost(Decimal("0"), Decimal("0.03")) == (Decimal("0.03"), "last")
        assert migration.stock_cost(None, None) == (None, None)

    def test_standard_equal_to_last_cost_is_repaired(self, db, make_product, migration):
        """No average cost, standard 0.0250 equal to last cost 0.0250: becomes 25.00."""
        item = _filament(make_product, standard_cost=Decimal("0.025"),
                         last_cost=Decimal("0.025"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("25")
        entry = next(r for r in report["repaired"] if r["sku"] == item.sku)
        assert entry["basis"] == "last"

    def test_average_cost_wins_over_last_cost(self, db, make_product, migration):
        """Standard equals the last cost but not the average: not the sync's
        signature, so it is reported and left alone."""
        item = _filament(make_product, standard_cost=Decimal("0.025"),
                         average_cost=Decimal("0.02"), last_cost=Decimal("0.025"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("0.025")
        assert item.sku in {r["sku"] for r in report["ambiguous"]}

    def test_correct_standard_with_only_a_last_cost_is_untouched(self, db, make_product, migration):
        """Standard 25.00 against last cost 0.0250 is already per KG."""
        item = _filament(make_product, standard_cost=Decimal("25"),
                         last_cost=Decimal("0.025"))
        report = _run(db, migration)

        assert item.standard_cost == Decimal("25")
        assert item.sku not in {r["sku"] for r in report["repaired"]}


class TestReportLines:
    """The upgrade log is built from the repair report."""

    def test_every_entry_kind_becomes_a_line(self, db, make_product, migration):
        """A repaired item and a reported item each get a line naming the SKU."""
        repaired = _filament(make_product, standard_cost=Decimal("0.02"),
                             average_cost=Decimal("0.02"))
        reported = _filament(make_product, standard_cost=Decimal("0.6"),
                             average_cost=Decimal("0.02"))
        report = _run(db, migration)
        report = {
            "repaired": [r for r in report["repaired"] if r["sku"] == repaired.sku],
            "ambiguous": [r for r in report["ambiguous"] if r["sku"] == reported.sku],
        }

        messages = [message for _, message in migration.report_lines(report)]
        assert any(repaired.sku in m and "20.0000" in m for m in messages)
        assert any(reported.sku in m and "Check it by hand" in m for m in messages)
        assert messages[-1] == "105: repaired 1 standard cost(s); 1 left for a manual check"
