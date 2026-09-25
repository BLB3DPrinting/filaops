"""SEC-402: every PO document read route requires a logged-in user.

Covers the three GET routes: list, get by id, and download. The 401 checks
run against a real PO and document, so they prove the route refuses before
it looks anything up, not just that a missing record 404s.
"""

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


def test_po_document_reads_work_when_logged_in(
    client, db, make_vendor, make_purchase_order, tmp_path
):
    """A logged-in user can still list, read and download documents."""
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
