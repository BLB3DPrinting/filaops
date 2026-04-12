"""
API endpoints for operation status transitions.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db, get_current_user
from app.schemas.operation_status import (
    OperationStartRequest,
    OperationCompleteRequest,
    OperationSkipRequest,
    OperationResponse,
    OperationListItem,
    OperationMaterial,
    ProductionOrderSummary,
    NextOperationInfo,
)
from app.schemas.operation_blocking import (
    CanStartResponse,
    OperationBlockingResponse,
)
from app.services.operation_status import (
    OperationError,
    start_operation,
    complete_operation,
    skip_operation,
    list_operations,
    get_next_operation,
    get_operation_max_quantity,
)
from app.services.operation_blocking import (
    OperationBlockingError,
    can_operation_start,
    check_operation_blocking,
)
from app.services.resource_scheduling import (
    schedule_operation as schedule_operation_service,
    find_next_available_slot,
    SequenceError,
)
from app.services.operation_generation import (
    generate_operations_manual,
)
from app.schemas.resource_scheduling import (
    ScheduleOperationRequest,
    ScheduleOperationResponse,
    NextAvailableSlotRequest,
    NextAvailableSlotResponse,
    ConflictInfo,
)
from app.schemas.routing_operations import (
    GenerateOperationsRequest,
    GenerateOperationsResponse,
)
from app.models.production_order import ProductionOrder, ProductionOrderOperation
from app.models.manufacturing import Resource
from app.models.printer import Printer


router = APIRouter()


def build_operation_response(op, po, next_op=None) -> OperationResponse:
    """Build response from operation model."""
    resource_code = None
    if op.resource:
        resource_code = op.resource.code

    # Get current operation sequence for PO
    current_seq = None
    for o in sorted(po.operations, key=lambda x: x.sequence):
        if o.status not in ('complete', 'skipped'):
            current_seq = o.sequence
            break

    next_op_info = None
    if next_op:
        next_op_info = NextOperationInfo(
            id=next_op.id,
            sequence=next_op.sequence,
            operation_code=next_op.operation_code,
            operation_name=next_op.operation_name,
            status=next_op.status,
            work_center_code=next_op.work_center.code if next_op.work_center else None,
            work_center_name=next_op.work_center.name if next_op.work_center else None,
        )

    # Calculate shortage info
    qty_ordered = po.quantity_ordered or 0
    qty_completed = po.quantity_completed or 0
    qty_short = max(0, qty_ordered - qty_completed) if po.status == 'short' else 0

    # Get sales order code if linked
    sales_order_code = None
    if po.sales_order:
        sales_order_code = po.sales_order.order_number

    return OperationResponse(
        id=op.id,
        sequence=op.sequence,
        operation_code=op.operation_code,
        operation_name=op.operation_name,
        status=op.status,
        resource_id=op.resource_id,
        resource_code=resource_code,
        planned_run_minutes=op.planned_run_minutes,
        actual_start=op.actual_start,
        actual_end=op.actual_end,
        actual_run_minutes=op.actual_run_minutes,
        quantity_completed=op.quantity_completed,
        quantity_scrapped=op.quantity_scrapped,
        scrap_reason=op.scrap_reason,
        notes=op.notes,
        production_order=ProductionOrderSummary(
            id=po.id,
            code=po.code,
            status=po.status,
            current_operation_sequence=current_seq,
            quantity_ordered=qty_ordered,
            quantity_completed=qty_completed,
            quantity_short=qty_short,
            sales_order_id=po.sales_order_id,
            sales_order_code=sales_order_code,
        ),
        next_operation=next_op_info,
    )


@router.get(
    "/{po_id}/operations",
    response_model=List[OperationListItem],
    summary="List operations for a production order"
)
def get_operations(
    po_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get all operations for a production order, ordered by sequence.

    Each operation includes:
    - quantity_input: max allowed qty (from previous op or order qty)
    - quantity_completed: good parts completed
    - quantity_scrapped: bad parts scrapped
    """
    # Get PO for quantity calculations
    po = db.get(ProductionOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    try:
        ops = list_operations(db, po_id)
    except OperationError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    result = []
    for op in ops:
        # Calculate max quantity allowed for this operation
        qty_input = get_operation_max_quantity(po, op)

        # Build materials list for this operation
        op_materials = []
        for mat in op.materials:
            op_materials.append(OperationMaterial(
                id=mat.id,
                component_id=mat.component_id,
                component_sku=mat.component.sku if mat.component else None,
                component_name=mat.component.name if mat.component else None,
                quantity_required=mat.quantity_required,
                quantity_consumed=mat.quantity_consumed,
                unit=mat.unit,
                status=mat.status,
            ))

        # Resolve resource name - handle negative IDs (printers) vs positive (resources)
        resource_code = None
        resource_name = None
        if op.resource_id:
            if op.resource_id < 0:
                # Negative ID = printer ID (stored as -printer_id)
                printer = db.get(Printer, abs(op.resource_id))
                if printer:
                    resource_code = printer.code
                    resource_name = printer.name
            else:
                # Positive ID = resource
                if op.resource:
                    resource_code = op.resource.code
                    resource_name = op.resource.name

        result.append(OperationListItem(
            id=op.id,
            sequence=op.sequence,
            operation_code=op.operation_code,
            operation_name=op.operation_name,
            status=op.status,
            work_center_id=op.work_center_id,
            work_center_code=op.work_center.code if op.work_center else None,
            work_center_name=op.work_center.name if op.work_center else None,
            resource_id=op.resource_id,
            resource_code=resource_code,
            resource_name=resource_name,
            planned_setup_minutes=op.planned_setup_minutes,
            planned_run_minutes=op.planned_run_minutes,
            actual_start=op.actual_start,
            actual_end=op.actual_end,
            quantity_input=qty_input,
            quantity_completed=op.quantity_completed,
            quantity_scrapped=op.quantity_scrapped,
            scrap_reason=op.scrap_reason,
            materials=op_materials,
        ))

    return result


@router.post(
    "/{po_id}/operations/{op_id}/start",
    response_model=OperationResponse,
    summary="Start an operation"
)
def start_operation_endpoint(
    po_id: int,
    op_id: int,
    request: OperationStartRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Start an operation.

    Validations:
    - Operation must be in pending or queued status
    - Previous operation must be complete or skipped
    - Resource must not have conflicting scheduled operation
    """
    try:
        op = start_operation(
            db=db,
            po_id=po_id,
            op_id=op_id,
            resource_id=request.resource_id,
            operator_name=request.operator_name,
            notes=request.notes,
        )
        db.commit()
    except OperationError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    po = db.get(ProductionOrder, po_id)
    next_op = get_next_operation(db, po, op)

    return build_operation_response(op, po, next_op)


@router.post(
    "/{po_id}/operations/{op_id}/complete",
    response_model=OperationResponse,
    summary="Complete an operation"
)
def complete_operation_endpoint(
    po_id: int,
    op_id: int,
    request: OperationCompleteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Complete an operation with optional partial scrap and cascading material accounting.

    Validations:
    - Operation must be in running status
    - If quantity_scrapped > 0, scrap_reason is required

    Side effects:
    - Consumes materials for this operation
    - If scrapping: Creates ScrapRecords with cascading material costs + GL entries
    - If create_replacement=true: Creates new PO linked to original
    - Updates PO status if this is the last operation
    - Auto-skips downstream operations if no good pieces remain
    """
    try:
        op, scrap_result = complete_operation(
            db=db,
            po_id=po_id,
            op_id=op_id,
            quantity_completed=request.quantity_completed,
            quantity_scrapped=request.quantity_scrapped,
            scrap_reason=request.scrap_reason,
            actual_run_minutes=request.actual_run_minutes,
            notes=request.notes,
            scrap_notes=request.scrap_notes,
            create_replacement=request.create_replacement,
            user_id=current_user.id if current_user else None,
        )
        db.commit()
    except OperationError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    po = db.get(ProductionOrder, po_id)
    next_op = get_next_operation(db, po, op)

    response = build_operation_response(op, po, next_op)

    # Add scrap result to response if available
    if scrap_result:
        response_dict = response.model_dump()
        response_dict["scrap_result"] = scrap_result
        return response_dict

    return response


@router.post(
    "/{po_id}/operations/{op_id}/skip",
    response_model=OperationResponse,
    summary="Skip an operation"
)
def skip_operation_endpoint(
    po_id: int,
    op_id: int,
    request: OperationSkipRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Skip an operation with a reason.

    Use cases:
    - Customer waived QC requirement
    - Operation not applicable for this product variant
    """
    try:
        op = skip_operation(
            db=db,
            po_id=po_id,
            op_id=op_id,
            reason=request.reason,
        )
        db.commit()
    except OperationError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    po = db.get(ProductionOrder, po_id)
    next_op = get_next_operation(db, po, op)

    return build_operation_response(op, po, next_op)


# =============================================================================
# Operation Blocking Check Endpoints (API-402)
# =============================================================================

@router.get(
    "/{po_id}/operations/{op_id}/can-start",
    response_model=CanStartResponse,
    summary="Check if operation can start"
)
def check_can_start(
    po_id: int,
    op_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Quick check if an operation can start based on material availability.

    Only checks materials for THIS operation's consume stage.
    For example, PRINT only checks production materials, not shipping materials.
    """
    try:
        result = can_operation_start(db, po_id, op_id)
        return result
    except OperationBlockingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/{po_id}/operations/{op_id}/blocking-issues",
    response_model=OperationBlockingResponse,
    summary="Get detailed blocking issues for operation"
)
def get_blocking_issues(
    po_id: int,
    op_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Get detailed blocking issues for an operation.

    Returns all material checks, not just blocking ones.
    Useful for showing full material requirements and availability.
    """
    try:
        result = check_operation_blocking(db, po_id, op_id)
        return result
    except OperationBlockingError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# =============================================================================
# Resource Scheduling Endpoints (API-403)
# =============================================================================

@router.get(
    "/{po_id}/check-resource-compatibility",
    summary="Check resource compatibility with production order materials"
)
def check_resource_compatibility(
    po_id: int,
    resource_id: int,
    is_printer: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Check if a resource/printer is compatible with a production order's materials.

    Returns compatibility status and reason.
    Used by the frontend to warn users before scheduling.
    """
    po = db.get(ProductionOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    from app.api.v1.endpoints.scheduling import is_machine_compatible

    if is_printer:
        printer = db.get(Printer, resource_id)
        if not printer:
            raise HTTPException(status_code=404, detail="Printer not found")

        class _PrinterAsResource:
            def __init__(self, p):
                self.code = p.code
                self.machine_type = p.model
        check_resource = _PrinterAsResource(printer)
    else:
        resource = db.get(Resource, resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")
        check_resource = resource

    compatible, reason = is_machine_compatible(db, check_resource, po)
    return {"compatible": compatible, "reason": reason}


@router.post(
    "/{po_id}/operations/{op_id}/schedule",
    response_model=ScheduleOperationResponse,
    summary="Schedule an operation on a resource"
)
def schedule_operation_endpoint(
    po_id: int,
    op_id: int,
    request: ScheduleOperationRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Schedule an operation on a resource with time slot validation.

    Validates:
    - Resource exists
    - Operation exists and belongs to this PO
    - No time conflicts with existing scheduled operations

    Returns 409 Conflict if scheduling would create a conflict.
    """
    # Validate PO exists
    po = db.get(ProductionOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    # Validate operation exists and belongs to PO
    op = db.get(ProductionOrderOperation, op_id)
    if not op:
        raise HTTPException(status_code=404, detail="Operation not found")
    if op.production_order_id != po_id:
        raise HTTPException(
            status_code=404,
            detail=f"Operation {op_id} does not belong to production order {po_id}"
        )

    # Validate resource/printer exists
    if request.is_printer:
        printer = db.get(Printer, request.resource_id)
        if not printer:
            raise HTTPException(status_code=404, detail="Printer not found")
        resource_obj = None
    else:
        resource = db.get(Resource, request.resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")
        resource_obj = resource

    # Check material/printer compatibility
    if resource_obj or request.is_printer:
        from app.api.v1.endpoints.scheduling import is_machine_compatible
        # For printers, build a resource-like object with machine_type
        if request.is_printer and printer:
            class _PrinterAsResource:
                def __init__(self, p):
                    self.code = p.code
                    self.machine_type = p.model
            check_resource = _PrinterAsResource(printer)
        else:
            check_resource = resource_obj
        if check_resource:
            compatible, reason = is_machine_compatible(db, check_resource, po)
            if not compatible:
                raise HTTPException(
                    status_code=422,
                    detail=f"Incompatible resource: {reason}"
                )

    # Attempt to schedule
    try:
        success, conflicts = schedule_operation_service(
            db=db,
            operation=op,
            resource_id=request.resource_id,
            scheduled_start=request.scheduled_start,
            scheduled_end=request.scheduled_end,
            is_printer=request.is_printer,
        )
    except SequenceError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not success:
        # Calculate next available slot for this resource
        from datetime import timedelta
        duration_minutes = int(
            (request.scheduled_end - request.scheduled_start).total_seconds() / 60
        )
        next_start = find_next_available_slot(
            db=db,
            resource_id=request.resource_id,
            duration_minutes=duration_minutes,
            after=request.scheduled_start,
            is_printer=request.is_printer,
        )
        suggested_end = next_start + timedelta(minutes=duration_minutes)

        # Build conflict details
        conflict_details = []
        for c in conflicts:
            conflict_details.append(ConflictInfo(
                operation_id=c.id,
                production_order_id=c.production_order_id,
                production_order_code=c.production_order.code if c.production_order else None,
                operation_code=c.operation_code,
                scheduled_start=c.scheduled_start,
                scheduled_end=c.scheduled_end,
            ))

        return ScheduleOperationResponse(
            success=False,
            message=f"Scheduling conflict with {len(conflicts)} existing operation(s)",
            conflicts=conflict_details,
            next_available_start=next_start,
            next_available_end=suggested_end,
        )

    db.commit()

    return ScheduleOperationResponse(success=True)


@router.post(
    "/resources/next-available",
    response_model=NextAvailableSlotResponse,
    summary="Find next available time slot on a resource"
)
def get_next_available_slot(
    request: NextAvailableSlotRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Find the next available time slot on a resource.

    Useful for suggesting alternative times when scheduling conflicts occur.
    Returns the earliest available start time and suggested end time.
    """
    from datetime import timedelta

    # Validate resource exists
    if request.is_printer:
        printer = db.get(Printer, request.resource_id)
        if not printer:
            raise HTTPException(status_code=404, detail="Printer not found")
        stored_resource_id = -request.resource_id
    else:
        resource = db.get(Resource, request.resource_id)
        if not resource:
            raise HTTPException(status_code=404, detail="Resource not found")
        stored_resource_id = request.resource_id

    # Find next available slot
    next_start = find_next_available_slot(
        db=db,
        resource_id=stored_resource_id,
        duration_minutes=request.duration_minutes,
        after=request.after
    )

    # Calculate suggested end time
    suggested_end = next_start + timedelta(minutes=request.duration_minutes)

    return NextAvailableSlotResponse(
        next_available=next_start,
        suggested_end=suggested_end
    )


# =============================================================================
# Operation Generation Endpoint (API-404)
# =============================================================================

@router.post(
    "/{po_id}/operations/generate",
    response_model=GenerateOperationsResponse,
    summary="Generate operations from routing"
)
def generate_operations(
    po_id: int,
    request: GenerateOperationsRequest = GenerateOperationsRequest(),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    Manually generate operations from routing.

    - Use force=True to replace existing operations
    - Without force, fails if operations already exist
    """
    po = db.get(ProductionOrder, po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Production order not found")

    try:
        created_ops = generate_operations_manual(db, po, force=request.force)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return GenerateOperationsResponse(
        success=True,
        operations_created=len(created_ops),
        message=f"Generated {len(created_ops)} operations from routing"
    )
