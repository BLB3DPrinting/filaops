"""
Audit API Response Schemas

Pydantic models for the transaction audit endpoints.
"""
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


# ============================================================================
# Nested Models
# ============================================================================

class AuditGapItem(BaseModel):
    """A single transaction gap found during an audit."""
    order_id: int
    order_number: str
    order_status: str
    production_order_id: Optional[int] = None
    production_status: Optional[str] = None
    gap_type: str
    expected_sku: Optional[str] = None
    expected_quantity: Optional[float] = None
    details: str


class TimelineItem(BaseModel):
    """A single transaction entry in an order timeline."""
    timestamp: Optional[str] = None
    transaction_type: str
    reference_type: str
    reference_id: int
    product_id: int
    product_sku: Optional[str] = None
    quantity: float = 0
    notes: Optional[str] = None


# ============================================================================
# Endpoint Response Models
# ============================================================================

class AuditTransactionsResponse(BaseModel):
    """Response for GET /transactions and GET /transactions/order/{order_id}."""
    audit_timestamp: str
    total_orders_checked: int
    orders_with_gaps: int
    total_gaps: int
    summary_by_type: Dict[str, int] = Field(default_factory=dict)
    gaps: List[AuditGapItem] = Field(default_factory=list)


class AuditTimelineResponse(BaseModel):
    """Response for GET /transactions/timeline/{order_id}."""
    order_id: int
    transaction_count: int
    timeline: List[TimelineItem] = Field(default_factory=list)


class AuditSummaryResponse(BaseModel):
    """Response for GET /transactions/summary."""
    total_orders: int
    orders_with_issues: int
    total_gaps: int
    gaps_by_type: Dict[str, int] = Field(default_factory=dict)
    health_score: float
