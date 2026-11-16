"""
The unit a BOM line or a routing material line is saved with.

Every writer that takes a line's unit from a request asks here, so there is
one rule and one message. The request schemas only tidy the code; whether the
unit exists is decided against the unit table, which an install can add to.
A writer that adds a quantity to a line that exists brings it into that
line's unit here too.
"""
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.services.unit_conversion import UnitConversionError, physical_factor, require_known_unit


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
      quantity edited. A caller passes it only while the line stays on the same
      component: a line moved to another component has its unit checked.

    The component's own stock unit is handed back as it is stored. Whether an
    item's units are in the unit table is the business of the item writers.
    Only the unit's existence is checked here, not whether it can be converted
    to the component's stock unit.
    """
    if requested is None or not str(requested).strip():
        return getattr(component, "unit", None) or "EA"
    if current is not None and str(requested).strip().upper() == str(current).strip().upper():
        return current
    try:
        return require_known_unit(db, requested)
    except UnitConversionError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


def quantity_in_line_unit(db: Session, quantity: Any, unit: Optional[str], line_unit: Optional[str]) -> Decimal:
    """A quantity given in ``unit``, expressed in the unit a line already holds.

    For adding to a line that exists: the line keeps its unit, and what is
    added is brought into it first. Adding the bare numbers would save 500 G
    plus 1 KG as 501. The unit table has to be able to convert one unit to the
    other, because lines do not read an item's own units yet. A pair it cannot
    convert is refused with a 400 that says what to do.
    """
    amount = Decimal(str(quantity))
    given, held = (unit or "").strip().upper(), (line_unit or "").strip().upper()
    if not given or given == held:
        return amount
    try:
        return amount * physical_factor(db, unit, line_unit)
    except UnitConversionError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"This component is already on the BOM in {line_unit}, and {given} cannot be converted to it "
                f"({error}). Give the quantity in {line_unit}, or change that line."
            ),
        ) from error
