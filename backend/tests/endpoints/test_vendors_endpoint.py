"""
Endpoint tests for Vendors API (/api/v1/vendors).

Tests the main CRUD paths:
- GET    /api/v1/vendors/       (list with pagination, search, active_only)
- GET    /api/v1/vendors/{id}   (get single vendor)
- POST   /api/v1/vendors/       (create vendor)
- PUT    /api/v1/vendors/{id}   (update vendor)
- DELETE /api/v1/vendors/{id}   (delete/deactivate vendor)
"""
import uuid

import pytest


BASE = "/api/v1/vendors"


def _uid():
    return uuid.uuid4().hex[:8]


def _create_vendor_via_api(client, **overrides):
    """Helper: create a vendor through the API and return the JSON body."""
    uid = _uid()
    payload = {
        "name": overrides.pop("name", f"Vendor {uid}"),
    }
    payload.update(overrides)
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# =============================================================================
# GET /api/v1/vendors/ — list vendors
# =============================================================================

class TestListVendors:
    """List vendors with pagination, search, and active_only filter."""

    def test_list_returns_200_with_structure(self, client):
        """Response contains 'items' list and 'pagination' dict."""
        _create_vendor_via_api(client)
        resp = client.get(BASE)
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "pagination" in body
        assert isinstance(body["items"], list)
        pag = body["pagination"]
        for key in ("total", "offset", "limit", "returned"):
            assert key in pag

    def test_list_contains_created_vendor(self, client):
        """A freshly created vendor appears in the list."""
        vendor = _create_vendor_via_api(client)
        resp = client.get(BASE)
        assert resp.status_code == 200
        codes = [v["code"] for v in resp.json()["items"]]
        assert vendor["code"] in codes

    def test_list_item_has_expected_fields(self, client):
        """Each list item has the VendorListResponse fields."""
        _create_vendor_via_api(client, contact_name="Alice", email="alice@test.com")
        resp = client.get(BASE)
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        for key in ("id", "code", "name", "contact_name", "email", "phone",
                     "city", "state", "payment_terms", "is_active", "po_count"):
            assert key in item, f"Missing key: {key}"

    def test_list_search_by_name(self, client):
        uid = _uid()
        name = f"SearchVendor-{uid}"
        _create_vendor_via_api(client, name=name)
        resp = client.get(BASE, params={"search": name})
        assert resp.status_code == 200
        assert any(v["name"] == name for v in resp.json()["items"])

    def test_list_search_by_code(self, client):
        uid = _uid()
        code = f"VSRCH-{uid}"
        _create_vendor_via_api(client, code=code)
        resp = client.get(BASE, params={"search": code})
        assert resp.status_code == 200
        assert any(v["code"] == code for v in resp.json()["items"])

    def test_list_active_only_default(self, client, make_vendor, db):
        """Default active_only=True excludes inactive vendors."""
        uid = _uid()
        v = make_vendor(name=f"Inactive-{uid}", code=f"INACT-{uid}")
        v.is_active = False
        db.flush()
        resp = client.get(BASE, params={"search": f"Inactive-{uid}"})
        assert resp.status_code == 200
        assert not any(i["code"] == f"INACT-{uid}" for i in resp.json()["items"])

    def test_list_include_inactive(self, client, make_vendor, db):
        uid = _uid()
        v = make_vendor(name=f"ShowInact-{uid}", code=f"SHINACT-{uid}")
        v.is_active = False
        db.flush()
        resp = client.get(BASE, params={"search": f"ShowInact-{uid}", "active_only": False})
        assert resp.status_code == 200
        assert any(i["code"] == f"SHINACT-{uid}" for i in resp.json()["items"])

    def test_list_pagination(self, client):
        """Limit and offset control result size."""
        for _ in range(3):
            _create_vendor_via_api(client)
        resp = client.get(BASE, params={"limit": 1, "offset": 0})
        assert resp.status_code == 200
        assert resp.json()["pagination"]["returned"] <= 1

    def test_list_search_no_results(self, client):
        resp = client.get(BASE, params={"search": "zzzNonExistent999"})
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["pagination"]["total"] == 0

    def test_list_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(BASE)
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/vendors/{vendor_id} — get single vendor
# =============================================================================

class TestGetVendor:
    """Get a single vendor by ID."""

    def test_get_vendor_success(self, client):
        vendor = _create_vendor_via_api(client, name="GetVendor", contact_name="Bob")
        resp = client.get(f"{BASE}/{vendor['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == vendor["id"]
        assert body["name"] == "GetVendor"
        assert body["contact_name"] == "Bob"
        assert "created_at" in body
        assert "updated_at" in body

    def test_get_vendor_full_response_shape(self, client):
        """Full vendor response has VendorResponse fields."""
        vendor = _create_vendor_via_api(client)
        resp = client.get(f"{BASE}/{vendor['id']}")
        body = resp.json()
        for key in ("id", "code", "name", "is_active", "created_at", "updated_at"):
            assert key in body

    def test_get_vendor_not_found(self, client):
        resp = client.get(f"{BASE}/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_vendor_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE}/1")
        assert resp.status_code == 401


# =============================================================================
# POST /api/v1/vendors/ — create vendor
# =============================================================================

class TestCreateVendor:
    """Create a new vendor."""

    def test_create_returns_201(self, client):
        resp = client.post(BASE, json={"name": f"V201-{_uid()}"})
        assert resp.status_code == 201

    def test_create_auto_generates_code(self, client):
        vendor = _create_vendor_via_api(client)
        assert vendor["code"].startswith("VND-")

    def test_create_with_explicit_code(self, client):
        uid = _uid()
        code = f"CUSTOM-{uid}"
        vendor = _create_vendor_via_api(client, code=code)
        assert vendor["code"] == code

    def test_create_with_all_fields(self, client):
        uid = _uid()
        payload = {
            "name": f"Full Vendor {uid}",
            "code": f"FULL-{uid}",
            "contact_name": "Jane Doe",
            "email": f"jane-{uid}@test.com",
            "phone": "555-1234",
            "website": "https://example.com",
            "address_line1": "123 Main St",
            "city": "Springfield",
            "state": "IL",
            "postal_code": "62701",
            "country": "USA",
            "payment_terms": "Net 30",
            "lead_time_days": 14,
            "notes": "Test notes",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["contact_name"] == "Jane Doe"
        assert body["city"] == "Springfield"
        assert body["payment_terms"] == "Net 30"
        assert body["lead_time_days"] == 14

    def test_create_duplicate_code_fails(self, client):
        uid = _uid()
        code = f"DUP-{uid}"
        _create_vendor_via_api(client, code=code)
        resp = client.post(BASE, json={"name": "Dup", "code": code})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_create_missing_name_returns_422(self, client):
        resp = client.post(BASE, json={})
        assert resp.status_code == 422

    def test_create_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE, json={"name": "NoAuth"})
        assert resp.status_code == 401


# =============================================================================
# PUT /api/v1/vendors/{vendor_id} — update vendor
# =============================================================================

class TestUpdateVendor:
    """Update an existing vendor."""

    def test_update_name(self, client):
        vendor = _create_vendor_via_api(client)
        new_name = f"Updated-{_uid()}"
        resp = client.put(f"{BASE}/{vendor['id']}", json={"name": new_name})
        assert resp.status_code == 200
        assert resp.json()["name"] == new_name

    def test_update_code(self, client):
        vendor = _create_vendor_via_api(client)
        new_code = f"UPD-{_uid()}"
        resp = client.put(f"{BASE}/{vendor['id']}", json={"code": new_code})
        assert resp.status_code == 200
        assert resp.json()["code"] == new_code

    def test_update_contact_and_address(self, client):
        vendor = _create_vendor_via_api(client)
        resp = client.put(f"{BASE}/{vendor['id']}", json={
            "contact_name": "New Contact",
            "phone": "555-9999",
            "city": "Portland",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["contact_name"] == "New Contact"
        assert body["phone"] == "555-9999"
        assert body["city"] == "Portland"

    def test_update_preserves_unchanged_fields(self, client):
        vendor = _create_vendor_via_api(client, contact_name="Original", city="OrigCity")
        resp = client.put(f"{BASE}/{vendor['id']}", json={"phone": "555-0000"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["contact_name"] == "Original"
        assert body["city"] == "OrigCity"
        assert body["phone"] == "555-0000"

    def test_update_not_found(self, client):
        resp = client.put(f"{BASE}/999999", json={"name": "Ghost"})
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_update_duplicate_code_fails(self, client):
        v1 = _create_vendor_via_api(client)
        v2 = _create_vendor_via_api(client)
        resp = client.put(f"{BASE}/{v2['id']}", json={"code": v1["code"]})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    def test_update_same_code_is_ok(self, client):
        """Updating with the same code (no actual change) should succeed."""
        vendor = _create_vendor_via_api(client)
        resp = client.put(f"{BASE}/{vendor['id']}", json={
            "code": vendor["code"],
            "name": "Same Code OK",
        })
        assert resp.status_code == 200

    def test_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.put(f"{BASE}/1", json={"name": "NoAuth"})
        assert resp.status_code == 401


# =============================================================================
# DELETE /api/v1/vendors/{vendor_id} — delete vendor
# =============================================================================

class TestDeleteVendor:
    """Delete a vendor (hard delete without POs, soft delete with POs)."""

    def test_delete_vendor_without_pos(self, client):
        """Vendor with no POs is permanently deleted."""
        vendor = _create_vendor_via_api(client)
        resp = client.delete(f"{BASE}/{vendor['id']}")
        assert resp.status_code == 200
        assert "deleted" in resp.json()["message"].lower()
        # Vendor should be gone
        get_resp = client.get(f"{BASE}/{vendor['id']}")
        assert get_resp.status_code == 404

    def test_soft_delete_vendor_with_pos(self, client, make_vendor, make_purchase_order, db):
        """Vendor with POs is soft-deleted (deactivated, not removed)."""
        uid = _uid()
        vendor = make_vendor(name=f"SoftDel-{uid}", code=f"SDEL-{uid}")
        make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()
        resp = client.delete(f"{BASE}/{vendor.id}")
        assert resp.status_code == 200
        assert "deactivated" in resp.json()["message"].lower()
        # Vendor still exists but is inactive
        get_resp = client.get(f"{BASE}/{vendor.id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["is_active"] is False

    def test_delete_not_found(self, client):
        resp = client.delete(f"{BASE}/999999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_delete_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE}/1")
        assert resp.status_code == 401
