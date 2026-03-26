"""
Notification Pydantic Schemas
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ============================================================================
# Request Schemas
# ============================================================================

class NotificationReply(BaseModel):
    """Reply to a notification thread"""
    body: str = Field(..., min_length=1, max_length=5000)


# ============================================================================
# Response Schemas
# ============================================================================

class NotificationResponse(BaseModel):
    """Single notification message"""
    id: int
    thread_id: str
    thread_subject: Optional[str] = None
    sales_order_id: Optional[int] = None
    sender_type: str
    sender_name: Optional[str] = None
    body: str
    read_at: Optional[datetime] = None
    source: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ThreadSummary(BaseModel):
    """Summary of a notification thread for list view"""
    thread_id: str
    thread_subject: Optional[str] = None
    sales_order_id: Optional[int] = None
    message_count: int
    unread_count: int
    last_message_at: datetime
    last_message_preview: str
    last_sender_name: Optional[str] = None


class UnreadCountResponse(BaseModel):
    """Unread notification count for badge"""
    unread_count: int
