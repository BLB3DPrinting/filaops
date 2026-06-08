"""Shared payment ledger helpers."""
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Integer, cast, func, text
from sqlalchemy.orm import Session

from app.models.accounting import GLAccount, GLJournalEntry
from app.models.payment import Payment
from app.models.sales_order import SalesOrder
from app.services.transaction_service import TransactionService

_PAYMENT_NUMBER_LOCK_NAMESPACE = 74001

_CORE_SALES_ACCOUNTS = {
    "1000": ("Cash", "asset", None, True, "Cash on hand and in bank accounts"),
    "1100": ("Accounts Receivable", "asset", None, True, "Amounts owed by customers"),
    "2100": ("Sales Tax Payable", "liability", None, False, "Collected sales tax owed to government"),
    "4000": ("Sales Revenue", "revenue", "1", True, "Gross receipts from sales"),
    "4200": ("Shipping Revenue", "revenue", "1", False, "Shipping charges collected"),
}


def _money(value) -> Decimal:
    """Normalize nullable numeric model values to GL currency precision."""
    return Decimal(str(value or "0")).quantize(Decimal("0.01"))


def _ensure_core_sales_accounts(db: Session) -> None:
    """Create missing canonical sales accounts for older local databases."""
    existing = {
        row[0]
        for row in db.query(GLAccount.account_code).filter(
            GLAccount.account_code.in_(_CORE_SALES_ACCOUNTS.keys())
        )
    }
    for code, (name, account_type, schedule_c_line, is_system, description) in _CORE_SALES_ACCOUNTS.items():
        if code in existing:
            continue
        db.add(GLAccount(
            account_code=code,
            name=name,
            account_type=account_type,
            schedule_c_line=schedule_c_line,
            is_system=is_system,
            active=True,
            description=description,
        ))
    db.flush()


def _posted_entry_exists(db: Session, *, source_type: str, source_id: int) -> bool:
    return db.query(GLJournalEntry.id).filter(
        GLJournalEntry.source_type == source_type,
        GLJournalEntry.source_id == source_id,
        GLJournalEntry.status != "voided",
    ).first() is not None


def post_invoice_receivable(db: Session, invoice, user_id: int | None = None) -> GLJournalEntry | None:
    """Post an invoice to AR, revenue, shipping revenue, and tax payable once."""
    if not invoice or not invoice.id:
        return None
    if _posted_entry_exists(db, source_type="invoice", source_id=invoice.id):
        return None

    revenue = max(_money(invoice.subtotal) - _money(invoice.discount_amount), Decimal("0"))
    tax = _money(invoice.tax_amount)
    shipping = _money(invoice.shipping_amount)

    credit_lines: list[tuple[str, Decimal, str]] = []
    if revenue > 0:
        credit_lines.append(("4000", revenue, "CR"))
    if tax > 0:
        credit_lines.append(("2100", tax, "CR"))
    if shipping > 0:
        credit_lines.append(("4200", shipping, "CR"))

    receivable = sum((amount for _, amount, _ in credit_lines), Decimal("0"))
    if receivable <= 0:
        return None

    _ensure_core_sales_accounts(db)
    return TransactionService(db)._create_journal_entry(
        description=f"Invoice {invoice.invoice_number}",
        lines=[("1100", receivable, "DR"), *credit_lines],
        source_type="invoice",
        source_id=invoice.id,
        user_id=user_id,
    )


def post_payment_receipt(db: Session, payment: Payment) -> GLJournalEntry | None:
    """Post a completed payment or refund to cash and AR once."""
    if not payment or not payment.id or payment.status != "completed":
        return None
    if _posted_entry_exists(db, source_type="payment", source_id=payment.id):
        return None

    amount = _money(payment.amount)
    if amount == 0:
        return None

    absolute_amount = abs(amount)
    if amount > 0:
        lines = [
            ("1000", absolute_amount, "DR"),
            ("1100", absolute_amount, "CR"),
        ]
        description = f"Payment {payment.payment_number}"
    else:
        lines = [
            ("1100", absolute_amount, "DR"),
            ("1000", absolute_amount, "CR"),
        ]
        description = f"Refund {payment.payment_number}"

    _ensure_core_sales_accounts(db)
    return TransactionService(db)._create_journal_entry(
        description=description,
        lines=lines,
        source_type="payment",
        source_id=payment.id,
        user_id=payment.recorded_by_id,
    )


def reverse_payment_receipt(
    db: Session,
    payment: Payment,
    user_id: int | None = None,
    reason: str | None = None,
) -> GLJournalEntry | None:
    """Post a one-time reversal for a previously posted payment."""
    if not payment or not payment.id:
        return None
    if not _posted_entry_exists(db, source_type="payment", source_id=payment.id):
        return None
    if _posted_entry_exists(db, source_type="payment_reversal", source_id=payment.id):
        return None

    amount = _money(payment.amount)
    if amount == 0:
        return None

    absolute_amount = abs(amount)
    if amount > 0:
        lines = [
            ("1100", absolute_amount, "DR"),
            ("1000", absolute_amount, "CR"),
        ]
    else:
        lines = [
            ("1000", absolute_amount, "DR"),
            ("1100", absolute_amount, "CR"),
        ]

    _ensure_core_sales_accounts(db)
    description = f"Reverse payment {payment.payment_number}"
    if reason:
        description = f"{description}: {reason}"[:255]
    return TransactionService(db)._create_journal_entry(
        description=description,
        lines=lines,
        source_type="payment_reversal",
        source_id=payment.id,
        user_id=user_id,
    )


def post_completed_payments_for_order(db: Session, order_id: int) -> None:
    """Post all unposted completed payments for an order."""
    payments = db.query(Payment).filter(
        Payment.sales_order_id == order_id,
        Payment.status == "completed",
    ).all()
    for payment in payments:
        post_payment_receipt(db, payment)


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
    post_completed_payments_for_order(db, order.id)

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
