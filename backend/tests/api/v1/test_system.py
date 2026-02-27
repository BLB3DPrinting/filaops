"""Tests for /api/v1/system endpoints (tier, features, version)."""

import pytest
from app.core import plugin_registry


BASE_URL = "/api/v1/system"


@pytest.fixture(autouse=True)
def _reset_registry():
    """Ensure each test starts with clean community defaults."""
    plugin_registry.reset()
    yield
    plugin_registry.reset()


# ── /system/info ─────────────────────────────────────────────────

class TestSystemInfoDefaults:
    """Community defaults — no plugin installed."""

    def test_info_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/info")
        assert resp.status_code == 200

    def test_info_default_tier_is_community(self, client):
        data = client.get(f"{BASE_URL}/info").json()
        assert data["tier"] == "community"

    def test_info_default_features_empty(self, client):
        data = client.get(f"{BASE_URL}/info").json()
        assert data["features_enabled"] == []

    def test_info_includes_version(self, client):
        data = client.get(f"{BASE_URL}/info").json()
        assert "version" in data
        assert isinstance(data["version"], str)


class TestSystemInfoWithPlugin:
    """Simulate PRO plugin having called set_tier/set_features."""

    def test_tier_reflects_registry(self, client):
        plugin_registry.set_tier("professional")
        data = client.get(f"{BASE_URL}/info").json()
        assert data["tier"] == "professional"

    def test_features_reflect_registry(self, client):
        plugin_registry.set_features(["b2b_portal", "quote_engine"])
        data = client.get(f"{BASE_URL}/info").json()
        assert data["features_enabled"] == ["b2b_portal", "quote_engine"]

    def test_tier_and_features_together(self, client):
        plugin_registry.set_tier("enterprise")
        plugin_registry.set_features(["advanced_tax", "cortex"])
        data = client.get(f"{BASE_URL}/info").json()
        assert data["tier"] == "enterprise"
        assert set(data["features_enabled"]) == {"advanced_tax", "cortex"}


# ── /system/version ──────────────────────────────────────────────

class TestSystemVersion:
    def test_version_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/version")
        assert resp.status_code == 200

    def test_version_has_expected_fields(self, client):
        data = client.get(f"{BASE_URL}/version").json()
        assert "version" in data
        assert "build_date" in data


# ── plugin_registry unit tests ───────────────────────────────────

class TestPluginRegistry:
    """Direct unit tests for the registry module."""

    def test_default_tier(self):
        assert plugin_registry.get_tier() == "community"

    def test_default_features(self):
        assert plugin_registry.get_features() == []

    def test_set_tier(self):
        plugin_registry.set_tier("professional")
        assert plugin_registry.get_tier() == "professional"

    def test_set_features(self):
        plugin_registry.set_features(["a", "b"])
        assert plugin_registry.get_features() == ["a", "b"]

    def test_get_features_returns_copy(self):
        plugin_registry.set_features(["a"])
        features = plugin_registry.get_features()
        features.append("b")
        assert plugin_registry.get_features() == ["a"]

    def test_reset(self):
        plugin_registry.set_tier("pro")
        plugin_registry.set_features(["x"])
        plugin_registry.reset()
        assert plugin_registry.get_tier() == "community"
        assert plugin_registry.get_features() == []
