"""
Endpoint tests for /api/v1/admin/backups and the database_backup setting.

Backups contain customer data and password hashes, so the access tests
matter as much as the happy path: only admins may see, start or download.
"""
import gzip
import threading
from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.backup_run import BackupRun
from app.models.system_setting import SystemSetting
from app.services import database_backup as backup

BASE = "/api/v1/admin/backups"


def _wipe() -> None:
    with SessionLocal() as s:
        s.query(BackupRun).delete()
        s.query(SystemSetting).filter(SystemSetting.key == backup.SETTING_KEY).delete()
        s.commit()


@pytest.fixture
def backup_folder(tmp_path, monkeypatch):
    folder = tmp_path / "backups"
    folder.mkdir()
    monkeypatch.setattr(settings, "BACKUP_DIR", str(folder))
    monkeypatch.setattr(backup, "_in_container", lambda: False)
    _wipe()
    yield folder
    _wipe()


@pytest.fixture
def stored_backup(db, backup_folder):
    """A finished backup row with its file on disk."""
    name = "filaops-20261013-030000.sql.gz"
    with gzip.open(backup_folder / name, "wb") as f:
        f.write(b"-- PostgreSQL database dump complete\n")
    run = BackupRun(
        status="ok", trigger="scheduled", filename=name,
        size_bytes=(backup_folder / name).stat().st_size, table_count=1,
        finished_at=datetime.now(timezone.utc),
    )
    db.add(run)
    db.flush()
    return run


# =============================================================================
# Access control
# =============================================================================


@pytest.mark.parametrize("method, path", [
    ("get", BASE),
    ("get", f"{BASE}/runs"),
    ("post", f"{BASE}/runs"),
    ("get", f"{BASE}/runs/1/download"),
])
def test_requires_authentication(unauthed_client, method, path):
    assert getattr(unauthed_client, method)(path).status_code == 401


@pytest.mark.parametrize("method, path", [
    ("get", BASE),
    ("get", f"{BASE}/runs"),
    ("post", f"{BASE}/runs"),
    ("get", f"{BASE}/runs/1/download"),
])
def test_operators_are_refused(unauthed_client, role_headers, method, path):
    response = getattr(unauthed_client, method)(path, headers=role_headers("operator"))
    assert response.status_code == 403


def test_operator_cannot_download_an_existing_backup(unauthed_client, role_headers, stored_backup):
    response = unauthed_client.get(
        f"{BASE}/runs/{stored_backup.id}/download", headers=role_headers("operator"),
    )
    assert response.status_code == 403


def test_operator_cannot_change_the_schedule(unauthed_client, role_headers):
    response = unauthed_client.put(
        "/api/v1/system/settings/database_backup",
        json={"value": {"enabled": False}},
        headers=role_headers("operator"),
    )
    assert response.status_code == 403


# =============================================================================
# Status, settings, runs
# =============================================================================


def test_status_shape(client, backup_folder):
    response = client.get(BASE)
    assert response.status_code == 200
    body = response.json()
    assert body["settings"] == backup.DEFAULT_SETTINGS
    assert body["running"] is False
    assert body["last_run"] is None
    assert body["storage"]["path"] == str(backup_folder)
    assert body["storage"]["problem"] is None
    assert set(body["tools"]) == {
        "pg_dump_path", "pg_dump_version", "server_version", "versions_match", "problem",
    }


def test_schedule_is_saved_and_validated(client, backup_folder):
    value = {"enabled": True, "time": "01:30", "timezone": "UTC", "retention_days": 30}
    response = client.put("/api/v1/system/settings/database_backup", json={"value": value})
    assert response.status_code == 200, response.text
    assert response.json()["value"] == value
    assert client.get(BASE).json()["settings"] == value

    bad = client.put(
        "/api/v1/system/settings/database_backup",
        json={"value": {**value, "retention_days": 0}},
    )
    assert bad.status_code == 400
    assert "retention_days" in bad.json()["detail"]


def test_run_list_and_download(client, stored_backup):
    runs = client.get(f"{BASE}/runs").json()
    assert [r["id"] for r in runs] == [stored_backup.id]
    assert runs[0]["downloadable"] is True

    response = client.get(f"{BASE}/runs/{stored_backup.id}/download")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/gzip"
    assert response.headers["cache-control"] == "no-store"
    assert stored_backup.filename in response.headers["content-disposition"]
    assert gzip.decompress(response.content).startswith(b"-- PostgreSQL")


def test_download_of_a_pruned_backup_is_404(client, db, stored_backup):
    stored_backup.file_deleted_at = datetime.now(timezone.utc)
    db.flush()
    assert client.get(f"{BASE}/runs/{stored_backup.id}/download").status_code == 404


def test_download_of_a_failed_run_is_404(client, db, backup_folder):
    run = BackupRun(status="failed", trigger="manual", error="boom")
    db.add(run)
    db.flush()
    assert client.get(f"{BASE}/runs/{run.id}/download").status_code == 404


def test_download_with_a_tampered_filename_is_404(client, db, backup_folder):
    run = BackupRun(status="ok", trigger="manual", filename="../../.env")
    db.add(run)
    db.flush()
    assert client.get(f"{BASE}/runs/{run.id}/download").status_code == 404


def test_run_now_starts_a_backup(client, backup_folder, monkeypatch):
    started = threading.Event()

    def _fake_start(trigger, triggered_by_id=None, **kwargs):
        assert trigger == "manual"
        assert triggered_by_id == 1
        started.set()
        return 42

    monkeypatch.setattr(backup, "start_backup", _fake_start)
    response = client.post(f"{BASE}/runs")
    assert response.status_code == 202
    assert response.json() == {"id": 42, "status": "running"}
    assert started.is_set()


def test_run_now_while_running_is_409(client, backup_folder, monkeypatch):
    def _busy(*args, **kwargs):
        raise backup.BackupAlreadyRunning()

    monkeypatch.setattr(backup, "start_backup", _busy)
    response = client.post(f"{BASE}/runs")
    assert response.status_code == 409
    assert "already running" in response.json()["detail"]
