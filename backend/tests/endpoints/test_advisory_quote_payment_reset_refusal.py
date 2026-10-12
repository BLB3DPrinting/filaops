"""GHSA-f9mr-93x7-cq5q: endpoint-level refusal for customer quote/payment access and
no-SMTP password reset. Self-contained (conftest fixtures + models only)."""
import uuid
from decimal import Decimal

import pytest

from app.core.security import create_access_token, hash_password
from app.models.payment import Payment
from app.models.quote import Quote
from app.models.user import PasswordResetRequest, User

QUOTES = "/api/v1/quotes"
PAYMENTS = "/api/v1/payments"
RESET = "/api/v1/auth/password-reset"


def _customer(db):
    user = User(
        email=f"a3-cust-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        account_type="customer",
        status="active",
    )
    db.add(user)
    db.flush()
    return user, {"Authorization": f"Bearer {create_access_token(user_id=user.id)}"}


def _victim_quote(db):
    """A quote owned by the admin (user 1), not by the attacking customer."""
    q = Quote(
        user_id=1,
        quote_number=f"Q-A3-{uuid.uuid4().hex[:10]}",
        product_name="Victim Widget",
        quantity=1,
        unit_price=Decimal("12.50"),
        subtotal=Decimal("12.50"),
        total_price=Decimal("12.50"),
        status="pending",
        file_format="manual",
        file_size_bytes=0,
        admin_notes="internal: secret margin note",
    )
    db.add(q)
    db.flush()
    return q


# ---------------------------------------------------------------- (a) quotes

def test_a_customer_cannot_read_foreign_quote(unauthed_client, db):
    _, headers = _customer(db)
    quote = _victim_quote(db)
    r = unauthed_client.get(f"{QUOTES}/{quote.id}", headers=headers)
    assert r.status_code == 403, f"read: {r.status_code} {r.text}"
    assert "secret margin note" not in r.text


def test_a_customer_cannot_approve_foreign_quote(unauthed_client, db):
    _, headers = _customer(db)
    quote = _victim_quote(db)
    r = unauthed_client.patch(
        f"{QUOTES}/{quote.id}/status", json={"status": "approved"}, headers=headers
    )
    assert r.status_code == 403, f"approve: {r.status_code} {r.text}"
    db.expire_all()
    assert db.get(Quote, quote.id).status == "pending"


def test_a_customer_cannot_delete_foreign_quote(unauthed_client, db):
    _, headers = _customer(db)
    quote = _victim_quote(db)
    r = unauthed_client.delete(f"{QUOTES}/{quote.id}", headers=headers)
    assert r.status_code == 403, f"delete: {r.status_code} {r.text}"
    db.expire_all()
    assert db.get(Quote, quote.id) is not None


# --------------------------------------------------------------- (b) payments

def _order_with_payment(db, make_sales_order, owner_id):
    order = make_sales_order(
        quantity=10, unit_price=Decimal("50.00"), status="confirmed",
        payment_status="partial", user_id=owner_id,
    )
    payment = Payment(
        payment_number=f"PAY-A3-{uuid.uuid4().hex[:8]}",
        sales_order_id=order.id,
        amount=Decimal("100.00"),
        payment_method="cash",
        payment_type="payment",
        status="completed",
    )
    db.add(payment)
    db.flush()
    return order, payment


def test_b_customer_cannot_record_payment(unauthed_client, db, make_sales_order):
    customer, headers = _customer(db)
    order, payment = _order_with_payment(db, make_sales_order, customer.id)
    r = unauthed_client.post(
        PAYMENTS, headers=headers,
        json={"sales_order_id": order.id, "amount": "400.00", "payment_method": "cash"},
    )
    assert r.status_code == 403, f"record: {r.status_code} {r.text}"
    db.expire_all()
    rows = db.query(Payment).filter(Payment.sales_order_id == order.id).all()
    assert [p.id for p in rows] == [payment.id], "a payment was recorded"


def test_b_customer_cannot_void_payment(unauthed_client, db, make_sales_order):
    customer, headers = _customer(db)
    order, payment = _order_with_payment(db, make_sales_order, customer.id)
    r = unauthed_client.delete(f"{PAYMENTS}/{payment.id}", headers=headers)
    assert r.status_code == 403, f"void: {r.status_code} {r.text}"
    db.expire_all()
    assert db.get(Payment, payment.id).status == "completed", "payment was voided"


# --------------------------------------------------- (c) no-SMTP password reset

@pytest.fixture
def no_smtp(monkeypatch):
    from app.core.config import settings
    from app.core.limiter import limiter

    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    monkeypatch.setattr(limiter, "enabled", False, raising=False)


def _walk(value):
    """Yield every key and string value in a JSON structure."""
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    elif value is not None:
        yield str(value)


def test_c_no_smtp_reset_request_returns_no_token_and_cannot_be_completed(
    unauthed_client, db, no_smtp
):
    old_hash = hash_password("OriginalPass123!")
    victim = User(
        email=f"a3-victim-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=old_hash,
        account_type="operator",
        status="active",
    )
    db.add(victim)
    db.flush()

    r = unauthed_client.post(f"{RESET}/request", json={"email": victim.email})
    assert r.status_code == 200, r.text

    # Body must carry no token/link, by key name or by value.
    body = r.json()
    strings = list(_walk(body))
    leaked_keys = [s for s in strings if "token" in s.lower() or s.lower().endswith("_url")]
    assert not leaked_keys, f"response exposes token/link fields: {body}"
    assert not any("reset-password" in s for s in strings), f"reset link in body: {body}"
    db.expire_all()
    rows = db.query(PasswordResetRequest).filter(PasswordResetRequest.user_id == victim.id).all()
    for row in rows:
        assert row.token not in r.text, "the reset token appears in the response"
        assert row.approval_token not in r.text

    # And the stored request must not be usable without admin approval.
    assert rows, "a request should be recorded for admin review"
    for row in rows:
        assert row.status == "pending", f"request auto-approved: {row.status}"
        done = unauthed_client.post(
            f"{RESET}/complete", json={"token": row.token, "new_password": "Hijacked-Pass123!"}
        )
        assert done.status_code == 400, f"complete without approval: {done.status_code} {done.text}"
    db.expire_all()
    assert db.get(User, victim.id).password_hash == old_hash, "password was changed"
