"""
Service layer for operation-level blocking checks.

Checks material availability for a specific operation, not the entire PO.
"""
from decimal import Decimal
from typing import List, Optional, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.bom import BOMLine
from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderOperationMaterial
)
from app.models.inventory import Inventory
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.services.operation_material_mapping import (
    load_operation_type_stage_map,
    resolve_consume_stages,
)


class OperationBlockingError(Exception):
    """Custom exception for operation blocking errors."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def get_operation_with_validation(
    db: Session,
    po_id: int,
    op_id: int
) -> Tuple[ProductionOrder, ProductionOrderOperation]:
    """
    Get operation and validate it belongs to the specified PO.

    Returns:
        Tuple of (ProductionOrder, ProductionOrderOperation)

    Raises:
        OperationBlockingError: If PO or operation not found
    """
    po = db.get(ProductionOrder, po_id)
    if not po:
        raise OperationBlockingError(f"Production order {po_id} not found", 404)

    op = db.get(ProductionOrderOperation, op_id)
    if not op:
        raise OperationBlockingError(f"Operation {op_id} not found", 404)

    if op.production_order_id != po_id:
        raise OperationBlockingError(
            f"Operation {op_id} does not belong to production order {po_id}", 404
        )

    return po, op


def get_material_available(db: Session, product_id: int) -> Decimal:
    """
    Get available inventory for a material.

    Available = on_hand - allocated (across all locations)
    """
    result = db.query(
        func.coalesce(func.sum(Inventory.on_hand_quantity - Inventory.allocated_quantity), Decimal("0"))
    ).filter(
        Inventory.product_id == product_id
    ).scalar()

    return Decimal(str(result or 0))


def get_bom_lines_for_operation(
    db: Session,
    bom_id: int,
    operation_code: str,
    operation_type: Optional[str] = None,
) -> List[BOMLine]:
    """
    Get BOM lines that should be checked for a specific operation.

    Filters by:
    - consume_stage matches operation's stages
    - is_cost_only = False (cost-only lines don't consume inventory)

    Resolution is type-first: when `operation_type` is set and known to the
    operation-type catalog, its consume_stages win; otherwise falls back to
    the legacy operation_code map (see resolve_consume_stages).

    Args:
        db: Database session
        bom_id: BOM ID
        operation_code: Operation code (e.g., "PRINT", "PACK")
        operation_type: Stored operation type code (e.g., "FDM_PRINT",
            "PACK_SHIP"), if the operation has one

    Returns:
        List of BOMLine objects to check
    """
    type_map = load_operation_type_stage_map(db)
    consume_stages = resolve_consume_stages(type_map, operation_type, operation_code)

    lines = db.query(BOMLine).filter(
        BOMLine.bom_id == bom_id,
        BOMLine.consume_stage.in_(consume_stages),
        BOMLine.is_cost_only == False  # noqa: E712
    ).all()

    return lines


def get_pending_purchase_orders(
    db: Session,
    product_id: int
) -> List[Tuple[PurchaseOrder, Decimal]]:
    """Get pending purchase orders for a product with remaining quantities."""
    active_statuses = ['draft', 'ordered', 'shipped']

    results = db.query(PurchaseOrder, PurchaseOrderLine).join(
        PurchaseOrderLine,
        PurchaseOrder.id == PurchaseOrderLine.purchase_order_id
    ).filter(
        PurchaseOrderLine.product_id == product_id,
        PurchaseOrder.status.in_(active_statuses)
    ).all()

    pos = []
    for po, pol in results:
        remaining = (pol.quantity_ordered or Decimal("0")) - (pol.quantity_received or Decimal("0"))
        if remaining > 0:
            pos.append((po, remaining))

    return pos


def check_operation_blocking(
    db: Session,
    po_id: int,
    op_id: int
) -> dict:
    """
    Check if an operation is blocked by material shortages.

    Uses a two-tier approach:
    1. PRIMARY: Check ProductionOrderOperationMaterial records (routing-based)
    2. FALLBACK: Check BOM lines via consume_stage (legacy)

    This matches the MRP precedence logic - if routing materials exist,
    use those; otherwise fall back to legacy BOM.

    Args:
        db: Database session
        po_id: Production order ID
        op_id: Operation ID

    Returns:
        dict with:
        - operation_id: int
        - operation_code: str
        - can_start: bool
        - blocking_issues: list of material shortage issues
        - material_issues: list of all material checks (for detailed view)
        - material_source: 'routing' or 'bom' indicating which source was used

    Raises:
        OperationBlockingError: If PO or operation not found
    """
    po, op = get_operation_with_validation(db, po_id, op_id)

    result = {
        "operation_id": op.id,
        "operation_code": op.operation_code,
        "operation_name": op.operation_name,
        "can_start": True,
        "blocking_issues": [],
        "material_issues": [],
        "material_source": None,
    }

    # =========================================================================
    # PRIMARY: Check PO Operation Materials (routing-based)
    # These are created when the PO is released from routing materials
    # =========================================================================
    po_op_materials = db.query(ProductionOrderOperationMaterial).filter(
        ProductionOrderOperationMaterial.production_order_operation_id == op_id
    ).all()

    # Filter to only non-cost-only, non-optional materials that aren't consumed
    active_materials = [
        m for m in po_op_materials
        if m.status != 'consumed'
    ]

    if active_materials:
        result["material_source"] = "routing"

        for mat in active_materials:
            component = db.get(Product, mat.component_id)
            if not component:
                continue

            # Quantity required is already calculated when the material was created
            qty_required = mat.quantity_required or Decimal("0")
            qty_allocated = mat.quantity_allocated or Decimal("0")

            # Get available inventory (not already allocated)
            qty_available = get_material_available(db, component.id)

            # Short = required - allocated - available
            qty_needed = qty_required - qty_allocated
            qty_short = max(Decimal("0"), qty_needed - qty_available)

            # Check for incoming supply
            incoming_supply = None
            pending_pos = get_pending_purchase_orders(db, component.id)
            if pending_pos:
                po_incoming, po_qty = pending_pos[0]
                incoming_supply = {
                    "purchase_order_id": po_incoming.id,
                    "purchase_order_code": po_incoming.po_number,
                    "quantity": float(po_qty),
                    "expected_date": po_incoming.expected_date.isoformat() if po_incoming.expected_date else None
                }

            material_issue = {
                "product_id": component.id,
                "product_sku": component.sku,
                "product_name": component.name,
                "quantity_required": float(qty_required),
                "quantity_allocated": float(qty_allocated),
                "quantity_available": float(max(Decimal("0"), qty_available)),
                "quantity_short": float(qty_short),
                "unit": mat.unit,
                "po_operation_material_id": mat.id,
                "status": mat.status,
                "incoming_supply": incoming_supply,
            }

            result["material_issues"].append(material_issue)

            # If short, add to blocking issues
            if qty_short > 0:
                result["can_start"] = False
                result["blocking_issues"].append(material_issue)

        return result

    # =========================================================================
    # FALLBACK: Check BOM lines via consume_stage (legacy)
    # Used when PO doesn't have operation materials (pre-routing products)
    # =========================================================================
    if not po.bom_id:
        return result

    bom_lines = get_bom_lines_for_operation(
        db, po.bom_id, op.operation_code, getattr(op, "operation_type", None)
    )

    if not bom_lines:
        return result

    result["material_source"] = "bom"

    # Calculate quantity to produce (remaining)
    qty_to_produce = (po.quantity_ordered or Decimal("0")) - (po.quantity_completed or Decimal("0"))

    if qty_to_produce <= 0:
        return result

    # Check each material
    for line in bom_lines:
        component = db.get(Product, line.component_id)
        if not component:
            continue

        # Calculate required quantity (including scrap factor)
        scrap_multiplier = 1 + (line.scrap_factor or Decimal("0")) / 100
        qty_required = line.quantity * qty_to_produce * scrap_multiplier

        # Get available inventory
        qty_available = get_material_available(db, component.id)
        qty_short = max(Decimal("0"), qty_required - qty_available)

        # Check for incoming supply
        incoming_supply = None
        pending_pos = get_pending_purchase_orders(db, component.id)
        if pending_pos:
            po_incoming, po_qty = pending_pos[0]
            incoming_supply = {
                "purchase_order_id": po_incoming.id,
                "purchase_order_code": po_incoming.po_number,
                "quantity": float(po_qty),
                "expected_date": po_incoming.expected_date.isoformat() if po_incoming.expected_date else None
            }

        material_issue = {
            "product_id": component.id,
            "product_sku": component.sku,
            "product_name": component.name,
            "quantity_required": float(qty_required),
            "quantity_available": float(max(Decimal("0"), qty_available)),
            "quantity_short": float(qty_short),
            "unit": line.unit,
            "consume_stage": line.consume_stage,
            "incoming_supply": incoming_supply,
        }

        result["material_issues"].append(material_issue)

        # If short, add to blocking issues
        if qty_short > 0:
            result["can_start"] = False
            result["blocking_issues"].append(material_issue)

    return result


def can_operation_start(
    db: Session,
    po_id: int,
    op_id: int
) -> dict:
    """
    Quick check if an operation can start.

    Returns simplified response with just can_start and blocking issues.
    """
    full_result = check_operation_blocking(db, po_id, op_id)

    return {
        "can_start": full_result["can_start"],
        "blocking_issues": full_result["blocking_issues"]
    }
