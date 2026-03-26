"""
Variant Service — CRUD for template/variant product relationships.

Variants are real Product rows linked to a template via parent_product_id.
This service handles creating variants (with BOM/routing material swaps),
bulk creation, listing, and deletion. Reuses duplicate_item() internal
logic for the actual product/BOM/routing cloning.
"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Product, Inventory
from app.models.material import MaterialType, Color, MaterialColor
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.services.item_service import (
    duplicate_item,
    get_item,
    calculate_item_cost,
)

logger = get_logger(__name__)


def _find_material_product(db: Session, material_type_id: int, color_id: int) -> Product:
    """Find the supply Product that represents a specific material+color combo."""
    product = (
        db.query(Product)
        .filter(
            Product.material_type_id == material_type_id,
            Product.color_id == color_id,
            Product.active.is_(True),
        )
        .first()
    )
    if not product:
        raise HTTPException(
            status_code=404,
            detail=f"No active product found for material_type_id={material_type_id}, color_id={color_id}",
        )
    return product


def _get_variable_material_ids(db: Session, template: Product) -> set[int]:
    """Get component_ids of all is_variable=True routing materials for the template."""
    rows = (
        db.query(RoutingOperationMaterial.component_id)
        .join(RoutingOperation, RoutingOperationMaterial.routing_operation_id == RoutingOperation.id)
        .join(Routing, RoutingOperation.routing_id == Routing.id)
        .filter(
            Routing.product_id == template.id,
            Routing.is_active.is_(True),
            RoutingOperationMaterial.is_variable.is_(True),
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def create_variant(
    db: Session,
    template_id: int,
    material_type_id: int,
    color_id: int,
    *,
    selling_price: Decimal | None = None,
    gcode_file_path: str | None = None,
) -> dict:
    """
    Create a single variant from a template product.

    Finds the material product for the chosen material+color, builds BOM line
    overrides from is_variable routing materials, then delegates to duplicate_item().
    Sets parent_product_id and variant_metadata on the result.
    """
    template = get_item(db, template_id)

    # Validate material+color combo exists in MaterialColor junction
    mc = (
        db.query(MaterialColor)
        .filter(
            MaterialColor.material_type_id == material_type_id,
            MaterialColor.color_id == color_id,
        )
        .first()
    )
    if not mc:
        raise HTTPException(
            status_code=400,
            detail="Invalid material/color combination",
        )

    # Look up MaterialType and Color for SKU/name generation
    mat_type = db.query(MaterialType).filter(MaterialType.id == material_type_id).first()
    color = db.query(Color).filter(Color.id == color_id).first()
    if not mat_type or not color:
        raise HTTPException(status_code=404, detail="Material type or color not found")

    # Find the supply product for this material+color
    target_material = _find_material_product(db, material_type_id, color_id)

    # Generate SKU and name
    new_sku = f"{template.sku}-{mat_type.code}-{color.code}"[:50]
    new_name = f"{template.name} - {mat_type.name} {color.name}"[:255]

    # Check if this variant already exists
    existing = db.query(Product).filter(Product.sku == new_sku.upper()).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Variant with SKU {new_sku.upper()} already exists (id={existing.id})",
        )

    # Build BOM line overrides: swap is_variable material components to the target
    variable_ids = _get_variable_material_ids(db, template)
    bom_line_overrides = [
        {"original_component_id": comp_id, "new_component_id": target_material.id}
        for comp_id in variable_ids
    ]

    # Use duplicate_item() to do the heavy lifting
    result = duplicate_item(
        db,
        template_id,
        new_sku=new_sku,
        new_name=new_name,
        bom_line_overrides=bom_line_overrides if bom_line_overrides else None,
    )

    # Set variant-specific fields on the newly created product
    variant = db.query(Product).filter(Product.id == result["id"]).first()
    variant.parent_product_id = template_id
    variant.is_template = False  # Variants are never templates themselves
    variant.variant_metadata = {
        "material_type_id": material_type_id,
        "color_id": color_id,
        "material_type_code": mat_type.code,
        "color_code": color.code,
    }
    if selling_price is not None:
        variant.selling_price = selling_price
    if gcode_file_path is not None:
        variant.gcode_file_path = gcode_file_path

    # Ensure template is marked as template
    if not template.is_template:
        template.is_template = True

    db.commit()

    # Recalculate cost for the new variant
    try:
        calculate_item_cost(variant, db)
        db.commit()
    except Exception:
        logger.warning(f"Could not recalculate cost for variant {variant.sku}", exc_info=True)

    return {
        "id": variant.id,
        "sku": variant.sku,
        "name": variant.name,
        "parent_product_id": template_id,
        "standard_cost": float(variant.standard_cost) if variant.standard_cost else None,
        "selling_price": float(variant.selling_price) if variant.selling_price else None,
        "status": "created",
    }


def bulk_create_variants(
    db: Session,
    template_id: int,
    selections: list[dict],
) -> list[dict]:
    """
    Bulk-create variants from a list of material+color selections.

    Skips combos where a variant already exists (by generated SKU).
    Returns list of {id, sku, name, status: "created"|"skipped", reason?}.
    """
    get_item(db, template_id)  # validate template exists
    results = []

    for sel in selections:
        mt_id = sel.get("material_type_id")
        c_id = sel.get("color_id")
        if not mt_id or not c_id:
            results.append({"status": "skipped", "reason": "Missing material_type_id or color_id"})
            continue

        try:
            result = create_variant(db, template_id, mt_id, c_id)
            results.append(result)
        except HTTPException as e:
            if e.status_code == 409:
                results.append({"status": "skipped", "reason": e.detail})
            else:
                results.append({"status": "error", "reason": e.detail})

    return results


def list_variants(db: Session, template_id: int) -> list[dict]:
    """
    List all variants for a template product, enriched with inventory data.
    """
    get_item(db, template_id)  # validate template exists

    variants = (
        db.query(Product)
        .filter(Product.parent_product_id == template_id)
        .order_by(Product.sku)
        .all()
    )

    # Batch inventory query for on_hand_qty
    variant_ids = [v.id for v in variants]
    inv_data = {}
    if variant_ids:
        inv_rows = (
            db.query(
                Inventory.product_id,
                func.sum(Inventory.on_hand_quantity).label("on_hand"),
            )
            .filter(Inventory.product_id.in_(variant_ids))
            .group_by(Inventory.product_id)
            .all()
        )
        inv_data = {r.product_id: r.on_hand for r in inv_rows}

    # Batch-load color hex codes to avoid N+1 queries
    all_color_ids = set()
    for v in variants:
        meta = v.variant_metadata or {}
        cid = meta.get("color_id")
        if cid:
            all_color_ids.add(cid)
    color_hex_map: dict[int, str | None] = {}
    if all_color_ids:
        color_rows = db.query(Color).filter(Color.id.in_(all_color_ids)).all()
        color_hex_map = {c.id: c.hex_code for c in color_rows}

    result = []
    for v in variants:
        meta = v.variant_metadata or {}
        color_id = meta.get("color_id")
        result.append({
            "id": v.id,
            "sku": v.sku,
            "name": v.name,
            "material_type_code": meta.get("material_type_code"),
            "color_code": meta.get("color_code"),
            "color_hex": color_hex_map.get(color_id) if color_id else None,
            "standard_cost": float(v.standard_cost) if v.standard_cost else None,
            "selling_price": float(v.selling_price) if v.selling_price else None,
            "on_hand_qty": float(inv_data.get(v.id, 0)),
            "active": v.active,
        })

    return result


def get_variant_matrix(db: Session, template_id: int) -> dict:
    """
    Return the full variant matrix for a template:
    - template info
    - existing variants
    - available MaterialColor combos (with already_exists flags)
    """
    template = get_item(db, template_id)
    variants = list_variants(db, template_id)

    # Find which material types are used in variable materials
    variable_ids = _get_variable_material_ids(db, template)

    # Get material_type_ids from those variable products
    variable_material_type_ids = set()
    if variable_ids:
        rows = (
            db.query(Product.material_type_id)
            .filter(Product.id.in_(variable_ids), Product.material_type_id.isnot(None))
            .distinct()
            .all()
        )
        variable_material_type_ids = {r[0] for r in rows}

    # Get all available MaterialColor combos for those material types
    if not variable_material_type_ids:
        logger.warning("Template %d has no variable material types — returning empty matrix", template_id)
        material_colors = []
    else:
        mc_query = db.query(MaterialColor).join(
            MaterialType, MaterialColor.material_type_id == MaterialType.id
        ).join(
            Color, MaterialColor.color_id == Color.id
        )
        mc_query = mc_query.filter(MaterialColor.material_type_id.in_(variable_material_type_ids))
        material_colors = mc_query.all()

    # Pre-fetch all needed MaterialType and Color objects in batch
    mc_mat_type_ids = {mc.material_type_id for mc in material_colors}
    mc_color_ids = {mc.color_id for mc in material_colors}
    mat_type_map: dict[int, MaterialType] = {}
    color_map: dict[int, Color] = {}
    if mc_mat_type_ids:
        mat_type_map = {
            mt.id: mt for mt in db.query(MaterialType).filter(MaterialType.id.in_(mc_mat_type_ids)).all()
        }
    if mc_color_ids:
        color_map = {
            c.id: c for c in db.query(Color).filter(Color.id.in_(mc_color_ids)).all()
        }

    # Build a lookup of existing variant SKUs
    existing_skus = {v["sku"] for v in variants}

    available_combos = []
    for mc in material_colors:
        mat_type = mat_type_map.get(mc.material_type_id)
        color = color_map.get(mc.color_id)
        if not mat_type or not color:
            continue

        expected_sku = f"{template.sku}-{mat_type.code}-{color.code}"[:50].upper()
        existing_variant = next((v for v in variants if v["sku"] == expected_sku), None)

        available_combos.append({
            "material_type_id": mc.material_type_id,
            "color_id": mc.color_id,
            "material_type_code": mat_type.code,
            "material_type_name": mat_type.name,
            "color_code": color.code,
            "color_name": color.name,
            "color_hex": color.hex_code,
            "already_exists": expected_sku in existing_skus,
            "variant_id": existing_variant["id"] if existing_variant else None,
        })

    return {
        "template": {
            "id": template.id,
            "sku": template.sku,
            "name": template.name,
            "is_template": template.is_template,
            "variable_material_ids": list(variable_ids),
        },
        "variants": variants,
        "available_combos": available_combos,
    }


def delete_variant(db: Session, item_id: int, variant_id: int) -> dict:
    """
    Delete a variant product and its BOM/routing. Clears is_template on parent if last variant.
    """
    from app.models.bom import BOM, BOMLine
    from app.models.manufacturing import Routing, RoutingOperation

    variant = get_item(db, variant_id)
    if not variant.parent_product_id:
        raise HTTPException(status_code=400, detail="Product is not a variant (no parent_product_id)")
    if variant.parent_product_id != item_id:
        raise HTTPException(status_code=400, detail="Variant does not belong to this item")

    parent_id = variant.parent_product_id
    sku = variant.sku

    # Delete BOM lines and BOMs
    bom_ids = [b.id for b in db.query(BOM).filter(BOM.product_id == variant_id).all()]
    if bom_ids:
        db.query(BOMLine).filter(BOMLine.bom_id.in_(bom_ids)).delete(synchronize_session=False)
        db.query(BOM).filter(BOM.id.in_(bom_ids)).delete(synchronize_session=False)

    # Delete routing materials, operations, and routings
    routing_ids = [r.id for r in db.query(Routing).filter(Routing.product_id == variant_id).all()]
    if routing_ids:
        op_ids = [o.id for o in db.query(RoutingOperation).filter(RoutingOperation.routing_id.in_(routing_ids)).all()]
        if op_ids:
            db.query(RoutingOperationMaterial).filter(
                RoutingOperationMaterial.routing_operation_id.in_(op_ids)
            ).delete(synchronize_session=False)
            db.query(RoutingOperation).filter(RoutingOperation.id.in_(op_ids)).delete(synchronize_session=False)
        db.query(Routing).filter(Routing.id.in_(routing_ids)).delete(synchronize_session=False)

    db.delete(variant)
    db.flush()

    # Check if parent still has variants
    remaining = (
        db.query(func.count(Product.id))
        .filter(Product.parent_product_id == parent_id)
        .scalar()
    )
    if remaining == 0:
        parent = db.query(Product).filter(Product.id == parent_id).first()
        if parent:
            parent.is_template = False

    db.commit()

    return {"id": variant_id, "sku": sku, "status": "deleted", "remaining_variants": remaining}


def sync_routing_to_variants(db: Session, template_id: int) -> dict:
    """
    Propagate the template's active routing to all variants.

    For each variant:
    - Replaces its routing operations wholesale from the template
    - Preserves material substitutions: is_variable materials are swapped
      to the variant's target material (from variant_metadata)
    - Non-variable materials, times, work centers, and sequence are
      taken directly from the template (no drift possible)
    - Uses savepoints so a bad variant doesn't roll back the others

    Returns: {"synced": N, "errors": [{"sku": ..., "error": ...}]}
    """
    from app.services.routing_service import recalculate_routing_totals

    template = get_item(db, template_id)
    if not template.is_template:
        raise HTTPException(status_code=400, detail="Item is not a template")

    # Load template routing
    template_routing = (
        db.query(Routing)
        .filter(Routing.product_id == template_id, Routing.is_active.is_(True))
        .order_by(desc(Routing.version))
        .first()
    )
    if not template_routing:
        raise HTTPException(status_code=400, detail="Template has no active routing to sync from")

    # Eagerly load operations + materials so we can iterate after clearing variant ops
    template_ops = (
        db.query(RoutingOperation)
        .filter(RoutingOperation.routing_id == template_routing.id)
        .order_by(RoutingOperation.sequence)
        .all()
    )
    # Snapshot materials per op before we touch anything
    op_materials: dict[int, list[RoutingOperationMaterial]] = {
        op.id: list(op.materials) for op in template_ops
    }

    variants = db.query(Product).filter(Product.parent_product_id == template_id).all()

    synced = 0
    errors = []

    for variant in variants:
        savepoint = db.begin_nested()
        try:
            # Resolve this variant's target material from stored metadata
            meta = variant.variant_metadata or {}
            mat_type_id = meta.get("material_type_id")
            color_id_meta = meta.get("color_id")
            target_material = None
            if mat_type_id and color_id_meta:
                target_material = (
                    db.query(Product)
                    .filter(
                        Product.material_type_id == mat_type_id,
                        Product.color_id == color_id_meta,
                        Product.active.is_(True),
                    )
                    .first()
                )

            # Get or create variant routing
            variant_routing = (
                db.query(Routing)
                .filter(Routing.product_id == variant.id, Routing.is_active.is_(True))
                .first()
            )
            if not variant_routing:
                variant_routing = Routing(
                    product_id=variant.id,
                    name=f"Routing for {variant.name}"[:200],
                    code=f"RTG-{variant.sku}"[:50],
                    version=1,
                    revision="1.0",
                    is_active=True,
                )
                db.add(variant_routing)
                db.flush()

            # Clear existing operations — cascade deletes materials via ORM relationship
            variant_routing.operations = []
            db.flush()

            # Re-copy operations from template
            for t_op in template_ops:
                new_op = RoutingOperation(
                    routing_id=variant_routing.id,
                    sequence=t_op.sequence,
                    operation_code=t_op.operation_code,
                    operation_name=t_op.operation_name,
                    description=t_op.description,
                    work_center_id=t_op.work_center_id,
                    setup_time_minutes=t_op.setup_time_minutes,
                    run_time_minutes=t_op.run_time_minutes,
                    wait_time_minutes=t_op.wait_time_minutes,
                    move_time_minutes=t_op.move_time_minutes,
                    runtime_source=t_op.runtime_source,
                    units_per_cycle=t_op.units_per_cycle,
                    scrap_rate_percent=t_op.scrap_rate_percent,
                    labor_rate_override=t_op.labor_rate_override,
                    machine_rate_override=t_op.machine_rate_override,
                    is_active=t_op.is_active,
                )
                db.add(new_op)
                db.flush()

                for t_mat in op_materials[t_op.id]:
                    # Swap is_variable materials to this variant's target
                    if t_mat.is_variable and not target_material:
                        logger.warning(
                            "Variable material on op %s (component_id=%s) has no target for variant %s",
                            t_op.operation_code, t_mat.component_id, variant.sku,
                        )
                    component_id = (
                        target_material.id
                        if t_mat.is_variable and target_material
                        else t_mat.component_id
                    )
                    new_mat = RoutingOperationMaterial(
                        routing_operation_id=new_op.id,
                        component_id=component_id,
                        quantity=t_mat.quantity,
                        quantity_per=t_mat.quantity_per,
                        unit=t_mat.unit,
                        scrap_factor=t_mat.scrap_factor,
                        is_cost_only=t_mat.is_cost_only,
                        is_optional=t_mat.is_optional,
                        is_variable=t_mat.is_variable,
                        notes=t_mat.notes,
                    )
                    db.add(new_mat)

            db.flush()
            recalculate_routing_totals(variant_routing, db)

            try:
                calculate_item_cost(variant, db)
            except Exception:
                logger.warning(f"Could not recalculate cost for variant {variant.sku} during sync", exc_info=True)

            savepoint.commit()
            synced += 1

        except Exception as e:
            savepoint.rollback()
            logger.error(f"Failed to sync routing to variant {variant.sku}: {e}", exc_info=True)
            errors.append({"sku": variant.sku, "error": "Sync failed for this variant"})

    db.commit()
    return {"synced": synced, "total": len(variants), "errors": errors}
