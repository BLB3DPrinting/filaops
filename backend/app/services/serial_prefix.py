"""
Shop-wide serial-number prefix.

Serial numbers look like ``{prefix}{YYYYMMDD}-{NNNN}``, e.g. ``SN-20261013-0001``.
The prefix is a Company Settings value so each shop can brand its own serials.

Rules for a prefix:
- letters, digits and dashes only, starting with a letter or digit
- always ends with a dash (one is added if missing)
- at most MAX_SERIAL_PREFIX_LENGTH characters including that dash

The same normaliser runs when an admin saves the setting and again when a
serial is generated, so a bad value written straight into the database can
never reach a serial number.
"""
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.company_settings import CompanySettings

logger = get_logger(__name__)

DEFAULT_SERIAL_PREFIX = "SN-"
MAX_SERIAL_PREFIX_LENGTH = 12

_PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*$")


def normalize_serial_prefix(value: Optional[str]) -> str:
    """Return the canonical form of a serial prefix, or raise ValueError.

    Strips surrounding whitespace and appends a trailing dash when missing.
    Case is kept as typed: serial lookups are exact matches, so changing
    case behind the admin's back would only cause confusion.
    """
    if value is None:
        raise ValueError("Serial number prefix cannot be empty")
    prefix = value.strip()
    if not prefix:
        raise ValueError("Serial number prefix cannot be empty")
    if not _PREFIX_PATTERN.match(prefix):
        raise ValueError(
            "Serial number prefix may contain only letters, digits and dashes, "
            "and must start with a letter or digit"
        )
    if not prefix.endswith("-"):
        prefix += "-"
    if len(prefix) > MAX_SERIAL_PREFIX_LENGTH:
        raise ValueError(
            f"Serial number prefix must be at most {MAX_SERIAL_PREFIX_LENGTH} "
            "characters including the trailing dash"
        )
    return prefix


def get_serial_prefix(db: Session) -> str:
    """Return the configured shop-wide serial prefix.

    Falls back to DEFAULT_SERIAL_PREFIX when no Company Settings row exists
    yet or the value is unset. A stored value that fails validation (only
    possible through a direct database edit) is logged and replaced by the
    default rather than written into a serial number.
    """
    stored = (
        db.query(CompanySettings.serial_number_prefix)
        .filter(CompanySettings.id == 1)
        .scalar()
    )
    if stored is None:
        return DEFAULT_SERIAL_PREFIX
    try:
        return normalize_serial_prefix(stored)
    except ValueError:
        logger.warning(
            "Ignoring invalid serial_number_prefix in company_settings; "
            "using the default %s",
            DEFAULT_SERIAL_PREFIX,
        )
        return DEFAULT_SERIAL_PREFIX
