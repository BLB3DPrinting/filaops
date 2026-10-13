"""
Unit tests for the one "is email configured" rule (app.core.settings).

Email counts as configured only when the SMTP login is set and
ADMIN_APPROVAL_EMAIL is a real address. Password reset approve/deny links are
emailed to that address, and it defaults to admin@example.com, so a shop that
set only the SMTP login must not send them to a placeholder domain.
"""
import pytest

from app.core.settings import Settings, email_is_configured, is_placeholder_email

REAL_ADDRESSES = [
    "owner@filaops.dev",
    "Admin@FilaOps.Dev",
    "  ops@shop.co.uk  ",
    "admin@examples.com",
    "admin@myexample.com",
    "admin@example.com.au",
    "admin@mail.testing.io",
]

PLACEHOLDER_ADDRESSES = [
    None,
    "",
    "   ",
    "admin@example.com",
    "ADMIN@EXAMPLE.COM",
    " admin@example.com ",
    "admin@example.org",
    "admin@example.net",
    "admin@example.com.",
    "owner@mail.example.com",
    "owner@shop.example",
    "owner@shop.test",
    "owner@shop.invalid",
    "admin@localhost",
    "admin@app.localhost",
    "admin@localhost.localdomain",
    "not-an-address",
    "@example.org",
    "admin@",
    "admin@@shop.com",
    "admin@shop@mail.com",
    "ad min@shop.com",
]


class TestIsPlaceholderEmail:

    @pytest.mark.parametrize("address", PLACEHOLDER_ADDRESSES)
    def test_placeholder_and_empty_addresses(self, address):
        assert is_placeholder_email(address) is True

    @pytest.mark.parametrize("address", REAL_ADDRESSES)
    def test_real_addresses(self, address):
        assert is_placeholder_email(address) is False


class TestEmailIsConfigured:

    @pytest.mark.parametrize("address", REAL_ADDRESSES)
    def test_smtp_login_and_real_address(self, address):
        assert email_is_configured("mailer@filaops.dev", "app-password", address) is True

    @pytest.mark.parametrize("address", PLACEHOLDER_ADDRESSES)
    def test_placeholder_or_empty_address_means_off(self, address):
        assert email_is_configured("mailer@filaops.dev", "app-password", address) is False

    @pytest.mark.parametrize(
        "user,password",
        [
            (None, "app-password"),
            ("mailer@filaops.dev", None),
            ("", "app-password"),
            ("mailer@filaops.dev", "   "),
            (None, None),
        ],
    )
    def test_missing_smtp_login_means_off(self, user, password):
        assert email_is_configured(user, password, "owner@filaops.dev") is False


class TestSettingsEmailConfigured:

    @staticmethod
    def _settings(**overrides):
        values = dict(
            _env_file=None,
            ENVIRONMENT="development",
            SECRET_KEY="f" * 64,
            DB_PASSWORD="real-db-pass-not-a-placeholder",
            DATABASE_URL=None,
            SMTP_USER="mailer@filaops.dev",
            SMTP_PASSWORD="app-password",
        )
        values.update(overrides)
        return Settings(**values)

    def test_stock_default_address_means_off(self, monkeypatch):
        monkeypatch.delenv("ADMIN_APPROVAL_EMAIL", raising=False)
        s = self._settings()
        assert s.ADMIN_APPROVAL_EMAIL == "admin@example.com"
        assert s.email_configured is False

    def test_empty_address_means_off(self):
        assert self._settings(ADMIN_APPROVAL_EMAIL="").email_configured is False

    def test_real_address_means_on(self):
        assert self._settings(ADMIN_APPROVAL_EMAIL="owner@filaops.dev").email_configured is True

    def test_real_address_without_smtp_login_means_off(self):
        s = self._settings(
            ADMIN_APPROVAL_EMAIL="owner@filaops.dev", SMTP_USER=None, SMTP_PASSWORD=None
        )
        assert s.email_configured is False
