"""
Customer-facing emails name the business from Company Settings.

Found during the 4.2.0 production upgrade: the "Password Reset Denied" email
told the customer to contact info@yourcompany.com, because the email service
read only BUSINESS_EMAIL from .env and ignored the company email the admin
had entered in the UI. These tests pin down the order:

- Company Settings (company_name, company_email) when set;
- .env (BUSINESS_NAME, BUSINESS_EMAIL, SMTP_FROM_NAME) when those are blank;
- neither: "FilaOps" and "contact your administrator", never the shipped
  "Your Company Name" / "info@yourcompany.com" placeholders.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from email import message_from_string
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.services.email_identity import (
    FALLBACK_BUSINESS_NAME,
    build_email_identity,
    resolve_email_identity,
)

PLACEHOLDERS = ("yourcompany.com", "Your Company Name", "BLB3D Printing")

UI_NAME = "Acme Print Works"
UI_EMAIL = "help@acmeprint.works"
ENV_NAME = "Env Print Co"
ENV_EMAIL = "support@envprint.co"
ENV_FROM_NAME = "Env Print Mailer"


@pytest.fixture
def env_identity(monkeypatch):
    """Real-looking .env values."""
    monkeypatch.setattr(settings, "BUSINESS_NAME", ENV_NAME)
    monkeypatch.setattr(settings, "BUSINESS_EMAIL", ENV_EMAIL)
    monkeypatch.setattr(settings, "SMTP_FROM_NAME", ENV_FROM_NAME)


@pytest.fixture
def env_placeholders(monkeypatch):
    """The values .env ships with."""
    monkeypatch.setattr(settings, "BUSINESS_NAME", "Your Company Name")
    monkeypatch.setattr(settings, "BUSINESS_EMAIL", "info@yourcompany.com")
    monkeypatch.setattr(settings, "SMTP_FROM_NAME", "Your Company Name")


def _company_settings(db, *, name, email):
    from app.models.company_settings import CompanySettings

    row = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if row is None:
        row = CompanySettings(id=1)
        db.add(row)
    row.company_name = name
    row.company_email = email
    db.flush()
    return row


# =============================================================================
# Precedence
# =============================================================================

class TestBuildEmailIdentity:

    def test_company_settings_win_over_env(self, env_identity):
        identity = build_email_identity(UI_NAME, UI_EMAIL)

        assert identity.business_name == UI_NAME
        assert identity.support_email == UI_EMAIL
        assert identity.from_name == UI_NAME

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_blank_company_settings_fall_back_to_env(self, env_identity, blank):
        identity = build_email_identity(blank, blank)

        assert identity.business_name == ENV_NAME
        assert identity.support_email == ENV_EMAIL
        assert identity.from_name == ENV_FROM_NAME

    def test_both_blank_never_shows_placeholders(self, env_placeholders):
        identity = build_email_identity(None, None)

        assert identity.business_name == FALLBACK_BUSINESS_NAME
        assert identity.support_email is None
        assert identity.from_name == FALLBACK_BUSINESS_NAME

    def test_each_value_falls_back_on_its_own(self, env_identity):
        identity = build_email_identity(UI_NAME, None)

        assert identity.business_name == UI_NAME
        assert identity.support_email == ENV_EMAIL

    def test_from_name_uses_business_name_when_smtp_from_name_is_default(
        self, monkeypatch, env_placeholders
    ):
        monkeypatch.setattr(settings, "BUSINESS_NAME", ENV_NAME)

        assert build_email_identity(None, None).from_name == ENV_NAME

    @pytest.mark.parametrize("address", ["info@yourcompany.com", "me@example.com", "not-an-email"])
    def test_placeholder_company_email_is_ignored(self, env_identity, address):
        assert build_email_identity(UI_NAME, address).support_email == ENV_EMAIL

    def test_placeholder_company_name_is_ignored(self, env_identity):
        assert build_email_identity(" your company name ", None).business_name == ENV_NAME


class TestResolveFromDatabase:

    def test_company_settings_set(self, db, env_identity):
        _company_settings(db, name=UI_NAME, email=UI_EMAIL)

        identity = resolve_email_identity(db)

        assert (identity.business_name, identity.support_email) == (UI_NAME, UI_EMAIL)

    def test_company_settings_blank_uses_env(self, db, env_identity):
        _company_settings(db, name=None, email="")

        identity = resolve_email_identity(db)

        assert (identity.business_name, identity.support_email) == (ENV_NAME, ENV_EMAIL)

    def test_both_blank(self, db, env_placeholders):
        _company_settings(db, name="", email=None)

        identity = resolve_email_identity(db)

        assert identity.business_name == FALLBACK_BUSINESS_NAME
        assert identity.support_email is None


# =============================================================================
# What the customer actually receives
# =============================================================================

def _sent_message(send, **kwargs):
    """Call an EmailService sender with SMTP mocked; return the parsed email."""
    from app.services import email_service as email_module
    from app.services.email_service import EmailService

    service = EmailService()
    service.user = "mailer@example.com"
    service.password = "not-a-real-password"
    service.admin_approval_email = "owner@filaops.dev"

    with patch.object(email_module.smtplib, "SMTP") as smtp:
        assert getattr(service, send)(user_email="someone@filaops.dev", user_name="Someone", **kwargs)

    raw = smtp.return_value.__enter__.return_value.sendmail.call_args.args[2]
    message = message_from_string(raw)
    bodies = [part.get_payload(decode=True).decode() for part in message.walk() if not part.is_multipart()]
    return message["From"], "\n".join(bodies)


CUSTOMER_EMAILS = [
    pytest.param("send_password_reset_denied", {"reason": "Not verified"}, id="denied"),
    pytest.param("send_password_reset_completed", {}, id="completed"),
    pytest.param(
        "send_password_reset_approved",
        {"reset_token": "tok", "frontend_url": "http://localhost"},
        id="approved",
    ),
]


class TestRenderedEmails:

    @pytest.mark.parametrize("send,kwargs", CUSTOMER_EMAILS)
    def test_company_settings_set(self, db, env_identity, send, kwargs):
        _company_settings(db, name=UI_NAME, email=UI_EMAIL)

        sender, body = _sent_message(send, identity=resolve_email_identity(db), **kwargs)

        assert sender.startswith(UI_NAME)
        assert UI_NAME in body
        assert ENV_EMAIL not in body and ENV_NAME not in body
        if send != "send_password_reset_approved":
            assert UI_EMAIL in body
        assert not any(p in body or p in sender for p in PLACEHOLDERS)

    @pytest.mark.parametrize("send,kwargs", CUSTOMER_EMAILS)
    def test_company_settings_blank_uses_env(self, db, env_identity, send, kwargs):
        _company_settings(db, name=None, email=None)

        sender, body = _sent_message(send, identity=resolve_email_identity(db), **kwargs)

        assert sender.startswith(ENV_FROM_NAME)
        assert ENV_NAME in body
        if send != "send_password_reset_approved":
            assert ENV_EMAIL in body
        assert not any(p in body or p in sender for p in PLACEHOLDERS)

    @pytest.mark.parametrize("send,kwargs", CUSTOMER_EMAILS)
    def test_both_blank(self, db, env_placeholders, send, kwargs):
        _company_settings(db, name=None, email=None)

        sender, body = _sent_message(send, identity=resolve_email_identity(db), **kwargs)

        assert sender.startswith(FALLBACK_BUSINESS_NAME)
        if send != "send_password_reset_approved":
            assert "contact your administrator" in body
        assert not any(p in body or p in sender for p in PLACEHOLDERS)

    def test_without_identity_falls_back_to_env(self, env_identity):
        sender, body = _sent_message("send_password_reset_denied")

        assert sender.startswith(ENV_FROM_NAME)
        assert ENV_EMAIL in body

    def test_sender_name_with_comma_is_quoted(self, env_identity):
        from email.utils import getaddresses

        identity = build_email_identity("Smith, Jones", UI_EMAIL)

        sender, _ = _sent_message("send_password_reset_completed", identity=identity)

        assert sender.startswith('"Smith, Jones" <')
        # One address, not two: the comma stays inside the display name.
        (name, address), = getaddresses([sender])
        assert name == "Smith, Jones"
        assert address == settings.SMTP_FROM_EMAIL

    def test_line_breaks_in_name_never_reach_the_header(self, env_identity):
        identity = build_email_identity("Acme\r\nBcc: victim@evil.example", UI_EMAIL)

        assert identity.from_name == "Acme Bcc: victim@evil.example"
        sender, _ = _sent_message("send_password_reset_completed", identity=identity)
        assert "\r" not in sender and "\n" not in sender

    def test_business_name_is_html_escaped(self, env_identity):
        identity = build_email_identity("Smith & <Sons>", UI_EMAIL)

        _, body = _sent_message("send_password_reset_completed", identity=identity)

        assert "Smith &amp; &lt;Sons&gt;" in body
        assert "<Sons>" not in body


# =============================================================================
# The endpoint passes the Company Settings identity to the email service
# =============================================================================

def test_deny_endpoint_sends_company_settings_identity(db, unauthed_client, env_identity, monkeypatch):
    from app.api.v1.endpoints import auth as auth_mod
    from app.core.limiter import limiter
    from app.core.security import hash_password
    from app.models.user import PasswordResetRequest, User

    monkeypatch.setattr(limiter, "enabled", False)
    _company_settings(db, name=UI_NAME, email=UI_EMAIL)
    user = User(
        email=f"identity-{uuid.uuid4().hex[:8]}@filaops.dev",
        password_hash=hash_password("TestPass123!"),
        first_name="Id",
        last_name="Tester",
        account_type="operator",
        status="active",
    )
    db.add(user)
    db.flush()
    row = PasswordResetRequest(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        approval_token=secrets.token_urlsafe(32),
        status="pending",
        expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1),
    )
    db.add(row)
    db.flush()

    with patch.object(auth_mod, "email_service") as mock_email:
        resp = unauthed_client.post(
            "/api/v1/auth/password-reset/deny",
            json={"approval_token": row.approval_token, "reason": "Not me"},
        )

    assert resp.status_code == 200, resp.text
    identity = mock_email.send_password_reset_denied.call_args.kwargs["identity"]
    assert (identity.business_name, identity.support_email) == (UI_NAME, UI_EMAIL)
