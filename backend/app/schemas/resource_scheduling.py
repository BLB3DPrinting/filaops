"""
Schemas for resource scheduling.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


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


class ConflictCheckResponse(BaseModel):
    """Response from conflict check."""
    has_conflicts: bool
    conflicts: List[ConflictInfo]


class ScheduleOperationResponse(BaseModel):
    """Response from schedule operation."""
    success: bool
    message: Optional[str] = None
    operation_id: Optional[int] = None
    conflicts: List[ConflictInfo] = []
    next_available_start: Optional[datetime] = None
    next_available_end: Optional[datetime] = None


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
