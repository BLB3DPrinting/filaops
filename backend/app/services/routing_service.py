"""
Routing Service — CRUD for routings, operations, and operation materials.

Extracted from routings.py (ARCHITECT-003).
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.work_center import WorkCenter
from app.models.product import Product
from app.core.utils import get_or_404

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Routing CRUD
# ---------------------------------------------------------------------------


def list_routings(
    db: Session,
    *,
    product_id: int | None = None,
    templates_only: bool = False,
    active_only: bool = True,
    search: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Routing]:
    """List routings with optional filters. Eagerly loads product and operations."""
    query = db.query(Routing).options(
        joinedload(Routing.product),
        joinedload(Routing.operations),
    )

    if templates_only:
        query = query.filter(Routing.is_template.is_(True))
    elif product_id:
        query = query.filter(Routing.product_id == product_id)

    if active_only:
        query = query.filter(Routing.is_active.is_(True))

    if search:
        query = query.outerjoin(Product).filter(
            (Routing.code.ilike(f"%{search}%"))
            | (Routing.name.ilike(f"%{search}%"))
            | (Product.sku.ilike(f"%{search}%"))
            | (Product.name.ilike(f"%{search}%"))
        )

    return query.order_by(desc(Routing.created_at)).offset(skip).limit(limit).all()


def get_routing(db: Session, routing_id: int) -> Routing:
    """Get routing by ID with operations and product, or raise 404."""
    routing = (
        db.query(Routing)
        .options(
            joinedload(Routing.product),
            joinedload(Routing.operations).joinedload(RoutingOperation.work_center),
        )
        .filter(Routing.id == routing_id)
        .first()
    )
    if not routing:
        raise HTTPException(status_code=404, detail="Routing not found")
    return routing


def get_product_routing(db: Session, product_id: int) -> Routing:
    """Get the active routing for a product (latest version), or raise 404."""
    routing = (
        db.query(Routing)
        .options(
            joinedload(Routing.product),
            joinedload(Routing.operations).joinedload(RoutingOperation.work_center),
        )
        .filter(Routing.product_id == product_id, Routing.is_active.is_(True))
        .order_by(desc(Routing.version))
        .first()
    )
    if not routing:
        raise HTTPException(status_code=404, detail="No active routing found for product")
    return routing


def create_routing(db: Session, *, data: dict, operations: list[dict] | None = None) -> Routing:
    """Create a new routing, optionally with operations."""
    is_template = data.get("is_template", False)
    product = None

    if is_template:
        if not data.get("code"):
            raise HTTPException(status_code=400, detail="Template routing requires a code")
        if not data.get("name"):
            raise HTTPException(status_code=400, detail="Template routing requires a name")
        code = data["code"]
        name = data["name"]
    else:
        product_id = data.get("product_id")
        if not product_id:
            raise HTTPException(status_code=400, detail="Product ID is required for non-template routings")
        product = get_or_404(db, Product, product_id, "Product not found")
        code = data.get("code") or f"RTG-{product.sku}-V{data.get('version', 1)}"
        name = data.get("name") or f"{product.name} Routing"

    routing = Routing(
        product_id=data.get("product_id") if not is_template else None,
        code=code,
        name=name,
        is_template=is_template,
        version=data.get("version", 1),
        revision=data.get("revision"),
        effective_date=data.get("effective_date"),
        notes=data.get("notes"),
        is_active=data.get("is_active", True),
    )
    db.add(routing)
    db.flush()

    if operations:
        for op_data in operations:
            wc_id = op_data.get("work_center_id")
            if not db.query(WorkCenter).filter(WorkCenter.id == wc_id).first():
                db.rollback()  # Rollback flushed routing before raising
                raise HTTPException(status_code=400, detail=f"Work center {wc_id} not found")
            operation = RoutingOperation(routing_id=routing.id, **op_data)
            db.add(operation)

    db.flush()
    recalculate_routing_totals(routing, db)
    db.commit()
    db.refresh(routing)

    if is_template:
        logger.info(f"Created template routing: {routing.code}")
    else:
        logger.info(f"Created routing: {routing.code} for product {product.sku if product else 'N/A'}")

    return routing


def update_routing(db: Session, routing_id: int, *, data: dict) -> Routing:
    """Update a routing's fields."""
    routing = get_or_404(db, Routing, routing_id, "Routing not found")

    for field, value in data.items():
        setattr(routing, field, value)

    routing.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(routing)

    logger.info(f"Updated routing: {routing.code}")
    return routing


def delete_routing(db: Session, routing_id: int) -> None:
    """Soft-delete a routing."""
    routing = get_or_404(db, Routing, routing_id, "Routing not found")
    routing.is_active = False
    routing.updated_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(f"Deactivated routing: {routing.code}")


# ---------------------------------------------------------------------------
# Template Seeding & Application
# ---------------------------------------------------------------------------

# Template definitions (data-only, no DB operations)
ROUTING_TEMPLATES = [
    {
        "code": "TPL-STANDARD",
        "name": "Standard Flow",
        "notes": "Standard routing: Print → QC → Pack → Ship",
        "operations": [
            {"sequence": 10, "operation_code": "PRINT", "operation_name": "3D Print", "work_center_code": "FDM-POOL", "setup_time_minutes": Decimal("7"), "run_time_minutes": Decimal("60"), "runtime_source": "slicer"},
            {"sequence": 20, "operation_code": "QC", "operation_name": "Quality Check", "work_center_code": "QC", "setup_time_minutes": Decimal("0"), "run_time_minutes": Decimal("2")},
            {"sequence": 30, "operation_code": "PACK", "operation_name": "Pack", "work_center_code": "SHIPPING", "setup_time_minutes": Decimal("1"), "run_time_minutes": Decimal("2")},
            {"sequence": 40, "operation_code": "SHIP", "operation_name": "Ship", "work_center_code": "SHIPPING", "setup_time_minutes": Decimal("0"), "run_time_minutes": Decimal("3")},
        ],
    },
    {
        "code": "TPL-ASSEMBLY",
        "name": "Assembly Flow",
        "notes": "Assembly routing: Print → QC → Assemble → Pack → Ship",
        "operations": [
            {"sequence": 10, "operation_code": "PRINT", "operation_name": "3D Print", "work_center_code": "FDM-POOL", "setup_time_minutes": Decimal("7"), "run_time_minutes": Decimal("60"), "runtime_source": "slicer"},
            {"sequence": 20, "operation_code": "QC", "operation_name": "Quality Check", "work_center_code": "QC", "setup_time_minutes": Decimal("0"), "run_time_minutes": Decimal("2")},
            {"sequence": 30, "operation_code": "ASSEMBLE", "operation_name": "Assembly", "work_center_code": "ASSEMBLY", "setup_time_minutes": Decimal("0"), "run_time_minutes": Decimal("5")},
            {"sequence": 40, "operation_code": "PACK", "operation_name": "Pack", "work_center_code": "SHIPPING", "setup_time_minutes": Decimal("1"), "run_time_minutes": Decimal("2")},
            {"sequence": 50, "operation_code": "SHIP", "operation_name": "Ship", "work_center_code": "SHIPPING", "setup_time_minutes": Decimal("0"), "run_time_minutes": Decimal("3")},
        ],
    },
]


def seed_routing_templates(db: Session) -> dict:
    """Seed standard routing templates. Safe to call multiple times."""
    created = []
    skipped = []

    # Build work center lookup
    work_centers = {}
    for wc in db.query(WorkCenter).filter(WorkCenter.is_active.is_(True)).all():
        work_centers[wc.code] = wc

    required = ["FDM-POOL", "QC", "ASSEMBLY", "SHIPPING"]
    missing = [code for code in required if code not in work_centers]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required work centers: {', '.join(missing)}. Please create them first.",
        )

    for tpl in ROUTING_TEMPLATES:
        existing = (
            db.query(Routing)
            .filter(Routing.code == tpl["code"], Routing.is_template.is_(True))
            .first()
        )
        if existing:
            skipped.append(tpl["code"])
            continue

        routing = Routing(
            code=tpl["code"],
            name=tpl["name"],
            notes=tpl["notes"],
            is_template=True,
            version=1,
            revision="1.0",
            is_active=True,
        )
        db.add(routing)
        db.flush()

        for op_data in tpl["operations"]:
            wc = work_centers[op_data["work_center_code"]]
            operation = RoutingOperation(
                routing_id=routing.id,
                work_center_id=wc.id,
                sequence=op_data["sequence"],
                operation_code=op_data["operation_code"],
                operation_name=op_data["operation_name"],
                setup_time_minutes=op_data["setup_time_minutes"],
                run_time_minutes=op_data["run_time_minutes"],
                wait_time_minutes=Decimal("0"),
                move_time_minutes=Decimal("0"),
                runtime_source=op_data.get("runtime_source", "manual"),
                is_active=True,
            )
            db.add(operation)

        db.flush()
        recalculate_routing_totals(routing, db)
        created.append(tpl["code"])

    db.commit()
    logger.info(f"Seeded routing templates - Created: {created}, Skipped: {skipped}")
    return {"message": "Routing templates seeded", "created": created, "skipped": skipped}


def apply_template_to_product(
    db: Session,
    *,
    template_id: int,
    product_id: int,
    overrides: dict[str, dict] | None = None,
) -> tuple[Routing, list[RoutingOperation], str]:
    """
    Apply a routing template to a product.

    Returns (routing, new_operations, message).
    """
    overrides = overrides or {}

    template = (
        db.query(Routing)
        .options(joinedload(Routing.operations).joinedload(RoutingOperation.work_center))
        .filter(
            Routing.id == template_id,
            Routing.is_template.is_(True),
            Routing.is_active.is_(True),
        )
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    product = get_or_404(db, Product, product_id, "Product not found")

    existing = (
        db.query(Routing)
        .filter(Routing.product_id == product_id, Routing.is_active.is_(True))
        .first()
    )

    if existing:
        for op in existing.operations:
            op.is_active = False
        db.flush()
        routing = existing
        routing.name = f"{template.name} - {product.sku}"
        routing.notes = f"Applied from template {template.code}"
        routing.updated_at = datetime.now(timezone.utc)
        message = f"Updated routing for {product.sku}"
    else:
        routing = Routing(
            product_id=product.id,
            code=f"RTG-{product.sku}",
            name=f"{template.name} - {product.sku}",
            is_template=False,
            version=1,
            revision="1.0",
            is_active=True,
            notes=f"Applied from template {template.code}",
        )
        db.add(routing)
        db.flush()
        message = f"Created routing for {product.sku}"

    new_operations = []
    for tpl_op in template.operations:
        if not tpl_op.is_active:
            continue

        override = overrides.get(tpl_op.operation_code, {})
        run_time = override.get("run_time_minutes", tpl_op.run_time_minutes)
        setup_time = override.get("setup_time_minutes", tpl_op.setup_time_minutes)

        operation = RoutingOperation(
            routing_id=routing.id,
            work_center_id=tpl_op.work_center_id,
            sequence=tpl_op.sequence,
            operation_code=tpl_op.operation_code,
            operation_name=tpl_op.operation_name,
            description=tpl_op.description,
            setup_time_minutes=setup_time,
            run_time_minutes=run_time,
            wait_time_minutes=tpl_op.wait_time_minutes,
            move_time_minutes=tpl_op.move_time_minutes,
            runtime_source="slicer" if override.get("run_time_minutes") else tpl_op.runtime_source,
            units_per_cycle=tpl_op.units_per_cycle,
            scrap_rate_percent=tpl_op.scrap_rate_percent,
            is_active=True,
        )
        db.add(operation)
        new_operations.append(operation)

    db.flush()
    recalculate_routing_totals(routing, db)
    db.commit()
    db.refresh(routing)

    logger.info(f"Applied template {template.code} to product {product.sku}")
    return routing, new_operations, message


# ---------------------------------------------------------------------------
# Operation CRUD
# ---------------------------------------------------------------------------


def list_operations(
    db: Session, routing_id: int, *, active_only: bool = True
) -> list[RoutingOperation]:
    """List operations for a routing with work center loaded."""
    get_or_404(db, Routing, routing_id, "Routing not found")

    query = (
        db.query(RoutingOperation)
        .options(joinedload(RoutingOperation.work_center))
        .filter(RoutingOperation.routing_id == routing_id)
    )
    if active_only:
        query = query.filter(RoutingOperation.is_active.is_(True))

    return query.order_by(RoutingOperation.sequence).all()


def add_operation(db: Session, routing_id: int, *, data: dict) -> RoutingOperation:
    """Add an operation to a routing."""
    routing = get_or_404(db, Routing, routing_id, "Routing not found")
    wc_id = data["work_center_id"]
    if not db.query(WorkCenter).filter(WorkCenter.id == wc_id).first():
        raise HTTPException(status_code=400, detail=f"Work center {wc_id} not found")

    # Convert enum values
    if "runtime_source" in data and hasattr(data["runtime_source"], "value"):
        data["runtime_source"] = data["runtime_source"].value

    operation = RoutingOperation(routing_id=routing_id, **data)
    db.add(operation)
    db.flush()

    recalculate_routing_totals(routing, db)
    db.commit()
    db.refresh(operation)

    logger.info(f"Added operation {operation.sequence} to routing {routing.code}")
    return operation


def get_operation(db: Session, operation_id: int) -> RoutingOperation:
    """Get an operation by ID with routing and work center loaded."""
    operation = (
        db.query(RoutingOperation)
        .options(
            joinedload(RoutingOperation.routing),
            joinedload(RoutingOperation.work_center),
        )
        .filter(RoutingOperation.id == operation_id)
        .first()
    )
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
    return operation


def update_operation(db: Session, operation_id: int, *, data: dict) -> RoutingOperation:
    """Update a routing operation."""
    operation = get_operation(db, operation_id)

    if "work_center_id" in data:
        wc_id = data["work_center_id"]
        if not db.query(WorkCenter).filter(WorkCenter.id == wc_id).first():
            raise HTTPException(status_code=400, detail=f"Work center {wc_id} not found")

    for field, value in data.items():
        if field == "runtime_source" and value and hasattr(value, "value"):
            value = value.value
        setattr(operation, field, value)

    operation.updated_at = datetime.now(timezone.utc)
    recalculate_routing_totals(operation.routing, db)
    db.commit()
    db.refresh(operation)

    logger.info(f"Updated operation {operation.id}")
    return operation


def delete_operation(db: Session, operation_id: int) -> None:
    """Soft-delete a routing operation."""
    operation = get_operation(db, operation_id)
    operation.is_active = False
    operation.updated_at = datetime.now(timezone.utc)
    recalculate_routing_totals(operation.routing, db)
    db.commit()
    logger.info(f"Deactivated operation {operation_id}")


# ---------------------------------------------------------------------------
# Operation Material CRUD
# ---------------------------------------------------------------------------


def list_operation_materials(
    db: Session, operation_id: int
) -> list[RoutingOperationMaterial]:
    """List materials for an operation."""
    get_or_404(db, RoutingOperation, operation_id, "Operation not found")

    return (
        db.query(RoutingOperationMaterial)
        .options(joinedload(RoutingOperationMaterial.component))
        .filter(RoutingOperationMaterial.routing_operation_id == operation_id)
        .all()
    )


def add_operation_material(
    db: Session, operation_id: int, *, data: dict
) -> RoutingOperationMaterial:
    """Add a material to an operation."""
    get_or_404(db, RoutingOperation, operation_id, "Operation not found")
    component = db.query(Product).filter(Product.id == data["component_id"]).first()
    if not component:
        raise HTTPException(status_code=400, detail="Component product not found")

    # Guard: prevent duplicate materials on the same operation
    duplicate = (
        db.query(RoutingOperationMaterial)
        .filter(
            RoutingOperationMaterial.routing_operation_id == operation_id,
            RoutingOperationMaterial.component_id == data["component_id"],
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="This material is already on this operation — adjust the quantity on the existing entry instead.",
        )

    # Convert enum values
    if "quantity_per" in data and hasattr(data["quantity_per"], "value"):
        data["quantity_per"] = data["quantity_per"].value

    material = RoutingOperationMaterial(routing_operation_id=operation_id, **data)
    db.add(material)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=409,
                detail="This material is already on this operation — adjust the quantity on the existing entry instead.",
            )
        raise

    # Recalculate routing totals to include the new material cost
    operation = db.query(RoutingOperation).filter(RoutingOperation.id == operation_id).first()
    if operation and operation.routing:
        recalculate_routing_totals(operation.routing, db)

    db.commit()
    db.refresh(material)

    logger.info(f"Added material {component.sku} to operation {operation_id}")
    return material


def update_operation_material(
    db: Session, material_id: int, *, data: dict
) -> RoutingOperationMaterial:
    """Update a routing operation material."""
    material = (
        db.query(RoutingOperationMaterial)
        .filter(RoutingOperationMaterial.id == material_id)
        .first()
    )
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    if "component_id" in data:
        if not db.query(Product).filter(Product.id == data["component_id"]).first():
            raise HTTPException(status_code=400, detail="Component product not found")

    for field, value in data.items():
        if field == "quantity_per" and value and hasattr(value, "value"):
            value = value.value
        setattr(material, field, value)

    material.updated_at = datetime.now(timezone.utc)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise HTTPException(
                status_code=409,
                detail="This material is already on this operation — adjust the quantity on the existing entry instead.",
            )
        raise

    # Recalculate routing totals to reflect the material change
    if material.routing_operation and material.routing_operation.routing:
        recalculate_routing_totals(material.routing_operation.routing, db)

    db.commit()
    db.refresh(material)

    logger.info(f"Updated material {material_id}")
    return material


def delete_operation_material(db: Session, material_id: int) -> None:
    """Delete a routing operation material (hard delete)."""
    material = (
        db.query(RoutingOperationMaterial)
        .filter(RoutingOperationMaterial.id == material_id)
        .first()
    )
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    routing = material.routing_operation.routing if material.routing_operation else None
    db.delete(material)
    db.flush()

    # Recalculate routing totals after material removal
    if routing:
        recalculate_routing_totals(routing, db)

    db.commit()
    logger.info(f"Deleted material {material_id}")


# ---------------------------------------------------------------------------
# Manufacturing BOM
# ---------------------------------------------------------------------------


def get_manufacturing_bom(db: Session, product_id: int) -> tuple[Routing, Product]:
    """Get the active routing with full materials for a product's manufacturing BOM.

    Returns (routing, product).
    """
    product = get_or_404(db, Product, product_id, "Product not found")

    routing = (
        db.query(Routing)
        .options(
            joinedload(Routing.operations).joinedload(RoutingOperation.work_center),
            joinedload(Routing.operations)
            .joinedload(RoutingOperation.materials)
            .joinedload(RoutingOperationMaterial.component),
        )
        .filter(Routing.product_id == product_id, Routing.is_active.is_(True))
        .order_by(desc(Routing.version))
        .first()
    )
    if not routing:
        raise HTTPException(status_code=404, detail="No active routing found for product")

    return routing, product


# ---------------------------------------------------------------------------
# Shared Helpers
# ---------------------------------------------------------------------------


def recalculate_routing_totals(routing: Routing, db: Session) -> None:
    """Recalculate routing totals from active operations.

    Cost includes setup + run time labor AND operation material costs.
    """
    operations = (
        db.query(RoutingOperation)
        .options(
            joinedload(RoutingOperation.work_center),
            joinedload(RoutingOperation.materials)
            .joinedload(RoutingOperationMaterial.component),
        )
        .filter(
            RoutingOperation.routing_id == routing.id,
            RoutingOperation.is_active.is_(True),
        )
        .all()
    )

    total_setup = Decimal("0")
    total_run = Decimal("0")
    total_cost = Decimal("0")

    for op in operations:
        total_setup += op.setup_time_minutes or Decimal("0")
        total_run += (
            (op.run_time_minutes or Decimal("0"))
            + (op.wait_time_minutes or Decimal("0"))
            + (op.move_time_minutes or Decimal("0"))
        )

        # Delegate to model properties (return Decimal natively)
        total_cost += op.calculated_cost
        total_cost += op.material_cost

    routing.total_setup_time_minutes = total_setup
    routing.total_run_time_minutes = total_run
    routing.total_cost = total_cost
    routing.updated_at = datetime.now(timezone.utc)
