"""
Tests for Products API endpoints (/api/v1/products).

Covers the main CRUD paths:
- GET  /api/v1/products/       (list with filtering and pagination)
- GET  /api/v1/products/{id}   (get single product)
- POST /api/v1/products/       (create product)
- PUT  /api/v1/products/{id}   (update product)
"""
import uuid
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/products"


def _uid():
    """Short unique suffix to ensure SKU uniqueness across tests."""
    return uuid.uuid4().hex[:8].upper()


# =============================================================================
# GET /api/v1/products/ -- List products
# =============================================================================


class TestListProducts:
    """Tests for the list products endpoint."""

    def test_list_returns_200_with_expected_shape(self, client):
        """GET /products returns 200 with total and items keys."""
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        body = resp.json()
        assert "total" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_list_includes_created_product(self, client, make_product):
        """A freshly created product appears in list results when searched."""
        uid = _uid()
        product = make_product(sku=f"LST-{uid}", name=f"List Test {uid}")
        resp = client.get(BASE_URL, params={"search": uid})
        assert resp.status_code == 200
        body = resp.json()
        skus = [item["sku"] for item in body["items"]]
        assert product.sku in skus

    def test_list_search_returns_empty_for_nonexistent(self, client):
        """Searching for a nonexistent term returns zero results."""
        resp = client.get(BASE_URL, params={"search": f"NOPE-{_uid()}"})
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_list_active_only_excludes_inactive(self, client, make_product):
        """Default active_only=True hides inactive products."""
        uid = _uid()
        make_product(sku=f"INACT-{uid}", name=f"Inactive {uid}", active=False)
        resp = client.get(BASE_URL, params={"search": uid})
        body = resp.json()
        assert all(item["active"] for item in body["items"])

    def test_list_active_only_false_includes_inactive(self, client, make_product):
        """Setting active_only=False includes inactive products."""
        uid = _uid()
        product = make_product(sku=f"INC-{uid}", name=f"IncInact {uid}", active=False)
        resp = client.get(BASE_URL, params={"active_only": False, "search": uid})
        body = resp.json()
        skus = [item["sku"] for item in body["items"]]
        assert product.sku in skus

    def test_list_filter_has_bom(self, client, make_product):
        """Filtering by has_bom=True only returns products with BOM."""
        uid = _uid()
        make_product(sku=f"BOM-{uid}", name=f"BOM {uid}", has_bom=True)
        resp = client.get(BASE_URL, params={"has_bom": True, "search": uid})
        body = resp.json()
        for item in body["items"]:
            assert item["has_bom"] is True

    def test_list_filter_procurement_type(self, client, make_product):
        """Filtering by procurement_type narrows the results."""
        uid = _uid()
        make_product(sku=f"MK-{uid}", name=f"Maker {uid}", procurement_type="make")
        resp = client.get(BASE_URL, params={"procurement_type": "make", "search": uid})
        body = resp.json()
        assert body["total"] >= 1

    def test_list_pagination_limit(self, client, make_product):
        """The limit parameter caps the number of returned items."""
        uid = _uid()
        for i in range(4):
            make_product(sku=f"PG-{uid}-{i}", name=f"Page {uid} {i}")
        resp = client.get(BASE_URL, params={"search": uid, "limit": 2})
        body = resp.json()
        assert len(body["items"]) <= 2
        assert body["total"] >= 4

    def test_list_pagination_offset(self, client, make_product):
        """Offset returns a different slice of results."""
        uid = _uid()
        for i in range(4):
            make_product(sku=f"OFF-{uid}-{i}", name=f"Offset {uid} {i}")
        resp1 = client.get(BASE_URL, params={"search": uid, "limit": 2, "offset": 0})
        resp2 = client.get(BASE_URL, params={"search": uid, "limit": 2, "offset": 2})
        ids1 = {item["id"] for item in resp1.json()["items"]}
        ids2 = {item["id"] for item in resp2.json()["items"]}
        assert ids1.isdisjoint(ids2)

    def test_list_requires_auth(self, unauthed_client):
        """Unauthenticated requests are rejected."""
        resp = unauthed_client.get(BASE_URL)
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/products/{id} -- Get product by ID
# =============================================================================


class TestGetProduct:
    """Tests for the get product by ID endpoint."""

    def test_get_product_success(self, client, make_product):
        """Fetching a product by ID returns correct data."""
        product = make_product(name="GetById Product")
        resp = client.get(f"{BASE_URL}/{product.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == product.id
        assert body["sku"] == product.sku
        assert body["name"] == "GetById Product"

    def test_get_product_response_fields(self, client, make_product):
        """Response contains expected fields."""
        product = make_product(
            name="Field Check",
            selling_price=Decimal("25.00"),
        )
        resp = client.get(f"{BASE_URL}/{product.id}")
        body = resp.json()
        expected_fields = {
            "id", "sku", "name", "unit", "is_raw_material",
            "has_bom", "active", "created_at",
        }
        assert expected_fields.issubset(body.keys())

    def test_get_product_not_found(self, client):
        """Requesting a non-existent product ID returns 404."""
        resp = client.get(f"{BASE_URL}/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_product_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1")
        assert resp.status_code == 401


# =============================================================================
# POST /api/v1/products/ -- Create product
# =============================================================================


class TestCreateProduct:
    """Tests for the create product endpoint."""

    def test_create_product_minimal_fields(self, client):
        """Creating a product with only required fields succeeds."""
        uid = _uid()
        payload = {"sku": f"CRT-{uid}", "name": f"Created {uid}"}
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["sku"] == f"CRT-{uid}"
        assert body["name"] == f"Created {uid}"
        assert "id" in body
        assert "created_at" in body

    def test_create_product_with_optional_fields(self, client):
        """Creating a product with all optional fields succeeds."""
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

    def test_create_product_defaults(self, client):
        """Default values are applied when optional fields are omitted."""
        uid = _uid()
        payload = {"sku": f"DEF-{uid}", "name": f"Default {uid}"}
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["unit"] == "EA"
        assert body["is_raw_material"] is False
        assert body["active"] is True

    def test_create_product_duplicate_sku_returns_400(self, client, make_product):
        """Duplicate SKU is rejected with 400."""
        uid = _uid()
        sku = f"DUP-{uid}"
        make_product(sku=sku, name=f"Original {uid}")
        resp = client.post(BASE_URL, json={"sku": sku, "name": f"Dup {uid}"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_create_product_missing_sku_returns_422(self, client):
        """Missing required field 'sku' returns validation error."""
        resp = client.post(BASE_URL, json={"name": "No SKU"})
        assert resp.status_code == 422

    def test_create_product_missing_name_returns_422(self, client):
        """Missing required field 'name' returns validation error."""
        resp = client.post(BASE_URL, json={"sku": f"NONAME-{_uid()}"})
        assert resp.status_code == 422

    def test_create_product_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE_URL, json={"sku": "X", "name": "X"})
        assert resp.status_code == 401


# =============================================================================
# PUT /api/v1/products/{id} -- Update product
# =============================================================================


class TestUpdateProduct:
    """Tests for the update product endpoint."""

    def test_update_product_name(self, client, make_product):
        """Updating the name field succeeds."""
        product = make_product(name="Before Update")
        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"name": "After Update"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "After Update"

    def test_update_product_not_found(self, client):
        """Updating a non-existent product returns 404."""
        resp = client.put(f"{BASE_URL}/999999", json={"name": "Ghost"})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_update_partial_preserves_other_fields(self, client, make_product):
        """PATCH-style partial update does not reset unset fields."""
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

    def test_update_sku_allowed_without_transactions(self, client, make_product):
        """SKU change succeeds when no transactional history exists."""
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
        """SKU change is blocked when product has purchase order lines."""
        from app.models.purchase_order import PurchaseOrderLine

        uid = _uid()
        product = make_product(sku=f"POBL-{uid}", name=f"PO Block {uid}")
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
            json={"sku": f"FAIL-{uid}"},
        )
        assert resp.status_code == 400
        assert "Cannot change SKU" in resp.json()["detail"]

    def test_update_duplicate_sku_returns_400(self, client, make_product):
        """Changing SKU to an existing one returns 400."""
        uid = _uid()
        existing = make_product(sku=f"EXIST-{uid}", name=f"Existing {uid}")
        target = make_product(sku=f"TARGET-{uid}", name=f"Target {uid}")
        resp = client.put(
            f"{BASE_URL}/{target.id}",
            json={"sku": existing.sku},
        )
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_update_deactivate_product(self, client, make_product):
        """Setting active=False deactivates the product."""
        product = make_product(name="Deactivate Me")
        resp = client.put(
            f"{BASE_URL}/{product.id}",
            json={"active": False},
        )
        assert resp.status_code == 200
        assert resp.json()["active"] is False

    def test_update_product_requires_auth(self, unauthed_client):
        resp = unauthed_client.put(f"{BASE_URL}/1", json={"name": "X"})
        assert resp.status_code == 401
