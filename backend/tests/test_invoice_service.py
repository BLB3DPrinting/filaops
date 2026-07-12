"""Tests for invoice service and API endpoints."""
import uuid
from datetime import date, datetime, timedelta, timezone
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

    def test_create_invoice_uses_linked_customer_for_staff_order(self, db, make_product, make_sales_order):
        from app.models.user import User
        from app.services.invoice_service import create_invoice

        uid = uuid.uuid4().hex[:8]
        customer = User(
            email=f"invoice-customer-{uid}@example.com",
            password_hash="test-hash",
            first_name="Invoice",
            last_name="Customer",
            company_name="Invoice Customer Co",
            account_type="customer",
            payment_terms="net30",
            billing_address_line1="123 Billing Way",
            billing_city="Billingtown",
            billing_state="IN",
            billing_zip="46204",
        )
        db.add(customer)
        db.flush()

        product = make_product(selling_price=Decimal("25.00"))
        so = make_sales_order(
            user_id=1,
            customer_id=customer.id,
            customer_name="Order Snapshot Name",
            customer_email="snapshot@example.com",
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("25.00"),
            status="confirmed",
        )

        invoice = create_invoice(db, so.id)

        assert invoice.customer_id == customer.id
        assert invoice.customer_name == "Order Snapshot Name"
        assert invoice.customer_email == "snapshot@example.com"
        assert invoice.customer_company == "Invoice Customer Co"
        assert invoice.bill_to_line1 == "123 Billing Way"
        assert invoice.bill_to_city == "Billingtown"
        assert invoice.payment_terms == "net30"

    def test_create_invoice_preserves_service_line_description(self, db, make_sales_order):
        from app.models.sales_order import SalesOrderLine
        from app.services.invoice_service import create_invoice

        so = make_sales_order(
            product_id=None,
            product_name="Manual Order",
            quantity=1,
            unit_price=Decimal("250.00"),
            status="confirmed",
        )
        db.add(SalesOrderLine(
            sales_order_id=so.id,
            line_type="service",
            description="Engineering Fee",
            quantity=Decimal("1.00"),
            unit_price=Decimal("250.00"),
            total=Decimal("250.00"),
        ))
        db.flush()

        invoice = create_invoice(db, so.id)

        assert len(invoice.lines) == 1
        assert invoice.lines[0].description == "Engineering Fee"
        assert invoice.lines[0].product_id is None
        assert invoice.lines[0].line_total == Decimal("250.00")

    def test_create_invoice_uses_adjusted_order_line_total(self, db, make_sales_order):
        from app.models.sales_order import SalesOrderLine
        from app.services.invoice_service import create_invoice

        so = make_sales_order(
            product_id=None,
            product_name="Manual Order",
            quantity=1,
            unit_price=Decimal("90.00"),
            status="confirmed",
        )
        db.add(SalesOrderLine(
            sales_order_id=so.id,
            line_type="service",
            description="Discounted Engineering",
            quantity=Decimal("2.00"),
            unit_price=Decimal("50.00"),
            discount=Decimal("10.00"),
            total=Decimal("90.00"),
        ))
        db.flush()

        invoice = create_invoice(db, so.id)

        assert invoice.lines[0].line_total == Decimal("90.00")
        assert invoice.lines[0].discount_percent is None
        assert invoice.subtotal == Decimal("90.00")
        assert invoice.total == Decimal("90.00")

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

    def test_create_invoice_reflects_existing_order_payment(
        self, db, make_product, make_sales_order
    ):
        from app.models.payment import Payment
        from app.services.invoice_service import create_invoice

        product = make_product(selling_price=Decimal("50.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("50.00"),
            status="confirmed",
            payment_status="pending",
        )
        paid_at = datetime.now(timezone.utc)
        db.add(Payment(
            payment_number=f"PAY-EXISTING-{so.id}",
            sales_order_id=so.id,
            amount=Decimal("50.00"),
            payment_method="cash",
            payment_type="payment",
            status="completed",
            transaction_id="cash-50",
            payment_date=paid_at,
        ))
        db.flush()

        invoice = create_invoice(db, so.id)
        db.refresh(so)

        assert invoice.amount_paid == Decimal("50.00")
        assert invoice.status == "paid"
        assert invoice.paid_at is not None
        assert invoice.payment_method == "cash"
        assert invoice.payment_reference == "cash-50"
        assert so.payment_status == "paid"

    def test_create_invoice_reflects_existing_partial_order_payment(
        self, db, make_product, make_sales_order
    ):
        from app.models.payment import Payment
        from app.services.invoice_service import create_invoice

        product = make_product(selling_price=Decimal("80.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("80.00"),
            status="confirmed",
            payment_status="pending",
        )
        db.add(Payment(
            payment_number=f"PAY-PARTIAL-{so.id}",
            sales_order_id=so.id,
            amount=Decimal("25.00"),
            payment_method="card",
            payment_type="payment",
            status="completed",
            transaction_id="txn-25",
            payment_date=datetime.now(timezone.utc),
        ))
        db.flush()

        invoice = create_invoice(db, so.id)
        db.refresh(so)

        assert invoice.amount_paid == Decimal("25.00")
        assert invoice.status == "draft"
        assert invoice.paid_at is None
        assert invoice.payment_method == "card"
        assert invoice.payment_reference == "txn-25"
        assert so.payment_status == "partial"


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

    def test_record_payment_writes_sales_order_payment_ledger(
        self, db, make_product, make_sales_order
    ):
        from app.models.payment import Payment
        from app.services.invoice_service import create_invoice, record_payment

        product = make_product(selling_price=Decimal("45.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("45.00"),
            status="confirmed",
            payment_status="pending",
        )
        invoice = create_invoice(db, so.id)

        record_payment(
            db, invoice.id, Decimal("45.00"), "card", reference="txn_invoice_123"
        )
        db.refresh(so)

        payment = db.query(Payment).filter(Payment.sales_order_id == so.id).one()
        assert payment.amount == Decimal("45.00")
        assert payment.payment_method == "card"
        assert payment.payment_type == "payment"
        assert payment.status == "completed"
        assert payment.transaction_id == "txn_invoice_123"
        assert payment.payment_number.startswith("PAY-")
        assert so.payment_status == "paid"
        assert so.paid_at is not None


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

    def test_list_invoices_filters_by_sales_order_id(
        self, client, db, make_product, make_sales_order
    ):
        product = make_product(selling_price=Decimal("30.00"))
        target_order = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("30.00"),
            status="confirmed",
        )
        other_order = make_sales_order(
            product_id=product.id,
            quantity=2,
            unit_price=Decimal("30.00"),
            status="confirmed",
        )

        target_response = client.post(
            "/api/v1/invoices", json={"sales_order_id": target_order.id}
        )
        other_response = client.post(
            "/api/v1/invoices", json={"sales_order_id": other_order.id}
        )
        assert target_response.status_code == 200
        assert other_response.status_code == 200

        response = client.get(f"/api/v1/invoices?sales_order_id={target_order.id}")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["sales_order_id"] == target_order.id
        assert data[0]["invoice_number"] == target_response.json()["invoice_number"]

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


# ============================================================================
# Void invoice (#894 PR-A)
# ============================================================================
#
# GL assertions are scoped to each invoice's own source_id, so they are
# delta-based by construction — the accumulated test DB's other rows never
# enter the query.


def _count_je(db, source_type, source_id):
    from app.models.accounting import GLJournalEntry

    return (
        db.query(GLJournalEntry)
        .filter(
            GLJournalEntry.source_type == source_type,
            GLJournalEntry.source_id == source_id,
        )
        .count()
    )


def _je_net_by_account(db, invoice_id):
    """Net (debit - credit) per account across the invoice + invoice_void JEs
    for this invoice. After a mirror void, every touched account nets to 0."""
    from decimal import Decimal as _D

    from sqlalchemy import func as _func

    from app.models.accounting import (
        GLAccount,
        GLJournalEntry,
        GLJournalEntryLine,
    )

    rows = (
        db.query(
            GLAccount.account_code,
            _func.coalesce(_func.sum(GLJournalEntryLine.debit_amount), 0),
            _func.coalesce(_func.sum(GLJournalEntryLine.credit_amount), 0),
        )
        .join(GLJournalEntryLine, GLJournalEntryLine.account_id == GLAccount.id)
        .join(
            GLJournalEntry,
            GLJournalEntry.id == GLJournalEntryLine.journal_entry_id,
        )
        .filter(
            GLJournalEntry.source_type.in_(["invoice", "invoice_void"]),
            GLJournalEntry.source_id == invoice_id,
        )
        .group_by(GLAccount.account_code)
        .all()
    )
    return {code: _D(str(dr)) - _D(str(cr)) for code, dr, cr in rows}


class TestVoidInvoice:
    """Service-level void behavior (guards + mirrored GL reversal)."""

    def test_void_posted_invoice_posts_mirror_reversal(
        self, db, make_product, make_sales_order
    ):
        from app.services.invoice_service import (
            create_invoice,
            mark_sent,
            void_invoice,
        )

        product = make_product(selling_price=Decimal("40.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("40.00"),
            status="confirmed",
        )
        invoice = create_invoice(db, so.id)
        mark_sent(db, invoice.id)  # posts DR 1100 AR / CR 4000 Revenue

        assert _count_je(db, "invoice", invoice.id) == 1
        assert _count_je(db, "invoice_void", invoice.id) == 0

        voided = void_invoice(
            db, invoice.id, reason="customer cancelled", voided_by_id=1
        )
        assert voided.status == "voided"
        assert voided.voided_at is not None
        assert voided.voided_by_id == 1
        assert voided.void_reason == "customer cancelled"

        # Exactly one reversal JE, and the pair nets every account to 0.
        assert _count_je(db, "invoice_void", invoice.id) == 1
        net = _je_net_by_account(db, invoice.id)
        assert net, "expected GL lines for a posted invoice"
        for code, value in net.items():
            assert value == Decimal("0"), (
                f"account {code} did not net to 0 across the void pair: {value}"
            )

    def test_void_draft_invoice_creates_no_je(
        self, db, make_product, make_sales_order
    ):
        from app.services.invoice_service import create_invoice, void_invoice

        product = make_product(selling_price=Decimal("15.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("15.00"),
            status="confirmed",
        )
        invoice = create_invoice(db, so.id)
        assert invoice.status == "draft"
        # A draft has never posted a receivable JE.
        assert _count_je(db, "invoice", invoice.id) == 0

        voided = void_invoice(db, invoice.id, reason="created in error", voided_by_id=1)
        assert voided.status == "voided"
        # Status-only void: no invoice JE and no reversal JE.
        assert _count_je(db, "invoice", invoice.id) == 0
        assert _count_je(db, "invoice_void", invoice.id) == 0

    def test_double_void_returns_400_and_single_reversal(
        self, db, make_product, make_sales_order
    ):
        from fastapi import HTTPException

        from app.services.invoice_service import (
            create_invoice,
            mark_sent,
            void_invoice,
        )

        product = make_product(selling_price=Decimal("22.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("22.00"),
            status="confirmed",
        )
        invoice = create_invoice(db, so.id)
        mark_sent(db, invoice.id)
        void_invoice(db, invoice.id, reason="first void", voided_by_id=1)
        assert _count_je(db, "invoice_void", invoice.id) == 1

        with pytest.raises(HTTPException) as exc_info:
            void_invoice(db, invoice.id, reason="second void", voided_by_id=1)
        assert exc_info.value.status_code == 400
        # Still exactly one reversal JE — no double reversal.
        assert _count_je(db, "invoice_void", invoice.id) == 1

    def test_void_with_completed_payment_returns_409(
        self, db, make_product, make_sales_order
    ):
        from fastapi import HTTPException

        from app.services.invoice_service import (
            create_invoice,
            record_payment,
            void_invoice,
        )

        product = make_product(selling_price=Decimal("60.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("60.00"),
            status="confirmed",
        )
        invoice = create_invoice(db, so.id)
        record_payment(db, invoice.id, Decimal("60.00"), "card")
        db.refresh(invoice)
        assert invoice.amount_paid == Decimal("60.00")

        with pytest.raises(HTTPException) as exc_info:
            void_invoice(db, invoice.id, reason="cannot void a paid invoice", voided_by_id=1)
        assert exc_info.value.status_code == 409

    def test_void_blank_reason_returns_422(self, db, make_product, make_sales_order):
        from fastapi import HTTPException

        from app.services.invoice_service import create_invoice, void_invoice

        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("10.00"),
            status="confirmed",
        )
        invoice = create_invoice(db, so.id)

        with pytest.raises(HTTPException) as exc_info:
            void_invoice(db, invoice.id, reason="   ", voided_by_id=1)
        assert exc_info.value.status_code == 422


class TestVoidInvoiceAPI:
    """Endpoint-level void behavior + PATCH status whitelist (#894 PR-A)."""

    def _make_invoice(self, client, make_product, make_sales_order, price="10.00"):
        product = make_product(selling_price=Decimal(price))
        so = make_sales_order(
            product_id=product.id,
            quantity=1,
            unit_price=Decimal(price),
            status="confirmed",
        )
        resp = client.post("/api/v1/invoices", json={"sales_order_id": so.id})
        assert resp.status_code == 200
        return resp.json()["id"]

    def test_void_endpoint_marks_voided(
        self, client, db, make_product, make_sales_order
    ):
        invoice_id = self._make_invoice(client, make_product, make_sales_order)
        # Send first so a receivable JE is posted, exercising the reversal path.
        assert client.post(f"/api/v1/invoices/{invoice_id}/send").status_code == 200

        resp = client.post(
            f"/api/v1/invoices/{invoice_id}/void",
            json={"reason": "duplicate invoice"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "voided"
        assert body["void_reason"] == "duplicate invoice"
        assert body["voided_at"] is not None
        # A mirror reversal JE was posted for this invoice.
        assert _count_je(db, "invoice_void", invoice_id) == 1

    def test_void_nonexistent_invoice_404(self, client):
        resp = client.post("/api/v1/invoices/999999/void", json={"reason": "x"})
        assert resp.status_code == 404

    def test_void_missing_reason_422(
        self, client, make_product, make_sales_order
    ):
        invoice_id = self._make_invoice(client, make_product, make_sales_order)
        resp = client.post(f"/api/v1/invoices/{invoice_id}/void", json={})
        assert resp.status_code == 422

    def test_void_empty_reason_422(
        self, client, make_product, make_sales_order
    ):
        invoice_id = self._make_invoice(client, make_product, make_sales_order)
        resp = client.post(
            f"/api/v1/invoices/{invoice_id}/void", json={"reason": ""}
        )
        assert resp.status_code == 422

    def test_patch_status_voided_rejected_422(
        self, client, make_product, make_sales_order
    ):
        invoice_id = self._make_invoice(client, make_product, make_sales_order)
        resp = client.patch(
            f"/api/v1/invoices/{invoice_id}", json={"status": "voided"}
        )
        assert resp.status_code == 422
        # The invoice must not have been forked to voided by the bypass.
        get_resp = client.get(f"/api/v1/invoices/{invoice_id}")
        assert get_resp.json()["status"] == "draft"

    def test_patch_status_paid_rejected_422(
        self, client, make_product, make_sales_order
    ):
        invoice_id = self._make_invoice(client, make_product, make_sales_order)
        resp = client.patch(
            f"/api/v1/invoices/{invoice_id}", json={"status": "paid"}
        )
        assert resp.status_code == 422

    def test_patch_status_sent_from_draft_ok_200(
        self, client, make_product, make_sales_order
    ):
        invoice_id = self._make_invoice(client, make_product, make_sales_order)
        resp = client.patch(
            f"/api/v1/invoices/{invoice_id}", json={"status": "sent"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"
        assert resp.json()["sent_at"] is not None

    def test_patch_status_sent_from_non_draft_rejected_422(
        self, client, make_product, make_sales_order
    ):
        invoice_id = self._make_invoice(client, make_product, make_sales_order)
        # Move to sent once (allowed) ...
        assert (
            client.patch(
                f"/api/v1/invoices/{invoice_id}", json={"status": "sent"}
            ).status_code
            == 200
        )
        # ... a second sent (from non-draft) is not a valid PATCH transition.
        resp = client.patch(
            f"/api/v1/invoices/{invoice_id}", json={"status": "sent"}
        )
        assert resp.status_code == 422
