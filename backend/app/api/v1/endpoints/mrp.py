"""
MRP (Material Requirements Planning) API Endpoints

Endpoints for:
- Running MRP calculations
- Managing planned orders
- Viewing requirements and supply/demand
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.models import MRPRun, PlannedOrder, Product
from app.models.user import User
from app.api.v1.deps import get_current_staff_user
from app.schemas.mrp import (
    MRPRunRequest, MRPRunResponse, MRPRunSummary,
    PlannedOrderResponse,
    PlannedOrderListResponse,
    FirmPlannedOrderRequest, ReleasePlannedOrderRequest, ReleasePlannedOrderResponse,
    RequirementsSummary, NetRequirement,
    SupplyDemandTimeline
)
from app.services.mrp import MRPService


router = APIRouter(
    prefix="/mrp",
    tags=["MRP"],
    dependencies=[Depends(get_current_staff_user)],
)


# ============================================================================
# MRP Run Endpoints
# ============================================================================

@router.post("/run", response_model=MRPRunResponse)
async def run_mrp(
    request: MRPRunRequest,
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db)
):
    """
    Run MRP calculation.

    This will:
    1. Analyze all production orders within the planning horizon
    2. Explode BOMs to calculate component requirements
    3. Net requirements against available inventory
    4. Generate planned orders for material shortages
    
    Requires admin authentication.
    """
    service = MRPService(db)

    try:
        result = service.run_mrp(
            planning_horizon_days=request.planning_horizon_days,
            include_draft_orders=request.include_draft_orders,
            regenerate_planned=request.regenerate_planned,
            user_id=current_user.id
        )

        # Get the MRP run record
        mrp_run = db.get(MRPRun, result.run_id)
        return mrp_run

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs", response_model=MRPRunSummary)
async def list_mrp_runs(
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List recent MRP runs"""
    runs = db.query(MRPRun).order_by(MRPRun.run_date.desc()).limit(limit).all()

    # Find last successful run
    last_success = db.query(MRPRun).filter(
        MRPRun.status == "completed"
    ).order_by(MRPRun.run_date.desc()).first()

    return MRPRunSummary(
        runs=runs,
        last_successful_run=last_success.run_date if last_success else None
    )


@router.get("/runs/{run_id}", response_model=MRPRunResponse)
async def get_mrp_run(
    run_id: int,
    db: Session = Depends(get_db)
):
    """Get details of a specific MRP run"""
    run = db.get(MRPRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="MRP run not found")
    return run


# ============================================================================
# Planned Order Endpoints
# ============================================================================

@router.get("/planned-orders", response_model=PlannedOrderListResponse)
async def list_planned_orders(
    status: Optional[str] = Query(None, description="Filter by status"),
    order_type: Optional[str] = Query(None, description="Filter by type (purchase/production)"),
    product_id: Optional[int] = Query(None, description="Filter by product"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """List planned orders with optional filters"""
    query = db.query(PlannedOrder)

    if status:
        query = query.filter(PlannedOrder.status == status)
    if order_type:
        query = query.filter(PlannedOrder.order_type == order_type)
    if product_id:
        query = query.filter(PlannedOrder.product_id == product_id)

    total = query.count()
    orders = query.order_by(PlannedOrder.due_date).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    # Enrich with product info
    items = []
    for order in orders:
        product = db.get(Product, order.product_id)
        items.append(PlannedOrderResponse(
            id=order.id,
            order_type=order.order_type,
            product_id=order.product_id,
            product_sku=product.sku if product else None,
            product_name=product.name if product else None,
            quantity=order.quantity,
            due_date=order.due_date,
            start_date=order.start_date,
            source_demand_type=order.source_demand_type,
            source_demand_id=order.source_demand_id,
            mrp_run_id=order.mrp_run_id,
            status=order.status,
            converted_to_po_id=order.converted_to_po_id,
            converted_to_mo_id=order.converted_to_mo_id,
            notes=order.notes,
            created_at=order.created_at,
            firmed_at=order.firmed_at,
            released_at=order.released_at
        ))

    return PlannedOrderListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/planned-orders/{order_id}", response_model=PlannedOrderResponse)
async def get_planned_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific planned order"""
    order = db.get(PlannedOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Planned order not found")

    product = db.get(Product, order.product_id)

    return PlannedOrderResponse(
        id=order.id,
        order_type=order.order_type,
        product_id=order.product_id,
        product_sku=product.sku if product else None,
        product_name=product.name if product else None,
        quantity=order.quantity,
        due_date=order.due_date,
        start_date=order.start_date,
        source_demand_type=order.source_demand_type,
        source_demand_id=order.source_demand_id,
        mrp_run_id=order.mrp_run_id,
        status=order.status,
        converted_to_po_id=order.converted_to_po_id,
        converted_to_mo_id=order.converted_to_mo_id,
        notes=order.notes,
        created_at=order.created_at,
        firmed_at=order.firmed_at,
        released_at=order.released_at
    )


@router.post("/planned-orders/{order_id}/firm", response_model=PlannedOrderResponse)
async def firm_planned_order(
    order_id: int,
    request: FirmPlannedOrderRequest,
    db: Session = Depends(get_db)
):
    """
    Firm a planned order.

    Firming locks the order so MRP regeneration won't delete it.
    Use this when you've confirmed you want to proceed with the order.
    """
    service = MRPService(db)

    try:
        order = service.firm_planned_order(
            planned_order_id=order_id,
            notes=request.notes
        )
        product = db.get(Product, order.product_id)

        return PlannedOrderResponse(
            id=order.id,
            order_type=order.order_type,
            product_id=order.product_id,
            product_sku=product.sku if product else None,
            product_name=product.name if product else None,
            quantity=order.quantity,
            due_date=order.due_date,
            start_date=order.start_date,
            source_demand_type=order.source_demand_type,
            source_demand_id=order.source_demand_id,
            mrp_run_id=order.mrp_run_id,
            status=order.status,
            converted_to_po_id=order.converted_to_po_id,
            converted_to_mo_id=order.converted_to_mo_id,
            notes=order.notes,
            created_at=order.created_at,
            firmed_at=order.firmed_at,
            released_at=order.released_at
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/planned-orders/{order_id}/release", response_model=ReleasePlannedOrderResponse)
async def release_planned_order(
    order_id: int,
    request: ReleasePlannedOrderRequest,
    db: Session = Depends(get_db)
):
    """
    Release a planned order to an actual PO or MO.

    For purchase orders, vendor_id is required.
    This creates the actual purchase order or production order.
    """
    service = MRPService(db)

    try:
        order, created_id = service.release_planned_order(
            planned_order_id=order_id,
            vendor_id=request.vendor_id,
            notes=request.notes
        )

        response = ReleasePlannedOrderResponse(
            planned_order_id=order.id,
            order_type=order.order_type
        )

        if order.order_type == "purchase":
            response.created_purchase_order_id = created_id
            # Get PO number
            from app.models import PurchaseOrder
            po = db.get(PurchaseOrder, created_id)
            response.created_purchase_order_code = po.po_number if po else None
        else:
            response.created_production_order_id = created_id
            # Get MO code
            from app.models import ProductionOrder
            mo = db.get(ProductionOrder, created_id)
            response.created_production_order_code = mo.code if mo else None

        return response

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/planned-orders/{order_id}")
async def cancel_planned_order(
    order_id: int,
    db: Session = Depends(get_db)
):
    """Cancel/delete a planned order"""
    order = db.get(PlannedOrder, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Planned order not found")

    if order.status == "released":
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel a released order"
        )

    order.status = "cancelled"
    db.commit()

    return {"message": "Planned order cancelled"}


# ============================================================================
# Requirements & Analysis Endpoints
# ============================================================================

@router.get("/requirements", response_model=RequirementsSummary)
async def get_requirements(
    product_id: Optional[int] = Query(None, description="Calculate for specific product"),
    production_order_id: Optional[int] = Query(None, description="Calculate for specific MO"),
    db: Session = Depends(get_db)
):
    """
    Calculate and return material requirements.

    Either provide a product_id to explode its BOM, or a production_order_id
    to see what materials are needed for that order.
    """
    service = MRPService(db)

    if production_order_id:
        from app.models import ProductionOrder
        mo = db.get(ProductionOrder, production_order_id)
        if not mo:
            raise HTTPException(status_code=404, detail="Production order not found")

        quantity = mo.quantity_ordered - mo.quantity_completed
        requirements = service.explode_bom(
            product_id=mo.product_id,
            quantity=quantity,
            source_demand_type="production_order",
            source_demand_id=mo.id,
            due_date=mo.due_date
        )
    elif product_id:
        requirements = service.explode_bom(
            product_id=product_id,
            quantity=1,
            source_demand_type="manual_query",
            source_demand_id=None
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Either product_id or production_order_id is required"
        )

    # Calculate net requirements
    net_requirements = service.calculate_net_requirements(requirements)

    shortages = [r for r in net_requirements if r.net_shortage > 0]

    # Convert to response schema
    response_requirements = [
        NetRequirement(
            product_id=r.product_id,
            product_sku=r.product_sku,
            product_name=r.product_name,
            gross_quantity=r.gross_quantity,
            on_hand_quantity=r.on_hand_quantity,
            allocated_quantity=r.allocated_quantity,
            available_quantity=r.available_quantity,
            incoming_quantity=r.incoming_quantity,
            safety_stock=r.safety_stock,
            net_shortage=r.net_shortage,
            lead_time_days=r.lead_time_days,
            reorder_point=r.reorder_point,
            min_order_qty=r.min_order_qty,
            has_bom=r.has_bom,
            unit_cost=r.unit_cost,
        )
        for r in net_requirements
    ]

    return RequirementsSummary(
        total_components_analyzed=len(net_requirements),
        shortages_found=len(shortages),
        components_in_stock=len(net_requirements) - len(shortages),
        requirements=response_requirements
    )


@router.get("/supply-demand/{product_id}", response_model=SupplyDemandTimeline)
async def get_supply_demand_timeline(
    product_id: int,
    days_ahead: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db)
):
    """
    Get supply and demand timeline for a product.

    Shows chronological view of incoming supply and outgoing demand
    with running balance projection.
    """
    service = MRPService(db)

    try:
        timeline = service.get_supply_demand_timeline(
            product_id=product_id,
            days_ahead=days_ahead
        )
        return SupplyDemandTimeline(**timeline)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# BOM Explosion Endpoint
# ============================================================================

@router.get("/explode-bom/{product_id}")
async def explode_bom(
    product_id: int,
    quantity: float = Query(1.0, gt=0),
    db: Session = Depends(get_db)
):
    """
    Explode a BOM to see all component requirements.

    This is a utility endpoint for viewing what components are needed
    for a given product and quantity.
    """
    from decimal import Decimal

    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    service = MRPService(db)
    requirements = service.explode_bom(
        product_id=product_id,
        quantity=Decimal(str(quantity)),
        source_demand_type="bom_explode",
        source_demand_id=None
    )

    return {
        "product_id": product_id,
        "product_sku": product.sku,
        "product_name": product.name,
        "quantity": quantity,
        "components": [
            {
                "product_id": r.product_id,
                "product_sku": r.product_sku,
                "product_name": r.product_name,
                "bom_level": r.bom_level,
                "gross_quantity": float(r.gross_quantity),
                "scrap_factor": float(r.scrap_factor),
                "parent_product_id": r.parent_product_id
            }
            for r in requirements
        ],
        "total_components": len(requirements)
    }
