"""
Manufacturing Routes Models

Work Centers, Resources, Routings, and Routing Operations.
"""
from sqlalchemy import (
    Column, Integer, String, Numeric, Boolean, DateTime, Text, Date, ForeignKey
)
from sqlalchemy.orm import relationship
from datetime import datetime

from app.db.base import Base


class Resource(Base):
    """
    An individual resource within a work center - e.g., a specific printer.

    Allows tracking of individual machines, their status, and Bambu integration.
    """
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    work_center_id = Column(Integer, ForeignKey("work_centers.id"), nullable=False, index=True)
    code = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=False)

    # Machine details
    machine_type = Column(String(100), nullable=True)  # 'X1C', 'P1S', 'A1'
    serial_number = Column(String(100), nullable=True)

    # Printer capabilities (for scheduling/filtering)
    # 'open' = open frame printer (A1, A1 Mini)
    # 'enclosed' = enclosed printer (P1S, P1P, X1C) - required for ABS/ASA/PC
    printer_class = Column(String(20), default="open", nullable=True)

    # Bambu Integration
    bambu_device_id = Column(String(100), nullable=True)
    bambu_ip_address = Column(String(50), nullable=True)

    # Capacity override
    capacity_hours_per_day = Column(Numeric(10, 2), nullable=True)

    # Status: 'available', 'busy', 'maintenance', 'offline'
    status = Column(String(50), default="available", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    work_center = relationship("WorkCenter", back_populates="resources")
    operations = relationship("ProductionOrderOperation", back_populates="resource")

    def __repr__(self):
        return f"<Resource {self.code}: {self.name} ({self.status})>"

    @property
    def is_available(self):
        """True if resource is available for scheduling"""
        return self.is_active and self.status == "available"

    @property
    def is_enclosed(self):
        """True if this is an enclosed printer (required for ABS/ASA/PC)"""
        return self.printer_class == "enclosed"

    @property
    def is_open(self):
        """True if this is an open frame printer"""
        return self.printer_class == "open" or self.printer_class is None


class Routing(Base):
    """
    A routing defines HOW to make a product - the sequence of operations.

    Like a BOM, routings have versions. Each product should have one active routing.
    Templates (is_template=True) have no product_id and can be assigned to products.
    """
    __tablename__ = "routings"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)  # Nullable for templates
    code = Column(String(50), nullable=False, index=True)
    name = Column(String(200), nullable=True)

    # Template flag - templates don't have a product_id
    is_template = Column(Boolean, default=False, nullable=False)

    # Version control
    version = Column(Integer, default=1, nullable=False)
    revision = Column(String(20), default="1.0", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Calculated totals (updated when operations change)
    total_setup_time_minutes = Column(Numeric(10, 2), nullable=True)
    total_run_time_minutes = Column(Numeric(10, 2), nullable=True)
    total_cost = Column(Numeric(18, 4), nullable=True)

    # Dates
    effective_date = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    product = relationship("Product", back_populates="routings")
    operations = relationship("RoutingOperation", back_populates="routing",
                              cascade="all, delete-orphan", order_by="RoutingOperation.sequence")

    def __repr__(self):
        return f"<Routing {self.code} for product_id={self.product_id}>"

    def recalculate_totals(self):
        """Recalculate total times and cost from operations"""
        total_setup = 0
        total_run = 0
        total_cost = 0

        for op in self.operations:
            if not op.is_active:
                continue
            total_setup += float(op.setup_time_minutes or 0)
            total_run += float(op.run_time_minutes or 0)
            total_run += float(op.wait_time_minutes or 0)
            total_run += float(op.move_time_minutes or 0)

            # Calculate operation cost
            op_time_hours = float(op.run_time_minutes or 0) / 60
            if op.work_center:
                rate = op.labor_rate_override or op.machine_rate_override or op.work_center.total_rate_per_hour
                total_cost += op_time_hours * float(rate or 0)

        self.total_setup_time_minutes = total_setup
        self.total_run_time_minutes = total_run
        self.total_cost = total_cost


class RoutingOperation(Base):
    """
    A single operation/step in a routing.

    Examples:
    - Print Base (FDM Pool, 2.5 hrs)
    - QC Inspect (QC Station, 5 min)
    - Assembly (Assembly Station, 10 min)
    """
    __tablename__ = "routing_operations"

    id = Column(Integer, primary_key=True, index=True)
    routing_id = Column(Integer, ForeignKey("routings.id", ondelete="CASCADE"), nullable=False, index=True)
    work_center_id = Column(Integer, ForeignKey("work_centers.id"), nullable=False, index=True)

    # Sequence
    sequence = Column(Integer, nullable=False)
    operation_code = Column(String(50), nullable=True)  # 'PRINT', 'QC', 'ASSEMBLE'
    operation_name = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)

    # Time (minutes)
    setup_time_minutes = Column(Numeric(10, 2), default=0, nullable=False)
    run_time_minutes = Column(Numeric(10, 2), nullable=False)
    wait_time_minutes = Column(Numeric(10, 2), default=0, nullable=False)
    move_time_minutes = Column(Numeric(10, 2), default=0, nullable=False)

    # Runtime source: 'manual', 'slicer', 'calculated'
    runtime_source = Column(String(50), default="manual", nullable=False)
    slicer_file_path = Column(String(500), nullable=True)

    # Quantity
    units_per_cycle = Column(Integer, default=1, nullable=False)
    scrap_rate_percent = Column(Numeric(5, 2), default=0, nullable=False)

    # Costing overrides
    labor_rate_override = Column(Numeric(18, 4), nullable=True)
    machine_rate_override = Column(Numeric(18, 4), nullable=True)

    # Dependencies
    predecessor_operation_id = Column(Integer, ForeignKey("routing_operations.id"), nullable=True)
    can_overlap = Column(Boolean, default=False, nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    routing = relationship("Routing", back_populates="operations")
    work_center = relationship("WorkCenter", back_populates="routing_operations")
    predecessor = relationship("RoutingOperation", remote_side=[id], foreign_keys=[predecessor_operation_id])
    materials = relationship("RoutingOperationMaterial", back_populates="routing_operation",
                            cascade="all, delete-orphan", order_by="RoutingOperationMaterial.id")

    def __repr__(self):
        return f"<RoutingOperation {self.sequence}: {self.operation_name}>"

    @property
    def total_time_minutes(self):
        """Total time for this operation (setup + run + wait + move)"""
        return (
            float(self.setup_time_minutes or 0) +
            float(self.run_time_minutes or 0) +
            float(self.wait_time_minutes or 0) +
            float(self.move_time_minutes or 0)
        )

    @property
    def calculated_cost(self):
        """Cost for this operation based on time and rates (includes setup + run)"""
        total_minutes = float(self.setup_time_minutes or 0) + float(self.run_time_minutes or 0)
        hours = total_minutes / 60
        rate = self.labor_rate_override or self.machine_rate_override
        if not rate and self.work_center:
            rate = self.work_center.total_rate_per_hour
        return hours * float(rate or 0)

    @property
    def material_cost(self):
        """Total material cost for this operation"""
        total = 0
        for mat in self.materials:
            total += mat.extended_cost
        return total


class RoutingOperationMaterial(Base):
    """
    Material required for a specific routing operation.
    
    This is the TEMPLATE - defines what materials are needed per unit.
    When a Production Order is released, these are copied to 
    ProductionOrderOperationMaterial with calculated quantities.
    
    Examples:
    - OP-10 Print: Black PLA 37g per unit
    - OP-40 Pack: Part Label 1 EA per unit
    - OP-50 Ship: 6x6x6 Box 1 EA per unit
    """
    __tablename__ = "routing_operation_materials"

    id = Column(Integer, primary_key=True, index=True)
    routing_operation_id = Column(Integer, ForeignKey("routing_operations.id", ondelete="CASCADE"), 
                                  nullable=False, index=True)
    component_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    
    # Quantity per unit/batch/order
    quantity = Column(Numeric(18, 6), nullable=False)
    quantity_per = Column(String(20), default="unit", nullable=False)  # unit, batch, order
    unit = Column(String(20), default="EA", nullable=False)
    
    # Scrap/waste allowance (percentage)
    scrap_factor = Column(Numeric(5, 2), default=0, nullable=True)
    
    # Flags
    is_cost_only = Column(Boolean, default=False, nullable=False)  # Don't consume inventory
    is_optional = Column(Boolean, default=False, nullable=False)   # Not required to complete op
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    routing_operation = relationship("RoutingOperation", back_populates="materials")
    component = relationship("Product", foreign_keys=[component_id])

    def __repr__(self):
        return f"<RoutingOperationMaterial {self.component.sku if self.component else 'N/A'}: {self.quantity} {self.unit}>"

    @property
    def unit_cost(self):
        """
        Cost per unit of this material.
        
        Component costs are stored per USAGE unit (e.g., $/G for filament).
        All UOM conversion happens at PO receiving, so no conversion needed here.
        """
        if not self.component:
            return 0
        # Use standard_cost, average_cost, or last_cost based on availability
        cost = self.component.standard_cost or self.component.average_cost or self.component.last_cost
        return float(cost) if cost else 0

    @property
    def extended_cost(self):
        """Total cost for this material line (quantity × unit_cost)"""
        qty = float(self.quantity or 0)
        scrap = float(self.scrap_factor or 0) / 100
        qty_with_scrap = qty * (1 + scrap)
        return qty_with_scrap * self.unit_cost

    def calculate_required_quantity(self, order_quantity: int) -> float:
        """
        Calculate total quantity required for a production order.
        
        Args:
            order_quantity: Number of units being produced
            
        Returns:
            Total quantity needed including scrap allowance
        """
        base_qty = float(self.quantity or 0)
        scrap = float(self.scrap_factor or 0) / 100
        
        if self.quantity_per == 'unit':
            gross_qty = base_qty * order_quantity
        else:  # batch or order
            gross_qty = base_qty
        
        return gross_qty * (1 + scrap)
