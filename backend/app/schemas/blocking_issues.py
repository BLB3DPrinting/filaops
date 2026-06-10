"""
Schemas for blocking issues endpoints.
Used by both sales order and production order blocking analysis.
"""
from datetime import date
from decimal import Decimal
from typing import Optional, List, Any, Dict
from enum import Enum
from pydantic import BaseModel, Field


class IssueSeverity(str, Enum):
    """Severity level of a blocking issue."""
    BLOCKING = "blocking"  # Prevents fulfillment
    WARNING = "warning"    # May cause delays
    INFO = "info"          # Informational only


class IssueType(str, Enum):
    """Types of blocking issues."""
    PRODUCTION_INCOMPLETE = "production_incomplete"
    PRODUCTION_MISSING = "production_missing"
    MATERIAL_SHORTAGE = "material_shortage"
    PURCHASE_PENDING = "purchase_pending"
    INVENTORY_RESERVED = "inventory_reserved"
    QUALITY_HOLD = "quality_hold"


class BlockingIssue(BaseModel):
    """A single blocking issue."""
    type: IssueType
    severity: IssueSeverity
    message: str
    reference_type: str = Field(description="Type: 'production_order', 'product', 'purchase_order'")
    reference_id: int
    reference_code: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ResolutionAction(BaseModel):
    """Suggested action to resolve blocking issues."""
    priority: int
    action: str
    impact: str
    reference_type: str
    reference_id: int


class StatusSummary(BaseModel):
    """Summary of fulfillment status."""
    can_fulfill: bool
    blocking_count: int
    estimated_ready_date: Optional[date] = None
    days_until_ready: Optional[int] = None


class LineIssues(BaseModel):
    """Blocking issues for a single sales order line."""
    line_number: int
    product_sku: str
    product_name: str
    quantity_ordered: Decimal
    quantity_available: Decimal
    quantity_short: Decimal
    blocking_issues: List[BlockingIssue]
    # HARD-6: material-level projected quantities (rolled up from all components)
    quantity_projected: Optional[Decimal] = None


class SalesOrderBlockingIssues(BaseModel):
    """Complete blocking issues analysis for a sales order."""
    sales_order_id: int
    sales_order_code: str
    customer: str
    order_date: date
    requested_date: Optional[date] = None

    status_summary: StatusSummary
    line_issues: List[LineIssues]
    resolution_actions: List[ResolutionAction]

    class Config:
        from_attributes = True


# =============================================================================
# Production Order Blocking Issues (API-202)
# =============================================================================

class IncomingSupply(BaseModel):
    """Incoming supply from purchase order."""
    purchase_order_id: int
    purchase_order_code: str
    quantity: Decimal
    expected_date: Optional[date] = None
    vendor: str


class MaterialIssue(BaseModel):
    """Material availability for production."""
    product_id: int
    product_sku: str
    product_name: str
    quantity_required: Decimal
    quantity_available: Decimal
    quantity_short: Decimal
    # HARD-6: projected = available + incoming; shortage is net of on-order supply
    quantity_projected: Optional[Decimal] = None
    quantity_short_projected: Optional[Decimal] = None
    covered_by_incoming: bool = False   # short now but PO(s) cover the gap
    status: str  # 'ok', 'shortage', 'warning'
    incoming_supply: Optional[IncomingSupply] = None


class LinkedSalesOrderInfo(BaseModel):
    """Sales order linked to production order."""
    id: int
    code: str
    customer: str
    requested_date: Optional[date] = None


class POStatusSummary(BaseModel):
    """Summary of production readiness."""
    can_produce: bool
    blocking_count: int
    estimated_ready_date: Optional[date] = None
    days_until_ready: Optional[int] = None


class OtherIssue(BaseModel):
    """Non-material blocking issue."""
    type: str  # 'machine_unavailable', 'quality_hold', etc.
    severity: IssueSeverity
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ProductionOrderBlockingIssues(BaseModel):
    """Complete blocking issues analysis for a production order."""
    production_order_id: int
    production_order_code: str
    product_sku: str
    product_name: str

    quantity_ordered: Decimal
    quantity_completed: Decimal
    quantity_remaining: Decimal

    status_summary: POStatusSummary
    linked_sales_order: Optional[LinkedSalesOrderInfo] = None
    material_issues: List[MaterialIssue]
    other_issues: List[OtherIssue] = Field(default_factory=list)
    resolution_actions: List[ResolutionAction]

    class Config:
        from_attributes = True
