"""
Transaction Audit Endpoints

Provides endpoints for auditing inventory transactions and finding gaps
in the order-to-ship lifecycle.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.transaction_audit_service import TransactionAuditService
from app.schemas.audit import (
    AuditTransactionsResponse,
    AuditTimelineResponse,
    AuditSummaryResponse,
)


router = APIRouter(prefix="/audit", tags=["Audit"])


@router.get("/transactions", response_model=AuditTransactionsResponse)
async def run_transaction_audit(
    db: Session = Depends(get_db),
    statuses: Optional[str] = Query(None, description="Comma-separated list of order statuses to check"),
    order_ids: Optional[str] = Query(None, description="Comma-separated list of order IDs to check"),
) -> AuditTransactionsResponse:
    """
    Run a transaction audit to find gaps in inventory tracking.

    Checks orders for:
    - Missing production orders
    - Missing material reservations
    - Missing material consumption
    - Missing finished goods receipts
    - Missing packaging consumption

    Args:
        statuses: Filter by order status (e.g., "in_production,ready_to_ship,shipped")
        order_ids: Check specific orders (e.g., "21,22,23")

    Returns:
        Audit results with summary and detailed gap list
    """
    service = TransactionAuditService(db)

    # Parse query params
    status_list = None
    if statuses:
        status_list = [s.strip() for s in statuses.split(",")]

    id_list = None
    if order_ids:
        try:
            id_list = [int(x.strip()) for x in order_ids.split(",")]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid order_ids format")

    result = service.run_full_audit(
        include_statuses=status_list,
        order_ids=id_list
    )

    return result.to_dict()


@router.get("/transactions/order/{order_id}", response_model=AuditTransactionsResponse)
async def audit_single_order(
    order_id: int,
    db: Session = Depends(get_db),
) -> AuditTransactionsResponse:
    """
    Audit a single order for transaction gaps.

    Returns detailed gap analysis for the specified order.
    """
    service = TransactionAuditService(db)
    result = service.audit_single_order(order_id)

    return result.to_dict()


@router.get("/transactions/timeline/{order_id}", response_model=AuditTimelineResponse)
async def get_order_timeline(
    order_id: int,
    db: Session = Depends(get_db),
) -> AuditTimelineResponse:
    """
    Get the complete transaction timeline for an order.

    Shows all inventory transactions in chronological order,
    useful for debugging what actually happened.
    """
    service = TransactionAuditService(db)
    timeline = service.get_transaction_timeline(order_id)

    return {
        "order_id": order_id,
        "transaction_count": len(timeline),
        "timeline": timeline,
    }


@router.get("/transactions/summary", response_model=AuditSummaryResponse)
async def get_audit_summary(
    db: Session = Depends(get_db),
) -> AuditSummaryResponse:
    """
    Get a quick summary of transaction health across all active orders.

    Returns counts by gap type for orders in:
    - in_production
    - ready_to_ship
    - shipped
    """
    service = TransactionAuditService(db)
    result = service.run_full_audit(
        include_statuses=['in_production', 'ready_to_ship', 'shipped']
    )

    return {
        "total_orders": result.total_orders_checked,
        "orders_with_issues": result.orders_with_gaps,
        "total_gaps": result.total_gaps,
        "gaps_by_type": result.summary_by_type,
        "health_score": round(
            (1 - (result.orders_with_gaps / max(result.total_orders_checked, 1))) * 100, 1
        ),
    }
