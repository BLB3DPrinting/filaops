"""GHSA-jgwx-xrmr-26fv: a customer account (account_type='customer') must be refused (403)
by staff-only Core API routes, over real HTTP via the FastAPI TestClient.

Self-contained: uses only conftest fixtures (unauthed_client, role_headers, db).
No request bodies are sent; FastAPI solves auth dependencies before body
validation, so a gated route answers 403 and an ungated one answers 200/4xx(!=403).
"""
import pytest

# (method, path) -- staff-only routes spanning the Core modules.
STAFF_ROUTES = [
    ("GET", "/api/v1/items"),
    ("POST", "/api/v1/items"),
    ("GET", "/api/v1/sales-orders/"),
    ("POST", "/api/v1/sales-orders/"),
    ("GET", "/api/v1/quotes/"),
    ("GET", "/api/v1/quotes/stats"),
    ("GET", "/api/v1/production-orders/"),
    ("POST", "/api/v1/production-orders/"),
    ("GET", "/api/v1/inventory/negative-inventory-report"),
    ("POST", "/api/v1/inventory/adjust-quantity"),
    ("GET", "/api/v1/materials/options"),
    ("GET", "/api/v1/vendors/"),
    ("POST", "/api/v1/vendors/"),
    ("GET", "/api/v1/purchase-orders/"),
    ("GET", "/api/v1/invoices"),
    ("GET", "/api/v1/payments"),
    ("GET", "/api/v1/mrp/runs"),
    ("GET", "/api/v1/accounting/trial-balance"),
    ("GET", "/api/v1/admin/users/"),
    ("POST", "/api/v1/admin/users/"),
    ("GET", "/api/v1/admin/audit/transactions"),
    ("GET", "/api/v1/admin/locations"),
    ("GET", "/api/v1/settings/company"),
    ("PATCH", "/api/v1/settings/company"),
    ("GET", "/api/v1/settings/ai"),
]


@pytest.mark.parametrize("method,path", STAFF_ROUTES, ids=[f"{m} {p}" for m, p in STAFF_ROUTES])
def test_customer_account_is_refused_on_staff_route(unauthed_client, role_headers, db, method, path):
    headers = role_headers("customer")
    db.commit()
    response = unauthed_client.request(method, path, headers=headers)
    db.rollback()
    assert response.status_code == 403, (
        f"customer account got {response.status_code} on {method} {path}: {response.text[:150]!r} "
        "(expected 403: staff-only route must refuse account_type='customer')"
    )


def test_operator_is_not_refused_on_a_read_route(unauthed_client, role_headers, db):
    """Control: the gate refuses customers, not staff (operator reads must not be 401/403)."""
    headers = role_headers("operator")
    db.commit()
    response = unauthed_client.get("/api/v1/items", headers=headers)
    db.rollback()
    assert response.status_code not in (401, 403), response.text[:150]
