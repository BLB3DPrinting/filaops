"""
Export Service

Handles data export queries for products and orders.
The endpoint layer handles CSV formatting and StreamingResponse.
Business logic extracted from ``admin/export.py``.
"""
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.sales_order import SalesOrder


def get_products_for_export(db: Session) -> List[Dict[str, Any]]:
    """Get active products with inventory totals for CSV export."""
    products = db.query(Product).filter(Product.active.is_(True)).all()

    rows = []
    for p in products:
        on_hand = sum(inv.on_hand_quantity for inv in p.inventory)
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
        query = query.filter(SalesOrder.created_at >= start_date)
    if end_date:
        query = query.filter(SalesOrder.created_at <= end_date)

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
