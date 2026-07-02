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
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.plugin_registry import get_tier
from app.models.user import User

# Account types that count as a staff/team "seat". Customers/portal accounts
# (account_type == "customer") are intentionally excluded.
STAFF_ACCOUNT_TYPES = ("admin", "operator")

# Fixed, arbitrary key for the transaction-scoped Postgres advisory lock that
# serializes seat-cap enforcement across concurrent requests (see
# enforce_seat_cap). Any stable int works; this private constant means only
# seat enforcement contends on it.
_SEAT_LOCK_KEY = 848_293_001

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

    CONCURRENCY (TOCTOU): the count-then-insert/activate performed by the caller
    is check-then-act. Two concurrent create/activate requests could each read
    a below-cap count and both proceed, overshooting the cap. To close that gap
    we take a transaction-scoped Postgres advisory lock at the top of the check.
    ``enforce_seat_cap`` runs inside the request's DB session/transaction and the
    caller commits the insert/activation on that SAME session with no
    intermediate commit, so the xact lock is held until that commit. A second
    concurrent request therefore blocks here until the first commits, then its
    count reflects the newly-added seat and it correctly 403s. The lock
    auto-releases at commit/rollback — no explicit unlock needed.

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

    # Serialize concurrent seat checks+writes. pg_advisory_xact_lock is
    # Postgres-only; guard by dialect so sqlite / other backends no-op (the
    # lock is a safety net, not a correctness requirement for single-writer
    # test backends).
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": _SEAT_LOCK_KEY},
        )

    current_active_staff = count_active_staff(db, exclude_user_id=exclude_user_id)

    # The action would add one more active staff seat. Block only if that pushes
    # the count above the cap (i.e. current already >= cap).
    if current_active_staff >= cap:
        raise HTTPException(
            status_code=403,
            detail=SEAT_LIMIT_MESSAGE,
        )
