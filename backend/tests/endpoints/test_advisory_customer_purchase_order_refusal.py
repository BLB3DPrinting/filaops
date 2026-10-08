"""GHSA-vrr8-gpvm-732v: a self-registered customer cannot read or modify purchase orders.

The customer account is created the way the advisory describes: through
POST /api/v1/auth/register with self-registration on (ENABLE_PUBLIC_QUOTER),
and the token that endpoint returns is used against the purchasing routes.
Every request must answer 403, and a modify attempt must leave the PO as it was.
"""
import uuid

import pytest

PO_BASE = "/api/v1/purchase-orders"


@pytest.fixture
def customer_headers(unauthed_client, monkeypatch):
    from app.core.config import settings
    from app.core.limiter import limiter

    monkeypatch.setattr(settings, "ENABLE_PUBLIC_QUOTER", True, raising=False)
    # /auth/register is limited to 3 a minute; the full suite registers more.
    monkeypatch.setattr(limiter, "enabled", False, raising=False)
    register = unauthed_client.post("/api/v1/auth/register", json={
        "email": f"a4-customer-{uuid.uuid4().hex[:8]}@example.com",
        "password": "Outsider-Passw0rd!",
        "first_name": "Out",
        "last_name": "Sider",
    })
    assert register.status_code == 201, register.text
    body = register.json()
    assert body.get("account_type", "customer") == "customer"
    token = body.get("access_token") or register.cookies.get("access_token")
    assert token, "register returned no token"
    return {"Authorization": f"Bearer {token}"}


def test_customer_cannot_list_or_read_purchase_orders(
    unauthed_client, customer_headers, make_vendor, make_purchase_order
):
    po = make_purchase_order(vendor_id=make_vendor().id)

    listing = unauthed_client.get(f"{PO_BASE}/", headers=customer_headers)
    assert listing.status_code == 403, f"list: {listing.status_code} {listing.text[:200]}"

    detail = unauthed_client.get(f"{PO_BASE}/{po.id}", headers=customer_headers)
    assert detail.status_code == 403, f"get: {detail.status_code} {detail.text[:200]}"
    assert po.po_number not in detail.text


def test_customer_cannot_create_purchase_order(
    unauthed_client, customer_headers, db, make_vendor, make_product
):
    from app.models.purchase_order import PurchaseOrder

    vendor = make_vendor()
    product = make_product(item_type="supply")
    before = db.query(PurchaseOrder).count()

    response = unauthed_client.post(f"{PO_BASE}/", headers=customer_headers, json={
        "vendor_id": vendor.id,
        "notes": "created by a customer",
        "lines": [{"product_id": product.id, "quantity_ordered": "1", "unit_cost": "1.00"}],
    })
    assert response.status_code == 403, f"create: {response.status_code} {response.text[:200]}"
    assert db.query(PurchaseOrder).count() == before


def test_customer_cannot_update_or_change_status_of_purchase_order(
    unauthed_client, customer_headers, db, make_vendor, make_purchase_order
):
    po = make_purchase_order(vendor_id=make_vendor().id)
    original_status = po.status

    update = unauthed_client.put(
        f"{PO_BASE}/{po.id}", headers=customer_headers, json={"notes": "tampered"}
    )
    assert update.status_code == 403, f"update: {update.status_code} {update.text[:200]}"

    status_change = unauthed_client.post(
        f"{PO_BASE}/{po.id}/status", headers=customer_headers, json={"status": "cancelled"}
    )
    assert status_change.status_code == 403, (
        f"status: {status_change.status_code} {status_change.text[:200]}"
    )

    db.refresh(po)
    assert po.notes != "tampered"
    assert po.status == original_status
