"""
FilaOps Version Management System

Handles version detection, update checking, and GitHub release integration.
Uses git-based versioning for native PostgreSQL installation.

Version resolution order:
  1. Git tag (git describe --tags --abbrev=0) — works in dev and non-Docker prod
  2. FILAOPS_VERSION environment variable — only if explicitly set
     (e.g. docker-compose .env override, or the Tauri shell stamping
     `git describe` output at build time)
  3. VERSION file (backend/VERSION) — single source of truth, read at import time
  4. FALLBACK_VERSION sentinel ("0.0.0") — last resort, should never be reached

Install-method awareness:
  Core ships in multiple deployment shapes (Docker, Tauri desktop, future
  Linux .deb). The version string is the **product** version and is identical
  across them — `4.0.0` means the same code regardless of install method.
  What differs is how updates are delivered. Deployment artifacts opt in by
  setting `FILAOPS_INSTALL_METHOD` to one of:

      docker   — default; admin checks out the release tag on the host and
                 runs `docker compose up -d --build`
      tauri    — native desktop install; updates via the Tauri auto-updater
                 (the shell handles download/swap on next launch)
      manual   — bare-metal install; admin runs alembic/pip themselves

  Endpoints expose the install method so the SPA can render the appropriate
  upgrade UX (and so customer support can identify the deployment shape from
  a screenshot).

See docs/VERSIONING.md for the full versioning strategy.
"""

import subprocess
import requests
import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
import threading

logger = logging.getLogger(__name__)

# Published upgrade guide (docs/UPGRADE.md on the docs site). The update
# instructions endpoint and the admin update endpoint both point here.
UPGRADE_DOCS_URL = "https://blb3dprinting.github.io/filaops/UPGRADE/"


def _read_version_file() -> Optional[str]:
    """Read version from backend/VERSION file (single source of truth)."""
    version_file = Path(__file__).parent.parent.parent / "VERSION"
    try:
        raw_version = version_file.read_text().strip()
        return raw_version or None
    except (FileNotFoundError, OSError):
        return None


class VersionManager:
    """Manages FilaOps version information and update checking"""

    GITHUB_REPO = "BLB3DPrinting/filaops"
    FALLBACK_VERSION = _read_version_file() or "0.0.0"

    # Known deployment shapes. Anything outside this set still flows through
    # the endpoint but the frontend treats it as "docker" for UI purposes —
    # this set is the explicit allow-list for branching behaviour.
    KNOWN_INSTALL_METHODS = frozenset({"docker", "tauri", "manual"})
    DEFAULT_INSTALL_METHOD = "docker"

    @staticmethod
    def get_install_method() -> str:
        """Return how FilaOps was deployed (docker, tauri, manual).

        Reads the `FILAOPS_INSTALL_METHOD` env var which the deployment
        artifact sets. Falls back to "docker" because Docker Compose is the
        historical default — every Core release prior to this method existing
        was a Docker install, and that's still what most customers run.

        An unrecognised value isn't an error (we don't want to crash an
        otherwise-healthy install over a typo) but is normalised back to
        "docker" so downstream UI branches don't have to handle an unknown
        sentinel.
        """
        raw = os.getenv("FILAOPS_INSTALL_METHOD", "").strip().lower()
        if raw in VersionManager.KNOWN_INSTALL_METHODS:
            return raw
        return VersionManager.DEFAULT_INSTALL_METHOD

    # Server-side cache for GitHub API responses (to avoid rate limiting)
    _update_cache: Optional[Dict[str, Any]] = None
    _cache_expiry: Optional[datetime] = None
    _cache_lock = threading.Lock()

    @staticmethod
    def get_current_version() -> Dict[str, Any]:
        """
        Get comprehensive current version information

        Reads from git tags if available, falls back to FILAOPS_VERSION env var,
        then to hardcoded fallback.

        Returns:
            dict: Version info including version, build date, commit hash, etc.
        """
        # Priority 1: Git tag (for development and production)
        version = None
        try:
            version = subprocess.check_output(
                ['git', 'describe', '--tags', '--abbrev=0'],
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

        # Priority 2: Environment variable (fallback)
        if not version:
            version = os.getenv('FILAOPS_VERSION')

        # Priority 3: Fallback to hardcoded version
        if not version:
            version = VersionManager.FALLBACK_VERSION

        # Clean up git tag (remove 'v' prefix if present)
        if version and version.startswith('v'):
            version = version[1:]

        # Get commit hash (only works in dev mode with git)
        commit_hash = "unknown"
        try:
            commit_hash = subprocess.check_output(
                ['git', 'rev-parse', '--short', 'HEAD'],
                stderr=subprocess.DEVNULL,
                cwd=Path(__file__).parent.parent.parent.parent
            ).decode().strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            # In Docker, try to read from env var
            commit_hash = os.getenv('FILAOPS_COMMIT', 'unknown')

        install_method = VersionManager.get_install_method()
        return {
            "version": version,
            "build_date": os.getenv('FILAOPS_BUILD_DATE', datetime.now().isoformat()),
            "commit_hash": commit_hash,
            "database_version": "unknown",  # Will be set by endpoint with DB session
            "environment": os.getenv("ENVIRONMENT", "production"),
            "install_method": install_method,
            # Legacy field — kept so older clients reading `update_method`
            # don't break. New code should read `install_method` and look up
            # the actual update mechanism from get_update_instructions().
            "update_method": (
                "tauri-updater" if install_method == "tauri" else "docker-compose"
            ),
        }

    @staticmethod
    def get_database_version(db_session) -> str:
        """
        Get current database schema version from Alembic version table

        Args:
            db_session: SQLAlchemy database session

        Returns:
            str: Current migration revision (first 8 chars) or "unknown"
        """
        try:
            from sqlalchemy import text
            result = db_session.execute(text("SELECT version_num FROM alembic_version")).scalar()
            return result[:8] if result else "unknown"
        except Exception as e:
            logger.error(f"Failed to get database version: {e}")
            return "unknown"

    @staticmethod
    def check_for_updates() -> Dict[str, Any]:
        """
        Check GitHub releases for newer version with server-side caching

        Uses a 1-hour cache to avoid hitting GitHub API rate limits.
        Rate limits: 60 req/hour (unauthenticated), 5000 req/hour (authenticated)

        Returns:
            dict: Update information including availability, version, download URL
        """
        with VersionManager._cache_lock:
            # Return cached result if less than 1 hour old
            if (VersionManager._cache_expiry and
                datetime.now() < VersionManager._cache_expiry and
                VersionManager._update_cache):
                logger.debug("Returning cached update info")
                return {**VersionManager._update_cache, "cached": True}

            # Fetch fresh data from GitHub
            try:
                url = f"https://api.github.com/repos/{VersionManager.GITHUB_REPO}/releases/latest"

                # Add GitHub token if available (increases rate limit to 5000/hour)
                headers = {}
                github_token = os.getenv('GITHUB_TOKEN')
                if github_token:
                    headers['Authorization'] = f'token {github_token}'

                logger.info(f"Checking for updates from GitHub: {url}")
                response = requests.get(url, headers=headers, timeout=30)
                response.raise_for_status()

                latest_release = response.json()
                current_version = VersionManager.get_current_version()["version"]
                latest_version = latest_release["tag_name"]

                # Clean up version tags
                if latest_version.startswith('v'):
                    latest_version = latest_version[1:]
                if current_version.startswith('v'):
                    current_version = current_version[1:]

                # Compare versions using semantic versioning
                try:
                    import semver
                    # Parse versions (handle cases like "1.5.0" vs "1.5.0-beta")
                    current_ver = semver.VersionInfo.parse(current_version.split('-')[0])
                    latest_ver = semver.VersionInfo.parse(latest_version.split('-')[0])
                    update_available = latest_ver > current_ver
                except (ValueError, ImportError) as e:
                    # Fallback comparison if not valid semver or semver not installed
                    logger.warning(f"Semver comparison failed, using string comparison: {e}")
                    update_available = latest_version != current_version

                result = {
                    "update_available": update_available,
                    "current_version": current_version,
                    "latest_version": latest_version,
                    "release_notes": latest_release.get("body", ""),
                    "release_date": latest_release.get("published_at", ""),
                    "release_url": latest_release.get("html_url", ""),
                    "prerelease": latest_release.get("prerelease", False),
                    "upgrade_method": "docker-compose",
                    "estimated_downtime": "5-10 minutes",
                    "requires_manual_steps": True,  # Phase 1 - still manual
                    "cached": False
                }

                # Cache for 1 hour
                VersionManager._update_cache = result
                VersionManager._cache_expiry = datetime.now() + timedelta(hours=1)

                logger.info(f"Update check complete: update_available={update_available}, latest={latest_version}")
                return result

            except requests.RequestException as e:
                logger.error(f"Failed to check for updates (network error): {e}")

                # Return stale cached data if available
                if VersionManager._update_cache:
                    logger.warning("Returning stale cached update info due to network error")
                    return {**VersionManager._update_cache, "cache_stale": True, "error": f"Network error: {str(e)}"}

                # No cache available, return error
                return {
                    "error": f"Failed to check for updates: {str(e)}",
                    "update_available": False,
                    "current_version": VersionManager.get_current_version()["version"]
                }

            except Exception as e:
                logger.error(f"Unexpected error checking for updates: {e}", exc_info=True)

                # Return stale cached data if available
                if VersionManager._update_cache:
                    return {**VersionManager._update_cache, "cache_stale": True, "error": f"Unexpected error: {str(e)}"}

                return {
                    "error": f"Unexpected error: {str(e)}",
                    "update_available": False,
                    "current_version": VersionManager.get_current_version()["version"]
                }

    @staticmethod
    def get_update_instructions() -> Dict[str, Any]:
        """
        Get step-by-step update instructions for the current deployment shape.

        Branches on `FILAOPS_INSTALL_METHOD` so each deployment artifact gets
        the upgrade path that's actually correct for its environment. Telling
        a Tauri desktop user to run `docker-compose down` is worse than no
        instructions at all — they'd either hit "command not found" or hunt
        for the wrong product.

        All branches return the same shape so frontend code can stay generic;
        the differences are in `instructions`, `downtime`, and
        `requires_manual_steps`.
        """
        install_method = VersionManager.get_install_method()

        if install_method == "tauri":
            # The Tauri auto-updater handles download + integrity check +
            # swap-on-next-launch. From the user's perspective there are no
            # commands to run — the tray app's "Check for Updates" item does
            # everything. We surface zero manual steps and let the frontend
            # render an "Updates install automatically" message keyed off
            # `requires_manual_steps=False`.
            return {
                "method": "tauri-updater",
                "estimated_time": "Under 1 minute",
                "downtime": "Brief restart on next launch",
                "instructions": [
                    "Updates install automatically through the FilaOps app.",
                    "Open the tray icon and choose Check for Updates if you want to upgrade now.",
                    "FilaOps restarts itself once the update finishes downloading.",
                ],
                "backup_recommendation": (
                    "FilaOps backs up your database automatically before each update. "
                    "No manual action required."
                ),
                "documentation_url": UPGRADE_DOCS_URL,
                "rollback_steps": [
                    "Re-install the previous version from "
                    "https://github.com/BLB3DPrinting/filaops/releases — the Tauri installer "
                    "preserves your data directory across versions.",
                ],
                "requires_manual_steps": False,
            }

        if install_method == "manual":
            # Bare-metal install — no docker, no Tauri shell, just a Python
            # interpreter pointed at the repo. Mirrors the "Manual install"
            # steps in docs/UPGRADE.md. We don't know whether they're under
            # systemd, supervisord, or a plain shell, so the restart step
            # stays generic instead of prescribing one specific verb.
            return {
                "method": "manual",
                "estimated_time": "10-20 minutes",
                "downtime": "Service restart required",
                "instructions": [
                    "1. Read the upgrade guide (Full Documentation below). "
                    "From 4.1.x or older, make the 4.2.0 configuration changes first, "
                    "or the backend may not start.",
                    "2. Back up the database: pg_dump -U <DB_USER> -d <DB_NAME> "
                    "--no-owner --no-privileges > filaops_before_upgrade.sql",
                    "3. Get the release: git fetch --tags",
                    "4. Check out the release: git checkout vX.Y.Z "
                    "(the new version number)",
                    "5. In backend/, with your virtual environment active: "
                    "pip install -r requirements.txt, then alembic upgrade head",
                    "6. In frontend/, with Node.js 24 or newer: npm ci, then npm run build",
                    "7. Restart the backend and your web server.",
                    "8. Confirm: curl -s <backend address>/api/v1/system/version "
                    "shows the new version, and alembic current matches alembic heads.",
                ],
                "backup_recommendation": (
                    "Back up the database before you start (step 2) and keep the file. "
                    "Rolling back means restoring that backup."
                ),
                "documentation_url": UPGRADE_DOCS_URL,
                "rollback_steps": [
                    "1. Stop the backend.",
                    "2. Restore the database backup taken before the upgrade "
                    "(drop and recreate the database, then load filaops_before_upgrade.sql). "
                    "An older version won't start against a database migrated further.",
                    "3. Check out the version you upgraded from: git checkout vX.Y.Z",
                    "4. Re-install dependencies and rebuild: pip install -r requirements.txt "
                    "in backend/, npm ci and npm run build in frontend/",
                    "5. Restart the backend and your web server.",
                ],
                "requires_manual_steps": True,
            }

        # Default: Docker Compose. Mirrors docs/UPGRADE.md: back up, check out
        # the release tag, rebuild. The `migrate` service applies database
        # migrations before the backend starts, so there is no separate
        # alembic step. The method label stays "docker-compose" so existing
        # clients that read it keep working.
        return {
            "method": "docker-compose",
            "estimated_time": "5-15 minutes",
            "downtime": "FilaOps is unavailable while the containers rebuild and restart",
            "instructions": [
                "1. Read the upgrade guide (Full Documentation below). "
                "From 4.1.x or older, make the 4.2.0 configuration changes first, "
                "or the backend may not start.",
                "2. Back up the database, from the filaops folder: "
                "docker exec filaops-db pg_dump -U postgres -d filaops "
                "--no-owner --no-privileges > filaops_before_upgrade.sql",
                "3. Get the release: git fetch --tags",
                "4. Check out the release: git checkout vX.Y.Z "
                "(the new version number)",
                "5. Rebuild and start: docker compose up -d --build "
                "(database migrations run automatically before the backend starts)",
                "6. Confirm: curl -s http://localhost/api/v1/system/version "
                "shows the new version",
            ],
            "backup_recommendation": (
                "Back up the database before you start (step 2) and keep the file: "
                "rolling back means restoring it. Use your own DB_USER and DB_NAME "
                "if you changed them. On 4.3.0 or later, back up the filaops_config "
                "volume too."
            ),
            "documentation_url": UPGRADE_DOCS_URL,
            "rollback_steps": [
                "1. Stop the backend: docker compose stop backend",
                "2. Restore the database backup taken before the upgrade "
                "(Backup and Recovery guide, 'Full Database Restore'). "
                "An older version won't start against a database migrated further.",
                "3. Check out the version you upgraded from: git checkout vX.Y.Z",
                "4. Rebuild and start: docker compose up -d --build",
                "Never use docker compose down -v to roll back: it also deletes "
                "the filaops_config volume, and stored secrets such as the AI API "
                "key then have to be entered again.",
            ],
            "requires_manual_steps": True,
        }
