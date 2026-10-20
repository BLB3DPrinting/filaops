"""
MRP (Material Requirements Planning) Pydantic Schemas

Schemas for:
- MRP run requests and responses
- Planned orders
- Requirements views
- Supply/demand timeline
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum


# ============================================================================
# Enums
# ============================================================================

class PlannedOrderType(str, Enum):
    """Type of planned order"""
    PURCHASE = "purchase"
    PRODUCTION = "production"


class PlannedOrderStatus(str, Enum):
    """Planned order lifecycle status"""
    PLANNED = "planned"  # MRP suggestion, can be auto-deleted
    FIRMED = "firmed"    # User confirmed, won't be deleted by MRP
    RELEASED = "released"  # Converted to actual PO or MO
    CANCELLED = "cancelled"


class MRPRunStatus(str, Enum):
    """MRP run status"""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DemandSource(str, Enum):
    """Source of demand for MRP"""
    PRODUCTION_ORDER = "production_order"
    SALES_ORDER = "sales_order"
    FORECAST = "forecast"
    SAFETY_STOCK = "safety_stock"


# ============================================================================
# MRP Run Schemas
# ============================================================================

class MRPRunRequest(BaseModel):
    """Request to run MRP calculation"""
    planning_horizon_days: int = Field(30, ge=1, le=365, description="Days to look ahead")
    include_draft_orders: bool = Field(True, description="Include draft production orders")
    regenerate_planned: bool = Field(True, description="Delete unfirmed planned orders first")


class MRPRunResponse(BaseModel):
    """Response from MRP run"""
    id: int
    run_date: datetime
    planning_horizon_days: int
    status: str
    orders_processed: int = 0
    components_analyzed: int = 0
    shortages_found: int = 0
    planned_orders_created: int = 0
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MRPRunSummary(BaseModel):
    """Summary of recent MRP runs"""
    runs: List[MRPRunResponse]
    last_successful_run: Optional[datetime] = None


# ============================================================================
# Planned Order Schemas
# ============================================================================

class PlannedOrderBase(BaseModel):
    """Base planned order fields"""
    order_type: PlannedOrderType
    product_id: int
    quantity: Decimal = Field(..., gt=0)
    due_date: date
    notes: Optional[str] = None


class PlannedOrderCreate(PlannedOrderBase):
    """Manually create a planned order"""
    start_date: Optional[date] = None  # Auto-calculated from lead time if not provided


class PlannedOrderUpdate(BaseModel):
    """Update a planned order"""
    quantity: Optional[Decimal] = Field(None, gt=0)
    due_date: Optional[date] = None
    start_date: Optional[date] = None
    notes: Optional[str] = None


class PlannedOrderResponse(BaseModel):
    """Planned order response"""
    id: int
    order_type: str
    product_id: int
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    quantity: Decimal
    due_date: date
    start_date: date
    source_demand_type: Optional[str] = None
    source_demand_id: Optional[int] = None
    mrp_run_id: Optional[int] = None
    status: str
    converted_to_po_id: Optional[int] = None
    converted_to_mo_id: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    firmed_at: Optional[datetime] = None
    released_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlannedOrderListResponse(BaseModel):
    """Paginated list of planned orders"""
    items: List[PlannedOrderResponse]
    total: int
    page: int = 1
    page_size: int = 50


# ============================================================================
# Requirements Schemas
# ============================================================================

class ComponentRequirement(BaseModel):
    """A single component requirement from BOM explosion"""
    product_id: int
    product_sku: str
    product_name: str
    bom_level: int  # 0=direct, 1=sub-component, etc
    gross_quantity: Decimal  # Quantity needed before netting
    scrap_factor: Decimal = 0  # BOM scrap allowance
    parent_product_id: Optional[int] = None  # What product needs this


class NetRequirement(BaseModel):
    """Net requirement after comparing to inventory"""
    product_id: int
    product_sku: str
    product_name: str
    gross_quantity: Decimal
    on_hand_quantity: Decimal
    allocated_quantity: Decimal
    available_quantity: Decimal
    incoming_quantity: Decimal  # From open POs
    safety_stock: Decimal
    net_shortage: Decimal  # How much we need to order
    lead_time_days: int
    reorder_point: Optional[Decimal] = None
    min_order_qty: Optional[Decimal] = None
    # MRP Make vs Buy indicator
    has_bom: bool = False  # True = make item (Create WO), False = buy item (Create PO)
    # Costing
    unit_cost: Decimal = Decimal("0")  # Standard or last cost for material costing


class RequirementsSummary(BaseModel):
    """Summary of all material requirements"""
    total_components_analyzed: int
    shortages_found: int
    components_in_stock: int
    requirements: List[NetRequirement]


# ============================================================================
# Supply/Demand Timeline
# ============================================================================

class SupplyDemandEntry(BaseModel):
    """A single supply or demand entry"""
    date: date
    entry_type: str  # 'demand', 'supply', 'on_hand'
    source_type: str  # 'production_order', 'purchase_order', 'safety_stock', 'inventory'
    source_id: Optional[int] = None
    source_code: Optional[str] = None
    quantity: Decimal
    running_balance: Optional[Decimal] = None


class SupplyDemandTimeline(BaseModel):
    """Timeline view of supply and demand for a product"""
    product_id: int
    product_sku: str
    product_name: str
    current_on_hand: Decimal
    current_available: Decimal
    safety_stock: Decimal
    entries: List[SupplyDemandEntry]
    projected_shortage_date: Optional[date] = None
    days_of_supply: Optional[int] = None


# ============================================================================
# Action Schemas
# ============================================================================

class FirmPlannedOrderRequest(BaseModel):
    """Firm a planned order (lock it in)"""
    notes: Optional[str] = None


class ReleasePlannedOrderRequest(BaseModel):
    """Release a planned order to actual PO or MO"""
    vendor_id: Optional[int] = None  # Required for purchase orders
    notes: Optional[str] = None


class ReleasePlannedOrderResponse(BaseModel):
    """Response from releasing a planned order"""
    planned_order_id: int
    order_type: str
    created_purchase_order_id: Optional[int] = None
    created_purchase_order_code: Optional[str] = None
    created_production_order_id: Optional[int] = None
    created_production_order_code: Optional[str] = None


# ============================================================================
# Pegging (Demand Tracing)
# ============================================================================

class PeggingEntry(BaseModel):
    """Shows what demand a supply order is fulfilling"""
    supply_type: str  # planned_order, purchase_order, production_order
    supply_id: int
    supply_code: str
    quantity: Decimal
    demand_type: str  # production_order, sales_order, forecast
    demand_id: int
    demand_code: Optional[str] = None


class ProductPegging(BaseModel):
    """Full pegging view for a product"""
    product_id: int
    product_sku: str
    supplies: List[PeggingEntry]
    demands: List[PeggingEntry]


# ============================================================================
# Make-vs-buy dry-run diff (MRP_ROUTING_MAKE_BUY)
# ============================================================================

class MakeBuyDiffEntry(BaseModel):
    """A product whose open planned orders would change type under the routing make-vs-buy rule"""
    product_id: int
    product_sku: str
    product_name: str
    procurement_type: Optional[str] = None
    has_bom: bool
    current_order_type: str  # today's decision: has_bom only
    proposed_order_type: str  # decision under the rule
    reason: str  # buy_override | bom | routing_materials | no_make_source
    planned_order_ids: List[int]


class MakeBuyDryRunDiff(BaseModel):
    """Read-only comparison of make-vs-buy decisions over open planned orders"""
    flag_enabled: bool  # MRP_ROUTING_MAKE_BUY as currently configured
    statuses: List[str]
    planned_orders_checked: int
    products_checked: int
    changes: List[MakeBuyDiffEntry]
    total_changes: int
