"""
Maintenance Window Pydantic Schemas (SCHED-7)

Planned maintenance time blocks on printers / machine resources.
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.maintenance import MaintenanceType


class MaintenanceWindowCreate(BaseModel):
    """Create a planned maintenance window.

    Exactly one of printer_id / resource_id must be set (service-validated
    in addition to the DB CHECK constraint).
    """
    printer_id: Optional[int] = Field(None, description="Target printer (XOR with resource_id)")
    resource_id: Optional[int] = Field(None, description="Target machine resource (XOR with printer_id)")
    starts_at: datetime = Field(..., description="Window start (UTC)")
    ends_at: datetime = Field(..., description="Window end (UTC; must be after starts_at)")
    reason: Optional[str] = Field(None, max_length=255, description="Why the machine is down")


class MaintenanceWindowCompleteRequest(BaseModel):
    """Complete a window — writes the MaintenanceLog entry (printer windows)."""
    maintenance_type: MaintenanceType = Field(
        MaintenanceType.ROUTINE, description="Type recorded on the MaintenanceLog"
    )
    performed_by: Optional[str] = Field(None, max_length=100)
    next_due_at: Optional[datetime] = Field(
        None, description="When the next maintenance is due (recorded on the log)"
    )
    cost: Optional[Decimal] = Field(None, ge=0)
    notes: Optional[str] = None


class MaintenanceWindowResponse(BaseModel):
    id: int
    printer_id: Optional[int]
    resource_id: Optional[int]
    starts_at: datetime
    ends_at: datetime
    reason: Optional[str]
    status: str
    maintenance_log_id: Optional[int]
    created_by: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class MaintenanceWindowListResponse(BaseModel):
    items: List[MaintenanceWindowResponse]
    total: int
