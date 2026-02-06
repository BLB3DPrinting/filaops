"""
Endpoint tests for Purchase Orders API (/api/v1/purchase-orders/).

Tests the main CRUD paths and status transitions through the HTTP layer.
Uses the client fixture (TestClient with auth) and db fixture for setup.
"""
import pytest
from decimal import Decimal


# =============================================================================
# GET /api/v1/purchase-orders/ — List
# =============================================================================

class TestListPurchaseOrders:
    """Tests for listing purchase orders."""

    def test_list_returns_200(self, client):
        """GET /purchase-orders/ returns 200 with paginated response."""
        resp = client.get("/api/v1/purchase-orders/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)

    def test_list_includes_created_po(self, client, db, make_vendor, make_purchase_order):
        """A PO created via DB shows up in the list."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)

        resp = client.get("/api/v1/purchase-orders/")
        assert resp.status_code == 200
        data = resp.json()
        po_ids = [item["id"] for item in data["items"]]
        assert po.id in po_ids

    def test_list_filters_by_status(self, client, db, make_vendor, make_purchase_order):
        """Status query parameter filters the list."""
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id, status="draft")

        resp = client.get("/api/v1/purchase-orders/?status=draft")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["status"] == "draft"

    def test_list_filters_by_vendor(self, client, db, make_vendor, make_purchase_order):
        """vendor_id query parameter filters the list."""
        v1 = make_vendor()
        v2 = make_vendor()
        make_purchase_order(vendor_id=v1.id)
        make_purchase_order(vendor_id=v2.id)

        resp = client.get(f"/api/v1/purchase-orders/?vendor_id={v1.id}")
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["vendor_id"] == v1.id

    def test_list_pagination(self, client, db, make_vendor, make_purchase_order):
        """Pagination params limit and offset work correctly."""
        vendor = make_vendor()
        for _ in range(5):
            make_purchase_order(vendor_id=vendor.id)

        resp = client.get("/api/v1/purchase-orders/?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["pagination"]["limit"] == 2
        assert len(data["items"]) <= 2


# =============================================================================
# GET /api/v1/purchase-orders/{id} — Get Detail
# =============================================================================

class TestGetPurchaseOrder:
    """Tests for getting a single purchase order."""

    def test_get_existing_po(self, client, db, make_vendor, make_purchase_order):
        """GET /purchase-orders/{id} returns full PO details with lines."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)

        resp = client.get(f"/api/v1/purchase-orders/{po.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == po.id
        assert data["po_number"] == po.po_number
        assert data["vendor_id"] == vendor.id
        assert data["status"] == "draft"
        assert "lines" in data
        assert "created_at" in data

    def test_get_nonexistent_returns_404(self, client):
        """GET with a non-existent ID returns 404."""
        resp = client.get("/api/v1/purchase-orders/999999")
        assert resp.status_code == 404


# =============================================================================
# POST /api/v1/purchase-orders/ — Create
# =============================================================================

class TestCreatePurchaseOrder:
    """Tests for creating a purchase order via the API."""

    def test_create_po_with_lines(self, client, db, make_vendor, make_product):
        """POST creates a PO with line items and returns 201."""
        vendor = make_vendor()
        product = make_product(
            item_type="supply",
            unit="G",
            purchase_uom="KG",
            purchase_factor=Decimal("1000"),
        )

        payload = {
            "vendor_id": vendor.id,
            "notes": "Test purchase order",
            "lines": [
                {
                    "product_id": product.id,
                    "quantity_ordered": "1000",
                    "unit_cost": "25.50",
                    "purchase_unit": "KG",
                }
            ],
        }

        resp = client.post("/api/v1/purchase-orders/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] is not None
        assert data["po_number"].startswith("PO-")
        assert data["vendor_id"] == vendor.id
        assert data["status"] == "draft"
        assert len(data["lines"]) == 1
        assert data["lines"][0]["product_id"] == product.id

    def test_create_po_no_lines(self, client, db, make_vendor):
        """POST without lines creates a PO with empty lines array."""
        vendor = make_vendor()

        payload = {
            "vendor_id": vendor.id,
            "notes": "Empty PO for later",
        }

        resp = client.post("/api/v1/purchase-orders/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["vendor_id"] == vendor.id
        assert len(data["lines"]) == 0

    def test_create_po_missing_vendor_fails(self, client):
        """POST without vendor_id returns 422 validation error."""
        payload = {
            "notes": "No vendor",
            "lines": [],
        }
        resp = client.post("/api/v1/purchase-orders/", json=payload)
        assert resp.status_code == 422

    def test_create_po_multiple_lines(self, client, db, make_vendor, make_product):
        """POST with multiple lines creates a multi-line PO."""
        vendor = make_vendor()
        p1 = make_product(item_type="supply", unit="EA")
        p2 = make_product(item_type="supply", unit="EA")

        payload = {
            "vendor_id": vendor.id,
            "lines": [
                {"product_id": p1.id, "quantity_ordered": "10", "unit_cost": "5.00"},
                {"product_id": p2.id, "quantity_ordered": "20", "unit_cost": "3.00"},
            ],
        }

        resp = client.post("/api/v1/purchase-orders/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["lines"]) == 2


# =============================================================================
# POST /api/v1/purchase-orders/{id}/status — Status Update
# =============================================================================

class TestUpdatePOStatus:
    """Tests for updating purchase order status."""

    def test_valid_transition_draft_to_ordered(self, client, db, make_vendor, make_product):
        """POST /status with valid transition (draft -> ordered) succeeds when PO has lines."""
        vendor = make_vendor()
        product = make_product(item_type="supply", unit="EA")

        # Create PO with lines via API so lines are properly attached
        create_resp = client.post("/api/v1/purchase-orders/", json={
            "vendor_id": vendor.id,
            "lines": [
                {"product_id": product.id, "quantity_ordered": "10", "unit_cost": "5.00"},
            ],
        })
        assert create_resp.status_code == 201
        po_id = create_resp.json()["id"]

        resp = client.post(
            f"/api/v1/purchase-orders/{po_id}/status",
            json={"status": "ordered"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ordered"

    def test_status_with_tracking_info(self, client, db, make_vendor, make_purchase_order):
        """POST /status can include tracking number and carrier."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")

        resp = client.post(
            f"/api/v1/purchase-orders/{po.id}/status",
            json={
                "status": "shipped",
                "tracking_number": "1Z999AA10123456784",
                "carrier": "UPS",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "shipped"
        assert data["tracking_number"] == "1Z999AA10123456784"
        assert data["carrier"] == "UPS"

    def test_invalid_transition_fails(self, client, db, make_vendor, make_purchase_order):
        """POST /status with invalid transition returns 400."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")

        # draft -> received is not a valid direct transition
        resp = client.post(
            f"/api/v1/purchase-orders/{po.id}/status",
            json={"status": "received"},
        )
        assert resp.status_code == 400

    def test_status_update_nonexistent_po(self, client):
        """POST /status on non-existent PO returns 404."""
        resp = client.post(
            "/api/v1/purchase-orders/999999/status",
            json={"status": "ordered"},
        )
        assert resp.status_code == 404


# =============================================================================
# DELETE /api/v1/purchase-orders/{id}
# =============================================================================

class TestDeletePurchaseOrder:
    """Tests for deleting a purchase order."""

    def test_delete_draft_po(self, client, db, make_vendor, make_purchase_order):
        """DELETE removes a draft PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")

        resp = client.delete(f"/api/v1/purchase-orders/{po.id}")
        assert resp.status_code == 200  # PO delete returns 200 with message

        # Confirm it is gone
        resp2 = client.get(f"/api/v1/purchase-orders/{po.id}")
        assert resp2.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        """DELETE on a non-existent PO returns 404."""
        resp = client.delete("/api/v1/purchase-orders/999999")
        assert resp.status_code == 404

    def test_delete_non_draft_fails(self, client, db, make_vendor, make_purchase_order):
        """DELETE on a non-draft PO returns 400 (only drafts can be deleted)."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")

        resp = client.delete(f"/api/v1/purchase-orders/{po.id}")
        assert resp.status_code == 400


# =============================================================================
# PUT /api/v1/purchase-orders/{id} — Update
# =============================================================================

class TestUpdatePurchaseOrder:
    """Tests for updating a purchase order."""

    def test_update_notes(self, client, db, make_vendor, make_purchase_order):
        """PUT updates PO fields like notes."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)

        resp = client.put(
            f"/api/v1/purchase-orders/{po.id}",
            json={"notes": "Updated test notes"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["notes"] == "Updated test notes"

    def test_update_nonexistent_returns_404(self, client):
        """PUT on non-existent PO returns 404."""
        resp = client.put(
            "/api/v1/purchase-orders/999999",
            json={"notes": "nope"},
        )
        assert resp.status_code == 404
