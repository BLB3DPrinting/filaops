"""
Unit tests for app.core.settings credential validation.

Audit finding F12 (Portainer compatibility review) — production startup
must refuse to boot with placeholder SECRET_KEY/DB_PASSWORD; development
should warn but proceed.
"""
import logging

import pytest

from app.core.settings import Settings


def _build(environment: str, *, secret_key: str = "f" * 64, db_password: str = "real-db-pass-not-a-placeholder"):
    """Construct a Settings instance bypassing the on-disk .env file."""
    return Settings(
        _env_file=None,
        ENVIRONMENT=environment,
        SECRET_KEY=secret_key,
        DB_PASSWORD=db_password,
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

    def test_database_url_set_skips_db_password_check(self):
        # When DATABASE_URL overrides DB_PASSWORD, the placeholder default is
        # irrelevant — startup must not block on it.
        s = Settings(
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="f" * 64,
            DB_PASSWORD="changeme",
            DATABASE_URL="postgresql+psycopg://realuser:realpass@db:5432/filaops",
        )
        assert s.is_production


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
