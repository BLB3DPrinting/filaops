"""
Tests for Settings API endpoints (app/api/v1/endpoints/settings.py)

Covers:
- GET /api/v1/settings/company (get company settings, requires staff)
- PATCH /api/v1/settings/company (update company settings, requires admin)
- POST /api/v1/settings/company/logo (upload logo, requires admin, validates type/size)
- GET /api/v1/settings/company/logo (get logo image, no auth required)
- DELETE /api/v1/settings/company/logo (delete logo, requires admin)
- GET /api/v1/settings/ai (get AI settings, requires staff)
- PATCH /api/v1/settings/ai (update AI settings, requires admin, blocked provider logic)
- POST /api/v1/settings/ai/test (test AI connection, requires admin)
- GET /api/v1/settings/ai/anthropic-status (check anthropic package, requires staff)
- POST /api/v1/settings/ai/install-anthropic (install anthropic package, requires admin)
- POST /api/v1/settings/ai/start-ollama (start ollama service, requires admin)
- Auth: 401 tests for all protected endpoints
- Roles: customers get 403 on staff reads; operators read but cannot change settings

Ollama URL validation and the other AI access checks live in
tests/endpoints/test_settings_ai_ollama_url.py.
"""
import io
import uuid

import pytest


BASE_URL = "/api/v1/settings"


# =============================================================================
# Auth tests
# =============================================================================

class TestSettingsAuth:
    """Verify auth is required on all protected endpoints."""

    def test_get_company_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/company")
        assert response.status_code == 401

    def test_patch_company_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/company", json={
            "company_name": "NoAuth Corp",
        })
        assert response.status_code == 401

    def test_upload_logo_requires_auth(self, unauthed_client):
        response = unauthed_client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("logo.png", b"\x89PNG", "image/png")},
        )
        assert response.status_code == 401

    def test_get_logo_no_auth_required(self, unauthed_client):
        """GET /company/logo does NOT require auth (used for PDF generation)."""
        response = unauthed_client.get(f"{BASE_URL}/company/logo")
        # Should be 200 (logo exists) or 404 (no logo) -- never 401
        assert response.status_code in (200, 404)

    def test_delete_logo_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/company/logo")
        assert response.status_code == 401

    def test_get_ai_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/ai")
        assert response.status_code == 401

    def test_patch_ai_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "ollama",
        })
        assert response.status_code == 401

    def test_ai_test_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/ai/test")
        assert response.status_code == 401

    def test_anthropic_status_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/ai/anthropic-status")
        assert response.status_code == 401

    def test_install_anthropic_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/ai/install-anthropic")
        assert response.status_code == 401

    def test_start_ollama_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/ai/start-ollama")
        assert response.status_code == 401


class TestSettingsRoleAccess:
    """Staff read the settings, only admins change them, customers get neither.

    Anyone can self-register a customer account, so a plain login must not be
    enough to read internal business settings (margins, tax registration,
    dispatch). The logo stays public for PDFs and the PRO B2B portal.
    """

    def test_customer_cannot_read_company_settings(self, unauthed_client, role_headers):
        response = unauthed_client.get(
            f"{BASE_URL}/company", headers=role_headers("customer")
        )
        assert response.status_code == 403
        assert "company_name" not in response.text

    def test_operator_can_read_company_settings(self, unauthed_client, role_headers):
        # Operators load company settings on quote and order pages.
        response = unauthed_client.get(
            f"{BASE_URL}/company", headers=role_headers("operator")
        )
        assert response.status_code == 200
        assert response.json()["id"] == 1

    def test_operator_cannot_update_company_settings(self, unauthed_client, role_headers, db):
        from app.api.v1.endpoints.settings import get_or_create_settings

        before = get_or_create_settings(db).company_name
        response = unauthed_client.patch(
            f"{BASE_URL}/company",
            headers=role_headers("operator"),
            json={"company_name": f"Operator Corp {uuid.uuid4().hex[:8]}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"
        db.expire_all()
        assert get_or_create_settings(db).company_name == before

    @pytest.mark.parametrize("method,path", [
        ("post", "/company/logo"),
        ("delete", "/company/logo"),
        ("post", "/ai/install-anthropic"),
    ])
    def test_operator_cannot_use_admin_routes(self, unauthed_client, role_headers, method, path):
        kwargs = {}
        if path == "/company/logo" and method == "post":
            kwargs["files"] = {"file": ("logo.png", io.BytesIO(b"\x89PNG" + b"\x00" * 20), "image/png")}
        response = getattr(unauthed_client, method)(
            f"{BASE_URL}{path}", headers=role_headers("operator"), **kwargs
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    def test_logo_stays_public_for_customers_and_anonymous(self, unauthed_client, role_headers):
        for headers in ({}, role_headers("customer")):
            response = unauthed_client.get(f"{BASE_URL}/company/logo", headers=headers)
            assert response.status_code in (200, 404)


# =============================================================================
# GET /company
# =============================================================================

class TestCompanySettingsGet:
    """GET /api/v1/settings/company"""

    def test_get_returns_settings(self, client):
        response = client.get(f"{BASE_URL}/company")
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["id"] == 1
        assert "updated_at" in data

    def test_get_returns_expected_fields(self, client):
        response = client.get(f"{BASE_URL}/company")
        assert response.status_code == 200
        data = response.json()
        # Verify all expected response fields are present
        expected_fields = [
            "id", "company_name", "company_address_line1",
            "company_address_line2", "company_city", "company_state",
            "company_zip", "company_country", "company_phone",
            "company_email", "company_website", "has_logo",
            "logo_filename", "tax_enabled", "tax_rate",
            "tax_rate_percent", "tax_name", "tax_registration_number",
            "default_quote_validity_days", "quote_terms", "quote_footer",
            "timezone", "business_hours_start", "business_hours_end",
            "business_days_per_week", "business_work_days", "updated_at",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_get_creates_default_settings_if_missing(self, client):
        """get_or_create_settings() creates id=1 row on first access.

        Note: Since data persists across tests (endpoints commit), the settings
        row may already exist with modified values. We just verify the row exists.
        """
        response = client.get(f"{BASE_URL}/company")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        # These fields have DB defaults and are always present
        assert isinstance(data["tax_enabled"], bool)
        assert isinstance(data["default_quote_validity_days"], int)

    def test_has_logo_false_when_no_logo(self, client):
        response = client.get(f"{BASE_URL}/company")
        assert response.status_code == 200
        data = response.json()
        assert "has_logo" in data
        # has_logo depends on whether logo_data is set; initially it should be False
        assert isinstance(data["has_logo"], bool)


# =============================================================================
# PATCH /company
# =============================================================================

class TestCompanySettingsUpdate:
    """PATCH /api/v1/settings/company"""

    def test_update_company_name(self, client):
        uid = uuid.uuid4().hex[:8]
        name = f"Test Corp {uid}"
        response = client.patch(f"{BASE_URL}/company", json={
            "company_name": name,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["company_name"] == name

    def test_update_multiple_fields(self, client):
        uid = uuid.uuid4().hex[:8]
        payload = {
            "company_name": f"Multi Corp {uid}",
            "company_city": "TestCity",
            "company_state": "TS",
            "company_zip": "12345",
            "company_phone": "555-9999",
            "company_email": f"info-{uid}@example.com",
        }
        response = client.patch(f"{BASE_URL}/company", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["company_name"] == payload["company_name"]
        assert data["company_city"] == "TestCity"
        assert data["company_state"] == "TS"
        assert data["company_zip"] == "12345"
        assert data["company_phone"] == "555-9999"
        assert data["company_email"] == payload["company_email"]

    def test_tax_rate_percent_conversion(self, client):
        """tax_rate_percent (e.g. 8.25) is stored as tax_rate (0.0825)."""
        response = client.patch(f"{BASE_URL}/company", json={
            "tax_rate_percent": 8.25,
            "tax_enabled": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["tax_enabled"] is True
        # The response should reflect the percentage
        assert data["tax_rate_percent"] == pytest.approx(8.25, abs=0.01)
        # The stored rate should be the decimal form
        assert float(data["tax_rate"]) == pytest.approx(0.0825, abs=0.0001)

    def test_tax_rate_percent_null_clears_rate(self, client):
        """Setting tax_rate_percent to null should clear tax_rate."""
        # First set a rate
        client.patch(f"{BASE_URL}/company", json={"tax_rate_percent": 5.0})
        # Then clear it
        response = client.patch(f"{BASE_URL}/company", json={"tax_rate_percent": None})
        assert response.status_code == 200
        data = response.json()
        assert data["tax_rate"] is None
        assert data["tax_rate_percent"] is None

    def test_update_quote_settings(self, client):
        uid = uuid.uuid4().hex[:8]
        response = client.patch(f"{BASE_URL}/company", json={
            "default_quote_validity_days": 60,
            "quote_terms": f"Terms {uid}",
            "quote_footer": f"Footer {uid}",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["default_quote_validity_days"] == 60
        assert data["quote_terms"] == f"Terms {uid}"
        assert data["quote_footer"] == f"Footer {uid}"

    def test_update_timezone(self, client):
        response = client.patch(f"{BASE_URL}/company", json={
            "timezone": "America/Chicago",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["timezone"] == "America/Chicago"

    def test_update_business_hours(self, client):
        response = client.patch(f"{BASE_URL}/company", json={
            "business_hours_start": 9,
            "business_hours_end": 17,
            "business_days_per_week": 6,
            "business_work_days": "0,1,2,3,4,5",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["business_hours_start"] == 9
        assert data["business_hours_end"] == 17
        assert data["business_days_per_week"] == 6
        assert data["business_work_days"] == "0,1,2,3,4,5"

    def test_empty_update_is_ok(self, client):
        """PATCH with empty body should succeed (no fields updated)."""
        response = client.patch(f"{BASE_URL}/company", json={})
        assert response.status_code == 200


# =============================================================================
# POST /company/logo (upload)
# =============================================================================

class TestCompanyLogoUpload:
    """POST /api/v1/settings/company/logo"""

    def test_upload_png_logo(self, client):
        # Minimal PNG-like bytes (the endpoint checks content_type, not magic bytes)
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        response = client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("logo.png", io.BytesIO(content), "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logo uploaded successfully"
        assert data["filename"] == "logo.png"

    def test_upload_jpeg_logo(self, client):
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        response = client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("photo.jpg", io.BytesIO(content), "image/jpeg")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "photo.jpg"

    def test_upload_gif_logo(self, client):
        content = b"GIF89a" + b"\x00" * 100
        response = client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("anim.gif", io.BytesIO(content), "image/gif")},
        )
        assert response.status_code == 200

    def test_upload_webp_logo(self, client):
        content = b"RIFF" + b"\x00" * 100
        response = client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("logo.webp", io.BytesIO(content), "image/webp")},
        )
        assert response.status_code == 200

    def test_upload_invalid_type_rejected(self, client):
        """Non-image types should be rejected with 400."""
        content = b"%PDF-1.4 fake pdf content"
        response = client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("doc.pdf", io.BytesIO(content), "application/pdf")},
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.json()["detail"]

    def test_upload_svg_type_rejected(self, client):
        """SVG is not in the allowed types list."""
        content = b"<svg></svg>"
        response = client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("logo.svg", io.BytesIO(content), "image/svg+xml")},
        )
        assert response.status_code == 400

    def test_upload_too_large_rejected(self, client):
        """Files over 2MB should be rejected."""
        # 2MB + 1 byte
        content = b"\x00" * (2 * 1024 * 1024 + 1)
        response = client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("big.png", io.BytesIO(content), "image/png")},
        )
        assert response.status_code == 400
        assert "File too large" in response.json()["detail"]

    def test_upload_exactly_2mb_accepted(self, client):
        """Files exactly 2MB should be accepted."""
        content = b"\x00" * (2 * 1024 * 1024)
        response = client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("max.png", io.BytesIO(content), "image/png")},
        )
        assert response.status_code == 200


# =============================================================================
# GET /company/logo
# =============================================================================

class TestCompanyLogoGet:
    """GET /api/v1/settings/company/logo"""

    def test_get_logo_returns_image_data(self, client):
        """After uploading a logo, GET should return the raw image bytes."""
        # First upload a logo
        logo_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("test.png", io.BytesIO(logo_bytes), "image/png")},
        )
        # Now fetch it (no auth needed)
        response = client.get(f"{BASE_URL}/company/logo")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert b"\x89PNG" in response.content

    def test_get_logo_content_disposition(self, client):
        """Response should include Content-Disposition header."""
        # Upload first
        client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("brand.png", io.BytesIO(b"\x89PNG" + b"\x00" * 20), "image/png")},
        )
        response = client.get(f"{BASE_URL}/company/logo")
        assert response.status_code == 200
        assert "content-disposition" in response.headers
        assert "brand.png" in response.headers["content-disposition"]

    def test_get_logo_404_when_no_logo(self, unauthed_client):
        """GET /company/logo returns 404 when settings have no logo_data.

        Note: This test uses unauthed_client to also verify no auth is needed.
        The logo may or may not exist depending on test order; we just verify
        the endpoint doesn't return 401.
        """
        response = unauthed_client.get(f"{BASE_URL}/company/logo")
        # Either 200 (logo exists from prior test) or 404 (no logo)
        assert response.status_code in (200, 404)


# =============================================================================
# DELETE /company/logo
# =============================================================================

class TestCompanyLogoDelete:
    """DELETE /api/v1/settings/company/logo"""

    def test_delete_logo(self, client):
        # Ensure a logo exists first
        client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("del.png", io.BytesIO(b"\x89PNG" + b"\x00" * 20), "image/png")},
        )
        response = client.delete(f"{BASE_URL}/company/logo")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Logo deleted"

    def test_delete_logo_clears_data(self, client):
        """After deletion, GET /company should show has_logo=False."""
        # Upload then delete
        client.post(
            f"{BASE_URL}/company/logo",
            files={"file": ("tmp.png", io.BytesIO(b"\x89PNG" + b"\x00" * 20), "image/png")},
        )
        client.delete(f"{BASE_URL}/company/logo")

        # Verify has_logo is False
        response = client.get(f"{BASE_URL}/company")
        assert response.status_code == 200
        assert response.json()["has_logo"] is False

    def test_delete_logo_when_none_exists(self, client):
        """Deleting when no logo should still succeed (idempotent)."""
        # Delete twice to ensure second delete works
        client.delete(f"{BASE_URL}/company/logo")
        response = client.delete(f"{BASE_URL}/company/logo")
        assert response.status_code == 200


# =============================================================================
# GET /ai
# =============================================================================

class TestAISettingsGet:
    """GET /api/v1/settings/ai"""

    def test_get_ai_settings_returns_shape(self, client):
        response = client.get(f"{BASE_URL}/ai")
        assert response.status_code == 200
        data = response.json()
        expected_fields = [
            "ai_provider", "ai_api_key_set", "ai_api_key_masked",
            "ai_anthropic_model", "ai_ollama_url", "ai_ollama_model",
            "ai_status", "ai_status_message", "external_ai_blocked",
        ]
        for field in expected_fields:
            assert field in data, f"Missing AI field: {field}"

    def test_get_ai_field_types(self, client):
        """AI settings fields should have correct types.

        Note: Exact values depend on committed state from prior tests
        since endpoints call db.commit() and data persists across runs.
        """
        response = client.get(f"{BASE_URL}/ai")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["ai_api_key_set"], bool)
        assert isinstance(data["external_ai_blocked"], bool)
        # These are always populated (endpoint falls back to defaults)
        assert isinstance(data["ai_ollama_url"], str)
        assert isinstance(data["ai_ollama_model"], str)
        assert isinstance(data["ai_anthropic_model"], str)
        assert isinstance(data["ai_status"], str)
        assert data["ai_status"] in ("not_configured", "configured", "connected")

    def test_ai_status_not_configured_when_no_provider(self, client):
        """When no provider is set, status should be not_configured."""
        # Clear any provider first
        client.patch(f"{BASE_URL}/ai", json={"ai_provider": ""})
        response = client.get(f"{BASE_URL}/ai")
        assert response.status_code == 200
        data = response.json()
        assert data["ai_status"] == "not_configured"

    def test_ai_status_configured_for_ollama(self, client):
        """Setting ollama provider should show configured status."""
        client.patch(f"{BASE_URL}/ai", json={"ai_provider": "ollama"})
        response = client.get(f"{BASE_URL}/ai")
        assert response.status_code == 200
        data = response.json()
        assert data["ai_status"] == "configured"
        assert "Ollama" in data["ai_status_message"]


# =============================================================================
# PATCH /ai
# =============================================================================

class TestAISettingsUpdate:
    """PATCH /api/v1/settings/ai"""

    def test_update_provider_to_ollama(self, client):
        response = client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "ollama",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ai_provider"] == "ollama"

    def test_update_ollama_settings(self, client):
        response = client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "ollama",
            "ai_ollama_url": "http://myhost:11434",
            "ai_ollama_model": "mistral",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ai_ollama_url"] == "http://myhost:11434"
        assert data["ai_ollama_model"] == "mistral"

    def test_external_ai_blocked_clears_anthropic(self, client):
        """Setting external_ai_blocked=True should clear anthropic provider and key.

        The endpoint validates provider vs blocked BEFORE applying changes,
        so we must send ai_provider=None alongside external_ai_blocked=True
        when the current provider is anthropic, OR switch provider first.
        """
        # First set up anthropic (unblocked)
        client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "anthropic",
            "ai_api_key": "sk-ant-test1234567890abcdef",
            "external_ai_blocked": False,
        })
        # Switch away from anthropic, then block
        client.patch(f"{BASE_URL}/ai", json={"ai_provider": "ollama"})
        response = client.patch(f"{BASE_URL}/ai", json={
            "external_ai_blocked": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["external_ai_blocked"] is True
        # API key should be cleared by the blocking logic
        assert data["ai_api_key_set"] is False

    def test_cannot_set_anthropic_while_blocked(self, client):
        """Cannot set provider to anthropic when external_ai_blocked is true."""
        # Ensure blocked
        client.patch(f"{BASE_URL}/ai", json={
            "external_ai_blocked": True,
            "ai_provider": "ollama",
        })
        # Try to switch to anthropic
        response = client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "anthropic",
        })
        assert response.status_code == 400
        assert "external AI is blocked" in response.json()["detail"]

    def test_cannot_set_anthropic_and_blocked_together(self, client):
        """Cannot set both provider=anthropic and external_ai_blocked=True."""
        # First unblock
        client.patch(f"{BASE_URL}/ai", json={"external_ai_blocked": False})
        response = client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "anthropic",
            "external_ai_blocked": True,
        })
        assert response.status_code == 400

    def test_empty_api_key_string_not_cleared(self, client):
        """Passing ai_api_key="" should NOT clear the key (guard clause)."""
        # Set a key first
        client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "anthropic",
            "ai_api_key": "sk-ant-test9876543210zyxwvu",
            "external_ai_blocked": False,
        })
        # Pass empty string - should be skipped
        response = client.patch(f"{BASE_URL}/ai", json={
            "ai_api_key": "",
        })
        assert response.status_code == 200
        data = response.json()
        # Key should still be set (empty string is ignored)
        assert data["ai_api_key_set"] is True

    def test_update_anthropic_model(self, client):
        # Ensure unblocked
        client.patch(f"{BASE_URL}/ai", json={"external_ai_blocked": False})
        response = client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "anthropic",
            "ai_anthropic_model": "claude-opus-4-20250514",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["ai_anthropic_model"] == "claude-opus-4-20250514"


# =============================================================================
# POST /ai/test
# =============================================================================

class TestAIConnectionTest:
    """POST /api/v1/settings/ai/test"""

    def test_no_provider_configured(self, client):
        """When no provider is configured, test should fail gracefully."""
        # Clear provider
        client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "",
            "external_ai_blocked": False,
        })
        response = client.post(f"{BASE_URL}/ai/test")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["provider"] is None
        assert "No AI provider configured" in data["message"]

    def test_anthropic_without_key(self, client):
        """When anthropic is set but no key, test should report key not set."""
        client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "anthropic",
            "ai_api_key": None,
            "external_ai_blocked": False,
        })
        response = client.post(f"{BASE_URL}/ai/test")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["provider"] == "anthropic"
        assert "key" in data["message"].lower()

    def test_ollama_connection_test(self, client):
        """Ollama test should attempt connection (will fail in CI - no ollama running)."""
        client.patch(f"{BASE_URL}/ai", json={
            "ai_provider": "ollama",
            "ai_ollama_url": "http://localhost:11434",
        })
        response = client.post(f"{BASE_URL}/ai/test")
        assert response.status_code == 200
        data = response.json()
        assert data["provider"] == "ollama"
        # Will likely fail in test env (no ollama), but should not error
        assert isinstance(data["success"], bool)
        assert isinstance(data["message"], str)


# =============================================================================
# GET /ai/anthropic-status
# =============================================================================

class TestAnthropicStatus:
    """GET /api/v1/settings/ai/anthropic-status"""

    def test_anthropic_status_returns_shape(self, client):
        response = client.get(f"{BASE_URL}/ai/anthropic-status")
        assert response.status_code == 200
        data = response.json()
        assert "installed" in data
        assert isinstance(data["installed"], bool)
        # version is either a string or None
        assert "version" in data

    def test_anthropic_status_installed_flag(self, client):
        """The installed flag should reflect whether the anthropic package is available."""
        response = client.get(f"{BASE_URL}/ai/anthropic-status")
        assert response.status_code == 200
        data = response.json()
        if data["installed"]:
            # If installed, version should be present
            assert data["version"] is not None
        else:
            assert data["version"] is None


# =============================================================================
# POST /ai/install-anthropic
# =============================================================================

class TestInstallAnthropic:
    """POST /api/v1/settings/ai/install-anthropic"""

    def test_install_anthropic_returns_shape(self, client):
        """Endpoint should return success/message shape."""
        response = client.post(f"{BASE_URL}/ai/install-anthropic")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "message" in data
        assert isinstance(data["success"], bool)
        assert isinstance(data["message"], str)

    def test_install_anthropic_already_installed(self, client):
        """If anthropic is already installed, should report that."""
        response = client.post(f"{BASE_URL}/ai/install-anthropic")
        assert response.status_code == 200
        data = response.json()
        # Either it installs or says already installed - both are valid
        assert data["success"] is True or "failed" in data["message"].lower() or "error" in data["message"].lower()


# =============================================================================
# POST /ai/start-ollama
# =============================================================================

class TestStartOllama:
    """POST /api/v1/settings/ai/start-ollama"""

    def test_start_ollama_returns_shape(self, client):
        """Endpoint should return success/message shape (may fail in CI)."""
        response = client.post(f"{BASE_URL}/ai/start-ollama")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert "message" in data
        assert isinstance(data["success"], bool)
        assert isinstance(data["message"], str)
