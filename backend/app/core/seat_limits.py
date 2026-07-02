"""
Multi-user seat caps for FilaOps Core.

The ``multi_user`` capability is a PRO feature: unlicensed (community) installs
get a single staff seat, while licensed installs (professional / enterprise) get
unlimited staff seats.

A *seat* is a STAFF/team user account — ``account_type`` in ``admin`` or
``operator``. Customer / portal accounts (``account_type == "customer"``) are NOT
team members and never consume or count against a seat.

Tier is read directly from ``app.core.plugin_registry`` (set by the filaops-pro
plugin at startup). This module is deliberately independent of
``app.core.features.LICENSING_ENABLED`` — that legacy master switch is dormant
(everything free) and owned by a separate change; seat enforcement must work
regardless of its value so the leak is actually closed.

GRANDFATHERING: the cap only blocks *adding* or *activating* a NEW staff seat
beyond the cap. It never deactivates or locks out existing users. An install that
is already over the cap (e.g. a pre-existing multi-user community deployment)
keeps every current user working; it simply cannot add or reactivate another
staff member until it upgrades. There is no startup- or login-time enforcement.
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.plugin_registry import get_tier
from app.models.user import User

# Account types that count as a staff/team "seat". Customers/portal accounts
# (account_type == "customer") are intentionally excluded.
STAFF_ACCOUNT_TYPES = ("admin", "operator")

# Tier -> maximum concurrent active staff seats.
# ``None`` means unlimited. Any tier not listed here falls back to the community
# cap (fail-safe: an unknown/unlicensed tier is treated as community).
_SEAT_CAPS: dict[str, Optional[int]] = {
    "community": 1,
    "professional": None,  # unlimited
    "enterprise": None,    # unlimited
}

# Shown to the user when they hit the community seat cap.
SEAT_LIMIT_MESSAGE = (
    "Your plan allows 1 user. Upgrade to PRO to add team members."
)


def seat_cap_for_tier(tier: str) -> Optional[int]:
    """Return the max active staff seats for a tier (``None`` = unlimited).

    Unknown tiers fall back to the community cap so a missing/garbled tier can
    never silently grant unlimited seats.
    """
    return _SEAT_CAPS.get((tier or "").lower(), _SEAT_CAPS["community"])


def count_active_staff(db: Session, exclude_user_id: Optional[int] = None) -> int:
    """Count currently-active staff (admin/operator) users.

    Args:
        db: Database session.
        exclude_user_id: Optional user id to exclude from the count — used when
            re-activating an existing user so we count the seats that would
            remain *besides* the one being activated.
    """
    query = db.query(User).filter(
        User.account_type.in_(STAFF_ACCOUNT_TYPES),
        User.status == "active",
    )
    if exclude_user_id is not None:
        query = query.filter(User.id != exclude_user_id)
    return query.count()


def enforce_seat_cap(db: Session, exclude_user_id: Optional[int] = None) -> None:
    """Raise 403 if adding/activating one more staff seat would exceed the cap.

    Reads the current tier from ``plugin_registry``. On a capped tier
    (community), blocks the action when the resulting active-staff count would
    exceed the cap. On an uncapped tier (professional/enterprise) this is a
    no-op.

    GRANDFATHER: this only guards the *incremental* seat. It never touches or
    deactivates existing users; installs already over the cap keep working and
    are simply prevented from adding more.

    Args:
        db: Database session.
        exclude_user_id: When activating/reactivating an existing user, pass its
            id so it is not double-counted against the cap.

    Raises:
        HTTPException: 403 when the community seat cap would be exceeded.
    """
    cap = seat_cap_for_tier(get_tier())
    if cap is None:
        return  # unlimited — nothing to enforce

    current_active_staff = count_active_staff(db, exclude_user_id=exclude_user_id)

    # The action would add one more active staff seat. Block only if that pushes
    # the count above the cap (i.e. current already >= cap).
    if current_active_staff >= cap:
        raise HTTPException(
            status_code=403,
            detail=SEAT_LIMIT_MESSAGE,
        )
