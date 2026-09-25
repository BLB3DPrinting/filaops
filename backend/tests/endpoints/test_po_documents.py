"""SEC-402: every PO document route requires a staff account.

A plain login is not enough: anyone can self-register a customer account
through POST /api/v1/auth/register. The checks run against a real PO and
document, so they prove each route refuses before it looks anything up,
not just that a missing record 404s.
"""
import uuid

from app.models.purchase_order_document import PurchaseOrderDocument


def _make_document(db, po_id, tmp_path):
    file_path = tmp_path / "invoice.pdf"
    file_path.write_bytes(b"%PDF-1.4 test invoice")
    doc = PurchaseOrderDocument(
        purchase_order_id=po_id,
        document_type="invoice",
        file_name="invoice.pdf",
        original_file_name="invoice.pdf",
        file_path=str(file_path),
        storage_type="local",
        file_size=file_path.stat().st_size,
        mime_type="application/pdf",
        uploaded_by="test@example.com",
    )
    db.add(doc)
    db.flush()
    return doc


def _doc_urls(po_id, doc_id):
    base = f"/api/v1/purchase-orders/{po_id}/documents"
    return {
        "list": base,
        "get": f"{base}/{doc_id}",
        "download": f"{base}/{doc_id}/download",
    }


def _all_routes(po_id, doc_id):
    """(name, method, url, request kwargs) for all seven document routes."""
    base = f"/api/v1/purchase-orders/{po_id}/documents"
    upload = ("invoice.pdf", b"%PDF-1.4 uploaded", "application/pdf")
    return [
        ("upload", "post", base, {"files": {"file": upload}, "data": {"document_type": "invoice"}}),
        ("bulk_upload", "post", f"{base}/bulk", {"files": [("files", upload)]}),
        ("list", "get", base, {}),
        ("get", "get", f"{base}/{doc_id}", {}),
        ("download", "get", f"{base}/{doc_id}/download", {}),
        ("update", "patch", f"{base}/{doc_id}", {"json": {"notes": "changed"}}),
        ("delete", "delete", f"{base}/{doc_id}", {}),
    ]


def test_po_document_reads_require_auth(
    unauthed_client, db, make_vendor, make_purchase_order, tmp_path
):
    """List, get and download all return 401 without a login."""
    po = make_purchase_order(vendor_id=make_vendor().id)
    doc = _make_document(db, po.id, tmp_path)

    for name, url in _doc_urls(po.id, doc.id).items():
        response = unauthed_client.get(url)
        assert response.status_code == 401, f"{name}: {response.status_code}"
        assert b"test invoice" not in response.content, name


def test_customer_account_gets_403_on_every_document_route(
    unauthed_client, role_headers, db, make_vendor, make_purchase_order, tmp_path
):
    """A customer account can't read, upload, change or delete documents."""
    po = make_purchase_order(vendor_id=make_vendor().id)
    doc = _make_document(db, po.id, tmp_path)
    headers = role_headers("customer")

    for name, method, url, kwargs in _all_routes(po.id, doc.id):
        response = getattr(unauthed_client, method)(url, headers=headers, **kwargs)
        assert response.status_code == 403, f"{name}: {response.status_code} {response.text}"
        assert b"test invoice" not in response.content, name
        assert str(tmp_path) not in response.text, name

    db.expire_all()
    stored = db.query(PurchaseOrderDocument).filter(
        PurchaseOrderDocument.purchase_order_id == po.id
    ).all()
    assert [d.id for d in stored] == [doc.id], "no upload or delete went through"
    assert stored[0].notes is None, "the update did not go through"


def test_self_registered_account_cannot_read_documents(
    unauthed_client, db, make_vendor, make_purchase_order, tmp_path
):
    """The public register flow's token is refused, end to end."""
    po = make_purchase_order(vendor_id=make_vendor().id)
    doc = _make_document(db, po.id, tmp_path)

    register = unauthed_client.post("/api/v1/auth/register", json={
        "email": f"outsider-{uuid.uuid4().hex[:8]}@example.com",
        "password": "Outsider-Passw0rd!",
        "first_name": "Out",
        "last_name": "Sider",
    })
    assert register.status_code == 201, register.text
    token = register.json().get("access_token") or register.cookies.get("access_token")
    assert token, "register returned no token"

    headers = {"Authorization": f"Bearer {token}"}
    for name, url in _doc_urls(po.id, doc.id).items():
        response = unauthed_client.get(url, headers=headers)
        assert response.status_code == 403, f"{name}: {response.status_code}"
        assert b"test invoice" not in response.content, name


def test_operator_can_read_documents(
    unauthed_client, role_headers, db, make_vendor, make_purchase_order, tmp_path
):
    """Operators are staff: list, get and download still work for them."""
    po = make_purchase_order(vendor_id=make_vendor().id)
    doc = _make_document(db, po.id, tmp_path)
    headers = role_headers("operator")
    urls = _doc_urls(po.id, doc.id)

    assert unauthed_client.get(urls["list"], headers=headers).status_code == 200
    assert unauthed_client.get(urls["get"], headers=headers).status_code == 200
    download = unauthed_client.get(urls["download"], headers=headers)
    assert download.status_code == 200
    assert download.content == b"%PDF-1.4 test invoice"


def test_po_document_reads_work_when_logged_in(
    client, db, make_vendor, make_purchase_order, tmp_path
):
    """The admin can still list, read and download documents."""
    po = make_purchase_order(vendor_id=make_vendor().id)
    doc = _make_document(db, po.id, tmp_path)
    urls = _doc_urls(po.id, doc.id)

    list_resp = client.get(urls["list"])
    assert list_resp.status_code == 200
    assert [d["id"] for d in list_resp.json()] == [doc.id]

    get_resp = client.get(urls["get"])
    assert get_resp.status_code == 200
    assert get_resp.json()["original_file_name"] == "invoice.pdf"

    download_resp = client.get(urls["download"])
    assert download_resp.status_code == 200
    assert download_resp.content == b"%PDF-1.4 test invoice"


def test_po_document_missing_records_404_when_logged_in(client):
    """Logged in, unknown ids get 404, not 401."""
    for name, url in _doc_urls(999999, 999999).items():
        response = client.get(url)
        assert response.status_code == 404, f"{name}: {response.status_code}"
