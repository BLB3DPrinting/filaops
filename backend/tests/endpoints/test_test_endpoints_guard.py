"""
Guard tests for the test-data seeding endpoints (/api/v1/test/).

The test router is opt-in: enabled only when ENVIRONMENT is test/ci/e2e or
TESTING is truthy, and never in production. These tests exercise the
test_endpoints_enabled() / require_test_mode() guards directly because
router registration happens at import time.
"""
import pytest
from fastapi import HTTPException

# Alias: the real name starts with "test_", which pytest would collect
# as a test function if imported unaliased into this module.
from app.api.v1.endpoints.test import (
    require_test_mode,
    test_endpoints_enabled as endpoints_enabled,
)


class TestTestEndpointsEnabled:
    """test_endpoints_enabled() must only allow explicit opt-in."""

    def test_disabled_in_production(self, monkeypatch):
        """Production is always disabled, even with TESTING=true."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("TESTING", "true")
        assert endpoints_enabled() is False

    def test_disabled_in_plain_development(self, monkeypatch):
        """Default development deployments do not expose test endpoints."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("TESTING", raising=False)
        assert endpoints_enabled() is False

    def test_disabled_when_no_env_set(self, monkeypatch):
        """Unset ENVIRONMENT defaults to development → disabled."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("TESTING", raising=False)
        assert endpoints_enabled() is False

    @pytest.mark.parametrize("env", ["test", "ci", "e2e", "TEST", "CI"])
    def test_enabled_in_test_environments(self, monkeypatch, env):
        """ENVIRONMENT=test/ci/e2e enables test endpoints."""
        monkeypatch.setenv("ENVIRONMENT", env)
        monkeypatch.delenv("TESTING", raising=False)
        assert endpoints_enabled() is True

    @pytest.mark.parametrize("flag", ["1", "true", "TRUE", "yes"])
    def test_enabled_with_testing_flag(self, monkeypatch, flag):
        """TESTING truthy enables test endpoints outside production."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("TESTING", flag)
        assert endpoints_enabled() is True

    def test_disabled_with_falsy_testing_flag(self, monkeypatch):
        """TESTING=false does not enable test endpoints."""
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.setenv("TESTING", "false")
        assert endpoints_enabled() is False


class TestRequireTestMode:
    """require_test_mode() raises 403 unless test endpoints are enabled."""

    def test_raises_403_when_disabled(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "development")
        monkeypatch.delenv("TESTING", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            require_test_mode()
        assert exc_info.value.status_code == 403

    def test_passes_when_enabled(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "test")
        assert require_test_mode() is True
