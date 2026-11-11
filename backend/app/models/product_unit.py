"""
A unit that belongs to one item, with its size in the item's stock unit.

The unit table knows that 1 KG is 1000 G for every item. It cannot know that
this item's BOX holds 12, or that this spool, stocked by the each, weighs
750 G. Those sizes live here, one row per item and unit.
"""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint

from app.db.base import Base


class ProductUnit(Base):
    """One of an item's own units.

    The size is stored the way it was typed, so it is never rounded on the way
    in. Exactly one of the two size columns is filled:

    - ``stock_units_per_unit``: "1 BOX = 12 EA" on an item stocked by the each.
    - ``units_per_stock_unit``: "1 EA = 750 G", stored on the G row of an item
      stocked by the each. The other way round would be 1 G = 1/750 EA, which
      has no exact decimal.

    Which units an item may have a row for is decided where rows are written,
    not here.
    """
    __tablename__ = "product_units"
    __table_args__ = (
        UniqueConstraint("product_id", "unit_code", name="uq_product_units_product_unit"),
        CheckConstraint(
            "(stock_units_per_unit IS NULL) <> (units_per_stock_unit IS NULL)",
            name="ck_product_units_one_size",
        ),
        CheckConstraint(
            "COALESCE(stock_units_per_unit, units_per_stock_unit) > 0",
            name="ck_product_units_size_positive",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_code = Column(String(10), nullable=False)
    stock_units_per_unit = Column(Numeric(20, 10), nullable=True)
    units_per_stock_unit = Column(Numeric(20, 10), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<ProductUnit product={self.product_id} {self.unit_code}>"
