"""
One production check.

Every place that behaves differently in production reads ENVIRONMENT through
Settings.is_production (or is_production_environment() for code that reads
the process environment itself), trimmed and in any case. Before, main.py
compared the raw string, so ENVIRONMENT=Production or "production " refused
a placeholder SECRET_KEY at startup but left Swagger on and HSTS off.
"""
from types import SimpleNamespace

import pytest

from app.core.settings import Settings, is_production_environment

PRODUCTION_SPELLINGS = ["production", "Production", " production ", "PRODUCTION", "production\n"]
NOT_PRODUCTION = ["development", "test", "prod", "staging", "", "   "]


def _settings(environment, **overrides):
    values = dict(
        _env_file=None,
        ENVIRONMENT=environment,
        SECRET_KEY="f" * 64,
        DB_PASSWORD="real-db-pass-not-a-placeholder",
        DATABASE_URL=None,
    )
    values.update(overrides)
    return Settings(**values)


class TestIsProduction:

    @pytest.mark.parametrize("environment", PRODUCTION_SPELLINGS)
    def test_production_spellings(self, environment):
        assert is_production_environment(environment) is True
        assert _settings(environment).is_production is True

    @pytest.mark.parametrize("environment", NOT_PRODUCTION)
    def test_other_values(self, environment):
        assert is_production_environment(environment) is False
        assert _settings(environment).is_production is False

    def test_missing_value_is_not_production(self):
        assert is_production_environment(None) is False

    @pytest.mark.parametrize("environment", [" development ", "Development"])
    def test_is_development_reads_the_same_way(self, environment):
        assert _settings(environment).is_development is True


class TestPlaceholderKeyRefused:

    @pytest.mark.parametrize("environment", PRODUCTION_SPELLINGS)
    def test_placeholder_secret_key_refused(self, environment):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            _settings(environment, SECRET_KEY="change-in-production")


class TestSwaggerOff:

    @pytest.mark.parametrize("environment", PRODUCTION_SPELLINGS)
    def test_docs_disabled_in_production(self, environment):
        from app.main import _api_docs_urls

        assert _api_docs_urls(_settings(environment)) == {
            "docs_url": None,
            "redoc_url": None,
            "openapi_url": None,
        }

    def test_docs_enabled_outside_production(self):
        from app.main import _api_docs_urls

        assert _api_docs_urls(_settings("development")) == {
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
        }


class TestHstsOn:

    @pytest.mark.parametrize("environment", PRODUCTION_SPELLINGS)
    def test_hsts_header_in_production(self, unauthed_client, monkeypatch, environment):
        from app.core.config import settings
        monkeypatch.setattr(settings, "ENVIRONMENT", environment)

        resp = unauthed_client.get("/api/v1/system/version")

        assert resp.status_code == 200
        assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"

    def test_no_hsts_header_outside_production(self, unauthed_client, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "ENVIRONMENT", "development")

        resp = unauthed_client.get("/api/v1/system/version")

        assert resp.status_code == 200
        assert "Strict-Transport-Security" not in resp.headers


class TestOtherProductionChecks:

    @pytest.mark.parametrize("environment", PRODUCTION_SPELLINGS)
    def test_test_endpoints_stay_off_with_testing_flag(self, monkeypatch, environment):
        # Aliased: the real name starts with "test_".
        from app.api.v1.endpoints.test import test_endpoints_enabled as endpoints_enabled

        monkeypatch.setenv("ENVIRONMENT", environment)
        monkeypatch.setenv("TESTING", "true")

        assert endpoints_enabled() is False

    @pytest.mark.parametrize("environment", PRODUCTION_SPELLINGS)
    def test_security_audit_sees_production(self, environment):
        from scripts.security_audit import CheckStatus, SecurityAuditor

        auditor = SecurityAuditor()
        auditor._settings = SimpleNamespace(ENVIRONMENT=environment)
        auditor.results = []
        auditor._check_environment_production()

        (result,) = auditor.results
        assert result.status == CheckStatus.PASS
