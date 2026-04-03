"""
Close Short Record Model

Immutable audit record for close-short actions on production orders and sales orders.
Captures before/after state for regulatory traceability (CAPA investigations).
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.sql import func

from app.db.base import Base


class CloseShortRecord(Base):
    """Audit record for close-short actions."""
    __tablename__ = "close_short_records"

    id = Column(Integer, primary_key=True, index=True)

    # What was closed short: 'production_order' or 'sales_order'
    entity_type = Column(String(20), nullable=False, index=True)
    entity_id = Column(Integer, nullable=False, index=True)

    # Who and when
    performed_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    performed_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    reason = Column(Text, nullable=True)

    # Snapshot of the decision inputs
    # Format: [{"line_id": 1, "before_qty": 5, "after_qty": 4, "reason": "..."}]
    line_adjustments = Column(JSON, nullable=True)

    # Format: [{"po_id": 39, "status": "complete", "ordered": 5, "completed": 4}]
    linked_po_states = Column(JSON, nullable=True)

    # Format: [{"product_id": 10, "on_hand": 4, "allocated": 0, "available": 4}]
    inventory_snapshot = Column(JSON, nullable=True)
