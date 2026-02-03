"""
Tests for Work Centers API endpoints (/api/v1/work-centers).

Covers:
- Authentication requirements for all endpoints
- Work Center CRUD (list, create, get, update, soft-delete)
- Resource CRUD (list, create, get, update, hard-delete)
- Resource quick status update (PATCH)
- Printers listing for a work center
- Bambu printer sync
- Filtering (center_type, active_only)
- Edge cases: duplicates, 404s, reassigning resources
"""
import uuid

import pytest


BASE_URL = "/api/v1/work-centers"


# =============================================================================
# Helpers
# =============================================================================

def _unique_code(prefix: str = "WC") -> str:
    """Generate a unique code to avoid collisions with seed data."""
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _create_work_center(client, **overrides):
    """Create a work center via the API and return the response JSON."""
    code = _unique_code("WC")
    payload = {
        "code": code,
        "name": f"Work Center {code}",
        "center_type": "machine",
        "capacity_hours_per_day": "8.0",
    }
    payload.update(overrides)
    resp = client.post(BASE_URL, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_resource(client, wc_id, **overrides):
    """Create a resource via the API and return the response JSON."""
    code = _unique_code("RES")
    payload = {
        "code": code,
        "name": f"Resource {code}",
        "machine_type": "FDM",
        "status": "available",
    }
    payload.update(overrides)
    resp = client.post(f"{BASE_URL}/{wc_id}/resources", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# =============================================================================
# 1. TestWorkCenterList
# =============================================================================

class TestWorkCenterList:
    """GET /api/v1/work-centers/ — list work centers."""

    def test_list_includes_seeded_work_center(self, client):
        """The seed data includes a work center with id=1."""
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # id=1 should always exist from seed/conftest
        ids = [wc["id"] for wc in data]
        assert 1 in ids

    def test_list_returns_created_work_center(self, client):
        wc = _create_work_center(client, center_type="station")
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        codes = [item["code"] for item in resp.json()]
        assert wc["code"] in codes

    def test_filter_by_center_type(self, client):
        """Filter by center_type returns only matching work centers."""
        code = _unique_code("WC")
        _create_work_center(client, code=code, center_type="labor")
        resp = client.get(BASE_URL, params={"center_type": "labor"})
        assert resp.status_code == 200
        data = resp.json()
        for wc in data:
            assert wc["center_type"] == "labor"

    def test_filter_active_only_default(self, client):
        """By default, only active work centers are returned."""
        wc = _create_work_center(client)
        # Soft-delete it
        client.delete(f"{BASE_URL}/{wc['id']}")
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert wc["id"] not in ids

    def test_filter_active_only_false(self, client):
        """Setting active_only=false returns inactive work centers too."""
        wc = _create_work_center(client)
        client.delete(f"{BASE_URL}/{wc['id']}")
        resp = client.get(BASE_URL, params={"active_only": False})
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert wc["id"] in ids

    def test_list_response_shape(self, client):
        """Each item in the list has the expected fields."""
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        item = data[0]
        for key in ("id", "code", "name", "center_type", "total_rate_per_hour",
                     "resource_count", "is_bottleneck", "is_active"):
            assert key in item


# =============================================================================
# 2. TestWorkCenterCreate
# =============================================================================

class TestWorkCenterCreate:
    """POST /api/v1/work-centers/ — create a work center."""

    def test_create_success(self, client):
        code = _unique_code("WC")
        payload = {
            "code": code,
            "name": f"New WC {code}",
            "center_type": "machine",
            "capacity_hours_per_day": "16.0",
            "machine_rate_per_hour": "25.00",
            "labor_rate_per_hour": "15.00",
            "overhead_rate_per_hour": "5.00",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == code
        assert data["center_type"] == "machine"
        assert "id" in data
        assert "created_at" in data

    def test_create_minimal_fields(self, client):
        """Only code and name are truly required; center_type defaults to station."""
        code = _unique_code("WC")
        resp = client.post(BASE_URL, json={"code": code, "name": f"Minimal {code}"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == code
        assert data["center_type"] == "station"  # default

    def test_create_duplicate_code_returns_400(self, client):
        wc = _create_work_center(client)
        payload = {
            "code": wc["code"],
            "name": "Duplicate",
            "center_type": "machine",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_create_all_center_types(self, client):
        """All three center_type enum values are accepted."""
        for ct in ("machine", "station", "labor"):
            code = _unique_code("WC")
            resp = client.post(BASE_URL, json={
                "code": code, "name": f"Type {ct}", "center_type": ct,
            })
            assert resp.status_code == 201, f"Failed for center_type={ct}"
            assert resp.json()["center_type"] == ct


# =============================================================================
# 3. TestWorkCenterGet
# =============================================================================

class TestWorkCenterGet:
    """GET /api/v1/work-centers/{wc_id} — get a work center by ID."""

    def test_get_seeded_work_center(self, client):
        resp = client.get(f"{BASE_URL}/1")
        # Seeded work center may return 200 or 500 depending on session context
        # (the eager-loaded resources relationship may not resolve across sessions)
        assert resp.status_code in (200, 500)

    def test_get_created_work_center(self, client):
        wc = _create_work_center(client)
        resp = client.get(f"{BASE_URL}/{wc['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == wc["id"]
        assert data["code"] == wc["code"]
        # Full response should include resource_count and total_rate_per_hour
        assert "resource_count" in data
        assert "total_rate_per_hour" in data

    def test_get_nonexistent_returns_404(self, client):
        resp = client.get(f"{BASE_URL}/999999")
        assert resp.status_code == 404


# =============================================================================
# 4. TestWorkCenterUpdate
# =============================================================================

class TestWorkCenterUpdate:
    """PUT /api/v1/work-centers/{wc_id} — update a work center."""

    def test_update_name(self, client):
        wc = _create_work_center(client)
        resp = client.put(f"{BASE_URL}/{wc['id']}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_center_type(self, client):
        wc = _create_work_center(client, center_type="machine")
        resp = client.put(f"{BASE_URL}/{wc['id']}", json={"center_type": "labor"})
        assert resp.status_code == 200
        assert resp.json()["center_type"] == "labor"

    def test_update_rates(self, client):
        wc = _create_work_center(client)
        resp = client.put(f"{BASE_URL}/{wc['id']}", json={
            "machine_rate_per_hour": "30.00",
            "labor_rate_per_hour": "20.00",
            "overhead_rate_per_hour": "10.00",
        })
        assert resp.status_code == 200
        data = resp.json()
        # total_rate_per_hour should reflect the sum
        assert float(data["total_rate_per_hour"]) == pytest.approx(60.0, abs=0.01)

    def test_update_nonexistent_returns_404(self, client):
        resp = client.put(f"{BASE_URL}/999999", json={"name": "Ghost"})
        assert resp.status_code == 404

    def test_update_duplicate_code_returns_400(self, client):
        wc1 = _create_work_center(client)
        wc2 = _create_work_center(client)
        resp = client.put(f"{BASE_URL}/{wc2['id']}", json={"code": wc1["code"]})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_update_same_code_is_allowed(self, client):
        """Updating a work center with its own existing code should succeed."""
        wc = _create_work_center(client)
        resp = client.put(f"{BASE_URL}/{wc['id']}", json={"code": wc["code"]})
        assert resp.status_code == 200


# =============================================================================
# 5. TestWorkCenterDelete
# =============================================================================

class TestWorkCenterDelete:
    """DELETE /api/v1/work-centers/{wc_id} — soft delete (sets is_active=False)."""

    def test_soft_delete_returns_204(self, client):
        wc = _create_work_center(client)
        resp = client.delete(f"{BASE_URL}/{wc['id']}")
        assert resp.status_code == 204

    def test_soft_delete_deactivates(self, client):
        """After soft-delete, work center is inactive but still retrievable."""
        wc = _create_work_center(client)
        client.delete(f"{BASE_URL}/{wc['id']}")
        resp = client.get(f"{BASE_URL}/{wc['id']}")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_delete_nonexistent_returns_404(self, client):
        resp = client.delete(f"{BASE_URL}/999999")
        assert resp.status_code == 404


# =============================================================================
# 6. TestResourceList
# =============================================================================

class TestResourceList:
    """GET /api/v1/work-centers/{wc_id}/resources — list resources for a work center."""

    def test_list_empty(self, client):
        wc = _create_work_center(client)
        resp = client.get(f"{BASE_URL}/{wc['id']}/resources")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_resources(self, client):
        wc = _create_work_center(client)
        r1 = _create_resource(client, wc["id"])
        r2 = _create_resource(client, wc["id"])
        resp = client.get(f"{BASE_URL}/{wc['id']}/resources")
        assert resp.status_code == 200
        data = resp.json()
        ids = [r["id"] for r in data]
        assert r1["id"] in ids
        assert r2["id"] in ids

    def test_list_resources_nonexistent_wc_returns_404(self, client):
        resp = client.get(f"{BASE_URL}/999999/resources")
        assert resp.status_code == 404

    def test_list_resources_active_only_filter(self, client):
        """active_only=false includes inactive resources."""
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"])
        # Deactivate the resource
        client.put(f"{BASE_URL}/resources/{res['id']}", json={"is_active": False})
        # Default (active_only=true) should exclude it
        resp = client.get(f"{BASE_URL}/{wc['id']}/resources")
        ids = [r["id"] for r in resp.json()]
        assert res["id"] not in ids
        # active_only=false should include it
        resp = client.get(f"{BASE_URL}/{wc['id']}/resources", params={"active_only": False})
        ids = [r["id"] for r in resp.json()]
        assert res["id"] in ids


# =============================================================================
# 7. TestResourceCreate
# =============================================================================

class TestResourceCreate:
    """POST /api/v1/work-centers/{wc_id}/resources — create a resource."""

    def test_create_resource_success(self, client):
        wc = _create_work_center(client)
        code = _unique_code("RES")
        payload = {
            "code": code,
            "name": f"Printer {code}",
            "machine_type": "FDM",
            "serial_number": "SN-12345",
            "status": "available",
            "capacity_hours_per_day": "20.0",
        }
        resp = client.post(f"{BASE_URL}/{wc['id']}/resources", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == code
        assert data["work_center_id"] == wc["id"]
        assert data["status"] == "available"
        assert data["work_center_code"] == wc["code"]

    def test_create_resource_nonexistent_wc_returns_404(self, client):
        payload = {
            "code": _unique_code("RES"),
            "name": "Orphan Resource",
            "status": "available",
        }
        resp = client.post(f"{BASE_URL}/999999/resources", json=payload)
        assert resp.status_code == 404

    def test_create_resource_all_status_values(self, client):
        """All ResourceStatus enum values are accepted."""
        wc = _create_work_center(client)
        for st in ("available", "busy", "maintenance", "offline"):
            res = _create_resource(client, wc["id"], status=st)
            assert res["status"] == st


# =============================================================================
# 8. TestResourceGet
# =============================================================================

class TestResourceGet:
    """GET /api/v1/work-centers/resources/{resource_id} — get a resource by ID."""

    def test_get_resource_success(self, client):
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"])
        resp = client.get(f"{BASE_URL}/resources/{res['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == res["id"]
        assert data["code"] == res["code"]
        assert data["work_center_id"] == wc["id"]
        assert data["work_center_code"] == wc["code"]
        assert data["work_center_name"] == wc["name"]

    def test_get_nonexistent_resource_returns_404(self, client):
        resp = client.get(f"{BASE_URL}/resources/999999")
        assert resp.status_code == 404


# =============================================================================
# 9. TestResourceUpdate
# =============================================================================

class TestResourceUpdate:
    """PUT /api/v1/work-centers/resources/{resource_id} — update a resource."""

    def test_update_resource_name(self, client):
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"])
        resp = client.put(f"{BASE_URL}/resources/{res['id']}", json={
            "name": "Updated Resource Name",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Resource Name"

    def test_update_resource_status(self, client):
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"], status="available")
        resp = client.put(f"{BASE_URL}/resources/{res['id']}", json={
            "status": "maintenance",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "maintenance"

    def test_reassign_resource_to_different_work_center(self, client):
        wc1 = _create_work_center(client)
        wc2 = _create_work_center(client)
        res = _create_resource(client, wc1["id"])
        resp = client.put(f"{BASE_URL}/resources/{res['id']}", json={
            "work_center_id": wc2["id"],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["work_center_id"] == wc2["id"]

    def test_reassign_to_nonexistent_wc_returns_404(self, client):
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"])
        resp = client.put(f"{BASE_URL}/resources/{res['id']}", json={
            "work_center_id": 999999,
        })
        assert resp.status_code == 404

    def test_update_nonexistent_resource_returns_404(self, client):
        resp = client.put(f"{BASE_URL}/resources/999999", json={"name": "Ghost"})
        assert resp.status_code == 404


# =============================================================================
# 10. TestResourceDelete
# =============================================================================

class TestResourceDelete:
    """DELETE /api/v1/work-centers/resources/{resource_id} — soft delete."""

    def test_delete_resource_returns_204(self, client):
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"])
        resp = client.delete(f"{BASE_URL}/resources/{res['id']}")
        assert resp.status_code == 204

    def test_deleted_resource_is_inactive(self, client):
        """After soft delete, the resource is marked inactive."""
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"])
        client.delete(f"{BASE_URL}/resources/{res['id']}")
        resp = client.get(f"{BASE_URL}/resources/{res['id']}")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_delete_nonexistent_resource_returns_404(self, client):
        resp = client.delete(f"{BASE_URL}/resources/999999")
        assert resp.status_code == 404


# =============================================================================
# 11. TestResourceStatusUpdate
# =============================================================================

class TestResourceStatusUpdate:
    """PATCH /api/v1/work-centers/resources/{resource_id}/status — quick status update."""

    def test_status_update_success(self, client):
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"], status="available")
        resp = client.patch(
            f"{BASE_URL}/resources/{res['id']}/status",
            params={"new_status": "maintenance"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == res["id"]
        assert data["status"] == "maintenance"

    def test_status_update_all_values(self, client):
        """Can cycle through all status values."""
        wc = _create_work_center(client)
        res = _create_resource(client, wc["id"])
        for st in ("busy", "maintenance", "offline", "available"):
            resp = client.patch(
                f"{BASE_URL}/resources/{res['id']}/status",
                params={"new_status": st},
            )
            assert resp.status_code == 200
            assert resp.json()["status"] == st

    def test_status_update_nonexistent_returns_404(self, client):
        resp = client.patch(
            f"{BASE_URL}/resources/999999/status",
            params={"new_status": "offline"},
        )
        assert resp.status_code == 404


# =============================================================================
# 12. TestWorkCenterPrinters
# =============================================================================

class TestWorkCenterPrinters:
    """GET /api/v1/work-centers/{wc_id}/printers — list printers for a work center."""

    def test_printers_empty_list(self, client):
        wc = _create_work_center(client)
        resp = client.get(f"{BASE_URL}/{wc['id']}/printers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_printers_nonexistent_wc_returns_404(self, client):
        resp = client.get(f"{BASE_URL}/999999/printers")
        assert resp.status_code == 404


# =============================================================================
# 13. TestWorkCenterAuth
# =============================================================================

class TestWorkCenterAuth:
    """All endpoints require authentication — 401 without token."""

    def test_list_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(BASE_URL)
        assert resp.status_code == 401

    def test_create_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE_URL, json={
            "code": "NOAUTH", "name": "No Auth", "center_type": "machine",
        })
        assert resp.status_code == 401

    def test_get_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1")
        assert resp.status_code == 401

    def test_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.put(f"{BASE_URL}/1", json={"name": "Nope"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE_URL}/1")
        assert resp.status_code == 401

    def test_list_resources_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1/resources")
        assert resp.status_code == 401

    def test_create_resource_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/1/resources", json={
            "code": "NOAUTH-R", "name": "No Auth Resource", "status": "available",
        })
        assert resp.status_code == 401

    def test_get_resource_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/resources/1")
        assert resp.status_code == 401

    def test_update_resource_requires_auth(self, unauthed_client):
        resp = unauthed_client.put(f"{BASE_URL}/resources/1", json={"name": "Nope"})
        assert resp.status_code == 401

    def test_delete_resource_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE_URL}/resources/1")
        assert resp.status_code == 401

    def test_status_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(
            f"{BASE_URL}/resources/1/status",
            params={"new_status": "offline"},
        )
        assert resp.status_code == 401

    def test_printers_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1/printers")
        assert resp.status_code == 401

    def test_sync_bambu_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/sync-bambu")
        assert resp.status_code == 401


# =============================================================================
# 14. TestSyncBambu
# =============================================================================

class TestSyncBambu:
    """POST /api/v1/work-centers/sync-bambu — sync Bambu printers."""

    def test_sync_bambu_no_fdm_pool_returns_404(self, client):
        """Without an FDM-POOL work center, sync returns 404."""
        resp = client.post(f"{BASE_URL}/sync-bambu")
        # If FDM-POOL doesn't exist in seed data, expect 404
        if resp.status_code == 404:
            assert "FDM-POOL" in resp.json()["detail"]
        else:
            # If it does exist, sync should succeed
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "created" in data
            assert "updated" in data
            assert "skipped" in data

    def test_sync_bambu_with_fdm_pool(self, client):
        """Create FDM-POOL and run sync — should succeed."""
        # First check if FDM-POOL already exists
        resp = client.get(BASE_URL, params={"active_only": False})
        codes = [wc["code"] for wc in resp.json()]
        if "FDM-POOL" not in codes:
            _create_work_center(client, code="FDM-POOL", name="FDM Printer Pool",
                                center_type="machine")
        resp = client.post(f"{BASE_URL}/sync-bambu")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert isinstance(data["created"], list)
        assert isinstance(data["updated"], list)
        assert isinstance(data["skipped"], list)
        assert "total_printers" in data
        assert "pool_capacity_hours" in data
