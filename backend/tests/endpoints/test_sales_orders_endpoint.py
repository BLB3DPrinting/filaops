"""
Endpoint tests for Sales Orders API (/api/v1/sales-orders/).

Tests the main CRUD paths and status transitions through the HTTP layer.
Uses the client fixture (TestClient with auth) and db fixture for setup.
"""
import pytest
from decimal import Decimal


# =============================================================================
# GET /api/v1/sales-orders/ — List
# =============================================================================

class TestListSalesOrders:
    """Tests for listing sales orders."""

    def test_list_returns_200(self, client):
        """GET /sales-orders/ returns 200 with a list."""
        resp = client.get("/api/v1/sales-orders/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_includes_created_order(self, client, db, make_product, make_sales_order):
        """A sales order created via DB appears in the list response."""
        product = make_product(selling_price=Decimal("15.00"))
        so = make_sales_order(product_id=product.id, quantity=3, unit_price=Decimal("15.00"))

        resp = client.get("/api/v1/sales-orders/")
        assert resp.status_code == 200
        data = resp.json()
        order_ids = [o["id"] for o in data]
        assert so.id in order_ids

    def test_list_respects_limit(self, client, db, make_product, make_sales_order):
        """Limit parameter caps the number of returned orders."""
        product = make_product(selling_price=Decimal("10.00"))
        for _ in range(5):
            make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))

        resp = client.get("/api/v1/sales-orders/?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) <= 2

    def test_list_filters_by_status(self, client, db, make_product, make_sales_order):
        """Status query param filters results."""
        product = make_product(selling_price=Decimal("10.00"))
        make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"), status="draft")

        resp = client.get("/api/v1/sales-orders/?status=draft")
        assert resp.status_code == 200
        data = resp.json()
        for order in data:
            assert order["status"] == "draft"


# =============================================================================
# GET /api/v1/sales-orders/{id} — Get Detail
# =============================================================================

class TestGetSalesOrder:
    """Tests for getting a single sales order."""

    def test_get_existing_order(self, client, db, make_product, make_sales_order):
        """GET /sales-orders/{id} returns full order details."""
        product = make_product(selling_price=Decimal("20.00"))
        so = make_sales_order(product_id=product.id, quantity=2, unit_price=Decimal("20.00"))

        resp = client.get(f"/api/v1/sales-orders/{so.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == so.id
        assert data["order_number"] == so.order_number
        assert data["status"] == "draft"
        assert "created_at" in data
        assert "lines" in data

    def test_get_nonexistent_returns_404(self, client):
        """GET with a non-existent ID returns 404."""
        resp = client.get("/api/v1/sales-orders/999999")
        assert resp.status_code == 404


# =============================================================================
# POST /api/v1/sales-orders/ — Create
# =============================================================================

class TestCreateSalesOrder:
    """Tests for creating a sales order via the API."""

    def test_create_with_line_items(self, client, db, make_product):
        """POST creates a line-item sales order and returns 201."""
        product = make_product(selling_price=Decimal("25.00"))

        payload = {
            "lines": [
                {"product_id": product.id, "quantity": 5}
            ],
            "source": "manual",
            "shipping_address_line1": "123 Test St",
            "shipping_city": "Testville",
            "shipping_state": "TX",
            "shipping_zip": "78701",
        }

        resp = client.post("/api/v1/sales-orders/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] is not None
        assert data["order_number"].startswith("SO-")
        assert data["status"] == "pending"
        assert len(data["lines"]) == 1
        assert data["lines"][0]["product_id"] == product.id
        assert float(data["lines"][0]["quantity"]) == 5

    def test_create_multiple_lines(self, client, db, make_product):
        """POST with multiple line items creates a multi-line order."""
        p1 = make_product(selling_price=Decimal("10.00"))
        p2 = make_product(selling_price=Decimal("20.00"))

        payload = {
            "lines": [
                {"product_id": p1.id, "quantity": 2},
                {"product_id": p2.id, "quantity": 3},
            ],
        }

        resp = client.post("/api/v1/sales-orders/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["lines"]) == 2

    def test_create_empty_lines_fails(self, client):
        """POST with no lines returns 422."""
        payload = {"lines": []}
        resp = client.post("/api/v1/sales-orders/", json=payload)
        assert resp.status_code == 422

    def test_create_with_notes(self, client, db, make_product):
        """POST with customer_notes and internal_notes stores them on the order."""
        product = make_product(selling_price=Decimal("15.00"))

        payload = {
            "lines": [{"product_id": product.id, "quantity": 1}],
            "customer_notes": "Please ship fast",
            "internal_notes": "VIP customer",
        }

        resp = client.post("/api/v1/sales-orders/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["customer_notes"] == "Please ship fast"
        assert data["internal_notes"] == "VIP customer"


# =============================================================================
# PATCH /api/v1/sales-orders/{id}/status — Status Update
# =============================================================================

class TestUpdateSalesOrderStatus:
    """Tests for updating sales order status."""

    def test_valid_transition(self, client, db, make_product, make_sales_order):
        """PATCH with valid transition (draft -> pending) succeeds."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"), status="draft")

        resp = client.patch(
            f"/api/v1/sales-orders/{so.id}/status",
            json={"status": "pending"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"

    def test_transition_pending_to_confirmed(self, client, db, make_product, make_sales_order):
        """PATCH with pending -> confirmed transition succeeds and sets confirmed_at."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"), status="pending")

        resp = client.patch(
            f"/api/v1/sales-orders/{so.id}/status",
            json={"status": "confirmed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert data["confirmed_at"] is not None

    def test_status_update_nonexistent_order(self, client):
        """PATCH on non-existent order returns 404."""
        resp = client.patch(
            "/api/v1/sales-orders/999999/status",
            json={"status": "pending"},
        )
        assert resp.status_code == 404


# =============================================================================
# DELETE /api/v1/sales-orders/{id}
# =============================================================================

class TestDeleteSalesOrder:
    """Tests for deleting a sales order."""

    def test_delete_pending_order(self, client, db, make_product, make_sales_order):
        """DELETE removes a pending order and returns 204."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"), status="pending")

        resp = client.delete(f"/api/v1/sales-orders/{so.id}")
        assert resp.status_code == 204

        # Confirm it is gone
        resp2 = client.get(f"/api/v1/sales-orders/{so.id}")
        assert resp2.status_code == 404

    def test_delete_non_deletable_status_returns_400(self, client, db, make_product, make_sales_order):
        """DELETE on an order with non-deletable status (e.g. confirmed) returns 400."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"), status="confirmed")

        resp = client.delete(f"/api/v1/sales-orders/{so.id}")
        assert resp.status_code == 400

    def test_delete_nonexistent_returns_404(self, client):
        """DELETE on a non-existent order returns 404."""
        resp = client.delete("/api/v1/sales-orders/999999")
        assert resp.status_code == 404


# =============================================================================
# POST /api/v1/sales-orders/{id}/cancel — Cancel
# =============================================================================

class TestCancelSalesOrder:
    """Tests for cancelling a sales order."""

    def test_cancel_draft_order(self, client, db, make_product, make_sales_order):
        """POST /cancel on a draft order succeeds."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"), status="draft")

        resp = client.post(
            f"/api/v1/sales-orders/{so.id}/cancel",
            json={"cancellation_reason": "Test cancellation"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["cancellation_reason"] == "Test cancellation"


# =============================================================================
# GET /api/v1/sales-orders/status-transitions — Metadata
# =============================================================================

class TestStatusTransitions:
    """Tests for status transition metadata endpoint."""

    def test_get_all_transitions(self, client):
        """GET /status-transitions returns all statuses and their transitions."""
        resp = client.get("/api/v1/sales-orders/status-transitions")
        assert resp.status_code == 200
        data = resp.json()
        assert "statuses" in data
        assert "transitions" in data
        assert "draft" in data["statuses"]

    def test_get_transitions_for_specific_status(self, client):
        """GET /status-transitions?current_status=draft returns transitions for draft."""
        resp = client.get("/api/v1/sales-orders/status-transitions?current_status=draft")
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_status"] == "draft"
        assert "allowed_transitions" in data
        assert "pending" in data["allowed_transitions"]

    def test_invalid_status_returns_400(self, client):
        """GET /status-transitions with invalid status returns 400."""
        resp = client.get("/api/v1/sales-orders/status-transitions?current_status=bogus")
        assert resp.status_code == 400
