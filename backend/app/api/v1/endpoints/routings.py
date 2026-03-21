"""
Routings API Endpoints

CRUD operations for routings and routing operations.
Uses routing_service for business logic (ARCHITECT-003).
"""
# pyright: reportArgumentType=false
# pyright: reportAssignmentType=false
# SQLAlchemy Column types resolve to actual values at runtime
from fastapi import APIRouter, Depends, Query, status
from typing import List, Optional
from decimal import Decimal
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.product import Product
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.schemas.manufacturing import (
    RoutingCreate,
    RoutingUpdate,
    RoutingResponse,
    RoutingListResponse,
    RoutingOperationCreate,
    RoutingOperationUpdate,
    RoutingOperationResponse,
    ApplyTemplateRequest,
    ApplyTemplateResponse,
    RoutingOperationMaterialCreate,
    RoutingOperationMaterialUpdate,
    RoutingOperationMaterialResponse,
    RoutingOperationWithMaterialsResponse,
    ManufacturingBOMResponse,
)
from app.services import routing_service

router = APIRouter()
logger = get_logger(__name__)


# ============================================================================
# Routing CRUD
# ============================================================================

@router.get("/", response_model=List[RoutingListResponse])
async def list_routings(
    product_id: Optional[int] = None,
    templates_only: bool = False,
    active_only: bool = True,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    List all routings.

    - **product_id**: Filter by product
    - **templates_only**: Only return template routings (no product_id)
    - **active_only**: Only return active routings
    - **search**: Search by code or product name
    """
    routings = routing_service.list_routings(
        db,
        product_id=product_id,
        templates_only=templates_only,
        active_only=active_only,
        search=search,
        skip=skip,
        limit=limit,
    )

    return [
        RoutingListResponse(  # type: ignore[arg-type]
            id=r.id,
            product_id=r.product_id,
            product_sku=r.product.sku if r.product else None,
            product_name=r.product.name if r.product else None,
            code=r.code,
            name=r.name,
            is_template=r.is_template,
            version=r.version,
            revision=r.revision,
            is_active=r.is_active,
            total_run_time_minutes=r.total_run_time_minutes,
            total_cost=r.total_cost,
            operation_count=len([op for op in r.operations if op.is_active]),
            created_at=r.created_at,
        )
        for r in routings
    ]


@router.post("/", response_model=RoutingResponse, status_code=status.HTTP_201_CREATED)
async def create_routing(
    data: RoutingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new routing for a product or a template routing."""
    # Build operation dicts with enum conversion
    operations = None
    if data.operations:
        operations = []
        for op_data in data.operations:
            op_dict = op_data.model_dump()
            if "runtime_source" in op_dict and hasattr(op_dict["runtime_source"], "value"):
                op_dict["runtime_source"] = op_dict["runtime_source"].value
            operations.append(op_dict)

    routing = routing_service.create_routing(
        db,
        data=data.model_dump(exclude={"operations"}),
        operations=operations,
    )
    return _build_routing_response(routing, db)


# ============================================================================
# Template Seeding (MUST be before /{routing_id} routes!)
# ============================================================================

@router.post("/seed-templates")
async def seed_routing_templates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Seed the two standard routing templates:
    - Standard Flow: Print → QC → Pack → Ship
    - Assembly Flow: Print → QC → Assemble → Pack → Ship

    Safe to call multiple times - will skip existing templates.
    """
    return routing_service.seed_routing_templates(db)


@router.post("/apply-template", response_model=ApplyTemplateResponse)
async def apply_template_to_product(
    data: ApplyTemplateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Apply a routing template to a product, creating a product-specific routing.

    - Copies operations from the template
    - Allows overriding times for specific operations (e.g., print time from slicer)
    - Creates or updates the routing for the product
    """
    # Build override map: operation_code -> {run_time_minutes, setup_time_minutes}
    override_map = {}
    for o in data.overrides:
        override_map[o.operation_code] = {}
        if o.run_time_minutes is not None:
            override_map[o.operation_code]["run_time_minutes"] = o.run_time_minutes
        if o.setup_time_minutes is not None:
            override_map[o.operation_code]["setup_time_minutes"] = o.setup_time_minutes

    routing, new_operations, message = routing_service.apply_template_to_product(
        db,
        template_id=data.template_id,
        product_id=data.product_id,
        overrides=override_map,
    )

    # Build response with operations
    ops_response = []
    for op in new_operations:
        db.refresh(op)
        ops_response.append(_build_operation_response(op))

    product = routing.product
    return ApplyTemplateResponse(  # type: ignore[arg-type]
        routing_id=routing.id,
        routing_code=routing.code,
        product_sku=product.sku if product else "",
        product_name=product.name if product else "",
        operations=ops_response,
        total_run_time_minutes=routing.total_run_time_minutes or Decimal("0"),
        total_cost=routing.total_cost or Decimal("0"),
        message=message,
    )


# ============================================================================
# Single Routing CRUD
# ============================================================================

@router.get("/{routing_id}", response_model=RoutingResponse)
async def get_routing(
    routing_id: int,
    db: Session = Depends(get_db),
):
    """Get a routing by ID with all operations."""
    routing = routing_service.get_routing(db, routing_id)
    return _build_routing_response(routing, db)


@router.get("/product/{product_id}", response_model=RoutingResponse)
async def get_product_routing(
    product_id: int,
    db: Session = Depends(get_db),
):
    """Get the active routing for a product."""
    routing = routing_service.get_product_routing(db, product_id)
    return _build_routing_response(routing, db)


@router.put("/{routing_id}", response_model=RoutingResponse)
async def update_routing(
    routing_id: int,
    data: RoutingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a routing."""
    routing = routing_service.update_routing(
        db, routing_id, data=data.model_dump(exclude_unset=True)
    )
    return _build_routing_response(routing, db)


@router.delete("/{routing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routing(
    routing_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a routing (soft delete - marks as inactive)."""
    routing_service.delete_routing(db, routing_id)


# ============================================================================
# Routing Operations CRUD
# ============================================================================

@router.get("/{routing_id}/operations", response_model=List[RoutingOperationResponse])
async def list_routing_operations(
    routing_id: int,
    active_only: bool = True,
    db: Session = Depends(get_db),
):
    """List all operations for a routing."""
    operations = routing_service.list_operations(db, routing_id, active_only=active_only)
    return [_build_operation_response(op) for op in operations]


@router.post("/{routing_id}/operations", response_model=RoutingOperationResponse, status_code=status.HTTP_201_CREATED)
async def add_routing_operation(
    routing_id: int,
    data: RoutingOperationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a new operation to a routing."""
    operation = routing_service.add_operation(
        db, routing_id, data=data.model_dump()
    )
    return _build_operation_response(operation)


@router.put("/operations/{operation_id}", response_model=RoutingOperationResponse)
async def update_routing_operation(
    operation_id: int,
    data: RoutingOperationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a routing operation."""
    operation = routing_service.update_operation(
        db, operation_id, data=data.model_dump(exclude_unset=True)
    )
    return _build_operation_response(operation)


@router.delete("/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routing_operation(
    operation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a routing operation (soft delete)."""
    routing_service.delete_operation(db, operation_id)


# ============================================================================
# Routing Operation Materials CRUD (Manufacturing BOM)
# ============================================================================

@router.get("/operations/{operation_id}/materials", response_model=List[RoutingOperationMaterialResponse])
async def list_operation_materials(
    operation_id: int,
    db: Session = Depends(get_db),
):
    """List all materials for a routing operation."""
    materials = routing_service.list_operation_materials(db, operation_id)
    return [_build_material_response(m) for m in materials]


@router.post("/operations/{operation_id}/materials", response_model=RoutingOperationMaterialResponse, status_code=status.HTTP_201_CREATED)
async def add_operation_material(
    operation_id: int,
    data: RoutingOperationMaterialCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a material to a routing operation."""
    material = routing_service.add_operation_material(
        db, operation_id, data=data.model_dump()
    )
    return _build_material_response(material)


@router.put("/materials/{material_id}", response_model=RoutingOperationMaterialResponse)
async def update_operation_material(
    material_id: int,
    data: RoutingOperationMaterialUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a routing operation material."""
    material = routing_service.update_operation_material(
        db, material_id, data=data.model_dump(exclude_unset=True)
    )
    return _build_material_response(material)


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_operation_material(
    material_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a routing operation material."""
    routing_service.delete_operation_material(db, material_id)


# ============================================================================
# Manufacturing BOM View (unified routing + materials)
# ============================================================================

@router.get("/manufacturing-bom/{product_id}", response_model=ManufacturingBOMResponse)
async def get_manufacturing_bom(
    product_id: int,
    db: Session = Depends(get_db),
):
    """
    Get the complete Manufacturing BOM for a product.

    Returns the active routing with all operations and their materials,
    providing a unified view of the manufacturing process.
    """
    routing, product = routing_service.get_manufacturing_bom(db, product_id)
    return _build_manufacturing_bom_response(routing, product, db)


# ============================================================================
# Helper Functions (presentation only — no DB queries)
# ============================================================================

def _build_routing_response(routing: Routing, db: Session) -> RoutingResponse:
    """Build a routing response with operations."""
    operations = []
    for op in sorted(routing.operations, key=lambda x: x.sequence):
        if op.is_active:
            operations.append(_build_operation_response(op))

    return RoutingResponse(  # type: ignore[arg-type]
        id=routing.id,
        product_id=routing.product_id,
        product_sku=routing.product.sku if routing.product else None,
        product_name=routing.product.name if routing.product else None,
        code=routing.code,
        name=routing.name,
        is_template=routing.is_template,
        version=routing.version,
        revision=routing.revision,
        effective_date=routing.effective_date,
        notes=routing.notes,
        is_active=routing.is_active,
        total_setup_time_minutes=routing.total_setup_time_minutes,
        total_run_time_minutes=routing.total_run_time_minutes,
        total_cost=routing.total_cost,
        operations=operations,
        created_at=routing.created_at,
        updated_at=routing.updated_at,
    )


def _build_operation_response(op: RoutingOperation) -> RoutingOperationResponse:
    """Build a routing operation response."""
    total_time = (
        (op.setup_time_minutes or Decimal("0")) +
        (op.run_time_minutes or Decimal("0")) +
        (op.wait_time_minutes or Decimal("0")) +
        (op.move_time_minutes or Decimal("0"))
    )

    # Use model's component-wise rate calculation
    calculated_cost = Decimal(str(op.calculated_cost))

    return RoutingOperationResponse(  # type: ignore[arg-type]
        id=op.id,
        routing_id=op.routing_id,
        work_center_id=op.work_center_id,
        work_center_code=op.work_center.code if op.work_center else None,
        work_center_name=op.work_center.name if op.work_center else None,
        sequence=op.sequence,
        operation_code=op.operation_code,
        operation_name=op.operation_name,
        description=op.description,
        setup_time_minutes=op.setup_time_minutes,
        run_time_minutes=op.run_time_minutes,
        wait_time_minutes=op.wait_time_minutes,
        move_time_minutes=op.move_time_minutes,
        runtime_source=op.runtime_source,
        slicer_file_path=op.slicer_file_path,
        units_per_cycle=op.units_per_cycle,
        scrap_rate_percent=op.scrap_rate_percent,
        labor_rate_override=op.labor_rate_override,
        machine_rate_override=op.machine_rate_override,
        predecessor_operation_id=op.predecessor_operation_id,
        can_overlap=op.can_overlap,
        is_active=op.is_active,
        total_time_minutes=total_time,
        calculated_cost=calculated_cost,
        created_at=op.created_at,
        updated_at=op.updated_at,
    )


def _build_material_response(material: RoutingOperationMaterial) -> RoutingOperationMaterialResponse:
    """Build a routing operation material response."""
    component = material.component

    return RoutingOperationMaterialResponse(  # type: ignore[arg-type]
        id=material.id,
        routing_operation_id=material.routing_operation_id,
        component_id=material.component_id,
        component_sku=component.sku if component else None,
        component_name=component.name if component else None,
        quantity=material.quantity,
        quantity_per=material.quantity_per,
        unit=material.unit,
        scrap_factor=material.scrap_factor,
        is_cost_only=material.is_cost_only,
        is_optional=material.is_optional,
        notes=material.notes,
        unit_cost=material.unit_cost or Decimal("0"),
        extended_cost=material.extended_cost or Decimal("0"),
        created_at=material.created_at,
        updated_at=material.updated_at,
    )


def _build_operation_with_materials_response(
    op: RoutingOperation,
    db: Session
) -> RoutingOperationWithMaterialsResponse:
    """Build a routing operation response with materials."""
    base = _build_operation_response(op)

    # Get materials for this operation
    materials = [_build_material_response(m) for m in (op.materials or [])]

    # Calculate material cost
    material_cost = sum(m.extended_cost for m in materials)
    total_cost_with_materials = base.calculated_cost + material_cost

    return RoutingOperationWithMaterialsResponse(
        **base.model_dump(),
        materials=materials,
        material_cost=material_cost,
        total_cost_with_materials=total_cost_with_materials,
    )


def _build_manufacturing_bom_response(
    routing: Routing,
    product: Product,
    db: Session
) -> ManufacturingBOMResponse:
    """Build a complete Manufacturing BOM response."""
    operations = []
    total_labor_cost = Decimal("0")
    total_material_cost = Decimal("0")

    for op in sorted(routing.operations, key=lambda x: x.sequence):
        if op.is_active:
            op_response = _build_operation_with_materials_response(op, db)
            operations.append(op_response)
            total_labor_cost += op_response.calculated_cost
            total_material_cost += op_response.material_cost

    return ManufacturingBOMResponse(  # type: ignore[arg-type]
        routing_id=routing.id,
        routing_code=routing.code,
        routing_name=routing.name,
        product_id=product.id,
        product_sku=product.sku,
        product_name=product.name,
        version=routing.version,
        revision=routing.revision,
        is_active=routing.is_active,
        operations=operations,
        total_labor_cost=total_labor_cost,
        total_material_cost=total_material_cost,
        total_cost=total_labor_cost + total_material_cost,
        created_at=routing.created_at,
        updated_at=routing.updated_at,
    )
