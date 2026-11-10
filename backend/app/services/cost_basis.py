"""
Cost basis: the one rule for "what does this product cost per stock unit".

The cost contract today:

  - ``standard_cost`` is per PURCHASE unit (``product.purchase_uom``, e.g. $/KG)
  - ``average_cost`` and ``last_cost`` are per STOCK unit (``product.unit``, e.g. $/G)
  - inventory quantities and ledger rows are in the STOCK unit

Every reader that multiplies a stock quantity by a cost must get that cost from
``cost_per_stock_unit``. Reading a cost column directly, or dividing by
``purchase_factor`` at the call site, is how the same filament came to be costed
1000x high in one screen and 1000x low in another.

Known limit: a material whose stock unit is a mass unit other than G (KG, LB,
OZ). PO receiving posts every material's quantity in grams and writes its
average_cost and last_cost per gram, whatever ``product.unit`` says, so for
those items "per stock unit" really means per gram and their on-hand quantity
is in grams. This module returns average_cost and last_cost as stored, exactly
as the code before it did, which is right against a gram quantity and wrong
against a quantity in ``product.unit``. Materials are created stocked in G by
default, where the two agree. Fixing the other case needs receiving to honour
the product's stock unit first.

This module is pure: it takes a product-like object and touches no database.
"""
from decimal import ROUND_HALF_UP, ROUND_UP, Decimal
from typing import Any, Optional, Tuple

from app.logging_config import get_logger
from app.services.uom_service import INLINE_UOM_CONVERSIONS

logger = get_logger(__name__)

# Count units people type that all mean "each".
_COUNT_SYNONYMS = {"PCS", "PC", "EACH", "UNIT", "UNITS"}

_FOUR_DP = Decimal("0.0001")


def normalize_unit(code: Optional[str]) -> str:
    """Upper-case and trim a unit code; a missing code or a count synonym is EA."""
    unit = (code or "EA").upper().strip() or "EA"
    return "EA" if unit in _COUNT_SYNONYMS else unit


def _positive_decimal(value: Any) -> Optional[Decimal]:
    """Return the value as a Decimal when it is greater than zero, otherwise None."""
    if value is None:
        return None
    number = Decimal(str(value))
    return number if number > 0 else None


def _raw_unit(code: Optional[str]) -> str:
    """Upper-case and trim only, so the code still matches the product's own."""
    return (code or "EA").upper().strip() or "EA"


def _class_conversion(product: Any) -> Optional[Decimal]:
    """
    Stock units per purchase unit when the two are the same unit or in the same
    measurement class (KG -> G is 1000). None when they are not, which is the
    pack case (BOX -> EA) and the G / EA / 1000 materials.
    """
    stock_unit = normalize_unit(getattr(product, "unit", None))
    purchase_unit = normalize_unit(getattr(product, "purchase_uom", None) or stock_unit)

    if purchase_unit == stock_unit:
        return Decimal("1")

    purchase_info = INLINE_UOM_CONVERSIONS.get(purchase_unit)
    stock_info = INLINE_UOM_CONVERSIONS.get(stock_unit)
    # Count units (EA, BOX, PK, ROLL) are each their own base in the table, so
    # only real measurement classes match here.
    if purchase_info and stock_info and purchase_info["base"] == stock_info["base"]:
        return purchase_info["factor"] / stock_info["factor"]
    return None


def stock_units_per_purchase_unit(product: Any) -> Optional[Decimal]:
    """
    How many stock units one purchase unit holds (KG -> G is 1000, BOX of 12 -> EA is 12).

    Resolution order:
      1. Same unit: 1.
      2. Both units in the same class (mass, length, volume): the physical
         conversion. This wins over ``purchase_factor``, because 1 KG is 1000 G
         whatever a mis-imported factor says.
      3. Otherwise ``purchase_factor`` (a pack size, or the G / EA / 1000
         materials the item form creates).

    Returns None when none of these applies: the purchase unit is a pack and no
    pack size is recorded.
    """
    units = _class_conversion(product)
    if units is not None:
        return units
    return _positive_decimal(getattr(product, "purchase_factor", None))


def _stored_stock_cost(product: Any) -> Optional[Decimal]:
    """The average or last cost the product's cost method uses, or None.

    ``average`` uses average_cost, then last_cost; ``fifo`` and ``last`` use
    last_cost. Both are stored per stock unit. None means the cost method
    is ``standard``, or nothing is stored, and standard_cost is used.
    """
    method = (getattr(product, "cost_method", None) or "average").lower()
    if method not in ("average", "fifo", "last"):
        return None
    average_cost = getattr(product, "average_cost", None)
    if method == "average" and average_cost is not None:
        return Decimal(str(average_cost))
    last_cost = getattr(product, "last_cost", None)
    if last_cost is not None:
        return Decimal(str(last_cost))
    return None


def uses_standard_cost(product: Any) -> bool:
    """Whether ``cost_per_stock_unit`` reads the product's standard_cost.

    False when the cost method prices it at a stored average or last cost,
    in which case a change to its standard cost changes nothing for readers
    of the shared rule.
    """
    return _stored_stock_cost(product) is None


def cost_per_stock_unit(product: Any) -> Optional[Decimal]:
    """
    The product's cost per stock unit, or None when it has no cost at all.

    ``average`` / ``fifo`` / ``last`` cost methods use average_cost (average
    only) and then last_cost, which are already per stock unit. Otherwise, and
    as the fallback, standard_cost is converted from the purchase unit.
    """
    stored = _stored_stock_cost(product)
    if stored is not None:
        return stored
    return _standard_cost_per_stock_unit(product)


def _standard_cost_per_stock_unit(product: Any) -> Optional[Decimal]:
    """standard_cost converted from the purchase unit to the stock unit, or None.

    When the purchase unit is a pack with no pack size recorded, the cost is
    returned unconverted and a warning is logged.
    """
    standard_cost = getattr(product, "standard_cost", None)
    if standard_cost is None:
        return None

    standard_cost = Decimal(str(standard_cost))
    units = stock_units_per_purchase_unit(product)
    if units is None:
        # Old pass-through kept for now: there is no screen yet where a user
        # can record a pack size, so refusing here would leave them stuck. Once
        # pack size can be entered, this becomes a refusal.
        logger.warning(
            "Cost basis: %s has standard_cost per %s but stock unit %s and no pack "
            "size; using the cost unconverted",
            getattr(product, "sku", "?"),
            normalize_unit(getattr(product, "purchase_uom", None)),
            normalize_unit(getattr(product, "unit", None)),
        )
        return standard_cost
    return standard_cost / units


def standard_first_cost_per_stock_unit(product: Any) -> Optional[Decimal]:
    """Cost per stock unit taking standard cost first, then average, then last.

    This is the order a BOM roll-up uses: it builds a standard cost, so it
    does not follow the item's cost method the way ``cost_per_stock_unit``
    does. Only positive costs count. The standard cost is converted from the
    purchase unit; average and last cost are already per stock unit. None
    when the product has no positive cost.
    """
    if _positive_decimal(getattr(product, "standard_cost", None)) is not None:
        return _standard_cost_per_stock_unit(product)
    for column in ("average_cost", "last_cost"):
        stock_cost = _positive_decimal(getattr(product, column, None))
        if stock_cost is not None:
            return stock_cost
    return None


def standard_cost_from_stock_cost(product: Any, stock_cost: Any) -> Decimal:
    """
    Express a cost per stock unit as a standard cost, which is per purchase unit.

    The inverse of the standard-cost branch of :func:`cost_per_stock_unit`:
    $0.01267/G for a filament bought by the KG is a $12.67 standard cost.
    Rounded to 4 decimal places, the precision of ``products.standard_cost``.
    Pass the unrounded stock cost where it is available, so the result is not
    built on a per-gram figure already rounded to 4 places.

    A pack purchase unit with no pack size is returned unscaled, matching the
    pass-through in ``cost_per_stock_unit`` so the two stay inverse.
    """
    stock_cost = Decimal(str(stock_cost))
    units = stock_units_per_purchase_unit(product)
    if units is None:
        units = Decimal("1")
    return (stock_cost * units).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)


def purchase_line_for_stock_quantity(
    product: Any, stock_quantity: Decimal
) -> Tuple[Decimal, str, Decimal]:
    """
    Turn a quantity in stock units into a purchase-order line.

    Returns ``(quantity, unit, unit_cost)`` with quantity and cost both in
    ``unit``, at 4 decimal places (the PO line columns). Quantity rounds up so
    the order never falls short of the requirement.

    The line is written in the purchase unit only when that unit is in the same
    measurement class as the stock unit (KG for a G item), because that is the
    only conversion PO receiving applies. A pack purchase unit (BOX of 12, or a
    G / EA / 1000 material) is written in the stock unit instead: receiving
    does not apply ``purchase_factor``, so a "5 BOX" line would be received as
    5 EA. The returned unit is the product's own code, so receiving sees it as
    equal to the product unit.
    """
    stock_quantity = Decimal(str(stock_quantity))
    stock_cost = cost_per_stock_unit(product) or Decimal("0")
    stock_unit = _raw_unit(getattr(product, "unit", None))

    units = _class_conversion(product)
    if units is None or units == 1:
        unit = stock_unit
        units = Decimal("1")
    else:
        unit = _raw_unit(getattr(product, "purchase_uom", None))

    quantity = (stock_quantity / units).quantize(_FOUR_DP, rounding=ROUND_UP)
    unit_cost = (stock_cost * units).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)
    return quantity, unit, unit_cost
