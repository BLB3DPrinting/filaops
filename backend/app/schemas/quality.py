"""
Pydantic schemas for Quality Management dashboard endpoints.
"""
from typing import Optional, List
from pydantic import BaseModel, Field


# =============================================================================
# Inspection Queue
# =============================================================================

class InspectionQueueItem(BaseModel):
    """A production order awaiting QC inspection."""
    id: int
    code: str
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    quantity_ordered: float = 0
    quantity_completed: float = 0
    qc_status: str
    priority: int
    due_date: Optional[str] = None
    status: str


class InspectionQueueResponse(BaseModel):
    """Paginated inspection queue."""
    items: List[InspectionQueueItem]
    total: int


# =============================================================================
# Quality Metrics
# =============================================================================

class QualityMetricsResponse(BaseModel):
    """Aggregate quality metrics for a time period."""
    period_days: int
    total_inspections: int
    passed: int
    failed: int
    first_pass_yield: Optional[float] = Field(
        None, description="Percentage of orders passing QC on first attempt"
    )
    pending_inspections: int
    scrap_rate: Optional[float] = Field(
        None, description="Scrapped qty as percentage of total completed"
    )
    total_scrapped_cost: float = 0


# =============================================================================
# Recent Inspections
# =============================================================================

class RecentInspectionItem(BaseModel):
    """A completed QC inspection."""
    id: int
    code: str
    product_name: Optional[str] = None
    quantity_ordered: float = 0
    quantity_completed: float = 0
    quantity_scrapped: float = 0
    qc_status: str
    qc_notes: Optional[str] = None
    qc_inspected_by: Optional[str] = None
    qc_inspected_at: Optional[str] = None


# =============================================================================
# Scrap Summary
# =============================================================================

class ScrapSummaryItem(BaseModel):
    """Scrap totals for a single reason code."""
    reason_code: str
    reason_name: str
    count: int
    total_quantity: float
    total_cost: float
