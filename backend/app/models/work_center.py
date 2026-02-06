"""
Work Center model for production scheduling.

Work Centers are logical groups of resources (e.g., "3D Printer Pool", "Assembly Station").
Resources (individual machines/printers) are defined in manufacturing.py.
"""
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base


class WorkCenter(Base):
    """
    Work Centers are logical production areas/departments.
    
    Examples:
    - "FDM-POOL" - Pool of FDM 3D printers (contains Leonardo, Donatelo, etc.)
    - "POST-PRINT" - Post-processing station
    - "QC" - Quality control station
    - "SHIP" - Shipping station
    
    Resources (individual machines) are linked via the Resource model.
    Operations are scheduled to Work Centers, then dispatched to specific Resources.
    """
    __tablename__ = "work_centers"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Work Center Type: 'machine' (has resources), 'station' (single station), 'production' (generic)
    center_type = Column(String(50), default="production", nullable=False)
    
    # Capacity Planning
    capacity_hours_per_day = Column(Numeric(10, 2), nullable=True)
    capacity_units_per_hour = Column(Numeric(10, 2), nullable=True)
    
    # Costing - multiple rate types for detailed job costing
    machine_rate_per_hour = Column(Numeric(18, 4), nullable=True)
    labor_rate_per_hour = Column(Numeric(18, 4), nullable=True)
    overhead_rate_per_hour = Column(Numeric(18, 4), nullable=True)
    
    # Simplified hourly rate (for backward compatibility and simple costing)
    hourly_rate = Column(Numeric(10, 2), default=0, nullable=False)
    
    # Scheduling
    is_bottleneck = Column(Boolean, default=False, nullable=False)
    scheduling_priority = Column(Integer, default=5, nullable=False)  # 1=highest, 10=lowest
    
    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    operations = relationship("ProductionOrderOperation", back_populates="work_center")
    printers = relationship("Printer", back_populates="work_center")
    resources = relationship("Resource", back_populates="work_center", cascade="all, delete-orphan")
    routing_operations = relationship("RoutingOperation", back_populates="work_center")
    
    def __repr__(self):
        return f"<WorkCenter {self.code}: {self.name}>"

    @property
    def total_rate_per_hour(self):
        """Combined hourly rate (machine + labor + overhead)"""
        machine = float(self.machine_rate_per_hour or 0)
        labor = float(self.labor_rate_per_hour or 0)
        overhead = float(self.overhead_rate_per_hour or 0)
        return machine + labor + overhead

    @property
    def available_resource_count(self):
        """Number of available resources in this work center"""
        return len([r for r in self.resources if r.is_active and r.status == 'available'])

    @property
    def total_resource_count(self):
        """Total number of resources in this work center"""
        return len(self.resources)
    
    # Backward compatibility aliases
    @property
    def available_machine_count(self):
        """Alias for available_resource_count"""
        return self.available_resource_count

    @property
    def total_machine_count(self):
        """Alias for total_resource_count"""
        return self.total_resource_count

