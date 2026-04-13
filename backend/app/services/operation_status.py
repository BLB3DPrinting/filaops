"""
Service layer for operation status transitions.
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session

from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderOperationMaterial
)
from app.models.manufacturing import Resource
from app.services.operation_blocking import check_operation_blocking
from app.services.resource_scheduling import check_resource_available_now
from app.services.inventory_service import consume_operation_material, process_production_completion
from app.services.status_sync_service import sync_on_production_complete


logger = logging.getLogger(__name__)


class OperationError(Exception):
    """Custom exception for operation errors."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

    def __str__(self):
        return self.message


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
        OperationError: If PO or operation not found, or operation doesn't belong to PO
    """
    po = db.get(ProductionOrder, po_id)
    if not po:
        raise OperationError(f"Production order {po_id} not found", 404)

    op = db.get(ProductionOrderOperation, op_id)
    if not op:
        raise OperationError(f"Operation {op_id} not found", 404)

    if op.production_order_id != po_id:
        raise OperationError(f"Operation {op_id} does not belong to production order {po_id}", 404)

    return po, op


def get_previous_operation(
    db: Session,
    po: ProductionOrder,
    current_op: ProductionOrderOperation
) -> Optional[ProductionOrderOperation]:
    """Get the previous operation in sequence."""
    ops = sorted(po.operations, key=lambda x: x.sequence)

    for i, op in enumerate(ops):
        if op.id == current_op.id and i > 0:
            return ops[i - 1]

    return None


def get_operation_max_quantity(
    po: ProductionOrder,
    op: ProductionOrderOperation
) -> Decimal:
    """
    Get maximum quantity allowed for this operation.

    Rules:
    - First operation: order quantity (allows over-production for MTS)
    - Subsequent operations: previous completed op's qty_completed
    - If previous op was skipped, inherit from the op before that

    Returns:
        Maximum quantity (good + bad) allowed for this operation
    """
    ops = sorted(po.operations, key=lambda x: x.sequence)

    # Find this op's position
    op_index = None
    for i, o in enumerate(ops):
        if o.id == op.id:
            op_index = i
            break

    if op_index is None or op_index == 0:
        # First operation - max is order quantity
        return po.quantity_ordered

    # Walk backwards to find last completed operation
    for i in range(op_index - 1, -1, -1):
        prev = ops[i]
        if prev.status == 'complete':
            return prev.quantity_completed
        elif prev.status == 'skipped':
            continue  # Keep looking back
        else:
            # Previous op not done yet - shouldn't happen if sequence enforced
            return Decimal("0")

    # No completed ops before this one - use order qty
    return po.quantity_ordered


def get_next_operation(
    db: Session,
    po: ProductionOrder,
    current_op: ProductionOrderOperation
) -> Optional[ProductionOrderOperation]:
    """Get the next operation in sequence."""
    ops = sorted(po.operations, key=lambda x: x.sequence)

    for i, op in enumerate(ops):
        if op.id == current_op.id and i < len(ops) - 1:
            return ops[i + 1]

    return None


def derive_po_status(po: ProductionOrder) -> str:
    """
    Derive PO status from its operations.

    Rules:
    - All pending → released
    - All complete/skipped AND qty_completed >= qty_ordered → complete
    - All complete/skipped AND qty_completed < qty_ordered → short
    - Any running or mixed → in_progress
    """
    if not po.operations:
        return po.status  # No operations, keep current

    statuses = [op.status for op in po.operations]

    if all(s == 'pending' for s in statuses):
        return 'released'
    elif all(s in ('complete', 'skipped') for s in statuses):
        # All operations done - check if we met the quantity requirement
        qty_ordered = po.quantity_ordered or Decimal("0")
        qty_completed = po.quantity_completed or Decimal("0")

        if qty_completed >= qty_ordered:
            return 'complete'
        else:
            # Under-production: not enough good pieces to fulfill order
            return 'short'
    else:
        return 'in_progress'


def update_po_status(db: Session, po: ProductionOrder, created_by: Optional[str] = None) -> None:
    """
    Update PO status based on operations.

    When PO transitions to 'complete':
    - Adds finished goods to inventory via process_production_completion
    - Syncs parent sales order status via sync_on_production_complete
    """
    new_status = derive_po_status(po)
    old_status = po.status

    if old_status != new_status:
        po.status = new_status
        po.updated_at = datetime.now(timezone.utc)

        if new_status == 'in_progress' and not po.actual_start:
            po.actual_start = datetime.now(timezone.utc)
        elif new_status == 'complete' and not po.actual_end:
            po.actual_end = datetime.now(timezone.utc)
            po.completed_at = datetime.now(timezone.utc)

            # === AUTO-COMPLETE: Add finished goods to inventory ===
            # This triggers when all operations complete, not just when
            # the explicit /complete endpoint is called
            qty_completed = po.quantity_completed or po.quantity_ordered
            try:
                process_production_completion(
                    db=db,
                    production_order=po,
                    quantity_completed=qty_completed,
                    created_by=created_by,
                )
                logger.info(
                    f"Auto-completed inventory receipt for {po.code}: "
                    f"{qty_completed} units of product {po.product_id}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to process inventory for {po.code}: {e}"
                )
                # Don't fail the operation completion - log and continue

            # === AUTO-SYNC: Update parent sales order status ===
            try:
                sync_on_production_complete(db, po)
            except Exception as e:
                logger.error(
                    f"Failed to sync sales order for {po.code}: {e}"
                )


def consume_operation_materials(
    db: Session,
    op: ProductionOrderOperation,
    quantity_completed: Decimal,
    quantity_scrapped: Decimal
) -> List[dict]:
    """
    Consume materials for a completed operation.

    FIXED VERSION: Creates proper InventoryTransactions with cost_per_unit.

    For each ProductionOrderOperationMaterial:
    - Creates InventoryTransaction with proper cost_per_unit
    - Updates Inventory.on_hand_quantity
    - Links transaction back to material record
    - Tracks lot consumption for traceability

    Note: This consumes the full planned amount regardless of yield.
    For 3D printing, filament is fully consumed whether the part is good or bad.

    Args:
        db: Database session
        op: The operation being completed
        quantity_completed: Good quantity produced
        quantity_scrapped: Bad quantity produced

    Returns:
        List of consumed material summaries
    """
    consumed_materials = []

    # Get materials for this operation
    materials = db.query(ProductionOrderOperationMaterial).filter(
        ProductionOrderOperationMaterial.production_order_operation_id == op.id
    ).all()

    # Get the production order for reference info
    po = op.production_order

    for mat in materials:
        # Use the robust inventory service function
        txn = consume_operation_material(
            db=db,
            material=mat,
            production_order=po,
            created_by=op.operator_name,  # Pass operator from operation
        )

        if txn:
            consumed_materials.append({
                "material_id": mat.id,
                "component_id": mat.component_id,
                "quantity_consumed": float(mat.quantity_consumed),
                "unit": mat.unit,
                "transaction_id": txn.id,
                "cost_per_unit": float(txn.cost_per_unit) if txn.cost_per_unit else 0,
            })

            logger.info(
                f"Created transaction {txn.id} for material {mat.id}: "
                f"{mat.quantity_consumed} {mat.unit} @ ${txn.cost_per_unit or 0:.4f}/unit"
            )

    return consumed_materials


def start_operation(
    db: Session,
    po_id: int,
    op_id: int,
    resource_id: Optional[int] = None,
    operator_name: Optional[str] = None,
    notes: Optional[str] = None
) -> ProductionOrderOperation:
    """
    Start an operation.

    Validations:
    - Operation must be pending or queued
    - Previous operation (by sequence) must be complete or skipped
    - Resource must not have conflicting scheduled operation

    Returns:
        Updated operation

    Raises:
        OperationError: If validation fails
    """
    po, op = get_operation_with_validation(db, po_id, op_id)

    # Check operation status
    if op.status == 'running':
        raise OperationError("Operation is already running", 400)
    if op.status in ('complete', 'skipped'):
        raise OperationError(f"Operation is already {op.status}", 400)
    if op.status not in ('pending', 'queued'):
        raise OperationError(f"Cannot start operation in status '{op.status}'", 400)

    # Check previous operation is complete
    prev_op = get_previous_operation(db, po, op)
    if prev_op and prev_op.status not in ('complete', 'skipped'):
        raise OperationError(
            f"Previous operation (sequence {prev_op.sequence}) must be complete before starting this one",
            400
        )

    # Check material availability for this operation (API-402)
    blocking_result = check_operation_blocking(db, po_id, op_id)
    if not blocking_result["can_start"]:
        short_materials = [m["product_sku"] for m in blocking_result["blocking_issues"]]
        raise OperationError(
            f"Operation blocked by material shortages: {', '.join(short_materials)}",
            400
        )

    # Validate resource if provided
    if resource_id:
        resource = db.get(Resource, resource_id)
        if not resource:
            raise OperationError(f"Resource {resource_id} not found", 404)

        # Check for double-booking (API-403)
        is_available, blocking_op = check_resource_available_now(db, resource_id)
        if not is_available:
            raise OperationError(
                f"Resource is busy with another running operation (operation {blocking_op.id})",
                409
            )
        op.resource_id = resource_id

    # Update operation
    op.status = 'running'
    op.actual_start = datetime.now(timezone.utc)
    op.operator_name = operator_name
    if notes:
        op.notes = notes
    op.updated_at = datetime.now(timezone.utc)

    # Update PO status
    update_po_status(db, po, created_by=operator_name)

    db.flush()
    return op


def complete_operation(
    db: Session,
    po_id: int,
    op_id: int,
    quantity_completed: Decimal,
    quantity_scrapped: Decimal = Decimal("0"),
    scrap_reason: Optional[str] = None,
    actual_run_minutes: Optional[int] = None,
    notes: Optional[str] = None,
    scrap_notes: Optional[str] = None,
    create_replacement: bool = False,
    user_id: Optional[int] = None,
) -> Tuple[ProductionOrderOperation, Optional[dict]]:
    """
    Complete an operation with optional partial scrap and cascading material accounting.

    Validations:
    - Operation must be running
    - quantity_completed + quantity_scrapped <= max_allowed
      (max_allowed = previous op's qty_completed, or order qty for first op)
    - If quantity_scrapped > 0 and scrap_reason is provided, cascading scrap accounting is triggered

    Side effects:
    - Consumes materials for this operation (marks as consumed)
    - If scrapping: Creates ScrapRecords with cascading material costs + GL entries
    - If scrapping with create_replacement: Creates new PO linked to original
    - Updates PO status if last operation
    - Auto-skips downstream operations if no good pieces remain

    Args:
        db: Database session
        po_id: Production order ID
        op_id: Operation ID
        quantity_completed: Number of good units
        quantity_scrapped: Number of units to scrap (default 0)
        scrap_reason: Scrap reason code (required if quantity_scrapped > 0)
        actual_run_minutes: Override for actual run time
        notes: General operation notes
        scrap_notes: Notes specific to the scrap event
        create_replacement: If True and scrapping, create replacement PO
        user_id: Current user ID for audit trail

    Returns:
        Tuple of (updated operation, scrap_result dict or None)

    Raises:
        OperationError: If validation fails
    """
    po, op = get_operation_with_validation(db, po_id, op_id)

    # Check operation status
    if op.status != 'running':
        raise OperationError("Operation is not running, cannot complete", 400)

    # Validate quantity doesn't exceed max allowed
    max_qty = get_operation_max_quantity(po, op)
    total_qty = quantity_completed + quantity_scrapped

    if total_qty > max_qty:
        raise OperationError(
            f"Total quantity ({total_qty}) exceeds maximum allowed ({max_qty}). "
            f"Good + Bad cannot exceed input from previous operation.",
            400
        )

    # Validate scrap reason if scrapping
    if quantity_scrapped > Decimal("0") and not scrap_reason:
        raise OperationError(
            "Scrap reason is required when quantity_scrapped > 0",
            400
        )

    # Update operation
    op.status = 'complete'
    op.actual_end = datetime.now(timezone.utc)
    op.quantity_completed = quantity_completed
    # Note: op.quantity_scrapped is set below — either by scrap_service (cascade)
    # or directly in the non-cascade path, to avoid double-counting.
    op.scrap_reason = scrap_reason

    # Calculate actual run time if not provided
    if actual_run_minutes is not None:
        op.actual_run_minutes = actual_run_minutes
    elif op.actual_start:
        # actual_start is stored as naive UTC (DateTime column); attach tzinfo
        # so the subtraction with an aware datetime works
        start = op.actual_start.replace(tzinfo=timezone.utc) if op.actual_start.tzinfo is None else op.actual_start
        elapsed = datetime.now(timezone.utc) - start
        op.actual_run_minutes = int(elapsed.total_seconds() / 60)

    if notes:
        op.notes = notes
    op.updated_at = datetime.now(timezone.utc)

    # Consume materials for this operation (for good + scrapped units)
    consumed = consume_operation_materials(db, op, quantity_completed, quantity_scrapped)
    if consumed:
        logger.info(f"Consumed {len(consumed)} materials for operation {op.id}")

    # Process cascading scrap accounting if scrapping
    scrap_result = None
    if quantity_scrapped > Decimal("0") and scrap_reason:
        from app.services.scrap_service import process_operation_scrap, ScrapError
        try:
            scrap_result = process_operation_scrap(
                db=db,
                po_id=po_id,
                op_id=op_id,
                quantity_scrapped=int(quantity_scrapped),
                scrap_reason_code=scrap_reason,
                notes=scrap_notes,
                create_replacement=create_replacement,
                user_id=user_id,
            )
            logger.info(
                f"Processed cascading scrap for {quantity_scrapped} units: "
                f"{scrap_result['scrap_records_created']} records, "
                f"${scrap_result['total_scrap_cost']:.2f} total cost"
            )
        except ScrapError as e:
            # Log but don't fail the operation completion
            logger.error(f"Failed to process cascading scrap: {e.message}")
            # Still record the scrap on the operation, just without cascade accounting
            pass

    # Auto-skip downstream operations if no good pieces remain
    if quantity_completed == Decimal("0"):
        skipped = auto_skip_downstream_operations(db, po, op)
        if skipped > 0:
            logger.info(f"Auto-skipped {skipped} downstream operations due to 0 good pieces")

    # Update PO quantities BEFORE deriving status
    po.quantity_completed = quantity_completed
    # Don't double-update scrap quantities — scrap_service handles both op and PO
    # when cascade accounting runs.  Only set directly if scrap_service wasn't called.
    if not scrap_result:
        op.quantity_scrapped = quantity_scrapped
        po.quantity_scrapped = (po.quantity_scrapped or Decimal("0")) + quantity_scrapped

    # Update PO status (uses quantity_completed to determine complete vs short)
    # Pass operator_name for inventory transaction attribution
    update_po_status(db, po, created_by=op.operator_name or f"user:{user_id}" if user_id else None)

    db.flush()
    return op, scrap_result


def auto_skip_downstream_operations(
    db: Session,
    po: ProductionOrder,
    completed_op: ProductionOrderOperation
) -> int:
    """
    Auto-skip all downstream operations when no pieces remain.

    Called when an operation completes with quantity_completed = 0.
    All subsequent pending/queued operations are marked as skipped
    with reason indicating no pieces from previous operation.

    Args:
        db: Database session
        po: Production order
        completed_op: The operation that just completed with 0 good pieces

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
            op.notes = f"SKIPPED: Auto-skipped - no pieces from operation {completed_op.sequence}"
            op.updated_at = datetime.now(timezone.utc)
            skipped_count += 1
            logger.info(f"Auto-skipped operation {op.id} (seq {op.sequence}) due to 0 pieces from op {completed_op.sequence}")

    return skipped_count


def skip_operation(
    db: Session,
    po_id: int,
    op_id: int,
    reason: str
) -> ProductionOrderOperation:
    """
    Skip an operation.

    Validations:
    - Operation must be pending or queued
    - Previous operation must be complete or skipped

    Returns:
        Updated operation

    Raises:
        OperationError: If validation fails
    """
    po, op = get_operation_with_validation(db, po_id, op_id)

    # Check operation status
    if op.status not in ('pending', 'queued'):
        raise OperationError(f"Cannot skip operation in status '{op.status}'", 400)

    # Check previous operation
    prev_op = get_previous_operation(db, po, op)
    if prev_op and prev_op.status not in ('complete', 'skipped'):
        raise OperationError(
            f"Previous operation (sequence {prev_op.sequence}) must be complete before skipping this one",
            400
        )

    # Update operation
    op.status = 'skipped'
    op.notes = f"SKIPPED: {reason}"
    op.updated_at = datetime.now(timezone.utc)

    # Update PO status
    update_po_status(db, po, created_by=op.operator_name)

    db.flush()
    return op


def list_operations(
    db: Session,
    po_id: int
) -> List[ProductionOrderOperation]:
    """
    List operations for a production order.

    Returns:
        List of operations ordered by sequence

    Raises:
        OperationError: If PO not found
    """
    po = db.get(ProductionOrder, po_id)
    if not po:
        raise OperationError(f"Production order {po_id} not found", 404)

    return sorted(po.operations, key=lambda x: x.sequence)
