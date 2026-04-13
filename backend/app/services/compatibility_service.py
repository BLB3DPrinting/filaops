"""
Material-Printer Compatibility Validation Service

Checks whether a printer (or resource) is compatible with the materials
required by a production order operation:
  - Enclosure: material requires_enclosure vs printer enclosure capability
  - Temperature: material nozzle/bed temp vs printer max temps
  - Filament diameter: material diameter vs printer supported diameters
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.material import MaterialType
from app.models.printer import Printer
from app.models.manufacturing import Resource
from app.models.product import Product
from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
)


@dataclass
class CompatibilityIssue:
    """A single compatibility finding."""

    severity: str  # "error" | "warning"
    check: str  # "enclosure" | "nozzle_temp" | "bed_temp" | "diameter"
    message: str
    material_name: str
    printer_name: str


@dataclass
class OperationCompatibility:
    """Compatibility result for one operation."""

    operation_id: int
    operation_name: Optional[str]
    printer_name: Optional[str]
    issues: List[CompatibilityIssue] = field(default_factory=list)

    @property
    def compatible(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


@dataclass
class OrderCompatibility:
    """Compatibility result for an entire production order."""

    production_order_id: int
    production_order_code: str
    operations: List[OperationCompatibility] = field(default_factory=list)

    @property
    def compatible(self) -> bool:
        return all(op.compatible for op in self.operations)

    @property
    def total_issues(self) -> int:
        return sum(len(op.issues) for op in self.operations)


# ---------------------------------------------------------------------------
# Core check: material vs printer capabilities
# ---------------------------------------------------------------------------

def _get_printer_capabilities(
    printer: Optional[Printer],
    resource: Optional[Resource],
) -> dict:
    """Merge printer JSON capabilities with resource metadata."""
    caps: dict = {}
    if printer and printer.capabilities:
        caps = dict(printer.capabilities)
    # Resource.printer_class is the authoritative enclosure flag when no
    # Printer JSON exists — e.g. for resources not linked to a Printer row.
    if resource:
        if "enclosure" not in caps:
            caps["enclosure"] = resource.printer_class == "enclosed"
    return caps


def _resolve_material_type(product: Product, db: Session) -> Optional[MaterialType]:
    """Get MaterialType for a product, loading via FK if not already loaded."""
    if product.material_type_id is None:
        return None
    if product.material_type is not None:
        return product.material_type
    return db.get(MaterialType, product.material_type_id)


def check_material_printer(
    material_type: MaterialType,
    printer_name: str,
    caps: dict,
) -> List[CompatibilityIssue]:
    """Run all compatibility checks for one material against one printer."""
    issues: List[CompatibilityIssue] = []
    mat_name = material_type.name

    # --- Enclosure ---
    # If enclosure capability is unknown (missing from caps), downgrade to a
    # warning rather than a hard error — we don't want to block scheduling
    # when the printer simply hasn't had its enclosure capability configured.
    if material_type.requires_enclosure:
        enclosure_cap = caps.get("enclosure")
        if enclosure_cap is False:
            issues.append(CompatibilityIssue(
                severity="error",
                check="enclosure",
                message=f"{mat_name} requires an enclosure but {printer_name} is open-frame",
                material_name=mat_name,
                printer_name=printer_name,
            ))
        elif enclosure_cap is None:
            issues.append(CompatibilityIssue(
                severity="warning",
                check="enclosure",
                message=(
                    f"{mat_name} requires an enclosure but enclosure capability "
                    f"for {printer_name} is unknown"
                ),
                material_name=mat_name,
                printer_name=printer_name,
            ))

    # --- Nozzle temperature ---
    max_hotend = caps.get("max_temp_hotend")
    if max_hotend is not None and material_type.nozzle_temp_max is not None:
        if material_type.nozzle_temp_max > max_hotend:
            issues.append(CompatibilityIssue(
                severity="error",
                check="nozzle_temp",
                message=(
                    f"{mat_name} needs up to {material_type.nozzle_temp_max}°C nozzle temp "
                    f"but {printer_name} max is {max_hotend}°C"
                ),
                material_name=mat_name,
                printer_name=printer_name,
            ))

    # --- Bed temperature ---
    max_bed = caps.get("max_temp_bed")
    if max_bed is not None and material_type.bed_temp_max is not None:
        if material_type.bed_temp_max > max_bed:
            issues.append(CompatibilityIssue(
                severity="warning",
                check="bed_temp",
                message=(
                    f"{mat_name} wants up to {material_type.bed_temp_max}°C bed temp "
                    f"but {printer_name} max is {max_bed}°C"
                ),
                material_name=mat_name,
                printer_name=printer_name,
            ))

    # --- Filament diameter ---
    # Compare with a small tolerance to avoid float round-trip bugs
    # (e.g. Decimal("2.85") → float comparisons can drift at the LSB).
    supported_diameters = caps.get("filament_diameters")
    if supported_diameters and material_type.filament_diameter is not None:
        mat_dia = float(material_type.filament_diameter)
        supported_floats = [float(d) for d in supported_diameters]
        if not any(abs(mat_dia - d) < 0.01 for d in supported_floats):
            issues.append(CompatibilityIssue(
                severity="error",
                check="diameter",
                message=(
                    f"{mat_name} uses {mat_dia}mm filament "
                    f"but {printer_name} supports {supported_diameters}"
                ),
                material_name=mat_name,
                printer_name=printer_name,
            ))

    return issues


# ---------------------------------------------------------------------------
# Operation-level check
# ---------------------------------------------------------------------------

def check_operation_compatibility(
    db: Session,
    operation: ProductionOrderOperation,
) -> OperationCompatibility:
    """Check if the printer assigned to an operation can handle its materials."""
    printer: Optional[Printer] = operation.printer
    resource: Optional[Resource] = operation.resource

    # If no printer or resource is assigned, nothing to validate.
    if printer is None and resource is None:
        return OperationCompatibility(
            operation_id=operation.id,
            operation_name=operation.operation_name,
            printer_name=None,
            issues=[],
        )

    printer_name = (printer.name if printer else None) or (resource.name if resource else "Unknown")
    caps = _get_printer_capabilities(printer, resource)

    all_issues: List[CompatibilityIssue] = []

    for mat in operation.materials:
        product: Product = mat.component
        material_type = _resolve_material_type(product, db)
        if material_type is None:
            continue
        all_issues.extend(check_material_printer(material_type, printer_name, caps))

    return OperationCompatibility(
        operation_id=operation.id,
        operation_name=operation.operation_name,
        printer_name=printer_name,
        issues=all_issues,
    )


# ---------------------------------------------------------------------------
# Order-level check
# ---------------------------------------------------------------------------

def check_order_compatibility(
    db: Session,
    order: ProductionOrder,
) -> OrderCompatibility:
    """Check all operations in a production order for compatibility issues."""
    op_results: List[OperationCompatibility] = []
    for op in order.operations:
        op_results.append(check_operation_compatibility(db, op))

    return OrderCompatibility(
        production_order_id=order.id,
        production_order_code=order.code,
        operations=op_results,
    )
