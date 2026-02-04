"""
Analytics Service — dashboard metrics for revenue, customers, products, and profit.

Extracted from admin/analytics.py (ARCHITECT-003).
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import and_, func, literal
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.bom import BOM
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.user import User

logger = get_logger(__name__)


def _compute_revenue_metrics(
    db: Session, *, end_date: datetime, start_date: datetime, prev_start: datetime
) -> dict:
    """Compute revenue totals, period breakdowns, growth, and average order value."""
    completed_filter = SalesOrder.status == "completed"

    total_revenue = (
        db.query(func.sum(SalesOrder.total_price))
        .filter(completed_filter)
        .scalar()
        or Decimal("0")
    )

    period_revenue = (
        db.query(func.sum(SalesOrder.total_price))
        .filter(completed_filter, SalesOrder.created_at >= start_date)
        .scalar()
        or Decimal("0")
    )

    revenue_30 = (
        db.query(func.sum(SalesOrder.total_price))
        .filter(completed_filter, SalesOrder.created_at >= end_date - timedelta(days=30))
        .scalar()
        or Decimal("0")
    )

    revenue_90 = (
        db.query(func.sum(SalesOrder.total_price))
        .filter(completed_filter, SalesOrder.created_at >= end_date - timedelta(days=90))
        .scalar()
        or Decimal("0")
    )

    revenue_365 = (
        db.query(func.sum(SalesOrder.total_price))
        .filter(completed_filter, SalesOrder.created_at >= end_date - timedelta(days=365))
        .scalar()
        or Decimal("0")
    )

    prev_revenue = (
        db.query(func.sum(SalesOrder.total_price))
        .filter(
            completed_filter,
            and_(SalesOrder.created_at >= prev_start, SalesOrder.created_at < start_date),
        )
        .scalar()
        or Decimal("0")
    )

    revenue_growth = None
    if prev_revenue > 0:
        revenue_growth = float(((revenue_30 - prev_revenue) / prev_revenue) * 100)

    order_count = (
        db.query(func.count(SalesOrder.id))
        .filter(completed_filter, SalesOrder.created_at >= start_date)
        .scalar()
        or 0
    )
    avg_order_value = period_revenue / order_count if order_count > 0 else Decimal("0")

    return {
        "total_revenue": total_revenue,
        "period_revenue": period_revenue,
        "revenue_30_days": revenue_30,
        "revenue_90_days": revenue_90,
        "revenue_365_days": revenue_365,
        "average_order_value": avg_order_value,
        "revenue_growth": revenue_growth,
    }


def _compute_customer_metrics(
    db: Session, *, end_date: datetime, start_date: datetime, period_revenue: Decimal
) -> dict:
    """Compute customer counts, activity, and top-10 customers by revenue."""
    total_customers = (
        db.query(func.count(User.id))
        .filter(User.account_type == "customer")
        .scalar()
        or 0
    )

    active_customers = (
        db.query(func.count(func.distinct(SalesOrder.user_id)))
        .filter(
            SalesOrder.status == "completed",
            SalesOrder.created_at >= end_date - timedelta(days=30),
        )
        .scalar()
        or 0
    )

    new_customers = (
        db.query(func.count(User.id))
        .filter(User.account_type == "customer", User.created_at >= end_date - timedelta(days=30))
        .scalar()
        or 0
    )

    top_customers_rows = (
        db.query(
            User.company_name,
            User.id,
            func.sum(SalesOrder.total_price).label("revenue"),
        )
        .join(SalesOrder)
        .filter(SalesOrder.status == "completed", SalesOrder.created_at >= start_date)
        .group_by(User.id, User.company_name)
        .order_by(func.sum(SalesOrder.total_price).desc())
        .limit(10)
        .all()
    )

    top_customers = [
        {
            "customer_id": c.id,
            "company_name": c.company_name or "N/A",
            "revenue": float(c.revenue),
        }
        for c in top_customers_rows
    ]

    avg_customer_value = (
        period_revenue / active_customers if active_customers > 0 else Decimal("0")
    )

    return {
        "total_customers": total_customers,
        "active_customers_30_days": active_customers,
        "new_customers_30_days": new_customers,
        "average_customer_value": avg_customer_value,
        "top_customers": top_customers,
    }


def _compute_product_metrics(db: Session, *, start_date: datetime) -> dict:
    """Compute active product count, top sellers, low-stock count, and BOM coverage."""
    total_products = (
        db.query(func.count(Product.id))
        .filter(Product.active.is_(True))
        .scalar()
        or 0
    )

    top_products_rows = (
        db.query(
            Product.sku,
            Product.name,
            func.sum(SalesOrderLine.quantity).label("qty_sold"),
            func.sum(SalesOrderLine.total).label("revenue"),
        )
        .join(SalesOrderLine, Product.id == SalesOrderLine.product_id)
        .join(SalesOrder)
        .filter(SalesOrder.status == "completed", SalesOrder.created_at >= start_date)
        .group_by(Product.id, Product.sku, Product.name)
        .order_by(func.sum(SalesOrderLine.quantity).desc())
        .limit(10)
        .all()
    )

    top_selling_products = [
        {
            "sku": p.sku,
            "name": p.name,
            "quantity_sold": float(p.qty_sold),
            "revenue": float(p.revenue),
        }
        for p in top_products_rows
    ]

    low_stock_count = (
        db.query(func.count(func.distinct(Product.id)))
        .join(Inventory)
        .filter(Inventory.on_hand_quantity < Product.reorder_point)
        .scalar()
        or 0
    )

    products_with_bom = (
        db.query(func.count(func.distinct(BOM.product_id))).scalar() or 0
    )

    return {
        "total_products": total_products,
        "top_selling_products": top_selling_products,
        "low_stock_count": low_stock_count,
        "products_with_bom": products_with_bom,
    }


def _compute_profit_metrics(
    db: Session, *, start_date: datetime, period_revenue: Decimal
) -> dict:
    """Compute cost, gross profit, margin, and per-product profit breakdown."""
    safe_cost = func.coalesce(Product.standard_cost, literal(0))
    total_cost = (
        db.query(func.sum(SalesOrderLine.quantity * safe_cost))
        .join(Product)
        .join(SalesOrder)
        .filter(SalesOrder.status == "completed", SalesOrder.created_at >= start_date)
        .scalar()
        or Decimal("0")
    )

    gross_profit = period_revenue - total_cost
    gross_margin = float(gross_profit / period_revenue * 100) if period_revenue > 0 else 0.0

    profit_rows = (
        db.query(
            Product.sku,
            Product.name,
            func.sum(SalesOrderLine.quantity).label("qty"),
            func.sum(SalesOrderLine.total).label("revenue"),
            func.sum(SalesOrderLine.quantity * safe_cost).label("cost"),
        )
        .join(SalesOrderLine, Product.id == SalesOrderLine.product_id)
        .join(SalesOrder)
        .filter(SalesOrder.status == "completed", SalesOrder.created_at >= start_date)
        .group_by(Product.id, Product.sku, Product.name)
        .having(func.sum(SalesOrderLine.total) > 0)
        .order_by(
            (
                func.sum(SalesOrderLine.total)
                - func.sum(SalesOrderLine.quantity * safe_cost)
            ).desc()
        )
        .limit(10)
        .all()
    )

    profit_by_product = [
        {
            "sku": p.sku,
            "name": p.name,
            "quantity": float(p.qty),
            "revenue": float(p.revenue),
            "cost": float(p.cost),
            "profit": float(p.revenue - p.cost),
            "margin": float((p.revenue - p.cost) / p.revenue * 100) if p.revenue > 0 else 0.0,
        }
        for p in profit_rows
    ]

    return {
        "total_cost": total_cost,
        "total_revenue": period_revenue,
        "gross_profit": gross_profit,
        "gross_margin": gross_margin,
        "profit_by_product": profit_by_product,
    }


def get_analytics_dashboard(db: Session, *, days: int = 30) -> dict:
    """
    Compute comprehensive analytics dashboard metrics.

    Returns a dict matching the AnalyticsDashboard schema shape with keys:
    revenue, customers, products, profit, period_start, period_end.
    """
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    prev_start = start_date - timedelta(days=days)

    revenue = _compute_revenue_metrics(
        db, end_date=end_date, start_date=start_date, prev_start=prev_start
    )

    customers = _compute_customer_metrics(
        db,
        end_date=end_date,
        start_date=start_date,
        period_revenue=revenue["period_revenue"],
    )

    products = _compute_product_metrics(db, start_date=start_date)

    profit = _compute_profit_metrics(
        db, start_date=start_date, period_revenue=revenue["period_revenue"]
    )

    return {
        "revenue": revenue,
        "customers": customers,
        "products": products,
        "profit": profit,
        "period_start": start_date,
        "period_end": end_date,
    }
