"""
Sales Order Shared Helpers — cross-cutting primitives used by the sales order
service modules (lookup + event recording).

Moved verbatim from sales_order_service.py (DEBT-1 D1-A mechanical split).
"""
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.order_event import OrderEvent


# =============================================================================
# Event Recording
# =============================================================================

def record_order_event(
    db: Session,
    order_id: int,
    event_type: str,
    title: str,
    description: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    user_id: Optional[int] = None,
    metadata_key: Optional[str] = None,
    metadata_value: Optional[str] = None,
) -> OrderEvent:
    """
    Record an order event to the activity timeline.

    Called internally by status change, payment, and shipping endpoints.
    Does NOT commit - caller handles the transaction.
    """
    event = OrderEvent(
        sales_order_id=order_id,
        user_id=user_id,
        event_type=event_type,
        title=title,
        description=description,
        old_value=old_value,
        new_value=new_value,
        metadata_key=metadata_key,
        metadata_value=metadata_value,
    )
    db.add(event)
    return event


def get_sales_order(db: Session, order_id: int) -> SalesOrder:
    """Get a sales order by ID or raise 404."""
    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return order


def get_sales_order_with_lines(db: Session, order_id: int) -> SalesOrder:
    """Get a sales order with lines eagerly loaded."""
    order = db.query(SalesOrder).options(
        joinedload(SalesOrder.lines).joinedload(SalesOrderLine.product),
        joinedload(SalesOrder.user),
    ).filter(SalesOrder.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return order
