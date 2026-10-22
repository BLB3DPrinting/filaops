"""
Service layer for item demand calculations.

Provides functions to calculate:
- On-hand quantity from inventory
- Allocations from active production orders
- Incoming supply from open purchase orders
- Shortage detection
"""
from datetime import date
from decimal import Decimal
from typing import Optional, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.bom import BOM, BOMLine
from app.models.production_order import ProductionOrder
from app.models.sales_order import SalesOrder
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.inventory import Inventory
from app.schemas.item_demand import (
    ItemDemandSummary, QuantitySummary, AllocationDetail,
    IncomingDetail, ShortageInfo, LinkedSalesOrder
)
from app.services import open_supply


def get_item_on_hand(db: Session, product_id: int) -> Decimal:
    """
    Get total on-hand quantity for a product across all locations.

    Uses the Inventory table which tracks current stock levels.
    """
    result = db.query(
        func.coalesce(func.sum(Inventory.on_hand_quantity), 0)
    ).filter(
        Inventory.product_id == product_id
    ).scalar()

    return Decimal(str(result or 0))


def get_allocated_quantity(db: Session, product_id: int) -> Decimal:
    """
    Get total allocated quantity for a product from active production orders.

    Calculates allocation based on active work orders that consume this
    product as a BOM component. This is the accurate allocation vs the
    Inventory.allocated_quantity column which may be stale.
    """
    # Find all BOMs that use this product as a component
    bom_lines_using_product = db.query(
        BOMLine.bom_id,
        BOMLine.quantity
    ).filter(
        BOMLine.component_id == product_id
    ).subquery()

    # Get the parent products from those BOMs
    boms_using_product = db.query(
        BOM.product_id,
        bom_lines_using_product.c.quantity
    ).join(
        bom_lines_using_product,
        BOM.id == bom_lines_using_product.c.bom_id
    ).filter(
        BOM.active == True  # noqa: E712
    ).subquery()

    # Active production order statuses
    active_statuses = ['draft', 'released', 'scheduled', 'in_progress']

    # Sum up allocation from all active production orders
    result = db.query(
        func.coalesce(
            func.sum(
                (ProductionOrder.quantity_ordered -
                 func.coalesce(ProductionOrder.quantity_completed, 0) -
                 func.coalesce(ProductionOrder.quantity_scrapped, 0)) *
                boms_using_product.c.quantity
            ),
            0
        )
    ).select_from(ProductionOrder).join(
        boms_using_product,
        ProductionOrder.product_id == boms_using_product.c.product_id
    ).filter(
        ProductionOrder.status.in_(active_statuses)
    ).scalar()

    return Decimal(str(result or 0))


def get_production_order_allocations(db: Session, product_id: int) -> List[AllocationDetail]:
    """
    Get all active production orders that consume this product.

    Finds products that use this item in their BOM, then finds
    production orders for those products that are in active status.

    Active statuses: draft, released, scheduled, in_progress
    """
    # Find all BOMs that use this product as a component
    bom_lines_using_product = db.query(
        BOMLine.bom_id,
        BOMLine.quantity
    ).filter(
        BOMLine.component_id == product_id
    ).subquery()

    # Get the parent products from those BOMs
    boms_using_product = db.query(
        BOM.product_id,
        bom_lines_using_product.c.quantity
    ).join(
        bom_lines_using_product,
        BOM.id == bom_lines_using_product.c.bom_id
    ).filter(
        BOM.active == True  # noqa: E712
    ).subquery()

    # Active production order statuses (not complete, closed, or cancelled)
    active_statuses = ['draft', 'released', 'scheduled', 'in_progress']

    # Find production orders for products that use this component
    query = db.query(
        ProductionOrder,
        boms_using_product.c.quantity.label('qty_per_unit')
    ).join(
        boms_using_product,
        ProductionOrder.product_id == boms_using_product.c.product_id
    ).filter(
        ProductionOrder.status.in_(active_statuses)
    ).order_by(
        ProductionOrder.due_date.asc().nullslast()
    )

    results = query.all()

    allocations = []
    for production_order, qty_per_unit in results:
        # Calculate quantity needed: (ordered - completed - scrapped) * qty_per_unit
        remaining = (
            (production_order.quantity_ordered or Decimal("0")) -
            (production_order.quantity_completed or Decimal("0")) -
            (production_order.quantity_scrapped or Decimal("0"))
        )
        allocated_qty = remaining * Decimal(str(qty_per_unit))

        if allocated_qty <= 0:
            continue  # Skip if no allocation needed

        # Get linked sales order if any
        linked_so = None
        if production_order.sales_order_id:
            so = db.query(SalesOrder).filter(
                SalesOrder.id == production_order.sales_order_id
            ).first()
            if so:
                linked_so = LinkedSalesOrder(
                    id=so.id,
                    code=so.order_number,
                    customer=so.customer_name or "Unknown"
                )

        allocations.append(AllocationDetail(
            type="production_order",
            reference_code=production_order.code,
            reference_id=production_order.id,
            quantity=allocated_qty,
            needed_date=production_order.due_date,
            status=production_order.status,
            linked_sales_order=linked_so
        ))

    return allocations


def get_incoming_supply(db: Session, product_id: int) -> List[IncomingDetail]:
    """
    Get all open purchase order lines for this product.

    Open PO statuses: draft, ordered, shipped (not received, closed, cancelled)

    Behind MRP_OPEN_PO_SUPPLY, open production orders for the product are
    listed too (type "production_order"), earliest expected date first.
    """
    # Active purchase order statuses
    active_statuses = ['draft', 'ordered', 'shipped']

    # Query purchase order lines for this product
    query = db.query(
        PurchaseOrderLine,
        PurchaseOrder,
    ).join(
        PurchaseOrder,
        PurchaseOrderLine.purchase_order_id == PurchaseOrder.id
    ).filter(
        PurchaseOrderLine.product_id == product_id,
        PurchaseOrder.status.in_(active_statuses)
    ).order_by(
        PurchaseOrder.expected_date.asc().nullslast()
    )

    results = query.all()

    incoming = []
    for pol, po in results:
        # Calculate remaining to receive
        ordered = pol.quantity_ordered or Decimal("0")
        received = pol.quantity_received or Decimal("0")
        remaining = ordered - received

        if remaining <= 0:
            continue  # Fully received

        # Get vendor name
        vendor_name = None
        if po.vendor:
            vendor_name = po.vendor.name

        incoming.append(IncomingDetail(
            type="purchase_order",
            reference_code=po.po_number,
            reference_id=po.id,
            quantity=remaining,
            expected_date=po.expected_date,
            status=po.status,
            vendor=vendor_name
        ))

    production = open_supply.get_open_production_supply(db, [product_id]).get(product_id, [])
    if production:
        for supply in production:
            incoming.append(IncomingDetail(
                type="production_order",
                reference_code=supply.code,
                reference_id=supply.production_order_id,
                quantity=supply.quantity,
                expected_date=supply.expected_date,
                status=supply.status,
                vendor=None
            ))
        # Same ordering as the query above: earliest first, undated last
        incoming.sort(key=lambda i: (i.expected_date is None, i.expected_date or date.max))

    return incoming


def calculate_shortage(
    available: Decimal,
    allocations: List[AllocationDetail]
) -> ShortageInfo:
    """
    Determine if there's a shortage and which orders are affected.

    A shortage exists when available < 0 (allocated > on_hand).
    """
    if available >= 0:
        return ShortageInfo(
            is_short=False,
            quantity=Decimal("0"),
            blocking_orders=[]
        )

    # There's a shortage
    shortage_amount = abs(available)

    # Find which orders are blocked (simplified: all orders if there's a shortage)
    # More sophisticated: could calculate which specific orders can't be fulfilled
    # based on priority/date order
    blocking = []

    # Sort allocations by priority (date, then status)
    sorted_allocs = sorted(
        allocations,
        key=lambda a: (a.needed_date or date.max, a.status != 'released')
    )

    # Walk through allocations to determine which are blocked
    running_total = Decimal("0")
    on_hand = available + sum(a.quantity for a in allocations)  # Calculate original on_hand

    for alloc in sorted_allocs:
        running_total += alloc.quantity
        if running_total > on_hand:
            blocking.append(alloc.reference_code)

    return ShortageInfo(
        is_short=True,
        quantity=shortage_amount,
        blocking_orders=blocking
    )


def get_item_demand_summary(db: Session, item_id: int) -> Optional[ItemDemandSummary]:
    """
    Get complete demand summary for a product.

    Returns None if product doesn't exist.

    The summary includes:
    - Current on-hand quantity
    - Allocated quantity (from active production orders)
    - Available quantity (on_hand - allocated)
    - Incoming quantity (from open purchase orders)
    - Projected quantity (available + incoming)
    - List of allocations with linked sales orders
    - List of incoming supply
    - Shortage information if applicable
    """
    # Get the product
    product = db.query(Product).filter(Product.id == item_id).first()
    if not product:
        return None

    # Calculate quantities
    on_hand = get_item_on_hand(db, item_id)
    allocations = get_production_order_allocations(db, item_id)
    incoming_list = get_incoming_supply(db, item_id)

    allocated = sum(a.quantity for a in allocations)
    incoming = sum(i.quantity for i in incoming_list)
    available = on_hand - allocated
    projected = available + incoming

    shortage = calculate_shortage(available, allocations)

    return ItemDemandSummary(
        item_id=product.id,
        sku=product.sku,
        name=product.name,
        stocking_policy=product.stocking_policy or "on_demand",
        reorder_point=product.reorder_point,
        quantities=QuantitySummary(
            on_hand=on_hand,
            allocated=allocated,
            available=available,
            incoming=incoming,
            projected=projected
        ),
        allocations=allocations,
        incoming=incoming_list,
        shortage=shortage
    )
