"""
Adjustment Reason Model

Stores configurable reasons for inventory adjustments.
Allows shops to define their own adjustment categories for accounting compliance.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime

from app.db.base import Base


class AdjustmentReason(Base):
    """
    A reason for adjusting inventory quantities.

    Examples:
    - physical_count: Discrepancy found during physical count
    - damaged: Item damaged in warehouse
    - correction: Data entry correction
    """
    __tablename__ = "adjustment_reasons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    sequence = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<AdjustmentReason {self.code}: {self.name}>"
