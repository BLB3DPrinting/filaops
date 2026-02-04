"""
Pro-tier analytics endpoints
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_admin_user
from app.core.features import Tier, require_tier
from app.db.session import get_db
from app.models.user import User
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


class RevenueMetrics(BaseModel):
    total_revenue: Decimal
    period_revenue: Decimal
    revenue_30_days: Decimal
    revenue_90_days: Decimal
    revenue_365_days: Decimal
    average_order_value: Decimal
    revenue_growth: Optional[float] = None


class CustomerMetrics(BaseModel):
    total_customers: int
    active_customers_30_days: int
    new_customers_30_days: int
    average_customer_value: Decimal
    top_customers: list[dict]


class ProductMetrics(BaseModel):
    total_products: int
    top_selling_products: list[dict]
    low_stock_count: int
    products_with_bom: int


class ProfitMetrics(BaseModel):
    total_cost: Decimal
    total_revenue: Decimal
    gross_profit: Decimal
    gross_margin: float
    profit_by_product: list[dict]


class AnalyticsDashboard(BaseModel):
    revenue: RevenueMetrics
    customers: CustomerMetrics
    products: ProductMetrics
    profit: ProfitMetrics
    period_start: datetime
    period_end: datetime


@router.get("/dashboard", response_model=AnalyticsDashboard)
@require_tier(Tier.PRO)
async def get_analytics_dashboard(
    days: int = 30,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Get comprehensive analytics dashboard (Pro feature)

    Returns revenue, customer, product, and profit metrics
    """
    return analytics_service.get_analytics_dashboard(db, days=days)

