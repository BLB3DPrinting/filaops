"""
Sales Order Production Service — production order generation from sales
orders, PO code generation, and routing-copy helpers.

Moved verbatim from sales_order_service.py (DEBT-1 D1-A mechanical split).
"""
import math
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.logging_config import get_logger
from app.models.quote import Quote
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.models.manufacturing import Routing, RoutingOperation
from app.models.product import Product
from app.models.bom import BOM
from app.services.sales_order_shared import get_sales_order, record_order_event

logger = get_logger(__name__)


def generate_production_order_code(db: Session) -> str:
    """
    Generate next production order code (PO-2025-0001, etc.)
    Uses row-level locking to prevent race conditions.
    """
    year = datetime.now(timezone.utc).year
    last_po = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.code.like(f"PO-{year}-%"))
        .order_by(desc(ProductionOrder.code))
        .with_for_update(skip_locked=False)
        .first()
    )

    if last_po:
        last_num = int(last_po.code.split("-")[2])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"PO-{year}-{next_num:04d}"


# =============================================================================
# Production Order Helpers
# =============================================================================

def copy_routing_to_operations(
    db: Session,
    production_order: ProductionOrder,
    routing_id: int,
) -> list[ProductionOrderOperation]:
    """
    Copy routing operations AND their materials to production order operations.

    Creates the individual operation records that track progress through
    the manufacturing process (Print, Finishing, QC, Pack, etc.), along with
    the material requirements for each operation.
    """
    routing_ops = (
        db.query(RoutingOperation)
        .filter(RoutingOperation.routing_id == routing_id)
        .order_by(RoutingOperation.sequence)
        .all()
    )

    operations = []
    for rop in routing_ops:
        op = ProductionOrderOperation(
            production_order_id=production_order.id,
            routing_operation_id=rop.id,
            work_center_id=rop.work_center_id,
            resource_id=None,  # Resource assigned during scheduling
            sequence=rop.sequence,
            operation_code=rop.operation_code,
            operation_name=rop.operation_name,
            planned_setup_minutes=rop.setup_time_minutes or 0,
            planned_run_minutes=float(rop.run_time_minutes or 0) * float(production_order.quantity_ordered),
            status="pending",
        )
        db.add(op)
        db.flush()  # Get op.id for material records

        # Copy materials from routing operation to production order operation
        for rom in rop.materials:
            if rom.is_cost_only:
                continue  # Skip cost-only materials (no inventory consumption)

            # Use built-in method that handles quantity_per and scrap_factor
            qty_required = rom.calculate_required_quantity(int(production_order.quantity_ordered))

            # Round up for discrete units (can't ship 0.792 boxes)
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


def create_production_orders_for_sales_order(
    db: Session,
    order: SalesOrder,
    created_by: str,
) -> list[str]:
    """
    Create production orders for a sales order.

    Returns list of created production order codes.
    """
    created_orders = []
    year = datetime.now(timezone.utc).year

    def get_next_po_code():
        """
        Generate next PO code with row-level locking to prevent race conditions.
        """
        last_po = (
            db.query(ProductionOrder)
            .filter(ProductionOrder.code.like(f"PO-{year}-%"))
            .order_by(desc(ProductionOrder.code))
            .with_for_update(skip_locked=False)
            .first()
        )
        if last_po:
            last_num = int(last_po.code.split("-")[2])
            next_num = last_num + 1
        else:
            next_num = 1
        return f"PO-{year}-{next_num:04d}"

    if order.order_type == "line_item":
        lines = db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == order.id
        ).order_by(SalesOrderLine.id).all()

        for idx, line in enumerate(lines, start=1):
            product = db.query(Product).filter(Product.id == line.product_id).first()
            if not product:
                continue

            # Only create WO for products with BOMs (make items)
            if not product.has_bom:
                continue

            bom = db.query(BOM).filter(
                BOM.product_id == line.product_id,
                BOM.active.is_(True)
            ).first()

            routing = db.query(Routing).filter(
                Routing.product_id == line.product_id,
                Routing.is_active.is_(True)
            ).first()

            # Retry with savepoints to avoid rolling back the entire transaction
            max_retries = 3
            for attempt in range(max_retries):
                savepoint = db.begin_nested()
                try:
                    po_code = get_next_po_code()

                    production_order = ProductionOrder(
                        code=po_code,
                        product_id=line.product_id,
                        bom_id=bom.id if bom else None,
                        routing_id=routing.id if routing else None,
                        sales_order_id=order.id,
                        sales_order_line_id=line.id,
                        quantity_ordered=line.quantity,
                        quantity_completed=0,
                        quantity_scrapped=0,
                        source="sales_order",
                        status="draft",
                        priority=3,
                        notes=f"Auto-generated from {order.order_number} Line {idx}",
                        created_by=created_by,
                    )
                    db.add(production_order)
                    db.flush()

                    # Copy routing operations to production order
                    if routing:
                        copy_routing_to_operations(db, production_order, routing.id)

                    created_orders.append(po_code)
                    break
                except IntegrityError as e:
                    savepoint.rollback()
                    logger.warning(
                        f"PO code generation attempt {attempt + 1}/{max_retries} failed: {str(e)}"
                    )
                    if attempt >= max_retries - 1:
                        logger.error(
                            f"Failed to generate unique PO code after {max_retries} attempts for SO {order.order_number}",
                            exc_info=True
                        )
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to generate unique PO code after {max_retries} attempts"
                        )

    elif order.order_type == "quote_based" and order.product_id:
        product = db.query(Product).filter(Product.id == order.product_id).first()
        if product and product.has_bom:
            bom = db.query(BOM).filter(
                BOM.product_id == order.product_id,
                BOM.active.is_(True)
            ).first()

            routing = db.query(Routing).filter(
                Routing.product_id == order.product_id,
                Routing.is_active.is_(True)
            ).first()

            max_retries = 3
            for attempt in range(max_retries):
                savepoint = db.begin_nested()
                try:
                    po_code = get_next_po_code()

                    production_order = ProductionOrder(
                        code=po_code,
                        product_id=order.product_id,
                        bom_id=bom.id if bom else None,
                        routing_id=routing.id if routing else None,
                        sales_order_id=order.id,
                        quantity_ordered=order.quantity or 1,
                        quantity_completed=0,
                        quantity_scrapped=0,
                        source="sales_order",
                        status="draft",
                        priority=3,
                        notes=f"Auto-generated from {order.order_number}",
                        created_by=created_by,
                    )
                    db.add(production_order)
                    db.flush()

                    if routing:
                        copy_routing_to_operations(db, production_order, routing.id)

                    created_orders.append(po_code)
                    break
                except IntegrityError as e:
                    savepoint.rollback()
                    logger.warning(
                        f"PO code generation attempt {attempt + 1}/{max_retries} failed: {str(e)}"
                    )
                    if attempt >= max_retries - 1:
                        logger.error(
                            f"Failed to generate unique PO code after {max_retries} attempts for SO {order.order_number}",
                            exc_info=True
                        )
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to generate unique PO code after {max_retries} attempts"
                        )

    return created_orders


# =============================================================================
# Generate Production Orders
# =============================================================================

def billing_release_satisfied(db: Session, order: SalesOrder) -> bool:
    """Whether billing has been INITIATED enough to release production.

    Production may be released once billing is under way — either a payment
    recorded (prepay customers) or an invoice issued/sent (net-terms
    customers). It deliberately does NOT require full payment: many customers
    are billed net-30 and pay after the work ships.

    Mirrors ``isBillingReleaseSatisfied()`` in
    ``frontend/src/pages/admin/OrderDetail.jsx`` — keep the two in sync.
    """
    if order.payment_status == "paid":
        return True

    # Any completed payment on the order (covers partial prepay).
    from app.models.payment import Payment
    paid = db.query(func.coalesce(func.sum(Payment.amount), 0)).filter(
        Payment.sales_order_id == order.id,
        Payment.status == "completed",
    ).scalar()
    if paid and Decimal(str(paid)) > 0:
        return True

    # An issued invoice (sent / partially paid / paid) — the net-terms path.
    from app.models.invoice import Invoice
    issued = db.query(Invoice.id).filter(
        Invoice.sales_order_id == order.id,
        Invoice.status.in_(["sent", "partially_paid", "paid"]),
    ).first()
    return issued is not None


def generate_production_orders(
    db: Session,
    order_id: int,
    user_email: str,
) -> dict:
    """
    Generate production orders from a sales order.

    For line_item orders: Creates one production order per line item.
    For quote_based orders: Creates a single production order.

    Returns:
        Dict with created_orders and existing_orders lists
    """
    from app.services.inventory_service import reserve_production_materials

    order = get_sales_order(db, order_id)

    if order.status == "cancelled":
        raise HTTPException(
            status_code=400,
            detail="Cannot generate production orders for cancelled sales order"
        )

    # Check for existing production orders
    producible_line_ids: list[int] = []
    covered_line_ids: set[int] = set()
    if order.order_type == "line_item":
        producible_lines = [line for line in order.lines if line.product_id]
        producible_line_ids = [line.id for line in producible_lines]
        existing_pos = []
        if producible_line_ids:
            # Cancelled WOs are not coverage — an order whose WOs were all
            # cancelled must be able to regenerate them.
            existing_pos = db.query(ProductionOrder).filter(
                ProductionOrder.sales_order_id == order_id,
                ProductionOrder.status != "cancelled",
            ).all()
            existing_po_line_ids = {
                po.sales_order_line_id
                for po in existing_pos
                if po.sales_order_line_id is not None
            }
            # LEGACY-1 fallback: production orders created before line-level
            # linkage existed have sales_order_line_id = NULL. Treat such a
            # WO as covering every line with the same product_id — this is a
            # coverage check (does production exist for this line's product?),
            # not an assignment, so one NULL-linked WO may cover multiple
            # lines of its product. Mirrored in hasMainProductWO() in
            # frontend/src/pages/admin/OrderDetail.jsx — keep in sync.
            legacy_covered_product_ids = {
                po.product_id
                for po in existing_pos
                if po.sales_order_line_id is None
            }
            covered_line_ids = {
                line.id
                for line in producible_lines
                if line.id in existing_po_line_ids
                or line.product_id in legacy_covered_product_ids
            }
    else:
        existing_pos = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id == order_id,
            ProductionOrder.status != "cancelled",
        ).all()

    if existing_pos and (
        order.order_type != "line_item"
        or len(covered_line_ids) == len(producible_line_ids)
    ):
        return {
            "message": "Production orders already exist",
            "existing_orders": [po.code for po in existing_pos],
            "created_orders": []
        }

    if order.status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Work orders can only be generated while the order is in Confirmed status; "
                f"this order is {order.status.replace('_', ' ')}."
            )
        )

    if not billing_release_satisfied(db, order):
        raise HTTPException(
            status_code=400,
            detail=(
                "Billing must be initiated before production release: record a "
                "payment or issue (send) an invoice for this order."
            ),
        )

    created_orders = []
    year = datetime.now(timezone.utc).year

    def get_next_po_code():
        last_po = (
            db.query(ProductionOrder)
            .filter(ProductionOrder.code.like(f"PO-{year}-%"))
            .order_by(desc(ProductionOrder.code))
            .with_for_update()
            .first()
        )
        if last_po:
            last_num = int(last_po.code.split("-")[2])
            next_num = last_num + 1
        else:
            next_num = 1
        return f"PO-{year}-{next_num:04d}"

    if order.order_type == "line_item":
        lines = db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == order_id
        ).order_by(SalesOrderLine.id).all()

        if not lines:
            raise HTTPException(
                status_code=400,
                detail="Sales order has no line items"
            )

        for idx, line in enumerate(lines, start=1):
            # covered_line_ids includes both directly-linked lines and lines
            # covered by legacy NULL-linked WOs (see coverage check above).
            if line.id in covered_line_ids:
                continue

            # Skip material-only lines — raw materials don't need production orders
            if not line.product_id:
                continue

            product = db.query(Product).filter(Product.id == line.product_id).first()
            if not product:
                raise HTTPException(
                    status_code=400,
                    detail=f"Product ID {line.product_id} not found for line {idx}"
                )

            bom = db.query(BOM).filter(
                BOM.product_id == line.product_id,
                BOM.active.is_(True)
            ).first()

            routing = db.query(Routing).filter(
                Routing.product_id == line.product_id,
                Routing.is_active.is_(True)
            ).first()

            po_code = get_next_po_code()

            production_order = ProductionOrder(
                code=po_code,
                product_id=line.product_id,
                bom_id=bom.id if bom else None,
                routing_id=routing.id if routing else None,
                sales_order_id=order.id,
                sales_order_line_id=line.id,
                quantity_ordered=line.quantity,
                quantity_completed=0,
                quantity_scrapped=0,
                source="sales_order",
                status="draft",
                priority=3,
                notes=f"Generated from {order.order_number} Line {idx}",
                created_by=user_email,
            )

            db.add(production_order)
            db.flush()

            if routing:
                copy_routing_to_operations(db, production_order, routing.id)

            reserve_production_materials(
                db=db,
                production_order=production_order,
                created_by=user_email,
            )

            created_orders.append(po_code)

    else:
        # quote_based order
        if order.quote_id:
            quote = db.query(Quote).filter(Quote.id == order.quote_id).first()
            if quote and quote.product_id:
                product_id = quote.product_id

                bom = db.query(BOM).filter(
                    BOM.product_id == product_id,
                    BOM.active.is_(True)
                ).first()

                routing = db.query(Routing).filter(
                    Routing.product_id == product_id,
                    Routing.is_active.is_(True)
                ).first()

                po_code = get_next_po_code()

                production_order = ProductionOrder(
                    code=po_code,
                    product_id=product_id,
                    bom_id=bom.id if bom else None,
                    routing_id=routing.id if routing else None,
                    sales_order_id=order.id,
                    quantity_ordered=order.quantity,
                    quantity_completed=0,
                    quantity_scrapped=0,
                    source="sales_order",
                    status="draft",
                    priority=3,
                    notes=f"Generated from {order.order_number}",
                    created_by=user_email,
                )

                db.add(production_order)
                db.flush()

                if routing:
                    copy_routing_to_operations(db, production_order, routing.id)

                reserve_production_materials(
                    db=db,
                    production_order=production_order,
                    created_by=user_email,
                )

                created_orders.append(po_code)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Quote-based order has no product. Please accept the quote first."
                )
        else:
            raise HTTPException(
                status_code=400,
                detail="Quote-based order has no associated quote"
            )

    # Record event
    if created_orders:
        record_order_event(
            db=db,
            order_id=order_id,
            event_type="production_started",
            title=f"Created {len(created_orders)} work order(s)",
            description=f"Work orders: {', '.join(created_orders)}",
            user_id=None,
        )

        # Update order status — only move to in_production when work orders exist
        if order.status == "confirmed":
            order.status = "in_production"
    elif order.order_type == "line_item":
        # All lines are material-only — no production needed (pick and ship)
        if order.status == "confirmed":
            logger.info("No production orders created for material-only sales order %s", order.id)

    return {
        "message": f"Created {len(created_orders)} production order(s)",
        "created_orders": created_orders,
        "existing_orders": [po.code for po in existing_pos]
    }
