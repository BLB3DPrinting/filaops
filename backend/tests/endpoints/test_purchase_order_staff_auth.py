"""SEC-407: purchasing routes are staff-only.

Anyone can self-register a customer account, so a plain login must not be
able to read or change purchase orders (supplier costs, spend, documents),
receive stock (inventory, lots, spools and GL entries), edit vendor SKU
mappings or read and rewrite supplier master data. Every route should
answer 403 for a customer before it does anything. The checks run against
real records, so they prove each route refuses before it looks anything
up, not just that a missing record 404s. Operators keep their access.
"""
import uuid
from decimal import Decimal

import pytest

from app.core.security import create_access_token
from app.models.inventory import InventoryTransaction
from app.models.material_spool import MaterialSpool
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.purchase_order_document import VendorItem
from app.models.purchasing_event import PurchasingEvent
from app.models.traceability import MaterialLot
from app.models.user import User
from app.models.vendor import Vendor

PO_BASE = "/api/v1/purchase-orders"
VENDOR_BASE = "/api/v1/vendors"


def _headers(db, account_type):
    user = User(
        email=f"po-{account_type}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        account_type=account_type,
        status="active",
    )
    db.add(user)
    db.flush()
    return {"Authorization": f"Bearer {create_access_token(user_id=user.id)}"}


def _add_line(db, po, product, quantity="10", unit_cost="5.00"):
    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product.id,
        line_number=1,
        quantity_ordered=Decimal(quantity),
        quantity_received=Decimal("0"),
        unit_cost=Decimal(unit_cost),
        line_total=Decimal(quantity) * Decimal(unit_cost),
    )
    db.add(line)
    db.flush()
    return line


def _po_routes(po_id, line_id, ordered_po_id, ordered_line_id, vendor_id, product_id):
    """(name, method, url, request kwargs) for all 14 purchase-order routes."""
    upload = ("invoice.pdf", b"%PDF-1.4 uploaded by a customer", "application/pdf")
    return [
        ("list", "get", f"{PO_BASE}/", {}),
        ("get", "get", f"{PO_BASE}/{po_id}", {}),
        ("create", "post", f"{PO_BASE}/", {"json": {
            "vendor_id": vendor_id,
            "notes": "created by a customer",
            "lines": [{"product_id": product_id, "quantity_ordered": "1", "unit_cost": "1.00"}],
        }}),
        ("update", "put", f"{PO_BASE}/{po_id}", {"json": {"notes": "tampered", "tax_amount": "999"}}),
        ("add_line", "post", f"{PO_BASE}/{po_id}/lines",
         {"json": {"product_id": product_id, "quantity_ordered": "2", "unit_cost": "0"}}),
        ("update_line", "put", f"{PO_BASE}/{po_id}/lines/{line_id}", {"json": {"unit_cost": "0.01"}}),
        ("delete_line", "delete", f"{PO_BASE}/{po_id}/lines/{line_id}", {}),
        ("status", "post", f"{PO_BASE}/{po_id}/status", {"json": {"status": "cancelled"}}),
        ("receive", "post", f"{PO_BASE}/{ordered_po_id}/receive",
         {"json": {"lines": [{"line_id": ordered_line_id, "quantity_received": "5"}]}}),
        ("upload", "post", f"{PO_BASE}/{po_id}/upload", {"files": {"file": upload}}),
        ("delete", "delete", f"{PO_BASE}/{po_id}", {}),
        ("events", "get", f"{PO_BASE}/{po_id}/events", {}),
        ("add_event", "post", f"{PO_BASE}/{po_id}/events",
         {"json": {"event_type": "note_added", "title": "forged by a customer"}}),
        ("pdf", "get", f"{PO_BASE}/{po_id}/pdf", {}),
    ]


def _vendor_item_routes(vendor_id, item_id, vendor_sku):
    """(name, method, url, request kwargs) for all eight vendor-item routes."""
    base = f"{PO_BASE}/vendors/{vendor_id}/items"
    return [
        ("vi_list", "get", base, {}),
        ("vi_create", "post", base, {"json": {"vendor_sku": "CUSTOMER-SKU"}}),
        ("vi_get", "get", f"{base}/{item_id}", {}),
        ("vi_update", "put", f"{base}/{item_id}", {"json": {"default_unit_cost": "0", "product_id": None}}),
        ("vi_delete", "delete", f"{base}/{item_id}", {}),
        ("vi_search", "get", f"{PO_BASE}/vendor-items/search?q={vendor_sku}", {}),
        ("vi_suggest", "post", f"{PO_BASE}/vendor-items/suggest-match?vendor_sku={vendor_sku}", {}),
        ("vi_last_seen", "post", f"{PO_BASE}/vendor-items/bulk-update-last-seen",
         {"json": [{"vendor_id": vendor_id, "vendor_sku": vendor_sku}]}),
    ]


def _vendor_routes(vendor_id):
    """(name, method, url, request kwargs) for all six vendor routes."""
    return [
        ("v_list", "get", f"{VENDOR_BASE}/", {}),
        ("v_get", "get", f"{VENDOR_BASE}/{vendor_id}", {}),
        ("v_create", "post", f"{VENDOR_BASE}/", {"json": {"name": "Vendor made by a customer"}}),
        ("v_update", "put", f"{VENDOR_BASE}/{vendor_id}", {"json": {"email": "attacker@example.com"}}),
        ("v_metrics", "get", f"{VENDOR_BASE}/{vendor_id}/metrics", {}),
        ("v_delete", "delete", f"{VENDOR_BASE}/{vendor_id}", {}),
    ]


def _all_routes(**ids):
    return (
        _po_routes(ids["po"], ids["line"], ids["ordered_po"], ids["ordered_line"], ids["vendor"], ids["product"])
        + _vendor_item_routes(ids["vendor"], ids["vendor_item"], ids["vendor_sku"])
        + _vendor_routes(ids["vendor"])
    )


_PLACEHOLDER_IDS = dict(
    po=1, line=1, ordered_po=1, ordered_line=1, vendor=1, product=1, vendor_item=1, vendor_sku="SKU-1",
)


@pytest.fixture
def purchasing_records(db, make_vendor, make_product, make_purchase_order):
    vendor = make_vendor(email="orders@supplier.example", account_number="ACCT-123")
    product = make_product(item_type="supply", unit="EA")
    draft_po = make_purchase_order(vendor_id=vendor.id, status="draft", notes="original notes")
    draft_line = _add_line(db, draft_po, product)
    ordered_po = make_purchase_order(vendor_id=vendor.id, status="ordered")
    ordered_line = _add_line(db, ordered_po, product)
    vendor_sku = f"VSKU-{uuid.uuid4().hex[:8]}"
    vendor_item = VendorItem(
        vendor_id=vendor.id,
        vendor_sku=vendor_sku,
        product_id=product.id,
        default_unit_cost="4.50",
        times_ordered=3,
    )
    db.add(vendor_item)
    db.flush()
    return {
        "vendor": vendor,
        "product": product,
        "draft_po": draft_po,
        "draft_line": draft_line,
        "ordered_po": ordered_po,
        "ordered_line": ordered_line,
        "vendor_item": vendor_item,
        "ids": dict(
            po=draft_po.id,
            line=draft_line.id,
            ordered_po=ordered_po.id,
            ordered_line=ordered_line.id,
            vendor=vendor.id,
            product=product.id,
            vendor_item=vendor_item.id,
            vendor_sku=vendor_sku,
        ),
    }


def test_route_tables_cover_every_purchasing_route():
    """Keep the tables in step with the routers (14 PO, 8 vendor-item, 6 vendor)."""
    assert len(_po_routes(1, 1, 1, 1, 1, 1)) == 14
    assert len(_vendor_item_routes(1, 1, "x")) == 8
    assert len(_vendor_routes(1)) == 6


@pytest.mark.parametrize("name,method,url,kwargs", _all_routes(**_PLACEHOLDER_IDS))
def test_purchasing_routes_require_login(unauthed_client, name, method, url, kwargs):
    response = getattr(unauthed_client, method)(url, **kwargs)
    assert response.status_code == 401, f"{name}: {response.status_code}"


def test_customer_gets_403_on_every_purchasing_route(unauthed_client, db, purchasing_records):
    rec = purchasing_records
    headers = _headers(db, "customer")
    po_count = db.query(PurchaseOrder).count()
    vendor_count = db.query(Vendor).count()
    txn_count = db.query(InventoryTransaction).count()
    lot_count = db.query(MaterialLot).count()
    spool_count = db.query(MaterialSpool).count()

    for name, method, url, kwargs in _all_routes(**rec["ids"]):
        response = getattr(unauthed_client, method)(url, headers=headers, **kwargs)
        assert response.status_code == 403, f"{name}: {response.status_code} {response.text}"
        assert response.json()["detail"] == "Staff access required", name

    db.expire_all()

    # Purchase orders: nothing created, edited, re-statused or deleted.
    assert db.query(PurchaseOrder).count() == po_count
    draft = db.get(PurchaseOrder, rec["draft_po"].id)
    assert draft is not None, "delete did not go through"
    assert draft.status == "draft"
    assert draft.notes == "original notes"
    assert draft.tax_amount == 0
    assert draft.document_url is None, "upload did not replace the document"
    lines = db.query(PurchaseOrderLine).filter(PurchaseOrderLine.purchase_order_id == draft.id).all()
    assert [line.id for line in lines] == [rec["draft_line"].id]
    assert lines[0].unit_cost == Decimal("5.00")
    assert db.query(PurchasingEvent).filter(
        PurchasingEvent.purchase_order_id == draft.id
    ).count() == 0, "no event was forged"

    # Receiving: no stock, lots, spools or receipt quantities.
    ordered = db.get(PurchaseOrder, rec["ordered_po"].id)
    assert ordered.status == "ordered"
    assert db.get(PurchaseOrderLine, rec["ordered_line"].id).quantity_received == 0
    assert db.query(InventoryTransaction).count() == txn_count
    assert db.query(MaterialLot).count() == lot_count
    assert db.query(MaterialSpool).count() == spool_count

    # Vendor items: nothing created, edited or deleted.
    item = db.get(VendorItem, rec["vendor_item"].id)
    assert item is not None
    assert item.default_unit_cost == "4.50"
    assert item.product_id == rec["product"].id
    assert item.times_ordered == 3
    assert db.query(VendorItem).filter(VendorItem.vendor_sku == "CUSTOMER-SKU").count() == 0

    # Vendors: nothing created, edited or deleted.
    assert db.query(Vendor).count() == vendor_count
    vendor = db.get(Vendor, rec["vendor"].id)
    assert vendor.is_active is True
    assert vendor.email == "orders@supplier.example"


def test_operator_keeps_purchasing_access(unauthed_client, db, purchasing_records):
    rec = purchasing_records
    headers = _headers(db, "operator")

    listed = unauthed_client.get(f"{PO_BASE}/", headers=headers)
    assert listed.status_code == 200, listed.text

    created = unauthed_client.post(
        f"{PO_BASE}/",
        headers=headers,
        json={
            "vendor_id": rec["vendor"].id,
            "lines": [{"product_id": rec["product"].id, "quantity_ordered": "3", "unit_cost": "2.00"}],
        },
    )
    assert created.status_code == 201, created.text

    search = unauthed_client.get(
        f"{PO_BASE}/vendor-items/search",
        headers=headers,
        params={"q": rec["ids"]["vendor_sku"]},
    )
    assert search.status_code == 200, search.text
    assert [i["id"] for i in search.json()] == [rec["vendor_item"].id]

    vendors = unauthed_client.get(f"{VENDOR_BASE}/", headers=headers)
    assert vendors.status_code == 200, vendors.text
