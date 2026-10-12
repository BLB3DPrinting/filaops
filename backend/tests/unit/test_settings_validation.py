"""
Unit tests for app.core.settings credential validation.

Audit finding F12 (Portainer compatibility review) — production startup
must refuse to boot with placeholder SECRET_KEY/DB_PASSWORD; development
should warn but proceed.

A placeholder SECRET_KEY must never sign tokens: the placeholders are
public, so anyone could forge an access token for any user id with them.
Outside production the key is replaced with a random per-process key, an
error is logged and the security audit fails until a real key is set.
The other well-known weak keys the security audit fails on (for example
'changeme') are treated the same way outside production.
"""
import logging
import os
import re
import subprocess
import sys
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import jwt
import pytest

from app.core.settings import (
    KNOWN_WEAK_SECRET_KEYS,
    Settings,
    _SECRET_KEY_PLACEHOLDERS,
)
from scripts.security_audit import CheckStatus, SecurityAuditor

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SETTINGS_DEFAULT_SECRET_KEY = Settings.model_fields["SECRET_KEY"].default

# Every placeholder spelling the validator must catch: the list itself, the
# Settings field default, and upper-case / whitespace-padded variants.
_PLACEHOLDER_SECRET_KEYS = [
    "",
    "   ",
    "change-in-production",
    "your-secret-key-here",
    _SETTINGS_DEFAULT_SECRET_KEY,
    "CHANGE-IN-PRODUCTION",
    "Your-Secret-Key-Here",
    "  change-in-production  ",
    "\tchange-this-to-a-random-secret-key-in-production\n",
]

# Example keys that earlier FilaOps files published (compose files, .env
# examples, setup and deployment docs, the old built-in fallback).
_LEGACY_EXAMPLE_SECRET_KEYS = [
    "dev-only-change-in-production",
    "change-this-in-production-use-openssl-rand-hex-32",
    "change-me-generate-with-command-above",
    "another-64-char-random-string-here",
    "change-this-to-a-random-string",
    "change-this-to-any-random-text-you-want",
    "your-super-secret-key-change-this-in-production",
    "your-secret-key-here-change-in-production",
    "dev-secret-key-change-in-production",
    "paste-your-generated-key-here",
    "your_generated_secret_key_here",
    "generate-a-random-string-here",
    "<your-generated-key>",
    "<paste output here>",
    "<64-char-hex-string>",
    "<output of openssl rand -hex 32>",
    "<a different output of openssl rand -hex 32>",
    "  Another-64-Char-Random-String-Here\n",
]

# Well-known weak keys that are not shipped defaults. The security audit has
# always failed on them; outside production they are now replaced too.
_COMMON_WEAK_SECRET_KEYS = [
    "secret",
    "changeme",
    "development-secret-key",
    "test-secret-key",
    "supersecretkey",
    "mysecretkey",
    "CHANGEME",
    "  Secret\n",
]


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


class TestUploadFileFormatSettings:
    def test_allowed_file_formats_normalizes_env_values(self):
        s = Settings(
            _env_file=None,
            ENVIRONMENT="development",
            ALLOWED_FILE_FORMATS="3MF, .STL, obj, STEP, .stp",
        )
        assert s.ALLOWED_FILE_FORMATS == [".3mf", ".stl", ".obj", ".step", ".stp"]


class TestDevelopmentPlaceholderCredentials:
    def test_placeholder_secret_key_logs_error(self, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        _build("development", secret_key="change-in-production")
        assert any(
            record.levelno == logging.ERROR and "SECRET_KEY" in record.getMessage()
            for record in caplog.records
        ), "expected an error naming SECRET_KEY"

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
        # ...but the public placeholder is never kept as the signing key.
        assert s.SECRET_KEY.strip().lower() != "change-in-production"
        assert re.fullmatch(r"[0-9a-f]{64,}", s.SECRET_KEY)
        assert s.secret_key_is_temporary is True
        # DB_PASSWORD handling is unchanged: warned about, not replaced.
        assert s.DB_PASSWORD == "changeme"

    def test_real_credentials_no_warning(self, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        _build("development")
        placeholder_warnings = [
            r for r in caplog.records if "placeholder credential" in r.getMessage()
        ]
        assert not placeholder_warnings


def _forged_token(key: str) -> str:
    """An access token for user 1, as an attacker who knows `key` would sign it."""
    with warnings.catch_warnings():
        # Newer PyJWT warns about short HMAC keys; the placeholder is short.
        warnings.simplefilter("ignore")
        return jwt.encode(
            {
                "sub": "1",
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            key,
            algorithm="HS256",
        )


class TestTemporarySecretKeyOutsideProduction:
    """A placeholder SECRET_KEY is swapped for a random per-process key."""

    @pytest.mark.parametrize("placeholder", _PLACEHOLDER_SECRET_KEYS)
    def test_placeholder_is_replaced_in_development(self, placeholder, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        s = _build("development", secret_key=placeholder)

        assert s.SECRET_KEY.strip().lower() not in {
            "",
            "change-in-production",
            "your-secret-key-here",
            _SETTINGS_DEFAULT_SECRET_KEY,
        }
        assert s.SECRET_KEY != placeholder
        assert re.fullmatch(r"[0-9a-f]{64,}", s.SECRET_KEY)
        assert s.secret_key_is_temporary is True
        assert any(
            record.levelno == logging.ERROR and "SECRET_KEY" in record.getMessage()
            for record in caplog.records
        ), "expected an error naming SECRET_KEY"

    @pytest.mark.parametrize("example", _LEGACY_EXAMPLE_SECRET_KEYS)
    def test_legacy_example_key_is_replaced_in_development(self, example):
        s = _build("development", secret_key=example)
        assert s.SECRET_KEY != example
        assert re.fullmatch(r"[0-9a-f]{64,}", s.SECRET_KEY)
        assert s.secret_key_is_temporary is True

    @pytest.mark.parametrize("example", _LEGACY_EXAMPLE_SECRET_KEYS)
    def test_legacy_example_key_refused_in_production(self, example):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _build("production", secret_key=example)

    def test_legacy_example_keys_are_in_the_shared_list(self):
        # The security audit reads KNOWN_WEAK_SECRET_KEYS, so it fails on
        # these too.
        for example in _LEGACY_EXAMPLE_SECRET_KEYS:
            assert example.strip().lower() in _SECRET_KEY_PLACEHOLDERS
            assert example.strip().lower() in KNOWN_WEAK_SECRET_KEYS

    def test_settings_default_is_replaced(self, monkeypatch):
        # No SECRET_KEY anywhere: the field default (itself a placeholder) is
        # what pydantic hands the validator.
        monkeypatch.delenv("SECRET_KEY", raising=False)
        s = Settings(
            _env_file=None,
            ENVIRONMENT="development",
            DB_PASSWORD="real-db-pass-not-a-placeholder",
            DATABASE_URL=None,
        )
        assert s.SECRET_KEY != _SETTINGS_DEFAULT_SECRET_KEY
        assert re.fullmatch(r"[0-9a-f]{64,}", s.SECRET_KEY)
        assert s.secret_key_is_temporary is True

    @pytest.mark.parametrize("environment", ["test", "staging", "DEVELOPMENT", ""])
    def test_placeholder_is_replaced_in_every_non_production_environment(self, environment):
        s = _build(environment, secret_key="change-in-production")
        assert re.fullmatch(r"[0-9a-f]{64,}", s.SECRET_KEY)
        assert s.secret_key_is_temporary is True

    def test_each_build_gets_its_own_key(self):
        first = _build("development", secret_key="")
        second = _build("development", secret_key="")
        assert first.SECRET_KEY != second.SECRET_KEY

    def test_real_key_is_kept(self, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        real_key = "a1" * 32
        s = _build("development", secret_key=real_key)
        assert s.SECRET_KEY == real_key
        assert s.secret_key_is_temporary is False
        assert not [r for r in caplog.records if "SECRET_KEY" in r.getMessage()]

    def test_production_real_key_is_not_temporary(self):
        s = _build("production")
        assert s.secret_key_is_temporary is False

    def test_production_placeholder_still_raises(self):
        # Production never falls back to a temporary key.
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _build("production", secret_key="")

    def test_production_reports_both_placeholders(self):
        with pytest.raises(RuntimeError, match="SECRET_KEY, DB_PASSWORD"):
            _build("production", secret_key="", db_password="changeme")

    def test_token_signed_with_placeholder_is_rejected(self):
        s = _build("development", secret_key="change-in-production")
        forged = _forged_token("change-in-production")
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(forged, s.SECRET_KEY, algorithms=["HS256"])

    def test_token_signed_with_temporary_key_verifies(self):
        s = _build("development", secret_key="")
        token = _forged_token(s.SECRET_KEY)
        assert jwt.decode(token, s.SECRET_KEY, algorithms=["HS256"])["sub"] == "1"


class TestShortSecretKey:
    """A real key under 32 characters warns in every environment, never raises."""

    SHORT_KEY = "short-but-real-key-1234"  # 23 characters, not a placeholder

    @pytest.mark.parametrize("environment", ["development", "test", "production"])
    def test_short_key_warns_but_starts(self, environment, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        s = _build(environment, secret_key=self.SHORT_KEY)
        assert s.SECRET_KEY == self.SHORT_KEY
        assert s.secret_key_is_temporary is False
        assert any(
            record.levelno == logging.WARNING
            and "SECRET_KEY" in record.getMessage()
            and "32" in record.getMessage()
            for record in caplog.records
        ), "expected a warning about the short SECRET_KEY"

    def test_warning_names_the_minimum_length(self, caplog):
        # The warning writes the length as text (see settings.py); it must
        # match the constant the check uses.
        from app.core.settings import _SECRET_KEY_MIN_LENGTH

        caplog.set_level(logging.WARNING, logger="app.core.settings")
        _build("development", secret_key=self.SHORT_KEY)
        assert any(
            f"shorter than {_SECRET_KEY_MIN_LENGTH} characters" in r.getMessage()
            for r in caplog.records
        )

    def test_32_character_key_does_not_warn(self, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        _build("production", secret_key="k" * 32)
        assert not [r for r in caplog.records if "SECRET_KEY" in r.getMessage()]


class TestCommonWeakSecretKey:
    """The startup check and the security audit agree on which keys are weak.

    A key the audit calls weak (for example 'changeme' or 'secret') is as easy
    to guess as a placeholder, so outside production it is replaced with a
    temporary key too. Production keeps starting with it, because short keys
    are not refused there yet, but it logs an error.
    """

    def test_one_list_covers_every_placeholder(self):
        assert _SECRET_KEY_PLACEHOLDERS <= KNOWN_WEAK_SECRET_KEYS
        for value in _COMMON_WEAK_SECRET_KEYS:
            assert value.strip().lower() in KNOWN_WEAK_SECRET_KEYS

    @pytest.mark.parametrize("weak_key", _COMMON_WEAK_SECRET_KEYS)
    @pytest.mark.parametrize("environment", ["development", "test"])
    def test_weak_key_is_replaced_outside_production(self, environment, weak_key, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        s = _build(environment, secret_key=weak_key)

        assert s.SECRET_KEY != weak_key
        assert re.fullmatch(r"[0-9a-f]{64,}", s.SECRET_KEY)
        assert s.secret_key_is_temporary is True
        assert any(
            record.levelno == logging.ERROR and "SECRET_KEY" in record.getMessage()
            for record in caplog.records
        ), "expected an error naming SECRET_KEY"

    def test_token_signed_with_a_weak_key_is_rejected(self):
        s = _build("development", secret_key="changeme")
        forged = _forged_token("changeme")
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(forged, s.SECRET_KEY, algorithms=["HS256"])

    @pytest.mark.parametrize("weak_key", ["changeme", "test-secret-key"])
    def test_production_keeps_starting_but_logs_an_error(self, weak_key, caplog):
        caplog.set_level(logging.WARNING, logger="app.core.settings")
        s = _build("production", secret_key=weak_key)

        assert s.SECRET_KEY == weak_key
        assert s.secret_key_is_temporary is False
        assert any(
            record.levelno == logging.ERROR
            and "SECRET_KEY" in record.getMessage()
            and "well-known weak value" in record.getMessage()
            for record in caplog.records
        ), "expected an error about the well-known weak SECRET_KEY"

    def test_production_audit_fails_on_a_weak_key(self):
        result = TestSecurityAuditTemporaryKey._secret_key_check(
            _build("production", secret_key="changeme")
        )
        assert result.status == CheckStatus.FAIL
        assert "known weak" in result.message.lower()

    def test_production_audit_fails_on_the_compose_placeholder_spelling(self):
        # 'change-in-production' was missing from the audit's own list. It
        # cannot reach the audit through Settings (production refuses it,
        # other environments replace it), so check the list directly.
        result = TestSecurityAuditTemporaryKey._secret_key_check(
            SimpleNamespace(SECRET_KEY=" Change-In-Production ", secret_key_is_temporary=False)
        )
        assert result.status == CheckStatus.FAIL
        assert "known weak" in result.message.lower()


class TestSecurityAuditTemporaryKey:
    """The Security page keeps asking for a real key while a temporary one is in use."""

    @staticmethod
    def _secret_key_check(settings_obj):
        auditor = SecurityAuditor()
        auditor._settings = settings_obj
        auditor.results = []
        auditor._check_secret_key_not_default()
        (result,) = auditor.results
        return result

    @staticmethod
    def _entropy_check(settings_obj):
        auditor = SecurityAuditor()
        auditor._settings = settings_obj
        auditor.results = []
        auditor._check_secret_key_entropy()
        (result,) = auditor.results
        return result

    def test_temporary_key_fails_the_audit(self):
        result = self._secret_key_check(_build("development", secret_key=""))
        assert result.id == "secret_key_not_default"
        assert result.status == CheckStatus.FAIL
        assert "temporary secret_key in use" in result.message.lower()
        assert "openssl rand -hex 32" in (result.remediation or "")

    def test_real_key_passes_the_audit(self):
        result = self._secret_key_check(_build("development", secret_key="a1" * 32))
        assert result.status == CheckStatus.PASS

    def test_temporary_key_does_not_pass_the_entropy_check(self):
        # The random replacement is 64 hex characters; the entropy check used
        # to pass it next to the FAIL above for the same missing key.
        result = self._entropy_check(_build("development", secret_key=""))
        assert result.id == "secret_key_entropy"
        assert result.status == CheckStatus.FAIL
        assert "temporary" in result.message.lower()
        assert "openssl rand -hex 32" in (result.remediation or "")

    def test_real_long_key_passes_the_entropy_check(self):
        result = self._entropy_check(
            _build("development", secret_key="9f2c4e7a1b3d5f6e8a0c2e4f6b8d0a1c3e5f7b9d1a3c5e7f9b2d4f6a8c0e2b4d")
        )
        assert result.status == CheckStatus.PASS


def test_app_signs_with_the_replacement_key_not_the_placeholder():
    """End to end in a fresh interpreter: app.core.security copies
    settings.SECRET_KEY at import time, so it must see the replacement, and a
    token forged with the public placeholder must not authenticate."""
    script = (
        "import jwt\n"
        "from datetime import datetime, timedelta, timezone\n"
        "from app.core import security\n"
        "from app.core.settings import settings\n"
        "assert settings.secret_key_is_temporary is True, 'flag not set'\n"
        "assert security.SECRET_KEY == settings.SECRET_KEY, 'security.py kept another key'\n"
        "assert security.SECRET_KEY.strip().lower() != 'change-in-production'\n"
        "forged = jwt.encode({'sub': '1', 'type': 'access',\n"
        "    'exp': datetime.now(timezone.utc) + timedelta(minutes=5)},\n"
        "    'change-in-production', algorithm='HS256')\n"
        "assert security.get_user_from_token(forged, expected_type='access') is None, 'forged token accepted'\n"
        "real = security.create_access_token(1)\n"
        "assert security.get_user_from_token(real, expected_type='access') == 1\n"
        "print('OK')\n"
    )
    env = dict(os.environ)
    env.update(
        ENVIRONMENT="development",
        SECRET_KEY="change-in-production",
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=_BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("OK")
