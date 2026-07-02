"""
Scheduling and Capacity Management Schemas
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel


class CapacityCheckRequest(BaseModel):
    """Request to check if a resource has capacity"""
    resource_id: int
    start_time: datetime
    end_time: datetime
    # Resources and Printers are distinct models with separate ID spaces
    # (see /scheduling/board); set True to check a printer lane.
    is_printer: bool = False


class ConflictInfo(BaseModel):
    """Information about a scheduling conflict"""
    # "operation" or "maintenance" — maintenance-window conflicts carry no order.
    type: str = "operation"
    order_id: Optional[int] = None
    order_code: str
    operation_id: Optional[int] = None
    operation_code: Optional[str] = None
    start_time: str
    end_time: str
    product_name: str


class CapacityCheckResponse(BaseModel):
    """Response from capacity check"""
    resource_id: int
    resource_code: str
    resource_name: str
    start_time: str
    end_time: str
    has_capacity: bool
    conflicts: List[ConflictInfo] = []


class AvailableSlotResponse(BaseModel):
    """An available time slot"""
    start_time: str
    end_time: str
    duration_hours: float


class MachineAvailabilityResponse(BaseModel):
    """Machine availability and utilization"""
    resource_id: int
    resource_code: str
    resource_name: str
    work_center_id: int
    work_center_code: Optional[str] = None
    status: str
    total_hours: float
    scheduled_hours: float
    available_hours: float
    utilization_percent: float
    scheduled_order_count: int

