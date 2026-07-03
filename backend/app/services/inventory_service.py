"""
Inventory Transaction Service

Handles automatic inventory transactions for:
- Production completion (consume materials, add finished goods)
- Shipping (consume packaging materials, issue finished goods)
"""
from decimal import Decimal
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.inventory import Inventory, InventoryTransaction, InventoryLocation
from app.models.product import Product
from app.models.bom import BOM, BOMLine
from app.models.production_order import ProductionOrder, ProductionOrderOperationMaterial
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.traceability import MaterialLot, ProductionLotConsumption
from app.logging_config import get_logger
from app.services import inventory_ledger
from app.services.uom_service import (
    convert_quantity_safe,
    format_conversion_note,
    UOMConversionError,
    convert_cost_for_unit,
)
from app.services.reservation_reconciliation_service import check_allocation_guard
from app.services.operation_material_mapping import get_consume_stages_for_operation

logger = get_logger(__name__)


def get_effective_cost(product: "Product") -> "Optional[Decimal]":
    """
    Get the effective cost for a product based on its declared cost_method.

    Cost methods:
    - 'standard': Use standard_cost (for manufactured items with set costs)
    - 'average': Use weighted average cost (default, for purchased items)
    - 'fifo': Use last_cost as approximation (full FIFO requires cost layers)
    - 'last': Use most recent purchase price

    Returns None if no cost is available.
    """
    method = (product.cost_method or "average").lower()

    if method == "standard":
        if product.standard_cost is not None:
            return Decimal(str(product.standard_cost))
        # Fallback: warn and use average/last
        logger.warning(
            f"Product {product.sku} uses standard costing but has no standard_cost set. "
            f"Falling back to average/last cost."
        )
        if product.average_cost is not None:
            return Decimal(str(product.average_cost))
        if product.last_cost is not None:
            return Decimal(str(product.last_cost))
        return None

    elif method == "average":
        if product.average_cost is not None:
            return Decimal(str(product.average_cost))
        # Fallback to last_cost for products without average yet
        if product.last_cost is not None:
            return Decimal(str(product.last_cost))
        # Fallback to standard_cost for new products with no receiving history yet
        # This allows BOM costing and quoting before first purchase
        if product.standard_cost is not None:
            return Decimal(str(product.standard_cost))
        return None

    elif method == "fifo":
        # Full FIFO requires cost layer tracking (not yet implemented)
        # For now, use last_cost as approximation
        if product.last_cost is not None:
            return Decimal(str(product.last_cost))
        if product.average_cost is not None:
            return Decimal(str(product.average_cost))
        return None

    elif method == "last":
        if product.last_cost is not None:
            return Decimal(str(product.last_cost))
        return None

    # Unknown method - default to average behavior
    logger.warning(f"Unknown cost_method '{method}' for {product.sku}, using average")
    if product.average_cost is not None:
        return Decimal(str(product.average_cost))
    if product.last_cost is not None:
        return Decimal(str(product.last_cost))
    return None


def get_allocations_by_production_order(
    db: Session,
    product_ids: List[int]
) -> Dict[int, Dict[int, Decimal]]:
    """
    Get inventory allocations grouped by product_id and production_order_id.

    This is used by MRP to correctly calculate net requirements:
    - When calculating demand for a specific production order, we need to know
      which allocations belong to THAT order vs OTHER orders
    - The Inventory.allocated_quantity is an aggregate - it doesn't tell us
      which orders own those allocations

    Uses InventoryTransaction records with:
    - reference_type = "production_order"
    - transaction_type = "reservation" (adds) or "reservation_release" (subtracts)

    Args:
        db: Database session
        product_ids: List of product IDs to get allocations for

    Returns:
        Dict mapping: {product_id: {production_order_id: allocated_quantity}}
        Only includes positive allocations (orders with net reservations)
    """
    from sqlalchemy import func, case
    from collections import defaultdict

    if not product_ids:
        return {}

    # Query all reservation transactions for these products
    # Sum reservation quantities, subtract reservation_release quantities
    reservations = db.query(
        InventoryTransaction.product_id,
        InventoryTransaction.reference_id.label("production_order_id"),
        func.sum(
            case(
                (InventoryTransaction.transaction_type == "reservation", InventoryTransaction.quantity),
                (InventoryTransaction.transaction_type == "reservation_release", -InventoryTransaction.quantity),
                else_=Decimal("0")
            )
        ).label("allocated")
    ).filter(
        InventoryTransaction.product_id.in_(product_ids),
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.transaction_type.in_(["reservation", "reservation_release"])
    ).group_by(
        InventoryTransaction.product_id,
        InventoryTransaction.reference_id
    ).all()

    result: Dict[int, Dict[int, Decimal]] = defaultdict(dict)
    for row in reservations:
        allocated = Decimal(str(row.allocated)) if row.allocated else Decimal("0")
        if allocated > 0 and row.production_order_id is not None:
            result[row.product_id][row.production_order_id] = allocated

    return dict(result)


# ============================================================================
# CRITICAL: Cost Per Unit Conversion - DO NOT MODIFY WITHOUT DISCUSSION
# ============================================================================
# This function converts cost from PURCHASING unit ($/KG) to INVENTORY unit ($/G).
#
# WHY THIS EXISTS:
# - Products store cost per PURCHASE unit (product.purchase_uom, e.g., $/KG)
# - Inventory transactions store quantity in STORAGE unit (product.unit, e.g., G)
# - We must convert cost to match: $20/KG -> $0.02/G
#
# WITHOUT THIS: 3856 G * $20 = $77,120 (caused $1.1M fake COGS!)
# WITH THIS:    3856 G * $0.02 = $77.12 (correct)
#
# KEY FIELDS:
# - product.purchase_uom: Unit we BUY in (KG, BOX, EA) - costs are per this
# - product.unit: Unit we STORE in (G, EA) - inventory quantities use this
#
# DO NOT CHANGE without verifying accounting dashboard COGS calculations.
# ============================================================================
def get_effective_cost_per_inventory_unit(product: "Product") -> "Optional[Decimal]":
    """
    Get the effective cost for a product in cost per inventory unit.

    IMPORTANT: Different cost fields are stored differently:
    - standard_cost: Stored per PURCHASE unit ($/KG) - needs conversion to $/G
    - average_cost: Already stored per STORAGE unit ($/G) - NO conversion
    - last_cost: Already stored per STORAGE unit ($/G) - NO conversion

    This is because average_cost and last_cost are calculated from inventory
    transactions which are already recorded in storage units.

    Example (standard_cost):
        - Product has purchase_uom='KG', unit='G', standard_cost=20.00 ($/KG)
        - Returns: 0.02 ($/G)
        - So: 1000 G * $0.02/G = $20.00 (correct!)

    Example (average_cost):
        - Product has unit='G', average_cost=0.02 ($/G, already converted)
        - Returns: 0.02 ($/G) - no conversion needed!

    Args:
        product: Product to get cost for

    Returns:
        Cost per inventory unit (e.g., $/G), or None if no cost available
    """
    method = (product.cost_method or "average").lower()

    # average_cost and last_cost are already stored in storage unit ($/G)
    # Only standard_cost needs conversion from purchase unit
    if method in ("average", "fifo", "last"):
        if method == "average" and product.average_cost is not None:
            return Decimal(str(product.average_cost))
        if product.last_cost is not None:
            return Decimal(str(product.last_cost))
        # Fallback to standard if no average/last

    # standard_cost is stored in purchase unit - needs conversion
    if product.standard_cost is not None:
        base_cost = Decimal(str(product.standard_cost))
        storage_unit = (product.unit or 'EA').upper().strip()
        purchase_unit = (getattr(product, 'purchase_uom', None) or storage_unit).upper().strip()
        if purchase_unit == storage_unit:
            return base_cost
        return convert_cost_for_unit(base_cost, purchase_unit, storage_unit)

    return None


def convert_and_generate_notes(
    db: Session,
    bom_qty: Decimal,
    line_unit: str,
    component_unit: str,
    component_name: str,
    component_sku: str,
    reference_prefix: str,
    reference_code: str,
) -> Tuple[Decimal, str]:
    """Convert BOM quantity to component unit and generate transaction notes.
    
    Args:
        db: Database session
        bom_qty: Quantity in BOM line units
        line_unit: BOM line unit code
        component_unit: Component's inventory unit code
        component_name: Component product name
        component_sku: Component SKU (for logging)
        reference_prefix: Prefix for notes (e.g., "Consumed for PO#", "Shipping materials for SO#")
        reference_code: Reference code/number for notes
    
    Returns:
        Tuple of (total_qty, notes) where total_qty is the converted quantity
        and notes is the formatted transaction description
    
    Raises:
        UOMConversionError: If units are incompatible and conversion fails.
            This prevents dangerous inventory errors (e.g., treating 225 G as 225 KG).
            The calling transaction will be rolled back automatically.
    """
    if line_unit != component_unit:
        total_qty, was_converted = convert_quantity_safe(db, bom_qty, line_unit, component_unit)
        if was_converted:
            notes = f"{reference_prefix}{reference_code}: " + \
                format_conversion_note(bom_qty, line_unit, total_qty, component_unit, component_name)
        else:
            # Conversion failed (incompatible units) - ABORT to prevent inventory errors
            # Using bom_qty would be dangerous: e.g., 225 G treated as 225 KG = massive error
            error_msg = (
                f"UOM conversion failed for {reference_prefix}{reference_code}: "
                f"Cannot convert {line_unit} to {component_unit} for component {component_sku} ({component_name}). "
                f"Attempted to convert {bom_qty} {line_unit} but units are incompatible. "
                f"Transaction aborted to prevent inventory errors."
            )
            logger.error(error_msg)
            raise UOMConversionError(error_msg)
    else:
        total_qty = bom_qty
        notes = f"{reference_prefix}{reference_code}: {total_qty} {component_unit} of {component_name}"
    
    return total_qty, notes


def get_default_location(db: Session) -> Optional[InventoryLocation]:
    """Read-only counterpart to get_or_create_default_location.

    Returns the default warehouse, or None if none exists yet. Never INSERTs,
    so it is safe for GET preflight endpoints and read-only DB replicas.
    """
    return db.query(InventoryLocation).filter(InventoryLocation.type == "warehouse").first()


def get_or_create_default_location(db: Session) -> InventoryLocation:
    """Get or create the default warehouse location."""
    location = db.query(InventoryLocation).filter(InventoryLocation.type == "warehouse").first()
    if not location:
        location = InventoryLocation(
            name="Main Warehouse",
            code="MAIN",
            type="warehouse",
            active=True
        )
        db.add(location)
        db.flush()
    return location


def get_or_create_inventory(
    db: Session,
    product_id: int,
    location_id: int
) -> Inventory:
    """Get or create an inventory record for a product at a location."""
    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.location_id == location_id
    ).first()

    if not inventory:
        inventory = Inventory(
            product_id=product_id,
            location_id=location_id,
            on_hand_quantity=Decimal("0"),
            allocated_quantity=Decimal("0")
        )
        db.add(inventory)
        db.flush()
    else:
        # Validate allocated doesn't exceed on_hand (consistency check)
        allocated = Decimal(str(inventory.allocated_quantity))
        on_hand = Decimal(str(inventory.on_hand_quantity))
        if allocated > on_hand:
            logger.warning(
                f"Inventory consistency issue detected: Product {product_id}, Location {location_id}: "
                f"Allocated ({allocated}) exceeds On Hand ({on_hand}). "
                f"Available quantity would be negative."
            )

    return inventory


def get_inventory_snapshot(
    db: Session,
    product_id: int,
    location_id: int,
) -> tuple[Decimal, Decimal]:
    """Read-only (on_hand, allocated) snapshot for a product at a location.

    No row lock and no insert-on-miss — safe to call from a GET/preflight path
    with many products in a loop. Do NOT use this where a write follows; use
    inventory_ledger.get_or_create_inventory_row (which locks) for that.
    A missing row reads as (0, 0), matching how a never-stocked product is
    treated everywhere else in inventory math.
    """
    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.location_id == location_id,
    ).first()
    if not inventory:
        return Decimal("0"), Decimal("0")
    return (
        Decimal(str(inventory.on_hand_quantity)),
        Decimal(str(inventory.allocated_quantity)),
    )


def validate_inventory_consistency(
    db: Session,
    product_id: Optional[int] = None,
    location_id: Optional[int] = None,
    auto_fix: bool = False
) -> List[Dict[str, Any]]:
    """
    Validate inventory consistency: allocated should not exceed on_hand.
    
    Args:
        db: Database session
        product_id: Optional filter by product
        location_id: Optional filter by location
        auto_fix: If True, automatically fix inconsistencies by reducing allocated to on_hand
        
    Returns:
        List of inconsistency records found/fixed
    """
    query = db.query(Inventory)
    if product_id:
        query = query.filter(Inventory.product_id == product_id)
    if location_id:
        query = query.filter(Inventory.location_id == location_id)
    
    inconsistencies = []
    for inv in query.all():
        allocated = Decimal(str(inv.allocated_quantity))
        on_hand = Decimal(str(inv.on_hand_quantity))
        available = on_hand - allocated
        
        if allocated > on_hand:
            inconsistency = {
                "product_id": inv.product_id,
                "location_id": inv.location_id,
                "on_hand": float(on_hand),
                "allocated": float(allocated),
                "available": float(available),
                "issue": "allocated_exceeds_on_hand",
                "fixed": False,
            }
            
            if auto_fix:
                # Fix by reducing allocated to on_hand
                inv.allocated_quantity = on_hand
                inv.updated_at = datetime.now(timezone.utc)
                inconsistency["fixed"] = True
                inconsistency["new_allocated"] = float(on_hand)
                logger.info(
                    f"Fixed inventory inconsistency: Product {inv.product_id}, "
                    f"Location {inv.location_id}: Reduced allocated from {allocated} to {on_hand}"
                )
            
            inconsistencies.append(inconsistency)
    
    if auto_fix and inconsistencies:
        db.commit()
    
    return inconsistencies


def create_inventory_transaction(
    db: Session,
    product_id: int,
    location_id: int,
    transaction_type: str,
    quantity: Decimal,
    reference_type: str,
    reference_id: int,
    notes: Optional[str] = None,
    cost_per_unit: Optional[Decimal] = None,
    created_by: Optional[str] = None,
    approval_reason: Optional[str] = None,
    approved_by: Optional[str] = None,
    allow_negative: bool = False,
) -> InventoryTransaction:
    """
    Create an inventory transaction and update inventory quantities.

    Args:
        db: Database session
        product_id: Product being transacted
        location_id: Location for the transaction
        transaction_type: receipt, issue, consumption, adjustment, negative_adjustment
        quantity: Positive magnitude; direction is implied by transaction_type
            (legacy caller convention). For "adjustment" the quantity IS the
            signed delta. Internally translated to the signed-delta convention
            of inventory_ledger.post (HARD-4a), which stores SIGNED quantities.
        reference_type: production_order, sales_order, etc.
        reference_id: ID of the reference document
        notes: Optional notes
        cost_per_unit: Optional cost per unit
        created_by: User who created the transaction
        approval_reason: Reason for negative inventory approval (required if negative)
        approved_by: User approving negative inventory (required if negative)
        allow_negative: If True, allow negative inventory with approval

    Returns:
        Created InventoryTransaction

    Raises:
        ValueError: If negative inventory would occur without approval
    """
    # Callers pass positive magnitudes with direction implied by type
    # (legacy convention). Translate to the signed-delta convention of the
    # canonical poster (HARD-4a): positive delta = stock increases.
    quantity = Decimal(str(quantity))
    if transaction_type in ("receipt", "initial", "return", "production"):
        quantity_delta = quantity
    elif transaction_type in (
        "issue", "consumption", "shipment", "scrap", "negative_adjustment"
    ):
        quantity_delta = -quantity
    elif transaction_type == "adjustment":
        # Adjustments are signed deltas as passed. (No production caller
        # uses this path today; the old code subtracted, which is the sign
        # bug HARD-4a removes.)
        quantity_delta = quantity
    else:
        raise ValueError(f"Unknown transaction_type: {transaction_type}")

    inventory = get_or_create_inventory(db, product_id, location_id)

    # Policy: consumption-like movements that would drive AVAILABLE
    # (on_hand - allocated) negative are held for approval unless the
    # caller pre-approved them.
    requires_approval = False
    if quantity_delta < 0 and transaction_type != "adjustment":
        current_available = (
            Decimal(str(inventory.on_hand_quantity))
            - Decimal(str(inventory.allocated_quantity))
        )
        new_available = current_available + quantity_delta

        if new_available < 0:
            if not allow_negative or not approval_reason or not approved_by:
                requires_approval = True
                # Don't raise - write the row held for approval; the
                # approval workflow applies it later.
            else:
                logger.warning(
                    f"Negative inventory transaction approved: Product {product_id}, "
                    f"Available: {current_available}, Delta: {quantity_delta}, "
                    f"New Available: {new_available}, Reason: {approval_reason}, "
                    f"Approved by: {approved_by}"
                )

    transaction = inventory_ledger.post(
        db,
        product_id=product_id,
        location_id=location_id,
        transaction_type=(
            transaction_type if not requires_approval else "negative_adjustment"
        ),
        quantity_delta=quantity_delta,
        cost_per_unit=cost_per_unit,
        reference_type=reference_type,
        reference_id=reference_id,
        notes=notes,
        created_by=created_by,
        requires_approval=requires_approval,
        approval_reason=approval_reason,
        approved_by=approved_by,
    )

    if requires_approval:
        logger.info(
            f"Inventory transaction {transaction.id} created but requires approval "
            f"for negative inventory: Product {product_id}, Delta: {quantity_delta}"
        )

    return transaction


def _get_net_reserved_by_component(
    db: Session,
    production_order_id: int,
) -> Dict[int, Decimal]:
    """
    Net ledger reservations per component for a production order:
    sum(reservation) - sum(reservation_release), floored at 0.

    Single source for the "how much is already reserved" question used by
    both the delta-idempotent reservation path (RESERVE-1) and the
    ledger→row backfill self-heal.
    """
    from sqlalchemy import func as sqlfunc
    from sqlalchemy import case

    net_rows = (
        db.query(
            InventoryTransaction.product_id,
            sqlfunc.sum(
                case(
                    (InventoryTransaction.transaction_type == "reservation",
                     InventoryTransaction.quantity),
                    else_=Decimal("0"),
                )
                - case(
                    (InventoryTransaction.transaction_type == "reservation_release",
                     InventoryTransaction.quantity),
                    else_=Decimal("0"),
                )
            ).label("net_reserved"),
        )
        .filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == production_order_id,
            InventoryTransaction.transaction_type.in_(
                ["reservation", "reservation_release"]
            ),
        )
        .group_by(InventoryTransaction.product_id)
        .all()
    )
    return {
        row.product_id: max(Decimal("0"), Decimal(str(row.net_reserved)))
        for row in net_rows
    }


def _get_reservation_requirements(
    db: Session,
    production_order: ProductionOrder,
) -> Dict[int, Dict[str, Any]]:
    """
    Canonical per-component reservation requirements for a production order
    (RESERVE-1, mirrors the HARD-12 routing-first explosion semantics).

    PRIMARY source — ProductionOrderOperationMaterial rows: when the order
    has materialized op-material rows (copied from the routing at creation),
    those rows are the order-specific truth and exactly what the release
    gate checks.  Rows already include scrap (applied by
    calculate_required_quantity at copy time) and cost-only routing
    materials were already excluded by copy_routing_to_operations, so
    neither is re-applied here.

    FALLBACK — legacy BOM walk: products without routing materials keep the
    original behavior (active BOM, consume_stage='production', scrap factor
    applied, cost-only lines skipped).

    The two sources are never mixed: op rows REPLACE the BOM walk entirely,
    preventing double reservation for mixed-source products.

    Returns:
        Dict mapping component_id -> {
            "component": Product,
            "quantity": Decimal,  # in the component's inventory unit
            "unit": str,          # component inventory unit
            "source": "routing" | "bom",
        }
    """
    from app.models.production_order import ProductionOrderOperation

    requirements: Dict[int, Dict[str, Any]] = {}

    op_rows = (
        db.query(ProductionOrderOperationMaterial)
        .join(
            ProductionOrderOperation,
            ProductionOrderOperationMaterial.production_order_operation_id
            == ProductionOrderOperation.id,
        )
        .filter(
            ProductionOrderOperation.production_order_id == production_order.id,
        )
        .order_by(
            ProductionOrderOperation.sequence,
            ProductionOrderOperationMaterial.id,
        )
        .all()
    )

    if op_rows:
        for row in op_rows:
            component = db.query(Product).filter(
                Product.id == row.component_id
            ).first()
            if not component:
                continue

            row_qty = Decimal(str(row.quantity_required or 0))
            if row_qty <= Decimal("0"):
                continue

            row_unit = (row.unit or component.unit or "EA").upper()
            component_unit = (component.unit or "EA").upper()

            try:
                converted_qty, _ = convert_and_generate_notes(
                    db=db,
                    bom_qty=row_qty,
                    line_unit=row_unit,
                    component_unit=component_unit,
                    component_name=component.name,
                    component_sku=component.sku,
                    reference_prefix="Reserved for PO#",
                    reference_code=production_order.code,
                )
            except UOMConversionError as e:
                logger.error(
                    f"Failed to reserve materials (op-material row {row.id}): {e}"
                )
                continue

            entry = requirements.get(row.component_id)
            if entry:
                entry["quantity"] += converted_qty
            else:
                requirements[row.component_id] = {
                    "component": component,
                    "quantity": converted_qty,
                    "unit": component_unit,
                    "source": "routing",
                }
        return requirements

    # FALLBACK — legacy BOM walk (no op-material rows on this order)
    bom = db.query(BOM).filter(
        BOM.product_id == production_order.product_id,
        BOM.active.is_(True)
    ).first()

    if not bom:
        logger.warning(
            f"No active BOM found for product {production_order.product_id} "
            f"- no materials to reserve"
        )
        return requirements

    quantity_ordered = Decimal(str(production_order.quantity_ordered or 0))

    bom_lines = db.query(BOMLine).filter(
        BOMLine.bom_id == bom.id,
        BOMLine.consume_stage == "production",
    ).all()

    for line in bom_lines:
        # Skip cost-only items (machine time, overhead)
        if line.is_cost_only:
            continue

        # Skip non-inventory items
        component = db.query(Product).filter(Product.id == line.component_id).first()
        if not component:
            continue

        # Calculate quantity to reserve (BOM qty per unit * ordered units)
        # Apply scrap factor if any
        base_qty = Decimal(str(line.quantity))
        scrap_factor = Decimal(str(line.scrap_factor or 0)) / Decimal("100")
        qty_with_scrap = base_qty * (Decimal("1") + scrap_factor)
        bom_qty = qty_with_scrap * quantity_ordered

        # UOM Conversion: Convert BOM line unit to component's inventory unit
        line_unit = (line.unit or component.unit or "EA").upper()
        component_unit = (component.unit or "EA").upper()

        try:
            total_qty, _ = convert_and_generate_notes(
                db=db,
                bom_qty=bom_qty,
                line_unit=line_unit,
                component_unit=component_unit,
                component_name=component.name,
                component_sku=component.sku,
                reference_prefix="Reserved for PO#",
                reference_code=production_order.code,
            )
        except UOMConversionError as e:
            logger.error(f"Failed to reserve materials: {e}")
            continue

        entry = requirements.get(line.component_id)
        if entry:
            entry["quantity"] += total_qty
        else:
            requirements[line.component_id] = {
                "component": component,
                "quantity": total_qty,
                "unit": component_unit,
                "source": "bom",
            }

    return requirements


def reserve_production_materials(
    db: Session,
    production_order: ProductionOrder,
    created_by: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Reserve (allocate) materials for a production order.

    This increases the allocated_quantity on inventory records, reducing
    available quantity without actually consuming the materials.

    RESERVE-1 — requirement source is routing-first: when the order has
    ProductionOrderOperationMaterial rows (materialized from the routing at
    creation), those rows drive the reservation; otherwise the legacy
    active-BOM walk applies.  See _get_reservation_requirements.

    RESERVE-1 — delta idempotency: the function is safely re-runnable.  For
    each component the net already-reserved quantity (reservation minus
    reservation_release in the ledger) is subtracted from the requirement
    and only the shortfall is reserved ("top-up reservation").  Calling it
    on a fully-reserved order is a no-op apart from re-syncing op-material
    rows.

    HARD-5: reservations may exceed on_hand (flag, not block) — production
    legitimately reserves ahead of receipt.

    Args:
        db: Database session
        production_order: The production order being scheduled
        created_by: User scheduling the order

    Returns:
        List of reservation records with details about what was reserved
        in THIS call (deltas only; components already fully reserved are
        omitted).
    """
    reservations = []
    location = get_or_create_default_location(db)

    requirements = _get_reservation_requirements(db, production_order)
    if not requirements:
        return reservations

    # Net already-reserved per component from the ledger — only reserve the
    # delta up to the requirement so re-runs never double-reserve.
    net_reserved = _get_net_reserved_by_component(db, production_order.id)
    net_after: Dict[int, Decimal] = {}

    for component_id, req in requirements.items():
        component = req["component"]
        component_unit = req["unit"]
        required_qty = req["quantity"]
        already_reserved = net_reserved.get(component_id, Decimal("0"))
        delta_qty = required_qty - already_reserved

        if delta_qty <= Decimal("0"):
            # Already fully reserved — nothing to add; rows re-synced below.
            net_after[component_id] = already_reserved
            logger.info(
                "Reservation already covers requirement for %s on PO#%s "
                "(required %s, net reserved %s) — skipping",
                component.sku,
                production_order.code,
                required_qty,
                already_reserved,
            )
            continue

        is_topup = already_reserved > Decimal("0")

        # Get or create inventory record
        inventory = get_or_create_inventory(db, component_id, location.id)

        # Increase allocated quantity
        current_allocated = Decimal(str(inventory.allocated_quantity))
        current_on_hand = Decimal(str(inventory.on_hand_quantity))
        new_allocated = current_allocated + delta_qty

        # HARD-5 write-time guard: flag (not block) when reservation would
        # exceed on_hand.  Production is allowed to reserve ahead of receipt,
        # so we log + flag but proceed.  The shortage is visible in the
        # reservation return value so callers/UIs can surface it.
        would_exceed, available_after = check_allocation_guard(
            current_on_hand, current_allocated, delta_qty
        )
        if would_exceed:
            logger.warning(
                "HARD-5 allocation guard: reserving %s %s of %s for PO#%s "
                "would exceed on_hand (%s). allocated %s → %s, available_after=%s. "
                "Proceeding (legitimate ahead-of-receipt reservation).",
                delta_qty,
                component_unit,
                component.sku,
                production_order.code,
                current_on_hand,
                current_allocated,
                new_allocated,
                available_after,
            )

        inventory.allocated_quantity = new_allocated
        inventory.updated_at = datetime.now(timezone.utc)

        # Create reservation transaction for audit trail
        unit_cost = get_effective_cost_per_inventory_unit(component)
        total_cost = abs(delta_qty) * unit_cost if unit_cost else None
        if is_topup:
            notes = (
                f"Top-up reservation for PO#{production_order.code}: "
                f"{delta_qty} {component_unit} of {component.name} "
                f"(net already reserved: {already_reserved} {component_unit})"
            )
        else:
            notes = (
                f"Reserved for PO#{production_order.code}: "
                f"{delta_qty} {component_unit} of {component.name}"
            )
        txn = InventoryTransaction(
            product_id=component_id,
            location_id=location.id,
            transaction_type="reservation",
            quantity=delta_qty,
            reference_type="production_order",
            reference_id=production_order.id,
            notes=notes,
            cost_per_unit=unit_cost,
            total_cost=total_cost,
            unit=component_unit,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )
        db.add(txn)

        net_after[component_id] = already_reserved + delta_qty

        reservation_info = {
            "product_id": component_id,
            "product_sku": component.sku,
            "product_name": component.name,
            "quantity_reserved": float(delta_qty),
            "already_reserved": float(already_reserved),
            "is_topup": is_topup,
            "unit": component_unit,
            "on_hand": float(current_on_hand),
            "allocated_after": float(new_allocated),
            "available_after": float(available_after),
            "is_shortage": would_exceed,
        }
        reservations.append(reservation_info)

        if is_topup:
            logger.info(
                f"Top-up reservation: {delta_qty} {component_unit} of "
                f"{component.sku} for PO#{production_order.code} "
                f"(already reserved {already_reserved})"
            )
        elif not would_exceed:
            logger.info(
                f"Reserved {delta_qty} {component_unit} of {component.sku} "
                f"for PO#{production_order.code}"
            )

    # Sync op-material rows: distribute the TOTAL net reserved quantity
    # (prior reservations + this run's delta) across op-material rows for
    # each component, in operation-sequence order, filling each row up to
    # its quantity_required.  Under partial reservation (HARD-5 shortage
    # path or UOM-skipped top-up) we allocate only what was actually
    # reserved.
    for component_id, qty_net in net_after.items():
        _sync_op_material_allocation(db, production_order, component_id, qty_net)

    return reservations


def _sync_op_material_allocation(
    db: Session,
    production_order: "ProductionOrder",
    component_id: int,
    qty_reserved: "Decimal",
) -> None:
    """
    Distribute *qty_reserved* across the op-material rows for *component_id*
    on *production_order*, in operation-sequence order.

    Fills each row up to its quantity_required; any remainder spills to the
    next row.  Excess reservation beyond the total requirement is capped at
    quantity_required (shouldn't happen in practice, but keeps the column
    semantically valid).

    UNITS: *qty_reserved* arrives in the COMPONENT's inventory unit (that is
    what reserve_production_materials reserves in), while row.quantity_required
    is stored in the ROW's unit (copied verbatim from the routing).  Each
    row's requirement is converted into the component unit for the
    distribution math, and the allocation is written back in the ROW's unit —
    quantity_allocated must be comparable to quantity_required because the
    release gate compares them directly.

    This is the single writer of ProductionOrderOperationMaterial.quantity_allocated
    for the reservation direction.  It is idempotent: calling it twice with the
    same qty_reserved leaves the rows in the same state.
    """
    from app.models.production_order import ProductionOrderOperation
    from app.services.uom_service import convert_quantity_safe

    # Collect op-material rows for this component across all operations,
    # ordered by operation.sequence then row id for deterministic distribution.
    rows = (
        db.query(ProductionOrderOperationMaterial)
        .join(
            ProductionOrderOperation,
            ProductionOrderOperationMaterial.production_order_operation_id
            == ProductionOrderOperation.id,
        )
        .filter(
            ProductionOrderOperation.production_order_id == production_order.id,
            ProductionOrderOperationMaterial.component_id == component_id,
        )
        .order_by(
            ProductionOrderOperation.sequence,
            ProductionOrderOperationMaterial.id,
        )
        .all()
    )

    if not rows:
        return

    component = db.query(Product).filter(Product.id == component_id).first()
    component_unit = (
        (component.unit if component else None) or "EA"
    ).upper()

    remaining = qty_reserved
    for row in rows:
        if remaining <= Decimal("0"):
            row.quantity_allocated = Decimal("0")
            continue
        required_row = Decimal(str(row.quantity_required))
        row_unit = (row.unit or component_unit).upper()
        # convert_quantity_safe fast-paths same-unit (the overwhelmingly
        # common case) and falls back to inline G/KG-style conversion when
        # the UOM table is unseeded — same resilience as
        # convert_and_generate_notes on the reservation side.
        required_comp, converted = convert_quantity_safe(
            db, required_row, row_unit, component_unit
        )
        if not converted:
            logger.error(
                "UOM conversion failed distributing reservation for "
                "component %s on PO#%s (row %s: %s -> %s) — assuming 1:1",
                component_id,
                production_order.code,
                row.id,
                row_unit,
                component_unit,
            )
            required_comp = required_row

        alloc_comp = min(remaining, required_comp)
        # Write the allocation back in the ROW's unit via the coverage
        # ratio — full coverage yields exactly quantity_required with no
        # round-trip conversion error.
        if required_comp > Decimal("0"):
            row.quantity_allocated = (alloc_comp / required_comp) * required_row
        else:
            row.quantity_allocated = Decimal("0")
        remaining -= alloc_comp


def _backfill_op_material_from_ledger(
    db: Session,
    production_order: "ProductionOrder",
) -> None:
    """
    Self-heal: rebuild quantity_allocated on op-material rows from the
    inventory reservation ledger for *production_order*.

    Called at the top of release_production_order when active reservations
    exist but op-material rows still show quantity_allocated=0.  The heal
    is idempotent and logged.

    Distribution rule: same as _sync_op_material_allocation — fill each row
    up to its quantity_required in operation-sequence order per component.
    """
    # Sum reservations minus reservation_releases per component
    net_reserved = _get_net_reserved_by_component(db, production_order.id)

    for component_id, qty in net_reserved.items():
        if qty > Decimal("0"):
            _sync_op_material_allocation(db, production_order, component_id, qty)

    logger.info(
        "Self-heal: backfilled op-material quantity_allocated from ledger "
        "for PO#%s (%d component(s))",
        production_order.code,
        len(net_reserved),
    )


def release_production_reservations(
    db: Session,
    production_order: ProductionOrder,
    created_by: Optional[str] = None,
    component_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """
    Release (un-allocate) materials that were reserved for a production order.

    Called when:
    - Production order is cancelled/unscheduled (full release, component_ids=None)
    - Before consuming actuals for a specific stage (to release then consume;
      component_ids scopes the release to that stage — see FIX-1/FIX-2)

    Args:
        db: Database session
        production_order: The production order
        created_by: User performing the action
        component_ids: If provided, only release reservations (and clear
            quantity_allocated) for components in this set. The reservation
            ledger has no stage column, so consumers that only want to
            release THEIR stage's share (e.g. consume_production_materials
            releasing only production-stage components, leaving
            shipping-stage box/label reservations intact until ship) pass
            the stage's component-id universe here. None (default) releases
            everything for the order — the original cancel/delete behavior.

    Returns:
        List of release records
    """
    releases = []
    # Ensure default location exists (not used directly but needed for consistency)
    _location = get_or_create_default_location(db)

    # Find all reservation transactions for this PO
    reservation_query = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.reference_id == production_order.id,
        InventoryTransaction.transaction_type == "reservation",
    )
    if component_ids is not None:
        reservation_query = reservation_query.filter(
            InventoryTransaction.product_id.in_(component_ids)
        )
    reservation_txns = reservation_query.all()

    for txn in reservation_txns:
        # Decrease allocated quantity
        inventory = db.query(Inventory).filter(
            Inventory.product_id == txn.product_id,
            Inventory.location_id == txn.location_id,
        ).first()
        
        if inventory:
            current_allocated = Decimal(str(inventory.allocated_quantity))
            release_qty = Decimal(str(txn.quantity))
            new_allocated = max(Decimal("0"), current_allocated - release_qty)
            
            inventory.allocated_quantity = new_allocated
            inventory.updated_at = datetime.now(timezone.utc)
            
            # Create release transaction for audit - copy cost from original reservation
            unit_cost = txn.cost_per_unit
            total_cost = abs(release_qty) * unit_cost if unit_cost else None
            release_txn = InventoryTransaction(
                product_id=txn.product_id,
                location_id=txn.location_id,
                transaction_type="reservation_release",
                quantity=release_qty,
                reference_type="production_order",
                reference_id=production_order.id,
                notes=f"Released reservation for PO#{production_order.code}",
                cost_per_unit=unit_cost,
                total_cost=total_cost,
                unit=txn.unit,
                created_by=created_by,
                created_at=datetime.now(timezone.utc),
            )
            db.add(release_txn)
            
            component = db.query(Product).filter(Product.id == txn.product_id).first()
            releases.append({
                "product_id": txn.product_id,
                "product_sku": component.sku if component else "Unknown",
                "quantity_released": float(release_qty),
                "new_allocated": float(new_allocated),
            })

            logger.info(
                f"Released reservation of {release_qty} for PO#{production_order.code}"
            )

    # Mirror the release on op-material rows: zero out quantity_allocated for
    # any rows that are still in a pre-consumption state (pending / allocated).
    # Rows already consumed retain their quantity_consumed; only the allocation
    # field is cleared so the two books stay in sync. Scoped to component_ids
    # when provided, matching the ledger-side filter above.
    from app.models.production_order import ProductionOrderOperation
    unconsumed_query = (
        db.query(ProductionOrderOperationMaterial)
        .join(
            ProductionOrderOperation,
            ProductionOrderOperationMaterial.production_order_operation_id
            == ProductionOrderOperation.id,
        )
        .filter(
            ProductionOrderOperation.production_order_id == production_order.id,
            ProductionOrderOperationMaterial.status.in_(["pending", "allocated"]),
        )
    )
    if component_ids is not None:
        unconsumed_query = unconsumed_query.filter(
            ProductionOrderOperationMaterial.component_id.in_(component_ids)
        )
    unconsumed_rows = unconsumed_query.all()
    for row in unconsumed_rows:
        row.quantity_allocated = Decimal("0")

    if unconsumed_rows:
        logger.info(
            "Zeroed quantity_allocated on %d op-material row(s) for PO#%s",
            len(unconsumed_rows),
            production_order.code,
        )

    return releases


def consume_from_material_lots(
    db: Session,
    component_id: int,
    quantity: Decimal,
    production_order_id: int,
    bom_line_id: Optional[int] = None,
) -> List[ProductionLotConsumption]:
    """
    Consume material from available lots using FIFO (oldest first).

    Creates ProductionLotConsumption records linking production orders to material lots.
    Updates MaterialLot.quantity_consumed for each lot used.

    Args:
        db: Database session
        component_id: Product ID of the component being consumed
        quantity: Total quantity to consume (in component's inventory unit)
        production_order_id: Production order consuming the material
        bom_line_id: Optional BOM line ID

    Returns:
        List of ProductionLotConsumption records created
    """
    consumptions = []

    # Get available lots for this component (FIFO by received_date)
    available_lots = db.query(MaterialLot).filter(
        MaterialLot.product_id == component_id,
        MaterialLot.status == "active",
    ).order_by(MaterialLot.received_date.asc()).all()

    if not available_lots:
        logger.debug(f"No active MaterialLots found for component {component_id}")
        return consumptions

    remaining = quantity
    for lot in available_lots:
        if remaining <= Decimal("0"):
            break

        # Calculate available quantity in this lot
        available = (
            lot.quantity_received
            - lot.quantity_consumed
            - lot.quantity_scrapped
            + lot.quantity_adjusted
        )

        if available <= Decimal("0"):
            continue

        # Consume from this lot
        consume_qty = min(available, remaining)

        # Create consumption record
        consumption = ProductionLotConsumption(
            production_order_id=production_order_id,
            material_lot_id=lot.id,
            bom_line_id=bom_line_id,
            quantity_consumed=consume_qty,
            consumed_at=datetime.now(timezone.utc),
        )
        db.add(consumption)
        consumptions.append(consumption)

        # Update lot's consumed quantity
        lot.quantity_consumed = Decimal(str(lot.quantity_consumed or 0)) + consume_qty

        # Check if lot is now depleted
        new_available = (
            lot.quantity_received
            - lot.quantity_consumed
            - lot.quantity_scrapped
            + lot.quantity_adjusted
        )
        if new_available <= Decimal("0"):
            lot.status = "depleted"
            logger.info(f"MaterialLot {lot.lot_number} depleted")

        remaining -= consume_qty
        logger.debug(
            f"Consumed {consume_qty} from lot {lot.lot_number}, "
            f"remaining in lot: {new_available}"
        )

    if remaining > Decimal("0"):
        logger.warning(
            f"Could not fully consume {quantity} for component {component_id}. "
            f"Remaining {remaining} not tracked in lots."
        )

    return consumptions


def consume_operation_material(
    db: Session,
    material: "ProductionOrderOperationMaterial",  # noqa: F821
    production_order: ProductionOrder,
    created_by: Optional[str] = None,
) -> Optional[InventoryTransaction]:
    """
    Consume a single operation material and create proper inventory transaction.

    This is the ROBUST version that actually:
    - Creates an InventoryTransaction with cost_per_unit
    - Updates Inventory.on_hand_quantity
    - Handles UOM conversion
    - Links the transaction back to the material record

    Called by operation_status.consume_operation_materials() when an operation completes.

    Args:
        db: Database session
        material: The ProductionOrderOperationMaterial to consume
        production_order: The production order (for reference info)
        created_by: User completing the operation

    Returns:
        The created InventoryTransaction, or None if material was already consumed
    """

    # Idempotency guard — keyed on THIS material row's status, not the
    # ledger-level (production_order, component) pair.  The per-row guard is
    # intentional: the same component can appear in multiple routing operations
    # (each with its own ProductionOrderOperationMaterial row), and each
    # occurrence is a legitimate independent consumption.  Using
    # _consumption_already_posted here would silently suppress all but the
    # first per-operation consumption of a given component.
    if material.status == 'consumed':
        logger.info(f"Material {material.id} already consumed, skipping")
        return None

    # Get the component product
    component = db.query(Product).filter(Product.id == material.component_id).first()
    if not component:
        logger.error(f"Component {material.component_id} not found for material {material.id}")
        return None

    location = get_or_create_default_location(db)

    # Calculate quantity to consume
    qty_to_consume = Decimal(str(material.quantity_required or 0))
    if qty_to_consume <= 0:
        logger.warning(f"Material {material.id} has zero quantity, skipping")
        return None

    # UOM Conversion: material.unit -> component.unit (inventory unit)
    material_unit = (material.unit or component.unit or "EA").upper().strip()
    component_unit = (component.unit or "EA").upper().strip()

    try:
        total_qty, notes = convert_and_generate_notes(
            db=db,
            bom_qty=qty_to_consume,
            line_unit=material_unit,
            component_unit=component_unit,
            component_name=component.name,
            component_sku=component.sku,
            reference_prefix="Op consumed for PO#",
            reference_code=production_order.code,
        )
    except UOMConversionError as e:
        logger.error(f"UOM conversion failed for material {material.id}: {e}")
        # Don't silently fail - mark material with error but don't create bad transaction
        material.status = 'error'
        material.updated_at = datetime.now(timezone.utc)
        return None

    # Create the actual inventory transaction with cost
    txn = create_inventory_transaction(
        db=db,
        product_id=material.component_id,
        location_id=location.id,
        transaction_type="consumption",
        quantity=total_qty,
        reference_type="production_order",
        reference_id=production_order.id,
        notes=notes,
        cost_per_unit=get_effective_cost_per_inventory_unit(component),
        created_by=created_by,
    )

    # Update the material record and link transaction
    material.quantity_consumed = qty_to_consume
    material.status = 'consumed'
    material.consumed_at = datetime.now(timezone.utc)
    material.inventory_transaction_id = txn.id
    material.updated_at = datetime.now(timezone.utc)

    # Track lot consumption for traceability (FIFO)
    lot_consumptions = consume_from_material_lots(
        db=db,
        component_id=material.component_id,
        quantity=total_qty,
        production_order_id=production_order.id,
        bom_line_id=None,  # Operation materials don't have BOM line links
    )

    logger.info(
        f"Consumed {total_qty} {component_unit} of {component.sku} "
        f"for operation material {material.id} (PO#{production_order.code})"
        f"{f' (tracked in {len(lot_consumptions)} lot(s))' if lot_consumptions else ''}"
        f" - cost_per_unit: ${txn.cost_per_unit or 0:.4f}"
    )

    return txn


def _consumption_already_posted(
    db: Session,
    production_order_id: int,
    component_id: int,
) -> bool:
    """Return True if a non-voided consumption transaction already exists for
    this (production_order, component) pair.

    **BOM-BACKFLUSH USE ONLY** — this helper is scoped to the completion
    backflush path (consume_production_materials).  It MUST NOT be called
    from consume_operation_material, which uses the per-material-row
    ``material.status == 'consumed'`` guard instead.  That per-row guard is
    correct for the per-operation path because the same physical component can
    legitimately appear in multiple routing operations (each with its own
    material row), and each occurrence deserves its own consumption
    transaction.  The ledger-level guard here would erroneously block the
    second (and later) per-operation consumptions of the same component.

    For the backflush path the opposite semantic is correct: skip the entire
    BOM line if ANY per-operation consumption already posted for this
    component — both paths consume the same physical inventory, and the
    per-operation one wins.

    A transaction counts as "already posted" when:
      - reference_type == 'production_order'
      - reference_id   == production_order_id
      - transaction_type == 'consumption'
      - voided_by IS NULL  (not rejected/voided)

    Pending held rows (requires_approval=True, approved_by=None) ARE counted
    as "already posted" — they represent a real consumption event that is
    waiting for inventory-level approval; the component was physically consumed.
    """
    existing = (
        db.query(InventoryTransaction)
        .filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == production_order_id,
            InventoryTransaction.transaction_type == "consumption",
            InventoryTransaction.product_id == component_id,
            InventoryTransaction.voided_by.is_(None),
        )
        .first()
    )
    return existing is not None


class MaterialConsumptionError(Exception):
    """
    Raised when a consumption stage had reservations/allocations but nothing
    was actually consumable (FIX-3 guardrail).

    This replaces the old silent-empty-return behavior: releasing a
    reservation and then finding no routing op-material rows AND no BOM
    line to consume from means material was reserved for real inventory
    that is now being un-reserved with nothing posted in its place — a
    correctness gap that must be surfaced, not swallowed.
    """
    def __init__(self, message: str, production_order_id: Optional[int] = None,
                 product_id: Optional[int] = None, stage: Optional[str] = None):
        self.message = message
        self.production_order_id = production_order_id
        self.product_id = product_id
        self.stage = stage
        super().__init__(self.message)

    def __str__(self):
        return self.message


def _get_stage_op_materials(
    db: Session,
    production_order_id: int,
    stage: str,
) -> Tuple[List["ProductionOrderOperationMaterial"], bool]:
    """
    Shared routing-first + stage-filter + idempotency resolver for material
    consumption (FIX-1/FIX-2).

    Mirrors _get_reservation_requirements's routing-first semantics: when a
    production order has ANY materialized ProductionOrderOperationMaterial
    rows (copied from the routing at release), those rows are the
    order-specific truth for consumption and the legacy BOM walk must NOT
    also run for this order (op rows REPLACE the BOM walk entirely, exactly
    as reservation already does) — this is what keeps reserve and consume
    from diverging again.

    Filters to rows whose parent operation's operation_code resolves (via
    get_consume_stages_for_operation) to include `stage` — e.g. only
    PRINT/EXTRUDE/etc-coded operations are returned for stage="production",
    only PACK/SHIP/LABEL-coded operations for stage="shipping". Operations
    with no operation_code use DEFAULT_CONSUME_STAGES (production + any),
    matching the mapping module's own default and existing test fixtures
    that don't set operation_code.

    IDEMPOTENCY: rows already status=='consumed' are excluded — the
    per-operation path (complete_operation -> consume_operation_materials
    -> consume_operation_material) may already have posted a transaction
    for that exact row; this resolver must never hand back a row for a
    second consumption.

    Args:
        db: Database session
        production_order_id: The production order
        stage: The consume stage to filter to ("production" or "shipping")

    Returns:
        Tuple of:
          - list of unconsumed ProductionOrderOperationMaterial rows for
            this stage (component eagerly usable via row.component_id)
          - has_any_op_rows: True if the order has ANY op-material rows at
            all (any stage, any status) — signals routing-first mode is
            active for this order so the BOM fallback must not also run,
            even if every routing-stage row for THIS stage was already
            consumed or filtered out.
    """
    all_op_rows = _get_all_op_material_rows(db, production_order_id)

    has_any_op_rows = len(all_op_rows) > 0

    stage_rows = []
    for row in all_op_rows:
        if row.status == "consumed":
            continue
        op = row.operation
        stages = get_consume_stages_for_operation(op.operation_code if op else None)
        if stage in stages:
            stage_rows.append(row)

    return stage_rows, has_any_op_rows


def _get_all_op_material_rows(
    db: Session,
    production_order_id: int,
) -> List["ProductionOrderOperationMaterial"]:
    """Load ALL ProductionOrderOperationMaterial rows for a production order
    (any stage, any status), ordered by operation sequence. Shared query
    used by both _get_stage_op_materials (unconsumed, stage-filtered) and
    _get_stage_component_ids (full component universe per stage)."""
    from app.models.production_order import ProductionOrderOperation

    return (
        db.query(ProductionOrderOperationMaterial)
        .join(
            ProductionOrderOperation,
            ProductionOrderOperationMaterial.production_order_operation_id
            == ProductionOrderOperation.id,
        )
        .filter(
            ProductionOrderOperation.production_order_id == production_order_id,
        )
        .order_by(
            ProductionOrderOperation.sequence,
            ProductionOrderOperationMaterial.id,
        )
        .all()
    )


def _get_stage_component_ids(
    db: Session,
    production_order: ProductionOrder,
    stage: str,
) -> set:
    """
    Return the set of component_ids that belong to `stage` for this
    production order — the "universe" of components a stage cares about,
    used to scope reservation-release and the FIX-3 guardrail's
    had-a-reservation check to just this stage's components (the
    reservation ledger itself has no stage column, so this is resolved from
    the same routing-first-then-BOM-fallback source that drives
    consumption).

    Routing-first: if the order has ANY op-material rows (any status), the
    universe is every row (consumed or not) whose parent operation resolves
    to `stage` — including already-consumed rows, since those components
    were legitimately part of this stage's reservation even though they're
    no longer awaiting consumption.

    BOM fallback: only consulted when the order has ZERO op-material rows,
    matching the "op rows replace the BOM walk entirely" rule used
    everywhere else in this module.
    """
    all_op_rows = _get_all_op_material_rows(db, production_order.id)

    if all_op_rows:
        component_ids = set()
        for row in all_op_rows:
            op = row.operation
            stages = get_consume_stages_for_operation(op.operation_code if op else None)
            if stage in stages:
                component_ids.add(row.component_id)
        return component_ids

    # FALLBACK — legacy BOM walk
    bom = db.query(BOM).filter(
        BOM.product_id == production_order.product_id,
        BOM.active.is_(True),
    ).first()
    if bom:
        bom_lines = db.query(BOMLine).filter(
            BOMLine.bom_id == bom.id,
            BOMLine.consume_stage == stage,
            BOMLine.is_cost_only.is_(False),
        ).all()
        return {line.component_id for line in bom_lines}

    # Order has NEITHER routing op-material rows NOR a BOM at all. There is
    # no source to attribute a reservation to any particular stage — but if
    # the ledger nonetheless shows a net-reserved component for this order
    # (an orphaned/legacy reservation, e.g. from a BOM that has since been
    # deleted or deactivated), the FIX-3 guardrail still needs to see it so
    # it doesn't silently vanish. With no BOM/routing at all there is no
    # shipping-stage concept for this order either, so attribute any
    # net-reserved component to the "production" stage query only (the
    # stage every pre-fix reservation implicitly belonged to) — never to
    # "shipping", so consume_shipping_materials doesn't also try to release
    # the same orphaned reservation a second time.
    if stage == "production":
        net_reserved = _get_net_reserved_by_component(db, production_order.id)
        return {
            component_id
            for component_id, qty in net_reserved.items()
            if qty > Decimal("0")
        }
    return set()


def consume_production_materials(
    db: Session,
    production_order: ProductionOrder,
    quantity_completed: Decimal,
    created_by: Optional[str] = None,
    release_reservations: bool = True,
) -> List[InventoryTransaction]:
    """
    Consume production-stage raw materials when a production order completes.

    FIX-1 (routing-first consumption): mirrors the reservation side's
    routing-first resolution (_get_reservation_requirements / RESERVE-1).
    PRIMARY source is materialized ProductionOrderOperationMaterial rows for
    this order's PRODUCTION-stage operations (resolved via
    get_consume_stages_for_operation through the shared
    _get_stage_op_materials helper) — this is the normal case for
    routing-driven / Intake-Studio products that have NO active BOM at all.
    FALLBACK — legacy BOM walk (consume_stage='production'): only runs when
    the order has ZERO op-material rows whatsoever (not just zero for this
    stage), matching reservation's "op rows REPLACE the BOM walk entirely"
    rule so the two paths can never diverge again.

    Only shipping-stage op-materials (PACK/SHIP/LABEL-coded operations) are
    intentionally excluded here — those are consumed at ship time by
    consume_shipping_materials (FIX-2), not at production completion.

    IDEMPOTENCY:
    - Routing-first rows: status=='consumed' rows are skipped by
      _get_stage_op_materials (the per-operation path may have already
      consumed them via complete_operation -> consume_operation_material).
    - BOM fallback (HARD-11): Before posting each BOM-line consumption,
      checks whether a non-voided consumption transaction already exists
      for (production_order, component); if per-operation consumption
      already posted for a component this backflush skips it.

    If release_reservations=True (default), first releases any existing
    PRODUCTION-stage reservations before consuming actual quantities.
    Shipping-stage reservations are left alone — they are released by
    consume_shipping_materials at ship time.

    FIX-3 guardrail: if this production order HAD reservations for the
    production stage but nothing was consumable (neither routing
    op-materials nor a BOM line matched), this is logged at ERROR and
    raised as MaterialConsumptionError rather than silently released with
    an empty return — a reservation vanishing with nothing posted in its
    place is exactly the bug this fix closes.

    Args:
        db: Database session
        production_order: The completed production order
        quantity_completed: Number of units completed (actual, may differ from ordered)
        created_by: User completing the order
        release_reservations: If True, release reservations before consuming

    Returns:
        List of created inventory transactions
    """
    # Resolve which components belong to the PRODUCTION stage for this order
    # (routing-first, BOM-fallback-only-if-no-op-rows — see
    # _get_stage_component_ids) so both the reservation snapshot and the
    # release below are scoped to THIS stage and never touch shipping-stage
    # reservations (e.g. a box reserved for a PACK op).
    stage_component_ids = _get_stage_component_ids(db, production_order, "production")

    # Snapshot whether this order had any net production-stage reservation
    # BEFORE releasing it, so the FIX-3 guardrail can tell "nothing to
    # consume because nothing was reserved" (fine) apart from "something
    # was reserved but consumption produced nothing" (the bug). Scoped to
    # production-stage components only — a shipping-stage-only reservation
    # (e.g. a box) must not trip the production-stage guardrail.
    net_reserved = _get_net_reserved_by_component(db, production_order.id)
    had_reservation = any(
        qty > Decimal("0")
        for component_id, qty in net_reserved.items()
        if component_id in stage_component_ids
    )

    # Release PRODUCTION-stage reservations only — shipping-stage
    # reservations (e.g. packaging) are left intact for
    # consume_shipping_materials to release at ship time.
    if release_reservations:
        release_production_reservations(
            db, production_order, created_by, component_ids=stage_component_ids
        )
    transactions = []
    location = get_or_create_default_location(db)

    # FIX-1: routing-first resolution, production stage only.
    stage_rows, has_any_op_rows = _get_stage_op_materials(
        db, production_order.id, "production"
    )

    if stage_rows:
        for row in stage_rows:
            component = db.query(Product).filter(Product.id == row.component_id).first()
            if not component:
                logger.error(
                    f"Component {row.component_id} not found for op-material "
                    f"row {row.id} (PO {production_order.code}) — skipping"
                )
                continue

            txn = consume_operation_material(
                db=db,
                material=row,
                production_order=production_order,
                created_by=created_by,
            )
            if txn:
                transactions.append(txn)

        # Routing-first mode is active for this order (it has op-material
        # rows) — never fall through to the BOM walk, even if this
        # particular call posted zero new rows (e.g. every stage_rows entry
        # was already consumed by a concurrent per-op call).
        if had_reservation and not transactions:
            logger.error(
                "Production-stage reservation existed for PO %s (product %s) "
                "but zero production-stage op-materials were actually "
                "consumed this call (all already consumed per-operation) — "
                "routing-first mode is active so the BOM fallback does not "
                "apply.",
                production_order.code,
                production_order.product_id,
            )
            raise MaterialConsumptionError(
                f"No production-stage material was consumed for PO "
                f"{production_order.code} despite an existing reservation, "
                f"and routing-first mode is active (order has op-material "
                f"rows) so the BOM fallback does not apply.",
                production_order_id=production_order.id,
                product_id=production_order.product_id,
                stage="production",
            )
        return transactions

    elif has_any_op_rows:
        # Order has op-material rows, just none for the production stage
        # (e.g. a shipping-only routing) — routing-first mode still applies;
        # do not fall back to the BOM walk.
        if had_reservation:
            logger.error(
                "Production-stage reservation existed for PO %s (product %s) "
                "but no consumable production-stage source was found "
                "(routing op-materials all non-production-stage or already "
                "consumed, no BOM fallback applies in routing-first mode).",
                production_order.code,
                production_order.product_id,
            )
            raise MaterialConsumptionError(
                f"No production-stage material was consumed for PO "
                f"{production_order.code} despite an existing reservation, "
                f"and routing-first mode is active (order has op-material "
                f"rows) so the BOM fallback does not apply.",
                production_order_id=production_order.id,
                product_id=production_order.product_id,
                stage="production",
            )
        return transactions

    # FALLBACK — legacy BOM walk (no op-material rows on this order at all)
    bom = db.query(BOM).filter(
        BOM.product_id == production_order.product_id,
        BOM.active.is_(True)
    ).first()

    if not bom:
        if had_reservation:
            logger.error(
                "Production-stage reservation existed for PO %s (product %s) "
                "but no active BOM and no routing op-material rows exist — "
                "nothing was consumed.",
                production_order.code,
                production_order.product_id,
            )
            raise MaterialConsumptionError(
                f"No production-stage material was consumed for PO "
                f"{production_order.code} despite an existing reservation: "
                f"no active BOM and no routing op-material rows.",
                production_order_id=production_order.id,
                product_id=production_order.product_id,
                stage="production",
            )
        logger.warning(f"No active BOM found for product {production_order.product_id}")
        return transactions

    # Get BOM lines for production consumption
    bom_lines = db.query(BOMLine).filter(
        BOMLine.bom_id == bom.id,
        BOMLine.consume_stage == "production",
    ).all()

    for line in bom_lines:
        # Skip cost-only items (machine time, overhead)
        if line.is_cost_only:
            continue

        # Skip non-inventory items
        component = db.query(Product).filter(Product.id == line.component_id).first()
        if not component:
            continue

        # IDEMPOTENCY (HARD-11): skip this BOM-line backflush if per-operation
        # consumption already posted a non-voided consumption transaction for
        # this component on the same production order.  The two paths
        # (per-operation vs BOM-level backflush) consume the same physical
        # inventory; the first one to post wins.
        if _consumption_already_posted(db, production_order.id, line.component_id):
            logger.info(
                "Skipping BOM-line backflush for component %s (PO %s) — "
                "a non-voided consumption transaction already exists "
                "(per-operation consumption or prior call)",
                component.sku,
                production_order.code,
            )
            continue

        # Calculate quantity to consume (BOM qty per unit * completed units)
        # Apply scrap factor if any
        base_qty = Decimal(str(line.quantity))
        scrap_factor = Decimal(str(line.scrap_factor or 0)) / Decimal("100")
        qty_with_scrap = base_qty * (Decimal("1") + scrap_factor)
        bom_qty = qty_with_scrap * quantity_completed

        # UOM Conversion: Convert BOM line unit to component's inventory unit
        # e.g., BOM says 225.23 G, but component is stored in KG
        line_unit = (line.unit or component.unit or "EA").upper()
        component_unit = (component.unit or "EA").upper()

        total_qty, notes = convert_and_generate_notes(
            db=db,
            bom_qty=bom_qty,
            line_unit=line_unit,
            component_unit=component_unit,
            component_name=component.name,
            component_sku=component.sku,
            reference_prefix="Consumed for PO#",
            reference_code=production_order.code,
        )

        # Create consumption transaction
        txn = create_inventory_transaction(
            db=db,
            product_id=line.component_id,
            location_id=location.id,
            transaction_type="consumption",
            quantity=total_qty,
            reference_type="production_order",
            reference_id=production_order.id,
            notes=notes,
            cost_per_unit=get_effective_cost_per_inventory_unit(component),
            created_by=created_by,
        )
        transactions.append(txn)

        # Record lot consumption for traceability (FIFO)
        lot_consumptions = consume_from_material_lots(
            db=db,
            component_id=line.component_id,
            quantity=total_qty,
            production_order_id=production_order.id,
            bom_line_id=line.id,
        )

        logger.info(
            f"Consumed {total_qty} {component_unit} of {component.sku} "
            f"for production order {production_order.id}"
            f"{f' (tracked in {len(lot_consumptions)} lot(s))' if lot_consumptions else ''}"
        )

    if had_reservation and not transactions:
        logger.error(
            "Production-stage reservation existed for PO %s (product %s) "
            "but the BOM produced zero consumable production-stage lines "
            "(all cost-only, missing components, or already consumed "
            "per-op) — nothing was consumed.",
            production_order.code,
            production_order.product_id,
        )
        raise MaterialConsumptionError(
            f"No production-stage material was consumed for PO "
            f"{production_order.code} despite an existing reservation: "
            f"BOM lines produced no consumable output.",
            production_order_id=production_order.id,
            product_id=production_order.product_id,
            stage="production",
        )

    return transactions


def receive_finished_goods(
    db: Session,
    production_order: ProductionOrder,
    quantity_completed: Decimal,
    created_by: Optional[str] = None,
) -> Tuple[Optional[InventoryTransaction], Optional[InventoryTransaction]]:
    """
    Add finished goods to inventory when production order completes.
    Handles overruns by creating separate transactions for ordered vs overrun quantities.

    Args:
        db: Database session
        production_order: The completed production order
        quantity_completed: Number of units completed (may exceed ordered)
        created_by: User completing the order

    Returns:
        Tuple of (ordered_receipt_txn, overrun_receipt_txn) - overrun_txn is None if no overrun
    """
    location = get_or_create_default_location(db)

    product = db.query(Product).filter(Product.id == production_order.product_id).first()
    if not product:
        logger.error(f"Product {production_order.product_id} not found for production order")
        return None, None

    quantity_ordered = Decimal(str(production_order.quantity_ordered or 0))
    overrun_qty = max(Decimal("0"), quantity_completed - quantity_ordered)

    # Create receipt transaction for ordered quantity
    ordered_txn = create_inventory_transaction(
        db=db,
        product_id=production_order.product_id,
        location_id=location.id,
        transaction_type="receipt",
        quantity=quantity_ordered,
        reference_type="production_order",
        reference_id=production_order.id,
        notes=f"Completed production PO#{production_order.code} (ordered quantity)",
        cost_per_unit=get_effective_cost_per_inventory_unit(product),
        created_by=created_by,
    )

    overrun_txn = None
    if overrun_qty > 0:
        # Create separate receipt transaction for overrun (MTS stock)
        overrun_txn = create_inventory_transaction(
            db=db,
            product_id=production_order.product_id,
            location_id=location.id,
            transaction_type="receipt",
            quantity=overrun_qty,
            reference_type="production_order",
            reference_id=production_order.id,
            notes=f"MTS overrun from PO#{production_order.code}: {overrun_qty} units added to stock",
            cost_per_unit=get_effective_cost_per_inventory_unit(product),
            created_by=created_by,
        )
        logger.info(
            f"Received {quantity_completed} units of {product.sku} "
            f"from production order {production_order.id} "
            f"({quantity_ordered} ordered + {overrun_qty} MTS overrun)"
        )
    else:
        logger.info(
            f"Received {quantity_completed} units of {product.sku} "
            f"from production order {production_order.id}"
        )

    return ordered_txn, overrun_txn


def process_production_completion(
    db: Session,
    production_order: ProductionOrder,
    quantity_completed: Decimal,
    created_by: Optional[str] = None,
) -> Tuple[List[InventoryTransaction], Optional[InventoryTransaction], Optional[InventoryTransaction]]:
    """
    Process all inventory transactions for production order completion.

    1. Consumes raw materials based on BOM (production stage items)
    2. Adds finished goods to inventory (ordered quantity)
    3. Adds overrun quantity to inventory as MTS stock (if any)

    Args:
        db: Database session
        production_order: The completed production order
        quantity_completed: Number of units completed (may exceed ordered)
        created_by: User completing the order

    Returns:
        Tuple of (material_consumption_txns, ordered_receipt_txn, overrun_receipt_txn)
    """
    # Consume materials (based on actual quantity completed, including overrun)
    consumption_txns = consume_production_materials(
        db=db,
        production_order=production_order,
        quantity_completed=quantity_completed,
        created_by=created_by,
    )

    # Receive finished goods (handles overruns automatically)
    ordered_txn, overrun_txn = receive_finished_goods(
        db=db,
        production_order=production_order,
        quantity_completed=quantity_completed,
        created_by=created_by,
    )

    return consumption_txns, ordered_txn, overrun_txn


def consume_shipping_materials(
    db: Session,
    sales_order: SalesOrder,
    created_by: Optional[str] = None,
) -> List[InventoryTransaction]:
    """
    Consume shipping-stage packaging materials when a sales order ships.

    FIX-2 (routing-first shipping consumption): supports BOTH sources at
    once, since either can exist depending on how the product was built:
      - Routing-first: ProductionOrderOperationMaterial rows on the
        shipped product's production order(s) whose parent operation
        resolves to stage "shipping" (PACK/SHIP/LABEL-coded ops) — the
        normal case for routing-driven / Intake-Studio products that put
        the box on a PACK/SHIP op and have no BOM at all.
      - BOM: BOMLine rows with consume_stage='shipping' on the product's
        active BOM — the existing/legacy path where packaging is a BOM
        shipping line.
    Both are consumed when both exist; there is no "replaces" relationship
    between BOM and routing at the PER-PRODUCT level the way there is for
    the (single) production-stage BOM-vs-routing choice, because shipping
    packaging is commonly modeled either way per product.

    IDEMPOTENCY: routing op-material rows already status=='consumed' are
    skipped (via the shared _get_stage_op_materials helper) — a component
    consumed once (per-op or by a prior ship call) is never double-posted.

    Reservations: releases only SHIPPING-stage reservations for each
    production order tied to this sales order (component_ids resolved via
    _get_stage_component_ids), leaving production-stage reservations alone
    (those are released by consume_production_materials at completion).

    FIX-3 guardrail: if a production order tied to this sales order HAD a
    shipping-stage reservation but nothing was consumed for it from either
    source, this is logged at ERROR and raised as MaterialConsumptionError.

    Args:
        db: Database session
        sales_order: The sales order being shipped
        created_by: User processing the shipment

    Returns:
        List of created inventory transactions
    """
    transactions = []
    location = get_or_create_default_location(db)

    # Get products to ship - either from lines or legacy single-product format
    products_to_ship = []

    if sales_order.lines:
        for line in sales_order.lines:
            if line.product_id:
                products_to_ship.append((line.product_id, line.quantity))
    elif sales_order.product_id:
        products_to_ship.append((sales_order.product_id, sales_order.quantity or 1))

    for product_id, qty in products_to_ship:
        product_had_reservation = False
        product_consumed_anything = False

        # --- Routing-first: shipping-stage op-materials on this sales
        # order's production order(s) for this product ---
        production_orders = (
            db.query(ProductionOrder)
            .filter(
                ProductionOrder.sales_order_id == sales_order.id,
                ProductionOrder.product_id == product_id,
            )
            .all()
        )

        for po in production_orders:
            stage_component_ids = _get_stage_component_ids(db, po, "shipping")

            net_reserved = _get_net_reserved_by_component(db, po.id)
            po_had_reservation = any(
                net_qty > Decimal("0")
                for component_id, net_qty in net_reserved.items()
                if component_id in stage_component_ids
            )
            product_had_reservation = product_had_reservation or po_had_reservation

            # Release SHIPPING-stage reservations for this PO only —
            # production-stage reservations were already released (or will
            # be) by consume_production_materials.
            release_production_reservations(
                db, po, created_by, component_ids=stage_component_ids
            )

            stage_rows, _has_any_op_rows = _get_stage_op_materials(db, po.id, "shipping")
            for row in stage_rows:
                component = db.query(Product).filter(Product.id == row.component_id).first()
                if not component:
                    logger.error(
                        f"Component {row.component_id} not found for shipping "
                        f"op-material row {row.id} (PO {po.code}) — skipping"
                    )
                    continue

                txn = consume_operation_material(
                    db=db,
                    material=row,
                    production_order=po,
                    created_by=created_by,
                )
                if txn:
                    transactions.append(txn)
                    product_consumed_anything = True

        # --- BOM: shipping-stage BOM lines on the product's active BOM ---
        bom = db.query(BOM).filter(
            BOM.product_id == product_id,
            BOM.active.is_(True)
        ).first()

        if bom:
            # Get BOM lines for shipping consumption
            bom_lines = db.query(BOMLine).filter(
                BOMLine.bom_id == bom.id,
                BOMLine.consume_stage == "shipping",
            ).all()

            for line in bom_lines:
                if line.is_cost_only:
                    continue

                component = db.query(Product).filter(Product.id == line.component_id).first()
                if not component:
                    continue

                # HARD-11-style idempotency: skip if a non-voided shipping
                # consumption already posted for this component on this
                # sales order (e.g. a prior call, or this same product
                # appearing on multiple lines).
                existing = (
                    db.query(InventoryTransaction)
                    .filter(
                        InventoryTransaction.reference_type == "sales_order",
                        InventoryTransaction.reference_id == sales_order.id,
                        InventoryTransaction.transaction_type == "consumption",
                        InventoryTransaction.product_id == line.component_id,
                        InventoryTransaction.voided_by.is_(None),
                    )
                    .first()
                )
                if existing:
                    logger.info(
                        "Skipping BOM shipping-line consumption for component %s "
                        "(SO %s) — a non-voided consumption transaction already "
                        "exists",
                        component.sku,
                        sales_order.order_number,
                    )
                    continue

                # Calculate quantity to consume
                bom_qty = Decimal(str(line.quantity)) * Decimal(str(qty))

                # UOM Conversion: Convert BOM line unit to component's inventory unit
                line_unit = (line.unit or component.unit or "EA").upper()
                component_unit = (component.unit or "EA").upper()

                total_qty, notes = convert_and_generate_notes(
                    db=db,
                    bom_qty=bom_qty,
                    line_unit=line_unit,
                    component_unit=component_unit,
                    component_name=component.name,
                    component_sku=component.sku,
                    reference_prefix="Shipping materials for SO#",
                    reference_code=sales_order.order_number,
                )

                txn = create_inventory_transaction(
                    db=db,
                    product_id=line.component_id,
                    location_id=location.id,
                    transaction_type="consumption",
                    quantity=total_qty,
                    reference_type="sales_order",
                    reference_id=sales_order.id,
                    notes=notes,
                    cost_per_unit=get_effective_cost_per_inventory_unit(component),
                    created_by=created_by,
                )
                transactions.append(txn)
                product_consumed_anything = True

                logger.info(
                    f"Consumed {total_qty} {component_unit} of {component.sku} "
                    f"for shipping order {sales_order.id}"
                )

        # FIX-3 guardrail: a shipping-stage reservation existed for this
        # product's production order(s) but neither routing op-materials
        # nor a BOM shipping line produced any consumption.
        if product_had_reservation and not product_consumed_anything:
            logger.error(
                "Shipping-stage reservation existed for product %s on SO %s "
                "but no consumable shipping-stage source was found (no "
                "matching routing op-materials, no BOM shipping line) — "
                "nothing was consumed.",
                product_id,
                sales_order.order_number,
            )
            raise MaterialConsumptionError(
                f"No shipping-stage material was consumed for product "
                f"{product_id} on SO {sales_order.order_number} despite an "
                f"existing reservation.",
                product_id=product_id,
                stage="shipping",
            )

    return transactions


def issue_shipped_goods(
    db: Session,
    sales_order: SalesOrder,
    created_by: Optional[str] = None,
) -> List[Tuple[Optional[SalesOrderLine], InventoryTransaction]]:
    """
    Issue finished goods from inventory when an order ships.

    Returns a list of (line, txn) pairs so callers can attribute each shipment
    transaction back to its originating SalesOrderLine — e.g. to write
    SalesOrderLine.shipped_quantity per line. Two lines that share a product_id
    each get their own pair (no positional collapsing). Lines without a product
    (service/material) are skipped. A header-only legacy order (no lines, but
    sales_order.product_id set) yields a single (None, txn).

    Args:
        db: Database session
        sales_order: The sales order being shipped
        created_by: User processing the shipment

    Returns:
        List of (SalesOrderLine | None, InventoryTransaction) pairs
    """
    result: List[Tuple[Optional[SalesOrderLine], InventoryTransaction]] = []
    location = get_or_create_default_location(db)

    def _issue(line: Optional[SalesOrderLine], product_id: int, qty) -> None:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return
        txn = create_inventory_transaction(
            db=db,
            product_id=product_id,
            location_id=location.id,
            transaction_type="shipment",
            quantity=Decimal(str(qty)),
            reference_type="sales_order",
            reference_id=sales_order.id,
            notes=f"Shipped for SO#{sales_order.order_number}: {product.name}",
            cost_per_unit=get_effective_cost_per_inventory_unit(product),
            created_by=created_by,
        )
        result.append((line, txn))
        logger.info(
            f"Issued {qty} units of {product.sku} for sales order "
            f"{sales_order.id}" + (f" (line {line.id})" if line is not None else "")
        )

    if sales_order.lines:
        for line in sales_order.lines:
            if line.product_id:
                _issue(line, line.product_id, line.quantity)
    elif sales_order.product_id:
        _issue(None, sales_order.product_id, sales_order.quantity or 1)

    return result


def process_shipment(
    db: Session,
    sales_order: SalesOrder,
    created_by: Optional[str] = None,
) -> Tuple[List[InventoryTransaction], List[Tuple[Optional[SalesOrderLine], InventoryTransaction]]]:
    """
    Process all inventory transactions for shipping an order.

    1. Consumes packaging materials (shipping stage BOM items)
    2. Issues finished goods from inventory

    Args:
        db: Database session
        sales_order: The sales order being shipped
        created_by: User processing the shipment

    Returns:
        Tuple of (packaging_consumption_txns, goods_issue_pairs) where each
        goods-issue pair is (SalesOrderLine | None, InventoryTransaction).
    """
    # Consume packaging materials
    packaging_txns = consume_shipping_materials(
        db=db,
        sales_order=sales_order,
        created_by=created_by,
    )

    # Issue finished goods (as (line, txn) pairs for per-line attribution)
    issue_pairs = issue_shipped_goods(
        db=db,
        sales_order=sales_order,
        created_by=created_by,
    )

    # Track consumed products for potential MRP recalculation
    # This is called from the endpoint which handles the actual trigger,
    # but we track here for future incremental MRP support
    consumed_product_ids = set()
    for txn in packaging_txns:
        consumed_product_ids.add(txn.product_id)
    
    # Log consumed products for MRP tracking
    if consumed_product_ids:
        logger.debug(
            f"Packaging materials consumed for SO {sales_order.id}",
            extra={
                "sales_order_id": sales_order.id,
                "consumed_product_ids": list(consumed_product_ids)
            }
        )

    return packaging_txns, issue_pairs
