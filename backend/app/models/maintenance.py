"""
Maintenance Models

MaintenanceLog  — tracks maintenance activities on printers for preventive
                  maintenance scheduling (freemium feature).
MaintenanceWindow — SCHED-7: a planned maintenance time block on a printer
                  or machine resource that the scheduling engine treats as
                  busy time. Completing a window writes a MaintenanceLog.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class MaintenanceLog(Base):
    """
    Maintenance Log model - tracks printer maintenance activities

    Supports:
    - Routine maintenance (cleaning, lubrication, etc.)
    - Repairs (part replacements, fixes)
    - Calibration (bed leveling, extrusion calibration)
    - Cleaning (nozzle cleaning, bed cleaning)
    """
    __tablename__ = "maintenance_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Printer relationship
    printer_id = Column(Integer, ForeignKey("printers.id", ondelete="CASCADE"), nullable=False, index=True)

    # Maintenance details
    maintenance_type = Column(String(50), nullable=False, index=True)
    # Valid types: routine, repair, calibration, cleaning

    description = Column(Text, nullable=True)
    performed_by = Column(String(100), nullable=True)
    performed_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    # Next maintenance scheduling
    next_due_at = Column(DateTime, nullable=True, index=True)

    # Cost tracking
    cost = Column(Numeric(10, 2), nullable=True)

    # Downtime tracking (for OEE calculations)
    downtime_minutes = Column(Integer, nullable=True)

    # Parts used (comma-separated list for simplicity)
    parts_used = Column(Text, nullable=True)

    # Additional notes
    notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    printer = relationship("Printer", back_populates="maintenance_logs")

    def __repr__(self):
        return f"<MaintenanceLog {self.id}: {self.maintenance_type} on Printer {self.printer_id}>"


# Window statuses that block scheduling (treated as busy time by the engine).
# 'completed' windows release the machine early; 'cancelled' never block.
WINDOW_BLOCKING_STATUSES = ("scheduled", "in_progress")

WINDOW_STATUSES = ("scheduled", "in_progress", "completed", "cancelled")


class MaintenanceWindow(Base):
    """
    Planned maintenance time block (SCHED-7).

    Exactly one of printer_id / resource_id is set (DB CHECK enforced) —
    Printer and Resource are distinct models with no FK between them, the
    same duality the scheduling engine handles via its ``is_printer`` flag.

    Times are naive UTC (matching every other DateTime in the schema).

    Lifecycle: scheduled → in_progress (window becomes active) →
    completed (operator confirms work done; writes a MaintenanceLog for
    printer windows) or cancelled (any time before completion).
    """
    __tablename__ = "maintenance_windows"
    __table_args__ = (
        CheckConstraint(
            "(printer_id IS NOT NULL) != (resource_id IS NOT NULL)",
            name="ck_maintenance_windows_one_machine",
        ),
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_maintenance_windows_valid_range",
        ),
        Index("ix_maintenance_windows_printer_starts", "printer_id", "starts_at"),
        Index("ix_maintenance_windows_resource_starts", "resource_id", "starts_at"),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Exactly one of these is set (CHECK constraint above)
    printer_id = Column(
        Integer, ForeignKey("printers.id", ondelete="CASCADE"), nullable=True
    )
    resource_id = Column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=True
    )

    # Window bounds — naive UTC
    starts_at = Column(DateTime, nullable=False)
    ends_at = Column(DateTime, nullable=False)

    reason = Column(String(255), nullable=True)

    # scheduled | in_progress | completed | cancelled
    status = Column(String(20), nullable=False, default="scheduled", index=True)

    # Set when the window is completed (printer windows only — MaintenanceLog
    # requires a printer_id)
    maintenance_log_id = Column(
        Integer, ForeignKey("maintenance_logs.id", ondelete="SET NULL"), nullable=True
    )

    created_by = Column(String(100), nullable=True)

    created_at = Column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships (one-directional — no back_populates so Printer/Resource
    # models stay untouched)
    printer = relationship("Printer", foreign_keys=[printer_id])
    resource = relationship("Resource", foreign_keys=[resource_id])
    maintenance_log = relationship("MaintenanceLog", foreign_keys=[maintenance_log_id])

    def __repr__(self):
        machine = (
            f"Printer {self.printer_id}"
            if self.printer_id is not None
            else f"Resource {self.resource_id}"
        )
        return (
            f"<MaintenanceWindow {self.id}: {machine} "
            f"{self.starts_at}–{self.ends_at} [{self.status}]>"
        )
