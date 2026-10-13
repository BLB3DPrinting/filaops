"""Tests for app/services/anthropic_models.py.

Every HTTP call is replaced with a fake; nothing here reaches the network.
"""
import pytest
import requests

from app.services import anthropic_models as am

FAKE_KEY = "sk-ant-test-0123456789abcdef"


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self._text = text

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def _model(model_id, name, lifecycle="active"):
    return {
        "type": "model",
        "id": model_id,
        "display_name": name,
        "created_at": "2026-09-21T00:00:00Z",
        "lifecycle": lifecycle,
        "capabilities": {"batch": {"supported": True}},
    }


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Fail loudly if a test forgets to fake a call."""
    def refuse(*args, **kwargs):
        raise AssertionError("unexpected real HTTP call")

    monkeypatch.setattr(am.requests, "get", refuse)
    monkeypatch.setattr(am.requests, "post", refuse)
    am.clear_model_cache()
    yield
    am.clear_model_cache()


class TestListModels:
    def test_returns_models_and_sends_key_only_in_header(self, monkeypatch):
        calls = []

        def fake_get(url, headers, params, timeout, allow_redirects):
            calls.append((url, headers, params, allow_redirects))
            return FakeResponse(200, {
                "data": [
                    _model("claude-opus-5-5", "Claude Opus 5.5"),
                    _model("claude-sonnet-4-20250514", "Claude Sonnet 4", "deprecated"),
                ],
                "has_more": False,
                "first_id": "claude-opus-5-5",
                "last_id": "claude-sonnet-4-20250514",
            })

        monkeypatch.setattr(am.requests, "get", fake_get)
        models, cached = am.list_models(FAKE_KEY)

        assert cached is False
        assert [m["id"] for m in models] == ["claude-opus-5-5", "claude-sonnet-4-20250514"]
        assert models[1]["lifecycle"] == "deprecated"
        assert set(models[0]) == {"id", "display_name", "lifecycle", "created_at"}
        url, headers, params, allow_redirects = calls[0]
        assert url == "https://api.anthropic.com/v1/models"
        assert headers["x-api-key"] == FAKE_KEY
        assert headers["anthropic-version"] == am.ANTHROPIC_VERSION
        assert FAKE_KEY not in url and FAKE_KEY not in str(params)
        assert allow_redirects is False

    def test_follows_pagination(self, monkeypatch):
        pages = [
            {"data": [_model("a", "A")], "has_more": True, "last_id": "a"},
            {"data": [_model("b", "B")], "has_more": False, "last_id": "b"},
        ]
        seen_params = []

        def fake_get(url, headers, params, timeout, allow_redirects):
            seen_params.append(dict(params))
            return FakeResponse(200, pages[len(seen_params) - 1])

        monkeypatch.setattr(am.requests, "get", fake_get)
        models, _ = am.list_models(FAKE_KEY)
        assert [m["id"] for m in models] == ["a", "b"]
        assert seen_params[1]["after_id"] == "a"

    def test_caches_success_per_key(self, monkeypatch):
        count = {"n": 0}

        def fake_get(*args, **kwargs):
            count["n"] += 1
            return FakeResponse(200, {"data": [_model("a", "A")], "has_more": False})

        monkeypatch.setattr(am.requests, "get", fake_get)
        am.list_models(FAKE_KEY)
        models, cached = am.list_models(FAKE_KEY)
        assert cached is True and models[0]["id"] == "a"
        assert count["n"] == 1

        am.list_models(FAKE_KEY, refresh=True)
        assert count["n"] == 2
        am.list_models(FAKE_KEY + "-other")
        assert count["n"] == 3

    def test_cache_expires(self, monkeypatch):
        count = {"n": 0}
        now = {"t": 1000.0}

        def fake_get(*args, **kwargs):
            count["n"] += 1
            return FakeResponse(200, {"data": [_model("a", "A")], "has_more": False})

        monkeypatch.setattr(am.requests, "get", fake_get)
        monkeypatch.setattr(am.time, "monotonic", lambda: now["t"])
        am.list_models(FAKE_KEY)
        now["t"] += am.CACHE_TTL_SECONDS + 1
        _, cached = am.list_models(FAKE_KEY)
        assert cached is False and count["n"] == 2

    @pytest.mark.parametrize("status_code,expected", [
        (401, "rejected the API key"),
        (403, "not allowed"),
        (429, "rate limit"),
        (529, "trouble"),
    ])
    def test_http_errors_raise_safe_message(self, monkeypatch, status_code, expected):
        monkeypatch.setattr(
            am.requests, "get",
            lambda *a, **k: FakeResponse(status_code, {"error": {"type": "x", "message": "m"}}),
        )
        with pytest.raises(am.AnthropicModelsError) as exc:
            am.list_models(FAKE_KEY)
        assert expected in str(exc.value)
        assert FAKE_KEY not in str(exc.value)

    def test_failures_are_not_cached(self, monkeypatch):
        responses = [FakeResponse(401, {}), FakeResponse(200, {"data": [], "has_more": False})]
        monkeypatch.setattr(am.requests, "get", lambda *a, **k: responses.pop(0))
        with pytest.raises(am.AnthropicModelsError):
            am.list_models(FAKE_KEY)
        models, cached = am.list_models(FAKE_KEY)
        assert models == [] and cached is False

    def test_network_error(self, monkeypatch):
        def boom(*a, **k):
            raise requests.exceptions.ConnectionError("dns failed for " + FAKE_KEY)

        monkeypatch.setattr(am.requests, "get", boom)
        with pytest.raises(am.AnthropicModelsError) as exc:
            am.list_models(FAKE_KEY)
        assert "Could not reach" in str(exc.value)
        assert FAKE_KEY not in str(exc.value)

    def test_timeout(self, monkeypatch):
        def slow(*a, **k):
            raise requests.exceptions.ReadTimeout()

        monkeypatch.setattr(am.requests, "get", slow)
        with pytest.raises(am.AnthropicModelsError, match="Timed out"):
            am.list_models(FAKE_KEY)

    @pytest.mark.parametrize("body", [None, {"data": "nope"}, ["x"]])
    def test_malformed_body(self, monkeypatch, body):
        monkeypatch.setattr(am.requests, "get", lambda *a, **k: FakeResponse(200, body))
        with pytest.raises(am.AnthropicModelsError):
            am.list_models(FAKE_KEY)

    def test_skips_entries_without_id(self, monkeypatch):
        body = {"data": [{"display_name": "no id"}, _model("a", "A"), "junk"], "has_more": False}
        monkeypatch.setattr(am.requests, "get", lambda *a, **k: FakeResponse(200, body))
        models, _ = am.list_models(FAKE_KEY)
        assert [m["id"] for m in models] == ["a"]


class TestFallback:
    def test_fallback_contains_default_and_no_bad_ids(self):
        ids = [m["id"] for m in am.fallback_models()]
        assert am.DEFAULT_ANTHROPIC_MODEL in ids
        assert "claude-haiku-3-5-20241022" not in ids
        assert am.DEFAULT_ANTHROPIC_MODEL != "claude-haiku-3-5-20241022"


class TestCheckModel:
    def test_success_sends_minimal_request(self, monkeypatch):
        sent = {}

        def fake_post(url, headers, json, timeout, allow_redirects):
            sent.update(url=url, headers=headers, json=json)
            return FakeResponse(200, {"type": "message", "stop_reason": "max_tokens"})

        monkeypatch.setattr(am.requests, "post", fake_post)
        ok, message = am.check_model(FAKE_KEY, "claude-sonnet-5-5")
        assert ok is True
        assert "claude-sonnet-5-5" in message
        assert sent["url"] == "https://api.anthropic.com/v1/messages"
        assert sent["json"]["model"] == "claude-sonnet-5-5"
        assert sent["json"]["max_tokens"] == 1
        assert FAKE_KEY not in message

    def test_retired_or_unknown_model(self, monkeypatch):
        monkeypatch.setattr(am.requests, "post", lambda *a, **k: FakeResponse(404, {
            "type": "error",
            "error": {"type": "not_found_error", "message": "model: claude-haiku-3-5-20241022"},
        }))
        ok, message = am.check_model(FAKE_KEY, "claude-haiku-3-5-20241022")
        assert ok is False
        assert "not found" in message and "retired" in message

    def test_bad_key(self, monkeypatch):
        monkeypatch.setattr(am.requests, "post", lambda *a, **k: FakeResponse(401, {
            "error": {"type": "authentication_error", "message": "invalid x-api-key"},
        }))
        ok, message = am.check_model(FAKE_KEY, "claude-sonnet-5-5")
        assert ok is False and "rejected the API key" in message

    def test_model_rejected_with_400(self, monkeypatch):
        monkeypatch.setattr(am.requests, "post", lambda *a, **k: FakeResponse(400, {
            "error": {"type": "invalid_request_error", "message": "model: bad id format"},
        }))
        ok, message = am.check_model(FAKE_KEY, "bad")
        assert ok is False and "did not accept model" in message

    def test_network_error(self, monkeypatch):
        def boom(*a, **k):
            raise requests.exceptions.ConnectionError()

        monkeypatch.setattr(am.requests, "post", boom)
        ok, message = am.check_model(FAKE_KEY, "claude-sonnet-5-5")
        assert ok is False and "Could not reach" in message
