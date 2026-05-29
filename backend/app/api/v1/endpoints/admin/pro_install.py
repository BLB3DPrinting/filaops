"""
PRO Installer API Endpoints (PR-04)

Orchestrates the post-activation download + pip install of the FilaOps PRO
wheel from the license server. After PR-02 the customer has a license.json
on disk; this module is what turns that into an actually-installed PRO
package, surfacing progress through a polled status endpoint so the admin UI
can show download/install progress without the customer ever touching a
terminal.

Sacred Rule: this module MUST NOT ``import filaops_pro``. Detection of an
already-installed PRO uses ``importlib.util.find_spec``, which only walks
the import system without executing module code, so Core's module graph
stays free of PRO references whether or not the wheel is present.

Patterns reused:
  - Background task + module-level status dict:
      app/api/v1/endpoints/admin/system.py:_update_status
  - subprocess pip install against sys.executable:
      app/api/v1/endpoints/settings.py:install_anthropic_package
  - httpx + admin-auth conventions:
      app/api/v1/endpoints/system_license.py

License-server endpoint contract:
  GET /api/v1/download/wheel
  Headers:
    X-API-Key: <server-to-server credential>
    X-License-Key: <customer license key>
  Response: wheel binary (application/octet-stream)
  Response headers: X-Wheel-SHA256 (hex digest)

State machine:
  idle -> downloading -> verifying -> installing -> restart_required
                                                 -> error (from any phase)
An ``error`` state is retryable. ``restart_required`` is not retryable from
this endpoint — Core has to be restarted so main.py:load_plugin can pick
up the freshly-installed wheel.
"""
from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.api.v1.deps import get_current_admin_user
from app.core.config import settings
from app.core.license_cache import load_license_cache
from app.logging_config import get_logger
from app.models.user import User

logger = get_logger(__name__)

router = APIRouter(prefix="/system/pro", tags=["Admin - PRO Installer"])

# Network read-budget for the wheel download. Wheels are 1-5MB today, but
# customer connections vary widely; 60s absorbs the long tail without leaving
# the UI hanging when the server is genuinely down.
_DOWNLOAD_TIMEOUT_SECONDS = 60.0
# pip install runtime budget. Mirrors settings.install_anthropic_package,
# which also installs a small no-deps wheel.
_PIP_INSTALL_TIMEOUT_SECONDS = 120

# ---- State machine ---------------------------------------------------------
#
# A module-level dict instead of Redis/DB because install state is inherently
# ephemeral: the only post-install action is restarting Core, which clears it
# anyway. A persisted state would just become a stale row to clean up.
_install_status: dict = {
    "state": "idle",            # idle | downloading | verifying | installing | restart_required | error
    "progress": "",             # human-readable progress string for the UI
    "error": None,              # error message when state == error, else None
    "installed_version": None,  # version string parsed from wheel filename
    "started_at": None,         # ISO 8601 UTC timestamp
    "completed_at": None,       # ISO 8601 UTC timestamp
}

# States during which a fresh install attempt must be rejected.
_BUSY_STATES = {"downloading", "verifying", "installing"}


class InstallError(Exception):
    """Internal exception used to short-circuit the install pipeline.

    Caught by the background-task wrapper, which converts it into the error
    state. Never raised across the FastAPI surface — callers see install
    failures only via the polling endpoint.
    """


# ---- Helpers ---------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_pro_installed() -> bool:
    """Whether ``filaops_pro`` is importable from the current environment.

    Uses ``importlib.util.find_spec`` so Core never pulls PRO into its own
    module graph — see Sacred Rule note in the module docstring.
    """
    return importlib.util.find_spec("filaops_pro") is not None


def _compute_sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of a file, streamed in 64KB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _extract_version_from_filename(wheel_path: Path) -> Optional[str]:
    """Best-effort version extraction from a PEP 427 wheel filename.

    Layout: ``<dist>-<version>(-<build>)?-<python>-<abi>-<platform>.whl``
    Example: ``filaops_pro-1.2.3-py3-none-any.whl`` -> ``"1.2.3"``
    Returns None if the filename doesn't match — the install still succeeds.
    """
    match = re.match(r"^[A-Za-z0-9_]+-([^-]+)-", wheel_path.stem)
    return match.group(1) if match else None


async def _download_wheel(
    *,
    license_server_url: str,
    license_key: str,
    api_key: str,
    dest_dir: Path,
) -> tuple[Path, Optional[str]]:
    """Fetch the PRO wheel from the license server.

    Returns ``(wheel_path, expected_sha256)``. ``expected_sha256`` may be
    None if the server omits the ``X-Wheel-SHA256`` header — the install
    still proceeds, but the integrity check becomes a no-op (forward-compat
    with older license-server builds).

    Raises InstallError on any network failure or non-200 response.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = f"{license_server_url}/api/v1/download/wheel"
    headers = {
        "X-API-Key": api_key,
        "X-License-Key": license_key,
    }

    async with httpx.AsyncClient(timeout=_DOWNLOAD_TIMEOUT_SECONDS) as client:
        try:
            resp = await client.get(url, headers=headers)
        except httpx.TimeoutException as exc:
            raise InstallError("License server did not respond in time.") from exc
        except httpx.RequestError as exc:
            raise InstallError(f"Could not reach the license server: {exc}") from exc

    if resp.status_code != 200:
        # Cap the error body so a runaway HTML response doesn't pollute the
        # status field that the UI displays verbatim.
        body = (resp.text or "")[:200]
        raise InstallError(
            f"License server returned {resp.status_code}: {body}".rstrip(": ")
        )

    expected_sha256 = resp.headers.get("X-Wheel-SHA256")
    # Honor the server-supplied filename when present so version detection
    # works on the install side; fall back to a deterministic name otherwise.
    filename = "filaops_pro.whl"
    cd = resp.headers.get("Content-Disposition", "")
    cd_match = re.search(r'filename="?([^"]+)"?', cd)
    if cd_match:
        # Strip path components — defense-in-depth against a server (compromised
        # or buggy) returning "../../something.whl" and escaping dest_dir. The
        # license-server endpoint is server-to-server-authenticated, but the
        # cost of `Path.name` is one call so there's no reason to trust it.
        filename = Path(cd_match.group(1)).name
    if not filename.endswith(".whl"):
        raise InstallError(
            f"License server returned a non-wheel filename: {filename!r}"
        )

    wheel_path = dest_dir / filename
    wheel_path.write_bytes(resp.content)
    return wheel_path, expected_sha256


async def _do_pro_install() -> None:
    """Background install pipeline: download -> verify -> pip install -> done.

    Mutates ``_install_status`` so the polling endpoint can surface progress.
    Every exception is converted into the error state — Core must keep
    running even when PRO install fails (Layer-0 non-regression constraint).
    """
    try:
        # Phase 1: Download.
        # State + started_at + cleared error fields are set synchronously by
        # the trigger endpoint (start_pro_install) so a /status poll that
        # races the bg task firing sees "downloading", not "idle". Don't
        # overwrite started_at here — that would re-stamp the install with
        # the bg task's wake time instead of the user's click.
        cache = load_license_cache()
        if cache is None:
            # Defensive: the trigger endpoint already checks this, but the
            # cache could be cleared between trigger and the bg task firing.
            raise InstallError("No license activated. Activate first.")

        api_key = settings.LICENSE_API_KEY
        if not api_key:
            raise InstallError(
                "Server is not configured for PRO install: LICENSE_API_KEY is not set."
            )

        dest_dir = Path(tempfile.gettempdir()) / "filaops-pro-install"
        wheel_path, expected_hash = await _download_wheel(
            license_server_url=settings.LICENSE_SERVER_URL,
            license_key=cache.license_key,
            api_key=api_key,
            dest_dir=dest_dir,
        )

        # Phase 2: Verify
        _install_status["state"] = "verifying"
        _install_status["progress"] = "Verifying package integrity..."
        if not expected_hash:
            # Fail closed. The PR-04 license-server endpoint always sets
            # X-Wheel-SHA256; missing it means a server regression or a
            # stripping proxy upstream — both are conditions where silent
            # install would defeat the integrity gate.
            raise InstallError(
                "License server did not provide X-Wheel-SHA256 header. "
                "Refusing to install an unverified wheel."
            )
        actual_hash = _compute_sha256(wheel_path)
        if actual_hash.lower() != expected_hash.lower():
            # Refuse to install a wheel whose hash doesn't match the
            # server's declared digest. The wheel is left on disk for
            # post-mortem inspection but never reaches pip.
            raise InstallError(
                f"Wheel hash mismatch: expected {expected_hash[:16]}..., "
                f"got {actual_hash[:16]}..."
            )

        # Phase 3: Install
        _install_status["state"] = "installing"
        _install_status["progress"] = "Installing PRO package..."
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", str(wheel_path), "--no-deps"],
            capture_output=True,
            text=True,
            timeout=_PIP_INSTALL_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise InstallError(f"pip install failed: {result.stderr[:500]}")

        # Phase 4: Done
        _install_status["state"] = "restart_required"
        _install_status["progress"] = (
            "PRO installed successfully. Restart Core to activate."
        )
        _install_status["installed_version"] = _extract_version_from_filename(wheel_path)
        _install_status["completed_at"] = _now_iso()
        logger.info(
            "PRO installed successfully (version=%s, wheel=%s)",
            _install_status["installed_version"],
            wheel_path.name,
        )

    except InstallError as exc:
        _install_status["state"] = "error"
        _install_status["error"] = str(exc)
        _install_status["progress"] = f"Installation failed: {exc}"
        _install_status["completed_at"] = _now_iso()
        logger.warning("PRO install failed: %s", exc)
    except subprocess.TimeoutExpired:
        _install_status["state"] = "error"
        _install_status["error"] = "pip install timed out."
        _install_status["progress"] = "Installation failed: pip install timed out."
        _install_status["completed_at"] = _now_iso()
        logger.warning("PRO install pip step timed out")
    except Exception as exc:  # pragma: no cover - defensive catch-all
        _install_status["state"] = "error"
        _install_status["error"] = str(exc)
        _install_status["progress"] = f"Installation failed: {exc}"
        _install_status["completed_at"] = _now_iso()
        logger.exception("Unexpected error during PRO install")


# ---- Endpoints -------------------------------------------------------------


@router.post("/install")
async def start_pro_install(
    background_tasks: BackgroundTasks,
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Trigger a PRO wheel download + install in the background.

    Returns immediately after scheduling the background task. The frontend
    polls ``GET /system/pro/install/status`` for state updates.

    Rejects with:
      400 — no license activated (no license.json on disk)
      409 — install already in progress, or PRO already installed
      500 — server is missing LICENSE_API_KEY (operator config issue)
    """
    cache = load_license_cache()
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No license activated. Activate a license before installing PRO.",
        )

    if _install_status["state"] in _BUSY_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"PRO install already in progress (state={_install_status['state']})."
            ),
        )

    if _install_status["state"] == "restart_required":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PRO is installed. Restart Core to activate it.",
        )

    if _is_pro_installed():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PRO is already installed in this environment.",
        )

    if not settings.LICENSE_API_KEY:
        # Operator config error — surface clearly rather than letting the
        # background task fail with a vaguer message later.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Server is not configured for PRO install: LICENSE_API_KEY is not set."
            ),
        )

    # Mark in-flight SYNCHRONOUSLY before scheduling the bg task. Two reasons:
    #   1. A /status poll between this return and the bg task firing must
    #      see "downloading", not "idle" — otherwise useProInstaller stops
    #      polling on a real install (its IN_PROGRESS_STATES check excludes
    #      idle).
    #   2. Closes the concurrent-POST race: a second request that arrives
    #      before the bg task starts hits the busy-state check and gets 409
    #      instead of scheduling a duplicate install.
    _install_status.update(
        {
            "state": "downloading",
            "progress": "Downloading PRO package from license server...",
            "error": None,
            "installed_version": None,
            "started_at": _now_iso(),
            "completed_at": None,
        }
    )

    background_tasks.add_task(_do_pro_install)
    logger.info("PRO install triggered by %s", current_user.email)
    return {
        "message": "PRO install started.",
        "state": "downloading",
    }


@router.get("/install/status")
async def get_pro_install_status(
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> dict:
    """Return the current PRO install state for frontend polling."""
    return dict(_install_status)
