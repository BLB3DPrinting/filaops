"""
Payment API Endpoints

Record, track, and manage payments for sales orders.
"""
from fastapi import APIRouter, HTTPException, Depends, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc
from typing import Optional
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging

from app.db.session import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.models.payment import Payment
from app.models.sales_order import SalesOrder
from app.models.order_event import OrderEvent
from app.services.payment_service import (
    outstanding_balance_summary,
    generate_payment_number,
    sales_order_total,
    update_order_payment_status,
)
from app.schemas.payment import (
    PaymentCreate,
    RefundCreate,
    PaymentUpdate,
    PaymentResponse,
    PaymentListResponse,
    PaymentSummary,
    PaymentDashboardStats,
)

router = APIRouter(prefix="/payments", tags=["payments"])
logger = logging.getLogger(__name__)


def payment_to_response(payment: Payment) -> PaymentResponse:
    """Convert Payment model to response schema"""
    return PaymentResponse(
        id=payment.id,
        payment_number=payment.payment_number,
        sales_order_id=payment.sales_order_id,
        order_number=payment.sales_order.order_number if payment.sales_order else None,
        amount=payment.amount,
        payment_method=payment.payment_method,
        payment_type=payment.payment_type,
        status=payment.status,
        transaction_id=payment.transaction_id,
        check_number=payment.check_number,
        notes=payment.notes,
        payment_date=payment.payment_date,
        created_at=payment.created_at,
        recorded_by_name=f"{payment.recorded_by.first_name} {payment.recorded_by.last_name}".strip() if payment.recorded_by else None,
    )


# ============================================================================
# CRUD Endpoints
# ============================================================================

@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def record_payment(
    payment_data: PaymentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Record a new payment for a sales order.

    Automatically updates the order's payment_status based on total paid.
    """
    # Verify order exists
    order = db.query(SalesOrder).filter(SalesOrder.id == payment_data.sales_order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sales order {payment_data.sales_order_id} not found"
        )

    # Create payment record
    payment = Payment(
        payment_number=generate_payment_number(db),
        sales_order_id=payment_data.sales_order_id,
        recorded_by_id=current_user.id,
        amount=payment_data.amount,
        payment_method=payment_data.payment_method,
        payment_type="payment",
        status="completed",
        payment_date=payment_data.payment_date or datetime.now(timezone.utc),
        transaction_id=payment_data.transaction_id,
        check_number=payment_data.check_number,
        notes=payment_data.notes,
    )

    db.add(payment)
    db.flush()  # Flush to make payment visible in subsequent queries

    # Update order payment status
    update_order_payment_status(db, order)

    # Record order event for activity timeline
    event = OrderEvent(
        sales_order_id=order.id,
        user_id=current_user.id,
        event_type="payment_received",
        title="Payment received",
        description=f"{payment.payment_number}: ${payment.amount:.2f} via {payment.payment_method}",
        metadata_key="payment_number",
        metadata_value=payment.payment_number,
    )
    db.add(event)

    db.commit()
    db.refresh(payment)

    logger.info(f"Payment {payment.payment_number} recorded for order {order.order_number} by {current_user.email}")

    return payment_to_response(payment)


@router.post("/refund", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def record_refund(
    refund_data: RefundCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Record a refund for a sales order.

    Amount is stored as negative value.
    """
    # Verify order exists
    order = db.query(SalesOrder).filter(SalesOrder.id == refund_data.sales_order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sales order {refund_data.sales_order_id} not found"
        )

    # Create refund record (negative amount)
    payment = Payment(
        payment_number=generate_payment_number(db),
        sales_order_id=refund_data.sales_order_id,
        recorded_by_id=current_user.id,
        amount=-abs(refund_data.amount),  # Always negative for refunds
        payment_method=refund_data.payment_method,
        payment_type="refund",
        status="completed",
        payment_date=refund_data.payment_date or datetime.now(timezone.utc),
        transaction_id=refund_data.transaction_id,
        notes=refund_data.notes,
    )

    db.add(payment)
    db.flush()  # Flush to make refund visible in subsequent queries

    # Update order payment status
    update_order_payment_status(db, order)

    # Record order event for activity timeline
    event = OrderEvent(
        sales_order_id=order.id,
        user_id=current_user.id,
        event_type="payment_refunded",
        title="Payment refunded",
        description=f"{payment.payment_number}: ${abs(payment.amount):.2f} via {payment.payment_method}",
        metadata_key="payment_number",
        metadata_value=payment.payment_number,
    )
    db.add(event)

    db.commit()
    db.refresh(payment)

    logger.info(f"Refund {payment.payment_number} recorded for order {order.order_number} by {current_user.email}")

    return payment_to_response(payment)


@router.get("", response_model=PaymentListResponse)
async def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    order_id: Optional[int] = None,
    payment_method: Optional[str] = None,
    status: Optional[str] = None,
    payment_type: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List payments with filtering and pagination.
    """
    query = db.query(Payment).options(
        joinedload(Payment.sales_order),
        joinedload(Payment.recorded_by)
    )

    # Apply filters
    if order_id:
        query = query.filter(Payment.sales_order_id == order_id)

    if payment_method:
        query = query.filter(Payment.payment_method == payment_method)

    if status:
        query = query.filter(Payment.status == status)

    if payment_type:
        query = query.filter(Payment.payment_type == payment_type)

    if from_date:
        query = query.filter(Payment.payment_date >= from_date)

    if to_date:
        query = query.filter(Payment.payment_date <= to_date)

    if search:
        search_filter = f"%{search}%"
        query = query.join(Payment.sales_order).filter(
            (Payment.payment_number.ilike(search_filter)) |
            (SalesOrder.order_number.ilike(search_filter)) |
            (Payment.transaction_id.ilike(search_filter))
        )

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    payments = query.order_by(desc(Payment.payment_date)).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    total_pages = (total + page_size - 1) // page_size

    return PaymentListResponse(
        items=[payment_to_response(p) for p in payments],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/dashboard", response_model=PaymentDashboardStats)
async def get_payment_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get payment dashboard statistics.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = today_start.replace(day=1)

    # Today's payments
    today_stats = db.query(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(
        Payment.payment_date >= today_start,
        Payment.status == "completed",
        Payment.payment_type == "payment"
    ).first()

    # This week's payments
    week_stats = db.query(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(
        Payment.payment_date >= week_start,
        Payment.status == "completed",
        Payment.payment_type == "payment"
    ).first()

    # This month's payments
    month_stats = db.query(
        func.count(Payment.id),
        func.coalesce(func.sum(Payment.amount), 0)
    ).filter(
        Payment.payment_date >= month_start,
        Payment.status == "completed",
        Payment.payment_type == "payment"
    ).first()

    # Outstanding balances are computed from the payment ledger so stale
    # SalesOrder.payment_status labels do not skew AR.
    total_outstanding, orders_with_balance = outstanding_balance_summary(db)

    # Payments by method (this month)
    by_method_query = db.query(
        Payment.payment_method,
        func.sum(Payment.amount)
    ).filter(
        Payment.payment_date >= month_start,
        Payment.status == "completed",
        Payment.payment_type == "payment"
    ).group_by(Payment.payment_method).all()

    by_method = {method: float(amount) for method, amount in by_method_query}

    return PaymentDashboardStats(
        payments_today=today_stats[0] or 0,
        amount_today=today_stats[1] or Decimal("0"),
        payments_this_week=week_stats[0] or 0,
        amount_this_week=week_stats[1] or Decimal("0"),
        payments_this_month=month_stats[0] or 0,
        amount_this_month=month_stats[1] or Decimal("0"),
        orders_with_balance=orders_with_balance,
        total_outstanding=total_outstanding,
        by_method=by_method,
    )


@router.get("/order/{order_id}/summary", response_model=PaymentSummary)
async def get_order_payment_summary(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get payment summary for a specific order.
    """
    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sales order not found"
        )

    # Get payment totals
    payments = db.query(Payment).filter(
        Payment.sales_order_id == order_id,
        Payment.status == "completed"
    ).all()

    total_paid = sum(p.amount for p in payments if p.amount > 0)
    total_refunded = abs(sum(p.amount for p in payments if p.amount < 0))
    order_total = sales_order_total(order)
    balance_due = max(order_total - total_paid + total_refunded, Decimal("0"))

    last_payment = db.query(Payment).filter(
        Payment.sales_order_id == order_id,
        Payment.status == "completed",
        Payment.payment_type == "payment"
    ).order_by(desc(Payment.payment_date)).first()

    return PaymentSummary(
        order_total=order_total,
        total_paid=total_paid,
        total_refunded=total_refunded,
        balance_due=balance_due,
        payment_count=len(payments),
        last_payment_date=last_payment.payment_date if last_payment else None,
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get a specific payment by ID.
    """
    payment = db.query(Payment).options(
        joinedload(Payment.sales_order),
        joinedload(Payment.recorded_by)
    ).filter(Payment.id == payment_id).first()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )

    return payment_to_response(payment)


@router.patch("/{payment_id}", response_model=PaymentResponse)
async def update_payment(
    payment_id: int,
    update_data: PaymentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update a payment record (limited to notes and status).
    """
    payment = db.query(Payment).options(
        joinedload(Payment.sales_order),
        joinedload(Payment.recorded_by)
    ).filter(Payment.id == payment_id).first()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )

    # Update allowed fields
    if update_data.notes is not None:
        payment.notes = update_data.notes

    if update_data.status is not None:
        old_status = payment.status
        payment.status = update_data.status

        # If status changed, update order payment status
        if old_status != update_data.status:
            update_order_payment_status(db, payment.sales_order)

    db.commit()
    db.refresh(payment)

    return payment_to_response(payment)


@router.delete("/{payment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def void_payment(
    payment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Void a payment (sets status to 'voided', doesn't delete).
    """
    payment = db.query(Payment).filter(Payment.id == payment_id).first()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )

    if payment.status == "voided":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment is already voided"
        )

    payment.status = "voided"

    # Update order payment status
    order = db.query(SalesOrder).filter(SalesOrder.id == payment.sales_order_id).first()
    if order:
        update_order_payment_status(db, order)

    db.commit()

    logger.info(f"Payment {payment.payment_number} voided by {current_user.email}")

    return None
