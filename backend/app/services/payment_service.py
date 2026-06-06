"""Shared payment ledger helpers."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Integer, cast, func, text
from sqlalchemy.orm import Session

from app.models.payment import Payment
from app.models.sales_order import SalesOrder

_PAYMENT_NUMBER_LOCK_NAMESPACE = 74001


def sales_order_total(order: SalesOrder) -> Decimal:
    """Return the customer-facing order total, preserving valid zero totals."""
    if order.grand_total is not None:
        return order.grand_total
    if order.total_price is not None:
        return order.total_price
    return Decimal("0")


def completed_payment_totals_by_order(
    db: Session,
    order_ids: list[int],
) -> dict[int, Decimal]:
    """Return completed ledger payment totals keyed by sales order id."""
    if not order_ids:
        return {}

    rows = db.query(
        Payment.sales_order_id,
        func.coalesce(func.sum(Payment.amount), 0).label("paid"),
    ).filter(
        Payment.sales_order_id.in_(order_ids),
        Payment.status == "completed",
    ).group_by(Payment.sales_order_id).all()

    return {
        row.sales_order_id: row.paid or Decimal("0")
        for row in rows
    }


def outstanding_balance_summary(db: Session) -> tuple[Decimal, int]:
    """Calculate AR from completed payment ledger rows, not cached status labels."""
    orders = db.query(
        SalesOrder.id,
        SalesOrder.grand_total,
        SalesOrder.total_price,
    ).filter(
        SalesOrder.status.notin_(["cancelled"])
    ).all()

    payment_totals = completed_payment_totals_by_order(
        db,
        [order.id for order in orders],
    )

    total_outstanding = Decimal("0")
    orders_with_balance = 0
    for order in orders:
        paid = payment_totals.get(order.id, Decimal("0"))
        balance = max(sales_order_total(order) - paid, Decimal("0"))
        if balance > 0:
            total_outstanding += balance
            orders_with_balance += 1

    return total_outstanding, orders_with_balance


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

    order_total = sales_order_total(order)

    if total_paid <= 0:
        order.payment_status = "pending"
    elif total_paid >= order_total:
        order.payment_status = "paid"
        if not order.paid_at:
            order.paid_at = datetime.now(timezone.utc)
    else:
        order.payment_status = "partial"
