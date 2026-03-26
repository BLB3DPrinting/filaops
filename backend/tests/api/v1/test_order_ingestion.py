"""Tests for external order ingestion — confirm, reject, source filter."""
from decimal import Decimal

import pytest


BASE_URL = "/api/v1/sales-orders"


class TestConfirmExternalOrder:
    def test_confirm_pending_confirmation(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="pending_confirmation",
            source="api",
            source_order_id="EXT-001",
        )
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/confirm")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "confirmed"
        assert data["confirmed_at"] is not None

    def test_confirm_wrong_status(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="draft",
        )
        db.flush()

        response = client.post(f"{BASE_URL}/{so.id}/confirm")
        assert response.status_code == 409

    def test_confirm_creates_notification(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="pending_confirmation",
            source="api",
        )
        db.flush()

        client.post(f"{BASE_URL}/{so.id}/confirm")

        # Check that a notification was created
        from app.models.notification import Notification
        notif = db.query(Notification).filter(
            Notification.sales_order_id == so.id
        ).first()
        assert notif is not None
        assert so.order_number in notif.thread_subject

    def test_confirm_not_found(self, client):
        response = client.post(f"{BASE_URL}/999999/confirm")
        assert response.status_code == 404


class TestRejectExternalOrder:
    def test_reject_pending_confirmation(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="pending_confirmation",
            source="api",
        )
        db.flush()

        response = client.post(
            f"{BASE_URL}/{so.id}/reject",
            json={"reason": "Customer credit limit exceeded"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "cancelled"
        assert data["cancellation_reason"] == "Customer credit limit exceeded"

    def test_reject_wrong_status(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="confirmed",
        )
        db.flush()

        response = client.post(
            f"{BASE_URL}/{so.id}/reject",
            json={"reason": "Test reason"},
        )
        assert response.status_code == 409


class TestSourceFilter:
    def test_filter_by_source(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            source="api",
        )
        make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            source="manual",
        )
        db.flush()

        response = client.get(f"{BASE_URL}?source=api")
        assert response.status_code == 200
        orders = response.json()
        assert len(orders) > 0, "Expected at least one order with source=api"
        for order in orders:
            assert order.get("source") == "api"

    def test_filter_pending_confirmation_status(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="pending_confirmation",
            source="api",
        )
        db.flush()

        response = client.get(f"{BASE_URL}?status=pending_confirmation")
        assert response.status_code == 200
        orders = response.json()
        assert len(orders) >= 1
        assert all(o["status"] == "pending_confirmation" for o in orders)
