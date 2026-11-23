"""
The rules for changing the unit table itself (the admin unit endpoints).

The unit table is shared by every item, so a change to it changes every
conversion through it:

- **A standard unit** (one of ``STANDARD_UNITS``, under its own kind) keeps its
  factor and cannot be switched off. Its name and symbol can change.
- **A new unit** is either a pack, which has no size until an item gives it
  one, or a unit of weight, length, area, volume or time with its factor to
  that kind's base unit, to at most 15 decimal places. A new counting unit is
  refused: it would convert to EA at whatever factor it was given, for every
  item. A new kind is refused, and so is a code the table already holds in any
  spelling, switched on or off.
- **A unit in use** (an item's stock or purchase unit, an item's own unit, or
  a BOM, routing or open purchase order line) cannot be switched off. A unit
  that is switched off can always be switched back on.

Errors are ``ItemUnitError``: a 400 whose detail is the sentence to show.
"""
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.uom import UnitOfMeasure
from app.services.item_unit_service import ItemUnitError
from app.services.unit_conversion import PACK, STANDARD_UNITS, UNIT_SPELLINGS, forget_units

_FACTOR_PLACES = 15
_FACTOR_MAX = Decimal("1e15")          # units_of_measure.to_base_factor is Numeric(30, 15)
_SCALED_NEW_KINDS = ("weight", "length", "area", "volume", "time")
_STANDARD = {(unit.code, unit.kind): unit for unit in STANDARD_UNITS}
_STANDARD_BASES = {unit.kind: unit.code for unit in STANDARD_UNITS if unit.base is None and unit.kind != PACK}


def _tidy(code: Optional[str]) -> str:
    return (code or "").strip().upper()


def _kind(row: UnitOfMeasure) -> str:
    return (row.uom_class or "").strip().lower()


def is_standard(row: UnitOfMeasure) -> bool:
    """True for one of the units every install has, filed under its own kind."""
    return (_tidy(row.code), _kind(row)) in _STANDARD


def find_unit(db: Session, code: Optional[str]) -> Optional[UnitOfMeasure]:
    """The row for a code in any spelling, switched on or off. The row in use wins."""
    rows = (
        db.query(UnitOfMeasure)
        .filter(func.upper(func.btrim(UnitOfMeasure.code)) == _tidy(code))
        .order_by(UnitOfMeasure.active.desc(), UnitOfMeasure.id)
        .all()
    )
    if not rows:
        return None
    candidates = [row for row in rows if row.active] or rows
    return next((row for row in candidates if row.code == _tidy(code)), candidates[0])


def _factor(value: Any) -> Decimal:
    try:
        factor = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ItemUnitError("The factor has to be a number.") from error
    if not factor.is_finite() or factor <= 0:
        raise ItemUnitError("The factor has to be greater than zero.")
    if factor >= _FACTOR_MAX:
        raise ItemUnitError("The factor is too large to record.")
    if -factor.as_tuple().exponent > _FACTOR_PLACES:
        raise ItemUnitError(f"The factor can have at most {_FACTOR_PLACES} decimal places.")
    return factor


def new_unit_values(
    db: Session,
    *,
    code: str,
    kind: str,
    factor: Any = None,
    base_unit_code: Optional[str] = None,
) -> dict:
    """Check a unit an install wants to add, and return the row's values."""
    tidy = _tidy(code)
    kind = (kind or "").strip().lower()
    if not tidy:
        raise ItemUnitError("A unit needs a code.")
    if find_unit(db, tidy) is not None:
        raise ItemUnitError(f"The unit table already has {tidy}. Switch it on or edit it instead of adding it again.")
    meant = UNIT_SPELLINGS.get(tidy)
    if meant and find_unit(db, meant) is not None:
        raise ItemUnitError(f"{tidy} is read as {meant}, which the unit table already has.")

    if kind == PACK:
        return {"code": tidy, "uom_class": PACK, "base_unit_id": None, "to_base_factor": Decimal("1")}
    if kind == "quantity":
        raise ItemUnitError(
            f"{tidy} would be a counting unit beside EA, and would convert to EA at one factor for every item. "
            f"Add it as a pack instead, and give each item its size."
        )
    if kind not in _SCALED_NEW_KINDS:
        raise ItemUnitError(
            f"'{kind}' is not a kind of unit FilaOps converts. Use pack, or one of: " + ", ".join(_SCALED_NEW_KINDS)
        )
    if factor is None:
        raise ItemUnitError(f"Give the factor: how many {_STANDARD_BASES.get(kind, 'base units')} one {tidy} is.")
    value = _factor(factor)

    base = find_unit(db, _STANDARD_BASES[kind])
    if base is None or not base.active or _kind(base) != kind:
        raise ItemUnitError(
            f"The unit table has no {_STANDARD_BASES[kind]} in use as the base of {kind}, so the factor of {tidy} "
            f"would mean nothing. Add or switch on {_STANDARD_BASES[kind]} first."
        )
    if base_unit_code and _tidy(base_unit_code) != _tidy(base.code):
        raise ItemUnitError(f"A {kind} unit's factor is to {_tidy(base.code)}, the base of {kind}.")
    return {"code": tidy, "uom_class": kind, "base_unit_id": base.id, "to_base_factor": value}


def unit_uses(db: Session, code: str) -> list:
    """What still uses a unit code, as short phrases. Empty when nothing does."""
    from app.models.bom import BOMLine
    from app.models.manufacturing import RoutingOperationMaterial
    from app.models.product import Product
    from app.models.product_unit import ProductUnit
    from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine

    tidy = _tidy(code)

    def same(column):
        return func.upper(func.btrim(column)) == tidy

    counts = (
        ("item(s) stocked in it", db.query(func.count(Product.id)).filter(same(Product.unit))),
        ("item(s) bought in it", db.query(func.count(Product.id)).filter(same(Product.purchase_uom))),
        ("item(s) with it as a unit of their own", db.query(func.count(ProductUnit.id)).filter(same(ProductUnit.unit_code))),
        ("BOM line(s)", db.query(func.count(BOMLine.id)).filter(same(BOMLine.unit))),
        ("routing material line(s)", db.query(func.count(RoutingOperationMaterial.id)).filter(
            same(RoutingOperationMaterial.unit))),
        ("open purchase order line(s)", db.query(func.count(PurchaseOrderLine.id))
            .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
            .filter(same(PurchaseOrderLine.purchase_unit),
                    PurchaseOrder.status.notin_(("received", "closed", "cancelled")))),
    )
    uses = []
    for label, query in counts:
        count = query.scalar()
        if count:
            uses.append(f"{count} {label}")
    return uses


def check_unit_update(db: Session, row: UnitOfMeasure, *, factor: Any = None, active: Optional[bool] = None) -> Optional[Decimal]:
    """Check a change to a unit's factor or switch. Returns the factor to store, or None to leave it."""
    code = _tidy(row.code)
    new_factor = None
    if factor is not None:
        value = _factor(factor)
        if is_standard(row):
            if value != Decimal(str(row.to_base_factor)):
                raise ItemUnitError(
                    f"{code} is a standard unit and its factor is fixed. Every conversion through it depends on it."
                )
        elif _kind(row) == PACK:
            raise ItemUnitError(f"{code} is a pack. A pack has no factor; each item gives it a size.")
        else:
            new_factor = value
    if active is False and row.active:
        if is_standard(row):
            raise ItemUnitError(f"{code} is a standard unit and cannot be switched off.")
        uses = unit_uses(db, code)
        if uses:
            raise ItemUnitError(f"{code} cannot be switched off while it is used by " + ", ".join(uses) + ".")
    forget_units(db)
    return new_factor
