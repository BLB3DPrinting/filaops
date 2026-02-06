"""
Export Service

Handles data export queries for products and orders.
The endpoint layer handles CSV formatting and StreamingResponse.
Business logic extracted from ``admin/export.py``.
"""
from datetime import datetime as dt
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.product import Product
from app.models.sales_order import SalesOrder

_DANGEROUS_CSV_CHARS = {"=", "@", "+", "-", "\t", "\r"}


def sanitize_csv_field(value: Any) -> str:
    """Prevent CSV formula injection by prefixing dangerous chars.

    Strips leading whitespace before checking so that payloads like
    ``" =CMD()"`` cannot bypass the guard.  Returns the stripped
    version prefixed with ``'`` so no whitespace sits before the
    escape character.
    """
    if value is None:
        return ""
    s = str(value).lstrip()
    if s and s[0] in _DANGEROUS_CSV_CHARS:
        return "'" + s
    return s


def _parse_date(value: str) -> dt:
    """Parse an ISO date string, raising HTTP 400 on bad input.

    Strips timezone info so that comparisons against naive DB timestamps
    (``TIMESTAMP WITHOUT TIME ZONE``) don't raise ``TypeError``.
    """
    try:
        parsed = dt.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid date format: {value!r}")
    return parsed.replace(tzinfo=None)


def get_products_for_export(db: Session) -> List[Dict[str, Any]]:
    """Get active products with inventory totals for CSV export."""
    products = (
        db.query(Product)
        .options(joinedload(Product.inventory_items))
        .filter(Product.active.is_(True))
        .all()
    )

    rows = []
    for p in products:
        on_hand = sum(inv.on_hand_quantity for inv in p.inventory_items)
        rows.append({
            "sku": p.sku,
            "name": p.name,
            "description": p.description or "",
            "item_type": p.item_type,
            "procurement_type": p.procurement_type,
            "unit": p.unit,
            "standard_cost": p.standard_cost or 0,
            "selling_price": p.selling_price or 0,
            "on_hand_qty": on_hand,
            "reorder_point": p.reorder_point or 0,
            "active": p.active,
        })
    return rows


def get_orders_for_export(
    db: Session,
    *,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get sales orders (optionally filtered by date range) for CSV export."""
    query = db.query(SalesOrder)

    if start_date:
        query = query.filter(SalesOrder.created_at >= _parse_date(start_date))
    if end_date:
        query = query.filter(SalesOrder.created_at <= _parse_date(end_date))

    orders = query.all()

    rows = []
    for order in orders:
        line_items = ", ".join(
            f"{line.product_sku} x{line.quantity}" for line in order.lines
        )
        customer_name = (
            order.user.company_name
            if order.user and order.user.company_name
            else (order.user.email if order.user else "N/A")
        )
        rows.append({
            "order_number": order.order_number,
            "customer": customer_name,
            "status": order.status,
            "total": float(order.total_price) if order.total_price else 0,
            "created_at": order.created_at.strftime("%Y-%m-%d") if order.created_at else "",
            "line_items": line_items,
        })
    return rows
