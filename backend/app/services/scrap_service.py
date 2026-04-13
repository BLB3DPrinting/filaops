"""
Scrap Service - Handles operation-level scrap with cascading material consumption.

Key Features:
1. Calculate cascading material consumption (current + all prior operations)
2. Create scrap records with GL entries for each affected material
3. Create replacement production orders linked to original
4. Auto-skip downstream operations when no good pieces remain

Usage:
    from app.services.scrap_service import calculate_scrap_cascade, process_operation_scrap

    # Preview cascade before committing
    cascade = calculate_scrap_cascade(db, po_id, op_id, quantity=2)

    # Execute scrap with optional replacement PO
    result = process_operation_scrap(
        db, po_id, op_id,
        quantity_scrapped=2,
        scrap_reason_code="layer_shift",
        create_replacement=True,
        user_id=current_user.id
    )
    db.commit()
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
    ScrapRecord,
)
from app.models.scrap_reason import ScrapReason
from app.models.product import Product
from app.services.transaction_service import TransactionService
from app.services.inventory_service import get_effective_cost_per_inventory_unit


logger = logging.getLogger(__name__)


def _get_work_center_hourly_rate(wc) -> Decimal:
    """Get combined hourly rate for a work center (machine + labor + overhead)."""
    if not wc:
        return Decimal("0")
    machine = Decimal(str(wc.machine_rate_per_hour or 0))
    labor = Decimal(str(wc.labor_rate_per_hour or 0))
    overhead = Decimal(str(wc.overhead_rate_per_hour or 0))
    combined = machine + labor + overhead
    if combined == Decimal("0"):
        combined = Decimal(str(wc.hourly_rate or 0))
    return combined


def _calculate_operation_labor_cost(
    op: ProductionOrderOperation,
    quantity_scrapped: int,
    quantity_ordered: Decimal,
) -> Decimal:
    """
    Calculate the labor/overhead cost attributable to scrapped units for one operation.

    Formula: (op_time_minutes / 60) × hourly_rate × (scrapped / ordered)

    Uses actual_run_minutes when available (operation completed), otherwise planned.
    """
    minutes = Decimal(str(op.actual_run_minutes or op.planned_run_minutes or 0))
    minutes += Decimal(str(op.actual_setup_minutes or op.planned_setup_minutes or 0))
    hours = minutes / Decimal("60")

    rate = _get_work_center_hourly_rate(op.work_center)
    if rate == Decimal("0") or hours == Decimal("0"):
        return Decimal("0")

    # Total operation cost, then proportion attributable to scrapped units
    total_op_cost = hours * rate
    scrap_share = Decimal(str(quantity_scrapped)) / (quantity_ordered or Decimal("1"))
    return total_op_cost * scrap_share


class ScrapError(Exception):
    """Custom exception for scrap processing errors."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


def get_operation_with_po(
    db: Session,
    po_id: int,
    op_id: int
) -> Tuple[ProductionOrder, ProductionOrderOperation]:
    """
    Get operation and validate it belongs to the specified PO.

    Returns:
        Tuple of (ProductionOrder, ProductionOrderOperation)

    Raises:
        ScrapError: If PO or operation not found
    """
    po = db.get(ProductionOrder, po_id)
    if not po:
        raise ScrapError(f"Production order {po_id} not found", 404)

    op = db.get(ProductionOrderOperation, op_id)
    if not op:
        raise ScrapError(f"Operation {op_id} not found", 404)

    if op.production_order_id != po_id:
        raise ScrapError(
            f"Operation {op_id} does not belong to production order {po_id}",
            400
        )

    return po, op


def get_prior_operations_inclusive(
    po: ProductionOrder,
    target_op: ProductionOrderOperation
) -> List[ProductionOrderOperation]:
    """
    Get all operations up to and including the target operation.

    For scrap at operation N, we need to account for materials consumed
    at operations 1, 2, ..., N since those materials were already used
    to get to this point.

    Args:
        po: Production order
        target_op: The operation where scrap occurred

    Returns:
        List of operations from first to target, ordered by sequence
    """
    ops = sorted(po.operations, key=lambda x: x.sequence)

    result = []
    for op in ops:
        result.append(op)
        if op.id == target_op.id:
            break

    return result


def calculate_scrap_cascade(
    db: Session,
    po_id: int,
    op_id: int,
    quantity: int,
) -> Dict[str, Any]:
    """
    Calculate cascading material consumption for scrap at a given operation.

    Returns materials consumed from current operation AND all prior operations,
    since those materials were already consumed to reach this point.

    This is a READ-ONLY preview - no database changes.

    Args:
        db: Database session
        po_id: Production order ID
        op_id: Operation ID where scrap occurred
        quantity: Number of units being scrapped

    Returns:
        Dict with:
        - production_order_id: int
        - operation_id: int
        - quantity_scrapped: int
        - materials_consumed: List of material details
        - total_cost: Decimal
    """
    po, op = get_operation_with_po(db, po_id, op_id)

    # Get all operations up to and including current
    affected_ops = get_prior_operations_inclusive(po, op)

    materials_consumed = []
    total_material_cost = Decimal("0")
    total_labor_cost = Decimal("0")
    labor_by_operation = []
    qty_ordered = po.quantity_ordered or Decimal("1")

    for affected_op in affected_ops:
        # --- Labor / overhead cost for this operation ---
        op_labor = _calculate_operation_labor_cost(affected_op, quantity, qty_ordered)
        total_labor_cost += op_labor
        labor_by_operation.append({
            "operation_id": affected_op.id,
            "operation_sequence": affected_op.sequence,
            "operation_name": affected_op.operation_name,
            "labor_cost": float(op_labor),
        })

        # --- Material cost for this operation ---
        op_materials = db.query(ProductionOrderOperationMaterial).filter(
            ProductionOrderOperationMaterial.production_order_operation_id == affected_op.id
        ).all()

        for mat in op_materials:
            component = db.get(Product, mat.component_id)
            if not component:
                logger.warning(f"Component {mat.component_id} not found for material {mat.id}")
                continue

            qty_per_unit = (mat.quantity_required or Decimal("0")) / qty_ordered
            scrap_qty = qty_per_unit * Decimal(str(quantity))

            if scrap_qty <= 0:
                continue

            unit_cost = get_effective_cost_per_inventory_unit(component)
            cost = scrap_qty * unit_cost
            total_material_cost += cost

            materials_consumed.append({
                "operation_id": affected_op.id,
                "operation_sequence": affected_op.sequence,
                "operation_name": affected_op.operation_name,
                "component_id": mat.component_id,
                "component_sku": component.sku,
                "component_name": component.name,
                "quantity": float(scrap_qty),
                "unit": mat.unit or "EA",
                "unit_cost": float(unit_cost),
                "cost": float(cost),
            })

    return {
        "production_order_id": po_id,
        "production_order_code": po.code,
        "operation_id": op_id,
        "operation_name": op.operation_name,
        "quantity_scrapped": quantity,
        "materials_consumed": materials_consumed,
        "labor_by_operation": labor_by_operation,
        "material_cost": float(total_material_cost),
        "labor_cost": float(total_labor_cost),
        "total_cost": float(total_material_cost + total_labor_cost),
        "operations_affected": len(affected_ops),
    }


def process_operation_scrap(
    db: Session,
    po_id: int,
    op_id: int,
    quantity_scrapped: int,
    scrap_reason_code: str,
    notes: Optional[str] = None,
    create_replacement: bool = False,
    user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Process scrap at operation level with cascading material accounting.

    This will:
    1. Validate scrap reason and quantities
    2. Create ScrapRecords for all consumed materials (current + prior ops)
    3. Create GL journal entries (DR Scrap Expense 5020, CR WIP 1210)
    4. Update operation/PO scrap quantities
    5. Auto-skip downstream operations if no good pieces remain
    6. Optionally create a replacement production order

    Args:
        db: Database session
        po_id: Production order ID
        op_id: Operation ID where scrap occurred
        quantity_scrapped: Number of units to scrap
        scrap_reason_code: Code from scrap_reasons table
        notes: Optional notes
        create_replacement: If True, create replacement PO
        user_id: Current user ID for audit trail

    Returns:
        Dict with scrap details and optional replacement PO info

    Raises:
        ScrapError: If validation fails
    """
    po, op = get_operation_with_po(db, po_id, op_id)

    # Validate scrap reason
    reason = db.query(ScrapReason).filter(
        ScrapReason.code == scrap_reason_code,
        ScrapReason.active.is_(True)
    ).first()

    if not reason:
        raise ScrapError(f"Invalid or inactive scrap reason: {scrap_reason_code}", 400)

    # Validate quantity doesn't exceed what's available
    # For running operations, max is what was started
    # For completed operations, max is what was completed
    max_scrappable = (op.quantity_completed or Decimal("0"))
    if op.status == 'running':
        # If running, can scrap up to the max from previous operation
        from app.services.operation_status import get_operation_max_quantity
        max_scrappable = get_operation_max_quantity(po, op)

    already_scrapped = op.quantity_scrapped or Decimal("0")
    available_to_scrap = max_scrappable - already_scrapped

    if Decimal(str(quantity_scrapped)) > available_to_scrap:
        raise ScrapError(
            f"Cannot scrap {quantity_scrapped} units. "
            f"Only {available_to_scrap} units available to scrap.",
            400
        )

    # Get all operations up to current
    affected_ops = get_prior_operations_inclusive(po, op)

    # Create transaction service for atomic operations
    txn_service = TransactionService(db)

    scrap_records_created = []
    total_material_cost = Decimal("0")
    total_labor_cost = Decimal("0")
    journal_entry = None  # We'll create one combined entry
    qty_ordered = po.quantity_ordered or Decimal("1")

    # Collect all materials to scrap for a combined journal entry
    materials_to_scrap = []

    for affected_op in affected_ops:
        # --- Labor / overhead cost for this operation ---
        op_labor = _calculate_operation_labor_cost(
            affected_op, quantity_scrapped, qty_ordered,
        )
        total_labor_cost += op_labor

        # --- Material cost for this operation ---
        op_materials = db.query(ProductionOrderOperationMaterial).filter(
            ProductionOrderOperationMaterial.production_order_operation_id == affected_op.id
        ).all()

        for mat in op_materials:
            component = db.get(Product, mat.component_id)
            if not component:
                continue

            # Calculate scrap quantity
            qty_per_unit = (mat.quantity_required or Decimal("0")) / qty_ordered
            scrap_qty = qty_per_unit * Decimal(str(quantity_scrapped))

            if scrap_qty <= 0:
                continue

            unit_cost = get_effective_cost_per_inventory_unit(component)

            materials_to_scrap.append({
                "operation": affected_op,
                "material": mat,
                "component": component,
                "scrap_qty": scrap_qty,
                "unit_cost": unit_cost,
            })

            total_material_cost += scrap_qty * unit_cost

    total_scrap_cost = total_material_cost + total_labor_cost

    # Create single combined journal entry for all materials + labor
    if total_scrap_cost > Decimal("0"):
        gl_lines = []
        # Debit: Scrap Expense for material
        if total_material_cost > Decimal("0"):
            gl_lines.append(("5020", total_material_cost, "DR"))   # Scrap Expense – Material
        # Debit: Scrap Expense for labor/overhead
        if total_labor_cost > Decimal("0"):
            gl_lines.append(("5020", total_labor_cost, "DR"))      # Scrap Expense – Labor
        # Credit: WIP for total
        gl_lines.append(("1210", total_scrap_cost, "CR"))          # WIP Inventory

        journal_entry = txn_service._create_journal_entry(
            description=f"Scrap at {op.operation_name} for {po.code}: {quantity_scrapped} units ({scrap_reason_code})",
            lines=gl_lines,
            source_type="production_order",
            source_id=po_id,
            user_id=user_id,
        )

    # Now create individual scrap records linked to the journal entry
    for mat_info in materials_to_scrap:
        affected_op = mat_info["operation"]
        component = mat_info["component"]
        scrap_qty = mat_info["scrap_qty"]
        unit_cost = mat_info["unit_cost"]

        # Create scrap record
        scrap_record = ScrapRecord(
            production_order_id=po_id,
            production_operation_id=affected_op.id,
            operation_sequence=affected_op.sequence,
            product_id=component.id,
            quantity=scrap_qty,
            unit_cost=unit_cost,
            total_cost=scrap_qty * unit_cost,
            scrap_reason_id=reason.id,
            scrap_reason_code=scrap_reason_code,
            notes=notes,
            journal_entry_id=journal_entry.id if journal_entry else None,
            created_by_user_id=user_id,
        )
        db.add(scrap_record)
        scrap_records_created.append(scrap_record)

        logger.info(
            f"Created scrap record for {scrap_qty} {component.unit or 'EA'} of "
            f"{component.sku} at operation {affected_op.sequence}"
        )

    # Update operation scrap quantity
    op.quantity_scrapped = (op.quantity_scrapped or Decimal("0")) + Decimal(str(quantity_scrapped))
    if not op.scrap_reason:
        op.scrap_reason = scrap_reason_code
    op.updated_at = datetime.now(timezone.utc)

    # Update PO scrap quantity
    po.quantity_scrapped = (po.quantity_scrapped or Decimal("0")) + Decimal(str(quantity_scrapped))
    po.updated_at = datetime.now(timezone.utc)

    # Check if all units scrapped at this operation - auto-skip downstream
    remaining_good = (op.quantity_completed or Decimal("0")) - (op.quantity_scrapped or Decimal("0"))
    skipped_ops = 0

    if remaining_good <= 0 and op.status == 'complete':
        skipped_ops = auto_skip_downstream_operations(db, po, op)
        if skipped_ops > 0:
            logger.info(f"Auto-skipped {skipped_ops} downstream operations due to 0 good pieces")

    # Create replacement PO if requested
    replacement_po = None
    if create_replacement:
        replacement_po = create_replacement_production_order(
            db=db,
            original_po=po,
            quantity=quantity_scrapped,
            scrap_reason=scrap_reason_code,
            user_id=user_id,
        )
        logger.info(f"Created replacement PO {replacement_po.code} for {quantity_scrapped} units")

    db.flush()

    return {
        "success": True,
        "scrap_records_created": len(scrap_records_created),
        "operations_affected": len(affected_ops),
        "material_cost": float(total_material_cost),
        "labor_cost": float(total_labor_cost),
        "total_scrap_cost": float(total_scrap_cost),
        "journal_entry_number": journal_entry.entry_number if journal_entry else None,
        "downstream_ops_skipped": skipped_ops,
        "replacement_order": {
            "id": replacement_po.id,
            "code": replacement_po.code,
        } if replacement_po else None,
    }


def auto_skip_downstream_operations(
    db: Session,
    po: ProductionOrder,
    completed_op: ProductionOrderOperation
) -> int:
    """
    Auto-skip all downstream operations when no good pieces remain.

    Called when an operation's good quantity (completed - scrapped) reaches 0.
    All subsequent pending/queued operations are marked as skipped.

    Args:
        db: Database session
        po: Production order
        completed_op: The operation with 0 remaining good pieces

    Returns:
        Number of operations skipped
    """
    ops = sorted(po.operations, key=lambda x: x.sequence)
    skipped_count = 0

    # Find ops after this one
    found_current = False
    for op in ops:
        if op.id == completed_op.id:
            found_current = True
            continue

        if not found_current:
            continue

        # Only skip pending/queued ops
        if op.status in ('pending', 'queued'):
            op.status = 'skipped'
            op.notes = f"SKIPPED: Auto-skipped - no good pieces from operation {completed_op.sequence}"
            op.updated_at = datetime.now(timezone.utc)
            skipped_count += 1

            logger.info(
                f"Auto-skipped operation {op.id} (seq {op.sequence}) "
                f"due to 0 good pieces from op {completed_op.sequence}"
            )

    return skipped_count


def create_replacement_production_order(
    db: Session,
    original_po: ProductionOrder,
    quantity: int,
    scrap_reason: str,
    user_id: Optional[int] = None,
) -> ProductionOrder:
    """
    Create a replacement production order linked to the original.

    The replacement PO:
    - Has same product, BOM, routing as original
    - Links to same sales order (if MTO)
    - Is marked as remake_of_id pointing to original
    - Starts in 'draft' status

    Args:
        db: Database session
        original_po: The PO that had scrap
        quantity: Number of replacement units needed
        scrap_reason: Reason for the remake
        user_id: Current user ID

    Returns:
        New ProductionOrder instance (not yet committed)
    """
    # Generate new PO code
    code = _generate_production_order_code(db)

    replacement = ProductionOrder(
        code=code,
        product_id=original_po.product_id,
        bom_id=original_po.bom_id,
        routing_id=original_po.routing_id,
        sales_order_id=original_po.sales_order_id,
        sales_order_line_id=original_po.sales_order_line_id,
        quantity_ordered=Decimal(str(quantity)),
        quantity_completed=Decimal("0"),
        quantity_scrapped=Decimal("0"),
        source="remake",
        order_type=original_po.order_type,
        status="draft",
        priority=original_po.priority,
        due_date=original_po.due_date,
        remake_of_id=original_po.id,
        notes=f"Remake of {original_po.code} due to scrap: {scrap_reason}",
        created_by=f"user:{user_id}" if user_id else "system",
    )
    db.add(replacement)
    db.flush()  # Get ID

    return replacement


def _generate_production_order_code(db: Session) -> str:
    """Generate next production order code: PO-{year}-{seq:04d}"""
    year = datetime.now(timezone.utc).year

    # Find max code for this year
    pattern = f"PO-{year}-%"
    result = db.query(func.max(ProductionOrder.code)).filter(
        ProductionOrder.code.like(pattern)
    ).scalar()

    if result:
        try:
            seq = int(result.split("-")[2]) + 1
        except (IndexError, ValueError):
            seq = 1
    else:
        seq = 1

    return f"PO-{year}-{seq:04d}"
