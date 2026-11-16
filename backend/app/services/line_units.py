"""
The unit a BOM line or a routing material line is saved with.

Every writer that takes a line's unit from a request asks here, so there is
one rule and one message. The request schemas only tidy the code; whether the
unit exists is decided against the unit table, which an install can add to.
"""
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services.unit_conversion import UnitConversionError, require_known_unit


def unit_for_line(
    db: Session, requested: Optional[str], component: Any, *, current: Optional[str] = None
) -> str:
    """The unit to save on a line of ``component``.

    - No unit was given: the component's stock unit. That is what a line means
      when nobody picks a unit.
    - A unit was given: it has to be in the unit table. One that is not, or is
      switched off there, is refused with a 400 that names it.
    - ``current`` is the unit the line already holds. Sending it back is not a
      change, so a line saved before its unit left the table can still have its
      quantity edited.
    """
    if requested is None or not str(requested).strip():
        return getattr(component, "unit", None) or "EA"
    if current is not None and str(requested).strip().upper() == str(current).strip().upper():
        return current
    try:
        return require_known_unit(db, requested)
    except UnitConversionError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
