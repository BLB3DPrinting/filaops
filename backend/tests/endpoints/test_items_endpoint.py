"""
Endpoint tests for Items API (/api/v1/items).

Tests the main CRUD paths:
- GET  /api/v1/items       (list with filters)
- GET  /api/v1/items/{id}  (get by id)
- POST /api/v1/items       (create)
- PATCH /api/v1/items/{id} (update — the endpoint uses PATCH, not PUT)
- DELETE /api/v1/items/{id} (soft delete)
"""
import uuid

import pytest
from decimal import Decimal


BASE = "/api/v1/items"


def _uid():
    return uuid.uuid4().hex[:8]


# =============================================================================
# GET /api/v1/items — list items
# =============================================================================

class TestListItems:
    """List items endpoint with filtering and pagination."""

    def test_list_returns_200_with_structure(self, client):
        """Response is 200 with 'total' and 'items' keys."""
        resp = client.get(BASE)
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_list_includes_created_item(self, client, make_product):
        """A freshly created product appears in the list."""
        uid = _uid()
        product = make_product(name=f"ListTest-{uid}")
        resp = client.get(BASE, params={"search": f"ListTest-{uid}"})
        assert resp.status_code == 200
        skus = [i["sku"] for i in resp.json()["items"]]
        assert product.sku in skus

    def test_list_filter_by_item_type(self, client, make_product):
        """Filtering by item_type returns only matching items."""
        make_product(item_type="component", name=f"Comp-{_uid()}")
        resp = client.get(BASE, params={"item_type": "component"})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["item_type"] == "component"

    def test_list_filter_by_procurement_type(self, client, make_product):
        """Filtering by procurement_type works."""
        make_product(procurement_type="make", name=f"Make-{_uid()}")
        resp = client.get(BASE, params={"procurement_type": "make"})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["procurement_type"] == "make"

    def test_list_search_by_sku(self, client, make_product):
        uid = _uid()
        sku = f"SRCH-{uid}"
        make_product(sku=sku, name=f"Search SKU {uid}")
        resp = client.get(BASE, params={"search": sku})
        assert resp.status_code == 200
        assert any(i["sku"] == sku for i in resp.json()["items"])

    def test_list_search_by_name(self, client, make_product):
        uid = _uid()
        name = f"UniqueNameSearch-{uid}"
        make_product(name=name)
        resp = client.get(BASE, params={"search": name})
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_list_active_only_default(self, client, make_product):
        """Default active_only=True excludes inactive items."""
        uid = _uid()
        make_product(name=f"InactiveDefault-{uid}", active=False)
        resp = client.get(BASE, params={"search": f"InactiveDefault-{uid}"})
        body = resp.json()
        assert all(i["active"] for i in body["items"])

    def test_list_include_inactive(self, client, make_product):
        uid = _uid()
        p = make_product(name=f"ShowInactive-{uid}", active=False)
        resp = client.get(BASE, params={"active_only": False, "search": f"ShowInactive-{uid}"})
        skus = [i["sku"] for i in resp.json()["items"]]
        assert p.sku in skus

    def test_list_pagination(self, client, make_product):
        """Limit and offset control result set."""
        for i in range(3):
            make_product(name=f"PageItem-{_uid()}")
        resp = client.get(BASE, params={"limit": 2, "offset": 0})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) <= 2

    def test_list_response_item_shape(self, client, make_product):
        """Each item in the list has expected fields."""
        make_product(name=f"Shape-{_uid()}", standard_cost=Decimal("10.00"))
        resp = client.get(BASE)
        assert resp.status_code == 200
        if resp.json()["items"]:
            item = resp.json()["items"][0]
            for key in ("id", "sku", "name", "item_type", "active"):
                assert key in item


# =============================================================================
# GET /api/v1/items/{item_id} — get single item
# =============================================================================

class TestGetItem:
    """Get a single item by ID."""

    def test_get_item_success(self, client, make_product):
        p = make_product(name=f"GetItem-{_uid()}")
        resp = client.get(f"{BASE}/{p.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == p.id
        assert body["sku"] == p.sku

    def test_get_item_not_found(self, client):
        resp = client.get(f"{BASE}/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_item_has_inventory_fields(self, client, make_product):
        p = make_product(name=f"InvFields-{_uid()}")
        resp = client.get(f"{BASE}/{p.id}")
        body = resp.json()
        for key in ("on_hand_qty", "available_qty", "allocated_qty"):
            assert key in body

    def test_get_item_has_bom_fields(self, client, make_product):
        p = make_product(name=f"BomFields-{_uid()}")
        resp = client.get(f"{BASE}/{p.id}")
        body = resp.json()
        assert "has_bom" in body
        assert "bom_count" in body

    def test_get_item_has_timestamps(self, client, make_product):
        p = make_product(name=f"Timestamps-{_uid()}")
        resp = client.get(f"{BASE}/{p.id}")
        body = resp.json()
        assert "created_at" in body
        assert "updated_at" in body


# =============================================================================
# POST /api/v1/items — create item
# =============================================================================

class TestCreateItem:
    """Create a new item."""

    def test_create_finished_good(self, client):
        uid = _uid()
        payload = {
            "name": f"New FG {uid}",
            "sku": f"EP-FG-{uid}",
            "item_type": "finished_good",
            "unit": "EA",
            "procurement_type": "buy",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["sku"] == f"EP-FG-{uid}".upper()
        assert body["name"] == f"New FG {uid}"
        assert body["item_type"] == "finished_good"

    def test_create_auto_generates_sku(self, client):
        payload = {
            "name": f"Auto SKU {_uid()}",
            "item_type": "finished_good",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 201
        assert resp.json()["sku"]  # SKU is non-empty

    def test_create_component(self, client):
        payload = {
            "name": f"Component {_uid()}",
            "item_type": "component",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 201
        assert resp.json()["sku"].startswith("COMP-")

    def test_create_supply(self, client):
        payload = {
            "name": f"Supply {_uid()}",
            "item_type": "supply",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 201
        assert resp.json()["sku"].startswith("SUP-")

    def test_create_duplicate_sku_fails(self, client, make_product):
        uid = _uid().upper()
        sku = f"DUP-{uid}"
        make_product(sku=sku)
        resp = client.post(BASE, json={"name": "Dup", "sku": sku, "item_type": "finished_good"})
        assert resp.status_code == 400

    def test_create_missing_name_returns_422(self, client):
        resp = client.post(BASE, json={"sku": f"NONAME-{_uid()}", "item_type": "finished_good"})
        assert resp.status_code == 422

    def test_create_with_costs(self, client):
        uid = _uid()
        payload = {
            "name": f"Costed {uid}",
            "sku": f"EP-COST-{uid}",
            "item_type": "finished_good",
            "standard_cost": "12.50",
            "selling_price": "29.99",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert float(body["selling_price"]) == pytest.approx(29.99, abs=0.01)

    def test_create_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE, json={"name": "NoAuth", "item_type": "finished_good"})
        assert resp.status_code == 401


# =============================================================================
# PATCH /api/v1/items/{item_id} — update item
# =============================================================================

class TestUpdateItem:
    """Update an existing item (PATCH, partial update)."""

    def test_update_name(self, client, make_product):
        p = make_product(name=f"Before-{_uid()}")
        resp = client.patch(f"{BASE}/{p.id}", json={"name": "After Update"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "After Update"

    def test_update_sku(self, client, make_product):
        p = make_product(name=f"SkuUpd-{_uid()}")
        new_sku = f"EP-UPSKU-{_uid()}"
        resp = client.patch(f"{BASE}/{p.id}", json={"sku": new_sku})
        assert resp.status_code == 200
        assert resp.json()["sku"] == new_sku.upper()

    def test_update_selling_price(self, client, make_product):
        p = make_product(name=f"PriceUpd-{_uid()}", selling_price=Decimal("10.00"))
        resp = client.patch(f"{BASE}/{p.id}", json={"selling_price": "24.99"})
        assert resp.status_code == 200
        assert float(resp.json()["selling_price"]) == pytest.approx(24.99, abs=0.01)

    def test_update_not_found(self, client):
        resp = client.patch(f"{BASE}/999999", json={"name": "Ghost"})
        assert resp.status_code == 404

    def test_update_duplicate_sku_fails(self, client, make_product):
        uid_a = _uid().upper()
        uid_b = _uid().upper()
        p_a = make_product(sku=f"EXIST-A-{uid_a}")
        p_b = make_product(sku=f"EXIST-B-{uid_b}")
        resp = client.patch(f"{BASE}/{p_b.id}", json={"sku": p_a.sku})
        assert resp.status_code == 400

    def test_partial_update_preserves_fields(self, client, make_product):
        """Updating name does not clear selling_price."""
        p = make_product(
            name=f"Partial-{_uid()}",
            selling_price=Decimal("50.00"),
            standard_cost=Decimal("20.00"),
        )
        resp = client.patch(f"{BASE}/{p.id}", json={"name": "Renamed"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Renamed"
        assert float(body["selling_price"]) == pytest.approx(50.00, abs=0.01)

    def test_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(f"{BASE}/1", json={"name": "NoAuth"})
        assert resp.status_code == 401


# =============================================================================
# DELETE /api/v1/items/{item_id} — soft delete
# =============================================================================

class TestDeleteItem:
    """Soft-delete (deactivate) an item."""

    def test_delete_success(self, client, make_product):
        p = make_product(name=f"DeleteMe-{_uid()}")
        resp = client.delete(f"{BASE}/{p.id}")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()

    def test_delete_makes_item_inactive(self, client, make_product):
        p = make_product(name=f"SoftDel-{_uid()}")
        client.delete(f"{BASE}/{p.id}")
        resp = client.get(f"{BASE}/{p.id}")
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_delete_not_found(self, client):
        resp = client.delete(f"{BASE}/999999")
        assert resp.status_code == 404

    def test_delete_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE}/1")
        assert resp.status_code == 401
