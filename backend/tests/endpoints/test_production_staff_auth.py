"""SEC-409: production, item, routing, work-center and maintenance routes are staff-only.

Anyone can self-register a customer account, so a plain login must not reach
shop-floor data: production orders and their operations, QC photos, the item
master, routings, work centers, maintenance logs and maintenance windows. Some
item and routing reads used to answer with no login at all. A customer now gets
403 before anything runs, an anonymous caller gets 401, and an operator keeps
the access they had. Editing scrap reasons is shop configuration and needs an
admin.
"""
import uuid
from datetime import datetime, timezone

import pytest

from app.models.production_order import ProductionOrder, QCInspection
from app.models.product import Product
from app.models.scrap_reason import ScrapReason

API = "/api/v1"


def _uid():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def shop(db, make_product, make_production_order):
    """A product, a draft production order and a QC inspection on it."""
    product = make_product(name="Staff auth widget")
    order = make_production_order(product_id=product.id, status="draft")
    inspection = QCInspection(
        production_order_id=order.id,
        result="failed",
        inspected_at=datetime.now(timezone.utc),
    )
    db.add(inspection)
    db.flush()
    return {"product": product, "order": order, "inspection": inspection}


def _reads(shop):
    """One representative read per module."""
    po_id = shop["order"].id
    insp_id = shop["inspection"].id
    return [
        ("production_orders", f"{API}/production-orders/"),
        ("operation_status", f"{API}/production-orders/{po_id}/operations"),
        ("qc_photos", f"{API}/production-orders/qc-inspections/{insp_id}/photos"),
        ("items", f"{API}/items"),
        ("routings", f"{API}/routings/"),
        ("work_centers", f"{API}/work-centers/"),
        ("maintenance", f"{API}/maintenance/"),
        ("maintenance_windows", f"{API}/maintenance-windows"),
    ]


def _writes(shop):
    """One representative write per module, with a valid body."""
    po_id = shop["order"].id
    insp_id = shop["inspection"].id
    return [
        ("production_orders", "post", f"{API}/production-orders/{po_id}/cancel", {}),
        ("operation_status", "post", f"{API}/production-orders/{po_id}/operations/generate", {}),
        ("qc_photos", "delete", f"{API}/production-orders/qc-inspections/{insp_id}/photos/1", {}),
        ("items", "post", f"{API}/items",
         {"json": {"sku": f"CUST-{_uid()}", "name": "Injected", "item_type": "finished_good"}}),
        ("routings", "post", f"{API}/routings/",
         {"json": {"product_id": shop["product"].id, "name": "Injected routing"}}),
        ("work_centers", "post", f"{API}/work-centers/",
         {"json": {"code": f"WC-{_uid()}", "name": "Injected", "center_type": "machine"}}),
        ("maintenance", "delete", f"{API}/maintenance/1", {}),
        ("maintenance_windows", "post", f"{API}/maintenance-windows",
         {"json": {"printer_id": 1, "start": "2030-01-01T00:00:00Z",
                   "end": "2030-01-01T02:00:00Z", "reason": "x"}}),
    ]


@pytest.mark.parametrize(
    "url",
    [
        f"{API}/items",
        f"{API}/items/categories",
        f"{API}/items/low-stock",
        f"{API}/items/sku/ANY-SKU",
        f"{API}/routings/",
        f"{API}/routings/1",
        f"{API}/routings/manufacturing-bom/1",
    ],
)
def test_formerly_anonymous_reads_now_require_login(unauthed_client, url):
    response = unauthed_client.get(url)
    assert response.status_code == 401, f"{url}: {response.status_code}"


def test_customer_gets_403_on_every_module(unauthed_client, role_headers, db, shop):
    headers = role_headers("customer")

    for name, url in _reads(shop):
        response = unauthed_client.get(url, headers=headers)
        assert response.status_code == 403, f"{name} read: {response.status_code} {response.text}"

    for name, method, url, kwargs in _writes(shop):
        response = getattr(unauthed_client, method)(url, headers=headers, **kwargs)
        assert response.status_code == 403, f"{name} write: {response.status_code} {response.text}"

    db.expire_all()
    order = db.query(ProductionOrder).filter(ProductionOrder.id == shop["order"].id).one()
    assert order.status == "draft"
    assert db.query(Product).filter(Product.name == "Injected").first() is None


def test_operator_keeps_access_on_every_module(unauthed_client, role_headers, db, shop):
    headers = role_headers("operator")

    for name, url in _reads(shop):
        response = unauthed_client.get(url, headers=headers)
        assert response.status_code == 200, f"{name}: {response.status_code} {response.text}"

    cancelled = unauthed_client.post(
        f"{API}/production-orders/{shop['order'].id}/cancel", headers=headers
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"


def _scrap_reason(db):
    reason = ScrapReason(
        code=f"auth_{_uid()}",
        name="Auth test reason",
        active=True,
        sequence=90000 + int(uuid.uuid4().int % 9000),
    )
    db.add(reason)
    db.flush()
    return reason


def test_scrap_reason_writes_are_admin_only(unauthed_client, role_headers, db):
    reason = _scrap_reason(db)
    base = f"{API}/production-orders/scrap-reasons"

    operator = role_headers("operator")
    listed = unauthed_client.get(base, headers=operator)
    assert listed.status_code == 200, listed.text

    created = unauthed_client.post(
        base, headers=operator, json={"code": f"op_{_uid()}", "name": "By operator"}
    )
    assert created.status_code == 403, created.text
    updated = unauthed_client.put(
        f"{base}/{reason.id}", headers=operator, json={"name": "Renamed by operator"}
    )
    assert updated.status_code == 403, updated.text
    deleted = unauthed_client.delete(f"{base}/{reason.id}", headers=operator)
    assert deleted.status_code == 403, deleted.text

    db.expire_all()
    stored = db.query(ScrapReason).filter(ScrapReason.id == reason.id).one()
    assert stored.name == "Auth test reason"
    assert db.query(ScrapReason).filter(ScrapReason.name == "By operator").first() is None

    admin = role_headers("admin")
    renamed = unauthed_client.put(
        f"{base}/{reason.id}", headers=admin, json={"name": "Renamed by admin"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Renamed by admin"
