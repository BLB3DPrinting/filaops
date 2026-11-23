"""
An item's units: the stock unit lock, known units, the default purchase unit,
``purchase_factor`` and the item's own units, all in ``item_unit_service``.
"""
from decimal import Decimal as D

import pytest

from app.models.bom import BOM, BOMLine
from app.models.inventory import Inventory, InventoryTransaction
from app.models.product_unit import ProductUnit
from app.models.purchase_order import PurchaseOrderLine
from app.models.uom import UnitOfMeasure
from app.services import item_unit_service as units
from app.services.item_unit_service import ItemUnitError


def _refused(call, *said):
    with pytest.raises(ItemUnitError) as caught:
        call()
    assert caught.value.status_code == 400
    for words in said:
        assert words in caught.value.message, caught.value.message
    return caught.value.message


def _rows(db, product):
    return {
        row.unit_code: (row.stock_units_per_unit, row.units_per_stock_unit)
        for row in db.query(ProductUnit).filter(ProductUnit.product_id == product.id)
    }


@pytest.fixture
def screw(make_product):
    return make_product(item_type="supply", unit="EA", purchase_uom="EA")


@pytest.fixture
def filament(make_product):
    return make_product(item_type="material", unit="G", purchase_uom="KG", purchase_factor=D("1000"))


@pytest.fixture
def spool(make_product):
    """A material counted by the each, bought by the each."""
    return make_product(item_type="material", unit="EA", purchase_uom="EA")


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------

class TestLock:
    def test_an_item_with_no_history_is_not_locked(self, db, screw):
        assert units.stock_unit_lock(db, screw) == units.StockUnitLock(False, None)

    def test_stock_on_hand_locks_it(self, db, filament):
        db.add(Inventory(product_id=filament.id, location_id=1, on_hand_quantity=D("5"), allocated_quantity=D("0")))
        db.flush()
        assert units.stock_unit_lock(db, filament).locked

    def test_stock_allocated_locks_it(self, db, filament):
        db.add(Inventory(product_id=filament.id, location_id=1, on_hand_quantity=D("0"), allocated_quantity=D("2")))
        db.flush()
        assert units.stock_unit_lock(db, filament).locked

    def test_an_empty_stock_row_does_not_lock_it(self, db, filament):
        db.add(Inventory(product_id=filament.id, location_id=1, on_hand_quantity=D("0"), allocated_quantity=D("0")))
        db.flush()
        assert not units.stock_unit_lock(db, filament).locked

    def test_a_ledger_row_locks_it(self, db, filament):
        db.add(InventoryTransaction(product_id=filament.id, transaction_type="adjustment", quantity=D("0")))
        db.flush()
        lock = units.stock_unit_lock(db, filament)
        assert lock.locked and "transactions" in lock.reason

    def test_a_unit_of_its_own_locks_it(self, db, screw):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        lock = units.stock_unit_lock(db, screw)
        assert lock.locked and "units of its own" in lock.reason

    def test_a_locked_change_is_refused_and_says_why(self, db, filament):
        db.add(InventoryTransaction(product_id=filament.id, transaction_type="receipt", quantity=D("1000")))
        db.flush()
        _refused(lambda: units.check_stock_unit_change(db, filament, "KG"), "cannot change from G to KG",
                 "inventory transactions", "create a new item")

    def test_a_change_of_spelling_is_not_a_change(self, db, filament):
        db.add(InventoryTransaction(product_id=filament.id, transaction_type="receipt", quantity=D("1000")))
        db.flush()
        assert units.check_stock_unit_change(db, filament, " g ") == "G"
        assert units.check_stock_unit_change(db, filament, "grams") == "G"

    def test_an_unlocked_item_may_change_to_a_known_unit(self, db, filament):
        assert units.check_stock_unit_change(db, filament, "kg") == "KG"

    def test_an_unlocked_item_may_not_change_to_an_unknown_unit(self, db, filament):
        _refused(lambda: units.check_stock_unit_change(db, filament, "SPOONS"), "Unknown unit 'SPOONS'")


# ---------------------------------------------------------------------------
# Known units, and the default purchase unit
# ---------------------------------------------------------------------------

class TestKnownUnits:
    def test_a_known_unit_comes_back_tidy(self, db):
        assert units.require_item_unit(db, " kg ") == "KG"
        assert units.require_item_unit(db, "pcs") == "EA"

    def test_an_unknown_unit_is_refused_and_named(self, db):
        _refused(lambda: units.require_item_unit(db, "spoons", field="purchase unit"),
                 "Item purchase unit", "SPOONS")

    def test_a_switched_off_unit_is_refused(self, db):
        db.add(UnitOfMeasure(code="ZOFF", name="Off", symbol="zo", uom_class="pack", to_base_factor=1, active=False))
        db.flush()
        _refused(lambda: units.require_item_unit(db, "ZOFF"), "switched off")

    def test_the_unit_an_item_holds_can_be_sent_back(self, db):
        assert units.require_item_unit(db, "spoons", current="SPOONS") == "SPOONS"
        assert units.require_item_unit(db, "SPOONS", current="spoons") == "spoons"

    def test_every_unit_the_quick_create_form_sends_is_accepted(self, db):
        for code in ("pcs", "kg", "g", "m", "ft", "L", "mL", "roll", "box", "pack"):
            assert units.require_item_unit(db, code)

    def test_an_install_with_no_ea_is_told_what_to_do(self, db):
        db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "EA").update({"active": False})
        db.flush()
        _refused(lambda: units.require_item_unit(db, "EA"), "Add EA under Units")

    @pytest.mark.parametrize("stock, item_type, expected", [
        ("G", "material", "KG"),
        ("g", "material", "KG"),
        ("EA", "material", "EA"),
        ("G", "supply", "G"),
        ("EA", "finished_good", "EA"),
    ])
    def test_default_purchase_unit(self, stock, item_type, expected):
        assert units.default_purchase_unit(stock, item_type) == expected


# ---------------------------------------------------------------------------
# purchase_factor
# ---------------------------------------------------------------------------

class TestPurchaseFactor:
    def test_kg_on_gram_filament_is_1000(self, db, filament):
        filament.purchase_factor = None
        units.sync_purchase_factor(db, filament)
        assert filament.purchase_factor == D("1000")

    def test_the_same_unit_is_1(self, db, screw):
        units.sync_purchase_factor(db, screw)
        assert screw.purchase_factor == D("1")

    def test_an_item_unit_gives_the_size(self, db, screw):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        screw.purchase_uom = "BOX"
        units.sync_purchase_factor(db, screw)
        assert screw.purchase_factor == D("12")

    def test_a_changed_size_follows(self, db, screw):
        screw.purchase_uom = "BOX"
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        assert screw.purchase_factor == D("12")
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="10")
        assert screw.purchase_factor == D("10")

    def test_a_pack_with_no_size_clears_it_when_the_purchase_unit_changes(self, db, screw):
        screw.purchase_factor = D("12")
        screw.purchase_uom = "CASE"
        units.sync_purchase_factor(db, screw)
        assert screw.purchase_factor is None

    def test_a_pack_with_no_size_keeps_it_when_nothing_changed(self, db, screw):
        screw.purchase_uom = "BOX"
        screw.purchase_factor = D("12")
        units.sync_purchase_factor(db, screw, purchase_unit_changed=False)
        assert screw.purchase_factor == D("12")


# ---------------------------------------------------------------------------
# The item's own units
# ---------------------------------------------------------------------------

class TestItemUnits:
    def test_a_box_of_12(self, db, screw):
        units.set_item_unit(db, screw, "box", stock_units_per_unit="12")
        assert _rows(db, screw) == {"BOX": (D("12"), None)}

    def test_a_spool_of_750_g_stored_the_way_it_was_typed(self, db, spool):
        units.set_item_unit(db, spool, "G", units_per_stock_unit="750")
        assert _rows(db, spool) == {"G": (None, D("750"))}

    def test_a_size_can_be_changed(self, db, screw):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="10")
        assert _rows(db, screw) == {"BOX": (D("10"), None)}

    def test_the_stock_unit_is_refused(self, db, screw):
        _refused(lambda: units.set_item_unit(db, screw, "EA", stock_units_per_unit="1"), "is the stock unit")

    def test_a_unit_the_table_already_converts_is_refused(self, db, filament):
        _refused(lambda: units.set_item_unit(db, filament, "KG", stock_units_per_unit="900"),
                 "already converts KG to G")

    def test_a_second_weight_unit_is_refused(self, db, spool):
        units.set_item_unit(db, spool, "G", units_per_stock_unit="750")
        _refused(lambda: units.set_item_unit(db, spool, "KG", units_per_stock_unit="0.75"),
                 "already has G as its weight unit")

    def test_two_packs_are_allowed(self, db, screw):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="100")
        units.set_item_unit(db, screw, "CASE", stock_units_per_unit="1000")
        assert set(_rows(db, screw)) == {"BOX", "CASE"}

    def test_an_unknown_unit_is_refused(self, db, screw):
        _refused(lambda: units.set_item_unit(db, screw, "CRATE", stock_units_per_unit="5"), "Unknown unit 'CRATE'")

    @pytest.mark.parametrize("size", ["0", "-3", "abc", "1e12", "0.12345678901"])
    def test_a_bad_size_is_refused(self, db, screw, size):
        _refused(lambda: units.set_item_unit(db, screw, "BOX", stock_units_per_unit=size))

    def test_exactly_one_size(self, db, screw):
        _refused(lambda: units.set_item_unit(db, screw, "BOX"), "Give one size")
        _refused(lambda: units.set_item_unit(db, screw, "BOX", stock_units_per_unit="1", units_per_stock_unit="1"),
                 "Give one size")


class TestRemoveItemUnit:
    def test_an_unused_unit_is_removed(self, db, screw):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        units.remove_item_unit(db, screw, "box")
        assert _rows(db, screw) == {}

    def test_the_purchase_unit_is_refused(self, db, screw):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        screw.purchase_uom = "BOX"
        _refused(lambda: units.remove_item_unit(db, screw, "BOX"), "is the purchase unit")

    def test_a_unit_on_a_bom_line_is_refused(self, db, screw, make_product):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        bom = BOM(product_id=make_product().id, code="B", name="B", active=True)
        db.add(bom)
        db.flush()
        db.add(BOMLine(bom_id=bom.id, component_id=screw.id, quantity=D("1"), unit="BOX", sequence=1))
        db.flush()
        _refused(lambda: units.remove_item_unit(db, screw, "BOX"), "1 BOM line(s)")

    def test_a_unit_on_a_purchase_order_line_is_refused(self, db, screw, make_purchase_order, make_vendor):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        po = make_purchase_order(vendor_id=make_vendor().id)
        db.add(PurchaseOrderLine(purchase_order_id=po.id, product_id=screw.id, line_number=1,
                                 quantity_ordered=D("2"), unit_cost=D("1"), line_total=D("2"),
                                 purchase_unit="box"))
        db.flush()
        _refused(lambda: units.remove_item_unit(db, screw, "BOX"), "1 purchase order line(s)")

    def test_a_unit_it_does_not_have(self, db, screw):
        _refused(lambda: units.remove_item_unit(db, screw, "BOX"), "has no unit BOX")


class TestCopy:
    def test_the_units_are_copied(self, db, screw, make_product):
        units.set_item_unit(db, screw, "BOX", stock_units_per_unit="12")
        units.set_item_unit(db, screw, "CASE", stock_units_per_unit="144")
        copy = make_product(item_type="supply", unit="EA")
        assert units.copy_item_units(db, screw.id, copy) == 2
        assert _rows(db, copy) == {"BOX": (D("12"), None), "CASE": (D("144"), None)}
