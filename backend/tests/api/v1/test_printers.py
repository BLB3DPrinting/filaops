"""
Tests for Printers API endpoints (/api/v1/printers).

Covers:
- Authentication requirements for all endpoints
- CRUD operations (create, read, update, delete)
- List printers with filtering (search, brand, active_only, status)
- Generate printer code
- Supported brands info
- Active work tracking
- Status updates
- CSV import (via JSON body)
- Network discovery, probe-ip, test-connection (accept 200 or 500)
- Edge cases: duplicates, 404s, invalid data
"""
import uuid

import pytest


BASE_URL = "/api/v1/printers"


# =============================================================================
# Helper: create a printer via the API
# =============================================================================

def _create_printer(client, **overrides):
    """Create a printer and return the response JSON.

    Accepts 200/201 as success, or 403 if the free-tier resource limit is hit.
    """
    uid = uuid.uuid4().hex[:6]
    payload = {
        "code": f"PRT-T{uid}",
        "name": f"Test Printer {uid}",
        "brand": "generic",
        "model": "Test Model",
        "ip_address": f"192.168.1.{hash(uid) % 254 + 1}",
        "location": "Test Lab",
        "active": True,
    }
    payload.update(overrides)
    response = client.post(BASE_URL, json=payload)
    assert response.status_code in (200, 201, 403), response.text
    return response.json()


# =============================================================================
# Authentication
# =============================================================================

class TestPrintersAuth:
    """All endpoints require authentication."""

    def test_list_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(BASE_URL)
        assert resp.status_code == 401

    def test_get_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1")
        assert resp.status_code == 401

    def test_create_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(BASE_URL, json={
            "code": "PRT-AUTH", "name": "X", "model": "Y", "brand": "generic",
        })
        assert resp.status_code == 401

    def test_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.put(f"{BASE_URL}/1", json={"name": "Updated"})
        assert resp.status_code == 401

    def test_delete_requires_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE_URL}/1")
        assert resp.status_code == 401

    def test_status_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(f"{BASE_URL}/1/status", json={"status": "idle"})
        assert resp.status_code == 401

    def test_generate_code_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/generate-code")
        assert resp.status_code == 401

    def test_brands_info_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/brands/info")
        assert resp.status_code == 401

    def test_active_work_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/active-work")
        assert resp.status_code == 401

    def test_discover_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/discover", json={})
        assert resp.status_code == 401

    def test_csv_import_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": "code,name,model\nPRT-001,X,Y",
        })
        assert resp.status_code == 401


# =============================================================================
# Generate Code
# =============================================================================

class TestGenerateCode:
    """GET /generate-code returns a unique PRT-NNN code."""

    def test_generate_code_default_prefix(self, client):
        resp = client.get(f"{BASE_URL}/generate-code")
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data
        assert data["code"].startswith("PRT-")

    def test_generate_code_custom_prefix(self, client):
        resp = client.get(f"{BASE_URL}/generate-code", params={"prefix": "BAM"})
        assert resp.status_code == 200
        assert resp.json()["code"].startswith("BAM-")

    def test_generate_code_increments(self, client):
        """Creating a printer then generating a code should increment."""
        printer = _create_printer(client, code="PRT-050")
        if "id" not in printer:
            pytest.skip("Could not create printer (tier limit)")

        resp = client.get(f"{BASE_URL}/generate-code")
        assert resp.status_code == 200
        code = resp.json()["code"]
        # The generated code should be greater than PRT-050
        num = int(code.split("-")[1])
        assert num >= 51


# =============================================================================
# Brands Info
# =============================================================================

class TestBrandsInfo:
    """GET /brands/info returns supported printer brands."""

    def test_brands_info_returns_list(self, client):
        resp = client.get(f"{BASE_URL}/brands/info")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_brands_info_structure(self, client):
        resp = client.get(f"{BASE_URL}/brands/info")
        assert resp.status_code == 200
        brand = resp.json()[0]
        assert "code" in brand
        assert "name" in brand
        assert "supports_discovery" in brand
        assert "models" in brand
        assert "connection_fields" in brand


# =============================================================================
# Active Work
# =============================================================================

class TestActiveWork:
    """GET /active-work returns printer-to-work mapping."""

    def test_active_work_empty(self, client):
        resp = client.get(f"{BASE_URL}/active-work")
        assert resp.status_code == 200
        data = resp.json()
        assert "printers" in data
        assert isinstance(data["printers"], dict)


# =============================================================================
# CRUD Operations
# =============================================================================

class TestPrinterCreate:
    """POST / creates a new printer."""

    def test_create_printer_success(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")
        assert printer["brand"] == "generic"
        assert printer["model"] == "Test Model"
        assert printer["status"] == "offline"
        assert printer["active"] is True

    def test_create_printer_all_fields(self, client):
        uid = uuid.uuid4().hex[:6]
        payload = {
            "code": f"PRT-FULL-{uid}",
            "name": f"Full Printer {uid}",
            "brand": "bambulab",
            "model": "X1 Carbon",
            "serial_number": f"SN-{uid}",
            "ip_address": "10.0.0.50",
            "mqtt_topic": f"device/{uid}/report",
            "location": "Print Farm Bay 3",
            "work_center_id": 1,
            "notes": "Test notes",
            "active": True,
        }
        resp = client.post(BASE_URL, json=payload)
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["brand"] == "bambulab"
        assert data["serial_number"] == f"SN-{uid}"
        assert data["mqtt_topic"] == f"device/{uid}/report"
        assert data["work_center_id"] == 1
        assert data["notes"] == "Test notes"

    def test_create_printer_duplicate_code(self, client):
        uid = uuid.uuid4().hex[:6]
        code = f"PRT-DUP-{uid}"
        first = _create_printer(client, code=code)
        if "id" not in first:
            pytest.skip("Tier limit reached")

        resp = client.post(BASE_URL, json={
            "code": code, "name": "Dup", "model": "M", "brand": "generic",
        })
        # Should be 400 (duplicate) or 403 (tier limit)
        assert resp.status_code in (400, 403)

    def test_create_printer_missing_required_fields(self, client):
        resp = client.post(BASE_URL, json={"name": "No Code"})
        assert resp.status_code == 422

    def test_create_printer_invalid_brand(self, client):
        resp = client.post(BASE_URL, json={
            "code": "PRT-BAD", "name": "Bad", "model": "M", "brand": "nonexistent",
        })
        assert resp.status_code == 422


class TestPrinterRead:
    """GET /{id} and GET / for reading printers."""

    def test_get_printer_by_id(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.get(f"{BASE_URL}/{printer['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == printer["id"]
        assert data["code"] == printer["code"]
        assert data["name"] == printer["name"]

    def test_get_printer_not_found(self, client):
        resp = client.get(f"{BASE_URL}/999999")
        assert resp.status_code == 404

    def test_list_printers_default(self, client):
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data

    def test_list_printers_pagination(self, client):
        resp = client.get(BASE_URL, params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2


class TestPrinterFilters:
    """GET / with filter parameters."""

    def test_filter_by_brand(self, client):
        _create_printer(client, code=f"PRT-FB-{uuid.uuid4().hex[:6]}", brand="bambulab")
        resp = client.get(BASE_URL, params={"brand": "bambulab"})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["brand"] == "bambulab"

    def test_filter_by_search(self, client):
        uid = uuid.uuid4().hex[:6]
        name = f"UniqueSearchable-{uid}"
        printer = _create_printer(client, code=f"PRT-SR-{uid}", name=name)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.get(BASE_URL, params={"search": name})
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(p["name"] == name for p in items)

    def test_filter_active_only_default(self, client):
        """Default is active_only=True, so inactive printers should not appear."""
        uid = uuid.uuid4().hex[:6]
        printer = _create_printer(client, code=f"PRT-IA-{uid}", active=False)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["items"]]
        assert printer["id"] not in ids

    def test_filter_active_only_false(self, client):
        """active_only=false should include inactive printers."""
        uid = uuid.uuid4().hex[:6]
        printer = _create_printer(client, code=f"PRT-AF-{uid}", active=False)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.get(BASE_URL, params={"active_only": "false"})
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["items"]]
        assert printer["id"] in ids

    def test_filter_by_status(self, client):
        resp = client.get(BASE_URL, params={"status": "offline", "active_only": "false"})
        assert resp.status_code == 200

    def test_filter_invalid_brand_returns_422(self, client):
        resp = client.get(BASE_URL, params={"brand": "nonexistent"})
        assert resp.status_code == 422


class TestPrinterUpdate:
    """PUT /{id} updates an existing printer."""

    def test_update_printer_name(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{BASE_URL}/{printer['id']}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_update_printer_brand_to_core_brand(self, client):
        """Changing to a Core brand (bambulab ↔ generic) is always allowed."""
        printer = _create_printer(client, brand="bambulab")
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{BASE_URL}/{printer['id']}", json={"brand": "generic"})
        assert resp.status_code == 200
        assert resp.json()["brand"] == "generic"

    def test_update_printer_brand_to_pro_brand_forbidden(self, client):
        """
        Changing to a non-Core brand (klipper/octoprint/prusa/creality) must
        be rejected on Core tier when no PRO plugin has registered the brand.
        This is the mechanical half of the freemium gate — without it, the
        UI brand filter is security theater and any curl can bypass.
        """
        printer = _create_printer(client, brand="bambulab")
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{BASE_URL}/{printer['id']}", json={"brand": "klipper"})
        assert resp.status_code == 403
        assert "klipper" in resp.json()["detail"].lower()
        assert "pro" in resp.json()["detail"].lower()

    def test_update_printer_not_found(self, client):
        resp = client.put(f"{BASE_URL}/999999", json={"name": "Ghost"})
        assert resp.status_code == 404

    def test_update_printer_duplicate_code(self, client):
        uid1, uid2 = uuid.uuid4().hex[:6], uuid.uuid4().hex[:6]
        p1 = _create_printer(client, code=f"PRT-U1-{uid1}")
        p2 = _create_printer(client, code=f"PRT-U2-{uid2}")
        if "id" not in p1 or "id" not in p2:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{BASE_URL}/{p2['id']}", json={"code": p1["code"]})
        assert resp.status_code == 400


class TestPrinterDelete:
    """DELETE /{id} removes a printer."""

    def test_delete_printer_success(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.delete(f"{BASE_URL}/{printer['id']}")
        assert resp.status_code == 200
        assert "deleted" in resp.json().get("message", "").lower()

        # Confirm it is gone
        resp = client.get(f"{BASE_URL}/{printer['id']}")
        assert resp.status_code == 404

    def test_delete_printer_not_found(self, client):
        resp = client.delete(f"{BASE_URL}/999999")
        assert resp.status_code == 404


# =============================================================================
# Status Updates
# =============================================================================

class TestPrinterStatusUpdate:
    """PATCH /{id}/status updates printer status."""

    def test_set_status_idle(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.patch(
            f"{BASE_URL}/{printer['id']}/status",
            json={"status": "idle"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "idle"

    def test_set_status_printing(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.patch(
            f"{BASE_URL}/{printer['id']}/status",
            json={"status": "printing"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "printing"

    def test_set_status_error(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.patch(
            f"{BASE_URL}/{printer['id']}/status",
            json={"status": "error"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_status_update_not_found(self, client):
        resp = client.patch(
            f"{BASE_URL}/999999/status",
            json={"status": "idle"},
        )
        assert resp.status_code == 404

    def test_status_update_invalid_status(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.patch(
            f"{BASE_URL}/{printer['id']}/status",
            json={"status": "flying"},
        )
        assert resp.status_code == 422


# =============================================================================
# CSV Import
# =============================================================================

class TestCSVImport:
    """POST /import-csv imports printers from CSV data (JSON body)."""

    def test_import_csv_success(self, client):
        uid = uuid.uuid4().hex[:6]
        csv_data = (
            "code,name,model,brand,ip_address,location\n"
            f"PRT-CSV-{uid},CSV Printer,Model X,generic,192.168.99.10,Lab A"
        )
        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data,
            "skip_duplicates": True,
        })
        # Could be 403 if tier limit is hit
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 1
        assert data["imported"] == 1
        assert data["skipped"] == 0
        assert data["errors"] == []

    def test_import_csv_skip_duplicates(self, client):
        uid = uuid.uuid4().hex[:6]
        code = f"PRT-DUP-{uid}"
        csv_data = f"code,name,model\n{code},First,M1"

        # Import once
        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data, "skip_duplicates": True,
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code == 200

        # Import same code again with skip_duplicates=True
        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data, "skip_duplicates": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] == 1
        assert data["imported"] == 0

    def test_import_csv_duplicate_error(self, client):
        uid = uuid.uuid4().hex[:6]
        code = f"PRT-DE-{uid}"
        csv_data = f"code,name,model\n{code},First,M1"

        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data, "skip_duplicates": False,
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code == 200

        # Import again with skip_duplicates=False -> should report error
        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data, "skip_duplicates": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["errors"]) == 1
        assert "already exists" in data["errors"][0]["error"]

    def test_import_csv_missing_required_field(self, client):
        csv_data = "code,name\nPRT-NOMODEL,Only Name"
        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data,
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 0
        assert len(data["errors"]) == 1
        assert "Missing required field" in data["errors"][0]["error"]

    def test_import_csv_multiple_rows(self, client):
        """Multi-row CSV import with only Core brands imports all rows."""
        uid = uuid.uuid4().hex[:6]
        csv_data = (
            "code,name,model,brand\n"
            f"PRT-M1-{uid},Printer A,Mod A,generic\n"
            f"PRT-M2-{uid},Printer B,Mod B,bambulab\n"
            f"PRT-M3-{uid},Printer C,Mod C,generic"
        )
        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data, "skip_duplicates": True,
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 3
        # Some may fail due to tier limit, but total_rows should be 3
        assert data["imported"] + data["skipped"] + len(data["errors"]) == 3

    def test_import_csv_rejects_pro_brand_row(self, client):
        """
        CSV import enforces the same freemium gate as POST /printers.
        A klipper row in an otherwise-valid CSV becomes a per-row error,
        while core brands import normally. Closes the CSV bypass path CR
        didn't call out but that existed alongside the POST/PUT holes.
        """
        uid = uuid.uuid4().hex[:6]
        csv_data = (
            "code,name,model,brand\n"
            f"PRT-CR1-{uid},Printer A,Mod A,bambulab\n"
            f"PRT-CR2-{uid},Printer B,Mod B,klipper"
        )
        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data, "skip_duplicates": True,
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 2
        # Bambu row succeeds (unless hitting tier limit), klipper row fails
        # the brand gate and becomes a per-row error.
        assert len(data["errors"]) >= 1
        klipper_errors = [
            e for e in data["errors"] if "klipper" in str(e.get("error", "")).lower()
        ]
        assert len(klipper_errors) == 1, f"Expected klipper gate error, got {data['errors']}"

    def test_import_csv_invalid_brand_defaults_to_generic(self, client):
        uid = uuid.uuid4().hex[:6]
        csv_data = f"code,name,model,brand\nPRT-IB-{uid},Printer,Mod,fakebrand"
        resp = client.post(f"{BASE_URL}/import-csv", json={
            "csv_data": csv_data, "skip_duplicates": True,
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1


# =============================================================================
# Network Discovery / Probe / Test Connection
# =============================================================================

class TestNetworkEndpoints:
    """Network-dependent endpoints may not work in test environments.

    We accept 200 or 500 (network unavailable) as valid responses.
    """

    def test_discover_printers(self, client):
        resp = client.post(f"{BASE_URL}/discover", json={
            "timeout_seconds": 1,
        })
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "printers" in data
            assert "scan_duration_seconds" in data

    def test_discover_printers_with_brand_filter(self, client):
        resp = client.post(f"{BASE_URL}/discover", json={
            "timeout_seconds": 1,
            "brands": ["bambulab"],
        })
        assert resp.status_code in (200, 500)

    def test_probe_ip(self, client):
        resp = client.post(
            f"{BASE_URL}/probe-ip",
            params={"ip_address": "192.168.1.1"},
        )
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "ip_address" in data
            assert "reachable" in data

    def test_probe_ip_with_brand_hint(self, client):
        resp = client.post(
            f"{BASE_URL}/probe-ip",
            params={"ip_address": "192.168.1.1", "brand": "bambulab"},
        )
        assert resp.status_code in (200, 500)

    def test_test_connection(self, client):
        resp = client.post(f"{BASE_URL}/test-connection", json={
            "ip_address": "192.168.1.1",
            "brand": "generic",
            "connection_config": {},
        })
        assert resp.status_code in (200, 400, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "success" in data
            assert "message" in data


# =============================================================================
# Edge Cases
# =============================================================================

class TestPrinterEdgeCases:
    """Boundary conditions and edge cases."""

    def test_get_negative_id(self, client):
        resp = client.get(f"{BASE_URL}/-1")
        assert resp.status_code in (404, 422)

    def test_update_with_empty_body(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{BASE_URL}/{printer['id']}", json={})
        # Empty update should still succeed (no fields changed)
        assert resp.status_code == 200

    def test_create_with_core_brands_allowed(self, client):
        """Core brands (bambulab, generic) must always be acceptable."""
        for brand in ["bambulab", "generic"]:
            uid = uuid.uuid4().hex[:6]
            resp = client.post(BASE_URL, json={
                "code": f"PRT-B-{uid}",
                "name": f"Brand Test {uid}",
                "model": "M",
                "brand": brand,
            })
            # 200/201 = created, 403 = tier resource limit (not brand gating).
            # The brand-gating 403 path is covered separately below.
            assert resp.status_code in (200, 201, 403), (
                f"Brand '{brand}' failed with {resp.status_code}: {resp.text}"
            )

    def test_create_with_pro_brands_forbidden(self, client):
        """
        Non-Core brands (klipper, octoprint, prusa, creality) must be
        rejected via 403 when no PRO plugin has called register_brand()
        for them. Matches `_CORE_BRAND_CODES` in
        `app/api/v1/endpoints/printers.py`.

        This is the mechanical freemium gate — a Core-tier install
        shouldn't be able to POST a Klipper printer directly via curl
        even though `PrinterBrand` enum still formally accepts the value.
        """
        for brand in ["klipper", "octoprint", "prusa", "creality"]:
            uid = uuid.uuid4().hex[:6]
            resp = client.post(BASE_URL, json={
                "code": f"PRT-B-{uid}",
                "name": f"Brand Test {uid}",
                "model": "M",
                "brand": brand,
            })
            assert resp.status_code == 403, (
                f"Brand '{brand}' expected 403, got {resp.status_code}: {resp.text}"
            )
            assert brand in resp.json()["detail"].lower()
            assert "pro" in resp.json()["detail"].lower()

    def test_create_with_all_statuses_via_patch(self, client):
        """Verify all valid status values can be set via PATCH."""
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        valid_statuses = ["offline", "idle", "printing", "paused", "error", "maintenance"]
        for status in valid_statuses:
            resp = client.patch(
                f"{BASE_URL}/{printer['id']}/status",
                json={"status": status},
            )
            assert resp.status_code == 200, (
                f"Status '{status}' failed with {resp.status_code}: {resp.text}"
            )
            assert resp.json()["status"] == status

    def test_list_pagination_beyond_results(self, client):
        resp = client.get(BASE_URL, params={"page": 9999, "page_size": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["page"] == 9999
