"""
Tests for Quotes API endpoints (/api/v1/quotes).

Covers the main CRUD paths:
- GET    /api/v1/quotes/        (list with filtering)
- GET    /api/v1/quotes/{id}    (get single quote)
- POST   /api/v1/quotes/        (create manual quote)
- PATCH  /api/v1/quotes/{id}    (update quote)
- DELETE /api/v1/quotes/{id}    (delete quote)
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


BASE_URL = "/api/v1/quotes"


def _create_quote(client, **overrides):
    """Helper to create a quote and return the JSON response."""
    payload = {
        "product_name": "Test Widget",
        "quantity": 2,
        "unit_price": "25.00",
        "customer_name": "Jane Doe",
        "customer_email": "jane@example.com",
        "material_type": "PLA",
        "valid_days": 30,
    }
    payload.update(overrides)
    response = client.post(BASE_URL, json=payload)
    assert response.status_code == 201, f"Create failed: {response.text}"
    return response.json()


# =============================================================================
# GET /api/v1/quotes/ -- List quotes
# =============================================================================


class TestListQuotes:
    """Tests for the list quotes endpoint."""

    def test_list_returns_200(self, client):
        resp = client.get(BASE_URL)
        assert resp.status_code == 200

    def test_list_returns_array(self, client):
        data = client.get(BASE_URL).json()
        assert isinstance(data, list)

    def test_list_contains_created_quote(self, client):
        quote = _create_quote(client)
        data = client.get(BASE_URL).json()
        ids = [q["id"] for q in data]
        assert quote["id"] in ids

    def test_list_filter_by_status(self, client):
        _create_quote(client)  # Creates a pending quote
        resp = client.get(f"{BASE_URL}?status=pending")
        assert resp.status_code == 200
        data = resp.json()
        assert all(q["status"] == "pending" for q in data)

    def test_list_search_by_product_name(self, client):
        _create_quote(client, product_name="SearchableWidget99")
        resp = client.get(f"{BASE_URL}?search=SearchableWidget99")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any("SearchableWidget99" in q["product_name"] for q in data)

    def test_list_search_by_customer_name(self, client):
        _create_quote(client, customer_name="Archibald Testsworth")
        resp = client.get(f"{BASE_URL}?search=Archibald")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_list_pagination_limit(self, client):
        resp = client.get(f"{BASE_URL}?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) <= 2

    def test_list_ordered_by_newest_first(self, client):
        """Quotes should be listed newest first."""
        q1 = _create_quote(client, product_name="First")
        q2 = _create_quote(client, product_name="Second")
        data = client.get(BASE_URL).json()
        ids = [q["id"] for q in data]
        if q1["id"] in ids and q2["id"] in ids:
            assert ids.index(q2["id"]) < ids.index(q1["id"])

    def test_list_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(BASE_URL)
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/quotes/{id} -- Get quote detail
# =============================================================================


class TestGetQuote:
    """Tests for the get quote detail endpoint."""

    def test_get_existing_quote(self, client):
        quote = _create_quote(client)
        resp = client.get(f"{BASE_URL}/{quote['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == quote["id"]
        assert data["quote_number"] == quote["quote_number"]

    def test_get_quote_detail_fields(self, client):
        """QuoteDetail response includes all detail fields."""
        quote = _create_quote(
            client,
            customer_notes="Rush please",
            admin_notes="VIP customer",
        )
        resp = client.get(f"{BASE_URL}/{quote['id']}")
        data = resp.json()
        assert "customer_notes" in data
        assert "admin_notes" in data
        assert "rejection_reason" in data
        assert "updated_at" in data
        assert "approved_at" in data
        assert "converted_at" in data
        assert "shipping_name" in data
        assert "shipping_address_line1" in data

    def test_get_quote_has_correct_values(self, client):
        quote = _create_quote(
            client,
            product_name="Precision Part",
            quantity=5,
            unit_price="12.50",
            customer_name="Bob Builder",
            customer_email="bob@build.com",
            material_type="PLA",
        )
        data = client.get(f"{BASE_URL}/{quote['id']}").json()
        assert data["product_name"] == "Precision Part"
        assert data["quantity"] == 5
        assert Decimal(str(data["unit_price"])) == Decimal("12.50")
        assert data["customer_name"] == "Bob Builder"
        assert data["customer_email"] == "bob@build.com"
        assert data["material_type"] == "PLA"

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get(f"{BASE_URL}/999999")
        assert resp.status_code == 404

    def test_get_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1")
        assert resp.status_code == 401


# =============================================================================
# POST /api/v1/quotes/ -- Create quote
# =============================================================================


class TestCreateQuote:
    """Tests for the create quote endpoint."""

    def test_create_basic_quote(self, client):
        resp = client.post(BASE_URL, json={
            "product_name": "Basic Widget",
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["quote_number"].startswith("Q-")
        assert data["status"] == "pending"
        assert data["product_name"] == "Basic Widget"

    def test_create_generates_unique_numbers(self, client):
        q1 = _create_quote(client)
        q2 = _create_quote(client)
        assert q1["quote_number"] != q2["quote_number"]

    def test_create_calculates_subtotal(self, client):
        data = _create_quote(client, quantity=3, unit_price="20.00")
        assert Decimal(str(data["subtotal"])) == Decimal("60.00")

    def test_create_total_equals_subtotal_without_tax(self, client):
        data = _create_quote(client, quantity=2, unit_price="15.00", apply_tax=False)
        expected = Decimal("30.00")
        assert Decimal(str(data["subtotal"])) == expected
        assert Decimal(str(data["total_price"])) == expected

    def test_create_with_shipping_cost(self, client):
        data = _create_quote(
            client, quantity=1, unit_price="50.00",
            apply_tax=False, shipping_cost="9.99",
        )
        assert Decimal(str(data["total_price"])) == Decimal("59.99")
        assert Decimal(str(data["shipping_cost"])) == Decimal("9.99")

    def test_create_with_customer_info(self, client):
        data = _create_quote(
            client,
            customer_name="Alice Wonderland",
            customer_email="alice@wonder.land",
        )
        assert data["customer_name"] == "Alice Wonderland"
        assert data["customer_email"] == "alice@wonder.land"

    def test_create_with_notes(self, client):
        data = _create_quote(
            client,
            customer_notes="Ship carefully",
            admin_notes="Priority",
        )
        assert data["customer_notes"] == "Ship carefully"
        assert data["admin_notes"] == "Priority"

    def test_create_defaults_material_to_pla(self, client):
        resp = client.post(BASE_URL, json={
            "product_name": "No Material",
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert resp.status_code == 201
        assert resp.json()["material_type"] == "PLA"

    def test_create_sets_expiration(self, client):
        data = _create_quote(client, valid_days=60)
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        delta = expires_at - created_at
        assert 59 <= delta.days <= 61

    def test_create_missing_product_name_returns_400(self, client):
        """product_name is optional in schema but service validates it when no lines provided."""
        resp = client.post(BASE_URL, json={
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert resp.status_code == 400

    def test_create_missing_unit_price_returns_400(self, client):
        """unit_price is optional in schema but service validates it when no lines provided."""
        resp = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
        })
        assert resp.status_code == 400

    def test_create_negative_unit_price_returns_422(self, client):
        resp = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
            "unit_price": "-5.00",
        })
        assert resp.status_code == 422

    def test_create_zero_quantity_returns_422(self, client):
        resp = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 0,
            "unit_price": "10.00",
        })
        assert resp.status_code == 422

    def test_create_invalid_customer_id_returns_400(self, client):
        resp = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
            "unit_price": "10.00",
            "customer_id": 999999,
        })
        assert resp.status_code == 400
        assert "customer" in resp.json()["detail"].lower()

    def test_create_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert resp.status_code == 401


# =============================================================================
# PATCH /api/v1/quotes/{id} -- Update quote
# =============================================================================


class TestUpdateQuote:
    """Tests for the update quote endpoint."""

    def test_update_product_name(self, client):
        quote = _create_quote(client)
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "Updated Widget",
        })
        assert resp.status_code == 200
        assert resp.json()["product_name"] == "Updated Widget"

    def test_update_quantity_recalculates_totals(self, client):
        quote = _create_quote(client, quantity=1, unit_price="20.00", apply_tax=False)
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "quantity": 5,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["quantity"] == 5
        assert Decimal(str(data["subtotal"])) == Decimal("100.00")
        assert Decimal(str(data["total_price"])) == Decimal("100.00")

    def test_update_unit_price_recalculates_totals(self, client):
        quote = _create_quote(client, quantity=2, unit_price="10.00", apply_tax=False)
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "unit_price": "30.00",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert Decimal(str(data["unit_price"])) == Decimal("30.00")
        assert Decimal(str(data["subtotal"])) == Decimal("60.00")

    def test_update_customer_info(self, client):
        quote = _create_quote(client)
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "customer_name": "New Customer",
            "customer_email": "new@customer.com",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer_name"] == "New Customer"
        assert data["customer_email"] == "new@customer.com"

    def test_update_notes(self, client):
        quote = _create_quote(client)
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "customer_notes": "Updated notes",
            "admin_notes": "Admin updated",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["customer_notes"] == "Updated notes"
        assert data["admin_notes"] == "Admin updated"

    def test_update_shipping_address(self, client):
        quote = _create_quote(client)
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "shipping_name": "John Doe",
            "shipping_address_line1": "123 Main St",
            "shipping_city": "Springfield",
            "shipping_state": "IL",
            "shipping_zip": "62701",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["shipping_name"] == "John Doe"
        assert data["shipping_address_line1"] == "123 Main St"
        assert data["shipping_city"] == "Springfield"

    def test_update_remove_tax(self, client):
        quote = _create_quote(client, quantity=1, unit_price="100.00")
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "apply_tax": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_rate"] is None
        assert data["tax_amount"] is None
        assert Decimal(str(data["total_price"])) == Decimal(str(data["subtotal"]))

    def test_update_nonexistent_returns_404(self, client):
        resp = client.patch(f"{BASE_URL}/999999", json={
            "product_name": "Ghost",
        })
        assert resp.status_code == 404

    def test_update_converted_quote_fails(self, client, db):
        """Cannot edit a converted quote."""
        from app.models.quote import Quote

        quote = _create_quote(client)
        db_quote = db.query(Quote).filter(Quote.id == quote["id"]).first()
        db_quote.status = "converted"
        db.flush()

        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "Should Fail",
        })
        assert resp.status_code == 400
        assert "converted" in resp.json()["detail"].lower()

    def test_update_only_specified_fields(self, client):
        """PATCH should only update provided fields, not reset others."""
        quote = _create_quote(
            client,
            product_name="Original Name",
            customer_name="Original Customer",
            customer_email="original@test.com",
        )
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "New Name",
        })
        data = resp.json()
        assert data["product_name"] == "New Name"
        assert data["customer_name"] == "Original Customer"
        assert data["customer_email"] == "original@test.com"

    def test_update_sets_updated_at(self, client):
        quote = _create_quote(client)
        original_updated = quote["updated_at"]
        resp = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "Trigger Timestamp",
        })
        data = resp.json()
        assert data["updated_at"] != original_updated

    def test_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(f"{BASE_URL}/1", json={
            "product_name": "Unauthed",
        })
        assert resp.status_code == 401


# =============================================================================
# DELETE /api/v1/quotes/{id} -- Delete quote
# =============================================================================


class TestDeleteQuote:
    """Tests for the delete quote endpoint."""

    def test_delete_pending_quote(self, client):
        quote = _create_quote(client)
        resp = client.delete(f"{BASE_URL}/{quote['id']}")
        assert resp.status_code == 204

    def test_deleted_quote_no_longer_found(self, client):
        quote = _create_quote(client)
        client.delete(f"{BASE_URL}/{quote['id']}")
        resp = client.get(f"{BASE_URL}/{quote['id']}")
        assert resp.status_code == 404

    def test_delete_rejected_quote(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "rejected",
        })
        resp = client.delete(f"{BASE_URL}/{quote['id']}")
        assert resp.status_code == 204

    def test_delete_cancelled_quote(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "cancelled",
        })
        resp = client.delete(f"{BASE_URL}/{quote['id']}")
        assert resp.status_code == 204

    def test_delete_converted_quote_fails(self, client, db):
        from app.models.quote import Quote

        quote = _create_quote(client)
        db_quote = db.query(Quote).filter(Quote.id == quote["id"]).first()
        db_quote.status = "converted"
        db.flush()

        resp = client.delete(f"{BASE_URL}/{quote['id']}")
        assert resp.status_code == 400
        assert "converted" in resp.json()["detail"].lower()

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete(f"{BASE_URL}/999999")
        assert resp.status_code == 404

    def test_delete_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE_URL}/1")
        assert resp.status_code == 401
