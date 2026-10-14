"""
Admin System Management Endpoints

Handles system-level operations like version reporting.

There is no in-app updater. Upgrading FilaOps means backing up the database,
checking out the release tag on the host and rebuilding the containers
(docs/UPGRADE.md). The web app cannot do that safely: on a standard Docker
install the backend has no access to the host's Docker daemon, and giving it
that access (mounting /var/run/docker.sock) would hand the web app
root-equivalent control of the host. POST /update/start is kept only so that
older frontends and scripts get a clear answer instead of a 404.
"""
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.user import User
from app.api.v1.deps import get_current_admin_user
from app.core.version import UPGRADE_DOCS_URL
from app.logging_config import get_logger

router = APIRouter(prefix="/system", tags=["Admin - System"])

logger = get_logger(__name__)

# Path to project root (assuming this file is in backend/app/api/v1/endpoints/admin/)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent.parent.parent

UPDATE_UNAVAILABLE_DETAIL = (
    "FilaOps can't update itself from the web app. Upgrade from the computer "
    "FilaOps runs on: back up the database, check out the new release and "
    f"rebuild. Step-by-step guide: {UPGRADE_DOCS_URL}"
)


def _get_current_git_version() -> Optional[str]:
    """Get current git version/tag"""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get git version: {e}")
    return None


@router.post("/update/start", status_code=status.HTTP_410_GONE)
async def start_update(
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Removed: one-click updates.

    Always responds 410 Gone and never runs git, docker or migrations.
    Follow the upgrade guide instead (see UPGRADE_DOCS_URL).

    **Security:** Admin-only endpoint. Requires admin authentication.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=UPDATE_UNAVAILABLE_DETAIL,
    )


@router.get("/version")
async def get_system_version(
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Get current system version

    Returns the current git version/tag of the system.
    """
    version = _get_current_git_version()
    return {
        "version": version,
        "package_version": "1.1.0",  # From package.json or settings
    }
