"""
Endpoint tests for Production Orders API (/api/v1/production-orders/).

Tests the main CRUD paths through the HTTP layer.
Uses the client fixture (TestClient with auth) and db fixture for setup.
"""
import pytest
from decimal import Decimal


# =============================================================================
# GET /api/v1/production-orders/ — List
# =============================================================================

class TestListProductionOrders:
    """Tests for listing production orders."""

    def test_list_returns_200(self, client):
        """GET /production-orders/ returns 200 with a list."""
        resp = client.get("/api/v1/production-orders/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_includes_created_order(self, client, db, make_product):
        """A production order created via the API appears in the list."""
        product = make_product(
            item_type="finished_good",
            procurement_type="make",
            selling_price=Decimal("15.00"),
        )

        # Create via API
        create_resp = client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "10",
        })
        assert create_resp.status_code == 200
        created_id = create_resp.json()["id"]

        # Verify it appears in the list
        resp = client.get("/api/v1/production-orders/")
        assert resp.status_code == 200
        data = resp.json()
        order_ids = [o["id"] for o in data]
        assert created_id in order_ids

    def test_list_filters_by_status(self, client, db, make_product):
        """Status query parameter filters the list."""
        product = make_product(
            item_type="finished_good",
            procurement_type="make",
        )

        client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "5",
        })

        resp = client.get("/api/v1/production-orders/?status=draft")
        assert resp.status_code == 200
        data = resp.json()
        for order in data:
            assert order["status"] == "draft"

    def test_list_filters_by_product_id(self, client, db, make_product):
        """product_id query parameter filters results."""
        p1 = make_product(item_type="finished_good", procurement_type="make")
        p2 = make_product(item_type="finished_good", procurement_type="make")

        client.post("/api/v1/production-orders/", json={
            "product_id": p1.id, "quantity_ordered": "5",
        })
        client.post("/api/v1/production-orders/", json={
            "product_id": p2.id, "quantity_ordered": "3",
        })

        resp = client.get(f"/api/v1/production-orders/?product_id={p1.id}")
        assert resp.status_code == 200
        data = resp.json()
        for order in data:
            assert order["product_id"] == p1.id

    def test_list_pagination(self, client, db, make_product):
        """Limit and offset pagination parameters work."""
        product = make_product(item_type="finished_good", procurement_type="make")
        for _ in range(5):
            client.post("/api/v1/production-orders/", json={
                "product_id": product.id,
                "quantity_ordered": "1",
            })

        resp = client.get("/api/v1/production-orders/?limit=2&offset=0")
        assert resp.status_code == 200
        assert len(resp.json()) <= 2


# =============================================================================
# GET /api/v1/production-orders/{id} — Get Detail
# =============================================================================

class TestGetProductionOrder:
    """Tests for getting a single production order."""

    def test_get_existing_order(self, client, db, make_product):
        """GET /production-orders/{id} returns full production order details."""
        product = make_product(
            item_type="finished_good",
            procurement_type="make",
            selling_price=Decimal("20.00"),
        )

        create_resp = client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "10",
            "priority": 2,
            "notes": "Test order",
        })
        assert create_resp.status_code == 200
        order_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/production-orders/{order_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == order_id
        assert data["product_id"] == product.id
        assert data["product_sku"] == product.sku
        assert data["status"] == "draft"
        assert data["priority"] == 2
        assert data["notes"] == "Test order"
        assert float(data["quantity_ordered"]) == 10
        assert "operations" in data
        assert "created_at" in data
        assert data["code"].startswith("PO-")

    def test_get_nonexistent_returns_404(self, client):
        """GET with a non-existent ID returns 404."""
        resp = client.get("/api/v1/production-orders/999999")
        assert resp.status_code == 404


# =============================================================================
# POST /api/v1/production-orders/ — Create
# =============================================================================

class TestCreateProductionOrder:
    """Tests for creating a production order via the API."""

    def test_create_basic_order(self, client, db, make_product):
        """POST creates a production order and returns the full response."""
        product = make_product(
            item_type="finished_good",
            procurement_type="make",
        )

        payload = {
            "product_id": product.id,
            "quantity_ordered": "25",
        }

        resp = client.post("/api/v1/production-orders/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] is not None
        assert data["product_id"] == product.id
        assert float(data["quantity_ordered"]) == 25
        assert data["status"] == "draft"
        assert data["source"] == "manual"
        assert data["code"].startswith("PO-")

    def test_create_with_all_optional_fields(self, client, db, make_product):
        """POST with all optional fields set."""
        product = make_product(
            item_type="finished_good",
            procurement_type="make",
        )

        payload = {
            "product_id": product.id,
            "quantity_ordered": "50",
            "priority": 1,
            "due_date": "2026-03-15",
            "assigned_to": "test-operator",
            "notes": "Urgent production order",
            "source": "manual",
        }

        resp = client.post("/api/v1/production-orders/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["priority"] == 1
        assert data["due_date"] == "2026-03-15"
        assert data["assigned_to"] == "test-operator"
        assert data["notes"] == "Urgent production order"

    def test_create_missing_product_id_fails(self, client):
        """POST without product_id returns 422 validation error."""
        payload = {"quantity_ordered": "10"}
        resp = client.post("/api/v1/production-orders/", json=payload)
        assert resp.status_code == 422

    def test_create_missing_quantity_fails(self, client, db, make_product):
        """POST without quantity_ordered returns 422 validation error."""
        product = make_product(item_type="finished_good", procurement_type="make")
        payload = {"product_id": product.id}
        resp = client.post("/api/v1/production-orders/", json=payload)
        assert resp.status_code == 422

    def test_create_zero_quantity_fails(self, client, db, make_product):
        """POST with quantity_ordered=0 returns 422 validation error."""
        product = make_product(item_type="finished_good", procurement_type="make")
        payload = {"product_id": product.id, "quantity_ordered": "0"}
        resp = client.post("/api/v1/production-orders/", json=payload)
        assert resp.status_code == 422

    def test_create_with_bom(self, client, db, make_product, make_bom):
        """POST with bom_id links the production order to a BOM."""
        fg = make_product(item_type="finished_good", procurement_type="make")
        raw = make_product(item_type="supply", unit="G", is_raw_material=True)
        bom = make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        payload = {
            "product_id": fg.id,
            "quantity_ordered": "10",
            "bom_id": bom.id,
        }

        resp = client.post("/api/v1/production-orders/", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["bom_id"] == bom.id


# =============================================================================
# PUT /api/v1/production-orders/{id} — Update
# =============================================================================

class TestUpdateProductionOrder:
    """Tests for updating a production order."""

    def test_update_quantity_and_priority(self, client, db, make_product):
        """PUT updates quantity_ordered and priority."""
        product = make_product(item_type="finished_good", procurement_type="make")

        create_resp = client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "10",
            "priority": 3,
        })
        order_id = create_resp.json()["id"]

        resp = client.put(f"/api/v1/production-orders/{order_id}", json={
            "quantity_ordered": "20",
            "priority": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert float(data["quantity_ordered"]) == 20
        assert data["priority"] == 1

    def test_update_notes(self, client, db, make_product):
        """PUT updates the notes field."""
        product = make_product(item_type="finished_good", procurement_type="make")

        create_resp = client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "5",
        })
        order_id = create_resp.json()["id"]

        resp = client.put(f"/api/v1/production-orders/{order_id}", json={
            "notes": "Updated notes for testing",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["notes"] == "Updated notes for testing"

    def test_update_due_date(self, client, db, make_product):
        """PUT updates the due_date field."""
        product = make_product(item_type="finished_good", procurement_type="make")

        create_resp = client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "5",
        })
        order_id = create_resp.json()["id"]

        resp = client.put(f"/api/v1/production-orders/{order_id}", json={
            "due_date": "2026-06-01",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["due_date"] == "2026-06-01"

    def test_update_nonexistent_returns_404(self, client):
        """PUT on non-existent order returns 404."""
        resp = client.put(
            "/api/v1/production-orders/999999",
            json={"notes": "nope"},
        )
        assert resp.status_code == 404


# =============================================================================
# DELETE /api/v1/production-orders/{id}
# =============================================================================

class TestDeleteProductionOrder:
    """Tests for deleting a production order."""

    def test_delete_draft_order(self, client, db, make_product):
        """DELETE removes a draft production order."""
        product = make_product(item_type="finished_good", procurement_type="make")

        create_resp = client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "5",
        })
        order_id = create_resp.json()["id"]

        resp = client.delete(f"/api/v1/production-orders/{order_id}")
        assert resp.status_code == 200

        # Confirm it is gone
        resp2 = client.get(f"/api/v1/production-orders/{order_id}")
        assert resp2.status_code == 404

    def test_delete_nonexistent_returns_404(self, client):
        """DELETE on a non-existent order returns 404."""
        resp = client.delete("/api/v1/production-orders/999999")
        assert resp.status_code == 404


# =============================================================================
# GET /api/v1/production-orders/status-transitions — Metadata
# =============================================================================

class TestProductionOrderStatusTransitions:
    """Tests for status transition metadata endpoint."""

    def test_get_all_transitions(self, client):
        """GET /status-transitions returns all statuses and their transitions."""
        resp = client.get("/api/v1/production-orders/status-transitions")
        assert resp.status_code == 200
        data = resp.json()
        assert "statuses" in data
        assert "transitions" in data
        assert "draft" in data["statuses"]

    def test_get_transitions_for_specific_status(self, client):
        """GET /status-transitions?current_status=draft returns transitions for draft."""
        resp = client.get("/api/v1/production-orders/status-transitions?current_status=draft")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_status"] == "draft"
        assert "allowed_transitions" in data

    def test_invalid_status_returns_400(self, client):
        """GET /status-transitions with invalid status returns 400."""
        resp = client.get("/api/v1/production-orders/status-transitions?current_status=bogus")
        assert resp.status_code == 400


# =============================================================================
# POST /api/v1/production-orders/{id}/release — Release
# =============================================================================

class TestReleaseProductionOrder:
    """Tests for releasing a production order."""

    def test_release_draft_order(self, client, db, make_product):
        """POST /release transitions a draft order to released."""
        product = make_product(item_type="finished_good", procurement_type="make")

        create_resp = client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "5",
        })
        order_id = create_resp.json()["id"]

        resp = client.post(f"/api/v1/production-orders/{order_id}/release?force=true")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "released"


# =============================================================================
# POST /api/v1/production-orders/{id}/cancel — Cancel
# =============================================================================

class TestCancelProductionOrder:
    """Tests for cancelling a production order."""

    def test_cancel_draft_order(self, client, db, make_product):
        """POST /cancel cancels a draft production order."""
        product = make_product(item_type="finished_good", procurement_type="make")

        create_resp = client.post("/api/v1/production-orders/", json={
            "product_id": product.id,
            "quantity_ordered": "5",
        })
        order_id = create_resp.json()["id"]

        resp = client.post(f"/api/v1/production-orders/{order_id}/cancel?notes=Test+cancel")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
