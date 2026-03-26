"""
Notification Endpoints

Thread-based operator messaging — list threads, view messages, reply, mark read.
"""
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.api.v1.deps import get_current_staff_user
from app.schemas.notification import (
    NotificationResponse,
    NotificationReply,
    ThreadSummary,
    UnreadCountResponse,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Get count of unread notifications for badge display."""
    count = notification_service.get_unread_count(db)
    return UnreadCountResponse(unread_count=count)


@router.get("/", response_model=List[ThreadSummary])
async def list_threads(
    skip: int = 0,
    limit: int = 50,
    unread_only: bool = Query(False, description="Only show threads with unread messages"),
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """List notification threads with summary info."""
    threads = notification_service.list_threads(
        db, skip=skip, limit=limit, unread_only=unread_only
    )
    return threads


@router.get("/{thread_id}", response_model=List[NotificationResponse])
async def get_thread(
    thread_id: str,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Get all messages in a notification thread."""
    return notification_service.get_thread(db, thread_id)


@router.post("/{thread_id}/reply", response_model=NotificationResponse)
async def reply_to_thread(
    thread_id: str,
    reply: NotificationReply,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Reply to a notification thread."""
    sender_name = getattr(current_user, "full_name", None) or current_user.email
    return notification_service.reply_to_thread(
        db, thread_id, sender_name=sender_name, body=reply.body
    )


@router.post("/{thread_id}/read")
async def mark_thread_read(
    thread_id: str,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Mark all messages in a thread as read."""
    count = notification_service.mark_thread_read(db, thread_id)
    return {"marked_read": count}


@router.post("/{notification_id}/mark-read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: int,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Mark a single notification as read."""
    return notification_service.mark_read(db, notification_id)
