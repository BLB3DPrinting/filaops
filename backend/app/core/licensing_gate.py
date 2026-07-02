"""
Live licensing gate for FilaOps Core.

This is the ONE server-side entitlement check for PRO features. It reads the
current enabled-feature set from ``plugin_registry`` (which the installed PRO
plugin populates at startup via ``set_features``) and denies any request for a
feature that is not licensed.

Design:
- Source of truth is ``plugin_registry.get_features()`` — a plugin calls
  ``set_features([...])`` during ``register(app)``. Core alone ships with an
  empty feature list (community tier).
- ``require_feature(key)`` is a FastAPI dependency factory. Apply it either at
  the router level (``dependencies=[Depends(require_feature("accounting"))]``)
  or per-route.
- FAIL CLOSED: if the feature key is absent from the licensed set — including
  the common case of an empty list on an unlicensed/community install — the
  request is denied with HTTP 403. There is no "licensing disabled" escape
  hatch here; absence of an entitlement is a denial.

Usage:
    from app.core.licensing_gate import require_feature

    router = APIRouter(
        prefix="/accounting",
        dependencies=[Depends(require_feature("accounting"))],
    )
"""
from typing import Callable

from fastapi import HTTPException

from app.core import plugin_registry

# Standard denial message. Kept generic so it maps to any PRO feature key.
UPGRADE_MESSAGE = "This feature requires a FilaOps PRO license."


def feature_enabled(key: str) -> bool:
    """Return True iff ``key`` is in the currently licensed feature set.

    Fails closed: an empty or absent feature list yields False. This is the
    plain-Python predicate behind ``require_feature`` and is convenient for
    direct unit testing and for imperative checks inside a handler.
    """
    if not key:
        return False
    return key in plugin_registry.get_features()


def require_feature(key: str) -> Callable[[], None]:
    """FastAPI dependency factory that enforces a PRO feature entitlement.

    Reads the licensed feature set from ``plugin_registry`` on every request
    (so a plugin loaded at startup is honored, and community installs — which
    have an empty set — are denied). Raises HTTP 403 when ``key`` is not
    licensed.

    Args:
        key: The feature key to require (matches the PRO plugin's
             ``set_features`` keys, e.g. "accounting", "reports_advanced",
             "production_advanced").

    Returns:
        A dependency callable suitable for ``Depends(...)`` /
        ``dependencies=[...]``.
    """

    def _dependency() -> None:
        if not feature_enabled(key):
            raise HTTPException(status_code=403, detail=UPGRADE_MESSAGE)

    return _dependency
