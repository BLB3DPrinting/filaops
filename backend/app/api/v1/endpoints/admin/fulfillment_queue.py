# pyright: reportArgumentType=false
# pyright: reportAssignmentType=false
"""
Admin Fulfillment Queue Endpoints

Handles production queue management:
1. Production Queue Management
2. Print Job Assignment & Tracking
3. Quality Check
4. Bulk Status Updates

Split from fulfillment.py — shipping endpoints are in fulfillment_shipping.py.
"""
import logging
from datetime import datetime, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc, func, or_
from pydantic import BaseModel

from app.db.session import get_db
from app.models.user import User
from app.models.quote import Quote
from app.models.sales_order import SalesOrder
from app.models.production_order import ProductionOrder
from app.models.print_job import PrintJob
from app.models.product import Product
from app.models.bom import BOM
from app.models.printer import Printer
from app.models.inventory import Inventory, InventoryTransaction, InventoryLocation
# MaterialInventory removed - using unified Inventory table (Phase 1.4)
from app.services.transaction_service import TransactionService, MaterialConsumption
from app.api.v1.deps import get_current_staff_user
from app.core.settings import settings

router = APIRouter(prefix="/fulfillment", tags=["Admin - Fulfillment Queue"])


def get_default_location(db: Session) -> InventoryLocation:
    """Get or create the default inventory location (MAIN warehouse)."""
    location = db.query(InventoryLocation).filter(
        InventoryLocation.code == 'MAIN'
    ).first()

    if not location:
        # Try to get any active location
        location = db.query(InventoryLocation).filter(
            InventoryLocation.active.is_(True)
        ).first()

    if not location:
        # Create default location if none exists
        location = InventoryLocation(
            code="MAIN",
            name="Main Warehouse",
            type="warehouse",
            active=True
        )
        db.add(location)
        db.flush()

    return location


# ============================================================================
# SCHEMAS
# ============================================================================

class ProductionQueueItem(BaseModel):
    """A single item in the production queue"""
    id: int
    code: str
    order_number: Optional[str] = None
    quote_number: Optional[str] = None
    product_name: Optional[str] = None
    product_sku: Optional[str] = None
    material: Optional[str] = None
    color: Optional[str] = None
    quantity: int
    status: str
    priority: Optional[str] = None
    estimated_time_minutes: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    customer_name: Optional[str] = None
    has_shipping_address: bool = False
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None


class ProductionQueueResponse(BaseModel):
    """Production queue with stats"""
    items: List[ProductionQueueItem]
    stats: dict
    total: int


class FulfillmentStatsResponse(BaseModel):
    """Stats for the fulfillment dashboard"""
    # Quote stats
    pending_quotes: int
    quotes_needing_review: int

    # Production stats
    scheduled: int
    in_progress: int
    ready_for_qc: int

    # Shipping stats
    ready_to_ship: int
    shipped_today: int

    # Revenue
    pending_revenue: float
    shipped_revenue_today: float


class StartProductionRequest(BaseModel):
    """Request to start production on an order"""
    printer_id: Optional[str] = None  # Printer code like "leonardo" or "donatello"
    notes: Optional[str] = None


class CompleteProductionRequest(BaseModel):
    """Request to complete production with good/bad quantity tracking"""
    actual_time_minutes: Optional[int] = None
    actual_material_grams: Optional[float] = None
    qty_good: Optional[int] = None  # Good sellable parts produced
    qty_bad: Optional[int] = None   # Scrapped parts (adhesion loss, defects, etc.)
    qc_notes: Optional[str] = None


class BulkStatusUpdate(BaseModel):
    """Request to update multiple orders"""
    production_order_ids: List[int]
    new_status: str
    notes: Optional[str] = None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def build_production_queue_item(po: ProductionOrder, db: Session) -> dict:
    """Build a queue item from a production order with all related data"""

    # Get related sales order if exists
    # FIXED: Use direct link first, fallback to quote lookup for legacy POs
    sales_order = None
    quote = None
    customer = None

    if po.sales_order_id:
        # Direct link (preferred)
        sales_order = db.query(SalesOrder).filter(SalesOrder.id == po.sales_order_id).first()
        if sales_order and sales_order.quote_id:
            quote = db.query(Quote).filter(Quote.id == sales_order.quote_id).first()
            if quote and quote.user_id:
                customer = db.query(User).filter(User.id == quote.user_id).first()
    elif po.product_id:
        # Fallback for legacy production orders without direct link
        quote = db.query(Quote).filter(Quote.product_id == po.product_id).first()
        if quote:
            sales_order = db.query(SalesOrder).filter(SalesOrder.quote_id == quote.id).first()
            if quote.user_id:
                customer = db.query(User).filter(User.id == quote.user_id).first()

    # Get product details
    product = db.query(Product).filter(Product.id == po.product_id).first() if po.product_id else None

    return {
        "id": po.id,
        "code": po.code,
        "order_number": sales_order.order_number if sales_order else None,
        "quote_number": quote.quote_number if quote else None,
        "product_name": product.name if product else po.notes,
        "product_sku": product.sku if product else None,
        "material": quote.material_type if quote else None,
        "color": quote.color if quote else None,
        "quantity": int(po.quantity),
        "status": po.status,
        "priority": str(po.priority) if po.priority is not None else None,
        "estimated_time_minutes": po.estimated_time_minutes,
        "created_at": po.created_at,
        "started_at": po.actual_start,
        "customer_name": customer.full_name if customer else None,
        "has_shipping_address": bool(quote and quote.shipping_address_line1) if quote else False,
        "shipping_city": quote.shipping_city if quote else None,
        "shipping_state": quote.shipping_state if quote else None,
    }


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/stats", response_model=FulfillmentStatsResponse)
async def get_fulfillment_stats(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Get fulfillment dashboard statistics.

    Returns counts for each stage of the fulfillment process.
    """
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Quote stats
    pending_quotes = db.query(Quote).filter(Quote.status == "pending").count()
    quotes_needing_review = db.query(Quote).filter(Quote.status == "pending_review").count()

    # Production stats
    scheduled = db.query(ProductionOrder).filter(
        ProductionOrder.status.in_(["scheduled", "confirmed", "released"])
    ).count()

    in_progress = db.query(ProductionOrder).filter(
        ProductionOrder.status == "in_progress"
    ).count()

    ready_for_qc = db.query(ProductionOrder).filter(
        ProductionOrder.status == "printed"  # Waiting for QC
    ).count()

    # Shipping stats - orders where production is complete
    ready_to_ship = db.query(SalesOrder).filter(
        or_(
            SalesOrder.status == "ready_to_ship",
            SalesOrder.status == "quality_check"
        )
    ).count()

    shipped_today = db.query(SalesOrder).filter(
        SalesOrder.status == "shipped",
        SalesOrder.shipped_at >= today_start
    ).count()

    # Revenue calculations
    pending_revenue_result = db.query(func.sum(SalesOrder.grand_total)).filter(
        SalesOrder.status.in_(["pending", "confirmed", "in_production"])
    ).scalar()
    pending_revenue = float(pending_revenue_result) if pending_revenue_result else 0.0

    shipped_revenue_result = db.query(func.sum(SalesOrder.grand_total)).filter(
        SalesOrder.status == "shipped",
        SalesOrder.shipped_at >= today_start
    ).scalar()
    shipped_revenue_today = float(shipped_revenue_result) if shipped_revenue_result else 0.0

    return FulfillmentStatsResponse(
        pending_quotes=pending_quotes,
        quotes_needing_review=quotes_needing_review,
        scheduled=scheduled,
        in_progress=in_progress,
        ready_for_qc=ready_for_qc,
        ready_to_ship=ready_to_ship,
        shipped_today=shipped_today,
        pending_revenue=pending_revenue,
        shipped_revenue_today=shipped_revenue_today,
    )


@router.get("/queue", response_model=ProductionQueueResponse)
async def get_production_queue(
    status_filter: Optional[str] = None,
    priority_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Get the production queue with all orders that need to be fulfilled.

    Filter options:
    - status: scheduled, in_progress, printed, completed, cancelled
    - priority: low, normal, high, urgent

    Returns items sorted by priority (urgent first) then by creation date.
    """
    query = db.query(ProductionOrder)

    # Apply filters
    if status_filter:
        if status_filter == "active":
            # Show all non-complete, non-cancelled
            query = query.filter(
                ~ProductionOrder.status.in_(["complete", "cancelled"])
            )
        else:
            query = query.filter(ProductionOrder.status == status_filter)
    else:
        # Default: show active orders
        query = query.filter(
            ~ProductionOrder.status.in_(["complete", "cancelled"])
        )

    if priority_filter:
        query = query.filter(ProductionOrder.priority == priority_filter)

    # Get total count
    total = query.count()

    # Sort: by priority (1=highest/urgent, 5=lowest), then by created_at
    # Priority is stored as integer: 1=urgent, 2=high, 3=normal, 4=low, 5=lowest
    production_orders = (
        query
        .order_by(ProductionOrder.priority, desc(ProductionOrder.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Build queue items with related data
    items = [build_production_queue_item(po, db) for po in production_orders]

    # Calculate stats
    stats = {
        "total_active": total,
        "scheduled": db.query(ProductionOrder).filter(ProductionOrder.status.in_(["scheduled", "confirmed"])).count(),
        "in_progress": db.query(ProductionOrder).filter(ProductionOrder.status == "in_progress").count(),
        "printed": db.query(ProductionOrder).filter(ProductionOrder.status == "printed").count(),
        "urgent_count": db.query(ProductionOrder).filter(
            ProductionOrder.priority == 1,  # 1 = urgent (highest priority)
            ~ProductionOrder.status.in_(["complete", "cancelled"])
        ).count(),
    }

    return ProductionQueueResponse(
        items=items,
        stats=stats,
        total=total,
    )


@router.get("/queue/{production_order_id}")
async def get_production_order_details(
    production_order_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Get detailed information about a specific production order.

    Includes related quote, sales order, product, BOM, and customer info.
    """
    po = db.query(ProductionOrder).filter(ProductionOrder.id == production_order_id).first()

    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    # Build the basic queue item
    item = build_production_queue_item(po, db)

    # Get additional details
    product = db.query(Product).filter(Product.id == po.product_id).first() if po.product_id else None
    bom = db.query(BOM).filter(BOM.product_id == po.product_id, BOM.active.is_(True)).first() if po.product_id else None  # noqa: E712

    # Get quote and sales order details
    # FIXED: Use direct link first, fallback to quote lookup for legacy POs
    quote = None
    sales_order = None
    if po.sales_order_id:
        # Direct link (preferred)
        sales_order = db.query(SalesOrder).filter(SalesOrder.id == po.sales_order_id).first()
        if sales_order and sales_order.quote_id:
            quote = db.query(Quote).filter(Quote.id == sales_order.quote_id).first()
    elif po.product_id:
        # Fallback for legacy production orders without direct link
        quote = db.query(Quote).filter(Quote.product_id == po.product_id).first()
        if quote:
            sales_order = db.query(SalesOrder).filter(SalesOrder.quote_id == quote.id).first()

    # Get print jobs
    print_jobs = db.query(PrintJob).filter(PrintJob.production_order_id == po.id).all()

    return {
        **item,
        "product": {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
            "type": product.type,
        } if product else None,
        "bom": {
            "id": bom.id,
            "code": bom.code,
            "total_cost": float(bom.total_cost) if bom.total_cost else None,
            "line_count": len(bom.lines) if bom.lines else 0,
        } if bom else None,
        "quote": {
            "id": quote.id,
            "quote_number": quote.quote_number,
            "material_type": quote.material_type,
            "color": quote.color,
            "material_grams": float(quote.material_grams) if quote.material_grams else None,
            "print_time_hours": float(quote.print_time_hours) if quote.print_time_hours else None,
            "total_price": float(quote.total_price) if quote.total_price else None,
            "dimensions": {
                "x": float(quote.dimensions_x) if quote.dimensions_x else None,
                "y": float(quote.dimensions_y) if quote.dimensions_y else None,
                "z": float(quote.dimensions_z) if quote.dimensions_z else None,
            },
            "shipping_address": {
                "name": quote.shipping_name,
                "line1": quote.shipping_address_line1,
                "line2": quote.shipping_address_line2,
                "city": quote.shipping_city,
                "state": quote.shipping_state,
                "zip": quote.shipping_zip,
                "country": quote.shipping_country,
            } if quote.shipping_address_line1 else None,
        } if quote else None,
        "sales_order": {
            "id": sales_order.id,
            "order_number": sales_order.order_number,
            "status": sales_order.status,
            "payment_status": sales_order.payment_status,
            "grand_total": float(sales_order.grand_total) if sales_order.grand_total else None,
            "tracking_number": sales_order.tracking_number,
            "carrier": sales_order.carrier,
        } if sales_order else None,
        "print_jobs": [
            {
                "id": pj.id,
                "status": pj.status,
                "printer_id": pj.printer_id,
                "queued_at": pj.queued_at.isoformat() if pj.queued_at else None,
                "started_at": pj.started_at.isoformat() if pj.started_at else None,
                "completed_at": pj.finished_at.isoformat() if pj.finished_at else None,
            }
            for pj in print_jobs
        ],
        "notes": po.notes,
        "actual_time_minutes": po.actual_time_minutes,
        "actual_cost": None,  # Not yet tracked on ProductionOrder model
    }


@router.post("/queue/{production_order_id}/start")
async def start_production(
    production_order_id: int,
    request: StartProductionRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Start production on an order.

    Changes status to 'in_progress' and records start time.
    Optionally assigns to a specific printer.
    """
    po = db.query(ProductionOrder).filter(ProductionOrder.id == production_order_id).first()

    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    if po.status not in ["scheduled", "confirmed", "released", "pending", "draft"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start production for order with status '{po.status}'"
        )

    # Update production order
    po.status = "in_progress"
    po.start_date = datetime.now(timezone.utc)

    if request.notes:
        po.notes = (po.notes + "\n" if po.notes else "") + f"[{datetime.now(timezone.utc).isoformat()}] Started: {request.notes}"

    # Create or update print job
    print_job = db.query(PrintJob).filter(PrintJob.production_order_id == po.id).first()

    if not print_job:
        print_job = PrintJob(
            production_order_id=po.id,
            status="printing",
            priority=po.priority or "normal",
            started_at=datetime.now(timezone.utc),
        )
        db.add(print_job)
    else:
        print_job.status = "printing"
        print_job.started_at = datetime.now(timezone.utc)

    # Look up printer by code if provided
    printer = None
    if request.printer_id:
        printer = db.query(Printer).filter(Printer.code == request.printer_id).first()
        if printer:
            print_job.printer_id = printer.id
        else:
            # Try as integer ID fallback
            try:
                print_job.printer_id = int(request.printer_id)
            except ValueError:
                pass  # Invalid printer code, continue without assignment

    # =========================================================================
    # BOM EXPLOSION AND MATERIAL RESERVATION
    # =========================================================================
    reserved_materials = []
    insufficient_materials = []
    synced_materials = []  # Track what we synced

    # Get BOM for this product (use po.bom_id if set, otherwise find active BOM)
    bom = None
    if po.bom_id:
        bom = db.query(BOM).filter(BOM.id == po.bom_id).first()
    elif po.product_id:
        bom = db.query(BOM).filter(
            BOM.product_id == po.product_id,
            BOM.active.is_(True)
        ).first()

    if bom and bom.lines:
        production_qty = float(po.quantity)

        # =====================================================================
        # PHASE 1.4: Ensure Inventory records exist for all BOM components
        #
        # After MaterialInventory migration, Inventory is the source of truth.
        # Ensure Inventory records exist for all materials before reserving.
        # =====================================================================
        for line in bom.lines:
            component = line.component
            if component:
                # Find or create Inventory record (for all components, not just materials)
                inv = db.query(Inventory).filter(
                    Inventory.product_id == component.id
                ).first()

                if not inv:
                    # Get default location
                    from app.models.inventory import InventoryLocation
                    location = db.query(InventoryLocation).filter(
                        InventoryLocation.code == 'MAIN'
                    ).first()

                    if not location:
                        # Create default location if it doesn't exist
                        location = InventoryLocation(
                            name="Main Warehouse",
                            code="MAIN",
                            type="warehouse"
                        )
                        db.add(location)
                        db.flush()

                    # Create Inventory record with zero quantity
                    inv = Inventory(
                        product_id=component.id,
                        location_id=location.id,
                        on_hand_quantity=Decimal("0"),
                        allocated_quantity=Decimal("0"),
                    )
                    db.add(inv)
                    synced_materials.append({
                        "sku": component.sku,
                        "action": "created",
                        "quantity": 0.0,
                    })

        # Flush to ensure Inventory records are available for reservation
        db.flush()

        # Now do the actual BOM explosion and reservation
        for line in bom.lines:
            component = line.component
            component_name = component.name if component else f"Component #{line.component_id}"
            component_sku = component.sku if component else "N/A"

            # Skip non-inventory cost items - they're for job costing, not physical inventory
            # SVC-* = legacy services, MFG-* = manufacturing overhead (machine time)
            if component_sku.startswith(("SVC-", "MFG-")):
                continue

            # Calculate required quantity (BOM line qty * production order qty)
            required_qty = float(line.quantity) * production_qty

            # Apply scrap factor if any
            if line.scrap_factor:
                required_qty *= (1 + float(line.scrap_factor) / 100)

            # Find inventory for this component (any location for now)
            inventory = db.query(Inventory).filter(
                Inventory.product_id == line.component_id
            ).first()

            if inventory and float(inventory.available_quantity) >= required_qty:
                # Reserve the material - only update allocated_quantity
                # available_quantity is a computed column (on_hand - allocated)
                new_allocated = float(inventory.allocated_quantity) + required_qty
                inventory.allocated_quantity = Decimal(str(new_allocated))
                # Calculate what available will be after this update
                new_available = float(inventory.on_hand_quantity) - new_allocated

                # Create reservation transaction with cost for accounting
                from app.services.inventory_service import get_effective_cost_per_inventory_unit
                unit_cost = get_effective_cost_per_inventory_unit(component)
                total_cost = Decimal(str(required_qty)) * unit_cost if unit_cost else None
                transaction = InventoryTransaction(
                    product_id=line.component_id,
                    location_id=inventory.location_id,
                    transaction_type="reservation",
                    reference_type="production_order",
                    reference_id=po.id,
                    quantity=Decimal(str(-required_qty)),  # Negative = reserved/out
                    cost_per_unit=unit_cost,
                    total_cost=total_cost,
                    unit=component.unit or "EA",
                    notes=f"Reserved for {po.code}: {required_qty:.2f} units of {component_sku}",
                    created_by="system",
                )
                db.add(transaction)

                reserved_materials.append({
                    "component_id": line.component_id,
                    "component_sku": component_sku,
                    "component_name": component_name,
                    "quantity_reserved": round(required_qty, 4),
                    "inventory_remaining": round(new_available, 4),
                })
            else:
                # Insufficient inventory - log but continue (warn, don't block)
                available = float(inventory.available_quantity) if inventory else 0
                insufficient_materials.append({
                    "component_id": line.component_id,
                    "component_sku": component_sku,
                    "component_name": component_name,
                    "quantity_required": round(required_qty, 4),
                    "quantity_available": round(available, 4),
                    "shortage": round(required_qty - available, 4),
                })

    # Update related sales order if exists
    # FIXED: Use direct link first, fallback to quote lookup for legacy POs
    sales_order = None
    if po.sales_order_id:
        # Direct link (preferred)
        sales_order = db.query(SalesOrder).filter(SalesOrder.id == po.sales_order_id).first()
    elif po.product_id:
        # Fallback for legacy production orders without direct link
        quote = db.query(Quote).filter(Quote.product_id == po.product_id).first()
        if quote:
            sales_order = db.query(SalesOrder).filter(SalesOrder.quote_id == quote.id).first()

    if sales_order and sales_order.status == "confirmed":
        sales_order.status = "in_production"

    db.commit()

    return {
        "success": True,
        "production_order_id": po.id,
        "status": po.status,
        "started_at": po.start_date.isoformat(),
        "printer": {
            "id": printer.id,
            "code": printer.code,
            "name": printer.name,
        } if printer else None,
        "bom_id": bom.id if bom else None,
        "materials_synced": synced_materials,  # BUG FIX #5: Show what was synced
        "materials_reserved": reserved_materials,
        "materials_insufficient": insufficient_materials,
        "message": f"Production started for {po.code}" + (f" on {printer.name}" if printer else ""),
    }


@router.post("/queue/{production_order_id}/complete-print")
async def complete_print(
    production_order_id: int,
    request: CompleteProductionRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Mark printing as complete with good/bad quantity tracking.

    - qty_good: Sellable parts → added to finished goods inventory
    - qty_bad: Scrapped parts → material consumed but no product output

    All materials (for good + bad) are consumed since they were physically used.
    """
    po = db.query(ProductionOrder).filter(ProductionOrder.id == production_order_id).first()

    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    if po.status != "in_progress":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot complete print for order with status '{po.status}'"
        )

    ordered_qty = int(po.quantity)
    qty_good = request.qty_good if request.qty_good is not None else ordered_qty
    qty_bad = request.qty_bad if request.qty_bad is not None else 0
    total_produced = qty_good + qty_bad
    overrun_qty = max(0, qty_good - ordered_qty)  # MTS overrun quantity

    # Update production order
    po.status = "printed"  # Waiting for final QC/ship
    po.finish_date = datetime.now(timezone.utc)

    if request.actual_time_minutes:
        po.actual_time_minutes = request.actual_time_minutes

    # Record actual quantities
    notes_entry = f"[{datetime.now(timezone.utc).isoformat()}] Print complete: {qty_good} good, {qty_bad} scrapped"
    if request.qc_notes:
        notes_entry += f" - {request.qc_notes}"
    po.notes = (po.notes + "\n" if po.notes else "") + notes_entry

    # Update print job
    print_job = db.query(PrintJob).filter(PrintJob.production_order_id == po.id).first()
    if print_job:
        print_job.status = "completed"
        print_job.finished_at = datetime.now(timezone.utc)
        if request.actual_time_minutes:
            print_job.actual_time_minutes = request.actual_time_minutes

    # =========================================================================
    # MATERIAL CONSUMPTION - Only consume PRODUCTION-stage materials
    # Shipping-stage items (boxes) are consumed at buy_label
    # =========================================================================
    consumed_materials = []

    # Get the BOM to check consume_stage for each component
    bom = None
    if po.bom_id:
        bom = db.query(BOM).filter(BOM.id == po.bom_id).first()
    elif po.product_id:
        bom = db.query(BOM).filter(
            BOM.product_id == po.product_id,
            BOM.active.is_(True)
        ).first()

    # Build a set of component_ids that should be consumed at production stage
    production_stage_components = set()
    if bom and bom.lines:
        for line in bom.lines:
            # Default is 'production', so consume if not explicitly 'shipping'
            if getattr(line, 'consume_stage', 'production') != 'shipping':
                production_stage_components.add(line.component_id)

    # Find all reservation transactions for this production order
    reservation_txns = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.reference_id == po.id,
        InventoryTransaction.transaction_type == "reservation"
    ).all()

    for res_txn in reservation_txns:
        # Skip shipping-stage items (boxes, packaging) - they're consumed at buy_label
        if res_txn.product_id not in production_stage_components:
            component = db.query(Product).filter(Product.id == res_txn.product_id).first()
            component_sku = component.sku if component else "N/A"
            consumed_materials.append({
                "component_sku": component_sku,
                "quantity_consumed": 0,
                "skipped_reason": "shipping-stage item (consumed at ship time)",
            })
            continue
        reserved_qty = abs(float(res_txn.quantity))

        # Find the inventory record
        inventory = db.query(Inventory).filter(
            Inventory.product_id == res_txn.product_id,
            Inventory.location_id == res_txn.location_id
        ).first()

        if inventory:
            # Release reservation only - on_hand decrement and GL handled by TransactionService
            inventory.allocated_quantity = Decimal(str(
                max(0, float(inventory.allocated_quantity) - reserved_qty)
            ))

            # Get component info for response and TransactionService
            component = db.query(Product).filter(Product.id == res_txn.product_id).first()
            component_sku = component.sku if component else "N/A"

            # Track for TransactionService call below (no manual txn creation here)
            consumed_materials.append({
                "component_id": res_txn.product_id,  # For TransactionService
                "component_sku": component_sku,
                "quantity_consumed": round(reserved_qty, 4),
            })

    # =========================================================================
    # MATERIAL CONSUMPTION via TransactionService (atomic + GL entries)
    # =========================================================================
    txn_service = TransactionService(db)

    # Build materials list from what was consumed
    materials_to_consume = []
    for mat in consumed_materials:
        if mat.get("quantity_consumed", 0) > 0 and mat.get("component_id"):
            product = db.query(Product).filter(Product.id == mat["component_id"]).first()
            materials_to_consume.append(MaterialConsumption(
                product_id=mat["component_id"],
                quantity=Decimal(str(mat["quantity_consumed"])),
                unit_cost=(product.standard_cost or product.average_cost or Decimal("0")) if product else Decimal("0"),
                unit=product.unit if product and product.unit else "EA",
            ))

    if materials_to_consume:
        inv_txns, journal_entry = txn_service.issue_materials_for_operation(
            production_order_id=po.id,
            operation_sequence=10,  # Printing operation
            materials=materials_to_consume,
        )

    # =========================================================================
    # MACHINE TIME TRACKING - Record printer usage for metrics & costing
    # =========================================================================
    machine_time_recorded = None

    if bom and bom.lines:
        for line in bom.lines:
            component = db.query(Product).filter(Product.id == line.component_id).first()
            if component and component.sku.startswith(("SVC-", "MFG-")):
                # This is a machine time / overhead component
                estimated_hours = float(line.quantity)

                # Use actual time if provided, otherwise use BOM estimate
                if request.actual_time_minutes:
                    actual_hours = request.actual_time_minutes / 60.0
                else:
                    actual_hours = estimated_hours

                # Calculate cost
                hourly_rate = float(component.cost) if component.cost else float(settings.MACHINE_HOURLY_RATE)
                machine_cost = actual_hours * hourly_rate

                # Get printer info if assigned
                printer_info = None
                if print_job and print_job.printer_id:
                    printer = db.query(Printer).filter(Printer.id == print_job.printer_id).first()
                    if printer:
                        printer_info = {"id": printer.id, "code": printer.code, "name": printer.name}

                # Create machine time transaction
                # This uses the machine time product_id for tracking
                default_location = get_default_location(db)
                machine_txn = InventoryTransaction(
                    product_id=component.id,
                    location_id=default_location.id,  # Default location (machine time isn't location-specific)
                    transaction_type="machine_time",
                    reference_type="production_order",
                    reference_id=po.id,
                    quantity=Decimal(str(actual_hours)),  # Positive = hours used
                    cost_per_unit=Decimal(str(hourly_rate)),
                    total_cost=Decimal(str(machine_cost)),
                    unit="HR",
                    notes=f"Machine time for {po.code}: {actual_hours:.2f} hrs @ ${hourly_rate}/hr = ${machine_cost:.2f}" +
                          (f" on {printer_info['name']}" if printer_info else ""),
                    created_by="system",
                )
                db.add(machine_txn)

                machine_time_recorded = {
                    "product_sku": component.sku,
                    "estimated_hours": round(estimated_hours, 2),
                    "actual_hours": round(actual_hours, 2),
                    "hourly_rate": hourly_rate,
                    "total_cost": round(machine_cost, 2),
                    "printer": printer_info,
                    "variance_hours": round(actual_hours - estimated_hours, 2),
                }
                break  # Only one machine time line per BOM

    # =========================================================================
    # FINISHED GOODS INVENTORY - MOVED TO pass_qc()
    # FG receipt now happens at QC pass (Step 3), not print complete (Step 1)
    # This ensures parts only enter FG inventory after passing quality check.
    # =========================================================================
    finished_goods_added = None  # FG receipt happens at pass_qc(), not here

    # =========================================================================
    # SCRAP TRACKING - Record scrapped parts for variance analysis
    # =========================================================================
    scrap_recorded = None
    if qty_bad > 0:
        # Get default location for scrap tracking
        default_location = get_default_location(db)
        # Get product for cost calculation
        product = db.query(Product).filter(Product.id == po.product_id).first()
        from app.services.inventory_service import get_effective_cost_per_inventory_unit
        unit_cost = get_effective_cost_per_inventory_unit(product) if product else None
        total_cost = Decimal(str(qty_bad)) * unit_cost if unit_cost else None
        # Create a scrap/variance transaction for tracking
        scrap_txn = InventoryTransaction(
            product_id=po.product_id,
            location_id=default_location.id,
            transaction_type="scrap",
            reference_type="production_order",
            reference_id=po.id,
            quantity=Decimal(str(-qty_bad)),  # Negative = loss
            cost_per_unit=unit_cost,
            total_cost=total_cost,
            unit=product.unit if product else "EA",
            notes=f"Production scrap from {po.code}: {qty_bad} parts failed (adhesion/defects)",
            created_by="system",
        )
        db.add(scrap_txn)

        scrap_recorded = {
            "quantity_scrapped": qty_bad,
            "scrap_rate": round(qty_bad / total_produced * 100, 1) if total_produced > 0 else 0,
        }

    # =========================================================================
    # CHECK FOR SHORTFALL - May need reprint
    # =========================================================================
    shortfall = ordered_qty - qty_good
    reprint_needed = shortfall > 0

    db.commit()

    return {
        "success": True,
        "production_order_id": po.id,
        "status": po.status,
        "quantities": {
            "ordered": ordered_qty,
            "good": qty_good,
            "bad": qty_bad,
            "overrun": overrun_qty,
            "shortfall": shortfall,
        },
        "materials_consumed": consumed_materials,
        "machine_time_recorded": machine_time_recorded,
        "finished_goods_added": finished_goods_added,
        "scrap_recorded": scrap_recorded,
        "reprint_needed": reprint_needed,
        "message": f"Print complete for {po.code}: {qty_good} good, {qty_bad} scrapped. FG will be added to inventory at QC pass." +
                   (f" SHORTFALL: {shortfall} parts need reprint!" if reprint_needed else ""),
    }


@router.post("/queue/{production_order_id}/pass-qc")
async def pass_quality_check(
    production_order_id: int,
    qc_notes: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Mark order as passed QC, receipt finished goods, and mark ready to ship.

    Updates production order to 'completed', receipts FG to inventory,
    and updates sales order to 'ready_to_ship'.

    Flow:
    1. start_production() - reserves materials (allocated_qty increases)
    2. complete_print() - consumes materials (on_hand + allocated decrease)
    3. pass_qc() - RECEIPTS FG TO INVENTORY + status updates (THIS FUNCTION)
    4. buy_label() - issues FG from inventory when shipped

    NOTE: Materials are consumed in complete_print(), NOT here.
    FG receipt happens HERE because parts should only enter inventory after QC.
    """
    po = db.query(ProductionOrder).filter(ProductionOrder.id == production_order_id).first()

    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    if po.status != "printed":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pass QC for order with status '{po.status}'"
        )

    # Complete production order
    po.status = "completed"
    # Don't overwrite finish_date - it was set in complete_print when printing finished
    # po.finish_date should already be set

    if qc_notes:
        po.notes = (po.notes + "\n" if po.notes else "") + f"[{datetime.now(timezone.utc).isoformat()}] QC Passed: {qc_notes}"

    # =========================================================================
    # NO MATERIAL CONSUMPTION HERE - Already done in complete_print()
    #
    # BUG FIX: Previously this endpoint ALSO consumed materials, causing
    # double-consumption when both complete_print and pass_qc were called.
    # Materials are physically consumed during printing, so consumption
    # is recorded in complete_print(). QC is just inspection.
    # =========================================================================

    # Update sales order to ready_to_ship
    # FIXED: Use direct link first, fallback to quote lookup for legacy POs
    sales_order_updated = False
    sales_order = None
    if po.sales_order_id:
        # Direct link (preferred)
        sales_order = db.query(SalesOrder).filter(SalesOrder.id == po.sales_order_id).first()
    elif po.product_id:
        # Fallback for legacy production orders without direct link
        quote = db.query(Quote).filter(Quote.product_id == po.product_id).first()
        if quote:
            sales_order = db.query(SalesOrder).filter(SalesOrder.quote_id == quote.id).first()

    if sales_order:
        sales_order.status = "ready_to_ship"
        sales_order_updated = True

    # =========================================================================
    # FINISHED GOODS RECEIPT via TransactionService (atomic + GL entries)
    # This is the correct point for FG receipt (Step 3: QC Pass)
    # Parts only enter FG inventory after passing quality check.
    # Accounting: DR 1220 FG Inventory, CR 1210 WIP
    # =========================================================================
    finished_goods_added = None

    # Get quantity from production order (full ordered quantity passes QC)
    qty_good = int(po.quantity)

    # Determine the product_id and get product for costing
    fg_product_id = po.product_id
    product = db.query(Product).filter(Product.id == fg_product_id).first() if fg_product_id else None

    if qty_good > 0 and fg_product_id and product:
        # Get unit cost from product (standard_cost preferred, fall back to cost)
        unit_cost = product.standard_cost if product.standard_cost else (product.cost if product.cost else Decimal("0"))

        # Use TransactionService for atomic inventory + GL entry
        txn_service = TransactionService(db)
        inv_txn, journal_entry = txn_service.receipt_finished_good(
            production_order_id=po.id,
            product_id=fg_product_id,
            quantity=Decimal(str(qty_good)),
            unit_cost=unit_cost,
            lot_number=None,  # Future: generate lot number
            user_id=None,  # Future: pass current_admin.id
        )

        # Get updated inventory for response
        fg_inventory = db.query(Inventory).filter(
            Inventory.product_id == fg_product_id
        ).first()

        finished_goods_added = {
            "product_sku": product.sku if product else "N/A",
            "quantity_added": qty_good,
            "new_on_hand": float(fg_inventory.on_hand_quantity) if fg_inventory else qty_good,
            "journal_entry_id": journal_entry.id if journal_entry else None,
        }

    db.commit()

    return {
        "success": True,
        "production_order_id": po.id,
        "code": po.code,
        "status": po.status,
        "sales_order_status": "ready_to_ship" if sales_order_updated else None,
        "finished_goods_added": finished_goods_added,
        "message": f"QC passed for {po.code}. {qty_good} units added to FG inventory. Order ready to ship!",
    }


@router.post("/queue/{production_order_id}/fail-qc")
async def fail_quality_check(
    production_order_id: int,
    failure_reason: str,
    reprint: bool = True,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Mark order as failed QC.

    If reprint=True, creates a new production order for reprint.
    """
    po = db.query(ProductionOrder).filter(ProductionOrder.id == production_order_id).first()

    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    if po.status != "printed":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot fail QC for order with status '{po.status}'"
        )

    # Mark as failed
    po.status = "qc_failed"
    po.notes = (po.notes + "\n" if po.notes else "") + f"[{datetime.now(timezone.utc).isoformat()}] QC FAILED: {failure_reason}"

    # =========================================================================
    # RELEASE SHIPPING-STAGE RESERVATIONS (boxes weren't used)
    # Production-stage materials were already consumed in complete_print()
    # =========================================================================
    released_materials = []

    # Get BOM to identify shipping-stage components
    bom = None
    if po.bom_id:
        bom = db.query(BOM).filter(BOM.id == po.bom_id).first()
    elif po.product_id:
        bom = db.query(BOM).filter(
            BOM.product_id == po.product_id,
            BOM.active.is_(True)
        ).first()

    # Build set of shipping-stage component IDs
    shipping_stage_components = set()
    if bom and bom.lines:
        for line in bom.lines:
            if getattr(line, 'consume_stage', 'production') == 'shipping':
                shipping_stage_components.add(line.component_id)

    # Find remaining reservation transactions (should only be shipping-stage)
    reservation_txns = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.reference_id == po.id,
        InventoryTransaction.transaction_type == "reservation"
    ).all()

    for res_txn in reservation_txns:
        reserved_qty = abs(float(res_txn.quantity))

        inventory = db.query(Inventory).filter(
            Inventory.product_id == res_txn.product_id,
            Inventory.location_id == res_txn.location_id
        ).first()

        if inventory:
            # Release the reservation (return to available, NOT consumed)
            inventory.allocated_quantity = Decimal(str(
                max(0, float(inventory.allocated_quantity) - reserved_qty)
            ))
            # NOTE: Do NOT decrement on_hand - material wasn't used!

            component = db.query(Product).filter(Product.id == res_txn.product_id).first()
            component_sku = component.sku if component else "N/A"

            # Create release transaction (positive qty = returned to available)
            # Copy cost from original reservation transaction
            unit_cost = res_txn.cost_per_unit
            total_cost = Decimal(str(reserved_qty)) * unit_cost if unit_cost else None
            release_txn = InventoryTransaction(
                product_id=res_txn.product_id,
                location_id=res_txn.location_id,
                transaction_type="release",
                reference_type="production_order",
                reference_id=po.id,
                quantity=Decimal(str(reserved_qty)),  # Positive = released back
                cost_per_unit=unit_cost,
                total_cost=total_cost,
                unit=res_txn.unit or (component.unit if component else "EA"),
                notes=f"Reservation released for {po.code} (QC Failed - materials not used)",
                created_by="system",
            )
            db.add(release_txn)

            released_materials.append({
                "component_sku": component_sku,
                "quantity_released": round(reserved_qty, 4),
            })

    # =========================================================================
    # WIP SCRAP via TransactionService (atomic + GL entries)
    # Write off the production costs (materials + labor already consumed)
    # Accounting: DR 5020 Scrap Expense, CR 1210 WIP
    # =========================================================================
    scrap_record = None
    qty_scrapped = int(po.quantity)
    fg_product = db.query(Product).filter(Product.id == po.product_id).first() if po.product_id else None

    if qty_scrapped > 0 and fg_product:
        # Get unit cost (WIP value per unit)
        unit_cost = fg_product.standard_cost if fg_product.standard_cost else (
            fg_product.cost if fg_product.cost else Decimal("0")
        )

        txn_service = TransactionService(db)
        inv_txn, journal_entry, scrap_rec = txn_service.scrap_materials(
            production_order_id=po.id,
            operation_sequence=30,  # QC operation (Step 3)
            product_id=fg_product.id,
            quantity=Decimal(str(qty_scrapped)),
            unit_cost=unit_cost,
            reason_code=f"QC_FAIL: {failure_reason[:50]}",  # Truncate for code field
            notes=f"QC Failed: {failure_reason}",
            user_id=None,  # Future: pass current_admin.id
        )

        scrap_record = {
            "product_sku": fg_product.sku,
            "quantity_scrapped": qty_scrapped,
            "unit_cost": float(unit_cost),
            "total_cost": float(qty_scrapped * unit_cost),
            "journal_entry_id": journal_entry.id if journal_entry else None,
            "scrap_record_id": scrap_rec.id if scrap_rec else None,
        }

    new_po = None
    if reprint:
        # Create new production order for reprint
        # Generate new code
        year = datetime.now(timezone.utc).year
        last_po = (
            db.query(ProductionOrder)
            .filter(ProductionOrder.code.like(f"PO-{year}-%"))
            .order_by(desc(ProductionOrder.code))
            .first()
        )
        if last_po:
            last_num = int(last_po.code.split("-")[2])
            next_num = last_num + 1
        else:
            next_num = 1

        new_code = f"PO-{year}-{next_num:03d}"

        new_po = ProductionOrder(
            code=new_code,
            product_id=po.product_id,
            bom_id=po.bom_id,
            quantity_ordered=po.quantity_ordered,
            status="scheduled",
            priority=1,  # Reprints are high priority (1=highest)
            estimated_time_minutes=po.estimated_time_minutes,
            notes=f"REPRINT of {po.code}. Original failed QC: {failure_reason}",
        )
        db.add(new_po)

    db.commit()

    return {
        "success": True,
        "production_order_id": po.id,
        "status": po.status,
        "reprint_created": reprint,
        "new_production_order_id": new_po.id if new_po else None,
        "new_production_order_code": new_po.code if new_po else None,
        "materials_released": released_materials,
        "scrap_record": scrap_record,
        "message": f"QC failed for {po.code}." + (f" Reprint order {new_po.code} created." if new_po else ""),
    }


# ============================================================================
# BULK OPERATIONS
# ============================================================================

@router.post("/bulk-update")
async def bulk_update_status(
    request: BulkStatusUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Update status for multiple production orders at once.

    Useful for batch operations like starting multiple prints.
    """
    valid_statuses = ["scheduled", "in_progress", "printed", "completed", "cancelled"]

    if request.new_status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    updated = []
    errors = []

    for po_id in request.production_order_ids:
        po = db.query(ProductionOrder).filter(ProductionOrder.id == po_id).first()

        if not po:
            errors.append({"id": po_id, "error": "Not found"})
            continue

        try:
            old_status = po.status
            po.status = request.new_status

            # Set timestamps based on status
            if request.new_status == "in_progress" and old_status != "in_progress":
                po.start_date = datetime.now(timezone.utc)
            elif request.new_status == "completed" and old_status != "completed":
                po.finish_date = datetime.now(timezone.utc)

            if request.notes:
                po.notes = (po.notes + "\n" if po.notes else "") + f"[{datetime.now(timezone.utc).isoformat()}] Bulk update: {request.notes}"

            updated.append({"id": po_id, "code": po.code, "old_status": old_status, "new_status": request.new_status})
        except Exception as e:
            logger.error(f"Bulk update failed for production order {po_id}: {e}")
            errors.append({"id": po_id, "error": "Update failed"})

    db.commit()

    return {
        "success": len(errors) == 0,
        "updated_count": len(updated),
        "error_count": len(errors),
        "updated": updated,
        "errors": errors,
    }
