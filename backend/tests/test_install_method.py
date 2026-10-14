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

from app.core.version import UPGRADE_DOCS_URL, VersionManager


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


def _step_index(steps: list[str], needle: str) -> int:
    """Index of the first step containing ``needle`` (fails if absent)."""
    for i, step in enumerate(steps):
        if needle in step:
            return i
    raise AssertionError(f"no step contains {needle!r}: {steps!r}")


def test_update_instructions_docker_matches_upgrade_guide(
    monkeypatch: pytest.MonkeyPatch,
):
    """Docker installs get the docs/UPGRADE.md runbook: back up with pg_dump,
    fetch tags, check out the release tag, `docker compose up -d --build`,
    then check /api/v1/system/version. The method label stays
    "docker-compose" so clients that read it keep working."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "docker")
    instructions = VersionManager.get_update_instructions()

    assert instructions["method"] == "docker-compose"
    assert instructions["requires_manual_steps"] is True
    steps = instructions["instructions"]

    backup = _step_index(
        steps,
        "docker exec filaops-db pg_dump -U postgres -d filaops "
        "--no-owner --no-privileges > filaops_before_upgrade.sql",
    )
    fetch = _step_index(steps, "git fetch --tags")
    checkout = _step_index(steps, "git checkout vX.Y.Z")
    rebuild = _step_index(steps, "docker compose up -d --build")
    verify = _step_index(steps, "/api/v1/system/version")
    assert backup < fetch < checkout < rebuild < verify


def test_update_instructions_docker_drops_obsolete_steps(
    monkeypatch: pytest.MonkeyPatch,
):
    """Migrations run in the `migrate` service, so there is no manual alembic
    step, and the runbook never stops the stack, pulls `main` or rebuilds
    with --no-cache."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "docker")
    joined = " ".join(VersionManager.get_update_instructions()["instructions"])

    assert "alembic" not in joined
    assert "docker-compose" not in joined
    assert " down" not in joined
    assert "--no-cache" not in joined
    assert "git pull" not in joined
    assert "main" not in joined


def test_update_instructions_docker_rollback_restores_backup(
    monkeypatch: pytest.MonkeyPatch,
):
    """Rolling back means restoring the pre-upgrade backup and checking out
    the previous tag (docs/UPGRADE.md "Rolling back"), never stepping
    migrations down one at a time or wiping volumes."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "docker")
    rollback = VersionManager.get_update_instructions()["rollback_steps"]
    joined = " ".join(rollback).lower()

    assert "alembic downgrade" not in joined
    restore = _step_index(rollback, "Restore the database backup")
    checkout = _step_index(rollback, "git checkout vX.Y.Z")
    rebuild = _step_index(rollback, "docker compose up -d --build")
    assert restore < checkout < rebuild
    # down -v is only mentioned as a warning, never as a step to run.
    for step in rollback:
        if "down -v" in step:
            assert step.startswith("Never")


def test_update_instructions_docker_requires_backup_up_front(
    monkeypatch: pytest.MonkeyPatch,
):
    """The backup is a step, not an optional recommendation."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "docker")
    instructions = VersionManager.get_update_instructions()

    assert "recommended" not in instructions["backup_recommendation"].lower()
    assert "restor" in instructions["backup_recommendation"].lower()
    assert "filaops_config" in instructions["backup_recommendation"]


@pytest.mark.parametrize("method", ["docker", "manual", "tauri"])
def test_update_instructions_link_to_docs_site(
    monkeypatch: pytest.MonkeyPatch, method: str
):
    """Every branch links to the published upgrade guide, not a GitHub path
    that didn't exist on main."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", method)
    instructions = VersionManager.get_update_instructions()

    assert instructions["documentation_url"] == UPGRADE_DOCS_URL
    assert UPGRADE_DOCS_URL == "https://blb3dprinting.github.io/filaops/UPGRADE/"


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


def test_update_instructions_manual_returns_baremetal_runbook(
    monkeypatch: pytest.MonkeyPatch,
):
    """Manual (bare-metal) installs need their own runbook — `pip install`,
    `alembic upgrade head`, restart-your-service — not the docker-compose
    runbook that the previous code would have served them as a fallthrough.

    The runbook stays generic on the restart step (systemd vs supervisord
    vs plain shell) because Core doesn't dictate a process manager."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "manual")
    instructions = VersionManager.get_update_instructions()

    assert instructions["method"] == "manual"
    assert instructions["requires_manual_steps"] is True
    joined = " ".join(instructions["instructions"]).lower()
    # Manual install is alembic + pip + git, NOT docker-compose
    assert "docker-compose" not in joined
    assert "pip install" in joined
    assert "alembic upgrade head" in joined


def test_update_instructions_manual_matches_upgrade_guide(
    monkeypatch: pytest.MonkeyPatch,
):
    """Manual installs follow docs/UPGRADE.md's manual steps: back up, check
    out the tag, pip + alembic in backend/, npm ci + build in frontend/,
    restart, confirm via /api/v1/system/version. Rollback restores the
    backup instead of stepping migrations down."""
    monkeypatch.setenv("FILAOPS_INSTALL_METHOD", "manual")
    instructions = VersionManager.get_update_instructions()
    steps = instructions["instructions"]

    backup = _step_index(steps, "pg_dump")
    checkout = _step_index(steps, "git checkout vX.Y.Z")
    backend = _step_index(steps, "pip install -r requirements.txt, then alembic upgrade head")
    frontend = _step_index(steps, "npm ci, then npm run build")
    restart = _step_index(steps, "Restart")
    verify = _step_index(steps, "/api/v1/system/version")
    assert backup < checkout < backend < frontend < restart < verify
    assert "Node.js 24" in steps[frontend]

    rollback = " ".join(instructions["rollback_steps"]).lower()
    assert "alembic downgrade" not in rollback
    assert "restore the database backup" in rollback


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
