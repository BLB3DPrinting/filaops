"""SEC-406: the /admin tree is staff-only, with no anonymous exceptions.

POST /api/v1/admin/fulfillment/ship/consolidate/get-rates had no auth at
all: anyone could look up other customers' ready-to-ship orders, learn
their order numbers and push their addresses to the shop's carrier
account. GET /api/v1/admin/orders/import/template was anonymous too. Both
now need a staff account, and the /admin aggregator itself carries the
staff gate so a sub-route that forgets its own dependency stays closed.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api.v1.deps import get_current_staff_user
from app.services.shipping_service import shipping_service

GET_RATES = "/api/v1/admin/fulfillment/ship/consolidate/get-rates"
TEMPLATE = "/api/v1/admin/orders/import/template"


@pytest.fixture
def carrier_calls(monkeypatch):
    """Stand-in carrier calls that record whether the route reached them."""
    calls = []

    def _estimate_weight_oz(total_grams, quantity):
        calls.append("estimate_weight_oz")
        return 12.0

    def _get_shipping_rates(**kwargs):
        calls.append("get_shipping_rates")
        rate = SimpleNamespace(
            carrier="USPS",
            service="Priority",
            rate=Decimal("9.99"),
            est_delivery_days=2,
            rate_id="rate_test_1",
        )
        return [rate], "shp_test_1"

    monkeypatch.setattr(shipping_service, "estimate_weight_oz", _estimate_weight_oz, raising=False)
    monkeypatch.setattr(shipping_service, "get_shipping_rates", _get_shipping_rates, raising=False)
    return calls


@pytest.fixture
def two_ready_orders(make_sales_order):
    """Two ready-to-ship orders going to the same address."""
    address = {
        "shipping_address_line1": "1 Consolidate Way",
        "shipping_city": "Springfield",
        "shipping_state": "IL",
        "shipping_zip": "62701",
        "shipping_country": "US",
    }
    return [
        make_sales_order(status="ready_to_ship", order_number=f"SO-RATES-{uuid.uuid4().hex[:8]}", **address)
        for _ in range(2)
    ]


def test_admin_aggregator_carries_the_staff_gate():
    from app.api.v1.endpoints.admin import router as admin_router

    assert any(d.dependency is get_current_staff_user for d in admin_router.dependencies)


def test_get_rates_requires_login(unauthed_client, carrier_calls, two_ready_orders):
    order_ids = [o.id for o in two_ready_orders]
    response = unauthed_client.post(GET_RATES, json={"order_ids": order_ids})
    assert response.status_code == 401, response.text
    assert carrier_calls == []
    assert "SO-RATES-" not in response.text


def test_customer_cannot_get_rates(unauthed_client, role_headers, carrier_calls, two_ready_orders):
    order_ids = [o.id for o in two_ready_orders]
    response = unauthed_client.post(
        GET_RATES, headers=role_headers("customer"), json={"order_ids": order_ids}
    )
    assert response.status_code == 403, response.text
    assert carrier_calls == []
    assert "SO-RATES-" not in response.text


def test_operator_single_order_is_rejected_before_any_carrier_call(
    unauthed_client, role_headers, carrier_calls, two_ready_orders
):
    response = unauthed_client.post(
        GET_RATES,
        headers=role_headers("operator"),
        json={"order_ids": [two_ready_orders[0].id]},
    )
    assert response.status_code == 400, response.text
    assert "Need at least 2 orders" in response.json()["detail"]
    assert carrier_calls == []


def test_operator_can_still_get_consolidated_rates(
    unauthed_client, role_headers, carrier_calls, two_ready_orders
):
    order_ids = [o.id for o in two_ready_orders]
    response = unauthed_client.post(
        GET_RATES, headers=role_headers("operator"), json={"order_ids": order_ids}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True
    assert body["consolidated"]["order_ids"] == order_ids
    assert "get_shipping_rates" in carrier_calls


def test_import_template_requires_login(unauthed_client):
    assert unauthed_client.get(TEMPLATE).status_code == 401


def test_import_template_refuses_customers(unauthed_client, role_headers):
    response = unauthed_client.get(TEMPLATE, headers=role_headers("customer"))
    assert response.status_code == 403


def test_operator_can_download_import_template(unauthed_client, role_headers):
    response = unauthed_client.get(TEMPLATE, headers=role_headers("operator"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "Customer Email" in response.text
