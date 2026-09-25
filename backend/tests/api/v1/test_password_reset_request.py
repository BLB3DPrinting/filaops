"""
Tests for the password reset request flow (app/api/v1/endpoints/auth.py).

The request endpoint is public. These tests pin down that it:
- never returns a reset token or reset link, with or without SMTP, in
  production or development;
- returns the same body whether or not the account exists, whether a request
  is already pending, and whether SMTP is configured;
- leaves no-SMTP requests pending, so /password-reset/complete rejects them;
- keeps the SMTP (admin approval email) flow working end to end;
- never writes the full reset token to the logs.

They also cover the admin-only recovery path that no-SMTP shops use instead:
POST /api/v1/admin/users/{id}/reset-password (Team Members > Reset Password).
"""
import logging
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import pytest

AUTH_URL = "/api/v1/auth"
ADMIN_USERS_URL = "/api/v1/admin/users"
GENERIC_MESSAGE = (
    "If an account exists with this email, a password reset request has been "
    "submitted for review."
)
FORBIDDEN_KEYS = {"reset_token", "reset_url", "request_id", "token", "approval_token"}

SMTP_MODES = [
    pytest.param(True, id="smtp"),
    pytest.param(False, id="no-smtp"),
]
ENVIRONMENTS = [
    pytest.param("production", id="production"),
    pytest.param("development", id="development"),
]


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def _disable_rate_limits():
    """Disable slowapi rate limiting for this module."""
    from app.core.limiter import limiter
    original_enabled = getattr(limiter, "_enabled", True)
    limiter.enabled = False
    yield
    limiter.enabled = original_enabled


@pytest.fixture(autouse=True)
def _force_header_mode(monkeypatch):
    """Header (bearer-in-body) mode, matching the other auth test modules."""
    import app.api.v1.endpoints.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_USE_COOKIES", False)


@pytest.fixture
def mock_email():
    """Replace the email service the auth endpoints use.

    Always mocked so no test ever opens a real SMTP connection.
    """
    with patch("app.api.v1.endpoints.auth.email_service") as mocked:
        mocked.send_password_reset_approval_request.return_value = True
        mocked.send_password_reset_approved.return_value = True
        mocked.send_password_reset_denied.return_value = True
        mocked.send_password_reset_completed.return_value = True
        yield mocked


def _configure(monkeypatch, *, smtp: bool, environment: str = "development"):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    if smtp:
        monkeypatch.setattr(settings, "SMTP_USER", "mailer@example.com")
        monkeypatch.setattr(settings, "SMTP_PASSWORD", "not-a-real-password")
    else:
        monkeypatch.setattr(settings, "SMTP_USER", None)
        monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


def _make_user(db, account_type="operator", password="TestPass123!"):
    from app.models.user import User
    from app.core.security import hash_password

    user = User(
        email=f"reset-{account_type}-{uuid.uuid4().hex[:8]}@filaops.dev",
        password_hash=hash_password(password),
        first_name="Reset",
        last_name="Tester",
        account_type=account_type,
        status="active",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def staff_user(db):
    return _make_user(db, account_type="operator")


def _reset_rows(db, user_id):
    from app.models.user import PasswordResetRequest
    db.expire_all()
    return (
        db.query(PasswordResetRequest)
        .filter(PasswordResetRequest.user_id == user_id)
        .order_by(PasswordResetRequest.id)
        .all()
    )


def _request_reset(client, email):
    return client.post(f"{AUTH_URL}/password-reset/request", json={"email": email})


@contextmanager
def _client_for(db, user):
    """TestClient authenticated as ``user`` (same shape as conftest ``client``)."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db
    from app.core.security import create_access_token

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            c.headers["Authorization"] = f"Bearer {create_access_token(user.id)}"
            yield c
    finally:
        app.dependency_overrides.clear()


# =============================================================================
# The request endpoint never returns a token or link
# =============================================================================

class TestRequestNeverReturnsToken:

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    @pytest.mark.parametrize("smtp", SMTP_MODES)
    def test_existing_account_gets_generic_body_only(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch, smtp, environment
    ):
        _configure(monkeypatch, smtp=smtp, environment=environment)

        resp = _request_reset(unauthed_client, staff_user.email)

        assert resp.status_code == 200
        assert resp.json() == {"message": GENERIC_MESSAGE}
        assert not FORBIDDEN_KEYS & resp.json().keys()

        rows = _reset_rows(db, staff_user.id)
        assert len(rows) == 1
        assert rows[0].token not in resp.text
        assert rows[0].approval_token not in resp.text
        assert "/reset-password/" not in resp.text

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    @pytest.mark.parametrize("smtp", SMTP_MODES)
    def test_unknown_email_gets_identical_body(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch, smtp, environment
    ):
        _configure(monkeypatch, smtp=smtp, environment=environment)

        known = _request_reset(unauthed_client, staff_user.email)
        unknown = _request_reset(unauthed_client, f"nobody-{uuid.uuid4().hex[:8]}@filaops.dev")

        assert known.status_code == unknown.status_code == 200
        assert known.json() == unknown.json() == {"message": GENERIC_MESSAGE}

    @pytest.mark.parametrize("smtp", SMTP_MODES)
    def test_repeat_request_gets_identical_body(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch, smtp
    ):
        _configure(monkeypatch, smtp=smtp)

        first = _request_reset(unauthed_client, staff_user.email)
        second = _request_reset(unauthed_client, staff_user.email)

        assert first.json() == second.json() == {"message": GENERIC_MESSAGE}
        # The pending request is reused, not duplicated.
        assert len(_reset_rows(db, staff_user.id)) == 1

    def test_body_is_same_with_and_without_smtp(
        self, unauthed_client, db, mock_email, monkeypatch
    ):
        _configure(monkeypatch, smtp=True)
        with_smtp = _request_reset(unauthed_client, _make_user(db).email)
        _configure(monkeypatch, smtp=False)
        without_smtp = _request_reset(unauthed_client, _make_user(db).email)

        assert with_smtp.json() == without_smtp.json() == {"message": GENERIC_MESSAGE}

    def test_response_schema_has_no_token_fields(self):
        from app.main import app

        schema = app.openapi()["components"]["schemas"]["PasswordResetRequestResponse"]
        assert set(schema["properties"]) == {"message"}


# =============================================================================
# Without SMTP the request stays pending and cannot be completed
# =============================================================================

class TestNoSmtpRequestStaysPending:

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_request_is_pending_not_approved(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch, environment
    ):
        _configure(monkeypatch, smtp=False, environment=environment)

        resp = _request_reset(unauthed_client, staff_user.email)
        assert resp.status_code == 200

        rows = _reset_rows(db, staff_user.id)
        assert len(rows) == 1
        assert rows[0].status == "pending"
        assert rows[0].approved_at is None
        # Nothing was emailed, so nobody holds the approval link.
        mock_email.send_password_reset_approval_request.assert_not_called()
        mock_email.send_password_reset_approved.assert_not_called()

    def test_status_reports_pending(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch
    ):
        _configure(monkeypatch, smtp=False)
        _request_reset(unauthed_client, staff_user.email)
        token = _reset_rows(db, staff_user.id)[0].token

        resp = unauthed_client.get(f"{AUTH_URL}/password-reset/status/{token}")

        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"
        assert resp.json()["can_reset"] is False

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    def test_complete_rejects_pending_token(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch, environment
    ):
        _configure(monkeypatch, smtp=False, environment=environment)
        _request_reset(unauthed_client, staff_user.email)
        row = _reset_rows(db, staff_user.id)[0]
        old_hash = staff_user.password_hash

        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={"token": row.token, "new_password": "Hijacked123!"},
        )

        assert resp.status_code == 400
        assert "pending" in resp.json()["detail"].lower()
        db.refresh(staff_user)
        assert staff_user.password_hash == old_hash
        assert _reset_rows(db, staff_user.id)[0].status == "pending"
        mock_email.send_password_reset_completed.assert_not_called()


# =============================================================================
# The SMTP (admin approval email) flow is unchanged
# =============================================================================

class TestSmtpApprovalFlow:

    def test_request_emails_admin_with_approval_token(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch
    ):
        from app.core.config import settings
        _configure(monkeypatch, smtp=True)

        resp = _request_reset(unauthed_client, staff_user.email)

        assert resp.status_code == 200
        row = _reset_rows(db, staff_user.id)[0]
        assert row.status == "pending"
        mock_email.send_password_reset_approval_request.assert_called_once()
        kwargs = mock_email.send_password_reset_approval_request.call_args.kwargs
        assert kwargs["admin_email"] == settings.ADMIN_APPROVAL_EMAIL
        assert kwargs["user_email"] == staff_user.email
        assert kwargs["approval_token"] == row.approval_token
        assert kwargs["frontend_url"] == settings.FRONTEND_URL

    def test_full_email_flow_request_approve_complete_login(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch
    ):
        _configure(monkeypatch, smtp=True)

        # 1. User requests a reset; the admin is emailed the approval token.
        _request_reset(unauthed_client, staff_user.email)
        approval_token = mock_email.send_password_reset_approval_request.call_args.kwargs[
            "approval_token"
        ]

        # 2. Before approval, the reset token cannot be used.
        pending_token = _reset_rows(db, staff_user.id)[0].token
        early = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={"token": pending_token, "new_password": "TooEarly123!"},
        )
        assert early.status_code == 400

        # 3. Admin approves from the email link; the user is emailed the reset token.
        approve = unauthed_client.post(
            f"{AUTH_URL}/password-reset/approve",
            json={"approval_token": approval_token},
        )
        assert approve.status_code == 200
        assert approve.json()["status"] == "approved"
        assert pending_token not in approve.text
        reset_kwargs = mock_email.send_password_reset_approved.call_args.kwargs
        assert reset_kwargs["user_email"] == staff_user.email
        emailed_token = reset_kwargs["reset_token"]
        assert emailed_token == pending_token

        status_resp = unauthed_client.get(f"{AUTH_URL}/password-reset/status/{emailed_token}")
        assert status_resp.json()["can_reset"] is True

        # 4. User completes the reset with the emailed token.
        done = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={"token": emailed_token, "new_password": "BrandNewPass456!"},
        )
        assert done.status_code == 200
        assert emailed_token not in done.text
        mock_email.send_password_reset_completed.assert_called_once()

        # 5. The new password works; the token is single-use.
        login = unauthed_client.post(
            f"{AUTH_URL}/login",
            data={"username": staff_user.email, "password": "BrandNewPass456!"},
        )
        assert login.status_code == 200
        reuse = unauthed_client.post(
            f"{AUTH_URL}/password-reset/complete",
            json={"token": emailed_token, "new_password": "AgainPass789!"},
        )
        assert reuse.status_code == 400

    def test_deny_still_works(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch
    ):
        _configure(monkeypatch, smtp=True)
        _request_reset(unauthed_client, staff_user.email)
        approval_token = mock_email.send_password_reset_approval_request.call_args.kwargs[
            "approval_token"
        ]

        resp = unauthed_client.post(
            f"{AUTH_URL}/password-reset/deny",
            json={"approval_token": approval_token, "reason": "Not me"},
        )

        assert resp.status_code == 200
        assert resp.json()["status"] == "denied"
        mock_email.send_password_reset_denied.assert_called_once()


# =============================================================================
# The full reset token never reaches the logs
# =============================================================================

def _log_dump(caplog):
    return "\n".join(
        f"{r.getMessage()} {r.__dict__!r}" for r in caplog.records
    )


class TestTokenNotLogged:

    @pytest.mark.parametrize("environment", ENVIRONMENTS)
    @pytest.mark.parametrize("smtp", SMTP_MODES)
    def test_request_does_not_log_tokens(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch, caplog, smtp, environment
    ):
        _configure(monkeypatch, smtp=smtp, environment=environment)
        caplog.set_level(logging.DEBUG)

        _request_reset(unauthed_client, staff_user.email)

        row = _reset_rows(db, staff_user.id)[0]
        dump = _log_dump(caplog)
        assert row.token not in dump
        assert row.approval_token not in dump

    def test_no_smtp_request_logs_admin_hint(
        self, unauthed_client, db, staff_user, mock_email, monkeypatch, caplog
    ):
        _configure(monkeypatch, smtp=False)
        caplog.set_level(logging.INFO)

        _request_reset(unauthed_client, staff_user.email)

        assert any(
            "SMTP is not configured" in r.getMessage() and "Team Members" in r.getMessage()
            for r in caplog.records
        )

    def test_unconfigured_email_service_does_not_log_body(self, caplog):
        from app.services.email_service import EmailService

        service = EmailService()
        service.user = None
        service.password = None
        caplog.set_level(logging.DEBUG)
        secret_token = "tok_" + uuid.uuid4().hex
        secret_approval = "appr_" + uuid.uuid4().hex

        assert service.send_password_reset_approved(
            user_email="someone@filaops.dev",
            user_name="Someone",
            reset_token=secret_token,
            frontend_url="http://localhost",
        ) is False
        assert service.send_password_reset_approval_request(
            admin_email="admin@filaops.dev",
            user_email="someone@filaops.dev",
            user_name="Someone",
            approval_token=secret_approval,
            frontend_url="http://localhost",
        ) is False

        dump = _log_dump(caplog)
        assert secret_token not in dump
        assert secret_approval not in dump


# =============================================================================
# No-SMTP recovery path: admin sets the password from Team Members
# =============================================================================

class TestAdminResetPasswordRequiresAdmin:
    """POST /admin/users/{id}/reset-password is the documented no-SMTP recovery path."""

    def test_unauthenticated_is_rejected(self, unauthed_client, staff_user):
        resp = unauthed_client.post(
            f"{ADMIN_USERS_URL}/{staff_user.id}/reset-password",
            json={"new_password": "Takeover123!"},
        )
        assert resp.status_code == 401

    @pytest.mark.parametrize("account_type", ["operator", "customer"])
    def test_non_admin_is_forbidden(self, db, staff_user, account_type):
        caller = _make_user(db, account_type=account_type)
        old_hash = staff_user.password_hash

        with _client_for(db, caller) as non_admin:
            resp = non_admin.post(
                f"{ADMIN_USERS_URL}/{staff_user.id}/reset-password",
                json={"new_password": "Takeover123!"},
            )

        assert resp.status_code == 403
        db.refresh(staff_user)
        assert staff_user.password_hash == old_hash

    def test_admin_can_reset_and_user_can_log_in(
        self, client, db, staff_user, mock_email, monkeypatch
    ):
        """``client`` is the seeded admin (user 1) from conftest."""
        _configure(monkeypatch, smtp=False)
        # A pending no-SMTP request exists; the admin resets the password directly.
        _request_reset(client, staff_user.email)

        resp = client.post(
            f"{ADMIN_USERS_URL}/{staff_user.id}/reset-password",
            json={"new_password": "AdminSet123!"},
        )
        assert resp.status_code == 200
        assert "token" not in resp.text.lower()

        login = client.post(
            f"{AUTH_URL}/login",
            data={"username": staff_user.email, "password": "AdminSet123!"},
        )
        assert login.status_code == 200
