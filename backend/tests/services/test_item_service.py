"""
Tests for app/services/item_service.py

Covers:
- Category CRUD: create, update, delete, list, tree, descendants
- Item CRUD: create, update, delete, get_item, get_item_by_sku
- list_items: filters (item_type, category, search, active, needs_reorder)
- create_item: auto-SKU generation, material auto-configuration, enum handling
- update_item: field updates, SKU uppercasing, category validation
- bulk_update_items: category assignment, active toggling, error handling
- delete_item: soft delete, inventory / BOM guards
- generate_item_sku: sequential numbering
- get_low_stock_items: reorder point detection
- recost operations: recalculate_bom_cost, calculate_item_cost, recost_item
- convert_uom_inline: unit conversion fallback
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

from app.services import item_service
from app.models.product import Product
from app.models.item_category import ItemCategory
from app.models.inventory import Inventory
from app.models.bom import BOM, BOMLine


# =============================================================================
# Helper: make_category inline (not a fixture — we need db directly)
# =============================================================================

def _make_category(db, code, name, parent_id=None, is_active=True, sort_order=0):
    """Create an ItemCategory directly for test setup."""
    cat = ItemCategory(
        code=code,
        name=name,
        parent_id=parent_id,
        is_active=is_active,
        sort_order=sort_order,
    )
    db.add(cat)
    db.flush()
    return cat


def _make_inventory(db, product_id, on_hand, location_id=1, allocated=0):
    """Create an Inventory record directly for test setup."""
    inv = Inventory(
        product_id=product_id,
        location_id=location_id,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


# =============================================================================
# convert_uom_inline
# =============================================================================

class TestConvertUomInline:
    """Test inline UOM conversion (no database)."""

    def test_same_unit_returns_identity(self):
        assert item_service.convert_uom_inline(Decimal("500"), "G", "G") == Decimal("500")

    def test_kg_to_g(self):
        result = item_service.convert_uom_inline(Decimal("1"), "KG", "G")
        assert result == Decimal("1000")

    def test_g_to_kg(self):
        result = item_service.convert_uom_inline(Decimal("500"), "G", "KG")
        assert result == Decimal("0.5")

    def test_lb_to_kg(self):
        result = item_service.convert_uom_inline(Decimal("1"), "LB", "KG")
        assert result == Decimal("0.453592")

    def test_incompatible_bases_returns_original(self):
        # Mass vs. length -- incompatible
        result = item_service.convert_uom_inline(Decimal("10"), "KG", "M")
        assert result == Decimal("10")

    def test_unknown_unit_returns_original(self):
        result = item_service.convert_uom_inline(Decimal("5"), "FOOBAR", "G")
        assert result == Decimal("5")

    def test_none_units_treated_as_ea(self):
        result = item_service.convert_uom_inline(Decimal("7"), None, None)
        assert result == Decimal("7")

    def test_case_insensitive(self):
        result = item_service.convert_uom_inline(Decimal("1"), "kg", "g")
        assert result == Decimal("1000")

    def test_mm_to_m(self):
        result = item_service.convert_uom_inline(Decimal("1000"), "MM", "M")
        assert result == Decimal("1")

    def test_ml_to_l(self):
        result = item_service.convert_uom_inline(Decimal("1500"), "ML", "L")
        assert result == Decimal("1.5")


# =============================================================================
# Category CRUD
# =============================================================================

class TestListCategories:
    """Test list_categories filtering."""

    def test_returns_active_by_default(self, db):
        active = _make_category(db, "CAT-ACT-1", "Active Category")
        _make_category(db, "CAT-INACT-1", "Inactive Category", is_active=False)

        categories = item_service.list_categories(db)
        codes = [c.code for c in categories]
        assert "CAT-ACT-1" in codes
        assert "CAT-INACT-1" not in codes

    def test_include_inactive(self, db):
        _make_category(db, "CAT-INACT-2", "Inactive", is_active=False)

        categories = item_service.list_categories(db, include_inactive=True)
        codes = [c.code for c in categories]
        assert "CAT-INACT-2" in codes

    def test_filter_by_parent_id(self, db):
        parent = _make_category(db, "CAT-PAR-1", "Parent")
        child = _make_category(db, "CAT-CHD-1", "Child", parent_id=parent.id)
        _make_category(db, "CAT-ORPHAN-1", "Orphan")

        children = item_service.list_categories(db, parent_id=parent.id)
        codes = [c.code for c in children]
        assert "CAT-CHD-1" in codes
        assert "CAT-ORPHAN-1" not in codes


class TestCreateCategory:
    """Test create_category."""

    def test_create_basic(self, db):
        cat = item_service.create_category(db, code="NEW-CAT", name="New Category")
        assert cat.id is not None
        assert cat.code == "NEW-CAT"
        assert cat.name == "New Category"
        assert cat.is_active is True

    def test_code_uppercased(self, db):
        cat = item_service.create_category(db, code="lower-cat", name="Lower")
        assert cat.code == "LOWER-CAT"

    def test_duplicate_code_raises_400(self, db):
        item_service.create_category(db, code="DUP-CAT", name="First")
        with pytest.raises(Exception) as exc_info:
            item_service.create_category(db, code="DUP-CAT", name="Second")
        assert exc_info.value.status_code == 400

    def test_with_parent(self, db):
        parent = _make_category(db, "P-FOR-CREATE", "Parent For Create")
        child = item_service.create_category(
            db, code="C-FOR-CREATE", name="Child", parent_id=parent.id
        )
        assert child.parent_id == parent.id

    def test_invalid_parent_raises_400(self, db):
        with pytest.raises(Exception) as exc_info:
            item_service.create_category(
                db, code="BAD-PARENT", name="Orphan", parent_id=999999
            )
        assert exc_info.value.status_code == 400


class TestUpdateCategory:
    """Test update_category."""

    def test_update_name(self, db):
        cat = _make_category(db, "UPD-CAT-1", "Original")
        db.commit()

        updated = item_service.update_category(db, cat.id, name="Renamed")
        assert updated.name == "Renamed"

    def test_update_code_checks_uniqueness(self, db):
        cat1 = _make_category(db, "UPD-CODE-A", "Cat A")
        cat2 = _make_category(db, "UPD-CODE-B", "Cat B")
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.update_category(db, cat2.id, code="UPD-CODE-A")
        assert exc_info.value.status_code == 400

    def test_self_parent_raises_400(self, db):
        cat = _make_category(db, "SELF-PAR", "Self Parent")
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.update_category(db, cat.id, parent_id=cat.id)
        assert exc_info.value.status_code == 400

    def test_update_sort_order(self, db):
        cat = _make_category(db, "SORT-CAT", "Sortable")
        db.commit()

        updated = item_service.update_category(db, cat.id, sort_order=99)
        assert updated.sort_order == 99

    def test_deactivate(self, db):
        cat = _make_category(db, "DEACT-CAT", "Deactivatable")
        db.commit()

        updated = item_service.update_category(db, cat.id, is_active=False)
        assert updated.is_active is False


class TestDeleteCategory:
    """Test delete_category (soft delete)."""

    def test_delete_empty_category(self, db):
        cat = _make_category(db, "DEL-CAT-1", "Deletable")
        db.commit()

        result = item_service.delete_category(db, cat.id)
        assert "deleted" in result["message"].lower() or "DEL-CAT-1" in result["message"]

        refreshed = db.query(ItemCategory).filter(ItemCategory.id == cat.id).first()
        assert refreshed.is_active is False

    def test_delete_with_active_children_raises_400(self, db):
        parent = _make_category(db, "DEL-PAR", "Parent")
        _make_category(db, "DEL-CHILD", "Child", parent_id=parent.id, is_active=True)
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.delete_category(db, parent.id)
        assert exc_info.value.status_code == 400
        assert "child" in str(exc_info.value.detail).lower()

    def test_delete_with_active_items_raises_400(self, db, make_product):
        cat = _make_category(db, "DEL-ITEMS-CAT", "Has Items")
        db.commit()

        make_product(category_id=cat.id)
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.delete_category(db, cat.id)
        assert exc_info.value.status_code == 400
        assert "item" in str(exc_info.value.detail).lower()


class TestGetCategoryAndDescendants:
    """Test get_category_and_descendants (recursive hierarchy)."""

    def test_single_category(self, db):
        cat = _make_category(db, "SINGLE-HIER", "Single")
        db.flush()

        ids = item_service.get_category_and_descendants(db, cat.id)
        assert ids == [cat.id]

    def test_parent_with_children(self, db):
        parent = _make_category(db, "HIER-P", "Parent")
        child1 = _make_category(db, "HIER-C1", "Child 1", parent_id=parent.id)
        child2 = _make_category(db, "HIER-C2", "Child 2", parent_id=parent.id)
        grandchild = _make_category(db, "HIER-GC", "Grandchild", parent_id=child1.id)
        db.flush()

        ids = item_service.get_category_and_descendants(db, parent.id)
        assert parent.id in ids
        assert child1.id in ids
        assert child2.id in ids
        assert grandchild.id in ids


class TestGetCategoryTree:
    """Test get_category_tree (nested dict)."""

    def test_returns_nested_structure(self, db):
        parent = _make_category(db, "TREE-P", "Tree Parent")
        _make_category(db, "TREE-C", "Tree Child", parent_id=parent.id)
        db.flush()

        tree = item_service.get_category_tree(db)
        # Find our parent node in the tree
        parent_nodes = [n for n in tree if n["code"] == "TREE-P"]
        assert len(parent_nodes) == 1
        assert len(parent_nodes[0]["children"]) >= 1
        child_codes = [c["code"] for c in parent_nodes[0]["children"]]
        assert "TREE-C" in child_codes


# =============================================================================
# generate_item_sku
# =============================================================================

class TestGenerateItemSku:
    """Test generate_item_sku."""

    def test_finished_good_prefix(self, db):
        sku = item_service.generate_item_sku(db, "finished_good")
        assert sku.startswith("FG-")

    def test_component_prefix(self, db):
        sku = item_service.generate_item_sku(db, "component")
        assert sku.startswith("COMP-")

    def test_supply_prefix(self, db):
        sku = item_service.generate_item_sku(db, "supply")
        assert sku.startswith("SUP-")

    def test_material_prefix(self, db):
        sku = item_service.generate_item_sku(db, "material")
        assert sku.startswith("MAT-")

    def test_unknown_type_uses_itm(self, db):
        sku = item_service.generate_item_sku(db, "unknown_type")
        assert sku.startswith("ITM-")

    def test_increments_from_existing(self, db, make_product):
        make_product(sku="SRV-010")
        db.commit()

        sku = item_service.generate_item_sku(db, "service")
        assert sku == "SRV-011"


# =============================================================================
# Item CRUD
# =============================================================================

class TestCreateItem:
    """Test create_item."""

    def test_create_basic_item(self, db):
        item = item_service.create_item(db, data={
            "name": "Widget",
            "item_type": "finished_good",
        })
        assert item.id is not None
        assert item.sku.startswith("FG-")
        assert item.name == "Widget"
        assert item.unit == "EA"
        assert item.active is True

    def test_create_with_explicit_sku(self, db):
        item = item_service.create_item(db, data={
            "sku": "my-custom-sku",
            "name": "Custom SKU Item",
        })
        assert item.sku == "MY-CUSTOM-SKU"

    def test_duplicate_sku_raises_400(self, db, make_product):
        make_product(sku="DUP-SKU-ITEM")
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.create_item(db, data={
                "sku": "DUP-SKU-ITEM",
                "name": "Duplicate",
            })
        assert exc_info.value.status_code == 400

    def test_material_auto_configuration(self, db):
        item = item_service.create_item(db, data={
            "name": "PLA Raw",
            "item_type": "material",
        })
        assert item.unit == "G"
        assert item.purchase_uom == "KG"
        assert item.is_raw_material is True

    def test_invalid_category_raises_400(self, db):
        with pytest.raises(Exception) as exc_info:
            item_service.create_item(db, data={
                "name": "Bad Category Item",
                "category_id": 999999,
            })
        assert exc_info.value.status_code == 400

    def test_auto_generates_sku_when_empty(self, db):
        item = item_service.create_item(db, data={
            "sku": "",
            "name": "Empty SKU Item",
            "item_type": "component",
        })
        assert item.sku.startswith("COMP-")

    def test_enum_values_converted(self, db):
        """Enum-like objects with .value attr are converted to strings."""
        class FakeEnum:
            value = "finished_good"

        item = item_service.create_item(db, data={
            "name": "Enum Test",
            "item_type": FakeEnum(),
        })
        assert item.item_type == "finished_good"

    def test_is_active_popped_from_data(self, db):
        """Pydantic alias is_active should not leak to Product model."""
        item = item_service.create_item(db, data={
            "name": "Active Test",
            "is_active": True,
        })
        assert item.active is True

    def test_valid_category_assignment(self, db):
        cat = _make_category(db, "ITEM-CAT", "Item Category")
        db.commit()

        item = item_service.create_item(db, data={
            "name": "Categorized Item",
            "category_id": cat.id,
        })
        assert item.category_id == cat.id


class TestGetItem:
    """Test get_item and get_item_by_sku."""

    def test_get_item_by_id(self, db, make_product):
        product = make_product(name="Findable")
        db.commit()

        found = item_service.get_item(db, product.id)
        assert found.id == product.id
        assert found.name == "Findable"

    def test_get_item_not_found_raises_404(self, db):
        with pytest.raises(Exception) as exc_info:
            item_service.get_item(db, 999999)
        assert exc_info.value.status_code == 404

    def test_get_item_by_sku(self, db, make_product):
        product = make_product(sku="FIND-BY-SKU")
        db.commit()

        found = item_service.get_item_by_sku(db, "find-by-sku")
        assert found.id == product.id

    def test_get_item_by_sku_not_found(self, db):
        with pytest.raises(Exception) as exc_info:
            item_service.get_item_by_sku(db, "NONEXISTENT-SKU")
        assert exc_info.value.status_code == 404


class TestUpdateItem:
    """Test update_item."""

    def test_update_name(self, db, make_product):
        product = make_product(name="Old Name")
        db.commit()

        updated = item_service.update_item(db, product.id, data={"name": "New Name"})
        assert updated.name == "New Name"

    def test_sku_uppercased_on_update(self, db, make_product):
        product = make_product()
        db.commit()

        updated = item_service.update_item(db, product.id, data={"sku": "new-sku-lower"})
        assert updated.sku == "NEW-SKU-LOWER"

    def test_duplicate_sku_raises_400(self, db, make_product):
        product1 = make_product(sku="TAKEN-SKU")
        product2 = make_product()
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.update_item(db, product2.id, data={"sku": "TAKEN-SKU"})
        assert exc_info.value.status_code == 400

    def test_invalid_category_raises_400(self, db, make_product):
        product = make_product()
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.update_item(db, product.id, data={"category_id": 999999})
        assert exc_info.value.status_code == 400

    def test_is_active_mapped_to_active(self, db, make_product):
        product = make_product()
        db.commit()

        updated = item_service.update_item(db, product.id, data={"is_active": False})
        assert updated.active is False

    def test_update_selling_price(self, db, make_product):
        product = make_product()
        db.commit()

        updated = item_service.update_item(
            db, product.id, data={"selling_price": Decimal("29.99")}
        )
        assert updated.selling_price == Decimal("29.99")


class TestDeleteItem:
    """Test delete_item (soft delete)."""

    def test_delete_sets_inactive(self, db, make_product):
        product = make_product()
        db.commit()

        result = item_service.delete_item(db, product.id)
        assert "deleted" in result["message"].lower() or product.sku in result["message"]

        refreshed = db.query(Product).filter(Product.id == product.id).first()
        assert refreshed.active is False

    def test_delete_with_inventory_raises_400(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, on_hand=Decimal("50"))
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.delete_item(db, product.id)
        assert exc_info.value.status_code == 400
        assert "on hand" in str(exc_info.value.detail).lower()

    def test_delete_with_active_bom_raises_400(self, db, make_product, make_bom):
        product = make_product()
        make_bom(product.id)
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.delete_item(db, product.id)
        assert exc_info.value.status_code == 400
        assert "bom" in str(exc_info.value.detail).lower()

    def test_not_found_raises_404(self, db):
        with pytest.raises(Exception) as exc_info:
            item_service.delete_item(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# list_items
# =============================================================================

class TestListItems:
    """Test list_items with various filters."""

    def test_basic_list(self, db, make_product):
        make_product(name="ListItem-A")
        make_product(name="ListItem-B")
        db.commit()

        items, total = item_service.list_items(db, search="ListItem-")
        assert total >= 2
        names = [i["name"] for i in items]
        assert "ListItem-A" in names
        assert "ListItem-B" in names

    def test_filter_by_item_type(self, db, make_product):
        make_product(sku="FILT-FG", item_type="finished_good")
        make_product(sku="FILT-COMP", item_type="component")
        db.commit()

        items, total = item_service.list_items(db, item_type="component")
        skus = [i["sku"] for i in items]
        assert "FILT-COMP" in skus
        assert "FILT-FG" not in skus

    def test_search_by_sku(self, db, make_product):
        make_product(sku="SRCH-XYZ-001", name="Searchable")
        db.commit()

        items, _ = item_service.list_items(db, search="SRCH-XYZ")
        skus = [i["sku"] for i in items]
        assert "SRCH-XYZ-001" in skus

    def test_search_by_name(self, db, make_product):
        make_product(name="UniqueSearchName99")
        db.commit()

        items, _ = item_service.list_items(db, search="UniqueSearchName99")
        names = [i["name"] for i in items]
        assert "UniqueSearchName99" in names

    def test_active_only_default(self, db, make_product):
        make_product(sku="ACT-ONLY-YES", active=True)
        make_product(sku="ACT-ONLY-NO", active=False)
        db.commit()

        items, _ = item_service.list_items(db)
        skus = [i["sku"] for i in items]
        assert "ACT-ONLY-YES" in skus
        assert "ACT-ONLY-NO" not in skus

    def test_include_inactive(self, db, make_product):
        make_product(sku="INACT-INC", active=False)
        db.commit()

        items, _ = item_service.list_items(db, active_only=False)
        skus = [i["sku"] for i in items]
        assert "INACT-INC" in skus

    def test_filter_by_category(self, db, make_product):
        cat = _make_category(db, "FILT-CAT", "Filter Cat")
        db.flush()
        make_product(sku="IN-CAT", category_id=cat.id)
        make_product(sku="NO-CAT")
        db.commit()

        items, _ = item_service.list_items(db, category_id=cat.id)
        skus = [i["sku"] for i in items]
        assert "IN-CAT" in skus
        assert "NO-CAT" not in skus

    def test_pagination(self, db, make_product):
        for i in range(5):
            make_product(sku=f"PAGE-{i:03d}")
        db.commit()

        items, total = item_service.list_items(db, limit=2, offset=0)
        assert len(items) <= 2
        assert total >= 5

    def test_filter_by_procurement_type(self, db, make_product):
        make_product(sku="PROC-MAKE", procurement_type="make")
        make_product(sku="PROC-BUY", procurement_type="buy")
        db.commit()

        items, _ = item_service.list_items(db, procurement_type="make")
        skus = [i["sku"] for i in items]
        assert "PROC-MAKE" in skus
        assert "PROC-BUY" not in skus

    def test_no_suggested_price_in_list(self, db, make_product):
        """suggested_price was removed — modal is now the sole source."""
        make_product(sku="SUGG-PRICE", standard_cost=Decimal("10.00"))
        db.commit()

        items, _ = item_service.list_items(db, search="SUGG-PRICE")
        match = [i for i in items if i["sku"] == "SUGG-PRICE"]
        assert len(match) == 1
        assert "suggested_price" not in match[0]


# =============================================================================
# bulk_update_items
# =============================================================================

class TestBulkUpdateItems:
    """Test bulk_update_items."""

    def test_assign_category(self, db, make_product):
        cat = _make_category(db, "BULK-CAT", "Bulk Category")
        db.flush()

        p1 = make_product()
        p2 = make_product()
        db.commit()

        result = item_service.bulk_update_items(
            db, item_ids=[p1.id, p2.id], category_id=cat.id
        )
        assert result["updated_count"] == 2

        db.refresh(p1)
        db.refresh(p2)
        assert p1.category_id == cat.id
        assert p2.category_id == cat.id

    def test_toggle_active(self, db, make_product):
        p = make_product()
        db.commit()

        result = item_service.bulk_update_items(
            db, item_ids=[p.id], is_active=False
        )
        assert result["updated_count"] == 1

        db.refresh(p)
        assert p.active is False

    def test_empty_item_ids_raises_400(self, db):
        with pytest.raises(Exception) as exc_info:
            item_service.bulk_update_items(db, item_ids=[])
        assert exc_info.value.status_code == 400

    def test_invalid_category_raises_400(self, db, make_product):
        p = make_product()
        db.commit()

        with pytest.raises(Exception) as exc_info:
            item_service.bulk_update_items(
                db, item_ids=[p.id], category_id=999999
            )
        assert exc_info.value.status_code == 400

    def test_missing_item_recorded_as_error(self, db, make_product):
        p = make_product()
        db.commit()

        result = item_service.bulk_update_items(
            db, item_ids=[p.id, 999999]
        )
        assert result["updated_count"] == 1
        assert result["error_count"] == 1
        assert result["errors"][0]["item_id"] == 999999

    def test_invalid_item_type_recorded_as_error(self, db, make_product):
        p = make_product()
        db.commit()

        result = item_service.bulk_update_items(
            db, item_ids=[p.id], item_type="not_a_valid_type"
        )
        assert result["error_count"] == 1

    def test_category_id_zero_clears_category(self, db, make_product):
        cat = _make_category(db, "BULK-CLR", "Clear Category")
        db.flush()
        p = make_product(category_id=cat.id)
        db.commit()

        result = item_service.bulk_update_items(
            db, item_ids=[p.id], category_id=0
        )
        assert result["updated_count"] == 1
        db.refresh(p)
        assert p.category_id is None

    def test_update_procurement_type(self, db, make_product):
        p = make_product(procurement_type="buy")
        db.commit()

        result = item_service.bulk_update_items(
            db, item_ids=[p.id], procurement_type="make"
        )
        assert result["updated_count"] == 1
        db.refresh(p)
        assert p.procurement_type == "make"


# =============================================================================
# build_item_response_data
# =============================================================================

class TestBuildItemResponseData:
    """Test build_item_response_data."""

    def test_basic_response_shape(self, db, make_product):
        product = make_product(
            name="Response Test",
            standard_cost=Decimal("5.00"),
            selling_price=Decimal("15.00"),
        )
        db.commit()

        data = item_service.build_item_response_data(product, db)
        assert data["id"] == product.id
        assert data["sku"] == product.sku
        assert data["name"] == "Response Test"
        assert data["on_hand_qty"] == 0
        assert data["available_qty"] == 0
        assert data["bom_count"] == 0
        assert "created_at" in data

    def test_includes_inventory_summary(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, on_hand=Decimal("100"), allocated=Decimal("30"))
        db.commit()

        data = item_service.build_item_response_data(product, db)
        assert data["on_hand_qty"] == 100.0
        assert data["allocated_qty"] == 30.0
        assert data["available_qty"] == 70.0

    def test_includes_bom_count(self, db, make_product, make_bom):
        fg = make_product()
        comp = make_product(item_type="component")
        make_bom(fg.id, lines=[{"component_id": comp.id, "quantity": Decimal("2")}])
        db.commit()

        data = item_service.build_item_response_data(fg, db)
        assert data["bom_count"] >= 1
        assert data["has_bom"] is True


# =============================================================================
# get_low_stock_items
# =============================================================================

class TestGetLowStockItems:
    """Test get_low_stock_items."""

    def test_stocked_item_below_reorder_point(self, db, make_product):
        product = make_product(
            sku="LOW-STK-1",
            stocking_policy="stocked",
            reorder_point=Decimal("10"),
            procurement_type="buy",
        )
        _make_inventory(db, product.id, on_hand=Decimal("5"))
        db.commit()

        result = item_service.get_low_stock_items(db, include_mrp_shortages=False)
        skus = [i["sku"] for i in result["items"]]
        assert "LOW-STK-1" in skus

    def test_stocked_item_above_reorder_not_included(self, db, make_product):
        product = make_product(
            sku="HIGH-STK-1",
            stocking_policy="stocked",
            reorder_point=Decimal("10"),
            procurement_type="buy",
        )
        _make_inventory(db, product.id, on_hand=Decimal("100"))
        db.commit()

        result = item_service.get_low_stock_items(db, include_mrp_shortages=False)
        skus = [i["sku"] for i in result["items"]]
        assert "HIGH-STK-1" not in skus

    def test_on_demand_items_excluded(self, db, make_product):
        product = make_product(
            sku="ON-DEMAND-1",
            stocking_policy="on_demand",
            reorder_point=Decimal("10"),
            procurement_type="buy",
        )
        db.commit()

        result = item_service.get_low_stock_items(db, include_mrp_shortages=False)
        skus = [i["sku"] for i in result["items"]]
        assert "ON-DEMAND-1" not in skus

    def test_result_structure(self, db):
        result = item_service.get_low_stock_items(db, include_mrp_shortages=False)
        assert "items" in result
        assert "count" in result
        assert "summary" in result
        assert "critical_count" in result["summary"]
        assert "urgent_count" in result["summary"]
        assert "total_shortfall_value" in result["summary"]

    def test_no_inventory_included_when_stocked(self, db, make_product):
        """Item with reorder point but no inventory record should appear."""
        product = make_product(
            sku="NO-INV-STK",
            stocking_policy="stocked",
            reorder_point=Decimal("5"),
            procurement_type="buy",
        )
        db.commit()

        result = item_service.get_low_stock_items(db, include_mrp_shortages=False)
        skus = [i["sku"] for i in result["items"]]
        assert "NO-INV-STK" in skus


# =============================================================================
# Recost Operations
# =============================================================================

class TestRecalculateBomCost:
    """Test recalculate_bom_cost."""

    def test_sums_component_costs(self, db, make_product, make_bom):
        fg = make_product()
        comp1 = make_product(
            item_type="component", standard_cost=Decimal("2.00"), unit="EA"
        )
        comp2 = make_product(
            item_type="component", standard_cost=Decimal("3.00"), unit="EA"
        )
        bom = make_bom(fg.id, lines=[
            {"component_id": comp1.id, "quantity": Decimal("2"), "unit": "EA"},
            {"component_id": comp2.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        db.commit()

        total = item_service.recalculate_bom_cost(bom, db)
        # 2 * $2.00 + 1 * $3.00 = $7.00
        assert total == Decimal("7.00")
        # Note: bom.total_cost is set by the caller (calculate_item_cost),
        # not by recalculate_bom_cost itself

    def test_no_cost_components_contribute_zero(self, db, make_product, make_bom):
        fg = make_product()
        comp = make_product(item_type="component")
        bom = make_bom(fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("5"), "unit": "EA"},
        ])
        db.commit()

        total = item_service.recalculate_bom_cost(bom, db)
        assert total == Decimal("0")


class TestCalculateItemCost:
    """Test calculate_item_cost."""

    def test_manufactured_item_with_bom(self, db, make_product, make_bom):
        fg = make_product()
        comp = make_product(
            item_type="component", standard_cost=Decimal("5.00"), unit="EA"
        )
        make_bom(fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("3"), "unit": "EA"},
        ])
        db.commit()

        result = item_service.calculate_item_cost(fg, db)
        assert result["cost_source"] == "manufactured"
        assert result["bom_cost"] == pytest.approx(15.0)

    def test_purchased_item_uses_standard_cost(self, db, make_product):
        product = make_product(standard_cost=Decimal("12.50"))
        db.commit()

        result = item_service.calculate_item_cost(product, db)
        assert result["cost_source"] == "purchased"
        assert result["purchase_cost"] == 12.50

    def test_purchased_item_fallback_to_average(self, db, make_product):
        product = make_product(average_cost=Decimal("8.00"))
        db.commit()

        result = item_service.calculate_item_cost(product, db)
        assert result["cost_source"] == "purchased"
        assert result["purchase_cost"] == 8.00


class TestRoutingCostDeduplication:
    """Test that materials on both BOM and routing operations are not double-counted."""

    def test_routing_material_excludes_bom_line(self, db, make_product, make_bom):
        """When a component is on both BOM and routing operation, count it once via routing."""
        from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
        from app.models.work_center import WorkCenter

        fg = make_product(standard_cost=Decimal("0"))
        mat = make_product(
            item_type="component", standard_cost=Decimal("20.00"),
            unit="EA",
        )

        # Put material on the BOM
        make_bom(fg.id, lines=[
            {"component_id": mat.id, "quantity": Decimal("2"), "unit": "EA"},
        ])

        # Also put material on a routing operation
        wc = db.query(WorkCenter).first()
        routing = Routing(
            product_id=fg.id, code=f"RTG-DEDUP-{uuid4().hex[:8]}", name="Test",
            is_active=True, version=1,
        )
        db.add(routing)
        db.flush()
        op = RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id if wc else None,
            sequence=10, operation_code="OP10", operation_name="Test Op",
            setup_time_minutes=Decimal("0"), run_time_minutes=Decimal("0"),
            is_active=True,
        )
        db.add(op)
        db.flush()
        rom = RoutingOperationMaterial(
            routing_operation_id=op.id, component_id=mat.id,
            quantity=Decimal("2"), unit="EA",
        )
        db.add(rom)
        db.commit()

        result = item_service.calculate_item_cost(fg, db)
        # Material cost should appear once: via routing (2 × $20 = $40), not BOM
        assert result["total_cost"] == pytest.approx(40.0, rel=1e-2)

    def test_no_routing_uses_full_bom(self, db, make_product, make_bom):
        """Without a routing, BOM cost is the full material cost."""
        fg = make_product(standard_cost=Decimal("0"))
        comp = make_product(
            item_type="component", standard_cost=Decimal("5.00"), unit="EA",
        )
        make_bom(fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("3"), "unit": "EA"},
        ])
        db.commit()

        result = item_service.calculate_item_cost(fg, db)
        assert result["bom_cost"] == pytest.approx(15.0)
        assert result["routing_cost"] == 0.0


class TestEffectiveHourlyRate:
    """Test RoutingOperation.effective_hourly_rate() component-wise logic."""

    def test_work_center_rates_summed(self, db):
        from app.models.manufacturing import RoutingOperation
        from app.models.work_center import WorkCenter

        wc = WorkCenter(
            name=f"WC-{uuid4().hex[:8]}", code=f"WC-{uuid4().hex[:8]}", center_type="assembly",
            machine_rate_per_hour=Decimal("10.00"),
            labor_rate_per_hour=Decimal("15.00"),
            overhead_rate_per_hour=Decimal("5.00"),
        )
        db.add(wc)
        db.flush()

        op = RoutingOperation(
            work_center_id=wc.id, sequence=10,
            operation_code="T1", operation_name="Test",
            setup_time_minutes=Decimal("30"), run_time_minutes=Decimal("60"),
            is_active=True,
        )
        op.work_center = wc
        assert op.effective_hourly_rate() == pytest.approx(30.0)
        # 30min setup + 60min run = 90min = 1.5hr × $30 = $45
        assert op.calculated_cost == pytest.approx(45.0)

    def test_labor_override_keeps_machine_and_overhead(self, db):
        from app.models.manufacturing import RoutingOperation
        from app.models.work_center import WorkCenter

        wc = WorkCenter(
            name=f"WC-{uuid4().hex[:8]}", code=f"WC-{uuid4().hex[:8]}", center_type="assembly",
            machine_rate_per_hour=Decimal("10.00"),
            labor_rate_per_hour=Decimal("15.00"),
            overhead_rate_per_hour=Decimal("5.00"),
        )
        db.add(wc)
        db.flush()

        op = RoutingOperation(
            work_center_id=wc.id, sequence=10,
            operation_code="T2", operation_name="Test",
            setup_time_minutes=Decimal("0"), run_time_minutes=Decimal("60"),
            labor_rate_override=Decimal("20.00"),
            is_active=True,
        )
        op.work_center = wc
        # Labor overridden to $20, machine $10 + overhead $5 from WC
        assert op.effective_hourly_rate() == pytest.approx(35.0)

    def test_zero_override_is_respected(self, db):
        from app.models.manufacturing import RoutingOperation
        from app.models.work_center import WorkCenter

        wc = WorkCenter(
            name=f"WC-{uuid4().hex[:8]}", code=f"WC-{uuid4().hex[:8]}", center_type="assembly",
            machine_rate_per_hour=Decimal("10.00"),
            labor_rate_per_hour=Decimal("15.00"),
            overhead_rate_per_hour=Decimal("5.00"),
        )
        db.add(wc)
        db.flush()

        op = RoutingOperation(
            work_center_id=wc.id, sequence=10,
            operation_code="T3", operation_name="Test",
            setup_time_minutes=Decimal("0"), run_time_minutes=Decimal("60"),
            labor_rate_override=Decimal("0"),  # Explicitly $0
            is_active=True,
        )
        op.work_center = wc
        # Labor zeroed, machine $10 + overhead $5
        assert op.effective_hourly_rate() == pytest.approx(15.0)


class TestRecostItem:
    """Test recost_item."""

    def test_updates_standard_cost(self, db, make_product, make_bom):
        fg = make_product(standard_cost=Decimal("0"))
        comp = make_product(
            item_type="component", standard_cost=Decimal("4.00"), unit="EA"
        )
        make_bom(fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("2"), "unit": "EA"},
        ])
        db.commit()

        result = item_service.recost_item(db, fg.id)
        assert result["new_cost"] == pytest.approx(8.0)
        assert result["old_cost"] == 0.0

        db.refresh(fg)
        assert float(fg.standard_cost) == pytest.approx(8.0)


class TestRecostAllItems:
    """Test recost_all_items."""

    def test_recosts_active_items(self, db, make_product, make_bom):
        fg = make_product(standard_cost=Decimal("0"))
        comp = make_product(
            item_type="component", standard_cost=Decimal("10.00"), unit="EA"
        )
        make_bom(fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        db.commit()

        result = item_service.recost_all_items(db)
        assert result["updated"] >= 1

    def test_skips_zero_cost_items(self, db, make_product):
        make_product(sku="ZERO-COST-RC", standard_cost=Decimal("0"))
        db.commit()

        result = item_service.recost_all_items(db)
        skipped_or_not = True  # The function skips items with total_cost == 0
        assert "skipped" in result
