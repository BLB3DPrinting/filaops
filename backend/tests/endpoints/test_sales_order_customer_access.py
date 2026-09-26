"""SEC-409: customers no longer reach Core sales-order routes, even their own.

The whole /sales-orders router is staff-only now (owner decision 2). Buyers
see and cancel their orders through the PRO portal, and imported orders attach
to any user with a matching email, so a customer who pre-registered a buyer's
email must not be able to read, cancel or annotate that buyer's orders here.

Operators keep exactly what they had: the owner-or-admin checks inside the
list/detail/cancel/event handlers are unchanged, so an operator still gets 403
on the detail of an order they do not own, and 200 on the staff-only reads.
"""
import uuid
from decimal import Decimal

import pytest

from app.core.security import create_access_token
from app.models.order_event import OrderEvent
from app.models.sales_order import SalesOrder
from app.models.shipping_event import ShippingEvent
from app.models.user import User

BASE = "/api/v1/sales-orders"


@pytest.fixture
def role_user(db):
    """Factory: account_type -> (User, Bearer headers) for a new active user."""

    def _factory(account_type):
        user = User(
            email=f"so-{account_type}-{uuid.uuid4().hex[:8]}@example.com",
            password_hash="not-a-real-hash",
            first_name="Test",
            last_name=account_type.title(),
            account_type=account_type,
            status="active",
        )
        db.add(user)
        db.flush()
        return user, {"Authorization": f"Bearer {create_access_token(user_id=user.id)}"}

    return _factory


def _owned_order(db, make_product, make_sales_order, owner):
    product = make_product(selling_price=Decimal("10.00"))
    so = make_sales_order(
        product_id=product.id,
        quantity=1,
        unit_price=Decimal("10.00"),
        status="confirmed",
        user_id=owner.id,
    )
    db.flush()
    return so, product


def _customer_routes(so_id, product_id, quote_id):
    """Every sales-order route a customer could use before the gate."""
    return [
        ("list", "get", f"{BASE}/", {}),
        ("detail", "get", f"{BASE}/{so_id}", {}),
        ("material_requirements", "get", f"{BASE}/{so_id}/material-requirements", {}),
        ("cancel", "post", f"{BASE}/{so_id}/cancel", {"json": {"cancellation_reason": "customer cancel"}}),
        ("events_list", "get", f"{BASE}/{so_id}/events", {}),
        ("events_add", "post", f"{BASE}/{so_id}/events",
         {"json": {"event_type": "note_added", "title": "customer note"}}),
        ("shipping_events_list", "get", f"{BASE}/{so_id}/shipping-events", {}),
        ("shipping_events_add", "post", f"{BASE}/{so_id}/shipping-events",
         {"json": {"event_type": "delivered", "title": "Delivered"}}),
        ("create", "post", f"{BASE}/",
         {"json": {"lines": [{"product_id": product_id, "quantity": 1, "unit_price": "0.01"}]}}),
        ("convert", "post", f"{BASE}/convert/{quote_id}", {"json": {}}),
        ("status_transitions", "get", f"{BASE}/status-transitions", {}),
        ("payment_statuses", "get", f"{BASE}/payment-statuses", {}),
        ("blocking_issues", "get", f"{BASE}/{so_id}/blocking-issues", {}),
        ("fulfillment_status", "get", f"{BASE}/{so_id}/fulfillment-status", {}),
        ("pre_flight_check", "post", f"{BASE}/{so_id}/pre-flight-check", {}),
    ]


def _accepted_quote_for(client, db, owner):
    """An accepted quote owned by the customer (convert used to accept it)."""
    from app.models.quote import Quote

    resp = client.post("/api/v1/quotes", json={
        "product_name": "Customer Widget",
        "quantity": 1,
        "unit_price": "10.00",
        "customer_name": "Cust Omer",
        "customer_email": owner.email,
        "material_type": "PLA",
        "valid_days": 30,
    })
    assert resp.status_code == 201, resp.text
    quote = db.get(Quote, resp.json()["id"])
    quote.user_id = owner.id
    quote.customer_id = owner.id
    quote.status = "accepted"
    db.flush()
    return quote


class TestCustomerHasNoSalesOrderAccess:

    def test_owner_customer_is_refused_on_every_route(
        self, client, db, role_user, make_product, make_sales_order
    ):
        customer, headers = role_user("customer")
        so, product = _owned_order(db, make_product, make_sales_order, customer)
        quote = _accepted_quote_for(client, db, customer)
        orders_before = db.query(SalesOrder).count()
        events_before = db.query(OrderEvent).filter(OrderEvent.sales_order_id == so.id).count()
        ship_events_before = db.query(ShippingEvent).filter(ShippingEvent.sales_order_id == so.id).count()

        failures = []
        for name, method, url, kwargs in _customer_routes(so.id, product.id, quote.id):
            resp = getattr(client, method)(url, headers=headers, **kwargs)
            if resp.status_code != 403 or resp.json().get("detail") != "Staff access required":
                failures.append(f"{name}: {resp.status_code} {resp.text[:200]}")
        assert failures == []

        db.expire_all()
        refreshed = db.get(SalesOrder, so.id)
        assert refreshed.status == "confirmed"
        assert refreshed.cancelled_at is None
        assert db.query(SalesOrder).count() == orders_before
        assert db.query(OrderEvent).filter(OrderEvent.sales_order_id == so.id).count() == events_before
        assert (
            db.query(ShippingEvent).filter(ShippingEvent.sales_order_id == so.id).count()
            == ship_events_before
        )
        assert quote.status == "accepted"
        assert quote.sales_order_id is None

    @pytest.mark.parametrize("name", ["list", "detail", "cancel", "shipping_events_list"])
    def test_anonymous_gets_401(self, unauthed_client, name):
        routes = {r[0]: r for r in _customer_routes(1, 1, 1)}
        _, method, url, kwargs = routes[name]
        resp = getattr(unauthed_client, method)(url, **kwargs)
        assert resp.status_code == 401


class TestOperatorBehaviourUnchanged:

    def test_operator_cannot_view_order_they_do_not_own(
        self, client, db, role_user, make_product, make_sales_order
    ):
        # Unchanged owner-or-admin rule: operators only see their own orders
        # through the detail route (opening it up is a separate UX change).
        owner, _ = role_user("customer")
        so, _ = _owned_order(db, make_product, make_sales_order, owner)
        _, headers = role_user("operator")

        resp = client.get(f"{BASE}/{so.id}", headers=headers)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Not authorized to view this order"

    def test_operator_can_read_blocking_issues(
        self, client, db, role_user, make_product, make_sales_order
    ):
        owner, _ = role_user("customer")
        so, _ = _owned_order(db, make_product, make_sales_order, owner)
        _, headers = role_user("operator")

        resp = client.get(f"{BASE}/{so.id}/blocking-issues", headers=headers)
        assert resp.status_code == 200, resp.text

    def test_operator_can_list_orders(self, client, role_user):
        _, headers = role_user("operator")
        resp = client.get(f"{BASE}/", headers=headers)
        assert resp.status_code == 200, resp.text

    def test_operator_still_refused_admin_only_status_change(
        self, client, db, role_user, make_product, make_sales_order
    ):
        owner, _ = role_user("customer")
        so, _ = _owned_order(db, make_product, make_sales_order, owner)
        _, headers = role_user("operator")

        resp = client.patch(
            f"{BASE}/{so.id}/status", json={"status": "in_production"}, headers=headers
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin access required"
        db.expire_all()
        assert db.get(SalesOrder, so.id).status == "confirmed"
