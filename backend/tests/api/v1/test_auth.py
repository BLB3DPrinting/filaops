"""
Tests for Authentication API endpoints (app/api/v1/endpoints/auth.py)

SENTINEL-001: Auth endpoints had ZERO test coverage.

Covers:
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- POST /api/v1/auth/logout
- GET  /api/v1/auth/me
- POST /api/v1/auth/password-reset/request
- POST /api/v1/auth/password-reset/approve
- POST /api/v1/auth/password-reset/deny
- GET  /api/v1/auth/password-reset/status/{token}
- POST /api/v1/auth/password-reset/complete
- POST /api/v1/auth/portal/register
- POST /api/v1/auth/portal/login

Self-registration (both register routes) is off unless ENABLE_PUBLIC_QUOTER
is on. The register test classes turn the flag on; TestSelfRegistrationGate
covers the off state.
"""
import pytest

BASE_URL = "/api/v1/auth"


@pytest.fixture(autouse=True)
def _disable_rate_limits():
    """Disable slowapi rate limiting for all auth tests."""
    from app.core.limiter import limiter
    original_enabled = getattr(limiter, '_enabled', True)
    limiter.enabled = False
    yield
    limiter.enabled = original_enabled


@pytest.fixture(autouse=True)
def _force_header_mode(monkeypatch):
    """Force header (bearer-in-body) mode for existing tests.

    Cookie-mode tests are in a dedicated class that overrides this.
    """
    import app.api.v1.endpoints.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_USE_COOKIES", False)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def registered_user(db):
    """Create a user with a known password for login tests."""
    import uuid
    from app.models.user import User
    from app.core.security import hash_password

    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"authtest-{unique}@filaops.dev",
        password_hash=hash_password("TestPass123!"),
        first_name="Auth",
        last_name="Tester",
        account_type="customer",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def inactive_user(db):
    """Create an inactive user for testing 403 responses."""
    import uuid
    from app.models.user import User
    from app.core.security import hash_password

    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"inactive-{unique}@filaops.dev",
        password_hash=hash_password("TestPass123!"),
        first_name="Inactive",
        last_name="User",
        account_type="customer",
        status="inactive",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def self_registration_enabled(monkeypatch):
    """Turn customer self-registration on (it follows ENABLE_PUBLIC_QUOTER)."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENABLE_PUBLIC_QUOTER", True)


@pytest.fixture
def login_tokens(unauthed_client, registered_user):
    """Log in as registered_user and return the token response."""
    resp = unauthed_client.post(
        f"{BASE_URL}/login",
        data={"username": registered_user.email, "password": "TestPass123!"},
    )
    assert resp.status_code == 200, f"Login setup failed: {resp.text}"
    return resp.json()


# =============================================================================
# POST /api/v1/auth/register
# =============================================================================

@pytest.mark.usefixtures("self_registration_enabled")
class TestRegister:

    def test_register_success(self, unauthed_client):
        import uuid
        email = f"newuser-{uuid.uuid4().hex[:8]}@example.com"
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={
                "email": email,
                "password": "SecurePass123!",
                "first_name": "New",
                "last_name": "User",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == email
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_register_duplicate_email(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={
                "email": registered_user.email,
                "password": "SecurePass123!",
                "first_name": "Dup",
            },
        )
        assert resp.status_code == 400

    def test_register_weak_password_too_short(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={"email": "short@example.com", "password": "Ab1!"},
        )
        assert resp.status_code == 422

    def test_register_weak_password_no_uppercase(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={"email": "noup@example.com", "password": "abcdefg1!"},
        )
        assert resp.status_code == 422

    def test_register_weak_password_no_number(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={"email": "nonum@example.com", "password": "Abcdefgh!"},
        )
        assert resp.status_code == 422

    def test_register_missing_email(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={"password": "SecurePass123!"},
        )
        assert resp.status_code == 422

    def test_register_missing_password(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={"email": "nopwd@example.com"},
        )
        assert resp.status_code == 422

    def test_register_invalid_email_format(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={"email": "not-an-email", "password": "SecurePass123!"},
        )
        assert resp.status_code == 422

    def test_register_ignores_privileged_fields_in_body(self, unauthed_client, db):
        """Twin of test_portal_register_ignores_account_type_in_body for
        /auth/register. Role, status and verification fields sneaked into the
        body are ignored: the account is always an active, unverified
        customer, and its token cannot reach an admin route."""
        import uuid
        from app.models.user import User

        email = f"escalate-{uuid.uuid4().hex[:8]}@example.com"
        resp = unauthed_client.post(
            f"{BASE_URL}/register",
            json={
                "email": email,
                "password": "SecurePass123!",
                # None of these are UserRegister fields; pin that they are ignored.
                "account_type": "admin",
                "role": "admin",
                "is_admin": True,
                "is_staff": True,
                "status": "inactive",
                "email_verified": True,
            },
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["account_type"] == "customer"
        assert data["status"] == "active"
        assert data["email_verified"] is False

        persisted = db.query(User).filter(User.email == email).first()
        assert persisted is not None
        assert persisted.account_type == "customer"
        assert persisted.status == "active"
        assert persisted.email_verified is False
        assert persisted.is_admin is False

        admin_only = unauthed_client.get(
            "/api/v1/admin/users/",
            headers={"Authorization": f"Bearer {data['access_token']}"},
        )
        assert admin_only.status_code == 403


# =============================================================================
# POST /api/v1/auth/login
# =============================================================================

class TestLogin:

    def test_login_success(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": registered_user.email, "password": "TestPass123!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": registered_user.email, "password": "WrongPass999!"},
        )
        assert resp.status_code == 401

    def test_login_nonexistent_email(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": "nobody@nowhere.com", "password": "Pass123!"},
        )
        assert resp.status_code == 401

    def test_login_inactive_user(self, unauthed_client, inactive_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": inactive_user.email, "password": "TestPass123!"},
        )
        # Should return 401 or 403 for inactive users
        assert resp.status_code in (401, 403)

    def test_login_missing_username(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"password": "TestPass123!"},
        )
        assert resp.status_code == 422

    def test_login_missing_password(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": registered_user.email},
        )
        assert resp.status_code == 422


# =============================================================================
# POST /api/v1/auth/refresh
# =============================================================================

class TestRefreshToken:

    def test_refresh_success(self, unauthed_client, login_tokens):
        resp = unauthed_client.post(
            f"{BASE_URL}/refresh",
            json={"refresh_token": login_tokens["refresh_token"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_refresh_invalid_token(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/refresh",
            json={"refresh_token": "totally-invalid-token"},
        )
        assert resp.status_code == 401

    def test_refresh_reuse_revoked_token(self, unauthed_client, login_tokens):
        """After refreshing once, the old refresh token should be revoked."""
        old_refresh = login_tokens["refresh_token"]

        # First refresh — should succeed
        resp1 = unauthed_client.post(
            f"{BASE_URL}/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp1.status_code == 200

        # Second refresh with same token — should fail (revoked)
        resp2 = unauthed_client.post(
            f"{BASE_URL}/refresh",
            json={"refresh_token": old_refresh},
        )
        assert resp2.status_code == 401


# =============================================================================
# GET /api/v1/auth/me
# =============================================================================

class TestMe:

    def test_me_authenticated(self, client):
        resp = client.get(f"{BASE_URL}/me")
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data
        assert "id" in data

    def test_me_unauthenticated(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/me")
        assert resp.status_code == 401

    def test_me_invalid_token(self, unauthed_client):
        resp = unauthed_client.get(
            f"{BASE_URL}/me",
            headers={"Authorization": "Bearer invalid-jwt-token"},
        )
        assert resp.status_code == 401


# =============================================================================
# Password Reset Flow
# =============================================================================

class TestPasswordResetRequest:

    def test_request_reset_existing_user(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/request",
            json={"email": registered_user.email},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data

    def test_request_reset_nonexistent_email(self, unauthed_client):
        """Should still return 200 to prevent email enumeration."""
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/request",
            json={"email": "nonexistent@nowhere.com"},
        )
        assert resp.status_code == 200

    def test_request_reset_invalid_email_format(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/request",
            json={"email": "not-an-email"},
        )
        assert resp.status_code == 422


class TestPasswordResetStatus:

    def test_status_invalid_token(self, unauthed_client):
        resp = unauthed_client.get(
            f"{BASE_URL}/password-reset/status/nonexistent-token",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["can_reset"] is False
        assert data["status"] == "invalid"


class TestPasswordResetComplete:

    def test_complete_invalid_token(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/complete",
            json={"token": "invalid-token", "new_password": "NewSecure123!"},
        )
        assert resp.status_code == 400


class TestPasswordResetFullFlow:
    """End-to-end password reset: the token only reaches the user by email
    after an admin approves. See test_password_reset_request.py for the
    no-SMTP and response-shape cases."""

    def test_full_reset_flow(self, unauthed_client, registered_user, monkeypatch):
        from unittest.mock import patch
        from app.core.config import settings

        monkeypatch.setattr(settings, "SMTP_USER", "mailer@example.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "not-a-real-password")
        monkeypatch.setattr(settings, "ADMIN_APPROVAL_EMAIL", "owner@filaops.dev")

        with patch("app.api.v1.endpoints.auth.email_service") as mock_email:
            # Step 1: Request reset — the response never carries the token
            resp = unauthed_client.post(
                f"{BASE_URL}/password-reset/request",
                json={"email": registered_user.email},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert "reset_token" not in data
            assert "reset_url" not in data

            # Step 1b: Admin approves via the emailed approval link
            approval_token = (
                mock_email.send_password_reset_approval_request.call_args.kwargs["approval_token"]
            )
            resp = unauthed_client.post(
                f"{BASE_URL}/password-reset/approve",
                json={"approval_token": approval_token},
            )
            assert resp.status_code == 200
            reset_token = mock_email.send_password_reset_approved.call_args.kwargs["reset_token"]

        # Step 2: Check status (should be approved)
        resp = unauthed_client.get(
            f"{BASE_URL}/password-reset/status/{reset_token}",
        )
        assert resp.status_code == 200
        status_data = resp.json()
        assert status_data["can_reset"] is True
        assert status_data["status"] == "approved"

        # Step 3: Complete reset with new password
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/complete",
            json={"token": reset_token, "new_password": "BrandNewPass456!"},
        )
        assert resp.status_code == 200

        # Step 4: Login with new password should work
        resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={
                "username": registered_user.email,
                "password": "BrandNewPass456!",
            },
        )
        assert resp.status_code == 200
        # In header mode: token in body; in cookie mode: token in cookie
        data = resp.json()
        assert "access_token" in data or data.get("token_type") == "cookie"

    def test_reset_with_weak_password_fails(self, unauthed_client, db, registered_user):
        # An admin-approved reset request
        import secrets
        from datetime import datetime, timedelta, timezone
        from app.models.user import PasswordResetRequest

        reset_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        db.add(PasswordResetRequest(
            user_id=registered_user.id,
            token=reset_token,
            approval_token=secrets.token_urlsafe(32),
            status="approved",
            approved_at=now,
            expires_at=now + timedelta(hours=1),
        ))
        db.flush()

        # Try to complete with weak password
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/complete",
            json={"token": reset_token, "new_password": "weak"},
        )
        # Should reject weak password
        assert resp.status_code in (400, 422)


class TestPasswordResetApproval:

    def test_approve_invalid_token(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/approve",
            json={"approval_token": "nonexistent-approval-token"},
        )
        assert resp.status_code == 404

    def test_deny_invalid_token(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/deny",
            json={"approval_token": "nonexistent-approval-token"},
        )
        assert resp.status_code == 404

    def test_approve_old_get_endpoint_returns_405(self, unauthed_client):
        """Old GET-style approve endpoint should no longer exist."""
        resp = unauthed_client.get(
            f"{BASE_URL}/password-reset/approve/some-token",
        )
        assert resp.status_code in (404, 405)

    def test_deny_old_get_endpoint_returns_405(self, unauthed_client):
        """Old GET-style deny endpoint should no longer exist."""
        resp = unauthed_client.get(
            f"{BASE_URL}/password-reset/deny/some-token",
        )
        assert resp.status_code in (404, 405)


# =============================================================================
# Cookie-Mode Tests
# =============================================================================

class TestCookieMode:
    """Test httpOnly cookie auth delivery."""

    @pytest.fixture(autouse=True)
    def _enable_cookie_mode(self, monkeypatch):
        """Override the module-level header-mode fixture for this class."""
        import app.api.v1.endpoints.auth as auth_mod
        monkeypatch.setattr(auth_mod, "_USE_COOKIES", True)

    def test_login_sets_httponly_cookies(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": registered_user.email, "password": "TestPass123!"},
        )
        assert resp.status_code == 200
        data = resp.json()

        # Body should NOT contain tokens
        assert "access_token" not in data
        assert "refresh_token" not in data
        assert data["token_type"] == "cookie"
        assert "user" in data

        # Cookies should be set
        assert "access_token" in resp.cookies
        assert "refresh_token" in resp.cookies

    def test_cookie_auth_works(self, unauthed_client, registered_user):
        """Request with cookie, no Authorization header → 200."""
        # Login to get cookies
        login_resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": registered_user.email, "password": "TestPass123!"},
        )
        assert login_resp.status_code == 200

        # /me should work using cookie from login (TestClient carries cookies)
        me_resp = unauthed_client.get(f"{BASE_URL}/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == registered_user.email

    def test_header_auth_fallback(self, unauthed_client, registered_user):
        """Request with Authorization header, no cookie → 200."""
        from app.core.security import create_access_token
        token = create_access_token(registered_user.id)
        resp = unauthed_client.get(
            f"{BASE_URL}/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    def test_no_auth_returns_401(self, unauthed_client):
        """No cookie, no header → 401."""
        resp = unauthed_client.get(f"{BASE_URL}/me")
        assert resp.status_code == 401

    def test_logout_clears_cookies(self, unauthed_client, registered_user):
        # Login first
        unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": registered_user.email, "password": "TestPass123!"},
        )

        # Logout
        resp = unauthed_client.post(f"{BASE_URL}/logout")
        assert resp.status_code == 200

        # Cookies should be cleared — next /me should fail
        me_resp = unauthed_client.get(f"{BASE_URL}/me")
        assert me_resp.status_code == 401

    def test_refresh_via_cookie(self, unauthed_client, registered_user):
        """Refresh endpoint should read refresh_token from cookie."""
        # Login to set cookies
        login_resp = unauthed_client.post(
            f"{BASE_URL}/login",
            data={"username": registered_user.email, "password": "TestPass123!"},
        )
        assert login_resp.status_code == 200

        # Refresh — no body needed, cookie is sent automatically by TestClient
        resp = unauthed_client.post(f"{BASE_URL}/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_type"] == "cookie"
        assert "access_token" not in data


# =============================================================================
# POST /api/v1/auth/portal/register  +  POST /api/v1/auth/portal/login
# =============================================================================
# Customer-facing auth for the Quoter SPA and B2B portal. Sibling endpoints
# to /auth/register + /auth/login. Key differences:
#   - JSON body (not OAuth2 form)
#   - account_type always "customer" on register; filtered to "customer" on login
#   - Admin accounts CANNOT authenticate via portal/login (same 401 as wrong
#     password — no enumeration of which accounts are admin)

@pytest.fixture
def admin_user(db):
    """An admin-type user, for proving the portal/login endpoint refuses them."""
    import uuid
    from app.models.user import User
    from app.core.security import hash_password

    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"admin-{unique}@filaops.dev",
        password_hash=hash_password("AdminPass123!"),
        first_name="Admin",
        last_name="User",
        account_type="admin",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


@pytest.mark.usefixtures("self_registration_enabled")
class TestPortalRegister:

    def test_portal_register_creates_customer_account(self, unauthed_client, db):
        import uuid
        from app.models.user import User

        email = f"portal-{uuid.uuid4().hex[:8]}@example.com"
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/register",
            json={
                "email": email,
                "password": "SecurePass123!",
                "first_name": "Portal",
                "last_name": "Customer",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == email
        assert data["account_type"] == "customer"
        assert "access_token" in data
        assert data["token_type"] == "bearer"

        # Verify the user landed in the DB with account_type=customer specifically.
        # A future regression where the body let a caller escalate account_type
        # would fail this assertion.
        persisted = db.query(User).filter(User.email == email).first()
        assert persisted is not None
        assert persisted.account_type == "customer"

    def test_portal_register_ignores_account_type_in_body(self, unauthed_client, db):
        """Even if a caller sneaks `account_type` into the JSON body, it must NOT
        escalate to admin. UserRegister has no account_type field; the endpoint
        hardcodes ``"customer"``. This test pins that contract."""
        import uuid
        from app.models.user import User

        email = f"escalate-{uuid.uuid4().hex[:8]}@example.com"
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/register",
            json={
                "email": email,
                "password": "SecurePass123!",
                "account_type": "admin",  # ignored by Pydantic; pin behavior
            },
        )
        assert resp.status_code == 201
        persisted = db.query(User).filter(User.email == email).first()
        assert persisted.account_type == "customer"

    def test_portal_register_duplicate_email(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/register",
            json={"email": registered_user.email, "password": "SecurePass123!"},
        )
        assert resp.status_code == 400

    def test_portal_register_weak_password(self, unauthed_client):
        """Password policy comes from UserRegister.validate_password_strength
        and is inherited by the portal endpoint for free."""
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/register",
            json={"email": "weak@example.com", "password": "short"},
        )
        assert resp.status_code == 422

    def test_portal_register_invalid_email(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/register",
            json={"email": "not-an-email", "password": "SecurePass123!"},
        )
        assert resp.status_code == 422


REGISTER_PATHS = ["/register", "/portal/register"]


class TestSelfRegistrationGate:
    """Both register routes follow ENABLE_PUBLIC_QUOTER, which is off by
    default. Staff accounts come from an admin or first-run setup, so only
    the public Quoter needs open sign-up."""

    def test_public_quoter_flag_defaults_off(self):
        from app.core.settings import Settings

        assert Settings.model_fields["ENABLE_PUBLIC_QUOTER"].default is False

    @pytest.mark.parametrize("path", REGISTER_PATHS)
    def test_register_refused_when_public_quoter_disabled(
        self, unauthed_client, db, monkeypatch, path
    ):
        import uuid
        from app.core.config import settings
        from app.models.user import User

        monkeypatch.setattr(settings, "ENABLE_PUBLIC_QUOTER", False)
        user_count = db.query(User).count()
        email = f"gated-{uuid.uuid4().hex[:8]}@example.com"
        resp = unauthed_client.post(
            f"{BASE_URL}{path}",
            json={
                "email": email,
                "password": "SecurePass123!",
                "first_name": "Gated",
            },
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Customer self-registration is disabled"
        assert "access_token" not in resp.json()
        assert "access_token" not in resp.cookies
        assert db.query(User).filter(User.email == email).first() is None
        assert db.query(User).count() == user_count

    @pytest.mark.parametrize("path", REGISTER_PATHS)
    def test_disabled_register_does_not_reveal_existing_emails(
        self, unauthed_client, registered_user, monkeypatch, path
    ):
        """The gate runs before the duplicate-email check, so a known email
        gets the same 403 as a new one (no 400 'already registered')."""
        from app.core.config import settings

        monkeypatch.setattr(settings, "ENABLE_PUBLIC_QUOTER", False)
        resp = unauthed_client.post(
            f"{BASE_URL}{path}",
            json={"email": registered_user.email, "password": "SecurePass123!"},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Customer self-registration is disabled"

    @pytest.mark.parametrize("path", REGISTER_PATHS)
    def test_register_allowed_when_public_quoter_enabled(
        self, unauthed_client, db, monkeypatch, path
    ):
        import uuid
        from app.core.config import settings
        from app.models.user import User

        monkeypatch.setattr(settings, "ENABLE_PUBLIC_QUOTER", True)
        email = f"open-{uuid.uuid4().hex[:8]}@example.com"
        resp = unauthed_client.post(
            f"{BASE_URL}{path}",
            json={"email": email, "password": "SecurePass123!"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["account_type"] == "customer"
        persisted = db.query(User).filter(User.email == email).first()
        assert persisted is not None
        assert persisted.account_type == "customer"


class TestPortalLogin:

    def test_portal_login_success(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/login",
            json={"email": registered_user.email, "password": "TestPass123!"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == registered_user.email
        assert data["account_type"] == "customer"
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_portal_login_wrong_password(self, unauthed_client, registered_user):
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/login",
            json={"email": registered_user.email, "password": "WrongPass456!"},
        )
        assert resp.status_code == 401
        assert "email or password" in resp.json()["detail"].lower()

    def test_portal_login_no_such_user(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/login",
            json={"email": "nobody@example.com", "password": "WhateverPass1!"},
        )
        assert resp.status_code == 401
        # Generic message — no enumeration of which emails exist
        assert "email or password" in resp.json()["detail"].lower()

    def test_portal_login_refuses_admin_account(self, unauthed_client, admin_user):
        """SECURITY: admin accounts must NOT authenticate via the portal endpoint.
        Returns the same generic 401 as a wrong password — no enumeration of
        which emails belong to admins vs customers."""
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/login",
            json={"email": admin_user.email, "password": "AdminPass123!"},
        )
        assert resp.status_code == 401
        assert "email or password" in resp.json()["detail"].lower()

    def test_portal_login_inactive_customer_returns_403(self, unauthed_client, inactive_user):
        """An inactive customer should get a different signal (403) than a
        wrong-credentials attempt (401) so the customer-facing UI can show a
        'contact support' message rather than a 'wrong password' message."""
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/login",
            json={"email": inactive_user.email, "password": "TestPass123!"},
        )
        assert resp.status_code == 403

    def test_portal_login_missing_password(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/login",
            json={"email": "missing@example.com"},
        )
        assert resp.status_code == 422

    def test_portal_login_invalid_email_format(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/portal/login",
            json={"email": "not-an-email", "password": "WhateverPass1!"},
        )
        assert resp.status_code == 422
