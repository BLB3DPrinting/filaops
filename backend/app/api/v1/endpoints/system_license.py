"""
License Activation API Endpoints (PR-02)

Owns the Core-side bootstrap of PRO licensing: takes a license key from the
admin UI, validates it against the license server via plain ``httpx``, and
persists the result to ``<config_dir>/license.json`` for PRO to pick up on
its next boot.

Sacred Rule: this module MUST NOT import from ``filaops_pro``. Core must
remain Community-functional whether or not PRO is installed, so the
activation flow re-implements the small subset of license-server
communication it needs (rather than reusing PRO's ``LicenseClient``).
PR-03 will extend this with a heartbeat scheduler that lives PRO-side.

The license-server's ``POST /api/v1/validate`` endpoint contract is
documented in ``license-server/CLAUDE.md`` and the request/response
shapes in ``license-server/app/schemas/license.py``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_admin_user
from app.core.config import settings
from app.core.license_cache import (
    LicenseCache,
    clear_license_cache,
    get_install_uuid,
    load_license_cache,
    save_license_cache,
    utc_now_iso,
)
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.user import User

logger = get_logger(__name__)

router = APIRouter(prefix="/system/license", tags=["System License"])

# How long Core waits for the license server before giving up. Short enough
# that a hung server doesn't leave the admin UI spinning indefinitely; long
# enough to absorb normal cross-region latency.
_LICENSE_SERVER_TIMEOUT_SECONDS = 15.0


# ============================================================================
# Schemas
# ============================================================================


class LicenseActivationRequest(BaseModel):
    """Body for ``POST /system/license/activate``."""

    license_key: str = Field(..., min_length=1, description="License key from purchase email")


class LicenseInfoResponse(BaseModel):
    """Response shape for ``GET /system/license/info`` and activation success."""

    activated: bool
    tier: str  # community | professional | enterprise
    features: list[str]
    install_uuid: str
    license_key: Optional[str] = None  # masked when returned
    expires_at: Optional[str] = None
    activated_at: Optional[str] = None
    message: Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================


def _mask_license_key(key: str) -> str:
    """Return a license key with the middle masked for display.

    Safe for log lines and admin UI display where exposing the full key
    would be overkill.
    """
    if not key:
        return ""
    if len(key) <= 12:
        return f"{key[:4]}***"
    return f"{key[:12]}***{key[-4:]}"


def _datetime_to_iso(value: object) -> Optional[str]:
    """Coerce a license-server datetime field to an ISO 8601 string.

    The server returns ``datetime`` (FastAPI serializes to ISO when sending
    JSON), but a strict client receives a string. Be defensive about both.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return None


def _build_info_response(
    cache: Optional[LicenseCache],
    install_uuid: str,
    *,
    message: Optional[str] = None,
) -> LicenseInfoResponse:
    """Map a LicenseCache (or its absence) to the response schema."""
    if cache is None:
        return LicenseInfoResponse(
            activated=False,
            tier="community",
            features=[],
            install_uuid=install_uuid,
            message=message,
        )
    return LicenseInfoResponse(
        activated=True,
        tier=cache.tier,
        features=list(cache.features),
        install_uuid=install_uuid,
        license_key=_mask_license_key(cache.license_key),
        expires_at=cache.expires_at,
        activated_at=cache.activated_at,
        message=message,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/info", response_model=LicenseInfoResponse)
async def get_license_info(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LicenseInfoResponse:
    """Read the persisted license state. Returns Community defaults if no license."""
    install_uuid = get_install_uuid()
    cache = load_license_cache()
    return _build_info_response(cache, install_uuid)


@router.post("/activate", response_model=LicenseInfoResponse)
async def activate_license(
    body: LicenseActivationRequest,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LicenseInfoResponse:
    """Validate a license key against the license server and persist the result.

    Flow:
      1. Generate (or reuse) the install_uuid for this Core instance
      2. POST to ``{LICENSE_SERVER_URL}/api/v1/validate`` with X-API-Key
      3. If the server says ``valid=False``, return 400 with the server's reason
      4. Otherwise persist a ``LicenseCache`` row and return the new info shape
    """
    if not settings.LICENSE_API_KEY:
        # Surface a clear server-config error rather than a confusing 401 from
        # the license server. This is most often a missed env var on a fresh
        # Core deploy.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "License activation is not configured: LICENSE_API_KEY is not set. "
                "Set it in the Core .env and restart."
            ),
        )

    license_key = body.license_key.strip()
    if not license_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="License key cannot be empty.",
        )

    install_uuid = get_install_uuid()
    validate_url = f"{settings.LICENSE_SERVER_URL}/api/v1/validate"
    payload = {
        "license_key": license_key,
        "instance_id": install_uuid,
        "app_version": settings.VERSION,
    }
    headers = {"X-API-Key": settings.LICENSE_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=_LICENSE_SERVER_TIMEOUT_SECONDS) as client:
            resp = await client.post(validate_url, json=payload, headers=headers)
    except httpx.TimeoutException:
        logger.warning(
            "License activation timed out talking to %s (key=%s)",
            validate_url, _mask_license_key(license_key),
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="License server did not respond in time. Try again in a moment.",
        )
    except httpx.RequestError as exc:
        # Connection refused, DNS failure, TLS error, etc.
        logger.warning(
            "License activation network error to %s: %s",
            validate_url, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Could not reach the license server. Check internet connectivity "
                "and the LICENSE_SERVER_URL setting."
            ),
        )

    if resp.status_code == 401:
        # Our server-to-server key was rejected — operator config issue.
        logger.error(
            "License server rejected our X-API-Key (license_key=%s)",
            _mask_license_key(license_key),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "License server rejected this Core's credentials. "
                "Verify LICENSE_API_KEY is set to the correct value."
            ),
        )
    if resp.status_code >= 500:
        logger.error(
            "License server returned %d on activation: %s",
            resp.status_code, resp.text[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="License server is having problems. Try again shortly.",
        )

    try:
        data = resp.json()
    except ValueError:
        logger.error(
            "License server returned non-JSON body (status=%d): %s",
            resp.status_code, resp.text[:300],
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="License server returned an unexpected response.",
        )

    valid = bool(data.get("valid"))
    server_message = data.get("message")
    if not valid:
        # Server-rejected — most often "invalid key" or "expired". 400 because
        # this is a user-input problem, not a server-side issue.
        logger.info(
            "License rejected by server: key=%s, message=%s",
            _mask_license_key(license_key), server_message,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=server_message or "License key was rejected by the license server.",
        )

    # Valid — persist the LicenseCache. PR-03 will extend this with the
    # heartbeat-related fields (status, last_verified_at, etc.); for now we
    # store just enough that PRO can pick up tier + features on next boot.
    tier = str(data.get("tier") or "community").lower()
    features = list(data.get("features") or [])
    expires_at = _datetime_to_iso(data.get("current_period_end"))

    cache = LicenseCache(
        license_key=license_key,
        install_uuid=install_uuid,
        tier=tier,
        features=features,
        activated_at=utc_now_iso(),
        expires_at=expires_at,
    )
    save_license_cache(cache)

    logger.info(
        "License activated: tier=%s, features=%d, key=%s, by=%s",
        tier, len(features), _mask_license_key(license_key), current_user.email,
    )

    return _build_info_response(cache, install_uuid, message=server_message)


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_license(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Remove the persisted license cache.

    Does NOT contact the license server (deactivation on the server side is
    a separate concept managed via Stripe / admin tools). This endpoint just
    purges the local activation file so a next-boot Core operates as
    Community.

    install_uuid is preserved — it's stable across activation cycles so any
    future re-activation reuses the same encryption keys (PR-06).
    """
    clear_license_cache()
    logger.info("License deactivated locally by %s", current_user.email)
