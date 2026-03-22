"""
Manufacturing Routes Pydantic Schemas

Work Centers, Resources, Routings, and Routing Operations.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum


# Valid UOM codes - should match uom_service.INLINE_UOM_CONVERSIONS
VALID_UOM_CODES = ['EA', 'G', 'KG', 'LB', 'OZ', 'M', 'MM', 'CM', 'IN', 'FT', 'L', 'ML', 'PK', 'BOX', 'ROLL', 'HR']


def validate_uom_code(value: Optional[str]) -> Optional[str]:
    """
    Validate and normalize a UOM code.
    Returns None if input is None/empty, otherwise normalizes to uppercase.
    Raises ValueError if the unit is not in the allowed list.
    """
    if value is None or value.strip() == '':
        return None

    normalized = value.upper().strip()
    if normalized not in VALID_UOM_CODES:
        raise ValueError(f"Invalid unit '{value}'. Must be one of: {', '.join(VALID_UOM_CODES)}")
    return normalized


# ============================================================================
# Enums
# ============================================================================

class WorkCenterType(str, Enum):
    """Type of work center"""
    MACHINE = "machine"
    STATION = "station"
    LABOR = "labor"


class ResourceStatus(str, Enum):
    """Resource availability status"""
    AVAILABLE = "available"
    BUSY = "busy"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class RuntimeSource(str, Enum):
    """Where the operation runtime comes from"""
    MANUAL = "manual"
    SLICER = "slicer"
    CALCULATED = "calculated"


# ============================================================================
# Work Center Schemas
# ============================================================================

class WorkCenterBase(BaseModel):
    """Base work center fields"""
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    center_type: WorkCenterType = WorkCenterType.STATION

    # Capacity (can exceed 24 for machine pools with multiple resources)
    capacity_hours_per_day: Optional[Decimal] = Field(None, ge=0)
    capacity_units_per_hour: Optional[Decimal] = Field(None, ge=0)

    # Costing
    machine_rate_per_hour: Optional[Decimal] = Field(None, ge=0)
    labor_rate_per_hour: Optional[Decimal] = Field(None, ge=0)
    overhead_rate_per_hour: Optional[Decimal] = Field(None, ge=0)

    # Scheduling
    is_bottleneck: bool = False
    scheduling_priority: int = Field(50, ge=0, le=100)

    is_active: bool = True


class WorkCenterCreate(WorkCenterBase):
    """Create a new work center"""
    pass


class WorkCenterUpdate(BaseModel):
    """Update an existing work center"""
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    center_type: Optional[WorkCenterType] = None
    capacity_hours_per_day: Optional[Decimal] = None
    capacity_units_per_hour: Optional[Decimal] = None
    machine_rate_per_hour: Optional[Decimal] = None
    labor_rate_per_hour: Optional[Decimal] = None
    overhead_rate_per_hour: Optional[Decimal] = None
    is_bottleneck: Optional[bool] = None
    scheduling_priority: Optional[int] = None
    is_active: Optional[bool] = None


class WorkCenterResponse(WorkCenterBase):
    """Work center response"""
    id: int
    created_at: datetime
    updated_at: datetime
    resource_count: int = 0
    total_rate_per_hour: Decimal = Decimal("0")

    class Config:
        from_attributes = True


class WorkCenterListResponse(BaseModel):
    """Work center list item"""
    id: int
    code: str
    name: str
    center_type: str
    capacity_hours_per_day: Optional[Decimal] = None
    total_rate_per_hour: Decimal = Decimal("0")
    resource_count: int = 0
    is_bottleneck: bool = False
    is_active: bool = True

    class Config:
        from_attributes = True


# ============================================================================
# Resource Schemas
# ============================================================================

class ResourceBase(BaseModel):
    """Base resource fields"""
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=200)
    machine_type: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=100)
    bambu_device_id: Optional[str] = Field(None, max_length=100)
    bambu_ip_address: Optional[str] = Field(None, max_length=50)
    capacity_hours_per_day: Optional[Decimal] = Field(None, ge=0, le=24)
    status: ResourceStatus = ResourceStatus.AVAILABLE
    is_active: bool = True


class ResourceCreate(ResourceBase):
    """Create a new resource (work_center_id is optional, taken from URL path)"""
    work_center_id: Optional[int] = None


class ResourceUpdate(BaseModel):
    """Update an existing resource"""
    work_center_id: Optional[int] = None  # Allow reassigning to different work center
    code: Optional[str] = Field(None, min_length=1, max_length=50)
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    machine_type: Optional[str] = None
    serial_number: Optional[str] = None
    bambu_device_id: Optional[str] = None
    bambu_ip_address: Optional[str] = None
    capacity_hours_per_day: Optional[Decimal] = None
    status: Optional[ResourceStatus] = None
    is_active: Optional[bool] = None


class ResourceResponse(ResourceBase):
    """Resource response"""
    id: int
    work_center_id: int
    work_center_code: Optional[str] = None
    work_center_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Routing Operation Schemas
# ============================================================================

class RoutingOperationBase(BaseModel):
    """Base routing operation fields"""
    work_center_id: int
    sequence: int = Field(..., ge=1)
    operation_code: Optional[str] = Field(None, max_length=50)
    operation_name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None

    # Times (minutes)
    setup_time_minutes: Decimal = Field(Decimal("0"), ge=0)
    run_time_minutes: Decimal = Field(..., ge=0)
    wait_time_minutes: Decimal = Field(Decimal("0"), ge=0)
    move_time_minutes: Decimal = Field(Decimal("0"), ge=0)

    runtime_source: RuntimeSource = RuntimeSource.MANUAL
    slicer_file_path: Optional[str] = None

    # Quantity
    units_per_cycle: int = Field(1, ge=1)
    scrap_rate_percent: Decimal = Field(Decimal("0"), ge=0, le=100)

    # Cost overrides
    labor_rate_override: Optional[Decimal] = None
    machine_rate_override: Optional[Decimal] = None

    # Dependencies
    predecessor_operation_id: Optional[int] = None
    can_overlap: bool = False

    is_active: bool = True


class RoutingOperationCreate(RoutingOperationBase):
    """Create a new routing operation"""
    pass


class RoutingOperationUpdate(BaseModel):
    """Update an existing routing operation"""
    work_center_id: Optional[int] = None
    sequence: Optional[int] = None
    operation_code: Optional[str] = None
    operation_name: Optional[str] = None
    description: Optional[str] = None
    setup_time_minutes: Optional[Decimal] = None
    run_time_minutes: Optional[Decimal] = None
    wait_time_minutes: Optional[Decimal] = None
    move_time_minutes: Optional[Decimal] = None
    runtime_source: Optional[RuntimeSource] = None
    slicer_file_path: Optional[str] = None
    units_per_cycle: Optional[int] = None
    scrap_rate_percent: Optional[Decimal] = None
    labor_rate_override: Optional[Decimal] = None
    machine_rate_override: Optional[Decimal] = None
    predecessor_operation_id: Optional[int] = None
    can_overlap: Optional[bool] = None
    is_active: Optional[bool] = None


class RoutingOperationResponse(RoutingOperationBase):
    """Routing operation response"""
    id: int
    routing_id: int
    work_center_code: Optional[str] = None
    work_center_name: Optional[str] = None
    total_time_minutes: Decimal = Decimal("0")
    calculated_cost: Decimal = Decimal("0")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Routing Schemas
# ============================================================================

class RoutingBase(BaseModel):
    """Base routing fields"""
    product_id: Optional[int] = None  # Optional for templates
    code: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=200)
    is_template: bool = False  # True for routing templates
    version: int = Field(1, ge=1)
    revision: str = Field("1.0", max_length=20)
    effective_date: Optional[date] = None
    notes: Optional[str] = None
    is_active: bool = True


class RoutingCreate(RoutingBase):
    """Create a new routing"""
    operations: List[RoutingOperationCreate] = Field(default_factory=list)


class RoutingUpdate(BaseModel):
    """Update an existing routing"""
    code: Optional[str] = None
    name: Optional[str] = None
    is_template: Optional[bool] = None
    revision: Optional[str] = None
    effective_date: Optional[date] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class RoutingResponse(RoutingBase):
    """Routing response with operations"""
    id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    total_setup_time_minutes: Optional[Decimal] = None
    total_run_time_minutes: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    operations: List[RoutingOperationResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RoutingListResponse(BaseModel):
    """Routing list item"""
    id: int
    product_id: Optional[int] = None  # Nullable for templates
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    code: str
    name: Optional[str] = None
    is_template: bool = False
    version: int
    revision: str
    is_active: bool
    total_run_time_minutes: Optional[Decimal] = None
    total_cost: Optional[Decimal] = None
    operation_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Capacity Schemas
# ============================================================================

class CapacitySummary(BaseModel):
    """Capacity summary for a work center"""
    work_center_id: int
    work_center_code: str
    work_center_name: str
    capacity_hours_per_day: Decimal
    scheduled_hours: Decimal = Decimal("0")
    available_hours: Decimal = Decimal("0")
    utilization_percent: Decimal = Decimal("0")
    is_bottleneck: bool = False


class CapacityCheckRequest(BaseModel):
    """Request to check if we can produce X units by date Y"""
    product_id: int
    quantity: int = Field(..., ge=1)
    required_date: date


class CapacityCheckResponse(BaseModel):
    """Response to capacity check"""
    can_fulfill: bool
    earliest_completion_date: date
    bottleneck_work_center: Optional[str] = None
    details: List[CapacitySummary] = Field(default_factory=list)


# ============================================================================
# Apply Template Schemas
# ============================================================================

class OperationTimeOverride(BaseModel):
    """Override times for a specific operation when applying a template"""
    operation_code: str  # e.g., "PRINT", "QC", "ASSEMBLE"
    run_time_minutes: Optional[Decimal] = None
    setup_time_minutes: Optional[Decimal] = None


class ApplyTemplateRequest(BaseModel):
    """Request to apply a routing template to a product"""
    product_id: int
    template_id: int
    overrides: List[OperationTimeOverride] = Field(default_factory=list)


class ApplyTemplateResponse(BaseModel):
    """Response after applying a template"""
    routing_id: int
    routing_code: str
    product_sku: str
    product_name: str
    operations: List[RoutingOperationResponse]
    total_run_time_minutes: Decimal
    total_cost: Decimal
    message: str


# ============================================================================
# Routing Operation Material Schemas (Manufacturing BOM)
# ============================================================================

class QuantityPer(str, Enum):
    """How to interpret quantity - per unit, batch, or order"""
    UNIT = "unit"       # Multiply by order quantity
    BATCH = "batch"     # Fixed per batch
    ORDER = "order"     # Fixed per order


class RoutingOperationMaterialBase(BaseModel):
    """Base fields for routing operation material"""
    component_id: int
    quantity: Decimal = Field(..., gt=0)
    quantity_per: QuantityPer = QuantityPer.UNIT
    unit: str = Field("EA", max_length=20)
    scrap_factor: Optional[Decimal] = Field(Decimal("0"), ge=0, le=100)
    is_cost_only: bool = False
    is_optional: bool = False
    is_variable: bool = False
    notes: Optional[str] = None

    @field_validator('unit')
    @classmethod
    def validate_unit(cls, v: str) -> str:
        """Validate and normalize the unit of measure."""
        result = validate_uom_code(v)
        return result if result else "EA"  # Default to EA if empty


class RoutingOperationMaterialCreate(RoutingOperationMaterialBase):
    """Create a new routing operation material"""
    pass


class RoutingOperationMaterialUpdate(BaseModel):
    """Update an existing routing operation material"""
    component_id: Optional[int] = None
    quantity: Optional[Decimal] = Field(None, gt=0)
    quantity_per: Optional[QuantityPer] = None
    unit: Optional[str] = Field(None, max_length=20)
    scrap_factor: Optional[Decimal] = Field(None, ge=0, le=100)
    is_cost_only: Optional[bool] = None
    is_optional: Optional[bool] = None
    is_variable: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator('unit')
    @classmethod
    def validate_unit(cls, v: Optional[str]) -> Optional[str]:
        """Validate and normalize the unit of measure."""
        return validate_uom_code(v)


class RoutingOperationMaterialResponse(RoutingOperationMaterialBase):
    """Routing operation material response"""
    id: int
    routing_operation_id: int
    component_sku: Optional[str] = None
    component_name: Optional[str] = None
    unit_cost: Decimal = Decimal("0")
    extended_cost: Decimal = Decimal("0")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Production Order Operation Material Schemas
# ============================================================================

class POOperationMaterialStatus(str, Enum):
    """Status of PO operation material"""
    PENDING = "pending"       # Not yet allocated
    ALLOCATED = "allocated"   # Inventory reserved
    CONSUMED = "consumed"     # Used in production
    RETURNED = "returned"     # Excess returned


class POOperationMaterialResponse(BaseModel):
    """Production order operation material response"""
    id: int
    production_order_operation_id: int
    component_id: int
    component_sku: Optional[str] = None
    component_name: Optional[str] = None
    routing_operation_material_id: Optional[int] = None
    quantity_required: Decimal
    quantity_allocated: Decimal = Decimal("0")
    quantity_consumed: Decimal = Decimal("0")
    quantity_remaining: Decimal = Decimal("0")
    unit: str
    lot_number: Optional[str] = None
    status: POOperationMaterialStatus
    shortage_quantity: Decimal = Decimal("0")
    consumed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class POOperationMaterialConsume(BaseModel):
    """Request to consume a PO operation material"""
    quantity: Decimal = Field(..., gt=0)
    lot_number: Optional[str] = None


class POOperationMaterialAllocate(BaseModel):
    """Request to allocate inventory to a PO operation material"""
    quantity: Decimal = Field(..., gt=0)
    lot_number: Optional[str] = None


# ============================================================================
# Extended Routing Operation Response with Materials
# ============================================================================

class RoutingOperationWithMaterialsResponse(RoutingOperationResponse):
    """Routing operation with its materials"""
    materials: List[RoutingOperationMaterialResponse] = Field(default_factory=list)
    material_cost: Decimal = Decimal("0")
    total_cost_with_materials: Decimal = Decimal("0")


# ============================================================================
# Manufacturing BOM View (unified view of routing + materials)
# ============================================================================

class ManufacturingBOMResponse(BaseModel):
    """Complete Manufacturing BOM for a product (routing + operation materials)"""
    routing_id: int
    routing_code: str
    routing_name: Optional[str] = None
    product_id: int
    product_sku: str
    product_name: str
    version: int
    revision: str
    is_active: bool
    operations: List[RoutingOperationWithMaterialsResponse] = Field(default_factory=list)
    total_labor_cost: Decimal = Decimal("0")
    total_material_cost: Decimal = Decimal("0")
    total_cost: Decimal = Decimal("0")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
