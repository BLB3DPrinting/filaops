"""SEC-412: portal accept can no longer re-price, revive or re-spec a quote.

POST /api/v1/quotes/portal/{id}/accept stays reachable for the customer who
created the quote (the public Quoter calls it before checkout). It used to
copy the client's unit price and total, revive rejected or expired quotes,
drop tax and the shop's shipping on shop-drafted quotes, overwrite the
server-side pricing snapshots and accept any colour slots. The honest Quoter
flows must keep working: accept on a quote that needs review (to save the
shipping choice), and accept again after a cancelled payment.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models.company_settings import CompanySettings
from app.models.quote import Quote, QuoteMaterial
from app.models.tax_rate import TaxRate
from app.models.user import User

BASE = "/api/v1/quotes"
ADMIN_HEADERS_USER_ID = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _customer(db):
    user = User(
        email=f"accept-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        first_name="Portal",
        last_name="Buyer",
        account_type="customer",
        status="active",
        shipping_address_line1="1 Old Road",
        shipping_city="Old Town",
        shipping_state="OH",
        shipping_zip="43004",
    )
    db.add(user)
    db.flush()
    return user


def _headers(user_id):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id)}"}


def _slicer_diagnostics(weights):
    """slicer_diagnostics as PRO stores it at enrichment."""
    multi = None
    if weights is not None:
        multi = {
            "is_multi_material": True,
            "material_count": sum(1 for grams in weights if grams > 0),
            "filament_weights_grams": weights,
        }
    return {
        "source": "filaops_pro.real_slicer",
        "input": {"filename": "lamp.3mf", "file_format": ".3mf"},
        "slice": {"estimation_method": "real", "multi_material": multi},
    }


def _portal_quote(db, owner, *, weights=(10.2, 9.1, 7.9), **overrides):
    """A quote the way POST /quotes/portal plus PRO enrichment leave it."""
    weights = list(weights) if weights is not None else None
    active_slots = sum(1 for grams in weights if grams > 0) if weights else 1
    values = {
        "user_id": owner.id,
        "customer_id": owner.id,
        "customer_email": owner.email,
        "customer_name": "Portal Buyer",
        "quote_number": f"Q-ACC-{uuid.uuid4().hex[:10]}",
        "product_name": "lamp.3mf",
        "quantity": 2,
        "material_type": "PLA_BASIC",
        "color": "JADE_WHITE",
        "unit_price": Decimal("12.50"),
        "subtotal": Decimal("25.00"),
        "total_price": Decimal("25.00"),
        "status": "approved",
        "approval_method": "auto",
        "auto_approved": True,
        "auto_approve_eligible": True,
        "file_format": ".3mf",
        "file_size_bytes": 1234,
        "expires_at": datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=90),
        "pricing_snapshot": {
            "source": "filaops_pro.quote_enrichment",
            "unit_price": "12.50",
            "total_price": "25.00",
            "active_material_slots": active_slots,
        },
        "slicer_diagnostics": _slicer_diagnostics(weights),
    }
    values.update(overrides)
    quote = Quote(**values)
    db.add(quote)
    db.flush()
    return quote


def _keep_material(db, quote):
    """An existing material row; a refused accept must leave it alone."""
    db.add(QuoteMaterial(
        quote_id=quote.id,
        slot_number=1,
        is_primary=True,
        material_type="PLA_BASIC",
        color_code="KEEP",
        color_name="Keep",
        color_hex="#123456",
        material_grams=Decimal("1.25"),
    ))
    db.flush()


def _materials(db, quote_id):
    return (
        db.query(QuoteMaterial)
        .filter(QuoteMaterial.quote_id == quote_id)
        .order_by(QuoteMaterial.slot_number)
        .all()
    )


def _slot(number, grams, code="RED"):
    return {
        "slot": number,
        "color_code": code,
        "color_name": code.title(),
        "color_hex": "#ff0000",
        "weight_grams": grams,
        "is_primary": False,
    }


def _payload(**overrides):
    """What QuoteResult.jsx sends."""
    payload = {
        "shipping_name": "Portal Buyer",
        "shipping_address_line1": "123 Print St",
        "shipping_address_line2": None,
        "shipping_city": "Indianapolis",
        "shipping_state": "IN",
        "shipping_zip": "46204",
        "shipping_country": "US",
        "shipping_phone": None,
        "shipping_rate_id": "rate_test",
        "shipping_carrier": "USPS",
        "shipping_service": "Ground Advantage",
        "shipping_cost": 8.5,
        "print_mode": None,
        "adjusted_unit_price": None,
        "multi_color_info": None,
        "shipping_snapshot": {"source": "quoter_accept", "carrier": "USPS", "cost": "8.50"},
    }
    payload.update(overrides)
    return payload


def _accept(client, quote, user, **overrides):
    return client.post(
        f"{BASE}/portal/{quote.id}/accept",
        json=_payload(**overrides),
        headers=_headers(user.id),
    )


def _assert_nothing_written(db, quote, owner, *, status, total=Decimal("25.00")):
    """Checked on the live session objects, so an unflushed write shows too."""
    assert quote.status == status
    assert quote.unit_price == Decimal("12.50")
    assert quote.subtotal == Decimal("25.00")
    assert quote.total_price == total
    assert quote.shipping_cost is None
    assert quote.shipping_address_line1 is None
    assert quote.shipping_rate_id is None
    assert quote.shipping_snapshot is None
    assert quote.color == "JADE_WHITE"
    assert [m.color_code for m in _materials(db, quote.id)] == ["KEEP"]
    assert owner.shipping_address_line1 == "1 Old Road"
    assert owner.shipping_state == "OH"


@pytest.fixture(autouse=True)
def public_quoter(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_PUBLIC_QUOTER", True)


@pytest.fixture
def checkout_calls(unauthed_client):
    """Stub PRO's payment provider on app.state; record the total it would charge."""
    state = unauthed_client.app.state
    had_previous = hasattr(state, "payment_checkout_provider")
    previous = getattr(state, "payment_checkout_provider", None)
    calls = []

    def provider(*, db, quote, current_user):
        calls.append({
            "quote_id": quote.id,
            "user_id": current_user.id,
            "total_price": Decimal(str(quote.total_price)),
        })
        return {"url": "https://checkout.example.test/session"}

    state.payment_checkout_provider = provider
    yield calls
    if had_previous:
        state.payment_checkout_provider = previous
    elif hasattr(state, "payment_checkout_provider"):
        delattr(state, "payment_checkout_provider")


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------

def test_lower_price_from_the_client_is_refused(unauthed_client, db):
    owner = _customer(db)
    quote = _portal_quote(db, owner)
    _keep_material(db, quote)

    response = _accept(unauthed_client, quote, owner, adjusted_unit_price="0.50", shipping_cost="0.00")

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Quote price changed; refresh the quote"
    _assert_nothing_written(db, quote, owner, status="approved")


@pytest.mark.parametrize("field", ["shipping_cost", "adjusted_unit_price"])
@pytest.mark.parametrize(
    "value",
    [1e30, "1E+30", "100000000.00", "8.505"],
    ids=["float_1e30", "string_1e30", "one_whole_digit_over", "third_decimal_place"],
)
def test_money_the_columns_cannot_hold_is_refused_with_422(unauthed_client, db, field, value):
    """shipping_cost and unit_price are Numeric(10, 2). A larger value used to
    reach the tax maths or Postgres and come back as a 500."""
    owner = _customer(db)
    quote = _portal_quote(db, owner)
    _keep_material(db, quote)

    response = _accept(unauthed_client, quote, owner, **{field: value})

    assert response.status_code == 422, response.text
    assert [e["field"] for e in response.json()["details"]["errors"]] == [field]
    _assert_nothing_written(db, quote, owner, status="approved")


def test_largest_column_value_is_still_a_valid_shipping_cost(unauthed_client, db):
    owner = _customer(db)
    quote = _portal_quote(
        db, owner, weights=None,
        unit_price=Decimal("0.00"), subtotal=Decimal("0.00"), total_price=Decimal("0.00"),
    )

    response = _accept(unauthed_client, quote, owner, shipping_cost="99999999.99")

    assert response.status_code == 200, response.text
    db.expire_all()
    assert db.get(Quote, quote.id).total_price == Decimal("99999999.99")


def test_shipping_that_would_overflow_the_total_is_refused_with_422(unauthed_client, db):
    """Each value fits its own column, but subtotal + shipping would not fit
    total_price (also Numeric(10, 2)). Refused before anything is written."""
    owner = _customer(db)
    quote = _portal_quote(db, owner)
    _keep_material(db, quote)

    response = _accept(unauthed_client, quote, owner, shipping_cost="99999999.99")

    assert response.status_code == 422, response.text
    assert response.json()["detail"] == "Shipping cost is too large"
    _assert_nothing_written(db, quote, owner, status="approved")


@pytest.mark.parametrize("sent_price", ["12.50", 12.5, "12.500"])
def test_unchanged_price_is_accepted(unauthed_client, db, sent_price):
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=None)

    response = _accept(unauthed_client, quote, owner, adjusted_unit_price=sent_price)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.unit_price == Decimal("12.50")
    assert stored.subtotal == Decimal("25.00")
    assert stored.total_price == Decimal("33.50")


# ---------------------------------------------------------------------------
# State and origin
# ---------------------------------------------------------------------------

_PAST = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)


@pytest.mark.parametrize(
    "overrides,detail",
    [
        ({"status": "rejected"}, "Quote can no longer be accepted"),
        ({"status": "cancelled"}, "Quote can no longer be accepted"),
        ({"status": "accepted"}, "Quote can no longer be accepted"),
        ({"status": "converted"}, "Quote can no longer be accepted"),
        ({"status": "calculating"}, "Quote can no longer be accepted"),
        ({"sales_order_id": 424242}, "Quote can no longer be accepted"),
        ({"expires_at": _PAST}, "Quote has expired"),
        ({"status": "pending", "approval_method": "manual", "expires_at": _PAST}, "Quote has expired"),
    ],
    ids=["rejected", "cancelled", "accepted", "converted", "calculating", "has_order",
         "expired", "expired_pending"],
)
def test_closed_or_expired_quote_is_refused(unauthed_client, db, overrides, detail):
    owner = _customer(db)
    quote = _portal_quote(db, owner, **overrides)
    _keep_material(db, quote)
    status_before = quote.status

    response = _accept(
        unauthed_client, quote, owner,
        print_mode="multi",
        multi_color_info={"primary_slot": 1, "slot_colors": [_slot(1, 10.2, "BLU")]},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == detail
    _assert_nothing_written(db, quote, owner, status=status_before)


def _shop_drafted_quote(unauthed_client, db, owner):
    """Staff draft a quote for the customer with a tax rate and shop shipping."""
    tax_rate = TaxRate(name="Test Sales Tax", rate=Decimal("0.0700"), is_default=False, is_active=True)
    db.add(tax_rate)
    db.flush()
    response = unauthed_client.post(
        f"{BASE}/",
        json={
            "product_name": "Shop bracket",
            "quantity": 2,
            "unit_price": "40.00",
            "customer_id": owner.id,
            "tax_rate_id": tax_rate.id,
            "shipping_cost": "15.00",
        },
        headers=_headers(ADMIN_HEADERS_USER_ID),
    )
    assert response.status_code == 201, response.text
    quote = db.get(Quote, response.json()["id"])
    assert quote.user_id == ADMIN_HEADERS_USER_ID
    assert quote.customer_id == owner.id
    assert quote.tax_amount > 0
    assert quote.total_price == quote.subtotal + quote.tax_amount + Decimal("15.00")
    return quote


def _snapshot(quote):
    return (quote.status, quote.total_price, quote.tax_amount, quote.shipping_cost,
            quote.shipping_address_line1)


def test_shop_drafted_quote_cannot_be_repriced_by_accept(unauthed_client, db, checkout_calls):
    owner = _customer(db)
    quote = _shop_drafted_quote(unauthed_client, db, owner)
    before = _snapshot(quote)

    response = _accept(unauthed_client, quote, owner, shipping_cost="0.00")

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "This quote was prepared by the shop and cannot be changed here"
    assert _snapshot(quote) == before
    assert owner.shipping_address_line1 == "1 Old Road"

    checkout = unauthed_client.post(f"{BASE}/portal/{quote.id}/checkout", headers=_headers(owner.id))
    assert checkout.status_code == 200, checkout.text
    assert checkout_calls == [{"quote_id": quote.id, "user_id": owner.id, "total_price": before[1]}]


def test_shop_approved_quote_goes_straight_to_checkout(unauthed_client, db, checkout_calls):
    owner = _customer(db)
    quote = _shop_drafted_quote(unauthed_client, db, owner)
    approve = unauthed_client.patch(
        f"{BASE}/{quote.id}/status",
        json={"status": "approved"},
        headers=_headers(ADMIN_HEADERS_USER_ID),
    )
    assert approve.status_code == 200, approve.text
    assert quote.approval_method == "manual"
    before = _snapshot(quote)

    response = _accept(unauthed_client, quote, owner, shipping_cost="0.00")

    assert response.status_code == 409, response.text
    assert _snapshot(quote) == before

    checkout = unauthed_client.post(f"{BASE}/portal/{quote.id}/checkout", headers=_headers(owner.id))
    assert checkout.status_code == 200, checkout.text
    assert [c["total_price"] for c in checkout_calls] == [before[1]]


def test_portal_quote_approved_by_staff_keeps_the_staff_price(unauthed_client, db, checkout_calls):
    owner = _customer(db)
    quote = _portal_quote(
        db, owner, weights=None,
        status="pending", approval_method="manual", auto_approved=False,
        customer_notes="Can you do it in blue?",
        requires_review_reason="Customer notes require manual review",
    )
    staff = _headers(ADMIN_HEADERS_USER_ID)
    repriced = unauthed_client.patch(f"{BASE}/{quote.id}", json={"unit_price": "20.00"}, headers=staff)
    assert repriced.status_code == 200, repriced.text
    approved = unauthed_client.patch(f"{BASE}/{quote.id}/status", json={"status": "approved"}, headers=staff)
    assert approved.status_code == 200, approved.text
    assert quote.total_price == Decimal("40.00")
    # Approval is the review, so PRO's checkout (which refuses a quote with a
    # review reason) lets the customer pay.
    assert quote.requires_review_reason is None

    response = _accept(unauthed_client, quote, owner, adjusted_unit_price="12.50", shipping_cost="0.00")

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Quote was approved by the shop; continue to checkout"
    assert quote.unit_price == Decimal("20.00")
    assert quote.total_price == Decimal("40.00")
    assert quote.status == "approved"
    assert quote.approval_method == "manual"

    checkout = unauthed_client.post(f"{BASE}/portal/{quote.id}/checkout", headers=_headers(owner.id))
    assert checkout.status_code == 200, checkout.text
    assert [c["total_price"] for c in checkout_calls] == [Decimal("40.00")]


def test_staff_hold_on_an_auto_approved_quote_survives_accept(unauthed_client, db, checkout_calls):
    """Staff moving an auto-approved quote back to pending is a hold: the
    customer's next accept must not re-approve it."""
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=None)
    assert (quote.status, quote.approval_method) == ("approved", "auto")

    staff = _headers(ADMIN_HEADERS_USER_ID)
    held = unauthed_client.patch(f"{BASE}/{quote.id}/status", json={"status": "pending"}, headers=staff)
    assert held.status_code == 200, held.text
    assert quote.status == "pending"
    assert quote.approval_method == "manual"

    response = _accept(unauthed_client, quote, owner)

    # The shipping choice is still saved, but the quote waits for staff
    # (PRO's checkout refuses a quote that is not approved).
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "pending"
    assert data["requires_review"] is True
    assert data["message"] == "Quote requires manual review"
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.status == "pending"
    assert stored.approval_method == "manual"
    assert stored.unit_price == Decimal("12.50")
    assert stored.shipping_cost == Decimal("8.50")
    assert stored.total_price == Decimal("33.50")

    # Once staff approve it, accept refuses to change it and the customer
    # pays the stored total at checkout.
    approved = unauthed_client.patch(f"{BASE}/{quote.id}/status", json={"status": "approved"}, headers=staff)
    assert approved.status_code == 200, approved.text
    again = _accept(unauthed_client, stored, owner, shipping_cost="0.00")
    assert again.status_code == 409, again.text
    assert again.json()["detail"] == "Quote was approved by the shop; continue to checkout"
    checkout = unauthed_client.post(f"{BASE}/portal/{quote.id}/checkout", headers=_headers(owner.id))
    assert checkout.status_code == 200, checkout.text
    assert [c["total_price"] for c in checkout_calls] == [Decimal("33.50")]


# ---------------------------------------------------------------------------
# Honest Quoter flows keep working
# ---------------------------------------------------------------------------

def test_quote_needing_review_still_saves_the_shipping_choice(unauthed_client, db):
    owner = _customer(db)
    quote = _portal_quote(
        db, owner, weights=None,
        status="pending", approval_method="manual", auto_approved=False,
        customer_notes="Please pack carefully",
        requires_review_reason="Customer notes require manual review",
    )

    response = _accept(unauthed_client, quote, owner)

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "pending"
    assert data["requires_review"] is True
    assert data["message"] == "Quote requires manual review"
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.status == "pending"
    assert stored.approval_method == "manual"
    assert stored.shipping_address_line1 == "123 Print St"
    assert stored.shipping_cost == Decimal("8.50")
    assert stored.total_price == Decimal("33.50")
    assert db.get(User, owner.id).shipping_address_line1 == "123 Print St"


def test_accept_again_after_cancelled_payment_does_not_add_shipping_twice(unauthed_client, db):
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=None)

    first = _accept(unauthed_client, quote, owner, shipping_cost="8.50")
    second = _accept(unauthed_client, quote, owner, shipping_cost="12.00", shipping_rate_id="rate_2")

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "approved"
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.status == "approved"
    assert stored.approval_method == "auto"
    assert stored.shipping_cost == Decimal("12.00")
    assert stored.shipping_rate_id == "rate_2"
    assert stored.total_price == Decimal("37.00")


@pytest.mark.parametrize(
    "ship_to_state,expected_tax",
    [("IN", Decimal("2.45")), ("OH", Decimal("1.75"))],
    ids=["shipping_taxable", "shipping_not_taxable"],
)
def test_tax_is_recomputed_and_never_dropped(unauthed_client, db, ship_to_state, expected_tax):
    company = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if company is None:
        company = CompanySettings(id=1, company_name="Test Co")
        db.add(company)
    company.company_state = "IN"
    db.flush()
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=None, tax_rate=Decimal("0.0700"), tax_amount=Decimal("0.00"))

    response = _accept(unauthed_client, quote, owner, shipping_state=ship_to_state, shipping_cost="10.00")

    assert response.status_code == 200, response.text
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.tax_amount == expected_tax
    assert stored.total_price == Decimal("25.00") + expected_tax + Decimal("10.00")
    assert stored.total_price >= stored.subtotal + stored.subtotal * Decimal("0.07")


# ---------------------------------------------------------------------------
# Print spec (colour slots become the BOM)
# ---------------------------------------------------------------------------

def test_multi_colour_choice_on_a_single_colour_quote_is_refused(unauthed_client, db):
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=None)
    assert quote.pricing_snapshot["active_material_slots"] == 1
    _keep_material(db, quote)

    response = _accept(
        unauthed_client, quote, owner,
        print_mode="multi",
        multi_color_info={
            "primary_slot": 1,
            "slot_colors": [_slot(n, 250, f"C{n}") for n in range(1, 17)],
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Quote was priced for a single colour"
    _assert_nothing_written(db, quote, owner, status="approved")


@pytest.mark.parametrize(
    "slot_colors",
    [
        [_slot(1, 10), _slot(2, 5, "YEL"), _slot(3, 5, "BLK")],
        [_slot(1, 50), _slot(3, 5, "BLK")],
        [_slot(1, 10), _slot(1, 10, "YEL")],
    ],
    ids=["unpriced_slot", "inflated_grams", "duplicate_slot"],
)
def test_colour_slots_must_match_the_priced_slots(unauthed_client, db, slot_colors):
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=(10, 0, 5))
    _keep_material(db, quote)

    response = _accept(
        unauthed_client, quote, owner,
        print_mode="multi",
        adjusted_unit_price=12.5,
        multi_color_info={"primary_slot": 1, "slot_colors": slot_colors},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Colour slots do not match the quoted print"
    _assert_nothing_written(db, quote, owner, status="approved")


def test_honest_colour_choice_is_saved_and_goes_to_checkout(unauthed_client, db, checkout_calls):
    """Exactly what QuoteResult.jsx sends for a two-colour print, then checkout."""
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=(10, 0, 5))
    _keep_material(db, quote)

    response = _accept(
        unauthed_client, quote, owner,
        print_mode="multi",
        adjusted_unit_price=12.5,
        multi_color_info={
            "primary_slot": 1,
            "slot_colors": [
                {**_slot(1, 10, "RED"), "is_primary": True},
                _slot(3, 5, "BLK"),
            ],
        },
        packaging_snapshot={"sku": "BOX-8"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    assert response.json()["requires_review"] is False
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.color == "MULTI_COLOR"
    assert stored.total_price == Decimal("33.50")
    materials = _materials(db, quote.id)
    assert [(m.slot_number, m.color_code, m.material_grams) for m in materials] == [
        (1, "RED", Decimal("10.00")),
        (3, "BLK", Decimal("5.00")),
    ]
    assert [m.is_primary for m in materials] == [True, False]

    checkout = unauthed_client.post(f"{BASE}/portal/{quote.id}/checkout", headers=_headers(owner.id))
    assert checkout.status_code == 200, checkout.text
    assert [c["total_price"] for c in checkout_calls] == [Decimal("33.50")]


@pytest.mark.parametrize(
    "slot_colors",
    [
        [_slot(1, 10), _slot(1, 10, "YEL")],
        [_slot(1, "1E+20")],
    ],
    ids=["duplicate_slot", "grams_the_column_cannot_hold"],
)
def test_colour_choice_without_stored_slot_data_is_still_checked(unauthed_client, db, slot_colors):
    """The unpriced fallback refuses what the priced path refuses, before writing."""
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=None, pricing_snapshot=None, slicer_diagnostics=None)
    _keep_material(db, quote)
    status_before = quote.status

    response = _accept(
        unauthed_client, quote, owner,
        print_mode="multi",
        multi_color_info={"primary_slot": 1, "slot_colors": slot_colors},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Colour slots do not match the quoted print"
    _assert_nothing_written(db, quote, owner, status=status_before)


def test_colour_choice_without_stored_slot_data_goes_to_review(unauthed_client, db):
    """PRO older than the slicer_diagnostics snapshot: keep the choice, staff review it."""
    owner = _customer(db)
    quote = _portal_quote(db, owner, weights=None, pricing_snapshot=None, slicer_diagnostics=None)

    response = _accept(
        unauthed_client, quote, owner,
        print_mode="multi",
        multi_color_info={"primary_slot": 1, "slot_colors": [_slot(1, 10), _slot(2, 5, "BLK")]},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["status"] == "pending"
    assert data["requires_review"] is True
    assert data["requires_review_reason"] == "Colour selection needs review"
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.status == "pending"
    assert stored.approval_method == "manual"
    assert stored.requires_review_reason == "Colour selection needs review"
    assert [m.color_code for m in _materials(db, quote.id)] == ["RED", "BLK"]


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------

def test_server_only_snapshots_from_the_client_are_ignored(unauthed_client, db):
    owner = _customer(db)
    quote = _portal_quote(db, owner)
    stored_pricing = dict(quote.pricing_snapshot)
    stored_diagnostics = dict(quote.slicer_diagnostics)

    response = _accept(
        unauthed_client, quote, owner,
        pricing_snapshot={"source": "client", "unit_price": "0.01"},
        component_snapshot={"items": [{"sku": "FREE-LED"}]},
        artifact_snapshot={"files": [{"kind": "gcode", "file_id": "client"}]},
        slicer_diagnostics=_slicer_diagnostics([500, 500, 500, 500]),
        packaging_snapshot={"sku": "BOX-8"},
        shipping_snapshot={"source": "quoter_accept", "package": {"sku": "BOX-8"}},
    )

    assert response.status_code == 200, response.text
    db.expire_all()
    stored = db.get(Quote, quote.id)
    assert stored.pricing_snapshot == stored_pricing
    assert stored.slicer_diagnostics == stored_diagnostics
    assert stored.component_snapshot is None
    assert stored.artifact_snapshot is None
    assert stored.packaging_snapshot == {"sku": "BOX-8"}
    assert stored.shipping_snapshot == {"source": "quoter_accept", "package": {"sku": "BOX-8"}}
