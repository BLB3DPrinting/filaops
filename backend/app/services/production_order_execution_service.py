"""
Production Order Execution Service — lifecycle transitions.

Moved from production_order_service.py (DEBT-1 D2-A mechanical split). Holds the
start / complete / accept-short / split lifecycle transitions. No behavior
change.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import (
    ProductionOrder,
    ProductionOrderOperation,
    Product,
)
from app.models.inventory import Inventory

logger = get_logger(__name__)


def start_production_order(db: Session, order_id: int) -> ProductionOrder:
    """Start production on an order."""
    from app.services.production_order_service import get_production_order

    order = get_production_order(db, order_id)

    if order.status not in ["released", "scheduled"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start order in {order.status} status"
        )

    order.status = "in_progress"
    order.actual_start = datetime.now(timezone.utc)

    # Start first operation if not already started
    first_op = (
        db.query(ProductionOrderOperation)
        .filter(ProductionOrderOperation.production_order_id == order_id)
        .order_by(ProductionOrderOperation.sequence)
        .first()
    )
    if first_op and first_op.status == "pending":
        first_op.status = "running"
        first_op.actual_start = datetime.now(timezone.utc)

    return order


def complete_production_order(
    db: Session,
    order_id: int,
    user_email: str,
    quantity_good: int,
    quantity_scrapped: int = 0,
    force_close_short: bool = False,
    notes: Optional[str] = None,
    user_id: Optional[int] = None,
) -> ProductionOrder:
    """
    Complete a production order and record finished goods to inventory.

    Args:
        order_id: Production order to complete
        user_email: User completing the order
        quantity_good: Good quantity produced
        quantity_scrapped: Scrapped quantity
        force_close_short: Allow closing order with less than ordered quantity
        notes: Completion notes
        user_id: Completing user's id for journal-entry attribution (the
            completion GL entry's created_by/posted_by); optional for
            backward compatibility

    Returns:
        Updated ProductionOrder
    """
    from app.services.inventory_service import process_production_completion
    from app.services.production_order_service import get_production_order

    order = get_production_order(db, order_id)

    # Idempotent: already complete is a no-op
    if order.status == "complete":
        return order

    if order.status == "short":
        raise HTTPException(
            status_code=400,
            detail="Order is in short status. Use the accept-short action to complete it."
        )
    if order.status not in ["in_progress", "released"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot complete order in {order.status} status"
        )

    total_reported = quantity_good + quantity_scrapped
    if total_reported > order.quantity_ordered:
        raise HTTPException(
            status_code=400,
            detail=f"Total reported ({total_reported}) exceeds ordered ({order.quantity_ordered})"
        )

    # Check for short completion
    remaining = order.quantity_ordered - (order.quantity_completed or 0)
    if quantity_good < remaining and not force_close_short:
        raise HTTPException(
            status_code=400,
            detail=f"Completing short ({quantity_good} of {remaining} remaining). Set force_close_short=true to close short."
        )

    # Process inventory transaction
    try:
        process_production_completion(
            db=db,
            production_order=order,
            quantity_completed=Decimal(str(quantity_good)),
            created_by=user_email,
            user_id=user_id,
        )
    except Exception as e:
        logger.error(f"Failed to process production completion: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process inventory: {str(e)}"
        )

    # Update order quantities
    order.quantity_completed = (order.quantity_completed or 0) + quantity_good
    order.quantity_scrapped = (order.quantity_scrapped or 0) + quantity_scrapped

    # Check if complete (either fully or force-closed short)
    if order.quantity_completed >= order.quantity_ordered or force_close_short:
        order.status = "complete"
        order.completed_at = datetime.now(timezone.utc)
        order.actual_end = datetime.now(timezone.utc)

        # Route the finished order into the QC inspection queue
        if order.qc_status in (None, "not_required"):
            order.qc_status = "pending"

        # Complete all operations
        for op in order.operations:
            if op.status != "complete":
                op.status = "complete"
                if not op.actual_end:
                    op.actual_end = datetime.now(timezone.utc)

        # Recalculate actual costs from consumed quantities and actual times
        try:
            from app.services.cost_estimation_service import recalculate_actual_cost
            recalculate_actual_cost(db, order)
        except Exception as e:
            logger.warning("Actual cost recalculation failed for %s: %s", order.code, e)

        # Advance the parent sales order (allocated qty + ready_to_ship once all
        # its WOs are done). The per-operation completion path syncs this; the
        # bulk-complete path (e.g. "Complete Production" on ProductionOrderDetail,
        # and the only path for routing-less WOs) must too, or the SO is stranded
        # in in_production and never becomes shippable. sync_on_production_complete
        # is a no-op unless every sibling WO is complete, so it is safe here.
        try:
            from app.services.status_sync_service import sync_on_production_complete
            sync_on_production_complete(db, order)
        except Exception as e:
            logger.error("Failed to sync sales order for %s: %s", order.code, e)

    if notes:
        if order.notes:
            order.notes = f"{order.notes}\n[{datetime.now(timezone.utc).isoformat()}] {notes}"
        else:
            order.notes = f"[{datetime.now(timezone.utc).isoformat()}] {notes}"

    return order


def accept_short_production_order(
    db: Session,
    order_id: int,
    user_email: str,
    user_id: int,
    notes: Optional[str] = None,
) -> ProductionOrder:
    """Accept a production order short — complete it with the quantity already produced.

    When all operations finish but quantity_completed < quantity_ordered, the PO
    enters "short" status. No inventory transactions have happened yet at that point.
    Accept-short processes inventory for the actual completed quantity and sets
    the PO to "complete", unblocking downstream SO close-short.

    Inventory actions:
    - Releases all material reservations (allocated_quantity freed)
    - Consumes materials for quantity_completed (BOM-proportional, may create GL via consume path)
    - Receipts quantity_completed as finished goods (not quantity_ordered)
    """
    from app.services.inventory_service import (
        consume_production_materials,
        get_or_create_default_location,
        create_inventory_transaction,
        get_effective_cost_per_inventory_unit,
    )
    from app.models.close_short_record import CloseShortRecord

    # Lock the row to prevent concurrent accept-short from double-applying inventory
    order = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Production order not found")

    # Guard: must be in "short" status (all operations finished, qty < ordered)
    if order.status != "short":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot accept short on order in '{order.status}' status. "
                   f"Order must be in 'short' status."
        )

    # Guard: must have produced something but less than ordered
    qty_completed = Decimal(str(order.quantity_completed or 0))
    qty_ordered = Decimal(str(order.quantity_ordered))
    if qty_completed <= 0:
        raise HTTPException(
            status_code=400,
            detail="Cannot accept short: no units have been completed."
        )
    if qty_completed >= qty_ordered:
        raise HTTPException(
            status_code=400,
            detail="Order is already fully completed — use the complete action instead."
        )

    # NOTE: Between accepting short on a component PO and its parent assembly PO,
    # component available_quantity may be temporarily negative. This is expected —
    # the assembly PO still holds reservations based on original ordered qty.
    # The negative window resolves when the assembly PO is accepted-short.
    # If this becomes a product feature, consider batch accept-short that resolves
    # the full PO chain in a single transaction.

    # Capture pre-action inventory state for audit record (all locations)
    product_invs = db.query(Inventory).filter(
        Inventory.product_id == order.product_id
    ).all()
    inv_snapshot = [
        {
            "product_id": order.product_id,
            "location_id": inv.location_id,
            "on_hand": str(inv.on_hand_quantity or 0),
            "allocated": str(inv.allocated_quantity or 0),
            "available": str(inv.available_quantity or 0),
        }
        for inv in product_invs
    ]

    # Idempotency guard: reject if inventory was already processed for this PO
    from app.models.inventory import InventoryTransaction
    existing_receipt = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.reference_id == order.id,
        InventoryTransaction.transaction_type == "receipt",
    ).first()
    if existing_receipt:
        raise HTTPException(
            status_code=400,
            detail=f"Inventory already processed for {order.code}. Cannot accept short again."
        )

    # Process inventory for the actual completed quantity:
    # 1. Release reservations and consume materials for qty_completed
    consume_production_materials(
        db=db,
        production_order=order,
        quantity_completed=qty_completed,
        created_by=user_email,
        release_reservations=True,
    )

    # 2. Receipt finished goods for qty_completed (NOT quantity_ordered)
    #    We call create_inventory_transaction directly instead of receive_finished_goods
    #    because receive_finished_goods always receipts quantity_ordered.
    product = db.query(Product).filter(Product.id == order.product_id).first()
    if not product:
        raise HTTPException(
            status_code=500,
            detail=f"Product {order.product_id} not found for production order {order.code}"
        )
    location = get_or_create_default_location(db)
    create_inventory_transaction(
        db=db,
        product_id=order.product_id,
        location_id=location.id,
        transaction_type="receipt",
        quantity=qty_completed,
        reference_type="production_order",
        reference_id=order.id,
        notes=f"Accept short PO#{order.code}: {qty_completed} of {qty_ordered} produced",
        cost_per_unit=get_effective_cost_per_inventory_unit(product),
        created_by=user_email,
    )

    # Post the completion journal entry (#880) over the consumption +
    # receipt transactions just written. This path hand-rolls its FG
    # receipt (instead of receive_finished_goods), so it must call the
    # poster itself; the sweep's journal_entry_id-IS-NULL predicate makes
    # this idempotent with any per-operation consumption already posted.
    from app.services.production_gl_service import (
        create_production_completion_gl_entry,
    )
    create_production_completion_gl_entry(db, order, user_id=user_id)

    # 3. Transition to complete
    order.status = "complete"
    order.completed_at = datetime.now(timezone.utc)
    order.actual_end = datetime.now(timezone.utc)

    # Route the finished order into the QC inspection queue
    if order.qc_status in (None, "not_required"):
        order.qc_status = "pending"

    # Complete any remaining operations
    for op in order.operations:
        if op.status != "complete":
            op.status = "complete"
            if not op.actual_end:
                op.actual_end = datetime.now(timezone.utc)

    # Append notes
    if notes:
        timestamp = datetime.now(timezone.utc).isoformat()
        if order.notes:
            order.notes = f"{order.notes}\n[{timestamp}] Accepted short: {notes}"
        else:
            order.notes = f"[{timestamp}] Accepted short: {notes}"

    # Write audit record
    audit_record = CloseShortRecord(
        entity_type="production_order",
        entity_id=order_id,
        performed_by=user_id,
        reason=notes,
        line_adjustments=[{
            "before_qty": str(qty_ordered),
            "after_qty": str(qty_completed),
            "reason": f"Accepted short: {qty_completed} of {qty_ordered} produced",
        }],
        inventory_snapshot=inv_snapshot,
    )
    db.add(audit_record)

    return order


def split_production_order(
    db: Session,
    order_id: int,
    split_quantity: int,
    user_email: str,
    reason: Optional[str] = None,
) -> tuple[ProductionOrder, ProductionOrder]:
    """
    Split a production order into two orders.

    Args:
        order_id: Order to split
        split_quantity: Quantity for the new order
        user_email: User performing the split
        reason: Reason for split

    Returns:
        Tuple of (original_order, new_order)
    """
    from app.services.inventory_service import reserve_production_materials
    from app.services.production_order_service import (
        get_production_order,
        generate_production_order_code,
        copy_routing_to_operations,
    )

    order = get_production_order(db, order_id)

    if order.status not in ["draft", "scheduled", "released"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot split order in {order.status} status"
        )

    if split_quantity <= 0:
        raise HTTPException(status_code=400, detail="Split quantity must be positive")

    remaining = order.quantity_ordered - split_quantity
    if remaining <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"Split quantity ({split_quantity}) must be less than ordered ({order.quantity_ordered})"
        )

    # Update original order quantity
    order.quantity_ordered = remaining

    # Create new order
    new_code = generate_production_order_code(db)
    new_order = ProductionOrder(
        code=new_code,
        product_id=order.product_id,
        bom_id=order.bom_id,
        routing_id=order.routing_id,
        sales_order_id=order.sales_order_id,
        sales_order_line_id=order.sales_order_line_id,
        quantity_ordered=split_quantity,
        quantity_completed=0,
        quantity_scrapped=0,
        source="split",
        status="draft",
        priority=order.priority,
        due_date=order.due_date,
        assigned_to=order.assigned_to,
        notes=f"Split from {order.code}" + (f": {reason}" if reason else ""),
        created_by=user_email,
    )
    db.add(new_order)
    db.flush()

    # Copy operations with recalculated quantities
    if order.routing_id:
        copy_routing_to_operations(db, new_order, order.routing_id)

    # Allocate materials for new order
    reserve_production_materials(
        db=db,
        production_order=new_order,
        created_by=user_email,
    )

    # Update original order notes
    if order.notes:
        order.notes = f"{order.notes}\n[SPLIT] {split_quantity} units moved to {new_code}"
    else:
        order.notes = f"[SPLIT] {split_quantity} units moved to {new_code}"

    logger.info(f"Split {order.code}: {split_quantity} units to {new_code}")

    return order, new_order
