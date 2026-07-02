"""Tests for the live PRO feature gate (app.core.licensing_gate.require_feature).

Covers (PR-D1 — the PRO-leak keystone):
- Direct unit tests of require_feature / feature_enabled (fail-closed).
- Per-router HTTP tests for the three gated features:
    * accounting          -> require_feature("accounting")
    * reports_advanced    -> require_feature("reports_advanced")  (admin analytics)
    * production_advanced -> require_feature("production_advanced") (scheduling auto-schedule)

For each router: unlicensed/community (no feature in plugin_registry) => 403;
licensed (feature present) => NOT 403 (the gate no longer blocks; the request
reaches the handler).

The unlicensed=>403 path is exercised by the gate dependency *before* the
DB-backed handler runs, so those assertions hold even without seeded data.
The licensed path reaches the handler and therefore relies on the seeded
Postgres fixture (as the rest of the suite does).
"""

import pytest
from fastapi import HTTPException

from app.core import plugin_registry
from app.core.licensing_gate import feature_enabled, require_feature, UPGRADE_MESSAGE


@pytest.fixture(autouse=True)
def _reset_registry():
    """Each test starts and ends with clean community defaults (no features)."""
    plugin_registry.reset()
    yield
    plugin_registry.reset()


# ── Direct unit tests: require_feature / feature_enabled ─────────────

class TestRequireFeatureUnit:
    """The gate must FAIL CLOSED: absent entitlement => deny."""

    def test_feature_enabled_false_on_empty(self):
        # Community default is an empty feature list.
        assert plugin_registry.get_features() == []
        assert feature_enabled("accounting") is False

    def test_feature_enabled_false_on_missing_key(self):
        plugin_registry.set_features(["reports_advanced"])
        assert feature_enabled("accounting") is False

    def test_feature_enabled_false_on_empty_key(self):
        plugin_registry.set_features(["accounting"])
        assert feature_enabled("") is False

    def test_feature_enabled_true_when_licensed(self):
        plugin_registry.set_features(["accounting"])
        assert feature_enabled("accounting") is True

    def test_require_feature_raises_403_when_unlicensed(self):
        dep = require_feature("accounting")
        with pytest.raises(HTTPException) as exc:
            dep()
        assert exc.value.status_code == 403
        assert exc.value.detail == UPGRADE_MESSAGE

    def test_require_feature_raises_403_on_wrong_key(self):
        plugin_registry.set_features(["reports_advanced"])
        dep = require_feature("accounting")
        with pytest.raises(HTTPException) as exc:
            dep()
        assert exc.value.status_code == 403

    def test_require_feature_allows_when_licensed(self):
        plugin_registry.set_features(["accounting"])
        dep = require_feature("accounting")
        # No exception => allowed.
        assert dep() is None


# ── Accounting router: require_feature("accounting") ─────────────────

class TestAccountingGate:
    URL = "/api/v1/accounting/trial-balance"

    def test_unlicensed_returns_403(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 403
        assert resp.json()["detail"] == UPGRADE_MESSAGE

    def test_licensed_not_403(self, client):
        plugin_registry.set_features(["accounting"])
        resp = client.get(self.URL)
        assert resp.status_code != 403


# ── Admin analytics router: require_feature("reports_advanced") ──────

class TestAnalyticsGate:
    URL = "/api/v1/admin/analytics/dashboard"

    def test_unlicensed_returns_403(self, client):
        resp = client.get(self.URL)
        assert resp.status_code == 403
        assert resp.json()["detail"] == UPGRADE_MESSAGE

    def test_licensed_not_403(self, client):
        plugin_registry.set_features(["reports_advanced"])
        resp = client.get(self.URL)
        assert resp.status_code != 403


# ── Scheduling auto-schedule: require_feature("production_advanced") ─

class TestSchedulingGate:
    URL = "/api/v1/scheduling/auto-schedule"

    def test_unlicensed_returns_403(self, client):
        # order_id is required (Query) — but the feature gate runs first, so an
        # unlicensed caller is denied regardless of query params.
        resp = client.post(f"{self.URL}?order_id=1")
        assert resp.status_code == 403
        assert resp.json()["detail"] == UPGRADE_MESSAGE

    def test_licensed_not_403(self, client):
        plugin_registry.set_features(["production_advanced"])
        resp = client.post(f"{self.URL}?order_id=1")
        assert resp.status_code != 403
