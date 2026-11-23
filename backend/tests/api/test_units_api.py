"""
The unit endpoints any staff account can read, an item's own units, and the
unit rules on item create and update through the API.
"""
from decimal import Decimal as D

import pytest

from app.models.inventory import InventoryTransaction
from app.models.product import Product

UNITS = "/api/v1/units"
ITEMS = "/api/v1/items"


@pytest.fixture
def screw(make_product):
    return make_product(item_type="supply", unit="EA", purchase_uom="EA")


class TestUnitTable:
    def test_an_operator_can_read_it(self, unauthed_client, role_headers):
        response = unauthed_client.get(UNITS, headers=role_headers("operator"))
        assert response.status_code == 200
        rows = {row["code"]: row for row in response.json()}
        assert rows["KG"] == {"code": "KG", "name": "Kilogram", "symbol": "kg", "kind": "weight", "is_standard": True}
        assert rows["BOX"]["kind"] == "pack"

    def test_a_customer_cannot(self, unauthed_client, role_headers):
        assert unauthed_client.get(UNITS, headers=role_headers("customer")).status_code == 403

    def test_an_install_unit_is_not_standard(self, client, db):
        from app.models.uom import UnitOfMeasure
        db.add(UnitOfMeasure(code="TUB", name="Tub", symbol="tub", uom_class="pack", to_base_factor=1, active=True))
        db.flush()
        rows = {row["code"]: row for row in client.get(UNITS).json()}
        assert rows["TUB"]["is_standard"] is False


class TestItemUnits:
    def test_gram_filament_lists_the_weight_units(self, client, make_product):
        item = make_product(item_type="material", unit="G", purchase_uom="KG", purchase_factor=D("1000"))
        body = client.get(f"{ITEMS}/{item.id}/units").json()
        sizes = {row["unit_code"]: D(str(row["stock_units_per_unit"])) for row in body["units"]}
        assert body["stock_unit"] == "G" and body["purchase_unit"] == "KG"
        assert sizes["G"] == 1 and sizes["KG"] == 1000 and sizes["LB"] == D("453.59237")
        assert body["stock_unit_locked"] is False

    def test_a_box_of_12_is_set_listed_and_removed(self, client, db, screw):
        response = client.put(f"{ITEMS}/{screw.id}/units/box", json={"stock_units_per_unit": "12"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["own_units"] == [{"unit_code": "BOX", "stock_units_per_unit": "12.0000000000",
                                      "units_per_stock_unit": None}]
        assert {"unit_code": "BOX", "source": "item"}.items() <= next(
            row for row in body["units"] if row["unit_code"] == "BOX").items()
        assert body["stock_unit_locked"] is True

        response = client.delete(f"{ITEMS}/{screw.id}/units/BOX")
        assert response.status_code == 200, response.text
        assert response.json()["own_units"] == []

    def test_a_refused_unit_is_a_400_with_a_sentence(self, client, make_product):
        item = make_product(item_type="material", unit="G", purchase_uom="KG")
        response = client.put(f"{ITEMS}/{item.id}/units/KG", json={"stock_units_per_unit": "900"})
        assert response.status_code == 400
        assert "already converts KG to G" in response.json()["detail"]

    def test_an_unknown_item_is_a_404(self, client):
        assert client.get(f"{ITEMS}/999999999/units").status_code == 404


class TestCreateItem:
    def test_a_material_in_grams_is_bought_by_the_kg(self, client):
        response = client.post(ITEMS, json={"name": "PLA test", "item_type": "material", "unit": "G"})
        assert response.status_code == 201, response.text
        body = response.json()
        assert (body["unit"], body["purchase_uom"]) == ("G", "KG")
        item_id = body["id"]
        assert client.get(f"{ITEMS}/{item_id}/units").json()["purchase_unit"] == "KG"

    def test_a_material_counted_by_the_each_is_bought_by_the_each(self, client):
        body = client.post(ITEMS, json={"name": "Spool", "item_type": "material", "unit": "EA"}).json()
        assert (body["unit"], body["purchase_uom"]) == ("EA", "EA")

    def test_it_is_saved_with_its_units_in_one_request(self, client, db):
        response = client.post(ITEMS, json={
            "name": "Screw", "item_type": "supply", "unit": "EA", "purchase_uom": "BOX",
            "units": [{"unit_code": "BOX", "stock_units_per_unit": "100"}],
        })
        assert response.status_code == 201, response.text
        item = db.get(Product, response.json()["id"])
        assert item.purchase_factor == D("100")

    def test_an_unknown_unit_is_refused(self, client):
        response = client.post(ITEMS, json={"name": "X", "unit": "SPOONS"})
        assert response.status_code == 400
        assert "SPOONS" in response.json()["detail"]

    def test_a_bad_own_unit_saves_nothing(self, client, db):
        sku = "UNITAPI-ROLLBACK"
        response = client.post(ITEMS, json={
            "sku": sku, "name": "X", "unit": "EA", "units": [{"unit_code": "EA", "stock_units_per_unit": "2"}],
        })
        assert response.status_code == 400
        assert db.query(Product).filter(Product.sku == sku).first() is None


class TestUpdateItem:
    def test_a_locked_stock_unit_is_refused(self, client, db, make_product):
        item = make_product(item_type="material", unit="G", purchase_uom="KG")
        db.add(InventoryTransaction(product_id=item.id, transaction_type="receipt", quantity=D("1000")))
        db.flush()
        response = client.patch(f"{ITEMS}/{item.id}", json={"unit": "KG"})
        assert response.status_code == 400
        assert "cannot change from G to KG" in response.json()["detail"]

    def test_a_change_of_spelling_is_saved_as_it_was(self, client, db, make_product):
        item = make_product(item_type="material", unit="G", purchase_uom="KG")
        db.add(InventoryTransaction(product_id=item.id, transaction_type="receipt", quantity=D("1000")))
        db.flush()
        response = client.patch(f"{ITEMS}/{item.id}", json={"unit": "g", "name": "Renamed"})
        assert response.status_code == 200, response.text
        assert response.json()["unit"] == "G"

    def test_an_item_holding_an_unknown_unit_can_still_be_saved(self, client, make_product):
        item = make_product(unit="SPOONS", purchase_uom="SPOONS")
        response = client.patch(f"{ITEMS}/{item.id}", json={"unit": "SPOONS", "purchase_uom": "spoons", "name": "Y"})
        assert response.status_code == 200, response.text

    def test_an_unknown_purchase_unit_is_refused(self, client, screw):
        response = client.patch(f"{ITEMS}/{screw.id}", json={"purchase_uom": "CRATE"})
        assert response.status_code == 400
        assert "CRATE" in response.json()["detail"]

    def test_purchase_factor_follows_the_purchase_unit(self, client, db, screw):
        client.put(f"{ITEMS}/{screw.id}/units/BOX", json={"stock_units_per_unit": "12"})
        response = client.patch(f"{ITEMS}/{screw.id}", json={"purchase_uom": "BOX"})
        assert response.status_code == 200, response.text
        db.expire_all()
        assert db.get(Product, screw.id).purchase_factor == D("12")
