"""
Database backups run from inside FilaOps.

An admin sets the schedule and retention on the Backups page; the backend runs
``pg_dump`` on that schedule (see ``app.services.backup_scheduler``) or when an
admin presses "Run backup now", and records every attempt in ``backup_runs``.

A backup is a plain-SQL dump, gzip-compressed — the same format as a
``pg_dump --no-owner --no-privileges | gzip`` cron job, so it restores with
``gunzip -c FILE | psql``. It counts as OK only if it passes the same checks a
careful admin would make by hand:

* the gzip stream reads back to the end (the file on disk is not damaged),
* the dump ends with pg_dump's "dump complete" marker (it was not cut short),
* it has a ``COPY public.`` data section for every table the database had
  when the dump started.

Rules that keep backups usable and private:

* ``pg_dump``'s major version must equal the server's. A newer pg_dump writes
  settings an older server rejects on restore; an older one cannot dump a
  newer server at all. The Docker image pins the client to the server's major.
* The database password reaches pg_dump through ``PGPASSWORD`` in a minimal
  environment, never on the command line (where ``ps`` would show it).
* Dumps hold customer data and password hashes: files are created ``0600``
  in a ``0700`` directory, are written under a ``.partial`` name until
  verified, and only admins can list or download them.
* One backup at a time across every backend process: a Postgres advisory lock
  guards each run, so two workers or a manual run during a scheduled one
  cannot overlap.
"""
from __future__ import annotations

import gzip
import os
import re
import shutil
import subprocess
import tempfile
import threading
import zlib
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.paths import resolve_backup_dir
from app.logging_config import get_logger
from app.models.backup_run import BackupRun
from app.models.system_setting import SystemSetting

logger = get_logger(__name__)

SETTING_KEY = "database_backup"
DEFAULT_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "time": "03:00",
    "timezone": "UTC",
    "retention_days": 14,
}
MAX_RETENTION_DAYS = 365

# filaops-YYYYMMDD-HHMMSS.sql.gz, with -2, -3... if two start in one second.
FILENAME_RE = re.compile(r"^filaops-\d{8}-\d{6}(?:-\d{1,3})?\.sql\.gz$")
PARTIAL_SUFFIX = ".partial"
DUMP_COMPLETE_MARKER = b"-- PostgreSQL database dump complete"
COPY_PREFIX = b"COPY public."
COPY_END = b"\\."

# Fixed, arbitrary key for the session-level advisory lock that allows one
# backup at a time. Kept below 2**31 so pg_locks shows it as classid=0,
# objid=<key>, which is_backup_running() relies on.
ADVISORY_LOCK_KEY = 0x0F11A0B5

# A backup newer than this counts as current for the Security Audit. The
# schedule is daily, so this leaves two hours of slack for a slow dump.
CURRENT_BACKUP_MAX_AGE = timedelta(hours=26)

# Refuse to start when free space is below this, or below twice the last
# dump's size, whichever is larger — a half-written dump helps no one.
MIN_FREE_BYTES = 50 * 1024 * 1024

_STDERR_TAIL = 1500

# Held for the whole run, so a second request in this process fails fast
# without touching the database.
_process_lock = threading.Lock()


class BackupError(Exception):
    """A backup failed for a reason an admin can read and act on."""


class BackupAlreadyRunning(Exception):
    """Another backup holds the lock."""


# ============================================================================
# Settings
# ============================================================================


def _zone(name: str) -> tzinfo:
    # "UTC" works even where the OS has no tz database (Windows without the
    # tzdata package), which keeps the default safe everywhere.
    if name == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown time zone {name!r}") from exc


def validate_backup_settings(value: Any) -> dict[str, Any]:
    """Validate a ``database_backup`` setting; missing keys take defaults."""
    if not isinstance(value, dict):
        raise ValueError("must be an object with enabled, time, timezone and retention_days")
    unknown = set(value) - set(DEFAULT_SETTINGS)
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}")
    merged = {**DEFAULT_SETTINGS, **value}

    if not isinstance(merged["enabled"], bool):
        raise ValueError("enabled must be true or false")

    clock = merged["time"]
    match = re.fullmatch(r"(\d{2}):(\d{2})", clock) if isinstance(clock, str) else None
    if not match or int(match.group(1)) > 23 or int(match.group(2)) > 59:
        raise ValueError("time must be HH:MM in 24-hour form, e.g. 03:00")

    if not isinstance(merged["timezone"], str) or not merged["timezone"].strip():
        raise ValueError("timezone must be a time zone name such as UTC or America/Chicago")
    merged["timezone"] = merged["timezone"].strip()
    _zone(merged["timezone"])

    days = merged["retention_days"]
    # bool is an int subclass; True must not mean "keep 1 day".
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_RETENTION_DAYS:
        raise ValueError(f"retention_days must be a whole number from 1 to {MAX_RETENTION_DAYS}")
    return merged


def settings_problem(db: Session) -> Optional[str]:
    """Why the saved schedule cannot be used, or None if it can (or none is saved)."""
    row = db.get(SystemSetting, SETTING_KEY)
    if row is None:
        return None
    try:
        validate_backup_settings(row.value)
    except ValueError as exc:
        return str(exc)
    return None


def get_backup_settings(db: Session) -> dict[str, Any]:
    """The saved schedule, or the defaults when none is saved.

    A saved schedule that no longer validates (say, a time zone this server
    cannot resolve) falls back to the defaults for time, zone and retention,
    but keeps the saved on/off choice: an admin who turned backups off must
    not find them silently back on. ``get_status`` reports the problem.
    """
    row = db.get(SystemSetting, SETTING_KEY)
    if row is None:
        return dict(DEFAULT_SETTINGS)
    try:
        return validate_backup_settings(row.value)
    except ValueError as exc:
        saved = row.value if isinstance(row.value, dict) else {}
        enabled = saved.get("enabled")
        if not isinstance(enabled, bool):
            enabled = DEFAULT_SETTINGS["enabled"]
        logger.warning(
            "Invalid %s setting (%s); using default time and retention, enabled=%s",
            SETTING_KEY, exc, enabled,
        )
        return {**DEFAULT_SETTINGS, "enabled": enabled}


# ============================================================================
# Schedule
# ============================================================================


def _slot_on(day: date, cfg: dict[str, Any]) -> datetime:
    hour, minute = (int(part) for part in cfg["time"].split(":"))
    local = datetime.combine(day, time(hour, minute), tzinfo=_zone(cfg["timezone"]))
    return local.astimezone(timezone.utc)


def most_recent_slot(now: datetime, cfg: dict[str, Any]) -> datetime:
    """The latest scheduled time at or before ``now``, in UTC."""
    local_today = now.astimezone(_zone(cfg["timezone"])).date()
    slot = _slot_on(local_today, cfg)
    if slot > now:
        slot = _slot_on(local_today - timedelta(days=1), cfg)
    return slot


def next_slot(now: datetime, cfg: dict[str, Any]) -> datetime:
    """The first scheduled time after ``now``, in UTC."""
    local_day = most_recent_slot(now, cfg).astimezone(_zone(cfg["timezone"])).date()
    return _slot_on(local_day + timedelta(days=1), cfg)


def is_due(db: Session, now: datetime, cfg: dict[str, Any]) -> bool:
    """True when backups are on and no scheduled run has started since the last slot.

    A server that was down at the scheduled time catches up when it comes
    back; a failed run is not retried until the next slot, so a persistent
    fault does not hammer the database every minute.
    """
    if not cfg["enabled"]:
        return False
    slot = most_recent_slot(now, cfg)
    started = (
        db.query(BackupRun.id)
        .filter(BackupRun.trigger == "scheduled", BackupRun.started_at >= slot)
        .first()
    )
    return started is None


# ============================================================================
# Tools and connection
# ============================================================================


def backup_dir() -> Path:
    return resolve_backup_dir(settings.BACKUP_DIR)


# ============================================================================
# Is the backup folder somewhere that survives the container?
# ============================================================================

MOUNTINFO = Path("/proc/self/mountinfo")


def _in_container() -> bool:
    """Docker writes /.dockerenv and Podman /run/.containerenv in every container."""
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def _unescape_mount_path(field: str) -> str:
    # mountinfo writes space, tab, newline and backslash as \040-style octal.
    return re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), field)


def _mount_points() -> list[str]:
    """Mount points of this process, from /proc/self/mountinfo (field 5)."""
    try:
        lines = MOUNTINFO.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    points = []
    for line in lines:
        fields = line.split(" ")
        if len(fields) > 4:
            points.append(_unescape_mount_path(fields[4]))
    return points


def _mount_of(path: str, mounts: list[str]) -> Optional[str]:
    """The mount point ``path`` lives on: the longest mount that contains it."""
    best = None
    for mount in mounts:
        trimmed = mount.rstrip("/\\")
        inside = (
            mount == "/"
            or path == mount
            or path.startswith(trimmed + "/")
            or path.startswith(trimmed + "\\")
        )
        if inside and (best is None or len(mount) > len(best)):
            best = mount
    return best


def storage_problem(directory: Path) -> Optional[str]:
    """Why backups must not be written to ``directory``, or None if they may.

    In a container, a folder that is not on a mounted volume lives in the
    container's own writable layer and is deleted when the container is
    recreated, as every upgrade does. Backups kept there would look fine on
    the Backups page until the day they were needed, so FilaOps refuses to
    write them. Outside a container the folder is on the host's disk.
    """
    if not _in_container():
        return None
    mounts = _mount_points()
    if not mounts:
        return (
            f"FilaOps cannot tell whether the backup folder {directory} is on a "
            "volume (no mount information), so it will not back up there."
        )
    # realpath: a symlinked folder is judged by where it really lives.
    mount = _mount_of(os.path.realpath(directory), mounts)
    if mount is None or mount == "/":
        return (
            f"The backup folder {directory} is not on a mounted volume, so backups "
            "would be deleted whenever the container is recreated (every upgrade "
            "does this). Backups will not run until a volume is mounted there: "
            "docker-compose.yml mounts the filaops_backups volume at /app/backups; "
            "add it to your compose file and restart the backend."
        )
    return None


def find_pg_dump() -> Optional[str]:
    configured = settings.BACKUP_PG_DUMP_PATH or "pg_dump"
    found = shutil.which(configured)
    if found:
        return found
    return configured if Path(configured).is_file() else None


def parse_major(version: Optional[str]) -> Optional[int]:
    """Major version from ``pg_dump (PostgreSQL) 16.4 (Debian ...)``."""
    if not version:
        return None
    match = re.search(r"PostgreSQL\)?\s+(\d+)", version)
    return int(match.group(1)) if match else None


def pg_dump_version(path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def server_version(db: Session) -> tuple[int, str]:
    """(major, full version string) of the connected server."""
    num = int(db.execute(text("SHOW server_version_num")).scalar())
    full = str(db.execute(text("SHOW server_version")).scalar())
    return num // 10000, full


def count_public_tables(db: Session) -> int:
    """Ordinary tables in the public schema — each gets a COPY section in a dump."""
    return int(db.execute(text(
        "SELECT count(*) FROM pg_class c "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "WHERE n.nspname = 'public' AND c.relkind = 'r'"
    )).scalar())


def _connection() -> dict[str, Any]:
    url = make_url(settings.database_url)
    return {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "user": url.username or "",
        "password": url.password or "",
        "dbname": url.database or "",
        "sslmode": url.query.get("sslmode"),
    }


def _pg_env(conn: dict[str, Any]) -> dict[str, str]:
    # Only what pg_dump needs: the app's environment holds SECRET_KEY, SMTP
    # and license credentials that have no business in a child process.
    env = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "HOME", "LANG", "LC_ALL", "TZ")
        if key in os.environ
    }
    env["PGPASSWORD"] = conn["password"]
    env["PGCONNECT_TIMEOUT"] = "15"
    env["PGAPPNAME"] = "filaops-backup"
    if conn["sslmode"]:
        env["PGSSLMODE"] = str(conn["sslmode"])
    return env


def _scrub(message: str) -> str:
    password = _connection()["password"]
    if password:
        message = message.replace(password, "***")
    return message


# ============================================================================
# Dump and verify
# ============================================================================


def verify_dump(path: Path) -> int:
    """Read a gzip'd plain-SQL dump to the end; return its COPY section count.

    Raises BackupError when the file is damaged or the dump was cut short.
    Lines inside a COPY block are table data, so they are skipped: a row
    that happens to start with "COPY public." must not count as a table.
    """
    sections = 0
    complete = False
    in_copy = False
    try:
        with gzip.open(path, "rb") as dump:
            for line in dump:
                if in_copy:
                    if line.rstrip(b"\r\n") == COPY_END:
                        in_copy = False
                    continue
                if line.startswith(COPY_PREFIX):
                    sections += 1
                    in_copy = True
                elif line.startswith(DUMP_COMPLETE_MARKER):
                    complete = True
    except (OSError, EOFError, zlib.error) as exc:
        raise BackupError(f"The backup file is damaged and cannot be read back ({exc}).") from exc
    if not complete:
        raise BackupError(
            "The dump is incomplete: it does not end with pg_dump's "
            "'dump complete' marker."
        )
    return sections


def _dump_to(partial: Path, pg_dump: str, conn: dict[str, Any], timeout: int) -> None:
    """Stream pg_dump's output through gzip into ``partial`` (created 0600)."""
    args = [
        pg_dump, "--no-owner", "--no-privileges",
        "--host", conn["host"], "--port", str(conn["port"]),
        "--username", conn["user"], "--dbname", conn["dbname"],
    ]
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(partial, flags, 0o600)
    timed_out = threading.Event()

    with tempfile.TemporaryFile() as stderr, os.fdopen(fd, "wb") as raw:
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=stderr, env=_pg_env(conn),
        )

        def _kill() -> None:
            timed_out.set()
            proc.kill()

        watchdog = threading.Timer(timeout, _kill)
        watchdog.daemon = True
        watchdog.start()
        try:
            assert proc.stdout is not None
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=6) as gz:
                for chunk in iter(lambda: proc.stdout.read(1 << 20), b""):
                    gz.write(chunk)
            returncode = proc.wait()
        finally:
            watchdog.cancel()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        raw.flush()
        os.fsync(raw.fileno())

        if timed_out.is_set():
            raise BackupError(f"pg_dump took longer than {timeout} seconds and was stopped.")
        if returncode != 0:
            stderr.seek(0)
            detail = stderr.read().decode("utf-8", "replace").strip()[-_STDERR_TAIL:]
            raise BackupError(_scrub(f"pg_dump failed (exit code {returncode}): {detail}"))


def _prepare_dir(directory: Path) -> None:
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"Cannot create the backup folder {directory}: {exc.strerror or exc}") from exc
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass  # Not our directory (e.g. a mounted share); the write check below decides.
    if not os.access(directory, os.W_OK):
        raise BackupError(f"The backup folder {directory} is not writable by the FilaOps service.")


def _check_free_space(db: Session, directory: Path) -> None:
    last = (
        db.query(BackupRun.size_bytes)
        .filter(BackupRun.status == "ok", BackupRun.size_bytes.isnot(None))
        .order_by(BackupRun.started_at.desc())
        .first()
    )
    needed = max(MIN_FREE_BYTES, 2 * (last[0] if last else 0))
    free = shutil.disk_usage(directory).free
    if free < needed:
        raise BackupError(
            f"Not enough free disk space for a backup: {free // (1024 * 1024)} MB free, "
            f"{needed // (1024 * 1024)} MB needed."
        )


def _free_name(directory: Path, now: datetime) -> str:
    stem = f"filaops-{now:%Y%m%d-%H%M%S}"
    for n in range(1, 1000):
        name = f"{stem}.sql.gz" if n == 1 else f"{stem}-{n}.sql.gz"
        if not (directory / name).exists() and not (directory / (name + PARTIAL_SUFFIX)).exists():
            return name
    raise BackupError("Too many backups started in the same second.")


def _perform(db: Session, run: BackupRun, now: datetime) -> None:
    directory = backup_dir()
    problem = storage_problem(directory)
    if problem:
        raise BackupError(problem)
    _prepare_dir(directory)

    pg_dump = find_pg_dump()
    if pg_dump is None:
        raise BackupError(
            "pg_dump was not found. The FilaOps Docker image includes it; for other "
            "installs, install the PostgreSQL client tools that match your server "
            "version, or set BACKUP_PG_DUMP_PATH."
        )
    client = pg_dump_version(pg_dump)
    client_major = parse_major(client)
    server_major, server_full = server_version(db)
    run.pg_dump_version = (client or "unknown")[:100]
    run.server_version = server_full[:100]
    db.commit()
    if client_major != server_major:
        raise BackupError(
            f"pg_dump is version {client_major or 'unknown'} but the database server is "
            f"version {server_major}. They must match, or the backup may not restore. "
            f"Install the PostgreSQL {server_major} client tools."
        )

    _check_free_space(db, directory)
    run.expected_tables = count_public_tables(db)
    db.commit()

    filename = _free_name(directory, now)
    final = directory / filename
    partial = directory / (filename + PARTIAL_SUFFIX)
    try:
        _dump_to(partial, pg_dump, _connection(), settings.BACKUP_TIMEOUT_SECONDS)
        sections = verify_dump(partial)
        if sections < run.expected_tables:
            raise BackupError(
                f"The dump has {sections} tables but the database has "
                f"{run.expected_tables}; it is not a complete backup."
            )
        # Record the name first: if the process dies after the rename, the
        # reaped row still points at the file, so retention can remove it.
        run.filename = filename
        db.commit()
        os.replace(partial, final)
    finally:
        partial.unlink(missing_ok=True)

    run.size_bytes = final.stat().st_size
    run.table_count = sections
    run.status = "ok"


# ============================================================================
# Retention
# ============================================================================


def prune_backups(db: Session, cfg: dict[str, Any], now: datetime) -> list[str]:
    """Delete backup files older than the retention period; return their names.

    The newest successful backup is never deleted, however old: if backups
    start failing, the last good copy must survive until a new one replaces
    it. Only files FilaOps recorded are touched — anything else an admin put
    in the folder is left alone. Leftover ``.partial`` files from a crash are
    removed once they are a day old, as are files of runs that did not finish
    as OK (for example, interrupted right after the dump was renamed).
    """
    directory = backup_dir()
    newest_ok = (
        db.query(BackupRun.id)
        .filter(BackupRun.status == "ok", BackupRun.file_deleted_at.is_(None))
        .order_by(BackupRun.started_at.desc())
        .first()
    )
    cutoff = now - timedelta(days=cfg["retention_days"])
    expired = (
        db.query(BackupRun)
        .filter(
            BackupRun.status.in_(("ok", "failed")),
            BackupRun.file_deleted_at.is_(None),
            BackupRun.filename.isnot(None),
            BackupRun.started_at < cutoff,
        )
        .all()
    )
    removed = []
    for run in expired:
        if newest_ok and run.id == newest_ok[0]:
            continue
        if FILENAME_RE.match(run.filename or ""):
            (directory / run.filename).unlink(missing_ok=True)
            removed.append(run.filename)
        run.file_deleted_at = now
    db.commit()

    stale = (now - timedelta(days=1)).timestamp()
    for leftover in directory.glob(f"filaops-*.sql.gz{PARTIAL_SUFFIX}"):
        try:
            if leftover.stat().st_mtime < stale:
                leftover.unlink()
        except OSError:
            pass
    return removed


# ============================================================================
# Running a backup
# ============================================================================


def _try_lock() -> Optional[Connection]:
    """Take the backup lock on a dedicated connection, or return None if held.

    The lock is session-level, so it belongs to one database connection. A
    Session returns its connection to the pool on every commit, and the unlock
    could then run on a different connection and leave the lock held forever,
    so the lock lives on a Connection kept for the whole run.
    """
    from app.db.session import engine

    conn = engine.connect()
    try:
        got = conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
        ).scalar()
        conn.commit()  # end the transaction; the session-level lock stays
    except Exception:
        conn.close()
        raise
    if not got:
        conn.close()
        return None
    return conn


def _unlock(conn: Connection) -> None:
    try:
        conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": ADVISORY_LOCK_KEY})
        conn.commit()
    except Exception:  # noqa: BLE001
        # Discard the connection rather than pool it: the lock dies with it.
        logger.warning("Could not release the backup lock cleanly", exc_info=True)
        conn.invalidate()
    finally:
        conn.close()


def _lock_held(db: Session) -> bool:
    return bool(db.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' "
            "AND classid = 0 AND objid = :key AND objsubid = 1 AND granted)"
        ),
        {"key": ADVISORY_LOCK_KEY},
    ).scalar())


def check_running(db: Session) -> bool:
    """True if a backup is running in any backend process.

    Read-only in the common case, so the status page (polled every few
    seconds) never blocks "Run backup now". Only when 'running' rows exist
    with nobody holding the lock (left by a crash) does it take the lock
    briefly to mark them failed, so a backup cannot start mid-cleanup.
    """
    if _process_lock.locked() or _lock_held(db):
        return True
    has_stale = db.query(BackupRun.id).filter(BackupRun.status == "running").first()
    if has_stale is None:
        return False
    if not _process_lock.acquire(blocking=False):
        return True
    try:
        conn = _try_lock()
        if conn is None:
            return True
        try:
            _fail_interrupted(db)
        finally:
            _unlock(conn)
        return False
    finally:
        _process_lock.release()


def _fail_interrupted(db: Session, exclude_id: Optional[int] = None) -> None:
    """Mark 'running' rows failed. Call only while nothing holds the lock."""
    query = db.query(BackupRun).filter(BackupRun.status == "running")
    if exclude_id is not None:
        query = query.filter(BackupRun.id != exclude_id)
    query.update(
        {
            BackupRun.status: "failed",
            BackupRun.finished_at: datetime.now(timezone.utc),
            BackupRun.error: "Interrupted: FilaOps stopped while this backup was running.",
        },
        synchronize_session=False,
    )
    db.commit()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def start_backup(
    trigger: str,
    triggered_by_id: Optional[int] = None,
    *,
    wait: bool = False,
    now: Optional[Callable[[], datetime]] = None,
) -> Optional[int]:
    """Start a backup and return its run id.

    Takes the locks and records the run before returning, so the caller gets
    a definite answer: a run id, ``BackupAlreadyRunning``, or — for a
    scheduled trigger that another process already handled — ``None``. The
    dump itself runs on a background thread unless ``wait`` is true.
    """
    from app.db.session import SessionLocal

    if trigger not in ("scheduled", "manual"):
        raise ValueError(f"unknown trigger {trigger!r}")
    clock = now or _utcnow

    if not _process_lock.acquire(blocking=False):
        raise BackupAlreadyRunning()
    handed_off = False
    lock_conn: Optional[Connection] = None
    db: Optional[Session] = None
    try:
        lock_conn = _try_lock()
        if lock_conn is None:
            raise BackupAlreadyRunning()

        db = SessionLocal()
        cfg = get_backup_settings(db)
        if trigger == "scheduled" and not is_due(db, clock(), cfg):
            return None

        # started_at from the same clock is_due() compares against, not the
        # database's now(): a DB clock behind the app's would make the slot
        # look unclaimed and run the scheduled backup twice.
        run = BackupRun(
            status="running", trigger=trigger, triggered_by_id=triggered_by_id,
            started_at=clock(),
        )
        db.add(run)
        db.commit()
        run_id = run.id
        # We hold the lock, so any other 'running' row is left over from a crash.
        _fail_interrupted(db, exclude_id=run_id)

        def _work() -> None:
            try:
                _execute(db, run, cfg, clock)
            finally:
                _release(lock_conn, db)

        if wait:
            handed_off = True
            _work()
        else:
            threading.Thread(target=_work, name=f"backup-{run_id}", daemon=True).start()
            handed_off = True
        return run_id
    finally:
        if not handed_off:
            _release(lock_conn, db)


def _execute(db: Session, run: BackupRun, cfg: dict[str, Any], clock: Callable[[], datetime]) -> None:
    run_id = run.id
    started = clock()
    try:
        _perform(db, run, started)
    except BackupError as exc:
        db.rollback()
        run.status = "failed"
        run.error = str(exc)
    except Exception as exc:  # noqa: BLE001 — recorded for the admin, logged in full
        logger.exception("Backup %s failed unexpectedly", run.id)
        db.rollback()
        run.status = "failed"
        run.error = _scrub(f"Unexpected error: {type(exc).__name__}: {exc}")[:2000]
    outcome = {
        "status": run.status,
        "error": run.error,
        "filename": run.filename,
        "size_bytes": run.size_bytes,
        "table_count": run.table_count,
        "finished_at": clock(),
    }
    try:
        run.finished_at = outcome["finished_at"]
        db.commit()
    except Exception:  # noqa: BLE001 - retry once on a fresh connection
        logger.exception("Could not record backup %s; retrying", run_id)
        db.rollback()
        from app.db.session import SessionLocal

        with SessionLocal() as retry:
            retry.query(BackupRun).filter(BackupRun.id == run_id).update(outcome)
            retry.commit()
        db.expire_all()
    logger.info(
        "Database backup %s finished: %s", run_id, outcome["status"],
        extra={"backup_run_id": run_id, "backup_status": outcome["status"]},
    )
    try:
        removed = prune_backups(db, cfg, clock())
        if removed:
            logger.info("Removed %d expired backup(s)", len(removed))
    except Exception:  # noqa: BLE001 — retention must never fail the backup
        logger.exception("Backup retention cleanup failed")
        db.rollback()


def _release(lock_conn: Optional[Connection], db: Optional[Session]) -> None:
    try:
        if lock_conn is not None:
            _unlock(lock_conn)
    finally:
        if db is not None:
            db.close()
        _process_lock.release()


# ============================================================================
# Status and health
# ============================================================================


def run_to_dict(run: Optional[BackupRun]) -> Optional[dict[str, Any]]:
    if run is None:
        return None
    return {
        "id": run.id,
        "status": run.status,
        "trigger": run.trigger,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "filename": run.filename,
        "size_bytes": run.size_bytes,
        "table_count": run.table_count,
        "expected_tables": run.expected_tables,
        "pg_dump_version": run.pg_dump_version,
        "server_version": run.server_version,
        "error": run.error,
        "downloadable": bool(
            run.status == "ok" and run.filename and run.file_deleted_at is None
        ),
    }


def _latest(db: Session, *conditions) -> Optional[BackupRun]:
    return db.query(BackupRun).filter(*conditions).order_by(BackupRun.started_at.desc()).first()


def _writable(directory: Path) -> bool:
    """Whether the backup folder is, or could be created, writable."""
    probe = directory
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return os.access(probe, os.W_OK)


def get_status(db: Session, now: Optional[datetime] = None) -> dict[str, Any]:
    """Everything the Backups page shows above the run list."""
    now = now or _utcnow()
    cfg = get_backup_settings(db)
    running = check_running(db)

    pg_dump = find_pg_dump()
    client = pg_dump_version(pg_dump) if pg_dump else None
    client_major = parse_major(client)
    server_major, server_full = server_version(db)
    if pg_dump is None:
        problem = "pg_dump was not found on this server."
    elif client_major != server_major:
        problem = (
            f"pg_dump is version {client_major or 'unknown'} but the database is "
            f"version {server_major}; backups will fail until they match."
        )
    else:
        problem = None

    directory = backup_dir()
    files = sorted(directory.glob("filaops-*.sql.gz")) if directory.is_dir() else []
    try:
        probe = directory
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
        free = shutil.disk_usage(probe).free
    except OSError:
        free = None

    return {
        "settings": cfg,
        "settings_problem": settings_problem(db),
        "scheduler_enabled": settings.BACKUP_SCHEDULER_ENABLED,
        "next_run_at": (
            next_slot(now, cfg).isoformat()
            if cfg["enabled"] and settings.BACKUP_SCHEDULER_ENABLED else None
        ),
        "running": running,
        "last_run": run_to_dict(_latest(db)),
        "last_success": run_to_dict(_latest(db, BackupRun.status == "ok")),
        "tools": {
            "pg_dump_path": pg_dump,
            "pg_dump_version": client,
            "server_version": server_full,
            "versions_match": problem is None,
            "problem": problem,
        },
        "storage": {
            "path": str(directory),
            "problem": storage_problem(directory),
            "writable": _writable(directory),
            "free_bytes": free,
            "file_count": len(files),
            "total_bytes": sum(f.stat().st_size for f in files),
        },
    }


def backup_health(db: Session, now: Optional[datetime] = None) -> tuple[bool, str]:
    """(is_healthy, message) for the Security Audit's backup_configured check."""
    now = now or _utcnow()
    cfg = get_backup_settings(db)
    problem = storage_problem(backup_dir())
    if problem:
        return False, problem
    last = _latest(db, BackupRun.status != "running")
    last_ok = _latest(db, BackupRun.status == "ok")

    if last is not None and last.status == "failed":
        return False, f"The last backup failed: {(last.error or 'no details')[:200]}"
    if last_ok is not None and last_ok.finished_at is not None:
        finished = last_ok.finished_at
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=timezone.utc)
        age = now - finished
        if age <= CURRENT_BACKUP_MAX_AGE:
            if not cfg["enabled"] or not settings.BACKUP_SCHEDULER_ENABLED:
                return False, (
                    "A backup ran recently, but scheduled backups are turned off, "
                    "so none will run tomorrow."
                )
            hours = int(age.total_seconds() // 3600)
            when = (
                "less than an hour ago" if hours == 0
                else f"{hours} hour{'s' if hours != 1 else ''} ago"
            )
            return True, (
                f"Last backup succeeded {when} "
                f"({last_ok.table_count} tables); daily at {cfg['time']} {cfg['timezone']}, "
                f"kept {cfg['retention_days']} days."
            )
        return False, f"The last successful backup is {age.days} day(s) old."
    if not cfg["enabled"] or not settings.BACKUP_SCHEDULER_ENABLED:
        return False, "Scheduled backups are turned off and no backup has run."
    return False, "Backups are scheduled, but none has completed yet."
