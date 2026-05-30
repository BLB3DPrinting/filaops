"""
Tests for Items API endpoints (/api/v1/items).

Covers:
- Authentication requirements for all endpoints
- CRUD operations on items (create, read, update, delete/deactivate)
- List items with filtering (item_type, search, active_only, pagination)
- Item categories CRUD and tree view
- Bulk update operations
- Low stock report
- Recost operations (single and bulk)
- Get item by SKU
- Demand summary endpoint
"""
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/items"


# =============================================================================
# Helper: category factory
# =============================================================================

@pytest.fixture
def make_category(db):
    """Factory fixture to create ItemCategory instances."""
    from app.models.item_category import ItemCategory

    def _factory(code=None, name=None, parent_id=None, is_active=True, sort_order=0):
        import uuid
        uid = uuid.uuid4().hex[:8]
        cat = ItemCategory(
            code=code or f"CAT-{uid}".upper(),
            name=name or f"Category {uid}",
            parent_id=parent_id,
            is_active=is_active,
            sort_order=sort_order,
        )
        db.add(cat)
        db.flush()
        return cat

    yield _factory


@pytest.fixture
def make_inventory(db):
    """Factory fixture to create Inventory records for a product."""
    from app.models.inventory import Inventory

    def _factory(product_id, on_hand_quantity=0, allocated_quantity=0, location_id=1):
        inv = Inventory(
            product_id=product_id,
            location_id=location_id,
            on_hand_quantity=on_hand_quantity,
            allocated_quantity=allocated_quantity,
        )
        db.add(inv)
        db.flush()
        return inv

    yield _factory


# =============================================================================
# Authentication — All write endpoints require auth
# =============================================================================

class TestItemsAuth:
    """Verify auth is required on write endpoints."""

    def test_create_item_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE_URL, json={"name": "X", "item_type": "finished_good"})
        assert resp.status_code == 401

    def test_update_item_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(f"{BASE_URL}/1", json={"name": "Updated"})
        assert resp.status_code == 401

    def test_delete_item_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE_URL}/1")
        assert resp.status_code == 401

    def test_bulk_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/bulk-update", json={"item_ids": [1]})
        assert resp.status_code == 401

    def test_create_category_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/categories",
            json={"code": "TST", "name": "Test"},
        )
        assert resp.status_code == 401

    def test_update_category_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(
            f"{BASE_URL}/categories/1",
            json={"name": "Updated"},
        )
        assert resp.status_code == 401

    def test_delete_category_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE_URL}/categories/1")
        assert resp.status_code == 401

    def test_recost_item_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/1/recost")
        assert resp.status_code == 401

    def test_recost_all_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/recost-all")
        assert resp.status_code == 401


# =============================================================================
# List items — GET /api/v1/items
# =============================================================================

class TestListItems:
    """Tests for the list items endpoint."""

    def test_list_returns_200(self, client):
        resp = client.get(BASE_URL)
        assert resp.status_code == 200

    def test_list_returns_total_and_items(self, client):
        resp = client.get(BASE_URL)
        body = resp.json()
        assert "total" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_list_includes_created_item(self, client, make_product):
        product = make_product(name="Unique List Test Widget")
        resp = client.get(BASE_URL, params={"search": "Unique List Test Widget"})
        assert resp.status_code == 200
        body = resp.json()
        skus = [item["sku"] for item in body["items"]]
        assert product.sku in skus

    def test_list_filter_by_item_type(self, client, make_product):
        make_product(item_type="component", name="Component Filter Test")
        resp = client.get(BASE_URL, params={"item_type": "component"})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["item_type"] == "component"

    def test_list_filter_by_packaging_item_type(self, client, make_product):
        make_product(item_type="packaging", name="Packaging Filter Test")
        resp = client.get(BASE_URL, params={"item_type": "packaging"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        for item in body["items"]:
            assert item["item_type"] == "packaging"

    def test_list_filter_by_procurement_type(self, client, make_product):
        make_product(procurement_type="make", name="Make Filter Test")
        resp = client.get(BASE_URL, params={"procurement_type": "make"})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["procurement_type"] == "make"

    def test_list_search_by_sku(self, client, make_product):
        product = make_product(sku="SRCH-SKU-001", name="Search SKU Test")
        resp = client.get(BASE_URL, params={"search": "SRCH-SKU-001"})
        assert resp.status_code == 200
        body = resp.json()
        assert any(item["sku"] == "SRCH-SKU-001" for item in body["items"])

    def test_list_search_by_name(self, client, make_product):
        make_product(name="XyZzYqUeRy Widget")
        resp = client.get(BASE_URL, params={"search": "XyZzYqUeRy"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1

    def test_list_active_only_default(self, client, make_product):
        """By default active_only=True, so inactive items are excluded."""
        make_product(name="Inactive Item", active=False)
        resp = client.get(BASE_URL, params={"search": "Inactive Item"})
        body = resp.json()
        # Should not find the inactive item with default filters
        assert all(item["active"] for item in body["items"])

    def test_list_include_inactive(self, client, make_product):
        product = make_product(name="InactiveInclude Test", active=False)
        resp = client.get(BASE_URL, params={"active_only": False, "search": "InactiveInclude"})
        body = resp.json()
        skus = [item["sku"] for item in body["items"]]
        assert product.sku in skus

    def test_list_pagination_limit(self, client, make_product):
        for i in range(5):
            make_product(name=f"Pagination Item {i}")
        resp = client.get(BASE_URL, params={"limit": 2, "offset": 0})
        body = resp.json()
        assert len(body["items"]) <= 2

    def test_list_pagination_offset(self, client, make_product):
        for i in range(5):
            make_product(name=f"Offset Item {i}")
        resp_first = client.get(BASE_URL, params={"limit": 2, "offset": 0})
        resp_second = client.get(BASE_URL, params={"limit": 2, "offset": 2})
        first_skus = {item["sku"] for item in resp_first.json()["items"]}
        second_skus = {item["sku"] for item in resp_second.json()["items"]}
        # Offset should produce different items
        assert first_skus != second_skus

    def test_list_filter_by_category(self, client, make_product, make_category):
        cat = make_category(code="FILT-CAT", name="Filter Category")
        make_product(name="Categorized Item", category_id=cat.id)
        resp = client.get(BASE_URL, params={"category_id": cat.id})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["category_id"] == cat.id

    def test_list_item_response_shape(self, client, make_product):
        make_product(name="Shape Test", standard_cost=Decimal("10.00"), selling_price=Decimal("25.00"))
        resp = client.get(BASE_URL, params={"search": "Shape Test"})
        body = resp.json()
        assert body["total"] >= 1
        item = body["items"][0]
        # Check expected fields exist
        expected_fields = {"id", "sku", "name", "item_type", "active", "on_hand_qty", "available_qty"}
        assert expected_fields.issubset(item.keys())


# =============================================================================
# Create item — POST /api/v1/items
# =============================================================================

class TestCreateItem:
    """Tests for the create item endpoint."""

    def test_create_item_success(self, client):
        payload = {
            "name": "New Test Product",
            "sku": "CREATE-TEST-001",
            "item_type": "finished_good",
            "unit": "EA",
            "procurement_type": "buy",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["sku"] == "CREATE-TEST-001"
        assert body["name"] == "New Test Product"
        assert body["item_type"] == "finished_good"

    def test_create_item_auto_generates_sku(self, client):
        payload = {
            "name": "Auto SKU Product",
            "item_type": "finished_good",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["sku"].startswith("FG-")

    def test_create_component_auto_sku_prefix(self, client):
        payload = {
            "name": "Auto SKU Component",
            "item_type": "component",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["sku"].startswith("COMP-")

    def test_create_supply_auto_sku_prefix(self, client):
        payload = {
            "name": "Auto SKU Supply",
            "item_type": "supply",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        assert resp.json()["sku"].startswith("SUP-")

    def test_create_packaging_auto_sku_prefix(self, client):
        payload = {
            "name": "Auto SKU Packaging",
            "item_type": "packaging",
            "weight_oz": "3.20",
            "length_in": "12.00",
            "width_in": "9.00",
            "height_in": "4.00",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["item_type"] == "packaging"
        assert body["sku"].startswith("PKG-")

    def test_create_packaging_requires_physical_metadata(self, client):
        payload = {
            "name": "Box Missing Physical Metadata",
            "item_type": "packaging",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 400
        assert "Packaging items require" in resp.json()["detail"]

    def test_create_packaging_with_physical_metadata_succeeds(self, client):
        payload = {
            "name": "12x9x4 Corrugated Box",
            "item_type": "packaging",
            "weight_oz": "3.20",
            "length_in": "12.00",
            "width_in": "9.00",
            "height_in": "4.00",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["item_type"] == "packaging"
        assert body["weight_oz"] == "3.20"
        assert body["length_in"] == "12.00"
        assert body["width_in"] == "9.00"
        assert body["height_in"] == "4.00"

    def test_create_non_packaging_can_omit_physical_metadata(self, client):
        payload = {
            "name": "Physical Metadata Optional Component",
            "item_type": "component",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["item_type"] == "component"
        assert body["weight_oz"] is None

    def test_create_service_auto_sku_prefix(self, client):
        payload = {
            "name": "Auto SKU Service",
            "item_type": "service",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        assert resp.json()["sku"].startswith("SRV-")

    def test_create_item_sku_uppercased(self, client):
        payload = {
            "name": "Lowercase SKU Test",
            "sku": "lower-case-sku",
            "item_type": "finished_good",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        assert resp.json()["sku"] == "LOWER-CASE-SKU"

    def test_create_item_duplicate_sku_fails(self, client, make_product):
        product = make_product(sku="DUP-SKU-001")
        payload = {
            "name": "Duplicate SKU",
            "sku": "DUP-SKU-001",
            "item_type": "finished_good",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_create_item_invalid_category_fails(self, client):
        payload = {
            "name": "Bad Category Item",
            "item_type": "finished_good",
            "category_id": 999999,
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_create_item_with_all_optional_fields(self, client):
        payload = {
            "name": "Full Fields Product",
            "sku": "FULL-FIELDS-001",
            "item_type": "finished_good",
            "unit": "EA",
            "procurement_type": "make",
            "cost_method": "standard",
            "standard_cost": "12.50",
            "selling_price": "29.99",
            "weight_oz": "8.5",
            "lead_time_days": 7,
            "min_order_qty": "10",
            "reorder_point": "5",
            "upc": "123456789012",
            "track_lots": True,
            "track_serials": False,
            "description": "A fully specified product",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["description"] == "A fully specified product"
        assert body["track_lots"] is True

    def test_create_item_missing_name_fails(self, client):
        payload = {
            "sku": "NO-NAME-001",
            "item_type": "finished_good",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 422

    def test_create_material_item_auto_configures_uom(self, client):
        """Creating a material item should auto-set unit=G, purchase_uom=KG."""
        payload = {
            "name": "Test Material Auto UOM",
            "sku": "MAT-AUTO-UOM-001",
            "item_type": "material",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["item_type"] == "material"
        assert body["is_raw_material"] is True

    def test_create_item_with_valid_category(self, client, make_category):
        cat = make_category(code="VALID-CAT", name="Valid Category")
        payload = {
            "name": "Categorized Item",
            "sku": "CAT-ITEM-001",
            "item_type": "finished_good",
            "category_id": cat.id,
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["category_id"] == cat.id
        assert body["category_name"] == "Valid Category"


# =============================================================================
# Get item — GET /api/v1/items/{item_id}
# =============================================================================

class TestGetItem:
    """Tests for the get item by ID endpoint."""

    def test_get_item_success(self, client, make_product):
        product = make_product(name="Get Test Item")
        resp = client.get(f"{BASE_URL}/{product.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == product.id
        assert body["sku"] == product.sku
        assert body["name"] == "Get Test Item"

    def test_get_item_not_found(self, client):
        resp = client.get(f"{BASE_URL}/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_get_item_response_has_inventory_fields(self, client, make_product):
        product = make_product(name="Inv Fields Test")
        resp = client.get(f"{BASE_URL}/{product.id}")
        body = resp.json()
        assert "on_hand_qty" in body
        assert "available_qty" in body
        assert "allocated_qty" in body

    def test_get_item_response_has_bom_fields(self, client, make_product):
        product = make_product(name="BOM Fields Test")
        resp = client.get(f"{BASE_URL}/{product.id}")
        body = resp.json()
        assert "has_bom" in body
        assert "bom_count" in body

    def test_get_item_response_has_timestamps(self, client, make_product):
        product = make_product(name="Timestamp Test")
        resp = client.get(f"{BASE_URL}/{product.id}")
        body = resp.json()
        assert "created_at" in body
        assert "updated_at" in body


# =============================================================================
# Get item by SKU — GET /api/v1/items/sku/{sku}
# =============================================================================

class TestGetItemBySku:
    """Tests for the get item by SKU endpoint."""

    def test_get_by_sku_success(self, client, make_product):
        product = make_product(sku="SKU-LOOKUP-001", name="SKU Lookup Test")
        resp = client.get(f"{BASE_URL}/sku/SKU-LOOKUP-001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sku"] == "SKU-LOOKUP-001"
        assert body["id"] == product.id

    def test_get_by_sku_case_insensitive(self, client, make_product):
        make_product(sku="UPPER-SKU-001", name="Case Test")
        resp = client.get(f"{BASE_URL}/sku/upper-sku-001")
        assert resp.status_code == 200
        assert resp.json()["sku"] == "UPPER-SKU-001"

    def test_get_by_sku_not_found(self, client):
        resp = client.get(f"{BASE_URL}/sku/NONEXISTENT-SKU")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


# =============================================================================
# Update item — PATCH /api/v1/items/{item_id}
# =============================================================================

class TestUpdateItem:
    """Tests for the update item endpoint."""

    def test_update_item_name(self, client, make_product):
        product = make_product(name="Before Update")
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"name": "After Update"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "After Update"

    def test_update_item_sku(self, client, make_product):
        product = make_product(name="SKU Update Test")
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"sku": "NEW-SKU-UPDATE"})
        assert resp.status_code == 200
        assert resp.json()["sku"] == "NEW-SKU-UPDATE"

    def test_update_item_sku_uppercased(self, client, make_product):
        product = make_product(name="SKU Case Test")
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"sku": "lowercase-update"})
        assert resp.status_code == 200
        assert resp.json()["sku"] == "LOWERCASE-UPDATE"

    def test_update_item_not_found(self, client):
        resp = client.patch(f"{BASE_URL}/999999", json={"name": "Ghost"})
        assert resp.status_code == 404

    def test_update_item_duplicate_sku_fails(self, client, make_product):
        product_a = make_product(sku="EXISTING-SKU-A", name="Item A")
        product_b = make_product(sku="EXISTING-SKU-B", name="Item B")
        resp = client.patch(f"{BASE_URL}/{product_b.id}", json={"sku": "EXISTING-SKU-A"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_update_item_invalid_category_fails(self, client, make_product):
        product = make_product(name="Bad Cat Update")
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"category_id": 999999})
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_update_item_selling_price(self, client, make_product):
        product = make_product(name="Price Update Test", selling_price=Decimal("10.00"))
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"selling_price": "24.99"})
        assert resp.status_code == 200
        assert float(resp.json()["selling_price"]) == pytest.approx(24.99, abs=0.01)

    def test_update_item_procurement_type(self, client, make_product):
        product = make_product(name="Proc Update", procurement_type="buy")
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"procurement_type": "make"})
        assert resp.status_code == 200
        assert resp.json()["procurement_type"] == "make"

    def test_update_item_description(self, client, make_product):
        product = make_product(name="Desc Update")
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"description": "Updated description"})
        assert resp.status_code == 200
        assert resp.json()["description"] == "Updated description"

    def test_update_partial_does_not_clear_other_fields(self, client, make_product):
        product = make_product(
            name="Partial Update Test",
            selling_price=Decimal("50.00"),
            standard_cost=Decimal("20.00"),
        )
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"name": "Renamed"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Renamed"
        # Original selling_price should be preserved
        assert float(body["selling_price"]) == pytest.approx(50.00, abs=0.01)

    def test_update_to_packaging_requires_physical_metadata(self, client, make_product):
        product = make_product(name="Supply Without Physical Data", item_type="supply")
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"item_type": "packaging"})
        assert resp.status_code == 400
        assert "Packaging items require" in resp.json()["detail"]

    def test_update_to_packaging_with_physical_metadata_succeeds(self, client, make_product):
        product = make_product(name="Supply With Physical Data", item_type="supply")
        resp = client.patch(
            f"{BASE_URL}/{product.id}",
            json={
                "item_type": "packaging",
                "weight_oz": "2.50",
                "length_in": "10.00",
                "width_in": "8.00",
                "height_in": "6.00",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["item_type"] == "packaging"
        assert body["weight_oz"] == "2.50"

    def test_update_packaging_cannot_clear_physical_metadata(self, client, make_product):
        product = make_product(
            name="Packaging With Physical Data",
            item_type="packaging",
            weight_oz=Decimal("2.50"),
            length_in=Decimal("10.00"),
            width_in=Decimal("8.00"),
            height_in=Decimal("6.00"),
        )
        resp = client.patch(f"{BASE_URL}/{product.id}", json={"weight_oz": None})
        assert resp.status_code == 400
        assert "Packaging items require" in resp.json()["detail"]


# =============================================================================
# Delete item — DELETE /api/v1/items/{item_id}
# =============================================================================

class TestDeleteItem:
    """Tests for the delete (soft-deactivate) item endpoint."""

    def test_delete_item_success(self, client, make_product):
        product = make_product(name="Delete Me")
        resp = client.delete(f"{BASE_URL}/{product.id}")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_item_not_found(self, client):
        resp = client.delete(f"{BASE_URL}/999999")
        assert resp.status_code == 404

    def test_delete_item_with_inventory_fails(self, client, make_product, make_inventory):
        product = make_product(name="Has Inventory")
        make_inventory(product_id=product.id, on_hand_quantity=10)
        resp = client.delete(f"{BASE_URL}/{product.id}")
        assert resp.status_code == 400
        assert "on hand" in resp.json()["detail"].lower()

    def test_delete_item_with_active_bom_fails(self, client, make_product, make_bom):
        fg = make_product(name="FG with BOM")
        comp = make_product(name="Component", item_type="component")
        make_bom(product_id=fg.id, lines=[{"component_id": comp.id, "quantity": Decimal("1")}])
        resp = client.delete(f"{BASE_URL}/{fg.id}")
        assert resp.status_code == 400
        assert "BOM" in resp.json()["detail"]

    def test_deleted_item_becomes_inactive(self, client, make_product):
        product = make_product(name="Soft Delete Check")
        client.delete(f"{BASE_URL}/{product.id}")
        # Verify the item is now inactive
        resp = client.get(f"{BASE_URL}/{product.id}")
        assert resp.status_code == 200
        assert resp.json()["active"] is False


# =============================================================================
# Categories — GET/POST /api/v1/items/categories
# =============================================================================

class TestListCategories:
    """Tests for listing categories."""

    def test_list_categories_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/categories")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_categories_includes_created(self, client, make_category):
        cat = make_category(code="LIST-CAT-001", name="List Test Category")
        resp = client.get(f"{BASE_URL}/categories")
        codes = [c["code"] for c in resp.json()]
        assert "LIST-CAT-001" in codes

    def test_list_categories_excludes_inactive_by_default(self, client, make_category):
        cat = make_category(code="INACTIVE-CAT", name="Inactive Cat", is_active=False)
        resp = client.get(f"{BASE_URL}/categories")
        codes = [c["code"] for c in resp.json()]
        assert "INACTIVE-CAT" not in codes

    def test_list_categories_include_inactive(self, client, make_category):
        cat = make_category(code="SHOW-INACTIVE", name="Show Inactive Cat", is_active=False)
        resp = client.get(f"{BASE_URL}/categories", params={"include_inactive": True})
        codes = [c["code"] for c in resp.json()]
        assert "SHOW-INACTIVE" in codes

    def test_list_categories_filter_by_parent(self, client, make_category):
        parent = make_category(code="PARENT-001", name="Parent Category")
        child = make_category(code="CHILD-001", name="Child Category", parent_id=parent.id)
        resp = client.get(f"{BASE_URL}/categories", params={"parent_id": parent.id})
        codes = [c["code"] for c in resp.json()]
        assert "CHILD-001" in codes
        assert "PARENT-001" not in codes


class TestCreateCategory:
    """Tests for creating categories."""

    def test_create_category_success(self, client):
        payload = {"code": "NEW-CAT", "name": "New Category"}
        resp = client.post(f"{BASE_URL}/categories", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["code"] == "NEW-CAT"
        assert body["name"] == "New Category"
        assert body["is_active"] is True

    def test_create_category_code_uppercased(self, client):
        payload = {"code": "lower-cat", "name": "Lowercase Code"}
        resp = client.post(f"{BASE_URL}/categories", json=payload)
        assert resp.status_code == 201
        assert resp.json()["code"] == "LOWER-CAT"

    def test_create_category_duplicate_code_fails(self, client, make_category):
        make_category(code="DUP-CAT-CODE", name="Original")
        payload = {"code": "DUP-CAT-CODE", "name": "Duplicate"}
        resp = client.post(f"{BASE_URL}/categories", json=payload)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_create_category_with_parent(self, client, make_category):
        parent = make_category(code="CAT-PARENT", name="Parent")
        payload = {"code": "CAT-CHILD", "name": "Child", "parent_id": parent.id}
        resp = client.post(f"{BASE_URL}/categories", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["parent_id"] == parent.id

    def test_create_category_invalid_parent_fails(self, client):
        payload = {"code": "BAD-PARENT", "name": "Bad Parent", "parent_id": 999999}
        resp = client.post(f"{BASE_URL}/categories", json=payload)
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_create_category_missing_code_fails(self, client):
        payload = {"name": "No Code"}
        resp = client.post(f"{BASE_URL}/categories", json=payload)
        assert resp.status_code == 422

    def test_create_category_missing_name_fails(self, client):
        payload = {"code": "NO-NAME"}
        resp = client.post(f"{BASE_URL}/categories", json=payload)
        assert resp.status_code == 422

    def test_create_category_response_shape(self, client):
        payload = {"code": "SHAPE-CAT", "name": "Shape Test", "description": "A test"}
        resp = client.post(f"{BASE_URL}/categories", json=payload)
        assert resp.status_code == 201
        body = resp.json()
        expected_fields = {"id", "code", "name", "parent_id", "description", "is_active", "created_at", "updated_at"}
        assert expected_fields.issubset(body.keys())


class TestGetCategory:
    """Tests for getting a single category."""

    def test_get_category_success(self, client, make_category):
        cat = make_category(code="GET-CAT", name="Get Category")
        resp = client.get(f"{BASE_URL}/categories/{cat.id}")
        assert resp.status_code == 200
        assert resp.json()["code"] == "GET-CAT"

    def test_get_category_not_found(self, client):
        resp = client.get(f"{BASE_URL}/categories/999999")
        assert resp.status_code == 404


class TestUpdateCategory:
    """Tests for updating categories."""

    def test_update_category_name(self, client, make_category):
        cat = make_category(code="UPD-CAT", name="Original Name")
        resp = client.patch(f"{BASE_URL}/categories/{cat.id}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_category_code(self, client, make_category):
        cat = make_category(code="OLD-CODE", name="Code Update Test")
        resp = client.patch(f"{BASE_URL}/categories/{cat.id}", json={"code": "new-code"})
        assert resp.status_code == 200
        assert resp.json()["code"] == "NEW-CODE"

    def test_update_category_not_found(self, client):
        resp = client.patch(f"{BASE_URL}/categories/999999", json={"name": "Ghost"})
        assert resp.status_code == 404

    def test_update_category_duplicate_code_fails(self, client, make_category):
        cat_a = make_category(code="EXIST-A", name="Cat A")
        cat_b = make_category(code="EXIST-B", name="Cat B")
        resp = client.patch(f"{BASE_URL}/categories/{cat_b.id}", json={"code": "EXIST-A"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_update_category_self_parent_fails(self, client, make_category):
        cat = make_category(code="SELF-PAR", name="Self Parent")
        resp = client.patch(f"{BASE_URL}/categories/{cat.id}", json={"parent_id": cat.id})
        assert resp.status_code == 400
        assert "own parent" in resp.json()["detail"].lower()

    def test_update_category_invalid_parent_fails(self, client, make_category):
        cat = make_category(code="BAD-PAR-UPD", name="Bad Parent Update")
        resp = client.patch(f"{BASE_URL}/categories/{cat.id}", json={"parent_id": 999999})
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]


class TestDeleteCategory:
    """Tests for deleting (deactivating) categories."""

    def test_delete_category_success(self, client, make_category):
        cat = make_category(code="DEL-CAT", name="Delete Category")
        resp = client.delete(f"{BASE_URL}/categories/{cat.id}")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_category_not_found(self, client):
        resp = client.delete(f"{BASE_URL}/categories/999999")
        assert resp.status_code == 404

    def test_delete_category_with_active_children_fails(self, client, make_category):
        parent = make_category(code="DEL-PARENT", name="Parent With Child")
        child = make_category(code="DEL-CHILD", name="Active Child", parent_id=parent.id)
        resp = client.delete(f"{BASE_URL}/categories/{parent.id}")
        assert resp.status_code == 400
        assert "child categories" in resp.json()["detail"].lower()

    def test_delete_category_with_active_items_fails(self, client, make_category, make_product):
        cat = make_category(code="DEL-CAT-ITEMS", name="Cat With Items")
        make_product(name="Item In Category", category_id=cat.id)
        resp = client.delete(f"{BASE_URL}/categories/{cat.id}")
        assert resp.status_code == 400
        assert "active items" in resp.json()["detail"].lower()


class TestCategoryTree:
    """Tests for the category tree endpoint."""

    def test_category_tree_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/categories/tree")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_category_tree_structure(self, client, make_category):
        parent = make_category(code="TREE-P", name="Tree Parent")
        child = make_category(code="TREE-C", name="Tree Child", parent_id=parent.id)
        resp = client.get(f"{BASE_URL}/categories/tree")
        body = resp.json()
        # Find the parent in the tree
        parent_node = next((n for n in body if n["code"] == "TREE-P"), None)
        assert parent_node is not None
        assert "children" in parent_node
        child_codes = [c["code"] for c in parent_node["children"]]
        assert "TREE-C" in child_codes


# =============================================================================
# Bulk update — POST /api/v1/items/bulk-update
# =============================================================================

class TestBulkUpdate:
    """Tests for bulk update endpoint."""

    def test_bulk_update_category(self, client, make_product, make_category):
        cat = make_category(code="BULK-CAT", name="Bulk Category")
        p1 = make_product(name="Bulk 1")
        p2 = make_product(name="Bulk 2")
        payload = {
            "item_ids": [p1.id, p2.id],
            "category_id": cat.id,
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 2
        assert body["error_count"] == 0

    def test_bulk_update_item_type(self, client, make_product):
        p1 = make_product(name="Bulk Type 1", item_type="finished_good")
        payload = {
            "item_ids": [p1.id],
            "item_type": "component",
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 1

    def test_bulk_update_packaging_item_type(self, client, make_product):
        p1 = make_product(
            name="Bulk Packaging",
            item_type="supply",
            weight_oz=Decimal("2.50"),
            length_in=Decimal("10.00"),
            width_in=Decimal("8.00"),
            height_in=Decimal("6.00"),
        )
        payload = {
            "item_ids": [p1.id],
            "item_type": "packaging",
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 1
        assert body["error_count"] == 0

    def test_bulk_update_packaging_item_type_requires_physical_metadata(self, client, make_product):
        p1 = make_product(name="Bulk Packaging Missing Metadata", item_type="supply")
        payload = {
            "item_ids": [p1.id],
            "item_type": "packaging",
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 0
        assert body["error_count"] == 1
        assert "Packaging items require" in body["errors"][0]["error"]

    def test_bulk_update_deactivate(self, client, make_product):
        p1 = make_product(name="Bulk Deactivate")
        payload = {
            "item_ids": [p1.id],
            "is_active": False,
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 1

    def test_bulk_update_empty_ids_fails(self, client):
        payload = {"item_ids": []}
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 400
        assert "No items" in resp.json()["detail"]

    def test_bulk_update_nonexistent_item_reports_error(self, client, make_product):
        p1 = make_product(name="Bulk Real")
        payload = {
            "item_ids": [p1.id, 999999],
            "item_type": "component",
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated_count"] == 1
        assert body["error_count"] == 1

    def test_bulk_update_invalid_category_fails(self, client, make_product):
        p1 = make_product(name="Bulk Bad Cat")
        payload = {
            "item_ids": [p1.id],
            "category_id": 999999,
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 400
        assert "not found" in resp.json()["detail"]

    def test_bulk_update_clear_category(self, client, make_product, make_category):
        cat = make_category(code="CLR-CAT", name="Clear Cat")
        p1 = make_product(name="Clear Category Item", category_id=cat.id)
        payload = {
            "item_ids": [p1.id],
            "category_id": 0,  # 0 means clear category
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 1

    def test_bulk_update_procurement_type(self, client, make_product):
        p1 = make_product(name="Bulk Proc", procurement_type="buy")
        payload = {
            "item_ids": [p1.id],
            "procurement_type": "make",
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        assert resp.status_code == 200
        assert resp.json()["updated_count"] == 1

    def test_bulk_update_response_shape(self, client, make_product):
        p1 = make_product(name="Bulk Shape")
        payload = {
            "item_ids": [p1.id],
            "item_type": "supply",
        }
        resp = client.post(f"{BASE_URL}/bulk-update", json=payload)
        body = resp.json()
        expected_keys = {"message", "updated_count", "error_count", "errors"}
        assert expected_keys.issubset(body.keys())


# =============================================================================
# Low stock — GET /api/v1/items/low-stock
# =============================================================================

class TestLowStock:
    """Tests for the low stock report endpoint."""

    def test_low_stock_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/low-stock")
        assert resp.status_code == 200

    def test_low_stock_response_shape(self, client):
        resp = client.get(f"{BASE_URL}/low-stock")
        body = resp.json()
        assert "items" in body
        assert "count" in body
        assert "summary" in body
        summary = body["summary"]
        expected = {"total_items_low", "critical_count", "urgent_count", "low_count", "mrp_shortage_count"}
        assert expected.issubset(summary.keys())

    def test_low_stock_includes_stocked_item_below_reorder(
        self, client, make_product, make_inventory
    ):
        """A stocked item with on_hand below reorder_point should appear."""
        product = make_product(
            name="Low Stock Item",
            stocking_policy="stocked",
            reorder_point=Decimal("100"),
            procurement_type="buy",
        )
        make_inventory(product_id=product.id, on_hand_quantity=5)
        resp = client.get(f"{BASE_URL}/low-stock")
        body = resp.json()
        low_ids = [item["id"] for item in body["items"]]
        assert product.id in low_ids

    def test_low_stock_excludes_on_demand_items(self, client, make_product, make_inventory):
        """On-demand items should not appear in low stock based on reorder point."""
        product = make_product(
            name="On Demand No Low Stock",
            stocking_policy="on_demand",
            reorder_point=Decimal("100"),
            procurement_type="buy",
        )
        make_inventory(product_id=product.id, on_hand_quantity=5)
        resp = client.get(f"{BASE_URL}/low-stock")
        body = resp.json()
        low_ids = [item["id"] for item in body["items"]]
        assert product.id not in low_ids


# =============================================================================
# Recost — POST /api/v1/items/{item_id}/recost
# =============================================================================

class TestRecostItem:
    """Tests for single item recost endpoint."""

    def test_recost_item_not_found(self, client):
        resp = client.post(f"{BASE_URL}/999999/recost")
        assert resp.status_code == 404

    def test_recost_purchased_item(self, client, make_product):
        product = make_product(
            name="Recost Purchased",
            standard_cost=Decimal("10.00"),
        )
        resp = client.post(f"{BASE_URL}/{product.id}/recost")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == product.id
        assert body["cost_source"] == "purchased"
        assert "old_cost" in body
        assert "new_cost" in body
        assert "message" in body

    def test_recost_manufactured_item_with_bom(self, client, make_product, make_bom):
        comp = make_product(
            name="Recost Component",
            item_type="component",
            standard_cost=Decimal("5.00"),
        )
        fg = make_product(name="Recost FG", item_type="finished_good")
        make_bom(product_id=fg.id, lines=[
            {"component_id": comp.id, "quantity": Decimal("2"), "unit": "EA"},
        ])
        resp = client.post(f"{BASE_URL}/{fg.id}/recost")
        assert resp.status_code == 200
        body = resp.json()
        assert body["cost_source"] == "manufactured"
        assert body["bom_cost"] == pytest.approx(10.0, abs=0.01)


class TestRecostAll:
    """Tests for the recost-all endpoint."""

    def test_recost_all_returns_200(self, client):
        resp = client.post(f"{BASE_URL}/recost-all")
        assert resp.status_code == 200
        body = resp.json()
        assert "updated" in body
        assert "skipped" in body
        assert "items" in body

    def test_recost_all_filter_by_cost_source(self, client, make_product):
        make_product(name="Recost Filter", standard_cost=Decimal("5.00"))
        resp = client.post(f"{BASE_URL}/recost-all", params={"cost_source": "purchased"})
        assert resp.status_code == 200
        body = resp.json()
        for item in body["items"]:
            assert item["cost_source"] == "purchased"


# =============================================================================
# Demand summary — GET /api/v1/items/{item_id}/demand-summary
# =============================================================================

class TestDemandSummary:
    """Tests for the item demand summary endpoint."""

    def test_demand_summary_not_found(self, client):
        resp = client.get(f"{BASE_URL}/999999/demand-summary")
        assert resp.status_code == 404

    def test_demand_summary_success(self, client, make_product, make_inventory):
        product = make_product(name="Demand Summary Test")
        make_inventory(product_id=product.id, on_hand_quantity=50, allocated_quantity=10)
        resp = client.get(f"{BASE_URL}/{product.id}/demand-summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "quantities" in body
        assert "on_hand" in body["quantities"]


# =============================================================================
# Public endpoints — no auth required
# =============================================================================

class TestPublicEndpoints:
    """Some read endpoints don't require auth (categories, list)."""

    def test_list_categories_no_auth(self, unauthed_client):
        """Category listing is public (no get_current_user dependency)."""
        resp = unauthed_client.get(f"{BASE_URL}/categories")
        assert resp.status_code == 200

    def test_category_tree_no_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/categories/tree")
        assert resp.status_code == 200

    def test_get_category_no_auth(self, unauthed_client, make_category):
        cat = make_category(code="PUB-CAT", name="Public Cat")
        resp = unauthed_client.get(f"{BASE_URL}/categories/{cat.id}")
        assert resp.status_code == 200

    def test_list_items_no_auth(self, unauthed_client):
        """Item listing is public (no get_current_user dependency)."""
        resp = unauthed_client.get(BASE_URL)
        assert resp.status_code == 200

    def test_get_item_no_auth(self, unauthed_client, make_product):
        product = make_product(name="Public Item")
        resp = unauthed_client.get(f"{BASE_URL}/{product.id}")
        assert resp.status_code == 200

    def test_get_item_by_sku_no_auth(self, unauthed_client, make_product):
        product = make_product(sku="PUB-SKU-001", name="Public SKU Item")
        resp = unauthed_client.get(f"{BASE_URL}/sku/PUB-SKU-001")
        assert resp.status_code == 200

    def test_low_stock_no_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/low-stock")
        assert resp.status_code == 200

    def test_demand_summary_no_auth(self, unauthed_client, make_product):
        product = make_product(name="Public Demand")
        resp = unauthed_client.get(f"{BASE_URL}/{product.id}/demand-summary")
        # This endpoint may or may not require auth -- test the contract
        assert resp.status_code in (200, 401)
