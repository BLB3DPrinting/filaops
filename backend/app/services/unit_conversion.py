"""
Unit conversion: the one place a quantity or a unit cost is converted.

An item has one stock unit. Anything entered in another unit goes through this
module, which answers "how many stock units is that" from two sources and no
others:

- the unit table (``units_of_measure``), which holds units with a fixed size
  and their exact factors, the same for every item;
- the item's own units (``product_units``), which hold the sizes only that
  item can know: its BOX of 12, its SHEET of 600 CM2.

``STANDARD_UNITS`` below is the only list of unit factors in the application
code. The unit table is filled from it. Do not write a factor, or a list of
unit codes, anywhere else.

Nothing here writes stock or changes a cost. A conversion that cannot be done
raises ``UnitConversionError``. It never hands the number back unchanged, with
one exception that exists only while the older callers are moved over:
``convert_or_keep``.
"""
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any, NamedTuple, Optional

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.product_unit import ProductUnit
from app.models.uom import UnitOfMeasure
from app.services.uom_service import UOMConversionError


class UnitConversionError(UOMConversionError):
    """A unit could not be converted. The message says which, and what to set."""


class StandardUnit(NamedTuple):
    """A unit every install has: its code, kind and exact factor to the kind's base unit."""
    code: str
    name: str
    symbol: str
    kind: str
    base: Optional[str]
    factor: Decimal


PACK = "pack"

# The international definitions, exact. A pack has no size of its own: its row
# stores 1 because the column cannot be empty, and nothing reads it.
STANDARD_UNITS = (
    StandardUnit("KG", "Kilogram", "kg", "weight", None, Decimal("1")),
    StandardUnit("G", "Gram", "g", "weight", "KG", Decimal("0.001")),
    StandardUnit("MG", "Milligram", "mg", "weight", "KG", Decimal("0.000001")),
    StandardUnit("LB", "Pound", "lb", "weight", "KG", Decimal("0.45359237")),
    StandardUnit("OZ", "Ounce", "oz", "weight", "KG", Decimal("0.028349523125")),
    StandardUnit("M", "Meter", "m", "length", None, Decimal("1")),
    StandardUnit("CM", "Centimeter", "cm", "length", "M", Decimal("0.01")),
    StandardUnit("MM", "Millimeter", "mm", "length", "M", Decimal("0.001")),
    StandardUnit("IN", "Inch", "in", "length", "M", Decimal("0.0254")),
    StandardUnit("FT", "Foot", "ft", "length", "M", Decimal("0.3048")),
    StandardUnit("M2", "Square meter", "m2", "area", None, Decimal("1")),
    StandardUnit("CM2", "Square centimeter", "cm2", "area", "M2", Decimal("0.0001")),
    StandardUnit("MM2", "Square millimeter", "mm2", "area", "M2", Decimal("0.000001")),
    StandardUnit("IN2", "Square inch", "in2", "area", "M2", Decimal("0.00064516")),
    StandardUnit("FT2", "Square foot", "ft2", "area", "M2", Decimal("0.09290304")),
    StandardUnit("L", "Liter", "L", "volume", None, Decimal("1")),
    StandardUnit("ML", "Milliliter", "mL", "volume", "L", Decimal("0.001")),
    StandardUnit("EA", "Each", "ea", "quantity", None, Decimal("1")),
    StandardUnit("HR", "Hour", "hr", "time", None, Decimal("1")),
    StandardUnit("MIN", "Minute", "min", "time", "HR", Decimal("0.016666666666667")),
    StandardUnit("BOX", "Box", "box", PACK, None, Decimal("1")),
    StandardUnit("PK", "Pack", "pk", PACK, None, Decimal("1")),
    StandardUnit("ROLL", "Roll", "roll", PACK, None, Decimal("1")),
    StandardUnit("SPOOL", "Spool", "spool", PACK, None, Decimal("1")),
    StandardUnit("SHEET", "Sheet", "sheet", PACK, None, Decimal("1")),
    StandardUnit("CASE", "Case", "case", PACK, None, Decimal("1")),
    StandardUnit("BAG", "Bag", "bag", PACK, None, Decimal("1")),
)

# What people type, and the code it means.
UNIT_SPELLINGS = {
    "PCS": "EA", "PC": "EA", "EACH": "EA", "UNIT": "EA", "UNITS": "EA",
    "PACK": "PK", "PACKS": "PK",
    "GRAM": "G", "GRAMS": "G",
    "KILOGRAM": "KG", "KILOGRAMS": "KG",
    "MILLIGRAM": "MG", "MILLIGRAMS": "MG",
}

_QUANTITY_PLACES = Decimal("0.000001")
_COST_PLACES = Decimal("0.00000001")
_CACHE_KEY = "unit_conversion.units"
_MADE_BY_TO_STOCK = object()


@dataclass(frozen=True)
class StockQuantity:
    """A quantity in an item's stock unit, with what was entered and the factor used.

    Only ``to_stock`` makes one, so holding one means the conversion was done.
    """
    quantity: Decimal
    unit: str
    factor: Decimal
    entered_quantity: Decimal
    entered_unit: str
    _made_by: Any = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._made_by is not _MADE_BY_TO_STOCK:
            raise TypeError("A StockQuantity is made by unit_conversion.to_stock, not built directly")


@dataclass(frozen=True)
class ItemUnit:
    """A unit an item can be entered in, and how many stock units one of it is.

    ``source`` says where the size comes from: ``stock`` (the stock unit
    itself), ``table`` (the unit table) or ``item`` (the item's own units).
    """
    unit_code: str
    name: str
    kind: Optional[str]
    stock_units_per_unit: Decimal
    source: str
    is_purchase_unit: bool


class _Unit(NamedTuple):
    code: str
    name: str
    kind: str
    factor: Decimal


def normalize_unit_code(code: Optional[str]) -> str:
    """Trim and upper-case a unit code, and read a known spelling as its code.

    A missing code comes back as an empty string. It is not guessed.
    """
    tidy = (code or "").strip().upper()
    return UNIT_SPELLINGS.get(tidy, tidy)


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Divide without the default 28-digit limit getting in the way of 15-place factors."""
    with localcontext() as context:
        context.prec = 50
        return numerator / denominator


def _units(db: Session) -> dict:
    """The active rows of the unit table by code, read once per session."""
    cached = db.info.get(_CACHE_KEY)
    if cached is not None:
        return cached
    rows = (
        db.query(UnitOfMeasure.code, UnitOfMeasure.name, UnitOfMeasure.uom_class, UnitOfMeasure.to_base_factor)
        .filter(UnitOfMeasure.active.is_(True))
        .order_by(UnitOfMeasure.id)
        .all()
    )
    units = {}
    for code, name, kind, factor in rows:
        key = (code or "").strip().upper()
        # A row typed in upper case wins over the same code in another spelling.
        if key and (key not in units or code == key):
            units[key] = _Unit(key, name, (kind or "").lower(), Decimal(str(factor)))
    db.info[_CACHE_KEY] = units
    return units


def forget_units(db: Session) -> None:
    """Drop the session's copy of the unit table, after writing to it with plain SQL."""
    db.info.pop(_CACHE_KEY, None)


@event.listens_for(Session, "after_flush")
def _forget_units_when_one_changes(session, flush_context):
    """Drop the session's copy of the unit table when a unit row was added or changed."""
    if _CACHE_KEY not in session.info:
        return
    changed = list(session.new) + list(session.dirty) + list(session.deleted)
    if any(isinstance(row, UnitOfMeasure) for row in changed):
        session.info.pop(_CACHE_KEY, None)


def unit_kind(db: Session, code: Optional[str]) -> Optional[str]:
    """The kind of a unit (weight, length, pack...), or None when the table does not know it."""
    unit = _units(db).get(normalize_unit_code(code))
    return unit.kind if unit else None


def require_known_unit(db: Session, code: Optional[str]) -> str:
    """Return the tidied code of a unit the table knows, or refuse."""
    tidy = normalize_unit_code(code)
    if not tidy:
        raise UnitConversionError("No unit was given.")
    if tidy not in _units(db):
        raise UnitConversionError(
            f"Unknown unit '{tidy}'. Use a unit from the unit table, or add this one under Units first."
        )
    return tidy


def physical_factor(db: Session, from_unit: Optional[str], to_unit: Optional[str]) -> Decimal:
    """How many ``to_unit`` are in one ``from_unit``, from the unit table alone.

    For code that has two unit names and no item. It never reads an item's own
    units, and it never converts a pack: a BOX has no size until an item gives
    it one.
    """
    source = normalize_unit_code(from_unit)
    target = normalize_unit_code(to_unit)
    if not source or not target:
        raise UnitConversionError("A unit is missing, so nothing can be converted.")
    if source == target:
        return Decimal("1")

    units = _units(db)
    if source not in units:
        raise UnitConversionError(f"Unknown unit: {source}")
    if target not in units:
        raise UnitConversionError(f"Unknown unit: {target}")

    from_row, to_row = units[source], units[target]
    for row in (from_row, to_row):
        if row.kind == PACK:
            raise UnitConversionError(
                f"{row.code} is a pack with no fixed size, so {source} cannot be converted to {target}. "
                f"Set its size on the item."
            )
    if from_row.kind != to_row.kind:
        raise UnitConversionError(
            f"Cannot convert between {from_row.kind} ({source}) and {to_row.kind} ({target})"
        )
    if to_row.factor <= 0:
        raise UnitConversionError(f"The unit table holds no usable factor for {target}.")
    return _divide(from_row.factor, to_row.factor)


def _stock_unit(product: Any) -> str:
    stock = normalize_unit_code(getattr(product, "unit", None))
    if not stock:
        raise UnitConversionError(f"Item {_label(product)} has no stock unit. Set one on the item.")
    return stock


def _label(product: Any) -> str:
    return getattr(product, "sku", None) or "(unsaved item)"


def _own_units(db: Session, product: Any) -> dict:
    """The item's own units by code: stock units in one of each."""
    product_id = getattr(product, "id", None)
    if product_id is None:
        return {}
    sizes = {}
    for row in db.query(ProductUnit).filter(ProductUnit.product_id == product_id).order_by(ProductUnit.id):
        if row.stock_units_per_unit is not None:
            size = Decimal(str(row.stock_units_per_unit))
        else:
            size = _divide(Decimal("1"), Decimal(str(row.units_per_stock_unit)))
        sizes[normalize_unit_code(row.unit_code)] = size
    return sizes


def stock_units_per(db: Session, product: Any, unit: Optional[str], *, line_factor: Any = None) -> Decimal:
    """How many of the item's stock units are in one ``unit``.

    The order, first match wins:

    1. ``unit`` is the item's stock unit: 1.
    2. Both are of the same kind in the unit table (KG and G): the table's
       factor. Never for a pack.
    3. ``line_factor`` was passed: that. It is the size a purchase order line
       was saved with. It is never typed on a line.
    4. The item has a unit of its own for ``unit``, or for another unit of the
       same kind: that size, through the table where needed.
    5. Otherwise it refuses.
    """
    stock = _stock_unit(product)
    entered = normalize_unit_code(unit)
    if not entered:
        raise UnitConversionError(f"No unit was given for item {_label(product)}.")
    if entered == stock:
        return Decimal("1")

    units = _units(db)
    entered_row, stock_row = units.get(entered), units.get(stock)
    if entered_row and stock_row and entered_row.kind == stock_row.kind and entered_row.kind != PACK:
        return physical_factor(db, entered, stock)

    if line_factor is not None and Decimal(str(line_factor)) > 0:
        return Decimal(str(line_factor))

    own = _own_units(db, product)
    if entered in own:
        return own[entered]
    if entered_row and entered_row.kind != PACK:
        for code, size in own.items():
            row = units.get(code)
            if row and row.kind == entered_row.kind:
                return physical_factor(db, entered, code) * size

    if entered_row and entered_row.kind != PACK and stock_row:
        raise UnitConversionError(
            f"{entered} is not a unit item {_label(product)} can be entered in. "
            f"It is stocked by the {stock}. Set how many {stock} are in one {entered} for this item."
        )
    raise UnitConversionError(
        f"Set how many {stock} are in one {entered} for this item ({_label(product)})."
    )


def to_stock(db: Session, product: Any, quantity: Any, unit: Optional[str], *, line_factor: Any = None) -> StockQuantity:
    """Convert a quantity entered in ``unit`` to the item's stock unit.

    A movement out is a negative quantity. The result is rounded half-up to
    6 decimal places; the factor is not rounded.
    """
    factor = stock_units_per(db, product, unit, line_factor=line_factor)
    entered = Decimal(str(quantity))
    return StockQuantity(
        quantity=(entered * factor).quantize(_QUANTITY_PLACES, rounding=ROUND_HALF_UP),
        unit=_stock_unit(product),
        factor=factor,
        entered_quantity=entered,
        entered_unit=normalize_unit_code(unit),
        _made_by=_MADE_BY_TO_STOCK,
    )


def from_stock(db: Session, product: Any, stock_quantity: Any, unit: Optional[str], *, line_factor: Any = None) -> Decimal:
    """Express a quantity held in the item's stock unit in ``unit``, to 6 decimal places."""
    factor = stock_units_per(db, product, unit, line_factor=line_factor)
    return _divide(Decimal(str(stock_quantity)), factor).quantize(_QUANTITY_PLACES, rounding=ROUND_HALF_UP)


def unit_cost_to_stock(db: Session, product: Any, cost_per_unit: Any, unit: Optional[str], *, line_factor: Any = None) -> Decimal:
    """Turn a cost per ``unit`` into a cost per stock unit, to 8 decimal places."""
    factor = stock_units_per(db, product, unit, line_factor=line_factor)
    return _divide(Decimal(str(cost_per_unit)), factor).quantize(_COST_PLACES, rounding=ROUND_HALF_UP)


def unit_cost_from_stock(db: Session, product: Any, cost_per_stock_unit: Any, unit: Optional[str], *, line_factor: Any = None) -> Decimal:
    """Turn a cost per stock unit into a cost per ``unit``, to 8 decimal places."""
    factor = stock_units_per(db, product, unit, line_factor=line_factor)
    return (Decimal(str(cost_per_stock_unit)) * factor).quantize(_COST_PLACES, rounding=ROUND_HALF_UP)


def units_for_item(db: Session, product: Any) -> list:
    """Every unit the item can be entered in, with its size in stock units. The stock unit is first."""
    stock = _stock_unit(product)
    units = _units(db)
    purchase = normalize_unit_code(getattr(product, "purchase_uom", None))
    found = {}

    def add(code: str, size: Decimal, source: str) -> None:
        if code in found:
            return
        row = units.get(code)
        found[code] = ItemUnit(
            unit_code=code,
            name=row.name if row else code,
            kind=row.kind if row else None,
            stock_units_per_unit=size,
            source=source,
            is_purchase_unit=(code == purchase),
        )

    add(stock, Decimal("1"), "stock")
    stock_row = units.get(stock)
    if stock_row and stock_row.kind != PACK:
        for code, row in sorted(units.items()):
            if row.kind == stock_row.kind:
                add(code, physical_factor(db, code, stock), "table")

    for own_code, size in _own_units(db, product).items():
        add(own_code, size, "item")
        own_row = units.get(own_code)
        if own_row and own_row.kind != PACK:
            for code, row in sorted(units.items()):
                if row.kind == own_row.kind:
                    add(code, physical_factor(db, code, own_code) * size, "item")
    return list(found.values())


def ensure_standard_units(db: Session) -> int:
    """Add any standard unit the table lacks, and return how many were added.

    An existing row is never changed here, whatever its factor or kind. The
    upgrade that corrects rounded factors is migration 106.
    """
    table = UnitOfMeasure.__table__
    existing = {
        (code or "").strip().upper(): unit_id
        for code, unit_id in db.execute(select(table.c.code, table.c.id))
    }
    missing = [unit for unit in STANDARD_UNITS if unit.code not in existing]
    if not missing:
        return 0

    def values(unit: StandardUnit) -> dict:
        return {
            "code": unit.code,
            "name": unit.name,
            "symbol": unit.symbol,
            "uom_class": unit.kind,
            "base_unit_id": existing.get(unit.base) if unit.base else None,
            "to_base_factor": unit.factor,
            "active": True,
        }

    # Base units first, so the others can point at them. Two statements in all.
    bases = [unit for unit in missing if unit.base is None]
    if bases:
        inserted = db.execute(
            table.insert().returning(table.c.code, table.c.id), [values(unit) for unit in bases]
        )
        existing.update({code: unit_id for code, unit_id in inserted})
    derived = [unit for unit in missing if unit.base is not None]
    if derived:
        db.execute(table.insert(), [values(unit) for unit in derived])
    forget_units(db)
    return len(missing)


def convert_or_keep(db: Session, quantity: Any, from_unit: Optional[str], to_unit: Optional[str]) -> tuple:
    """Convert by the unit table, or hand the number back unchanged with ``False``.

    Temporary. This is what the older converters did when they could not
    convert, and their callers are moved onto it so that they are all in one
    named place. Each caller is ended in a later stage of the unit conversion
    plan; do not add a new one.
    """
    if normalize_unit_code(from_unit) == normalize_unit_code(to_unit):
        return quantity, True
    try:
        factor = physical_factor(db, from_unit, to_unit)
    except UOMConversionError:
        return quantity, False
    return Decimal(str(quantity)) * factor, True
