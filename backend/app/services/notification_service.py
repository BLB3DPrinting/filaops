"""
Notification Service — Thread-based operator messaging.

Provides CRUD for the notifications table with thread grouping.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, case, desc
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.notification import Notification

logger = get_logger(__name__)


def create_notification(
    db: Session,
    *,
    thread_id: Optional[str] = None,
    thread_subject: str,
    sales_order_id: Optional[int] = None,
    sender_type: str = "system",
    sender_name: Optional[str] = None,
    body: str,
    source: str = "system",
) -> Notification:
    """Create a notification. Generates thread_id if not provided."""
    if not thread_id:
        thread_id = str(uuid.uuid4())

    notification = Notification(
        thread_id=thread_id,
        thread_subject=thread_subject,
        sales_order_id=sales_order_id,
        sender_type=sender_type,
        sender_name=sender_name,
        body=body,
        source=source,
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def list_threads(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    unread_only: bool = False,
) -> list[dict]:
    """List notification threads with summary info."""
    # Subquery: latest message per thread
    latest_msg = (
        db.query(
            Notification.thread_id,
            func.max(Notification.id).label("latest_id"),
            func.count(Notification.id).label("message_count"),
            func.count(case((Notification.read_at.is_(None), 1))).label("unread_count"),
            func.max(Notification.created_at).label("last_message_at"),
        )
        .group_by(Notification.thread_id)
    )

    if unread_only:
        # Only threads that have at least one unread message
        latest_msg = latest_msg.having(
            func.count(case((Notification.read_at.is_(None), 1))) > 0
        )

    latest_msg = latest_msg.order_by(desc("last_message_at"))
    latest_msg = latest_msg.offset(skip).limit(limit)
    thread_rows = latest_msg.all()

    if not thread_rows:
        return []

    # Get the latest notification for each thread (for preview + subject)
    latest_ids = [row.latest_id for row in thread_rows]
    latest_notifications = (
        db.query(Notification)
        .filter(Notification.id.in_(latest_ids))
        .all()
    )
    latest_by_id = {n.id: n for n in latest_notifications}

    threads = []
    for row in thread_rows:
        latest = latest_by_id.get(row.latest_id)
        if not latest:
            continue

        # Get thread_subject from earliest message in thread (the original)
        first_msg = (
            db.query(Notification.thread_subject, Notification.sales_order_id)
            .filter(Notification.thread_id == row.thread_id)
            .order_by(Notification.created_at)
            .first()
        )

        threads.append({
            "thread_id": row.thread_id,
            "thread_subject": first_msg.thread_subject if first_msg else None,
            "sales_order_id": first_msg.sales_order_id if first_msg else None,
            "message_count": row.message_count,
            "unread_count": row.unread_count,
            "last_message_at": row.last_message_at,
            "last_message_preview": latest.body[:100] if latest.body else "",
            "last_sender_name": latest.sender_name,
        })

    return threads


def get_thread(db: Session, thread_id: str) -> list[Notification]:
    """Get all messages in a thread, ordered chronologically."""
    messages = (
        db.query(Notification)
        .filter(Notification.thread_id == thread_id)
        .order_by(Notification.created_at)
        .all()
    )
    if not messages:
        raise HTTPException(status_code=404, detail="Thread not found")
    return messages


def reply_to_thread(
    db: Session,
    thread_id: str,
    *,
    sender_name: str,
    body: str,
) -> Notification:
    """Add a reply to an existing thread."""
    # Get the first message (verifies thread exists + provides metadata)
    first_msg = (
        db.query(Notification)
        .filter(Notification.thread_id == thread_id)
        .order_by(Notification.created_at)
        .first()
    )
    if not first_msg:
        raise HTTPException(status_code=404, detail="Thread not found")

    notification = Notification(
        thread_id=thread_id,
        thread_subject=first_msg.thread_subject if first_msg else None,
        sales_order_id=first_msg.sales_order_id if first_msg else None,
        sender_type="admin",
        sender_name=sender_name,
        body=body,
        source="admin",
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def mark_read(db: Session, notification_id: int) -> Notification:
    """Mark a single notification as read."""
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(notification)
    return notification


def mark_thread_read(db: Session, thread_id: str) -> int:
    """Mark all unread messages in a thread as read. Returns count updated."""
    now = datetime.now(timezone.utc)
    count = (
        db.query(Notification)
        .filter(
            Notification.thread_id == thread_id,
            Notification.read_at.is_(None),
        )
        .update({"read_at": now})
    )
    db.commit()
    return count


def get_unread_count(db: Session) -> int:
    """Get total count of unread notifications."""
    return (
        db.query(Notification)
        .filter(Notification.read_at.is_(None))
        .count()
    )
