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
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class QualityPlan(Base):
    """A product's inspection plan header. ``product_id`` is nullable so a plan
    can be a reusable template (is_template=True), mirroring Routing."""

    __tablename__ = "quality_plans"
    __table_args__ = (
        # A template has no product; a product-specific plan must name one. This
        # keeps scope-based consumers unambiguous (no orphan plans, no
        # product-bound templates). Mirrors the migration CHECK.
        CheckConstraint(
            "(is_template AND product_id IS NULL) OR "
            "(NOT is_template AND product_id IS NOT NULL)",
            name="ck_quality_plans_template_scope",
        ),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    code = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    # server_default mirrors migration 097 so create_all (tests/self-host) and
    # Alembic (deploy) build identical schema.
    version = Column(Integer, default=1, server_default="1", nullable=False)
    revision = Column(String(20), default="1.0", server_default="1.0", nullable=False)
    is_active = Column(Boolean, default=True, server_default=text("true"), nullable=False)
    is_template = Column(Boolean, default=False, server_default=text("false"), nullable=False)
    effective_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False,
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
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
        # A stable code is unique within a plan (so it's an unambiguous SPC key),
        # but the SAME code recurs across plan versions on purpose. Partial so
        # manual rows (code NULL) are unconstrained. Mirrors migration 098.
        Index(
            "uq_quality_plan_characteristics_plan_code",
            "quality_plan_id",
            "code",
            unique=True,
            postgresql_where=text("code IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True)
    quality_plan_id = Column(
        Integer,
        ForeignKey("quality_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Stable, rename-/edit-proof key for SPC series (keyed on (product_id, code)).
    # Nullable: manual/ad-hoc characteristics fall back to text grouping.
    code = Column(String(50), nullable=True)
    characteristic = Column(String(100), nullable=False)
    nominal = Column(Numeric(18, 4), nullable=True)
    lower_limit = Column(Numeric(18, 4), nullable=True)
    upper_limit = Column(Numeric(18, 4), nullable=True)
    unit = Column(String(20), nullable=True)
    sequence = Column(Integer, default=0, server_default="0", nullable=False)
    severity = Column(String(20), nullable=True)  # minor | major | critical
    # Optional: which routing step this characteristic is inspected at.
    routing_operation_id = Column(
        Integer,
        ForeignKey("routing_operations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        server_default=func.now(), nullable=False,
    )

    plan = relationship("QualityPlan", back_populates="characteristics")

    def __repr__(self) -> str:
        return f"<QualityPlanCharacteristic {self.characteristic}>"
