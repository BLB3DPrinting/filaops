"""
Tests for install-method awareness in app.core.version.VersionManager.

Background:
    Core ships in multiple deployment shapes (Docker compose today, Tauri
    desktop install in progress, future Linux .deb). The product version
    string is identical across them — `4.0.0` means the same code regardless
    of how it's installed. What differs is how customers upgrade. Telling a
    Tauri desktop user to run `docker-compose down` would be the worst kind
    of bad UX: a literal "command not found" or, worse, the user hunting for
    a Docker daemon they never installed.

    Each deployment artifact opts in via `FILAOPS_INSTALL_METHOD`. These
    tests pin both halves of the contract: the env-var → install-method
    parser, and the install-method → update-instructions dispatch.
"""
from __future__ import annotations

import pytest

from app.core.version import VersionManager


# ---------------------------------------------------------------------------
# get_install_method
# ---------------------------------------------------------------------------


def test_get_install_method_defaults_to_docker_when_unset(
    monkeypatch: pytest.MonkeyPatch,
):
    """An absent env var means Docker — that's the historical Core deployment
    shape and the only one that existed before this method. Defaulting any
    other way would silently change behaviour for every prior installation."""
    monkeypatch.delenv("FILAOPS_INSTALL_METHOD", raising=False)
    assert VersionManager.get_install_method() == "docker"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("docker", "docker"),
        ("tauri", "tauri"),
        ("manual", "manual"),
        ("  tauri  ", "tauri"),          # surrounding whitespace
        ("TAURI", "tauri"),              # case insensitive
        ("Docker", "docker"),
    ],
)
def test_get_install_method_recognises_known_values(
    raw: str, expected: str, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", raw)
    assert VersionManager.get_install_method() == expected


@pytest.mark.parametrize("raw", ["", "   ", "kubernetes", "snap", "random-typo"])
def test_get_install_method_unknown_values_collapse_to_default(
    raw: str, monkeypatch: pytest.MonkeyPatch,
):
    """Unknown values shouldn't crash — they collapse to the default so
    downstream UI branches don't have to handle a sentinel they don't know
    about. A typo in a deployment script should degrade gracefully rather
    than break the Settings page."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", raw)
    assert VersionManager.get_install_method() == "docker"


# ---------------------------------------------------------------------------
# get_current_version surfaces install_method
# ---------------------------------------------------------------------------


def test_get_current_version_includes_install_method(monkeypatch: pytest.MonkeyPatch):
    """The /system/version response derives its install_method from this
    field — exposing it via get_current_version() keeps a single source of
    truth so the health endpoint, the settings endpoint, and any future
    diagnostics report the same value."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "tauri")
    info = VersionManager.get_current_version()
    assert info["install_method"] == "tauri"


def test_get_current_version_legacy_update_method_matches_install(
    monkeypatch: pytest.MonkeyPatch,
):
    """The legacy `update_method` field is preserved for older clients that
    haven't migrated to reading install_method directly. It tracks the
    install method so they don't fall out of sync, but tauri reports its
    own updater rather than the docker-compose default."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "tauri")
    info = VersionManager.get_current_version()
    assert info["update_method"] == "tauri-updater"

    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "docker")
    info = VersionManager.get_current_version()
    assert info["update_method"] == "docker-compose"


# ---------------------------------------------------------------------------
# get_update_instructions branches on install method
# ---------------------------------------------------------------------------


def test_update_instructions_docker_keeps_legacy_runbook(
    monkeypatch: pytest.MonkeyPatch,
):
    """Existing Docker installs must keep getting the docker-compose runbook —
    this PR is additive, not a breaking change for the deployment shape that's
    in production. The first instruction must still be the `docker-compose down`
    step that every customer-facing Core upgrade has used since the v1 era."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "docker")
    instructions = VersionManager.get_update_instructions()

    assert instructions["method"] == "docker-compose"
    assert instructions["requires_manual_steps"] is True
    assert "docker-compose down" in instructions["instructions"][0]


def test_update_instructions_tauri_returns_no_manual_steps(
    monkeypatch: pytest.MonkeyPatch,
):
    """Tauri installs surface a short explainer pointing at the tray icon —
    no copy-pasteable shell commands. The `requires_manual_steps=False`
    flag is what the frontend keys off to swap its docker-runbook section
    for an "this happens automatically" message."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "tauri")
    instructions = VersionManager.get_update_instructions()

    assert instructions["method"] == "tauri-updater"
    assert instructions["requires_manual_steps"] is False
    # No shell-command instructions should leak through to a desktop user.
    joined = " ".join(instructions["instructions"]).lower()
    assert "docker-compose" not in joined
    assert "alembic" not in joined


def test_update_instructions_default_when_env_unset_matches_docker(
    monkeypatch: pytest.MonkeyPatch,
):
    """When no env var is set we fall back to docker — same shape, same copy.
    This guarantees that a fresh Docker install (no env override) gets the
    historical experience and isn't accidentally pushed onto an empty
    branch."""
    monkeypatch.delenv("FILAOPS_INSTALL_METHOD", raising=False)
    instructions = VersionManager.get_update_instructions()
    assert instructions["method"] == "docker-compose"
    assert instructions["requires_manual_steps"] is True
