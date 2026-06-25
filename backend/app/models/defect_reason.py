"""
Defect Reason model

A configurable taxonomy of QC defect reasons (#784). Distinct from
``ScrapReason``: a scrap reason explains why material was destroyed; a defect
reason classifies *what was wrong* at inspection (category + severity), and is
referenced by ``QCInspection.defect_reason_id`` so failed inspections carry a
structured, reportable cause rather than only free text.

Maintainer decision (locked): a dedicated table, NOT reused ``ScrapReason``.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)

from app.db.base import Base


class DefectReason(Base):
    """A configurable QC defect classification (category + severity)."""

    __tablename__ = "defect_reasons"
    __table_args__ = (
        # Mirror migration 095 so create_all (tests/self-host) enforces the same
        # severity domain the migration does on a real deployment.
        CheckConstraint(
            "severity IN ('minor', 'major', 'critical')",
            name="ck_defect_reasons_severity",
        ),
    )

    id = Column(Integer, primary_key=True)  # PK is auto-indexed; no redundant ix_*_id
    code = Column(String(50), unique=True, nullable=False, index=True)  # e.g. "layer_shift"
    name = Column(String(100), nullable=False)  # Display name
    description = Column(Text, nullable=True)

    # Grouping for reporting, e.g. "dimensional", "cosmetic", "functional".
    # Free-form (categories are operator-configurable), unlike severity.
    category = Column(String(50), nullable=True)
    # AQL-style severity. CHECK-constrained at the DB so it cannot drift.
    severity = Column(String(20), nullable=True)  # minor | major | critical

    active = Column(Boolean, default=True, nullable=False)
    sequence = Column(Integer, default=0)  # ordering in dropdowns

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<DefectReason {self.code}: {self.name} ({self.severity})>"
