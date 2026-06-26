"""Quality Plan models (#784) — a per-product definition of WHAT to inspect.

Mirrors the BOM/Routing shape: a product-level header (nullable product_id so a
plan can be a reusable template) with child characteristic rows. Each
characteristic names a measurable (nominal + spec limits + unit) and may
optionally pin to a specific routing operation, so a routing with several
inspection steps can specify which characteristics belong to which step.

Core owns this table; a later PR pre-populates QC measurements from the active
plan, and PRO layers approval / e-signature / AQL sampling on top via FK.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class QualityPlan(Base):
    """A product's inspection plan header. ``product_id`` is nullable so a plan
    can be a reusable template (is_template=True), mirroring Routing."""

    __tablename__ = "quality_plans"

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    code = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    version = Column(Integer, default=1, nullable=False)
    revision = Column(String(20), default="1.0", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_template = Column(Boolean, default=False, nullable=False)
    effective_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    characteristics = relationship(
        "QualityPlanCharacteristic",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="(QualityPlanCharacteristic.sequence, QualityPlanCharacteristic.id)",
    )

    def __repr__(self) -> str:
        return f"<QualityPlan {self.code} product_id={self.product_id}>"


class QualityPlanCharacteristic(Base):
    """One thing to measure under a quality plan. Spec columns mirror
    QCInspectionMeasurement so the inspection form can be seeded from the plan."""

    __tablename__ = "quality_plan_characteristics"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('minor', 'major', 'critical')",
            name="ck_quality_plan_characteristics_severity",
        ),
    )

    id = Column(Integer, primary_key=True)
    quality_plan_id = Column(
        Integer,
        ForeignKey("quality_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    characteristic = Column(String(100), nullable=False)
    nominal = Column(Numeric(18, 4), nullable=True)
    lower_limit = Column(Numeric(18, 4), nullable=True)
    upper_limit = Column(Numeric(18, 4), nullable=True)
    unit = Column(String(20), nullable=True)
    sequence = Column(Integer, default=0, nullable=False)
    severity = Column(String(20), nullable=True)  # minor | major | critical
    # Optional: which routing step this characteristic is inspected at.
    routing_operation_id = Column(
        Integer,
        ForeignKey("routing_operations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    plan = relationship("QualityPlan", back_populates="characteristics")

    def __repr__(self) -> str:
        return f"<QualityPlanCharacteristic {self.characteristic}>"
