"""BOM costs are unit-correct, and every BOM money path gives the same figure.

standard_cost is per PURCHASE unit and average_cost / last_cost are per STOCK
unit. The BOM code used to take whichever it found first and treat it as
$/KG for a material and as per stock unit for everything else.
"""
from decimal import Decimal

import pytest

from app.models.manufacturing import Routing
from app.models.uom import UnitOfMeasure
from app.services import bom_management_service as bom_service

D = Decimal

FILAMENT = {"item_type": "material", "unit": "G", "purchase_uom": "KG", "purchase_factor": D("1000")}
KG_STOCKED = {"item_type": "material", "unit": "KG", "purchase_uom": "KG"}
BOXED = {"item_type": "component", "unit": "EA", "purchase_uom": "BOX", "purchase_factor": D("12")}

# (name, component fields, line quantity, line unit, scrap %, expected line cost)
CASES = [
    ("filament with a standard and an average cost",
     {**FILAMENT, "standard_cost": D("20"), "average_cost": D("0.02")}, "50", "G", 0, 1.00),
    ("filament with only an average cost", {**FILAMENT, "average_cost": D("0.02")}, "50", "G", 0, 1.00),
    ("filament with only a last cost", {**FILAMENT, "last_cost": D("0.02")}, "50", "G", 0, 1.00),
    ("filament with only an average cost, line written in KG",
     {**FILAMENT, "average_cost": D("0.02")}, "0.05", "KG", 0, 1.00),
    ("filament saved as G / EA / 1000 (the item form's shape)",
     {**FILAMENT, "purchase_uom": "EA", "standard_cost": D("20")}, "50", "G", 0, 1.00),
    ("filament stocked in KG with only a per-gram average cost",
     {**KG_STOCKED, "average_cost": D("0.02")}, "50", "G", 0, 1.00),
    ("filament stocked in KG with only a per-gram average cost, line written in KG",
     {**KG_STOCKED, "average_cost": D("0.02")}, "0.05", "KG", 0, 1.00),
    # Known limit, unchanged: a material's standard cost is read as $/KG whatever
    # its purchase unit, so this is not converted from $/LB.
    ("filament bought by the LB keeps its standard cost read per KG",
     {"item_type": "material", "unit": "G", "purchase_uom": "LB", "standard_cost": D("10")},
     "100", "G", 0, 1.00),
    ("material stocked by the each with only an average cost",
     {"item_type": "material", "unit": "EA", "purchase_uom": "EA", "average_cost": D("5")},
     "1", "EA", 0, 5.00),
    ("filament typed as a supply, with a standard cost",
     {**FILAMENT, "item_type": "supply", "standard_cost": D("20"), "average_cost": D("0.02")},
     "50", "G", 0, 1.00),
    ("part bought by the box of 12", {**BOXED, "standard_cost": D("24")}, "3", "EA", 0, 6.00),
    ("part bought by the box of 12, with an average cost too",
     {**BOXED, "standard_cost": D("24"), "average_cost": D("2")}, "3", "EA", 0, 6.00),
    ("part bought by the box of 12, with 10% scrap",
     {**BOXED, "standard_cost": D("24")}, "3", "EA", 10, 6.60),
    ("part bought by the box of 12, line written in boxes",
     {**BOXED, "standard_cost": D("24")}, "1", "BOX", 0, 24.00),
    ("part bought by a pack with no pack size recorded",
     {**BOXED, "purchase_factor": None, "standard_cost": D("24")}, "3", "EA", 0, 72.00),
    ("part bought and stocked by the each",
     {"item_type": "component", "standard_cost": D("5")}, "2", "EA", 0, 10.00),
    ("line in a unit that cannot be converted is multiplied as it stands",
     {"item_type": "component", "standard_cost": D("5")}, "2", "HR", 0, 10.00),
]


def _bom_with_one_line(db, make_product, make_bom, fields, quantity, unit, scrap=0):
    """A finished good whose BOM has one line of a component built from ``fields``."""
    component = make_product(**fields)
    finished = make_product()
    bom = make_bom(finished.id, lines=[{"component_id": component.id, "quantity": D(quantity), "unit": unit}])
    db.refresh(bom)
    if scrap:
        bom.lines[0].scrap_factor = D(scrap)
        db.flush()
    return bom, component


def _figures(db, bom):
    """The cost of ``bom`` from each BOM function that produces money."""
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
    return figures


class TestEveryPathAgrees:
    """One BOM line, costed through each BOM function that produces money."""

    @pytest.mark.parametrize("name,fields,quantity,unit,scrap,expected", CASES, ids=[c[0] for c in CASES])
    def test_line_cost_is_right_on_every_path(
        self, db, make_product, make_bom, name, fields, quantity, unit, scrap, expected
    ):
        """The flat total, the page line, the roll-ups and the explosion all agree."""
        bom, _ = _bom_with_one_line(db, make_product, make_bom, fields, quantity, unit, scrap)

        wrong = {path: float(value) for path, value in _figures(db, bom).items()
                 if float(value) != pytest.approx(expected, abs=0.0001)}
        assert wrong == {}, f"{name}: expected {expected}"


class TestMadeComponents:
    """A made component's standard cost is what Recost wrote: per stock unit."""

    def _made_with_routing(self, db, make_product, **fields):
        """A component that has its own active routing, so Recost owns its standard cost."""
        component = make_product(item_type="component", procurement_type="make", **fields)
        db.add(Routing(product_id=component.id, code=f"RTG-{component.sku}", name="Make", is_active=True, version=1))
        db.flush()
        return component

    def _figures_for_line(self, db, make_product, make_bom, component, quantity, unit):
        """Every money path for a one-line BOM that uses ``component``."""
        finished = make_product()
        bom = make_bom(finished.id, lines=[{"component_id": component.id, "quantity": D(quantity), "unit": unit}])
        db.refresh(bom)
        return _figures(db, bom)

    def test_made_component_with_a_larger_purchase_unit_is_not_divided(self, db, make_product, make_bom):
        """Stocked by the inch, purchase unit FT: 24.00 an inch stays 24.00, not 2.00."""
        made = self._made_with_routing(db, make_product, unit="IN", purchase_uom="FT", standard_cost=D("24"))
        figures = self._figures_for_line(db, make_product, make_bom, made, "1", "IN")
        wrong = {path: float(value) for path, value in figures.items()
                 if float(value) != pytest.approx(24.00, abs=0.0001)}
        assert wrong == {}

    def test_made_blend_copied_from_a_filament_is_not_divided(self, db, make_product, make_bom):
        """A made item stocked in G that kept purchase unit KG: 0.05 a gram x 50 G = 2.50."""
        made = self._made_with_routing(
            db, make_product, unit="G", purchase_uom="KG", purchase_factor=D("1000"), standard_cost=D("0.05"),
        )
        figures = self._figures_for_line(db, make_product, make_bom, made, "50", "G")
        wrong = {path: float(value) for path, value in figures.items()
                 if float(value) != pytest.approx(2.50, abs=0.0001)}
        assert wrong == {}

    def test_bought_component_with_the_same_units_is_still_divided(self, db, make_product, make_bom):
        """With no BOM or routing of its own, 24.00 a foot is 2.00 an inch."""
        bought = make_product(item_type="component", unit="IN", purchase_uom="FT", standard_cost=D("24"))
        figures = self._figures_for_line(db, make_product, make_bom, bought, "1", "IN")
        wrong = {path: float(value) for path, value in figures.items()
                 if float(value) != pytest.approx(2.00, abs=0.0001)}
        assert wrong == {}


class TestLineInThePurchaseUnit:
    """A line written in the component's purchase unit uses the item's pack size."""

    def test_a_unit_table_row_for_the_pack_does_not_override_the_pack_size(
        self, db, make_product, make_bom
    ):
        """BOX set up in the unit table as 1 EA must not turn 1 BOX of 12 into 1 EA.

        The test database starts with BOX as a pack, which the table never
        converts. An install can still have filed it as a counting unit, so
        the test files it that way itself.
        """
        each = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "EA").one()
        box = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "BOX").one()
        box.uom_class, box.base_unit_id, box.to_base_factor = "quantity", each.id, D("1")
        db.flush()
        bom, _ = _bom_with_one_line(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "1", "BOX")

        wrong = {path: float(value) for path, value in _figures(db, bom).items()
                 if float(value) != pytest.approx(24.00, abs=0.0001)}
        assert wrong == {}

    def test_line_written_in_boxes_is_short_by_the_each(self, db, make_product, make_bom):
        """A line of 1 BOX with nothing in stock is short 12 EA."""
        bom, _ = _bom_with_one_line(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "1", "BOX")
        line = bom_service.build_bom_response(bom, db)["lines"][0]
        assert line["shortage"] == pytest.approx(12)


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

    def test_line_that_cannot_be_converted_is_labelled_with_the_stock_unit(self, db, make_product, make_bom):
        """A cost that was not converted to the line unit keeps the stock unit's label."""
        fields = {"item_type": "component", "standard_cost": D("5")}
        line = self._line(db, make_product, make_bom, fields, "2", "HR")
        assert line["component_cost"] == pytest.approx(5.00)
        assert line["component_cost_unit"] == "EA"


class TestExplodedViewFigures:
    """The exploded view shows a unit cost that matches its quantity column."""

    def _row(self, db, make_product, make_bom, fields, quantity, unit):
        """The exploded view's row for a one-line BOM."""
        bom, _ = _bom_with_one_line(db, make_product, make_bom, fields, quantity, unit)
        return bom_service.explode_bom(db, bom.id)["lines"][0]

    def test_line_written_in_boxes_shows_the_cost_per_box(self, db, make_product, make_bom):
        """1 BOX at 24.00 a box reads 1 x 24.00 = 24.00, and says it is per BOX."""
        row = self._row(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "1", "BOX")
        assert row["unit_cost"] == pytest.approx(24.00)
        assert row["line_cost"] == pytest.approx(24.00)
        assert (row["unit"], row["unit_cost_unit"]) == ("BOX", "BOX")

    def test_line_written_in_the_stock_unit_shows_the_cost_per_each(self, db, make_product, make_bom):
        """3 EA of a part bought by the box reads 3 x 2.00 = 6.00, per EA."""
        row = self._row(db, make_product, make_bom, {**BOXED, "standard_cost": D("24")}, "3", "EA")
        assert row["unit_cost"] == pytest.approx(2.00)
        assert row["line_cost"] == pytest.approx(6.00)
        assert (row["unit"], row["unit_cost_unit"]) == ("EA", "EA")

    def test_material_row_says_its_cost_is_per_kg(self, db, make_product, make_bom):
        """A material's unit cost is per KG while its quantity is in grams."""
        row = self._row(db, make_product, make_bom, {**FILAMENT, "average_cost": D("0.02")}, "50", "G")
        assert row["unit_cost"] == pytest.approx(20.00)
        assert (row["unit"], row["unit_cost_unit"]) == ("G", "KG")


class TestThroughTheApi:
    """The same figures as they leave GET /api/v1/admin/bom/{id}."""

    def test_page_line_carries_the_cost_and_its_unit(self, db, client, make_product, make_bom):
        """The response schema keeps component_cost_unit beside the corrected cost."""
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
