"""BOM costs are unit-correct, and every BOM money path gives the same figure.

standard_cost is per PURCHASE unit and average_cost / last_cost are per STOCK
unit. The BOM code used to take whichever it found first and treat it as
$/KG for a material and as per stock unit for everything else.
"""
from decimal import Decimal

import pytest

from app.services import bom_management_service as bom_service

D = Decimal

FILAMENT = {"item_type": "material", "unit": "G", "purchase_uom": "KG", "purchase_factor": D("1000")}
BOXED = {"item_type": "component", "unit": "EA", "purchase_uom": "BOX", "purchase_factor": D("12")}

# (name, component fields, line quantity, line unit, expected line cost)
CASES = [
    ("filament with a standard and an average cost",
     {**FILAMENT, "standard_cost": D("20"), "average_cost": D("0.02")}, "50", "G", 1.00),
    ("filament with only an average cost", {**FILAMENT, "average_cost": D("0.02")}, "50", "G", 1.00),
    ("filament with only a last cost", {**FILAMENT, "last_cost": D("0.02")}, "50", "G", 1.00),
    ("filament saved as G / EA / 1000 (the item form's shape)",
     {**FILAMENT, "purchase_uom": "EA", "standard_cost": D("20")}, "50", "G", 1.00),
    ("filament bought by the LB",
     {"item_type": "material", "unit": "G", "purchase_uom": "LB", "standard_cost": D("10")},
     "100", "G", 2.2046),
    ("filament bought by the OZ",
     {"item_type": "material", "unit": "G", "purchase_uom": "OZ", "standard_cost": D("1")},
     "100", "G", 3.5274),
    ("filament typed as a supply, with a standard cost",
     {**FILAMENT, "item_type": "supply", "standard_cost": D("20"), "average_cost": D("0.02")},
     "50", "G", 1.00),
    ("part bought by the box of 12", {**BOXED, "standard_cost": D("24")}, "3", "EA", 6.00),
    ("part bought by the box of 12, with an average cost too",
     {**BOXED, "standard_cost": D("24"), "average_cost": D("2")}, "3", "EA", 6.00),
    ("part bought by the box of 12, line written in boxes",
     {**BOXED, "standard_cost": D("24")}, "1", "BOX", 24.00),
    ("part bought by a pack with no pack size recorded",
     {**BOXED, "purchase_factor": None, "standard_cost": D("24")}, "3", "EA", 72.00),
    ("part bought and stocked by the each",
     {"item_type": "component", "standard_cost": D("5")}, "2", "EA", 10.00),
]


def _bom_with_one_line(db, make_product, make_bom, fields, quantity, unit):
    """A finished good whose BOM has one line of a component built from ``fields``."""
    component = make_product(**fields)
    finished = make_product()
    bom = make_bom(finished.id, lines=[{"component_id": component.id, "quantity": D(quantity), "unit": unit}])
    db.refresh(bom)
    return bom, component


class TestEveryPathAgrees:
    """One BOM line, costed through each BOM function that produces money."""

    @pytest.mark.parametrize("name,fields,quantity,unit,expected", CASES, ids=[c[0] for c in CASES])
    def test_line_cost_is_right_on_every_path(
        self, db, make_product, make_bom, name, fields, quantity, unit, expected
    ):
        """The flat total, the page line, the roll-ups and the explosion all agree."""
        bom, _ = _bom_with_one_line(db, make_product, make_bom, fields, quantity, unit)

        page_lines = bom_service.build_bom_response(bom, db)["lines"]
        exploded = bom_service.explode_bom(db, bom.id)
        figures = {
            "recalculate_bom_cost": bom_service.recalculate_bom_cost(bom, db),
            "BOM page line": sum(line["line_cost"] or 0 for line in page_lines),
            "calculate_rolled_up_cost": bom_service.calculate_rolled_up_cost(bom.id, db),
            "explode total": exploded["total_cost"],
            "explode leaf total": exploded["total_leaf_cost"],
            "cost roll-up": bom_service.get_cost_rollup(db, bom.id)["rolled_up_cost"],
        }
        recalculated = bom_service.recalculate_bom_endpoint(db, bom.id)
        figures["recalculate endpoint total"] = recalculated["new_cost"]
        figures["recalculate endpoint lines"] = sum(row["line_cost"] or 0 for row in recalculated["line_costs"])

        wrong = {path: float(value) for path, value in figures.items()
                 if float(value) != pytest.approx(expected, abs=0.0001)}
        assert wrong == {}, f"{name}: expected {expected}"


class TestPageLineFigures:
    """What the BOM page shows beside each line: the unit cost and its unit."""

    def _line(self, db, make_product, make_bom, fields, quantity, unit):
        """The BOM page's line dict for a one-line BOM."""
        bom, _ = _bom_with_one_line(db, make_product, make_bom, fields, quantity, unit)
        return bom_service.build_bom_response(bom, db)["lines"][0]

    def test_boxed_part_shows_the_cost_per_each(self, db, make_product, make_bom):
        """A part bought by the box is shown at its cost per stock unit."""
        line = self._line(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "3", "EA")
        assert line["component_cost"] == pytest.approx(2.00)
        assert line["component_cost_unit"] == "EA"

    def test_line_written_in_boxes_shows_the_cost_per_box(self, db, make_product, make_bom):
        """A line written in the purchase unit is shown per purchase unit."""
        line = self._line(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "1", "BOX")
        assert line["component_cost"] == pytest.approx(24.00)
        assert line["component_cost_unit"] == "BOX"

    def test_filament_with_only_an_average_cost_shows_per_kg(self, db, make_product, make_bom):
        """A material is shown per KG even when only its per-gram average is stored."""
        line = self._line(db, make_product, make_bom, {**FILAMENT, "average_cost": D("0.02")}, "50", "G")
        assert line["component_cost"] == pytest.approx(20.00)
        assert line["component_cost_unit"] == "KG"

    def test_supply_filament_shows_per_gram(self, db, make_product, make_bom):
        """A gram-stocked item that is not a material is shown per gram."""
        fields = {**FILAMENT, "item_type": "supply", "standard_cost": D("20")}
        line = self._line(db, make_product, make_bom, fields, "50", "G")
        assert line["component_cost"] == pytest.approx(0.02)
        assert line["component_cost_unit"] == "G"


class TestExplodedViewFigures:
    """The exploded view shows a unit cost that matches its quantity column."""

    def _row(self, db, make_product, make_bom, fields, quantity, unit):
        """The exploded view's row for a one-line BOM."""
        bom, _ = _bom_with_one_line(db, make_product, make_bom, fields, quantity, unit)
        return bom_service.explode_bom(db, bom.id)["lines"][0]

    def test_line_written_in_boxes_shows_the_cost_per_box(self, db, make_product, make_bom):
        """1 BOX at 24.00 a box reads 1 x 24.00 = 24.00, not 1 x 2.00."""
        row = self._row(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "1", "BOX")
        assert row["unit_cost"] == pytest.approx(24.00)
        assert row["line_cost"] == pytest.approx(24.00)

    def test_line_written_in_the_stock_unit_shows_the_cost_per_each(self, db, make_product, make_bom):
        """3 EA of a part bought by the box reads 3 x 2.00 = 6.00."""
        row = self._row(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "3", "EA")
        assert row["unit_cost"] == pytest.approx(2.00)
        assert row["line_cost"] == pytest.approx(6.00)


class TestShortagePurchase:
    """The purchase the BOM page suggests for a line that is short."""

    def _line(self, db, make_product, make_bom, fields, quantity, unit):
        """The BOM page's line dict for a one-line BOM whose component has no stock."""
        bom, _ = _bom_with_one_line(db, make_product, make_bom, fields, quantity, unit)
        return bom_service.build_bom_response(bom, db)["lines"][0]

    def test_filament_shortage_is_ordered_by_the_kg(self, db, make_product, make_bom):
        """500 g short is 0.5 KG at the per-KG price, not 500 KG."""
        line = self._line(db, make_product, make_bom, {**FILAMENT, "average_cost": D("0.02")}, "500", "G")
        assert line["shortage"] == pytest.approx(500)
        assert line["suggested_purchase"] == {
            "quantity": pytest.approx(0.5), "unit": "KG", "unit_cost": pytest.approx(20.00),
        }

    def test_boxed_part_shortage_is_ordered_in_the_stock_unit(self, db, make_product, make_bom):
        """Receiving does not apply pack sizes yet, so a pack item is ordered by the each."""
        line = self._line(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "3", "EA")
        assert line["suggested_purchase"] == {
            "quantity": pytest.approx(3), "unit": "EA", "unit_cost": pytest.approx(2.00),
        }

    def test_line_written_in_boxes_is_short_by_the_each(self, db, make_product, make_bom):
        """A line of 1 BOX with nothing in stock is short 12 EA."""
        line = self._line(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "1", "BOX")
        assert line["shortage"] == pytest.approx(12)

    def test_line_that_is_not_short_suggests_nothing(self, db, make_product, make_bom):
        """No suggested purchase when the quantity is zero."""
        line = self._line(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "0", "EA")
        assert line["suggested_purchase"] is None


class TestThroughTheApi:
    """The same figures as they leave GET /api/v1/admin/bom/{id}."""

    def test_page_line_carries_the_cost_unit_and_the_suggested_purchase(
        self, db, client, make_product, make_bom
    ):
        """The response schema keeps component_cost_unit and suggested_purchase."""
        bom, _ = _bom_with_one_line(
            db, make_product, make_bom, {**FILAMENT, "average_cost": D("0.02")}, "500", "G"
        )

        response = client.get(f"/api/v1/admin/bom/{bom.id}")

        assert response.status_code == 200
        line = response.json()["lines"][0]
        assert float(line["component_cost"]) == pytest.approx(20.00)
        assert line["component_cost_unit"] == "KG"
        assert float(line["line_cost"]) == pytest.approx(10.00)
        assert line["shortage"] == pytest.approx(500)
        assert line["suggested_purchase"] == {
            "quantity": pytest.approx(0.5), "unit": "KG", "unit_cost": pytest.approx(20.00),
        }
