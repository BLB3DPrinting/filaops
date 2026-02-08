"""
Accounting Pydantic Schemas

Request/response schemas for the GL accounting module and accounting view endpoints.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Literal
from datetime import datetime, date
from decimal import Decimal


# ============================================================================
# GL Account Schemas (Chart of Accounts)
# ============================================================================

class GLAccountBase(BaseModel):
    """Base fields for GL Account"""
    account_code: str = Field(..., max_length=20, description="Account code (e.g., 1000, 4000)")
    name: str = Field(..., max_length=100, description="Account name")
    account_type: Literal["asset", "liability", "equity", "revenue", "expense"] = Field(
        ..., description="Account type"
    )
    schedule_c_line: Optional[str] = Field(
        None, max_length=10, description="IRS Schedule C line mapping (e.g., 1, 8, 22)"
    )
    parent_id: Optional[int] = Field(None, description="Parent account ID for sub-accounts")
    description: Optional[str] = Field(None, description="Account description")


class GLAccountCreate(GLAccountBase):
    """Create a new GL Account"""
    is_system: bool = Field(default=False, description="System accounts cannot be deleted")
    active: bool = Field(default=True)


class GLAccountUpdate(BaseModel):
    """Update an existing GL Account"""
    account_code: Optional[str] = Field(None, max_length=20)
    name: Optional[str] = Field(None, max_length=100)
    account_type: Optional[Literal["asset", "liability", "equity", "revenue", "expense"]] = None
    schedule_c_line: Optional[str] = Field(None, max_length=10)
    parent_id: Optional[int] = None
    description: Optional[str] = None
    active: Optional[bool] = None


class GLAccountResponse(GLAccountBase):
    """GL Account response"""
    id: int
    is_system: bool
    active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GLAccountListResponse(BaseModel):
    """GL Account list item"""
    id: int
    account_code: str
    name: str
    account_type: str
    schedule_c_line: Optional[str]
    is_system: bool
    active: bool

    model_config = {"from_attributes": True}


# ============================================================================
# GL Fiscal Period Schemas
# ============================================================================

class GLFiscalPeriodBase(BaseModel):
    """Base fields for Fiscal Period"""
    year: int = Field(..., ge=2000, le=2100, description="Fiscal year")
    period: int = Field(..., ge=1, le=12, description="Period (1-12 for months)")
    start_date: date = Field(..., description="Period start date")
    end_date: date = Field(..., description="Period end date")


class GLFiscalPeriodCreate(GLFiscalPeriodBase):
    """Create a new Fiscal Period"""
    pass


class GLFiscalPeriodResponse(GLFiscalPeriodBase):
    """Fiscal Period response"""
    id: int
    status: str
    closed_by: Optional[int]
    closed_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class GLFiscalPeriodClose(BaseModel):
    """Request to close a fiscal period"""
    confirm: bool = Field(
        ..., description="Must be true to confirm closing the period"
    )


# ============================================================================
# GL Journal Entry Line Schemas
# ============================================================================

class GLJournalEntryLineBase(BaseModel):
    """Base fields for Journal Entry Line"""
    account_id: int = Field(..., description="GL Account ID")
    debit_amount: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        description="Debit amount"
    )
    credit_amount: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        description="Credit amount"
    )
    memo: Optional[str] = Field(None, max_length=255, description="Line memo")

    @field_validator('debit_amount', 'credit_amount', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert float/int to Decimal"""
        if v is None:
            return Decimal("0")
        return Decimal(str(v))


class GLJournalEntryLineCreate(GLJournalEntryLineBase):
    """Create a journal entry line"""
    line_order: int = Field(default=0, description="Line order for display")


class GLJournalEntryLineResponse(BaseModel):
    """Journal Entry Line response"""
    id: int
    account_id: int
    account_code: Optional[str] = None
    account_name: Optional[str] = None
    debit_amount: Decimal
    credit_amount: Decimal
    memo: Optional[str]
    line_order: int

    model_config = {"from_attributes": True}


# ============================================================================
# GL Journal Entry Schemas
# ============================================================================

class GLJournalEntryBase(BaseModel):
    """Base fields for Journal Entry"""
    entry_date: date = Field(..., description="Entry date")
    description: str = Field(..., max_length=255, description="Entry description")
    source_type: Optional[str] = Field(
        None, max_length=50,
        description="Source type (sales_order, purchase_order, payment, manual)"
    )
    source_id: Optional[int] = Field(None, description="Source record ID")
    fiscal_period_id: Optional[int] = Field(None, description="Fiscal period ID")


class GLJournalEntryCreate(GLJournalEntryBase):
    """Create a new Journal Entry"""
    lines: List[GLJournalEntryLineCreate] = Field(
        ..., min_length=2, description="Journal entry lines (minimum 2)"
    )


class GLJournalEntryUpdate(BaseModel):
    """Update a draft Journal Entry"""
    entry_date: Optional[date] = None
    description: Optional[str] = Field(None, max_length=255)
    fiscal_period_id: Optional[int] = None
    lines: Optional[List[GLJournalEntryLineCreate]] = None


class GLJournalEntryResponse(GLJournalEntryBase):
    """Journal Entry response"""
    id: int
    entry_number: str
    status: str
    created_by: Optional[int]
    created_at: datetime
    posted_by: Optional[int]
    posted_at: Optional[datetime]
    voided_by: Optional[int]
    voided_at: Optional[datetime]
    void_reason: Optional[str]

    # Nested lines
    lines: List[GLJournalEntryLineResponse] = []

    # Computed totals
    total_debits: Decimal = Decimal("0")
    total_credits: Decimal = Decimal("0")
    is_balanced: bool = True

    model_config = {"from_attributes": True}


class GLJournalEntryListResponse(BaseModel):
    """Journal Entry list item"""
    id: int
    entry_number: str
    entry_date: date
    description: str
    source_type: Optional[str]
    status: str
    total_debits: Decimal
    total_credits: Decimal
    created_at: datetime

    model_config = {"from_attributes": True}


class GLJournalEntryPost(BaseModel):
    """Request to post a journal entry"""
    confirm: bool = Field(
        ..., description="Must be true to confirm posting"
    )


class GLJournalEntryVoid(BaseModel):
    """Request to void a journal entry"""
    void_reason: str = Field(
        ..., min_length=5, max_length=500,
        description="Reason for voiding the entry"
    )


# ============================================================================
# Report Schemas
# ============================================================================

class TrialBalanceLineResponse(BaseModel):
    """Single line in trial balance report"""
    account_id: int
    account_code: str
    account_name: str
    account_type: str
    debit_balance: Decimal
    credit_balance: Decimal


class TrialBalanceResponse(BaseModel):
    """Trial balance report response"""
    start_date: date
    end_date: date
    lines: List[TrialBalanceLineResponse]
    total_debits: Decimal
    total_credits: Decimal
    is_balanced: bool


class ProfitLossLineResponse(BaseModel):
    """Single line in P&L report"""
    account_id: int
    account_code: str
    account_name: str
    amount: Decimal


class ProfitLossResponse(BaseModel):
    """Profit & Loss report response"""
    start_date: date
    end_date: date
    revenue_lines: List[ProfitLossLineResponse]
    expense_lines: List[ProfitLossLineResponse]
    total_revenue: Decimal
    total_expenses: Decimal
    net_income: Decimal


class ScheduleCLineResponse(BaseModel):
    """Single line in Schedule C report"""
    line_number: str
    line_description: str
    amount: Decimal
    accounts: List[str]  # Account codes that contribute to this line


class ScheduleCResponse(BaseModel):
    """Schedule C report response - THE KILLER FEATURE"""
    year: int
    lines: List[ScheduleCLineResponse]
    gross_receipts: Decimal  # Line 1
    total_expenses: Decimal
    net_profit: Decimal  # Line 31


# ============================================================================
# Accounting View Endpoint Response Schemas
# ============================================================================

# --- Inventory by Account ---

class InventoryAccountItem(BaseModel):
    """An inventory item within an account."""
    product_id: int
    sku: str
    name: str
    on_hand: float
    allocated: float
    available: float
    unit_cost: float
    total_value: float


class WIPItem(BaseModel):
    """A WIP item (production order in progress)."""
    production_order_id: int
    code: Optional[str] = None
    status: str
    estimated_value: float


class InventoryAccount(BaseModel):
    """An accounting category with its inventory items."""
    account_code: str
    account_name: str
    total_value: float
    total_units: float
    items: list  # Mixed: InventoryAccountItem or WIPItem depending on account


class InventoryByAccountSummary(BaseModel):
    """Summary totals for inventory-by-account."""
    raw_materials: float
    wip: float
    finished_goods: float
    total_inventory: float


class InventoryByAccountResponse(BaseModel):
    """Response for GET /inventory-by-account."""
    as_of: str
    accounts: List[InventoryAccount]
    summary: InventoryByAccountSummary


# --- Transactions Journal ---

class JournalAccountEntry(BaseModel):
    """Debit or credit account in a journal entry."""
    code: str
    name: str
    amount: float


class TransactionJournalEntry(BaseModel):
    """A single journal entry in the transactions journal."""
    date: Optional[str] = None
    transaction_id: int
    transaction_type: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[int] = None
    product_sku: str
    quantity: float
    unit_cost: float
    value: float
    debit_account: Optional[JournalAccountEntry] = None
    credit_account: Optional[JournalAccountEntry] = None
    notes: Optional[str] = None


class TransactionsJournalResponse(BaseModel):
    """Response for GET /transactions-journal."""
    period: str
    transaction_count: int
    entries: List[TransactionJournalEntry]


# --- Order Cost Breakdown ---

class CostLineItem(BaseModel):
    """A line item in cost breakdown (material or packaging)."""
    sku: str
    quantity: float
    unit_cost: float
    total: float


class MaterialsCost(BaseModel):
    """Materials cost breakdown."""
    total: float
    items: List[CostLineItem]


class PackagingCost(BaseModel):
    """Packaging cost breakdown."""
    total: float
    items: List[CostLineItem]


class OrderCosts(BaseModel):
    """All cost categories for an order."""
    materials: MaterialsCost
    labor: float
    packaging: PackagingCost


class OrderCostBreakdownResponse(BaseModel):
    """Response for GET /order-cost-breakdown/{order_id}."""
    order_id: int
    order_number: Optional[str] = None
    order_status: Optional[str] = None
    revenue: float
    costs: OrderCosts
    shipping_expense: float
    total_cogs: float
    gross_profit: float
    gross_margin_pct: float
    note: str


# --- COGS Summary ---

class COGSBreakdown(BaseModel):
    """COGS breakdown by category."""
    materials: float
    labor: float
    packaging: float
    total: float


class COGSSummaryResponse(BaseModel):
    """Response for GET /cogs-summary."""
    period: str
    orders_shipped: int
    revenue: float
    cogs: COGSBreakdown
    shipping_expense: float
    gross_profit: float
    gross_margin_pct: float


# --- Dashboard ---

class DashboardRevenue(BaseModel):
    """Revenue section of the dashboard."""
    mtd: float
    mtd_orders: int
    ytd: float
    ytd_orders: int


class DashboardPayments(BaseModel):
    """Payments section of the dashboard."""
    mtd_received: float
    ytd_received: float
    outstanding: float
    outstanding_orders: int


class DashboardTax(BaseModel):
    """Tax section of the dashboard."""
    mtd_collected: float
    ytd_collected: float


class DashboardCOGS(BaseModel):
    """COGS section of the dashboard."""
    mtd: float


class DashboardProfit(BaseModel):
    """Profit section of the dashboard."""
    mtd_gross: float
    mtd_margin_pct: float


class DashboardResponse(BaseModel):
    """Response for GET /dashboard."""
    as_of: str
    fiscal_year_start: str
    revenue: DashboardRevenue
    payments: DashboardPayments
    tax: DashboardTax
    cogs: DashboardCOGS
    profit: DashboardProfit


# --- Sales Journal ---

class SalesJournalEntry(BaseModel):
    """A single entry in the sales journal."""
    date: Optional[str] = None
    order_number: Optional[str] = None
    order_id: int
    status: Optional[str] = None
    payment_status: Optional[str] = None
    source: Optional[str] = None
    product_name: Optional[str] = None
    quantity: Optional[int] = None
    subtotal: float
    tax_rate: Optional[float] = None
    tax_amount: float
    is_taxable: bool
    shipping: float
    grand_total: float
    paid_at: Optional[str] = None
    shipped_at: Optional[str] = None


class SalesJournalPeriod(BaseModel):
    """Period range for the sales journal."""
    start: str
    end: str


class SalesJournalTotals(BaseModel):
    """Totals for the sales journal."""
    subtotal: float
    tax: float
    shipping: float
    grand_total: float
    order_count: int


class SalesJournalResponse(BaseModel):
    """Response for GET /sales-journal."""
    period: SalesJournalPeriod
    totals: SalesJournalTotals
    entries: List[SalesJournalEntry]


# --- Tax Summary ---

class TaxSummarySummary(BaseModel):
    """Summary section of the tax summary."""
    total_sales: float
    taxable_sales: float
    non_taxable_sales: float
    tax_collected: float
    order_count: int


class TaxSummaryPending(BaseModel):
    """Pending tax liability section."""
    tax_amount: float
    order_count: int


class TaxByRateEntry(BaseModel):
    """Tax breakdown by rate."""
    rate_pct: float
    taxable_sales: float
    tax_collected: float
    order_count: int


class TaxMonthlyBreakdown(BaseModel):
    """Monthly breakdown of tax data."""
    month: str
    taxable_sales: float
    tax_collected: float
    order_count: int


class TaxSummaryResponse(BaseModel):
    """Response for GET /tax-summary."""
    period: str
    period_start: str
    period_end: str
    summary: TaxSummarySummary
    pending: TaxSummaryPending
    by_rate: List[TaxByRateEntry]
    monthly_breakdown: List[TaxMonthlyBreakdown]


# --- Payments Journal ---

class PaymentJournalEntry(BaseModel):
    """A single entry in the payments journal."""
    date: Optional[str] = None
    payment_number: Optional[str] = None
    order_number: Optional[str] = None
    payment_method: Optional[str] = None
    payment_type: Optional[str] = None
    amount: float
    transaction_id: Optional[str] = None
    notes: Optional[str] = None


class PaymentsJournalPeriod(BaseModel):
    """Period range for the payments journal."""
    start: str
    end: str


class PaymentsJournalTotals(BaseModel):
    """Totals for the payments journal."""
    payments: float
    refunds: float
    net: float
    count: int


class PaymentsJournalResponse(BaseModel):
    """Response for GET /payments-journal."""
    period: PaymentsJournalPeriod
    totals: PaymentsJournalTotals
    by_method: Dict[str, float]
    entries: List[PaymentJournalEntry]
