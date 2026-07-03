"""
Tests for Products API endpoints (/api/v1/products).

Covers:
- Authentication requirements for all endpoints
- List products with filtering (category, active, search, has_bom, procurement_type, pagination)
- Get product by ID
- Get product by SKU (exact match)
- Create product (duplicate SKU check)
- Update product (SKU change blocked by transactions, duplicate SKU check)
- Product routing endpoint (empty ops when no routing, 404)
"""
import uuid
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/products"


def _uid():
    """Short unique suffix to ensure SKU uniqueness across tests."""
    return uuid.uuid4().hex[:8].upper()


# =============================================================================
# Authentication — All endpoints require auth
# =============================================================================


class TestProductAuth:
    """Verify all product endpoints require authentication."""

    def test_list_products_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(BASE_URL)
        assert resp.status_code == 401

    def test_get_product_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1")
        assert resp.status_code == 401

    def test_get_product_by_sku_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/sku/SOME-SKU")
        assert resp.status_code == 401

    def test_create_product_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE_URL, json={"sku": "X", "name": "X"})
        assert resp.status_code == 401

    def test_update_product_requires_auth(self, unauthed_client):
        resp = unauthed_client.put(f"{BASE_URL}/1", json={"name": "X"})
        assert resp.status_code == 401

    def test_get_routing_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1/routing")
        assert resp.status_code == 401


# =============================================================================
# List products — GET /api/v1/products
# =============================================================================


class TestProductList:
    """Tests for the list products endpoint."""

    def test_list_returns_200(self, client):
        resp = client.get(BASE_URL)
        assert resp.status_code == 200

    def test_list_returns_total_and_items(self, client):
        resp = client.get(BASE_URL)
        body = resp.json()
        assert "total" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_list_empty_when_no_matching_products(self, client):
        resp = client.get(BASE_URL, params={"search": f"NONEXISTENT-{_uid()}"})
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_includes_created_product(self, client, make_product):
        uid = _uid()
        product = make_product(sku=f"LST-{uid}", name=f"List Test {uid}")
        resp = client.get(BASE_URL, params={"search": uid})
        assert resp.status_code == 200
        body = resp.json()
        skus = [item["sku"] for item in body["items"]]
        assert product.sku in skus

    def test_list_exposes_has_routing(self, client, db, make_product):
        """Routing-built products (no BOM) must report has_routing=True so the
        sales-order product picker treats them as sellable. Without this field
        the picker filters them out as "No sellable products" (issue #883)."""
        from app.models.manufacturing import Routing

        uid = _uid()
        routed = make_product(sku=f"HASRT-{uid}", name=f"Routed {uid}")
        db.add(Routing(product_id=routed.id, code=f"RT-{uid}", name="R", is_active=True))
        plain = make_product(sku=f"NORT-{uid}", name=f"Plain {uid}")
        db.flush()

        resp = client.get(BASE_URL, params={"search": uid})
        assert resp.status_code == 200
        items = {i["sku"]: i for i in resp.json()["items"]}
        assert items[routed.sku]["has_routing"] is True
        assert items[plain.sku]["has_routing"] is False

    @pytest.mark.parametrize("legacy_unit", [None, "", "   "])
    def test_list_defaults_legacy_blank_unit(self, client, db, make_product, legacy_unit):
        """Legacy product rows with NULL/blank unit should not break API responses."""
        uid = _uid()
        product = make_product(
            sku=f"NULLUNIT-{uid}",
            name=f"Null Unit {uid}",
        )
        product.unit = legacy_unit
        db.flush()

        resp = client.get(BASE_URL, params={"search": uid})

        assert resp.status_code == 200
        body = resp.json()
        item = next(item for item in body["items"] if item["sku"] == product.sku)
        assert item["unit"] == "EA"

    def test_list_active_only_default(self, client, make_product):
        """Default active_only=True excludes inactive products."""
        uid = _uid()
        make_product(sku=f"INACT-{uid}", name=f"Inactive {uid}", active=False)
        resp = client.get(BASE_URL, params={"search": uid})
        body = resp.json()
        assert all(item["active"] for item in body["items"])

    def test_list_include_inactive(self, client, make_product):
        uid = _uid()
        product = make_product(sku=f"INCINC-{uid}", name=f"IncludeInactive {uid}", active=False)
        resp = client.get(BASE_URL, params={"active_only": False, "search": uid})
        body = resp.json()
        skus = [item["sku"] for item in body["items"]]
        assert product.sku in skus

    def test_list_search_by_sku(self, client, make_product):
        uid = _uid()
        product = make_product(sku=f"SKUSRC-{uid}", name=f"SKU Search {uid}")
        resp = client.get(BASE_URL, params={"search": f"SKUSRC-{uid}"})
        body = resp.json()
        assert any(item["sku"] == product.sku for item in body["items"])

    def test_list_search_by_name(self, client, make_product):
        uid = _uid()
        make_product(name=f"UniqueNameSearch-{uid}")
        resp = client.get(BASE_URL, params={"search": f"UniqueNameSearch-{uid}"})
        body = resp.json()
        assert body["total"] >= 1

    def test_list_filter_has_bom_true(self, client, make_product):
        uid = _uid()
        make_product(sku=f"BOM-T-{uid}", name=f"HasBom {uid}", has_bom=True)
        resp = client.get(BASE_URL, params={"has_bom": True, "search": uid})
        body = resp.json()
        for item in body["items"]:
            assert item["has_bom"] is True

    def test_list_filter_has_bom_false(self, client, make_product):
        uid = _uid()
        make_product(sku=f"BOM-F-{uid}", name=f"NoBom {uid}", has_bom=False)
        resp = client.get(BASE_URL, params={"has_bom": False, "search": uid})
        body = resp.json()
        for item in body["items"]:
            assert item["has_bom"] is False

    def test_list_filter_procurement_type(self, client, make_product):
        uid = _uid()
        make_product(
            sku=f"PROC-{uid}", name=f"ProcFilter {uid}", procurement_type="make"
        )
        resp = client.get(BASE_URL, params={"procurement_type": "make", "search": uid})
        body = resp.json()
        assert body["total"] >= 1

    def test_list_pagination_limit(self, client, make_product):
        uid = _uid()
        for i in range(4):
            make_product(sku=f"PAG-{uid}-{i}", name=f"Page {uid} {i}")
        resp = client.get(BASE_URL, params={"search": uid, "limit": 2})
        body = resp.json()
        assert len(body["items"]) <= 2

    def test_list_pagination_offset(self, client, make_product):
        uid = _uid()
        for i in range(4):
            make_product(sku=f"OFF-{uid}-{i}", name=f"Offset {uid} {i}")
        resp_first = client.get(BASE_URL, params={"search": uid, "limit": 2, "offset": 0})
        resp_second = client.get(BASE_URL, params={"search": uid, "limit": 2, "offset": 2})
        first_ids = {item["id"] for item in resp_first.json()["items"]}
        second_ids = {item["id"] for item in resp_second.json()["items"]}
        assert first_ids.isdisjoint(second_ids)

    def test_list_total_reflects_all_matching(self, client, make_product):
        uid = _uid()
        for i in range(3):
            make_product(sku=f"TOT-{uid}-{i}", name=f"Total {uid} {i}")
        resp = client.get(BASE_URL, params={"search": uid, "limit": 1})
        body = resp.json()
        assert body["total"] >= 3
        assert len(body["items"]) == 1


# =============================================================================
# Get product by ID — GET /api/v1/products/{id}
# =============================================================================


class TestProductGetById:
    """Tests for the get product by ID endpoint."""

    def test_get_product_success(self, client, make_product):
        product = make_product(name="GetById Test")
        resp = client.get(f"{BASE_URL}/{product.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == product.id
        assert body["sku"] == product.sku
        assert body["name"] == "GetById Test"

    def test_get_product_not_found(self, client):
        resp = client.get(f"{BASE_URL}/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_product_response_shape(self, client, make_product):
        product = make_product(
            name="Shape Test Product",
            selling_price=Decimal("25.00"),
        )
        resp = client.get(f"{BASE_URL}/{product.id}")
        body = resp.json()
        expected_fields = {"id", "sku", "name", "unit", "is_raw_material", "has_bom", "active", "created_at"}
        assert expected_fields.issubset(body.keys())


# =============================================================================
# Get product by SKU — GET /api/v1/products/sku/{sku}
# =============================================================================


class TestProductGetBySku:
    """Tests for the get product by SKU endpoint."""

    def test_get_by_sku_success(self, client, make_product):
        uid = _uid()
        sku = f"SKUGET-{uid}"
        product = make_product(sku=sku, name=f"SKU Get Test {uid}")
        resp = client.get(f"{BASE_URL}/sku/{sku}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["sku"] == sku
        assert body["id"] == product.id

    def test_get_by_sku_not_found(self, client):
        resp = client.get(f"{BASE_URL}/sku/DOES-NOT-EXIST-{_uid()}")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_by_sku_exact_match(self, client, make_product):
        """SKU lookup uses exact match (==), not ilike."""
        uid = _uid()
        sku = f"EXACT-{uid}"
        make_product(sku=sku, name=f"Exact Match {uid}")
        # Partial match should not work
        resp = client.get(f"{BASE_URL}/sku/EXACT")
        assert resp.status_code == 404


# =============================================================================
# Create product — POST /api/v1/products
# =============================================================================


class TestProductCreate:
    """Tests for the create product endpoint."""

    def test_create_product_success(self, client):
        uid = _uid()
        payload = {
            "sku": f"CRT-{uid}",
            "name": f"Created Product {uid}",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["sku"] == f"CRT-{uid}"
        assert body["name"] == f"Created Product {uid}"
        assert "id" in body
        assert "created_at" in body

    def test_create_product_with_all_fields(self, client):
        uid = _uid()
        payload = {
            "sku": f"FULL-{uid}",
            "name": f"Full Product {uid}",
            "description": "A fully specified product",
            "unit": "KG",
            "standard_cost": 12.50,
            "selling_price": 29.99,
            "is_raw_material": True,
            "active": True,
            "image_url": "https://example.com/image.png",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["sku"] == f"FULL-{uid}"
        assert body["is_raw_material"] is True

    def test_create_product_duplicate_sku_returns_400(self, client, make_product):
        uid = _uid()
        sku = f"DUPSKU-{uid}"
        make_product(sku=sku, name=f"Original {uid}")
        payload = {
            "sku": sku,
            "name": f"Duplicate {uid}",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_create_product_defaults(self, client):
        uid = _uid()
        payload = {
            "sku": f"DEF-{uid}",
            "name": f"Defaults Product {uid}",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["unit"] == "EA"
        assert body["is_raw_material"] is False
        assert body["active"] is True

    def test_create_product_missing_sku_returns_422(self, client):
        payload = {"name": "No SKU"}
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 422

    def test_create_product_missing_name_returns_422(self, client):
        payload = {"sku": f"NONAME-{_uid()}"}
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 422


# =============================================================================
# Update product — PUT /api/v1/products/{id}
# =============================================================================


class TestProductUpdate:
    """Tests for the update product endpoint."""

    def test_update_product_name(self, client, make_product):
        product = make_product(name="Before Update")
        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"name": "After Update"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "After Update"

    def test_update_product_not_found(self, client):
        resp = client.put(f"{BASE_URL}/999999", json={"name": "Ghost"})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_update_sku_success_no_transactions(self, client, make_product):
        """SKU change allowed when product has no transactional history."""
        uid = _uid()
        product = make_product(sku=f"OLD-{uid}", name=f"SKU Change {uid}")
        new_sku = f"NEW-{uid}"
        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"sku": new_sku},
        )
        assert resp.status_code == 200
        assert resp.json()["sku"] == new_sku

    def test_update_sku_blocked_by_po_lines(self, client, db, make_product, make_vendor, make_purchase_order):
        """SKU change blocked when product has purchase order lines."""
        from app.models.purchase_order import PurchaseOrderLine

        uid = _uid()
        product = make_product(sku=f"POBLOCK-{uid}", name=f"PO Block {uid}")
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        po_line = PurchaseOrderLine(
            purchase_order_id=po.id,
            product_id=product.id,
            line_number=1,
            quantity_ordered=Decimal("10"),
            unit_cost=Decimal("5.00"),
            line_total=Decimal("50.00"),
        )
        db.add(po_line)
        db.flush()

        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"sku": f"NEWSKU-{uid}"},
        )
        assert resp.status_code == 400
        assert "Cannot change SKU" in resp.json()["detail"]
        assert "purchase order" in resp.json()["detail"].lower()

    def test_update_sku_blocked_by_inventory_transactions(self, client, db, make_product):
        """SKU change blocked when product has inventory transactions."""
        from app.models.inventory import InventoryTransaction

        uid = _uid()
        product = make_product(sku=f"INVBLOCK-{uid}", name=f"Inv Block {uid}")
        txn = InventoryTransaction(
            product_id=product.id,
            location_id=1,
            quantity=Decimal("10"),
            transaction_type="receipt",
            reference_type="adjustment",
        )
        db.add(txn)
        db.flush()

        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"sku": f"NEWSKU-{uid}"},
        )
        assert resp.status_code == 400
        assert "Cannot change SKU" in resp.json()["detail"]
        assert "inventory transaction" in resp.json()["detail"].lower()

    def test_update_sku_blocked_by_material_lots(self, client, db, make_product):
        """SKU change blocked when product has material lots."""
        from app.models.traceability import MaterialLot

        uid = _uid()
        product = make_product(sku=f"LOTBLOCK-{uid}", name=f"Lot Block {uid}")
        lot = MaterialLot(
            product_id=product.id,
            lot_number=f"LOT-{uid}",
            quantity_received=Decimal("100"),
        )
        db.add(lot)
        db.flush()

        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"sku": f"NEWSKU-{uid}"},
        )
        assert resp.status_code == 400
        assert "Cannot change SKU" in resp.json()["detail"]
        assert "material lot" in resp.json()["detail"].lower()

    def test_update_sku_duplicate_returns_400(self, client, make_product):
        """Changing SKU to one that already exists returns 400."""
        uid = _uid()
        existing = make_product(sku=f"EXIST-{uid}", name=f"Existing {uid}")
        target = make_product(sku=f"TARGET-{uid}", name=f"Target {uid}")
        resp = client.put(
            f"{BASE_URL}/{target.id}",
            json={"sku": existing.sku},
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_update_same_sku_no_error(self, client, make_product):
        """Setting the same SKU value should succeed (no change detected)."""
        uid = _uid()
        sku = f"SAME-{uid}"
        product = make_product(sku=sku, name=f"Same SKU {uid}")
        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"sku": sku, "name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_partial_preserves_other_fields(self, client, make_product):
        uid = _uid()
        product = make_product(
            sku=f"PART-{uid}",
            name=f"Partial {uid}",
            selling_price=Decimal("50.00"),
        )
        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Renamed"
        assert body["sku"] == f"PART-{uid}"

    def test_update_deactivate_product(self, client, make_product):
        product = make_product(name="Deactivate Me")
        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["active"] is False


# =============================================================================
# Product routing — GET /api/v1/products/{product_id}/routing
# =============================================================================


class TestProductRouting:
    """Tests for the product routing endpoint."""

    def test_routing_no_routing_returns_empty_ops(self, client, make_product):
        """Product with no routing returns empty operations list."""
        product = make_product(name="No Routing Product")
        resp = client.get(f"{BASE_URL}/{product.id}/routing")
        assert resp.status_code == 200
        body = resp.json()
        assert body["product_id"] == product.id
        assert body["routing_id"] is None
        assert body["operations"] == []

    def test_routing_product_not_found(self, client):
        resp = client.get(f"{BASE_URL}/999999/routing")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_routing_response_shape(self, client, make_product):
        product = make_product(name="Routing Shape Product")
        resp = client.get(f"{BASE_URL}/{product.id}/routing")
        assert resp.status_code == 200
        body = resp.json()
        expected_fields = {"product_id", "routing_id", "operations"}
        assert expected_fields.issubset(body.keys())
