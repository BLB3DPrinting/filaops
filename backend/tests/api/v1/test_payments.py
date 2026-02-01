"""
Tests for Payment API endpoints (app/api/v1/endpoints/payments.py)

SENTINEL-002: Payment endpoints had ZERO test coverage.

Covers:
- POST   /api/v1/payments          (record payment)
- POST   /api/v1/payments/refund   (record refund)
- GET    /api/v1/payments          (list payments)
- GET    /api/v1/payments/dashboard (dashboard stats)
- GET    /api/v1/payments/order/{order_id}/summary
- GET    /api/v1/payments/{payment_id}
- PATCH  /api/v1/payments/{payment_id}
- DELETE /api/v1/payments/{payment_id}  (void)
"""
import pytest
from decimal import Decimal

BASE_URL = "/api/v1/payments"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def test_order(make_sales_order):
    """Create a confirmed sales order worth $500."""
    return make_sales_order(
        quantity=10,
        unit_price=Decimal("50.00"),
        status="confirmed",
        payment_status="pending",
    )


@pytest.fixture
def test_payment(client, test_order):
    """Record a $100 payment and return the response data."""
    resp = client.post(
        BASE_URL,
        json={
            "sales_order_id": test_order.id,
            "amount": "100.00",
            "payment_method": "credit_card",
            "notes": "Test payment",
        },
    )
    assert resp.status_code == 201, f"Payment fixture failed: {resp.text}"
    return resp.json()


# =============================================================================
# POST /api/v1/payments (Record Payment)
# =============================================================================

class TestRecordPayment:

    def test_record_payment_success(self, client, test_order):
        resp = client.post(
            BASE_URL,
            json={
                "sales_order_id": test_order.id,
                "amount": "150.00",
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["sales_order_id"] == test_order.id
        assert Decimal(data["amount"]) == Decimal("150.00")
        assert data["payment_method"] == "cash"
        assert data["payment_type"] == "payment"
        assert data["status"] == "completed"
        assert data["payment_number"].startswith("PAY-")

    def test_record_payment_with_all_fields(self, client, test_order):
        resp = client.post(
            BASE_URL,
            json={
                "sales_order_id": test_order.id,
                "amount": "200.00",
                "payment_method": "check",
                "check_number": "1234",
                "transaction_id": "TXN-ABC-123",
                "notes": "Full payment with check",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["check_number"] == "1234"
        assert data["transaction_id"] == "TXN-ABC-123"
        assert data["notes"] == "Full payment with check"

    def test_record_payment_nonexistent_order(self, client):
        resp = client.post(
            BASE_URL,
            json={
                "sales_order_id": 999999,
                "amount": "100.00",
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 404

    def test_record_payment_zero_amount(self, client, test_order):
        resp = client.post(
            BASE_URL,
            json={
                "sales_order_id": test_order.id,
                "amount": "0",
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 422

    def test_record_payment_negative_amount(self, client, test_order):
        resp = client.post(
            BASE_URL,
            json={
                "sales_order_id": test_order.id,
                "amount": "-50.00",
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 422

    def test_record_payment_unauthorized(self, unauthed_client):
        resp = unauthed_client.post(
            BASE_URL,
            json={
                "sales_order_id": 1,
                "amount": "100.00",
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 401

    def test_record_payment_missing_required_fields(self, client):
        resp = client.post(BASE_URL, json={})
        assert resp.status_code == 422


# =============================================================================
# POST /api/v1/payments/refund (Record Refund)
# =============================================================================

class TestRecordRefund:

    def test_record_refund_success(self, client, test_order, test_payment):
        resp = client.post(
            f"{BASE_URL}/refund",
            json={
                "sales_order_id": test_order.id,
                "amount": "50.00",
                "payment_method": "credit_card",
                "notes": "Partial refund",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["payment_type"] == "refund"
        assert Decimal(data["amount"]) < 0  # stored as negative

    def test_record_refund_nonexistent_order(self, client):
        resp = client.post(
            f"{BASE_URL}/refund",
            json={
                "sales_order_id": 999999,
                "amount": "50.00",
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 404

    def test_record_refund_unauthorized(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/refund",
            json={
                "sales_order_id": 1,
                "amount": "50.00",
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/payments (List Payments)
# =============================================================================

class TestListPayments:

    def test_list_payments(self, client, test_payment):
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert data["total"] >= 1

    def test_list_payments_pagination(self, client, test_payment):
        resp = client.get(BASE_URL, params={"page": 1, "page_size": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 5
        assert data["page"] == 1
        assert data["page_size"] == 5

    def test_list_payments_filter_by_order(self, client, test_order, test_payment):
        resp = client.get(BASE_URL, params={"order_id": test_order.id})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for item in data["items"]:
            assert item["sales_order_id"] == test_order.id

    def test_list_payments_filter_by_method(self, client, test_payment):
        resp = client.get(BASE_URL, params={"payment_method": "credit_card"})
        assert resp.status_code == 200

    def test_list_payments_unauthorized(self, unauthed_client):
        resp = unauthed_client.get(BASE_URL)
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/payments/dashboard
# =============================================================================

class TestPaymentDashboard:

    def test_dashboard_returns_stats(self, client, test_payment):
        resp = client.get(f"{BASE_URL}/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "payments_today" in data
        assert "amount_today" in data
        assert "payments_this_week" in data
        assert "payments_this_month" in data
        assert "orders_with_balance" in data
        assert "by_method" in data

    def test_dashboard_unauthorized(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/dashboard")
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/payments/order/{order_id}/summary
# =============================================================================

class TestOrderPaymentSummary:

    def test_order_summary(self, client, test_order, test_payment):
        resp = client.get(f"{BASE_URL}/order/{test_order.id}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "order_total" in data
        assert "total_paid" in data
        assert "total_refunded" in data
        assert "balance_due" in data
        assert "payment_count" in data
        assert Decimal(data["total_paid"]) == Decimal("100.00")
        assert data["payment_count"] >= 1

    def test_order_summary_nonexistent(self, client):
        resp = client.get(f"{BASE_URL}/order/999999/summary")
        assert resp.status_code == 404

    def test_order_summary_unauthorized(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/order/1/summary")
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/payments/{payment_id}
# =============================================================================

class TestGetPayment:

    def test_get_payment_by_id(self, client, test_payment):
        payment_id = test_payment["id"]
        resp = client.get(f"{BASE_URL}/{payment_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == payment_id
        assert data["payment_number"] == test_payment["payment_number"]

    def test_get_payment_not_found(self, client):
        resp = client.get(f"{BASE_URL}/999999")
        assert resp.status_code == 404

    def test_get_payment_unauthorized(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1")
        assert resp.status_code == 401


# =============================================================================
# PATCH /api/v1/payments/{payment_id}
# =============================================================================

class TestUpdatePayment:

    def test_update_payment_notes(self, client, test_payment):
        payment_id = test_payment["id"]
        resp = client.patch(
            f"{BASE_URL}/{payment_id}",
            json={"notes": "Updated notes"},
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] == "Updated notes"

    def test_update_payment_status(self, client, test_payment):
        payment_id = test_payment["id"]
        resp = client.patch(
            f"{BASE_URL}/{payment_id}",
            json={"status": "voided"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "voided"

    def test_update_payment_not_found(self, client):
        resp = client.patch(f"{BASE_URL}/999999", json={"notes": "x"})
        assert resp.status_code == 404

    def test_update_payment_unauthorized(self, unauthed_client):
        resp = unauthed_client.patch(f"{BASE_URL}/1", json={"notes": "x"})
        assert resp.status_code == 401


# =============================================================================
# DELETE /api/v1/payments/{payment_id} (Void)
# =============================================================================

class TestVoidPayment:

    def test_void_payment_success(self, client, test_payment):
        payment_id = test_payment["id"]
        resp = client.delete(f"{BASE_URL}/{payment_id}")
        assert resp.status_code == 204

    def test_void_already_voided(self, client, test_payment):
        payment_id = test_payment["id"]
        client.delete(f"{BASE_URL}/{payment_id}")
        resp = client.delete(f"{BASE_URL}/{payment_id}")
        assert resp.status_code == 400

    def test_void_payment_not_found(self, client):
        resp = client.delete(f"{BASE_URL}/999999")
        assert resp.status_code == 404

    def test_void_payment_unauthorized(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE_URL}/1")
        assert resp.status_code == 401
