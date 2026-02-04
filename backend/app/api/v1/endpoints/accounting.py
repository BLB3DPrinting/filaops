"""
Accounting API Endpoints

Provides financial reporting endpoints based on GL Journal Entries:
- Trial Balance
- Inventory Valuation (future)
- Transaction Ledger (future)

These endpoints query actual GL journal entries created by TransactionService.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.api.v1.endpoints.auth import get_current_admin_user
from app.models.user import User
from app.services import accounting_service

router = APIRouter()


# =============================================================================
# SCHEMAS
# =============================================================================

class TrialBalanceAccount(BaseModel):
    account_code: str
    account_name: str
    account_type: str
    debit_balance: Decimal
    credit_balance: Decimal
    net_balance: Decimal

    class Config:
        from_attributes = True


class TrialBalanceResponse(BaseModel):
    as_of_date: date
    accounts: List[TrialBalanceAccount]
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool
    variance: Decimal

    class Config:
        from_attributes = True


# =============================================================================
# INVENTORY VALUATION SCHEMAS
# =============================================================================

class InventoryCategory(BaseModel):
    """Inventory valuation by category"""
    category: str  # Raw Materials, WIP, Finished Goods, Packaging
    gl_account_code: str
    gl_account_name: str
    item_count: int
    total_quantity: Decimal
    inventory_value: Decimal  # Sum of (on_hand * cost) from Inventory table
    gl_balance: Decimal  # Balance from GL journal entries
    variance: Decimal  # inventory_value - gl_balance
    variance_pct: Optional[Decimal] = None  # Variance as percentage

    class Config:
        from_attributes = True


class InventoryValuationResponse(BaseModel):
    """Complete inventory valuation report"""
    as_of_date: date
    categories: List[InventoryCategory]
    total_inventory_value: Decimal
    total_gl_balance: Decimal
    total_variance: Decimal
    is_reconciled: bool  # True if variance < threshold

    class Config:
        from_attributes = True


# =============================================================================
# TRANSACTION LEDGER SCHEMAS
# =============================================================================

class LedgerTransaction(BaseModel):
    """Single transaction in the ledger"""
    entry_date: date
    entry_number: str
    description: str
    debit: Decimal
    credit: Decimal
    running_balance: Decimal
    source_type: Optional[str] = None  # purchase_order, production_order, sales_order, etc.
    source_id: Optional[int] = None
    journal_entry_id: int

    class Config:
        from_attributes = True


class LedgerResponse(BaseModel):
    """Complete ledger for an account"""
    account_code: str
    account_name: str
    account_type: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    opening_balance: Decimal
    transactions: List[LedgerTransaction]
    closing_balance: Decimal
    total_debits: Decimal
    total_credits: Decimal
    transaction_count: int

    class Config:
        from_attributes = True


# =============================================================================
# PERIOD MANAGEMENT SCHEMAS
# =============================================================================

class FiscalPeriodResponse(BaseModel):
    """Fiscal period details"""
    id: int
    name: str  # Derived from year/period: "January 2025"
    year: int
    period: int
    start_date: date
    end_date: date
    status: str  # open, closed
    closed_at: Optional[datetime] = None
    closed_by: Optional[str] = None  # User email
    journal_entry_count: int
    total_debits: Decimal
    total_credits: Decimal

    class Config:
        from_attributes = True


class PeriodListResponse(BaseModel):
    """List of fiscal periods"""
    periods: List[FiscalPeriodResponse]
    current_period: Optional[FiscalPeriodResponse] = None

    class Config:
        from_attributes = True


class PeriodCloseRequest(BaseModel):
    """Request to close a period"""
    confirm: bool = False  # Must be True to actually close

    class Config:
        from_attributes = True


class PeriodCloseResponse(BaseModel):
    """Result of period close operation"""
    success: bool
    period_id: int
    period_name: str
    status: str
    message: str
    journal_entry_count: int
    warnings: List[str] = []

    class Config:
        from_attributes = True


# =============================================================================
# DASHBOARD WIDGET SCHEMAS
# =============================================================================

class InventorySummaryItem(BaseModel):
    """Inventory value by category for dashboard"""
    category: str
    value: Decimal
    item_count: int

    class Config:
        from_attributes = True


class AccountingSummaryResponse(BaseModel):
    """Quick financial snapshot for dashboard"""
    as_of_date: date

    # Inventory totals
    total_inventory_value: Decimal
    inventory_by_category: List[InventorySummaryItem]

    # Period info
    current_period: Optional[str] = None
    current_period_status: Optional[str] = None

    # Activity metrics
    entries_today: int
    entries_this_week: int
    entries_this_month: int

    # Balance check
    books_balanced: bool
    variance: Decimal

    class Config:
        from_attributes = True


class RecentEntryItem(BaseModel):
    """Simplified journal entry for dashboard list"""
    id: int
    entry_number: str
    entry_date: date
    description: str
    total_amount: Decimal  # Sum of debits (= sum of credits)
    source_type: Optional[str] = None
    source_id: Optional[int] = None

    class Config:
        from_attributes = True


class RecentEntriesResponse(BaseModel):
    """List of recent journal entries"""
    entries: List[RecentEntryItem]
    total_count: int

    class Config:
        from_attributes = True


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get(
    "/trial-balance",
    response_model=TrialBalanceResponse,
    summary="Get GL Trial Balance",
    description="Returns the trial balance showing all GL account balances as of a given date."
)
async def get_trial_balance(
    as_of_date: Optional[date] = Query(None, description="Balance as of this date (default: today)"),
    include_zero_balances: bool = Query(False, description="Include accounts with zero balance"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Generate a trial balance report.

    The trial balance shows:
    - All GL accounts with their debit/credit balances
    - Total debits and credits (should be equal)
    - Whether the books are balanced

    For asset and expense accounts: normal balance is DEBIT
    For liability, equity, and revenue accounts: normal balance is CREDIT
    """
    return accounting_service.get_trial_balance(
        db,
        as_of_date=as_of_date,
        include_zero_balances=include_zero_balances,
    )


# =============================================================================
# INVENTORY VALUATION ENDPOINT
# =============================================================================

@router.get(
    "/inventory-valuation",
    response_model=InventoryValuationResponse,
    summary="Get Inventory Valuation Report",
    description="Returns inventory value by category compared to GL balances for reconciliation."
)
async def get_inventory_valuation(
    as_of_date: Optional[date] = Query(None, description="Valuation as of this date (default: today)"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Generate an inventory valuation report with GL reconciliation.

    Compares:
    - Physical inventory value (sum of on_hand_qty * unit_cost from Inventory/Product)
    - GL balance (sum of journal entry lines for inventory accounts)

    Categories and their GL accounts:
    - Raw Materials -> 1200
    - WIP -> 1210
    - Finished Goods -> 1220
    - Packaging -> 1230

    A variance indicates potential issues:
    - Missing journal entries
    - Double-counted transactions
    - Manual inventory adjustments without GL entries
    """
    return accounting_service.get_inventory_valuation(
        db,
        as_of_date=as_of_date,
    )


# =============================================================================
# TRANSACTION LEDGER ENDPOINT
# =============================================================================

@router.get(
    "/ledger/{account_code}",
    response_model=LedgerResponse,
    summary="Get Transaction Ledger",
    description="Returns all transactions for a GL account with running balance."
)
async def get_transaction_ledger(
    account_code: str,
    start_date: Optional[date] = Query(None, description="Filter transactions from this date"),
    end_date: Optional[date] = Query(None, description="Filter transactions to this date"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum transactions to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Get the transaction ledger for a specific GL account.

    Shows all journal entry lines affecting this account with:
    - Date and entry number
    - Description
    - Debit/Credit amounts
    - Running balance
    - Source document reference (PO, SO, etc.)

    Use this to:
    - Investigate variances found in inventory valuation
    - Audit transaction history
    - Trace costs through the system
    """
    return accounting_service.get_transaction_ledger(
        db,
        account_code,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


# =============================================================================
# PERIOD MANAGEMENT ENDPOINTS
# =============================================================================

@router.get(
    "/periods",
    response_model=PeriodListResponse,
    summary="List Fiscal Periods",
    description="Returns all fiscal periods with their status and summary data."
)
async def list_fiscal_periods(
    year: Optional[int] = Query(None, description="Filter by year"),
    status: Optional[str] = Query(None, description="Filter by status: open, closed"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    List all fiscal periods with summary information.

    Each period shows:
    - Date range
    - Open/closed status
    - Journal entry count and totals
    - Who closed it and when (if closed)
    """
    return accounting_service.list_fiscal_periods(
        db,
        year=year,
        status_filter=status,
    )


@router.post(
    "/periods/{period_id}/close",
    response_model=PeriodCloseResponse,
    summary="Close a Fiscal Period",
    description="Close a fiscal period to prevent new entries. Requires confirmation."
)
async def close_fiscal_period(
    period_id: int,
    request: PeriodCloseRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Close a fiscal period.

    Once closed:
    - No new journal entries can be created in this period
    - Existing entries cannot be modified
    - Period can be reopened by admin if needed

    Before closing, validates:
    - Period exists and is currently open
    - All entries in the period are balanced
    - Confirm flag is True
    """
    return accounting_service.close_fiscal_period(
        db,
        period_id,
        request.confirm,
        current_admin.id,
    )


@router.post(
    "/periods/{period_id}/reopen",
    response_model=PeriodCloseResponse,
    summary="Reopen a Closed Period",
    description="Reopen a previously closed fiscal period. Use with caution."
)
async def reopen_fiscal_period(
    period_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Reopen a closed fiscal period.

    Use with caution - this allows modifications to historical data.
    Typically used to correct errors discovered after close.
    """
    return accounting_service.reopen_fiscal_period(db, period_id)


# =============================================================================
# DASHBOARD WIDGET ENDPOINTS
# =============================================================================

@router.get(
    "/summary",
    response_model=AccountingSummaryResponse,
    summary="Get Accounting Summary",
    description="Quick financial snapshot for the admin dashboard."
)
async def get_accounting_summary(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Get a quick financial summary for the dashboard.

    Includes:
    - Total inventory value by category
    - Current period status
    - Activity metrics (entries today/week/month)
    - Balance verification
    """
    return accounting_service.get_accounting_summary(db)


@router.get(
    "/recent-entries",
    response_model=RecentEntriesResponse,
    summary="Get Recent Journal Entries",
    description="Returns the most recent journal entries for the dashboard."
)
async def get_recent_entries(
    limit: int = Query(10, ge=1, le=50, description="Number of entries to return"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    Get recent journal entries for dashboard display.

    Returns simplified entry data suitable for a list view.
    """
    return accounting_service.get_recent_entries(db, limit)
