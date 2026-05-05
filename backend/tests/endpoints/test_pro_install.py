"""
Tests for PRO installer endpoints (PR-04).

Covers POST /api/v1/admin/system/pro/install + GET .../install/status:
- Trigger validation: no license (400), busy (409), already-installed (409),
  restart-pending (409), missing LICENSE_API_KEY (500)
- Happy path: state transitions to ``restart_required`` after the background
  task runs (FastAPI BackgroundTasks executes inline in TestClient, so the
  pipeline finishes before the next request)
- License-server contract: GET to ``/api/v1/download/wheel`` with
  ``X-API-Key`` header + ``license_key`` query param
- Error pipeline: download network error, download timeout, server 4xx,
  hash mismatch, pip non-zero exit, pip timeout — all leave Core running
  and surface as ``state=error`` (retryable)
- pip invocation contract: subprocess called with ``--no-deps`` and
  ``sys.executable``, never the system pip
- Status endpoint reflects mutated state without polling
- Auth: 401 when unauthenticated, 403 for non-admin

The license server is mocked via an httpx.AsyncClient swap-in (same shape
as test_system_license.py); subprocess.run is mocked with a CompletedProcess
stub so pip never actually executes.
"""
from __future__ import annotations

import hashlib
import subprocess
import uuid
from typing import Optional

import httpx
import pytest

from app.core.config import settings
from app.core.license_cache import LicenseCache, save_license_cache, utc_now_iso

# =============================================================================
# Constants
# =============================================================================

INSTALL_URL = "/api/v1/admin/system/pro/install"
STATUS_URL = "/api/v1/admin/system/pro/install/status"

VALID_KEY = "FILAOPS-PRO-test1234567890ab"
WHEEL_BYTES = b"PK\x03\x04fake-wheel-content-for-testing"
WHEEL_SHA256 = hashlib.sha256(WHEEL_BYTES).hexdigest()
WHEEL_FILENAME = "filaops_pro-1.2.3-py3-none-any.whl"


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
def _reset_install_status():
    """Module-level state outlives a single test — reset before each one."""
    import app.api.v1.endpoints.admin.pro_install as mod

    mod._install_status.update(
        {
            "state": "idle",
            "progress": "",
            "error": None,
            "installed_version": None,
            "started_at": None,
            "completed_at": None,
        }
    )
    yield


@pytest.fixture(autouse=True)
def _license_env(monkeypatch, tmp_path):
    """Each test gets a fresh tmpdir for license.json and known server config."""
    monkeypatch.setattr(settings, "LICENSE_CONFIG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "LICENSE_API_KEY", "test-api-key", raising=False)
    monkeypatch.setattr(
        settings, "LICENSE_SERVER_URL", "http://license-test.local", raising=False
    )
    yield tmp_path


@pytest.fixture
def with_license(_license_env):
    """Persist a valid LicenseCache so the install endpoint accepts the call."""
    cache = LicenseCache(
        license_key=VALID_KEY,
        install_uuid="uuid-test",
        tier="professional",
        features=["catalogs", "shopify"],
        activated_at=utc_now_iso(),
        expires_at="2027-01-01T00:00:00+00:00",
    )
    save_license_cache(cache)
    return cache


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
# httpx + subprocess mocking
# =============================================================================


class _MockResponse:
    """Minimal stand-in for ``httpx.Response`` (only the fields we touch)."""

    def __init__(
        self,
        status_code: int,
        *,
        content: Optional[bytes] = None,
        text: Optional[str] = None,
        headers: Optional[dict] = None,
    ):
        self.status_code = status_code
        self.content = content if content is not None else b""
        self.text = text if text is not None else ""
        self.headers = headers or {}


@pytest.fixture
def mock_license_server(monkeypatch):
    """Swap ``httpx.AsyncClient`` inside pro_install for a controllable double.

    Returns a setter ``configure(response_or_exception)`` so each test can
    declare what the next outbound GET sees, plus ``configure.calls`` for
    contract assertions on URL / headers / params.
    """
    state: dict = {"response": None, "exception": None, "calls": []}

    class _MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, *, headers=None, params=None):
            state["calls"].append({"url": url, "headers": headers, "params": params})
            if state["exception"] is not None:
                raise state["exception"]
            return state["response"]

    import app.api.v1.endpoints.admin.pro_install as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", _MockAsyncClient)

    def configure(response_or_exception):
        if isinstance(response_or_exception, BaseException):
            state["exception"] = response_or_exception
            state["response"] = None
        else:
            state["response"] = response_or_exception
            state["exception"] = None

    configure.calls = state["calls"]  # type: ignore[attr-defined]
    return configure


@pytest.fixture
def mock_pip_success(monkeypatch):
    """Replace subprocess.run inside pro_install with a 0-exit stub."""
    calls: list = []

    def fake_run(args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="ok", stderr=""
        )

    import app.api.v1.endpoints.admin.pro_install as mod

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    fake_run.calls = calls  # type: ignore[attr-defined]
    return fake_run


@pytest.fixture
def mock_pro_not_installed(monkeypatch):
    """Force ``_is_pro_installed()`` to False regardless of the dev environment.

    Most CI runners don't have ``filaops_pro`` installed, but a developer
    machine might — and the prod-server install absolutely will. Pin the
    answer so the test is environment-independent.
    """
    import app.api.v1.endpoints.admin.pro_install as mod

    monkeypatch.setattr(mod, "_is_pro_installed", lambda: False)


def _ok_wheel_response(*, sha256: str = WHEEL_SHA256) -> _MockResponse:
    return _MockResponse(
        200,
        content=WHEEL_BYTES,
        headers={
            "X-Wheel-SHA256": sha256,
            "Content-Disposition": f'attachment; filename="{WHEEL_FILENAME}"',
        },
    )


# =============================================================================
# POST /install — input / state validation
# =============================================================================


def test_install_rejects_when_no_license(client, mock_pro_not_installed):
    resp = client.post(INSTALL_URL)
    assert resp.status_code == 400
    assert "license" in resp.json()["detail"].lower()


def test_install_rejects_when_already_in_progress(
    client, with_license, mock_pro_not_installed
):
    import app.api.v1.endpoints.admin.pro_install as mod

    mod._install_status["state"] = "downloading"
    resp = client.post(INSTALL_URL)
    assert resp.status_code == 409
    assert "in progress" in resp.json()["detail"].lower()


def test_install_rejects_when_verifying(
    client, with_license, mock_pro_not_installed
):
    import app.api.v1.endpoints.admin.pro_install as mod

    mod._install_status["state"] = "verifying"
    resp = client.post(INSTALL_URL)
    assert resp.status_code == 409


def test_install_rejects_when_installing(
    client, with_license, mock_pro_not_installed
):
    import app.api.v1.endpoints.admin.pro_install as mod

    mod._install_status["state"] = "installing"
    resp = client.post(INSTALL_URL)
    assert resp.status_code == 409


def test_install_rejects_when_restart_required(
    client, with_license, mock_pro_not_installed
):
    import app.api.v1.endpoints.admin.pro_install as mod

    mod._install_status["state"] = "restart_required"
    resp = client.post(INSTALL_URL)
    assert resp.status_code == 409
    assert "restart" in resp.json()["detail"].lower()


def test_install_rejects_when_pro_already_installed(
    client, with_license, monkeypatch
):
    import app.api.v1.endpoints.admin.pro_install as mod

    monkeypatch.setattr(mod, "_is_pro_installed", lambda: True)
    resp = client.post(INSTALL_URL)
    assert resp.status_code == 409
    assert "already" in resp.json()["detail"].lower()


def test_install_rejects_when_api_key_unset(
    client, with_license, mock_pro_not_installed, monkeypatch
):
    monkeypatch.setattr(settings, "LICENSE_API_KEY", None, raising=False)
    resp = client.post(INSTALL_URL)
    assert resp.status_code == 500
    assert "license_api_key" in resp.json()["detail"].lower()


# =============================================================================
# POST /install — happy path
# =============================================================================


def test_install_happy_path_transitions_to_restart_required(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    """Full pipeline: trigger -> download -> verify -> install -> done."""
    mock_license_server(_ok_wheel_response())

    resp = client.post(INSTALL_URL)
    assert resp.status_code == 200
    assert resp.json()["state"] == "downloading"

    # FastAPI BackgroundTasks runs inline in TestClient, so the pipeline has
    # already completed by the time we call /status.
    body = client.get(STATUS_URL).json()
    assert body["state"] == "restart_required"
    assert body["error"] is None
    assert body["installed_version"] == "1.2.3"
    assert body["started_at"] is not None
    assert body["completed_at"] is not None
    assert "restart" in body["progress"].lower()


def test_install_calls_license_server_with_correct_credentials(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    """Contract test: ``X-API-Key`` header + ``license_key`` query param."""
    mock_license_server(_ok_wheel_response())
    client.post(INSTALL_URL)

    calls = mock_license_server.calls  # type: ignore[attr-defined]
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "http://license-test.local/api/v1/download/wheel"
    assert call["headers"]["X-API-Key"] == "test-api-key"
    assert call["params"]["license_key"] == VALID_KEY


def test_install_invokes_pip_with_no_deps_and_current_python(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    """pip is invoked via ``sys.executable -m pip install <wheel> --no-deps``."""
    import sys

    mock_license_server(_ok_wheel_response())
    client.post(INSTALL_URL)

    calls = mock_pip_success.calls  # type: ignore[attr-defined]
    assert len(calls) == 1
    args = calls[0]["args"]
    assert args[0] == sys.executable
    assert args[1:4] == ["-m", "pip", "install"]
    assert "--no-deps" in args
    # Wheel path is the last positional before the flag
    wheel_arg = args[4]
    assert wheel_arg.endswith(WHEEL_FILENAME)


# =============================================================================
# Background pipeline error states
# =============================================================================


def test_install_download_network_error_marks_state_error(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    mock_license_server(httpx.ConnectError("connection refused"))
    client.post(INSTALL_URL)

    body = client.get(STATUS_URL).json()
    assert body["state"] == "error"
    assert body["error"]
    # pip must never run when the download fails
    assert len(mock_pip_success.calls) == 0  # type: ignore[attr-defined]


def test_install_download_timeout_marks_state_error(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    mock_license_server(httpx.TimeoutException("simulated timeout"))
    client.post(INSTALL_URL)

    body = client.get(STATUS_URL).json()
    assert body["state"] == "error"
    assert "time" in body["error"].lower()


def test_install_server_4xx_marks_state_error_and_skips_pip(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    """A 403 from the license server should never reach pip."""
    mock_license_server(_MockResponse(403, text="forbidden"))
    client.post(INSTALL_URL)

    body = client.get(STATUS_URL).json()
    assert body["state"] == "error"
    assert "403" in body["error"]
    assert len(mock_pip_success.calls) == 0  # type: ignore[attr-defined]


def test_install_hash_mismatch_marks_state_error_and_skips_pip(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    """A hash mismatch is the hard integrity gate — wheel must NOT be installed."""
    bad_hash = "0" * 64
    mock_license_server(_ok_wheel_response(sha256=bad_hash))
    client.post(INSTALL_URL)

    body = client.get(STATUS_URL).json()
    assert body["state"] == "error"
    assert "hash" in body["error"].lower() or "mismatch" in body["error"].lower()
    assert len(mock_pip_success.calls) == 0  # type: ignore[attr-defined]


def test_install_proceeds_when_server_omits_hash_header(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    """Forward-compat: missing ``X-Wheel-SHA256`` is treated as no-op verify."""
    resp_no_hash = _MockResponse(
        200,
        content=WHEEL_BYTES,
        headers={"Content-Disposition": f'attachment; filename="{WHEEL_FILENAME}"'},
    )
    mock_license_server(resp_no_hash)

    client.post(INSTALL_URL)
    body = client.get(STATUS_URL).json()
    assert body["state"] == "restart_required"


def test_install_pip_failure_marks_state_error(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    monkeypatch,
):
    mock_license_server(_ok_wheel_response())

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args=args, returncode=1, stdout="", stderr="ERROR: dependency conflict"
        )

    import app.api.v1.endpoints.admin.pro_install as mod

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    client.post(INSTALL_URL)
    body = client.get(STATUS_URL).json()
    assert body["state"] == "error"
    assert "pip" in body["error"].lower()


def test_install_pip_timeout_marks_state_error(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    monkeypatch,
):
    mock_license_server(_ok_wheel_response())

    def fake_run(args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args, timeout=120)

    import app.api.v1.endpoints.admin.pro_install as mod

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    client.post(INSTALL_URL)
    body = client.get(STATUS_URL).json()
    assert body["state"] == "error"
    assert "time" in body["error"].lower()


def test_install_retry_after_error_succeeds(
    client,
    with_license,
    mock_pro_not_installed,
    mock_license_server,
    mock_pip_success,
):
    """``error`` is retryable: a second POST proceeds and reaches restart_required."""
    # Attempt 1: network failure
    mock_license_server(httpx.ConnectError("offline"))
    client.post(INSTALL_URL)
    assert client.get(STATUS_URL).json()["state"] == "error"

    # Attempt 2: server is back
    mock_license_server(_ok_wheel_response())
    resp = client.post(INSTALL_URL)
    assert resp.status_code == 200
    assert client.get(STATUS_URL).json()["state"] == "restart_required"


# =============================================================================
# GET /install/status
# =============================================================================


def test_status_returns_idle_initially(client):
    resp = client.get(STATUS_URL)
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "idle"
    assert body["error"] is None
    assert body["installed_version"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None


def test_status_reflects_in_progress_state(client):
    """Status endpoint is a pure read of ``_install_status``."""
    import app.api.v1.endpoints.admin.pro_install as mod

    mod._install_status["state"] = "installing"
    mod._install_status["progress"] = "Installing PRO package..."
    body = client.get(STATUS_URL).json()
    assert body["state"] == "installing"
    assert body["progress"] == "Installing PRO package..."


# =============================================================================
# Auth / permission
# =============================================================================


def test_install_no_auth_returns_401(unauthed_client):
    resp = unauthed_client.post(INSTALL_URL)
    assert resp.status_code == 401


def test_install_non_admin_returns_403(non_admin_client):
    resp = non_admin_client.post(INSTALL_URL)
    assert resp.status_code == 403


def test_status_no_auth_returns_401(unauthed_client):
    resp = unauthed_client.get(STATUS_URL)
    assert resp.status_code == 401


def test_status_non_admin_returns_403(non_admin_client):
    resp = non_admin_client.get(STATUS_URL)
    assert resp.status_code == 403
