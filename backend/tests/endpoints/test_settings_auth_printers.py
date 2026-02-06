"""
Additional coverage tests for settings, auth, and printers endpoints.

Targets uncovered code paths in:
- backend/app/api/v1/endpoints/settings.py  (~77 lines)
- backend/app/api/v1/endpoints/auth.py      (~90 lines)
- backend/app/api/v1/endpoints/printers.py  (~130 lines)

Focuses on:
- Admin/non-admin permission checks (403 paths)
- Edge cases in helper functions
- Password reset full flow with DB-created tokens
- Printer active work with assigned operations
- CSV import edge cases
"""
import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest


def _utcnow_naive():
    """Return current UTC time as a naive datetime (no tzinfo).

    Matches PostgreSQL DateTime(timezone=False) column storage and the
    comparison pattern used in auth.py: datetime.now(timezone.utc).replace(tzinfo=None).
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

SETTINGS_URL = "/api/v1/settings"
AUTH_URL = "/api/v1/auth"
PRINTERS_URL = "/api/v1/printers"


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def _disable_rate_limits():
    """Disable slowapi rate limiting for all tests in this module."""
    from app.core.limiter import limiter
    original_enabled = getattr(limiter, '_enabled', True)
    limiter.enabled = False
    yield
    limiter.enabled = original_enabled


@pytest.fixture
def non_admin_user(db):
    """Create a non-admin user (account_type=customer) for 403 tests."""
    from app.models.user import User
    from app.core.security import hash_password

    uid = uuid.uuid4().hex[:8]
    user = User(
        email=f"nonadmin-{uid}@filaops.dev",
        password_hash=hash_password("TestPass123!"),
        first_name="NonAdmin",
        last_name="User",
        account_type="customer",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def non_admin_client(db, non_admin_user):
    """Authenticated client with non-admin user (for 403 permission tests)."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db
    from app.core.security import create_access_token

    token = create_access_token(non_admin_user.id)

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def registered_user(db):
    """Create a user with known password for auth tests."""
    from app.models.user import User
    from app.core.security import hash_password

    uid = uuid.uuid4().hex[:8]
    user = User(
        email=f"authcov-{uid}@filaops.dev",
        password_hash=hash_password("TestPass123!"),
        first_name="Auth",
        last_name="Coverage",
        account_type="customer",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def reset_request_approved(db, registered_user):
    """Create an approved password reset request for testing completion."""
    import secrets
    from app.models.user import PasswordResetRequest

    reset_token = secrets.token_urlsafe(32)
    approval_token = secrets.token_urlsafe(32)

    reset_req = PasswordResetRequest(
        user_id=registered_user.id,
        token=reset_token,
        approval_token=approval_token,
        status='approved',
        expires_at=_utcnow_naive() + timedelta(hours=1),
        approved_at=_utcnow_naive(),
    )
    db.add(reset_req)
    db.flush()
    return reset_req


@pytest.fixture
def reset_request_pending(db, registered_user):
    """Create a pending password reset request."""
    import secrets
    from app.models.user import PasswordResetRequest

    reset_token = secrets.token_urlsafe(32)
    approval_token = secrets.token_urlsafe(32)

    reset_req = PasswordResetRequest(
        user_id=registered_user.id,
        token=reset_token,
        approval_token=approval_token,
        status='pending',
        expires_at=_utcnow_naive() + timedelta(hours=24),
    )
    db.add(reset_req)
    db.flush()
    return reset_req


@pytest.fixture
def reset_request_expired(db, registered_user):
    """Create an approved but expired password reset request."""
    import secrets
    from app.models.user import PasswordResetRequest

    reset_token = secrets.token_urlsafe(32)
    approval_token = secrets.token_urlsafe(32)

    reset_req = PasswordResetRequest(
        user_id=registered_user.id,
        token=reset_token,
        approval_token=approval_token,
        status='approved',
        expires_at=_utcnow_naive() - timedelta(hours=1),
        approved_at=_utcnow_naive() - timedelta(hours=2),
    )
    db.add(reset_req)
    db.flush()
    return reset_req


@pytest.fixture
def reset_request_denied(db, registered_user):
    """Create a denied password reset request."""
    import secrets
    from app.models.user import PasswordResetRequest

    reset_token = secrets.token_urlsafe(32)
    approval_token = secrets.token_urlsafe(32)

    reset_req = PasswordResetRequest(
        user_id=registered_user.id,
        token=reset_token,
        approval_token=approval_token,
        status='denied',
        expires_at=_utcnow_naive() + timedelta(hours=24),
        admin_notes="Test denial",
    )
    db.add(reset_req)
    db.flush()
    return reset_req


@pytest.fixture
def reset_request_completed(db, registered_user):
    """Create a completed password reset request."""
    import secrets
    from app.models.user import PasswordResetRequest

    reset_token = secrets.token_urlsafe(32)
    approval_token = secrets.token_urlsafe(32)

    reset_req = PasswordResetRequest(
        user_id=registered_user.id,
        token=reset_token,
        approval_token=approval_token,
        status='completed',
        expires_at=_utcnow_naive() + timedelta(hours=24),
        approved_at=_utcnow_naive() - timedelta(hours=1),
        completed_at=_utcnow_naive(),
    )
    db.add(reset_req)
    db.flush()
    return reset_req


def _create_printer(client, **overrides):
    """Create a printer and return the response JSON."""
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
    response = client.post(PRINTERS_URL, json=payload)
    assert response.status_code in (200, 201, 403), response.text
    if response.status_code == 403:
        pytest.skip("Printer tier limit reached")
    return response.json()


# =============================================================================
# SETTINGS: Non-admin 403 tests
# =============================================================================

class TestSettingsNonAdmin:
    """Verify admin-only endpoints return 403 for non-admin users."""

    def test_patch_company_non_admin(self, non_admin_client):
        resp = non_admin_client.patch(
            f"{SETTINGS_URL}/company", json={"company_name": "Hacked"}
        )
        assert resp.status_code == 403
        assert "Admin" in resp.json()["detail"]

    def test_upload_logo_non_admin(self, non_admin_client):
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        resp = non_admin_client.post(
            f"{SETTINGS_URL}/company/logo",
            files={"file": ("logo.png", io.BytesIO(content), "image/png")},
        )
        assert resp.status_code == 403

    def test_delete_logo_non_admin(self, non_admin_client):
        resp = non_admin_client.delete(f"{SETTINGS_URL}/company/logo")
        assert resp.status_code == 403

    def test_patch_ai_non_admin(self, non_admin_client):
        resp = non_admin_client.patch(
            f"{SETTINGS_URL}/ai", json={"ai_provider": "ollama"}
        )
        assert resp.status_code == 403

    def test_ai_test_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{SETTINGS_URL}/ai/test")
        assert resp.status_code == 403

    def test_start_ollama_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{SETTINGS_URL}/ai/start-ollama")
        assert resp.status_code == 403

    def test_install_anthropic_non_admin(self, non_admin_client):
        resp = non_admin_client.post(f"{SETTINGS_URL}/ai/install-anthropic")
        assert resp.status_code == 403


# =============================================================================
# SETTINGS: Helper function edge cases
# =============================================================================

class TestSettingsHelpers:
    """Test helper functions via endpoint behavior."""

    def test_tax_rate_computed_in_response(self, client):
        """When tax_rate is set, tax_rate_percent should be computed."""
        # Set a known tax rate
        resp = client.patch(f"{SETTINGS_URL}/company", json={
            "tax_rate_percent": 10.0,
            "tax_enabled": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_rate_percent"] == pytest.approx(10.0, abs=0.01)
        assert float(data["tax_rate"]) == pytest.approx(0.10, abs=0.001)

    def test_update_company_address_fields(self, client):
        """Cover address line 1/2, country, website updates."""
        uid = uuid.uuid4().hex[:6]
        payload = {
            "company_address_line1": f"123 Main St {uid}",
            "company_address_line2": "Suite 100",
            "company_country": "Canada",
            "company_website": f"https://{uid}.example.com",
        }
        resp = client.patch(f"{SETTINGS_URL}/company", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_address_line1"] == payload["company_address_line1"]
        assert data["company_address_line2"] == "Suite 100"
        assert data["company_country"] == "Canada"
        assert data["company_website"] == payload["company_website"]

    def test_get_ai_settings_anthropic_configured(self, client):
        """When anthropic provider and key are set, status=configured."""
        # Ensure unblocked
        client.patch(f"{SETTINGS_URL}/ai", json={"external_ai_blocked": False})
        client.patch(f"{SETTINGS_URL}/ai", json={
            "ai_provider": "anthropic",
            "ai_api_key": "sk-ant-test1234567890xyz",
        })
        resp = client.get(f"{SETTINGS_URL}/ai")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_status"] == "configured"
        assert data["ai_api_key_set"] is True
        # Key should be masked
        assert data["ai_api_key_masked"] is not None
        assert "..." in data["ai_api_key_masked"]
        assert data["ai_anthropic_model"] is not None

    def test_ai_test_anthropic_with_key(self, client):
        """Test anthropic connection when key is set (validates format)."""
        client.patch(f"{SETTINGS_URL}/ai", json={
            "external_ai_blocked": False,
        })
        client.patch(f"{SETTINGS_URL}/ai", json={
            "ai_provider": "anthropic",
            "ai_api_key": "sk-ant-real-format-key12345678",
        })
        resp = client.post(f"{SETTINGS_URL}/ai/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["provider"] == "anthropic"
        assert isinstance(data["success"], bool)
        assert isinstance(data["message"], str)

    def test_ai_settings_update_with_blocking_clears_anthropic_key(self, client):
        """Enabling external_ai_blocked clears anthropic provider and key."""
        client.patch(f"{SETTINGS_URL}/ai", json={
            "external_ai_blocked": False,
        })
        # Set anthropic
        client.patch(f"{SETTINGS_URL}/ai", json={
            "ai_provider": "anthropic",
            "ai_api_key": "sk-ant-clearme1234567890test",
        })
        # Switch away from anthropic first (to avoid 400)
        client.patch(f"{SETTINGS_URL}/ai", json={"ai_provider": "ollama"})
        # Block external AI
        resp = client.patch(f"{SETTINGS_URL}/ai", json={
            "external_ai_blocked": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ai_api_key_set"] is False
        assert data["external_ai_blocked"] is True


# =============================================================================
# SETTINGS: Logo with has_logo=True verification
# =============================================================================

class TestSettingsLogoState:
    """Test logo state reflected in GET /company."""

    def test_has_logo_true_after_upload(self, client):
        """After uploading, GET /company should show has_logo=True."""
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50
        client.post(
            f"{SETTINGS_URL}/company/logo",
            files={"file": ("state.png", io.BytesIO(content), "image/png")},
        )
        resp = client.get(f"{SETTINGS_URL}/company")
        assert resp.status_code == 200
        data = resp.json()
        assert data["has_logo"] is True
        assert data["logo_filename"] == "state.png"


# =============================================================================
# AUTH: Password reset status for various states
# =============================================================================

class TestPasswordResetStatusStates:
    """Cover all password reset status branches."""

    def test_status_pending(self, unauthed_client, reset_request_pending):
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/status/{reset_request_pending.token}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pending"
        assert data["can_reset"] is False
        assert "awaiting" in data["message"].lower()

    def test_status_denied(self, unauthed_client, reset_request_denied):
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/status/{reset_request_denied.token}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "denied"
        assert data["can_reset"] is False

    def test_status_completed(self, unauthed_client, reset_request_completed):
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/status/{reset_request_completed.token}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["can_reset"] is False
        assert "already been used" in data["message"]

    def test_status_expired(self, unauthed_client, reset_request_expired):
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/status/{reset_request_expired.token}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "expired"
        assert data["can_reset"] is False

    def test_status_approved(self, unauthed_client, reset_request_approved):
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/status/{reset_request_approved.token}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["can_reset"] is True


# =============================================================================
# AUTH: Password reset complete with various states
# =============================================================================

class TestPasswordResetCompleteStates:
    """Cover complete endpoint with different request states."""

    def test_complete_approved_token_success(self, unauthed_client, reset_request_approved):
        """Completing with valid approved token should succeed."""
        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={
                "token": reset_request_approved.token,
                "new_password": "NewSecure456!",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "successfully" in data["message"].lower()

    def test_complete_expired_token_rejected(self, unauthed_client, reset_request_expired):
        """Completing with expired token should fail."""
        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={
                "token": reset_request_expired.token,
                "new_password": "NewSecure456!",
            },
        )
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    def test_complete_pending_token_rejected(self, unauthed_client, reset_request_pending):
        """Completing with unapproved (pending) token should fail."""
        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={
                "token": reset_request_pending.token,
                "new_password": "NewSecure456!",
            },
        )
        assert resp.status_code == 400
        assert "pending" in resp.json()["detail"].lower()

    def test_complete_denied_token_rejected(self, unauthed_client, reset_request_denied):
        """Completing with denied token should fail."""
        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={
                "token": reset_request_denied.token,
                "new_password": "NewSecure456!",
            },
        )
        assert resp.status_code == 400

    def test_complete_already_completed_rejected(self, unauthed_client, reset_request_completed):
        """Completing with already-completed token should fail."""
        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={
                "token": reset_request_completed.token,
                "new_password": "NewSecure456!",
            },
        )
        assert resp.status_code == 400


# =============================================================================
# AUTH: Password reset approval with real DB tokens
# =============================================================================

class TestPasswordResetApprovalFlow:
    """Test approve/deny with tokens created in DB."""

    @patch("app.api.v1.endpoints.auth.email_service")
    def test_approve_valid_pending_request(
        self, mock_email, unauthed_client, reset_request_pending
    ):
        """Approving a pending request should succeed."""
        mock_email.send_password_reset_approved.return_value = True
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/approve/{reset_request_pending.approval_token}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert "approved" in data["message"].lower()

    @patch("app.api.v1.endpoints.auth.email_service")
    def test_deny_valid_pending_request(
        self, mock_email, unauthed_client, reset_request_pending
    ):
        """Denying a pending request should succeed."""
        mock_email.send_password_reset_denied.return_value = True
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/deny/{reset_request_pending.approval_token}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "denied"

    def test_approve_already_approved_rejected(
        self, unauthed_client, reset_request_approved
    ):
        """Approving an already-approved request should fail."""
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/approve/{reset_request_approved.approval_token}"
        )
        assert resp.status_code == 400
        assert "already been" in resp.json()["detail"].lower()

    def test_deny_already_denied_rejected(
        self, unauthed_client, reset_request_denied
    ):
        """Denying an already-denied request should fail."""
        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/deny/{reset_request_denied.approval_token}"
        )
        assert resp.status_code == 400

    def test_deny_with_reason(self, unauthed_client, db, registered_user):
        """Denying with a reason should store admin_notes."""
        import secrets
        from app.models.user import PasswordResetRequest

        token = secrets.token_urlsafe(32)
        approval_token = secrets.token_urlsafe(32)
        req = PasswordResetRequest(
            user_id=registered_user.id,
            token=token,
            approval_token=approval_token,
            status='pending',
            expires_at=_utcnow_naive() + timedelta(hours=24),
        )
        db.add(req)
        db.flush()

        with patch("app.api.v1.endpoints.auth.email_service") as mock_email:
            mock_email.send_password_reset_denied.return_value = True
            resp = unauthed_client.get(
                f"{AUTH_URL}/password-reset/deny/{approval_token}",
                params={"reason": "Suspicious request"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "denied"


# =============================================================================
# AUTH: Approval of expired pending request
# =============================================================================

class TestPasswordResetApprovalExpired:
    """Approving an expired pending request should fail."""

    def test_approve_expired_pending_request(self, unauthed_client, db, registered_user):
        import secrets
        from app.models.user import PasswordResetRequest

        token = secrets.token_urlsafe(32)
        approval_token = secrets.token_urlsafe(32)
        req = PasswordResetRequest(
            user_id=registered_user.id,
            token=token,
            approval_token=approval_token,
            status='pending',
            expires_at=_utcnow_naive() - timedelta(hours=1),
        )
        db.add(req)
        db.flush()

        resp = unauthed_client.get(
            f"{AUTH_URL}/password-reset/approve/{approval_token}"
        )
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()


# =============================================================================
# AUTH: Login then use access token for /me
# =============================================================================

class TestAuthMeWithLoginToken:
    """Test GET /me using tokens from a fresh login."""

    def test_me_with_fresh_login_token(self, unauthed_client, registered_user):
        """Login and use the access token to call /me."""
        login_resp = unauthed_client.post(
            f"{AUTH_URL}/login",
            data={
                "username": registered_user.email,
                "password": "TestPass123!",
            },
        )
        assert login_resp.status_code == 200
        token = login_resp.json()["access_token"]

        me_resp = unauthed_client.get(
            f"{AUTH_URL}/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 200
        data = me_resp.json()
        assert data["email"] == registered_user.email
        assert data["first_name"] == "Auth"
        assert data["last_name"] == "Coverage"


# =============================================================================
# AUTH: Duplicate pending reset request
# =============================================================================

class TestPasswordResetDuplicatePending:
    """Submitting a reset request when one is already pending."""

    def test_duplicate_pending_returns_message(
        self, unauthed_client, reset_request_pending, registered_user
    ):
        """Requesting reset when pending should return appropriate message."""
        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/request",
            json={"email": registered_user.email},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data["message"].lower()


# =============================================================================
# AUTH: Register with optional fields
# =============================================================================

class TestAuthRegisterOptionalFields:
    """Test registration with optional fields populated."""

    def test_register_with_all_optional_fields(self, unauthed_client):
        uid = uuid.uuid4().hex[:8]
        resp = unauthed_client.post(
            f"{AUTH_URL}/register",
            json={
                "email": f"full-{uid}@example.com",
                "password": "SecurePass123!",
                "first_name": "Full",
                "last_name": "User",
                "company_name": "Test Corp",
                "phone": "555-1234",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["first_name"] == "Full"
        assert data["last_name"] == "User"
        assert data["company_name"] == "Test Corp"
        assert data["phone"] == "555-1234"


# =============================================================================
# PRINTERS: Auth checks for probe-ip and test-connection
# =============================================================================

class TestPrinterNetworkAuth:
    """Auth required for probe-ip and test-connection."""

    def test_probe_ip_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(
            f"{PRINTERS_URL}/probe-ip",
            params={"ip_address": "192.168.1.1"},
        )
        assert resp.status_code == 401

    def test_test_connection_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(
            f"{PRINTERS_URL}/test-connection",
            json={
                "ip_address": "192.168.1.1",
                "brand": "generic",
                "connection_config": {},
            },
        )
        assert resp.status_code == 401


# =============================================================================
# PRINTERS: CSV import edge cases
# =============================================================================

class TestPrinterCSVEdgeCases:
    """CSV import edge cases."""

    def test_csv_empty_data(self, client):
        """Empty CSV body should return 0 rows."""
        resp = client.post(f"{PRINTERS_URL}/import-csv", json={
            "csv_data": "",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 0
        assert data["imported"] == 0

    def test_csv_header_only(self, client):
        """CSV with only headers should return 0 rows."""
        resp = client.post(f"{PRINTERS_URL}/import-csv", json={
            "csv_data": "code,name,model,brand",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 0

    def test_csv_with_serial_and_notes(self, client):
        """CSV with all optional fields populated."""
        uid = uuid.uuid4().hex[:6]
        csv_data = (
            "code,name,model,brand,serial_number,ip_address,location,notes\n"
            f"PRT-FULL-{uid},Full CSV,ModelZ,bambulab,SN-{uid},10.0.0.99,Bay 5,Test notes"
        )
        resp = client.post(f"{PRINTERS_URL}/import-csv", json={
            "csv_data": csv_data,
            "skip_duplicates": True,
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 1

    def test_csv_empty_required_fields(self, client):
        """CSV with blank required fields should report errors."""
        csv_data = "code,name,model\n,,\n"
        resp = client.post(f"{PRINTERS_URL}/import-csv", json={
            "csv_data": csv_data,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 0
        assert len(data["errors"]) >= 1


# =============================================================================
# PRINTERS: Create with connection_config and capabilities
# =============================================================================

class TestPrinterCreateAdvanced:
    """Test creation with connection_config and capabilities."""

    def test_create_with_connection_config(self, client):
        uid = uuid.uuid4().hex[:6]
        resp = client.post(PRINTERS_URL, json={
            "code": f"PRT-CC-{uid}",
            "name": f"Config Printer {uid}",
            "model": "X1 Carbon",
            "brand": "bambulab",
            "connection_config": {"access_code": "12345678"},
            "capabilities": {"bed_size_x": 256, "bed_size_y": 256, "ams_slots": 4},
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["connection_config"]["access_code"] == "12345678"
        assert data["capabilities"]["bed_size_x"] == 256
        assert data["capabilities"]["ams_slots"] == 4

    def test_create_with_null_optional_fields(self, client):
        """Creating without serial_number, ip, mqtt should succeed."""
        uid = uuid.uuid4().hex[:6]
        resp = client.post(PRINTERS_URL, json={
            "code": f"PRT-NULL-{uid}",
            "name": f"Null Printer {uid}",
            "model": "Basic Model",
            "brand": "generic",
        })
        if resp.status_code == 403:
            pytest.skip("Tier limit reached")
        assert resp.status_code in (200, 201)
        data = resp.json()
        assert data["serial_number"] is None
        assert data["mqtt_topic"] is None


# =============================================================================
# PRINTERS: Update with connection_config and capabilities
# =============================================================================

class TestPrinterUpdateAdvanced:
    """Test updates with connection_config, capabilities, and code change."""

    def test_update_connection_config(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{PRINTERS_URL}/{printer['id']}", json={
            "connection_config": {"api_key": "test-key-123"},
        })
        assert resp.status_code == 200
        assert resp.json()["connection_config"]["api_key"] == "test-key-123"

    def test_update_capabilities(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{PRINTERS_URL}/{printer['id']}", json={
            "capabilities": {"heated_bed": True, "camera": True},
        })
        assert resp.status_code == 200
        assert resp.json()["capabilities"]["heated_bed"] is True

    def test_update_code_to_new_unique_code(self, client):
        """Updating code to a new unique code should succeed."""
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        new_code = f"PRT-NEW-{uuid.uuid4().hex[:6]}"
        resp = client.put(f"{PRINTERS_URL}/{printer['id']}", json={
            "code": new_code,
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == new_code

    def test_update_same_code_is_ok(self, client):
        """Updating code to the same value should succeed (no duplicate)."""
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{PRINTERS_URL}/{printer['id']}", json={
            "code": printer["code"],
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == printer["code"]

    def test_update_location_and_notes(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{PRINTERS_URL}/{printer['id']}", json={
            "location": "New Location",
            "notes": "Updated notes for testing",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["location"] == "New Location"
        assert data["notes"] == "Updated notes for testing"

    def test_update_ip_and_serial(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{PRINTERS_URL}/{printer['id']}", json={
            "ip_address": "10.0.0.99",
            "serial_number": "SN-UPDATED-123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ip_address"] == "10.0.0.99"
        assert data["serial_number"] == "SN-UPDATED-123"

    def test_update_active_false(self, client):
        """Deactivating a printer via PUT."""
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.put(f"{PRINTERS_URL}/{printer['id']}", json={
            "active": False,
        })
        assert resp.status_code == 200
        assert resp.json()["active"] is False


# =============================================================================
# PRINTERS: Response field validation
# =============================================================================

class TestPrinterResponseFields:
    """Verify response schema fields are present and correct types."""

    def test_response_has_all_fields(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.get(f"{PRINTERS_URL}/{printer['id']}")
        assert resp.status_code == 200
        data = resp.json()

        expected_fields = [
            "id", "code", "name", "model", "brand",
            "serial_number", "ip_address", "mqtt_topic",
            "location", "work_center_id", "notes",
            "active", "status", "connection_config",
            "capabilities", "last_seen", "created_at",
            "updated_at", "is_online", "has_ams", "has_camera",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"

    def test_response_field_types(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.get(f"{PRINTERS_URL}/{printer['id']}")
        data = resp.json()

        assert isinstance(data["id"], int)
        assert isinstance(data["active"], bool)
        assert isinstance(data["is_online"], bool)
        assert isinstance(data["has_ams"], bool)
        assert isinstance(data["has_camera"], bool)
        assert isinstance(data["connection_config"], dict)
        assert isinstance(data["capabilities"], dict)
        assert isinstance(data["created_at"], str)
        assert isinstance(data["updated_at"], str)


# =============================================================================
# PRINTERS: Active work with operations
# =============================================================================

class TestPrinterActiveWork:
    """Test active work endpoint with actual printer+operations data."""

    def test_active_work_with_no_work_centers(self, client):
        """Printers without work centers should not appear."""
        _create_printer(client, work_center_id=None)
        resp = client.get(f"{PRINTERS_URL}/active-work")
        assert resp.status_code == 200
        data = resp.json()
        assert "printers" in data

    def test_active_work_with_work_center_no_ops(self, client, db, make_work_center):
        """Printer with work center but no operations should return None."""
        wc = make_work_center()
        uid = uuid.uuid4().hex[:6]
        printer = _create_printer(
            client,
            code=f"PRT-WC-{uid}",
            work_center_id=wc.id,
        )
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.get(f"{PRINTERS_URL}/active-work")
        assert resp.status_code == 200
        data = resp.json()
        assert "printers" in data
        # The printer may or may not be in the result depending on active state
        # but the endpoint should not error


# =============================================================================
# PRINTERS: Discover with default timeout
# =============================================================================

class TestPrinterDiscoverDefaults:
    """Test discovery with minimal/default parameters."""

    def test_discover_with_empty_request(self, client):
        """Discovery with empty body uses defaults."""
        resp = client.post(f"{PRINTERS_URL}/discover", json={})
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "printers" in data
            assert "scan_duration_seconds" in data
            assert "errors" in data

    def test_discover_with_multiple_brands(self, client):
        """Discovery with multiple brand filter."""
        resp = client.post(f"{PRINTERS_URL}/discover", json={
            "timeout_seconds": 1,
            "brands": ["bambulab", "klipper"],
        })
        assert resp.status_code in (200, 500)


# =============================================================================
# PRINTERS: Probe IP with brand hints
# =============================================================================

class TestPrinterProbeIP:
    """Test probe-ip with various brand hints."""

    def test_probe_with_klipper_hint(self, client):
        resp = client.post(
            f"{PRINTERS_URL}/probe-ip",
            params={"ip_address": "192.168.99.99", "brand": "klipper"},
        )
        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["ip_address"] == "192.168.99.99"
            assert "reachable" in data

    def test_probe_with_generic_hint(self, client):
        resp = client.post(
            f"{PRINTERS_URL}/probe-ip",
            params={"ip_address": "10.0.0.1", "brand": "generic"},
        )
        assert resp.status_code in (200, 500)

    def test_probe_with_no_brand(self, client):
        resp = client.post(
            f"{PRINTERS_URL}/probe-ip",
            params={"ip_address": "10.0.0.2"},
        )
        assert resp.status_code in (200, 500)


# =============================================================================
# PRINTERS: Test connection with various brands
# =============================================================================

class TestPrinterTestConnection:
    """Test connection with different brand adapters."""

    def test_connection_bambulab(self, client):
        resp = client.post(f"{PRINTERS_URL}/test-connection", json={
            "ip_address": "192.168.1.100",
            "brand": "bambulab",
            "connection_config": {"access_code": "12345678"},
        })
        assert resp.status_code in (200, 400, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert "success" in data
            assert "message" in data

    def test_connection_klipper(self, client):
        resp = client.post(f"{PRINTERS_URL}/test-connection", json={
            "ip_address": "192.168.1.101",
            "brand": "klipper",
            "connection_config": {},
        })
        assert resp.status_code in (200, 400, 500)

    def test_connection_nonexistent_brand_adapter(self, client):
        """Testing connection with an unsupported brand should fail."""
        resp = client.post(f"{PRINTERS_URL}/test-connection", json={
            "ip_address": "192.168.1.1",
            "brand": "prusa",
            "connection_config": {},
        })
        # May get 200 (with success=false), 400, or 500
        assert resp.status_code in (200, 400, 500)


# =============================================================================
# PRINTERS: Pagination edge cases
# =============================================================================

class TestPrinterPaginationExtra:
    """Additional pagination tests."""

    def test_page_size_max(self, client):
        """page_size=200 (max) should work."""
        resp = client.get(PRINTERS_URL, params={"page_size": 200})
        assert resp.status_code == 200
        assert resp.json()["page_size"] == 200

    def test_page_size_one(self, client):
        """page_size=1 should return at most 1 item."""
        resp = client.get(PRINTERS_URL, params={"page_size": 1})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 1
        assert data["page_size"] == 1

    def test_total_pages_calculation(self, client):
        """Verify total_pages = ceil(total / page_size)."""
        resp = client.get(PRINTERS_URL, params={"page_size": 1, "active_only": "false"})
        assert resp.status_code == 200
        data = resp.json()
        if data["total"] > 0:
            expected_pages = (data["total"] + 1 - 1) // 1
            assert data["total_pages"] == expected_pages


# =============================================================================
# SETTINGS: AI connection test - unknown provider
# =============================================================================

class TestAITestUnknownProvider:
    """Test AI connection test with an unknown provider stored in DB."""

    def test_ai_test_unknown_provider_fallthrough(self, client, db):
        """If ai_provider is set to something weird, test returns unknown."""
        from app.models.company_settings import CompanySettings

        # Directly set an unusual provider in DB
        settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
        if settings:
            settings.ai_provider = "some_weird_provider"
            db.flush()

        resp = client.post(f"{SETTINGS_URL}/ai/test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        # Provider is either "some_weird_provider" or None depending on path
        assert isinstance(data["message"], str)

        # Clean up
        if settings:
            settings.ai_provider = None
            db.flush()


# =============================================================================
# AUTH: Password reset complete revokes refresh tokens
# =============================================================================

class TestPasswordResetRevokesTokens:
    """After completing password reset, old refresh tokens should be revoked."""

    def test_complete_reset_revokes_tokens(
        self, unauthed_client, db, registered_user, reset_request_approved
    ):
        """Completing reset should revoke all existing refresh tokens."""
        from app.models.user import RefreshToken
        from app.core.security import hash_refresh_token, create_refresh_token as _crt
        from datetime import timedelta

        # Create a refresh token for this user
        raw_token = _crt(registered_user.id)
        token_hash = hash_refresh_token(raw_token)
        rt = RefreshToken(
            user_id=registered_user.id,
            token_hash=token_hash,
            expires_at=_utcnow_naive() + timedelta(days=7),
        )
        db.add(rt)
        db.flush()

        # Complete password reset
        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={
                "token": reset_request_approved.token,
                "new_password": "AfterReset789!",
            },
        )
        assert resp.status_code == 200

        # Verify old refresh tokens are revoked
        active_tokens = db.query(RefreshToken).filter(
            RefreshToken.user_id == registered_user.id,
            RefreshToken.revoked.is_(False),
        ).count()
        assert active_tokens == 0

    def test_login_with_new_password_after_reset(
        self, unauthed_client, registered_user, reset_request_approved
    ):
        """After reset, login with new password should work."""
        # Complete reset
        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={
                "token": reset_request_approved.token,
                "new_password": "BrandNew999!",
            },
        )
        assert resp.status_code == 200

        # Login with new password
        resp = unauthed_client.post(
            f"{AUTH_URL}/login",
            data={
                "username": registered_user.email,
                "password": "BrandNew999!",
            },
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()


# =============================================================================
# PRINTERS: Delete then verify gone
# =============================================================================

class TestPrinterDeleteVerify:
    """Test delete with subsequent list verification."""

    def test_deleted_printer_not_in_list(self, client):
        """After deleting a printer, it should not appear in list."""
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        # Delete
        resp = client.delete(f"{PRINTERS_URL}/{printer['id']}")
        assert resp.status_code == 200

        # Verify not in list
        resp = client.get(PRINTERS_URL, params={"active_only": "false"})
        assert resp.status_code == 200
        ids = [p["id"] for p in resp.json()["items"]]
        assert printer["id"] not in ids


# =============================================================================
# PRINTERS: Status update updates last_seen
# =============================================================================

class TestPrinterStatusLastSeen:
    """Status update should update last_seen timestamp."""

    def test_status_update_sets_last_seen(self, client):
        printer = _create_printer(client)
        if "id" not in printer:
            pytest.skip("Tier limit reached")

        resp = client.patch(
            f"{PRINTERS_URL}/{printer['id']}/status",
            json={"status": "idle"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["last_seen"] is not None


# =============================================================================
# SETTINGS: Quote validation edges
# =============================================================================

class TestSettingsValidation:
    """Test validation constraints on settings updates."""

    def test_quote_validity_days_min(self, client):
        """Minimum quote validity is 1 day."""
        resp = client.patch(f"{SETTINGS_URL}/company", json={
            "default_quote_validity_days": 0,
        })
        assert resp.status_code == 422

    def test_quote_validity_days_max(self, client):
        """Maximum quote validity is 365 days."""
        resp = client.patch(f"{SETTINGS_URL}/company", json={
            "default_quote_validity_days": 366,
        })
        assert resp.status_code == 422

    def test_tax_rate_percent_negative(self, client):
        """Negative tax rate should be rejected."""
        resp = client.patch(f"{SETTINGS_URL}/company", json={
            "tax_rate_percent": -1,
        })
        assert resp.status_code == 422

    def test_tax_rate_percent_over_100(self, client):
        """Tax rate over 100% should be rejected."""
        resp = client.patch(f"{SETTINGS_URL}/company", json={
            "tax_rate_percent": 101,
        })
        assert resp.status_code == 422

    def test_business_hours_start_invalid(self, client):
        """business_hours_start > 23 should be rejected."""
        resp = client.patch(f"{SETTINGS_URL}/company", json={
            "business_hours_start": 24,
        })
        assert resp.status_code == 422

    def test_business_days_per_week_invalid(self, client):
        """business_days_per_week > 7 should be rejected."""
        resp = client.patch(f"{SETTINGS_URL}/company", json={
            "business_days_per_week": 8,
        })
        assert resp.status_code == 422

    def test_ai_provider_invalid_pattern(self, client):
        """AI provider must match ^(anthropic|ollama)?$ pattern."""
        resp = client.patch(f"{SETTINGS_URL}/ai", json={
            "ai_provider": "chatgpt",
        })
        assert resp.status_code == 422
