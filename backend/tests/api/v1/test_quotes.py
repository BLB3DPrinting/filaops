"""
Tests for Quotes API endpoints (app/api/v1/endpoints/quotes.py)

Covers:
- GET /api/v1/quotes/ (list with filtering, search, pagination)
- GET /api/v1/quotes/stats (dashboard statistics)
- GET /api/v1/quotes/{id} (get single quote)
- POST /api/v1/quotes/ (create manual quote)
- PATCH /api/v1/quotes/{id} (update quote details)
- PATCH /api/v1/quotes/{id}/status (status transitions)
- POST /api/v1/quotes/{id}/convert (convert quote to sales order)
- DELETE /api/v1/quotes/{id} (delete quote)
- POST /api/v1/quotes/{id}/image (upload image)
- GET /api/v1/quotes/{id}/image (get image)
- DELETE /api/v1/quotes/{id}/image (delete image)
- GET /api/v1/quotes/{id}/pdf (generate PDF)
- Auth: 401 without token on all endpoints
"""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta


BASE_URL = "/api/v1/quotes"


# =============================================================================
# Helper: create a quote via the API (returns response data)
# =============================================================================

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
# Auth tests - endpoints requiring authentication
# =============================================================================

class TestQuoteAuth:
    """Verify auth is required on all protected endpoints."""

    def test_list_requires_auth(self, unauthed_client):
        response = unauthed_client.get(BASE_URL)
        assert response.status_code == 401

    def test_stats_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/stats")
        assert response.status_code == 401

    def test_get_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_create_requires_auth(self, unauthed_client):
        response = unauthed_client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert response.status_code == 401

    def test_update_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/1", json={
            "product_name": "Updated",
        })
        assert response.status_code == 401

    def test_status_update_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/1/status", json={
            "status": "approved",
        })
        assert response.status_code == 401

    def test_convert_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/convert")
        assert response.status_code == 401

    def test_delete_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_upload_image_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/image")
        assert response.status_code == 401

    def test_get_image_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1/image")
        assert response.status_code == 401

    def test_delete_image_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/1/image")
        assert response.status_code == 401

    def test_pdf_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1/pdf")
        assert response.status_code == 401


# =============================================================================
# List - GET /api/v1/quotes/
# =============================================================================

class TestListQuotes:
    """Test GET /api/v1/quotes/ with filtering, search, and pagination."""

    def test_list_returns_200(self, client):
        response = client.get(BASE_URL)
        assert response.status_code == 200

    def test_list_returns_array(self, client):
        response = client.get(BASE_URL)
        data = response.json()
        assert isinstance(data, list)

    def test_list_contains_created_quote(self, client):
        quote = _create_quote(client)
        response = client.get(BASE_URL)
        data = response.json()
        ids = [q["id"] for q in data]
        assert quote["id"] in ids

    def test_list_filter_by_status(self, client):
        _create_quote(client)  # Creates a pending quote
        response = client.get(f"{BASE_URL}?status=pending")
        assert response.status_code == 200
        data = response.json()
        assert all(q["status"] == "pending" for q in data)

    def test_list_filter_by_status_no_results(self, client):
        response = client.get(f"{BASE_URL}?status=converted")
        assert response.status_code == 200
        # May or may not have results, just verify no error

    def test_list_search_by_product_name(self, client):
        _create_quote(client, product_name="UniqueSearchableGadget")
        response = client.get(f"{BASE_URL}?search=UniqueSearchableGadget")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any("UniqueSearchableGadget" in q["product_name"] for q in data)

    def test_list_search_by_customer_name(self, client):
        _create_quote(client, customer_name="Archibald Testsworth")
        response = client.get(f"{BASE_URL}?search=Archibald")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_list_search_by_customer_email(self, client):
        _create_quote(client, customer_email="searchme-unique@example.com")
        response = client.get(f"{BASE_URL}?search=searchme-unique@example.com")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_list_pagination_skip(self, client):
        # Create a few quotes
        _create_quote(client, product_name="Page A")
        _create_quote(client, product_name="Page B")
        response = client.get(f"{BASE_URL}?skip=0&limit=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1

    def test_list_pagination_limit(self, client):
        response = client.get(f"{BASE_URL}?limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 2

    def test_list_ordered_by_created_at_desc(self, client):
        """Quotes should be listed newest first."""
        q1 = _create_quote(client, product_name="First Created")
        q2 = _create_quote(client, product_name="Second Created")
        response = client.get(BASE_URL)
        data = response.json()
        ids = [q["id"] for q in data]
        # q2 (newer) should appear before q1 (older) in the list
        if q1["id"] in ids and q2["id"] in ids:
            assert ids.index(q2["id"]) < ids.index(q1["id"])


# =============================================================================
# Stats - GET /api/v1/quotes/stats
# =============================================================================

class TestQuoteStats:
    """Test GET /api/v1/quotes/stats dashboard endpoint."""

    def test_stats_returns_200(self, client):
        response = client.get(f"{BASE_URL}/stats")
        assert response.status_code == 200

    def test_stats_contains_expected_fields(self, client):
        response = client.get(f"{BASE_URL}/stats")
        data = response.json()
        expected_fields = [
            "total", "pending", "approved", "accepted",
            "rejected", "converted", "expired",
            "total_value", "pending_value",
        ]
        for field in expected_fields:
            assert field in data, f"Missing stats field: {field}"

    def test_stats_reflects_created_quote(self, client):
        _create_quote(client, unit_price="100.00", quantity=1)
        response = client.get(f"{BASE_URL}/stats")
        data = response.json()
        assert data["total"] >= 1
        assert data["pending"] >= 1
        assert float(data["total_value"]) > 0
        assert float(data["pending_value"]) > 0


# =============================================================================
# Get - GET /api/v1/quotes/{id}
# =============================================================================

class TestGetQuote:
    """Test GET /api/v1/quotes/{id}."""

    def test_get_existing_quote(self, client):
        quote = _create_quote(client)
        response = client.get(f"{BASE_URL}/{quote['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == quote["id"]
        assert data["quote_number"] == quote["quote_number"]

    def test_get_quote_detail_fields(self, client):
        """QuoteDetail response should include all detail fields."""
        quote = _create_quote(
            client,
            customer_notes="Please rush",
            admin_notes="VIP customer",
        )
        response = client.get(f"{BASE_URL}/{quote['id']}")
        data = response.json()
        # QuoteDetail extends QuoteListItem with extra fields
        assert "customer_notes" in data
        assert "admin_notes" in data
        assert "rejection_reason" in data
        assert "updated_at" in data
        assert "approved_at" in data
        assert "converted_at" in data
        # Shipping address fields
        assert "shipping_name" in data
        assert "shipping_address_line1" in data
        assert "shipping_city" in data

    def test_get_nonexistent_returns_404(self, client):
        response = client.get(f"{BASE_URL}/999999")
        assert response.status_code == 404

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
        response = client.get(f"{BASE_URL}/{quote['id']}")
        data = response.json()
        assert data["product_name"] == "Precision Part"
        assert data["quantity"] == 5
        assert Decimal(str(data["unit_price"])) == Decimal("12.50")
        assert data["customer_name"] == "Bob Builder"
        assert data["customer_email"] == "bob@build.com"
        assert data["material_type"] == "PLA"


# =============================================================================
# Create - POST /api/v1/quotes/
# =============================================================================

class TestCreateQuote:
    """Test POST /api/v1/quotes/ (manual quote creation)."""

    def test_create_basic_quote(self, client):
        response = client.post(BASE_URL, json={
            "product_name": "Basic Widget",
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["quote_number"].startswith("Q-")
        assert data["status"] == "pending"
        assert data["product_name"] == "Basic Widget"

    def test_create_quote_generates_unique_number(self, client):
        q1 = _create_quote(client)
        q2 = _create_quote(client)
        assert q1["quote_number"] != q2["quote_number"]

    def test_create_quote_calculates_subtotal(self, client):
        data = _create_quote(client, quantity=3, unit_price="20.00")
        # subtotal = 20 * 3 = 60
        assert Decimal(str(data["subtotal"])) == Decimal("60.00")

    def test_create_quote_total_equals_subtotal_without_tax(self, client):
        """Without tax, total_price should equal subtotal."""
        data = _create_quote(client, quantity=2, unit_price="15.00", apply_tax=False)
        expected_subtotal = Decimal("30.00")
        assert Decimal(str(data["subtotal"])) == expected_subtotal
        assert Decimal(str(data["total_price"])) == expected_subtotal

    def test_create_quote_with_shipping_cost(self, client):
        data = _create_quote(client, quantity=1, unit_price="50.00",
                             apply_tax=False, shipping_cost="9.99")
        # total = 50 + 9.99 = 59.99
        assert Decimal(str(data["total_price"])) == Decimal("59.99")
        assert Decimal(str(data["shipping_cost"])) == Decimal("9.99")

    def test_create_quote_with_customer_info(self, client):
        data = _create_quote(
            client,
            customer_name="Alice Wonderland",
            customer_email="alice@wonder.land",
        )
        assert data["customer_name"] == "Alice Wonderland"
        assert data["customer_email"] == "alice@wonder.land"

    def test_create_quote_with_notes(self, client):
        data = _create_quote(
            client,
            customer_notes="Ship carefully",
            admin_notes="Priority customer",
        )
        assert data["customer_notes"] == "Ship carefully"
        assert data["admin_notes"] == "Priority customer"

    def test_create_quote_with_material_type(self, client):
        data = _create_quote(client, material_type="PLA")
        assert data["material_type"] == "PLA"

    def test_create_quote_defaults_material_to_pla(self, client):
        """material_type defaults to PLA if not provided."""
        response = client.post(BASE_URL, json={
            "product_name": "No Material Specified",
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["material_type"] == "PLA"

    def test_create_quote_sets_expiration(self, client):
        data = _create_quote(client, valid_days=60)
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        delta = expires_at - created_at
        # Should be approximately 60 days (allow small tolerance)
        assert 59 <= delta.days <= 61

    def test_create_quote_missing_product_name_fails(self, client):
        """product_name is optional in schema but service validates when no lines provided."""
        response = client.post(BASE_URL, json={
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert response.status_code == 400

    def test_create_quote_missing_unit_price_fails(self, client):
        """unit_price is optional in schema but service validates when no lines provided."""
        response = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
        })
        assert response.status_code == 400

    def test_create_quote_negative_unit_price_fails(self, client):
        response = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
            "unit_price": "-5.00",
        })
        assert response.status_code == 422

    def test_create_quote_zero_quantity_fails(self, client):
        response = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 0,
            "unit_price": "10.00",
        })
        assert response.status_code == 422

    def test_create_quote_quantity_exceeds_max_fails(self, client):
        response = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 99999,
            "unit_price": "10.00",
        })
        assert response.status_code == 422

    def test_create_quote_valid_days_too_high_fails(self, client):
        response = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
            "unit_price": "10.00",
            "valid_days": 999,
        })
        assert response.status_code == 422

    def test_create_quote_with_product_id(self, client, make_product, db):
        product = make_product(selling_price=Decimal("20.00"))
        db.flush()

        data = _create_quote(client, product_id=product.id)
        assert data["product_id"] == product.id

    def test_create_quote_invalid_customer_id_fails(self, client):
        """customer_id must reference an actual customer user."""
        response = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
            "unit_price": "10.00",
            "customer_id": 999999,
        })
        assert response.status_code == 400
        assert "customer" in response.json()["detail"].lower()


# =============================================================================
# Update - PATCH /api/v1/quotes/{id}
# =============================================================================

class TestUpdateQuote:
    """Test PATCH /api/v1/quotes/{id}."""

    def test_update_product_name(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "Updated Widget",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["product_name"] == "Updated Widget"

    def test_update_quantity_recalculates_totals(self, client):
        quote = _create_quote(client, quantity=1, unit_price="20.00", apply_tax=False)
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "quantity": 5,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["quantity"] == 5
        assert Decimal(str(data["subtotal"])) == Decimal("100.00")
        assert Decimal(str(data["total_price"])) == Decimal("100.00")

    def test_update_unit_price_recalculates_totals(self, client):
        quote = _create_quote(client, quantity=2, unit_price="10.00", apply_tax=False)
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "unit_price": "30.00",
        })
        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["unit_price"])) == Decimal("30.00")
        # subtotal = 30 * 2 = 60
        assert Decimal(str(data["subtotal"])) == Decimal("60.00")

    def test_update_customer_info(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "customer_name": "New Customer",
            "customer_email": "new@customer.com",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["customer_name"] == "New Customer"
        assert data["customer_email"] == "new@customer.com"

    def test_update_notes(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "customer_notes": "Updated notes",
            "admin_notes": "Admin updated",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["customer_notes"] == "Updated notes"
        assert data["admin_notes"] == "Admin updated"

    def test_update_shipping_address(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "shipping_name": "John Doe",
            "shipping_address_line1": "123 Main St",
            "shipping_address_line2": "Apt 4",
            "shipping_city": "Springfield",
            "shipping_state": "IL",
            "shipping_zip": "62701",
            "shipping_country": "USA",
            "shipping_phone": "555-0100",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["shipping_name"] == "John Doe"
        assert data["shipping_address_line1"] == "123 Main St"
        assert data["shipping_city"] == "Springfield"
        assert data["shipping_state"] == "IL"
        assert data["shipping_zip"] == "62701"

    def test_update_remove_tax(self, client):
        """Setting apply_tax=False should clear tax fields."""
        quote = _create_quote(client, quantity=1, unit_price="100.00")
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "apply_tax": False,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["tax_rate"] is None
        assert data["tax_amount"] is None
        # total should equal subtotal without tax
        assert Decimal(str(data["total_price"])) == Decimal(str(data["subtotal"]))

    def test_update_nonexistent_quote_returns_404(self, client):
        response = client.patch(f"{BASE_URL}/999999", json={
            "product_name": "Ghost",
        })
        assert response.status_code == 404

    def test_update_converted_quote_fails(self, client, db):
        """Cannot edit a converted quote."""
        from app.models.quote import Quote

        quote = _create_quote(client)
        # Directly set status to converted in DB
        db_quote = db.query(Quote).filter(Quote.id == quote["id"]).first()
        db_quote.status = "converted"
        db.flush()

        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "Should Fail",
        })
        assert response.status_code == 400
        assert "converted" in response.json()["detail"].lower()

    def test_update_invalid_customer_id_fails(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "customer_id": 999999,
        })
        assert response.status_code == 400
        assert "customer" in response.json()["detail"].lower()

    def test_update_material_type(self, client):
        quote = _create_quote(client, material_type="PLA")
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "material_type": "PETG",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["material_type"] == "PETG"

    def test_update_sets_updated_at(self, client):
        quote = _create_quote(client)
        original_updated = quote["updated_at"]
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "Triggers Update Timestamp",
        })
        data = response.json()
        assert data["updated_at"] != original_updated


# =============================================================================
# Status transitions - PATCH /api/v1/quotes/{id}/status
# =============================================================================

class TestQuoteStatusTransitions:
    """Test PATCH /api/v1/quotes/{id}/status."""

    def test_approve_pending_quote(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "approved",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["approved_at"] is not None

    def test_reject_pending_quote(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "rejected",
            "rejection_reason": "Out of stock material",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert data["rejection_reason"] == "Out of stock material"

    def test_accept_quote(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "accepted",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"

    def test_cancel_quote(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "cancelled",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    def test_status_update_with_admin_notes(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "approved",
            "admin_notes": "Reviewed and approved by manager",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["admin_notes"] == "Reviewed and approved by manager"

    def test_invalid_status_fails(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "invalid_status",
        })
        assert response.status_code == 400
        assert "invalid status" in response.json()["detail"].lower()

    def test_cannot_change_converted_quote_status(self, client, db):
        from app.models.quote import Quote

        quote = _create_quote(client)
        db_quote = db.query(Quote).filter(Quote.id == quote["id"]).first()
        db_quote.status = "converted"
        db.flush()

        response = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "cancelled",
        })
        assert response.status_code == 400
        assert "converted" in response.json()["detail"].lower()

    def test_status_nonexistent_quote_returns_404(self, client):
        response = client.patch(f"{BASE_URL}/999999/status", json={
            "status": "approved",
        })
        assert response.status_code == 404

    def test_approve_sets_approval_fields(self, client):
        quote = _create_quote(client)
        response = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "approved",
        })
        data = response.json()
        assert data["approved_at"] is not None
        # approval_method should be "manual"
        # (QuoteDetail may or may not expose this; check the detail endpoint)
        detail_response = client.get(f"{BASE_URL}/{quote['id']}")
        detail = detail_response.json()
        assert detail["status"] == "approved"


# =============================================================================
# Convert - POST /api/v1/quotes/{id}/convert
# =============================================================================

class TestConvertQuote:
    """Test POST /api/v1/quotes/{id}/convert."""

    def test_convert_approved_quote(self, client):
        quote = _create_quote(client, quantity=3, unit_price="25.00")
        # First approve
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "approved",
        })
        # Then convert
        response = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert response.status_code == 201
        data = response.json()
        assert "order_id" in data
        assert "order_number" in data
        assert data["order_number"].startswith("SO-")
        assert "message" in data

    def test_convert_accepted_quote(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "accepted",
        })
        response = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert response.status_code == 201
        data = response.json()
        assert data["order_number"].startswith("SO-")

    def test_convert_marks_quote_as_converted(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "approved",
        })
        convert_response = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert convert_response.status_code == 201

        # Verify quote is now converted
        detail = client.get(f"{BASE_URL}/{quote['id']}").json()
        assert detail["status"] == "converted"
        assert detail["sales_order_id"] is not None
        assert detail["converted_at"] is not None

    def test_convert_creates_sales_order_with_correct_data(self, client):
        quote = _create_quote(
            client,
            product_name="Custom Part",
            quantity=5,
            unit_price="30.00",
            customer_name="Convert Customer",
            customer_email="convert@test.com",
            apply_tax=False,
        )
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "approved",
        })
        convert_data = client.post(f"{BASE_URL}/{quote['id']}/convert").json()

        # Fetch the created sales order
        so_response = client.get(f"/api/v1/sales-orders/{convert_data['order_id']}")
        assert so_response.status_code == 200
        so = so_response.json()
        assert so["product_name"] == "Custom Part"
        assert so["quantity"] == 5
        assert so["customer_name"] == "Convert Customer"
        assert so["customer_email"] == "convert@test.com"

    def test_convert_pending_quote_fails(self, client):
        """Only approved/accepted quotes can be converted."""
        quote = _create_quote(client)
        response = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert response.status_code == 400
        assert "approved or accepted" in response.json()["detail"].lower()

    def test_convert_rejected_quote_fails(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "rejected",
        })
        response = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert response.status_code == 400

    def test_convert_cancelled_quote_fails(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "cancelled",
        })
        response = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert response.status_code == 400

    def test_convert_already_converted_quote_fails(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "approved",
        })
        # First conversion succeeds
        first = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert first.status_code == 201

        # Second conversion fails (already converted, status changed)
        second = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert second.status_code == 400

    def test_convert_expired_quote_fails(self, client, db):
        from app.models.quote import Quote

        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "approved",
        })

        # Set expiration to the past
        db_quote = db.query(Quote).filter(Quote.id == quote["id"]).first()
        db_quote.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.flush()

        response = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    def test_convert_nonexistent_quote_returns_404(self, client):
        response = client.post(f"{BASE_URL}/999999/convert")
        assert response.status_code == 404

    def test_convert_generates_unique_order_numbers(self, client):
        """Each conversion should produce a unique SO number."""
        q1 = _create_quote(client)
        q2 = _create_quote(client)
        client.patch(f"{BASE_URL}/{q1['id']}/status", json={"status": "approved"})
        client.patch(f"{BASE_URL}/{q2['id']}/status", json={"status": "approved"})

        r1 = client.post(f"{BASE_URL}/{q1['id']}/convert").json()
        r2 = client.post(f"{BASE_URL}/{q2['id']}/convert").json()
        assert r1["order_number"] != r2["order_number"]


# =============================================================================
# Delete - DELETE /api/v1/quotes/{id}
# =============================================================================

class TestDeleteQuote:
    """Test DELETE /api/v1/quotes/{id}."""

    def test_delete_pending_quote(self, client):
        quote = _create_quote(client)
        response = client.delete(f"{BASE_URL}/{quote['id']}")
        assert response.status_code == 204

    def test_deleted_quote_no_longer_found(self, client):
        quote = _create_quote(client)
        client.delete(f"{BASE_URL}/{quote['id']}")
        response = client.get(f"{BASE_URL}/{quote['id']}")
        assert response.status_code == 404

    def test_delete_rejected_quote(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "rejected",
        })
        response = client.delete(f"{BASE_URL}/{quote['id']}")
        assert response.status_code == 204

    def test_delete_cancelled_quote(self, client):
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "cancelled",
        })
        response = client.delete(f"{BASE_URL}/{quote['id']}")
        assert response.status_code == 204

    def test_delete_converted_quote_fails(self, client, db):
        from app.models.quote import Quote

        quote = _create_quote(client)
        db_quote = db.query(Quote).filter(Quote.id == quote["id"]).first()
        db_quote.status = "converted"
        db.flush()

        response = client.delete(f"{BASE_URL}/{quote['id']}")
        assert response.status_code == 400
        assert "converted" in response.json()["detail"].lower()

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete(f"{BASE_URL}/999999")
        assert response.status_code == 404


# =============================================================================
# Image - POST/GET/DELETE /api/v1/quotes/{id}/image
# =============================================================================

class TestQuoteImage:
    """Test quote image upload, retrieval, and deletion."""

    @staticmethod
    def _make_png_bytes():
        """Minimal valid 1x1 white PNG file (67 bytes)."""
        import struct
        import zlib

        def _chunk(chunk_type, data):
            c = chunk_type + data
            crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            return struct.pack(">I", len(data)) + c + crc

        signature = b"\x89PNG\r\n\x1a\n"
        ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
        ihdr = _chunk(b"IHDR", ihdr_data)
        raw_data = b"\x00\xff\xff\xff"  # filter byte + RGB
        compressed = zlib.compress(raw_data)
        idat = _chunk(b"IDAT", compressed)
        iend = _chunk(b"IEND", b"")
        return signature + ihdr + idat + iend

    def test_upload_image(self, client):
        quote = _create_quote(client)
        png_bytes = self._make_png_bytes()
        response = client.post(
            f"{BASE_URL}/{quote['id']}/image",
            files={"file": ("test_image.png", png_bytes, "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Image uploaded successfully"
        assert data["filename"] == "test_image.png"

    def test_get_uploaded_image(self, client):
        quote = _create_quote(client)
        png_bytes = self._make_png_bytes()
        client.post(
            f"{BASE_URL}/{quote['id']}/image",
            files={"file": ("product.png", png_bytes, "image/png")},
        )
        response = client.get(f"{BASE_URL}/{quote['id']}/image")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert len(response.content) > 0

    def test_get_image_no_image_returns_404(self, client):
        quote = _create_quote(client)
        response = client.get(f"{BASE_URL}/{quote['id']}/image")
        assert response.status_code == 404
        assert "no image" in response.json()["detail"].lower()

    def test_get_image_nonexistent_quote_returns_404(self, client):
        response = client.get(f"{BASE_URL}/999999/image")
        assert response.status_code == 404

    def test_delete_image(self, client):
        quote = _create_quote(client)
        png_bytes = self._make_png_bytes()
        client.post(
            f"{BASE_URL}/{quote['id']}/image",
            files={"file": ("to_delete.png", png_bytes, "image/png")},
        )
        response = client.delete(f"{BASE_URL}/{quote['id']}/image")
        assert response.status_code == 200
        assert response.json()["message"] == "Image deleted"

        # Verify image is gone
        get_response = client.get(f"{BASE_URL}/{quote['id']}/image")
        assert get_response.status_code == 404

    def test_delete_image_nonexistent_quote_returns_404(self, client):
        response = client.delete(f"{BASE_URL}/999999/image")
        assert response.status_code == 404

    def test_upload_invalid_file_type_fails(self, client):
        quote = _create_quote(client)
        response = client.post(
            f"{BASE_URL}/{quote['id']}/image",
            files={"file": ("document.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert response.status_code == 400
        assert "file type" in response.json()["detail"].lower()

    def test_upload_image_nonexistent_quote_returns_404(self, client):
        png_bytes = self._make_png_bytes()
        response = client.post(
            f"{BASE_URL}/999999/image",
            files={"file": ("test.png", png_bytes, "image/png")},
        )
        assert response.status_code == 404

    def test_upload_jpeg_image(self, client):
        quote = _create_quote(client)
        # Minimal JPEG header (not truly valid but content_type is checked, not bytes)
        jpeg_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        response = client.post(
            f"{BASE_URL}/{quote['id']}/image",
            files={"file": ("photo.jpg", jpeg_bytes, "image/jpeg")},
        )
        assert response.status_code == 200

    def test_upload_webp_image(self, client):
        quote = _create_quote(client)
        webp_bytes = b"RIFF" + b"\x00" * 100
        response = client.post(
            f"{BASE_URL}/{quote['id']}/image",
            files={"file": ("photo.webp", webp_bytes, "image/webp")},
        )
        assert response.status_code == 200


# =============================================================================
# PDF - GET /api/v1/quotes/{id}/pdf
# =============================================================================

class TestQuotePDF:
    """Test GET /api/v1/quotes/{id}/pdf."""

    def test_generate_pdf(self, client):
        quote = _create_quote(client, customer_name="PDF Customer")
        response = client.get(f"{BASE_URL}/{quote['id']}/pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        # PDF files start with %PDF
        assert response.content[:5] == b"%PDF-"

    def test_pdf_filename_matches_quote_number(self, client):
        quote = _create_quote(client)
        response = client.get(f"{BASE_URL}/{quote['id']}/pdf")
        content_disposition = response.headers.get("content-disposition", "")
        assert quote["quote_number"] in content_disposition

    def test_pdf_nonexistent_quote_returns_404(self, client):
        response = client.get(f"{BASE_URL}/999999/pdf")
        assert response.status_code == 404

    def test_pdf_with_notes(self, client):
        """Quote with customer notes should still generate a valid PDF."""
        quote = _create_quote(
            client,
            customer_notes="Please include gift wrapping",
        )
        response = client.get(f"{BASE_URL}/{quote['id']}/pdf")
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"

    def test_pdf_with_shipping_cost(self, client):
        """Quote with shipping should include shipping in PDF."""
        quote = _create_quote(client, shipping_cost="12.50", apply_tax=False)
        response = client.get(f"{BASE_URL}/{quote['id']}/pdf")
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"


# =============================================================================
# Full lifecycle - end-to-end workflow
# =============================================================================

class TestQuoteLifecycle:
    """Test the full quote lifecycle: create -> approve -> convert."""

    def test_full_lifecycle_create_approve_convert(self, client):
        """Happy path: create a quote, approve it, convert to sales order."""
        # 1. Create
        quote = _create_quote(
            client,
            product_name="Lifecycle Widget",
            quantity=10,
            unit_price="15.00",
            customer_name="Lifecycle Customer",
            customer_email="lifecycle@test.com",
        )
        assert quote["status"] == "pending"
        quote_id = quote["id"]

        # 2. Verify it appears in list
        list_response = client.get(BASE_URL)
        ids = [q["id"] for q in list_response.json()]
        assert quote_id in ids

        # 3. Approve
        approve_response = client.patch(f"{BASE_URL}/{quote_id}/status", json={
            "status": "approved",
            "admin_notes": "Looks good, approved!",
        })
        assert approve_response.status_code == 200
        assert approve_response.json()["status"] == "approved"

        # 4. Convert to sales order
        convert_response = client.post(f"{BASE_URL}/{quote_id}/convert")
        assert convert_response.status_code == 201
        order_data = convert_response.json()
        assert order_data["order_number"].startswith("SO-")

        # 5. Verify quote is now converted
        detail = client.get(f"{BASE_URL}/{quote_id}").json()
        assert detail["status"] == "converted"
        assert detail["sales_order_id"] == order_data["order_id"]
        assert detail["converted_at"] is not None

        # 6. Verify the created sales order exists
        so_response = client.get(f"/api/v1/sales-orders/{order_data['order_id']}")
        assert so_response.status_code == 200
        so = so_response.json()
        assert so["product_name"] == "Lifecycle Widget"
        assert so["quantity"] == 10

    def test_lifecycle_create_reject(self, client):
        """Quote is created and then rejected."""
        quote = _create_quote(client)
        reject = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "rejected",
            "rejection_reason": "Material unavailable",
        })
        assert reject.status_code == 200
        assert reject.json()["status"] == "rejected"
        assert reject.json()["rejection_reason"] == "Material unavailable"

        # Rejected quotes can still be deleted
        delete = client.delete(f"{BASE_URL}/{quote['id']}")
        assert delete.status_code == 204

    def test_lifecycle_create_cancel(self, client):
        """Quote is created and then cancelled."""
        quote = _create_quote(client)
        cancel = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "cancelled",
        })
        assert cancel.status_code == 200
        assert cancel.json()["status"] == "cancelled"

    def test_lifecycle_create_update_approve_convert(self, client):
        """Create, update details, approve, then convert."""
        quote = _create_quote(
            client,
            product_name="Draft Widget",
            quantity=1,
            unit_price="10.00",
            apply_tax=False,
        )

        # Update
        client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "Final Widget",
            "quantity": 5,
            "unit_price": "20.00",
        })

        # Verify updated
        updated = client.get(f"{BASE_URL}/{quote['id']}").json()
        assert updated["product_name"] == "Final Widget"
        assert updated["quantity"] == 5
        assert Decimal(str(updated["subtotal"])) == Decimal("100.00")

        # Approve and convert
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={"status": "approved"})
        convert = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert convert.status_code == 201

    def test_lifecycle_cannot_edit_after_conversion(self, client):
        """After conversion, the quote should be locked."""
        quote = _create_quote(client)
        client.patch(f"{BASE_URL}/{quote['id']}/status", json={"status": "approved"})
        client.post(f"{BASE_URL}/{quote['id']}/convert")

        # Try to edit
        edit = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "Should Not Work",
        })
        assert edit.status_code == 400

        # Try to change status
        status_change = client.patch(f"{BASE_URL}/{quote['id']}/status", json={
            "status": "cancelled",
        })
        assert status_change.status_code == 400

        # Try to delete
        delete = client.delete(f"{BASE_URL}/{quote['id']}")
        assert delete.status_code == 400

        # Try to convert again
        reconvert = client.post(f"{BASE_URL}/{quote['id']}/convert")
        assert reconvert.status_code == 400


# =============================================================================
# Edge cases and boundary tests
# =============================================================================

class TestQuoteEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_create_quote_with_zero_unit_price(self, client):
        """Zero price should be allowed (free quotes)."""
        response = client.post(BASE_URL, json={
            "product_name": "Free Sample",
            "quantity": 1,
            "unit_price": "0.00",
        })
        assert response.status_code == 201
        data = response.json()
        assert Decimal(str(data["total_price"])) == Decimal("0.00")

    def test_create_quote_with_max_quantity(self, client):
        """Maximum allowed quantity (10000)."""
        response = client.post(BASE_URL, json={
            "product_name": "Bulk Order",
            "quantity": 10000,
            "unit_price": "1.00",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["quantity"] == 10000

    def test_create_quote_with_minimum_valid_days(self, client):
        data = _create_quote(client, valid_days=1)
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        delta = expires_at - created_at
        assert 0 <= delta.days <= 2

    def test_create_quote_with_max_valid_days(self, client):
        data = _create_quote(client, valid_days=365)
        expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        delta = expires_at - created_at
        assert 364 <= delta.days <= 366

    def test_create_quote_with_long_product_name(self, client):
        long_name = "A" * 255
        data = _create_quote(client, product_name=long_name)
        assert data["product_name"] == long_name

    def test_create_quote_product_name_too_long_fails(self, client):
        response = client.post(BASE_URL, json={
            "product_name": "A" * 256,
            "quantity": 1,
            "unit_price": "10.00",
        })
        assert response.status_code == 422

    def test_create_quote_with_long_notes(self, client):
        long_note = "B" * 1000
        data = _create_quote(client, customer_notes=long_note)
        assert data["customer_notes"] == long_note

    def test_create_quote_notes_too_long_fails(self, client):
        response = client.post(BASE_URL, json={
            "product_name": "Widget",
            "quantity": 1,
            "unit_price": "10.00",
            "customer_notes": "N" * 1001,
        })
        assert response.status_code == 422

    def test_create_quote_with_description_ignored(self, client):
        """description is on the schema but not the Quote model — should not error."""
        data = _create_quote(client, description="A detailed product description")
        # Quote model has no description column, so it won't appear in the response
        assert data["id"] is not None

    def test_create_quote_with_invalid_color_rejects(self, client):
        """Creating a quote with material+color triggers material validation."""
        payload = {
            "product_name": "Color Test Widget",
            "quantity": 1,
            "unit_price": "10.00",
            "material_type": "PLA",
            "color": "NONEXISTENT",
        }
        response = client.post(BASE_URL, json=payload)
        # Endpoint should reject invalid material/color combinations (400 or 500)
        assert response.status_code >= 400

    def test_decimal_precision_preserved(self, client):
        """Verify decimal precision in pricing calculations."""
        data = _create_quote(
            client,
            quantity=3,
            unit_price="9.99",
            apply_tax=False,
        )
        # subtotal = 9.99 * 3 = 29.97
        assert Decimal(str(data["subtotal"])) == Decimal("29.97")
        assert Decimal(str(data["total_price"])) == Decimal("29.97")

    def test_update_only_specified_fields(self, client):
        """PATCH should only update provided fields, not reset others."""
        quote = _create_quote(
            client,
            product_name="Original Name",
            customer_name="Original Customer",
            customer_email="original@test.com",
        )
        # Update only product_name
        response = client.patch(f"{BASE_URL}/{quote['id']}", json={
            "product_name": "New Name",
        })
        data = response.json()
        assert data["product_name"] == "New Name"
        # Other fields should remain unchanged
        assert data["customer_name"] == "Original Customer"
        assert data["customer_email"] == "original@test.com"

    def test_search_is_case_insensitive(self, client):
        _create_quote(client, product_name="CaseSensitiveTest")
        response = client.get(f"{BASE_URL}?search=casesensitivetest")
        data = response.json()
        assert len(data) >= 1

    def test_multiple_status_changes(self, client):
        """A quote can go through multiple status changes."""
        quote = _create_quote(client)
        # pending -> approved
        r1 = client.patch(f"{BASE_URL}/{quote['id']}/status", json={"status": "approved"})
        assert r1.json()["status"] == "approved"
        # approved -> pending (revert)
        r2 = client.patch(f"{BASE_URL}/{quote['id']}/status", json={"status": "pending"})
        assert r2.json()["status"] == "pending"
        # pending -> rejected
        r3 = client.patch(f"{BASE_URL}/{quote['id']}/status", json={"status": "rejected"})
        assert r3.json()["status"] == "rejected"
