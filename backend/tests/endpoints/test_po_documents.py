"""SEC-402: PO Document download must require authentication."""

import pytest


def test_po_document_download_requires_auth(unauthed_client):
    """Unauthenticated download request must be rejected with 401 Unauthorized."""
    response = unauthed_client.get("/api/v1/purchase-orders/1/documents/1/download")
    assert response.status_code == 401


def test_po_document_download_authenticated(client):
    """Authenticated user gets 404 for non-existent document, not 401."""
    response = client.get("/api/v1/purchase-orders/9999/documents/9999/download")
    assert response.status_code == 404
