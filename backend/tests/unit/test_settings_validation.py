"""
Unit tests for app.core.settings credential validation.

Audit finding F12 (Portainer compatibility review) — production startup
must refuse to boot with placeholder SECRET_KEY/DB_PASSWORD; development
should warn but proceed.
"""
import logging
from typing import Optional

import pytest

from app.core.settings import Settings


def _build(
    environment: str,
    *,
    secret_key: str = "f" * 64,
    db_password: str = "real-db-pass-not-a-placeholder",
    database_url: Optional[str] = None,
):
    """Construct a Settings instance with hermetic config.

    `_env_file=None` disables the on-disk .env, but pydantic-settings still
    reads OS environment variables. CI exports DATABASE_URL, which would
    silently route around the DB_PASSWORD branch of the validator. Passing
    `DATABASE_URL=database_url` (default None) explicitly overrides any
    inherited env var so each test exercises the branch it claims to.
    """
    return Settings(
        _env_file=None,
        ENVIRONMENT=environment,
        SECRET_KEY=secret_key,
        DB_PASSWORD=db_password,
        DATABASE_URL=database_url,
    )


class TestProductionPlaceholderCredentials:
    def test_placeholder_secret_key_raises(self):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _build("production", secret_key="change-in-production")

    def test_placeholder_db_password_raises(self):
        with pytest.raises(RuntimeError, match="DB_PASSWORD"):
            _build("production", db_password="changeme")

    def test_empty_secret_key_raises(self):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _build("production", secret_key="")

    def test_compose_default_secret_key_raises(self):
        # Settings field default value
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _build("production", secret_key="change-this-to-a-random-secret-key-in-production")

    def test_error_message_includes_openssl_hint(self):
        with pytest.raises(RuntimeError, match=r"openssl rand"):
            _build("production", secret_key="change-in-production")

    def test_real_credentials_pass(self):
        s = _build("production")
        assert s.is_production
        assert s.SECRET_KEY

    def test_uppercase_placeholder_still_rejected(self):
        # Case-insensitive comparison so CHANGEME / Password don't slip through.
        with pytest.raises(RuntimeError, match="DB_PASSWORD"):
            _build("production", db_password="CHANGEME")

    def test_whitespace_padded_placeholder_still_rejected(self):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _build("production", secret_key="  change-in-production  ")

    def test_whitespace_padded_environment_still_triggers_gate(self):
        # ENVIRONMENT="production " (trailing space) must not silently fall
        # into the warning path — that turns the safeguard into mood lighting.
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _build("production ", secret_key="change-in-production")


class TestDatabaseUrlPasswordValidation:
    """The effective DB password is whatever `database_url` hands to
    SQLAlchemy — the URL's password when DATABASE_URL is set, else
    DB_PASSWORD. Validating only DB_PASSWORD would leave docker-compose's
    `DATABASE_URL: ...:${DB_PASSWORD:-changeme}@db/...` as an open airlock.
    """

    def test_url_with_placeholder_password_raises(self):
        with pytest.raises(RuntimeError, match="DB_PASSWORD"):
            _build(
                "production",
                db_password="real-not-checked-because-url-overrides",
                database_url="postgresql+psycopg://user:changeme@db:5432/filaops",
            )

    def test_url_with_real_password_passes(self):
        s = _build(
            "production",
            db_password="changeme",  # ignored — URL takes precedence
            database_url="postgresql+psycopg://user:strongpw-actually-set@db:5432/filaops",
        )
        assert s.is_production

    def test_url_without_password_skips_check(self):
        # No password in the URL = peer auth, trust auth, .pgpass, or IAM
        # auth. These are legitimate production configs; do NOT fail-closed.
        s = _build(
            "production",
            db_password="changeme",  # not used at runtime when URL is set
            database_url="postgresql+psycopg://user@db:5432/filaops",
        )
        assert s.is_production

    def test_url_with_url_encoded_placeholder_password_raises(self):
        # %63%68%61%6e%67%65%6d%65 decodes to "changeme". This proves
        # urllib.parse end-to-end decoding works and prevents a future
        # refactor from accidentally comparing the encoded form.
        with pytest.raises(RuntimeError, match="DB_PASSWORD"):
            _build(
                "production",
                database_url="postgresql+psycopg://user:%63%68%61%6e%67%65%6d%65@db:5432/filaops",
            )


class TestDevelopmentPlaceholderCredentials:
    def test_placeholder_secret_key_logs_warning(self, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        _build("development", secret_key="change-in-production")
        assert any(
            "SECRET_KEY" in record.getMessage() for record in caplog.records
        ), "expected a warning naming SECRET_KEY"

    def test_placeholder_db_password_logs_warning(self, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        _build("development", db_password="changeme")
        assert any(
            "DB_PASSWORD" in record.getMessage() for record in caplog.records
        ), "expected a warning naming DB_PASSWORD"

    def test_placeholder_does_not_raise_in_development(self):
        # Must not raise — kick-the-tires UX is preserved.
        s = _build("development", secret_key="change-in-production", db_password="changeme")
        assert s.is_development

    def test_real_credentials_no_warning(self, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        _build("development")
        placeholder_warnings = [
            r for r in caplog.records if "placeholder credential" in r.getMessage()
        ]
        assert not placeholder_warnings
