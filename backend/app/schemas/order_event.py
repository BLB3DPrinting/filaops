"""
Order Event Schemas

Pydantic models for the Order Event API endpoints
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of order events"""
    STATUS_CHANGE = "status_change"
    NOTE_ADDED = "note_added"
    PAYMENT_RECEIVED = "payment_received"
    PAYMENT_REFUNDED = "payment_refunded"
    PRODUCTION_STARTED = "production_started"
    PRODUCTION_COMPLETED = "production_completed"
    QC_PASSED = "qc_passed"
    QC_FAILED = "qc_failed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    ADDRESS_UPDATED = "address_updated"
    SHIPPING_CHARGE_UPDATED = "shipping_charge_updated"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"
    RESUMED = "resumed"
    CREATED = "created"


class OrderEventCreate(BaseModel):
    """Schema for creating an order event"""
    event_type: EventType
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    old_value: Optional[str] = Field(None, max_length=100)
    new_value: Optional[str] = Field(None, max_length=100)
    metadata_key: Optional[str] = Field(None, max_length=100)
    metadata_value: Optional[str] = Field(None, max_length=255)


class OrderEventResponse(BaseModel):
    """Schema for order event response"""
    id: int
    sales_order_id: int
    user_id: Optional[int] = None
    user_name: Optional[str] = None  # Populated from relationship
    event_type: str
    title: str
    description: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    metadata_key: Optional[str] = None
    metadata_value: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class OrderEventListResponse(BaseModel):
    """Schema for list of order events"""
    items: list[OrderEventResponse]
    total: int
