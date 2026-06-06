"""Shared payment ledger helpers."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Integer, cast, func, text
from sqlalchemy.orm import Session

from app.models.payment import Payment
from app.models.sales_order import SalesOrder

_PAYMENT_NUMBER_LOCK_NAMESPACE = 74001


def generate_payment_number(db: Session) -> str:
    """Generate next payment number under a transaction-scoped DB lock."""
    year = datetime.now(timezone.utc).year
    prefix = f"PAY-{year}-"

    db.execute(
        text(
            """
            SELECT pg_advisory_xact_lock(
                CAST(:namespace AS integer),
                CAST(:year AS integer)
            )
            """
        ),
        {"namespace": _PAYMENT_NUMBER_LOCK_NAMESPACE, "year": year},
    )

    sequence_value = cast(func.replace(Payment.payment_number, prefix, ""), Integer)
    max_seq = (
        db.query(func.max(sequence_value))
        .filter(
            Payment.payment_number.like(f"{prefix}%"),
            Payment.payment_number.op("~")(rf"^PAY-{year}-\d+$"),
        )
        .scalar()
        or 0
    )

    return f"{prefix}{max_seq + 1:04d}"


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
