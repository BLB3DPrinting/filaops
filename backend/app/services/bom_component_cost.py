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
"""
from decimal import Decimal
from typing import Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.services.cost_basis import (
    normalize_unit,
    purchase_line_for_stock_quantity,
    standard_first_cost_per_stock_unit,
    stock_units_per_purchase_unit,
)
from app.services.inventory_helpers import is_material
from app.services.uom_service import INLINE_UOM_CONVERSIONS, convert_quantity_safe

_GRAMS_PER_KG = Decimal("1000")

# Purchase units whose standard cost is converted to $/KG for a material. A
# standard cost per KG is used as stored. So is one whose purchase unit is G,
# EA or a pack: the BOM has always read a material's standard cost as $/KG, and
# existing rows were entered that way whatever purchase unit they carry.
_CONVERTED_MASS_UNITS = ("LB", "OZ")


def _positive(value: Any) -> Optional[Decimal]:
    """The value as a Decimal when it is greater than zero, otherwise None."""
    if value is None:
        return None
    number = Decimal(str(value))
    return number if number > 0 else None


def _material_cost_per_kg(product: Any) -> Decimal:
    """A material's cost per KG: standard cost first, then average, then last.

    The standard cost is per purchase unit: per KG as stored, and per LB or OZ
    converted by weight. Average and last cost are per gram for every material,
    because receiving stores them that way (see the known limit in
    ``cost_basis``), so they are multiplied by 1000.
    """
    standard = _positive(getattr(product, "standard_cost", None))
    if standard is not None:
        purchase_unit = normalize_unit(getattr(product, "purchase_uom", None))
        if purchase_unit in _CONVERTED_MASS_UNITS:
            # Table factors are KG per unit, so this is (KG per KG) / (KG per LB).
            return standard * INLINE_UOM_CONVERSIONS["KG"]["factor"] / INLINE_UOM_CONVERSIONS[purchase_unit]["factor"]
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

    Tries the unit conversion first (KG to G). When there is none and the line
    is written in the component's purchase unit, the pack size is used, so a
    line of 1 BOX of a part bought in boxes of 12 is 12 EA.

    Returns ``(quantity, True)`` when converted or already in the stock unit,
    and ``(the quantity unchanged, False)`` when it cannot be converted.
    """
    stock_unit = getattr(component, "unit", None)
    if not line_unit or not stock_unit or line_unit.upper() == stock_unit.upper():
        return quantity, True

    converted, success = convert_quantity_safe(db, quantity, line_unit, stock_unit)
    if success:
        return converted, True

    purchase_unit = getattr(component, "purchase_uom", None)
    if purchase_unit and normalize_unit(line_unit) == normalize_unit(purchase_unit):
        units = stock_units_per_purchase_unit(component)
        if units is not None:
            return quantity * units, True
    return quantity, False


def suggested_purchase(component: Any, shortage: Any) -> Optional[dict]:
    """A purchase-order line that covers a shortage given in stock units.

    The quantity, unit and unit cost agree with each other and with what
    receiving can convert (``cost_basis.purchase_line_for_stock_quantity``):
    500 G of filament short is 0.5 KG at the per-KG price. None when nothing
    is short.
    """
    if component is None or not shortage or shortage <= 0:
        return None
    quantity, unit, unit_cost = purchase_line_for_stock_quantity(component, Decimal(str(shortage)))
    return {"quantity": float(quantity), "unit": unit, "unit_cost": float(unit_cost)}
