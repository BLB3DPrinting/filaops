"""
Releasing an MRP planned order (print-batch plan S1).

Two rules live here so services/mrp.py stays small:

- ``MRP_RELEASE_COPIES_ROUTING``: when on, a released production-type planned
  order is built by ``production_order_service.create_production_order``, the
  path the UI uses, so it gets its routing, routing operations, operation
  materials and material reservations. Off, ``MRPService`` keeps building the
  bare order it always has (``bom_id`` only).
- Partial release: ``resolve_release_quantity`` validates an optional release
  quantity against the planned quantity.

The flag is read through ``get_settings()`` at call time, never through
``app.services.mrp.settings``: existing tests replace that name with a
MagicMock, which would make any new flag read as on.
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models import PlannedOrder
from app.services import production_order_service


class InvalidReleaseQuantity(ValueError):
    """The release quantity is zero, negative, or more than the planned quantity."""


def copies_routing() -> bool:
    """True when MRP_RELEASE_COPIES_ROUTING is on."""
    return bool(get_settings().MRP_RELEASE_COPIES_ROUTING)


def resolve_release_quantity(
    planned_order: PlannedOrder,
    requested: Optional[Decimal],
) -> Decimal:
    """The quantity to release: the whole plan when none is requested.

    Raises InvalidReleaseQuantity for zero, a negative, or more than planned.
    """
    if requested is None:
        return planned_order.quantity
    quantity = Decimal(requested)
    if quantity <= 0 or quantity > planned_order.quantity:
        raise InvalidReleaseQuantity(
            f"Release quantity must be more than 0 and at most the planned "
            f"quantity ({planned_order.quantity}), got {quantity}"
        )
    return quantity


def create_full_production_order(
    db: Session,
    planned_order: PlannedOrder,
    quantity: Decimal,
    user_id: Optional[int],
) -> int:
    """Create the production order for a release with routing, operations and reservations.

    ``source`` stays ``mrp_planned`` (the value ``ProductionOrderSource``
    accepts and the flag-off path already writes). The BOM and the active
    routing are resolved by ``create_production_order`` itself; flushes only,
    the caller commits.
    """
    order = production_order_service.create_production_order(
        db,
        product_id=planned_order.product_id,
        quantity_ordered=quantity,
        created_by=str(user_id) if user_id else None,
        source="mrp_planned",
        due_date=planned_order.due_date,
        notes=f"Created from planned order {planned_order.id}",
    )
    return order.id
