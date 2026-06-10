"""
Auth tests for test seeding endpoints (/api/v1/test/).

Seeding and cleanup endpoints must require staff authentication even in
non-production environments.  The /health endpoint is intentionally public.

The router is only registered when ENVIRONMENT != 'production' (handled in
api/v1/__init__.py), so these tests run in the default 'development' environment
that pytest uses.
"""
import pytest


BASE_URL = "/api/v1/test"


class TestSeedingEndpointsRequireAuth:
    """Unauthenticated requests to destructive/seeding endpoints return 401."""

    def test_scenarios_unauthed_returns_401(self, unauthed_client):
        """GET /test/scenarios requires staff auth."""
        resp = unauthed_client.get(f"{BASE_URL}/scenarios")
        assert resp.status_code == 401

    def test_seed_unauthed_returns_401(self, unauthed_client):
        """POST /test/seed requires staff auth."""
        resp = unauthed_client.post(
            f"{BASE_URL}/seed",
            json={"scenario": "basic"},
        )
        assert resp.status_code == 401

    def test_cleanup_unauthed_returns_401_or_403(self, unauthed_client):
        """POST /test/cleanup is blocked for unauthenticated users.

        Returns 401 (no auth) or 403 (ALLOW_TEST_DATA_WIPE not set) depending
        on which dependency FastAPI evaluates first.  Either code means the
        request is properly rejected.
        """
        resp = unauthed_client.post(f"{BASE_URL}/cleanup")
        assert resp.status_code in (401, 403)


class TestSeedingHealthEndpointPublic:
    """GET /test/health is intentionally public — no destructive capability."""

    def test_health_unauthenticated_returns_200(self, unauthed_client):
        """Health check is accessible without auth for CI diagnostics."""
        resp = unauthed_client.get(f"{BASE_URL}/health")
        assert resp.status_code == 200

    def test_health_returns_expected_fields(self, unauthed_client):
        data = unauthed_client.get(f"{BASE_URL}/health").json()
        assert "status" in data
        assert "test_mode" in data
        assert "environment" in data
        assert data["status"] == "ok"


class TestSeedingEndpointsAuthenticatedStaff:
    """Authenticated staff can reach non-destructive test endpoints."""

    def test_scenarios_authed_staff_returns_200(self, client):
        """GET /test/scenarios returns 200 for authenticated staff."""
        resp = client.get(f"{BASE_URL}/scenarios")
        assert resp.status_code == 200

    def test_scenarios_response_is_list(self, client):
        data = client.get(f"{BASE_URL}/scenarios").json()
        assert "scenarios" in data
        assert isinstance(data["scenarios"], list)
