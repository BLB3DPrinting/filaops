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
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_admin_user
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.system_setting import SystemSetting
from app.models.user import User

logger = get_logger(__name__)

router = APIRouter(prefix="/system/settings", tags=["System Settings"])


# ============================================================================
# Origin validation (shared with main.py CORS loader)
# ============================================================================


def is_valid_origin(value: object) -> bool:
    """Strict CORS-Origin shape check.

    A browser ``Origin`` header is always exactly ``scheme://host[:port]`` — no
    path, query, fragment, or userinfo. Anything else stored in our allowlist
    can never match a real browser origin, so this function rejects:

    - Non-string values
    - Schemes other than ``http``/``https``
    - Empty hostnames (incl. authorities like ``http://:80`` where only a port
      is given — ``parsed.netloc`` is truthy but ``parsed.hostname`` is None)
    - Out-of-range or non-numeric ports (``parsed.port`` raises ``ValueError``)
    - Non-empty path (including a trailing ``/``)
    - Query strings (``?...``) or fragments (``#...``)
    - Userinfo in netloc (``user@host``)

    Used by both ``_validate_origin_list`` (PUT body validation) and
    ``app.main._load_pro_cors_origins`` (defensive runtime filtering).
    """
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value.strip())
    try:
        # Accessing .port forces stdlib to parse and validate the port number.
        # Out-of-range (>65535) or non-numeric ports raise ValueError here.
        _ = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in ("http", "https")
        and bool(parsed.hostname)  # hostname (not just netloc) must be present
        and parsed.path == ""
        and parsed.query == ""
        and parsed.fragment == ""
        and "@" not in parsed.netloc
    )


def _validate_origin_list(value: Any) -> list[str]:
    """Validate and normalize a list of CORS origin strings.

    Each origin must be ``scheme://host[:port]`` — see ``is_valid_origin``.
    Surrounding whitespace is stripped (browsers never send padding in
    ``Origin`` headers, so unstripped values would never match), and the
    normalized list is what gets persisted.

    Returns the validated, normalized list (empty list is acceptable —
    means "no origins").
    """
    if not isinstance(value, list):
        raise ValueError("must be a list of origin strings")
    normalized: list[str] = []
    for origin in value:
        if not isinstance(origin, str):
            raise ValueError(
                f"origin must be a string, got {type(origin).__name__}"
            )
        candidate = origin.strip()
        if not is_valid_origin(candidate):
            raise ValueError(
                f"invalid origin {origin!r}: must be scheme + host with no path, "
                "trailing slash, query string, fragment, or userinfo"
            )
        normalized.append(candidate)
    return normalized


def _validate_quality_mode(value: Any) -> str:
    """Validate the QC rigor dial: must be one of off | basic | full.

    See ``app.services.quality_policy`` for what each mode means.
    """
    from app.services.quality_policy import QualityMode

    allowed = [m.value for m in QualityMode]
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"quality_mode must be one of: {', '.join(allowed)}")
    return value


def _validate_bool(value: Any) -> bool:
    """Validate a strict JSON boolean (no truthy coercion)."""
    if not isinstance(value, bool):
        raise ValueError("must be a boolean (true or false)")
    return value


SETTING_VALIDATORS: dict[str, Callable[[Any], Any]] = {
    "pro_portal_origins": _validate_origin_list,
    "pro_quoter_origins": _validate_origin_list,
    # QC rigor dial (#784 QMS) — read via app.services.quality_policy
    "quality_mode": _validate_quality_mode,
    "quality_gate_close": _validate_bool,
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
    """List all registered system settings.

    Filtered to keys present in ``SETTING_VALIDATORS`` so this endpoint surfaces
    only the contracted-and-supported configuration. Unregistered rows that may
    exist from manual DB edits or stale data are intentionally hidden from the
    admin UI.
    """
    registered_keys = list(SETTING_VALIDATORS.keys())
    if not registered_keys:
        return []
    return (
        db.query(SystemSetting)
        .filter(SystemSetting.key.in_(registered_keys))
        .order_by(SystemSetting.key)
        .all()
    )


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
    """Update a setting's value. Validates against the registered validator.

    Concurrency-safe: if the row is missing (manually deleted, never seeded)
    we attempt to insert it; on ``IntegrityError`` (another admin won the race)
    we rollback, re-fetch, and update. Mirrors the pattern used by
    ``get_or_create_settings`` in ``endpoints/settings.py``.
    """
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
        # Row missing (manually deleted or never seeded) — try to insert,
        # fall back to updating the row another concurrent request just created.
        setting = SystemSetting(
            key=key, value=validated_value, updated_by=current_user.email,
        )
        db.add(setting)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            setting = (
                db.query(SystemSetting).filter(SystemSetting.key == key).first()
            )
            if setting is None:
                # Truly impossible state — surface an error rather than guessing.
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"could not persist setting {key!r}",
                )
            setting.value = validated_value
            setting.updated_by = current_user.email
            db.commit()
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
