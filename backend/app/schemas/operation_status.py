"""
Schemas for operation status transitions.
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, Field


class OperationStartRequest(BaseModel):
    """Request to start an operation."""
    resource_id: Optional[int] = Field(None, description="Specific resource/machine to use")
    operator_name: Optional[str] = Field(None, max_length=100, description="Name of operator")
    notes: Optional[str] = Field(None, description="Notes for starting operation")


class OperationCompleteRequest(BaseModel):
    """
    Request to complete an operation with optional partial scrap.

    When quantity_scrapped > 0 and scrap_reason is provided:
    - Cascading scrap accounting is triggered
    - ScrapRecords are created for materials from all prior operations
    - GL entry: DR Scrap Expense (5020), CR WIP (1210)
    - Optionally creates a replacement production order
    """
    quantity_completed: Decimal = Field(..., ge=0, description="Number of good units completed")
    quantity_scrapped: Decimal = Field(default=Decimal("0"), ge=0, description="Number of units to scrap")
    scrap_reason: Optional[str] = Field(
        None,
        max_length=100,
        description="Scrap reason code (required if quantity_scrapped > 0)"
    )
    scrap_notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Notes specific to the scrap event"
    )
    actual_run_minutes: Optional[int] = Field(None, ge=0, description="Override actual run time")
    notes: Optional[str] = Field(None, description="General completion notes")
    create_replacement: bool = Field(
        default=False,
        description="If True and scrapping, create a replacement production order"
    )


class OperationSkipRequest(BaseModel):
    """Request to skip an operation."""
    reason: str = Field(..., min_length=5, max_length=500, description="Reason for skipping")


class ProductionOrderSummary(BaseModel):
    """Summary of production order for operation responses."""
    id: int
    code: str
    status: str
    current_operation_sequence: Optional[int] = None

    # Quantity info for shortage detection
    quantity_ordered: Optional[Decimal] = None
    quantity_completed: Optional[Decimal] = None
    quantity_short: Optional[Decimal] = None  # Calculated: ordered - completed

    # Sales order link (for shortage notifications)
    sales_order_id: Optional[int] = None
    sales_order_code: Optional[str] = None

    class Config:
        from_attributes = True


class NextOperationInfo(BaseModel):
    """Info about the next operation in sequence."""
    id: int
    sequence: int
    operation_code: Optional[str]
    operation_name: Optional[str]
    status: str
    work_center_code: Optional[str] = None
    work_center_name: Optional[str] = None

    class Config:
        from_attributes = True


class OperationResponse(BaseModel):
    """Response for operation status changes."""
    id: int
    sequence: int
    operation_code: Optional[str]
    operation_name: Optional[str]
    status: str

    # Resource assignment
    resource_id: Optional[int] = None
    resource_code: Optional[str] = None

    # Timing
    planned_run_minutes: Optional[Decimal] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    actual_run_minutes: Optional[Decimal] = None

    # Quantities
    quantity_completed: Decimal = Decimal("0")
    quantity_scrapped: Decimal = Decimal("0")
    scrap_reason: Optional[str] = None

    # Notes
    notes: Optional[str] = None

    # Related
    production_order: ProductionOrderSummary
    next_operation: Optional[NextOperationInfo] = None

    class Config:
        from_attributes = True


class OperationMaterial(BaseModel):
    """Material assigned to an operation."""
    id: int
    component_id: int
    component_sku: Optional[str] = None
    component_name: Optional[str] = None
    component_is_template: bool = False  # Workstream B0: gates the variant-swap UI
    quantity_required: Decimal
    quantity_consumed: Decimal = Decimal("0")
    unit: Optional[str] = None
    status: str = "pending"  # pending, allocated, consumed

    class Config:
        from_attributes = True


class OperationListItem(BaseModel):
    """Operation in a list."""
    id: int
    sequence: int
    operation_code: Optional[str]
    operation_name: Optional[str]
    status: str

    work_center_id: int
    work_center_code: Optional[str] = None
    work_center_name: Optional[str] = None

    resource_id: Optional[int] = None
    # Printer assignment (mutually exclusive with resource_id — see
    # resource_scheduling.schedule_operation). resource_code/resource_name are
    # populated from whichever machine lane is set.
    printer_id: Optional[int] = None
    resource_code: Optional[str] = None
    resource_name: Optional[str] = None

    planned_setup_minutes: Decimal = Decimal("0")
    planned_run_minutes: Decimal
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None

    # Quantity tracking
    quantity_input: Decimal = Field(
        default=Decimal("0"),
        description="Max quantity allowed (from previous op or order qty)"
    )
    quantity_completed: Decimal = Decimal("0")
    quantity_scrapped: Decimal = Decimal("0")
    scrap_reason: Optional[str] = None

    # Materials for this operation
    materials: List[OperationMaterial] = Field(
        default_factory=list,
        description="Materials required for this operation"
    )

    class Config:
        from_attributes = True
