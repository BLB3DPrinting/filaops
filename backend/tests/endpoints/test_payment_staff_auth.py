"""SEC-405: payment routes are staff-only.

Anyone can self-register a customer account, so a plain login must not be
able to record, refund, void or edit payments, or read anyone's payment
history. Every route should answer 403 for a customer before it touches
the order, the payment rows or the general ledger. Operators keep the
access they had (RecordPaymentModal on the order page).
"""
import uuid
from decimal import Decimal

import pytest

from app.core.security import create_access_token
from app.models.accounting import GLJournalEntry
from app.models.payment import Payment
from app.models.sales_order import SalesOrder
from app.models.user import User

BASE = "/api/v1/payments"


def _user(db, account_type):
    """Create an active user and return (user, bearer headers)."""
    user = User(
        email=f"pay-{account_type}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        account_type=account_type,
        status="active",
    )
    db.add(user)
    db.flush()
    return user, {"Authorization": f"Bearer {create_access_token(user_id=user.id)}"}


def _seed_order_with_payment(db, make_sales_order, owner_id=1):
    """A $500 order with one completed $100 payment on it."""
    order = make_sales_order(
        quantity=10,
        unit_price=Decimal("50.00"),
        status="confirmed",
        payment_status="partial",
        user_id=owner_id,
    )
    payment = Payment(
        payment_number=f"PAY-AUTH-{uuid.uuid4().hex[:8]}",
        sales_order_id=order.id,
        amount=Decimal("100.00"),
        payment_method="cash",
        payment_type="payment",
        status="completed",
    )
    db.add(payment)
    db.flush()
    return order, payment


def _routes(order_id, payment_id):
    """(name, method, url, request kwargs) for all eight payment routes."""
    return [
        ("record", "post", BASE,
         {"json": {"sales_order_id": order_id, "amount": "400.00", "payment_method": "cash"}}),
        ("refund", "post", f"{BASE}/refund",
         {"json": {"sales_order_id": order_id, "amount": "100.00", "payment_method": "cash"}}),
        ("list", "get", BASE, {}),
        ("dashboard", "get", f"{BASE}/dashboard", {}),
        ("order_summary", "get", f"{BASE}/order/{order_id}/summary", {}),
        ("get", "get", f"{BASE}/{payment_id}", {}),
        ("update", "patch", f"{BASE}/{payment_id}", {"json": {"status": "voided", "notes": "x"}}),
        ("void", "delete", f"{BASE}/{payment_id}", {}),
    ]


@pytest.mark.parametrize("name,method,url,kwargs", _routes(1, 1))
def test_payment_routes_require_login(unauthed_client, name, method, url, kwargs):
    response = getattr(unauthed_client, method)(url, **kwargs)
    assert response.status_code == 401, f"{name}: {response.status_code}"


def test_customer_gets_403_on_every_payment_route(unauthed_client, db, make_sales_order):
    """Even on their own order, a customer cannot touch payments."""
    customer, headers = _user(db, "customer")
    order, payment = _seed_order_with_payment(db, make_sales_order, owner_id=customer.id)
    gl_entries_before = db.query(GLJournalEntry).count()

    for name, method, url, kwargs in _routes(order.id, payment.id):
        response = getattr(unauthed_client, method)(url, headers=headers, **kwargs)
        assert response.status_code == 403, f"{name}: {response.status_code} {response.text}"
        assert response.json()["detail"] == "Staff access required", name

    db.expire_all()
    rows = db.query(Payment).filter(Payment.sales_order_id == order.id).all()
    assert [p.id for p in rows] == [payment.id], "no payment or refund was recorded"
    stored = rows[0]
    assert stored.status == "completed", "payment was not voided or edited"
    assert stored.amount == Decimal("100.00")
    assert stored.notes is None
    assert db.get(SalesOrder, order.id).payment_status == "partial"
    assert db.query(GLJournalEntry).count() == gl_entries_before, "no GL entries were posted"


def test_operator_can_record_and_list_payments(unauthed_client, db, make_sales_order):
    """Operators keep recording payments from the order page."""
    operator, headers = _user(db, "operator")
    order, _ = _seed_order_with_payment(db, make_sales_order)

    recorded = unauthed_client.post(
        BASE,
        headers=headers,
        json={"sales_order_id": order.id, "amount": "50.00", "payment_method": "check"},
    )
    assert recorded.status_code == 201, recorded.text
    assert recorded.json()["sales_order_id"] == order.id

    listed = unauthed_client.get(BASE, headers=headers)
    assert listed.status_code == 200, listed.text

    summary = unauthed_client.get(f"{BASE}/order/{order.id}/summary", headers=headers)
    assert summary.status_code == 200, summary.text
