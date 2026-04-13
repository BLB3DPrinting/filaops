"""
Production Order Service — CRUD, status management, scheduling, and operations.

Extracted from production_orders.py (ARCHITECT-003).
"""
import math
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, desc, or_, case
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import (
    ProductionOrder,
    ProductionOrderOperation,
    Product,
    BOM,
    ScrapReason,
)
from app.models.bom import BOMLine
from app.models.inventory import Inventory
from app.models.manufacturing import Routing, RoutingOperation, Resource
from app.models.production_order import ProductionOrderOperationMaterial, ScrapRecord
from app.models.work_center import WorkCenter
from app.models.material_spool import MaterialSpool, ProductionOrderSpool
logger = get_logger(__name__)


# =============================================================================
# Code Generation
# =============================================================================

def generate_production_order_code(db: Session) -> str:
    """Generate sequential production order code: PO-YYYY-NNN"""
    year = datetime.now(timezone.utc).year
    last = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.code.like(f"PO-{year}-%"))
        .order_by(desc(ProductionOrder.code))
        .first()
    )
    if last:
        try:
            last_num = int(last.code.split("-")[2])
            next_num = last_num + 1
        except (IndexError, ValueError):
            next_num = 1
    else:
        next_num = 1
    return f"PO-{year}-{next_num:04d}"


# =============================================================================
# Routing / Operations Helpers
# =============================================================================

def copy_routing_to_operations(
    db: Session,
    order: ProductionOrder,
    routing_id: int,
) -> list[ProductionOrderOperation]:
    """Copy routing operations AND their materials to production order operations."""
    routing_ops = (
        db.query(RoutingOperation)
        .filter(RoutingOperation.routing_id == routing_id)
        .order_by(RoutingOperation.sequence)
        .all()
    )

    operations = []
    for rop in routing_ops:
        op = ProductionOrderOperation(
            production_order_id=order.id,
            routing_operation_id=rop.id,
            work_center_id=rop.work_center_id,
            resource_id=None,
            sequence=rop.sequence,
            operation_code=rop.operation_code,
            operation_name=rop.operation_name,
            planned_setup_minutes=rop.setup_time_minutes or 0,
            planned_run_minutes=float(rop.run_time_minutes or 0) * float(order.quantity_ordered),
            status="pending",
        )
        db.add(op)
        db.flush()

        # Copy materials from routing operation
        for rom in rop.materials:
            if rom.is_cost_only:
                continue

            qty_required = rom.calculate_required_quantity(int(order.quantity_ordered))

            unit_upper = (rom.unit or "").upper()
            if unit_upper in ("EA", "EACH", "PCS", "UNIT", "BOX", "BOXES"):
                qty_required = math.ceil(qty_required)

            mat = ProductionOrderOperationMaterial(
                production_order_operation_id=op.id,
                component_id=rom.component_id,
                routing_operation_material_id=rom.id,
                quantity_required=Decimal(str(qty_required)),
                unit=rom.unit,
                quantity_allocated=Decimal("0"),
                quantity_consumed=Decimal("0"),
                status="pending",
            )
            db.add(mat)

        operations.append(op)

    return operations


# =============================================================================
# Production Order CRUD
# =============================================================================

def list_production_orders(
    db: Session,
    *,
    status: Optional[str] = None,
    product_id: Optional[int] = None,
    sales_order_id: Optional[int] = None,
    priority: Optional[int] = None,
    due_before: Optional[date] = None,
    due_after: Optional[date] = None,
    search: Optional[str] = None,
    offset: int = 0,
    limit: int = 50,
) -> list[ProductionOrder]:
    """List production orders with filtering and pagination."""
    query = db.query(ProductionOrder)

    if status:
        query = query.filter(ProductionOrder.status == status)
    if product_id:
        query = query.filter(ProductionOrder.product_id == product_id)
    if sales_order_id:
        query = query.filter(ProductionOrder.sales_order_id == sales_order_id)
    if priority:
        query = query.filter(ProductionOrder.priority == priority)
    if due_before:
        query = query.filter(ProductionOrder.due_date <= due_before)
    if due_after:
        query = query.filter(ProductionOrder.due_date >= due_after)
    if search:
        search_term = f"%{search}%"
        query = query.join(Product, ProductionOrder.product_id == Product.id).filter(
            or_(
                ProductionOrder.code.ilike(search_term),
                Product.sku.ilike(search_term),
                Product.name.ilike(search_term),
            )
        )

    query = query.order_by(
        ProductionOrder.priority.asc(),
        case((ProductionOrder.due_date.is_(None), 1), else_=0),
        ProductionOrder.due_date.asc(),
        ProductionOrder.created_at.desc(),
    )

    return query.offset(offset).limit(limit).all()


def get_production_order(db: Session, order_id: int) -> ProductionOrder:
    """Get a production order by ID or raise 404."""
    order = db.query(ProductionOrder).filter(ProductionOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Production order not found")
    return order


def get_production_order_by_code(db: Session, code: str) -> ProductionOrder:
    """Get a production order by code or raise 404."""
    order = db.query(ProductionOrder).filter(ProductionOrder.code == code).first()
    if not order:
        raise HTTPException(status_code=404, detail="Production order not found")
    return order


def create_production_order(
    db: Session,
    *,
    product_id: int,
    quantity_ordered: int,
    created_by: str,
    bom_id: Optional[int] = None,
    routing_id: Optional[int] = None,
    sales_order_id: Optional[int] = None,
    sales_order_line_id: Optional[int] = None,
    source: str = "manual",
    priority: int = 3,
    due_date: Optional[date] = None,
    assigned_to: Optional[str] = None,
    notes: Optional[str] = None,
) -> ProductionOrder:
    """Create a new production order."""
    from app.services.inventory_service import reserve_production_materials

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Find default BOM if not specified
    if not bom_id:
        default_bom = db.query(BOM).filter(
            BOM.product_id == product_id,
            BOM.active.is_(True)
        ).order_by(desc(BOM.created_at)).first()
        if default_bom:
            bom_id = default_bom.id

    # Find default routing if not specified
    if not routing_id:
        default_routing = db.query(Routing).filter(
            Routing.product_id == product_id,
            Routing.is_active.is_(True)
        ).first()
        if default_routing:
            routing_id = default_routing.id

    code = generate_production_order_code(db)

    order = ProductionOrder(
        code=code,
        product_id=product_id,
        bom_id=bom_id,
        routing_id=routing_id,
        sales_order_id=sales_order_id,
        sales_order_line_id=sales_order_line_id,
        quantity_ordered=quantity_ordered,
        quantity_completed=0,
        quantity_scrapped=0,
        source=source,
        status="draft",
        priority=priority,
        due_date=due_date,
        assigned_to=assigned_to,
        notes=notes,
        created_by=created_by,
    )
    db.add(order)
    db.flush()

    if routing_id:
        copy_routing_to_operations(db, order, routing_id)

    reserve_production_materials(
        db=db,
        production_order=order,
        created_by=created_by,
    )

    # Auto-estimate costs if operations exist
    if order.operations:
        from app.services.cost_estimation_service import estimate_production_order_cost
        try:
            estimate_production_order_cost(db, order)
        except Exception:
            logger.exception("Cost estimation failed for production order id=%s code=%s", order.id, order.code)

    return order


def update_production_order(
    db: Session,
    order_id: int,
    *,
    quantity_ordered: Optional[int] = None,
    priority: Optional[int] = None,
    due_date: Optional[date] = None,
    assigned_to: Optional[str] = None,
    notes: Optional[str] = None,
) -> ProductionOrder:
    """Update a production order."""
    order = get_production_order(db, order_id)

    if order.status not in ["draft", "scheduled"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update order in {order.status} status. Only draft/scheduled orders can be modified."
        )

    if quantity_ordered is not None:
        order.quantity_ordered = quantity_ordered
    if priority is not None:
        order.priority = priority
    if due_date is not None:
        order.due_date = due_date
    if assigned_to is not None:
        order.assigned_to = assigned_to
    if notes is not None:
        order.notes = notes

    order.updated_at = datetime.now(timezone.utc)

    return order


def delete_production_order(db: Session, order_id: int) -> None:
    """Delete a production order."""
    from app.services.inventory_service import release_production_reservations

    order = get_production_order(db, order_id)

    # Can only delete draft orders
    if order.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete order in {order.status} status. Only draft orders can be deleted."
        )

    # Release any reservations
    release_production_reservations(db, order, "Deleted")

    db.delete(order)


# =============================================================================
# Status Management
# =============================================================================

def release_production_order(
    db: Session,
    order_id: int,
    user_email: str,
    force: bool = False,
) -> ProductionOrder:
    """
    Release a production order for manufacturing.

    Validates material availability and transitions status to 'released'.
    """
    order = get_production_order(db, order_id)

    # Idempotent: already released is a no-op
    if order.status == "released":
        return order

    # Allow releasing from draft, scheduled, or on_hold (resume from hold)
    if order.status not in ["draft", "scheduled", "on_hold"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot release order in {order.status} status"
        )

    # Check material availability unless forced
    if not force:
        blocking_issues = []
        for op in order.operations:
            for mat in op.materials:
                if mat.quantity_allocated < mat.quantity_required:
                    shortage = mat.quantity_required - mat.quantity_allocated
                    component = db.query(Product).filter(Product.id == mat.component_id).first()
                    blocking_issues.append({
                        "component_sku": component.sku if component else f"ID:{mat.component_id}",
                        "operation": op.operation_name,
                        "shortage": float(shortage),
                    })

        if blocking_issues:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Cannot release: material shortages detected",
                    "shortages": blocking_issues,
                    "hint": "Use force=true to release anyway"
                }
            )

    order.status = "released"
    order.released_at = datetime.now(timezone.utc)

    logger.info(f"Production order {order.code} released by {user_email}")

    return order


def start_production_order(db: Session, order_id: int) -> ProductionOrder:
    """Start production on an order."""
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

    Returns:
        Updated ProductionOrder
    """
    from app.services.inventory_service import process_production_completion

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

    # 3. Transition to complete
    order.status = "complete"
    order.completed_at = datetime.now(timezone.utc)
    order.actual_end = datetime.now(timezone.utc)

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


def cancel_production_order(
    db: Session,
    order_id: int,
    user_email: str,
    notes: Optional[str] = None,
) -> ProductionOrder:
    """Cancel a production order."""
    from app.services.inventory_service import release_production_reservations

    order = get_production_order(db, order_id)

    # Idempotent: already cancelled is a no-op
    if order.status == "cancelled":
        return order

    # Can't cancel completed orders
    if order.status == "complete":
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel a completed order"
        )

    # Release reservations
    release_production_reservations(db, order, f"Cancelled: {notes or 'No reason given'}")

    order.status = "cancelled"
    if notes:
        if order.notes:
            order.notes = f"{order.notes}\n[CANCELLED] {notes}"
        else:
            order.notes = f"[CANCELLED] {notes}"

    logger.info(f"Production order {order.code} cancelled by {user_email}: {notes}")

    return order


def refresh_production_order_routing(
    db: Session,
    order_id: int,
    user_email: str,
) -> ProductionOrder:
    """Replace PO operations with the product's current active routing.

    Allowed when the order is draft, released, or on_hold and has no
    in-progress or completed operations.  Any pending operations (and their
    materials) are deleted before the new routing is copied in.
    """
    order = get_production_order(db, order_id)

    REFRESHABLE = {"draft", "released", "on_hold"}
    if order.status not in REFRESHABLE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot refresh routing on a {order.status} order. "
                   f"Order must be draft, released, or on_hold.",
        )

    # Block if any operation has already been started
    active_ops = [
        op for op in order.operations
        if op.status not in ("pending", "cancelled")
    ]
    if active_ops:
        raise HTTPException(
            status_code=409,
            detail="Cannot refresh routing: one or more operations are already in progress or complete.",
        )

    # Find the active routing for this product
    routing = (
        db.query(Routing)
        .filter(
            Routing.product_id == order.product_id,
            Routing.is_active.is_(True),
            Routing.is_template.is_(False),
        )
        .order_by(Routing.id.desc())
        .first()
    )
    if not routing:
        raise HTTPException(
            status_code=404,
            detail="No active routing found for this product. Add a routing to the item first.",
        )

    # Delete existing pending operations (cascade removes their materials)
    for op in list(order.operations):
        if op.status in ("pending", "cancelled"):
            db.delete(op)
    db.flush()

    # Snapshot new routing onto the order
    order.routing_id = routing.id
    copy_routing_to_operations(db, order, routing.id)

    logger.info(
        f"Production order {order.code} routing refreshed to routing {routing.id} "
        f"({routing.code}) by {user_email}"
    )

    return order


def hold_production_order(
    db: Session,
    order_id: int,
    reason: Optional[str] = None,
) -> ProductionOrder:
    """Put a production order on hold."""
    order = get_production_order(db, order_id)

    # Can only hold released or in_progress orders
    if order.status not in ["released", "in_progress"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot hold order in {order.status} status. Must be released or in progress."
        )

    order.status = "on_hold"
    if reason:
        if order.notes:
            order.notes = f"{order.notes}\n[ON HOLD] {reason}"
        else:
            order.notes = f"[ON HOLD] {reason}"

    return order


# =============================================================================
# Scheduling
# =============================================================================

def schedule_production_order(
    db: Session,
    order_id: int,
    scheduled_start: Optional[datetime] = None,
    scheduled_end: Optional[datetime] = None,
    resource_assignments: Optional[dict] = None,
) -> ProductionOrder:
    """Schedule a production order with start/end times and resource assignments."""
    order = get_production_order(db, order_id)

    if order.status not in ["draft", "scheduled"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot schedule order in {order.status} status"
        )

    if scheduled_start:
        order.scheduled_start = scheduled_start
    if scheduled_end:
        order.scheduled_end = scheduled_end

    # Assign resources to operations
    if resource_assignments:
        for op in order.operations:
            if str(op.id) in resource_assignments:
                resource_id = resource_assignments[str(op.id)]
                resource = db.query(Resource).filter(Resource.id == resource_id).first()
                if resource:
                    op.resource_id = resource_id

    order.status = "scheduled"

    return order


def get_schedule_summary(db: Session) -> dict:
    """Get production schedule summary by status and work center."""
    # Count by status
    status_counts = (
        db.query(
            ProductionOrder.status,
            func.count(ProductionOrder.id).label("count")
        )
        .filter(ProductionOrder.status.notin_(["complete", "cancelled"]))
        .group_by(ProductionOrder.status)
        .all()
    )

    by_status = {row.status: row.count for row in status_counts}

    # Count due today/overdue
    today = date.today()
    due_today = db.query(ProductionOrder).filter(
        ProductionOrder.status.notin_(["complete", "cancelled"]),
        ProductionOrder.due_date == today
    ).count()

    overdue = db.query(ProductionOrder).filter(
        ProductionOrder.status.notin_(["complete", "cancelled"]),
        ProductionOrder.due_date < today
    ).count()

    # Work center queues
    wc_query = (
        db.query(
            WorkCenter.id,
            WorkCenter.code,
            WorkCenter.name,
            func.count(ProductionOrderOperation.id).label("queue_count")
        )
        .join(ProductionOrderOperation, ProductionOrderOperation.work_center_id == WorkCenter.id)
        .join(ProductionOrder, ProductionOrderOperation.production_order_id == ProductionOrder.id)
        .filter(
            ProductionOrder.status.in_(["released", "in_progress"]),
            ProductionOrderOperation.status.in_(["pending", "queued", "running"])
        )
        .group_by(WorkCenter.id, WorkCenter.code, WorkCenter.name)
        .all()
    )

    work_centers = [
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "queue_count": row.queue_count
        }
        for row in wc_query
    ]

    return {
        "by_status": by_status,
        "due_today": due_today,
        "overdue": overdue,
        "work_centers": work_centers,
        "total_active": sum(by_status.values()),
    }


def get_work_center_queues(db: Session) -> list[dict]:
    """Get queue of operations by work center."""
    work_centers = db.query(WorkCenter).filter(WorkCenter.is_active.is_(True)).all()

    result = []
    for wc in work_centers:
        ops = (
            db.query(ProductionOrderOperation)
            .join(ProductionOrder, ProductionOrderOperation.production_order_id == ProductionOrder.id)
            .filter(
                ProductionOrderOperation.work_center_id == wc.id,
                ProductionOrder.status.in_(["released", "in_progress"]),
                ProductionOrderOperation.status.in_(["pending", "queued", "running"])
            )
            .order_by(
                ProductionOrder.priority.asc(),
                ProductionOrder.due_date.asc()
            )
            .all()
        )

        queue_items = []
        for op in ops:
            order = db.query(ProductionOrder).filter(ProductionOrder.id == op.production_order_id).first()
            product = db.query(Product).filter(Product.id == order.product_id).first() if order else None

            queue_items.append({
                "operation_id": op.id,
                "production_order_id": op.production_order_id,
                "production_order_code": order.code if order else None,
                "product_sku": product.sku if product else None,
                "product_name": product.name if product else None,
                "operation_name": op.operation_name,
                "status": op.status,
                "priority": order.priority if order else 3,
                "due_date": order.due_date if order else None,
                "scheduled_start": op.scheduled_start,
            })

        result.append({
            "work_center_id": wc.id,
            "work_center_code": wc.code,
            "work_center_name": wc.name,
            "queue_count": len(queue_items),
            "queue": queue_items,
        })

    return result


# =============================================================================
# QC Inspection
# =============================================================================

def record_qc_inspection(
    db: Session,
    order_id: int,
    inspector: str,
    qc_status: str,
    quantity_passed: int,
    quantity_failed: int = 0,
    failure_reason: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    """
    Record QC inspection results for a production order.

    Args:
        order_id: Production order
        inspector: Inspector name
        qc_status: QC result (passed, failed, conditional)
        quantity_passed: Quantity that passed QC
        quantity_failed: Quantity that failed QC
        failure_reason: Reason for failures
        notes: Inspection notes

    Returns:
        Dict with inspection results
    """
    order = get_production_order(db, order_id)

    # Find QC operation
    qc_op = (
        db.query(ProductionOrderOperation)
        .filter(
            ProductionOrderOperation.production_order_id == order_id,
            ProductionOrderOperation.operation_code.ilike("%QC%")
        )
        .first()
    )

    if qc_op:
        qc_op.status = "complete"
        qc_op.actual_end = datetime.now(timezone.utc)
        qc_op.quantity_completed = quantity_passed
        qc_op.quantity_scrapped = quantity_failed
        qc_op.operator_name = inspector
        if notes:
            qc_op.notes = notes

    # Update order based on QC result
    if qc_status == "failed" and quantity_failed > 0:
        order.quantity_scrapped = (order.quantity_scrapped or 0) + quantity_failed

    inspection_result = {
        "order_id": order_id,
        "order_code": order.code,
        "inspector": inspector,
        "qc_status": qc_status,
        "quantity_passed": quantity_passed,
        "quantity_failed": quantity_failed,
        "failure_reason": failure_reason,
        "notes": notes,
        "inspected_at": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"QC inspection recorded for {order.code}: {qc_status}")

    return inspection_result


# =============================================================================
# Split Order
# =============================================================================

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


# =============================================================================
# Scrap Management
# =============================================================================

def get_scrap_reasons(db: Session, include_inactive: bool = False) -> list[ScrapReason]:
    """Get list of scrap reasons."""
    query = db.query(ScrapReason)
    if not include_inactive:
        query = query.filter(ScrapReason.active.is_(True))
    return query.order_by(ScrapReason.sequence, ScrapReason.name).all()


def create_scrap_reason(
    db: Session,
    *,
    code: str,
    name: str,
    description: Optional[str] = None,
    sequence: int = 0,
) -> ScrapReason:
    """Create a new scrap reason."""
    # Check for duplicate code
    existing = db.query(ScrapReason).filter(ScrapReason.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Scrap reason with code '{code}' already exists")

    # Check for duplicate sequence
    seq_conflict = db.query(ScrapReason).filter(ScrapReason.sequence == sequence).first()
    if seq_conflict:
        raise HTTPException(
            status_code=400,
            detail=f"Sort order {sequence} is already used by '{seq_conflict.name}'"
        )

    reason = ScrapReason(
        code=code,
        name=name,
        description=description,
        sequence=sequence,
        active=True,
    )
    db.add(reason)
    return reason


def update_scrap_reason(
    db: Session,
    reason_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    sequence: Optional[int] = None,
    active: Optional[bool] = None,
) -> ScrapReason:
    """Update a scrap reason."""
    reason = db.query(ScrapReason).filter(ScrapReason.id == reason_id).first()
    if not reason:
        raise HTTPException(status_code=404, detail="Scrap reason not found")

    if name is not None:
        reason.name = name
    if description is not None:
        reason.description = description
    if sequence is not None:
        # Check for duplicate sequence (excluding this reason)
        seq_conflict = (
            db.query(ScrapReason)
            .filter(ScrapReason.sequence == sequence, ScrapReason.id != reason_id)
            .first()
        )
        if seq_conflict:
            raise HTTPException(
                status_code=400,
                detail=f"Sort order {sequence} is already used by '{seq_conflict.name}'"
            )
        reason.sequence = sequence
    if active is not None:
        reason.active = active

    return reason


def delete_scrap_reason(db: Session, reason_id: int) -> None:
    """Delete a scrap reason."""
    reason = db.query(ScrapReason).filter(ScrapReason.id == reason_id).first()
    if not reason:
        raise HTTPException(status_code=404, detail="Scrap reason not found")

    # Check if used
    used = db.query(ScrapRecord).filter(ScrapRecord.scrap_reason_code == reason.code).first()
    if used:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete: scrap reason is in use. Deactivate instead."
        )

    db.delete(reason)


def record_scrap(
    db: Session,
    order_id: int,
    *,
    quantity_scrapped: int,
    reason_code: str,
    operation_id: Optional[int] = None,
    notes: Optional[str] = None,
    create_remake: bool = False,
    user_email: str,
) -> dict:
    """
    Record scrap for a production order.

    Args:
        order_id: Production order
        quantity_scrapped: Quantity being scrapped
        reason_code: Scrap reason code
        operation_id: Optional operation where scrap occurred
        notes: Scrap notes
        create_remake: Whether to create a remake order
        user_email: User recording the scrap

    Returns:
        Dict with scrap details and optional remake order
    """
    from app.services.inventory_service import reserve_production_materials

    order = get_production_order(db, order_id)

    # Validate reason exists
    reason = db.query(ScrapReason).filter(ScrapReason.code == reason_code).first()
    if not reason:
        raise HTTPException(status_code=400, detail=f"Invalid scrap reason: {reason_code}")

    # Update order scrap quantity
    order.quantity_scrapped = (order.quantity_scrapped or 0) + quantity_scrapped

    # Create scrap record
    scrap_record = ScrapRecord(
        production_order_id=order_id,
        operation_id=operation_id,
        quantity=quantity_scrapped,
        reason_code=reason_code,
        notes=notes,
        recorded_by=user_email,
    )
    db.add(scrap_record)
    db.flush()

    result = {
        "order_id": order_id,
        "order_code": order.code,
        "quantity_scrapped": quantity_scrapped,
        "reason_code": reason_code,
        "scrap_record_id": scrap_record.id,
        "remake_order": None,
    }

    # Create remake order if requested
    if create_remake:
        remake_code = generate_production_order_code(db)
        remake_order = ProductionOrder(
            code=remake_code,
            product_id=order.product_id,
            bom_id=order.bom_id,
            routing_id=order.routing_id,
            sales_order_id=order.sales_order_id,
            sales_order_line_id=order.sales_order_line_id,
            quantity_ordered=quantity_scrapped,
            quantity_completed=0,
            quantity_scrapped=0,
            source="remake",
            status="draft",
            priority=max(1, order.priority - 1),  # Higher priority
            due_date=order.due_date,
            notes=f"Remake of {order.code} - {reason.name}: {notes or ''}",
            created_by=user_email,
            remake_of_id=order.id,
        )
        db.add(remake_order)
        db.flush()

        if order.routing_id:
            copy_routing_to_operations(db, remake_order, order.routing_id)

        reserve_production_materials(
            db=db,
            production_order=remake_order,
            created_by=user_email,
        )

        result["remake_order"] = {
            "id": remake_order.id,
            "code": remake_order.code,
            "quantity": remake_order.quantity_ordered,
        }

        logger.info(f"Created remake order {remake_code} from scrap on {order.code}")

    logger.info(f"Recorded scrap for {order.code}: {quantity_scrapped} units ({reason_code})")

    return result


# =============================================================================
# Operation Management
# =============================================================================

def update_operation(
    db: Session,
    order_id: int,
    operation_id: int,
    *,
    status: Optional[str] = None,
    quantity_completed: Optional[int] = None,
    quantity_scrapped: Optional[int] = None,
    actual_setup_minutes: Optional[float] = None,
    actual_run_minutes: Optional[float] = None,
    resource_id: Optional[int] = None,
    operator_name: Optional[str] = None,
    notes: Optional[str] = None,
) -> ProductionOrderOperation:
    """Update a production order operation."""
    get_production_order(db, order_id)  # Validate order exists

    op = db.query(ProductionOrderOperation).filter(
        ProductionOrderOperation.id == operation_id,
        ProductionOrderOperation.production_order_id == order_id
    ).first()

    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")

    if status:
        old_status = op.status
        op.status = status

        # Set timestamps based on status
        if status == "running" and old_status != "running":
            op.actual_start = datetime.now(timezone.utc)
        elif status == "complete" and old_status != "complete":
            op.actual_end = datetime.now(timezone.utc)

    if quantity_completed is not None:
        op.quantity_completed = quantity_completed
    if quantity_scrapped is not None:
        op.quantity_scrapped = quantity_scrapped
    if actual_setup_minutes is not None:
        op.actual_setup_minutes = actual_setup_minutes
    if actual_run_minutes is not None:
        op.actual_run_minutes = actual_run_minutes
    if resource_id is not None:
        op.resource_id = resource_id
    if operator_name is not None:
        op.operator_name = operator_name
    if notes is not None:
        op.notes = notes

    op.updated_at = datetime.now(timezone.utc)

    return op


# =============================================================================
# Material Availability
# =============================================================================

def get_material_availability(db: Session, order_id: int) -> dict:
    """
    Get material availability analysis for a production order.

    Returns:
        Dict with materials list and availability summary
    """
    order = get_production_order(db, order_id)

    materials = []
    total_required = 0
    total_available = 0
    total_short = 0

    for op in order.operations:
        for mat in op.materials:
            component = db.query(Product).filter(Product.id == mat.component_id).first()

            # Get available inventory
            inv_qty = db.query(func.sum(Inventory.available_quantity)).filter(
                Inventory.product_id == mat.component_id
            ).scalar() or Decimal("0")

            qty_required = float(mat.quantity_required)
            qty_available = float(inv_qty)
            qty_allocated = float(mat.quantity_allocated or 0)
            qty_short = max(0, qty_required - qty_available)

            materials.append({
                "operation_id": op.id,
                "operation_name": op.operation_name,
                "component_id": mat.component_id,
                "component_sku": component.sku if component else None,
                "component_name": component.name if component else None,
                "unit": mat.unit,
                "quantity_required": qty_required,
                "quantity_available": qty_available,
                "quantity_allocated": qty_allocated,
                "quantity_short": qty_short,
                "status": "ok" if qty_short == 0 else "short",
            })

            total_required += qty_required
            total_available += min(qty_available, qty_required)
            total_short += qty_short

    return {
        "order_id": order_id,
        "order_code": order.code,
        "materials": materials,
        "summary": {
            "total_materials": len(materials),
            "materials_available": sum(1 for m in materials if m["status"] == "ok"),
            "materials_short": sum(1 for m in materials if m["status"] == "short"),
            "can_start": total_short == 0,
        }
    }


# =============================================================================
# Required Orders (MRP)
# =============================================================================

def get_required_orders(db: Session, order_id: int) -> dict:
    """
    Get MRP cascade of required orders for a production order.

    Returns work orders needed for sub-assemblies and purchase orders
    needed for raw materials.
    """
    order = get_production_order(db, order_id)

    work_orders_needed = []
    purchase_orders_needed = []

    def explode_bom(product_id: int, quantity: Decimal, level: int = 0, visited: set = None):
        """Recursively explode BOM."""
        if visited is None:
            visited = set()

        bom = db.query(BOM).filter(
            BOM.product_id == product_id,
            BOM.active.is_(True)
        ).first()

        if not bom or bom.id in visited:
            return

        visited.add(bom.id)

        for line in db.query(BOMLine).filter(BOMLine.bom_id == bom.id).all():
            if line.is_cost_only:
                continue

            component = db.query(Product).filter(Product.id == line.component_id).first()
            if not component:
                continue

            # Calculate required quantity with scrap
            base_qty = Decimal(str(line.quantity or 0))
            scrap_factor = Decimal(str(line.scrap_factor or 0)) / Decimal("100")
            required_qty = base_qty * (Decimal("1") + scrap_factor) * quantity

            # Check inventory
            inv_qty = db.query(func.sum(Inventory.available_quantity)).filter(
                Inventory.product_id == component.id
            ).scalar() or Decimal("0")

            shortage = max(Decimal("0"), required_qty - inv_qty)

            if shortage <= 0:
                continue

            order_info = {
                "product_id": component.id,
                "product_sku": component.sku,
                "product_name": component.name,
                "quantity_required": float(required_qty),
                "quantity_available": float(inv_qty),
                "quantity_short": float(shortage),
                "bom_level": level,
                "has_bom": component.has_bom or False,
            }

            if component.has_bom:
                work_orders_needed.append(order_info)
                explode_bom(component.id, shortage, level + 1, visited.copy())
            else:
                purchase_orders_needed.append(order_info)

    # Start BOM explosion from order product
    explode_bom(order.product_id, Decimal(str(order.quantity_ordered)))

    return {
        "order_id": order_id,
        "order_code": order.code,
        "work_orders_needed": work_orders_needed,
        "purchase_orders_needed": purchase_orders_needed,
        "summary": {
            "work_orders": len(work_orders_needed),
            "purchase_orders": len(purchase_orders_needed),
            "total": len(work_orders_needed) + len(purchase_orders_needed),
        }
    }


# =============================================================================
# Cost Breakdown
# =============================================================================

def get_cost_breakdown(db: Session, order_id: int) -> dict:
    """Get cost breakdown for a production order.

    Uses get_effective_cost_per_inventory_unit() for material pricing and
    work center rates (machine + labor + overhead) for labor/machine costing.
    """
    from app.services.inventory_service import get_effective_cost_per_inventory_unit

    order = get_production_order(db, order_id)

    # Material costs — use proper UOM-aware cost per inventory unit
    material_costs = []
    total_material_cost = Decimal("0")

    for op in order.operations:
        for mat in op.materials:
            if mat.component:
                unit_cost = get_effective_cost_per_inventory_unit(mat.component) or Decimal("0")
                qty = mat.quantity_consumed if mat.status == "consumed" else mat.quantity_required
                line_cost = unit_cost * Decimal(str(qty))
                total_material_cost += line_cost

                material_costs.append({
                    "component_sku": mat.component.sku,
                    "component_name": mat.component.name,
                    "quantity": float(qty),
                    "unit_cost": float(unit_cost),
                    "total_cost": float(line_cost),
                })

    # Labor costs — use work center rates instead of hardcoded value
    labor_costs = []
    total_labor_cost = Decimal("0")

    for op in order.operations:
        minutes = op.actual_run_minutes if op.actual_run_minutes is not None else (op.planned_run_minutes or 0)
        setup = op.actual_setup_minutes if op.actual_setup_minutes is not None else (op.planned_setup_minutes or 0)
        total_minutes = Decimal(str(minutes)) + Decimal(str(setup))
        hours = total_minutes / Decimal("60")

        # Get rate from work center (machine + labor + overhead)
        wc = op.work_center
        if wc:
            machine = Decimal(str(wc.machine_rate_per_hour or 0))
            labor = Decimal(str(wc.labor_rate_per_hour or 0))
            overhead = Decimal(str(wc.overhead_rate_per_hour or 0))
            hourly_rate = machine + labor + overhead
            # Fall back to simplified hourly_rate if component rates are all zero
            if hourly_rate == Decimal("0"):
                hourly_rate = Decimal(str(wc.hourly_rate or 0))
        else:
            hourly_rate = Decimal("0")

        cost = hours * hourly_rate
        total_labor_cost += cost

        labor_costs.append({
            "operation": op.operation_name,
            "minutes": float(total_minutes),
            "hourly_rate": float(hourly_rate),
            "cost": float(cost),
        })

    total_cost = total_material_cost + total_labor_cost

    return {
        "order_id": order_id,
        "order_code": order.code,
        "material_costs": material_costs,
        "labor_costs": labor_costs,
        "summary": {
            "total_material_cost": float(total_material_cost),
            "total_labor_cost": float(total_labor_cost),
            "total_cost": float(total_cost),
            "quantity_ordered": order.quantity_ordered,
            "unit_cost": float(total_cost / order.quantity_ordered) if order.quantity_ordered else 0,
        }
    }


# =============================================================================
# Spool Management
# =============================================================================

def assign_spool_to_order(
    db: Session,
    order_id: int,
    spool_id: int,
    user_email: str,
) -> dict:
    """Assign a material spool to a production order."""
    get_production_order(db, order_id)  # Validate order exists

    spool = db.query(MaterialSpool).filter(MaterialSpool.id == spool_id).first()
    if not spool:
        raise HTTPException(status_code=404, detail="Spool not found")

    # Check if already assigned
    existing = db.query(ProductionOrderSpool).filter(
        ProductionOrderSpool.production_order_id == order_id,
        ProductionOrderSpool.spool_id == spool_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Spool already assigned to this order")

    assignment = ProductionOrderSpool(
        production_order_id=order_id,
        spool_id=spool_id,
        assigned_by=user_email,
    )
    db.add(assignment)

    return {
        "order_id": order_id,
        "spool_id": spool_id,
        "spool_code": spool.code,
        "assigned": True,
    }


def get_order_spools(db: Session, order_id: int) -> list[dict]:
    """Get spools assigned to a production order."""
    get_production_order(db, order_id)  # Validate order exists

    assignments = db.query(ProductionOrderSpool).filter(
        ProductionOrderSpool.production_order_id == order_id
    ).all()

    result = []
    for assignment in assignments:
        spool = db.query(MaterialSpool).filter(MaterialSpool.id == assignment.spool_id).first()
        if spool:
            product = db.query(Product).filter(Product.id == spool.product_id).first()
            result.append({
                "spool_id": spool.id,
                "spool_code": spool.code,
                "product_id": spool.product_id,
                "product_sku": product.sku if product else None,
                "product_name": product.name if product else None,
                "quantity_remaining": float(spool.quantity_remaining or 0),
                "assigned_at": assignment.created_at.isoformat() if assignment.created_at else None,
            })

    return result
