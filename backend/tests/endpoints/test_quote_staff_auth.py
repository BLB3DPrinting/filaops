"""SEC-404: staff quote routes need a staff account; customers keep the portal.

Anyone can self-register a customer account, so a plain login must not be
able to list, read, edit, approve, convert or delete quotes. The customer
routes the public Quoter and PRO call (portal accept/checkout, archive and
file download) stay reachable for the customer who owns the quote and for
nobody else.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models.quote import Quote, QuoteFile
from app.models.sales_order import SalesOrder
from app.models.user import User

BASE = "/api/v1/quotes"
IMAGE_BYTES = b"\x89PNG\r\n\x1a\noriginal-image"


def _user(db, account_type):
    """Create an active user and return (user, bearer headers)."""
    user = User(
        email=f"quote-{account_type}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        first_name=account_type.title(),
        last_name="Tester",
        account_type=account_type,
        status="active",
    )
    db.add(user)
    db.flush()
    return user, {"Authorization": f"Bearer {create_access_token(user_id=user.id)}"}


def _quote(db, *, user_id, customer_id=None, **overrides):
    values = {
        "user_id": user_id,
        "customer_id": customer_id,
        "quote_number": f"Q-AUTH-{uuid.uuid4().hex[:10]}",
        "product_name": "Staff Widget",
        "quantity": 1,
        "unit_price": Decimal("12.50"),
        "subtotal": Decimal("12.50"),
        "total_price": Decimal("12.50"),
        "status": "pending",
        "file_format": "manual",
        "file_size_bytes": 0,
        "admin_notes": "internal: margin is thin",
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
    }
    values.update(overrides)
    quote = Quote(**values)
    db.add(quote)
    db.flush()
    return quote


def _quote_file(db, quote_id):
    quote_file = QuoteFile(
        quote_id=quote_id,
        original_filename="owned-part.stl",
        stored_filename=f"stored-{uuid.uuid4().hex[:8]}.stl",
        file_path=str(Path(__file__)),
        file_size_bytes=123,
        file_format=".stl",
        mime_type="model/stl",
        file_hash="a" * 64,
    )
    db.add(quote_file)
    db.flush()
    return quote_file


def _staff_routes(quote_id, file_id=1):
    """(name, method, url, request kwargs) for the 15 staff-only quote routes."""
    upload = ("part.stl", b"solid test\nendsolid test\n", "model/stl")
    image = ("render.png", b"\x89PNG\r\n\x1a\nreplacement", "image/png")
    return [
        ("list", "get", f"{BASE}/", {}),
        ("stats", "get", f"{BASE}/stats", {}),
        ("get", "get", f"{BASE}/{quote_id}", {}),
        ("create", "post", f"{BASE}/",
         {"json": {"product_name": "Injected", "quantity": 1, "unit_price": "0.01",
                   "admin_notes": "seeded by a customer"}}),
        ("update", "patch", f"{BASE}/{quote_id}", {"json": {"product_name": "Hijacked", "unit_price": "0.01"}}),
        ("status", "patch", f"{BASE}/{quote_id}/status", {"json": {"status": "approved"}}),
        ("convert", "post", f"{BASE}/{quote_id}/convert", {}),
        ("image_upload", "post", f"{BASE}/{quote_id}/image", {"files": {"file": image}}),
        ("image_get", "get", f"{BASE}/{quote_id}/image", {}),
        ("image_delete", "delete", f"{BASE}/{quote_id}/image", {}),
        ("pdf", "get", f"{BASE}/{quote_id}/pdf", {}),
        ("create_item", "post", f"{BASE}/{quote_id}/create-item", {}),
        ("file_upload", "post", f"{BASE}/{quote_id}/files", {"files": {"file": upload}}),
        ("file_delete", "delete", f"{BASE}/{quote_id}/files/{file_id}", {}),
        ("delete", "delete", f"{BASE}/{quote_id}", {}),
    ]


def _shipping(**overrides):
    payload = {
        "shipping_name": "Jane Customer",
        "shipping_address_line1": "123 Print St",
        "shipping_city": "Indianapolis",
        "shipping_state": "IN",
        "shipping_zip": "46204",
        "shipping_country": "US",
        "shipping_rate_id": "rate_test",
        "shipping_carrier": "USPS",
        "shipping_service": "Ground Advantage",
        "shipping_cost": "8.50",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def public_quoter(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_PUBLIC_QUOTER", True)


@pytest.fixture
def checkout_calls(unauthed_client):
    """Stub the PRO payment provider on app.state and record who it was called for."""
    state = unauthed_client.app.state
    had_previous = hasattr(state, "payment_checkout_provider")
    previous = getattr(state, "payment_checkout_provider", None)
    calls = []

    def provider(*, db, quote, current_user):
        calls.append({"quote_id": quote.id, "user_id": current_user.id, "total": quote.total_price})
        return {"url": "https://checkout.example.test/session"}

    state.payment_checkout_provider = provider
    yield calls
    if had_previous:
        state.payment_checkout_provider = previous
    elif hasattr(state, "payment_checkout_provider"):
        delattr(state, "payment_checkout_provider")


# ---------------------------------------------------------------------------
# Staff routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name,method,url,kwargs", _staff_routes(1))
def test_staff_quote_routes_require_login(unauthed_client, name, method, url, kwargs):
    response = getattr(unauthed_client, method)(url, **kwargs)
    assert response.status_code == 401, f"{name}: {response.status_code}"


def test_customer_gets_403_on_every_staff_quote_route(unauthed_client, role_headers, db):
    """A customer can't read, create, edit, approve, convert or delete any quote."""
    admin = db.get(User, 1)
    quote = _quote(db, user_id=admin.id, image_data=IMAGE_BYTES,
                   image_filename="render.png", image_mime_type="image/png")
    quote_file = _quote_file(db, quote.id)
    quote_count = db.query(Quote).count()
    order_count = db.query(SalesOrder).count()
    file_count = db.query(QuoteFile).count()
    headers = role_headers("customer")

    for name, method, url, kwargs in _staff_routes(quote.id, quote_file.id):
        response = getattr(unauthed_client, method)(url, headers=headers, **kwargs)
        assert response.status_code == 403, f"{name}: {response.status_code} {response.text}"
        assert quote.quote_number not in response.text, name
        assert "margin is thin" not in response.text, name

    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored is not None, "delete did not go through"
    assert stored.status == "pending", "status change did not go through"
    assert stored.product_name == "Staff Widget"
    assert stored.unit_price == Decimal("12.50")
    assert stored.image_data == IMAGE_BYTES, "image was not replaced or deleted"
    assert stored.product_id is None, "create-item did not go through"
    assert stored.sales_order_id is None
    assert db.query(Quote).count() == quote_count, "no quote was created"
    assert db.query(SalesOrder).count() == order_count, "no order was created"
    assert db.query(QuoteFile).count() == file_count, "no file was added or removed"
    assert db.get(QuoteFile, quote_file.id) is not None


def test_self_registered_account_cannot_approve_convert_or_delete(
    unauthed_client, db, monkeypatch, public_quoter
):
    """The public register flow's token is refused on the reported routes, end to end."""
    from app.core.limiter import limiter

    monkeypatch.setattr(limiter, "enabled", False, raising=False)
    admin = db.get(User, 1)
    quote = _quote(db, user_id=admin.id)

    register = unauthed_client.post("/api/v1/auth/register", json={
        "email": f"quote-outsider-{uuid.uuid4().hex[:8]}@example.com",
        "password": "Outsider-Passw0rd!",
        "first_name": "Out",
        "last_name": "Sider",
    })
    assert register.status_code == 201, register.text
    token = register.json().get("access_token") or register.cookies.get("access_token")
    assert token, "register returned no token"
    headers = {"Authorization": f"Bearer {token}"}

    approve = unauthed_client.patch(f"{BASE}/{quote.id}/status", json={"status": "approved"}, headers=headers)
    convert = unauthed_client.post(f"{BASE}/{quote.id}/convert", headers=headers)
    delete = unauthed_client.delete(f"{BASE}/{quote.id}", headers=headers)

    assert approve.status_code == 403, approve.text
    assert convert.status_code == 403, convert.text
    assert delete.status_code == 403, delete.text
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored is not None
    assert stored.status == "pending"
    assert stored.sales_order_id is None


def test_operator_can_list_and_approve_quotes(unauthed_client, role_headers, db):
    """Operators are staff: the quote screens keep working for them."""
    admin = db.get(User, 1)
    quote = _quote(db, user_id=admin.id)
    headers = role_headers("operator")

    listed = unauthed_client.get(f"{BASE}/", headers=headers)
    assert listed.status_code == 200, listed.text
    assert quote.id in [q["id"] for q in listed.json()]

    approved = unauthed_client.patch(f"{BASE}/{quote.id}/status", json={"status": "approved"}, headers=headers)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


# ---------------------------------------------------------------------------
# Customer routes: owner only
# ---------------------------------------------------------------------------

def _owned_portal_quote(db, owner):
    """A quote customer A created through POST /quotes/portal and PRO approved."""
    return _quote(
        db,
        user_id=owner.id,
        customer_id=owner.id,
        status="approved",
        approval_method="auto",
        auto_approved=True,
        file_format=".stl",
        file_size_bytes=123,
        admin_notes=None,
    )


def test_owner_can_accept_and_checkout(unauthed_client, db, public_quoter, checkout_calls):
    owner, owner_headers = _user(db, "customer")
    quote = _owned_portal_quote(db, owner)

    accept = unauthed_client.post(f"{BASE}/portal/{quote.id}/accept", json=_shipping(), headers=owner_headers)
    assert accept.status_code == 200, accept.text
    assert accept.json()["status"] == "approved"

    checkout = unauthed_client.post(f"{BASE}/portal/{quote.id}/checkout", headers=owner_headers)
    assert checkout.status_code == 200, checkout.text
    assert checkout.json() == {"url": "https://checkout.example.test/session"}
    assert [(c["quote_id"], c["user_id"]) for c in checkout_calls] == [(quote.id, owner.id)]


def test_other_customer_cannot_touch_owned_quote(unauthed_client, db, public_quoter, checkout_calls):
    owner, _owner_headers = _user(db, "customer")
    _other, other_headers = _user(db, "customer")
    quote = _owned_portal_quote(db, owner)
    quote_file = _quote_file(db, quote.id)
    db.commit()

    responses = {
        "accept": unauthed_client.post(
            f"{BASE}/portal/{quote.id}/accept",
            json=_shipping(shipping_cost="0.00", adjusted_unit_price="0.01"),
            headers=other_headers,
        ),
        "checkout": unauthed_client.post(f"{BASE}/portal/{quote.id}/checkout", headers=other_headers),
        "archive": unauthed_client.get(f"{BASE}/{quote.id}/archive", headers=other_headers),
        "files": unauthed_client.get(f"{BASE}/{quote.id}/files", headers=other_headers),
        "download": unauthed_client.get(
            f"{BASE}/{quote.id}/files/{quote_file.id}/download", headers=other_headers
        ),
    }
    for name, response in responses.items():
        assert response.status_code == 403, f"{name}: {response.status_code} {response.text}"
        assert response.json()["detail"] == "Quote does not belong to current customer", name

    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.status == "approved"
    assert stored.unit_price == Decimal("12.50")
    assert stored.total_price == Decimal("12.50")
    assert stored.shipping_cost is None
    assert stored.shipping_address_line1 is None
    assert checkout_calls == [], "the payment provider was never called for another customer"


def test_archive_hides_admin_notes_from_the_owner_but_not_from_staff(unauthed_client, db):
    owner, owner_headers = _user(db, "customer")
    _operator, operator_headers = _user(db, "operator")
    quote = _owned_portal_quote(db, owner)
    quote.admin_notes = "internal: customer asked twice"
    quote.customer_notes = "Please pack carefully"
    db.commit()

    as_owner = unauthed_client.get(f"{BASE}/{quote.id}/archive", headers=owner_headers)
    assert as_owner.status_code == 200, as_owner.text
    owner_view = as_owner.json()["quote"]
    assert owner_view["id"] == quote.id
    assert owner_view["admin_notes"] is None
    assert owner_view["customer_notes"] == "Please pack carefully"
    assert "customer asked twice" not in as_owner.text

    as_staff = unauthed_client.get(f"{BASE}/{quote.id}/archive", headers=operator_headers)
    assert as_staff.status_code == 200, as_staff.text
    assert as_staff.json()["quote"]["admin_notes"] == "internal: customer asked twice"

    db.expire_all()
    assert db.get(Quote, quote.id).admin_notes == "internal: customer asked twice"
