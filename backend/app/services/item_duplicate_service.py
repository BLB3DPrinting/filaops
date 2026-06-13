"""
Item Duplicate Service — clone an item with its BOM/routing and overrides.

Extracted verbatim from item_service.py (DEBT-1 D1-B mechanical split).
item_service re-exports duplicate_item for backward compatibility.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.utils import check_unique_or_400
from app.models import Product, BOM, BOMLine
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.services.bom_management_service import recalculate_bom_cost


def duplicate_item(
    db: Session,
    source_item_id: int,
    *,
    new_sku: str,
    new_name: str,
    bom_line_overrides: list[dict] | None = None,
) -> dict:
    """
    Duplicate a product: clone all fields with a new SKU/name,
    copy the active BOM (if any), and apply component overrides.

    Returns dict with: id, sku, name, has_bom, bom_id, message
    """
    # Function-level import avoids a circular import with item_service,
    # which re-exports this module's public functions.
    from app.services.item_service import get_item

    source = get_item(db, source_item_id)

    # Validate new SKU uniqueness
    new_sku_upper = new_sku.upper().strip()
    if not new_sku_upper:
        raise HTTPException(status_code=400, detail="SKU cannot be blank")
    new_name_clean = new_name.strip()
    if not new_name_clean:
        raise HTTPException(status_code=400, detail="Name cannot be blank")
    check_unique_or_400(db, Product, "sku", new_sku_upper)

    # Fields to exclude from copy:
    # - Identity: id, sku, name, timestamps
    # - External IDs: woocommerce, squarespace, legacy_sku, upc (unique per item)
    # - Purchase history: average_cost, last_cost (no history for new item)
    # - Per-variant assets: gcode_file_path, image_url (different per color/variant)
    # - B2B restriction: customer_id (new item starts unrestricted)
    EXCLUDE_FIELDS = {
        "id", "sku", "name", "created_at", "updated_at",
        "woocommerce_product_id", "squarespace_product_id",
        "legacy_sku", "upc",
        "average_cost", "last_cost",
        "gcode_file_path", "image_url",
        "customer_id",
        "parent_product_id", "is_template", "variant_metadata",
    }

    # Clone product fields
    clone_data = {}
    for col in Product.__table__.columns:
        if col.name not in EXCLUDE_FIELDS:
            clone_data[col.name] = getattr(source, col.name)

    clone_data["sku"] = new_sku_upper
    clone_data["name"] = new_name_clean
    clone_data["has_bom"] = False  # Will be set True if BOM is copied

    new_item = Product(**clone_data)
    db.add(new_item)
    db.flush()  # Get the new item's ID

    # Copy active BOM if source has one
    bom_id = None
    active_bom = (
        db.query(BOM)
        .filter(BOM.product_id == source.id, BOM.active.is_(True))
        .first()
    )

    if active_bom:
        new_bom = BOM(
            product_id=new_item.id,
            code=f"{new_sku_upper}-BOM"[:50],
            name=f"BOM for {new_item.name}"[:255],
            version=1,
            revision=active_bom.revision,
            assembly_time_minutes=active_bom.assembly_time_minutes,
            effective_date=active_bom.effective_date,
            notes=f"Duplicated from {source.sku}",
            active=True,
        )
        db.add(new_bom)
        db.flush()

        # Build override lookup: original_component_id -> new_component_id
        # NOTE: Keyed by component_id, so if the same component appears on
        # multiple BOM lines, ALL instances get swapped. This is intentional
        # for color variants (swap every instance of "PLA Red" to "PLA Blue").
        override_map = {}
        if bom_line_overrides:
            for ov in bom_line_overrides:
                orig_id = ov.get("original_component_id")
                new_id = ov.get("new_component_id")
                if orig_id and new_id:
                    # Validate new component exists
                    if not db.query(Product).filter(Product.id == new_id).first():
                        raise HTTPException(
                            status_code=400,
                            detail=f"Override component ID {new_id} not found"
                        )
                    override_map[orig_id] = new_id

        # Copy lines with overrides
        source_lines = (
            db.query(BOMLine)
            .filter(BOMLine.bom_id == active_bom.id)
            .order_by(BOMLine.sequence)
            .all()
        )
        for line in source_lines:
            component_id = override_map.get(line.component_id, line.component_id)
            new_line = BOMLine(
                bom_id=new_bom.id,
                component_id=component_id,
                quantity=line.quantity,
                unit=line.unit,
                sequence=line.sequence,
                consume_stage=line.consume_stage,
                is_cost_only=line.is_cost_only,
                scrap_factor=line.scrap_factor,
                notes=line.notes,
            )
            db.add(new_line)

        db.flush()
        new_bom.total_cost = recalculate_bom_cost(new_bom, db)
        new_item.has_bom = True
        bom_id = new_bom.id

    # Copy active routing if source has one
    routing_id = None
    active_routing = (
        db.query(Routing)
        .filter(Routing.product_id == source.id, Routing.is_active.is_(True))
        .first()
    )

    if active_routing:
        new_routing = Routing(
            product_id=new_item.id,
            code=f"RTG-{new_sku_upper}"[:50],
            name=f"Routing for {new_item.name}"[:200],
            is_template=False,
            version=1,
            revision="1.0",
            is_active=True,
            effective_date=active_routing.effective_date,
            notes=f"Duplicated from {source.sku}",
        )
        db.add(new_routing)
        db.flush()

        # Copy operations — track old_id -> new_id for predecessor remapping
        op_id_map: dict[int, int] = {}
        source_ops = (
            db.query(RoutingOperation)
            .options(joinedload(RoutingOperation.materials))
            .filter(RoutingOperation.routing_id == active_routing.id)
            .order_by(RoutingOperation.sequence)
            .all()
        )

        for op in source_ops:
            new_op = RoutingOperation(
                routing_id=new_routing.id,
                work_center_id=op.work_center_id,
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
                can_overlap=op.can_overlap,
                is_active=op.is_active,
                # predecessor_operation_id set in second pass below
            )
            db.add(new_op)
            db.flush()
            op_id_map[op.id] = new_op.id

            # Copy operation materials with component overrides
            for mat in op.materials:
                component_id = override_map.get(mat.component_id, mat.component_id) if active_bom else mat.component_id
                new_mat = RoutingOperationMaterial(
                    routing_operation_id=new_op.id,
                    component_id=component_id,
                    quantity=mat.quantity,
                    quantity_per=mat.quantity_per,
                    unit=mat.unit,
                    scrap_factor=mat.scrap_factor,
                    is_cost_only=mat.is_cost_only,
                    is_optional=mat.is_optional,
                    is_variable=mat.is_variable,
                    notes=mat.notes,
                )
                db.add(new_mat)

        # Second pass: remap predecessor_operation_id references
        for old_op in source_ops:
            if old_op.predecessor_operation_id and old_op.predecessor_operation_id in op_id_map:
                new_op_id = op_id_map[old_op.id]
                db.query(RoutingOperation).filter(
                    RoutingOperation.id == new_op_id
                ).update({
                    "predecessor_operation_id": op_id_map[old_op.predecessor_operation_id]
                })

        db.flush()
        # Use service function (does its own eager-loading) to avoid N+1
        from app.services.routing_service import recalculate_routing_totals
        recalculate_routing_totals(new_routing, db)
        routing_id = new_routing.id

    db.commit()
    db.refresh(new_item)

    # Build summary message
    parts = [f"Duplicated from {source.sku}"]
    if active_bom:
        parts.append(f"with BOM ({len(source_lines)} lines)")
    if active_routing:
        parts.append(f"routing ({len(source_ops)} operations)")
    if not active_bom and not active_routing:
        parts.append("(no BOM or routing)")

    return {
        "id": new_item.id,
        "sku": new_item.sku,
        "name": new_item.name,
        "has_bom": new_item.has_bom,
        "bom_id": bom_id,
        "routing_id": routing_id,
        "message": " ".join(parts),
    }
