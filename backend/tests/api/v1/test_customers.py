"""
Tests for Admin Customers API endpoints (app/api/v1/endpoints/admin/customers.py)

Covers:
- GET /api/v1/admin/customers/ (list with search, status filter, pagination)
- GET /api/v1/admin/customers/search?q=... (quick search for dropdowns)
- GET /api/v1/admin/customers/{id} (get single customer with stats)
- POST /api/v1/admin/customers/ (create customer, generates CUST-NNN)
- PATCH /api/v1/admin/customers/{id} (partial update, duplicate email check)
- DELETE /api/v1/admin/customers/{id} (soft delete with orders, hard delete without)
- GET /api/v1/admin/customers/{id}/orders (customer order history)
- GET /api/v1/admin/customers/import/template (download CSV template)
- POST /api/v1/admin/customers/import/preview (preview CSV import)
- POST /api/v1/admin/customers/import (import customers from CSV)
- Auth: 401 without token on key endpoints
"""
import io
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


BASE_URL = "/api/v1/admin/customers"


# =============================================================================
# Helper: create a customer via the API (returns response JSON)
# =============================================================================

def _create_customer(client, **overrides):
    """Helper to create a customer and return the JSON response."""
    uid = uuid.uuid4().hex[:8]
    payload = {
        "email": f"test-{uid}@example.com",
        "first_name": "Test",
        "last_name": "Customer",
        "company_name": f"Test Co {uid}",
        "phone": "555-0100",
    }
    payload.update(overrides)
    response = client.post(BASE_URL, json=payload)
    assert response.status_code == 201, f"Create failed: {response.text}"
    return response.json()


# =============================================================================
# Auth tests
# =============================================================================

class TestCustomerAuth:
    """Verify auth is required on all protected endpoints."""

    def test_list_requires_auth(self, unauthed_client):
        response = unauthed_client.get(BASE_URL)
        assert response.status_code == 401

    def test_get_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_create_requires_auth(self, unauthed_client):
        response = unauthed_client.post(BASE_URL, json={
            "email": "noauth@example.com",
            "first_name": "No",
            "last_name": "Auth",
        })
        assert response.status_code == 401

    def test_update_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/1", json={
            "first_name": "Updated",
        })
        assert response.status_code == 401

    def test_delete_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_search_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/search", params={"q": "test"})
        assert response.status_code == 401

    def test_orders_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1/orders")
        assert response.status_code == 401

    def test_import_template_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/import/template")
        assert response.status_code == 401

    def test_import_requires_auth(self, unauthed_client):
        csv_content = "email,first_name,last_name\ntest@example.com,John,Doe"
        response = unauthed_client.post(
            f"{BASE_URL}/import",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 401


# =============================================================================
# POST /api/v1/admin/customers/ - Create customer
# =============================================================================

class TestCreateCustomer:
    """Test customer creation endpoint."""

    def test_create_customer_minimal(self, client):
        """Create a customer with only the required email field."""
        uid = uuid.uuid4().hex[:8]
        response = client.post(BASE_URL, json={
            "email": f"minimal-{uid}@example.com",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == f"minimal-{uid}@example.com"
        assert data["customer_number"].startswith("CUST-")
        assert data["status"] == "active"
        assert data["order_count"] == 0
        assert data["total_spent"] == 0.0
        assert data["total_paid"] == 0.0
        assert data["outstanding_balance"] == 0.0

    def test_create_customer_full(self, client):
        """Create a customer with all fields populated."""
        uid = uuid.uuid4().hex[:8]
        payload = {
            "email": f"full-{uid}@example.com",
            "first_name": "Jane",
            "last_name": "Doe",
            "company_name": "Acme Corp",
            "phone": "555-1234",
            "billing_address_line1": "123 Main St",
            "billing_address_line2": "Suite 100",
            "billing_city": "Springfield",
            "billing_state": "IL",
            "billing_zip": "62701",
            "billing_country": "USA",
            "shipping_address_line1": "456 Oak Ave",
            "shipping_city": "Chicago",
            "shipping_state": "IL",
            "shipping_zip": "60601",
            "shipping_country": "USA",
        }
        response = client.post(BASE_URL, json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["first_name"] == "Jane"
        assert data["last_name"] == "Doe"
        assert data["company_name"] == "Acme Corp"
        assert data["phone"] == "555-1234"
        assert data["billing_address_line1"] == "123 Main St"
        assert data["billing_city"] == "Springfield"
        assert data["shipping_address_line1"] == "456 Oak Ave"
        assert data["shipping_city"] == "Chicago"

    def test_create_customer_generates_customer_number(self, client):
        """Customer number is auto-generated with CUST- prefix."""
        c1 = _create_customer(client)
        c2 = _create_customer(client)
        assert c1["customer_number"].startswith("CUST-")
        assert c2["customer_number"].startswith("CUST-")
        # Numbers should be different
        assert c1["customer_number"] != c2["customer_number"]

    def test_create_customer_defaults_country_to_usa(self, client):
        """Country fields default to USA when not provided."""
        customer = _create_customer(client)
        assert customer["billing_country"] == "USA"
        assert customer["shipping_country"] == "USA"

    def test_create_customer_duplicate_email(self, client):
        """Duplicate email returns 400."""
        uid = uuid.uuid4().hex[:8]
        email = f"dup-{uid}@example.com"
        _create_customer(client, email=email)

        response = client.post(BASE_URL, json={"email": email})
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    def test_create_customer_invalid_email(self, client):
        """Invalid email format returns 422."""
        response = client.post(BASE_URL, json={"email": "not-an-email"})
        assert response.status_code == 422

    def test_create_customer_missing_email(self, client):
        """Missing required email returns 422."""
        response = client.post(BASE_URL, json={"first_name": "No Email"})
        assert response.status_code == 422

    def test_create_customer_email_verified_is_false(self, client):
        """New customers should have email_verified=False."""
        customer = _create_customer(client)
        assert customer["email_verified"] is False

    def test_create_customer_with_status(self, client):
        """Customer can be created with a specific status."""
        customer = _create_customer(client, status="inactive")
        assert customer["status"] == "inactive"


# =============================================================================
# GET /api/v1/admin/customers/ - List customers
# =============================================================================

class TestListCustomers:
    """Test customer listing with filters and pagination."""

    def test_list_customers_empty(self, client):
        """List returns an array (may be empty if no customers exist)."""
        response = client.get(BASE_URL)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_returns_created_customer(self, client):
        """Created customers appear in list results."""
        customer = _create_customer(client)
        response = client.get(BASE_URL)
        assert response.status_code == 200
        data = response.json()
        emails = [c["email"] for c in data]
        assert customer["email"] in emails

    def test_list_customer_has_expected_fields(self, client):
        """List response includes summary fields and stats."""
        _create_customer(client, first_name="FieldCheck", last_name="Test")
        response = client.get(BASE_URL)
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0
        item = data[0]
        assert "id" in item
        assert "customer_number" in item
        assert "email" in item
        assert "status" in item
        assert "order_count" in item
        assert "total_spent" in item
        assert "total_paid" in item
        assert "outstanding_balance" in item
        assert "created_at" in item

    def test_list_search_by_email(self, client):
        """Search parameter filters by email."""
        uid = uuid.uuid4().hex[:8]
        email = f"searchable-{uid}@example.com"
        _create_customer(client, email=email)

        response = client.get(BASE_URL, params={"search": f"searchable-{uid}"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(c["email"] == email for c in data)

    def test_list_search_by_company(self, client):
        """Search parameter filters by company name."""
        uid = uuid.uuid4().hex[:8]
        company = f"UniqueCompany-{uid}"
        _create_customer(client, company_name=company)

        response = client.get(BASE_URL, params={"search": company})
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(c["company_name"] == company for c in data)

    def test_list_search_by_first_name(self, client):
        """Search parameter filters by first name."""
        uid = uuid.uuid4().hex[:8]
        name = f"Unique{uid}"
        _create_customer(client, first_name=name)

        response = client.get(BASE_URL, params={"search": name})
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(c["first_name"] == name for c in data)

    def test_list_status_filter(self, client):
        """Status filter returns only matching customers."""
        _create_customer(client, status="inactive")

        response = client.get(BASE_URL, params={"status": "inactive"})
        assert response.status_code == 200
        data = response.json()
        for c in data:
            assert c["status"] == "inactive"

    def test_list_excludes_inactive_by_default(self, client):
        """By default, inactive customers are excluded."""
        uid = uuid.uuid4().hex[:8]
        email = f"inactive-{uid}@example.com"
        _create_customer(client, email=email, status="inactive")

        response = client.get(BASE_URL)
        assert response.status_code == 200
        data = response.json()
        assert not any(c["email"] == email for c in data)

    def test_list_include_inactive(self, client):
        """include_inactive=true shows inactive customers."""
        uid = uuid.uuid4().hex[:8]
        email = f"inactive-show-{uid}@example.com"
        _create_customer(client, email=email, status="inactive")

        response = client.get(BASE_URL, params={"include_inactive": True})
        assert response.status_code == 200
        data = response.json()
        assert any(c["email"] == email for c in data)

    def test_list_pagination_skip(self, client):
        """Skip parameter offsets results."""
        for _ in range(3):
            _create_customer(client)

        all_response = client.get(BASE_URL, params={"limit": 100})
        skip_response = client.get(BASE_URL, params={"skip": 1, "limit": 100})
        assert all_response.status_code == 200
        assert skip_response.status_code == 200
        assert len(skip_response.json()) == len(all_response.json()) - 1

    def test_list_pagination_limit(self, client):
        """Limit parameter caps number of results."""
        for _ in range(3):
            _create_customer(client)

        response = client.get(BASE_URL, params={"limit": 2})
        assert response.status_code == 200
        assert len(response.json()) <= 2

    def test_list_full_name_constructed(self, client):
        """Full name is built from first + last name."""
        _create_customer(client, first_name="Jane", last_name="Smith")
        response = client.get(BASE_URL, params={"search": "Jane"})
        assert response.status_code == 200
        data = response.json()
        match = [c for c in data if c["first_name"] == "Jane" and c["last_name"] == "Smith"]
        assert len(match) >= 1
        assert match[0]["full_name"] == "Jane Smith"

    def test_list_counts_orders_linked_by_customer_id(self, client, db, make_sales_order):
        """Customer list stats include staff-owned orders linked by customer_id."""
        customer = _create_customer(client, first_name="LinkedStats")
        customer_id = customer["id"]
        order = make_sales_order(
            user_id=1,
            customer_id=customer_id,
            status="confirmed",
        )
        order.grand_total = Decimal("87.65")
        order.total_price = Decimal("87.65")
        db.flush()

        response = client.get(BASE_URL, params={"search": customer["email"]})
        assert response.status_code == 200
        match = next(c for c in response.json() if c["id"] == customer_id)
        assert match["order_count"] == 1
        assert match["total_spent"] == 87.65

    def test_list_allocates_paid_and_outstanding_by_customer_id(self, client, db, make_sales_order):
        """Customer list stats include net paid cash and outstanding balance."""
        from app.models.payment import Payment

        customer = _create_customer(client, first_name="PaymentStats")
        customer_id = customer["id"]
        order = make_sales_order(
            user_id=1,
            customer_id=customer_id,
            status="confirmed",
        )
        order.total_price = Decimal("100.00")
        order.tax_amount = Decimal("10.00")
        order.shipping_cost = Decimal("10.00")
        order.grand_total = Decimal("120.00")
        db.add_all([
            Payment(
                payment_number=f"PAY-{uuid.uuid4().hex[:8]}",
                sales_order_id=order.id,
                recorded_by_id=1,
                amount=Decimal("50.00"),
                payment_method="card",
                payment_type="payment",
                status="completed",
            ),
            Payment(
                payment_number=f"PAY-{uuid.uuid4().hex[:8]}",
                sales_order_id=order.id,
                recorded_by_id=1,
                amount=Decimal("-10.00"),
                payment_method="card",
                payment_type="refund",
                status="completed",
            ),
        ])
        db.flush()

        response = client.get(BASE_URL, params={"search": customer["email"]})
        assert response.status_code == 200
        match = next(c for c in response.json() if c["id"] == customer_id)
        assert match["total_spent"] == 120.0
        assert match["total_paid"] == 40.0
        assert match["outstanding_balance"] == 80.0

    def test_list_maps_payment_stats_to_each_customer(self, client, db, make_sales_order):
        """Customer list batch stats are mapped back to the right customers."""
        from app.models.payment import Payment

        first_customer = _create_customer(client, first_name="BatchStatsA")
        second_customer = _create_customer(client, first_name="BatchStatsB")
        first_order = make_sales_order(
            user_id=1,
            customer_id=first_customer["id"],
            status="confirmed",
        )
        first_order.grand_total = Decimal("120.00")
        first_order.total_price = Decimal("120.00")
        second_order = make_sales_order(
            user_id=1,
            customer_id=second_customer["id"],
            status="confirmed",
        )
        second_order.grand_total = Decimal("80.00")
        second_order.total_price = Decimal("80.00")
        db.add_all([
            Payment(
                payment_number=f"PAY-{uuid.uuid4().hex[:8]}",
                sales_order_id=first_order.id,
                recorded_by_id=1,
                amount=Decimal("50.00"),
                payment_method="card",
                payment_type="payment",
                status="completed",
            ),
            Payment(
                payment_number=f"PAY-{uuid.uuid4().hex[:8]}",
                sales_order_id=second_order.id,
                recorded_by_id=1,
                amount=Decimal("80.00"),
                payment_method="card",
                payment_type="payment",
                status="completed",
            ),
        ])
        db.flush()

        response = client.get(BASE_URL, params={"limit": 100})
        assert response.status_code == 200
        customers_by_id = {customer["id"]: customer for customer in response.json()}
        first_stats = customers_by_id[first_customer["id"]]
        second_stats = customers_by_id[second_customer["id"]]
        assert first_stats["total_spent"] == 120.0
        assert first_stats["total_paid"] == 50.0
        assert first_stats["outstanding_balance"] == 70.0
        assert second_stats["total_spent"] == 80.0
        assert second_stats["total_paid"] == 80.0
        assert second_stats["outstanding_balance"] == 0.0


# =============================================================================
# GET /api/v1/admin/customers/search?q=... - Quick search
# =============================================================================

class TestSearchCustomers:
    """Test quick search endpoint for dropdowns/autocomplete."""

    def test_search_returns_results(self, client):
        """Search by email returns matching customers."""
        uid = uuid.uuid4().hex[:8]
        email = f"quicksearch-{uid}@example.com"
        _create_customer(client, email=email)

        response = client.get(f"{BASE_URL}/search", params={"q": f"quicksearch-{uid}"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["email"] == email

    def test_search_returns_lightweight_fields(self, client):
        """Search results contain only lightweight fields for dropdowns."""
        _create_customer(client, first_name="Dropdown", last_name="User")
        response = client.get(f"{BASE_URL}/search", params={"q": "Dropdown"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        item = data[0]
        assert "id" in item
        assert "customer_number" in item
        assert "email" in item
        assert "full_name" in item
        assert "company_name" in item
        # Should not include heavy fields like addresses or stats
        assert "billing_address_line1" not in item
        assert "order_count" not in item

    def test_search_requires_q_param(self, client):
        """Missing q parameter returns 422."""
        response = client.get(f"{BASE_URL}/search")
        assert response.status_code == 422

    def test_search_by_company_name(self, client):
        """Search by company name works."""
        uid = uuid.uuid4().hex[:8]
        company = f"SearchCo-{uid}"
        _create_customer(client, company_name=company)

        response = client.get(f"{BASE_URL}/search", params={"q": company})
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(c["company_name"] == company for c in data)

    def test_search_by_customer_number(self, client):
        """Search by CUST-NNN number works."""
        customer = _create_customer(client)
        cust_num = customer["customer_number"]

        response = client.get(f"{BASE_URL}/search", params={"q": cust_num})
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(c["customer_number"] == cust_num for c in data)

    def test_search_no_results(self, client):
        """Search with non-matching term returns empty list."""
        response = client.get(f"{BASE_URL}/search", params={"q": "zzznonexistent999"})
        assert response.status_code == 200
        assert response.json() == []

    def test_search_excludes_inactive(self, client):
        """Quick search only returns active customers."""
        uid = uuid.uuid4().hex[:8]
        email = f"inactivesearch-{uid}@example.com"
        _create_customer(client, email=email, status="inactive")

        response = client.get(f"{BASE_URL}/search", params={"q": f"inactivesearch-{uid}"})
        assert response.status_code == 200
        assert not any(c["email"] == email for c in response.json())


# =============================================================================
# GET /api/v1/admin/customers/{id} - Get single customer
# =============================================================================

class TestGetCustomer:
    """Test get single customer endpoint."""

    def test_get_customer(self, client):
        """Get a customer by ID returns full details."""
        customer = _create_customer(client, first_name="GetMe", last_name="Now")
        customer_id = customer["id"]

        response = client.get(f"{BASE_URL}/{customer_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == customer_id
        assert data["first_name"] == "GetMe"
        assert data["last_name"] == "Now"
        assert data["customer_number"] is not None

    def test_get_customer_includes_stats(self, client):
        """Get customer response includes order, quote, booked, paid, and balance stats."""
        customer = _create_customer(client)
        response = client.get(f"{BASE_URL}/{customer['id']}")
        assert response.status_code == 200
        data = response.json()
        assert "order_count" in data
        assert "quote_count" in data
        assert "total_spent" in data
        assert "total_paid" in data
        assert "outstanding_balance" in data
        assert data["order_count"] == 0
        assert data["quote_count"] == 0
        assert data["total_spent"] == 0.0
        assert data["total_paid"] == 0.0
        assert data["outstanding_balance"] == 0.0

    def test_get_customer_counts_orders_linked_by_customer_id(self, client, db, make_sales_order):
        """Staff-owned orders linked via customer_id count toward customer stats."""
        customer = _create_customer(client)
        customer_id = customer["id"]
        order = make_sales_order(
            user_id=1,
            customer_id=customer_id,
            status="confirmed",
        )
        order.grand_total = Decimal("123.45")
        order.total_price = Decimal("123.45")
        db.flush()

        response = client.get(f"{BASE_URL}/{customer_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["order_count"] == 1
        assert data["total_spent"] == 123.45

    def test_get_customer_preserves_zero_grand_total(self, client, db, make_sales_order):
        """A zero grand_total is authoritative and does not fall back to total_price."""
        customer = _create_customer(client)
        customer_id = customer["id"]
        order = make_sales_order(
            user_id=1,
            customer_id=customer_id,
            status="confirmed",
        )
        order.grand_total = Decimal("0.00")
        order.total_price = Decimal("99.99")
        db.flush()

        response = client.get(f"{BASE_URL}/{customer_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["order_count"] == 1
        assert data["total_spent"] == 0.0
        assert data["outstanding_balance"] == 0.0

    def test_get_customer_allocates_paid_and_outstanding(self, client, db, make_sales_order):
        """Customer detail separates booked order value from net paid cash."""
        from app.models.payment import Payment

        customer = _create_customer(client)
        customer_id = customer["id"]
        order = make_sales_order(
            user_id=1,
            customer_id=customer_id,
            status="confirmed",
        )
        order.grand_total = Decimal("200.00")
        order.total_price = Decimal("175.00")
        db.add(Payment(
            payment_number=f"PAY-{uuid.uuid4().hex[:8]}",
            sales_order_id=order.id,
            recorded_by_id=1,
            amount=Decimal("75.00"),
            payment_method="cash",
            payment_type="payment",
            status="completed",
        ))
        db.flush()

        response = client.get(f"{BASE_URL}/{customer_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["total_spent"] == 200.0
        assert data["total_paid"] == 75.0
        assert data["outstanding_balance"] == 125.0

    def test_get_customer_counts_quotes_linked_by_customer_id(self, client, db):
        """Staff-owned quotes linked via customer_id count toward customer stats."""
        from app.models.quote import Quote

        customer = _create_customer(client)
        quote = Quote(
            user_id=1,
            customer_id=customer["id"],
            quote_number=f"Q-CUST-{uuid.uuid4().hex[:8]}",
            product_name="Customer Linked Quote",
            quantity=1,
            material_type="PLA",
            unit_price=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_price=Decimal("10.00"),
            status="pending",
            file_format="manual",
            file_size_bytes=0,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(quote)
        db.flush()

        response = client.get(f"{BASE_URL}/{customer['id']}")
        assert response.status_code == 200
        assert response.json()["quote_count"] == 1

    def test_get_customer_includes_addresses(self, client):
        """Get customer includes full billing and shipping address fields."""
        customer = _create_customer(
            client,
            billing_address_line1="100 Bill St",
            billing_city="Billville",
            shipping_address_line1="200 Ship Rd",
            shipping_city="Shiptown",
        )
        response = client.get(f"{BASE_URL}/{customer['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["billing_address_line1"] == "100 Bill St"
        assert data["billing_city"] == "Billville"
        assert data["shipping_address_line1"] == "200 Ship Rd"
        assert data["shipping_city"] == "Shiptown"

    def test_get_customer_not_found(self, client):
        """Non-existent ID returns 404."""
        response = client.get(f"{BASE_URL}/999999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_non_customer_user_returns_404(self, client):
        """Getting user_id=1 (an admin, not a customer) returns 404."""
        response = client.get(f"{BASE_URL}/1")
        assert response.status_code == 404


# =============================================================================
# PATCH /api/v1/admin/customers/{id} - Update customer
# =============================================================================

class TestUpdateCustomer:
    """Test partial update of customer records."""

    def test_update_first_name(self, client):
        """Partial update of first_name works."""
        customer = _create_customer(client, first_name="Old")
        response = client.patch(
            f"{BASE_URL}/{customer['id']}",
            json={"first_name": "New"},
        )
        assert response.status_code == 200
        assert response.json()["first_name"] == "New"

    def test_update_email(self, client):
        """Email can be updated."""
        customer = _create_customer(client)
        uid = uuid.uuid4().hex[:8]
        new_email = f"updated-{uid}@example.com"
        response = client.patch(
            f"{BASE_URL}/{customer['id']}",
            json={"email": new_email},
        )
        assert response.status_code == 200
        assert response.json()["email"] == new_email

    def test_update_duplicate_email(self, client):
        """Updating to an existing email returns 400."""
        c1 = _create_customer(client)
        c2 = _create_customer(client)

        response = client.patch(
            f"{BASE_URL}/{c2['id']}",
            json={"email": c1["email"]},
        )
        assert response.status_code == 400
        assert "already in use" in response.json()["detail"].lower()

    def test_update_same_email_is_allowed(self, client):
        """Updating with the same email (no change) is fine."""
        customer = _create_customer(client)
        response = client.patch(
            f"{BASE_URL}/{customer['id']}",
            json={"email": customer["email"]},
        )
        assert response.status_code == 200

    def test_update_address_fields(self, client):
        """Address fields can be updated."""
        customer = _create_customer(client)
        response = client.patch(
            f"{BASE_URL}/{customer['id']}",
            json={
                "billing_address_line1": "999 New St",
                "billing_city": "Newville",
                "shipping_address_line1": "888 Ship Ln",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["billing_address_line1"] == "999 New St"
        assert data["billing_city"] == "Newville"
        assert data["shipping_address_line1"] == "888 Ship Ln"

    def test_update_status(self, client):
        """Status can be updated."""
        customer = _create_customer(client)
        response = client.patch(
            f"{BASE_URL}/{customer['id']}",
            json={"status": "inactive"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "inactive"

    def test_update_not_found(self, client):
        """Updating non-existent customer returns 404."""
        response = client.patch(
            f"{BASE_URL}/999999",
            json={"first_name": "Ghost"},
        )
        assert response.status_code == 404

    def test_update_preserves_unchanged_fields(self, client):
        """Fields not included in the update are preserved."""
        customer = _create_customer(
            client,
            first_name="Keep",
            last_name="This",
            company_name="Stable Corp",
        )
        response = client.patch(
            f"{BASE_URL}/{customer['id']}",
            json={"phone": "555-9999"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Keep"
        assert data["last_name"] == "This"
        assert data["company_name"] == "Stable Corp"
        assert data["phone"] == "555-9999"


# =============================================================================
# DELETE /api/v1/admin/customers/{id}
# =============================================================================

class TestDeleteCustomer:
    """Test customer deletion (hard delete without orders, soft delete with)."""

    def test_hard_delete_no_orders(self, client):
        """Customer with no orders is hard-deleted (removed from DB)."""
        customer = _create_customer(client)
        customer_id = customer["id"]

        response = client.delete(f"{BASE_URL}/{customer_id}")
        assert response.status_code == 204

        # Verify customer is gone
        get_response = client.get(f"{BASE_URL}/{customer_id}")
        assert get_response.status_code == 404

    def test_soft_delete_with_orders(self, client, make_sales_order):
        """Customer with orders is soft-deleted (status set to inactive)."""
        customer = _create_customer(client)
        customer_id = customer["id"]

        # Create an order linked to this customer
        make_sales_order(user_id=customer_id, status="draft")

        response = client.delete(f"{BASE_URL}/{customer_id}")
        assert response.status_code == 204

        # Customer should still exist but be inactive
        get_response = client.get(f"{BASE_URL}/{customer_id}")
        assert get_response.status_code == 200
        assert get_response.json()["status"] == "inactive"

    def test_delete_not_found(self, client):
        """Deleting non-existent customer returns 404."""
        response = client.delete(f"{BASE_URL}/999999")
        assert response.status_code == 404

    def test_delete_non_customer_returns_404(self, client):
        """Deleting user_id=1 (admin user) returns 404."""
        response = client.delete(f"{BASE_URL}/1")
        assert response.status_code == 404


# =============================================================================
# GET /api/v1/admin/customers/{id}/orders
# =============================================================================

class TestCustomerOrders:
    """Test customer order history endpoint."""

    def test_orders_empty(self, client):
        """Customer with no orders returns empty list."""
        customer = _create_customer(client)
        response = client.get(f"{BASE_URL}/{customer['id']}/orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_orders_returns_linked_orders(self, client, make_sales_order):
        """Orders linked to the customer are returned."""
        customer = _create_customer(client)
        customer_id = customer["id"]
        so = make_sales_order(user_id=customer_id, status="confirmed")

        response = client.get(f"{BASE_URL}/{customer_id}/orders")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        order = data[0]
        assert "id" in order
        assert "order_number" in order
        assert "status" in order
        assert "grand_total" in order
        assert "amount_paid" in order
        assert "balance_due" in order
        assert "created_at" in order

    def test_orders_returns_orders_linked_by_customer_id(self, client, make_sales_order):
        """Order history includes staff-owned orders linked by customer_id."""
        customer = _create_customer(client)
        customer_id = customer["id"]
        so = make_sales_order(user_id=1, customer_id=customer_id, status="confirmed")

        response = client.get(f"{BASE_URL}/{customer_id}/orders")
        assert response.status_code == 200
        data = response.json()
        assert any(order["id"] == so.id for order in data)

    def test_orders_not_found(self, client):
        """Orders for non-existent customer returns 404."""
        response = client.get(f"{BASE_URL}/999999/orders")
        assert response.status_code == 404

    def test_orders_non_customer_returns_404(self, client):
        """Orders for admin user (not customer type) returns 404."""
        response = client.get(f"{BASE_URL}/1/orders")
        assert response.status_code == 404


# =============================================================================
# GET /api/v1/admin/customers/import/template
# =============================================================================

class TestImportTemplate:
    """Test CSV template download."""

    def test_download_template(self, client):
        """Template endpoint returns a CSV file."""
        response = client.get(f"{BASE_URL}/import/template")
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        assert "customer_import_template" in response.headers.get(
            "content-disposition", ""
        )

    def test_template_contains_headers(self, client):
        """Template CSV contains expected column headers."""
        response = client.get(f"{BASE_URL}/import/template")
        assert response.status_code == 200
        content = response.text
        assert "email" in content
        assert "first_name" in content
        assert "last_name" in content
        assert "company_name" in content
        assert "phone" in content
        assert "billing_address_line1" in content
        assert "shipping_address_line1" in content

    def test_template_contains_example_row(self, client):
        """Template includes an example data row."""
        response = client.get(f"{BASE_URL}/import/template")
        assert response.status_code == 200
        content = response.text
        assert "john@example.com" in content
        assert "Acme Corp" in content


# =============================================================================
# POST /api/v1/admin/customers/import/preview
# =============================================================================

class TestImportPreview:
    """Test CSV import preview endpoint."""

    def test_preview_valid_csv(self, client):
        """Preview parses valid CSV and returns row data."""
        uid = uuid.uuid4().hex[:8]
        csv_content = (
            "email,first_name,last_name,company_name\n"
            f"preview-{uid}@example.com,John,Doe,Preview Corp\n"
        )
        response = client.post(
            f"{BASE_URL}/import/preview",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 1
        assert data["valid_rows"] == 1
        assert data["error_rows"] == 0
        assert len(data["rows"]) == 1
        assert data["rows"][0]["valid"] is True
        assert data["rows"][0]["data"]["email"] == f"preview-{uid}@example.com"

    def test_preview_missing_email(self, client):
        """Preview flags rows with missing email as errors."""
        csv_content = "email,first_name\n,John\n"
        response = client.post(
            f"{BASE_URL}/import/preview",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["error_rows"] == 1
        assert data["rows"][0]["valid"] is False
        assert any("required" in e.lower() for e in data["rows"][0]["errors"])

    def test_preview_invalid_email(self, client):
        """Preview flags rows with invalid email format."""
        csv_content = "email,first_name\nnot-an-email,John\n"
        response = client.post(
            f"{BASE_URL}/import/preview",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["error_rows"] == 1
        assert data["rows"][0]["valid"] is False

    def test_preview_duplicate_email_in_csv(self, client):
        """Preview flags duplicate emails within the same CSV."""
        uid = uuid.uuid4().hex[:8]
        email = f"dup-csv-{uid}@example.com"
        csv_content = (
            "email,first_name\n"
            f"{email},First\n"
            f"{email},Second\n"
        )
        response = client.post(
            f"{BASE_URL}/import/preview",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid_rows"] == 1
        assert data["error_rows"] == 1
        # Second row should have the duplicate error
        dup_row = data["rows"][1]
        assert dup_row["valid"] is False
        assert any("duplicate" in e.lower() for e in dup_row["errors"])

    def test_preview_existing_email_in_db(self, client):
        """Preview flags emails that already exist in the database."""
        existing = _create_customer(client)
        csv_content = f"email,first_name\n{existing['email']},Existing\n"
        response = client.post(
            f"{BASE_URL}/import/preview",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["error_rows"] == 1
        assert data["rows"][0]["valid"] is False
        assert any("already exists" in e.lower() for e in data["rows"][0]["errors"])

    def test_preview_non_csv_file(self, client):
        """Non-CSV file returns 400."""
        response = client.post(
            f"{BASE_URL}/import/preview",
            files={"file": ("data.txt", io.BytesIO(b"not csv"), "text/plain")},
        )
        assert response.status_code == 400
        assert "csv" in response.json()["detail"].lower()

    def test_preview_detected_format(self, client):
        """Preview detects the CSV format."""
        uid = uuid.uuid4().hex[:8]
        csv_content = f"email,first_name,last_name\nformat-{uid}@example.com,A,B\n"
        response = client.post(
            f"{BASE_URL}/import/preview",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "detected_format" in data

    def test_preview_multiple_rows(self, client):
        """Preview handles multiple rows correctly."""
        uid = uuid.uuid4().hex[:8]
        csv_content = (
            "email,first_name,last_name\n"
            f"a-{uid}@example.com,Alice,One\n"
            f"b-{uid}@example.com,Bob,Two\n"
            f"c-{uid}@example.com,Charlie,Three\n"
        )
        response = client.post(
            f"{BASE_URL}/import/preview",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_rows"] == 3
        assert data["valid_rows"] == 3
        assert data["error_rows"] == 0


# =============================================================================
# POST /api/v1/admin/customers/import
# =============================================================================

class TestImportCustomers:
    """Test CSV customer import endpoint."""

    def test_import_valid_csv(self, client):
        """Import creates customers from valid CSV."""
        uid = uuid.uuid4().hex[:8]
        csv_content = (
            "email,first_name,last_name,company_name\n"
            f"import-a-{uid}@example.com,Alice,Import,Import Corp\n"
            f"import-b-{uid}@example.com,Bob,Import,Import Inc\n"
        )
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 2
        assert data["skipped"] == 0

    def test_import_skips_duplicate_emails(self, client):
        """Import skips rows with emails that already exist."""
        existing = _create_customer(client)
        uid = uuid.uuid4().hex[:8]
        csv_content = (
            "email,first_name\n"
            f"{existing['email']},Duplicate\n"
            f"new-{uid}@example.com,Fresh\n"
        )
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["skipped"] == 1

    def test_import_skips_invalid_emails(self, client):
        """Import skips rows with missing or invalid email."""
        uid = uuid.uuid4().hex[:8]
        csv_content = (
            "email,first_name\n"
            ",NoEmail\n"
            "bademail,BadFormat\n"
            f"valid-{uid}@example.com,Valid\n"
        )
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 1
        assert data["skipped"] == 2

    def test_import_non_csv_file(self, client):
        """Non-CSV file returns 400."""
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("data.xlsx", io.BytesIO(b"not csv"), "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_import_returns_error_details(self, client):
        """Import response includes error details for skipped rows."""
        csv_content = "email,first_name\n,Missing\n"
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["skipped"] >= 1
        assert len(data["errors"]) >= 1
        assert "row" in data["errors"][0]
        assert "reason" in data["errors"][0]

    def test_import_generates_customer_numbers(self, client):
        """Imported customers get auto-generated CUST-NNN numbers."""
        uid = uuid.uuid4().hex[:8]
        csv_content = f"email,first_name\nimported-{uid}@example.com,Numbered\n"
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1

        # Verify the imported customer has a customer number
        search = client.get(f"{BASE_URL}/search", params={"q": f"imported-{uid}"})
        assert search.status_code == 200
        results = search.json()
        assert len(results) >= 1
        assert results[0]["customer_number"] is not None
        assert results[0]["customer_number"].startswith("CUST-")

    def test_import_message_field(self, client):
        """Import response includes a human-readable message."""
        uid = uuid.uuid4().hex[:8]
        csv_content = f"email,first_name\nmsg-{uid}@example.com,Msg\n"
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "imported" in data["message"].lower()

    def test_import_with_address_columns(self, client):
        """Import handles address columns correctly."""
        uid = uuid.uuid4().hex[:8]
        csv_content = (
            "email,first_name,billing_address_line1,billing_city,billing_state,billing_zip\n"
            f"addr-{uid}@example.com,Addr,100 Main St,Springfield,IL,62701\n"
        )
        response = client.post(
            f"{BASE_URL}/import",
            files={"file": ("customers.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["imported"] == 1

        # Verify address was saved
        search = client.get(f"{BASE_URL}/search", params={"q": f"addr-{uid}"})
        assert search.status_code == 200
        results = search.json()
        assert len(results) >= 1
        customer_id = results[0]["id"]

        detail = client.get(f"{BASE_URL}/{customer_id}")
        assert detail.status_code == 200
        assert detail.json()["billing_address_line1"] == "100 Main St"
        assert detail.json()["billing_city"] == "Springfield"
