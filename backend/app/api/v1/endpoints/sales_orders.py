"""
Sales Order Management Endpoints

Handles converting quotes to sales orders and order lifecycle management.
"""
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.models.user import User
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.product import Product
from app.models.material import MaterialInventory
from app.models.shipping_event import ShippingEvent
from app.logging_config import get_logger
from app.schemas.sales_order import (
    SalesOrderCreate,
    SalesOrderConvert,
    SalesOrderResponse,
    SalesOrderLineResponse,
    SalesOrderListResponse,
    SalesOrderUpdateStatus,
    SalesOrderUpdatePayment,
    SalesOrderUpdateShipping,
    SalesOrderUpdateAddress,
    SalesOrderCancel,
    SalesOrderEditLines,
    SalesOrderCloseShort,
)
from app.schemas.order_event import (
    OrderEventCreate,
    OrderEventResponse,
    OrderEventListResponse,
)
from app.schemas.shipping_event import (
    ShippingEventCreate,
    ShippingEventResponse,
    ShippingEventListResponse,
)
from app.api.v1.endpoints.auth import get_current_user
from app.services.event_service import record_shipping_event
from app.core.status_config import (
    SalesOrderStatus,
    PaymentStatus,
    get_allowed_sales_order_transitions,
)
from app.schemas.blocking_issues import SalesOrderBlockingIssues
from app.services.blocking_issues import get_sales_order_blocking_issues
from app.schemas.fulfillment_status import FulfillmentStatus
from app.services.fulfillment_status import get_fulfillment_status
from app.services import sales_order_service

logger = get_logger(__name__)

router = APIRouter(prefix="/sales-orders", tags=["Sales Orders"])


# =============================================================================
# Response Builders
# =============================================================================

def build_sales_order_response(order: SalesOrder, db: Session) -> SalesOrderResponse:
    """Build sales order response with line items."""
    lines = []
    if order.order_type == "line_item":
        order_lines = db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == order.id
        ).order_by(SalesOrderLine.id).all()

        for line in order_lines:
            line_total = line.total if line.total else (line.unit_price * line.quantity)

            # Resolve product or material info
            product_sku = None
            product_name = None
            material_sku = None
            material_name = None

            if line.product_id:
                product = db.query(Product).filter(Product.id == line.product_id).first()
                product_sku = product.sku if product else ""
                product_name = product.name if product else ""
            elif line.material_inventory_id:
                material = db.query(MaterialInventory).filter(
                    MaterialInventory.id == line.material_inventory_id
                ).first()
                material_sku = material.sku if material else ""
                material_name = material.display_name if material else ""

            lines.append(SalesOrderLineResponse(
                id=line.id,
                product_id=line.product_id,
                material_inventory_id=line.material_inventory_id,
                product_sku=product_sku,
                product_name=product_name,
                material_sku=material_sku,
                material_name=material_name,
                quantity=line.quantity if line.quantity else Decimal("0"),
                unit_price=line.unit_price,
                total=line_total,
                discount=line.discount or Decimal("0"),
                allocated_quantity=line.allocated_quantity or Decimal("0"),
                shipped_quantity=line.shipped_quantity or Decimal("0"),
                original_quantity=line.original_quantity,
                notes=line.notes,
            ))

    order_data = {
        "id": order.id,
        "user_id": order.user_id,
        "quote_id": order.quote_id,
        "product_id": getattr(order, "product_id", None),
        "order_number": order.order_number,
        "order_type": order.order_type,
        "source": order.source,
        "source_order_id": order.source_order_id,
        "product_name": order.product_name,
        "quantity": int(order.quantity) if order.quantity else 0,
        "material_type": order.material_type,
        "finish": order.finish,
        "unit_price": order.unit_price,
        "total_price": order.total_price,
        "tax_amount": order.tax_amount if order.tax_amount is not None else Decimal("0"),
        "shipping_cost": order.shipping_cost if order.shipping_cost is not None else Decimal("0"),
        "grand_total": order.grand_total,
        "status": order.status,
        "fulfillment_status": getattr(order, "fulfillment_status", "pending"),
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "payment_transaction_id": order.payment_transaction_id,
        "paid_at": getattr(order, "paid_at", None),
        "estimated_completion_date": getattr(order, "estimated_completion_date", None),
        "actual_completion_date": getattr(order, "actual_completion_date", None),
        "customer_id": getattr(order, "customer_id", None),
        "customer_name": getattr(order, "customer_name", None),
        "customer_email": getattr(order, "customer_email", None),
        "customer_phone": getattr(order, "customer_phone", None),
        "shipping_address_line1": order.shipping_address_line1,
        "shipping_address_line2": order.shipping_address_line2,
        "shipping_city": order.shipping_city,
        "shipping_state": order.shipping_state,
        "shipping_zip": order.shipping_zip,
        "shipping_country": order.shipping_country,
        "tracking_number": order.tracking_number,
        "carrier": order.carrier,
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
        "rush_level": order.rush_level,
        "customer_notes": order.customer_notes,
        "internal_notes": order.internal_notes,
        "production_notes": order.production_notes,
        "cancelled_at": getattr(order, "cancelled_at", None),
        "cancellation_reason": order.cancellation_reason,
        "closed_short": getattr(order, "closed_short", False),
        "closed_short_at": getattr(order, "closed_short_at", None),
        "close_short_reason": getattr(order, "close_short_reason", None),
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "confirmed_at": getattr(order, "confirmed_at", None),
        "lines": lines,
    }

    return SalesOrderResponse.model_validate(order_data)


# =============================================================================
# Status Transitions Metadata
# =============================================================================

@router.get("/status-transitions")
async def get_sales_order_status_transitions(
    current_status: Optional[str] = Query(None, description="Get transitions for a specific status"),
    current_user: User = Depends(get_current_user),
):
    """
    Get valid status transitions for sales orders.

    Returns:
    - All valid statuses and their allowed transitions
    - If current_status is provided, returns only transitions for that status
    """
    all_statuses = [s.value for s in SalesOrderStatus]

    if current_status:
        if current_status not in all_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{current_status}'. Must be one of: {', '.join(all_statuses)}"
            )
        allowed = get_allowed_sales_order_transitions(current_status)
        return {
            "current_status": current_status,
            "allowed_transitions": allowed,
            "is_terminal": len(allowed) == 0,
        }

    transitions = {}
    for order_status in SalesOrderStatus:
        allowed = get_allowed_sales_order_transitions(order_status.value)
        transitions[order_status.value] = {
            "allowed_transitions": allowed,
            "is_terminal": len(allowed) == 0,
        }

    return {
        "statuses": all_statuses,
        "transitions": transitions,
        "terminal_statuses": [s.value for s in SalesOrderStatus if len(get_allowed_sales_order_transitions(s.value)) == 0],
    }


@router.get("/payment-statuses")
async def get_payment_statuses(
    current_user: User = Depends(get_current_user),
):
    """Get valid payment status values for sales orders."""
    return {
        "statuses": [s.value for s in PaymentStatus],
        "descriptions": {
            PaymentStatus.PENDING.value: "Payment not yet received",
            PaymentStatus.PARTIAL.value: "Partial payment received",
            PaymentStatus.PAID.value: "Full payment received",
            PaymentStatus.REFUNDED.value: "Payment refunded",
            PaymentStatus.OVERDUE.value: "Payment is overdue",
        },
    }


# =============================================================================
# CRUD Endpoints
# =============================================================================

@router.post("/", response_model=SalesOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_sales_order(
    request: SalesOrderCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a manual sales order (line_item type).

    This endpoint creates a line-item based sales order for standard products.
    Use this for orders from manual entry, Squarespace, WooCommerce, etc.
    """
    lines = [
        {
            "product_id": line.product_id,
            "material_inventory_id": line.material_inventory_id,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "notes": line.notes,
        }
        for line in request.lines
    ]

    order = sales_order_service.create_sales_order(
        db,
        customer_id=request.customer_id,
        lines=lines,
        source=request.source or "manual",
        source_order_id=request.source_order_id,
        shipping_address_line1=request.shipping_address_line1,
        shipping_address_line2=request.shipping_address_line2,
        shipping_city=request.shipping_city,
        shipping_state=request.shipping_state,
        shipping_zip=request.shipping_zip,
        shipping_country=request.shipping_country or "USA",
        shipping_cost=request.shipping_cost or Decimal("0"),
        customer_notes=request.customer_notes,
        internal_notes=request.internal_notes,
        created_by_user_id=current_user.id,
    )

    db.commit()
    db.refresh(order)

    # Trigger MRP check if enabled
    try:
        from app.services.mrp_trigger_service import trigger_mrp_check
        from app.core.settings import get_settings
        settings = get_settings()

        if settings.AUTO_MRP_ON_ORDER_CREATE:
            trigger_mrp_check(db, order.id)
    except Exception as e:
        logger.warning(f"MRP trigger failed for sales order {order.id}: {str(e)}", exc_info=True)

    return order


@router.post("/convert/{quote_id}", response_model=SalesOrderResponse, status_code=status.HTTP_201_CREATED)
async def convert_quote_to_sales_order(
    quote_id: int,
    convert_request: SalesOrderConvert,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Convert an accepted quote to a sales order.

    Requirements:
    - Quote must exist and belong to current user
    - Quote must be in 'accepted' status
    - Quote must have associated product
    - Quote must not be expired or already converted
    """
    order = sales_order_service.convert_quote_to_sales_order(
        db,
        quote_id=quote_id,
        user_id=current_user.id,
        shipping_address_line1=convert_request.shipping_address_line1,
        shipping_address_line2=convert_request.shipping_address_line2,
        shipping_city=convert_request.shipping_city,
        shipping_state=convert_request.shipping_state,
        shipping_zip=convert_request.shipping_zip,
        shipping_country=convert_request.shipping_country or "USA",
        customer_notes=convert_request.customer_notes,
    )

    db.commit()
    db.refresh(order)

    return order


# Fulfillment filtering constants
VALID_FULFILLMENT_STATES = {"ready_to_ship", "partially_ready", "blocked", "shipped", "cancelled"}
FULFILLMENT_PRIORITY = {
    "ready_to_ship": 1,
    "partially_ready": 2,
    "blocked": 3,
    "shipped": 4,
    "cancelled": 5,
}


@router.get("/", response_model=List[SalesOrderListResponse])
async def get_user_sales_orders(
    skip: int = 0,
    limit: int = 50,
    status_filter: Optional[str] = None,
    status: Optional[List[str]] = Query(None),
    include_fulfillment: bool = Query(False, description="Include fulfillment status summary"),
    fulfillment_state: Optional[str] = Query(
        None,
        description="Filter by fulfillment state(s), comma-separated"
    ),
    sort_by: str = Query("order_date", description="Sort field"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    source: Optional[str] = Query(None, description="Filter by source (manual, portal, api, squarespace, woocommerce)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get list of sales orders.

    Query parameters:
    - skip: Pagination offset
    - limit: Max results (max: 100)
    - status_filter: Filter by single status (deprecated)
    - status: Filter by status(es)
    - include_fulfillment: Include fulfillment status summary
    - fulfillment_state: Filter by fulfillment state(s), comma-separated
    - sort_by: Sort field (order_date, fulfillment_priority, fulfillment_percent, customer_name)
    - sort_order: Sort order (asc or desc)
    - source: Filter by order source
    """
    if limit > 100:
        limit = 100

    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort_order must be 'asc' or 'desc'")

    valid_sort_fields = {"order_date", "fulfillment_priority", "fulfillment_percent", "customer_name"}
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {', '.join(valid_sort_fields)}"
        )

    # Parse fulfillment_state filter
    requested_states = None
    if fulfillment_state:
        requested_states = set(s.strip().lower() for s in fulfillment_state.split(","))
        invalid_states = requested_states - VALID_FULFILLMENT_STATES
        if invalid_states:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid fulfillment_state value(s): {', '.join(invalid_states)}"
            )

    is_admin = current_user.account_type == "admin"

    # Check if we need fulfillment data for filtering/sorting
    needs_fulfillment = (
        include_fulfillment or
        fulfillment_state is not None or
        sort_by in ("fulfillment_priority", "fulfillment_percent")
    )

    if needs_fulfillment:
        # Fetch all orders for fulfillment processing
        orders = sales_order_service.list_sales_orders(
            db,
            user_id=current_user.id,
            is_admin=is_admin,
            status_filter=status_filter,
            statuses=status,
            source=source,
            skip=0,
            limit=10000,  # Get all for fulfillment filtering
            sort_by="order_date",
            sort_order="desc",
        )

        # Compute fulfillment for each order
        orders_with_fulfillment = []
        for order in orders:
            order_dict = SalesOrderListResponse.model_validate(order).model_dump()
            fulfillment_data = get_fulfillment_status(db, order.id)
            if fulfillment_data:
                order_dict["fulfillment"] = fulfillment_data.summary
            orders_with_fulfillment.append(order_dict)

        # Filter by fulfillment_state
        if requested_states:
            orders_with_fulfillment = [
                o for o in orders_with_fulfillment
                if o.get("fulfillment") and o["fulfillment"].state.value in requested_states
            ]

        # Sort
        reverse = sort_order == "desc"
        if sort_by == "order_date":
            orders_with_fulfillment.sort(key=lambda o: o.get("created_at") or "", reverse=reverse)
        elif sort_by == "fulfillment_priority":
            orders_with_fulfillment.sort(
                key=lambda o: FULFILLMENT_PRIORITY.get(
                    o["fulfillment"].state.value if o.get("fulfillment") else "cancelled", 5
                ),
                reverse=reverse
            )
        elif sort_by == "fulfillment_percent":
            orders_with_fulfillment.sort(
                key=lambda o: o["fulfillment"].fulfillment_percent if o.get("fulfillment") else 0,
                reverse=reverse
            )
        elif sort_by == "customer_name":
            orders_with_fulfillment.sort(
                key=lambda o: (o.get("customer_name") or "").lower(),
                reverse=reverse
            )

        # Paginate
        paginated = orders_with_fulfillment[skip:skip + limit]
        return [SalesOrderListResponse(**o) for o in paginated]

    # No fulfillment needed - use service with pagination
    orders = sales_order_service.list_sales_orders(
        db,
        user_id=current_user.id,
        is_admin=is_admin,
        status_filter=status_filter,
        statuses=status,
        source=source,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return orders


@router.get("/{order_id}", response_model=SalesOrderResponse)
async def get_sales_order_details(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get detailed information about a specific sales order."""
    order = sales_order_service.get_sales_order(db, order_id)

    # Verify access
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if order.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")

    return build_sales_order_response(order, db)


# =============================================================================
# PDF Generation
# =============================================================================

@router.get("/{order_id}/packing-slip/pdf")
async def get_packing_slip_pdf(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate and return a packing slip PDF for a sales order."""
    from starlette.responses import StreamingResponse

    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can generate packing slips")

    pdf_buffer = sales_order_service.generate_packing_slip_pdf(db, order_id)

    # Get order number for filename
    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
    filename = f"packing-slip-{order.order_number}.pdf" if order else f"packing-slip-{order_id}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        },
    )


# =============================================================================
# MRP / Requirements Endpoints
# =============================================================================

@router.get("/{order_id}/required-orders")
async def get_required_orders_for_sales_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get full MRP cascade of WOs and POs needed to fulfill this sales order.

    Admin only.
    """
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can view MRP requirements")

    return sales_order_service.get_required_orders_for_sales_order(db, order_id)


@router.get("/{order_id}/blocking-issues", response_model=SalesOrderBlockingIssues)
async def get_blocking_issues(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get blocking issues analysis for a sales order."""
    result = get_sales_order_blocking_issues(db, order_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Sales order {order_id} not found")
    return result


@router.get("/{order_id}/fulfillment-status", response_model=FulfillmentStatus)
async def get_order_fulfillment_status(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get fulfillment status for a sales order."""
    result = get_fulfillment_status(db, order_id)
    if not result:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return result


class MaterialRequirementItem(BaseModel):
    """Single material requirement for a sales order."""
    product_id: int
    product_sku: str
    product_name: str
    unit: str
    quantity_required: Decimal
    quantity_available: Decimal
    quantity_short: Decimal
    operation_code: Optional[str] = None
    material_source: str
    has_incoming_supply: bool = False
    incoming_supply_details: Optional[dict] = None


class MaterialRequirementsResponse(BaseModel):
    """Material requirements for a sales order."""
    sales_order_id: int
    order_number: str
    requirements: List[MaterialRequirementItem]
    summary: dict


@router.get("/{order_id}/material-requirements", response_model=MaterialRequirementsResponse)
async def get_material_requirements(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get material requirements for a sales order.

    Uses routing-first approach for operation-level materials,
    falls back to BOM if no routing materials exist.
    """
    order = sales_order_service.get_sales_order(db, order_id)

    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if order.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this order")

    return sales_order_service.get_material_requirements(db, order_id)


@router.post("/{order_id}/pre-flight-check")
async def pre_flight_check(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Pre-flight check before confirming a sales order.

    Quick validation to check if all materials are available.
    """
    mat_req_result = sales_order_service.get_material_requirements(db, order_id)

    shortages = [
        {
            "product_sku": r["product_sku"],
            "product_name": r["product_name"],
            "quantity_required": float(r["quantity_required"]),
            "quantity_available": float(r["quantity_available"]),
            "quantity_short": float(r["quantity_short"]),
            "has_incoming_supply": r["has_incoming_supply"],
            "incoming_supply_details": r["incoming_supply_details"]
        }
        for r in mat_req_result["requirements"]
        if r["quantity_short"] > 0
    ]

    warnings = []
    for shortage in shortages:
        if shortage["has_incoming_supply"]:
            details = shortage["incoming_supply_details"]
            expected = details.get("expected_date", "unknown") if details else "unknown"
            warnings.append({
                "type": "incoming_supply",
                "message": f"{shortage['product_sku']} has pending PO, expected {expected}",
                "product_sku": shortage["product_sku"]
            })

    return {
        "sales_order_id": order_id,
        "order_number": mat_req_result["order_number"],
        "can_proceed": len(shortages) == 0,
        "shortages": shortages,
        "warnings": warnings,
        "summary": mat_req_result["summary"]
    }


# =============================================================================
# Status Update Endpoints
# =============================================================================

@router.patch("/{order_id}/status", response_model=SalesOrderResponse)
async def update_order_status(
    order_id: int,
    update: SalesOrderUpdateStatus,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update sales order status (admin only)."""
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can update order status")

    order = sales_order_service.update_sales_order_status(
        db,
        order_id=order_id,
        new_status=update.status,
        user_id=current_user.id,
        user_email=current_user.email,
        internal_notes=update.internal_notes,
        production_notes=update.production_notes,
    )

    db.commit()
    db.refresh(order)

    return order


@router.patch("/{order_id}/payment", response_model=SalesOrderResponse)
async def update_payment_info(
    order_id: int,
    update: SalesOrderUpdatePayment,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update payment information for an order (admin only)."""
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can update payment information")

    order = sales_order_service.update_payment_info(
        db,
        order_id=order_id,
        payment_status=update.payment_status,
        user_id=current_user.id,
        payment_method=update.payment_method,
        payment_transaction_id=update.payment_transaction_id,
    )

    db.commit()
    db.refresh(order)

    return order


@router.patch("/{order_id}/shipping", response_model=SalesOrderResponse)
async def update_shipping_info(
    order_id: int,
    update: SalesOrderUpdateShipping,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update shipping information for an order (admin only)."""
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can update shipping information")

    order = sales_order_service.update_shipping_info(
        db,
        order_id=order_id,
        user_id=current_user.id,
        tracking_number=update.tracking_number,
        carrier=update.carrier,
        shipped_at=update.shipped_at,
    )

    db.commit()
    db.refresh(order)

    return order


@router.patch("/{order_id}/address", response_model=SalesOrderResponse)
async def update_shipping_address(
    order_id: int,
    update: SalesOrderUpdateAddress,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update shipping address for an order (admin only)."""
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can update shipping address")

    order = sales_order_service.update_shipping_address(
        db,
        order_id=order_id,
        user_id=current_user.id,
        shipping_address_line1=update.shipping_address_line1,
        shipping_address_line2=update.shipping_address_line2,
        shipping_city=update.shipping_city,
        shipping_state=update.shipping_state,
        shipping_zip=update.shipping_zip,
        shipping_country=update.shipping_country,
    )

    db.commit()
    db.refresh(order)

    return order


# =============================================================================
# Cancel / Delete Endpoints
# =============================================================================

@router.post("/{order_id}/cancel", response_model=SalesOrderResponse)
async def cancel_sales_order(
    order_id: int,
    cancel_request: SalesOrderCancel,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cancel a sales order.

    Requirements:
    - Order must be cancellable (pending, confirmed, or on_hold)
    - User must own the order OR be an admin
    """
    order = sales_order_service.get_sales_order(db, order_id)

    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if order.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this order")

    order = sales_order_service.cancel_sales_order(
        db,
        order_id=order_id,
        user_id=current_user.id,
        cancellation_reason=cancel_request.cancellation_reason,
    )

    db.commit()
    db.refresh(order)

    return order


@router.patch("/{order_id}/lines", response_model=SalesOrderResponse)
async def edit_order_lines(
    order_id: int,
    edit_request: SalesOrderEditLines,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Edit line item quantities on a sales order.

    Admin only. Allowed on orders with status: confirmed, in_production, on_hold.
    Cannot reduce quantity below already-shipped amount.
    """
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    line_updates = [
        {"line_id": ln.line_id, "new_quantity": ln.new_quantity, "reason": ln.reason}
        for ln in edit_request.lines
    ]

    order = sales_order_service.edit_sales_order_lines(
        db, order_id=order_id, line_updates=line_updates, user_id=current_user.id
    )
    return build_sales_order_response(order, db)


@router.post("/{order_id}/close-short", response_model=SalesOrderResponse)
async def close_short_order(
    order_id: int,
    close_request: SalesOrderCloseShort,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Close an order short — accept partial fulfillment and complete.

    Admin only. Adjusts line quantities to actual shipped/produced amounts,
    recalculates totals, and transitions to completed status.
    """
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    order = sales_order_service.close_short_sales_order(
        db, order_id=order_id, user_id=current_user.id, reason=close_request.reason
    )
    return build_sales_order_response(order, db)


class RejectRequest(BaseModel):
    """Rejection reason for external orders"""
    reason: str


@router.post("/{order_id}/confirm", response_model=SalesOrderResponse)
async def confirm_external_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Confirm a pending_confirmation order from an external source.

    Transitions the order from pending_confirmation to confirmed and sets confirmed_at.
    Admin only.
    """
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can confirm orders")

    order = sales_order_service.confirm_external_order(
        db,
        order_id=order_id,
        confirmed_by_user_id=current_user.id,
    )
    return order


@router.post("/{order_id}/reject", response_model=SalesOrderResponse)
async def reject_external_order(
    order_id: int,
    reject_request: RejectRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Reject a pending_confirmation order from an external source.

    Transitions the order from pending_confirmation to cancelled with a reason.
    Admin only.
    """
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can reject orders")

    if not reject_request.reason.strip():
        raise HTTPException(status_code=400, detail="Rejection reason cannot be empty")

    order = sales_order_service.reject_external_order(
        db,
        order_id=order_id,
        reason=reject_request.reason,
        rejected_by_user_id=current_user.id,
    )
    return order


@router.delete("/{order_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sales_order(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a sales order (admin only)."""
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can delete sales orders")

    sales_order_service.delete_sales_order(db, order_id)
    db.commit()

    return None


# =============================================================================
# Shipping / Production Endpoints
# =============================================================================

class ShipOrderRequest(BaseModel):
    """Request to ship an order."""
    carrier: str = "USPS"
    service: Optional[str] = "Priority"
    tracking_number: Optional[str] = None


@router.post("/{order_id}/ship")
async def ship_order(
    order_id: int,
    request: ShipOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create shipping label and mark order as shipped."""
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can ship orders")

    result = sales_order_service.ship_order(
        db,
        order_id=order_id,
        user_id=current_user.id,
        user_email=current_user.email,
        carrier=request.carrier,
        service=request.service,
        tracking_number=request.tracking_number,
    )

    db.commit()

    return result


@router.post("/{order_id}/generate-production-orders")
async def generate_production_orders(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate production orders from a sales order (admin only)."""
    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can generate production orders")

    result = sales_order_service.generate_production_orders(
        db,
        order_id=order_id,
        user_email=current_user.email,
    )

    db.commit()

    return result


# =============================================================================
# Order Events Endpoints
# =============================================================================

@router.get("/{order_id}/events", response_model=OrderEventListResponse)
async def get_order_events(
    order_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get activity timeline for a sales order."""
    order = sales_order_service.get_sales_order(db, order_id)

    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if order.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to view this order's events")

    events, total = sales_order_service.list_order_events(db, order_id, limit=limit, offset=offset)

    # Build response with user names
    items = []
    for event in events:
        user_name = None
        if event.user_id:
            user = db.query(User).filter(User.id == event.user_id).first()
            if user:
                user_name = user.full_name or user.email

        items.append(OrderEventResponse(
            id=event.id,
            sales_order_id=event.sales_order_id,
            user_id=event.user_id,
            user_name=user_name,
            event_type=event.event_type,
            title=event.title,
            description=event.description,
            old_value=event.old_value,
            new_value=event.new_value,
            metadata_key=event.metadata_key,
            metadata_value=event.metadata_value,
            created_at=event.created_at,
        ))

    return OrderEventListResponse(items=items, total=total)


@router.post("/{order_id}/events", response_model=OrderEventResponse, status_code=status.HTTP_201_CREATED)
async def add_order_event(
    order_id: int,
    event_data: OrderEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add an event to a sales order's activity timeline."""
    order = sales_order_service.get_sales_order(db, order_id)

    is_admin = getattr(current_user, "account_type", None) == "admin" or getattr(current_user, "is_admin", False)
    if order.user_id != current_user.id and not is_admin:
        raise HTTPException(status_code=403, detail="Not authorized to add events to this order")

    event = sales_order_service.add_order_event(
        db,
        order_id=order_id,
        user_id=current_user.id,
        event_type=event_data.event_type,
        title=event_data.title,
        description=event_data.description,
        old_value=event_data.old_value,
        new_value=event_data.new_value,
        metadata_key=event_data.metadata_key,
        metadata_value=event_data.metadata_value,
    )

    db.commit()
    db.refresh(event)

    user_name = current_user.full_name or current_user.email

    return OrderEventResponse(
        id=event.id,
        sales_order_id=event.sales_order_id,
        user_id=event.user_id,
        user_name=user_name,
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        old_value=event.old_value,
        new_value=event.new_value,
        metadata_key=event.metadata_key,
        metadata_value=event.metadata_value,
        created_at=event.created_at,
    )


# =============================================================================
# Shipping Events Endpoints
# =============================================================================

@router.get("/{order_id}/shipping-events", response_model=ShippingEventListResponse)
async def list_shipping_events(
    order_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List shipping events for a sales order."""
    # Verify order exists (raises 404 if not found)
    sales_order_service.get_sales_order(db, order_id)

    query = db.query(ShippingEvent).filter(
        ShippingEvent.sales_order_id == order_id
    ).order_by(desc(ShippingEvent.created_at))

    total = query.count()
    events = query.offset(offset).limit(limit).all()

    items = []
    for event in events:
        user_name = None
        if event.user_id and event.user:
            user_name = f"{event.user.first_name or ''} {event.user.last_name or ''}".strip() or event.user.email

        items.append(ShippingEventResponse(
            id=event.id,
            sales_order_id=event.sales_order_id,
            user_id=event.user_id,
            user_name=user_name,
            event_type=event.event_type,
            title=event.title,
            description=event.description,
            tracking_number=event.tracking_number,
            carrier=event.carrier,
            location_city=event.location_city,
            location_state=event.location_state,
            location_zip=event.location_zip,
            event_date=event.event_date,
            event_timestamp=event.event_timestamp,
            metadata_key=event.metadata_key,
            metadata_value=event.metadata_value,
            source=event.source,
            created_at=event.created_at,
        ))

    return ShippingEventListResponse(items=items, total=total)


@router.post("/{order_id}/shipping-events", response_model=ShippingEventResponse, status_code=201)
async def add_shipping_event(
    order_id: int,
    request: ShippingEventCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a shipping event to a sales order."""
    order = sales_order_service.get_sales_order(db, order_id)

    event = record_shipping_event(
        db=db,
        sales_order_id=order_id,
        event_type=request.event_type.value,
        title=request.title,
        description=request.description,
        tracking_number=request.tracking_number,
        carrier=request.carrier,
        location_city=request.location_city,
        location_state=request.location_state,
        location_zip=request.location_zip,
        event_date=request.event_date,
        event_timestamp=request.event_timestamp,
        user_id=current_user.id,
        metadata_key=request.metadata_key,
        metadata_value=request.metadata_value,
        source=request.source.value,
    )
    db.commit()
    db.refresh(event)

    user_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email

    logger.info(f"Added shipping event '{request.event_type.value}' to order {order.order_number}")

    return ShippingEventResponse(
        id=event.id,
        sales_order_id=event.sales_order_id,
        user_id=event.user_id,
        user_name=user_name,
        event_type=event.event_type,
        title=event.title,
        description=event.description,
        tracking_number=event.tracking_number,
        carrier=event.carrier,
        location_city=event.location_city,
        location_state=event.location_state,
        location_zip=event.location_zip,
        event_date=event.event_date,
        event_timestamp=event.event_timestamp,
        metadata_key=event.metadata_key,
        metadata_value=event.metadata_value,
        source=event.source,
        created_at=event.created_at,
    )
