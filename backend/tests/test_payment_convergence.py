"""
Tests for PR-7: Convergent payment-recording paths.

Verifies that BOTH entry points (PATCH /api/v1/invoices/{id} and
POST /api/v1/payments) produce identical Payment attribution,
invoice status transitions (including partially_paid), GL entries,
and OrderEvents.
"""
import pytest
from decimal import Decimal

INV_URL = "/api/v1/invoices"
PAY_URL = "/api/v1/payments"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def confirmed_order(make_sales_order):
    """A confirmed sales order worth $200."""
    return make_sales_order(
        quantity=4,
        unit_price=Decimal("50.00"),
        status="confirmed",
        payment_status="pending",
    )


@pytest.fixture
def open_invoice(client, confirmed_order):
    """Invoice created for the confirmed order (via API)."""
    resp = client.post(INV_URL, json={"sales_order_id": confirmed_order.id})
    assert resp.status_code == 200, f"Invoice creation failed: {resp.text}"
    return resp.json()


# =============================================================================
# PATH A — PATCH /invoices/{id}  (Invoices page path)
# =============================================================================

class TestPathA_InvoicePatch:
    """Payments recorded through the invoice PATCH endpoint."""

    def test_partial_payment_sets_partially_paid(self, client, db, confirmed_order, open_invoice):
        """A partial PATCH payment sets invoice.status = 'partially_paid'."""
        invoice_id = open_invoice["id"]
        resp = client.patch(
            f"{INV_URL}/{invoice_id}",
            json={
                "amount_paid": 100.00,
                "payment_method": "credit_card",
                "payment_reference": "TXN-A001",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "partially_paid"
        assert float(data["amount_paid"]) == pytest.approx(100.00)

    def test_full_payment_sets_paid(self, client, db, confirmed_order, open_invoice):
        """A full PATCH payment sets invoice.status = 'paid'."""
        invoice_id = open_invoice["id"]
        resp = client.patch(
            f"{INV_URL}/{invoice_id}",
            json={
                "amount_paid": 200.00,
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "paid"

    def test_creates_payment_row_with_attribution(self, client, db, confirmed_order, open_invoice):
        """PATCH path creates a Payment row with recorded_by_id (user_id=1 from auth)."""
        from app.models.payment import Payment

        invoice_id = open_invoice["id"]
        resp = client.patch(
            f"{INV_URL}/{invoice_id}",
            json={"amount_paid": 50.00, "payment_method": "check"},
        )
        assert resp.status_code == 200, resp.text

        pay = (
            db.query(Payment)
            .filter(Payment.sales_order_id == confirmed_order.id)
            .order_by(Payment.id.desc())
            .first()
        )
        assert pay is not None, "No Payment row created"
        assert pay.recorded_by_id == 1  # seeded test user
        assert pay.payment_method == "check"
        assert float(pay.amount) == pytest.approx(50.00)
        assert pay.status == "completed"

    def test_creates_order_event(self, client, db, confirmed_order, open_invoice):
        """PATCH path records an OrderEvent on the order timeline."""
        from app.models.order_event import OrderEvent

        invoice_id = open_invoice["id"]
        client.patch(
            f"{INV_URL}/{invoice_id}",
            json={"amount_paid": 75.00, "payment_method": "online"},
        )

        event = (
            db.query(OrderEvent)
            .filter(
                OrderEvent.sales_order_id == confirmed_order.id,
                OrderEvent.event_type == "payment_received",
            )
            .first()
        )
        assert event is not None, "No OrderEvent created by PATCH path"

    def test_posts_gl_invoice_receivable(self, client, db, confirmed_order, open_invoice):
        """PATCH path posts the AR accrual GL entry (DR 1100 AR / CR 4000 Revenue)."""
        from app.models.accounting import GLJournalEntry

        invoice_id = open_invoice["id"]
        client.patch(
            f"{INV_URL}/{invoice_id}",
            json={"amount_paid": 100.00, "payment_method": "cash"},
        )

        # Invoice receivable entry: source_type="invoice", source_id=invoice_id
        entry = (
            db.query(GLJournalEntry)
            .filter(
                GLJournalEntry.source_type == "invoice",
                GLJournalEntry.source_id == invoice_id,
                GLJournalEntry.status != "voided",
            )
            .first()
        )
        assert entry is not None, "No invoice-receivable GL entry posted"

    def test_posts_gl_payment_receipt(self, client, db, confirmed_order, open_invoice):
        """PATCH path posts payment-receipt GL entry (DR 1000 Cash / CR 1100 AR)."""
        from app.models.payment import Payment
        from app.models.accounting import GLJournalEntry

        invoice_id = open_invoice["id"]
        client.patch(
            f"{INV_URL}/{invoice_id}",
            json={"amount_paid": 100.00, "payment_method": "cash"},
        )

        pay = (
            db.query(Payment)
            .filter(Payment.sales_order_id == confirmed_order.id)
            .first()
        )
        assert pay is not None

        receipt_entry = (
            db.query(GLJournalEntry)
            .filter(
                GLJournalEntry.source_type == "payment",
                GLJournalEntry.source_id == pay.id,
                GLJournalEntry.status != "voided",
            )
            .first()
        )
        assert receipt_entry is not None, "No payment-receipt GL entry posted"


# =============================================================================
# PATH B — POST /payments  (Payments / OrderDetail page path)
# =============================================================================

class TestPathB_PaymentsPost:
    """Payments recorded through the POST /payments endpoint."""

    def test_partial_payment_sets_invoice_partially_paid(self, client, db, confirmed_order, open_invoice):
        """POST /payments with partial amount sets linked invoice.status = 'partially_paid'."""
        from app.models.invoice import Invoice

        resp = client.post(
            PAY_URL,
            json={
                "sales_order_id": confirmed_order.id,
                "amount": 100.00,
                "payment_method": "credit_card",
            },
        )
        assert resp.status_code == 201, resp.text

        inv = db.query(Invoice).filter(Invoice.id == open_invoice["id"]).first()
        assert inv is not None
        assert inv.status == "partially_paid"
        assert float(inv.amount_paid) == pytest.approx(100.00)

    def test_full_payment_sets_invoice_paid(self, client, db, confirmed_order, open_invoice):
        """POST /payments with full amount sets linked invoice.status = 'paid'."""
        from app.models.invoice import Invoice

        resp = client.post(
            PAY_URL,
            json={
                "sales_order_id": confirmed_order.id,
                "amount": 200.00,
                "payment_method": "cash",
            },
        )
        assert resp.status_code == 201, resp.text

        inv = db.query(Invoice).filter(Invoice.id == open_invoice["id"]).first()
        assert inv is not None
        assert inv.status == "paid"

    def test_creates_payment_row_with_attribution(self, client, db, confirmed_order, open_invoice):
        """POST /payments creates a Payment with full attribution fields."""
        resp = client.post(
            PAY_URL,
            json={
                "sales_order_id": confirmed_order.id,
                "amount": 50.00,
                "payment_method": "check",
                "transaction_id": "TXN-B001",
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["recorded_by_name"] is not None  # set from current_user
        assert data["payment_method"] == "check"
        assert float(data["amount"]) == pytest.approx(50.00)

    def test_creates_order_event(self, client, db, confirmed_order, open_invoice):
        """POST /payments records an OrderEvent."""
        from app.models.order_event import OrderEvent

        client.post(
            PAY_URL,
            json={
                "sales_order_id": confirmed_order.id,
                "amount": 75.00,
                "payment_method": "online",
            },
        )

        event = (
            db.query(OrderEvent)
            .filter(
                OrderEvent.sales_order_id == confirmed_order.id,
                OrderEvent.event_type == "payment_received",
            )
            .first()
        )
        assert event is not None, "No OrderEvent created by POST /payments path"

    def test_posts_gl_invoice_receivable(self, client, db, confirmed_order, open_invoice):
        """POST /payments posts the AR accrual GL entry for the linked invoice."""
        from app.models.accounting import GLJournalEntry

        client.post(
            PAY_URL,
            json={
                "sales_order_id": confirmed_order.id,
                "amount": 100.00,
                "payment_method": "cash",
            },
        )

        entry = (
            db.query(GLJournalEntry)
            .filter(
                GLJournalEntry.source_type == "invoice",
                GLJournalEntry.source_id == open_invoice["id"],
                GLJournalEntry.status != "voided",
            )
            .first()
        )
        assert entry is not None, "No invoice-receivable GL entry posted by POST /payments"

    def test_posts_gl_payment_receipt(self, client, db, confirmed_order, open_invoice):
        """POST /payments posts the payment-receipt GL entry."""
        from app.models.accounting import GLJournalEntry

        resp = client.post(
            PAY_URL,
            json={
                "sales_order_id": confirmed_order.id,
                "amount": 100.00,
                "payment_method": "cash",
            },
        )
        payment_id = resp.json()["id"]

        entry = (
            db.query(GLJournalEntry)
            .filter(
                GLJournalEntry.source_type == "payment",
                GLJournalEntry.source_id == payment_id,
                GLJournalEntry.status != "voided",
            )
            .first()
        )
        assert entry is not None, "No payment-receipt GL entry posted"


# =============================================================================
# Convergence — both paths must produce identical state
# =============================================================================

class TestConvergence:
    """Verify the two entry points produce identical state for the same money."""

    def test_both_paths_produce_payment_row_with_attribution(self, client, db, make_sales_order):
        """After payment via each path a Payment row exists with non-NULL attribution."""
        from app.models.payment import Payment

        # Order A — paid via Invoices PATCH
        order_a = make_sales_order(quantity=1, unit_price=Decimal("100.00"), status="confirmed")
        inv_resp = client.post(INV_URL, json={"sales_order_id": order_a.id})
        invoice_id_a = inv_resp.json()["id"]
        client.patch(
            f"{INV_URL}/{invoice_id_a}",
            json={"amount_paid": 100.00, "payment_method": "credit_card"},
        )

        # Order B — paid via POST /payments
        order_b = make_sales_order(quantity=1, unit_price=Decimal("100.00"), status="confirmed")
        client.post(INV_URL, json={"sales_order_id": order_b.id})
        client.post(
            PAY_URL,
            json={"sales_order_id": order_b.id, "amount": 100.00, "payment_method": "credit_card"},
        )

        pay_a = db.query(Payment).filter(Payment.sales_order_id == order_a.id).first()
        pay_b = db.query(Payment).filter(Payment.sales_order_id == order_b.id).first()

        assert pay_a is not None, "Path A did not create a Payment row"
        assert pay_b is not None, "Path B did not create a Payment row"
        assert pay_a.recorded_by_id is not None, "Path A Payment.recorded_by_id is NULL"
        assert pay_b.recorded_by_id is not None, "Path B Payment.recorded_by_id is NULL"
        assert pay_a.payment_date is not None, "Path A Payment.payment_date is NULL"
        assert pay_b.payment_date is not None, "Path B Payment.payment_date is NULL"

    def test_both_paths_set_invoice_paid_for_full_payment(self, client, db, make_sales_order):
        """Full payment via either path sets invoice status to 'paid'."""
        from app.models.invoice import Invoice

        # Path A
        order_a = make_sales_order(quantity=1, unit_price=Decimal("50.00"), status="confirmed")
        inv_a = client.post(INV_URL, json={"sales_order_id": order_a.id}).json()
        client.patch(
            f"{INV_URL}/{inv_a['id']}",
            json={"amount_paid": 50.00, "payment_method": "cash"},
        )
        inv_a_db = db.query(Invoice).filter(Invoice.id == inv_a["id"]).first()
        assert inv_a_db.status == "paid", f"Path A: expected 'paid', got '{inv_a_db.status}'"

        # Path B
        order_b = make_sales_order(quantity=1, unit_price=Decimal("50.00"), status="confirmed")
        inv_b = client.post(INV_URL, json={"sales_order_id": order_b.id}).json()
        client.post(
            PAY_URL,
            json={"sales_order_id": order_b.id, "amount": 50.00, "payment_method": "cash"},
        )
        inv_b_db = db.query(Invoice).filter(Invoice.id == inv_b["id"]).first()
        assert inv_b_db.status == "paid", f"Path B: expected 'paid', got '{inv_b_db.status}'"

    def test_gl_idempotency_second_payment_does_not_duplicate_invoice_entry(
        self, client, db, confirmed_order, open_invoice
    ):
        """The invoice receivable GL entry is posted exactly once even after two payments."""
        from app.models.accounting import GLJournalEntry

        invoice_id = open_invoice["id"]
        # First payment — partial
        client.patch(
            f"{INV_URL}/{invoice_id}",
            json={"amount_paid": 100.00, "payment_method": "cash"},
        )
        # Second payment — brings to full
        client.patch(
            f"{INV_URL}/{invoice_id}",
            json={"amount_paid": 100.00, "payment_method": "cash"},
        )

        # Invoice receivable entry should exist exactly once (idempotent guard)
        count = (
            db.query(GLJournalEntry)
            .filter(
                GLJournalEntry.source_type == "invoice",
                GLJournalEntry.source_id == invoice_id,
                GLJournalEntry.status != "voided",
            )
            .count()
        )
        assert count == 1, f"Expected 1 invoice-receivable GL entry, found {count}"

    def test_both_paths_create_order_event(self, client, db, make_sales_order):
        """Both paths produce an OrderEvent on the order timeline."""
        from app.models.order_event import OrderEvent

        order = make_sales_order(quantity=1, unit_price=Decimal("100.00"), status="confirmed")
        inv = client.post(INV_URL, json={"sales_order_id": order.id}).json()

        # Path A
        client.patch(
            f"{INV_URL}/{inv['id']}",
            json={"amount_paid": 50.00, "payment_method": "check"},
        )
        events_a = (
            db.query(OrderEvent)
            .filter(
                OrderEvent.sales_order_id == order.id,
                OrderEvent.event_type == "payment_received",
            )
            .count()
        )
        assert events_a >= 1, "Path A did not create an OrderEvent"
