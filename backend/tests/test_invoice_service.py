"""Tests for invoice service and API endpoints."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.services.invoice_service import _calculate_due_date, _generate_invoice_number


# ============================================================================
# Pure function tests (no DB needed beyond session)
# ============================================================================


class TestCalculateDueDate:
    """Test due date calculation from payment terms."""

    def test_cod_returns_today(self):
        result = _calculate_due_date("cod")
        assert result == date.today()

    def test_prepay_returns_today(self):
        result = _calculate_due_date("prepay")
        assert result == date.today()

    def test_net15_returns_today_plus_15(self):
        result = _calculate_due_date("net15")
        assert result == date.today() + timedelta(days=15)

    def test_net30_returns_today_plus_30(self):
        result = _calculate_due_date("net30")
        assert result == date.today() + timedelta(days=30)

    def test_card_on_file_returns_today(self):
        result = _calculate_due_date("card_on_file")
        assert result == date.today()

    def test_unknown_terms_default_to_zero_days(self):
        result = _calculate_due_date("unknown_term")
        assert result == date.today()

    def test_custom_from_date(self):
        base = date(2026, 1, 1)
        result = _calculate_due_date("net30", from_date=base)
        assert result == date(2026, 1, 31)


class TestGenerateInvoiceNumber:
    """Test invoice number generation."""

    def test_returns_inv_yyyy_nnn_format(self, db):
        number = _generate_invoice_number(db)
        year = date.today().year
        assert number.startswith(f"INV-{year}-")
        # Sequence part should be zero-padded 3 digits
        seq = number.split("-")[-1]
        assert len(seq) >= 3


# ============================================================================
# Service-level tests (need DB)
# ============================================================================


class TestGetInvoice:
    """Test get_invoice error handling."""

    def test_nonexistent_invoice_returns_404(self, db):
        from fastapi import HTTPException
        from app.services.invoice_service import get_invoice

        with pytest.raises(HTTPException) as exc_info:
            get_invoice(db, 999999)
        assert exc_info.value.status_code == 404

    def test_get_invoice_summary(self, db):
        from app.services.invoice_service import get_invoice_summary

        result = get_invoice_summary(db)
        assert "overdue_count" in result
        assert "total_ar" in result


class TestCreateInvoice:
    """Test create_invoice error handling."""

    def test_nonexistent_order_returns_404(self, db):
        from fastapi import HTTPException
        from app.services.invoice_service import create_invoice

        with pytest.raises(HTTPException) as exc_info:
            create_invoice(db, 999999)
        assert exc_info.value.status_code == 404

    def test_draft_order_returns_400(self, db, make_sales_order):
        from fastapi import HTTPException
        from app.services.invoice_service import create_invoice

        so = make_sales_order(status="draft")
        with pytest.raises(HTTPException) as exc_info:
            create_invoice(db, so.id)
        assert exc_info.value.status_code == 400
        assert "draft" in exc_info.value.detail

    def test_create_invoice_from_confirmed_order(self, db, make_product, make_sales_order):
        from app.services.invoice_service import create_invoice

        product = make_product(selling_price=Decimal("25.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=2,
            unit_price=Decimal("25.00"),
            status="confirmed",
        )

        invoice = create_invoice(db, so.id)

        assert invoice.invoice_number.startswith("INV-")
        assert invoice.sales_order_id == so.id
        assert invoice.total == Decimal("50.00")
        assert invoice.status == "draft"
        assert len(invoice.lines) == 1
        assert invoice.lines[0].quantity == 2
        assert invoice.lines[0].unit_price == Decimal("25.00")

    def test_duplicate_invoice_returns_400(self, db, make_product, make_sales_order):
        from fastapi import HTTPException
        from app.services.invoice_service import create_invoice

        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="confirmed",
        )
        # First invoice succeeds
        create_invoice(db, so.id)
        # Second raises 400
        with pytest.raises(HTTPException) as exc_info:
            create_invoice(db, so.id)
        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail


class TestRecordPayment:
    """Test payment recording."""

    def test_record_payment_marks_paid(self, db, make_product, make_sales_order):
        from app.services.invoice_service import create_invoice, record_payment

        product = make_product(selling_price=Decimal("20.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("20.00"),
            status="confirmed",
        )
        invoice = create_invoice(db, so.id)

        updated = record_payment(db, invoice.id, Decimal("20.00"), "card")
        assert updated.status == "paid"
        assert updated.amount_paid == Decimal("20.00")
        assert updated.paid_at is not None


class TestMarkSent:
    """Test mark_sent transition."""

    def test_mark_sent_updates_status(self, db, make_product, make_sales_order):
        from app.services.invoice_service import create_invoice, mark_sent

        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="confirmed",
        )
        invoice = create_invoice(db, so.id)
        assert invoice.status == "draft"

        sent = mark_sent(db, invoice.id)
        assert sent.status == "sent"
        assert sent.sent_at is not None

    def test_mark_sent_non_draft_returns_400(self, db, make_product, make_sales_order):
        from fastapi import HTTPException
        from app.services.invoice_service import create_invoice, mark_sent, record_payment

        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="confirmed",
        )
        invoice = create_invoice(db, so.id)
        record_payment(db, invoice.id, Decimal("10.00"), "cash")

        with pytest.raises(HTTPException) as exc_info:
            mark_sent(db, invoice.id)
        assert exc_info.value.status_code == 400


# ============================================================================
# API endpoint tests
# ============================================================================


class TestInvoiceAPI:
    """Test invoice API endpoints."""

    def test_list_invoices_unauthorized(self, unauthed_client):
        response = unauthed_client.get("/api/v1/invoices")
        assert response.status_code == 401

    def test_list_invoices(self, client):
        response = client.get("/api/v1/invoices")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_invoice_not_found(self, client):
        response = client.get("/api/v1/invoices/999999")
        assert response.status_code == 404

    def test_invoice_summary(self, client):
        response = client.get("/api/v1/invoices/summary")
        assert response.status_code == 200
        data = response.json()
        assert "overdue_count" in data
        assert "total_ar" in data

    def test_create_invoice_nonexistent_order(self, client):
        response = client.post("/api/v1/invoices", json={"sales_order_id": 999999})
        assert response.status_code == 404

    def test_create_invoice_from_order(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("30.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=3,
            unit_price=Decimal("30.00"),
            status="confirmed",
        )

        response = client.post("/api/v1/invoices", json={"sales_order_id": so.id})
        assert response.status_code == 200
        data = response.json()
        assert data["invoice_number"].startswith("INV-")
        assert data["sales_order_id"] == so.id
        assert float(data["total"]) == 90.00
        assert data["status"] == "draft"
        assert len(data["lines"]) == 1

    def test_send_invoice(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="confirmed",
        )

        # Create
        resp = client.post("/api/v1/invoices", json={"sales_order_id": so.id})
        assert resp.status_code == 200
        invoice_id = resp.json()["id"]

        # Send
        resp = client.post(f"/api/v1/invoices/{invoice_id}/send")
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"
        assert resp.json()["sent_at"] is not None

    def test_send_nonexistent_invoice_404(self, client):
        resp = client.post("/api/v1/invoices/999999/send")
        assert resp.status_code == 404

    def test_patch_invoice_payment(self, client, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("50.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("50.00"),
            status="confirmed",
        )

        resp = client.post("/api/v1/invoices", json={"sales_order_id": so.id})
        invoice_id = resp.json()["id"]

        resp = client.patch(f"/api/v1/invoices/{invoice_id}", json={
            "amount_paid": "50.00",
            "payment_method": "card",
            "payment_reference": "ch_test123",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "paid"
        assert float(resp.json()["amount_paid"]) == 50.00
