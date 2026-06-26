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
        None,
        description="Scrapped qty as a percentage of total handled (good + scrapped)",
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


# =============================================================================
# Quality Policy (the QC rigor "dial")
# =============================================================================

class QualityPolicyResponse(BaseModel):
    """The company's QC rigor configuration, for the UI to decide what to show.

    ``mode`` is the raw dial position; the booleans are the derived questions the
    UI actually asks (e.g. hide all QC nav when ``surfaces_enabled`` is False).
    """
    mode: str = Field(description="off | basic | full")
    gate_close: bool = Field(
        description="Raw setting: hard-block close on failed inspection (full mode only)"
    )
    surfaces_enabled: bool = Field(
        description="Whether QC surfaces should appear at all (basic or full)"
    )
    plan_driven: bool = Field(
        description="Whether quality plans + measurements apply (full only)"
    )
    gates_close: bool = Field(
        description="Effective gating: a failed inspection hard-blocks close (full + gate_close)"
    )
