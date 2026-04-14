"""
Resource-material compatibility helpers.

Extracted from the scheduling endpoint so both the scheduling and
operation_status endpoints can share the logic without importing
across endpoint modules.
"""
from __future__ import annotations

from typing import Union
from sqlalchemy.orm import Session

from app.models.manufacturing import Resource
from app.models.printer import Printer
from app.models.production_order import ProductionOrder
from app.models.product import Product
from app.models.bom import BOM
from app.models.material import MaterialType


class _ResourceAdapter:
    """Duck-typed adapter so Printer can be passed where Resource is expected."""

    def __init__(self, printer: Printer) -> None:
        self.code = printer.code
        self.machine_type = printer.model


def normalize_resource(resource_or_printer: Union[Resource, Printer]) -> _ResourceAdapter | Resource:
    """Return a Resource-like object regardless of whether a Printer or Resource is passed."""
    if isinstance(resource_or_printer, Printer):
        return _ResourceAdapter(resource_or_printer)
    return resource_or_printer


def get_material_requirements(db: Session, production_order: ProductionOrder) -> dict:
    """
    Get material requirements for a production order.

    Analyzes the product and BOM to determine material compatibility needs.
    This ensures ABS/ASA materials are only scheduled on enclosed printers.

    Returns:
        {
            'requires_enclosure': bool,
            'material_types': [list of material type codes],
            'base_materials': [list of base materials like 'ABS', 'ASA']
        }
    """
    requires_enclosure = False
    material_types = []
    base_materials: set[str] = set()

    # Check if the product itself is a material
    product = db.query(Product).filter(Product.id == production_order.product_id).first()
    if product and product.material_type_id:
        material_type = db.query(MaterialType).filter(MaterialType.id == product.material_type_id).first()
        if material_type:
            if material_type.requires_enclosure:
                requires_enclosure = True
            material_types.append(material_type.code)
            base_materials.add(material_type.base_material)

    # Check BOM for material components
    bom = None
    if production_order.bom_id:
        bom = db.query(BOM).filter(BOM.id == production_order.bom_id).first()
    elif production_order.product_id:
        bom = db.query(BOM).filter(
            BOM.product_id == production_order.product_id,
            BOM.active.is_(True)
        ).first()

    if bom and bom.lines:
        for line in bom.lines:
            component = db.query(Product).filter(Product.id == line.component_id).first()
            if component and component.material_type_id:
                material_type = db.query(MaterialType).filter(MaterialType.id == component.material_type_id).first()
                if material_type:
                    if material_type.requires_enclosure:
                        requires_enclosure = True
                    material_types.append(material_type.code)
                    base_materials.add(material_type.base_material)

    return {
        'requires_enclosure': requires_enclosure,
        'material_types': list(set(material_types)),
        'base_materials': list(base_materials),
    }


def machine_has_enclosure(resource: Union[Resource, _ResourceAdapter]) -> bool:
    """
    Check if a machine/resource has an enclosure based on its machine_type string.

    For BambuLab printers:
    - X1C, X1, P1S have enclosures (can print ABS/ASA)
    - P1P, A1, A1 MINI do NOT have enclosures (PLA/PETG only)

    TODO: Add has_enclosure field to Resource model for explicit configuration.
    """
    if not resource.machine_type:
        return False

    machine_type_upper = resource.machine_type.upper()

    # BambuLab models with enclosures (substring match to handle stored values
    # like "Bambu Lab X1C", "X1 Carbon", "X1", etc.).
    # P1P has no enclosure; X1 (non-Carbon) does.
    enclosed_models = ['X1C', 'X1 CARBON', 'X1', 'P1S']
    if any(m in machine_type_upper for m in enclosed_models):
        return True

    # Check A1 MINI before plain A1 to avoid substring false-match
    if 'A1 MINI' in machine_type_upper or 'A1MINI' in machine_type_upper:
        return False
    if 'A1' in machine_type_upper:
        return False

    # Default: assume no enclosure for unknown models
    return False


def is_machine_compatible(
    db: Session,
    resource: Union[Resource, Printer, _ResourceAdapter],
    production_order: ProductionOrder,
) -> tuple[bool, str]:
    """
    Check if a machine is compatible with a production order's material requirements.

    Accepts a Resource, a Printer, or an already-normalized adapter.
    Returns (is_compatible, reason).
    """
    # Normalize Printer → adapter so machine_has_enclosure sees .machine_type
    normalized = normalize_resource(resource) if isinstance(resource, Printer) else resource

    material_reqs = get_material_requirements(db, production_order)

    if material_reqs['requires_enclosure']:
        if not machine_has_enclosure(normalized):
            base_mats = ', '.join(material_reqs['base_materials']) if material_reqs['base_materials'] else 'material'
            return False, (
                f"{base_mats} requires enclosure but "
                f"{normalized.code} ({normalized.machine_type or 'unknown model'}) does not have one"
            )

    return True, "Compatible"
