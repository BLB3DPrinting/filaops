"""
Endpoint tests for Work Centers API (/api/v1/work-centers).

Tests the main CRUD paths:
- GET    /api/v1/work-centers/       (list with filters)
- GET    /api/v1/work-centers/{id}   (get by id)
- POST   /api/v1/work-centers/       (create)
- PUT    /api/v1/work-centers/{id}   (update)
- DELETE /api/v1/work-centers/{id}   (soft delete)
"""
import uuid

import pytest


BASE = "/api/v1/work-centers"


def _uid():
    return uuid.uuid4().hex[:8].upper()


def _create_wc_via_api(client, **overrides):
    """Helper: create a work center through the API and return the JSON body."""
    code = f"WC-{_uid()}"
    payload = {
        "code": overrides.pop("code", code),
        "name": overrides.pop("name", f"Work Center {code}"),
        "center_type": overrides.pop("center_type", "machine"),
        "capacity_hours_per_day": overrides.pop("capacity_hours_per_day", "8.0"),
    }
    payload.update(overrides)
    resp = client.post(BASE, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# =============================================================================
# GET /api/v1/work-centers/ — list work centers
# =============================================================================

class TestListWorkCenters:
    """List work centers with filtering."""

    def test_list_returns_200_with_list(self, client):
        """Response is 200 with a JSON list."""
        resp = client.get(BASE)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_includes_seeded_work_center(self, client):
        """Seed data includes work center id=1."""
        resp = client.get(BASE)
        assert resp.status_code == 200
        ids = [wc["id"] for wc in resp.json()]
        assert 1 in ids

    def test_list_includes_created_work_center(self, client):
        wc = _create_wc_via_api(client)
        resp = client.get(BASE)
        assert resp.status_code == 200
        codes = [item["code"] for item in resp.json()]
        assert wc["code"] in codes

    def test_list_filter_by_center_type(self, client):
        """Filter by center_type returns only matching work centers."""
        _create_wc_via_api(client, center_type="labor")
        resp = client.get(BASE, params={"center_type": "labor"})
        assert resp.status_code == 200
        for wc in resp.json():
            assert wc["center_type"] == "labor"

    def test_list_active_only_default(self, client):
        """By default, only active work centers are listed."""
        wc = _create_wc_via_api(client)
        client.delete(f"{BASE}/{wc['id']}")
        resp = client.get(BASE)
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert wc["id"] not in ids

    def test_list_include_inactive(self, client):
        """Setting active_only=false includes inactive work centers."""
        wc = _create_wc_via_api(client)
        client.delete(f"{BASE}/{wc['id']}")
        resp = client.get(BASE, params={"active_only": False})
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.json()]
        assert wc["id"] in ids

    def test_list_response_shape(self, client):
        """Each item in the list has expected WorkCenterListResponse fields."""
        resp = client.get(BASE)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        item = data[0]
        for key in ("id", "code", "name", "center_type", "total_rate_per_hour",
                     "resource_count", "is_bottleneck", "is_active"):
            assert key in item, f"Missing key: {key}"

    def test_list_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(BASE)
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/work-centers/{wc_id} — get single work center
# =============================================================================

class TestGetWorkCenter:
    """Get a single work center by ID."""

    def test_get_created_work_center(self, client):
        wc = _create_wc_via_api(client)
        resp = client.get(f"{BASE}/{wc['id']}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == wc["id"]
        assert body["code"] == wc["code"]
        assert "resource_count" in body
        assert "total_rate_per_hour" in body

    def test_get_full_response_shape(self, client):
        """Full response has WorkCenterResponse fields."""
        wc = _create_wc_via_api(client)
        resp = client.get(f"{BASE}/{wc['id']}")
        body = resp.json()
        for key in ("id", "code", "name", "center_type", "capacity_hours_per_day",
                     "machine_rate_per_hour", "labor_rate_per_hour", "overhead_rate_per_hour",
                     "is_bottleneck", "scheduling_priority", "is_active",
                     "created_at", "updated_at", "resource_count", "total_rate_per_hour"):
            assert key in body, f"Missing key: {key}"

    def test_get_not_found(self, client):
        resp = client.get(f"{BASE}/999999")
        assert resp.status_code == 404

    def test_get_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE}/1")
        assert resp.status_code == 401


# =============================================================================
# POST /api/v1/work-centers/ — create work center
# =============================================================================

class TestCreateWorkCenter:
    """Create a new work center."""

    def test_create_success(self, client):
        code = f"WC-{_uid()}"
        payload = {
            "code": code,
            "name": f"New WC {code}",
            "center_type": "machine",
            "capacity_hours_per_day": "16.0",
            "machine_rate_per_hour": "25.00",
            "labor_rate_per_hour": "15.00",
            "overhead_rate_per_hour": "5.00",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 201
        body = resp.json()
        assert body["code"] == code
        assert body["center_type"] == "machine"
        assert "id" in body
        assert "created_at" in body

    def test_create_minimal_fields(self, client):
        """Only code and name are required; center_type defaults to station."""
        code = f"WC-{_uid()}"
        resp = client.post(BASE, json={"code": code, "name": f"Minimal {code}"})
        assert resp.status_code == 201
        assert resp.json()["center_type"] == "station"

    def test_create_all_center_types(self, client):
        """All three center_type values are accepted."""
        for ct in ("machine", "station", "labor"):
            code = f"WC-{_uid()}"
            resp = client.post(BASE, json={
                "code": code, "name": f"Type {ct}", "center_type": ct,
            })
            assert resp.status_code == 201, f"Failed for center_type={ct}"
            assert resp.json()["center_type"] == ct

    def test_create_duplicate_code_fails(self, client):
        wc = _create_wc_via_api(client)
        payload = {
            "code": wc["code"],
            "name": "Duplicate",
            "center_type": "machine",
        }
        resp = client.post(BASE, json=payload)
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_create_with_rates_computes_total(self, client):
        """Creating with rates should give a computed total_rate_per_hour."""
        code = f"WC-{_uid()}"
        resp = client.post(BASE, json={
            "code": code,
            "name": f"Rated {code}",
            "center_type": "machine",
            "machine_rate_per_hour": "10.00",
            "labor_rate_per_hour": "20.00",
            "overhead_rate_per_hour": "5.00",
        })
        assert resp.status_code == 201
        assert float(resp.json()["total_rate_per_hour"]) == pytest.approx(35.0, abs=0.01)

    def test_create_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE, json={
            "code": "NOAUTH", "name": "No Auth", "center_type": "machine",
        })
        assert resp.status_code == 401


# =============================================================================
# PUT /api/v1/work-centers/{wc_id} — update work center
# =============================================================================

class TestUpdateWorkCenter:
    """Update an existing work center."""

    def test_update_name(self, client):
        wc = _create_wc_via_api(client)
        resp = client.put(f"{BASE}/{wc['id']}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_center_type(self, client):
        wc = _create_wc_via_api(client, center_type="machine")
        resp = client.put(f"{BASE}/{wc['id']}", json={"center_type": "labor"})
        assert resp.status_code == 200
        assert resp.json()["center_type"] == "labor"

    def test_update_rates_and_total(self, client):
        """Updating rates recalculates total_rate_per_hour."""
        wc = _create_wc_via_api(client)
        resp = client.put(f"{BASE}/{wc['id']}", json={
            "machine_rate_per_hour": "30.00",
            "labor_rate_per_hour": "20.00",
            "overhead_rate_per_hour": "10.00",
        })
        assert resp.status_code == 200
        assert float(resp.json()["total_rate_per_hour"]) == pytest.approx(60.0, abs=0.01)

    def test_update_not_found(self, client):
        resp = client.put(f"{BASE}/999999", json={"name": "Ghost"})
        assert resp.status_code == 404

    def test_update_duplicate_code_fails(self, client):
        wc1 = _create_wc_via_api(client)
        wc2 = _create_wc_via_api(client)
        resp = client.put(f"{BASE}/{wc2['id']}", json={"code": wc1["code"]})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"]

    def test_update_same_code_is_ok(self, client):
        """Updating a work center with its own existing code should succeed."""
        wc = _create_wc_via_api(client)
        resp = client.put(f"{BASE}/{wc['id']}", json={"code": wc["code"]})
        assert resp.status_code == 200

    def test_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.put(f"{BASE}/1", json={"name": "NoAuth"})
        assert resp.status_code == 401


# =============================================================================
# DELETE /api/v1/work-centers/{wc_id} — soft delete
# =============================================================================

class TestDeleteWorkCenter:
    """Soft-delete a work center (sets is_active=False)."""

    def test_delete_returns_204(self, client):
        wc = _create_wc_via_api(client)
        resp = client.delete(f"{BASE}/{wc['id']}")
        assert resp.status_code == 204

    def test_delete_deactivates(self, client):
        """After soft-delete, work center is inactive but still retrievable."""
        wc = _create_wc_via_api(client)
        client.delete(f"{BASE}/{wc['id']}")
        resp = client.get(f"{BASE}/{wc['id']}")
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    def test_delete_not_found(self, client):
        resp = client.delete(f"{BASE}/999999")
        assert resp.status_code == 404

    def test_delete_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE}/1")
        assert resp.status_code == 401
