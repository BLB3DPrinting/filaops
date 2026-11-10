"""
What a component costs on a BOM line, and how much of it the line uses.

A BOM roll-up is a standard-cost build-up: it takes a component's standard
cost first, then its average cost, then its last cost, whatever the item's
cost method. That order is the BOM's own and is kept here. What this module
adds is the unit handling the shared cost rule defines
(``app.services.cost_basis``): standard_cost is per PURCHASE unit, while
average_cost and last_cost are per STOCK unit.

Two shapes of figure leave this module, matching the two branches the BOM
service already has:

* a material (filament) is costed per KG and its line quantity is turned into
  grams (``bom_management_service.calculate_material_line_cost``);
* everything else is costed per stock unit and its line quantity is turned
  into stock units (``convert_line_quantity``).

Known limits, left for the cost-contract work:

* A material's standard cost is read as $/KG whatever its purchase unit. The
  material form and the material import store a price per KG there for every
  material, while a purchase-order receipt stores it per purchase unit, so
  for a material bought by the LB or OZ the two writers disagree and the
  stored figure cannot be told apart.
* A material stocked by the each has per-each costs. Its average or last cost
  is still multiplied by 1000 here; the line cost comes out right because the
  line-cost code divides an each quantity by 1000, but the unit cost shown is
  1000 times the per-each cost. With a standard cost it is costed as before.
"""
from decimal import Decimal
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.cost_basis import (
    normalize_unit,
    standard_first_cost_per_stock_unit,
    stock_units_per_purchase_unit,
)
from app.services.inventory_helpers import is_material
from app.services.uom_service import convert_quantity_safe

_GRAMS_PER_KG = Decimal("1000")


def _positive(value: Any) -> Optional[Decimal]:
    """The value as a Decimal when it is greater than zero, otherwise None."""
    if value is None:
        return None
    number = Decimal(str(value))
    return number if number > 0 else None


def _material_cost_per_kg(product: Any) -> Decimal:
    """A material's cost per KG: standard cost first, then average, then last.

    The standard cost is used as stored: the BOM has always read a material's
    standard cost as $/KG. Average and last cost are per gram for a material
    stocked by weight (G, KG, LB, OZ), because receiving stores them that way
    whatever the stock unit, so they are multiplied by 1000.
    """
    standard = _positive(getattr(product, "standard_cost", None))
    if standard is not None:
        return standard

    for column in ("average_cost", "last_cost"):
        per_gram = _positive(getattr(product, column, None))
        if per_gram is not None:
            return per_gram * _GRAMS_PER_KG
    return Decimal("0")


def component_cost_for_bom(product: Any) -> Decimal:
    """The cost a BOM line multiplies by: $/KG for a material, else per stock unit.

    Returns 0 when the component has no cost at all.
    """
    if is_material(product):
        return _material_cost_per_kg(product)
    return standard_first_cost_per_stock_unit(product) or Decimal("0")


def convert_line_quantity(
    db: Session, quantity: Decimal, line_unit: Optional[str], component: Any
) -> Tuple[Decimal, bool]:
    """Turn a BOM line quantity into the component's stock unit.

    A line written in the component's purchase unit uses the same figure the
    cost does (``cost_basis.stock_units_per_purchase_unit``): 1 BOX of a part
    bought in boxes of 12 is 12 EA, and 1 KG of a gram-stocked item is 1000 G.
    That comes first, so a unit-table row for BOX cannot disagree with the
    item's own pack size. Any other unit goes through the unit conversion.

    Returns ``(quantity, True)`` when converted or already in the stock unit,
    and ``(the quantity unchanged, False)`` when it cannot be converted.
    """
    stock_unit = getattr(component, "unit", None)
    if not line_unit or not stock_unit or line_unit.upper() == stock_unit.upper():
        return quantity, True

    purchase_unit = getattr(component, "purchase_uom", None)
    if purchase_unit and normalize_unit(line_unit) == normalize_unit(purchase_unit):
        units = stock_units_per_purchase_unit(component)
        if units is not None:
            return quantity * units, True

    return convert_quantity_safe(db, quantity, line_unit, stock_unit)
