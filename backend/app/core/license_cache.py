"""License cache — filesystem-persisted license state for Core.

PR-03 extends the PR-02 activation cache with the four fields
``filaops_pro``'s reader requires: ``status``, ``last_verified_at``,
``last_server_timestamp``, and ``grace_until``. PRO's heartbeat scheduler
keeps them fresh; Core writes initial values on activation so a fresh
install can be consumed by PRO without waiting for the first heartbeat.

Why filesystem instead of DB:
- Core must function before any PRO migration runs — license activation can
  happen on a fresh install where DB is healthy but PRO tables don't exist
  yet, so license state cannot live in a PRO-owned table.
- License state needs to outlive container restarts. A host-side volume
  mount (``/var/lib/filaops/config/``) is cleaner than a DB row that PRO
  would have to reach for on every request.
- PRO's heartbeat scheduler reads/writes the same file. By making the cache
  filesystem-based with a known JSON shape, Core and PRO share the contract
  without sharing a Python module — preserving the Sacred Rule that Core
  must not import from ``filaops_pro``.

The on-disk JSON shape is the contract. Both Core (this module) and PRO
(``filaops_pro/licensing/cache.py``) bind to it independently — adding a
field requires coordinated writers on both sides, but readers must accept
extra unknown fields silently for forward-compatibility.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("app.core.license_cache")

# Default location matches v3 plan. Override via ``LICENSE_CONFIG_DIR`` env
# var in environments where ``/var/lib`` isn't writable (e.g. Windows dev,
# alternate Docker volume mounts, pytest tmpdir).
_DEFAULT_CONFIG_DIR = "/var/lib/filaops/config"

LICENSE_CACHE_FILENAME = "license.json"
INSTALL_UUID_FILENAME = "install_uuid"

# Vendor-outage grace window. MUST stay in sync with
# ``filaops_pro.licensing.cache.GRACE_DAYS`` — the two writers compute the
# same anchor (last_verified_at + GRACE_DAYS days) so neither side can
# accidentally widen or narrow the grace window without the other agreeing.
GRACE_DAYS = 14

# Sentinel for ``last_server_timestamp`` when no signed heartbeat has been
# observed yet. PRO's verifier treats this field as a strict anti-rollback
# floor (``response_ts <= cached_ts`` rejects), so any real heartbeat
# timestamp will be strictly greater than epoch zero. A fresh activation
# whose ``server_timestamp`` is missing from the validate response (older
# license-server versions) therefore never blocks the legitimate first
# heartbeat that follows.
EPOCH_ZERO_ISO = "1970-01-01T00:00:00+00:00"


@dataclass
class LicenseCache:
    """On-disk license state shared with ``filaops_pro``'s reader.

    The four PR-03 fields (``status``, ``last_verified_at``,
    ``last_server_timestamp``, ``grace_until``) have defaults so an older
    PR-02 cache file still loads — ``from_dict`` derives sane values from
    ``activated_at`` and the epoch sentinel rather than crashing on a
    missing key. New activations always write the full ten-field shape.
    """

    license_key: str
    install_uuid: str
    tier: str  # community | professional | enterprise
    features: list[str]
    activated_at: str  # ISO 8601 UTC, set on successful activation
    expires_at: Optional[str] = None  # ISO 8601 UTC; None for perpetual licenses
    # PR-03 fields — populated on activation, refreshed by PRO's heartbeat.
    status: str = "active"  # active | grace_period | expired | cancelled
    last_verified_at: str = ""  # ISO 8601 UTC; grace-math anchor (local clock)
    last_server_timestamp: str = EPOCH_ZERO_ISO  # ISO 8601 UTC; anti-rollback floor
    grace_until: str = ""  # ISO 8601 UTC; last_verified_at + GRACE_DAYS days

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LicenseCache":
        """Construct a LicenseCache from JSON, deriving defaults for legacy files.

        Pre-PR-03 cache files lack ``status``, ``last_verified_at``,
        ``last_server_timestamp``, and ``grace_until``. For those fields,
        defaults are anchored at the **current** time, not at
        ``activated_at``. A Core that's been installed for weeks may
        otherwise emerge from an in-place PR-03 upgrade with a
        ``grace_until`` already in the past — PRO's ``evaluate_license``
        would then see an expired grace window the instant the upgrade
        runs (the exact failure mode the upgrade is meant to fix). The
        first PRO heartbeat (~6 hours after boot) overwrites both fields
        with server-signed values, so the upgrade-time anchor is in
        effect for at most one heartbeat interval.

        The on-disk file is unchanged — callers that want to persist
        the upgraded shape must call ``save_license_cache`` on the
        returned object.
        """
        activated_at = data["activated_at"]
        # For legacy files, anchor the upgrade window at "now" rather
        # than at activated_at (see class docstring).
        upgrade_anchor_iso = utc_now_iso()
        last_verified_at = data.get("last_verified_at") or upgrade_anchor_iso
        grace_until = data.get("grace_until") or _compute_grace_until(last_verified_at)
        return cls(
            license_key=data["license_key"],
            install_uuid=data["install_uuid"],
            tier=data["tier"],
            features=list(data.get("features", [])),
            activated_at=activated_at,
            expires_at=data.get("expires_at"),
            status=data.get("status") or "active",
            last_verified_at=last_verified_at,
            last_server_timestamp=data.get("last_server_timestamp") or EPOCH_ZERO_ISO,
            grace_until=grace_until,
        )


def _compute_grace_until(anchor_iso: str) -> str:
    """Return ``anchor + GRACE_DAYS days`` as an ISO 8601 string.

    On malformed input, returns ``EPOCH_ZERO_ISO`` so PRO's
    ``evaluate_license`` treats the cache as already past its grace
    window (``now < grace_until`` is False → deny with
    ``grace_period_expired``). Failing closed on a parse error is
    deliberate: granting a fresh ``GRACE_DAYS`` window on garbage input
    would silently extend access during corruption or tampering. The
    operator sees a clean denial rather than a covertly-renewed grace.
    """
    try:
        anchor = datetime.fromisoformat(anchor_iso)
    except ValueError:
        return EPOCH_ZERO_ISO
    return (anchor + timedelta(days=GRACE_DAYS)).isoformat()


def is_pr02_shape(raw: dict) -> bool:
    """Return True if ``raw`` is missing any PR-03 field.

    Used by the /info endpoint to detect a pre-PR-03 file on disk and
    trigger a one-shot re-save in the PR-03 shape. The check is intentionally
    permissive — if any of the four new keys is absent, the file predates
    PR-03 and should be upgraded.
    """
    return not all(
        k in raw
        for k in ("status", "last_verified_at", "last_server_timestamp", "grace_until")
    )


def get_config_dir() -> Path:
    """Return the directory holding ``license.json`` + ``install_uuid``.

    Sourced from ``settings.LICENSE_CONFIG_DIR`` so configuration stays
    centralized in the Settings model.
    """
    return Path(settings.LICENSE_CONFIG_DIR)


def ensure_config_dir() -> Path:
    """Create the config directory if missing. Returns the path."""
    cfg_dir = get_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


_AWAIT_UUID_TIMEOUT_SECONDS = 5.0
_AWAIT_UUID_POLL_SECONDS = 0.01


def _await_uuid_content(
    path: Path,
    timeout_seconds: float = _AWAIT_UUID_TIMEOUT_SECONDS,
    poll_seconds: float = _AWAIT_UUID_POLL_SECONDS,
) -> Optional[str]:
    """Poll ``path`` for non-empty stripped content within a timeout.

    Closes two race windows that a single read cannot:

    1. Read-after-create. Between a winner's ``os.open(O_EXCL)`` succeeding
       and its ``os.write`` completing, the file exists at size 0. A loser
       that observes ``FileExistsError`` and reads immediately can see "".
    2. In-flight cold-start observed via the fast path. A second caller
       that opens the function while the first is still inside its
       open/write window would see an existing-but-empty file and
       (pre-fix) interpret that as corruption.

    Returns the trimmed UUID as soon as it becomes non-empty, or ``None``
    on timeout. ``FileNotFoundError`` is treated as "still pending" and
    polling continues — defensive only; the current implementation never
    unlinks while another caller could be reading.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            value = ""
        if value:
            return value
        time.sleep(poll_seconds)
    return None


def get_install_uuid() -> str:
    """Return this installation's stable UUID, generating + persisting on first call.

    This UUID is the secret used by PRO for token encryption (PR-05). Once
    written it must never change — under encryption-at-rest, two callers
    that each derive a Fernet key from a different UUID would persist
    ciphertext that the survivor cannot decrypt.

    Concurrency model:
        * Cold start (file absent): the file is created with
          ``O_CREAT | O_EXCL``. Exactly one caller's create succeeds; any
          loser catches ``FileExistsError`` and waits via
          ``_await_uuid_content`` for the winner's write to be visible.
        * In-flight observation (file exists at size 0 because a winner
          is between open and write): callers wait for content rather
          than treating size 0 as corruption. Treating it as corruption
          and "recovering" can clobber the winner's just-created file.

    Empty-file corruption:
        If the file is observably empty after polling, this is treated
        as a fatal state and ``RuntimeError`` is raised. Silently
        regenerating an empty UUID would invalidate the key any existing
        encrypted-at-rest data was sealed with — exactly the data-loss
        outcome this function exists to prevent. An operator must
        restore from backup or remove the file and restart.
    """
    cfg_dir = ensure_config_dir()
    uuid_file = cfg_dir / INSTALL_UUID_FILENAME

    if uuid_file.exists():
        settled = _await_uuid_content(uuid_file)
        if settled:
            return settled
        raise RuntimeError(
            f"install_uuid file at {uuid_file} is empty after polling for "
            f"{_AWAIT_UUID_TIMEOUT_SECONDS}s. Refusing to regenerate — "
            "doing so would invalidate any encrypted-at-rest data sealed "
            "with the original key. Restore from backup or remove the "
            "file manually before restart."
        )

    new_uuid = str(uuid.uuid4())
    try:
        fd = os.open(
            str(uuid_file),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            os.write(fd, new_uuid.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        logger.info("Generated new install_uuid for this instance")
        return new_uuid
    except FileExistsError:
        settled = _await_uuid_content(uuid_file)
        if settled:
            return settled
        raise RuntimeError(
            f"install_uuid race timeout: lost the create race at "
            f"{uuid_file} but no content became visible within "
            f"{_AWAIT_UUID_TIMEOUT_SECONDS}s. The winning caller may "
            "have crashed mid-write."
        )


def get_license_path() -> Path:
    """Path to the license cache JSON file."""
    return ensure_config_dir() / LICENSE_CACHE_FILENAME


def load_license_cache() -> Optional[LicenseCache]:
    """Read the persisted LicenseCache. Returns None if missing or unreadable."""
    cache, _ = load_license_cache_with_raw()
    return cache


def load_license_cache_with_raw() -> tuple[Optional[LicenseCache], Optional[dict]]:
    """Read the cache and return ``(cache, raw_dict)`` so callers that need
    the on-disk shape (e.g. ``is_pr02_shape`` upgrade detection) can inspect
    it without re-reading the file. Returns ``(None, None)`` if the file
    is missing or unreadable.
    """
    path = get_license_path()
    if not path.exists():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LicenseCache.from_dict(data), data
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        # An unreadable file is treated like "no license" — safer than
        # crashing on a malformed cache.
        logger.warning("license.json present but unreadable: %s", exc)
        return None, None


def save_license_cache(cache: LicenseCache) -> None:
    """Atomically persist the LicenseCache to disk."""
    path = get_license_path()
    _atomic_write_text(path, json.dumps(cache.to_dict(), indent=2, sort_keys=True))
    logger.info(
        "Persisted license cache: tier=%s, features=%d, expires_at=%s",
        cache.tier,
        len(cache.features),
        cache.expires_at or "perpetual",
    )


def clear_license_cache() -> bool:
    """Remove the license.json file. Returns True if a file was removed."""
    path = get_license_path()
    if path.exists():
        path.unlink()
        logger.info("Removed license cache at %s", path)
        return True
    return False


def utc_now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, content: str) -> None:
    """Write text to ``path`` atomically (temp file + rename).

    Prevents partial-write corruption if the process is killed mid-write.
    The temp file lives in the same directory so ``os.replace`` is a true
    atomic rename rather than a copy across filesystems.
    """
    cfg_dir = path.parent
    cfg_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(cfg_dir), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        # Cleanup the half-written tmp file on any failure.
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
