"""
The stock unit lock (R9) and the unit rules, through every writer that sets an
item's units: item update, product update, both CSV imports, and duplicates.

The lock itself is tested in test_item_unit_service.py. These tests check that
each writer goes through it, and that a refused unit changes nothing.
"""
import uuid
from decimal import Decimal as D

import pytest
from fastapi import HTTPException

from app.models.inventory import Inventory
from app.models.product import Product
from app.models.product_unit import ProductUnit
from app.services import data_import_service, item_service, product_service
from app.services import item_unit_service as units
from app.services.item_import_service import import_items_from_csv


def _sku(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _stock(db, product, on_hand=500):
    db.add(Inventory(product_id=product.id, location_id=1, on_hand_quantity=D(on_hand), allocated_quantity=D(0)))
    db.flush()


@pytest.fixture
def stocked_filament(db, make_product):
    item = make_product(sku=_sku("LOCK-FIL"), item_type="material", unit="G", purchase_uom="KG",
                        purchase_factor=D("1000"))
    _stock(db, item)
    return item


class TestProductUpdate:
    def test_a_locked_unit_is_refused(self, db, stocked_filament):
        with pytest.raises(HTTPException) as exc_info:
            product_service.update_product(db, stocked_filament.id, data={"unit": "KG"})
        assert exc_info.value.status_code == 400
        db.refresh(stocked_filament)
        assert stocked_filament.unit == "G"

    def test_an_unlocked_unit_changes_and_the_factor_follows(self, db, make_product):
        item = make_product(sku=_sku("LOCK-FREE"), item_type="material", unit="G", purchase_uom="KG",
                            purchase_factor=D("1000"))
        product_service.update_product(db, item.id, data={"unit": "KG"})
        db.refresh(item)
        assert item.unit == "KG"
        assert D(str(item.purchase_factor)) == D("1")


class TestItemCsvImport:
    def _run(self, db, csv_text):
        return import_items_from_csv(db, file_content=csv_text.encode(), update_existing=True)

    def test_a_locked_unit_skips_the_row(self, db, stocked_filament):
        result = self._run(db, f"SKU,Name,Unit\n{stocked_filament.sku},Renamed,KG\n")
        assert result["skipped"] == 1
        assert "cannot change from G to KG" in result["errors"][0]["error"]
        db.refresh(stocked_filament)
        assert stocked_filament.unit == "G"
        assert stocked_filament.name != "Renamed"

    def test_the_same_unit_in_another_spelling_is_not_a_change(self, db, stocked_filament):
        result = self._run(db, f"SKU,Name,Unit\n{stocked_filament.sku},Renamed,grams\n")
        assert result["updated"] == 1, result["errors"]
        db.refresh(stocked_filament)
        assert stocked_filament.unit == "G"

    def test_an_unknown_unit_on_a_new_item_skips_the_row(self, db):
        sku = _sku("LOCK-NEW")
        result = self._run(db, f"SKU,Name,Unit\n{sku},New thing,FURLONG\n")
        assert result["skipped"] == 1
        assert result["created"] == 0
        assert db.query(Product).filter(Product.sku == sku).first() is None

    def test_a_blank_unit_cell_changes_nothing(self, db, stocked_filament):
        result = self._run(db, f"SKU,Name,Unit\n{stocked_filament.sku},Renamed,\n")
        assert result["updated"] == 1, result["errors"]
        db.refresh(stocked_filament)
        assert stocked_filament.unit == "G"


class TestProductCsvImport:
    HEADER = "SKU,Name,Item Type,Procurement Type,Unit\n"

    def test_a_locked_unit_is_reported(self, db, stocked_filament):
        result = data_import_service.import_products(
            db, self.HEADER + f"{stocked_filament.sku},Filament,material,buy,KG\n")
        assert result["updated"] == 0
        assert "cannot change from G to KG" in result["errors"][0]
        db.refresh(stocked_filament)
        assert stocked_filament.unit == "G"

    def test_a_blank_unit_cell_changes_nothing(self, db, stocked_filament):
        result = data_import_service.import_products(
            db, self.HEADER + f"{stocked_filament.sku},Filament,material,buy,\n")
        assert result["updated"] == 1, result["errors"]
        db.refresh(stocked_filament)
        assert stocked_filament.unit == "G"

    def test_an_unknown_unit_on_a_new_item_is_reported(self, db):
        sku = _sku("LOCK-NEWP")
        result = data_import_service.import_products(db, self.HEADER + f"{sku},Thing,supply,buy,FURLONG\n")
        assert result["created"] == 0
        assert result["errors"]
        assert db.query(Product).filter(Product.sku == sku).first() is None

    def test_a_new_material_in_grams_is_bought_in_kilograms(self, db):
        sku = _sku("LOCK-NEWG")
        result = data_import_service.import_products(db, self.HEADER + f"{sku},PLA,material,buy,G\n")
        assert result["created"] == 1, result["errors"]
        item = db.query(Product).filter(Product.sku == sku).one()
        assert (item.unit, item.purchase_uom) == ("G", "KG")
        assert D(str(item.purchase_factor)) == D("1000")


class TestDuplicate:
    def test_a_duplicate_carries_the_items_own_units(self, db, make_product):
        source = make_product(sku=_sku("LOCK-SRC"), item_type="supply", unit="EA", purchase_uom="EA")
        units.set_item_unit(db, source, "BOX", stock_units_per_unit=D("12"))
        db.flush()

        result = item_service.duplicate_item(db, source.id, new_sku=_sku("LOCK-DUP"), new_name="Copy")

        rows = db.query(ProductUnit).filter(ProductUnit.product_id == result["id"]).all()
        assert [(row.unit_code, D(str(row.stock_units_per_unit))) for row in rows] == [("BOX", D("12"))]
