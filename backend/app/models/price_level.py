"""
Price Level Model

Stores wholesale pricing tiers for B2B customers.
Price level management (CRUD) is a Core feature.
Customer assignment to price levels is a PRO feature (pro_customer_price_levels table).
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Numeric, CheckConstraint
from datetime import datetime, timezone

from app.db.base import Base


class PriceLevel(Base):
    """
    A wholesale pricing tier, e.g. "Tier A — 25% off".

    Core manages the price level definitions.
    PRO manages which customers are assigned to each level.
    """
    __tablename__ = "price_levels"
    __table_args__ = (
        CheckConstraint(
            "discount_percent >= 0 AND discount_percent <= 100",
            name="ck_price_levels_discount_percent_range",
        ),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)       # e.g., "Tier A", "Wholesale"
    discount_percent = Column(Numeric(5, 2), nullable=False)      # 0.00–100.00
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=True)

    def __repr__(self) -> str:
        return f"<PriceLevel {self.name}: {self.discount_percent}% off>"
