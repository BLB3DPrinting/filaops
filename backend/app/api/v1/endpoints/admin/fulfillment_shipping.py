# pyright: reportArgumentType=false
# pyright: reportAssignmentType=false
"""
Admin Fulfillment Shipping Endpoints

Handles shipping and ship-from-stock workflows:
1. Ready-to-Ship Queue
2. Shipping Rate Quotes
3. Label Purchase
4. Consolidated Shipping
5. Ship-from-Stock (direct FG fulfillment)
6. Manual Ship Marking

Split from fulfillment.py — production queue endpoints are in fulfillment_queue.py.
"""
from datetime import datetime, timezone
from typing import List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from pydantic import BaseModel

from app.db.session import get_db
from app.models.user import User
from app.models.quote import Quote
from app.models.sales_order import SalesOrder
from app.models.production_order import ProductionOrder
from app.models.product import Product
from app.models.bom import BOM
from app.models.inventory import Inventory, InventoryTransaction, InventoryLocation
from app.models.traceability import SerialNumber
from app.services.shipping_service import shipping_service
from app.services.transaction_service import TransactionService, ShipmentItem, PackagingUsed
from app.api.v1.deps import get_current_staff_user

router = APIRouter(prefix="/fulfillment", tags=["Admin - Fulfillment Shipping"])


# ============================================================================
# SCHEMAS
# ============================================================================

class CreateShippingLabelRequest(BaseModel):
    """Request to create a shipping label"""
    carrier_preference: Optional[str] = None  # USPS, UPS, FedEx
    service_preference: Optional[str] = None  # Priority, Ground, etc.


class ShipOrderRequest(BaseModel):
    """Request to mark order as shipped"""
    tracking_number: str
    carrier: str
    shipping_cost: Optional[float] = None
    notify_customer: bool = True


class ConsolidatedShipRequest(BaseModel):
    """Request to get rates for consolidated shipment"""
    order_ids: List[int]
    box_product_id: Optional[int] = None


class ShipFromStockRequest(BaseModel):
    """Request to ship from existing FG inventory (Ship-from-Stock path)"""
    rate_id: str  # EasyPost rate ID from get-rates
    shipment_id: str  # EasyPost shipment ID from get-rates
    packaging_product_id: Optional[int] = None  # Optional: override default box
    packaging_quantity: Optional[int] = None  # Optional: override box count (default=1)

    class Config:
        from_attributes = True


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/ready-to-ship")
async def get_orders_ready_to_ship(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Get all orders that are ready to ship.

    These orders have completed production and passed QC.
    Includes reserved box information from BOM for shipper selection.
    """
    orders = (
        db.query(SalesOrder)
        .filter(SalesOrder.status == "ready_to_ship")
        .order_by(desc(SalesOrder.created_at))
        .limit(limit)
        .all()
    )

    result = []
    for order in orders:
        # Get quote for additional details
        quote = db.query(Quote).filter(Quote.id == order.quote_id).first() if order.quote_id else None
        customer = db.query(User).filter(User.id == order.user_id).first() if order.user_id else None

        # Get reserved box from BOM (shipping-stage item)
        reserved_box = None
        if quote and quote.product_id:
            bom = db.query(BOM).filter(
                BOM.product_id == quote.product_id,
                BOM.active.is_(True)
            ).first()

            if bom and bom.lines:
                for line in bom.lines:
                    if getattr(line, 'consume_stage', 'production') == 'shipping':
                        box_product = db.query(Product).filter(Product.id == line.component_id).first()
                        if box_product:
                            # Parse box dimensions from product name
                            from app.services.bom_service import parse_box_dimensions
                            dims = parse_box_dimensions(box_product.name)
                            reserved_box = {
                                "product_id": box_product.id,
                                "sku": box_product.sku,
                                "name": box_product.name,
                                "dimensions": {
                                    "length": dims[0] if dims else None,
                                    "width": dims[1] if dims else None,
                                    "height": dims[2] if dims else None,
                                } if dims else None,
                            }
                            break

        # Create address key for grouping orders to same destination
        address_key = f"{order.shipping_address_line1}|{order.shipping_city}|{order.shipping_state}|{order.shipping_zip}".lower().strip()

        result.append({
            "id": order.id,
            "order_number": order.order_number,
            "product_name": order.product_name,
            "quantity": order.quantity,
            "grand_total": float(order.grand_total) if order.grand_total else None,
            "customer_name": customer.full_name if customer else None,
            "customer_email": customer.email if customer else None,
            "shipping_address": {
                "name": quote.shipping_name if quote else None,
                "line1": order.shipping_address_line1,
                "line2": order.shipping_address_line2,
                "city": order.shipping_city,
                "state": order.shipping_state,
                "zip": order.shipping_zip,
                "country": order.shipping_country,
            },
            "address_key": address_key,  # For grouping orders to same address
            "material_grams": float(quote.material_grams) if quote and quote.material_grams else None,
            "dimensions": {
                "x": float(quote.dimensions_x) if quote and quote.dimensions_x else None,
                "y": float(quote.dimensions_y) if quote and quote.dimensions_y else None,
                "z": float(quote.dimensions_z) if quote and quote.dimensions_z else None,
            } if quote else None,
            "reserved_box": reserved_box,  # Box from BOM for shipper to use or override
            "created_at": order.created_at.isoformat(),
        })

    return {
        "orders": result,
        "total": len(result),
    }


@router.get("/ship/boxes")
async def get_available_boxes(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Get all available shipping boxes for shipper selection.

    Returns boxes sorted by volume (smallest first) with dimensions parsed.
    """
    from app.services.bom_service import parse_box_dimensions

    # Get all box products (matching the pattern used in bom_service)
    box_products = db.query(Product).filter(
        Product.active.is_(True),  # noqa: E712
        Product.name.like('%box%')
    ).all()

    boxes = []
    for box in box_products:
        dims = parse_box_dimensions(box.name)
        if dims:
            length, width, height = dims
            volume = length * width * height
            boxes.append({
                "product_id": box.id,
                "sku": box.sku,
                "name": box.name,
                "dimensions": {
                    "length": length,
                    "width": width,
                    "height": height,
                },
                "volume": volume,
            })

    # Sort by volume (smallest first)
    boxes.sort(key=lambda x: x["volume"])

    return {
        "boxes": boxes,
        "total": len(boxes),
    }


# =============================================================================
# CONSOLIDATED SHIPPING - Must be before parameterized routes!
# =============================================================================

@router.post("/ship/consolidate/get-rates")
async def get_consolidated_shipping_rates(
    request: ConsolidatedShipRequest,
    db: Session = Depends(get_db),
):
    """
    Get shipping rates for multiple orders consolidated into one package.

    All orders must be going to the same address.
    Calculates combined weight from all orders.
    """
    from app.services.bom_service import parse_box_dimensions

    if len(request.order_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 orders to consolidate")

    # Fetch all orders
    orders = db.query(SalesOrder).filter(
        SalesOrder.id.in_(request.order_ids),
        SalesOrder.status == "ready_to_ship"
    ).all()

    if len(orders) != len(request.order_ids):
        raise HTTPException(
            status_code=400,
            detail=f"Some orders not found or not ready to ship. Found {len(orders)} of {len(request.order_ids)}"
        )

    # Verify all orders go to same address
    first_order = orders[0]
    address_key = f"{first_order.shipping_address_line1}|{first_order.shipping_city}|{first_order.shipping_state}|{first_order.shipping_zip}".lower().strip()

    for order in orders[1:]:
        order_key = f"{order.shipping_address_line1}|{order.shipping_city}|{order.shipping_state}|{order.shipping_zip}".lower().strip()
        if order_key != address_key:
            raise HTTPException(
                status_code=400,
                detail=f"Order {order.order_number} has different shipping address. Cannot consolidate."
            )

    # Calculate combined weight from all orders
    total_weight_grams = 0
    total_quantity = 0
    order_numbers = []

    for order in orders:
        order_numbers.append(order.order_number)
        total_quantity += order.quantity or 1

        quote = db.query(Quote).filter(Quote.id == order.quote_id).first() if order.quote_id else None
        if quote and quote.material_grams:
            total_weight_grams += float(quote.material_grams) * (order.quantity or 1)
        else:
            total_weight_grams += 100 * (order.quantity or 1)  # Default 100g per item

    # Convert to ounces with packaging overhead
    weight_oz = shipping_service.estimate_weight_oz(total_weight_grams, 1)

    # Determine box dimensions
    length, width, height = 12.0, 10.0, 6.0  # Default medium box for consolidated

    if request.box_product_id:
        box = db.query(Product).filter(Product.id == request.box_product_id).first()
        if box:
            dims = parse_box_dimensions(box.name)
            if dims:
                length, width, height = dims

    # Get shipping name from first order
    quote = db.query(Quote).filter(Quote.id == first_order.quote_id).first() if first_order.quote_id else None
    shipping_name = quote.shipping_name if quote and quote.shipping_name else "Customer"

    # Get rates
    rates, shipment_id = shipping_service.get_shipping_rates(
        to_name=shipping_name,
        to_street1=first_order.shipping_address_line1,
        to_street2=first_order.shipping_address_line2,
        to_city=first_order.shipping_city,
        to_state=first_order.shipping_state,
        to_zip=first_order.shipping_zip,
        to_country=first_order.shipping_country or "US",
        weight_oz=weight_oz,
        length=length,
        width=width,
        height=height,
    )

    if not rates:
        return {
            "success": False,
            "rates": [],
            "error": "No shipping rates available. Please verify the address."
        }

    formatted_rates = [
        {
            "carrier": r.carrier,
            "service": r.service,
            "rate": float(r.rate),
            "est_delivery_days": r.est_delivery_days,
            "rate_id": r.rate_id,
            "display_name": f"{r.carrier} {r.service}",
        }
        for r in rates
    ]

    return {
        "success": True,
        "rates": formatted_rates,
        "shipment_id": shipment_id,
        "consolidated": {
            "order_count": len(orders),
            "order_numbers": order_numbers,
            "order_ids": request.order_ids,
            "total_weight_oz": round(weight_oz, 2),
            "total_items": total_quantity,
        },
        "package": {
            "weight_oz": round(weight_oz, 2),
            "length": length,
            "width": width,
            "height": height,
        },
    }


@router.post("/ship/consolidate/buy-label")
async def buy_consolidated_shipping_label(
    order_ids: List[int],
    rate_id: str,
    shipment_id: str,
    db: Session = Depends(get_db),
):
    """
    Purchase a shipping label for consolidated orders.

    Updates ALL orders with the same tracking number.
    Only consumes packaging from ONE order (avoids double-consumption).
    """
    if len(order_ids) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 orders to consolidate")

    # Fetch all orders
    orders = db.query(SalesOrder).filter(
        SalesOrder.id.in_(order_ids),
        SalesOrder.status == "ready_to_ship"
    ).all()

    if len(orders) != len(order_ids):
        raise HTTPException(
            status_code=400,
            detail="Some orders not found or not ready to ship"
        )

    # Buy the label
    result = shipping_service.buy_label(rate_id=rate_id, shipment_id=shipment_id)

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to purchase label: {result.error}"
        )

    # Consume packaging from FIRST order only (consolidated = one box)
    packaging_consumed = []
    first_order = orders[0]

    production_orders = db.query(ProductionOrder).filter(
        ProductionOrder.sales_order_id == first_order.id
    ).all()

    for po in production_orders:
        bom = None
        if po.bom_id:
            bom = db.query(BOM).filter(BOM.id == po.bom_id).first()
        elif po.product_id:
            bom = db.query(BOM).filter(
                BOM.product_id == po.product_id,
                BOM.active.is_(True)
            ).first()

        if not bom or not bom.lines:
            continue

        for line in bom.lines:
            if getattr(line, 'consume_stage', 'production') != 'shipping':
                continue

            res_txn = db.query(InventoryTransaction).filter(
                InventoryTransaction.reference_type == "production_order",
                InventoryTransaction.reference_id == po.id,
                InventoryTransaction.product_id == line.component_id,
                InventoryTransaction.transaction_type == "reservation"
            ).first()

            if not res_txn:
                continue

            reserved_qty = abs(float(res_txn.quantity))

            inventory = db.query(Inventory).filter(
                Inventory.product_id == res_txn.product_id,
                Inventory.location_id == res_txn.location_id
            ).first()

            if inventory:
                inventory.allocated_quantity = Decimal(str(
                    max(0, float(inventory.allocated_quantity) - reserved_qty)
                ))
                inventory.on_hand_quantity = Decimal(str(
                    max(0, float(inventory.on_hand_quantity) - reserved_qty)
                ))

                component = db.query(Product).filter(Product.id == res_txn.product_id).first()

                # Get cost for accounting
                from app.services.inventory_service import get_effective_cost_per_inventory_unit
                unit_cost = get_effective_cost_per_inventory_unit(component) if component else None
                total_cost = Decimal(str(reserved_qty)) * unit_cost if unit_cost else None

                consumption_txn = InventoryTransaction(
                    product_id=res_txn.product_id,
                    location_id=res_txn.location_id,
                    transaction_type="consumption",
                    reference_type="consolidated_shipment",
                    reference_id=first_order.id,
                    quantity=Decimal(str(-reserved_qty)),
                    cost_per_unit=unit_cost,
                    total_cost=total_cost,
                    unit=component.unit if component else "EA",
                    notes=f"Packaging for consolidated shipment: {', '.join([o.order_number for o in orders])}",
                    created_by="system",
                )
                db.add(consumption_txn)

                packaging_consumed.append({
                    "component_sku": component.sku if component else "N/A",
                    "quantity_consumed": round(reserved_qty, 4),
                })

    # Release packaging reservations from OTHER orders (not consumed, just released)
    for order in orders[1:]:
        other_pos = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id == order.id
        ).all()

        for po in other_pos:
            bom = None
            if po.bom_id:
                bom = db.query(BOM).filter(BOM.id == po.bom_id).first()
            elif po.product_id:
                bom = db.query(BOM).filter(
                    BOM.product_id == po.product_id,
                    BOM.active.is_(True)
                ).first()

            if not bom or not bom.lines:
                continue

            for line in bom.lines:
                if getattr(line, 'consume_stage', 'production') != 'shipping':
                    continue

                res_txn = db.query(InventoryTransaction).filter(
                    InventoryTransaction.reference_type == "production_order",
                    InventoryTransaction.reference_id == po.id,
                    InventoryTransaction.product_id == line.component_id,
                    InventoryTransaction.transaction_type == "reservation"
                ).first()

                if not res_txn:
                    continue

                reserved_qty = abs(float(res_txn.quantity))

                inventory = db.query(Inventory).filter(
                    Inventory.product_id == res_txn.product_id,
                    Inventory.location_id == res_txn.location_id
                ).first()

                if inventory:
                    # Just release the reservation (box not used)
                    inventory.allocated_quantity = Decimal(str(
                        max(0, float(inventory.allocated_quantity) - reserved_qty)
                    ))

                    component = db.query(Product).filter(Product.id == res_txn.product_id).first()

                    # Copy cost from original reservation transaction
                    unit_cost = res_txn.cost_per_unit
                    total_cost = Decimal(str(reserved_qty)) * unit_cost if unit_cost else None
                    release_txn = InventoryTransaction(
                        product_id=res_txn.product_id,
                        location_id=res_txn.location_id,
                        transaction_type="release",
                        reference_type="consolidated_shipment",
                        reference_id=order.id,
                        quantity=Decimal(str(reserved_qty)),  # Positive = released back
                        cost_per_unit=unit_cost,
                        total_cost=total_cost,
                        unit=res_txn.unit or (component.unit if component else "EA"),
                        notes=f"Box reservation released - consolidated into {first_order.order_number}",
                        created_by="system",
                    )
                    db.add(release_txn)

    # Update ALL orders with same tracking
    order_numbers = []
    for order in orders:
        order.tracking_number = result.tracking_number
        order.carrier = result.carrier
        order.shipping_cost = Decimal(str(result.rate / len(orders))) if result.rate else None  # Split cost
        order.status = "shipped"
        order.shipped_at = datetime.now(timezone.utc)
        order_numbers.append(order.order_number)

    db.commit()

    return {
        "success": True,
        "consolidated_orders": order_numbers,
        "tracking_number": result.tracking_number,
        "carrier": result.carrier,
        "label_url": result.label_url,
        "total_shipping_cost": float(result.rate) if result.rate else None,
        "cost_per_order": float(result.rate / len(orders)) if result.rate else None,
        "packaging_consumed": packaging_consumed,
        "message": f"Consolidated {len(orders)} orders! Tracking: {result.tracking_number}",
    }


# =============================================================================
# SINGLE ORDER SHIPPING - Parameterized routes must come after static routes!
# =============================================================================

@router.post("/ship/{sales_order_id}/get-rates")
async def get_shipping_rates_for_order(
    sales_order_id: int,
    box_product_id: Optional[int] = None,  # Optional override for box selection
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Get shipping rate options for an order.

    Args:
        sales_order_id: The sales order to get rates for
        box_product_id: Optional box product ID to override BOM default.
                        If provided, uses this box's dimensions for rate calculation.
    """
    from app.services.bom_service import parse_box_dimensions

    order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")

    if not order.shipping_address_line1:
        raise HTTPException(status_code=400, detail="Order has no shipping address")

    # Get quote for dimensions/weight
    quote = db.query(Quote).filter(Quote.id == order.quote_id).first() if order.quote_id else None

    # Calculate weight
    weight_oz = 16.0  # Default 1 lb
    if quote and quote.material_grams:
        weight_oz = shipping_service.estimate_weight_oz(
            float(quote.material_grams),
            order.quantity
        )

    # Determine box dimensions
    length, width, height = 10.0, 8.0, 4.0
    selected_box = None

    if box_product_id:
        # Use shipper's selected box
        box = db.query(Product).filter(Product.id == box_product_id).first()
        if box:
            dims = parse_box_dimensions(box.name)
            if dims:
                length, width, height = dims
                selected_box = {"id": box.id, "sku": box.sku, "name": box.name}
    elif quote and quote.dimensions_x and quote.dimensions_y and quote.dimensions_z:
        # Use BOM's default box estimation
        length, width, height = shipping_service.estimate_box_size(
            (float(quote.dimensions_x), float(quote.dimensions_y), float(quote.dimensions_z)),
            order.quantity
        )

    # Get shipping name
    shipping_name = "Customer"
    if quote and quote.shipping_name:
        shipping_name = quote.shipping_name

    # Get rates (returns tuple of rates and shipment_id)
    rates, shipment_id = shipping_service.get_shipping_rates(
        to_name=shipping_name,
        to_street1=order.shipping_address_line1,
        to_street2=order.shipping_address_line2,
        to_city=order.shipping_city,
        to_state=order.shipping_state,
        to_zip=order.shipping_zip,
        to_country=order.shipping_country or "US",
        weight_oz=weight_oz,
        length=length,
        width=width,
        height=height,
    )

    if not rates:
        return {
            "success": False,
            "rates": [],
            "error": "No shipping rates available. Please verify the address."
        }

    # Format rates
    formatted_rates = [
        {
            "carrier": r.carrier,
            "service": r.service,
            "rate": float(r.rate),
            "est_delivery_days": r.est_delivery_days,
            "rate_id": r.rate_id,
            "display_name": f"{r.carrier} {r.service}",
        }
        for r in rates
    ]

    return {
        "success": True,
        "rates": formatted_rates,
        "shipment_id": shipment_id,  # REQUIRED for buy-label
        "package": {
            "weight_oz": weight_oz,
            "length": length,
            "width": width,
            "height": height,
        },
        "selected_box": selected_box,  # Included if box_product_id was provided
    }


@router.post("/ship/{sales_order_id}/buy-label")
async def buy_shipping_label(
    sales_order_id: int,
    rate_id: str,
    shipment_id: str,  # Required - from get-rates response
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Purchase a shipping label for an order.

    Args:
        rate_id: The rate ID to purchase (from get-rates)
        shipment_id: The shipment ID (from get-rates response)

    Updates the order with tracking information.
    """
    order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")

    if order.status != "ready_to_ship":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create label for order with status '{order.status}'"
        )

    # Buy the label
    result = shipping_service.buy_label(rate_id=rate_id, shipment_id=shipment_id)

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to purchase label: {result.error}"
        )

    # =========================================================================
    # SHIPMENT via TransactionService (atomic + GL entries)
    # Handles both FG issue and packaging consumption with proper accounting
    # Accounting:
    #   - FG: DR 5000 COGS, CR 1220 FG Inventory
    #   - Packaging: DR 5010 Shipping Expense, CR 1230 Packaging Inventory
    # =========================================================================
    from app.services.transaction_service import ShipmentItem, PackagingUsed

    packaging_consumed = []
    finished_goods_shipped = None

    # Get quote for product info
    quote = db.query(Quote).filter(Quote.id == order.quote_id).first() if order.quote_id else None
    fg_product = db.query(Product).filter(Product.id == quote.product_id).first() if quote and quote.product_id else None
    qty_shipped = order.quantity or 1

    # Build packaging list from BOM shipping-stage items
    packaging_list = []  # List[PackagingUsed]
    production_orders = db.query(ProductionOrder).filter(
        ProductionOrder.sales_order_id == sales_order_id
    ).all()

    for po in production_orders:
        bom = None
        if po.bom_id:
            bom = db.query(BOM).filter(BOM.id == po.bom_id).first()
        elif po.product_id:
            bom = db.query(BOM).filter(
                BOM.product_id == po.product_id,
                BOM.active.is_(True)
            ).first()

        if not bom or not bom.lines:
            continue

        for line in bom.lines:
            if getattr(line, 'consume_stage', 'production') != 'shipping':
                continue

            # Find reservation to get actual reserved quantity
            res_txn = db.query(InventoryTransaction).filter(
                InventoryTransaction.reference_type == "production_order",
                InventoryTransaction.reference_id == po.id,
                InventoryTransaction.product_id == line.component_id,
                InventoryTransaction.transaction_type == "reservation"
            ).first()

            if res_txn:
                reserved_qty = int(abs(float(res_txn.quantity)))  # PackagingUsed expects int
                pkg_product = db.query(Product).filter(Product.id == line.component_id).first()
                pkg_cost = pkg_product.cost if pkg_product and pkg_product.cost else Decimal("0")

                packaging_list.append(PackagingUsed(
                    product_id=line.component_id,
                    quantity=reserved_qty,
                    unit_cost=pkg_cost,
                ))

                # Release the reservation (TransactionService handles the consumption)
                inventory = db.query(Inventory).filter(
                    Inventory.product_id == res_txn.product_id,
                    Inventory.location_id == res_txn.location_id
                ).first()
                if inventory:
                    inventory.allocated_quantity = Decimal(str(
                        max(0, float(inventory.allocated_quantity) - reserved_qty)
                    ))

                packaging_consumed.append({
                    "component_sku": pkg_product.sku if pkg_product else "N/A",
                    "quantity_consumed": reserved_qty,
                })

    # Call TransactionService for atomic shipment with GL
    if fg_product and qty_shipped > 0:
        fg_cost = fg_product.standard_cost if fg_product.standard_cost else (
            fg_product.cost if fg_product.cost else Decimal("0")
        )

        # Build shipment items list (uses ShipmentItem NamedTuple)
        shipment_items = [ShipmentItem(
            product_id=fg_product.id,
            quantity=Decimal(str(qty_shipped)),
            unit_cost=fg_cost,
        )]

        txn_service = TransactionService(db)
        inv_txns, journal_entry = txn_service.ship_order(
            sales_order_id=sales_order_id,
            items=shipment_items,
            packaging=packaging_list if packaging_list else None,
        )

        # Get updated FG inventory for response
        fg_inventory = db.query(Inventory).filter(
            Inventory.product_id == fg_product.id
        ).first()

        finished_goods_shipped = {
            "product_sku": fg_product.sku,
            "quantity_shipped": qty_shipped,
            "inventory_remaining": float(fg_inventory.on_hand_quantity) if fg_inventory else 0,
            "journal_entry_id": journal_entry.id if journal_entry else None,
        }

    # Update order
    order.tracking_number = result.tracking_number
    order.carrier = result.carrier
    order.shipping_cost = Decimal(str(result.rate)) if result.rate else None
    order.status = "shipped"
    order.shipped_at = datetime.now(timezone.utc)

    # =========================================================================
    # SERIAL NUMBER TRACEABILITY - Link serials to this shipment
    # =========================================================================
    serials_updated = 0
    serial_numbers_for_order = db.query(SerialNumber).filter(
        SerialNumber.sales_order_id == sales_order_id,
        SerialNumber.status.in_(["manufactured", "in_stock", "allocated"])
    ).all()

    for serial in serial_numbers_for_order:
        serial.tracking_number = result.tracking_number
        serial.shipped_at = datetime.now(timezone.utc)
        serial.status = "shipped"
        serials_updated += 1

    if serials_updated > 0:
        from app.logging_config import get_logger
        logger = get_logger(__name__)
        logger.info(
            f"Updated {serials_updated} serial number(s) with tracking {result.tracking_number} "
            f"for order {order.order_number}"
        )

    db.commit()

    return {
        "success": True,
        "order_number": order.order_number,
        "tracking_number": result.tracking_number,
        "carrier": result.carrier,
        "label_url": result.label_url,
        "shipping_cost": float(result.rate) if result.rate else None,
        "packaging_consumed": packaging_consumed,
        "finished_goods_shipped": finished_goods_shipped,
        "serials_updated": serials_updated,
        "message": f"Label created! Tracking: {result.tracking_number}",
    }


# =============================================================================
# SHIP-FROM-STOCK (SFS) - Direct shipping without production
# =============================================================================

@router.post(
    "/ship-from-stock/{sales_order_id}/check",
    summary="Check if order can ship from stock",
    description="Verify FG inventory is available to fulfill this order without production."
)
async def check_ship_from_stock(
    sales_order_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Check if a sales order can be fulfilled directly from existing FG inventory.

    Returns:
        - can_ship: bool - True if sufficient FG on hand
        - available_qty: int - Current FG available (on_hand - allocated)
        - required_qty: int - Quantity needed for this order
        - product_info: dict - Product details
    """
    # 1. Get the sales order
    order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")

    # 2. Verify order is in a shippable state (not already shipped, not cancelled)
    if order.status in ["shipped", "cancelled", "delivered"]:
        raise HTTPException(
            status_code=400,
            detail=f"Order cannot be shipped - status is {order.status}"
        )

    # 3. Get product from quote
    quote = db.query(Quote).filter(Quote.id == order.quote_id).first() if order.quote_id else None
    if not quote or not quote.product_id:
        raise HTTPException(
            status_code=400,
            detail="Order has no linked product - cannot determine what to ship"
        )

    product = db.query(Product).filter(Product.id == quote.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # 4. Check FG inventory
    fg_inventory = db.query(Inventory).filter(
        Inventory.product_id == product.id
    ).first()

    on_hand = int(fg_inventory.on_hand_quantity) if fg_inventory else 0
    allocated = int(fg_inventory.allocated_quantity) if fg_inventory else 0
    available = on_hand - allocated
    required = order.quantity or 1

    # 5. Check for existing production orders (might be MTO path)
    existing_po = db.query(ProductionOrder).filter(
        ProductionOrder.sales_order_id == sales_order_id,
        ProductionOrder.status.notin_(["cancelled", "shipped"])
    ).first()

    return {
        "sales_order_id": sales_order_id,
        "order_number": order.order_number,
        "can_ship": available >= required,
        "available_qty": available,
        "on_hand_qty": on_hand,
        "allocated_qty": allocated,
        "required_qty": required,
        "has_production_order": existing_po is not None,
        "production_order_status": existing_po.status if existing_po else None,
        "product_info": {
            "id": product.id,
            "sku": product.sku,
            "name": product.name,
        },
        "recommendation": "ready_to_ship" if available >= required else "needs_production",
    }


@router.post(
    "/ship-from-stock/{sales_order_id}/ship",
    summary="Ship order directly from FG inventory",
    description="Ship from existing FG inventory without production. Reuses get-rates for shipping quotes."
)
async def ship_from_stock(
    sales_order_id: int,
    request: ShipFromStockRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Ship a sales order directly from existing FG inventory (Ship-from-Stock path).

    Prerequisites:
        1. Call GET /ship/{so_id}/get-rates to get shipping rates
        2. Call POST /ship-from-stock/{so_id}/check to verify availability
        3. Call this endpoint with rate_id and shipment_id from step 1

    Flow:
        1. Verify FG availability
        2. Buy shipping label (reuses EasyPost shipment)
        3. Issue FG from inventory with GL entry
        4. Consume packaging with GL entry (if specified)
        5. Update serial numbers (if any)
        6. Update order status to shipped
    """
    # 1. Get and validate sales order
    order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")

    if order.status in ["shipped", "cancelled", "delivered"]:
        raise HTTPException(
            status_code=400,
            detail=f"Order cannot be shipped - status is {order.status}"
        )

    # 2. Get product from quote
    quote = db.query(Quote).filter(Quote.id == order.quote_id).first() if order.quote_id else None
    if not quote or not quote.product_id:
        raise HTTPException(status_code=400, detail="Order has no linked product")

    product = db.query(Product).filter(Product.id == quote.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # 3. Verify FG inventory availability
    fg_inventory = db.query(Inventory).filter(Inventory.product_id == product.id).first()
    qty_to_ship = order.quantity or 1

    if not fg_inventory:
        raise HTTPException(
            status_code=400,
            detail=f"No inventory record for product {product.sku}"
        )

    available = int(fg_inventory.on_hand_quantity) - int(fg_inventory.allocated_quantity)
    if available < qty_to_ship:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient FG inventory. Available: {available}, Required: {qty_to_ship}"
        )

    # 4. Buy shipping label (reuse EasyPost shipment from get-rates)
    result = shipping_service.buy_label(
        shipment_id=request.shipment_id,
        rate_id=request.rate_id,
    )

    if not result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to purchase shipping label: {result.error}"
        )

    # 5. Ship via TransactionService (FG issue + optional packaging)
    txn_service = TransactionService(db)
    packaging_consumed = []
    finished_goods_shipped = None

    # Build shipment items
    fg_cost = product.standard_cost if product.standard_cost else (
        product.cost if product.cost else Decimal("0")
    )
    shipment_items = [ShipmentItem(
        product_id=product.id,
        quantity=Decimal(str(qty_to_ship)),
        unit_cost=fg_cost,
    )]

    # Handle packaging if specified
    packaging_list = []
    if request.packaging_product_id:
        pkg_product = db.query(Product).filter(
            Product.id == request.packaging_product_id
        ).first()
        if pkg_product:
            pkg_qty = request.packaging_quantity or 1
            pkg_cost = pkg_product.cost if pkg_product.cost else Decimal("0")

            # Verify packaging inventory
            pkg_inventory = db.query(Inventory).filter(
                Inventory.product_id == pkg_product.id
            ).first()
            if pkg_inventory and int(pkg_inventory.on_hand_quantity) >= pkg_qty:
                packaging_list.append(PackagingUsed(
                    product_id=pkg_product.id,
                    quantity=pkg_qty,
                    unit_cost=pkg_cost,
                ))
                packaging_consumed.append({
                    "component_sku": pkg_product.sku,
                    "quantity_consumed": pkg_qty,
                })

    # Execute shipment
    inv_txns, journal_entry = txn_service.ship_order(
        sales_order_id=sales_order_id,
        items=shipment_items,
        packaging=packaging_list if packaging_list else None,
    )

    # Get updated inventory for response
    fg_inventory = db.query(Inventory).filter(
        Inventory.product_id == product.id
    ).first()

    finished_goods_shipped = {
        "product_sku": product.sku,
        "quantity_shipped": qty_to_ship,
        "inventory_remaining": float(fg_inventory.on_hand_quantity) if fg_inventory else 0,
        "journal_entry_id": journal_entry.id if journal_entry else None,
    }

    # 6. Update serial numbers if any exist
    serials_updated = 0
    serials = db.query(SerialNumber).filter(
        SerialNumber.sales_order_id == sales_order_id,
        SerialNumber.status.in_(["manufactured", "in_stock", "allocated"])
    ).all()
    for serial in serials:
        serial.status = "shipped"
        serial.tracking_number = result.tracking_number
        serial.shipped_at = datetime.now(timezone.utc)
        serials_updated += 1

    # 7. Update order status
    order.status = "shipped"
    order.tracking_number = result.tracking_number
    order.carrier = result.carrier
    order.shipping_cost = Decimal(str(result.rate)) if result.rate else None
    order.shipped_at = datetime.now(timezone.utc)

    db.commit()

    return {
        "success": True,
        "order_number": order.order_number,
        "fulfillment_type": "ship_from_stock",
        "tracking_number": result.tracking_number,
        "carrier": result.carrier,
        "label_url": result.label_url,
        "shipping_cost": float(result.rate) if result.rate else None,
        "finished_goods_shipped": finished_goods_shipped,
        "packaging_consumed": packaging_consumed,
        "serials_updated": serials_updated,
        "message": f"Shipped from stock! Tracking: {result.tracking_number}",
    }


@router.post("/ship/{sales_order_id}/mark-shipped")
async def mark_order_shipped(
    sales_order_id: int,
    request: ShipOrderRequest,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_staff_user),
):
    """
    Manually mark an order as shipped (for when label was created outside system).

    Updates tracking info and optionally sends notification to customer.
    """
    order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")

    # Update order
    order.tracking_number = request.tracking_number
    order.carrier = request.carrier
    if request.shipping_cost:
        order.shipping_cost = Decimal(str(request.shipping_cost))
    order.status = "shipped"
    order.shipped_at = datetime.now(timezone.utc)

    # Update serial numbers with tracking info for traceability
    serials_updated = 0
    serial_numbers_for_order = db.query(SerialNumber).filter(
        SerialNumber.sales_order_id == sales_order_id,
        SerialNumber.status.in_(["manufactured", "in_stock", "allocated"])
    ).all()

    for serial in serial_numbers_for_order:
        serial.tracking_number = request.tracking_number
        serial.shipped_at = datetime.now(timezone.utc)
        serial.status = "shipped"
        serials_updated += 1

    # =========================================================================
    # FINISHED GOODS SHIPMENT - Issue finished goods from inventory
    # =========================================================================
    finished_goods_shipped = None
    if order.quote_id:
        quote = db.query(Quote).filter(Quote.id == order.quote_id).first()
        if quote and quote.product_id:
            fg_inventory = db.query(Inventory).filter(
                Inventory.product_id == quote.product_id
            ).first()

            if fg_inventory:
                qty_shipped = order.quantity or 1

                # Decrement inventory
                fg_inventory.on_hand_quantity = Decimal(str(
                    max(0, float(fg_inventory.on_hand_quantity) - qty_shipped)
                ))

                # Get product for cost calculation
                product = db.query(Product).filter(Product.id == quote.product_id).first()
                from app.services.inventory_service import get_effective_cost_per_inventory_unit
                unit_cost = get_effective_cost_per_inventory_unit(product) if product else None
                total_cost = Decimal(str(qty_shipped)) * unit_cost if unit_cost else None

                # Create shipment transaction
                shipment_txn = InventoryTransaction(
                    product_id=quote.product_id,
                    location_id=fg_inventory.location_id,
                    transaction_type="shipment",
                    reference_type="sales_order",
                    reference_id=sales_order_id,
                    quantity=Decimal(str(-qty_shipped)),  # Negative = outgoing
                    cost_per_unit=unit_cost,
                    total_cost=total_cost,
                    unit=product.unit if product else "EA",
                    notes=f"Shipped {qty_shipped} units for {order.order_number}",
                    created_by="system",
                )
                db.add(shipment_txn)
                finished_goods_shipped = {
                    "product_sku": product.sku if product else "N/A",
                    "quantity_shipped": qty_shipped,
                    "inventory_remaining": float(fg_inventory.on_hand_quantity),
                }

    db.commit()

    # Future: Send email notification when request.notify_customer is set

    return {
        "success": True,
        "order_number": order.order_number,
        "status": order.status,
        "tracking_number": order.tracking_number,
        "carrier": order.carrier,
        "finished_goods_shipped": finished_goods_shipped,
        "serials_updated": serials_updated,
        "message": f"Order {order.order_number} marked as shipped!",
    }
