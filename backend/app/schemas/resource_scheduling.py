"""
Schemas for resource scheduling.
"""
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field


class ScheduleOperationRequest(BaseModel):
    """Request to schedule an operation."""
    resource_id: int
    scheduled_start: datetime
    scheduled_end: datetime
    is_printer: bool = False  # True if resource_id refers to a printer, not a resource


class ScheduledOperationInfo(BaseModel):
    """Information about a scheduled operation."""
    operation_id: int
    production_order_id: int
    production_order_code: Optional[str] = None
    operation_code: Optional[str] = None
    operation_name: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    status: str

    class Config:
        from_attributes = True


class ConflictInfo(BaseModel):
    """Information about a conflicting operation."""
    operation_id: int
    production_order_id: int
    production_order_code: Optional[str] = None
    operation_code: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None

    class Config:
        from_attributes = True


class ResourceScheduleResponse(BaseModel):
    """Response with resource schedule."""
    resource_id: int
    resource_code: Optional[str] = None
    resource_name: Optional[str] = None
    operations: List[ScheduledOperationInfo]


class MaintenanceWindowInfo(BaseModel):
    """Information about a conflicting maintenance window (SCHED-7)."""
    id: int
    starts_at: datetime
    ends_at: datetime
    reason: Optional[str] = None
    status: str

    class Config:
        from_attributes = True


class ConflictCheckResponse(BaseModel):
    """Response from conflict check."""
    has_conflicts: bool
    conflicts: List[ConflictInfo]
    # Maintenance windows overlapping the range (SCHED-7) — additive field,
    # also counted in has_conflicts.
    maintenance_windows: List[MaintenanceWindowInfo] = Field(default_factory=list)


class ScheduleOperationResponse(BaseModel):
    """Response from schedule operation."""
    success: bool
    message: Optional[str] = None
    operation_id: Optional[int] = None
    conflicts: List[ConflictInfo] = Field(default_factory=list)
    next_available_start: Optional[datetime] = None
    next_available_end: Optional[datetime] = None
    # Predecessor-specific fields
    # conflict_type is "resource" when blocked by another op on the same
    # resource, "predecessor" when blocked purely by sequence constraints,
    # "maintenance" when blocked by a maintenance window (SCHED-7).
    conflict_type: Optional[Literal["predecessor", "resource", "maintenance"]] = None
    # earliest_valid_start is the latest predecessor scheduled_end — the
    # absolute floor for this operation regardless of resource availability.
    # Present only for predecessor conflicts (conflict_type == "predecessor").
    earliest_valid_start: Optional[datetime] = None


class NextAvailableSlotRequest(BaseModel):
    """Request to find next available time slot."""
    resource_id: int
    duration_minutes: int
    is_printer: bool = False
    after: Optional[datetime] = None  # Start searching after this time


class NextAvailableSlotResponse(BaseModel):
    """Response with next available time slot."""
    next_available: datetime
    suggested_end: datetime  # Based on requested duration


# ---------------------------------------------------------------------------
# SCHED-2: Reschedule / Unschedule
# ---------------------------------------------------------------------------

class RescheduleRequest(BaseModel):
    """
    Request body for POST .../reschedule.

    At least one of resource_id or scheduled_start must be provided.
    scheduled_end is optional — if omitted the endpoint recomputes it from
    the operation's planned duration (setup + run minutes, defaulting to
    120 min when not set).
    """

    resource_id: Optional[int] = None
    is_printer: Optional[bool] = None  # True when resource_id refers to a Printer
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None


class SuccessorConflictInfo(BaseModel):
    """A successor operation whose existing schedule would be violated."""

    operation_id: int
    operation_code: Optional[str] = None
    operation_name: Optional[str] = None
    sequence: int
    scheduled_start: Optional[datetime] = None
    # earliest_valid_start = the proposed reschedule end — the soonest the
    # successor can now validly start, mirroring the predecessor-conflict shape.
    earliest_valid_start: Optional[datetime] = None

    class Config:
        from_attributes = True


class RescheduleResponse(BaseModel):
    """Response from a reschedule operation."""

    success: bool
    operation_id: Optional[int] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    message: Optional[str] = None
    # Conflict fields — same shape as ScheduleOperationResponse so the modal
    # can reuse its existing conflict/suggestion affordances.
    conflicts: List[ConflictInfo] = Field(default_factory=list)
    conflict_type: Optional[
        Literal["predecessor", "resource", "successor", "maintenance"]
    ] = None
    earliest_valid_start: Optional[datetime] = None
    next_available_start: Optional[datetime] = None
    next_available_end: Optional[datetime] = None
    # Successor violations (when conflict_type == "successor")
    successor_conflicts: List[SuccessorConflictInfo] = Field(default_factory=list)


class UnscheduleResponse(BaseModel):
    """Response from an unschedule operation."""

    success: bool
    operation_id: int
    message: str
