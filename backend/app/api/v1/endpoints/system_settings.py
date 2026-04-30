"""
System Settings API Endpoints

Generic admin-editable key/value configuration store. First launch use is PRO
CORS origins (`pro_portal_origins`, `pro_quoter_origins`). Subsequent PRs may
add their own keys, each requiring a validator entry in
``SETTING_VALIDATORS``.

Unknown keys are rejected at the endpoint with 404, so this is not a generic
JSON dump — every key must be registered in the validator table.

All endpoints require admin authentication.
"""
from datetime import datetime
from typing import Annotated, Any, Callable

import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_admin_user
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.system_setting import SystemSetting
from app.models.user import User

logger = get_logger(__name__)

router = APIRouter(prefix="/system/settings", tags=["System Settings"])


# ============================================================================
# Validator registry
# ============================================================================

_ORIGIN_REGEX = re.compile(r"^https?://[^/\s]+$")


def _validate_origin_list(value: Any) -> list[str]:
    """Validate a list of CORS origin strings.

    Each origin must be `scheme://host[:port]` — no path, no trailing slash,
    no whitespace. Returns the validated list.
    """
    if not isinstance(value, list):
        raise ValueError("must be a list of origin strings")
    for origin in value:
        if not isinstance(origin, str):
            raise ValueError(
                f"origin must be a string, got {type(origin).__name__}"
            )
        if not _ORIGIN_REGEX.match(origin):
            raise ValueError(
                f"invalid origin {origin!r}: must be scheme + host with no path "
                "or trailing slash"
            )
    return value


SETTING_VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "pro_portal_origins": _validate_origin_list,
    "pro_quoter_origins": _validate_origin_list,
}


# ============================================================================
# Schemas
# ============================================================================


class SystemSettingResponse(BaseModel):
    """Response shape for a single setting."""
    key: str
    value: Any
    updated_at: datetime
    updated_by: str | None = None

    model_config = {"from_attributes": True}


class SystemSettingUpdate(BaseModel):
    """PUT body for a setting update."""
    value: Any


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=list[SystemSettingResponse])
async def list_settings(
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[SystemSetting]:
    """List all registered system settings (admin overview)."""
    return db.query(SystemSetting).order_by(SystemSetting.key).all()


@router.get("/{key}", response_model=SystemSettingResponse)
async def get_setting(
    key: str,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SystemSetting:
    """Get a single setting by key. 404 if the key is not registered or has no row."""
    if key not in SETTING_VALIDATORS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown setting key {key!r}",
        )
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"setting {key!r} has no row (was it seeded by migration?)",
        )
    return setting


@router.put("/{key}", response_model=SystemSettingResponse)
async def update_setting(
    key: str,
    body: SystemSettingUpdate,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> SystemSetting:
    """Update a setting's value. Validates against the registered validator."""
    validator = SETTING_VALIDATORS.get(key)
    if validator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown setting key {key!r}",
        )
    try:
        validated_value = validator(body.value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting is None:
        # Seeded by migration, but if the row was somehow removed, re-create it.
        setting = SystemSetting(key=key, value=validated_value)
        db.add(setting)
    else:
        setting.value = validated_value
    setting.updated_by = current_user.email

    db.commit()
    db.refresh(setting)

    logger.info(
        "system setting updated: %s by %s", key, current_user.email,
        extra={"setting_key": key, "updated_by": current_user.email},
    )
    return setting
