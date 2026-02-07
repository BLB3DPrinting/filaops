"""
BOM Management Service — CRUD helpers for admin BOM endpoints.

Extracted from admin/bom.py (ARCHITECT-003).

NOTE: ``bom_service.py`` already contains the quote-to-BOM auto-creation
logic, so this module is intentionally named ``bom_management_service`` to
avoid collision.
"""
from typing import Optional, List
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models.bom import BOM, BOMLine
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.manufacturing import Routing
from app.schemas.bom import (
    BOMCreate,
    BOMUpdate,
    BOMLineCreate,
    BOMLineUpdate,
    BOMCopyRequest,
)
from app.services.uom_service import convert_quantity_safe

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def get_effective_cost(product: Product) -> Decimal:
    """Get the effective cost for a product using fallback priority.

    Priority: standard_cost -> average_cost -> last_cost -> cost (legacy)
    """
    if product.standard_cost and product.standard_cost > 0:
        return Decimal(str(product.standard_cost))
    if product.average_cost and product.average_cost > 0:
        return Decimal(str(product.average_cost))
    if product.last_cost and product.last_cost > 0:
        return Decimal(str(product.last_cost))
    # Removed legacy 'cost' field fallback - use standard_cost, average_cost, or last_cost
    return Decimal("0")


def get_component_inventory(component_id: int, db: Session) -> dict:
    """Get total inventory for a component across all locations"""

    result = db.query(
        func.sum(Inventory.on_hand_quantity).label('on_hand'),
        func.sum(Inventory.allocated_quantity).label('allocated'),
        func.sum(Inventory.available_quantity).label('available')
    ).filter(Inventory.product_id == component_id).first()

    return {
        "on_hand": float(result.on_hand or 0) if result else 0,
        "allocated": float(result.allocated or 0) if result else 0,
        "available": float(result.available or 0) if result else 0,
    }


def calculate_material_line_cost(
    effective_qty: Decimal,
    line_unit: Optional[str],
    cost_per_kg: Decimal,
    db: Optional[Session] = None
) -> Decimal:
    """Calculate material line cost by converting quantity to grams, then computing (qty_g/1000) x cost_per_kg.

    Args:
        effective_qty: The effective quantity (including scrap factor)
        line_unit: The unit of the quantity (None, "G", "KG", or other)
        cost_per_kg: The cost per kilogram as Decimal
        db: Optional database session for UOM conversion

    Returns:
        The line cost as Decimal: (qty_g / 1000) x cost_per_kg
    """
    # Normalize units: treat None or "G" as grams, handle "KG" by multiplying by 1000
    if not line_unit or line_unit.upper() == "G":
        qty_g = effective_qty
    elif line_unit.upper() == "KG":
        qty_g = effective_qty * Decimal("1000")
    else:
        # Unit is neither G nor KG - try conversion if db is provided
        if db is not None:
            qty_g, success = convert_quantity_safe(db, effective_qty, line_unit, "G")
            if not success:
                # Conversion failed, fall back to assuming grams
                logger.warning(
                    f"Unit conversion unavailable for unit '{line_unit}', "
                    f"effective_qty={effective_qty}. Assuming grams as fallback."
                )
                qty_g = effective_qty
        else:
            # No DB available, fall back to assuming grams
            logger.warning(
                f"Unit conversion unavailable for unit '{line_unit}', "
                f"effective_qty={effective_qty}. Assuming grams as fallback."
            )
            qty_g = effective_qty

    # Compute and return (qty_g / 1000) x cost_per_kg as Decimal
    return (qty_g / Decimal("1000")) * cost_per_kg


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------


def build_line_response(line: BOMLine, component: Optional[Product], comp_cost: Decimal, db: Session = None) -> dict:
    """Build a standardized BOM line response dict.

    Args:
        line: The BOMLine object
        component: The component Product (may be None)
        comp_cost: The component cost as Decimal (per component's unit)
        db: Database session for UOM conversion

    Returns:
        Dict containing the standardized line response
    """
    from app.services.inventory_helpers import is_material

    component_unit = component.unit if component else None
    is_mat = is_material(component) if component else False

    # Calculate effective quantity including scrap factor
    qty = line.quantity or Decimal("0")
    scrap = line.scrap_factor or Decimal("0")
    effective_qty = qty * (1 + scrap / 100)

    # For materials: Cost is always $/KG, regardless of component.unit or line.unit
    # For others: Convert cost to BOM line's unit if different from component's unit
    display_cost = comp_cost
    if is_mat:
        # Materials: Cost is always per-KG (industry standard)
        # comp_cost is already per-KG (from get_effective_cost)
        # Don't convert - keep as $/KG
        display_cost = comp_cost
    elif (
        db is not None
        and line.unit
        and component_unit
        and line.unit != component_unit
        and comp_cost
        and comp_cost > 0
    ):
        # Non-materials: Convert cost to BOM line's unit if different from component's unit
        # Cost is per component_unit, convert to per line.unit
        # Use _safe variant to handle empty UOM table with inline fallbacks
        converted_factor, success = convert_quantity_safe(db, Decimal("1"), line.unit, component_unit)
        if success:
            display_cost = comp_cost * converted_factor

    # Track whether a UOM conversion actually happened for non-materials
    converted = (
        not is_mat
        and db is not None
        and line.unit
        and component_unit
        and line.unit != component_unit
        and comp_cost
        and comp_cost > 0
        and display_cost != comp_cost  # conversion was applied
    )

    # Calculate line cost
    # For materials: line_cost = (quantity_g / 1000) x cost_per_kg
    # For others: line_cost = quantity x cost_per_unit
    line_cost = None
    if display_cost and display_cost > 0 and effective_qty:
        if is_mat:
            # Material: use helper function to calculate cost
            line_cost_decimal = calculate_material_line_cost(effective_qty, line.unit, display_cost, db)
            line_cost = float(line_cost_decimal)
        else:
            # Non-materials: simple multiplication
            line_cost = float(display_cost) * float(effective_qty)

    return {
        "id": line.id,
        "bom_id": line.bom_id,
        "component_id": line.component_id,
        "quantity": line.quantity,
        "unit": line.unit,
        "sequence": line.sequence,
        "consume_stage": line.consume_stage,
        "is_cost_only": line.is_cost_only,
        "scrap_factor": line.scrap_factor,
        "notes": line.notes,
        "component_sku": component.sku if component else None,
        "component_name": component.name if component else None,
        "component_unit": component_unit,
        "component_cost": float(display_cost) if display_cost else None,
        "component_cost_unit": "KG" if is_mat else (line.unit if converted else component_unit),
        "line_cost": line_cost,
        "qty_needed": float(effective_qty),
        "is_material": is_mat,  # Flag for frontend display
    }


def build_bom_response(bom: BOM, db: Session) -> dict:
    """Build a full BOM response with product info and lines"""

    # Batch-fetch all components for this BOM's lines
    component_ids = [line.component_id for line in bom.lines]
    components_by_id = {}
    if component_ids:
        components = db.query(Product).filter(Product.id.in_(component_ids)).all()
        components_by_id = {c.id: c for c in components}

    # Batch-fetch inventory for all components
    inventory_by_id = {}
    if component_ids:
        inv_rows = (
            db.query(
                Inventory.product_id,
                func.sum(Inventory.on_hand_quantity).label("on_hand"),
                func.sum(Inventory.allocated_quantity).label("allocated"),
                func.sum(Inventory.available_quantity).label("available"),
            )
            .filter(Inventory.product_id.in_(component_ids))
            .group_by(Inventory.product_id)
            .all()
        )
        inventory_by_id = {
            row.product_id: {
                "on_hand": float(row.on_hand or 0),
                "allocated": float(row.allocated or 0),
                "available": float(row.available or 0),
            }
            for row in inv_rows
        }

    # Batch-check which components have active BOMs (sub-assemblies)
    components_with_bom = set()
    if component_ids:
        sub_bom_rows = (
            db.query(BOM.product_id)
            .filter(BOM.product_id.in_(component_ids), BOM.active.is_(True))
            .distinct()
            .all()
        )
        components_with_bom = {row.product_id for row in sub_bom_rows}

    lines = []
    for line in bom.lines:
        component = components_by_id.get(line.component_id)
        component_cost = get_effective_cost(component) if component else Decimal("0")

        # Calculate effective quantity including scrap factor
        qty = line.quantity or Decimal("0")
        scrap = line.scrap_factor or Decimal("0")
        effective_qty = qty * (1 + scrap / 100)

        # Get inventory status from batch-loaded data
        inventory = inventory_by_id.get(line.component_id, {"on_hand": 0, "allocated": 0, "available": 0})

        # Convert effective_qty to inventory unit for comparison if needed
        qty_needed_in_inventory_unit = float(effective_qty)
        component_unit = component.unit if component else None
        if (
            line.unit
            and component_unit
            and line.unit != component_unit
        ):
            converted_qty, success = convert_quantity_safe(db, effective_qty, line.unit, component_unit)
            if success:
                qty_needed_in_inventory_unit = float(converted_qty)

        is_available = inventory["available"] >= qty_needed_in_inventory_unit
        shortage = max(0, qty_needed_in_inventory_unit - inventory["available"])

        # Build base line response using helper
        line_dict = build_line_response(line, component, component_cost, db)

        # Add inventory and sub-assembly info specific to this endpoint
        line_dict.update({
            "inventory_on_hand": inventory["on_hand"],
            "inventory_available": inventory["available"],
            "is_available": is_available,
            "shortage": shortage,
            "has_bom": line.component_id in components_with_bom,
        })

        lines.append(line_dict)

    product = bom.product
    return {
        "id": bom.id,
        "product_id": bom.product_id,
        "product_sku": product.sku if product else None,
        "product_name": product.name if product else None,
        "code": bom.code,
        "name": bom.name,
        "version": bom.version,
        "revision": bom.revision,
        "active": bom.active,
        "total_cost": bom.total_cost,
        "assembly_time_minutes": bom.assembly_time_minutes,
        "effective_date": bom.effective_date,
        "notes": bom.notes,
        "created_at": bom.created_at,
        "lines": lines,
    }


# ---------------------------------------------------------------------------
# Cost calculation
# ---------------------------------------------------------------------------


def recalculate_bom_cost(bom: BOM, db: Session) -> Decimal:
    """Recalculate total BOM cost from component costs, with UOM conversion"""
    from app.services.inventory_helpers import is_material

    # Batch-fetch all components for this BOM's lines
    component_ids = [line.component_id for line in bom.lines]
    components_by_id = {}
    if component_ids:
        components = db.query(Product).filter(Product.id.in_(component_ids)).all()
        components_by_id = {c.id: c for c in components}

    total = Decimal("0")
    for line in bom.lines:
        component = components_by_id.get(line.component_id)
        if component:
            cost = get_effective_cost(component)
            if cost > 0:
                qty = line.quantity or Decimal("0")
                scrap = line.scrap_factor or Decimal("0")
                # Add scrap factor: qty * (1 + scrap/100)
                effective_qty = qty * (1 + scrap / 100)

                is_mat = is_material(component)

                if is_mat:
                    # Materials: Cost is per-KG, quantity might be in G
                    # Use helper function to calculate: (qty_g / 1000) x cost_per_kg
                    total += calculate_material_line_cost(effective_qty, line.unit, cost, db)
                else:
                    # Non-materials: Apply UOM conversion if line unit differs from component unit
                    component_unit = component.unit
                    line_unit = line.unit

                    if line_unit and component_unit and line_unit.upper() != component_unit.upper():
                        # Convert effective_qty from line.unit to component.unit
                        # Use _safe variant to handle empty UOM table with inline fallbacks
                        converted_qty, success = convert_quantity_safe(db, effective_qty, line_unit, component_unit)
                        if success:
                            total += cost * converted_qty
                        else:
                            # Conversion failed (incompatible units), fall back to direct multiplication
                            total += cost * effective_qty
                    else:
                        # Same unit or no unit specified, direct multiply
                        total += cost * effective_qty
    return total


# ---------------------------------------------------------------------------
# Multi-level / recursive helpers
# ---------------------------------------------------------------------------


def explode_bom_recursive(
    bom_id: int,
    db: Session,
    parent_qty: Decimal = Decimal("1"),
    level: int = 0,
    visited: set = None,
    max_depth: int = 10
) -> list:
    """
    Recursively explode a BOM into all leaf components.

    Args:
        bom_id: The BOM to explode
        db: Database session
        parent_qty: Quantity multiplier from parent (for nested BOMs)
        level: Current depth level
        visited: Set of visited BOM IDs (circular reference detection)
        max_depth: Maximum recursion depth

    Returns:
        List of exploded components with quantities and levels
    """
    if visited is None:
        visited = set()

    # Circular reference check
    if bom_id in visited:
        return [{
            "error": "circular_reference",
            "bom_id": bom_id,
            "level": level,
            "message": f"Circular reference detected at BOM {bom_id}"
        }]

    # Depth limit check
    if level > max_depth:
        return [{
            "error": "max_depth_exceeded",
            "level": level,
            "message": f"Maximum depth of {max_depth} exceeded"
        }]

    visited.add(bom_id)

    bom = db.query(BOM).options(joinedload(BOM.lines)).filter(BOM.id == bom_id).first()
    if not bom:
        return []

    exploded = []

    for line in bom.lines:
        component = db.query(Product).filter(Product.id == line.component_id).first()
        if not component:
            continue

        # Calculate effective quantity (including scrap factor)
        qty = line.quantity or Decimal("0")
        scrap = line.scrap_factor or Decimal("0")
        effective_qty = qty * (1 + scrap / 100) * parent_qty

        # Check if this component has its own BOM (sub-assembly)
        sub_bom = (
            db.query(BOM)
            .filter(BOM.product_id == component.id, BOM.active.is_(True))  # noqa: E712
            .order_by(desc(BOM.version))
            .first()
        )

        # Get inventory
        inventory = get_component_inventory(component.id, db)

        # Get effective cost using fallback logic
        from app.services.inventory_helpers import is_material
        cost = get_effective_cost(component)
        component_cost = float(cost) if cost else 0.0

        # Calculate line cost with material-aware logic
        line_cost = 0.0
        if cost and cost > 0:
            if is_material(component):
                line_cost = float(calculate_material_line_cost(effective_qty, line.unit, cost, db))
            else:
                # Non-materials: convert units if needed
                qty_for_cost = effective_qty
                if line.unit and component.unit and line.unit.upper() != component.unit.upper():
                    converted_qty, success = convert_quantity_safe(db, effective_qty, line.unit, component.unit)
                    if success:
                        qty_for_cost = converted_qty
                line_cost = float(cost * qty_for_cost)
        else:
            line_cost = 0.0

        component_data = {
            "component_id": component.id,
            "component_sku": component.sku,
            "component_name": component.name,
            "component_unit": component.unit,
            "component_cost": component_cost,
            "base_quantity": float(qty),
            "effective_quantity": float(effective_qty),
            "scrap_factor": float(scrap) if scrap else 0,
            "level": level,
            "parent_bom_id": bom_id,
            "is_sub_assembly": sub_bom is not None,
            "sub_bom_id": sub_bom.id if sub_bom else None,
            "inventory_available": inventory["available"],
            "line_cost": line_cost,
        }

        exploded.append(component_data)

        # Recursively explode sub-assemblies
        if sub_bom:
            sub_exploded = explode_bom_recursive(
                sub_bom.id,
                db,
                parent_qty=effective_qty,
                level=level + 1,
                visited=visited.copy(),  # Copy to allow parallel branches
                max_depth=max_depth
            )
            exploded.extend(sub_exploded)

    return exploded


def calculate_rolled_up_cost(bom_id: int, db: Session, visited: set = None) -> Decimal:
    """
    Calculate total BOM cost including all sub-assembly costs.

    This recursively sums costs through the entire BOM tree.
    """
    if visited is None:
        visited = set()

    if bom_id in visited:
        return Decimal("0")  # Circular reference, don't double-count

    visited.add(bom_id)

    bom = db.query(BOM).options(joinedload(BOM.lines)).filter(BOM.id == bom_id).first()
    if not bom:
        return Decimal("0")

    total = Decimal("0")

    for line in bom.lines:
        component = db.query(Product).filter(Product.id == line.component_id).first()
        if not component:
            continue

        qty = line.quantity or Decimal("0")
        scrap = line.scrap_factor or Decimal("0")
        effective_qty = qty * (1 + scrap / 100)

        # Check for sub-BOM
        sub_bom = (
            db.query(BOM)
            .filter(BOM.product_id == component.id, BOM.active.is_(True))  # noqa: E712
            .order_by(desc(BOM.version))
            .first()
        )

        if sub_bom:
            # Use rolled-up cost from sub-assembly
            sub_cost = calculate_rolled_up_cost(sub_bom.id, db, visited.copy())
            total += sub_cost * effective_qty
        else:
            # Use component's effective cost with material-aware UOM conversion
            from app.services.inventory_helpers import is_material
            component_cost = get_effective_cost(component)
            if component_cost and component_cost > 0:
                if is_material(component):
                    total += calculate_material_line_cost(effective_qty, line.unit, component_cost, db)
                else:
                    component_unit = component.unit
                    line_unit = line.unit

                    if line_unit and component_unit and line_unit.upper() != component_unit.upper():
                        converted_qty, success = convert_quantity_safe(db, effective_qty, line_unit, component_unit)
                        if success:
                            total += component_cost * converted_qty
                        else:
                            total += component_cost * effective_qty
                    else:
                        total += component_cost * effective_qty

    return total


# ---------------------------------------------------------------------------
# BOM CRUD
# ---------------------------------------------------------------------------


def list_boms(
    db: Session,
    *,
    product_id: Optional[int] = None,
    active_only: bool = True,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[dict]:
    """List all BOMs with summary info including routing process costs."""
    query = db.query(BOM).options(joinedload(BOM.product), joinedload(BOM.lines))

    if product_id:
        query = query.filter(BOM.product_id == product_id)

    if active_only:
        query = query.filter(BOM.active.is_(True))  # noqa: E712

    if search:
        query = query.join(Product).filter(
            (Product.sku.ilike(f"%{search}%")) |
            (Product.name.ilike(f"%{search}%")) |
            (BOM.code.ilike(f"%{search}%")) |
            (BOM.name.ilike(f"%{search}%"))
        )

    query = query.order_by(desc(BOM.created_at))
    boms = query.offset(skip).limit(limit).all()

    # Batch-fetch active routings for all BOM products
    product_ids = [bom.product_id for bom in boms]
    routings_by_product = {}
    if product_ids:
        routings = db.query(Routing).filter(
            Routing.product_id.in_(product_ids),
            Routing.is_active.is_(True)
        ).all()
        for r in routings:
            # Keep first (or only) active routing per product
            if r.product_id not in routings_by_product:
                routings_by_product[r.product_id] = r

    result = []
    for bom in boms:
        product = bom.product
        material_cost = bom.total_cost or Decimal("0")

        # Get routing process cost from batch-loaded data
        routing = routings_by_product.get(bom.product_id)
        process_cost = routing.total_cost if routing and routing.total_cost else Decimal("0")

        # Combined total
        combined_total = material_cost + process_cost

        result.append({
            "id": bom.id,
            "product_id": bom.product_id,
            "product_sku": product.sku if product else None,
            "product_name": product.name if product else None,
            "code": bom.code,
            "name": bom.name,
            "version": bom.version,
            "revision": bom.revision,
            "active": bom.active,
            "material_cost": material_cost,
            "process_cost": process_cost,
            "total_cost": combined_total,
            "line_count": len(bom.lines),
            "created_at": bom.created_at,
        })

    return result


def get_bom_detail(db: Session, bom_id: int) -> dict:
    """Load BOM with joinedloads and return full response dict, or raise 404."""
    bom = (
        db.query(BOM)
        .options(joinedload(BOM.product), joinedload(BOM.lines))
        .filter(BOM.id == bom_id)
        .first()
    )

    if not bom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BOM not found"
        )

    return build_bom_response(bom, db)


def create_bom(
    db: Session,
    bom_data: BOMCreate,
    force_new: bool = False,
) -> dict:
    """Create or upsert a BOM for a product.

    If an active BOM already exists for the product:
    - By default, adds the provided lines to the existing BOM (upsert behaviour)
    - If *force_new* is True, deactivates the old BOM and creates a new version

    Returns the full BOM response dict (via ``build_bom_response``).
    """
    # Verify product exists
    product = db.query(Product).filter(Product.id == bom_data.product_id).first()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Check for existing active BOM (use created_at as BOM model doesn't have updated_at)
    existing_bom = db.query(BOM).filter(
        BOM.product_id == bom_data.product_id,
        BOM.active == True  # noqa: E712
    ).order_by(desc(BOM.created_at)).first()

    # If BOM exists and we're not forcing a new version, add lines to existing BOM
    if existing_bom and not force_new:
        logger.info(
            "Adding lines to existing BOM (upsert)",
            extra={
                "bom_id": existing_bom.id,
                "product_id": product.id,
                "product_sku": product.sku,
            }
        )

        # Add new lines to the existing BOM
        if bom_data.lines:
            max_seq = (
                db.query(func.max(BOMLine.sequence))
                .filter(BOMLine.bom_id == existing_bom.id)
                .scalar()
            )
            start_seq = (max_seq or 0) + 1
            for seq, line_data in enumerate(bom_data.lines, start=start_seq):
                # Verify component exists
                component = db.query(Product).filter(Product.id == line_data.component_id).first()
                if not component:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Component {line_data.component_id} not found"
                    )

                # Check if component already exists in BOM
                existing_line = db.query(BOMLine).filter(
                    BOMLine.bom_id == existing_bom.id,
                    BOMLine.component_id == line_data.component_id
                ).first()

                if existing_line:
                    # Update existing line quantity (add to it)
                    existing_line.quantity = (existing_line.quantity or 0) + line_data.quantity
                    if line_data.unit:
                        existing_line.unit = line_data.unit
                    if line_data.scrap_factor is not None:
                        existing_line.scrap_factor = line_data.scrap_factor
                    if line_data.notes:
                        existing_line.notes = line_data.notes
                else:
                    # Add new line
                    line = BOMLine(
                        bom_id=existing_bom.id,
                        component_id=line_data.component_id,
                        quantity=line_data.quantity,
                        unit=line_data.unit or component.unit or "EA",
                        sequence=line_data.sequence or seq,
                        consume_stage=line_data.consume_stage or "production",
                        is_cost_only=line_data.is_cost_only or False,
                        scrap_factor=line_data.scrap_factor,
                        notes=line_data.notes,
                    )
                    db.add(line)

        # Recalculate cost
        db.flush()
        existing_bom.total_cost = recalculate_bom_cost(existing_bom, db)

        db.commit()
        db.refresh(existing_bom)

        return build_bom_response(existing_bom, db)

    # Deactivate existing active BOMs if we're creating a new version
    if force_new:
        existing_boms = db.query(BOM).filter(
            BOM.product_id == bom_data.product_id,
            BOM.active == True  # noqa: E712
        ).all()
        for old_bom in existing_boms:
            old_bom.active = False

    # Generate BOM code if not provided
    bom_code = bom_data.code
    if not bom_code:
        # Generate code based on product SKU and version
        version = bom_data.version or 1
        bom_code = f"BOM-{product.sku}-V{version}"

    # Generate name if not provided
    bom_name = bom_data.name
    if not bom_name:
        bom_name = f"{product.name} BOM"

    # Create BOM
    bom = BOM(
        product_id=bom_data.product_id,
        code=bom_code,
        name=bom_name,
        version=bom_data.version or 1,
        revision=bom_data.revision or "1.0",
        assembly_time_minutes=bom_data.assembly_time_minutes,
        effective_date=bom_data.effective_date,
        notes=bom_data.notes,
        active=True,
    )
    db.add(bom)
    db.flush()  # Get the BOM ID

    # Add lines if provided
    if bom_data.lines:
        for seq, line_data in enumerate(bom_data.lines, start=1):
            # Verify component exists
            component = db.query(Product).filter(Product.id == line_data.component_id).first()
            if not component:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Component {line_data.component_id} not found"
                )

            line = BOMLine(
                bom_id=bom.id,
                component_id=line_data.component_id,
                quantity=line_data.quantity,
                unit=line_data.unit or component.unit or "EA",
                sequence=line_data.sequence or seq,
                consume_stage=line_data.consume_stage or "production",
                is_cost_only=line_data.is_cost_only or False,
                scrap_factor=line_data.scrap_factor,
                notes=line_data.notes,
            )
            db.add(line)

    # Calculate total cost
    db.flush()
    bom.total_cost = recalculate_bom_cost(bom, db)

    # Update product flag
    product.has_bom = True

    db.commit()
    db.refresh(bom)

    return build_bom_response(bom, db)


def update_bom_header(db: Session, bom_id: int, bom_data: BOMUpdate) -> dict:
    """Find BOM, apply header updates, return full response dict."""
    bom = db.query(BOM).filter(BOM.id == bom_id).first()
    if not bom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BOM not found"
        )

    # Update provided fields
    update_data = bom_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(bom, field, value)

    db.commit()
    db.refresh(bom)

    return build_bom_response(bom, db)


def deactivate_bom(db: Session, bom_id: int) -> None:
    """Soft-delete a BOM by setting active=False."""
    bom = db.query(BOM).filter(BOM.id == bom_id).first()
    if not bom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BOM not found"
        )

    # Soft delete
    bom.active = False
    db.commit()


# ---------------------------------------------------------------------------
# BOM Line CRUD
# ---------------------------------------------------------------------------


def add_bom_line(db: Session, bom_id: int, line_data: BOMLineCreate) -> dict:
    """Add a line to a BOM, recalculate cost, return line response dict."""
    bom = db.query(BOM).filter(BOM.id == bom_id).first()
    if not bom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BOM not found"
        )

    # Verify component exists
    component = db.query(Product).filter(Product.id == line_data.component_id).first()
    if not component:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Component not found"
        )

    # Get next sequence if not provided
    if line_data.sequence is None:
        max_seq = (
            db.query(func.max(BOMLine.sequence))
            .filter(BOMLine.bom_id == bom_id)
            .scalar()
        )
        sequence = (max_seq or 0) + 1
    else:
        sequence = line_data.sequence

    # Create line - inherit unit from component if not specified
    line = BOMLine(
        bom_id=bom_id,
        component_id=line_data.component_id,
        quantity=line_data.quantity,
        unit=line_data.unit or component.unit or "EA",
        sequence=sequence,
        consume_stage=line_data.consume_stage or "production",
        is_cost_only=line_data.is_cost_only or False,
        scrap_factor=line_data.scrap_factor,
        notes=line_data.notes,
    )
    db.add(line)

    # Recalculate BOM cost
    db.flush()
    bom.total_cost = recalculate_bom_cost(bom, db)

    db.commit()
    db.refresh(line)

    # Get component cost for response
    comp_cost = get_effective_cost(component)

    return build_line_response(line, component, comp_cost, db)


def update_bom_line(db: Session, bom_id: int, line_id: int, line_data: BOMLineUpdate) -> dict:
    """Update a BOM line, recalculate cost, return line response dict."""
    line = db.query(BOMLine).filter(
        BOMLine.id == line_id,
        BOMLine.bom_id == bom_id
    ).first()

    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BOM line not found"
        )

    # If changing component, verify it exists
    new_component = None
    if line_data.component_id is not None:
        new_component = db.query(Product).filter(Product.id == line_data.component_id).first()
        if not new_component:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Component not found"
            )

    # Update provided fields
    update_data = line_data.model_dump(exclude_unset=True)

    # Inherit new component's unit when component actually changes without explicit unit
    if new_component and "unit" not in update_data and line_data.component_id != line.component_id:
        update_data["unit"] = new_component.unit or "EA"

    for field, value in update_data.items():
        setattr(line, field, value)

    # Recalculate BOM cost
    bom = db.query(BOM).filter(BOM.id == bom_id).first()
    bom.total_cost = recalculate_bom_cost(bom, db)

    db.commit()
    db.refresh(line)

    # Get component for response
    component = db.query(Product).filter(Product.id == line.component_id).first()
    comp_cost = get_effective_cost(component) if component else Decimal("0")

    return build_line_response(line, component, comp_cost, db)


def delete_bom_line(db: Session, bom_id: int, line_id: int) -> None:
    """Delete a BOM line and recalculate BOM cost."""
    line = db.query(BOMLine).filter(
        BOMLine.id == line_id,
        BOMLine.bom_id == bom_id
    ).first()

    if not line:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BOM line not found"
        )

    db.delete(line)

    # Recalculate BOM cost
    bom = db.query(BOM).filter(BOM.id == bom_id).first()
    db.flush()
    bom.total_cost = recalculate_bom_cost(bom, db)

    db.commit()


# ---------------------------------------------------------------------------
# Bulk & utility operations
# ---------------------------------------------------------------------------


def recalculate_bom_endpoint(db: Session, bom_id: int) -> dict:
    """Recalculate BOM total cost and return line-level cost breakdown."""
    from app.services.inventory_helpers import is_material

    bom = (
        db.query(BOM)
        .options(joinedload(BOM.lines))
        .filter(BOM.id == bom_id)
        .first()
    )

    if not bom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="BOM not found"
        )

    previous_cost = bom.total_cost

    # Batch-fetch all components for this BOM's lines
    component_ids = [line.component_id for line in bom.lines]
    components_by_id = {}
    if component_ids:
        components = db.query(Product).filter(Product.id.in_(component_ids)).all()
        components_by_id = {c.id: c for c in components}

    # Batch-prefetch active sub-BOMs to avoid N+1 queries in the loop
    sub_bom_map: dict[int, BOM] = {}
    if component_ids:
        sub_boms = (
            db.query(BOM)
            .filter(BOM.product_id.in_(component_ids), BOM.active.is_(True))
            .order_by(desc(BOM.version))
            .all()
        )
        for sb in sub_boms:
            if sb.product_id not in sub_bom_map:  # first = highest version
                sub_bom_map[sb.product_id] = sb

    line_costs = []
    for line in bom.lines:
        component = components_by_id.get(line.component_id)
        component_cost = get_effective_cost(component) if component else Decimal("0")

        # Check if this component has a sub-assembly BOM
        sub_bom = sub_bom_map.get(line.component_id)

        qty = line.quantity or Decimal("0")
        scrap = line.scrap_factor or Decimal("0")
        effective_qty = qty * (1 + scrap / 100)

        if sub_bom:
            # Sub-assembly: use rolled-up cost (includes all nested components)
            sub_cost = calculate_rolled_up_cost(sub_bom.id, db)
            unit_cost = sub_cost  # cost for 1x of the sub-assembly
            line_cost = float(sub_cost * effective_qty)
        elif component and component_cost and component_cost > 0:
            is_mat = is_material(component)
            component_unit = component.unit
            line_unit = line.unit
            unit_cost = component_cost

            if is_mat:
                # Materials: Cost is per-KG, quantity might be in G
                # Use helper function to calculate: (qty_g / 1000) x cost_per_kg
                line_cost_decimal = calculate_material_line_cost(effective_qty, line_unit, component_cost, db)
                line_cost = float(line_cost_decimal)  # Cast to float for API response
                unit_cost = component_cost  # Keep as $/KG
            elif line_unit and component_unit and line_unit.upper() != component_unit.upper():
                # Non-materials: Apply UOM conversion if needed
                # Use _safe variant to handle empty UOM table with inline fallbacks
                converted_qty, qty_success = convert_quantity_safe(db, effective_qty, line_unit, component_unit)
                if qty_success:
                    line_cost = float(component_cost * converted_qty)
                    # Adjust unit cost to show per line unit
                    # Derive factor from converted_qty to avoid second call
                    if effective_qty:
                        conversion_factor = converted_qty / effective_qty
                        unit_cost = component_cost * conversion_factor
                else:
                    line_cost = float(component_cost * effective_qty)
            else:
                line_cost = float(component_cost * effective_qty)
        else:
            line_cost = 0
            unit_cost = Decimal("0")

        line_costs.append({
            "line_id": line.id,
            "component_sku": component.sku if component else None,
            "quantity": float(line.quantity) if line.quantity else 0,
            "unit_cost": float(unit_cost) if unit_cost else 0,
            "line_cost": line_cost,
        })

    # Update total - use rolled-up cost to include sub-assembly costs
    new_cost = calculate_rolled_up_cost(bom_id, db)
    bom.total_cost = new_cost
    db.commit()

    return {
        "bom_id": bom_id,
        "previous_cost": previous_cost,
        "new_cost": new_cost,
        "line_costs": line_costs,
    }


def copy_bom(db: Session, bom_id: int, copy_data: BOMCopyRequest) -> dict:
    """Copy a BOM to another product. Returns the full BOM response dict."""
    # Get source BOM
    source_bom = (
        db.query(BOM)
        .options(joinedload(BOM.lines))
        .filter(BOM.id == bom_id)
        .first()
    )

    if not source_bom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source BOM not found"
        )

    # Verify target product exists
    target_product = db.query(Product).filter(Product.id == copy_data.target_product_id).first()
    if not target_product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target product not found"
        )

    # Create new BOM
    new_bom = BOM(
        product_id=copy_data.target_product_id,
        code=f"{target_product.sku}-BOM",
        name=f"BOM for {target_product.name}",
        version=copy_data.new_version or 1,
        revision=source_bom.revision,
        assembly_time_minutes=source_bom.assembly_time_minutes,
        effective_date=source_bom.effective_date,
        notes=f"Copied from BOM {bom_id}",
        active=True,
    )
    db.add(new_bom)
    db.flush()

    # Copy lines if requested
    if copy_data.include_lines:
        for line in source_bom.lines:
            new_line = BOMLine(
                bom_id=new_bom.id,
                component_id=line.component_id,
                quantity=line.quantity,
                unit=line.unit,
                sequence=line.sequence,
                consume_stage=line.consume_stage,
                is_cost_only=line.is_cost_only,
                scrap_factor=line.scrap_factor,
                notes=line.notes,
            )
            db.add(new_line)

    # Calculate cost
    db.flush()
    new_bom.total_cost = recalculate_bom_cost(new_bom, db)

    # Update target product flag
    target_product.has_bom = True

    db.commit()
    db.refresh(new_bom)

    return build_bom_response(new_bom, db)


def get_bom_by_product(db: Session, product_id: int) -> dict:
    """Find the active BOM for a product, or raise 404."""
    bom = (
        db.query(BOM)
        .options(joinedload(BOM.product), joinedload(BOM.lines))
        .filter(BOM.product_id == product_id, BOM.active.is_(True))  # noqa: E712
        .order_by(desc(BOM.version))
        .first()
    )

    if not bom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active BOM found for this product"
        )

    return build_bom_response(bom, db)


def explode_bom(db: Session, bom_id: int, max_depth: int = 10, flatten: bool = False) -> dict:
    """Full explode endpoint logic returning a structured dict."""
    bom = db.query(BOM).options(joinedload(BOM.product)).filter(BOM.id == bom_id).first()
    if not bom:
        raise HTTPException(status_code=404, detail="BOM not found")

    exploded = explode_bom_recursive(bom_id, db, max_depth=max_depth)

    # Check for errors
    errors = [e for e in exploded if isinstance(e, dict) and e.get("error")]
    if errors:
        return {
            "bom_id": bom_id,
            "product_sku": bom.product.sku if bom.product else None,
            "product_name": bom.product.name if bom.product else None,
            "errors": errors,
            "components": [c for c in exploded if not c.get("error")],
        }

    # Optionally flatten/aggregate
    if flatten:
        aggregated = {}
        for comp in exploded:
            key = comp["component_id"]
            if key in aggregated:
                aggregated[key]["effective_quantity"] += comp["effective_quantity"]
                aggregated[key]["line_cost"] += comp["line_cost"]
            else:
                aggregated[key] = comp.copy()
                aggregated[key]["level"] = "aggregated"
        exploded = list(aggregated.values())

    # Calculate totals
    total_cost = sum(c.get("line_cost", 0) for c in exploded if not c.get("is_sub_assembly"))
    rolled_up_cost = float(calculate_rolled_up_cost(bom_id, db))

    # Unique components (by component_id)
    unique_ids = set(c.get("component_id") for c in exploded)

    # Transform component data for frontend compatibility
    lines = []
    for comp in exploded:
        lines.append({
            "level": comp.get("level", 0),
            "component_id": comp.get("component_id"),
            "component_sku": comp.get("component_sku"),
            "component_name": comp.get("component_name"),
            "component_unit": comp.get("component_unit"),
            "quantity_per_unit": comp.get("base_quantity", 0),
            "extended_quantity": comp.get("effective_quantity", 0),
            "unit_cost": comp.get("component_cost", 0),
            "line_cost": comp.get("line_cost", 0),
            "is_sub_assembly": comp.get("is_sub_assembly", False),
            "sub_bom_id": comp.get("sub_bom_id"),
            "inventory_available": comp.get("inventory_available", 0),
            "parent_bom_id": comp.get("parent_bom_id"),
        })

    return {
        "bom_id": bom_id,
        "product_sku": bom.product.sku if bom.product else None,
        "product_name": bom.product.name if bom.product else None,
        "max_depth": max(c.get("level", 0) for c in exploded) if exploded else 0,
        "total_components": len(exploded),
        "unique_components": len(unique_ids),
        "leaf_component_count": len([c for c in exploded if not c.get("is_sub_assembly")]),
        "total_cost": rolled_up_cost,
        "total_leaf_cost": total_cost,
        "lines": lines,
        # Keep legacy fields for backwards compat
        "components": exploded,
    }


def get_cost_rollup(db: Session, bom_id: int) -> dict:
    """Get a detailed cost breakdown with sub-assembly costs rolled up."""
    bom = db.query(BOM).options(joinedload(BOM.product), joinedload(BOM.lines)).filter(BOM.id == bom_id).first()
    if not bom:
        raise HTTPException(status_code=404, detail="BOM not found")

    # Batch-fetch all components for this BOM's lines
    component_ids = [line.component_id for line in bom.lines]
    components_by_id = {}
    if component_ids:
        components = db.query(Product).filter(Product.id.in_(component_ids)).all()
        components_by_id = {c.id: c for c in components}

    # Batch-fetch active sub-BOMs for all components
    sub_boms_by_product = {}
    if component_ids:
        sub_boms = (
            db.query(BOM)
            .filter(BOM.product_id.in_(component_ids), BOM.active.is_(True))
            .order_by(desc(BOM.version))
            .all()
        )
        for sb in sub_boms:
            if sb.product_id not in sub_boms_by_product:
                sub_boms_by_product[sb.product_id] = sb

    breakdown = []
    total = Decimal("0")

    for line in bom.lines:
        component = components_by_id.get(line.component_id)
        if not component:
            continue

        qty = line.quantity or Decimal("0")
        scrap = line.scrap_factor or Decimal("0")
        effective_qty = qty * (1 + scrap / 100)

        # Check for sub-BOM from batch-loaded data
        sub_bom = sub_boms_by_product.get(component.id)

        if sub_bom:
            sub_cost = calculate_rolled_up_cost(sub_bom.id, db)
            line_cost = sub_cost * effective_qty
            cost_source = "sub_assembly"
            unit_cost = sub_cost
        else:
            # Apply UOM conversion for direct components using effective cost
            from app.services.inventory_helpers import is_material
            component_cost = get_effective_cost(component)
            if component_cost and component_cost > 0:
                unit_cost = component_cost

                if is_material(component):
                    line_cost = calculate_material_line_cost(effective_qty, line.unit, component_cost, db)
                else:
                    component_unit = component.unit
                    line_unit = line.unit

                    if line_unit and component_unit and line_unit.upper() != component_unit.upper():
                        converted_qty, qty_success = convert_quantity_safe(db, effective_qty, line_unit, component_unit)
                        if qty_success:
                            line_cost = component_cost * converted_qty
                            if effective_qty:
                                conversion_factor = converted_qty / effective_qty
                                unit_cost = component_cost * conversion_factor
                        else:
                            line_cost = component_cost * effective_qty
                    else:
                        line_cost = component_cost * effective_qty
                cost_source = "direct"
            else:
                line_cost = Decimal("0")
                unit_cost = Decimal("0")
                cost_source = "missing"

        total += line_cost

        breakdown.append({
            "component_id": component.id,
            "component_sku": component.sku,
            "component_name": component.name,
            "quantity": float(qty),
            "effective_quantity": float(effective_qty),
            "unit_cost": float(unit_cost),
            "line_cost": float(line_cost),
            "cost_source": cost_source,
            "is_sub_assembly": sub_bom is not None,
            "sub_bom_id": sub_bom.id if sub_bom else None,
        })

    # Calculate sub-assembly totals
    sub_assembly_items = [b for b in breakdown if b["is_sub_assembly"]]
    direct_items = [b for b in breakdown if not b["is_sub_assembly"]]

    return {
        "bom_id": bom_id,
        "product_sku": bom.product.sku if bom.product else None,
        "product_name": bom.product.name if bom.product else None,
        "stored_cost": float(bom.total_cost) if bom.total_cost else 0,
        "rolled_up_cost": float(total),
        "cost_difference": float(total - (bom.total_cost or 0)),
        # Additional summary fields for UI
        "has_sub_assemblies": len(sub_assembly_items) > 0,
        "sub_assembly_count": len(sub_assembly_items),
        "direct_cost": sum(b["line_cost"] for b in direct_items),
        "sub_assembly_cost": sum(b["line_cost"] for b in sub_assembly_items),
        "breakdown": breakdown,
    }


def where_used(db: Session, product_id: int, include_inactive: bool = False) -> dict:
    """Find all BOMs that use a specific product as a component."""
    # Verify product exists
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Find all BOM lines using this component
    query = (
        db.query(BOMLine)
        .join(BOM)
        .options(joinedload(BOMLine.bom).joinedload(BOM.product))
        .filter(BOMLine.component_id == product_id)
    )

    if not include_inactive:
        query = query.filter(BOM.active.is_(True))  # noqa: E712

    lines = query.all()

    # Group by BOM
    bom_usage = {}
    for line in lines:
        bom = line.bom
        if bom.id not in bom_usage:
            bom_usage[bom.id] = {
                "bom_id": bom.id,
                "bom_code": bom.code,
                "product_id": bom.product_id,
                "product_sku": bom.product.sku if bom.product else None,
                "product_name": bom.product.name if bom.product else None,
                "active": bom.active,
                "quantity_used": float(line.quantity) if line.quantity else 0,
                "line_id": line.id,
            }
        else:
            # Same component appears multiple times in same BOM
            bom_usage[bom.id]["quantity_used"] += float(line.quantity) if line.quantity else 0

    return {
        "component_id": product_id,
        "component_sku": product.sku,
        "component_name": product.name,
        "used_in_count": len(bom_usage),
        "used_in": list(bom_usage.values()),
    }


def validate_bom(db: Session, bom_id: int) -> dict:
    """Validate a BOM for issues like circular references, missing costs, etc."""
    bom = db.query(BOM).options(joinedload(BOM.product), joinedload(BOM.lines)).filter(BOM.id == bom_id).first()
    if not bom:
        raise HTTPException(status_code=404, detail="BOM not found")

    issues = []

    # Check for empty BOM
    if not bom.lines:
        issues.append({
            "severity": "warning",
            "code": "empty_bom",
            "message": "BOM has no components"
        })

    # Batch-fetch all components for validation
    component_ids = [line.component_id for line in bom.lines]
    components_by_id = {}
    if component_ids:
        components = db.query(Product).filter(Product.id.in_(component_ids)).all()
        components_by_id = {c.id: c for c in components}

    # Batch-check which components have active BOMs (sub-assemblies)
    components_with_bom = set()
    if component_ids:
        sub_bom_rows = (
            db.query(BOM.product_id)
            .filter(BOM.product_id.in_(component_ids), BOM.active.is_(True))
            .distinct()
            .all()
        )
        components_with_bom = {row.product_id for row in sub_bom_rows}

    # Check each line
    for line in bom.lines:
        component = components_by_id.get(line.component_id)

        if not component:
            issues.append({
                "severity": "error",
                "code": "missing_component",
                "message": f"Component ID {line.component_id} not found",
                "line_id": line.id
            })
            continue

        # Missing cost
        component_cost = get_effective_cost(component)
        if not component_cost or component_cost <= 0:
            # Check if it's a sub-assembly
            has_sub_bom = component.id in components_with_bom

            if not has_sub_bom:
                issues.append({
                    "severity": "warning",
                    "code": "missing_cost",
                    "message": f"Component {component.sku} has no cost defined",
                    "component_id": component.id,
                    "line_id": line.id
                })

        # Zero quantity
        if not line.quantity or line.quantity <= 0:
            issues.append({
                "severity": "error",
                "code": "invalid_quantity",
                "message": f"Line for {component.sku} has invalid quantity",
                "line_id": line.id
            })

    # Check for circular references
    exploded = explode_bom_recursive(bom_id, db, max_depth=15)
    circular_errors = [e for e in exploded if isinstance(e, dict) and e.get("error") == "circular_reference"]

    for err in circular_errors:
        issues.append({
            "severity": "error",
            "code": "circular_reference",
            "message": err.get("message", "Circular reference detected"),
            "bom_id": err.get("bom_id")
        })

    return {
        "bom_id": bom_id,
        "product_sku": bom.product.sku if bom.product else None,
        "is_valid": not any(i["severity"] == "error" for i in issues),
        "error_count": len([i for i in issues if i["severity"] == "error"]),
        "warning_count": len([i for i in issues if i["severity"] == "warning"]),
        "issues": issues,
    }
