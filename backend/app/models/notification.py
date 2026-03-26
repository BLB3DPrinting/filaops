"""
Notification Model

Thread-based operator messaging system. Each notification belongs to a thread
identified by a UUID. Threads can be linked to sales orders.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from app.db.base import Base


class Notification(Base):
    """Operator notification / message in a threaded conversation."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    thread_id = Column(String(36), nullable=False, index=True)
    thread_subject = Column(String(200), nullable=True)
    sales_order_id = Column(
        Integer,
        ForeignKey("sales_orders.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    sender_type = Column(String(20), nullable=False, default="system")
    sender_name = Column(String(200), nullable=True)
    body = Column(Text, nullable=False)
    read_at = Column(DateTime, nullable=True)
    source = Column(String(20), default="system")
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    sales_order = relationship("SalesOrder")

    def __repr__(self):
        return f"<Notification {self.id} thread={self.thread_id[:8]}>"
