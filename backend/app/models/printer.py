"""
Printer model - Brand-agnostic printer management
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db.base import Base


class Printer(Base):
    """
    Printer model - supports multiple printer brands with flexible configuration.

    Brand support:
    - BambuLab (X1C, P1S, A1, etc.)
    - Klipper/Moonraker
    - OctoPrint
    - Prusa Connect
    - Generic/Manual entry
    """
    __tablename__ = "printers"

    id = Column(Integer, primary_key=True, index=True)

    # Printer identification
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    model = Column(String(100), nullable=False)
    serial_number = Column(String(100), nullable=True)

    # Brand identification (bambulab, klipper, octoprint, prusa, creality, generic)
    brand = Column(String(50), nullable=False, default="generic", index=True)

    # Network - basic fields kept for quick access
    ip_address = Column(String(50), nullable=True)
    mqtt_topic = Column(String(255), nullable=True)

    # Connection configuration - JSON for brand-specific settings
    # Examples:
    # BambuLab: {"access_code": "xxx", "serial": "xxx"}
    # Klipper: {"port": 7125, "api_key": "xxx"}
    # OctoPrint: {"port": 5000, "api_key": "xxx"}
    connection_config = Column(JSON, nullable=True, default=dict)

    # Printer capabilities - JSON for feature detection
    # {"bed_size": [256, 256, 256], "heated_bed": true, "enclosure": true,
    #  "ams_slots": 4, "camera": true, "max_temp_hotend": 300}
    # Canonical unit-suffixed keys (bed_width_mm, chamber_temp_max_c,
    # nozzle_count, has_ams_support, discontinued, ...) come from the model
    # catalog: app/services/printer_discovery/models.py::PrinterCapabilities.
    # Schemaless on purpose — new capability fields need no migration.
    capabilities = Column(JSON, nullable=True, default=dict)

    # Status
    status = Column(String(50), nullable=True, default='offline')
    # offline, idle, printing, paused, error, maintenance

    # Last communication timestamp
    last_seen = Column(DateTime, nullable=True)

    # Location
    location = Column(String(255), nullable=True)

    # Work center association (optional - for multi-site operations)
    work_center_id = Column(Integer, ForeignKey("work_centers.id"), nullable=True)

    # Notes for operators
    notes = Column(Text, nullable=True)

    # Active flag
    active = Column(Boolean, default=True, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    print_jobs = relationship("PrintJob", back_populates="printer")
    work_center = relationship("WorkCenter", back_populates="printers")
    maintenance_logs = relationship("MaintenanceLog", back_populates="printer", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Printer {self.code}: {self.name} [{self.brand}] ({self.status})>"

    @property
    def is_online(self) -> bool:
        """Check if printer was seen recently (within 5 minutes)"""
        if not self.last_seen:
            return False
        # last_seen is stored as naive UTC (DateTime without timezone=True).
        # Use a naive UTC now to avoid aware-vs-naive TypeError.
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        last_seen = self.last_seen.replace(tzinfo=None) if self.last_seen.tzinfo else self.last_seen
        return (now_utc - last_seen).total_seconds() < 300

    @property
    def has_ams(self) -> bool:
        """Check if printer has AMS/multi-material capability"""
        if not self.capabilities:
            return False
        return self.capabilities.get("ams_slots", 0) > 0

    @property
    def has_camera(self) -> bool:
        """Check if printer has camera support"""
        if not self.capabilities:
            return False
        return self.capabilities.get("camera", False)
