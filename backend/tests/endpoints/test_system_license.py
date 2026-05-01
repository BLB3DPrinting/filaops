"""
Tests for license_cache + system_license endpoints (PR-02).

Covers:
- ``app.core.license_cache`` module surface (UUID gen, save/load, malformed
  JSON, PR-03 forward-compat, atomic write, clear)
- ``GET /api/v1/system/license/info`` (community default, active state,
  auth/permission)
- ``POST /api/v1/system/license/activate`` happy path + every error class
  (timeout, network, 401, 5xx, non-JSON, ``valid=false``, missing API key,
  empty body)
- ``DELETE /api/v1/system/license/`` happy path + auth/permission
- License key masking in responses
- ``install_uuid`` preserved across activate/deactivate cycles

The license server is mocked entirely via a swap-in for ``httpx.AsyncClient``.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any, Optional

import httpx
import pytest

from app.core.license_cache import (
    LICENSE_CACHE_FILENAME,
    INSTALL_UUID_FILENAME,
    LicenseCache,
    clear_license_cache,
    get_install_uuid,
    load_license_cache,
    save_license_cache,
    utc_now_iso,
)


# =============================================================================
# Constants
# =============================================================================

ACTIVATE_URL = "/api/v1/system/license/activate"
INFO_URL = "/api/v1/system/license/info"
DEACTIVATE_URL = "/api/v1/system/license/"

VALID_KEY = "FILAOPS-PRO-bef4723f987560ea"
MASK_RE = re.compile(r"^.{1,12}\*\*\*.{0,4}$")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _disable_rate_limits():
    from app.core.limiter import limiter

    original = getattr(limiter, "_enabled", True)
    limiter.enabled = False
    yield
    limiter.enabled = original


@pytest.fixture(autouse=True)
def _license_env(monkeypatch, tmp_path):
    """Each test gets:
    - A fresh tmpdir for license.json + install_uuid (LICENSE_CONFIG_DIR env)
    - settings.LICENSE_API_KEY set to a known test value
    - settings.LICENSE_SERVER_URL pointed at a fake host
    """
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    from app.core.config import settings

    monkeypatch.setattr(settings, "LICENSE_API_KEY", "test-api-key", raising=False)
    monkeypatch.setattr(
        settings, "LICENSE_SERVER_URL", "http://license-test.local", raising=False
    )
    yield tmp_path


@pytest.fixture
def non_admin_user(db):
    from app.core.security import hash_password
    from app.models.user import User

    uid = uuid.uuid4().hex[:8]
    user = User(
        email=f"nonadmin-{uid}@filaops.dev",
        password_hash=hash_password("TestPass123!"),
        first_name="NonAdmin",
        last_name="User",
        account_type="customer",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def non_admin_client(db, non_admin_user):
    from fastapi.testclient import TestClient

    from app.core.security import create_access_token
    from app.db.session import get_db
    from app.main import app

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    token = create_access_token(user_id=non_admin_user.id)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    app.dependency_overrides.clear()


# =============================================================================
# httpx mocking
# =============================================================================


class _MockResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(
        self,
        status_code: int,
        json_data: Optional[dict] = None,
        text: Optional[str] = None,
    ):
        self.status_code = status_code
        self._json = json_data
        if text is not None:
            self.text = text
        elif json_data is not None:
            self.text = json.dumps(json_data)
        else:
            self.text = ""

    def json(self) -> Any:
        if self._json is None:
            # Match real httpx behavior: invalid body raises ValueError.
            raise ValueError("Expecting value")
        return self._json


@pytest.fixture
def mock_license_server(monkeypatch):
    """Swap ``httpx.AsyncClient`` for a controllable test double.

    Returns a setter ``configure(response_or_exception)`` so each test can
    declare what the next outbound call sees.
    """
    state: dict = {"response": None, "exception": None, "calls": []}

    class _MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, json=None, headers=None):
            state["calls"].append({"url": url, "json": json, "headers": headers})
            if state["exception"] is not None:
                raise state["exception"]
            return state["response"]

    import app.api.v1.endpoints.system_license as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", _MockAsyncClient)

    def configure(response_or_exception):
        if isinstance(response_or_exception, Exception):
            state["exception"] = response_or_exception
            state["response"] = None
        else:
            state["response"] = response_or_exception
            state["exception"] = None

    configure.calls = state["calls"]  # type: ignore[attr-defined]
    return configure


def _ok_validate_response(
    *,
    tier: str = "professional",
    features: Optional[list[str]] = None,
    expires_at: Optional[str] = "2027-01-01T00:00:00+00:00",
    message: Optional[str] = None,
) -> _MockResponse:
    return _MockResponse(
        200,
        json_data={
            "valid": True,
            "tier": tier,
            "status": "active",
            "license_type": "subscription",
            "limits": {"max_users": -1, "max_printers": -1, "max_sites": 1},
            "features": features or ["catalogs", "shopify"],
            "current_period_end": expires_at,
            "grace_period_end": None,
            "message": message,
        },
    )


# =============================================================================
# license_cache module unit tests
# =============================================================================


def test_install_uuid_is_generated_on_first_call(tmp_path, monkeypatch):
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    u = get_install_uuid()
    assert u
    assert (tmp_path / INSTALL_UUID_FILENAME).read_text().strip() == u


def test_install_uuid_is_stable_across_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    u1 = get_install_uuid()
    u2 = get_install_uuid()
    assert u1 == u2


def test_install_uuid_regenerates_when_file_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    (tmp_path / INSTALL_UUID_FILENAME).write_text("")
    u = get_install_uuid()
    assert u
    assert (tmp_path / INSTALL_UUID_FILENAME).read_text().strip() == u


def test_load_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    assert load_license_cache() is None


def test_save_then_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    cache = LicenseCache(
        license_key="FILAOPS-PRO-test",
        install_uuid="uuid-x",
        tier="professional",
        features=["catalogs", "shopify"],
        activated_at=utc_now_iso(),
        expires_at="2027-01-01T00:00:00+00:00",
    )
    save_license_cache(cache)
    loaded = load_license_cache()
    assert loaded is not None
    assert loaded.license_key == "FILAOPS-PRO-test"
    assert loaded.tier == "professional"
    assert loaded.features == ["catalogs", "shopify"]
    assert loaded.expires_at == "2027-01-01T00:00:00+00:00"


def test_load_tolerates_pr03_extra_fields(tmp_path, monkeypatch):
    """Forward-compat: PR-03 will add fields like status, last_verified_at,
    nonce_history. The PR-02 reader must ignore them, not crash."""
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    extended = {
        "license_key": "FILAOPS-PRO-test",
        "install_uuid": "uuid-x",
        "tier": "professional",
        "features": ["catalogs"],
        "activated_at": "2026-05-01T00:00:00+00:00",
        "expires_at": "2027-01-01T00:00:00+00:00",
        # Fields PR-03 will add:
        "status": "active",
        "last_verified_at": "2026-05-01T00:00:00+00:00",
        "nonce_history": ["abc", "def"],
    }
    (tmp_path / LICENSE_CACHE_FILENAME).write_text(json.dumps(extended))
    loaded = load_license_cache()
    assert loaded is not None
    assert loaded.license_key == "FILAOPS-PRO-test"


def test_load_returns_none_on_malformed_json(tmp_path, monkeypatch):
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    (tmp_path / LICENSE_CACHE_FILENAME).write_text("this is not json {")
    assert load_license_cache() is None


def test_clear_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("LICENSE_CONFIG_DIR", str(tmp_path))
    cache = LicenseCache(
        license_key="k",
        install_uuid="u",
        tier="community",
        features=[],
        activated_at=utc_now_iso(),
    )
    save_license_cache(cache)
    assert clear_license_cache() is True
    assert clear_license_cache() is False


# =============================================================================
# GET /info
# =============================================================================


def test_info_returns_community_when_no_cache(client):
    resp = client.get(INFO_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["activated"] is False
    assert body["tier"] == "community"
    assert body["features"] == []
    assert body["install_uuid"]  # generated on demand
    assert body.get("license_key") is None


def test_info_returns_active_state_when_cache_present(client, _license_env):
    cache = LicenseCache(
        license_key=VALID_KEY,
        install_uuid="uuid-x",
        tier="professional",
        features=["catalogs", "shopify"],
        activated_at="2026-05-01T00:00:00+00:00",
        expires_at="2027-01-01T00:00:00+00:00",
    )
    save_license_cache(cache)
    resp = client.get(INFO_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["activated"] is True
    assert body["tier"] == "professional"
    assert body["features"] == ["catalogs", "shopify"]
    assert body["expires_at"] == "2027-01-01T00:00:00+00:00"
    # Key is masked, never returned in full
    assert body["license_key"] != VALID_KEY
    assert MASK_RE.match(body["license_key"])


def test_info_no_auth_returns_401(unauthed_client):
    resp = unauthed_client.get(INFO_URL)
    assert resp.status_code == 401


def test_info_non_admin_returns_403(non_admin_client):
    resp = non_admin_client.get(INFO_URL)
    assert resp.status_code == 403


# =============================================================================
# POST /activate — happy path
# =============================================================================


def test_activate_happy_path_persists_cache(client, mock_license_server, _license_env):
    mock_license_server(_ok_validate_response())

    resp = client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 200
    body = resp.json()
    assert body["activated"] is True
    assert body["tier"] == "professional"
    assert body["features"] == ["catalogs", "shopify"]
    assert MASK_RE.match(body["license_key"])  # masked

    # Verify the cache file actually has the correct contents
    persisted = load_license_cache()
    assert persisted is not None
    assert persisted.license_key == VALID_KEY  # full key in cache
    assert persisted.tier == "professional"


def test_activate_sends_correct_payload_to_server(
    client, mock_license_server, _license_env
):
    mock_license_server(_ok_validate_response())

    client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    calls = mock_license_server.calls  # type: ignore[attr-defined]
    assert len(calls) == 1
    call = calls[0]
    assert call["url"].endswith("/api/v1/validate")
    assert call["json"]["license_key"] == VALID_KEY
    assert call["json"]["instance_id"]  # install_uuid
    assert call["headers"]["X-API-Key"] == "test-api-key"


def test_activate_strips_whitespace_from_key(
    client, mock_license_server, _license_env
):
    mock_license_server(_ok_validate_response())

    resp = client.post(ACTIVATE_URL, json={"license_key": f"   {VALID_KEY}   "})
    assert resp.status_code == 200
    persisted = load_license_cache()
    assert persisted is not None
    assert persisted.license_key == VALID_KEY  # stripped


def test_activate_install_uuid_preserved_across_cycles(
    client, mock_license_server, _license_env
):
    """install_uuid must be stable across activate / deactivate / activate
    so PRO's encryption key (PR-06) is preserved."""
    mock_license_server(_ok_validate_response())

    info1 = client.get(INFO_URL).json()
    initial_uuid = info1["install_uuid"]

    client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    client.delete(DEACTIVATE_URL)
    client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    info2 = client.get(INFO_URL).json()

    assert info2["install_uuid"] == initial_uuid


# =============================================================================
# POST /activate — input validation
# =============================================================================


def test_activate_rejects_empty_body_with_422(client, mock_license_server):
    mock_license_server(_ok_validate_response())  # not actually called
    resp = client.post(ACTIVATE_URL, json={})
    assert resp.status_code == 422  # FastAPI / Pydantic


def test_activate_rejects_empty_string_with_422(client, mock_license_server):
    mock_license_server(_ok_validate_response())
    resp = client.post(ACTIVATE_URL, json={"license_key": ""})
    assert resp.status_code == 422


def test_activate_rejects_whitespace_only_with_400(client, mock_license_server):
    """Pydantic min_length=1 lets through whitespace; the endpoint strips
    and rejects empty result with 400."""
    mock_license_server(_ok_validate_response())
    resp = client.post(ACTIVATE_URL, json={"license_key": "   "})
    assert resp.status_code == 400


# =============================================================================
# POST /activate — server-side errors
# =============================================================================


def test_activate_returns_400_when_server_says_invalid(
    client, mock_license_server
):
    mock_license_server(
        _MockResponse(
            200,
            json_data={
                "valid": False,
                "tier": "community",
                "status": "invalid",
                "license_type": "none",
                "limits": {"max_users": 1, "max_printers": 4, "max_sites": 1},
                "features": [],
                "current_period_end": None,
                "grace_period_end": None,
                "message": "License key not found.",
            },
        )
    )

    resp = client.post(ACTIVATE_URL, json={"license_key": "FILAOPS-PRO-bogus"})
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()
    assert load_license_cache() is None  # nothing persisted


def test_activate_returns_504_on_timeout(client, mock_license_server):
    mock_license_server(httpx.TimeoutException("simulated timeout"))
    resp = client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 504


def test_activate_returns_502_on_network_error(client, mock_license_server):
    mock_license_server(httpx.ConnectError("connection refused"))
    resp = client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 502
    assert "license server" in resp.json()["detail"].lower()


def test_activate_returns_502_on_server_401(client, mock_license_server):
    mock_license_server(_MockResponse(401, text="invalid api key"))
    resp = client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 502
    assert "credentials" in resp.json()["detail"].lower()


def test_activate_returns_502_on_server_500(client, mock_license_server):
    mock_license_server(_MockResponse(500, text="boom"))
    resp = client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 502


def test_activate_returns_502_on_non_json_body(client, mock_license_server):
    mock_license_server(_MockResponse(200, text="<html>not json</html>"))
    resp = client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 502


# =============================================================================
# POST /activate — server-config errors
# =============================================================================


def test_activate_returns_500_when_api_key_unset(
    client, mock_license_server, monkeypatch
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "LICENSE_API_KEY", None, raising=False)
    resp = client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 500
    assert "license_api_key" in resp.json()["detail"].lower()


def test_activate_no_auth_returns_401(unauthed_client, mock_license_server):
    mock_license_server(_ok_validate_response())
    resp = unauthed_client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 401


def test_activate_non_admin_returns_403(non_admin_client, mock_license_server):
    mock_license_server(_ok_validate_response())
    resp = non_admin_client.post(ACTIVATE_URL, json={"license_key": VALID_KEY})
    assert resp.status_code == 403


# =============================================================================
# DELETE /
# =============================================================================


def test_deactivate_removes_cache_but_preserves_uuid(client, _license_env):
    cache = LicenseCache(
        license_key=VALID_KEY,
        install_uuid="uuid-stable",
        tier="professional",
        features=["catalogs"],
        activated_at=utc_now_iso(),
    )
    save_license_cache(cache)

    info_before = client.get(INFO_URL).json()
    assert info_before["activated"] is True

    resp = client.delete(DEACTIVATE_URL)
    assert resp.status_code == 204

    info_after = client.get(INFO_URL).json()
    assert info_after["activated"] is False
    # install_uuid is preserved across deactivate (it's PRO's encryption secret)
    assert info_after["install_uuid"] == info_before["install_uuid"]


def test_deactivate_when_no_license_returns_204(client):
    """Idempotent — DELETE on an empty state still returns 204."""
    resp = client.delete(DEACTIVATE_URL)
    assert resp.status_code == 204


def test_deactivate_no_auth_returns_401(unauthed_client):
    resp = unauthed_client.delete(DEACTIVATE_URL)
    assert resp.status_code == 401


def test_deactivate_non_admin_returns_403(non_admin_client):
    resp = non_admin_client.delete(DEACTIVATE_URL)
    assert resp.status_code == 403
