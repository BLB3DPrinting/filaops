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
from app.models.production_order import ProductionOrder
from app.models.sales_order import SalesOrder
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


def reserve_production_materials(
    db: Session,
    production_order: ProductionOrder,
    created_by: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Reserve (allocate) materials when a production order is scheduled.
    
    This increases the allocated_quantity on inventory records, reducing
    available quantity without actually consuming the materials.
    
    Materials are reserved based on BOM quantity * ordered quantity.
    
    Args:
        db: Database session
        production_order: The production order being scheduled
        created_by: User scheduling the order
    
    Returns:
        List of reservation records with details about what was reserved
    """
    reservations = []
    location = get_or_create_default_location(db)
    
    # Get BOM for the product
    bom = db.query(BOM).filter(
        BOM.product_id == production_order.product_id,
        BOM.active.is_(True)
    ).first()
    
    if not bom:
        logger.warning(f"No active BOM found for product {production_order.product_id} - no materials to reserve")
        return reservations
    
    quantity_ordered = Decimal(str(production_order.quantity_ordered or 0))
    
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
        
        # Get or create inventory record
        inventory = get_or_create_inventory(db, line.component_id, location.id)

        # Increase allocated quantity
        current_allocated = Decimal(str(inventory.allocated_quantity))
        current_on_hand = Decimal(str(inventory.on_hand_quantity))
        new_allocated = current_allocated + total_qty

        # HARD-5 write-time guard: flag (not block) when reservation would
        # exceed on_hand.  Production is allowed to reserve ahead of receipt,
        # so we log + flag but proceed.  The shortage is visible in the
        # reservation return value so callers/UIs can surface it.
        would_exceed, available_after = check_allocation_guard(
            current_on_hand, current_allocated, total_qty
        )
        if would_exceed:
            logger.warning(
                "HARD-5 allocation guard: reserving %s %s of %s for PO#%s "
                "would exceed on_hand (%s). allocated %s → %s, available_after=%s. "
                "Proceeding (legitimate ahead-of-receipt reservation).",
                total_qty,
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
        total_cost = abs(total_qty) * unit_cost if unit_cost else None
        txn = InventoryTransaction(
            product_id=line.component_id,
            location_id=location.id,
            transaction_type="reservation",
            quantity=total_qty,
            reference_type="production_order",
            reference_id=production_order.id,
            notes=f"Reserved for PO#{production_order.code}: {total_qty} {component_unit} of {component.name}",
            cost_per_unit=unit_cost,
            total_cost=total_cost,
            unit=component_unit,
            created_by=created_by,
            created_at=datetime.now(timezone.utc),
        )
        db.add(txn)

        reservation_info = {
            "product_id": line.component_id,
            "product_sku": component.sku,
            "product_name": component.name,
            "quantity_reserved": float(total_qty),
            "unit": component_unit,
            "on_hand": float(current_on_hand),
            "allocated_after": float(new_allocated),
            "available_after": float(available_after),
            "is_shortage": would_exceed,
        }
        reservations.append(reservation_info)

        if not would_exceed:
            logger.info(
                f"Reserved {total_qty} {component_unit} of {component.sku} "
                f"for PO#{production_order.code}"
            )
    
    return reservations


def release_production_reservations(
    db: Session,
    production_order: ProductionOrder,
    created_by: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Release (un-allocate) materials that were reserved for a production order.
    
    Called when:
    - Production order is cancelled/unscheduled
    - Before consuming actuals (to release then consume)
    
    Args:
        db: Database session
        production_order: The production order
        created_by: User performing the action
    
    Returns:
        List of release records
    """
    releases = []
    # Ensure default location exists (not used directly but needed for consistency)
    _location = get_or_create_default_location(db)

    # Find all reservation transactions for this PO
    reservation_txns = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.reference_id == production_order.id,
        InventoryTransaction.transaction_type == "reservation",
    ).all()
    
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

    # Skip already consumed materials
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

    Used by consume_production_materials to prevent double-posting when
    per-operation consumption (consume_operation_material) already fired for
    the same component before the BOM-level completion backflush runs.

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


def consume_production_materials(
    db: Session,
    production_order: ProductionOrder,
    quantity_completed: Decimal,
    created_by: Optional[str] = None,
    release_reservations: bool = True,
) -> List[InventoryTransaction]:
    """
    Consume raw materials based on BOM when production order completes.

    Only consumes items with consume_stage='production' and cost_only=False.

    IDEMPOTENCY (HARD-11): Before posting each BOM-line consumption, checks
    whether a non-voided consumption transaction already exists for
    (production_order, component).  If per-operation consumption
    (consume_operation_material) already posted a transaction for a given
    component, this backflush skips it with a log entry.  The check is
    keyed on component_id so that if the same component appears on multiple
    BOM lines (unusual but possible) each line is guarded independently.

    If release_reservations=True (default), first releases any existing
    reservations before consuming actual quantities.

    Args:
        db: Database session
        production_order: The completed production order
        quantity_completed: Number of units completed (actual, may differ from ordered)
        created_by: User completing the order
        release_reservations: If True, release reservations before consuming

    Returns:
        List of created inventory transactions
    """
    # Release reservations first if requested
    if release_reservations:
        release_production_reservations(db, production_order, created_by)
    transactions = []
    location = get_or_create_default_location(db)

    # Get BOM for the product
    bom = db.query(BOM).filter(
        BOM.product_id == production_order.product_id,
        BOM.active.is_(True)
    ).first()

    if not bom:
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
    Consume packaging materials based on BOM when order ships.

    Only consumes items with consume_stage='shipping' from the order's product BOMs.

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
        # Get BOM for product
        bom = db.query(BOM).filter(
            BOM.product_id == product_id,
            BOM.active.is_(True)
        ).first()

        if not bom:
            continue

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

            logger.info(
                f"Consumed {total_qty} {component_unit} of {component.sku} "
                f"for shipping order {sales_order.id}"
            )

    return transactions


def issue_shipped_goods(
    db: Session,
    sales_order: SalesOrder,
    created_by: Optional[str] = None,
) -> List[InventoryTransaction]:
    """
    Issue finished goods from inventory when order ships.

    Args:
        db: Database session
        sales_order: The sales order being shipped
        created_by: User processing the shipment

    Returns:
        List of created inventory transactions
    """
    transactions = []
    location = get_or_create_default_location(db)

    # Get products to ship
    products_to_ship = []

    if sales_order.lines:
        for line in sales_order.lines:
            if line.product_id:
                products_to_ship.append((line.product_id, line.quantity))
    elif sales_order.product_id:
        products_to_ship.append((sales_order.product_id, sales_order.quantity or 1))

    for product_id, qty in products_to_ship:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            continue

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
        transactions.append(txn)

        logger.info(
            f"Issued {qty} units of {product.sku} "
            f"for sales order {sales_order.id}"
        )

    return transactions


def process_shipment(
    db: Session,
    sales_order: SalesOrder,
    created_by: Optional[str] = None,
) -> Tuple[List[InventoryTransaction], List[InventoryTransaction]]:
    """
    Process all inventory transactions for shipping an order.

    1. Consumes packaging materials (shipping stage BOM items)
    2. Issues finished goods from inventory

    Args:
        db: Database session
        sales_order: The sales order being shipped
        created_by: User processing the shipment

    Returns:
        Tuple of (packaging_consumption_txns, goods_issue_txns)
    """
    # Consume packaging materials
    packaging_txns = consume_shipping_materials(
        db=db,
        sales_order=sales_order,
        created_by=created_by,
    )

    # Issue finished goods
    issue_txns = issue_shipped_goods(
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

    return packaging_txns, issue_txns
