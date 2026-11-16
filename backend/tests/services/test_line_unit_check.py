"""
The unit on a BOM line or a routing material line is checked in one place.

The request schemas only tidy the code. Every writer that takes a unit from a
request asks ``app.services.line_units.unit_for_line``, which asks the unit
table. These tests go through each writer.
"""
from decimal import Decimal as D

import pytest
from fastapi import HTTPException

from app.models.bom import BOMLine
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.uom import UnitOfMeasure
from app.schemas.bom import BOMCreate, BOMLineCreate, BOMLineUpdate, BOMResponse
from app.services import bom_management_service as boms
from app.services import routing_service as routings
from app.services.line_units import unit_for_line

# The list both schemas held until now. A line in any of these must still be accepted.
_OLD_SIXTEEN = ["EA", "G", "KG", "LB", "OZ", "M", "MM", "CM", "IN", "FT", "L", "ML", "PK", "BOX", "ROLL", "HR"]


def _refused(call, *said):
    """Run ``call`` and return the detail of the 400 it must raise."""
    with pytest.raises(HTTPException) as caught:
        call()
    assert caught.value.status_code == 400
    for words in said:
        assert words in caught.value.detail
    return caught.value.detail


@pytest.fixture
def operation(db, make_product, make_work_center):
    """A routing operation to hang materials on."""
    made = make_product()
    routing = Routing(product_id=made.id, code=f"RT-{made.id}", name="Routing", is_active=True)
    db.add(routing)
    db.flush()
    step = RoutingOperation(routing_id=routing.id, work_center_id=make_work_center().id, operation_code="PRINT",
                            operation_name="Print", sequence=10, run_time_minutes=D("30"))
    db.add(step)
    db.flush()
    return step


@pytest.fixture
def filament(make_product):
    return make_product(item_type="material", unit="G", purchase_uom="KG", purchase_factor=D("1000"))


class TestUnitForLine:
    def test_no_unit_means_the_components_stock_unit(self, db, filament):
        assert unit_for_line(db, None, filament) == "G"
        assert unit_for_line(db, "  ", filament) == "G"

    def test_a_unit_in_the_table_comes_back_tidy(self, db, filament):
        assert unit_for_line(db, " kg ", filament) == "KG"

    def test_a_known_spelling_is_read_as_its_code(self, db, filament):
        assert unit_for_line(db, "pcs", filament) == "EA"

    @pytest.mark.parametrize("code", _OLD_SIXTEEN)
    def test_every_code_the_old_list_accepted_is_accepted(self, db, filament, code):
        assert unit_for_line(db, code, filament) == code

    def test_a_unit_outside_the_old_list_is_accepted_when_the_table_has_it(self, db, filament):
        assert unit_for_line(db, "sheet", filament) == "SHEET"
        assert unit_for_line(db, "CM2", filament) == "CM2"

    def test_an_unknown_unit_is_refused_by_name(self, db, filament):
        _refused(lambda: unit_for_line(db, "scoop", filament), "Unknown unit 'SCOOP'", "Units")

    def test_a_unit_that_is_switched_off_is_refused(self, db, filament):
        db.add(UnitOfMeasure(code="SCOOP", name="Scoop", symbol="scoop", uom_class="pack",
                             to_base_factor=D("1"), active=False))
        db.flush()
        _refused(lambda: unit_for_line(db, "scoop", filament), "'SCOOP' is switched off")

    def test_the_unit_a_line_already_holds_can_be_sent_back(self, db, filament):
        """Editing the quantity of a line saved before its unit left the table."""
        assert unit_for_line(db, "scoop", filament, current="SCOOP") == "SCOOP"
        _refused(lambda: unit_for_line(db, "ladle", filament, current="SCOOP"), "LADLE")


class TestBomWriters:
    def _bom(self, make_product, make_bom, component, unit="G"):
        return make_bom(product_id=make_product().id,
                        lines=[{"component_id": component.id, "quantity": D("50"), "unit": unit}])

    def test_add_bom_line_refuses_an_unknown_unit(self, db, make_product, make_bom, filament):
        bom = make_bom(product_id=make_product().id)
        line = BOMLineCreate(component_id=filament.id, quantity=D("5"), unit="scoop")
        _refused(lambda: boms.add_bom_line(db, bom.id, line), "SCOOP")
        assert db.query(BOMLine).filter(BOMLine.bom_id == bom.id).count() == 0

    @pytest.mark.parametrize("code", _OLD_SIXTEEN + ["SHEET"])
    def test_add_bom_line_accepts_a_unit_in_the_table(self, db, make_product, make_bom, code):
        bom = make_bom(product_id=make_product().id)
        part = make_product(item_type="component", unit="EA")
        saved = boms.add_bom_line(db, bom.id, BOMLineCreate(component_id=part.id, quantity=D("5"), unit=code.lower()))
        assert saved["unit"] == code

    def test_add_bom_line_with_no_unit_gets_the_stock_unit(self, db, make_product, make_bom, filament):
        bom = make_bom(product_id=make_product().id)
        saved = boms.add_bom_line(db, bom.id, BOMLineCreate(component_id=filament.id, quantity=D("5")))
        assert saved["unit"] == "G"

    def test_update_bom_line_refuses_an_unknown_unit(self, db, make_product, make_bom, filament):
        bom = self._bom(make_product, make_bom, filament)
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        _refused(lambda: boms.update_bom_line(db, bom.id, line.id, BOMLineUpdate(unit="scoop")), "SCOOP")
        db.expire_all()
        assert line.unit == "G"

    def test_update_bom_line_accepts_a_unit_in_the_table(self, db, make_product, make_bom, filament):
        bom = self._bom(make_product, make_bom, filament)
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        assert boms.update_bom_line(db, bom.id, line.id, BOMLineUpdate(unit="kg"))["unit"] == "KG"

    def test_update_bom_line_with_the_unit_cleared_gets_the_stock_unit(self, db, make_product, make_bom, filament):
        bom = self._bom(make_product, make_bom, filament, unit="KG")
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        assert boms.update_bom_line(db, bom.id, line.id, BOMLineUpdate(unit=None))["unit"] == "G"

    def test_a_line_holding_a_unit_the_table_lost_can_still_be_edited(self, db, make_product, make_bom, filament):
        bom = self._bom(make_product, make_bom, filament, unit="SCOOP")
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        saved = boms.update_bom_line(db, bom.id, line.id, BOMLineUpdate(quantity=D("75"), unit="SCOOP"))
        assert (saved["unit"], D(str(saved["quantity"]))) == ("SCOOP", D("75"))

    def test_a_unit_the_table_lost_does_not_follow_the_line_to_another_component(self, db, make_product, make_bom,
                                                                                filament):
        """Sending the held unit back is allowed only while the line stays on its component."""
        bom = self._bom(make_product, make_bom, filament, unit="SCOOP")
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        tube = make_product(item_type="component", unit="M")
        move = BOMLineUpdate(component_id=tube.id, unit="SCOOP")
        _refused(lambda: boms.update_bom_line(db, bom.id, line.id, move), "SCOOP")
        db.expire_all()
        assert line.component_id == filament.id
        # Naming the component it is already on is not a move.
        stay = BOMLineUpdate(component_id=filament.id, unit="SCOOP", quantity=D("60"))
        assert boms.update_bom_line(db, bom.id, line.id, stay)["unit"] == "SCOOP"

    def test_changing_the_component_without_a_unit_takes_the_new_components_unit(self, db, make_product, make_bom,
                                                                                 filament):
        bom = self._bom(make_product, make_bom, filament)
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        tube = make_product(item_type="component", unit="M")
        assert boms.update_bom_line(db, bom.id, line.id, BOMLineUpdate(component_id=tube.id))["unit"] == "M"

    def test_create_bom_refuses_an_unknown_unit(self, db, make_product, filament):
        made = make_product()
        request = BOMCreate(product_id=made.id, lines=[
            BOMLineCreate(component_id=filament.id, quantity=D("5"), unit="scoop")])
        _refused(lambda: boms.create_bom(db, request), "SCOOP")

    def test_create_bom_saves_tidy_units_and_fills_in_a_missing_one(self, db, make_product, filament):
        made, part = make_product(), make_product(item_type="component", unit="EA")
        created = boms.create_bom(db, BOMCreate(product_id=made.id, lines=[
            BOMLineCreate(component_id=filament.id, quantity=D("5")),
            BOMLineCreate(component_id=part.id, quantity=D("2"), unit="pcs"),
        ]))
        assert {line["component_id"]: line["unit"] for line in created["lines"]} == {filament.id: "G", part.id: "EA"}

    def test_adding_to_an_existing_bom_refuses_an_unknown_unit_on_a_new_line(self, db, make_product, make_bom,
                                                                            filament):
        """create_bom adds to the item's active BOM when it has one. That branch is checked too."""
        made = make_product()
        make_bom(product_id=made.id)
        request = BOMCreate(product_id=made.id, lines=[
            BOMLineCreate(component_id=filament.id, quantity=D("5"), unit="scoop")])
        _refused(lambda: boms.create_bom(db, request), "SCOOP")

    def test_adding_to_an_existing_bom_refuses_an_unknown_unit_on_a_line_it_already_has(
            self, db, make_product, make_bom, filament):
        made = make_product()
        bom = make_bom(product_id=made.id, lines=[{"component_id": filament.id, "quantity": D("5"), "unit": "G"}])
        request = BOMCreate(product_id=made.id, lines=[
            BOMLineCreate(component_id=filament.id, quantity=D("5"), unit="scoop")])
        _refused(lambda: boms.create_bom(db, request), "SCOOP")
        # Refused before anything on the line was changed: the quantity was not added either.
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        assert (line.unit, line.quantity) == ("G", D("5"))


class TestAddingToALineThatExists:
    """create_bom adds to the item's active BOM. A component already on it gets the new quantity added to its line.

    The line keeps its unit. Adding the bare numbers saved 500 G plus 1 KG as 501 KG.
    """

    def _existing(self, make_product, make_bom, component, quantity, unit):
        made = make_product()
        bom = make_bom(product_id=made.id,
                       lines=[{"component_id": component.id, "quantity": D(quantity), "unit": unit}])
        return made, bom

    def _add(self, db, made, component, quantity, unit=None):
        return boms.create_bom(db, BOMCreate(product_id=made.id, lines=[
            BOMLineCreate(component_id=component.id, quantity=D(quantity), unit=unit)]))

    def _line(self, db, bom):
        db.expire_all()
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        return line.quantity, line.unit

    def test_a_quantity_in_another_unit_is_brought_into_the_lines_unit(self, db, make_product, make_bom, filament):
        made, bom = self._existing(make_product, make_bom, filament, "500", "G")
        self._add(db, made, filament, "1", "kg")
        assert self._line(db, bom) == (D("1500"), "G")

    def test_a_unit_of_the_installs_own_converts_by_its_factor(self, db, make_product, make_bom):
        each = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "EA").one()
        db.add(UnitOfMeasure(code="PAIR", name="Pair", symbol="pair", uom_class="quantity",
                             base_unit_id=each.id, to_base_factor=D("2")))
        db.flush()
        part = make_product(item_type="component", unit="EA")
        made, bom = self._existing(make_product, make_bom, part, "10", "EA")
        self._add(db, made, part, "3", "pair")
        assert self._line(db, bom) == (D("16"), "EA")

    def test_the_same_unit_or_no_unit_adds_the_number(self, db, make_product, make_bom, filament):
        made, bom = self._existing(make_product, make_bom, filament, "500", "G")
        self._add(db, made, filament, "25", "g")
        self._add(db, made, filament, "25")
        assert self._line(db, bom) == (D("550"), "G")

    def test_a_unit_the_table_cannot_convert_is_refused_and_the_line_is_untouched(self, db, make_product, make_bom):
        part = make_product(item_type="component", unit="EA")
        made, bom = self._existing(make_product, make_bom, part, "10", "EA")
        said = _refused(lambda: self._add(db, made, part, "1", "box"),
                        "already on the BOM in EA", "Give the quantity in EA")
        assert "BOX" in said
        assert self._line(db, bom) == (D("10"), "EA")

    def test_a_line_holding_a_unit_the_table_lost_takes_a_quantity_in_that_unit(self, db, make_product, make_bom,
                                                                               filament):
        made, bom = self._existing(make_product, make_bom, filament, "5", "SCOOP")
        self._add(db, made, filament, "2", "scoop")
        assert self._line(db, bom) == (D("7"), "SCOOP")
        _refused(lambda: self._add(db, made, filament, "1", "kg"), "already on the BOM in SCOOP")


class TestRoutingWriters:
    def test_add_operation_material_refuses_an_unknown_unit(self, db, operation, filament):
        data = {"component_id": filament.id, "quantity": D("37"), "unit": "SCOOP"}
        _refused(lambda: routings.add_operation_material(db, operation.id, data=data), "SCOOP")
        assert db.query(RoutingOperationMaterial).filter(
            RoutingOperationMaterial.routing_operation_id == operation.id).count() == 0

    @pytest.mark.parametrize("code", _OLD_SIXTEEN + ["SHEET"])
    def test_add_operation_material_accepts_a_unit_in_the_table(self, db, operation, make_product, code):
        part = make_product(item_type="component", unit="EA")
        saved = routings.add_operation_material(
            db, operation.id, data={"component_id": part.id, "quantity": D("1"), "unit": code})
        assert saved.unit == code

    def test_a_routing_material_saved_with_no_unit_gets_the_stock_unit(self, db, operation, filament):
        """It used to get EA, which does not convert to grams."""
        saved = routings.add_operation_material(
            db, operation.id, data={"component_id": filament.id, "quantity": D("37"), "unit": None})
        assert saved.unit == "G"

    def test_update_operation_material_refuses_an_unknown_unit(self, db, operation, filament):
        saved = routings.add_operation_material(
            db, operation.id, data={"component_id": filament.id, "quantity": D("37"), "unit": "G"})
        _refused(lambda: routings.update_operation_material(db, saved.id, data={"unit": "SCOOP"}), "SCOOP")
        db.expire_all()
        assert saved.unit == "G"

    def test_update_operation_material_accepts_a_unit_in_the_table(self, db, operation, filament):
        saved = routings.add_operation_material(
            db, operation.id, data={"component_id": filament.id, "quantity": D("37"), "unit": "G"})
        assert routings.update_operation_material(db, saved.id, data={"unit": "KG"}).unit == "KG"

    def test_update_operation_material_with_the_unit_cleared_gets_the_stock_unit(self, db, operation, filament):
        saved = routings.add_operation_material(
            db, operation.id, data={"component_id": filament.id, "quantity": D("37"), "unit": "KG"})
        assert routings.update_operation_material(db, saved.id, data={"unit": None}).unit == "G"

    def test_changing_the_component_without_a_unit_takes_the_new_components_unit(self, db, operation, make_product,
                                                                                 filament):
        """As a BOM line does. It used to keep the old unit: grams on a part stocked by the metre."""
        saved = routings.add_operation_material(
            db, operation.id, data={"component_id": filament.id, "quantity": D("37"), "unit": "G"})
        tube = make_product(item_type="component", unit="M")
        assert routings.update_operation_material(db, saved.id, data={"component_id": tube.id}).unit == "M"

    def test_moving_a_line_to_another_component_costs_the_routing_with_the_new_one(self, db, operation,
                                                                                   make_product):
        """The stored routing total has to come from the component the line was moved to."""
        cheap = make_product(item_type="component", unit="EA", standard_cost=D("2"))
        dear = make_product(item_type="component", unit="EA", standard_cost=D("5"))
        saved = routings.add_operation_material(
            db, operation.id, data={"component_id": cheap.id, "quantity": D("3"), "unit": "EA"})
        routing = db.get(Routing, operation.routing_id)
        before = routing.total_cost
        for data in ({"component_id": dear.id}, {"component_id": cheap.id, "unit": "EA"}):
            moved = routings.update_operation_material(db, saved.id, data=dict(data))
            db.refresh(routing)
            assert moved.component.id == data["component_id"]
            expected = D("9") if data["component_id"] == dear.id else D("0")
            assert routing.total_cost - before == expected

    def test_a_line_holding_a_unit_the_table_lost_can_still_be_edited(self, db, operation, filament):
        material = RoutingOperationMaterial(routing_operation_id=operation.id, component_id=filament.id,
                                            quantity=D("37"), unit="SCOOP", scrap_factor=D("0"))
        db.add(material)
        db.flush()
        saved = routings.update_operation_material(db, material.id, data={"quantity": D("40"), "unit": "SCOOP"})
        assert (saved.unit, saved.quantity) == ("SCOOP", D("40"))

    def test_a_unit_the_table_lost_does_not_follow_the_line_to_another_component(self, db, operation, make_product,
                                                                                filament):
        material = RoutingOperationMaterial(routing_operation_id=operation.id, component_id=filament.id,
                                            quantity=D("37"), unit="SCOOP", scrap_factor=D("0"))
        db.add(material)
        db.flush()
        tube = make_product(item_type="component", unit="M")
        move = {"component_id": tube.id, "unit": "SCOOP"}
        _refused(lambda: routings.update_operation_material(db, material.id, data=move), "SCOOP")


class TestThroughTheApi:
    """The status a client sees, and that a response carries a unit outside the old list."""

    def test_a_bom_line_with_an_unknown_unit_is_a_400_that_names_it(self, client, db, make_product, make_bom,
                                                                    filament):
        bom = make_bom(product_id=make_product().id)
        response = client.post(f"/api/v1/admin/bom/{bom.id}/lines",
                               json={"component_id": filament.id, "quantity": "5", "unit": "scoop"})
        assert response.status_code == 400
        assert "SCOOP" in response.json()["detail"]

    def test_a_bom_line_in_a_unit_outside_the_old_list_is_saved_and_read_back(self, client, db, make_product,
                                                                             make_bom):
        """SHEET is in the unit table and was not one of the sixteen."""
        board = make_product(item_type="component", unit="EA")
        bom = make_bom(product_id=make_product().id)
        saved = client.post(f"/api/v1/admin/bom/{bom.id}/lines",
                            json={"component_id": board.id, "quantity": "2", "unit": "sheet"})
        assert saved.status_code == 201
        assert saved.json()["unit"] == "SHEET"
        read = client.get(f"/api/v1/admin/bom/{bom.id}")
        assert read.status_code == 200
        assert [line["unit"] for line in read.json()["lines"]] == ["SHEET"]

    def test_a_bom_whose_line_holds_a_unit_the_table_does_not_know_can_be_read_back(self, client, db, make_product,
                                                                                   make_bom, filament):
        """The response schema used to inherit the list and failed on such a line."""
        bom = make_bom(product_id=make_product().id,
                       lines=[{"component_id": filament.id, "quantity": D("5"), "unit": "Scoop"}])
        read = client.get(f"/api/v1/admin/bom/{bom.id}")
        assert read.status_code == 200
        assert [line["unit"] for line in read.json()["lines"]] == ["Scoop"]
        assert BOMResponse.model_validate(read.json()).lines[0].unit == "Scoop"

    def test_a_routing_material_with_no_unit_gets_the_stock_unit(self, client, db, operation, filament):
        response = client.post(f"/api/v1/routings/operations/{operation.id}/materials",
                               json={"component_id": filament.id, "quantity": "37"})
        assert response.status_code == 201
        assert response.json()["unit"] == "G"

    def test_a_routing_material_holding_a_unit_the_table_does_not_know_can_be_read_back(self, client, db, operation,
                                                                                       filament):
        """The response schema used to inherit the list and failed on such a line."""
        db.add(RoutingOperationMaterial(routing_operation_id=operation.id, component_id=filament.id,
                                        quantity=D("37"), unit="Scoop", scrap_factor=D("0")))
        db.flush()
        read = client.get(f"/api/v1/routings/operations/{operation.id}/materials")
        assert read.status_code == 200
        assert [line["unit"] for line in read.json()] == ["Scoop"]

    def test_choosing_default_as_a_bom_lines_unit_gives_the_stock_unit(self, client, db, make_product, make_bom,
                                                                       filament):
        """The BOM page's "Default" option sends no unit. That used to end in a server error."""
        bom = make_bom(product_id=make_product().id,
                       lines=[{"component_id": filament.id, "quantity": D("5"), "unit": "KG"}])
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).one()
        response = client.patch(f"/api/v1/admin/bom/{bom.id}/lines/{line.id}", json={"unit": None})
        assert response.status_code == 200
        # The quantity is not converted: the line now says 5 G.
        assert (response.json()["unit"], D(str(response.json()["quantity"]))) == ("G", D("5"))
