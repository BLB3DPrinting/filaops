"""
Who customer-facing emails say they are from.

Admins enter the business name and contact email under Company Settings, so
those win. The .env values (BUSINESS_NAME, BUSINESS_EMAIL, SMTP_FROM_NAME)
are the fallback for installs that have not filled Company Settings in. The
shipped defaults ("Your Company Name", "info@yourcompany.com") are never
shown: with nothing real configured the email names FilaOps and asks the
reader to contact their administrator instead.

Resolve the identity in the request (which has a database session) and pass
it to EmailService; the email itself is sent from a worker thread.
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.settings import Settings, is_placeholder_email
from app.logging_config import get_logger
from app.models.company_settings import CompanySettings

logger = get_logger(__name__)

# Shown when neither Company Settings nor .env name the business.
FALLBACK_BUSINESS_NAME = "FilaOps"

_PLACEHOLDER_NAMES = frozenset(
    (Settings.model_fields[field].default or "").strip().lower()
    for field in ("BUSINESS_NAME", "SMTP_FROM_NAME")
)
_PLACEHOLDER_EMAILS = frozenset({
    (Settings.model_fields["BUSINESS_EMAIL"].default or "").strip().lower(),
})


@dataclass(frozen=True)
class EmailIdentity:
    """The business name and support address an email shows."""

    business_name: str
    support_email: Optional[str]
    from_name: str


def _real_name(value: Optional[str]) -> Optional[str]:
    # Collapse whitespace: a line break in a name typed into Company Settings
    # must not reach the From header.
    name = " ".join((value or "").split())
    if not name or name.lower() in _PLACEHOLDER_NAMES:
        return None
    return name


def _real_email(value: Optional[str]) -> Optional[str]:
    address = (value or "").strip()
    if address.lower() in _PLACEHOLDER_EMAILS or is_placeholder_email(address):
        return None
    return address


def _first(*values: Optional[str]) -> Optional[str]:
    return next((v for v in values if v), None)


def build_email_identity(
    company_name: Optional[str] = None,
    company_email: Optional[str] = None,
) -> EmailIdentity:
    """Pick each value from Company Settings, then .env, then a neutral default."""
    business_name = _first(_real_name(company_name), _real_name(settings.BUSINESS_NAME))
    from_name = _first(_real_name(company_name), _real_name(settings.SMTP_FROM_NAME), business_name)
    return EmailIdentity(
        business_name=business_name or FALLBACK_BUSINESS_NAME,
        support_email=_first(_real_email(company_email), _real_email(settings.BUSINESS_EMAIL)),
        from_name=from_name or FALLBACK_BUSINESS_NAME,
    )


def resolve_email_identity(db: Session) -> EmailIdentity:
    """Build the identity from the Company Settings row, if there is one."""
    try:
        row = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    except Exception:
        # A settings read must never stop a password email; fall back to .env.
        logger.warning("Could not read Company Settings for email identity", exc_info=True)
        db.rollback()
        row = None
    if row is None:
        return build_email_identity()
    return build_email_identity(row.company_name, row.company_email)
