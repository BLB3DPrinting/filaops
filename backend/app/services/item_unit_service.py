"""
An item's units: its stock unit, its purchase unit and its own units.

Every writer of those goes through here, so there is one set of rules and one
set of messages:

- **The lock.** An item's stock unit cannot change once the item has stock on
  hand or allocated, a ledger row, or a unit of its own. Everything stored
  about it is in that unit, and nothing rescales it. A change of spelling
  (``g`` to ``G``) is not a change.
- **Known units.** An item's stock unit and purchase unit must be units the
  unit table knows. A unit the item already holds can be sent back unchanged,
  so an item saved before its unit left the table can still be edited.
- **The default purchase unit.** A material stocked in G is bought by the KG;
  anything else is bought in its stock unit.
- **``purchase_factor``.** Kept in step with the purchase unit, for the code
  that still reads it: how many stock units one purchase unit is.
- **The item's own units** (``product_units``): a row only for a unit the unit
  table cannot convert to the stock unit, at most one per physical kind, and
  never for a unit a line of the item still uses when it is removed.

Errors are ``ItemUnitError``, a 400 whose detail is the sentence to show. The
imports catch it, report the row and carry on.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product_unit import ProductUnit
from app.services.unit_conversion import (
    PACK,
    UnitConversionError,
    physical_factor,
    require_known_unit,
    stock_units_per,
    tidy_unit_code,
    unit_kind,
)

_FACTOR_PLACES = Decimal("0.000001")      # products.purchase_factor is Numeric(18, 6)
_SIZE_PLACES = 10                         # product_units sizes are Numeric(20, 10)
_SIZE_MAX = Decimal("1e10")
_DEFAULT_MATERIAL_STOCK = "G"
_DEFAULT_MATERIAL_PURCHASE = "KG"
_NO_EA_HINT = (
    " This install has no EA unit. Add EA under Units, and set each of your own counting units "
    "to how many EA it is."
)


class ItemUnitError(HTTPException):
    """A unit an item writer refuses. ``detail`` is the sentence to show."""

    def __init__(self, message: str):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=message)

    @property
    def message(self) -> str:
        return str(self.detail)


@dataclass(frozen=True)
class StockUnitLock:
    """Whether an item's stock unit can still change, and why not."""
    locked: bool
    reason: Optional[str]


# ---------------------------------------------------------------------------
# Known units
# ---------------------------------------------------------------------------

def _same(db: Session, a: Optional[str], b: Optional[str]) -> bool:
    return bool(tidy_unit_code(db, a)) and tidy_unit_code(db, a) == tidy_unit_code(db, b)


def require_item_unit(db: Session, code: Optional[str], *, field: str = "unit", current: Optional[str] = None) -> str:
    """The code to store for an item's stock or purchase unit, or refuse.

    ``current`` is what the item holds now. Sending it back, in any spelling,
    is not a change and is accepted even when the table no longer knows it.
    """
    if current is not None and str(current).strip() and _same(db, code, current):
        return current
    try:
        return require_known_unit(db, code)
    except UnitConversionError as error:
        message = f"Item {field}: {error}"
        if tidy_unit_code(db, code) == "EA":
            message += _NO_EA_HINT
        raise ItemUnitError(message) from error


def default_purchase_unit(stock_unit: Optional[str], item_type: Any) -> Optional[str]:
    """The purchase unit an item gets when none is given.

    A material stocked in G is bought by the KG; anything else in its stock unit.
    """
    kind = getattr(item_type, "value", item_type)
    if str(kind or "").lower() == "material" and (stock_unit or "").strip().upper() == _DEFAULT_MATERIAL_STOCK:
        return _DEFAULT_MATERIAL_PURCHASE
    return stock_unit


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------

def stock_unit_lock(db: Session, product: Any) -> StockUnitLock:
    """Whether the item's stock unit is locked, and the reason in one sentence."""
    from app.models.inventory import Inventory, InventoryTransaction

    product_id = getattr(product, "id", None)
    if product_id is None:
        return StockUnitLock(False, None)

    on_hand, allocated = (
        db.query(
            func.coalesce(func.sum(Inventory.on_hand_quantity), 0),
            func.coalesce(func.sum(Inventory.allocated_quantity), 0),
        )
        .filter(Inventory.product_id == product_id)
        .one()
    )
    if Decimal(str(on_hand)) != 0 or Decimal(str(allocated)) != 0:
        return StockUnitLock(True, "it has stock on hand or allocated")
    if db.query(InventoryTransaction.id).filter(InventoryTransaction.product_id == product_id).first():
        return StockUnitLock(True, "it has inventory transactions")
    if db.query(ProductUnit.id).filter(ProductUnit.product_id == product_id).first():
        return StockUnitLock(True, "it has units of its own; remove them first")
    return StockUnitLock(False, None)


def check_stock_unit_change(db: Session, product: Any, new_unit: Optional[str]) -> str:
    """The stock unit to store when a writer sets ``new_unit`` on an existing item.

    A unit that only differs in spelling is not a change. A real change is
    refused while the item is locked, and otherwise needs a known unit.
    """
    current = getattr(product, "unit", None)
    if _same(db, new_unit, current):
        return current
    lock = stock_unit_lock(db, product)
    if lock.locked:
        raise ItemUnitError(
            f"The stock unit of {product.sku} cannot change from {current} to "
            f"{tidy_unit_code(db, new_unit) or new_unit}: {lock.reason}. Everything stored about how much of "
            f"it there is, is in {current}. To stock it in another unit, create a new item."
        )
    return require_item_unit(db, new_unit)


# ---------------------------------------------------------------------------
# purchase_factor
# ---------------------------------------------------------------------------

def purchase_size(db: Session, product: Any) -> Optional[Decimal]:
    """How many stock units one purchase unit is, or None when nothing says."""
    if not tidy_unit_code(db, getattr(product, "purchase_uom", None)):
        return None
    try:
        return stock_units_per(db, product, product.purchase_uom)
    except UnitConversionError:
        return None


def sync_purchase_factor(db: Session, product: Any, *, purchase_unit_changed: bool = True) -> None:
    """Keep ``purchase_factor`` in step with the purchase unit and its size.

    The size comes from the unit table for a unit of the same kind as the stock
    unit, and from the item's own unit otherwise. Where nothing gives a size
    (a BOX with no size on the item) a changed purchase unit clears the factor,
    so an old pack size is not read as the new unit's; an unchanged one keeps it.
    """
    size = purchase_size(db, product)
    if size is not None:
        rounded = size.quantize(_FACTOR_PLACES, rounding=ROUND_HALF_UP)
        if rounded > 0:
            product.purchase_factor = rounded
            return
    if purchase_unit_changed:
        product.purchase_factor = None


# ---------------------------------------------------------------------------
# The item's own units
# ---------------------------------------------------------------------------

def _size(value: Any, what: str) -> Decimal:
    try:
        size = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ItemUnitError(f"{what} has to be a number.") from error
    if not size.is_finite() or size <= 0:
        raise ItemUnitError(f"{what} has to be greater than zero.")
    if size >= _SIZE_MAX:
        raise ItemUnitError(f"{what} is too large to record.")
    if -size.as_tuple().exponent > _SIZE_PLACES:
        raise ItemUnitError(f"{what} can have at most {_SIZE_PLACES} decimal places.")
    return size


def _own_rows(db: Session, product_id: int) -> list:
    return (
        db.query(ProductUnit)
        .filter(ProductUnit.product_id == product_id)
        .order_by(ProductUnit.id)
        .all()
    )


def set_item_unit(
    db: Session,
    product: Any,
    unit_code: Optional[str],
    *,
    stock_units_per_unit: Any = None,
    units_per_stock_unit: Any = None,
) -> ProductUnit:
    """Add one of the item's own units, or change its size. Does not commit.

    Exactly one size is given, the way it was typed: ``stock_units_per_unit``
    for "1 BOX = 12 EA", ``units_per_stock_unit`` for "1 EA = 750 G" (on the G
    row of an item stocked by the each). A saved purchase order line keeps the
    size it was saved with, so a size can be changed while lines use the unit.
    """
    stock = getattr(product, "unit", None)
    code = require_item_unit(db, unit_code, field="unit of its own")
    if _same(db, code, stock):
        raise ItemUnitError(f"{code} is the stock unit of {product.sku}. One {code} is one {code}.")

    if (stock_units_per_unit is None) == (units_per_stock_unit is None):
        raise ItemUnitError(
            f"Give one size for {code}: how many {stock} are in one {code}, or how many {code} are in one {stock}."
        )
    if stock_units_per_unit is not None:
        per_unit, per_stock = _size(stock_units_per_unit, f"The number of {stock} in one {code}"), None
    else:
        per_unit, per_stock = None, _size(units_per_stock_unit, f"The number of {code} in one {stock}")

    try:
        physical_factor(db, code, stock)
    except UnitConversionError:
        pass
    else:
        raise ItemUnitError(
            f"The unit table already converts {code} to {stock}. An item has a size of its own only for a unit "
            f"the table cannot convert, such as a pack or a unit of another kind."
        )

    kind = unit_kind(db, code)
    rows = _own_rows(db, product.id)
    existing = next((row for row in rows if _same(db, row.unit_code, code)), None)
    if kind and kind != PACK:
        other = next(
            (row for row in rows if row is not existing and unit_kind(db, row.unit_code) == kind),
            None,
        )
        if other is not None:
            raise ItemUnitError(
                f"{product.sku} already has {other.unit_code} as its {kind} unit. A {kind} unit such as {code} "
                f"is reached through {other.unit_code} and the unit table, so it needs no size of its own."
            )

    if existing is None:
        existing = ProductUnit(product_id=product.id, unit_code=code)
        db.add(existing)
    existing.stock_units_per_unit = per_unit
    existing.units_per_stock_unit = per_stock
    db.flush()
    if _same(db, code, getattr(product, "purchase_uom", None)):
        sync_purchase_factor(db, product, purchase_unit_changed=False)
    return existing


def item_unit_uses(db: Session, product_id: int, unit_code: str) -> list:
    """What still uses one of an item's units, as short phrases. Empty when nothing does."""
    from app.models.bom import BOMLine
    from app.models.manufacturing import RoutingOperationMaterial
    from app.models.purchase_order import PurchaseOrderLine

    code = unit_code.strip().upper()
    checks = (
        ("purchase order line(s)", PurchaseOrderLine, PurchaseOrderLine.product_id, PurchaseOrderLine.purchase_unit),
        ("BOM line(s)", BOMLine, BOMLine.component_id, BOMLine.unit),
        (
            "routing material line(s)",
            RoutingOperationMaterial,
            RoutingOperationMaterial.component_id,
            RoutingOperationMaterial.unit,
        ),
    )
    uses = []
    for label, model, product_column, unit_column in checks:
        count = (
            db.query(func.count(model.id))
            .filter(product_column == product_id, func.upper(func.btrim(unit_column)) == code)
            .scalar()
        )
        if count:
            uses.append(f"{count} {label}")
    return uses


def remove_item_unit(db: Session, product: Any, unit_code: Optional[str]) -> None:
    """Remove one of the item's own units. Refused while anything uses it. Does not commit."""
    code = tidy_unit_code(db, unit_code)
    row = next((row for row in _own_rows(db, product.id) if _same(db, row.unit_code, code)), None)
    if row is None:
        raise ItemUnitError(f"{product.sku} has no unit {code or unit_code} of its own.")
    if _same(db, code, getattr(product, "purchase_uom", None)):
        raise ItemUnitError(
            f"{code} is the purchase unit of {product.sku}. Choose another purchase unit before removing it."
        )
    uses = item_unit_uses(db, product.id, row.unit_code)
    if uses:
        raise ItemUnitError(
            f"{code} cannot be removed from {product.sku}: it is used on " + ", ".join(uses) + "."
        )
    db.delete(row)
    db.flush()


def apply_item_units(db: Session, product: Any, units: Iterable[Any]) -> None:
    """Set each unit in ``units`` on a new item. Each has ``unit_code`` and one size. Does not commit."""
    for unit in units or ():
        get = unit.get if isinstance(unit, dict) else lambda name, unit=unit: getattr(unit, name, None)
        set_item_unit(
            db,
            product,
            get("unit_code"),
            stock_units_per_unit=get("stock_units_per_unit"),
            units_per_stock_unit=get("units_per_stock_unit"),
        )


def copy_item_units(db: Session, source_id: int, target: Any) -> int:
    """Copy an item's own units onto a copy of it (a duplicate or a variant). Does not commit.

    The rows were checked when they were written, and the copy has the same
    stock unit, so they are copied as they are.
    """
    copied = 0
    held = {row.unit_code for row in _own_rows(db, target.id)}
    for row in _own_rows(db, source_id):
        if row.unit_code in held:
            continue
        db.add(ProductUnit(
            product_id=target.id,
            unit_code=row.unit_code,
            stock_units_per_unit=row.stock_units_per_unit,
            units_per_stock_unit=row.units_per_stock_unit,
        ))
        copied += 1
    if copied:
        db.flush()
    return copied
