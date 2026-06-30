"""Shared payment ledger helpers."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Integer, cast, func, text
from sqlalchemy.orm import Session

from app.models.accounting import GLAccount, GLJournalEntry
from app.models.order_event import OrderEvent
from app.models.payment import Payment
from app.models.sales_order import SalesOrder
from app.services.transaction_service import TransactionService

_PAYMENT_NUMBER_LOCK_NAMESPACE = 74001

_CORE_SALES_ACCOUNTS = {
    "1000": ("Cash", "asset", None, True, "Cash on hand and in bank accounts"),
    "1100": ("Accounts Receivable", "asset", None, True, "Amounts owed by customers"),
    "1220": ("Finished Goods Inventory", "asset", None, True, "Finished goods held for sale"),
    "1230": ("Packaging Inventory", "asset", None, True, "Packaging materials inventory"),
    "2100": ("Sales Tax Payable", "liability", None, False, "Collected sales tax owed to government"),
    "4000": ("Sales Revenue", "revenue", "1", True, "Gross receipts from sales"),
    "4200": ("Shipping Revenue", "revenue", "1", False, "Shipping charges collected"),
    "5000": ("Cost of Goods Sold", "expense", "36", True, "Cost of goods sold for shipped products"),
    "5010": ("Shipping Supplies Expense", "expense", "22", False, "Packaging consumed when shipping"),
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


def ensure_core_sales_accounts(db: Session) -> None:
    """Public wrapper for services that need canonical sales accounts."""
    _ensure_core_sales_accounts(db)


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
    return TransactionService(db).create_journal_entry(
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
    return TransactionService(db).create_journal_entry(
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
    return TransactionService(db).create_journal_entry(
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


def record_payment_and_reconcile(
    db: Session,
    *,
    sales_order_id: int,
    amount: Decimal,
    payment_method: str,
    recorded_by_id: Optional[int] = None,
    payment_date: Optional[datetime] = None,
    transaction_id: Optional[str] = None,
    check_number: Optional[str] = None,
    notes: Optional[str] = None,
    invoice=None,
) -> Payment:
    """Canonical payment-recording path shared by both API entry points.

    Creates a Payment row with full attribution, posts GL entries
    (payment receipt + invoice receivable if a linked invoice is provided),
    updates the order's payment_status, records an OrderEvent on the order
    timeline, and reconciles the invoice's amount_paid / status.

    Multi-invoice rule: the ``invoice`` argument is the specific Invoice to
    reconcile.  When paying through the Invoices page the caller passes the
    open invoice directly.  When paying through the Payments/OrderDetail page
    ``invoice`` is None and invoice reconciliation is skipped (the invoice
    ``amount_paid`` will sync the next time it is re-opened, or when the
    invoice is explicitly paid via the Invoices page).  In practice each
    confirmed sales order has exactly one invoice (the service enforces a
    uniqueness constraint), so the two paths converge naturally.

    This function does NOT commit. Callers must call db.commit().
    """
    order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()
    if order is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Sales order {sales_order_id} not found")

    payment = Payment(
        payment_number=generate_payment_number(db),
        sales_order_id=order.id,
        recorded_by_id=recorded_by_id,
        amount=amount,
        payment_method=payment_method,
        payment_type="payment",
        status="completed",
        payment_date=payment_date or datetime.now(timezone.utc),
        transaction_id=transaction_id,
        check_number=check_number,
        notes=notes,
    )
    db.add(payment)
    db.flush()  # assign payment.id before GL posting

    # Update order payment_status (also posts unposted completed payments)
    update_order_payment_status(db, order)

    # Post payment receipt GL: DR 1000 Cash / CR 1100 AR
    post_payment_receipt(db, payment)

    # Record activity event on the order timeline
    event = OrderEvent(
        sales_order_id=order.id,
        user_id=recorded_by_id,
        event_type="payment_received",
        title="Payment received",
        description=f"{payment.payment_number}: ${payment.amount:.2f} via {payment.payment_method}",
        metadata_key="payment_number",
        metadata_value=payment.payment_number,
    )
    db.add(event)

    # Reconcile the linked invoice if one was provided
    if invoice is not None:
        _reconcile_invoice(db, invoice=invoice, payment=payment)

    return payment


def _reconcile_invoice(db: Session, *, invoice, payment: Payment) -> None:
    """Update invoice.amount_paid / status and post the AR accrual GL entry.

    Acquires a row-level lock (SELECT … FOR UPDATE) to prevent two concurrent
    payments from reading the same starting balance and both writing a lower
    final amount_paid than the true total.  The invoice object passed in may
    have been loaded without a lock earlier; we reload it under the lock so the
    increment is always based on the persisted value.

    Called only when an invoice is explicitly supplied (Invoices page path).
    The invoice receivable GL entry is idempotent (guarded by source_type/id).
    """
    from app.models.invoice import Invoice as _Invoice

    # Re-read under an exclusive row lock to prevent concurrent double-payment.
    locked = (
        db.query(_Invoice)
        .filter(_Invoice.id == invoice.id)
        .with_for_update()
        .first()
    )
    if locked is None:
        return  # invoice was deleted concurrently — skip

    new_paid = (locked.amount_paid or Decimal("0")) + _money(payment.amount)
    locked.amount_paid = new_paid
    locked.payment_method = payment.payment_method
    locked.payment_reference = payment.transaction_id or payment.check_number

    # Post invoice receivable: DR 1100 AR / CR 4000 Revenue + 2100 Tax + 4200 Shipping
    post_invoice_receivable(db, locked, user_id=payment.recorded_by_id)

    # Set invoice status
    if new_paid >= locked.total:
        locked.status = "paid"
        locked.paid_at = payment.payment_date or datetime.now(timezone.utc)
    elif new_paid > 0:
        locked.status = "partially_paid"


def resync_invoice_paid_from_payments(db: Session, *, sales_order_id: int):
    """Recompute the order's invoice amount_paid / status from its completed
    payments (refunds count as negative), under a row lock.

    Called after a payment is voided or refunded so the invoice's AR view
    matches the ledger. Previously void/refund reversed the GL and the order
    status but left the invoice marked Paid, understating AR and blocking
    re-payment (#846 audit). Drift-free: it sums the source-of-truth payments
    rather than incrementally adjusting, so repeated calls converge.

    Does NOT touch the invoice-receivable GL — the invoice is still issued
    (revenue earned, AR reopened by the reversed payment-receipt entry); only
    the invoice's bookkeeping metadata is synced. Does NOT commit.

    Returns the locked invoice, or None if the order has no invoice.
    """
    from app.models.invoice import Invoice as _Invoice

    locked = (
        db.query(_Invoice)
        .filter(_Invoice.sales_order_id == sales_order_id)
        .with_for_update()
        .first()
    )
    if locked is None:
        return None

    net = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.sales_order_id == sales_order_id,
        Payment.status == "completed",
    ).scalar()
    net = _money(net or 0)
    if net < 0:
        net = Decimal("0")

    locked.amount_paid = net
    if locked.total and net >= _money(locked.total):
        locked.status = "paid"
        if not locked.paid_at:
            locked.paid_at = datetime.now(timezone.utc)
    elif net > 0:
        locked.status = "partially_paid"
        locked.paid_at = None
    else:
        # Fully unpaid again — reopen AR. Keep an issued invoice at 'sent';
        # never resurrect a draft, and don't disturb void/cancelled invoices.
        if locked.status in ("paid", "partially_paid"):
            locked.status = "sent"
        locked.paid_at = None

    return locked
