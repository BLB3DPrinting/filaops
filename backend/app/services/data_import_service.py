"""
Data Import Service

Handles CSV imports for products and inventory records.
Business logic extracted from ``admin/data_import.py``.
"""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.inventory import Inventory, InventoryLocation
from app.models.product import Product


# ============================================================================
# COLUMN NAME VARIATIONS
# ============================================================================

SKU_COLS = ["SKU", "sku", "Product SKU", "product_sku", "Item SKU"]
QTY_COLS = ["Quantity", "quantity", "Qty", "qty", "QTY", "On Hand", "on_hand"]
LOC_COLS = ["Location", "location", "Warehouse", "warehouse", "Location Code"]
LOT_COLS = ["Lot Number", "lot_number", "Lot", "lot", "Lot #"]
MODE_COLS = ["Mode", "mode", "Action", "action"]


def _find_col(row: dict, candidates: list) -> str:
    """Return first non-empty matching column value."""
    for col in candidates:
        val = row.get(col, "").strip()
        if val:
            return val
    return ""


# ============================================================================
# PRODUCT IMPORT
# ============================================================================

def import_products(db: Session, csv_text: str) -> Dict[str, Any]:
    """Import products from CSV text.

    Creates new products or updates existing ones matched by SKU.

    Returns:
        Dict with created, updated, errors, total_processed counts.
    """
    reader = csv.DictReader(io.StringIO(csv_text))

    created = 0
    updated = 0
    errors: List[str] = []

    for row_num, row in enumerate(reader, start=2):
        try:
            sku = row.get("SKU", "").strip()
            if not sku:
                errors.append(f"Row {row_num}: Missing SKU")
                continue

            product = db.query(Product).filter(Product.sku == sku).first()

            if product:
                product.name = row.get("Name", product.name)
                product.description = row.get("Description", product.description)
                product.item_type = row.get("Item Type", product.item_type)
                product.procurement_type = row.get("Procurement Type", product.procurement_type)
                product.unit = row.get("Unit", product.unit)
                if row.get("Standard Cost"):
                    product.standard_cost = float(row.get("Standard Cost"))
                if row.get("Selling Price"):
                    product.selling_price = float(row.get("Selling Price"))
                if row.get("Reorder Point"):
                    product.reorder_point = float(row.get("Reorder Point"))
                product.updated_at = datetime.now(timezone.utc)
                updated += 1
            else:
                now = datetime.now(timezone.utc)
                product = Product(
                    sku=sku,
                    name=row.get("Name", ""),
                    description=row.get("Description"),
                    item_type=row.get("Item Type", "finished_good"),
                    procurement_type=row.get("Procurement Type", "buy"),
                    unit=row.get("Unit", "EA"),
                    standard_cost=float(row.get("Standard Cost", 0)) if row.get("Standard Cost") else None,
                    selling_price=float(row.get("Selling Price", 0)) if row.get("Selling Price") else None,
                    reorder_point=float(row.get("Reorder Point", 0)) if row.get("Reorder Point") else None,
                    active=row.get("Active", "true").lower() == "true",
                    created_at=now,
                    updated_at=now,
                )
                db.add(product)
                created += 1

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Database error: {str(e)}")

    return {"created": created, "updated": updated, "errors": errors, "total_processed": created + updated}


# ============================================================================
# INVENTORY IMPORT
# ============================================================================

def import_inventory(db: Session, csv_text: str) -> Dict[str, Any]:
    """Import inventory from CSV text.

    Supports ``set`` (replace) and ``add`` modes per row.

    Returns:
        Dict with created, updated, errors, total_processed counts.
    """
    reader = csv.DictReader(io.StringIO(csv_text))

    created = 0
    updated = 0
    errors: List[str] = []

    # Get or create default location
    default_location = db.query(InventoryLocation).filter(InventoryLocation.code == "MAIN").first()
    if not default_location:
        default_location = InventoryLocation(
            code="MAIN", name="Main Warehouse", type="warehouse", active=True
        )
        db.add(default_location)
        db.flush()

    for row_num, row in enumerate(reader, start=2):
        try:
            sku = _find_col(row, SKU_COLS)
            if not sku:
                errors.append(f"Row {row_num}: Missing SKU")
                continue

            product = db.query(Product).filter(Product.sku == sku).first()
            if not product:
                errors.append(f"Row {row_num}: Product with SKU '{sku}' not found")
                continue

            # Parse quantity
            quantity: Optional[Decimal] = None
            quantity_error = False
            for col in QTY_COLS:
                raw = row.get(col, "").strip()
                if raw:
                    try:
                        quantity = Decimal(raw)
                    except InvalidOperation:
                        errors.append(f"Row {row_num}: Invalid quantity")
                        quantity_error = True
                    break

            if quantity_error:
                continue
            if quantity is None:
                errors.append(f"Row {row_num}: Missing quantity")
                continue

            # Location
            location_code = _find_col(row, LOC_COLS) or "MAIN"
            location = db.query(InventoryLocation).filter(InventoryLocation.code == location_code).first()
            if not location:
                location = default_location

            # Lot number (placeholder for future lot tracking)
            _lot_number = _find_col(row, LOT_COLS)  # noqa: F841

            # Mode
            mode_val = _find_col(row, MODE_COLS).lower()
            mode = mode_val if mode_val in ("add", "set") else "set"

            # Find or create inventory record
            inventory = db.query(Inventory).filter(
                Inventory.product_id == product.id,
                Inventory.location_id == location.id,
            ).first()

            if inventory:
                if mode == "add":
                    inventory.on_hand_quantity = (inventory.on_hand_quantity or Decimal("0")) + quantity
                else:
                    inventory.on_hand_quantity = quantity
                inventory.updated_at = datetime.now(timezone.utc)
                updated += 1
            else:
                inventory = Inventory(
                    product_id=product.id,
                    location_id=location.id,
                    on_hand_quantity=quantity,
                    allocated_quantity=Decimal("0"),
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(inventory)
                created += 1

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        errors.append(f"Database error: {str(e)}")

    return {"created": created, "updated": updated, "errors": errors, "total_processed": created + updated}
