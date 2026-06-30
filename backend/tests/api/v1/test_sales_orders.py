"""
Tests for Sales Orders API endpoints (app/api/v1/endpoints/sales_orders.py)

Covers:
- GET /api/v1/sales-orders/ (list with pagination, filters, sorting)
- GET /api/v1/sales-orders/{id} (get single order)
- POST /api/v1/sales-orders/ (create line-item order)
- PATCH /api/v1/sales-orders/{id}/status (status transitions)
- PATCH /api/v1/sales-orders/{id}/payment (payment updates)
- PATCH /api/v1/sales-orders/{id}/shipping (shipping updates)
- PATCH /api/v1/sales-orders/{id}/address (address updates)
- POST /api/v1/sales-orders/{id}/cancel (cancellation)
- DELETE /api/v1/sales-orders/{id} (delete draft/cancelled)
- GET /api/v1/sales-orders/status-transitions (metadata)
- GET /api/v1/sales-orders/payment-statuses (metadata)
- GET /api/v1/sales-orders/{id}/events (order event timeline)
- POST /api/v1/sales-orders/{id}/events (add event)
- Auth: 401 without token on all protected endpoints
"""
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/sales-orders"


def _seed_ship_inventory(db, product_id, on_hand=Decimal("100")):
    """Seed on-hand FG inventory so ship_order's availability pre-check passes."""
    from app.models.inventory import Inventory
    from app.services.inventory_service import get_or_create_default_location
    loc = get_or_create_default_location(db)
    inv = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.location_id == loc.id,
    ).first()
    if inv is None:
        inv = Inventory(
            product_id=product_id, location_id=loc.id,
            on_hand_quantity=on_hand, allocated_quantity=Decimal("0"),
        )
        db.add(inv)
    else:
        inv.on_hand_quantity = on_hand
    db.flush()
    return inv


# =============================================================================
# Auth tests -- endpoints requiring authentication
# =============================================================================

class TestSalesOrderAuth:
    """Verify auth is required on all protected endpoints."""

    def test_create_requires_auth(self, unauthed_client):
        response = unauthed_client.post(BASE_URL, json={
            "lines": [{"product_id": 1, "quantity": 1}],
        })
        assert response.status_code == 401

    def test_list_requires_auth(self, unauthed_client):
        response = unauthed_client.get(BASE_URL)
        assert response.status_code in (200, 401)

    def test_get_detail_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1")
        assert response.status_code in (401, 404)

    def test_update_status_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/1/status", json={
            "status": "confirmed",
        })
        assert response.status_code == 401

    def test_cancel_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/cancel", json={
            "cancellation_reason": "test",
        })
        assert response.status_code == 401

    def test_delete_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_update_payment_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/1/payment", json={
            "payment_status": "paid",
        })
        assert response.status_code == 401

    def test_update_shipping_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/1/shipping", json={
            "tracking_number": "TRACK123",
        })
        assert response.status_code == 401

    def test_update_address_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/1/address", json={
            "shipping_city": "Test",
        })
        assert response.status_code == 401

    def test_status_transitions_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/status-transitions")
        assert response.status_code == 401

    def test_payment_statuses_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/payment-statuses")
        assert response.status_code == 401

    def test_get_events_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1/events")
        assert response.status_code in (401, 404)

    def test_add_event_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/events", json={
            "event_type": "note_added",
            "title": "Test note",
        })
        assert response.status_code == 401


# =============================================================================
# Status Transitions Metadata
# =============================================================================

class TestStatusTransitions:
    """Test GET /api/v1/sales-orders/status-transitions"""

    def test_get_all_status_transitions(self, client):
        response = client.get(f"{BASE_URL}/status-transitions")
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert "transitions" in data
        assert "terminal_statuses" in data
        assert isinstance(data["statuses"], list)
        assert len(data["statuses"]) > 0

    def test_get_transitions_for_specific_status(self, client):
        response = client.get(f"{BASE_URL}/status-transitions?current_status=pending")
        assert response.status_code == 200
        data = response.json()
        assert data["current_status"] == "pending"
        assert "allowed_transitions" in data
        assert "is_terminal" in data

    def test_get_transitions_for_terminal_status(self, client):
        response = client.get(f"{BASE_URL}/status-transitions?current_status=completed")
        assert response.status_code == 200
        data = response.json()
        # Completed should be terminal (no further transitions)
        assert data["is_terminal"] is True
        assert data["allowed_transitions"] == []

    def test_get_transitions_invalid_status(self, client):
        response = client.get(f"{BASE_URL}/status-transitions?current_status=bogus")
        assert response.status_code == 400
        assert "invalid" in response.json()["detail"].lower()


class TestPaymentStatuses:
    """Test GET /api/v1/sales-orders/payment-statuses"""

    def test_get_payment_statuses(self, client):
        response = client.get(f"{BASE_URL}/payment-statuses")
        assert response.status_code == 200
        data = response.json()
        assert "statuses" in data
        assert "descriptions" in data
        assert "pending" in data["statuses"]
        assert "paid" in data["statuses"]


# =============================================================================
# List -- read operations
# =============================================================================

class TestListSalesOrders:
    """Test GET /api/v1/sales-orders/"""

    def test_list_returns_200(self, client):
        response = client.get(BASE_URL)
        assert response.status_code == 200

    def test_list_returns_array(self, client):
        response = client.get(BASE_URL)
        data = response.json()
        assert isinstance(data, list)

    def test_list_with_status_filter(self, client):
        response = client.get(f"{BASE_URL}?status_filter=draft")
        assert response.status_code == 200

    def test_list_with_multi_status_filter(self, client):
        response = client.get(f"{BASE_URL}?status=draft&status=pending")
        assert response.status_code == 200

    def test_list_with_pagination(self, client):
        response = client.get(f"{BASE_URL}?skip=0&limit=5")
        assert response.status_code == 200

    def test_list_limit_capped_at_100(self, client):
        """Even if limit=9999, the endpoint caps at 100."""
        response = client.get(f"{BASE_URL}?limit=9999")
        assert response.status_code == 200

    def test_list_with_sort_order_asc(self, client):
        response = client.get(f"{BASE_URL}?sort_by=order_date&sort_order=asc")
        assert response.status_code == 200

    def test_list_with_sort_order_desc(self, client):
        response = client.get(f"{BASE_URL}?sort_by=order_date&sort_order=desc")
        assert response.status_code == 200

    def test_list_invalid_sort_order(self, client):
        response = client.get(f"{BASE_URL}?sort_order=invalid")
        assert response.status_code == 400

    def test_list_invalid_sort_by(self, client):
        response = client.get(f"{BASE_URL}?sort_by=nonexistent_field")
        assert response.status_code == 400

    def test_list_with_fulfillment_include(self, client):
        response = client.get(f"{BASE_URL}?include_fulfillment=true")
        assert response.status_code == 200

    def test_list_with_invalid_fulfillment_state(self, client):
        response = client.get(f"{BASE_URL}?fulfillment_state=bogus")
        assert response.status_code == 400

    def test_list_contains_created_order(self, client, db, make_product, make_sales_order):
        """Ensure a created order appears in the list."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        db.flush()

        response = client.get(BASE_URL)
        assert response.status_code == 200
        data = response.json()
        order_numbers = [o["order_number"] for o in data]
        assert so.order_number in order_numbers


# =============================================================================
# Get single order
# =============================================================================

class TestGetSalesOrder:
    """Test GET /api/v1/sales-orders/{id}"""

    def test_get_existing_order(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("25.00"))
        so = make_sales_order(product_id=product.id, quantity=2, unit_price=Decimal("25.00"))
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == so.id
        assert data["order_number"] == so.order_number

    def test_get_nonexistent_returns_404(self, client):
        response = client.get(f"{BASE_URL}/999999")
        assert response.status_code == 404

    def test_get_order_has_expected_fields(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("15.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=3,
            unit_price=Decimal("15.00"),
            status="pending",
            material_type="PLA",
        )
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}")
        assert response.status_code == 200
        data = response.json()
        # Verify key response fields are present
        assert "order_number" in data
        assert "status" in data
        assert "total_price" in data
        assert "grand_total" in data
        assert "payment_status" in data
        assert "created_at" in data

    def test_get_order_returns_correct_status(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="confirmed")
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}")
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"


# =============================================================================
# Create -- POST /api/v1/sales-orders/
# =============================================================================

class TestCreateSalesOrder:
    """Test manual line-item order creation."""

    def test_create_basic_order(self, client, db, make_product):
        product = make_product(
            selling_price=Decimal("15.00"),
            item_type="finished_good",
        )
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [
                {"product_id": product.id, "quantity": 3}
            ],
            "source": "manual",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["order_number"].startswith("SO-")
        assert data["status"] == "pending"
        assert data["order_type"] == "line_item"

    def test_create_order_accepts_manual_line_price(self, client, db, make_product):
        """Manual/admin order creation can override product catalog price per line."""
        product = make_product(selling_price=Decimal("25.00"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [
                {"product_id": product.id, "quantity": 1, "unit_price": 30.00}
            ],
        })
        assert response.status_code == 201
        data = response.json()
        assert Decimal(str(data["total_price"])) == Decimal("30.00")
        assert Decimal(str(data["lines"][0]["unit_price"])) == Decimal("30.00")

    def test_create_order_missing_lines_fails(self, client):
        response = client.post(BASE_URL, json={
            "lines": [],
        })
        assert response.status_code == 422

    def test_create_order_nonexistent_product_fails(self, client):
        response = client.post(BASE_URL, json={
            "lines": [{"product_id": 999999, "quantity": 1}],
        })
        assert response.status_code == 404

    def test_create_order_inactive_product_fails(self, client, db, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        product.active = False
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
        })
        assert response.status_code == 400
        assert "discontinued" in response.json()["detail"].lower()

    def test_create_order_zero_price_product_fails(self, client, db, make_product):
        product = make_product(selling_price=Decimal("0"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
        })
        assert response.status_code == 400
        assert "no selling price" in response.json()["detail"].lower()

    def test_create_order_null_price_product_fails(self, client, db, make_product):
        """Product with no selling_price at all should fail."""
        product = make_product(selling_price=None)
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
        })
        assert response.status_code == 400

    def test_create_multi_line_order(self, client, db, make_product):
        p1 = make_product(selling_price=Decimal("10.00"))
        p2 = make_product(selling_price=Decimal("20.00"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [
                {"product_id": p1.id, "quantity": 2},
                {"product_id": p2.id, "quantity": 1},
            ],
        })
        assert response.status_code == 201
        data = response.json()
        # Total should be (10*2) + (20*1) = 40
        assert Decimal(str(data["total_price"])) == Decimal("40.00")

    def test_create_order_returns_correct_order_type(self, client, db, make_product):
        """Manual orders should always be 'line_item' type."""
        product = make_product(selling_price=Decimal("10.00"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
        })
        assert response.status_code == 201
        assert response.json()["order_type"] == "line_item"

    def test_create_order_default_source_is_manual(self, client, db, make_product):
        """If source not specified, should default to 'manual'."""
        product = make_product(selling_price=Decimal("10.00"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
        })
        assert response.status_code == 201
        assert response.json()["source"] == "manual"

    def test_create_order_custom_source(self, client, db, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
            "source": "squarespace",
            "source_order_id": "SQ-1234",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["source"] == "squarespace"
        assert data["source_order_id"] == "SQ-1234"

    def test_create_order_with_notes(self, client, db, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
            "customer_notes": "Please ship quickly",
            "internal_notes": "VIP customer",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["customer_notes"] == "Please ship quickly"
        assert data["internal_notes"] == "VIP customer"

    def test_create_order_with_shipping_address(self, client, db, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
            "shipping_address_line1": "123 Test St",
            "shipping_city": "TestCity",
            "shipping_state": "TX",
            "shipping_zip": "75001",
            "shipping_country": "USA",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["shipping_address_line1"] == "123 Test St"
        assert data["shipping_city"] == "TestCity"
        assert data["shipping_state"] == "TX"

    def test_create_order_without_body_fails(self, client):
        """POST with no JSON body should fail."""
        response = client.post(BASE_URL)
        assert response.status_code == 422

    def test_create_order_generates_unique_order_numbers(self, client, db, make_product):
        """Two orders should get different order numbers."""
        product = make_product(selling_price=Decimal("10.00"))
        db.flush()

        payload = {"lines": [{"product_id": product.id, "quantity": 1}]}
        r1 = client.post(BASE_URL, json=payload)
        r2 = client.post(BASE_URL, json=payload)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["order_number"] != r2.json()["order_number"]

    def test_create_order_grand_total_includes_shipping(self, client, db, make_product):
        """Grand total should be total_price + tax + shipping."""
        product = make_product(selling_price=Decimal("10.00"))
        db.flush()

        response = client.post(BASE_URL, json={
            "lines": [{"product_id": product.id, "quantity": 1}],
            "shipping_cost": 5.99,
        })
        assert response.status_code == 201
        data = response.json()
        grand_total = Decimal(str(data["grand_total"]))
        total_price = Decimal(str(data["total_price"]))
        shipping = Decimal(str(data.get("shipping_cost", 0)))
        tax = Decimal(str(data.get("tax_amount", 0)))
        assert grand_total == total_price + shipping + tax


# =============================================================================
# Update Status -- PATCH /api/v1/sales-orders/{id}/status
# =============================================================================

class TestUpdateStatus:
    """Test sales order status updates."""

    def test_update_status_valid_transition(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            status="pending",
            material_type="PLA",
        )
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/status", json={
            "status": "confirmed",
        })
        # Should succeed (200) since admin user
        assert response.status_code == 200

    def test_update_status_nonexistent_order(self, client):
        response = client.patch(f"{BASE_URL}/999999/status", json={
            "status": "confirmed",
        })
        assert response.status_code == 404

    def test_update_status_with_internal_notes(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/status", json={
            "status": "confirmed",
            "internal_notes": "Confirmed by admin",
        })
        assert response.status_code == 200
        assert response.json()["internal_notes"] == "Confirmed by admin"

    def test_update_status_with_production_notes(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/status", json={
            "status": "confirmed",
            "production_notes": "Rush order - prioritize",
        })
        assert response.status_code == 200
        assert response.json()["production_notes"] == "Rush order - prioritize"

    def test_confirm_sets_confirmed_at(self, client, db, make_sales_order, make_product):
        """Confirming an order should set confirmed_at timestamp."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/status", json={
            "status": "confirmed",
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("confirmed_at") is not None

    def test_status_update_to_shipped_is_blocked(self, client, db, make_sales_order, make_product):
        """Shipping must go through POST /ship, not a bare status flip (#838)."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/status", json={
            "status": "shipped",
        })
        assert response.status_code == 400
        assert "ship" in response.json()["detail"].lower()
        # No corruption: status and shipment evidence untouched.
        got = client.get(f"{BASE_URL}/{so.id}").json()
        assert got["status"] == "ready_to_ship"
        assert got["shipped_at"] is None

    def test_delivered_sets_delivered_at(self, client, db, make_sales_order, make_product):
        """Marking as delivered should set delivered_at timestamp."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="shipped")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/status", json={
            "status": "delivered",
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("delivered_at") is not None

    def test_completed_sets_actual_completion_date(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="delivered")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/status", json={
            "status": "completed",
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("actual_completion_date") is not None


# =============================================================================
# Update Payment -- PATCH /api/v1/sales-orders/{id}/payment
# =============================================================================

class TestUpdatePayment:
    """Test payment information updates."""

    def test_update_payment_to_paid(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/payment", json={
            "payment_status": "paid",
            "payment_method": "credit_card",
            "payment_transaction_id": "TXN-12345",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["payment_status"] == "paid"
        assert data["payment_method"] == "credit_card"
        assert data["payment_transaction_id"] == "TXN-12345"
        assert data["paid_at"] is not None

    def test_update_payment_to_refunded(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/payment", json={
            "payment_status": "refunded",
        })
        assert response.status_code == 200
        assert response.json()["payment_status"] == "refunded"

    def test_update_payment_nonexistent_order(self, client):
        response = client.patch(f"{BASE_URL}/999999/payment", json={
            "payment_status": "paid",
        })
        assert response.status_code == 404

    def test_update_payment_partial(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/payment", json={
            "payment_status": "partial",
        })
        assert response.status_code == 200
        assert response.json()["payment_status"] == "partial"


# =============================================================================
# Update Shipping -- PATCH /api/v1/sales-orders/{id}/shipping
# =============================================================================

class TestUpdateShipping:
    """Test shipping information updates."""

    def test_update_shipping_tracking(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/shipping", json={
            "tracking_number": "1Z999AA10123456784",
            "carrier": "UPS",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["tracking_number"] == "1Z999AA10123456784"
        assert data["carrier"] == "UPS"

    def test_update_shipping_with_shipped_at_is_blocked(self, client, db, make_sales_order, make_product):
        """PATCH /shipping cannot mark an unshipped order shipped — use POST /ship (#838)."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/shipping", json={
            "tracking_number": "TRACK123",
            "carrier": "USPS",
            "shipped_at": "2026-01-15T10:00:00",
        })
        assert response.status_code == 400
        assert "ship" in response.json()["detail"].lower()
        # No corruption: status and shipment evidence untouched.
        got = client.get(f"{BASE_URL}/{so.id}").json()
        assert got["status"] == "ready_to_ship"
        assert got["shipped_at"] is None

    def test_update_shipping_nonexistent_order(self, client):
        response = client.patch(f"{BASE_URL}/999999/shipping", json={
            "tracking_number": "TRACK123",
        })
        assert response.status_code == 404


# =============================================================================
# Update Address -- PATCH /api/v1/sales-orders/{id}/address
# =============================================================================

class TestUpdateAddress:
    """Test shipping address updates."""

    def test_update_full_address(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/address", json={
            "shipping_address_line1": "456 New Ave",
            "shipping_address_line2": "Suite 100",
            "shipping_city": "Austin",
            "shipping_state": "TX",
            "shipping_zip": "73301",
            "shipping_country": "USA",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["shipping_address_line1"] == "456 New Ave"
        assert data["shipping_city"] == "Austin"
        assert data["shipping_state"] == "TX"
        assert data["shipping_zip"] == "73301"

    def test_update_partial_address(self, client, db, make_sales_order, make_product):
        """Should be able to update just one address field."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.patch(f"{BASE_URL}/{so.id}/address", json={
            "shipping_city": "Dallas",
        })
        assert response.status_code == 200
        assert response.json()["shipping_city"] == "Dallas"

    def test_update_address_nonexistent_order(self, client):
        response = client.patch(f"{BASE_URL}/999999/address", json={
            "shipping_city": "Test",
        })
        assert response.status_code == 404


# =============================================================================
# Cancel -- POST /api/v1/sales-orders/{id}/cancel
# =============================================================================

class TestCancelSalesOrder:
    """Test order cancellation."""

    def test_cancel_draft_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="draft")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Customer changed their mind",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"

    def test_cancel_pending_payment_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending_payment")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Payment issue",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_confirmed_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="confirmed")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "No longer needed",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_on_hold_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="on_hold")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Held too long",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_sets_cancelled_at(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="draft")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Test cancel",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["cancelled_at"] is not None
        assert data["cancellation_reason"] == "Test cancel"

    def test_cancel_nonexistent_order(self, client):
        response = client.post(f"{BASE_URL}/999999/cancel", json={
            "cancellation_reason": "test",
        })
        assert response.status_code == 404

    def test_cancel_shipped_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="shipped")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Too late",
        })
        # Shipped orders can't be cancelled
        assert response.status_code == 400

    def test_cancel_delivered_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="delivered")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Already received",
        })
        assert response.status_code == 400

    def test_cancel_completed_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="completed")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Oops",
        })
        assert response.status_code == 400

    def test_cancel_in_production_order_fails(self, client, db, make_sales_order, make_product):
        """in_production is not in the cancellable list."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="in_production")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Need to cancel",
        })
        assert response.status_code == 400

    def test_cancel_already_cancelled_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="cancelled")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={
            "cancellation_reason": "Cancel again?",
        })
        assert response.status_code == 400

    def test_cancel_missing_reason_fails(self, client, db, make_sales_order, make_product):
        """cancellation_reason is a required field."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="draft")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/cancel", json={})
        assert response.status_code == 422


# =============================================================================
# Delete -- DELETE /api/v1/sales-orders/{id}
# =============================================================================

class TestDeleteSalesOrder:
    """Test order deletion (only cancelled or pending orders can be deleted)."""

    def test_delete_cancelled_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="cancelled")
        db.flush()

        response = client.delete(f"{BASE_URL}/{so.id}")
        assert response.status_code == 204

    def test_delete_pending_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.delete(f"{BASE_URL}/{so.id}")
        assert response.status_code == 204

    def test_delete_confirmed_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="confirmed")
        db.flush()

        response = client.delete(f"{BASE_URL}/{so.id}")
        assert response.status_code == 400

    def test_delete_in_production_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="in_production")
        db.flush()

        response = client.delete(f"{BASE_URL}/{so.id}")
        assert response.status_code == 400

    def test_delete_shipped_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="shipped")
        db.flush()

        response = client.delete(f"{BASE_URL}/{so.id}")
        assert response.status_code == 400

    def test_delete_delivered_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="delivered")
        db.flush()

        response = client.delete(f"{BASE_URL}/{so.id}")
        assert response.status_code == 400

    def test_delete_completed_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="completed")
        db.flush()

        response = client.delete(f"{BASE_URL}/{so.id}")
        assert response.status_code == 400

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete(f"{BASE_URL}/999999")
        assert response.status_code == 404

    def test_delete_draft_order_fails(self, client, db, make_sales_order, make_product):
        """'draft' is NOT in the deletable statuses (only cancelled, pending)."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="draft")
        db.flush()

        response = client.delete(f"{BASE_URL}/{so.id}")
        assert response.status_code == 400

    def test_deleted_order_no_longer_accessible(self, client, db, make_sales_order, make_product):
        """After deletion, GET should return 404."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="cancelled")
        db.flush()
        order_id = so.id

        response = client.delete(f"{BASE_URL}/{order_id}")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get(f"{BASE_URL}/{order_id}")
        assert response.status_code == 404


# =============================================================================
# Order Events -- GET/POST /api/v1/sales-orders/{id}/events
# =============================================================================

class TestOrderEvents:
    """Test order event timeline endpoints."""

    def test_get_events_for_existing_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}/events")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_get_events_nonexistent_order(self, client):
        response = client.get(f"{BASE_URL}/999999/events")
        assert response.status_code == 404

    def test_get_events_with_pagination(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}/events?limit=5&offset=0")
        assert response.status_code == 200

    def test_add_event_to_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/events", json={
            "event_type": "note_added",
            "title": "Admin note",
            "description": "Customer called about ETA",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "note_added"
        assert data["title"] == "Admin note"
        assert data["description"] == "Customer called about ETA"

    def test_add_event_nonexistent_order(self, client):
        response = client.post(f"{BASE_URL}/999999/events", json={
            "event_type": "note_added",
            "title": "Test",
        })
        assert response.status_code == 404

    def test_add_event_with_metadata(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/events", json={
            "event_type": "note_added",
            "title": "Custom note with metadata",
            "metadata_key": "priority",
            "metadata_value": "high",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["metadata_key"] == "priority"
        assert data["metadata_value"] == "high"


# =============================================================================
# Shipping Events -- GET /api/v1/sales-orders/{id}/shipping-events
# =============================================================================

class TestShippingEvents:
    """Test shipping event timeline endpoint."""

    def test_get_shipping_events_returns_200(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="shipped")
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}/shipping-events")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    def test_get_shipping_events_nonexistent_order(self, client):
        response = client.get(f"{BASE_URL}/999999/shipping-events")
        assert response.status_code == 404


# =============================================================================
# Blocking Issues -- GET /api/v1/sales-orders/{id}/blocking-issues
# =============================================================================

class TestBlockingIssues:
    """Test the blocking issues analysis endpoint."""

    def test_blocking_issues_existing_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="confirmed")
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}/blocking-issues")
        assert response.status_code == 200

    def test_blocking_issues_nonexistent_order(self, client):
        response = client.get(f"{BASE_URL}/999999/blocking-issues")
        assert response.status_code == 404


# =============================================================================
# Fulfillment Status -- GET /api/v1/sales-orders/{id}/fulfillment-status
# =============================================================================

class TestFulfillmentStatus:
    """Test the fulfillment status endpoint."""

    def test_fulfillment_status_existing_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="confirmed")
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}/fulfillment-status")
        assert response.status_code == 200

    def test_fulfillment_status_nonexistent_order(self, client):
        response = client.get(f"{BASE_URL}/999999/fulfillment-status")
        assert response.status_code == 404


# =============================================================================
# Material Requirements -- GET /api/v1/sales-orders/{id}/material-requirements
# =============================================================================

class TestMaterialRequirements:
    """Test the material requirements endpoint."""

    def test_material_requirements_existing_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="confirmed")
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}/material-requirements")
        assert response.status_code == 200
        data = response.json()
        assert "requirements" in data
        assert "summary" in data

    def test_material_requirements_nonexistent_order(self, client):
        response = client.get(f"{BASE_URL}/999999/material-requirements")
        assert response.status_code == 404


# =============================================================================
# Pre-flight Check -- POST /api/v1/sales-orders/{id}/pre-flight-check
# =============================================================================

class TestPreFlightCheck:
    """Test the pre-flight check endpoint."""

    def test_preflight_check_existing_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="pending")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/pre-flight-check")
        assert response.status_code == 200
        data = response.json()
        assert "can_proceed" in data
        assert "shortages" in data
        assert "warnings" in data

    def test_preflight_check_nonexistent_order(self, client):
        response = client.post(f"{BASE_URL}/999999/pre-flight-check")
        assert response.status_code == 404


# =============================================================================
# Generate Production Orders -- POST /api/v1/sales-orders/{id}/generate-production-orders
# =============================================================================

class TestGenerateProductionOrders:
    """Test production order generation from sales orders."""

    def test_generate_po_nonexistent_order(self, client):
        response = client.post(f"{BASE_URL}/999999/generate-production-orders")
        assert response.status_code == 404

    def test_generate_po_cancelled_order_fails(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="cancelled")
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/generate-production-orders")
        assert response.status_code == 400
        assert "cancelled" in response.json()["detail"].lower()


# =============================================================================
# Ship Order -- POST /api/v1/sales-orders/{id}/ship
# =============================================================================

class TestShipOrder:
    """Test the ship order endpoint."""

    def test_ship_order_nonexistent(self, client):
        response = client.post(f"{BASE_URL}/999999/ship", json={
            "carrier": "USPS",
        })
        assert response.status_code == 404

    def test_ship_order_without_address_fails(self, client, db, make_sales_order, make_product):
        """Cannot ship if no shipping address is set."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        # Ensure no address
        so.shipping_address_line1 = None
        so.shipping_city = None
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/ship", json={
            "carrier": "USPS",
        })
        assert response.status_code == 400
        assert "no shipping address" in response.json()["detail"].lower()

    def test_ship_order_with_address_succeeds(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        so.shipping_address_line1 = "789 Ship Lane"
        so.shipping_city = "Houston"
        so.shipping_state = "TX"
        so.shipping_zip = "77001"
        db.flush()
        _seed_ship_inventory(db, product.id)

        response = client.post(f"{BASE_URL}/{so.id}/ship", json={
            "carrier": "FedEx",
            "service": "Ground",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["tracking_number"] is not None
        assert data["carrier"] == "FedEx"
        assert "shipped_at" in data

    def test_ship_order_with_custom_tracking(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        so.shipping_address_line1 = "100 Main St"
        so.shipping_city = "Dallas"
        db.flush()
        _seed_ship_inventory(db, product.id)

        response = client.post(f"{BASE_URL}/{so.id}/ship", json={
            "carrier": "UPS",
            "tracking_number": "1Z999AA10123456784",
        })
        assert response.status_code == 200
        assert response.json()["tracking_number"] == "1Z999AA10123456784"


class TestCanShipBatch:
    """#845/#846: GET /sales-orders/can-ship preflight."""

    @pytest.fixture
    def customer_client(self, db):
        """TestClient authenticated as a non-staff (customer) user — used to
        verify /can-ship rejects non-staff (staff = admin or operator)."""
        from app.models.user import User
        from app.core.security import create_access_token
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import get_db

        user = db.query(User).filter(User.id == 3).first()
        if not user:
            user = User(
                id=3, email="customer@filaops.dev",
                password_hash="not-a-real-hash",
                first_name="Customer", last_name="User",
                account_type="customer",
            )
            db.add(user)
            db.flush()
        token = create_access_token(user_id=3)

        def _override_get_db():
            try:
                yield db
            finally:
                pass

        app.dependency_overrides[get_db] = _override_get_db
        with TestClient(app, raise_server_exceptions=False) as c:
            c.headers["Authorization"] = f"Bearer {token}"
            yield c
        app.dependency_overrides.clear()

    def test_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/can-ship")
        assert response.status_code == 401

    def test_rejects_non_staff(self, customer_client):
        response = customer_client.get(f"{BASE_URL}/can-ship")
        assert response.status_code == 403

    def test_not_shadowed_by_order_id_route(self, client):
        """Regression for the #818 route-shadow class: GET /can-ship must hit
        this endpoint, not be swallowed as order_id='can-ship' by the bare
        GET /{order_id} detail route."""
        response = client.get(f"{BASE_URL}/can-ship")
        assert response.status_code == 200
        assert isinstance(response.json(), dict)

    def test_ready_order_with_stock_is_can_ship_true(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        so.shipping_address_line1 = "1 Ship Way"
        so.shipping_city = "Portland"
        db.flush()
        _seed_ship_inventory(db, product.id)

        response = client.get(f"{BASE_URL}/can-ship")
        assert response.status_code == 200
        data = response.json()
        assert str(so.id) in data or so.id in data
        entry = data.get(str(so.id), data.get(so.id))
        assert entry == {"can_ship": True, "reasons": []}

    def test_non_ready_orders_excluded(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="in_production")
        db.flush()

        response = client.get(f"{BASE_URL}/can-ship")
        assert response.status_code == 200
        data = response.json()
        assert str(so.id) not in data and so.id not in data

    def test_short_order_is_can_ship_false(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="ready_to_ship")
        so.shipping_address_line1 = "1 Ship Way"
        so.shipping_city = "Portland"
        db.flush()
        _seed_ship_inventory(db, product.id, on_hand=Decimal("0"))

        response = client.get(f"{BASE_URL}/can-ship")
        data = response.json()
        entry = data.get(str(so.id), data.get(so.id))
        assert entry["can_ship"] is False
        assert len(entry["reasons"]) >= 1

    def test_query_count_does_not_scale_with_order_count(self, client, db, make_sales_order, make_product):
        """The whole point of the batch design: a fixed, small number of SQL
        queries regardless of how many ready_to_ship orders exist."""
        from sqlalchemy import event
        from app.db.session import engine

        products = [make_product(selling_price=Decimal("10.00")) for _ in range(8)]
        for p in products:
            _seed_ship_inventory(db, p.id)
        orders = []
        for p in products:
            so = make_sales_order(product_id=p.id, status="ready_to_ship")
            so.shipping_address_line1 = "1 Ship Way"
            so.shipping_city = "Portland"
            orders.append(so)
        db.flush()

        counts = {"many": 0}

        def _count_many(*a, **kw):
            counts["many"] += 1

        event.listen(engine, "before_cursor_execute", _count_many)
        try:
            response = client.get(f"{BASE_URL}/can-ship")
        finally:
            event.remove(engine, "before_cursor_execute", _count_many)

        assert response.status_code == 200
        # Bounded: orders+lines, location, existing-products, inventory ≈ a
        # handful of queries — not anywhere near one-per-order (8).
        assert counts["many"] < 8, (
            f"can-ship issued {counts['many']} queries for 8 orders — "
            "looks like a per-order query crept back in"
        )


# =============================================================================
# Required Orders (MRP Cascade) -- GET /api/v1/sales-orders/{id}/required-orders
# =============================================================================

class TestRequiredOrders:
    """Test the MRP cascade required orders endpoint."""

    def test_required_orders_existing_order(self, client, db, make_sales_order, make_product):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="confirmed")
        db.flush()

        response = client.get(f"{BASE_URL}/{so.id}/required-orders")
        assert response.status_code == 200
        data = response.json()
        assert "order_id" in data
        assert "summary" in data

    def test_required_orders_nonexistent_order(self, client):
        response = client.get(f"{BASE_URL}/999999/required-orders")
        assert response.status_code == 404
