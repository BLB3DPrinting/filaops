"""
Pydantic schemas for the dispatch (suggest-and-confirm) engine.

SCHED-1: Dispatch service brain — read-only ranking + single assign action.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class PrinterInfo(BaseModel):
    """Minimal printer descriptor in a suggestion."""

    model_config = {"from_attributes": True}

    id: int
    code: str
    name: str
    model: str
    status: Optional[str] = None


class DispatchSuggestion(BaseModel):
    """
    A single ranked suggestion: one operation on one printer.

    ``why`` contains human-readable rank factors so the operator can
    understand why this job rose to the top, e.g.::

        ["priority 1 (highest)", "due 2026-06-12", "FIFO"]

    ``maintenance_warning`` is present when the printer's latest
    ``MaintenanceLog.next_due_at`` falls before ``now + estimated_duration``.
    The operator still decides — dispatch never silently skips.
    """

    production_order_id: int
    production_order_code: str
    product_name: str
    operation_id: int
    operation_code: Optional[str] = None
    operation_name: Optional[str] = None
    quantity: str  # Decimal serialised as str to avoid float drift
    due_date: Optional[date] = None
    priority: int
    estimated_duration_minutes: int = Field(
        description="Best-available duration: planned_setup + planned_run, "
        "or DEFAULT_DURATION_MINUTES if no routing data"
    )
    why: List[str] = Field(
        default_factory=list,
        description="Human-readable rank factors (priority, due date, FIFO)",
    )
    maintenance_warning: Optional[str] = Field(
        default=None,
        description="Non-None when maintenance is due before the job would finish",
    )


class PrinterDispatchResult(BaseModel):
    """Top suggestion + up to 2 runners-up for one printer."""

    printer: PrinterInfo
    top_suggestion: Optional[DispatchSuggestion] = None
    runners_up: List[DispatchSuggestion] = Field(default_factory=list)


class DispatchSuggestionsResponse(BaseModel):
    """Response envelope for GET /api/v1/dispatch/suggestions."""

    results: List[PrinterDispatchResult]
    generated_at: datetime


class AssignRequest(BaseModel):
    """
    Request body for POST /api/v1/dispatch/assign.

    Commits a suggestion: validates compatibility + conflicts via the
    existing engine, then calls schedule_operation(now → now+duration).
    """

    operation_id: int = Field(description="ProductionOrderOperation.id to assign")
    printer_id: int = Field(description="Printer.id to assign the operation to")


class AssignResponse(BaseModel):
    """Response for a successful assignment."""

    operation_id: int
    printer_id: int
    printer_code: str
    production_order_code: str
    scheduled_start: datetime
    scheduled_end: datetime
    # Status the operation was moved to after assignment
    # Semantics: schedule_operation() sets status='queued'.
    # The operation is QUEUED (assigned to a specific printer and time slot)
    # but NOT yet started. The operator/printer starts it via the existing
    # operation-status endpoint (POST /production-orders/{id}/operations/{op_id}/start).
    operation_status: str
