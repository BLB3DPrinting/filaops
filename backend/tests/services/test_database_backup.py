"""
Tests for app.services.database_backup — in-app database backups.

Most tests replace pg_dump with a synthetic dump so they run anywhere. The
last test runs the real pg_dump and restores nothing; it is skipped unless a
pg_dump whose major version matches the test server is installed (it runs in
the backend Docker image).
"""
import gzip
import os
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.backup_run import BackupRun
from app.models.system_setting import SystemSetting
from app.services import database_backup as backup
from app.services.database_backup import (
    BackupAlreadyRunning,
    BackupError,
    validate_backup_settings,
)

UTC = timezone.utc


# =============================================================================
# Fixtures and helpers
# =============================================================================


def _wipe() -> None:
    with SessionLocal() as s:
        s.query(BackupRun).delete()
        s.query(SystemSetting).filter(SystemSetting.key == backup.SETTING_KEY).delete()
        s.commit()


@pytest.fixture
def backups(tmp_path, monkeypatch):
    """Empty backup history and a private backup folder; returns the folder."""
    folder = tmp_path / "backups"
    monkeypatch.setattr(settings, "BACKUP_DIR", str(folder))
    # These tests may run inside a container, where a tmp folder is not a
    # volume; the mount check has its own tests below.
    monkeypatch.setattr(backup, "_in_container", lambda: False)
    _wipe()
    yield folder
    _wipe()


def _server_major() -> int:
    with SessionLocal() as s:
        return backup.server_version(s)[0]


def _table_count() -> int:
    with SessionLocal() as s:
        return backup.count_public_tables(s)


def _dump_bytes(tables: int, complete: bool = True) -> bytes:
    lines = ["--\n-- PostgreSQL database dump\n--\n"]
    for i in range(tables):
        lines.append(f"COPY public.t{i} (id, note) FROM stdin;\n")
        # A data row that looks like a COPY header must not count as a table.
        lines.append("1\tCOPY public.not_a_table\n")
        lines.append("\\.\n")
    if complete:
        lines.append("--\n-- PostgreSQL database dump complete\n--\n")
    return "".join(lines).encode()


def _write_gz(path: Path, payload: bytes) -> Path:
    with gzip.open(path, "wb") as f:
        f.write(payload)
    return path


@pytest.fixture
def fake_pg_dump(monkeypatch):
    """Replace pg_dump with a synthetic one; returns a dict to tune it."""
    major = _server_major()
    knobs = {"tables": None, "complete": True, "major": major, "fail": None}

    monkeypatch.setattr(backup, "find_pg_dump", lambda: "/usr/bin/pg_dump")
    monkeypatch.setattr(
        backup, "pg_dump_version",
        lambda path: f"pg_dump (PostgreSQL) {knobs['major']}.4 (Debian)",
    )

    def _dump_to(partial, pg_dump, conn, timeout):
        if knobs["fail"]:
            raise BackupError(knobs["fail"])
        tables = knobs["tables"] if knobs["tables"] is not None else _table_count()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(partial, flags, 0o600), "wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb") as gz:
                gz.write(_dump_bytes(tables, knobs["complete"]))

    monkeypatch.setattr(backup, "_dump_to", _dump_to)
    return knobs


def _runs() -> list[BackupRun]:
    with SessionLocal() as s:
        runs = s.query(BackupRun).order_by(BackupRun.id).all()
        s.expunge_all()
        return runs


def _add_run(**fields) -> int:
    with SessionLocal() as s:
        run = BackupRun(**fields)
        s.add(run)
        s.commit()
        return run.id


def _lock_held() -> bool:
    """Whether any connection holds the backup lock (checked via pg_locks)."""
    with engine.connect() as conn:
        return bool(conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
                "AND classid = 0 AND objid = :k AND granted)"
            ),
            {"k": backup.ADVISORY_LOCK_KEY},
        ).scalar())


def _zone_or_skip(name: str):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        pytest.skip(f"no tz database entry for {name} on this machine")


# =============================================================================
# Settings validation
# =============================================================================


class TestValidateSettings:
    def test_missing_fields_take_defaults(self):
        assert validate_backup_settings({}) == backup.DEFAULT_SETTINGS

    def test_valid_values_pass(self):
        value = {"enabled": False, "time": "23:59", "timezone": "UTC", "retention_days": 365}
        assert validate_backup_settings(value) == value

    @pytest.mark.parametrize("value, fragment", [
        ([], "must be an object"),
        ({"keep": 3}, "unknown field"),
        ({"enabled": "yes"}, "enabled"),
        ({"time": "3:00"}, "HH:MM"),
        ({"time": "24:00"}, "HH:MM"),
        ({"time": "12:60"}, "HH:MM"),
        ({"timezone": "Mars/Olympus"}, "unknown time zone"),
        ({"timezone": ""}, "timezone"),
        ({"retention_days": 0}, "retention_days"),
        ({"retention_days": 366}, "retention_days"),
        ({"retention_days": True}, "retention_days"),
        ({"retention_days": 7.5}, "retention_days"),
    ])
    def test_invalid_values_are_rejected(self, value, fragment):
        with pytest.raises(ValueError, match=fragment):
            validate_backup_settings(value)

    def test_invalid_stored_value_falls_back_to_defaults(self, backups):
        with SessionLocal() as s:
            s.add(SystemSetting(key=backup.SETTING_KEY, value={"time": "nope"}))
            s.commit()
            assert backup.get_backup_settings(s) == backup.DEFAULT_SETTINGS


# =============================================================================
# Schedule
# =============================================================================


class TestSchedule:
    cfg = {**backup.DEFAULT_SETTINGS, "time": "03:00", "timezone": "UTC"}

    def test_slot_earlier_today(self):
        now = datetime(2026, 10, 13, 15, 0, tzinfo=UTC)
        assert backup.most_recent_slot(now, self.cfg) == datetime(2026, 10, 13, 3, 0, tzinfo=UTC)
        assert backup.next_slot(now, self.cfg) == datetime(2026, 10, 14, 3, 0, tzinfo=UTC)

    def test_slot_before_todays_time_is_yesterday(self):
        now = datetime(2026, 10, 13, 2, 59, tzinfo=UTC)
        assert backup.most_recent_slot(now, self.cfg) == datetime(2026, 10, 12, 3, 0, tzinfo=UTC)
        assert backup.next_slot(now, self.cfg) == datetime(2026, 10, 13, 3, 0, tzinfo=UTC)

    def test_legacy_zone_names_from_browsers_are_accepted(self):
        # Chrome reports America/Indianapolis. Debian 13's tzdata dropped such
        # names and Windows has no tz database; the tzdata requirement has them.
        value = validate_backup_settings({"timezone": "America/Indianapolis"})
        assert value["timezone"] == "America/Indianapolis"

    def test_local_time_zone_is_honoured_across_dst(self):
        _zone_or_skip("America/Chicago")
        cfg = {**self.cfg, "time": "02:30", "timezone": "America/Chicago"}
        # 02:30 CDT (UTC-5) on Oct 13 is 07:30 UTC.
        now = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
        assert backup.most_recent_slot(now, cfg) == datetime(2026, 10, 13, 7, 30, tzinfo=UTC)
        # After DST ends on Nov 1, 02:30 CST (UTC-6) is 08:30 UTC.
        now = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
        assert backup.most_recent_slot(now, cfg) == datetime(2026, 11, 3, 8, 30, tzinfo=UTC)

    def test_due_when_no_scheduled_run_since_slot(self, backups):
        now = datetime.now(UTC)
        with SessionLocal() as s:
            assert backup.is_due(s, now, self.cfg) is True

    def test_not_due_when_disabled(self, backups):
        with SessionLocal() as s:
            assert backup.is_due(s, datetime.now(UTC), {**self.cfg, "enabled": False}) is False

    def test_scheduled_run_since_slot_means_not_due(self, backups):
        now = datetime.now(UTC)
        slot = backup.most_recent_slot(now, self.cfg)
        _add_run(status="failed", trigger="scheduled", started_at=slot + timedelta(minutes=1))
        with SessionLocal() as s:
            assert backup.is_due(s, now, self.cfg) is False

    def test_manual_run_does_not_replace_the_scheduled_one(self, backups):
        now = datetime.now(UTC)
        slot = backup.most_recent_slot(now, self.cfg)
        _add_run(status="ok", trigger="manual", started_at=slot + timedelta(minutes=1))
        _add_run(status="ok", trigger="scheduled", started_at=slot - timedelta(minutes=1))
        with SessionLocal() as s:
            assert backup.is_due(s, now, self.cfg) is True


# =============================================================================
# Version parsing and dump verification
# =============================================================================


@pytest.mark.parametrize("version, major", [
    ("pg_dump (PostgreSQL) 16.4 (Debian 16.4-1.pgdg130+1)", 16),
    ("pg_dump (PostgreSQL) 17.0", 17),
    ("pg_dump (PostgreSQL) 9.6.24", 9),
    ("something else", None),
    (None, None),
])
def test_parse_major(version, major):
    assert backup.parse_major(version) == major


class TestVerifyDump:
    def test_counts_copy_sections_and_skips_data_rows(self, tmp_path):
        path = _write_gz(tmp_path / "d.sql.gz", _dump_bytes(3))
        assert backup.verify_dump(path) == 3

    def test_missing_completion_marker_fails(self, tmp_path):
        path = _write_gz(tmp_path / "d.sql.gz", _dump_bytes(3, complete=False))
        with pytest.raises(BackupError, match="incomplete"):
            backup.verify_dump(path)

    def test_truncated_file_fails(self, tmp_path):
        path = _write_gz(tmp_path / "d.sql.gz", _dump_bytes(50))
        data = path.read_bytes()
        path.write_bytes(data[: len(data) // 2])
        with pytest.raises(BackupError, match="damaged"):
            backup.verify_dump(path)

    def test_not_gzip_fails(self, tmp_path):
        path = tmp_path / "d.sql.gz"
        path.write_bytes(b"plain text, not gzip")
        with pytest.raises(BackupError, match="damaged"):
            backup.verify_dump(path)


# =============================================================================
# Running a backup
# =============================================================================


class TestStartBackup:
    def test_successful_backup_is_recorded_and_verified(self, backups, fake_pg_dump):
        run_id = backup.start_backup("manual", triggered_by_id=1, wait=True)

        [run] = _runs()
        assert run.id == run_id
        assert run.status == "ok", run.error
        assert run.trigger == "manual"
        assert run.triggered_by_id == 1
        assert run.table_count == run.expected_tables == _table_count()
        assert run.finished_at is not None
        assert backup.FILENAME_RE.match(run.filename)
        path = backups / run.filename
        assert path.stat().st_size == run.size_bytes
        assert list(backups.glob("*.partial")) == []
        # Released on the connection that took it, not left on a pooled one.
        assert _lock_held() is False
        if sys.platform != "win32":
            assert path.stat().st_mode & 0o777 == 0o600
            assert backups.stat().st_mode & 0o777 == 0o700

    def test_version_mismatch_fails_with_a_clear_reason(self, backups, fake_pg_dump):
        fake_pg_dump["major"] = _server_major() + 1
        backup.start_backup("manual", wait=True)

        [run] = _runs()
        assert run.status == "failed"
        assert "must match" in run.error
        assert list(backups.iterdir()) == []
        assert _lock_held() is False

    def test_missing_pg_dump_fails_with_a_clear_reason(self, backups, monkeypatch):
        monkeypatch.setattr(backup, "find_pg_dump", lambda: None)
        backup.start_backup("manual", wait=True)

        [run] = _runs()
        assert run.status == "failed"
        assert "pg_dump was not found" in run.error

    def test_dump_missing_tables_fails_and_leaves_no_file(self, backups, fake_pg_dump):
        fake_pg_dump["tables"] = 1
        backup.start_backup("manual", wait=True)

        [run] = _runs()
        assert run.status == "failed"
        assert "not a complete backup" in run.error
        assert list(backups.iterdir()) == []

    def test_incomplete_dump_fails(self, backups, fake_pg_dump):
        fake_pg_dump["complete"] = False
        backup.start_backup("manual", wait=True)

        [run] = _runs()
        assert run.status == "failed"
        assert "incomplete" in run.error

    def test_pg_dump_error_is_recorded(self, backups, fake_pg_dump):
        fake_pg_dump["fail"] = "pg_dump failed (exit code 1): connection refused"
        backup.start_backup("manual", wait=True)

        [run] = _runs()
        assert run.status == "failed"
        assert "connection refused" in run.error

    def test_second_backup_while_one_holds_the_lock_is_refused(self, backups, fake_pg_dump):
        with engine.connect() as other:
            assert other.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": backup.ADVISORY_LOCK_KEY}
            ).scalar()
            try:
                with pytest.raises(BackupAlreadyRunning):
                    backup.start_backup("manual", wait=True)
            finally:
                other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": backup.ADVISORY_LOCK_KEY})
                other.commit()
        assert _runs() == []
        # The lock was released: the next request works.
        assert backup.start_backup("manual", wait=True) is not None

    def test_scheduled_trigger_skips_when_already_done(self, backups, fake_pg_dump):
        now = datetime.now(UTC)
        slot = backup.most_recent_slot(now, backup.DEFAULT_SETTINGS)
        _add_run(status="ok", trigger="scheduled", started_at=slot + timedelta(seconds=1))
        assert backup.start_backup("scheduled", wait=True) is None
        assert len(_runs()) == 1

    def test_stale_running_rows_are_marked_interrupted(self, backups, fake_pg_dump):
        stale = _add_run(status="running", trigger="scheduled")
        backup.start_backup("manual", wait=True)

        runs = {r.id: r for r in _runs()}
        assert runs[stale].status == "failed"
        assert "Interrupted" in runs[stale].error

    def test_background_run_finishes(self, backups, fake_pg_dump):
        run_id = backup.start_backup("manual")
        for thread in threading.enumerate():
            if thread.name == f"backup-{run_id}":
                thread.join(timeout=30)
        [run] = _runs()
        assert run.status == "ok", run.error

    def test_status_reports_running_and_reaps_stale_rows(self, backups, fake_pg_dump):
        stale = _add_run(status="running", trigger="manual")
        with SessionLocal() as s:
            status = backup.get_status(s)
        assert status["running"] is False
        assert status["last_run"]["id"] == stale
        assert status["last_run"]["status"] == "failed"
        assert status["tools"]["versions_match"] is True
        assert status["storage"]["path"] == str(backups)
        assert _lock_held() is False

    def test_repeated_runs_never_leave_the_lock_held(self, backups, fake_pg_dump):
        # A Session hands its connection back to the pool on commit; if the
        # lock were taken through one, some of these would find it still held.
        for _ in range(5):
            with SessionLocal() as s:
                assert backup.check_running(s) is False
            assert backup.start_backup("manual", wait=True) is not None
        assert _lock_held() is False
        assert [r.status for r in _runs()] == ["ok"] * 5


# =============================================================================
# Retention
# =============================================================================


class TestPrune:
    def _ok_run(self, folder: Path, days_old: int, name: str) -> int:
        _write_gz(folder / name, _dump_bytes(1))
        return _add_run(
            status="ok", trigger="scheduled", filename=name,
            started_at=datetime.now(UTC) - timedelta(days=days_old),
        )

    def test_removes_expired_files_but_keeps_recent_ones(self, backups):
        backups.mkdir()
        old = self._ok_run(backups, 20, "filaops-20260901-030000.sql.gz")
        new = self._ok_run(backups, 1, "filaops-20261012-030000.sql.gz")
        cfg = {**backup.DEFAULT_SETTINGS, "retention_days": 14}

        with SessionLocal() as s:
            removed = backup.prune_backups(s, cfg, datetime.now(UTC))

        assert removed == ["filaops-20260901-030000.sql.gz"]
        assert not (backups / "filaops-20260901-030000.sql.gz").exists()
        assert (backups / "filaops-20261012-030000.sql.gz").exists()
        runs = {r.id: r for r in _runs()}
        assert runs[old].file_deleted_at is not None
        assert runs[new].file_deleted_at is None

    def test_never_removes_the_newest_good_backup(self, backups):
        backups.mkdir()
        self._ok_run(backups, 40, "filaops-20260801-030000.sql.gz")
        newest = self._ok_run(backups, 30, "filaops-20260901-030000.sql.gz")
        _add_run(status="failed", trigger="scheduled", error="boom")
        cfg = {**backup.DEFAULT_SETTINGS, "retention_days": 14}

        with SessionLocal() as s:
            removed = backup.prune_backups(s, cfg, datetime.now(UTC))

        assert removed == ["filaops-20260801-030000.sql.gz"]
        assert (backups / "filaops-20260901-030000.sql.gz").exists()
        assert {r.id: r for r in _runs()}[newest].file_deleted_at is None

    def test_leaves_untracked_files_and_cleans_old_partials(self, backups):
        backups.mkdir()
        mine = backups / "my-own-copy.sql.gz"
        mine.write_bytes(b"x")
        old_partial = backups / "filaops-20260901-030000.sql.gz.partial"
        old_partial.write_bytes(b"x")
        two_days_ago = (datetime.now() - timedelta(days=2)).timestamp()
        os.utime(old_partial, (two_days_ago, two_days_ago))
        fresh_partial = backups / "filaops-20261013-030000.sql.gz.partial"
        fresh_partial.write_bytes(b"x")

        with SessionLocal() as s:
            backup.prune_backups(s, backup.DEFAULT_SETTINGS, datetime.now(UTC))

        assert mine.exists()
        assert not old_partial.exists()
        assert fresh_partial.exists()


# =============================================================================
# Security Audit health
# =============================================================================


class TestBackupHealth:
    def _health(self, now=None):
        with SessionLocal() as s:
            return backup.backup_health(s, now or datetime.now(UTC))

    def test_no_backups_yet(self, backups, monkeypatch):
        monkeypatch.setattr(settings, "BACKUP_SCHEDULER_ENABLED", True)
        healthy, message = self._health()
        assert healthy is False
        assert "none has completed" in message

    def test_recent_success_is_healthy(self, backups, monkeypatch):
        monkeypatch.setattr(settings, "BACKUP_SCHEDULER_ENABLED", True)
        _add_run(status="ok", trigger="scheduled", table_count=95,
                 finished_at=datetime.now(UTC) - timedelta(hours=3))
        healthy, message = self._health()
        assert healthy is True
        assert "3 hours ago" in message
        assert "95 tables" in message

    def test_very_recent_success_is_not_called_an_hour_old(self, backups, monkeypatch):
        monkeypatch.setattr(settings, "BACKUP_SCHEDULER_ENABLED", True)
        _add_run(status="ok", trigger="manual", table_count=95,
                 finished_at=datetime.now(UTC) - timedelta(minutes=5))
        healthy, message = self._health()
        assert healthy is True
        assert "less than an hour ago" in message

    def test_last_run_failed(self, backups, monkeypatch):
        monkeypatch.setattr(settings, "BACKUP_SCHEDULER_ENABLED", True)
        _add_run(status="ok", trigger="scheduled", table_count=95,
                 started_at=datetime.now(UTC) - timedelta(hours=5),
                 finished_at=datetime.now(UTC) - timedelta(hours=5))
        _add_run(status="failed", trigger="manual", error="disk full",
                 started_at=datetime.now(UTC) - timedelta(hours=1))
        healthy, message = self._health()
        assert healthy is False
        assert "disk full" in message

    def test_stale_success(self, backups, monkeypatch):
        monkeypatch.setattr(settings, "BACKUP_SCHEDULER_ENABLED", True)
        _add_run(status="ok", trigger="scheduled", table_count=95,
                 started_at=datetime.now(UTC) - timedelta(days=3),
                 finished_at=datetime.now(UTC) - timedelta(days=3))
        healthy, message = self._health()
        assert healthy is False
        assert "3 day(s) old" in message

    def test_schedule_turned_off(self, backups):
        with SessionLocal() as s:
            s.add(SystemSetting(key=backup.SETTING_KEY, value={"enabled": False}))
            s.commit()
        _add_run(status="ok", trigger="manual", table_count=95,
                 finished_at=datetime.now(UTC) - timedelta(hours=1))
        healthy, message = self._health()
        assert healthy is False
        assert "turned off" in message

    def test_audit_check_reads_recorded_runs(self, backups, monkeypatch):
        monkeypatch.setattr(settings, "BACKUP_SCHEDULER_ENABLED", True)
        _add_run(status="ok", trigger="scheduled", table_count=95,
                 finished_at=datetime.now(UTC) - timedelta(hours=2))
        scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
        monkeypatch.syspath_prepend(scripts_dir)
        from scripts.security_audit import CheckStatus, SecurityAuditor

        auditor = SecurityAuditor()
        auditor._check_backup_configured()
        [result] = auditor.results
        assert result.id == "backup_configured"
        assert result.status == CheckStatus.PASS
        assert result.remediation is None


# =============================================================================
# Real pg_dump (runs where a matching pg_dump is installed, e.g. the Docker image)
# =============================================================================


def _real_pg_dump_matches() -> bool:
    path = backup.find_pg_dump()
    return bool(path) and backup.parse_major(backup.pg_dump_version(path)) == _server_major()


@pytest.mark.skipif(not _real_pg_dump_matches(), reason="no pg_dump matching the server's major version")
def test_real_pg_dump_produces_a_verified_backup(backups):
    run_id = backup.start_backup("manual", wait=True)

    [run] = _runs()
    assert run.id == run_id
    assert run.status == "ok", run.error
    assert run.table_count >= run.expected_tables > 0
    path = backups / run.filename
    with gzip.open(path, "rb") as dump:
        head = dump.read(4096)
    assert b"PostgreSQL database dump" in head
    # The password never appears in what we recorded.
    password = backup._connection()["password"]
    if password:
        assert password not in (run.error or "")
        assert password.encode() not in path.read_bytes()


# =============================================================================
# Review follow-ups
# =============================================================================


class TestReviewFollowUps:
    def test_invalid_saved_schedule_keeps_backups_off(self, backups):
        with SessionLocal() as s:
            s.add(SystemSetting(key=backup.SETTING_KEY,
                                value={"enabled": False, "timezone": "Mars/Olympus"}))
            s.commit()
            assert backup.get_backup_settings(s)["enabled"] is False
            assert "unknown time zone" in backup.settings_problem(s)

    def test_started_at_uses_the_schedule_clock(self, backups, fake_pg_dump):
        # A database clock behind the app's must not leave the slot unclaimed.
        fixed = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)
        backup.start_backup("manual", wait=True, now=lambda: fixed)
        [run] = _runs()
        assert run.started_at == fixed

    def test_status_does_not_take_the_lock(self, backups, fake_pg_dump):
        with engine.connect() as other:
            other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": backup.ADVISORY_LOCK_KEY})
            other.commit()
            try:
                with SessionLocal() as s:
                    assert backup.check_running(s) is True
            finally:
                other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": backup.ADVISORY_LOCK_KEY})
                other.commit()
        # With nothing running and nothing stale, the check is read-only and
        # leaves a start free to proceed.
        with SessionLocal() as s:
            assert backup.check_running(s) is False
        assert backup._process_lock.locked() is False
        assert _lock_held() is False

    def test_failed_thread_start_releases_the_locks(self, backups, fake_pg_dump, monkeypatch):
        def _no_thread(self):
            raise RuntimeError("can't start new thread")

        monkeypatch.setattr(threading.Thread, "start", _no_thread)
        with pytest.raises(RuntimeError):
            backup.start_backup("manual")
        assert backup._process_lock.locked() is False
        assert _lock_held() is False

    def test_files_of_runs_that_did_not_finish_ok_expire_too(self, backups):
        backups.mkdir()
        name = "filaops-20260901-030000.sql.gz"
        _write_gz(backups / name, _dump_bytes(1))
        _add_run(status="failed", trigger="scheduled", filename=name,
                 error="Interrupted", started_at=datetime.now(UTC) - timedelta(days=30))
        with SessionLocal() as s:
            removed = backup.prune_backups(s, backup.DEFAULT_SETTINGS, datetime.now(UTC))
        assert removed == [name]
        assert not (backups / name).exists()


# =============================================================================
# Backup folder must be on a volume inside a container
# =============================================================================


class TestStorageMustBeAVolume:
    def _container(self, monkeypatch, mounts):
        monkeypatch.setattr(backup, "_in_container", lambda: True)
        monkeypatch.setattr(backup, "_mount_points", lambda: mounts)

    def test_folder_on_the_container_layer_is_refused(self, backups, fake_pg_dump, monkeypatch):
        self._container(monkeypatch, ["/", "/etc/hosts", "/var/lib/filaops/config"])
        backup.start_backup("manual", wait=True)

        [run] = _runs()
        assert run.status == "failed"
        assert "not on a mounted volume" in run.error
        assert not backups.exists()  # refused before anything was written

    def test_folder_on_a_volume_is_accepted(self, backups, fake_pg_dump, monkeypatch):
        self._container(monkeypatch, ["/", str(backups)])
        backup.start_backup("manual", wait=True)

        [run] = _runs()
        assert run.status == "ok", run.error

    def test_folder_inside_a_mounted_parent_is_accepted(self, backups, monkeypatch):
        self._container(monkeypatch, ["/", str(backups.parent)])
        assert backup.storage_problem(backups) is None

    def test_a_mount_with_a_similar_name_does_not_count(self, backups, monkeypatch):
        self._container(monkeypatch, ["/", str(backups) + "-old"])
        assert "not on a mounted volume" in backup.storage_problem(backups)

    def test_unreadable_mount_information_is_refused(self, backups, monkeypatch):
        self._container(monkeypatch, [])
        assert "cannot tell" in backup.storage_problem(backups)

    def test_outside_a_container_any_folder_is_fine(self, backups, monkeypatch):
        monkeypatch.setattr(backup, "_in_container", lambda: False)
        assert backup.storage_problem(backups) is None

    def test_status_and_audit_report_the_problem(self, backups, monkeypatch):
        self._container(monkeypatch, ["/"])
        with SessionLocal() as s:
            status = backup.get_status(s)
            healthy, message = backup.backup_health(s)
        assert "not on a mounted volume" in status["storage"]["problem"]
        assert healthy is False
        assert "not on a mounted volume" in message

    def test_mountinfo_parsing(self, tmp_path, monkeypatch):
        info = tmp_path / "mountinfo"
        info.write_text(
            "22 1 0:21 / / rw,relatime - overlay overlay rw\n"
            "530 22 8:1 /volumes/filaops_backups/_data /app/backups rw - ext4 /dev/sda1 rw\n"
            "531 22 8:1 /x /mnt/my\\040disk rw - ext4 /dev/sda1 rw\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(backup, "MOUNTINFO", info)
        assert backup._mount_points() == ["/", "/app/backups", "/mnt/my disk"]
