"""Tests for the Anthropic model list and model check in the AI settings.

Covers:
- GET /api/v1/settings/ai/anthropic-models (admin only; live list, cache,
  fallback on no key / blocked / 401 / network error; never returns the key)
- POST /api/v1/settings/ai/test with a model (one-token request, retired IDs)
- Defaults: backend default is a current model, never the invalid Haiku ID
- Compat: saved values that Anthropic no longer lists still load and save

Anthropic's HTTP API is faked everywhere; nothing here reaches the network.
"""
import sys
import types

import pytest
import requests

from app.services import anthropic_models as am

BASE_URL = "/api/v1/settings"
FAKE_KEY = "sk-ant-test-models-0123456789abcdef"
INVALID_HAIKU_ID = "claude-haiku-3-5-20241022"


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


LIVE_MODELS = {
    "data": [
        {"type": "model", "id": "claude-opus-5-5", "display_name": "Claude Opus 5.5",
         "lifecycle": "active", "created_at": "2026-09-21T00:00:00Z"},
        {"type": "model", "id": "claude-sonnet-5-5", "display_name": "Claude Sonnet 5.5",
         "lifecycle": "active", "created_at": "2026-09-28T00:00:00Z"},
        {"type": "model", "id": "claude-opus-4-5-20251101", "display_name": "Claude Opus 4.5",
         "lifecycle": "active", "created_at": "2025-11-01T00:00:00Z"},
    ],
    "has_more": False,
}


@pytest.fixture(autouse=True)
def fake_anthropic(monkeypatch):
    """Fake Anthropic: no real HTTP, and the optional SDK 'installed'."""
    state = {"get": [], "post": [], "get_response": FakeResponse(200, LIVE_MODELS),
             "post_response": FakeResponse(200, {"type": "message"})}

    def fake_get(url, headers, params, timeout, allow_redirects):
        state["get"].append({"url": url, "headers": headers, "params": params})
        resp = state["get_response"]
        if isinstance(resp, Exception):
            raise resp
        return resp

    def fake_post(url, headers, json, timeout, allow_redirects):
        state["post"].append({"url": url, "headers": headers, "json": json})
        resp = state["post_response"]
        if isinstance(resp, Exception):
            raise resp
        return resp

    monkeypatch.setattr(am.requests, "get", fake_get)
    monkeypatch.setattr(am.requests, "post", fake_post)
    # CI installs requirements.txt only; the SDK is optional (PRO invoice
    # parsing). The connection test checks it is importable.
    monkeypatch.setitem(sys.modules, "anthropic", types.ModuleType("anthropic"))
    am.clear_model_cache()
    yield state
    am.clear_model_cache()


def _configure_anthropic(client, key=FAKE_KEY, model=None):
    payload = {"ai_provider": "anthropic", "external_ai_blocked": False}
    if key:
        payload["ai_api_key"] = key
    if model is not None:
        payload["ai_anthropic_model"] = model
    response = client.patch(f"{BASE_URL}/ai", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _save_raw_model(db, value):
    """Write a value straight to the row, the way an old install has it."""
    from app.api.v1.endpoints.settings import get_or_create_settings

    settings = get_or_create_settings(db)
    settings.ai_anthropic_model = value
    db.commit()


# =============================================================================
# Access
# =============================================================================

class TestAccess:
    def test_requires_auth(self, unauthed_client):
        assert unauthed_client.get(f"{BASE_URL}/ai/anthropic-models").status_code == 401

    @pytest.mark.parametrize("account_type", ["operator", "customer"])
    def test_non_admin_is_refused(self, unauthed_client, role_headers, account_type, fake_anthropic):
        response = unauthed_client.get(
            f"{BASE_URL}/ai/anthropic-models", headers=role_headers(account_type)
        )
        assert response.status_code == 403
        assert fake_anthropic["get"] == []


# =============================================================================
# GET /ai/anthropic-models
# =============================================================================

class TestListModels:
    def test_live_list_for_saved_key(self, client, fake_anthropic):
        _configure_anthropic(client)
        response = client.get(f"{BASE_URL}/ai/anthropic-models")
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "anthropic"
        assert data["error"] is None
        assert data["recommended"] == am.DEFAULT_ANTHROPIC_MODEL
        assert data["pricing_url"].startswith("https://")
        assert [m["id"] for m in data["models"]] == [
            "claude-opus-5-5", "claude-sonnet-5-5", "claude-opus-4-5-20251101",
        ]
        # The decrypted key went to Anthropic in the header, and nowhere else.
        assert fake_anthropic["get"][0]["headers"]["x-api-key"] == FAKE_KEY
        assert FAKE_KEY not in response.text

    def test_cached_briefly_and_refresh_bypasses(self, client, fake_anthropic):
        _configure_anthropic(client)
        first = client.get(f"{BASE_URL}/ai/anthropic-models").json()
        second = client.get(f"{BASE_URL}/ai/anthropic-models").json()
        assert first["cached"] is False and second["cached"] is True
        assert len(fake_anthropic["get"]) == 1

        third = client.get(f"{BASE_URL}/ai/anthropic-models?refresh=true").json()
        assert third["cached"] is False
        assert len(fake_anthropic["get"]) == 2

    def test_no_key_returns_fallback(self, client, db, fake_anthropic):
        client.patch(f"{BASE_URL}/ai", json={"external_ai_blocked": False, "ai_provider": "anthropic"})
        from app.api.v1.endpoints.settings import get_or_create_settings
        settings = get_or_create_settings(db)
        settings.ai_api_key = None
        db.commit()

        data = client.get(f"{BASE_URL}/ai/anthropic-models").json()
        assert data["source"] == "fallback"
        assert "API key" in data["error"]
        ids = [m["id"] for m in data["models"]]
        assert am.DEFAULT_ANTHROPIC_MODEL in ids
        assert INVALID_HAIKU_ID not in ids
        assert fake_anthropic["get"] == []

    def test_blocked_external_ai_never_contacts_anthropic(self, client, fake_anthropic):
        client.patch(f"{BASE_URL}/ai", json={"ai_provider": "ollama"})
        client.patch(f"{BASE_URL}/ai", json={"external_ai_blocked": True})
        data = client.get(f"{BASE_URL}/ai/anthropic-models").json()
        assert data["source"] == "fallback"
        assert "blocked" in data["error"]
        assert fake_anthropic["get"] == []
        client.patch(f"{BASE_URL}/ai", json={"external_ai_blocked": False})

    def test_bad_key_returns_fallback_with_clear_error(self, client, fake_anthropic):
        _configure_anthropic(client)
        fake_anthropic["get_response"] = FakeResponse(401, {
            "type": "error",
            "error": {"type": "authentication_error", "message": "invalid x-api-key"},
        })
        response = client.get(f"{BASE_URL}/ai/anthropic-models")
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "fallback"
        assert "rejected the API key" in data["error"]
        assert FAKE_KEY not in response.text

    def test_network_failure_returns_fallback(self, client, fake_anthropic):
        _configure_anthropic(client)
        fake_anthropic["get_response"] = requests.exceptions.ConnectionError("no route")
        data = client.get(f"{BASE_URL}/ai/anthropic-models").json()
        assert data["source"] == "fallback"
        assert "Could not reach" in data["error"]

    def test_failure_is_not_cached(self, client, fake_anthropic):
        _configure_anthropic(client)
        fake_anthropic["get_response"] = requests.exceptions.ConnectionError()
        assert client.get(f"{BASE_URL}/ai/anthropic-models").json()["source"] == "fallback"
        fake_anthropic["get_response"] = FakeResponse(200, LIVE_MODELS)
        assert client.get(f"{BASE_URL}/ai/anthropic-models").json()["source"] == "anthropic"


# =============================================================================
# POST /ai/test with a model
# =============================================================================

class TestConnectionTestUsesModel:
    def test_tests_the_selected_unsaved_model(self, client, fake_anthropic):
        _configure_anthropic(client, model="claude-opus-4-5-20251101")
        response = client.post(
            f"{BASE_URL}/ai/test", json={"ai_anthropic_model": "claude-sonnet-5-5"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        sent = fake_anthropic["post"][0]
        assert sent["url"] == "https://api.anthropic.com/v1/messages"
        assert sent["json"]["model"] == "claude-sonnet-5-5"
        assert sent["json"]["max_tokens"] == 1
        assert FAKE_KEY not in response.text

    def test_without_body_tests_saved_model(self, client, fake_anthropic):
        # The owner's production value must keep working.
        _configure_anthropic(client, model="claude-opus-4-5-20251101")
        data = client.post(f"{BASE_URL}/ai/test").json()
        assert data["success"] is True
        assert fake_anthropic["post"][0]["json"]["model"] == "claude-opus-4-5-20251101"

    def test_retired_model_is_reported(self, client, fake_anthropic):
        _configure_anthropic(client, model=INVALID_HAIKU_ID)
        fake_anthropic["post_response"] = FakeResponse(404, {
            "type": "error",
            "error": {"type": "not_found_error", "message": f"model: {INVALID_HAIKU_ID}"},
        })
        data = client.post(f"{BASE_URL}/ai/test").json()
        assert data["success"] is False
        assert INVALID_HAIKU_ID in data["message"]
        assert "not found" in data["message"]

    def test_bad_key_is_reported(self, client, fake_anthropic):
        _configure_anthropic(client)
        fake_anthropic["post_response"] = FakeResponse(401, {
            "error": {"type": "authentication_error", "message": "invalid x-api-key"},
        })
        data = client.post(f"{BASE_URL}/ai/test").json()
        assert data["success"] is False
        assert "rejected the API key" in data["message"]

    def test_package_missing_is_reported_without_network(self, client, fake_anthropic, monkeypatch):
        _configure_anthropic(client)
        monkeypatch.setitem(sys.modules, "anthropic", None)  # import raises ImportError
        data = client.post(f"{BASE_URL}/ai/test").json()
        assert data["success"] is False
        assert "not installed" in data["message"]
        assert fake_anthropic["post"] == []

    def test_rejects_malformed_model_id(self, client):
        response = client.post(
            f"{BASE_URL}/ai/test", json={"ai_anthropic_model": "bad model\nid"}
        )
        assert response.status_code == 422


# =============================================================================
# Defaults and saved-value compatibility
# =============================================================================

class TestDefaultsAndCompat:
    def test_default_is_current_and_not_the_invalid_haiku_id(self):
        from app.models.company_settings import CompanySettings

        column_default = CompanySettings.__table__.c.ai_anthropic_model.default.arg
        assert column_default == am.DEFAULT_ANTHROPIC_MODEL
        assert am.DEFAULT_ANTHROPIC_MODEL != INVALID_HAIKU_ID
        assert am.DEFAULT_ANTHROPIC_MODEL in [m["id"] for m in am.FALLBACK_MODELS]

    def test_unset_model_reads_as_backend_default(self, client, db):
        _save_raw_model(db, None)
        data = client.get(f"{BASE_URL}/ai").json()
        assert data["ai_anthropic_model"] == am.DEFAULT_ANTHROPIC_MODEL

    def test_clearing_model_falls_back_to_default(self, client):
        _configure_anthropic(client, model="")
        data = client.get(f"{BASE_URL}/ai").json()
        assert data["ai_anthropic_model"] == am.DEFAULT_ANTHROPIC_MODEL

    @pytest.mark.parametrize("saved", [
        INVALID_HAIKU_ID,
        "claude-opus-4-5-20251101",
        "claude-sonnet-4-20250514",
    ])
    def test_saved_values_load_unchanged(self, client, db, saved):
        # Old installs keep their value; the page shows it with a warning
        # instead of the API rewriting it or failing.
        _save_raw_model(db, saved)
        response = client.get(f"{BASE_URL}/ai")
        assert response.status_code == 200
        assert response.json()["ai_anthropic_model"] == saved

    def test_other_settings_save_with_an_unlisted_saved_model(self, client, db):
        _configure_anthropic(client)
        _save_raw_model(db, INVALID_HAIKU_ID)
        response = client.patch(f"{BASE_URL}/ai", json={"ai_ollama_model": "llama3.2"})
        assert response.status_code == 200
        assert response.json()["ai_anthropic_model"] == INVALID_HAIKU_ID

    def test_patch_rejects_malformed_model_id(self, client):
        response = client.patch(
            f"{BASE_URL}/ai", json={"ai_anthropic_model": "claude sonnet; drop"}
        )
        assert response.status_code == 422
