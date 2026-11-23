"""
Unit endpoints for any staff account.

- ``GET /api/v1/units``: the unit table, each row marked standard or not.
- ``GET /api/v1/items/{id}/units``: the units an item can be entered in, with
  their size in its stock unit, and whether its stock unit is locked.
- ``PUT`` / ``DELETE /api/v1/items/{id}/units/{unit_code}``: the item's own
  units (a BOX of 12, a spool of 750 G).

The admin endpoints under ``/admin/uom`` edit the unit table itself.
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_staff_user
from app.db.session import get_db
from app.models.product import Product
from app.models.product_unit import ProductUnit
from app.models.uom import UnitOfMeasure
from app.core.utils import get_or_404
from app.schemas.unit import ItemOwnUnit, ItemUnitRow, ItemUnitSize, ItemUnitsResponse, UnitRow
from app.services import item_unit_service as item_units
from app.services.unit_conversion import STANDARD_UNITS, UnitConversionError, units_for_item

router = APIRouter(dependencies=[Depends(get_current_staff_user)])
item_router = APIRouter(dependencies=[Depends(get_current_staff_user)])

_STANDARD = {(unit.code, unit.kind) for unit in STANDARD_UNITS}


@router.get("", response_model=List[UnitRow])
def list_units(db: Session = Depends(get_db)):
    """The units in use in the unit table, by kind and code."""
    rows = (
        db.query(UnitOfMeasure)
        .filter(UnitOfMeasure.active.is_(True))
        .order_by(UnitOfMeasure.uom_class, UnitOfMeasure.code)
        .all()
    )
    seen, result = set(), []
    for row in rows:
        code = (row.code or "").strip().upper()
        kind = (row.uom_class or "").strip().lower()
        if not code or code in seen:
            continue
        seen.add(code)
        result.append(UnitRow(
            code=code, name=row.name, symbol=row.symbol, kind=kind, is_standard=(code, kind) in _STANDARD,
        ))
    return result


def _item_units(db: Session, item: Product) -> ItemUnitsResponse:
    lock = item_units.stock_unit_lock(db, item)
    try:
        rows = units_for_item(db, item)
    except UnitConversionError:
        rows = []
    own = (
        db.query(ProductUnit)
        .filter(ProductUnit.product_id == item.id)
        .order_by(ProductUnit.unit_code)
        .all()
    )
    return ItemUnitsResponse(
        item_id=item.id,
        sku=item.sku,
        stock_unit=item.unit or "",
        purchase_unit=item.purchase_uom,
        stock_unit_locked=lock.locked,
        stock_unit_locked_reason=lock.reason,
        units=[ItemUnitRow(**row.__dict__) for row in rows],
        own_units=[
            ItemOwnUnit(
                unit_code=row.unit_code,
                stock_units_per_unit=row.stock_units_per_unit,
                units_per_stock_unit=row.units_per_stock_unit,
            )
            for row in own
        ],
    )


@item_router.get("/{item_id}/units", response_model=ItemUnitsResponse)
def get_item_units(item_id: int, db: Session = Depends(get_db)):
    """The units this item can be entered in, each with its size in the stock unit."""
    return _item_units(db, get_or_404(db, Product, item_id))


@item_router.put("/{item_id}/units/{unit_code}", response_model=ItemUnitsResponse)
def set_item_unit(item_id: int, unit_code: str, request: ItemUnitSize, db: Session = Depends(get_db)):
    """Add one of the item's own units, or change its size."""
    item = get_or_404(db, Product, item_id)
    item_units.set_item_unit(
        db,
        item,
        unit_code,
        stock_units_per_unit=request.stock_units_per_unit,
        units_per_stock_unit=request.units_per_stock_unit,
    )
    db.commit()
    db.refresh(item)
    return _item_units(db, item)


@item_router.delete("/{item_id}/units/{unit_code}", response_model=ItemUnitsResponse)
def delete_item_unit(item_id: int, unit_code: str, db: Session = Depends(get_db)):
    """Remove one of the item's own units. Refused while a line uses it or it is the purchase unit."""
    item = get_or_404(db, Product, item_id)
    item_units.remove_item_unit(db, item, unit_code)
    db.commit()
    db.refresh(item)
    return _item_units(db, item)
