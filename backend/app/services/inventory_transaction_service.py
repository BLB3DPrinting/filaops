"""
Admin Inventory Transaction Service

Handles manual inventory transaction CRUD for admin endpoints:
- List transactions with filters
- Create transactions (receipt, issue, transfer, adjustment)
- List locations
- Batch inventory updates (cycle counting)
- Inventory summary for cycle counting

This is distinct from ``inventory_service.py`` (automated production/shipping
transactions) and ``transaction_service.py`` (atomic inventory + GL entries).
Business logic extracted from ``admin/inventory_transactions.py``.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models.inventory import Inventory, InventoryLocation, InventoryTransaction
from app.models.product import Product
from app.services.inventory_helpers import is_material
from app.services.transaction_service import TransactionService
from app.services.uom_service import convert_quantity_safe

logger = get_logger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def normalize_unit(unit: Optional[str]) -> Optional[str]:
    """Normalize unit string to standard format.

    Handles common variations:
    - "gram", "grams", "g" -> "G"
    - "kilogram", "kilograms", "kg" -> "KG"
    - "milligram", "milligrams", "mg" -> "MG"
    - Other units are uppercased and stripped
    """
    if not unit:
        return None

    unit = unit.strip().lower()

    if unit in ("gram", "grams", "g"):
        return "G"
    elif unit in ("kilogram", "kilograms", "kg"):
        return "KG"
    elif unit in ("milligram", "milligrams", "mg"):
        return "MG"

    return unit.upper()


def convert_quantity_to_kg_for_cost(
    db: Session,
    quantity: Decimal,
    product_unit: Optional[str],
    product_id: int,
    product_sku: Optional[str] = None,
) -> float:
    """Convert quantity to kilograms for cost calculation.

    Cost per unit is stored per-KG for materials, so we need to convert
    the quantity to KG before multiplying by cost_per_unit.
    """
    normalized_unit = normalize_unit(product_unit)

    if not normalized_unit:
        logger.warning(
            f"Product {product_id} ({product_sku or 'unknown'}) has no unit specified. "
            f"Assuming quantity {quantity} is already in cost unit (KG) for cost calculation.",
            extra={"product_id": product_id, "product_sku": product_sku, "quantity": str(quantity)},
        )
        try:
            return float(quantity)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Cannot convert quantity {quantity} to float: {e}")

    if normalized_unit == "KG":
        try:
            return float(quantity)
        except (ValueError, TypeError) as e:
            raise ValueError(f"Cannot convert quantity {quantity} to float: {e}")

    converted_qty, success = convert_quantity_safe(db, quantity, normalized_unit, "KG")

    if not success:
        local_mass_conversions = {
            "MG": Decimal("0.000001"),
            "G": Decimal("0.001"),
        }
        if normalized_unit in local_mass_conversions:
            conversion_factor = local_mass_conversions[normalized_unit]
            converted_qty = quantity * conversion_factor
            success = True

    if not success:
        error_msg = (
            f"Cannot convert quantity {quantity} {normalized_unit} to KG for product {product_id} "
            f"({product_sku or 'unknown'}). Unit '{normalized_unit}' is unknown or incompatible."
        )
        logger.error(error_msg, extra={"product_id": product_id, "product_sku": product_sku})
        raise ValueError(error_msg)

    try:
        return float(converted_qty)
    except (ValueError, TypeError) as e:
        raise ValueError(f"Cannot convert quantity {converted_qty} to float: {e}")


# ============================================================================
# QUERY FUNCTIONS
# ============================================================================

def list_transactions(
    db: Session,
    *,
    product_id: Optional[int] = None,
    transaction_type: Optional[str] = None,
    location_id: Optional[int] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """List inventory transactions with filters.

    Returns stored total_cost and unit directly (single source of truth).
    Legacy transactions without stored values get a fallback calculation.
    """
    query = db.query(InventoryTransaction).join(Product)

    if product_id:
        query = query.filter(InventoryTransaction.product_id == product_id)
    if transaction_type:
        query = query.filter(InventoryTransaction.transaction_type == transaction_type)
    if location_id:
        query = query.filter(InventoryTransaction.location_id == location_id)
    if reference_type:
        query = query.filter(InventoryTransaction.reference_type == reference_type)
    if reference_id:
        query = query.filter(InventoryTransaction.reference_id == reference_id)

    transactions = query.order_by(desc(InventoryTransaction.created_at)).offset(offset).limit(limit).all()

    result = []
    for txn in transactions:
        product = db.query(Product).filter(Product.id == txn.product_id).first()
        location = (
            db.query(InventoryLocation).filter(InventoryLocation.id == txn.location_id).first()
            if txn.location_id
            else None
        )
        to_location = (
            db.query(InventoryLocation).filter(InventoryLocation.id == txn.to_location_id).first()
            if hasattr(txn, "to_location_id") and txn.to_location_id
            else None
        )

        stored_total_cost = getattr(txn, "total_cost", None)
        stored_unit = getattr(txn, "unit", None)

        if stored_total_cost is not None:
            total_cost = stored_total_cost
        elif txn.cost_per_unit is not None and txn.quantity is not None:
            try:
                if product and is_material(product):
                    quantity_kg = convert_quantity_to_kg_for_cost(
                        db, txn.quantity, product.unit, product.id, product.sku
                    )
                    total_cost = Decimal(str(float(txn.cost_per_unit) * quantity_kg))
                else:
                    total_cost = Decimal(str(float(txn.cost_per_unit) * float(txn.quantity)))
            except (ValueError, TypeError) as e:
                logger.error(f"Failed to calculate total_cost for transaction {txn.id}: {e}")
                total_cost = None
        else:
            total_cost = None

        if stored_unit:
            display_unit = stored_unit
        elif product:
            display_unit = "G" if is_material(product) else product.unit
        else:
            display_unit = None

        result.append({
            "id": txn.id,
            "product_id": txn.product_id,
            "product_sku": product.sku if product else "",
            "product_name": product.name if product else "",
            "product_unit": product.unit if product else None,
            "material_type_id": product.material_type_id if product else None,
            "location_id": txn.location_id,
            "location_name": location.name if location else None,
            "transaction_type": txn.transaction_type,
            "quantity": txn.quantity,
            "unit": display_unit,
            "cost_per_unit": txn.cost_per_unit,
            "total_cost": total_cost,
            "reference_type": txn.reference_type,
            "reference_id": txn.reference_id,
            "lot_number": txn.lot_number,
            "serial_number": txn.serial_number,
            "notes": txn.notes,
            "created_at": txn.created_at,
            "created_by": txn.created_by,
            "to_location_id": getattr(txn, "to_location_id", None),
            "to_location_name": to_location.name if to_location else None,
        })

    return result


def list_locations(db: Session) -> List[Dict[str, Any]]:
    """List all active inventory locations."""
    locations = db.query(InventoryLocation).filter(InventoryLocation.active.is_(True)).all()
    return [
        {"id": loc.id, "name": loc.name, "code": loc.code, "type": loc.type}
        for loc in locations
    ]


def get_inventory_summary(
    db: Session,
    *,
    location_id: Optional[int] = None,
    category_id: Optional[int] = None,
    search: Optional[str] = None,
    show_zero: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """Get inventory summary for cycle counting."""
    query = db.query(Inventory).join(Product)

    if location_id:
        query = query.filter(Inventory.location_id == location_id)
    if category_id:
        query = query.filter(Product.category_id == category_id)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(Product.sku.ilike(search_term), Product.name.ilike(search_term))
        )
    if not show_zero:
        query = query.filter(Inventory.on_hand_quantity > 0)

    total = query.count()
    items = query.order_by(Product.sku).offset(offset).limit(limit).all()

    result = []
    for inv in items:
        product = inv.product
        location = inv.location
        result.append({
            "inventory_id": inv.id,
            "product_id": product.id,
            "product_sku": product.sku,
            "product_name": product.name,
            "category_name": product.item_category.name if product.item_category else None,
            "unit": "G" if is_material(product) else (product.unit or "EA"),
            "location_id": location.id if location else None,
            "location_name": location.name if location else None,
            "on_hand_quantity": float(inv.on_hand_quantity),
            "allocated_quantity": float(inv.allocated_quantity),
            "available_quantity": (
                float(inv.available_quantity)
                if inv.available_quantity
                else float(inv.on_hand_quantity) - float(inv.allocated_quantity)
            ),
            "last_counted": inv.last_counted.isoformat() if inv.last_counted else None,
        })

    return {"items": result, "total": total, "limit": limit, "offset": offset}


# ============================================================================
# MUTATION FUNCTIONS
# ============================================================================

def _get_or_create_default_location(db: Session) -> InventoryLocation:
    """Get first warehouse location or create a default one."""
    location = db.query(InventoryLocation).filter(InventoryLocation.type == "warehouse").first()
    if not location:
        location = InventoryLocation(
            name="Main Warehouse", code="MAIN", type="warehouse", active=True
        )
        db.add(location)
        db.flush()
    return location


def _get_or_create_inventory(
    db: Session, product_id: int, location_id: int
) -> Inventory:
    """Get or create an inventory record."""
    inventory = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.location_id == location_id,
    ).first()
    if not inventory:
        inventory = Inventory(
            product_id=product_id,
            location_id=location_id,
            on_hand_quantity=0,
            allocated_quantity=0,
        )
        db.add(inventory)
        db.flush()
    return inventory


def create_transaction(
    db: Session,
    *,
    product_id: int,
    transaction_type: str,
    quantity: Decimal,
    created_by: str,
    location_id: Optional[int] = None,
    cost_per_unit: Optional[Decimal] = None,
    reference_type: Optional[str] = None,
    reference_id: Optional[int] = None,
    lot_number: Optional[str] = None,
    serial_number: Optional[str] = None,
    notes: Optional[str] = None,
    to_location_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Create an inventory transaction and update inventory.

    Returns a dict with the transaction data plus product/location names
    for building the API response.

    Raises:
        ValueError: For validation errors (product not found, bad type, etc.)
    """
    # Validate product
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise ValueError(f"Product {product_id} not found")

    # Validate / resolve location
    if location_id:
        location = db.query(InventoryLocation).filter(InventoryLocation.id == location_id).first()
        if not location:
            raise ValueError(f"Location {location_id} not found")
    else:
        location = _get_or_create_default_location(db)

    # Validate transaction type
    valid_types = ["receipt", "issue", "transfer", "adjustment", "consumption", "scrap"]
    if transaction_type not in valid_types:
        raise ValueError(f"Invalid transaction_type. Must be one of: {', '.join(valid_types)}")

    # Transfer validation
    to_location = None
    if transaction_type == "transfer":
        if not to_location_id:
            raise ValueError("to_location_id required for transfer transactions")
        to_location = db.query(InventoryLocation).filter(InventoryLocation.id == to_location_id).first()
        if not to_location:
            raise ValueError(f"To location {to_location_id} not found")
        if to_location_id == location.id:
            raise ValueError("Cannot transfer to the same location")

    inventory = _get_or_create_inventory(db, product_id, location.id)

    # Handle transfers (two transactions)
    if transaction_type == "transfer":
        if float(inventory.on_hand_quantity) < float(quantity):
            raise ValueError(
                f"Insufficient inventory for transfer. "
                f"On hand: {inventory.on_hand_quantity}, requested: {quantity}"
            )

        total_cost = None
        if cost_per_unit is not None and quantity:
            total_cost = float(quantity) * float(cost_per_unit)

        from_transaction = InventoryTransaction(
            product_id=product_id,
            location_id=location.id,
            transaction_type="issue",
            reference_type=reference_type or "transfer",
            reference_id=reference_id,
            quantity=quantity,
            cost_per_unit=cost_per_unit,
            total_cost=total_cost,
            lot_number=lot_number,
            serial_number=serial_number,
            notes=f"Transfer to {to_location.name if to_location else 'location'}: {notes or ''}",
            created_by=created_by,
        )
        db.add(from_transaction)

        inventory.on_hand_quantity = float(inventory.on_hand_quantity) - float(quantity)

        to_inventory = _get_or_create_inventory(db, product_id, to_location_id)

        to_transaction = InventoryTransaction(
            product_id=product_id,
            location_id=to_location_id,
            transaction_type="receipt",
            reference_type=reference_type or "transfer",
            reference_id=reference_id,
            quantity=quantity,
            cost_per_unit=cost_per_unit,
            total_cost=total_cost,
            lot_number=lot_number,
            serial_number=serial_number,
            notes=f"Transfer from {location.name}: {notes or ''}",
            created_by=created_by,
        )
        db.add(to_transaction)

        to_inventory.on_hand_quantity = float(to_inventory.on_hand_quantity) + float(quantity)

        transaction = from_transaction
    else:
        total_cost = None
        if cost_per_unit is not None and quantity:
            total_cost = float(quantity) * float(cost_per_unit)

        transaction = InventoryTransaction(
            product_id=product_id,
            location_id=location.id,
            transaction_type=transaction_type,
            reference_type=reference_type,
            reference_id=reference_id,
            quantity=quantity,
            cost_per_unit=cost_per_unit,
            total_cost=total_cost,
            lot_number=lot_number,
            serial_number=serial_number,
            notes=notes,
            created_by=created_by,
        )
        db.add(transaction)

        if transaction_type == "receipt":
            inventory.on_hand_quantity = float(inventory.on_hand_quantity) + float(quantity)
        elif transaction_type in ["issue", "consumption", "scrap"]:
            if float(inventory.on_hand_quantity) < float(quantity):
                raise ValueError(
                    f"Insufficient inventory. "
                    f"On hand: {inventory.on_hand_quantity}, requested: {quantity}"
                )
            inventory.on_hand_quantity = float(inventory.on_hand_quantity) - float(quantity)
        elif transaction_type == "adjustment":
            inventory.on_hand_quantity = float(quantity)

    db.commit()
    db.refresh(transaction)

    # Build response total_cost
    response_total_cost = None
    if transaction.cost_per_unit is not None and transaction.quantity is not None:
        try:
            if is_material(product):
                quantity_kg = convert_quantity_to_kg_for_cost(
                    db, transaction.quantity, product.unit, product.id, product.sku
                )
                response_total_cost = float(transaction.cost_per_unit) * quantity_kg
            else:
                response_total_cost = float(transaction.cost_per_unit) * float(transaction.quantity)
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to calculate total_cost for transaction {transaction.id}: {e}")
            response_total_cost = None

    return {
        "transaction": transaction,
        "product": product,
        "location": location,
        "to_location": to_location,
        "original_type": transaction_type,
        "response_total_cost": Decimal(str(response_total_cost)) if response_total_cost else None,
    }


def batch_update_inventory(
    db: Session,
    *,
    items: List[Dict[str, Any]],
    location_id: Optional[int] = None,
    count_reference: Optional[str] = None,
    admin_id: int,
) -> Dict[str, Any]:
    """Batch update inventory for cycle counting.

    Args:
        db: Database session
        items: List of dicts with product_id, counted_quantity, reason
        location_id: Location to count (defaults to first warehouse)
        count_reference: Human-readable count reference
        admin_id: ID of the admin user performing the count

    Returns:
        Dict with total_items, successful, failed, results, count_reference
    """
    results = []
    successful = 0
    failed = 0

    if location_id:
        location = db.query(InventoryLocation).filter(
            InventoryLocation.id == location_id
        ).first()
        if not location:
            raise ValueError(f"Location {location_id} not found")
    else:
        location = _get_or_create_default_location(db)

    count_ref = count_reference or f"Cycle Count {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"
    txn_service = TransactionService(db)

    for item in items:
        product_id = item["product_id"]
        counted_quantity = item["counted_quantity"]
        reason = item["reason"]
        product = None
        previous_qty = Decimal(0)

        try:
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product:
                results.append({
                    "product_id": product_id,
                    "product_sku": "UNKNOWN",
                    "product_name": "Unknown Product",
                    "previous_quantity": Decimal(0),
                    "counted_quantity": counted_quantity,
                    "variance": Decimal(0),
                    "transaction_id": None,
                    "journal_entry_id": None,
                    "success": False,
                    "error": f"Product {product_id} not found",
                })
                failed += 1
                continue

            inventory = _get_or_create_inventory(db, product_id, location.id)
            previous_qty = Decimal(str(inventory.on_hand_quantity))
            variance = counted_quantity - previous_qty

            if variance == 0:
                results.append({
                    "product_id": product_id,
                    "product_sku": product.sku,
                    "product_name": product.name,
                    "previous_quantity": previous_qty,
                    "counted_quantity": counted_quantity,
                    "variance": Decimal(0),
                    "transaction_id": None,
                    "journal_entry_id": None,
                    "success": True,
                    "error": None,
                })
                successful += 1
                continue

            full_reason = f"{count_ref}: {reason}"
            inv_txn, journal_entry = txn_service.cycle_count_adjustment(
                product_id=product_id,
                expected_qty=previous_qty,
                actual_qty=counted_quantity,
                reason=full_reason,
                location_id=location.id,
                user_id=admin_id,
            )

            inventory.last_counted = datetime.now(timezone.utc)
            db.flush()

            results.append({
                "product_id": product_id,
                "product_sku": product.sku,
                "product_name": product.name,
                "previous_quantity": previous_qty,
                "counted_quantity": counted_quantity,
                "variance": variance,
                "transaction_id": inv_txn.id,
                "journal_entry_id": journal_entry.id,
                "success": True,
                "error": None,
            })
            successful += 1

        except ValueError as e:
            logger.error(f"Accounting error for batch item {product_id}: {e}")
            results.append({
                "product_id": product_id,
                "product_sku": product.sku if product else "ERROR",
                "product_name": product.name if product else "Error",
                "previous_quantity": previous_qty,
                "counted_quantity": counted_quantity,
                "variance": Decimal(0),
                "transaction_id": None,
                "journal_entry_id": None,
                "success": False,
                "error": "Accounting validation failed. Check GL account configuration.",
            })
            failed += 1
        except Exception as e:
            logger.error(f"Error processing batch item {product_id}: {e}")
            results.append({
                "product_id": product_id,
                "product_sku": product.sku if product else "ERROR",
                "product_name": product.name if product else "Error",
                "previous_quantity": Decimal(0),
                "counted_quantity": counted_quantity,
                "variance": Decimal(0),
                "transaction_id": None,
                "journal_entry_id": None,
                "success": False,
                "error": "Internal processing error. Check server logs for details.",
            })
            failed += 1

    db.commit()

    return {
        "total_items": len(items),
        "successful": successful,
        "failed": failed,
        "results": results,
        "count_reference": count_ref,
    }
