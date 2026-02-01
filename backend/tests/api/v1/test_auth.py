"""
Tests for Authentication API endpoints (app/api/v1/endpoints/auth.py)

SENTINEL-001: Auth endpoints had ZERO test coverage.

Covers:
- POST /api/v1/auth/register
- POST /api/v1/auth/login
- POST /api/v1/auth/refresh
- GET  /api/v1/auth/me
- POST /api/v1/auth/password-reset/request
- GET  /api/v1/auth/password-reset/approve/{approval_token}
- GET  /api/v1/auth/password-reset/deny/{approval_token}
- GET  /api/v1/auth/password-reset/status/{token}
- POST /api/v1/auth/password-reset/complete
"""
import pytest
from unittest.mock import patch, MagicMock

BASE_URL = "/api/v1/auth"


@pytest.fixture(autouse=True)
def _disable_rate_limits():
    """Disable slowapi rate limiting for all auth tests."""
    from app.core.limiter import limiter
    original_enabled = getattr(limiter, '_enabled', True)
    limiter.enabled = False
    yield
    limiter.enabled = original_enabled


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
    """End-to-end password reset in dev mode (no email configured = auto-approve)."""

    def test_full_reset_flow(self, unauthed_client, registered_user):
        # Step 1: Request reset
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/request",
            json={"email": registered_user.email},
        )
        assert resp.status_code == 200
        data = resp.json()

        # In dev mode (no SMTP), reset_token should be returned directly
        if "reset_token" not in data or data["reset_token"] is None:
            pytest.skip("SMTP configured — auto-approve not available")

        reset_token = data["reset_token"]

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
        assert "access_token" in resp.json()

    def test_reset_with_weak_password_fails(self, unauthed_client, registered_user):
        # Request reset
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/request",
            json={"email": registered_user.email},
        )
        data = resp.json()
        if "reset_token" not in data or data["reset_token"] is None:
            pytest.skip("SMTP configured — auto-approve not available")

        reset_token = data["reset_token"]

        # Try to complete with weak password
        resp = unauthed_client.post(
            f"{BASE_URL}/password-reset/complete",
            json={"token": reset_token, "new_password": "weak"},
        )
        # Should reject weak password
        assert resp.status_code in (400, 422)


class TestPasswordResetApproval:

    def test_approve_invalid_token(self, unauthed_client):
        resp = unauthed_client.get(
            f"{BASE_URL}/password-reset/approve/nonexistent-approval-token",
        )
        assert resp.status_code == 404

    def test_deny_invalid_token(self, unauthed_client):
        resp = unauthed_client.get(
            f"{BASE_URL}/password-reset/deny/nonexistent-approval-token",
        )
        assert resp.status_code == 404
