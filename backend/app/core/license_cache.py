"""License cache — filesystem-persisted license state for Core.

PR-02 scope: bootstrap activation. PR-03 extends with heartbeat scheduler +
grace window + anti-rollback fields (server_timestamp, nonce_history,
last_verified_at).

Why filesystem instead of DB:
- Core must function before any PRO migration runs — license activation can
  happen on a fresh install where DB is healthy but PRO tables don't exist
  yet, so license state cannot live in a PRO-owned table.
- License state needs to outlive container restarts. A host-side volume
  mount (``/var/lib/filaops/config/``) is cleaner than a DB row that PRO
  would have to reach for on every request.
- PRO's heartbeat scheduler (PR-03) reads/writes the same file. By making
  the cache filesystem-based with a known JSON shape, Core and PRO share
  the contract without sharing a Python module — preserving the Sacred
  Rule that Core must not import from ``filaops_pro``.

The LicenseCache shape is documented in ``PRO_LAUNCH_PIVOT_v3.md``; this
module implements the activation-time subset only. PR-03 will extend the
dataclass and the JSON shape; readers must tolerate unknown fields.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
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


@dataclass
class LicenseCache:
    """Activation-time subset of the LicenseCache shape.

    Fields added by PR-03 (status, last_verified_at, last_server_timestamp,
    grace_until, nonce_history) are NOT declared here yet — but
    ``from_dict`` tolerates extra keys so a forward-compatible PR-03 cache
    can still be read by this PR-02 reader.
    """

    license_key: str
    install_uuid: str
    tier: str  # community | professional | enterprise
    features: list[str]
    activated_at: str  # ISO 8601 UTC, set on successful activation
    expires_at: Optional[str] = None  # ISO 8601 UTC; None for perpetual licenses

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LicenseCache":
        """Construct a LicenseCache from JSON, dropping fields we don't know."""
        return cls(
            license_key=data["license_key"],
            install_uuid=data["install_uuid"],
            tier=data["tier"],
            features=list(data.get("features", [])),
            activated_at=data["activated_at"],
            expires_at=data.get("expires_at"),
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


def get_install_uuid() -> str:
    """Return this installation's stable UUID, generating + persisting on first call.

    This UUID is the secret used by PRO for token encryption (PR-05). Once
    written it must never change — under encryption-at-rest, two callers
    that each derive a Fernet key from a different UUID would persist
    ciphertext that the survivor cannot decrypt.

    Concurrency: the file is created with ``O_CREAT | O_EXCL`` so only one
    caller can win the create. Any concurrent first-caller that loses the
    race gets ``FileExistsError`` and reads back the winner's UUID. Empty
    files (corruption-by-truncation) are unlinked first so O_EXCL can
    recreate.
    """
    cfg_dir = ensure_config_dir()
    uuid_file = cfg_dir / INSTALL_UUID_FILENAME

    # Fast path: file already has content.
    try:
        existing = uuid_file.read_text(encoding="utf-8").strip()
        if existing:
            return existing
        # Empty file (corruption-by-truncation). Unlink so O_EXCL below can
        # recreate; the unlink itself is idempotent under concurrent callers
        # because missing_ok suppresses the lost-race FileNotFoundError.
        logger.warning("install_uuid file is empty, regenerating")
        uuid_file.unlink(missing_ok=True)
    except FileNotFoundError:
        pass

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
        # Lost the create race to a concurrent caller. The winner has
        # already written a UUID; read it back.
        return uuid_file.read_text(encoding="utf-8").strip()


def get_license_path() -> Path:
    """Path to the license cache JSON file."""
    return ensure_config_dir() / LICENSE_CACHE_FILENAME


def load_license_cache() -> Optional[LicenseCache]:
    """Read the persisted LicenseCache. Returns None if missing or unreadable."""
    path = get_license_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LicenseCache.from_dict(data)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        # An unreadable file is treated like "no license" — safer than
        # crashing on a malformed cache.
        logger.warning("license.json present but unreadable: %s", exc)
        return None


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
