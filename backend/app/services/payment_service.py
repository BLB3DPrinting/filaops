"""Shared payment ledger helpers."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.models.payment import Payment
from app.models.sales_order import SalesOrder


def generate_payment_number(db: Session) -> str:
    """Generate next payment number: PAY-YYYY-NNNN."""
    year = datetime.now(timezone.utc).year
    prefix = f"PAY-{year}-"

    last_payment = db.query(Payment).filter(
        Payment.payment_number.like(f"{prefix}%")
    ).order_by(desc(Payment.payment_number)).first()

    if last_payment:
        try:
            seq = int(last_payment.payment_number.split("-")[2])
            next_seq = seq + 1
        except (IndexError, ValueError):
            next_seq = 1
    else:
        next_seq = 1

    return f"{prefix}{next_seq:04d}"


def update_order_payment_status(db: Session, order: SalesOrder) -> None:
    """Update order payment_status based on completed ledger payments."""
    total_paid = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.sales_order_id == order.id,
        Payment.status == "completed",
    ).scalar() or Decimal("0")

    order_total = (
        order.grand_total
        if order.grand_total is not None
        else (order.total_price or Decimal("0"))
    )

    if total_paid <= 0:
        order.payment_status = "pending"
    elif total_paid >= order_total:
        order.payment_status = "paid"
        if not order.paid_at:
            order.paid_at = datetime.now(timezone.utc)
    else:
        order.payment_status = "partial"
