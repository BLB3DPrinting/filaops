"""
FilaOps Version Management System

Handles version detection, update checking, and GitHub release integration.
Uses git-based versioning for native PostgreSQL installation.

Version resolution order:
  1. Git tag (git describe --tags --abbrev=0) — works in dev and non-Docker prod
  2. FILAOPS_VERSION environment variable — set via Dockerfile ARG or docker-compose
  3. _VERSION_FILE (backend/VERSION) — single source of truth, read at import time
  4. Hardcoded FALLBACK_VERSION — last resort, should never be reached

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

    GITHUB_REPO = "Blb3D/filaops"
    FALLBACK_VERSION = _read_version_file() or "3.0.1"

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

        return {
            "version": version,
            "build_date": os.getenv('FILAOPS_BUILD_DATE', datetime.now().isoformat()),
            "commit_hash": commit_hash,
            "database_version": "unknown",  # Will be set by endpoint with DB session
            "environment": os.getenv("ENVIRONMENT", "production"),
            "update_method": "docker-compose"
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
        Get step-by-step update instructions for current deployment method

        Returns manual upgrade steps for Phase 1 implementation
        """
        return {
            "method": "docker-compose",
            "estimated_time": "5-10 minutes",
            "downtime": "Full system downtime during upgrade",
            "instructions": [
                "1. Stop FilaOps: docker-compose down",
                "2. Get latest code: git fetch --tags",
                "3. Find latest version: git tag --sort=-v:refname | head -1",
                "4. Checkout version: git checkout vX.X.X (replace with actual version)",
                "5. Rebuild containers: docker-compose build --no-cache",
                "6. Start services: docker-compose up -d",
                "7. Run migrations: docker-compose exec backend alembic upgrade head",
                "8. Clear browser cache (Ctrl+Shift+R) and test"
            ],
            "backup_recommendation": "Backup database before starting (recommended for production)",
            "documentation_url": "https://github.com/Blb3D/filaops/blob/main/UPGRADE.md",
            "rollback_steps": [
                "1. Stop services: docker-compose down",
                "2. Checkout previous version: git checkout vX.X.X",
                "3. Rebuild: docker-compose build",
                "4. Start: docker-compose up -d",
                "5. Rollback migrations: docker-compose exec backend alembic downgrade -1 (repeat as needed)"
            ]
        }
