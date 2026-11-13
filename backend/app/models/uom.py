"""
Unit of Measure (UOM) model

Provides standardized units with conversion factors for proper
inventory consumption across different measurement systems.
"""
from decimal import Decimal

from sqlalchemy import Column, Integer, String, Numeric, Boolean, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship

from app.db.base import Base


class UnitOfMeasure(Base):
    """
    Unit of Measure model - standardized units with conversion factors.

    Units are grouped by class (weight, length, time, quantity).
    Each class has a base unit (KG, M, HR, EA) and all other units
    in the class have a conversion factor to the base unit.

    Example:
        - KG is the base unit for weight (to_base_factor = 1)
        - G has to_base_factor = 0.001 (1g = 0.001kg)
        - LB has to_base_factor = 0.45359237 (1lb = 0.45359237kg, exact)

    The standard rows and their exact factors are listed once, in
    ``app.services.unit_conversion.STANDARD_UNITS``. Convert through that
    module, not from these rows directly.
    """
    __tablename__ = "units_of_measure"
    __table_args__ = (
        CheckConstraint('to_base_factor > 0', name='check_to_base_factor_positive'),
    )

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False, index=True)  # EA, KG, G, LB, M, FT
    name = Column(String(50), nullable=False)  # Each, Kilogram, Gram
    symbol = Column(String(10), nullable=True)  # ea, kg, g, lb, m, ft
    uom_class = Column(String(20), nullable=False)  # quantity, weight, length, time

    # Self-referential FK to the base unit in this class (NULL for base units)
    base_unit_id = Column(Integer, ForeignKey("units_of_measure.id"), nullable=True)

    # Multiply quantity by this factor to get base unit quantity
    # e.g., 500 G * 0.001 = 0.5 KG
    # 15 places: the exact ounce is 0.028349523125 KG, which does not fit in 8.
    to_base_factor = Column(Numeric(30, 15), default=1, nullable=False)

    active = Column(Boolean, default=True, nullable=False)

    # Self-referential relationship
    base_unit = relationship("UnitOfMeasure", remote_side=[id], foreign_keys=[base_unit_id])

    def __repr__(self):
        return f"<UOM {self.code}: {self.name}>"

    def is_base_unit(self) -> bool:
        """Check if this is a base unit (base_unit_id is NULL)."""
        return self.base_unit_id is None

    def convert_to(self, quantity, to_unit: "UnitOfMeasure") -> Decimal:
        """
        Convert a quantity from this unit to another unit.

        Args:
            quantity: The quantity to convert
            to_unit: The target UnitOfMeasure

        Returns:
            Converted quantity

        Raises:
            ValueError: If units are not in the same class or invalid conversion factor
        """
        # Get actual values (SQLAlchemy returns values on instance access)
        from_class = str(self.uom_class)
        to_class = str(to_unit.uom_class)
        to_factor = Decimal(str(to_unit.to_base_factor))

        if from_class != to_class:
            raise ValueError(f"Cannot convert {from_class} to {to_class}")

        if to_factor == 0:
            raise ValueError(f"Invalid conversion factor for unit {to_unit.code}")

        qty = Decimal(str(quantity))

        # Convert to base unit first
        base_qty = qty * Decimal(str(self.to_base_factor))

        # Convert from base to target unit
        result = base_qty / to_factor

        return result
