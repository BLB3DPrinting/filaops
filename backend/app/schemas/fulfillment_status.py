"""
Fulfillment Status Schema - API-301

Response schema for GET /api/v1/sales-orders/{order_id}/fulfillment-status
"""
from pydantic import BaseModel
from typing import List, Optional
from datetime import date
from enum import Enum


class FulfillmentState(str, Enum):
    """Possible fulfillment states for a sales order."""
    READY_TO_SHIP = "ready_to_ship"
    PARTIALLY_READY = "partially_ready"
    BLOCKED = "blocked"
    SHIPPED = "shipped"
    CANCELLED = "cancelled"


class LineStatus(BaseModel):
    """Status of a single order line."""
    line_id: int
    line_number: int
    product_id: Optional[int] = None
    product_sku: str
    product_name: str
    quantity_ordered: float
    quantity_allocated: float
    quantity_shipped: float
    quantity_remaining: float  # ordered - shipped
    is_ready: bool  # allocated >= remaining
    shortage: float  # max(0, remaining - allocated)
    blocking_reason: Optional[str] = None  # e.g., "Insufficient inventory"


class FulfillmentStatusSummary(BaseModel):
    """High-level fulfillment status."""
    state: FulfillmentState
    lines_total: int
    lines_ready: int
    lines_blocked: int
    fulfillment_percent: float  # 0-100
    can_ship_partial: bool  # At least one line ready
    can_ship_complete: bool  # All lines ready
    estimated_complete_date: Optional[date] = None  # Based on incoming POs


class FulfillmentStatus(BaseModel):
    """Complete fulfillment status for a sales order."""
    order_id: int
    order_number: str
    customer_name: str
    order_date: date
    requested_date: Optional[date] = None
    summary: FulfillmentStatusSummary
    lines: List[LineStatus]
