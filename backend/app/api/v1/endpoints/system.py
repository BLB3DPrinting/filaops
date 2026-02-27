"""
System management endpoints for FilaOps

Includes version checking, update detection, and system health monitoring.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional
from sqlalchemy.orm import Session
import logging

from app.core.version import VersionManager
from app.core.plugin_registry import get_tier, get_features
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System Management"])


# ============================================================================
# Response Models
# ============================================================================

class VersionResponse(BaseModel):
    """Current version information (public-safe fields only)"""
    version: str
    build_date: str


class SystemInfoResponse(BaseModel):
    """System tier and enabled features — used by frontend for feature gating."""
    tier: str
    features_enabled: list[str]
    version: str


class UpdateCheckResponse(BaseModel):
    """Update availability information"""
    update_available: bool
    current_version: str
    latest_version: Optional[str] = None
    release_notes: Optional[str] = None
    release_date: Optional[str] = None
    release_url: Optional[str] = None
    prerelease: Optional[bool] = None
    upgrade_method: Optional[str] = None
    estimated_downtime: Optional[str] = None
    requires_manual_steps: Optional[bool] = None
    cached: Optional[bool] = None
    cache_stale: Optional[bool] = None
    error: Optional[str] = None


class UpdateInstructionsResponse(BaseModel):
    """Update instructions"""
    method: str
    estimated_time: str
    downtime: str
    instructions: list[str]
    backup_recommendation: str
    documentation_url: str
    rollback_steps: list[str]


class SystemHealthResponse(BaseModel):
    """System health status"""
    status: str
    version: str
    timestamp: str
    services: Dict[str, str]
    database_connected: Optional[bool] = None
    error: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/version", response_model=VersionResponse)
async def get_system_version():
    """
    Get current FilaOps version and build date.

    Returns only public-safe version info for bug reporting.
    Sensitive fields (environment, database_version, etc.) are redacted.
    """
    try:
        version_info = VersionManager.get_current_version()

        # Return only public-safe fields
        return VersionResponse(
            version=version_info.get("version", "unknown"),
            build_date=version_info.get("build_date", "unknown")
        )
    except Exception as e:
        logger.error(f"Failed to get version info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get version info"
        )


@router.get("/info", response_model=SystemInfoResponse)
async def get_system_info():
    """
    Get system tier and enabled features.

    Core always returns tier="community" with no features.
    When a plugin (e.g. filaops-pro) is installed, its register()
    updates the plugin registry to advertise tier and features.
    The frontend fetches this at startup to show/hide PRO sections.
    """
    try:
        version_info = VersionManager.get_current_version()
        return SystemInfoResponse(
            tier=get_tier(),
            features_enabled=get_features(),
            version=version_info.get("version", "unknown"),
        )
    except Exception as e:
        logger.error(f"Failed to get system info: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get system info"
        )


@router.get("/updates/check", response_model=UpdateCheckResponse)
async def check_for_updates():
    """
    Check GitHub releases for available updates

    Returns update availability, version info, and upgrade instructions.
    Uses server-side caching (1 hour) to avoid GitHub API rate limits.

    Rate limits:
    - Without GitHub token: 60 requests/hour
    - With GitHub token: 5000 requests/hour
    """
    try:
        update_info = VersionManager.check_for_updates()
        return UpdateCheckResponse(**update_info)
    except Exception as e:
        logger.error(f"Failed to check for updates: {e}", exc_info=True)
        return UpdateCheckResponse(
            update_available=False,
            current_version=VersionManager.get_current_version()["version"],
            error=f"Failed to check for updates: {str(e)}"
        )


@router.get("/updates/instructions", response_model=UpdateInstructionsResponse)
async def get_update_instructions():
    """
    Get step-by-step update instructions for current deployment method

    Returns the manual upgrade steps for Phase 1 implementation.
    Future versions may include automated update capabilities.
    """
    try:
        instructions = VersionManager.get_update_instructions()
        return UpdateInstructionsResponse(**instructions)
    except Exception as e:
        logger.error(f"Failed to get update instructions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get update instructions: {str(e)}"
        )


@router.get("/health", response_model=SystemHealthResponse)
async def system_health(db: Session = Depends(get_db)):
    """
    System health check endpoint

    Returns basic system status including version, database connectivity,
    and service availability. Used for monitoring and diagnostics.
    """
    try:
        version_info = VersionManager.get_current_version()

        # Test database connection
        database_connected = False
        try:
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
            database_connected = True
        except Exception as db_error:
            logger.error(f"Database health check failed: {db_error}")

        return SystemHealthResponse(
            status="healthy" if database_connected else "degraded",
            version=version_info["version"],
            timestamp=version_info["build_date"],
            database_connected=database_connected,
            services={
                "version_manager": "operational",
                "update_checker": "ready",
                "database": "connected" if database_connected else "disconnected"
            }
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        return SystemHealthResponse(
            status="error",
            version="unknown",
            timestamp="",
            error=str(e),
            services={
                "version_manager": "error",
                "update_checker": "error",
                "database": "error"
            }
        )
