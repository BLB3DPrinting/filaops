"""
Accounting Service — trial balance, inventory valuation, ledger, fiscal periods.

Extracted from accounting.py (ARCHITECT-003).
"""
import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine, GLFiscalPeriod
from app.models.inventory import Inventory
from app.models.product import Product

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_period_name(year: int, period: int) -> str:
    """Convert year/period to human-readable name like 'January 2025'"""
    if not 1 <= period <= 12:
        return f"Period {period} {year}"
    return f"{calendar.month_name[period]} {year}"


def _build_period_response(db: Session, period: GLFiscalPeriod) -> dict:
    """Build FiscalPeriodResponse dict with journal entry stats."""
    # Get journal entry stats for this period
    je_stats = db.query(
        func.count(GLJournalEntry.id).label("count"),
        func.coalesce(func.sum(GLJournalEntryLine.debit_amount), Decimal("0")).label("total_dr"),
        func.coalesce(func.sum(GLJournalEntryLine.credit_amount), Decimal("0")).label("total_cr"),
    ).outerjoin(
        GLJournalEntryLine, GLJournalEntry.id == GLJournalEntryLine.journal_entry_id
    ).filter(
        GLJournalEntry.entry_date >= period.start_date,
        GLJournalEntry.entry_date <= period.end_date,
    ).first()

    # Get closed_by email if applicable
    closed_by_email = None
    if period.closed_by_user:
        closed_by_email = period.closed_by_user.email

    return {
        "id": period.id,
        "name": _get_period_name(period.year, period.period),
        "year": period.year,
        "period": period.period,
        "start_date": period.start_date,
        "end_date": period.end_date,
        "status": period.status,
        "closed_at": period.closed_at,
        "closed_by": closed_by_email,
        "journal_entry_count": je_stats.count or 0,
        "total_debits": Decimal(str(je_stats.total_dr or 0)),
        "total_credits": Decimal(str(je_stats.total_cr or 0)),
    }


# ---------------------------------------------------------------------------
# Trial Balance
# ---------------------------------------------------------------------------


def get_trial_balance(
    db: Session,
    *,
    as_of_date: date | None = None,
    include_zero_balances: bool = False,
) -> dict:
    """Generate a trial balance report. Returns dict matching TrialBalanceResponse."""
    if as_of_date is None:
        as_of_date = date.today()

    # Query to sum debits and credits by account
    # Use conditional sums so accounts with only future entries still appear
    query = db.query(
        GLAccount.account_code,
        GLAccount.name,
        GLAccount.account_type,
        func.coalesce(
            func.sum(
                case(
                    (GLJournalEntry.entry_date <= as_of_date, GLJournalEntryLine.debit_amount),
                    else_=Decimal("0"),
                )
            ),
            Decimal("0"),
        ).label("total_debits"),
        func.coalesce(
            func.sum(
                case(
                    (GLJournalEntry.entry_date <= as_of_date, GLJournalEntryLine.credit_amount),
                    else_=Decimal("0"),
                )
            ),
            Decimal("0"),
        ).label("total_credits"),
    ).outerjoin(
        GLJournalEntryLine, GLAccount.id == GLJournalEntryLine.account_id
    ).outerjoin(
        GLJournalEntry, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id
    ).group_by(
        GLAccount.id,
        GLAccount.account_code,
        GLAccount.name,
        GLAccount.account_type,
    ).order_by(
        GLAccount.account_code
    )

    results = query.all()

    accounts = []
    total_debits = Decimal("0")
    total_credits = Decimal("0")

    for row in results:
        debit_bal = Decimal(str(row.total_debits or 0))
        credit_bal = Decimal(str(row.total_credits or 0))

        # Calculate net balance based on account type
        # Assets/Expenses: DR increases, CR decreases -> net = DR - CR
        # Liabilities/Equity/Revenue: CR increases, DR decreases -> net = CR - DR
        if row.account_type in ("asset", "expense"):
            net_balance = debit_bal - credit_bal
            # Show as debit balance if positive
            if net_balance >= 0:
                display_debit = net_balance
                display_credit = Decimal("0")
            else:
                display_debit = Decimal("0")
                display_credit = abs(net_balance)
        else:  # liability, equity, revenue
            net_balance = credit_bal - debit_bal
            # Show as credit balance if positive
            if net_balance >= 0:
                display_debit = Decimal("0")
                display_credit = net_balance
            else:
                display_debit = abs(net_balance)
                display_credit = Decimal("0")

        # Skip zero balances unless requested
        if not include_zero_balances and display_debit == 0 and display_credit == 0:
            continue

        accounts.append({
            "account_code": row.account_code,
            "account_name": row.name,
            "account_type": row.account_type,
            "debit_balance": display_debit,
            "credit_balance": display_credit,
            "net_balance": net_balance,
        })

        total_debits += display_debit
        total_credits += display_credit

    variance = abs(total_debits - total_credits)
    is_balanced = variance < Decimal("0.01")  # Allow for rounding

    return {
        "as_of_date": as_of_date,
        "accounts": accounts,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "is_balanced": is_balanced,
        "variance": variance,
    }


# ---------------------------------------------------------------------------
# Inventory Valuation
# ---------------------------------------------------------------------------


def get_inventory_valuation(db: Session, *, as_of_date: date | None = None) -> dict:
    """Generate an inventory valuation report with GL reconciliation.
    Returns dict matching InventoryValuationResponse."""
    if as_of_date is None:
        as_of_date = date.today()

    # Define category mappings
    # item_type -> (category_name, gl_account_code)
    # Valid item_types: finished_good, component, supply, service (see Product model)
    # Note: WIP (1210) and Packaging (1230) GL accounts exist for journal entries
    # but have no corresponding item_type — they track cost flow, not inventory categories
    category_map = {
        "supply": ("Raw Materials", "1200"),
        "component": ("Components", "1200"),
        "finished_good": ("Finished Goods", "1220"),
    }

    categories = []
    total_inventory_value = Decimal("0")
    total_gl_balance = Decimal("0")

    for item_type, (category_name, gl_code) in category_map.items():
        # Get GL account
        gl_account = db.query(GLAccount).filter(
            GLAccount.account_code == gl_code
        ).first()

        if not gl_account:
            continue

        # Calculate inventory value from physical inventory
        # Sum of (on_hand_quantity * product.standard_cost) for all products of this type
        inventory_query = db.query(
            func.count(Inventory.id).label("item_count"),
            func.coalesce(func.sum(Inventory.on_hand_quantity), Decimal("0")).label("total_qty"),
            func.coalesce(
                func.sum(Inventory.on_hand_quantity * func.coalesce(Product.standard_cost, Decimal("0"))),
                Decimal("0")
            ).label("total_value"),
        ).join(
            Product, Inventory.product_id == Product.id
        ).filter(
            Product.item_type == item_type,
        )

        # Raw Materials category: only include products flagged as raw materials
        if item_type == "supply":
            inventory_query = inventory_query.filter(Product.is_raw_material.is_(True))

        inv_result = inventory_query.first()

        item_count = inv_result.item_count or 0
        total_qty = Decimal(str(inv_result.total_qty or 0))
        inventory_value = Decimal(str(inv_result.total_value or 0))

        # Calculate GL balance from journal entries up to as_of_date
        gl_query = db.query(
            func.coalesce(func.sum(GLJournalEntryLine.debit_amount), Decimal("0")).label("total_dr"),
            func.coalesce(func.sum(GLJournalEntryLine.credit_amount), Decimal("0")).label("total_cr"),
        ).join(
            GLJournalEntry, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id
        ).filter(
            GLJournalEntryLine.account_id == gl_account.id,
            GLJournalEntry.entry_date <= as_of_date,
        )

        gl_result = gl_query.first()

        total_dr = Decimal(str(gl_result.total_dr or 0))
        total_cr = Decimal(str(gl_result.total_cr or 0))

        # For asset accounts: balance = DR - CR
        gl_balance = total_dr - total_cr

        # Calculate variance
        variance = inventory_value - gl_balance
        variance_pct = None
        if gl_balance != 0:
            variance_pct = (variance / abs(gl_balance)) * 100
        elif inventory_value != 0:
            variance_pct = Decimal("100")  # 100% variance if GL is 0 but inventory exists

        categories.append({
            "category": category_name,
            "gl_account_code": gl_code,
            "gl_account_name": gl_account.name,
            "item_count": item_count,
            "total_quantity": total_qty,
            "inventory_value": inventory_value,
            "gl_balance": gl_balance,
            "variance": variance,
            "variance_pct": variance_pct,
        })

        total_inventory_value += inventory_value
        total_gl_balance += gl_balance

    total_variance = total_inventory_value - total_gl_balance

    # Consider reconciled if variance is less than $1 or 0.1%
    variance_threshold = max(Decimal("1.00"), abs(total_gl_balance) * Decimal("0.001"))
    is_reconciled = abs(total_variance) < variance_threshold

    return {
        "as_of_date": as_of_date,
        "categories": categories,
        "total_inventory_value": total_inventory_value,
        "total_gl_balance": total_gl_balance,
        "total_variance": total_variance,
        "is_reconciled": is_reconciled,
    }


# ---------------------------------------------------------------------------
# Transaction Ledger
# ---------------------------------------------------------------------------


def get_transaction_ledger(
    db: Session,
    account_code: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Get the transaction ledger for a specific GL account.
    Returns dict matching LedgerResponse."""
    # Get the account
    account = db.query(GLAccount).filter(
        GLAccount.account_code == account_code
    ).first()

    if not account:
        raise HTTPException(
            status_code=404,
            detail=f"GL Account {account_code} not found"
        )

    if start_date and end_date and end_date < start_date:
        raise HTTPException(
            status_code=400,
            detail="end_date must be on or after start_date"
        )

    # Build base query for transactions
    query = db.query(
        GLJournalEntry.entry_date,
        GLJournalEntry.entry_number,
        GLJournalEntry.description,
        GLJournalEntry.source_type,
        GLJournalEntry.source_id,
        GLJournalEntry.id.label("journal_entry_id"),
        GLJournalEntryLine.debit_amount,
        GLJournalEntryLine.credit_amount,
    ).join(
        GLJournalEntryLine, GLJournalEntry.id == GLJournalEntryLine.journal_entry_id
    ).filter(
        GLJournalEntryLine.account_id == account.id
    )

    # Apply date filters
    if start_date:
        query = query.filter(GLJournalEntry.entry_date >= start_date)
    if end_date:
        query = query.filter(GLJournalEntry.entry_date <= end_date)

    # Order by date, then entry number for consistent ordering
    query = query.order_by(
        GLJournalEntry.entry_date,
        GLJournalEntry.entry_number,
        GLJournalEntry.id,
    )

    # Get total count before pagination
    total_count = query.count()

    # Apply pagination
    results = query.offset(offset).limit(limit).all()

    # Calculate opening balance (all transactions before start_date)
    opening_balance = Decimal("0")
    if start_date:
        opening_query = db.query(
            func.coalesce(func.sum(GLJournalEntryLine.debit_amount), Decimal("0")).label("dr"),
            func.coalesce(func.sum(GLJournalEntryLine.credit_amount), Decimal("0")).label("cr"),
        ).join(
            GLJournalEntry, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id
        ).filter(
            GLJournalEntryLine.account_id == account.id,
            GLJournalEntry.entry_date < start_date,
        )

        opening_result = opening_query.first()
        if opening_result:
            dr = Decimal(str(opening_result.dr or 0))
            cr = Decimal(str(opening_result.cr or 0))
            # For assets/expenses: balance = DR - CR
            # For liabilities/equity/revenue: balance = CR - DR
            if account.account_type in ("asset", "expense"):
                opening_balance = dr - cr
            else:
                opening_balance = cr - dr

    # Build transactions with running balance
    transactions = []
    running_balance = opening_balance

    # Adjust running balance for skipped rows when paginating (offset > 0)
    if offset > 0:
        skipped_subq = query.limit(offset).subquery()
        skipped_sums = db.query(
            func.coalesce(func.sum(skipped_subq.c.debit_amount), Decimal("0")),
            func.coalesce(func.sum(skipped_subq.c.credit_amount), Decimal("0")),
        ).first()
        if skipped_sums:
            skipped_dr = Decimal(str(skipped_sums[0] or 0))
            skipped_cr = Decimal(str(skipped_sums[1] or 0))
            if account.account_type in ("asset", "expense"):
                running_balance += skipped_dr - skipped_cr
            else:
                running_balance += skipped_cr - skipped_dr

    total_debits = Decimal("0")
    total_credits = Decimal("0")

    for row in results:
        debit = Decimal(str(row.debit_amount or 0))
        credit = Decimal(str(row.credit_amount or 0))

        # Update running balance based on account type
        if account.account_type in ("asset", "expense"):
            running_balance = running_balance + debit - credit
        else:
            running_balance = running_balance + credit - debit

        total_debits += debit
        total_credits += credit

        transactions.append({
            "entry_date": row.entry_date,
            "entry_number": row.entry_number,
            "description": row.description or "",
            "debit": debit,
            "credit": credit,
            "running_balance": running_balance,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "journal_entry_id": row.journal_entry_id,
        })

    closing_balance = running_balance

    return {
        "account_code": account.account_code,
        "account_name": account.name,
        "account_type": account.account_type,
        "start_date": start_date,
        "end_date": end_date,
        "opening_balance": opening_balance,
        "transactions": transactions,
        "closing_balance": closing_balance,
        "total_debits": total_debits,
        "total_credits": total_credits,
        "transaction_count": total_count,
    }


# ---------------------------------------------------------------------------
# Fiscal Periods
# ---------------------------------------------------------------------------


def list_fiscal_periods(
    db: Session,
    *,
    year: int | None = None,
    status_filter: str | None = None,
) -> dict:
    """List all fiscal periods with summary information.
    Returns dict matching PeriodListResponse."""
    # Build query
    query = db.query(GLFiscalPeriod)

    if year:
        query = query.filter(GLFiscalPeriod.year == year)

    if status_filter:
        query = query.filter(GLFiscalPeriod.status == status_filter)

    query = query.order_by(GLFiscalPeriod.year.desc(), GLFiscalPeriod.period.desc())
    periods = query.all()

    # Build response with summary data for each period
    period_responses = []
    current_period = None
    today = date.today()

    for period in periods:
        period_resp = _build_period_response(db, period)
        period_responses.append(period_resp)

        # Check if this is the current period
        if period.start_date <= today <= period.end_date:
            current_period = period_resp

    return {
        "periods": period_responses,
        "current_period": current_period,
    }


def close_fiscal_period(
    db: Session,
    period_id: int,
    confirm: bool,
    admin_id: int,
) -> dict:
    """Close a fiscal period. Returns dict matching PeriodCloseResponse."""
    # Get the period
    period = db.query(GLFiscalPeriod).filter(GLFiscalPeriod.id == period_id).first()

    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")

    period_name = _get_period_name(period.year, period.period)

    if period.status == "closed":
        raise HTTPException(
            status_code=400,
            detail=f"Period {period_name} is already closed"
        )

    # Get journal entry count
    je_count = db.query(func.count(GLJournalEntry.id)).filter(
        GLJournalEntry.entry_date >= period.start_date,
        GLJournalEntry.entry_date <= period.end_date,
    ).scalar() or 0

    warnings = []

    # Check for unbalanced entries
    unbalanced_query = db.query(
        GLJournalEntry.id,
        GLJournalEntry.entry_number,
        func.sum(GLJournalEntryLine.debit_amount).label("dr"),
        func.sum(GLJournalEntryLine.credit_amount).label("cr"),
    ).join(
        GLJournalEntryLine, GLJournalEntry.id == GLJournalEntryLine.journal_entry_id
    ).filter(
        GLJournalEntry.entry_date >= period.start_date,
        GLJournalEntry.entry_date <= period.end_date,
    ).group_by(
        GLJournalEntry.id, GLJournalEntry.entry_number
    ).having(
        func.abs(func.sum(GLJournalEntryLine.debit_amount) - func.sum(GLJournalEntryLine.credit_amount)) > Decimal("0.01")
    )

    unbalanced = unbalanced_query.all()
    if unbalanced:
        entry_nums = [u.entry_number for u in unbalanced[:5]]  # Show first 5
        warnings.append(f"Warning: {len(unbalanced)} unbalanced entries found: {', '.join(entry_nums)}")

    # If not confirmed, return preview
    if not confirm:
        return {
            "success": False,
            "period_id": period.id,
            "period_name": period_name,
            "status": "preview",
            "message": f"Period {period_name} has {je_count} journal entries. Set confirm=true to close.",
            "journal_entry_count": je_count,
            "warnings": warnings,
        }

    # Block close if unbalanced entries exist
    if unbalanced:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot close period with {len(unbalanced)} unbalanced entries. Fix entries first."
        )

    # Close the period
    period.status = "closed"
    period.closed_at = datetime.now(timezone.utc)
    period.closed_by = admin_id
    db.commit()

    return {
        "success": True,
        "period_id": period.id,
        "period_name": period_name,
        "status": "closed",
        "message": f"Period {period_name} closed successfully",
        "journal_entry_count": je_count,
        "warnings": [],
    }


def reopen_fiscal_period(db: Session, period_id: int) -> dict:
    """Reopen a closed fiscal period. Returns dict matching PeriodCloseResponse."""
    period = db.query(GLFiscalPeriod).filter(GLFiscalPeriod.id == period_id).first()

    if not period:
        raise HTTPException(status_code=404, detail="Fiscal period not found")

    period_name = _get_period_name(period.year, period.period)

    if period.status == "open":
        raise HTTPException(
            status_code=400,
            detail=f"Period {period_name} is already open"
        )

    # Reopen the period
    period.status = "open"
    period.closed_at = None
    period.closed_by = None
    db.commit()

    # Get entry count for response
    je_count = db.query(func.count(GLJournalEntry.id)).filter(
        GLJournalEntry.entry_date >= period.start_date,
        GLJournalEntry.entry_date <= period.end_date,
    ).scalar() or 0

    return {
        "success": True,
        "period_id": period.id,
        "period_name": period_name,
        "status": "open",
        "message": f"Period {period_name} reopened successfully",
        "journal_entry_count": je_count,
        "warnings": ["Warning: Historical data can now be modified"],
    }


# ---------------------------------------------------------------------------
# Dashboard / Summary
# ---------------------------------------------------------------------------


def get_accounting_summary(db: Session) -> dict:
    """Get a quick financial summary for the dashboard.
    Returns dict matching AccountingSummaryResponse."""
    today = date.today()
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)

    # Inventory by category (valid item_types only)
    category_map = {
        "supply": "Raw Materials",
        "component": "Components",
        "finished_good": "Finished Goods",
    }

    inventory_by_category = []
    total_inventory_value = Decimal("0")

    for item_type, category_name in category_map.items():
        inv_query = db.query(
            func.count(Inventory.id).label("count"),
            func.coalesce(
                func.sum(Inventory.on_hand_quantity * func.coalesce(Product.standard_cost, Decimal("0"))),
                Decimal("0")
            ).label("value"),
        ).join(
            Product, Inventory.product_id == Product.id
        ).filter(
            Product.item_type == item_type,
            Product.active.is_(True),
        )

        # Raw Materials category: only include products flagged as raw materials
        if item_type == "supply":
            inv_query = inv_query.filter(Product.is_raw_material.is_(True))

        inv_result = inv_query.first()

        value = Decimal(str(inv_result.value or 0))
        count = inv_result.count or 0

        if value > 0 or count > 0:
            inventory_by_category.append({
                "category": category_name,
                "value": value,
                "item_count": count,
            })
            total_inventory_value += value

    # Current period
    current_period = db.query(GLFiscalPeriod).filter(
        GLFiscalPeriod.start_date <= today,
        GLFiscalPeriod.end_date >= today,
    ).first()

    current_period_name = None
    current_period_status = None
    if current_period:
        current_period_name = f"{current_period.year}-{current_period.period:02d}"
        current_period_status = current_period.status

    # Entry counts
    entries_today = db.query(func.count(GLJournalEntry.id)).filter(
        GLJournalEntry.entry_date == today
    ).scalar() or 0

    entries_this_week = db.query(func.count(GLJournalEntry.id)).filter(
        GLJournalEntry.entry_date >= week_ago
    ).scalar() or 0

    entries_this_month = db.query(func.count(GLJournalEntry.id)).filter(
        GLJournalEntry.entry_date >= month_start
    ).scalar() or 0

    # Balance check (sum all debits vs credits)
    balance_query = db.query(
        func.coalesce(func.sum(GLJournalEntryLine.debit_amount), Decimal("0")).label("dr"),
        func.coalesce(func.sum(GLJournalEntryLine.credit_amount), Decimal("0")).label("cr"),
    ).first()

    total_dr = Decimal(str(balance_query.dr or 0))
    total_cr = Decimal(str(balance_query.cr or 0))
    variance = abs(total_dr - total_cr)
    books_balanced = variance < Decimal("0.01")

    return {
        "as_of_date": today,
        "total_inventory_value": total_inventory_value,
        "inventory_by_category": inventory_by_category,
        "current_period": current_period_name,
        "current_period_status": current_period_status,
        "entries_today": entries_today,
        "entries_this_week": entries_this_week,
        "entries_this_month": entries_this_month,
        "books_balanced": books_balanced,
        "variance": variance,
    }


# ---------------------------------------------------------------------------
# Recent Entries
# ---------------------------------------------------------------------------


def get_recent_entries(db: Session, limit: int = 10) -> dict:
    """Get recent journal entries for dashboard display.
    Returns dict matching RecentEntriesResponse."""
    # Get total count
    total_count = db.query(func.count(GLJournalEntry.id)).scalar() or 0

    # Get recent entries with their totals
    entries_query = db.query(
        GLJournalEntry.id,
        GLJournalEntry.entry_number,
        GLJournalEntry.entry_date,
        GLJournalEntry.description,
        GLJournalEntry.source_type,
        GLJournalEntry.source_id,
        func.coalesce(func.sum(GLJournalEntryLine.debit_amount), Decimal("0")).label("total_amount"),
    ).outerjoin(
        GLJournalEntryLine, GLJournalEntry.id == GLJournalEntryLine.journal_entry_id
    ).group_by(
        GLJournalEntry.id,
        GLJournalEntry.entry_number,
        GLJournalEntry.entry_date,
        GLJournalEntry.description,
        GLJournalEntry.source_type,
        GLJournalEntry.source_id,
    ).order_by(
        GLJournalEntry.entry_date.desc(),
        GLJournalEntry.id.desc(),
    ).limit(limit)

    results = entries_query.all()

    entries = [
        {
            "id": row.id,
            "entry_number": row.entry_number,
            "entry_date": row.entry_date,
            "description": row.description or "",
            "total_amount": Decimal(str(row.total_amount or 0)),
            "source_type": row.source_type,
            "source_id": row.source_id,
        }
        for row in results
    ]

    return {
        "entries": entries,
        "total_count": total_count,
    }
