"""
Production Order Pydantic Schemas

Manufacturing Orders (MOs) for tracking production of finished goods.
"""
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class ProductionOrderStatus(str, Enum):
    """Production order status"""
    DRAFT = "draft"
    RELEASED = "released"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    QC_HOLD = "qc_hold"
    SCRAPPED = "scrapped"
    CLOSED = "closed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class ProductionOrderSource(str, Enum):
    """How the production order was created"""
    MANUAL = "manual"
    SALES_ORDER = "sales_order"
    MRP_PLANNED = "mrp_planned"


class ProductionOrderType(str, Enum):
    """Production order type - determines fulfillment flow"""
    MAKE_TO_ORDER = "MAKE_TO_ORDER"  # MTO: Produced for specific sales order, ships when complete
    MAKE_TO_STOCK = "MAKE_TO_STOCK"  # MTS: Produced for inventory, FG sits on shelf until ordered


class OperationStatus(str, Enum):
    """Operation execution status"""
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    SKIPPED = "skipped"


class QCStatus(str, Enum):
    """Quality Control status"""
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    WAIVED = "waived"


# ============================================================================
# Production Order Operation Schemas
# ============================================================================

class ProductionOrderOperationBase(BaseModel):
    """Base operation fields"""
    work_center_id: int
    resource_id: Optional[int] = None
    sequence: int = Field(..., ge=1)
    operation_code: Optional[str] = Field(None, max_length=50)
    operation_name: Optional[str] = Field(None, max_length=200)
    planned_setup_minutes: Decimal = Field(0, ge=0)
    planned_run_minutes: Decimal = Field(..., ge=0)
    notes: Optional[str] = None


class ProductionOrderOperationCreate(ProductionOrderOperationBase):
    """Create a new operation (usually auto-created from routing)"""
    routing_operation_id: Optional[int] = None


class ProductionOrderOperationUpdate(BaseModel):
    """Update an operation - typically during execution"""
    resource_id: Optional[int] = None
    status: Optional[OperationStatus] = None
    quantity_completed: Optional[Decimal] = Field(None, ge=0)
    quantity_scrapped: Optional[Decimal] = Field(None, ge=0)
    actual_setup_minutes: Optional[Decimal] = Field(None, ge=0)
    actual_run_minutes: Optional[Decimal] = Field(None, ge=0)
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    bambu_task_id: Optional[str] = Field(None, max_length=100)
    bambu_plate_index: Optional[int] = None
    operator_name: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class ProductionOrderOperationResponse(BaseModel):
    """Operation response with full details"""
    id: int
    production_order_id: int
    routing_operation_id: Optional[int] = None
    work_center_id: int
    work_center_code: Optional[str] = None
    work_center_name: Optional[str] = None
    resource_id: Optional[int] = None
    resource_code: Optional[str] = None
    resource_name: Optional[str] = None

    sequence: int
    operation_code: Optional[str] = None
    operation_name: Optional[str] = None
    status: str

    quantity_completed: Decimal = 0
    quantity_scrapped: Decimal = 0

    planned_setup_minutes: Decimal = 0
    planned_run_minutes: Decimal
    actual_setup_minutes: Optional[Decimal] = None
    actual_run_minutes: Optional[Decimal] = None

    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None

    bambu_task_id: Optional[str] = None
    bambu_plate_index: Optional[int] = None
    operator_name: Optional[str] = None
    notes: Optional[str] = None

    # Computed
    is_complete: bool = False
    is_running: bool = False
    efficiency_percent: Optional[float] = None

    # Materials for this operation
    materials: List["OperationMaterialResponse"] = Field(default_factory=list)

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OperationMaterialResponse(BaseModel):
    """Material requirement for a production order operation"""
    id: int
    component_id: int
    component_sku: Optional[str] = None
    component_name: Optional[str] = None
    quantity_required: Decimal
    quantity_allocated: Decimal = Decimal("0")
    quantity_consumed: Decimal = Decimal("0")
    unit: str
    status: str

    class Config:
        from_attributes = True


# ============================================================================
# Production Order Schemas
# ============================================================================

class ProductionOrderBase(BaseModel):
    """Base production order fields"""
    product_id: int
    quantity_ordered: Decimal = Field(..., gt=0)
    due_date: Optional[date] = None
    priority: int = Field(3, ge=1, le=5, description="1=highest, 5=lowest")
    notes: Optional[str] = None


class ProductionOrderCreate(ProductionOrderBase):
    """Create a new production order"""
    bom_id: Optional[int] = None
    routing_id: Optional[int] = None
    sales_order_id: Optional[int] = None
    sales_order_line_id: Optional[int] = None
    source: ProductionOrderSource = ProductionOrderSource.MANUAL
    order_type: ProductionOrderType = ProductionOrderType.MAKE_TO_ORDER
    assigned_to: Optional[str] = Field(None, max_length=100)


class ProductionOrderUpdate(BaseModel):
    """Update a production order"""
    quantity_ordered: Optional[Decimal] = Field(None, gt=0)
    quantity_completed: Optional[Decimal] = Field(None, ge=0)
    quantity_scrapped: Optional[Decimal] = Field(None, ge=0)
    status: Optional[ProductionOrderStatus] = None
    order_type: Optional[ProductionOrderType] = None
    priority: Optional[int] = Field(None, ge=1, le=5)
    due_date: Optional[date] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    assigned_to: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class ProductionOrderScheduleRequest(BaseModel):
    """Schedule a production order to a specific resource and time"""
    scheduled_start: datetime
    scheduled_end: datetime
    resource_id: Optional[int] = Field(None, description="Resource/machine ID to assign")
    notes: Optional[str] = None


class ProductionOrderStatusUpdate(BaseModel):
    """Update just the status (with optional timestamps)"""
    status: ProductionOrderStatus
    notes: Optional[str] = None


class ProductionOrderListResponse(BaseModel):
    """Summary for list views"""
    id: int
    code: str
    product_id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None

    quantity_ordered: Decimal
    quantity_completed: Decimal = 0
    quantity_remaining: float = 0
    completion_percent: float = 0

    status: str
    priority: int
    source: str
    order_type: str = "MAKE_TO_ORDER"  # MTO or MTS

    # QC Status
    qc_status: str = "not_required"

    due_date: Optional[date] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None

    sales_order_id: Optional[int] = None
    sales_order_code: Optional[str] = None

    assigned_to: Optional[str] = None
    operation_count: int = 0
    current_operation: Optional[str] = None  # Name of current/next operation

    created_at: datetime

    class Config:
        from_attributes = True


class ProductionOrderResponse(BaseModel):
    """Full production order details"""
    id: int
    code: str

    # References
    product_id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    bom_id: Optional[int] = None
    bom_code: Optional[str] = None
    routing_id: Optional[int] = None
    routing_code: Optional[str] = None
    sales_order_id: Optional[int] = None
    sales_order_code: Optional[str] = None
    sales_order_line_id: Optional[int] = None

    # Quantities
    quantity_ordered: Decimal
    quantity_completed: Decimal = 0
    quantity_scrapped: Decimal = 0
    quantity_remaining: float = 0
    completion_percent: float = 0

    # Status
    source: str
    order_type: str = "MAKE_TO_ORDER"  # MTO or MTS
    status: str
    priority: int

    # QC Status
    qc_status: str = "not_required"
    qc_notes: Optional[str] = None
    qc_inspected_by: Optional[str] = None
    qc_inspected_at: Optional[datetime] = None

    # Scheduling
    due_date: Optional[date] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None

    # Time
    estimated_time_minutes: Optional[int] = None
    actual_time_minutes: Optional[int] = None

    # Costs
    estimated_material_cost: Optional[Decimal] = None
    estimated_labor_cost: Optional[Decimal] = None
    estimated_total_cost: Optional[Decimal] = None
    actual_material_cost: Optional[Decimal] = None
    actual_labor_cost: Optional[Decimal] = None
    actual_total_cost: Optional[Decimal] = None

    # Assignment
    assigned_to: Optional[str] = None
    notes: Optional[str] = None

    # Lineage - for tracking remakes and parent/child orders
    remake_of_id: Optional[int] = None  # If this is a remake, links to original failed order
    remake_of_code: Optional[str] = None  # Code of original order
    remake_reason: Optional[str] = None  # Why this remake was created (scrap reason)

    # Operations
    operations: List[ProductionOrderOperationResponse] = []

    # Metadata
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    released_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductionOrderScrapResponse(ProductionOrderResponse):
    """Response schema for production order scrap operations.
    
    This schema extends ProductionOrderResponse to provide comprehensive information
    when a production order is scrapped, including details about automatically created
    remake orders when applicable.
    
    Used by the scrap endpoint to return the updated production order state along with
    information about any automatically generated remake orders that replace the scrapped
    quantity.
    
    Attributes:
        remake_order_id (Optional[int]): The unique identifier of the automatically 
            created remake production order. This field is populated when the system 
            automatically creates a new order to replace scrapped quantity. None if no 
            remake order was created.
            
        remake_order_code (Optional[str]): The human-readable code/reference number 
            assigned to the remake production order (e.g., "MO-2024-001234"). None if 
            no remake order was created.
    
    Inherited Attributes (from ProductionOrderResponse):
        All attributes from ProductionOrderResponse are inherited, including:
        
        - **Identification**: id, code
        - **Product References**: product_id, product_sku, product_name
        - **BOM/Routing**: bom_id, bom_code, routing_id, routing_code
        - **Sales Order Links**: sales_order_id, sales_order_code, sales_order_line_id
        - **Quantities**: quantity_ordered, quantity_completed, quantity_scrapped, 
          quantity_remaining, completion_percent
        - **Status & Priority**: source, status, priority
        - **Scheduling**: due_date, scheduled_start, scheduled_end, actual_start, actual_end
        - **Time Tracking**: estimated_time_minutes, actual_time_minutes
        - **Cost Tracking**: estimated_material_cost, estimated_labor_cost, 
          estimated_total_cost, actual_material_cost, actual_labor_cost, actual_total_cost
        - **Assignment**: assigned_to, notes
        - **Operations**: operations (list of ProductionOrderOperationResponse)
        - **Metadata**: created_at, updated_at, created_by, released_at, completed_at
    
    Example:
        ```json
        {
            "id": 123,
            "code": "MO-2024-001000",
            "product_id": 456,
            "product_sku": "WIDGET-001",
            "quantity_ordered": 100,
            "quantity_scrapped": 100,
            "status": "cancelled",
            "remake_order_id": 124,
            "remake_order_code": "MO-2024-001001",
            ...
        }
        ```
    
    See Also:
        - ProductionOrderResponse: Parent class with full production order details
        - ProductionOrderStatus: Enum for valid status values
        - ProductionOrderOperationResponse: Schema for operation details
    """
    remake_order_id: Optional[int] = None
    remake_order_code: Optional[str] = None


# ============================================================================
# Bulk Operations
# ============================================================================

class ProductionOrderBulkCreate(BaseModel):
    """Create multiple production orders"""
    orders: List[ProductionOrderCreate]


class ProductionOrderBulkStatusUpdate(BaseModel):
    """Update status of multiple orders"""
    order_ids: List[int]
    status: ProductionOrderStatus


# ============================================================================
# Schedule/Queue Views
# ============================================================================

class ProductionQueueItem(BaseModel):
    """Item for the production queue/kanban view"""
    id: int
    code: str
    product_sku: str
    product_name: str
    quantity_ordered: Decimal
    quantity_completed: Decimal = 0
    status: str
    priority: int
    due_date: Optional[date] = None
    current_operation_name: Optional[str] = None
    current_work_center_code: Optional[str] = None
    is_late: bool = False
    days_until_due: Optional[int] = None

    class Config:
        from_attributes = True


class WorkCenterQueue(BaseModel):
    """Operations queued at a work center"""
    work_center_id: int
    work_center_code: str
    work_center_name: str
    queued_operations: List[ProductionOrderOperationResponse] = []
    running_operations: List[ProductionOrderOperationResponse] = []
    total_queued_minutes: float = 0


class ProductionScheduleSummary(BaseModel):
    """Summary stats for the production schedule"""
    total_orders: int = 0
    orders_by_status: dict = {}
    orders_due_today: int = 0
    orders_overdue: int = 0
    orders_in_progress: int = 0
    total_quantity_to_produce: float = 0


# ============================================================================
# Split Order Schemas
# ============================================================================

class SplitQuantity(BaseModel):
    """Quantity for a single split order"""
    quantity: int = Field(..., gt=0, description="Quantity for this split")


class ProductionOrderSplitRequest(BaseModel):
    """Request to split a production order into multiple child orders"""
    splits: List[SplitQuantity] = Field(
        ...,
        min_length=2,
        description="List of quantities for each split (must have at least 2)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "splits": [
                    {"quantity": 25},
                    {"quantity": 25}
                ]
            }
        }


class ProductionOrderSplitResponse(BaseModel):
    """Response from splitting a production order"""
    parent_order_id: int
    parent_order_code: str
    parent_status: str
    child_orders: List[ProductionOrderListResponse]
    message: str


# ============================================================================
# Scrap Reason Schemas
# ============================================================================

class ScrapReasonCreate(BaseModel):
    """Create schema for scrap reasons"""
    code: str = Field(..., min_length=1, max_length=50, description="Unique code for the scrap reason")
    name: str = Field(..., min_length=1, max_length=100, description="Display name")
    description: Optional[str] = Field(None, description="Detailed description")
    sequence: int = Field(default=0, ge=0, description="Display order sequence")


class ScrapReasonDetail(BaseModel):
    """Detailed scrap reason information"""
    id: int
    code: str
    name: str
    description: Optional[str] = None
    sequence: int
    active: bool = True

    class Config:
        from_attributes = True


class ScrapReasonUpdate(BaseModel):
    """Update schema for scrap reasons"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    active: Optional[bool] = None
    sequence: Optional[int] = Field(None, ge=0)

    class Config:
        from_attributes = True


class ScrapReasonsResponse(BaseModel):
    """Response for scrap reasons endpoint"""
    reasons: List[str] = Field(..., description="List of scrap reason codes")
    details: List[ScrapReasonDetail] = Field(..., description="Detailed scrap reason information")
    descriptions: dict[str, str] = Field(..., description="Map of code to description")

    class Config:
        from_attributes = True


# ============================================================================
# QC Inspection Schemas
# ============================================================================

class QCInspectionRequest(BaseModel):
    """Request to perform QC inspection on a production order"""
    result: QCStatus = Field(
        ...,
        description="QC result: 'passed' or 'failed'"
    )
    notes: Optional[str] = Field(
        None,
        max_length=2000,
        description="Inspector notes about the QC inspection"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "result": "passed",
                "notes": "All units inspected. Surface finish acceptable."
            }
        }


class QCInspectionResponse(BaseModel):
    """Response from QC inspection"""
    production_order_id: int
    production_order_code: str
    qc_status: str
    qc_notes: Optional[str] = None
    qc_inspected_by: Optional[str] = None
    qc_inspected_at: Optional[datetime] = None
    sales_order_updated: bool = False
    sales_order_status: Optional[str] = None
    message: str


# ============================================================================
# Spool Consumption Schemas
# ============================================================================

class SpoolUsage(BaseModel):
    """Record of spool used during production - enables material traceability"""
    product_id: int = Field(..., description="Material product ID from BOM")
    spool_id: int = Field(..., description="Spool ID being consumed")
    weight_consumed_g: Optional[Decimal] = Field(
        None, ge=0, description="Weight consumed in grams (calculated from BOM if not provided)"
    )


class ProductionOrderCompleteRequest(BaseModel):
    """Request body for completing a production order with optional spool tracking"""
    quantity_completed: Optional[Decimal] = Field(None, ge=0)
    quantity_scrapped: Optional[Decimal] = Field(None, ge=0)
    force_close_short: bool = Field(False, description="Explicitly close order short without producing all units")
    notes: Optional[str] = None
    spools_used: Optional[List[SpoolUsage]] = Field(
        None, description="List of spools consumed during production (for traceability)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "quantity_completed": 10,
                "spools_used": [
                    {"product_id": 5, "spool_id": 12, "weight_consumed_g": 150.5}
                ]
            }
        }


# ============================================================================
# Operation-Level Scrap Schemas
# ============================================================================

class OperationScrapRequest(BaseModel):
    """Request to scrap units at a specific operation with cascading material accounting"""
    quantity_scrapped: int = Field(..., ge=1, description="Number of units to scrap")
    scrap_reason_code: str = Field(..., min_length=1, max_length=50, description="Scrap reason code")
    notes: Optional[str] = Field(None, max_length=2000, description="Optional notes about the scrap")
    create_replacement: bool = Field(
        True,
        description="If True, create a replacement production order for the scrapped quantity"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "quantity_scrapped": 2,
                "scrap_reason_code": "layer_shift",
                "notes": "Layer shift detected at z=50mm",
                "create_replacement": True
            }
        }


class ScrapCascadeMaterial(BaseModel):
    """Material consumed in the scrap cascade"""
    operation_id: int
    operation_sequence: int
    operation_name: str
    component_id: int
    component_sku: str
    component_name: str
    quantity: float
    unit: str
    unit_cost: float
    cost: float


class ScrapCascadeResponse(BaseModel):
    """Response from scrap cascade calculation (preview before scrap)"""
    production_order_id: int
    production_order_code: str
    operation_id: int
    operation_name: str
    quantity_scrapped: int
    materials_consumed: List[ScrapCascadeMaterial]
    total_cost: float
    operations_affected: int

    class Config:
        json_schema_extra = {
            "example": {
                "production_order_id": 123,
                "production_order_code": "PO-2026-0001",
                "operation_id": 456,
                "operation_name": "Assembly",
                "quantity_scrapped": 2,
                "materials_consumed": [
                    {
                        "operation_id": 450,
                        "operation_sequence": 1,
                        "operation_name": "Printing",
                        "component_id": 10,
                        "component_sku": "PLA-BLUE",
                        "component_name": "PLA Blue Filament",
                        "quantity": 100.0,
                        "unit": "G",
                        "unit_cost": 0.02,
                        "cost": 2.0
                    }
                ],
                "total_cost": 5.50,
                "operations_affected": 3
            }
        }


class ReplacementOrderInfo(BaseModel):
    """Info about a created replacement production order"""
    id: int
    code: str


class OperationScrapResponse(BaseModel):
    """Response from operation-level scrap execution"""
    success: bool
    scrap_records_created: int
    operations_affected: int
    total_scrap_cost: float
    journal_entry_number: Optional[str] = None
    downstream_ops_skipped: int = 0
    replacement_order: Optional[ReplacementOrderInfo] = None

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "scrap_records_created": 5,
                "operations_affected": 3,
                "total_scrap_cost": 12.50,
                "journal_entry_number": "JE-2026-000042",
                "downstream_ops_skipped": 2,
                "replacement_order": {
                    "id": 124,
                    "code": "PO-2026-0002"
                }
            }
        }


# ============================================================================
# Partial Operation Completion Schemas
# ============================================================================

class OperationPartialCompleteRequest(BaseModel):
    """Request to partially complete an operation with optional scrap"""
    quantity_completed: int = Field(..., ge=0, description="Number of good units completed")
    quantity_scrapped: int = Field(0, ge=0, description="Number of units scrapped at this operation")
    scrap_reason_code: Optional[str] = Field(
        None,
        max_length=50,
        description="Required if quantity_scrapped > 0"
    )
    scrap_notes: Optional[str] = Field(None, max_length=2000, description="Notes about the scrap")
    actual_run_minutes: Optional[int] = Field(None, ge=0, description="Actual run time in minutes")
    notes: Optional[str] = Field(None, max_length=2000, description="General operation notes")
    create_replacement: bool = Field(
        True,
        description="If scrapping, create replacement PO for scrapped qty"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "quantity_completed": 8,
                "quantity_scrapped": 2,
                "scrap_reason_code": "layer_shift",
                "scrap_notes": "Layer shift on 2 parts",
                "actual_run_minutes": 45,
                "create_replacement": True
            }
        }


# ============================================================================
# Endpoint Response Models (for endpoints missing response_model)
# ============================================================================

class StatusTransitionDetail(BaseModel):
    """Detail for a single status transition entry."""
    allowed_transitions: List[str]
    is_terminal: bool


class StatusTransitionsResponse(BaseModel):
    """Response for GET /status-transitions.

    When current_status is provided, returns that status with its transitions.
    When not provided, returns all statuses and their transition maps.
    """
    # Returned when current_status query param is provided
    current_status: Optional[str] = None
    allowed_transitions: Optional[List[str]] = None
    is_terminal: Optional[bool] = None

    # Returned when no current_status query param
    statuses: Optional[List[str]] = None
    transitions: Optional[Dict[str, StatusTransitionDetail]] = None


class QCStatusesResponse(BaseModel):
    """Response for GET /qc-statuses."""
    statuses: List[str]
    descriptions: Dict[str, str]


class OperationStatusesResponse(BaseModel):
    """Response for GET /operation-statuses."""
    statuses: List[str]
    descriptions: Dict[str, str]


class MaterialAvailabilityItem(BaseModel):
    """A single material availability line."""
    operation_id: int
    operation_name: Optional[str] = None
    component_id: int
    component_sku: Optional[str] = None
    component_name: Optional[str] = None
    unit: str
    quantity_required: float
    quantity_available: float
    quantity_allocated: float
    quantity_short: float
    status: str


class MaterialAvailabilitySummary(BaseModel):
    """Summary of material availability."""
    total_materials: int
    materials_available: int
    materials_short: int
    can_start: bool


class MaterialAvailabilityResponse(BaseModel):
    """Response for GET /{order_id}/material-availability."""
    order_id: int
    order_code: str
    materials: List[MaterialAvailabilityItem]
    summary: MaterialAvailabilitySummary


class RequiredOrderItem(BaseModel):
    """A single required order (work order or purchase order)."""
    product_id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    quantity_required: float
    quantity_available: float
    quantity_short: float
    bom_level: int
    has_bom: bool


class RequiredOrdersSummary(BaseModel):
    """Summary of required orders."""
    work_orders: int
    purchase_orders: int
    total: int


class RequiredOrdersResponse(BaseModel):
    """Response for GET /{order_id}/required-orders."""
    order_id: int
    order_code: str
    work_orders_needed: List[RequiredOrderItem]
    purchase_orders_needed: List[RequiredOrderItem]
    summary: RequiredOrdersSummary


class MaterialCostItem(BaseModel):
    """A single material cost line."""
    component_sku: Optional[str] = None
    component_name: Optional[str] = None
    quantity: float
    unit_cost: float
    total_cost: float


class LaborCostItem(BaseModel):
    """A single labor cost line."""
    operation: Optional[str] = None
    minutes: float
    hourly_rate: float
    cost: float


class CostBreakdownSummary(BaseModel):
    """Summary of cost breakdown."""
    total_material_cost: float
    total_labor_cost: float
    total_cost: float
    quantity_ordered: Any  # Decimal from DB
    unit_cost: float


class CostBreakdownResponse(BaseModel):
    """Response for GET /{order_id}/cost-breakdown."""
    order_id: int
    order_code: str
    material_costs: List[MaterialCostItem]
    labor_costs: List[LaborCostItem]
    summary: CostBreakdownSummary


class SpoolListItem(BaseModel):
    """A single spool assignment."""
    spool_id: int
    spool_code: Optional[str] = None
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    quantity_remaining: float
    assigned_at: Optional[str] = None


# Type alias for the spools list endpoint response
SpoolsListResponse = List[SpoolListItem]


class SpoolAssignmentResponse(BaseModel):
    """Response for POST /{order_id}/spools/{spool_id}."""
    order_id: int
    spool_id: int
    spool_code: Optional[str] = None
    assigned: bool
