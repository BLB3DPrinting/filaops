"""
Open production orders as incoming supply (print-batch plan S0b).

One place answers "how much of this product is already being made, and when?"
so MRP (`MRPService._get_incoming_supply`), supply netting
(`supply_netting.get_projected_available[_bulk]`) and the item demand summary
(`item_demand.get_incoming_supply`) cannot drift apart on the status set or the
date rule.

Rule, behind ``settings.MRP_OPEN_PO_SUPPLY`` (default False):

* Orders in ``OPEN_PRODUCTION_STATUSES`` contribute
  ``quantity_ordered - quantity_completed - quantity_scrapped`` of their
  product (nothing once that reaches zero). Scrapped units are never coming,
  and a scrap with a replacement order puts them on a separate order that
  counts for itself; item_demand's allocation query subtracts them the same
  way. ``complete``, ``short``, ``cancelled``, ``scrapped``, ``on_hold``,
  ``qc_hold`` and ``closed`` contribute nothing.
* An order linked to a sales order (``sales_order_id`` set) contributes
  nothing: its output is committed to that sale. MRP already leaves such a
  sales order out of demand (``_get_sales_orders_within_horizon``), so counting
  the output as supply would let it cover other demand for the same product.
  MRP-released and manual orders have no sales order and are the supply.
* The expected date is ``scheduled_end`` where set, else ``due_date``, else
  today.

With the flag off every function here returns an empty result without touching
the database, so the three callers behave exactly as they did before.

The flag is read here, through ``get_settings()``, and not through
``app.services.mrp.settings``: existing MRP tests replace that name with a
MagicMock, which would make any new attribute truthy.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.production_order import ProductionOrder

# `scheduled` is what schedule_production_order() writes (and the only thing
# that sets scheduled_end); leaving it out would drop a scheduled order from
# supply and plan it again.
OPEN_PRODUCTION_STATUSES = ("draft", "released", "scheduled", "in_progress")


@dataclass(frozen=True)
class OpenProductionSupply:
    """One open production order's remaining output."""
    production_order_id: int
    code: str
    product_id: int
    quantity: Decimal  # ordered - completed - scrapped, always > 0
    expected_date: date
    status: str


def is_enabled() -> bool:
    """True when MRP_OPEN_PO_SUPPLY is on."""
    return bool(get_settings().MRP_OPEN_PO_SUPPLY)


def expected_date_for(
    order: ProductionOrder,
    today: Optional[date] = None,
) -> date:
    """scheduled_end where set, else due_date, else today."""
    scheduled_end = order.scheduled_end
    if scheduled_end is not None:
        return scheduled_end.date() if isinstance(scheduled_end, datetime) else scheduled_end
    if order.due_date is not None:
        return order.due_date
    return today or date.today()


def get_open_production_supply(
    db: Session,
    product_ids: Iterable[int],
    today: Optional[date] = None,
) -> Dict[int, List[OpenProductionSupply]]:
    """
    Remaining output of open, unpegged production orders, per product,
    earliest first.

    Only products with something outstanding appear in the result. Empty when
    the flag is off or ``product_ids`` is empty (no query in either case).
    """
    ids = list(product_ids)
    if not ids or not is_enabled():
        return {}

    orders = (
        db.query(ProductionOrder)
        .filter(
            ProductionOrder.product_id.in_(ids),
            ProductionOrder.status.in_(OPEN_PRODUCTION_STATUSES),
            ProductionOrder.sales_order_id.is_(None),
            ProductionOrder.quantity_ordered
            > func.coalesce(ProductionOrder.quantity_completed, 0)
            + func.coalesce(ProductionOrder.quantity_scrapped, 0),
        )
        .all()
    )

    result: Dict[int, List[OpenProductionSupply]] = {}
    for order in orders:
        remaining = (
            Decimal(str(order.quantity_ordered or 0))
            - Decimal(str(order.quantity_completed or 0))
            - Decimal(str(order.quantity_scrapped or 0))
        )
        if remaining <= Decimal("0"):
            continue
        result.setdefault(order.product_id, []).append(
            OpenProductionSupply(
                production_order_id=order.id,
                code=order.code,
                product_id=order.product_id,
                quantity=remaining,
                expected_date=expected_date_for(order, today),
                status=order.status,
            )
        )

    for supplies in result.values():
        supplies.sort(key=lambda s: (s.expected_date, s.production_order_id))
    return result


def get_open_production_supply_qty(
    db: Session,
    product_ids: Iterable[int],
) -> Dict[int, Decimal]:
    """Total remaining output per product (same rule as the detail form)."""
    return {
        product_id: sum((s.quantity for s in supplies), Decimal("0"))
        for product_id, supplies in get_open_production_supply(db, product_ids).items()
    }
