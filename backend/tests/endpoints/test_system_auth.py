"""
Auth tests for system endpoints (/api/v1/system/).

/version, /info, and /health are intentionally public (pre-login SPA
bootstrap and monitoring probes). /updates/check and /updates/instructions
require staff authentication.
"""


class TestSystemPublicEndpoints:
    """Version, info, and health stay reachable without authentication."""

    def test_version_is_public(self, unauthed_client):
        """GET /system/version returns 200 without auth (login page footer)."""
        resp = unauthed_client.get("/api/v1/system/version")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"version", "build_date", "install_method"}

    def test_info_is_public(self, unauthed_client):
        """GET /system/info returns 200 without auth (pre-login feature gating)."""
        resp = unauthed_client.get("/api/v1/system/info")
        assert resp.status_code == 200
        assert "tier" in resp.json()

    def test_health_is_public(self, unauthed_client):
        """GET /system/health returns 200 without auth (monitoring probe)."""
        resp = unauthed_client.get("/api/v1/system/health")
        assert resp.status_code == 200


class TestSystemUpdateEndpointsRequireAuth:
    """Update channel endpoints must reject unauthenticated requests with 401."""

    def test_updates_check_requires_auth(self, unauthed_client):
        """GET /system/updates/check returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/system/updates/check")
        assert resp.status_code == 401

    def test_updates_instructions_requires_auth(self, unauthed_client):
        """GET /system/updates/instructions returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/system/updates/instructions")
        assert resp.status_code == 401

    def test_updates_check_accessible_with_auth(self, client, monkeypatch):
        """GET /system/updates/check returns 200 with valid staff auth."""
        from app.core.version import VersionManager

        # Avoid a live GitHub API call in unit tests
        monkeypatch.setattr(
            VersionManager,
            "check_for_updates",
            staticmethod(lambda: {
                "update_available": False,
                "current_version": "0.0.0-test",
            }),
        )
        resp = client.get("/api/v1/system/updates/check")
        assert resp.status_code == 200
        assert resp.json()["update_available"] is False

    def test_updates_instructions_accessible_with_auth(self, client):
        """GET /system/updates/instructions returns 200 with valid staff auth."""
        resp = client.get("/api/v1/system/updates/instructions")
        assert resp.status_code == 200
        assert "instructions" in resp.json()
