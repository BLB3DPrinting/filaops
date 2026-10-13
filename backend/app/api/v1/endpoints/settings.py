"""
Company Settings API Endpoints

Manage company-wide settings including:
- Company info (name, address, contact)
- Logo upload
- Tax configuration
- Quote settings

SEC-408: reading settings needs a staff account (admin or operator) and
changing them needs an admin. A plain login is not enough, because anyone can
self-register a customer account. The one exception is GET /company/logo,
which stays public because PDFs and the PRO B2B portal load it anonymously.
This router mixes public and staff routes, so each route carries its own gate.
"""
import json
import re
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator

from app.db.session import get_db
from app.models.user import User
from app.models.company_settings import CompanySettings
from app.api.v1.deps import get_current_admin_user, get_current_staff_user
from app.core.outbound_guard import (
    BlockedDestinationError,
    guarded_session,
    is_blocked_destination,
    parse_ip_literal,
)
from app.logging_config import get_logger
from app.services import anthropic_models
from app.services.serial_prefix import DEFAULT_SERIAL_PREFIX, normalize_serial_prefix

logger = get_logger(__name__)

router = APIRouter(prefix="/settings", tags=["Settings"])


# ============================================================================
# SCHEMAS
# ============================================================================

class CompanySettingsResponse(BaseModel):
    """Company settings response"""
    id: int
    company_name: Optional[str] = None
    company_address_line1: Optional[str] = None
    company_address_line2: Optional[str] = None
    company_city: Optional[str] = None
    company_state: Optional[str] = None
    company_zip: Optional[str] = None
    company_country: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    company_website: Optional[str] = None

    # Logo info (not the data itself)
    has_logo: bool = False
    logo_filename: Optional[str] = None

    # Tax
    tax_enabled: bool = False
    tax_rate: Optional[Decimal] = None
    tax_rate_percent: Optional[float] = None  # For display (e.g., 8.25)
    tax_name: Optional[str] = None
    tax_registration_number: Optional[str] = None

    # Quote settings
    default_quote_validity_days: int = 30
    quote_terms: Optional[str] = None
    quote_footer: Optional[str] = None

    # Timezone
    timezone: Optional[str] = None  # IANA timezone (e.g., "America/New_York")

    # i18n / Locale
    currency_code: Optional[str] = "USD"  # ISO 4217 (e.g., "USD", "EUR", "CAD")
    locale: Optional[str] = "en-US"  # BCP-47 (e.g., "en-US", "fr-CA", "ar-SA")

    # Business hours settings
    business_hours_start: Optional[int] = None  # Hour of day (0-23), default 8am
    business_hours_end: Optional[int] = None  # Hour of day (0-23), default 4pm
    business_days_per_week: Optional[int] = None  # 5 = Mon-Fri
    business_work_days: Optional[str] = None  # "0,1,2,3,4" for Mon-Fri

    # Pricing
    default_margin_percent: Optional[float] = None

    # Dispatch
    auto_dispatch: bool = False

    # Serial numbers
    serial_number_prefix: str = DEFAULT_SERIAL_PREFIX

    updated_at: datetime

    model_config = {"from_attributes": True}


class CompanySettingsUpdate(BaseModel):
    """Update company settings"""
    company_name: Optional[str] = Field(None, max_length=255)
    company_address_line1: Optional[str] = Field(None, max_length=255)
    company_address_line2: Optional[str] = Field(None, max_length=255)
    company_city: Optional[str] = Field(None, max_length=100)
    company_state: Optional[str] = Field(None, max_length=50)
    company_zip: Optional[str] = Field(None, max_length=20)
    company_country: Optional[str] = Field(None, max_length=100)
    company_phone: Optional[str] = Field(None, max_length=30)
    company_email: Optional[str] = Field(None, max_length=255)
    company_website: Optional[str] = Field(None, max_length=255)

    # Tax (rate as percent, e.g., 8.25 for 8.25%)
    tax_enabled: Optional[bool] = None
    tax_rate_percent: Optional[float] = Field(None, ge=0, le=100)
    tax_name: Optional[str] = Field(None, max_length=50)
    tax_registration_number: Optional[str] = Field(None, max_length=100)

    # Quote settings
    default_quote_validity_days: Optional[int] = Field(None, ge=1, le=365)
    quote_terms: Optional[str] = Field(None, max_length=2000)
    quote_footer: Optional[str] = Field(None, max_length=1000)

    # Timezone (IANA timezone name)
    timezone: Optional[str] = Field(None, max_length=50)

    # i18n / Locale
    currency_code: Optional[str] = Field(None, max_length=10, pattern=r"^[A-Z]{3}$")
    locale: Optional[str] = Field(None, max_length=20)

    # Business hours settings
    business_hours_start: Optional[int] = Field(None, ge=0, le=23)  # Hour of day (0-23)
    business_hours_end: Optional[int] = Field(None, ge=0, le=23)  # Hour of day (0-23)
    business_days_per_week: Optional[int] = Field(None, ge=1, le=7)  # 1-7 days
    business_work_days: Optional[str] = Field(None, max_length=20)  # "0,1,2,3,4" for Mon-Fri

    # Pricing
    default_margin_percent: Optional[float] = Field(None, ge=0, le=99.99)

    # Dispatch
    auto_dispatch: Optional[bool] = None

    # Serial numbers: letters/digits/dashes, trailing dash added if missing.
    # New serials use it; existing serials are never renamed.
    serial_number_prefix: Optional[str] = Field(None, max_length=20)

    @field_validator("serial_number_prefix")
    @classmethod
    def _validate_serial_number_prefix(cls, value: Optional[str]) -> str:
        # Runs only when the field is sent. An explicit null is rejected
        # rather than silently switching the shop back to the default.
        return normalize_serial_prefix(value)


# ============================================================================
# HELPER: Get or Create Settings
# ============================================================================

def get_or_create_settings(db: Session) -> CompanySettings:
    """Get existing settings or create default (handles race condition)"""
    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if not settings:
        try:
            settings = CompanySettings(id=1)
            db.add(settings)
            db.commit()
            db.refresh(settings)
        except Exception:
            # Another request created it first - rollback and fetch
            db.rollback()
            settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    return settings


def settings_to_response(settings: CompanySettings) -> CompanySettingsResponse:
    """Convert settings model to response with computed fields"""
    tax_rate_percent = None
    if settings.tax_rate is not None:
        tax_rate_percent = float(settings.tax_rate) * 100

    return CompanySettingsResponse(
        id=settings.id,
        company_name=settings.company_name,
        company_address_line1=settings.company_address_line1,
        company_address_line2=settings.company_address_line2,
        company_city=settings.company_city,
        company_state=settings.company_state,
        company_zip=settings.company_zip,
        company_country=settings.company_country,
        company_phone=settings.company_phone,
        company_email=settings.company_email,
        company_website=settings.company_website,
        has_logo=settings.logo_data is not None,
        logo_filename=settings.logo_filename,
        tax_enabled=settings.tax_enabled,
        tax_rate=settings.tax_rate,
        tax_rate_percent=tax_rate_percent,
        tax_name=settings.tax_name,
        tax_registration_number=settings.tax_registration_number,
        default_quote_validity_days=settings.default_quote_validity_days,
        quote_terms=settings.quote_terms,
        quote_footer=settings.quote_footer,
        timezone=settings.timezone,
        currency_code=settings.currency_code or "USD",
        locale=settings.locale or "en-US",
        business_hours_start=settings.business_hours_start,
        business_hours_end=settings.business_hours_end,
        business_days_per_week=settings.business_days_per_week,
        business_work_days=settings.business_work_days,
        default_margin_percent=float(settings.default_margin_percent) if settings.default_margin_percent is not None else None,
        auto_dispatch=bool(settings.auto_dispatch) if settings.auto_dispatch is not None else False,
        serial_number_prefix=settings.serial_number_prefix or DEFAULT_SERIAL_PREFIX,
        updated_at=settings.updated_at,
    )


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/company", response_model=CompanySettingsResponse)
async def get_company_settings(
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Get company settings"""
    settings = get_or_create_settings(db)
    return settings_to_response(settings)


@router.patch("/company", response_model=CompanySettingsResponse)
async def update_company_settings(
    data: CompanySettingsUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Update company settings"""
    settings = get_or_create_settings(db)

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # Handle tax_rate_percent -> tax_rate conversion
    if "tax_rate_percent" in update_data:
        percent = update_data.pop("tax_rate_percent")
        if percent is not None:
            settings.tax_rate = Decimal(str(percent / 100))
        else:
            settings.tax_rate = None

    for field, value in update_data.items():
        setattr(settings, field, value)

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)

    logger.info(f"Company settings updated by {current_user.email}")
    return settings_to_response(settings)


@router.post("/company/logo")
async def upload_company_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Upload company logo"""
    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Allowed: PNG, JPEG, GIF, WebP"
        )

    # Limit file size (2MB)
    max_size = 2 * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size: 2MB"
        )

    settings = get_or_create_settings(db)
    settings.logo_data = content
    settings.logo_filename = file.filename
    settings.logo_mime_type = file.content_type
    settings.updated_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Company logo uploaded by {current_user.email}")
    return {"message": "Logo uploaded successfully", "filename": file.filename}


@router.get("/company/logo")
async def get_company_logo(
    db: Session = Depends(get_db),
):
    """Get company logo image.

    Public on purpose: PDFs and the PRO B2B portal load it without a login.
    """
    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()

    if not settings or not settings.logo_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No logo uploaded"
        )

    return Response(
        content=settings.logo_data,
        media_type=settings.logo_mime_type or "image/png",
        headers={
            "Content-Disposition": f'inline; filename="{settings.logo_filename or "logo.png"}"'
        }
    )


@router.delete("/company/logo")
async def delete_company_logo(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Delete company logo"""
    settings = get_or_create_settings(db)
    settings.logo_data = None
    settings.logo_filename = None
    settings.logo_mime_type = None
    settings.updated_at = datetime.now(timezone.utc)

    db.commit()

    logger.info(f"Company logo deleted by {current_user.email}")
    return {"message": "Logo deleted"}


# ============================================================================
# AI SETTINGS
# ============================================================================

class AISettingsResponse(BaseModel):
    """AI settings response (API key masked)"""
    ai_provider: Optional[str] = None  # 'anthropic', 'ollama', or None
    ai_api_key_set: bool = False  # True if key is configured (don't expose actual key)
    ai_api_key_masked: Optional[str] = None  # e.g., "sk-...XYZ"
    ai_anthropic_model: Optional[str] = None  # Claude model selection
    ai_ollama_url: Optional[str] = None
    ai_ollama_model: Optional[str] = None
    ai_status: str = "not_configured"  # 'not_configured', 'configured', 'connected'
    ai_status_message: Optional[str] = None
    external_ai_blocked: bool = False  # When true, only local AI (Ollama) allowed


# Model IDs look like claude-sonnet-5-5 or claude-opus-4-5-20251101. "" is
# allowed and means "use the default", like null.
_ANTHROPIC_MODEL_PATTERN = r"^([A-Za-z0-9][A-Za-z0-9._:@-]*)?$"


class AISettingsUpdate(BaseModel):
    """Update AI settings"""
    ai_provider: Optional[str] = Field(None, pattern="^(anthropic|ollama)?$")
    ai_api_key: Optional[str] = Field(None, max_length=500)
    ai_anthropic_model: Optional[str] = Field(
        None, max_length=100, pattern=_ANTHROPIC_MODEL_PATTERN
    )
    ai_ollama_url: Optional[str] = Field(None, max_length=255)
    ai_ollama_model: Optional[str] = Field(None, max_length=100)
    external_ai_blocked: Optional[bool] = None


class AnthropicModelOption(BaseModel):
    id: str
    display_name: str
    lifecycle: Optional[str] = None  # 'active' | 'deprecated' | None if unknown
    created_at: Optional[str] = None


class AnthropicModelsResponse(BaseModel):
    """Models to offer in the settings dropdown. Never contains the API key."""
    models: list[AnthropicModelOption]
    # 'anthropic' = live list for the saved key; 'fallback' = built-in list
    source: str
    recommended: str
    pricing_url: str
    error: Optional[str] = None  # why the fallback list is shown
    cached: bool = False


class AITestRequest(BaseModel):
    """Optional body for POST /ai/test: test a model before saving it."""
    ai_anthropic_model: Optional[str] = Field(
        None, max_length=100, pattern=_ANTHROPIC_MODEL_PATTERN
    )


class AnthropicStatusResponse(BaseModel):
    """Response for Anthropic package installation status"""
    installed: bool
    version: Optional[str] = None


class PackageInstallResponse(BaseModel):
    """Response for package installation operations"""
    success: bool
    message: str


def _mask_api_key(key: Optional[str]) -> Optional[str]:
    """Mask API key for display, showing only first 3 and last 4 chars"""
    if not key or len(key) < 10:
        return None
    return f"{key[:3]}...{key[-4:]}"


def _test_anthropic_connection(api_key: str, model: str) -> tuple[bool, str]:
    """Send a one-token request with the chosen model.

    A real request, so a bad key, or a retired or mistyped model ID, is
    reported now instead of when the first invoice is parsed.
    """
    try:
        import anthropic  # noqa: F401  (invoice parsing needs the package)
    except ImportError:
        return False, "anthropic package not installed"
    return anthropic_models.check_model(api_key, model)


# SEC: ai_ollama_url is fetched by the server. Ollama normally runs on
# localhost or the LAN, so private addresses stay allowed. What is refused is
# anything that lets the setting reach more than <base>/api/tags: other
# schemes, credentials in the URL, query strings, fragments, redirects, and
# (app.core.outbound_guard) link-local and cloud metadata addresses, checked
# on the address the server actually connects to.
_OLLAMA_DEFAULT_URL = "http://localhost:11434"
_OLLAMA_URL_HELP = (
    "Ollama URL must look like http://host:port (http or https, "
    "no username/password, no ? or #)."
)
_OLLAMA_BLOCKED_HELP = (
    "That address can't be used for Ollama: link-local, cloud metadata and "
    "multicast addresses (such as 169.254.x.x) are blocked. Use localhost or "
    "the Ollama machine's LAN address."
)
_OLLAMA_PATH_RE = re.compile(r"[A-Za-z0-9._~/-]*")
_OLLAMA_MAX_TAGS_BYTES = 1024 * 1024
_OLLAMA_DEADLINE_SECONDS = 10


def _normalize_ollama_url(raw: Optional[str]) -> Optional[str]:
    """Return a clean Ollama base URL (no trailing slash), or None if invalid."""
    if not raw or not raw.isascii():
        return None
    if any(ord(c) <= 0x20 or ord(c) == 0x7F or c in "\\@?#" for c in raw):
        return None
    try:
        parts = urlsplit(raw)
        parts.port  # raises ValueError for a non-numeric or out-of-range port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    if not _OLLAMA_PATH_RE.fullmatch(parts.path):
        return None
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def _ollama_host_is_blocked_ip(base_url: str) -> bool:
    """True if the URL's host is a blocked IP address written out (no DNS).

    Host names are left to the connect-time check in _fetch_ollama_models.
    """
    ip = parse_ip_literal(urlsplit(base_url).hostname or "")
    return ip is not None and is_blocked_destination(ip)


def _fetch_ollama_models(base_url: str, timeout=(3, 5)) -> tuple[int, Optional[list[str]]]:
    """GET <base_url>/api/tags. No redirects, bounded size and time.

    Returns (status_code, model names) where names is None unless the answer
    is a 200 shaped like Ollama's {"models": [{"name": ...}]}. The raw body is
    never returned, so nothing else the URL answers with reaches the caller.
    Raises BlockedDestinationError if the host is, or resolves only to,
    link-local, cloud metadata or other blocked addresses.
    """
    deadline = time.monotonic() + _OLLAMA_DEADLINE_SECONDS
    with guarded_session() as session, session.get(
        f"{base_url}/api/tags",
        timeout=timeout,
        allow_redirects=False,
        stream=True,
    ) as response:
        if response.status_code != 200:
            return response.status_code, None
        body = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            body += chunk
            if len(body) > _OLLAMA_MAX_TAGS_BYTES or time.monotonic() > deadline:
                return 200, None
    try:
        models = json.loads(body).get("models")
    except (ValueError, AttributeError):
        return 200, None
    if not isinstance(models, list):
        return 200, None
    return 200, [
        m["name"] for m in models
        if isinstance(m, dict) and isinstance(m.get("name"), str)
    ]


def _test_ollama_connection(url: str, model: str) -> tuple[bool, str]:
    """Test Ollama connection"""
    import requests

    base_url = _normalize_ollama_url(url)
    if base_url is None:
        return False, _OLLAMA_URL_HELP
    try:
        status_code, names = _fetch_ollama_models(base_url)
    except BlockedDestinationError:  # before ConnectionError, its base class
        return False, _OLLAMA_BLOCKED_HELP
    except requests.exceptions.ConnectionError:
        return False, "Ollama is not running. Click 'Start Ollama' below or launch the Ollama app."
    except requests.exceptions.Timeout:
        return False, "Connection timed out"
    except Exception as e:
        logger.error(f"Ollama connection test failed: {e}")
        return False, "Connection test failed"

    if 300 <= status_code < 400:
        return False, f"Ollama URL redirects (status {status_code}). Enter the final address."
    if status_code != 200:
        return False, f"Ollama not responding (status {status_code})"
    if names is None:
        return False, "Something answered at that address, but it is not an Ollama server"

    if model not in [n.split(":")[0] for n in names] and f"{model}:latest" not in names:
        available = ", ".join(n.split(":")[0][:64] for n in names[:5])
        return True, f"Connected, but model '{model}' not found. Available: {available}"

    return True, f"Connected to Ollama, model '{model}' available"


def _ollama_is_up(base_url: str, timeout) -> bool:
    try:
        _, names = _fetch_ollama_models(base_url, timeout=timeout)
    except Exception:  # includes BlockedDestinationError: a blocked address is never up
        return False
    return names is not None


@router.get("/ai", response_model=AISettingsResponse)
async def get_ai_settings(
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Get AI configuration settings (API keys masked)"""
    settings = get_or_create_settings(db)

    # Determine status
    ai_status = "not_configured"
    ai_status_message = "No AI provider configured"

    if settings.ai_provider == "anthropic" and settings.ai_api_key:
        ai_status = "configured"
        ai_status_message = "Anthropic API key configured"
    elif settings.ai_provider == "ollama":
        ai_status = "configured"
        ai_status_message = f"Ollama configured at {settings.ai_ollama_url or 'http://localhost:11434'}"

    return AISettingsResponse(
        ai_provider=settings.ai_provider,
        ai_api_key_set=bool(settings.ai_api_key),
        ai_api_key_masked=_mask_api_key(settings.ai_api_key),
        ai_anthropic_model=settings.ai_anthropic_model or anthropic_models.DEFAULT_ANTHROPIC_MODEL,
        ai_ollama_url=settings.ai_ollama_url or "http://localhost:11434",
        ai_ollama_model=settings.ai_ollama_model or "llama3.2",
        ai_status=ai_status,
        ai_status_message=ai_status_message,
        external_ai_blocked=settings.external_ai_blocked or False,
    )


@router.patch("/ai", response_model=AISettingsResponse)
async def update_ai_settings(
    data: AISettingsUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Update AI configuration settings"""
    settings = get_or_create_settings(db)

    # Update fields
    update_data = data.model_dump(exclude_unset=True)

    # The server fetches this URL, so only store a plain http(s) base URL.
    # "" resets to the default, like null.
    if update_data.get("ai_ollama_url"):
        normalized = _normalize_ollama_url(update_data["ai_ollama_url"])
        if normalized is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_OLLAMA_URL_HELP,
            )
        # A host name is checked when the server connects (no DNS here).
        if _ollama_host_is_blocked_ip(normalized):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_OLLAMA_BLOCKED_HELP,
            )
        update_data["ai_ollama_url"] = normalized
    elif "ai_ollama_url" in update_data:
        update_data["ai_ollama_url"] = None

    # Check if trying to set Anthropic while external AI is blocked
    new_provider = update_data.get("ai_provider", settings.ai_provider)
    is_blocked = update_data.get("external_ai_blocked", settings.external_ai_blocked)

    if new_provider == "anthropic" and is_blocked:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot use Anthropic while external AI is blocked. Disable the block first or use Ollama."
        )

    # If enabling the block, clear Anthropic settings
    if update_data.get("external_ai_blocked") is True:
        if settings.ai_provider == "anthropic":
            settings.ai_provider = None
        settings.ai_api_key = None
        logger.info("External AI blocked - cleared Anthropic settings")

    for field, value in update_data.items():
        # Don't clear API key if empty string passed (only if explicitly None)
        if field == "ai_api_key" and value == "":
            continue
        setattr(settings, field, value)

    settings.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(settings)

    logger.info(f"AI settings updated by {current_user.email}")

    # Return updated settings
    return await get_ai_settings(current_user, db)


@router.get("/ai/anthropic-models", response_model=AnthropicModelsResponse)
def list_anthropic_models(
    refresh: bool = Query(False, description="Skip the short server-side cache"),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Claude models the saved API key can use, from Anthropic's Models API.

    On any failure (no key, external AI blocked, network, bad key) this still
    answers 200, with `error` set and a small built-in list, so the settings
    page can always render a dropdown.
    """
    settings = get_or_create_settings(db)

    def fallback(error: str) -> AnthropicModelsResponse:
        return AnthropicModelsResponse(
            models=anthropic_models.fallback_models(),
            source="fallback",
            recommended=anthropic_models.DEFAULT_ANTHROPIC_MODEL,
            pricing_url=anthropic_models.PRICING_URL,
            error=error,
        )

    if settings.external_ai_blocked:
        return fallback("External AI is blocked, so Anthropic was not contacted.")
    if not settings.ai_api_key:
        return fallback("Save an Anthropic API key to load the models it can use.")

    try:
        models, cached = anthropic_models.list_models(settings.ai_api_key, refresh=refresh)
    except anthropic_models.AnthropicModelsError as exc:
        logger.warning("Anthropic model list unavailable: %s", exc)
        return fallback(str(exc))

    return AnthropicModelsResponse(
        models=models,
        source="anthropic",
        recommended=anthropic_models.DEFAULT_ANTHROPIC_MODEL,
        pricing_url=anthropic_models.PRICING_URL,
        cached=cached,
    )


@router.post("/ai/test")
def test_ai_connection(
    data: Optional[AITestRequest] = Body(None),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Test the configured AI connection.

    For Anthropic, `ai_anthropic_model` in the body tests the model picked on
    the page before it is saved; without it the saved model is tested.
    """
    settings = get_or_create_settings(db)

    if not settings.ai_provider:
        return {
            "success": False,
            "provider": None,
            "message": "No AI provider configured. Select 'anthropic' or 'ollama' first."
        }

    if settings.ai_provider == "anthropic":
        if not settings.ai_api_key:
            return {
                "success": False,
                "provider": "anthropic",
                "message": "Anthropic API key not set"
            }
        model = (
            (data.ai_anthropic_model if data else None)
            or settings.ai_anthropic_model
            or anthropic_models.DEFAULT_ANTHROPIC_MODEL
        )
        success, message = _test_anthropic_connection(settings.ai_api_key, model)
        return {
            "success": success,
            "provider": "anthropic",
            "message": message
        }

    elif settings.ai_provider == "ollama":
        url = settings.ai_ollama_url or _OLLAMA_DEFAULT_URL
        model = settings.ai_ollama_model or "llama3.2"
        success, message = _test_ollama_connection(url, model)
        return {
            "success": success,
            "provider": "ollama",
            "message": message
        }

    return {
        "success": False,
        "provider": settings.ai_provider,
        "message": f"Unknown provider: {settings.ai_provider}"
    }


@router.post("/ai/start-ollama")
def start_ollama(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """Attempt to start the Ollama service"""
    import subprocess
    import platform

    settings = get_or_create_settings(db)
    ollama_url = _normalize_ollama_url(settings.ai_ollama_url or _OLLAMA_DEFAULT_URL)
    if ollama_url is None:
        return {"success": False, "message": _OLLAMA_URL_HELP}

    # First check if already running
    try:
        _, names = _fetch_ollama_models(ollama_url, timeout=2)
    except BlockedDestinationError:
        # SEC: a blocked address never answers. Say so, rather than falling
        # through to launching a local 'ollama serve' for a URL the server
        # will never contact.
        return {"success": False, "message": _OLLAMA_BLOCKED_HELP}
    except Exception:
        names = None
    if names is not None:
        return {
            "success": True,
            "message": "Ollama is already running!"
        }

    # Try to start Ollama
    try:
        if platform.system() == "Windows":
            # On Windows, try to start ollama serve in background
            # Using CREATE_NO_WINDOW flag to run silently
            CREATE_NO_WINDOW = 0x08000000
            subprocess.Popen(
                ["ollama", "serve"],
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # On Linux/Mac
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

        # Wait a moment and check if it started
        time.sleep(2)

        if _ollama_is_up(ollama_url, timeout=3):
            return {
                "success": True,
                "message": "Ollama started successfully!"
            }

        return {
            "success": False,
            "message": "Ollama is starting... Please try 'Test Connection' again in a few seconds."
        }

    except FileNotFoundError:
        return {
            "success": False,
            "message": "Ollama is not installed. Download it from ollama.com"
        }
    except Exception as e:
        logger.error(f"Failed to start Ollama: {e}")
        return {
            "success": False,
            "message": "Could not start Ollama. Check logs for details."
        }


@router.get("/ai/anthropic-status", response_model=AnthropicStatusResponse)
async def check_anthropic_status(
    current_user: User = Depends(get_current_staff_user),
) -> AnthropicStatusResponse:
    """Check if the anthropic package is installed."""
    try:
        import anthropic
        return AnthropicStatusResponse(
            installed=True,
            version=getattr(anthropic, "__version__", "unknown")
        )
    except ImportError:
        return AnthropicStatusResponse(
            installed=False,
            version=None
        )


@router.post("/ai/install-anthropic", response_model=PackageInstallResponse)
async def install_anthropic_package(
    current_user: User = Depends(get_current_admin_user),
) -> PackageInstallResponse:
    """Install the anthropic Python package."""
    import subprocess
    import sys

    # Check if already installed
    try:
        import anthropic
        return PackageInstallResponse(
            success=True,
            message=f"Anthropic package already installed (v{getattr(anthropic, '__version__', 'unknown')})"
        )
    except ImportError:
        pass

    # Install using pip
    try:
        # Get the pip executable from the same environment as the running Python
        python_executable = sys.executable
        result = subprocess.run(
            [python_executable, "-m", "pip", "install", "anthropic"],
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            # Verify installation
            try:
                # Force reimport
                import importlib
                anthropic = importlib.import_module("anthropic")
                version = getattr(anthropic, "__version__", "unknown")
                return PackageInstallResponse(
                    success=True,
                    message=f"Anthropic package installed successfully (v{version}). Please refresh the page."
                )
            except ImportError:
                return PackageInstallResponse(
                    success=True,
                    message="Package installed. Please restart the application to use it."
                )
        else:
            logger.error(f"pip install failed: {result.stderr}")
            return PackageInstallResponse(
                success=False,
                message=f"Installation failed: {result.stderr[:200]}"
            )

    except subprocess.TimeoutExpired:
        return PackageInstallResponse(
            success=False,
            message="Installation timed out. Please try again or install manually."
        )
    except Exception as e:
        logger.error(f"Failed to install anthropic: {e}")
        return PackageInstallResponse(
            success=False,
            message=f"Installation error: {str(e)}"
        )
