"""
Fulfillment Status Service - API-301

Calculates fulfillment status for sales orders.
"""
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.models.sales_order import SalesOrder
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.schemas.fulfillment_status import (
    FulfillmentStatus, FulfillmentStatusSummary, LineStatus, FulfillmentState
)


def get_fulfillment_status(db: Session, order_id: int) -> Optional[FulfillmentStatus]:
    """
    Calculate complete fulfillment status for a sales order.

    Logic:
    1. Load order with lines
    2. For each line, calculate allocated vs remaining
    3. Determine line-level readiness
    4. Aggregate to order-level status
    5. Check for incoming supply to estimate completion

    Args:
        db: Database session
        order_id: Sales order ID

    Returns:
        FulfillmentStatus if order found, None otherwise
    """
    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
    if not order:
        return None

    # Handle already-terminal states
    if order.status == "shipped":
        return _build_shipped_status(db, order)
    if order.status == "cancelled":
        return _build_cancelled_status(db, order)

    lines_status = []
    lines_ready = 0
    lines_blocked = 0

    for idx, line in enumerate(order.lines, start=1):
        # Get quantities from the line
        quantity_ordered = float(line.quantity or 0)
        allocated = float(line.allocated_quantity or 0)
        shipped = float(line.shipped_quantity or 0)
        remaining = quantity_ordered - shipped
        product_id, product_sku, product_name = _line_product_identity(line)

        if line.line_type == "service":
            allocated = remaining
            shortage = 0
            is_ready = True
        else:
            shortage = max(0, remaining - allocated)
            is_ready = allocated >= remaining

        if is_ready:
            lines_ready += 1
        else:
            lines_blocked += 1

        lines_status.append(LineStatus(
            line_id=line.id,
            line_number=idx,
            product_id=product_id,
            product_sku=product_sku,
            product_name=product_name,
            quantity_ordered=quantity_ordered,
            quantity_allocated=allocated,
            quantity_shipped=shipped,
            quantity_remaining=remaining,
            is_ready=is_ready,
            shortage=shortage,
            blocking_reason=f"Insufficient inventory (need {shortage:.1f} more)" if shortage > 0 else None
        ))

    lines_total = len(lines_status)

    # Determine state
    if lines_total == 0:
        # Order with no lines
        state = FulfillmentState.BLOCKED
    elif lines_ready == lines_total:
        state = FulfillmentState.READY_TO_SHIP
    elif lines_ready > 0:
        state = FulfillmentState.PARTIALLY_READY
    else:
        state = FulfillmentState.BLOCKED

    # Calculate fulfillment percent
    fulfillment_percent = (lines_ready / lines_total * 100) if lines_total > 0 else 0

    # Estimate completion date based on incoming POs
    estimated_date = _estimate_completion_date(db, order, lines_status)

    # Get order date
    order_date = order.created_at.date() if order.created_at else date.today()

    # Get customer name
    customer_name = order.customer_name
    if not customer_name and order.customer:
        customer_name = f"{order.customer.first_name or ''} {order.customer.last_name or ''}".strip()
    if not customer_name:
        customer_name = "Unknown"

    return FulfillmentStatus(
        order_id=order.id,
        order_number=order.order_number,
        customer_name=customer_name,
        order_date=order_date,
        requested_date=order.estimated_completion_date.date() if order.estimated_completion_date else None,
        summary=FulfillmentStatusSummary(
            state=state,
            lines_total=lines_total,
            lines_ready=lines_ready,
            lines_blocked=lines_blocked,
            fulfillment_percent=round(fulfillment_percent, 1),
            can_ship_partial=lines_ready > 0,
            can_ship_complete=lines_ready == lines_total and lines_total > 0,
            estimated_complete_date=estimated_date
        ),
        lines=lines_status
    )


def _estimate_completion_date(db: Session, order: SalesOrder, lines_status: list) -> Optional[date]:
    """
    Estimate when all lines could be fulfilled based on incoming POs.
    Returns None if no incoming supply found for blocked items.
    """
    blocked_product_ids = [
        line.product_id
        for line in lines_status
        if not line.is_ready and line.product_id is not None
    ]

    if not blocked_product_ids:
        return None  # All lines ready, no estimate needed

    # Find open PO lines for blocked products with expected dates
    latest_date = None

    po_lines = db.query(PurchaseOrderLine).join(PurchaseOrder).filter(
        PurchaseOrderLine.product_id.in_(blocked_product_ids),
        PurchaseOrder.status.in_(["draft", "submitted", "approved", "ordered", "partial"])
    ).all()

    for pol in po_lines:
        if pol.purchase_order and pol.purchase_order.expected_date:
            po_date = pol.purchase_order.expected_date
            if isinstance(po_date, date):
                if latest_date is None or po_date > latest_date:
                    latest_date = po_date

    return latest_date


def _build_shipped_status(db: Session, order: SalesOrder) -> FulfillmentStatus:
    """Build status for already-shipped order."""
    lines_status = []

    for idx, line in enumerate(order.lines, start=1):
        quantity_ordered = float(line.quantity or 0)
        shipped = float(line.shipped_quantity or 0)
        product_id, product_sku, product_name = _line_product_identity(line)

        lines_status.append(LineStatus(
            line_id=line.id,
            line_number=idx,
            product_id=product_id,
            product_sku=product_sku,
            product_name=product_name,
            quantity_ordered=quantity_ordered,
            quantity_allocated=quantity_ordered,  # Fully allocated since shipped
            quantity_shipped=shipped,
            quantity_remaining=0,  # All shipped
            is_ready=True,
            shortage=0,
            blocking_reason=None
        ))

    order_date = order.created_at.date() if order.created_at else date.today()
    customer_name = order.customer_name or (
        f"{order.customer.first_name or ''} {order.customer.last_name or ''}".strip()
        if order.customer else "Unknown"
    )

    return FulfillmentStatus(
        order_id=order.id,
        order_number=order.order_number,
        customer_name=customer_name,
        order_date=order_date,
        requested_date=None,
        summary=FulfillmentStatusSummary(
            state=FulfillmentState.SHIPPED,
            lines_total=len(lines_status),
            lines_ready=len(lines_status),
            lines_blocked=0,
            fulfillment_percent=100.0,
            can_ship_partial=False,  # Already shipped
            can_ship_complete=False,  # Already shipped
            estimated_complete_date=None
        ),
        lines=lines_status
    )


def _build_cancelled_status(db: Session, order: SalesOrder) -> FulfillmentStatus:
    """Build status for cancelled order."""
    lines_status = []

    for idx, line in enumerate(order.lines, start=1):
        quantity_ordered = float(line.quantity or 0)
        product_id, product_sku, product_name = _line_product_identity(line)

        lines_status.append(LineStatus(
            line_id=line.id,
            line_number=idx,
            product_id=product_id,
            product_sku=product_sku,
            product_name=product_name,
            quantity_ordered=quantity_ordered,
            quantity_allocated=0,
            quantity_shipped=0,
            quantity_remaining=0,
            is_ready=False,
            shortage=0,
            blocking_reason="Order cancelled"
        ))

    order_date = order.created_at.date() if order.created_at else date.today()
    customer_name = order.customer_name or (
        f"{order.customer.first_name or ''} {order.customer.last_name or ''}".strip()
        if order.customer else "Unknown"
    )

    return FulfillmentStatus(
        order_id=order.id,
        order_number=order.order_number,
        customer_name=customer_name,
        order_date=order_date,
        requested_date=None,
        summary=FulfillmentStatusSummary(
            state=FulfillmentState.CANCELLED,
            lines_total=len(lines_status),
            lines_ready=0,
            lines_blocked=0,
            fulfillment_percent=0.0,
            can_ship_partial=False,
            can_ship_complete=False,
            estimated_complete_date=None
        ),
        lines=lines_status
    )


def _line_product_identity(line) -> tuple[Optional[int], str, str]:
    """Return display identity for product, material, and service order lines."""
    if line.line_type == "service":
        return None, "SERVICE", line.description or "Service / Fee"

    if line.line_type == "material":
        material = line.material_inventory
        if material:
            return material.product_id, material.sku, material.display_name
        return None, "MATERIAL", line.description or "Material"

    product = line.product
    if product:
        return line.product_id, product.sku, product.name

    return line.product_id, "UNKNOWN", line.description or "Unknown Product"
