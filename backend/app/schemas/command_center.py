"""
Schemas for Command Center dashboard.

Provides action items and summary data for the "What do I need to do NOW?" view.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict
from enum import Enum
from pydantic import BaseModel, Field


class ActionItemType(str, Enum):
    """Types of action items for the command center."""
    BLOCKED_PO = "blocked_po"           # Production blocked by material shortage
    OVERDUE_SO = "overdue_so"           # Sales order past due date
    DUE_TODAY_SO = "due_today_so"       # Sales order due today
    OVERRUNNING_OP = "overrunning_op"   # Operation exceeding estimated time
    IDLE_RESOURCE = "idle_resource"     # Resource with work waiting
    MAINTENANCE_DUE = "maintenance_due" # SCHED-4: Printers due/overdue for maintenance


class ActionItemPriority(int, Enum):
    """Priority levels for action items (lower = more urgent)."""
    CRITICAL = 1  # Blocked POs, overdue SOs
    HIGH = 2      # Due today SOs
    MEDIUM = 3    # Overrunning operations
    LOW = 4       # Idle resources


class SuggestedAction(BaseModel):
    """A suggested action to resolve an issue."""
    label: str
    url: str
    action_type: Optional[str] = None  # 'navigate', 'api_call', etc.


class ActionItem(BaseModel):
    """A single action item requiring attention."""
    id: str = Field(description="Unique ID for deduplication (type_entityId)")
    type: ActionItemType
    priority: int = Field(ge=1, le=4)
    title: str
    description: str
    entity_type: str = Field(description="production_order, sales_order, operation, resource")
    entity_id: int
    entity_code: Optional[str] = None
    suggested_actions: List[SuggestedAction] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    metadata: Dict[str, str] = Field(default_factory=dict)


class ActionItemsResponse(BaseModel):
    """Response containing prioritized action items."""
    items: List[ActionItem]
    total_count: int
    counts_by_type: Dict[str, int] = Field(
        default_factory=dict,
        description="Count of items by type: {'blocked_po': 2, 'overdue_so': 1}"
    )


class TodaySummary(BaseModel):
    """Summary statistics for today's operations."""
    # Sales Orders
    orders_due_today: int = 0
    orders_due_today_ready: int = 0
    orders_shipped_today: int = 0
    orders_overdue: int = 0

    # Production
    production_in_progress: int = 0
    production_blocked: int = 0
    production_completed_today: int = 0
    operations_running: int = 0

    # Resources
    resources_total: int = 0
    resources_busy: int = 0
    resources_idle: int = 0
    resources_down: int = 0

    # Timestamps
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class OperationSummary(BaseModel):
    """Summary of a running operation for resource status."""
    operation_id: int
    production_order_id: int
    production_order_code: str
    operation_code: str
    sequence: int
    started_at: datetime
    planned_minutes: int
    product_name: Optional[str] = None


class ResourceStatus(BaseModel):
    """Status of a single resource/machine."""
    id: int
    code: str
    name: str
    work_center_id: Optional[int] = None
    work_center_name: Optional[str] = None
    status: str = Field(description="running, idle, maintenance, offline")
    current_operation: Optional[OperationSummary] = None
    idle_since: Optional[datetime] = None
    pending_operations_count: int = 0
    # SCHED-3: ID of the Printer linked to this resource (same work_center + matching
    # code/name heuristic).  None when no printer can be resolved.  Used by the
    # frontend to look up dispatch suggestions keyed by printer_id.
    printer_id: Optional[int] = None
    # SCHED-4: Maintenance due-soon badge — True when the linked printer has
    # next_due_at within MAINTENANCE_DUE_THRESHOLD_DAYS from now.
    maintenance_due_soon: bool = False


class ResourcesResponse(BaseModel):
    """Response containing all resource statuses."""
    resources: List[ResourceStatus]
    summary: Dict[str, int] = Field(
        default_factory=dict,
        description="Counts by status: {'running': 3, 'idle': 2}"
    )
