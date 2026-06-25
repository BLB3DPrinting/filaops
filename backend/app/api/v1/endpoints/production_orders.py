"""
Production Orders API Endpoints

Manufacturing Orders (MOs) for tracking production of finished goods.
Supports creation from sales orders, manual entry, and MRP planning.
"""
from typing import Annotated, List, Optional
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.deps import get_pagination_params
from app.schemas.common import MessageResponse, PaginationParams
from app.models import User, Product, SalesOrder
from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.models.work_center import WorkCenter
from app.models.manufacturing import Resource
from app.models.printer import Printer
from app.schemas.production_order import (
    ProductionOrderCreate,
    ProductionOrderUpdate,
    ProductionOrderResponse,
    ProductionOrderScrapResponse,
    ProductionOrderListResponse,
    ProductionOrderOperationUpdate,
    ProductionOrderOperationResponse,
    ProductionOrderScheduleRequest,
    WorkCenterQueue,
    ProductionScheduleSummary,
    ProductionOrderSplitRequest,
    ProductionOrderSplitResponse,
    ScrapReasonCreate,
    ScrapReasonDetail,
    ScrapReasonUpdate,
    ProductionOrderCompleteRequest,
    ScrapReasonsResponse,
    QCInspectionRequest,
    QCInspectionResponse,
    QCInspectionRecord,
    QCInspectionHistoryResponse,
    OperationMaterialResponse,
    SwapMaterialVariantRequest,
    OperationScrapRequest,
    StatusTransitionsResponse,
    QCStatusesResponse,
    OperationStatusesResponse,
    MaterialAvailabilityResponse,
    RequiredOrdersResponse,
    CostBreakdownResponse,
    SpoolListItem,
    SpoolAssignmentResponse,
    AcceptShortRequest,
    CompatibilityIssueResponse,
    OperationCompatibilityResponse,
    OrderCompatibilityResponse,
)
from app.core.status_config import (
    ProductionOrderStatus,
    OperationStatus,
    QCStatus,
    get_allowed_production_order_transitions,
)
from app.schemas.blocking_issues import ProductionOrderBlockingIssues
from app.schemas.resource_scheduling import (
    RescheduleRequest,
    RescheduleResponse,
    UnscheduleResponse,
    ConflictInfo,
    SuccessorConflictInfo,
)
from app.services.blocking_issues import get_production_order_blocking_issues
from app.services import production_order_service
from app.services.resource_scheduling import (
    find_conflicts,
    find_next_available_slot,
    find_window_conflicts,
    check_predecessor_scheduling,
    check_successor_scheduling,
    get_earliest_start_after_predecessors,
    TERMINAL_STATUSES,
)
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Response Builders
# =============================================================================

def _build_operation_material_response(
    mat: ProductionOrderOperationMaterial, db: Session
) -> OperationMaterialResponse:
    """Build the wire-format OperationMaterialResponse for one PO operation material.

    Single source of truth for material serialization — every new field (e.g.
    component_is_template added in Workstream B0) only needs to be wired here
    rather than in each call site.
    """
    component = db.query(Product).filter(Product.id == mat.component_id).first()
    return OperationMaterialResponse(
        id=mat.id,
        component_id=mat.component_id,
        component_sku=component.sku if component else None,
        component_name=component.name if component else None,
        component_is_template=bool(component.is_template) if component else False,
        quantity_required=mat.quantity_required,
        quantity_allocated=mat.quantity_allocated or Decimal(0),
        quantity_consumed=mat.quantity_consumed or Decimal(0),
        unit=mat.unit,
        status=mat.status or "pending",
    )


def build_production_order_response(order: ProductionOrder, db: Session) -> ProductionOrderResponse:
    """Build full response with related data."""
    from app.models import BOM
    from app.models.manufacturing import Routing
    from app.models.production_order import ScrapRecord

    product = db.query(Product).filter(Product.id == order.product_id).first()
    bom = db.query(BOM).filter(BOM.id == order.bom_id).first() if order.bom_id else None
    routing = db.query(Routing).filter(Routing.id == order.routing_id).first() if order.routing_id else None
    sales_order = db.query(SalesOrder).filter(SalesOrder.id == order.sales_order_id).first() if order.sales_order_id else None

    qty_ordered = float(order.quantity_ordered or 0)
    qty_completed = float(order.quantity_completed or 0)
    # When a PO is complete (including accept-short), remaining is 0 and
    # completion is 100% even if qty_completed < qty_ordered
    if order.status == "complete":
        qty_remaining = 0
        completion_pct = 100.0
    else:
        qty_remaining = max(0, qty_ordered - qty_completed)
        completion_pct = (qty_completed / qty_ordered * 100) if qty_ordered > 0 else 0

    # Build operations list
    operations_response = []
    if order.operations:
        for op in sorted(order.operations, key=lambda x: x.sequence):
            wc = db.query(WorkCenter).filter(WorkCenter.id == op.work_center_id).first()
            res = db.query(Resource).filter(Resource.id == op.resource_id).first() if op.resource_id else None

            materials_response = [
                _build_operation_material_response(mat, db) for mat in op.materials
            ]

            operations_response.append(
                ProductionOrderOperationResponse(
                    id=op.id,
                    production_order_id=op.production_order_id,
                    routing_operation_id=op.routing_operation_id,
                    work_center_id=op.work_center_id,
                    work_center_code=wc.code if wc else None,
                    work_center_name=wc.name if wc else None,
                    resource_id=op.resource_id,
                    resource_code=res.code if res else None,
                    resource_name=res.name if res else None,
                    sequence=op.sequence,
                    operation_code=op.operation_code,
                    operation_name=op.operation_name,
                    status=op.status or "pending",
                    quantity_completed=op.quantity_completed or Decimal(0),
                    quantity_scrapped=op.quantity_scrapped or Decimal(0),
                    planned_setup_minutes=op.planned_setup_minutes or Decimal(0),
                    planned_run_minutes=op.planned_run_minutes or Decimal(0),
                    actual_setup_minutes=op.actual_setup_minutes,
                    actual_run_minutes=op.actual_run_minutes,
                    scheduled_start=op.scheduled_start,
                    scheduled_end=op.scheduled_end,
                    actual_start=op.actual_start,
                    actual_end=op.actual_end,
                    bambu_task_id=op.bambu_task_id,
                    bambu_plate_index=op.bambu_plate_index,
                    operator_name=op.operator_name,
                    notes=op.notes,
                    is_complete=op.status == "complete",
                    is_running=op.status == "running",
                    efficiency_percent=None,
                    materials=materials_response,
                    created_at=op.created_at,
                    updated_at=op.updated_at,
                )
            )

    # Lineage
    original_order = None
    remake_reason = None
    if order.remake_of_id:
        original_order = db.query(ProductionOrder).filter(ProductionOrder.id == order.remake_of_id).first()
        if order.notes and "remake" in order.notes.lower():
            remake_reason = order.notes
        else:
            scrap_record = db.query(ScrapRecord).filter(
                ScrapRecord.production_order_id == order.remake_of_id
            ).order_by(ScrapRecord.created_at.desc()).first()
            if scrap_record:
                remake_reason = scrap_record.reason_code

    return ProductionOrderResponse(
        id=order.id,
        code=order.code,
        product_id=order.product_id,
        product_sku=product.sku if product else None,
        product_name=product.name if product else None,
        bom_id=order.bom_id,
        bom_code=bom.code if bom else None,
        routing_id=order.routing_id,
        routing_code=routing.code if routing else None,
        sales_order_id=order.sales_order_id,
        sales_order_code=sales_order.order_number if sales_order else None,
        sales_order_line_id=order.sales_order_line_id,
        quantity_ordered=order.quantity_ordered,
        quantity_completed=order.quantity_completed or Decimal(0),
        quantity_scrapped=order.quantity_scrapped or Decimal(0),
        quantity_remaining=qty_remaining,
        completion_percent=round(completion_pct, 1),
        source=order.source or "manual",
        status=order.status or "draft",
        priority=order.priority or 3,
        due_date=order.due_date,
        scheduled_start=order.scheduled_start,
        scheduled_end=order.scheduled_end,
        actual_start=order.actual_start,
        actual_end=order.actual_end,
        estimated_time_minutes=order.estimated_time_minutes,
        actual_time_minutes=order.actual_time_minutes,
        estimated_material_cost=order.estimated_material_cost,
        estimated_labor_cost=order.estimated_labor_cost,
        estimated_total_cost=order.estimated_total_cost,
        actual_material_cost=order.actual_material_cost,
        actual_labor_cost=order.actual_labor_cost,
        actual_total_cost=order.actual_total_cost,
        assigned_to=order.assigned_to,
        notes=order.notes,
        remake_of_id=order.remake_of_id,
        remake_of_code=original_order.code if original_order else None,
        remake_reason=remake_reason,
        operations=operations_response,
        created_at=order.created_at,
        updated_at=order.updated_at,
        created_by=order.created_by,
        released_at=order.released_at,
        completed_at=order.completed_at,
    )


def build_list_response(order: ProductionOrder, db: Session) -> ProductionOrderListResponse:
    """Build list response for a production order."""
    product = db.query(Product).filter(Product.id == order.product_id).first()
    sales_order = db.query(SalesOrder).filter(SalesOrder.id == order.sales_order_id).first() if order.sales_order_id else None

    op_count = db.query(ProductionOrderOperation).filter(
        ProductionOrderOperation.production_order_id == order.id
    ).count()

    current_op = (
        db.query(ProductionOrderOperation)
        .filter(
            ProductionOrderOperation.production_order_id == order.id,
            ProductionOrderOperation.status.in_(["running", "queued", "pending"]),
        )
        .order_by(ProductionOrderOperation.sequence)
        .first()
    )

    qty_ordered = float(order.quantity_ordered or 0)
    qty_completed = float(order.quantity_completed or 0)
    # When a PO is complete (including accept-short), remaining is 0 and
    # completion is 100% even if qty_completed < qty_ordered
    if order.status == "complete":
        qty_remaining = 0
        completion_pct = 100.0
    else:
        qty_remaining = max(0, qty_ordered - qty_completed)
        completion_pct = (qty_completed / qty_ordered * 100) if qty_ordered > 0 else 0

    return ProductionOrderListResponse(
        id=order.id,
        code=order.code,
        product_id=order.product_id,
        product_sku=product.sku if product else None,
        product_name=product.name if product else None,
        quantity_ordered=order.quantity_ordered,
        quantity_completed=order.quantity_completed or 0,
        quantity_remaining=qty_remaining,
        completion_percent=round(completion_pct, 1),
        status=order.status or "draft",
        priority=order.priority or 3,
        source=order.source or "manual",
        due_date=order.due_date,
        scheduled_start=order.scheduled_start,
        scheduled_end=order.scheduled_end,
        sales_order_id=order.sales_order_id,
        sales_order_code=sales_order.order_number if sales_order else None,
        sales_order_line_id=order.sales_order_line_id,
        assigned_to=order.assigned_to,
        operation_count=op_count,
        current_operation=current_op.operation_name if current_op else None,
        estimated_material_cost=order.estimated_material_cost,
        estimated_labor_cost=order.estimated_labor_cost,
        estimated_total_cost=order.estimated_total_cost,
        actual_material_cost=order.actual_material_cost,
        actual_labor_cost=order.actual_labor_cost,
        actual_total_cost=order.actual_total_cost,
        # QC status + computed guards for the next-action contract (#808).
        # qc_status was previously omitted, so the list always reported the
        # "not_required" default regardless of the real value.
        qc_status=order.qc_status or "not_required",
        is_ready_for_qc=order.is_ready_for_qc,
        can_close=order.can_close,
        is_qc_required=order.is_qc_required,
        created_at=order.created_at,
    )


# =============================================================================
# CRUD Endpoints
# =============================================================================

@router.get("/", response_model=List[ProductionOrderListResponse])
async def list_production_orders(
    pagination: Annotated[PaginationParams, Depends(get_pagination_params)],
    status: Optional[str] = Query(None, description="Filter by status"),
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    sales_order_id: Optional[int] = Query(None, description="Filter by sales order ID"),
    priority: Optional[int] = Query(None, ge=1, le=5, description="Filter by priority"),
    due_before: Optional[date] = Query(None, description="Filter orders due before this date"),
    due_after: Optional[date] = Query(None, description="Filter orders due after this date"),
    search: Optional[str] = Query(None, description="Search by PO code, product SKU, or name"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ProductionOrderListResponse]:
    """List production orders with filtering and pagination."""
    orders = production_order_service.list_production_orders(
        db,
        status=status,
        product_id=product_id,
        sales_order_id=sales_order_id,
        priority=priority,
        due_before=due_before,
        due_after=due_after,
        search=search,
        offset=pagination.offset,
        limit=pagination.limit,
    )

    return [build_list_response(order, db) for order in orders]


@router.post("/", response_model=ProductionOrderResponse)
async def create_production_order(
    request: ProductionOrderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Create a new production order."""
    order = production_order_service.create_production_order(
        db,
        product_id=request.product_id,
        quantity_ordered=request.quantity_ordered,
        created_by=current_user.email,
        bom_id=request.bom_id,
        routing_id=request.routing_id,
        sales_order_id=request.sales_order_id,
        sales_order_line_id=request.sales_order_line_id,
        source=request.source.value if request.source else "manual",
        priority=request.priority or 3,
        due_date=request.due_date,
        assigned_to=request.assigned_to,
        notes=request.notes,
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


# Static routes MUST be defined before /{order_id} to avoid route conflicts
@router.get("/status-transitions", response_model=StatusTransitionsResponse)
async def get_status_transitions(
    current_status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
) -> StatusTransitionsResponse:
    """Get valid status transitions for production orders."""
    all_statuses = [s.value for s in ProductionOrderStatus]

    if current_status:
        if current_status not in all_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{current_status}'"
            )
        allowed = get_allowed_production_order_transitions(current_status)
        return {
            "current_status": current_status,
            "allowed_transitions": allowed,
            "is_terminal": len(allowed) == 0,
        }

    transitions = {}
    for po_status in ProductionOrderStatus:
        allowed = get_allowed_production_order_transitions(po_status.value)
        transitions[po_status.value] = {
            "allowed_transitions": allowed,
            "is_terminal": len(allowed) == 0,
        }

    return {
        "statuses": all_statuses,
        "transitions": transitions,
    }


@router.get("/{order_id:int}", response_model=ProductionOrderResponse)
async def get_production_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Get a production order by ID."""
    order = production_order_service.get_production_order(db, order_id)
    return build_production_order_response(order, db)


@router.put("/{order_id:int}", response_model=ProductionOrderResponse)
async def update_production_order(
    order_id: int,
    request: ProductionOrderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Update a production order."""
    order = production_order_service.update_production_order(
        db,
        order_id,
        quantity_ordered=request.quantity_ordered,
        priority=request.priority,
        due_date=request.due_date,
        assigned_to=request.assigned_to,
        notes=request.notes,
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


@router.delete("/{order_id:int}", response_model=MessageResponse)
async def delete_production_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a production order."""
    production_order_service.delete_production_order(db, order_id)
    db.commit()
    return {"message": "Production order deleted"}


# =============================================================================
# Scrap Reasons Management
# =============================================================================

@router.get("/scrap-reasons", response_model=ScrapReasonsResponse)
async def get_scrap_reasons(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScrapReasonsResponse:
    """Get list of active scrap reasons."""
    reasons = production_order_service.get_scrap_reasons(db)

    return ScrapReasonsResponse(
        reasons=[r.code for r in reasons],
        details=[
            ScrapReasonDetail(
                id=r.id,
                code=r.code,
                name=r.name,
                description=r.description,
                sequence=r.sequence or 0,
                active=r.active,
            )
            for r in reasons
        ]
    )


@router.get("/scrap-reasons/all", response_model=List[ScrapReasonDetail])
async def get_all_scrap_reasons(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all scrap reasons including inactive."""
    reasons = production_order_service.get_scrap_reasons(db, include_inactive=True)

    return [
        ScrapReasonDetail(
            id=r.id,
            code=r.code,
            name=r.name,
            description=r.description,
            sequence=r.sequence or 0,
            active=r.active,
        )
        for r in reasons
    ]


@router.post("/scrap-reasons", response_model=ScrapReasonDetail)
async def create_scrap_reason(
    request: ScrapReasonCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScrapReasonDetail:
    """Create a new scrap reason."""
    reason = production_order_service.create_scrap_reason(
        db,
        code=request.code,
        name=request.name,
        description=request.description,
        sequence=request.sequence or 0,
    )

    db.commit()
    db.refresh(reason)

    return ScrapReasonDetail(
        id=reason.id,
        code=reason.code,
        name=reason.name,
        description=reason.description,
        sequence=reason.sequence or 0,
        active=reason.active,
    )


@router.put("/scrap-reasons/{reason_id}", response_model=ScrapReasonDetail)
async def update_scrap_reason(
    reason_id: int,
    request: ScrapReasonUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScrapReasonDetail:
    """Update a scrap reason."""
    reason = production_order_service.update_scrap_reason(
        db,
        reason_id,
        name=request.name,
        description=request.description,
        sequence=request.sequence,
        active=request.active,
    )

    db.commit()
    db.refresh(reason)

    return ScrapReasonDetail(
        id=reason.id,
        code=reason.code,
        name=reason.name,
        description=reason.description,
        sequence=reason.sequence or 0,
        active=reason.active,
    )


@router.delete("/scrap-reasons/{reason_id}", response_model=MessageResponse)
async def delete_scrap_reason(
    reason_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a scrap reason."""
    production_order_service.delete_scrap_reason(db, reason_id)
    db.commit()
    return {"message": "Scrap reason deleted"}


@router.get("/qc-statuses", response_model=QCStatusesResponse)
async def get_qc_statuses(
    current_user: User = Depends(get_current_user),
) -> QCStatusesResponse:
    """Get valid QC status values."""
    return {
        "statuses": [s.value for s in QCStatus],
        "descriptions": {
            QCStatus.NOT_REQUIRED.value: "No inspection required",
            QCStatus.PENDING.value: "Awaiting inspection",
            QCStatus.IN_PROGRESS.value: "Inspection in progress",
            QCStatus.PASSED.value: "Passed quality check",
            QCStatus.FAILED.value: "Failed quality check",
            QCStatus.WAIVED.value: "Failed but accepted (waived)",
        }
    }


@router.get("/operation-statuses", response_model=OperationStatusesResponse)
async def get_operation_statuses(
    current_user: User = Depends(get_current_user),
) -> OperationStatusesResponse:
    """Get valid operation status values."""
    return {
        "statuses": [s.value for s in OperationStatus],
        "descriptions": {
            OperationStatus.PENDING.value: "Not started",
            OperationStatus.QUEUED.value: "Waiting in queue",
            OperationStatus.RUNNING.value: "Currently running",
            OperationStatus.PAUSED.value: "Temporarily paused",
            OperationStatus.COMPLETE.value: "Finished",
            OperationStatus.SKIPPED.value: "Skipped",
        }
    }


# =============================================================================
# Status Management Endpoints
# =============================================================================

@router.post("/{order_id}/release", response_model=ProductionOrderResponse)
async def release_production_order(
    order_id: int,
    force: bool = Query(False, description="Force release even with shortages"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Release a production order for manufacturing."""
    order = production_order_service.release_production_order(
        db, order_id, current_user.email, force=force
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


@router.post("/{order_id}/start", response_model=ProductionOrderResponse)
async def start_production_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Start production on an order."""
    order = production_order_service.start_production_order(db, order_id)

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


@router.post("/{order_id}/complete", response_model=ProductionOrderResponse)
async def complete_production_order(
    order_id: int,
    request: Optional[ProductionOrderCompleteRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Complete a production order."""
    # Get order first to calculate defaults
    order = production_order_service.get_production_order(db, order_id)

    # Handle empty or missing request body
    if request is None:
        request = ProductionOrderCompleteRequest()

    # Default quantity to remaining if not specified
    quantity_good = request.quantity_completed
    if quantity_good is None:
        quantity_good = order.quantity_ordered - (order.quantity_completed or 0)

    order = production_order_service.complete_production_order(
        db,
        order_id,
        user_email=current_user.email,
        quantity_good=int(quantity_good),
        quantity_scrapped=int(request.quantity_scrapped or 0),
        force_close_short=request.force_close_short,
        notes=request.notes,
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


@router.post("/{order_id}/accept-short", response_model=ProductionOrderResponse)
async def accept_short(
    order_id: int,
    request: Optional[AcceptShortRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Accept a production order short — complete it with the quantity already produced."""
    order = production_order_service.accept_short_production_order(
        db,
        order_id,
        user_email=current_user.email,
        user_id=current_user.id,
        notes=request.notes if request else None,
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


@router.post("/{order_id}/cancel", response_model=ProductionOrderResponse)
async def cancel_production_order(
    order_id: int,
    notes: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Cancel a production order."""
    order = production_order_service.cancel_production_order(
        db, order_id, current_user.email, notes=notes
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


@router.post("/{order_id}/refresh-routing", response_model=ProductionOrderResponse)
async def refresh_production_order_routing(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Re-snapshot the product's current active routing onto the production order.

    Useful when a routing is added or updated after the PO was already created.
    Only allowed while all operations are still pending (nothing started yet).
    """
    order = production_order_service.refresh_production_order_routing(
        db, order_id, current_user.email
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


@router.post("/{order_id}/hold", response_model=ProductionOrderResponse)
async def hold_production_order(
    order_id: int,
    reason: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Put a production order on hold."""
    order = production_order_service.hold_production_order(db, order_id, reason=reason)

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


# =============================================================================
# Scheduling Endpoints
# =============================================================================

@router.put("/{order_id}/schedule", response_model=ProductionOrderResponse)
async def schedule_production_order(
    order_id: int,
    request: ProductionOrderScheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderResponse:
    """Schedule a production order."""
    order = production_order_service.schedule_production_order(
        db,
        order_id,
        scheduled_start=request.scheduled_start,
        scheduled_end=request.scheduled_end,
        resource_assignments=request.resource_assignments,
    )

    db.commit()
    db.refresh(order)

    return build_production_order_response(order, db)


@router.get("/schedule/summary", response_model=ProductionScheduleSummary)
async def get_schedule_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionScheduleSummary:
    """Get production schedule summary."""
    summary = production_order_service.get_schedule_summary(db)

    return ProductionScheduleSummary(
        by_status=summary["by_status"],
        due_today=summary["due_today"],
        overdue=summary["overdue"],
        work_centers=[
            WorkCenterQueue(
                work_center_id=wc["id"],
                work_center_code=wc["code"],
                work_center_name=wc["name"],
                queue_count=wc["queue_count"],
                queue=[],
            )
            for wc in summary["work_centers"]
        ],
        total_active=summary["total_active"],
    )


@router.get("/queue/by-work-center", response_model=List[WorkCenterQueue])
async def get_work_center_queues(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[WorkCenterQueue]:
    """Get queue of operations by work center."""
    queues = production_order_service.get_work_center_queues(db)

    return [
        WorkCenterQueue(
            work_center_id=q["work_center_id"],
            work_center_code=q["work_center_code"],
            work_center_name=q["work_center_name"],
            queue_count=q["queue_count"],
            queue=q["queue"],
        )
        for q in queues
    ]


# =============================================================================
# Reschedule / Unschedule  (SCHED-2)
# =============================================================================

#: Statuses that allow reschedule / unschedule (op must not have started).
_RESCHEDULABLE_STATUSES = frozenset({"pending", "queued"})

#: Default duration (minutes) when an operation has no planned time data.
_DEFAULT_DURATION_MINUTES = 120


def _get_op_duration_minutes(op: ProductionOrderOperation) -> int:
    """Return the best-available estimated duration for an operation."""
    setup = float(op.planned_setup_minutes or 0)
    run = float(op.planned_run_minutes or 0)
    total = setup + run
    return int(total) if total > 0 else _DEFAULT_DURATION_MINUTES


def _append_po_note(order: ProductionOrder, note: str) -> None:
    """
    Append a timestamped note to production order notes.

    Reuses the same pattern as production_order_service.complete_production_order
    and accept_short_production_order — timestamp prefix, newline separator.
    """
    ts = datetime.now(timezone.utc).isoformat()
    if order.notes:
        order.notes = f"{order.notes}\n[{ts}] {note}"
    else:
        order.notes = f"[{ts}] {note}"


@router.post(
    "/{order_id}/operations/{op_id}/reschedule",
    response_model=RescheduleResponse,
    status_code=200,
)
async def reschedule_operation(
    order_id: int,
    op_id: int,
    request: RescheduleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RescheduleResponse:
    """
    Reschedule a scheduled operation — move it to a new resource and/or time.

    **Allowed statuses**: ``pending`` or ``queued`` (not yet started).

    At least one of ``resource_id`` or ``scheduled_start`` must be provided.
    ``scheduled_end`` is optional; if omitted it is recomputed from the
    operation's planned duration (setup + run, defaulting to 120 min).

    Validates:
    1. Resource / printer exists (when provided).
    2. No time conflicts on the target resource (``exclude_operation_id`` so
       the operation doesn't conflict with its own current slot).
    3. Predecessor sequence constraints (lower-sequence sibling ops).
    4. Successor implications — if moving this op later would violate a
       SUCCESSOR's existing scheduled_start, surfaces a 400 with
       ``conflict_type="successor"`` + per-successor ``earliest_valid_start``
       so the operator can fix the succession order.

    On success: writes an audit note to the production order's notes field and
    returns the new scheduled times.
    """
    # --- Validate PO + op ---
    po = db.get(ProductionOrder, order_id)
    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    op = db.get(ProductionOrderOperation, op_id)
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    if op.production_order_id != order_id:
        raise HTTPException(
            status_code=404,
            detail=f"Operation {op_id} does not belong to production order {order_id}",
        )

    if op.status not in _RESCHEDULABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Operation {op_id} has status '{op.status}'; "
                f"only pending/queued operations can be rescheduled"
            ),
        )

    # --- At least one change required ---
    if request.resource_id is None and request.scheduled_start is None:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of resource_id or scheduled_start",
        )

    # --- Resolve target resource / printer ---
    # Start from the operation's current values and overlay the request.
    new_resource_id: Optional[int] = request.resource_id
    is_printer: bool = request.is_printer if request.is_printer is not None else False

    if new_resource_id is None:
        # Keep current resource / printer
        if op.printer_id is not None:
            new_resource_id = op.printer_id
            is_printer = True
        elif op.resource_id is not None:
            new_resource_id = op.resource_id
            is_printer = False
        else:
            raise HTTPException(
                status_code=400,
                detail="Operation has no current resource; provide resource_id",
            )
    else:
        # Validate the supplied resource exists
        if is_printer:
            res_obj = db.get(Printer, new_resource_id)
            if not res_obj:
                raise HTTPException(status_code=404, detail="Printer not found")
        else:
            res_obj = db.get(Resource, new_resource_id)
            if not res_obj:
                raise HTTPException(status_code=404, detail="Resource not found")

    # --- Resolve start / end times ---
    duration_minutes = _get_op_duration_minutes(op)

    if request.scheduled_start is not None:
        new_start = request.scheduled_start
    else:
        # Keep current start
        if op.scheduled_start is None:
            raise HTTPException(
                status_code=400,
                detail="Operation has no current start time; provide scheduled_start",
            )
        new_start = op.scheduled_start
        # Normalize naive DB timestamp to UTC-aware
        if new_start.tzinfo is None:
            new_start = new_start.replace(tzinfo=timezone.utc)

    if request.scheduled_end is not None:
        new_end = request.scheduled_end
    else:
        new_end = new_start + timedelta(minutes=duration_minutes)

    if new_end <= new_start:
        raise HTTPException(
            status_code=422,
            detail="scheduled_end must be after scheduled_start",
        )

    # --- Conflict check (exclude self so we don't block on our own current slot) ---
    resource_conflicts = find_conflicts(
        db=db,
        resource_id=new_resource_id,
        start_time=new_start,
        end_time=new_end,
        exclude_operation_id=op_id,
        is_printer=is_printer,
    )

    if resource_conflicts:
        earliest = get_earliest_start_after_predecessors(
            db=db, operation=op, after=new_start
        )
        next_start = find_next_available_slot(
            db=db,
            resource_id=new_resource_id,
            duration_minutes=duration_minutes,
            after=earliest,
            is_printer=is_printer,
        )
        conflict_details = [
            ConflictInfo(
                operation_id=c.id,
                production_order_id=c.production_order_id,
                production_order_code=c.production_order.code if c.production_order else None,
                operation_code=c.operation_code,
                scheduled_start=c.scheduled_start,
                scheduled_end=c.scheduled_end,
            )
            for c in resource_conflicts
        ]
        return RescheduleResponse(
            success=False,
            message=f"Scheduling conflict with {len(resource_conflicts)} existing operation(s)",
            conflicts=conflict_details,
            conflict_type="resource",
            next_available_start=next_start,
            next_available_end=next_start + timedelta(minutes=duration_minutes),
        )

    # --- Maintenance-window check (SCHED-7) ---
    window_conflicts = find_window_conflicts(
        db=db,
        resource_id=new_resource_id,
        start_time=new_start,
        end_time=new_end,
        is_printer=is_printer,
    )
    if window_conflicts:
        w = window_conflicts[0]
        # find_next_available_slot is window-aware, so the suggested slot
        # already skips past the maintenance block.
        next_start = find_next_available_slot(
            db=db,
            resource_id=new_resource_id,
            duration_minutes=duration_minutes,
            after=get_earliest_start_after_predecessors(db=db, operation=op, after=new_start),
            is_printer=is_printer,
        )
        return RescheduleResponse(
            success=False,
            message=(
                f"Overlaps maintenance window "
                f"{w.starts_at:%Y-%m-%d %H:%M}–{w.ends_at:%H:%M} UTC"
                + (f" ({w.reason})" if w.reason else "")
            ),
            conflicts=[],
            conflict_type="maintenance",
            next_available_start=next_start,
            next_available_end=next_start + timedelta(minutes=duration_minutes),
        )

    # --- Predecessor check ---
    try:
        seq_error = check_predecessor_scheduling(db, op, new_start)
    except Exception:
        seq_error = None  # never raises in current impl; guard for safety

    if seq_error:
        # Check if any predecessor is unscheduled
        has_unscheduled_pred = (
            db.query(ProductionOrderOperation.id)
            .filter(
                ProductionOrderOperation.production_order_id == op.production_order_id,
                ProductionOrderOperation.sequence < op.sequence,
                ProductionOrderOperation.id != op.id,
                ProductionOrderOperation.status.notin_(list(TERMINAL_STATUSES)),
                ProductionOrderOperation.scheduled_end.is_(None),
            )
            .first()
        ) is not None

        earliest = None
        next_start = None
        if not has_unscheduled_pred:
            earliest = get_earliest_start_after_predecessors(
                db=db, operation=op, after=new_start
            )
            next_start = find_next_available_slot(
                db=db,
                resource_id=new_resource_id,
                duration_minutes=duration_minutes,
                after=earliest,
                is_printer=is_printer,
            )
        return RescheduleResponse(
            success=False,
            message=seq_error,
            conflicts=[],
            conflict_type="predecessor",
            earliest_valid_start=earliest,
            next_available_start=next_start,
            next_available_end=(
                next_start + timedelta(minutes=duration_minutes)
                if next_start is not None else None
            ),
        )

    # --- Successor implication check ---
    successor_violations = check_successor_scheduling(db, op, new_end)
    if successor_violations:
        succ_details = [
            SuccessorConflictInfo(
                operation_id=s.id,
                operation_code=s.operation_code,
                operation_name=s.operation_name,
                sequence=s.sequence,
                scheduled_start=s.scheduled_start,
                earliest_valid_start=new_end,
            )
            for s in successor_violations
        ]
        return RescheduleResponse(
            success=False,
            message=(
                f"Moving this operation would violate {len(successor_violations)} "
                f"successor operation(s) that are already scheduled"
            ),
            conflict_type="successor",
            successor_conflicts=succ_details,
        )

    # --- Apply the reschedule ---
    old_resource_desc = (
        f"printer_id={op.printer_id}" if op.printer_id
        else f"resource_id={op.resource_id}"
    )
    old_start_str = (
        op.scheduled_start.isoformat() if op.scheduled_start else "unscheduled"
    )

    if is_printer:
        op.printer_id = new_resource_id
        op.resource_id = None
    else:
        op.resource_id = new_resource_id
        op.printer_id = None

    op.scheduled_start = new_start
    op.scheduled_end = new_end
    if op.status == "pending":
        op.status = "queued"

    # Audit trail — append a timestamped note to the production order
    new_resource_desc = f"printer_id={new_resource_id}" if is_printer else f"resource_id={new_resource_id}"
    _append_po_note(
        po,
        f"Operation {op.sequence} ({op.operation_code}) rescheduled by "
        f"{current_user.email}: "
        f"{old_resource_desc} {old_start_str} → "
        f"{new_resource_desc} {new_start.isoformat()}",
    )

    db.flush()
    db.commit()

    return RescheduleResponse(
        success=True,
        operation_id=op_id,
        scheduled_start=op.scheduled_start,
        scheduled_end=op.scheduled_end,
    )


@router.post(
    "/{order_id}/operations/{op_id}/unschedule",
    response_model=UnscheduleResponse,
    status_code=200,
)
async def unschedule_operation(
    order_id: int,
    op_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UnscheduleResponse:
    """
    Unschedule an operation — clear its times and resource, return to pending.

    **Allowed statuses**: ``pending`` or ``queued`` (not yet started).

    Writes an audit note to the production order's notes field.
    """
    po = db.get(ProductionOrder, order_id)
    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    op = db.get(ProductionOrderOperation, op_id)
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    if op.production_order_id != order_id:
        raise HTTPException(
            status_code=404,
            detail=f"Operation {op_id} does not belong to production order {order_id}",
        )

    if op.status not in _RESCHEDULABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Operation {op_id} has status '{op.status}'; "
                f"only pending/queued operations can be unscheduled"
            ),
        )

    old_resource_desc = (
        f"printer_id={op.printer_id}" if op.printer_id
        else (f"resource_id={op.resource_id}" if op.resource_id else "no resource")
    )
    old_start_str = (
        op.scheduled_start.isoformat() if op.scheduled_start else "unscheduled"
    )

    # Clear schedule
    op.scheduled_start = None
    op.scheduled_end = None
    op.resource_id = None
    op.printer_id = None
    op.status = "pending"

    # Audit trail
    _append_po_note(
        po,
        f"Operation {op.sequence} ({op.operation_code}) unscheduled by "
        f"{current_user.email}: cleared {old_resource_desc} @ {old_start_str}",
    )

    db.flush()
    db.commit()

    return UnscheduleResponse(
        success=True,
        operation_id=op_id,
        message=(
            f"Operation {op.sequence} ({op.operation_code}) unscheduled; "
            f"returned to pending"
        ),
    )


# =============================================================================
# QC / Inspection
# =============================================================================

@router.post("/{order_id}/qc", response_model=QCInspectionResponse)
async def record_qc_inspection(
    order_id: int,
    request: QCInspectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QCInspectionResponse:
    """Record QC inspection results."""
    inspection = production_order_service.record_qc_inspection(
        db,
        order_id,
        inspector=current_user.email,
        qc_status=request.result.value,
        quantity_passed=request.quantity_passed,
        quantity_failed=request.quantity_failed,
        failure_reason=request.failure_reason,
        notes=request.notes,
    )

    db.commit()

    order = production_order_service.get_production_order(db, order_id)

    return QCInspectionResponse(
        production_order_id=order.id,
        production_order_code=order.code,
        inspection_id=inspection.get("inspection_id"),
        qc_status=order.qc_status,
        qc_notes=order.qc_notes,
        qc_inspected_by=order.qc_inspected_by,
        qc_inspected_at=order.qc_inspected_at,
        sales_order_updated=False,
        sales_order_status=None,
        message=f"QC {order.qc_status} recorded for {order.code}",
    )


@router.get("/{order_id}/qc-inspections", response_model=QCInspectionHistoryResponse)
async def get_qc_inspections(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QCInspectionHistoryResponse:
    """Return the append-only QC inspection history for an order (#783).

    Oldest-first, so the first entry is the first-pass inspection.
    """
    inspections = production_order_service.get_qc_inspections(db, order_id)
    return QCInspectionHistoryResponse(
        production_order_id=order_id,
        total=len(inspections),
        inspections=[QCInspectionRecord.model_validate(i) for i in inspections],
    )


# =============================================================================
# Split Order
# =============================================================================

@router.post("/{order_id}/split", response_model=ProductionOrderSplitResponse)
async def split_production_order(
    order_id: int,
    request: ProductionOrderSplitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderSplitResponse:
    """Split a production order into two."""
    original, new_order = production_order_service.split_production_order(
        db,
        order_id,
        split_quantity=request.split_quantity,
        user_email=current_user.email,
        reason=request.reason,
    )

    db.commit()
    db.refresh(original)
    db.refresh(new_order)

    return ProductionOrderSplitResponse(
        original_order=build_production_order_response(original, db),
        new_order=build_production_order_response(new_order, db),
        message=f"Split {request.split_quantity} units to {new_order.code}",
    )


# =============================================================================
# Scrap Recording
# =============================================================================

@router.post("/{order_id}/scrap", response_model=ProductionOrderScrapResponse)
async def record_scrap(
    order_id: int,
    request: OperationScrapRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderScrapResponse:
    """Record scrap for a production order."""
    result = production_order_service.record_scrap(
        db,
        order_id,
        quantity_scrapped=request.quantity_scrapped,
        reason_code=request.scrap_reason_code,
        operation_id=None,
        notes=request.notes,
        create_remake=request.create_replacement,
        user_email=current_user.email,
    )

    db.commit()

    order = production_order_service.get_production_order(db, order_id)

    return ProductionOrderScrapResponse(
        order_id=order.id,
        order_code=order.code,
        quantity_scrapped=order.quantity_scrapped or 0,
        scrap_reason=request.scrap_reason_code,
        remake_order_id=result["remake_order"]["id"] if result["remake_order"] else None,
        remake_order_code=result["remake_order"]["code"] if result["remake_order"] else None,
    )


# =============================================================================
# Operation Management
# =============================================================================

@router.put("/{order_id}/operations/{operation_id}", response_model=ProductionOrderOperationResponse)
async def update_operation(
    order_id: int,
    operation_id: int,
    request: ProductionOrderOperationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProductionOrderOperationResponse:
    """Update a production order operation."""
    op = production_order_service.update_operation(
        db,
        order_id,
        operation_id,
        status=request.status,
        quantity_completed=request.quantity_completed,
        quantity_scrapped=request.quantity_scrapped,
        actual_setup_minutes=request.actual_setup_minutes,
        actual_run_minutes=request.actual_run_minutes,
        resource_id=request.resource_id,
        operator_name=request.operator_name,
        notes=request.notes,
    )

    db.commit()
    db.refresh(op)

    wc = db.query(WorkCenter).filter(WorkCenter.id == op.work_center_id).first()
    res = db.query(Resource).filter(Resource.id == op.resource_id).first() if op.resource_id else None

    materials_response = [
        _build_operation_material_response(mat, db) for mat in op.materials
    ]

    return ProductionOrderOperationResponse(
        id=op.id,
        production_order_id=op.production_order_id,
        routing_operation_id=op.routing_operation_id,
        work_center_id=op.work_center_id,
        work_center_code=wc.code if wc else None,
        work_center_name=wc.name if wc else None,
        resource_id=op.resource_id,
        resource_code=res.code if res else None,
        resource_name=res.name if res else None,
        sequence=op.sequence,
        operation_code=op.operation_code,
        operation_name=op.operation_name,
        status=op.status or "pending",
        quantity_completed=op.quantity_completed or Decimal(0),
        quantity_scrapped=op.quantity_scrapped or Decimal(0),
        planned_setup_minutes=op.planned_setup_minutes or Decimal(0),
        planned_run_minutes=op.planned_run_minutes or Decimal(0),
        actual_setup_minutes=op.actual_setup_minutes,
        actual_run_minutes=op.actual_run_minutes,
        scheduled_start=op.scheduled_start,
        scheduled_end=op.scheduled_end,
        actual_start=op.actual_start,
        actual_end=op.actual_end,
        bambu_task_id=op.bambu_task_id,
        bambu_plate_index=op.bambu_plate_index,
        operator_name=op.operator_name,
        notes=op.notes,
        is_complete=op.status == "complete",
        is_running=op.status == "running",
        efficiency_percent=None,
        materials=materials_response,
        created_at=op.created_at,
        updated_at=op.updated_at,
    )


# =============================================================================
# Material Availability / Blocking Issues
# =============================================================================

@router.get("/{order_id}/material-availability", response_model=MaterialAvailabilityResponse)
async def get_material_availability(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MaterialAvailabilityResponse:
    """Get material availability analysis for a production order."""
    return production_order_service.get_material_availability(db, order_id)


@router.get("/{order_id}/blocking-issues", response_model=ProductionOrderBlockingIssues)
async def get_blocking_issues(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get blocking issues for a production order."""
    result = get_production_order_blocking_issues(db, order_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Production order not found")
    return result


@router.get("/{order_id}/required-orders", response_model=RequiredOrdersResponse)
async def get_required_orders(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RequiredOrdersResponse:
    """Get MRP cascade of required orders."""
    return production_order_service.get_required_orders(db, order_id)


@router.get("/{order_id}/cost-breakdown", response_model=CostBreakdownResponse)
async def get_cost_breakdown(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CostBreakdownResponse:
    """Get cost breakdown for a production order."""
    return production_order_service.get_cost_breakdown(db, order_id)


@router.post("/{order_id}/estimate-cost", response_model=CostBreakdownResponse)
async def estimate_cost(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CostBreakdownResponse:
    """Re-estimate costs for a production order from its routing and BOM.

    Updates estimated_material_cost, estimated_labor_cost, and estimated_total_cost
    on the production order using current work center rates and material prices
    (always from planned/required quantities).

    Returns:
        Full cost breakdown using best-available data: consumed quantities for
        materials with status 'consumed', required quantities otherwise; actual
        times where recorded, planned times otherwise.
    """
    from app.services.cost_estimation_service import estimate_production_order_cost

    order = production_order_service.get_production_order(db, order_id)
    if not order.operations:
        raise HTTPException(status_code=400, detail="No operations to estimate — assign a routing first")

    estimate_production_order_cost(db, order)
    db.commit()
    db.refresh(order)

    return production_order_service.get_cost_breakdown(db, order_id)


# =============================================================================
# Material-Printer Compatibility
# =============================================================================

@router.get("/{order_id}/compatibility", response_model=OrderCompatibilityResponse)
async def check_compatibility(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderCompatibilityResponse:
    """Check material-printer compatibility for all operations in a production order.

    Validates enclosure requirements, temperature ranges, and filament diameter
    for every operation that has a printer or resource assigned.
    """
    from app.services.compatibility_service import check_order_compatibility
    from sqlalchemy.orm import selectinload
    from app.models.product import Product

    order = (
        db.query(ProductionOrder)
        .options(
            selectinload(ProductionOrder.operations)
            .selectinload(ProductionOrderOperation.materials)
            .joinedload(ProductionOrderOperationMaterial.component)
            .joinedload(Product.material_type),
        )
        .filter(ProductionOrder.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Production order not found")
    result = check_order_compatibility(db, order)
    return OrderCompatibilityResponse(
        production_order_id=result.production_order_id,
        production_order_code=result.production_order_code,
        compatible=result.compatible,
        total_issues=result.total_issues,
        operations=[
            OperationCompatibilityResponse(
                operation_id=op.operation_id,
                operation_name=op.operation_name,
                printer_name=op.printer_name,
                compatible=op.compatible,
                issues=[
                    CompatibilityIssueResponse(
                        severity=i.severity,
                        check=i.check,
                        message=i.message,
                        material_name=i.material_name,
                        printer_name=i.printer_name,
                    )
                    for i in op.issues
                ],
            )
            for op in result.operations
        ],
    )


@router.get(
    "/{order_id}/operations/{operation_id}/compatibility",
    response_model=OperationCompatibilityResponse,
)
async def check_operation_compat(
    order_id: int,
    operation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OperationCompatibilityResponse:
    """Check material-printer compatibility for a single operation."""
    from app.services.compatibility_service import check_operation_compatibility
    from sqlalchemy.orm import selectinload
    from app.models.production_order import ProductionOrderOperationMaterial
    from app.models.product import Product

    operation = (
        db.query(ProductionOrderOperation)
        .options(
            selectinload(ProductionOrderOperation.materials)
            .joinedload(ProductionOrderOperationMaterial.component)
            .joinedload(Product.material_type),
        )
        .filter(
            ProductionOrderOperation.id == operation_id,
            ProductionOrderOperation.production_order_id == order_id,
        )
        .first()
    )
    if operation is None:
        raise HTTPException(status_code=404, detail="Operation not found")

    result = check_operation_compatibility(db, operation)
    return OperationCompatibilityResponse(
        operation_id=result.operation_id,
        operation_name=result.operation_name,
        printer_name=result.printer_name,
        compatible=result.compatible,
        issues=[
            CompatibilityIssueResponse(
                severity=i.severity,
                check=i.check,
                message=i.message,
                material_name=i.material_name,
                printer_name=i.printer_name,
            )
            for i in result.issues
        ],
    )


# =============================================================================
# Spool Management
# =============================================================================

@router.get("/{order_id}/spools", response_model=List[SpoolListItem])
async def get_order_spools(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[SpoolListItem]:
    """Get spools assigned to a production order."""
    return production_order_service.get_order_spools(db, order_id)


@router.post("/{order_id}/spools/{spool_id}", response_model=SpoolAssignmentResponse)
async def assign_spool_to_order(
    order_id: int,
    spool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SpoolAssignmentResponse:
    """Assign a spool to a production order."""
    result = production_order_service.assign_spool_to_order(
        db, order_id, spool_id, current_user.email
    )

    db.commit()

    return result


@router.patch(
    "/{order_id}/materials/{material_id}/component",
    response_model=OperationMaterialResponse,
)
async def swap_material_variant_endpoint(
    order_id: int,
    material_id: int,
    request: SwapMaterialVariantRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OperationMaterialResponse:
    """Workstream B0: swap a PO operation material's component to a variant.

    Tactical override for the case where a PO's BOM specifies a template that has
    0 own-stock but variants have stock. Operator picks the variant they want to
    consume from instead of the template.
    """
    mat = production_order_service.swap_material_variant(
        db, order_id, material_id, request.new_component_id, request.reason,
    )
    db.commit()
    db.refresh(mat)
    return _build_operation_material_response(mat, db)
