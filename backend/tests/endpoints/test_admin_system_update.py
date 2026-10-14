"""
Tests for the removed one-click updater (/api/v1/admin/system/update/*).

FilaOps has no safe way to update itself from the web app: on a standard
Docker install the backend can't reach the host's Docker daemon, and the old
endpoint's advice to mount /var/run/docker.sock would have handed the web app
root-equivalent control of the host. POST /update/start now always answers
410 Gone with a link to the upgrade guide, and never runs anything.
"""
import subprocess

import pytest

from app.api.v1.endpoints.admin import system as admin_system
from app.core.version import UPGRADE_DOCS_URL

START_URL = "/api/v1/admin/system/update/start"
STATUS_URL = "/api/v1/admin/system/update/status"


@pytest.fixture
def no_subprocess(monkeypatch):
    """Fail the test if the endpoint shells out to git, docker or alembic."""
    calls = []

    def _forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError(f"update endpoint ran a subprocess: {args!r}")

    monkeypatch.setattr(subprocess, "run", _forbidden)
    monkeypatch.setattr(subprocess, "Popen", _forbidden)
    monkeypatch.setattr(subprocess, "check_output", _forbidden)
    return calls


def test_start_update_returns_410_with_upgrade_guide(client, no_subprocess):
    resp = client.post(START_URL, json={})

    assert resp.status_code == 410
    detail = resp.json()["detail"]
    assert UPGRADE_DOCS_URL in detail
    assert no_subprocess == []


def test_start_update_with_version_still_runs_nothing(client, no_subprocess):
    """A pinned version used to run `git fetch` + `git checkout`; it must not now."""
    resp = client.post(START_URL, json={"version": "v4.3.0"})

    assert resp.status_code == 410
    assert no_subprocess == []


def test_start_update_never_suggests_mounting_docker_socket(client):
    detail = client.post(START_URL, json={}).json()["detail"].lower()

    assert "docker.sock" not in detail
    assert "docker cli" not in detail
    assert "mount" not in detail


def test_start_update_requires_auth(unauthed_client):
    assert unauthed_client.post(START_URL, json={}).status_code == 401


def test_start_update_requires_admin(unauthed_client, role_headers):
    resp = unauthed_client.post(START_URL, json={}, headers=role_headers("operator"))
    assert resp.status_code == 403


def test_update_status_endpoint_removed(client):
    assert client.get(STATUS_URL).status_code == 404


def test_updater_internals_removed():
    """The background updater and its Docker/git probes are gone, not just unwired."""
    for name in (
        "_run_update",
        "_update_status",
        "_check_docker_available",
        "_is_running_in_container",
    ):
        assert not hasattr(admin_system, name), name
