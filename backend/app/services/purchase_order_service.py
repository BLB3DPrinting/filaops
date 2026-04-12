"""
Purchase Order Service — CRUD, status management, receiving, and events.

Extracted from purchase_orders.py (ARCHITECT-003).
"""
import io
import os
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import desc, extract
from sqlalchemy import func as sql_func
from sqlalchemy.orm import Session, joinedload, selectinload

from app.logging_config import get_logger
from app.core.utils import get_or_404
from app.models.vendor import Vendor
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product
from app.models.company_settings import CompanySettings
from app.models.inventory import Inventory, InventoryLocation
from app.models.material_spool import MaterialSpool
from app.models.traceability import MaterialLot
from app.services.uom_service import convert_quantity_safe, get_conversion_factor
from app.services.inventory_helpers import is_material
from app.services.transaction_service import TransactionService, ReceiptItem
from app.services.event_service import record_purchasing_event

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_po_number(db: Session) -> str:
    """Generate next PO number (PO-2025-001, PO-2025-002, etc.)"""
    year = datetime.now(timezone.utc).year
    pattern = f"PO-{year}-%"
    last = db.query(PurchaseOrder).filter(
        PurchaseOrder.po_number.like(pattern)
    ).order_by(desc(PurchaseOrder.po_number)).first()

    if last:
        try:
            num = int(last.po_number.split("-")[2])
            return f"PO-{year}-{num + 1:03d}"
        except (IndexError, ValueError):
            pass
    return f"PO-{year}-001"


def calculate_totals(po: PurchaseOrder) -> None:
    """Recalculate PO totals from lines."""
    subtotal = sum(line.line_total for line in po.lines) if po.lines else Decimal("0")
    po.subtotal = subtotal
    po.total_amount = subtotal + (po.tax_amount or Decimal("0")) + (po.shipping_cost or Decimal("0"))


# ---------------------------------------------------------------------------
# PO CRUD
# ---------------------------------------------------------------------------

def list_purchase_orders(
    db: Session,
    *,
    status: str | None = None,
    vendor_id: int | None = None,
    search: str | None = None,
    offset: int = 0,
    limit: int = 50,
) -> tuple[list[PurchaseOrder], int]:
    """List purchase orders with filters. Returns (pos, total_count)."""
    query = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.vendor),
        selectinload(PurchaseOrder.lines),  # Eager load lines for list item building
    )

    if status:
        query = query.filter(PurchaseOrder.status == status)
    if vendor_id:
        query = query.filter(PurchaseOrder.vendor_id == vendor_id)
    if search:
        query = query.filter(PurchaseOrder.po_number.ilike(f"%{search}%"))

    total = query.count()
    pos = query.order_by(desc(PurchaseOrder.created_at)).offset(offset).limit(limit).all()
    return pos, total


def get_purchase_order(db: Session, po_id: int) -> PurchaseOrder:
    """Get a PO with vendor and lines+products loaded, or raise 404."""
    po = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.vendor),
        joinedload(PurchaseOrder.lines).joinedload(PurchaseOrderLine.product),
    ).filter(PurchaseOrder.id == po_id).first()

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return po


def create_purchase_order(
    db: Session,
    *,
    data: dict,
    lines_data: list[dict],
    created_by: str,
    user_id: int,
) -> PurchaseOrder:
    """Create a new PO with lines."""
    vendor = db.query(Vendor).filter(Vendor.id == data["vendor_id"]).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor not found")

    po_number = generate_po_number(db)

    # Validate all line products BEFORE creating the PO to avoid orphaned records
    line_products = {}
    for line_data in lines_data:
        product = db.query(Product).filter(Product.id == line_data["product_id"]).first()
        if not product:
            raise HTTPException(
                status_code=404, detail=f"Product ID {line_data['product_id']} not found"
            )
        line_products[line_data["product_id"]] = product

    po = PurchaseOrder(
        po_number=po_number,
        vendor_id=data["vendor_id"],
        status="draft",
        order_date=data.get("order_date"),
        expected_date=data.get("expected_date"),
        tracking_number=data.get("tracking_number"),
        carrier=data.get("carrier"),
        tax_amount=data.get("tax_amount"),
        shipping_cost=data.get("shipping_cost"),
        payment_method=data.get("payment_method"),
        payment_reference=data.get("payment_reference"),
        document_url=data.get("document_url"),
        notes=data.get("notes"),
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(po)
    db.flush()

    for i, line_data in enumerate(lines_data, start=1):
        product = line_products[line_data["product_id"]]

        line = PurchaseOrderLine(
            line_number=i,
            product_id=line_data["product_id"],
            quantity_ordered=line_data["quantity_ordered"],
            quantity_received=Decimal("0"),
            purchase_unit=(
                line_data.get("purchase_unit")
                or getattr(product, "purchase_uom", None)
                or product.unit
            ),
            unit_cost=line_data["unit_cost"],
            line_total=line_data["quantity_ordered"] * line_data["unit_cost"],
            notes=line_data.get("notes"),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        po.lines.append(line)  # cascade="all" handles db.add

    calculate_totals(po)

    record_purchasing_event(
        db=db,
        purchase_order_id=po.id,
        event_type="created",
        title="Purchase Order Created",
        description=f"Created for vendor {vendor.name}",
        new_value="draft",
        user_id=user_id,
    )

    db.commit()
    db.refresh(po)

    logger.info(f"Created PO {po.po_number} for vendor {vendor.name}")
    return po


def update_purchase_order(db: Session, po_id: int, *, data: dict) -> PurchaseOrder:
    """Update a purchase order (draft/ordered only)."""
    po = get_or_404(db, PurchaseOrder, po_id, "Purchase order not found")

    if po.status in ["received", "closed", "cancelled"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot update PO in '{po.status}' status"
        )

    for field, value in data.items():
        setattr(po, field, value)

    if any(f in data for f in ["tax_amount", "shipping_cost"]):
        calculate_totals(po)

    po.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(po)

    logger.info(f"Updated PO {po.po_number}")
    return po


def delete_purchase_order(db: Session, po_id: int) -> dict:
    """Delete a draft PO."""
    po = get_or_404(db, PurchaseOrder, po_id, "Purchase order not found")

    if po.status != "draft":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete PO in '{po.status}' status. Cancel it instead.",
        )

    db.delete(po)
    db.commit()

    logger.info(f"Deleted PO {po.po_number}")
    return {"message": f"Purchase order {po.po_number} deleted"}


# ---------------------------------------------------------------------------
# Line Management
# ---------------------------------------------------------------------------

def add_po_line(
    db: Session, po_id: int, *, data: dict
) -> PurchaseOrder:
    """Add a line to a PO. Returns the refreshed PO."""
    po = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.lines)
    ).filter(PurchaseOrder.id == po_id).first()

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    if po.status not in ["draft", "ordered"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot add lines to PO in '{po.status}' status"
        )

    product = db.query(Product).filter(Product.id == data["product_id"]).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    next_line = max([line.line_number for line in po.lines], default=0) + 1

    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        line_number=next_line,
        product_id=data["product_id"],
        quantity_ordered=data["quantity_ordered"],
        quantity_received=Decimal("0"),
        purchase_unit=(
            data.get("purchase_unit")
            or getattr(product, "purchase_uom", None)
            or product.unit
        ),
        unit_cost=data["unit_cost"],
        line_total=data["quantity_ordered"] * data["unit_cost"],
        notes=data.get("notes"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(line)
    po.lines.append(line)
    calculate_totals(po)
    po.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(po)
    return po


def update_po_line(
    db: Session, po_id: int, line_id: int, *, data: dict
) -> PurchaseOrder:
    """Update a PO line. Returns the refreshed PO."""
    po = get_or_404(db, PurchaseOrder, po_id, "Purchase order not found")

    if po.status not in ["draft", "ordered"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot modify PO in '{po.status}' status"
        )

    line = db.query(PurchaseOrderLine).filter(
        PurchaseOrderLine.id == line_id,
        PurchaseOrderLine.purchase_order_id == po_id,
    ).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")

    if "quantity_ordered" in data and data["quantity_ordered"] is not None:
        if data["quantity_ordered"] < line.quantity_received:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reduce quantity below received amount ({line.quantity_received})",
            )
        line.quantity_ordered = data["quantity_ordered"]

    if "unit_cost" in data and data["unit_cost"] is not None:
        line.unit_cost = data["unit_cost"]

    if "notes" in data and data["notes"] is not None:
        line.notes = data["notes"]

    line.line_total = line.quantity_ordered * line.unit_cost
    line.updated_at = datetime.now(timezone.utc)

    calculate_totals(po)
    po.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(po)

    logger.info(f"Updated line {line_id} on PO {po.po_number}")
    return po


def delete_po_line(db: Session, po_id: int, line_id: int) -> dict:
    """Remove a line from a PO."""
    po = get_or_404(db, PurchaseOrder, po_id, "Purchase order not found")

    if po.status not in ["draft", "ordered"]:
        raise HTTPException(
            status_code=400, detail=f"Cannot modify PO in '{po.status}' status"
        )

    line = db.query(PurchaseOrderLine).filter(
        PurchaseOrderLine.id == line_id,
        PurchaseOrderLine.purchase_order_id == po_id,
    ).first()
    if not line:
        raise HTTPException(status_code=404, detail="Line not found")

    if line.quantity_received > 0:
        raise HTTPException(
            status_code=400, detail="Cannot delete line with received quantity"
        )

    db.delete(line)
    calculate_totals(po)
    po.updated_at = datetime.now(timezone.utc)

    db.commit()
    return {"message": "Line deleted"}


# ---------------------------------------------------------------------------
# Status Management
# ---------------------------------------------------------------------------

VALID_TRANSITIONS = {
    "draft": ["ordered", "cancelled"],
    "ordered": ["shipped", "received", "cancelled"],
    "shipped": ["received", "cancelled"],
    "received": ["closed", "cancelled"],
    "closed": [],
    "cancelled": [],
}

STATUS_TITLES = {
    "ordered": "Order Placed",
    "shipped": "Marked as Shipped",
    "received": "Marked as Received",
    "closed": "Order Closed",
    "cancelled": "Order Cancelled",
}


def update_po_status(
    db: Session,
    po_id: int,
    *,
    new_status: str,
    tracking_number: str | None = None,
    carrier: str | None = None,
    user_id: int,
) -> PurchaseOrder:
    """Update PO status with transition validation."""
    po = get_or_404(db, PurchaseOrder, po_id, "Purchase order not found")
    old_status = po.status

    if new_status not in VALID_TRANSITIONS.get(old_status, []):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{old_status}' to '{new_status}'",
        )

    if new_status == "ordered":
        if not po.lines:
            raise HTTPException(status_code=400, detail="Cannot order a PO with no lines")
        po.order_date = po.order_date or date.today()
    elif new_status == "shipped":
        po.shipped_date = date.today()
        if tracking_number:
            po.tracking_number = tracking_number
        if carrier:
            po.carrier = carrier
    elif new_status == "received":
        po.received_date = date.today()

    po.status = new_status
    po.updated_at = datetime.now(timezone.utc)

    description = None
    if new_status == "shipped" and tracking_number:
        description = f"Tracking: {tracking_number}"
        if carrier:
            description += f" ({carrier})"

    record_purchasing_event(
        db=db,
        purchase_order_id=po.id,
        event_type="status_change",
        title=STATUS_TITLES.get(new_status, f"Status changed to {new_status}"),
        description=description,
        old_value=old_status,
        new_value=new_status,
        user_id=user_id,
    )

    db.commit()
    db.refresh(po)

    logger.info(f"PO {po.po_number} status: {old_status} -> {new_status}")
    return po


# ---------------------------------------------------------------------------
# Receiving
# ---------------------------------------------------------------------------

def receive_purchase_order(
    db: Session,
    po_id: int,
    *,
    lines: list[dict],
    location_id: int | None = None,
    received_date: date | None = None,
    user_id: int,
    user_email: str,
) -> dict:
    """
    Receive items from a purchase order.

    Returns dict with keys:
        po_number, lines_received, total_quantity, inventory_updated,
        transactions_created, spools_created, material_lots_created
    """
    po = db.query(PurchaseOrder).options(
        joinedload(PurchaseOrder.lines)
    ).filter(PurchaseOrder.id == po_id).first()

    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")

    if po.status not in ["ordered", "shipped"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot receive items on PO in '{po.status}' status",
        )

    actual_received_date = received_date or date.today()

    # Default location
    if not location_id:
        default_loc = db.query(InventoryLocation).filter(
            InventoryLocation.type == "warehouse"
        ).first()
        if default_loc:
            location_id = default_loc.id
        else:
            default_loc = InventoryLocation(
                name="Main Warehouse", code="MAIN", type="warehouse", active=True
            )
            db.add(default_loc)
            db.flush()
            location_id = default_loc.id

    line_map = {line.id: line for line in po.lines}

    transaction_ids = []
    spools_created = []
    material_lots_created = []
    total_received = Decimal("0")
    lines_received = 0
    receipt_items_for_service = []

    # Track cumulative per-product receipt quantities/costs within this batch
    # to avoid weighted average drift when the same product appears multiple times
    product_receipt_accum: dict[int, dict] = {}  # product_id -> {qty, cost_sum}

    for item in lines:
        line_id = item["line_id"]
        if line_id not in line_map:
            raise HTTPException(
                status_code=404, detail=f"Line {line_id} not found on this PO"
            )

        line = line_map[line_id]
        remaining = line.quantity_ordered - line.quantity_received
        qty_received = item["quantity_received"]

        if qty_received > remaining:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot receive {qty_received} for line {line_id}. "
                    f"Only {remaining} remaining."
                ),
            )

        line.quantity_received = line.quantity_received + qty_received
        line.updated_at = datetime.now(timezone.utc)
        total_received += qty_received
        lines_received += 1

        product = db.query(Product).filter(Product.id == line.product_id).first()
        if not product:
            raise HTTPException(
                status_code=404, detail=f"Product {line.product_id} not found"
            )

        purchase_unit = (line.purchase_unit or product.unit or "EA").upper().strip()
        product_unit = (product.unit or "EA").upper().strip()
        is_mat = is_material(product)

        quantity_received_decimal = Decimal(str(qty_received))
        quantity_for_inventory = quantity_received_decimal
        cost_per_unit_for_inventory = line.unit_cost
        # Track whether we fell back to purchase_unit due to incompatible product unit.
        # Used below so the inventory transaction is labeled with the correct unit.
        effective_unit = product_unit

        if purchase_unit != product_unit:
            logger.info(
                f"Converting quantity for PO {po.po_number} line {line.line_number}: "
                f"{quantity_received_decimal} {purchase_unit} -> {product_unit}"
            )

            converted_qty, conversion_success = convert_quantity_safe(
                db, quantity_received_decimal, purchase_unit, product_unit
            )

            if not conversion_success:
                if is_mat:
                    # Materials MUST convert — mass-based cost math requires it.
                    logger.error(
                        f"UOM conversion FAILED for PO {po.po_number} line {line.line_number}. "
                        f"Purchase unit: '{purchase_unit}', Product unit: '{product_unit}', "
                        f"Quantity received: {quantity_received_decimal}. "
                        f"Cannot convert incompatible units - this will cause incorrect inventory!"
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Cannot convert {quantity_received_decimal} {purchase_unit} to {product_unit} "
                            f"for product {product.sku}. "
                            f"Units are incompatible. Supported conversions: G↔KG, LB↔KG, OZ↔KG, etc."
                        ),
                    )
                else:
                    # Non-material items (supplies, maintenance parts, etc.): receive as-is
                    # in the purchase unit. No cost normalisation needed — cost is already
                    # per-purchase-unit (e.g. $/M of PTFE tubing purchased in metres).
                    logger.warning(
                        f"UOM conversion not available for PO {po.po_number} line {line.line_number}: "
                        f"'{purchase_unit}' → '{product_unit}' (product: {product.sku}). "
                        f"Non-material item — receiving quantity as-is in {purchase_unit}."
                    )
                    effective_unit = purchase_unit  # record inventory in purchase unit
                    # Skip quantity_for_inventory update — keep original quantity as-is.
                    # Skip to cost section; no cost conversion needed either.
            else:
                quantity_for_inventory = converted_qty
                logger.info(
                    f"Conversion successful: {quantity_received_decimal} {purchase_unit} "
                    f"= {quantity_for_inventory} {product_unit}"
                )

            # Convert cost_per_unit
            if is_mat:
                if purchase_unit == "KG":
                    cost_per_unit_for_inventory = line.unit_cost / Decimal("1000")
                    logger.info(
                        f"Material cost conversion: ${line.unit_cost}/KG → "
                        f"${cost_per_unit_for_inventory}/G"
                    )
                else:
                    try:
                        quantity_conversion_factor = get_conversion_factor(
                            db, purchase_unit, "G"
                        )
                        cost_conversion_factor = Decimal("1") / quantity_conversion_factor
                        cost_per_unit_for_inventory = (
                            line.unit_cost * cost_conversion_factor
                        )
                        logger.info(
                            f"Material cost conversion: ${line.unit_cost}/{purchase_unit} → "
                            f"${cost_per_unit_for_inventory}/G (factor: {cost_conversion_factor})"
                        )
                    except Exception as e:
                        logger.error(f"Cost conversion failed for material: {e}")
                        raise HTTPException(
                            status_code=400,
                            detail=f"Cannot convert cost from {purchase_unit} to G",
                        )
            else:
                try:
                    quantity_conversion_factor = get_conversion_factor(
                        db, purchase_unit, product_unit
                    )
                    logger.info(
                        f"Cost conversion: quantity_factor={quantity_conversion_factor} "
                        f"(from {purchase_unit} to {product_unit})"
                    )
                    cost_conversion_factor = Decimal("1") / quantity_conversion_factor
                    cost_per_unit_for_inventory = line.unit_cost * cost_conversion_factor
                    logger.info(
                        f"Cost conversion: cost_factor={cost_conversion_factor}, "
                        f"unit_cost={line.unit_cost}, result={cost_per_unit_for_inventory}"
                    )
                except Exception as e:
                    qty_recv = Decimal(str(qty_received))
                    if qty_recv > 0 and quantity_for_inventory > 0:
                        quantity_conversion_factor_derived = (
                            quantity_for_inventory / qty_recv
                        )
                        cost_conversion_factor = (
                            Decimal("1") / quantity_conversion_factor_derived
                        )
                        cost_per_unit_for_inventory = (
                            line.unit_cost * cost_conversion_factor
                        )
                        logger.info(
                            f"Cost conversion (fallback): qty_factor={quantity_conversion_factor_derived}, "
                            f"cost_factor={cost_conversion_factor}, unit_cost={line.unit_cost}, "
                            f"result={cost_per_unit_for_inventory}"
                        )
                    else:
                        cost_per_unit_for_inventory = line.unit_cost
                        logger.warning(
                            f"Cost conversion: Cannot derive factor (qty_received={qty_recv}, "
                            f"quantity_for_inventory={quantity_for_inventory}), using original cost"
                        )
                    logger.warning(
                        f"Cost conversion factor lookup failed, using derived factor: {e}"
                    )

            logger.info(
                f"UOM conversion for PO {po.po_number} line {line.line_number}: "
                f"{qty_received} {purchase_unit} @ ${line.unit_cost}/{purchase_unit} -> "
                f"{quantity_for_inventory} {effective_unit} @ ${cost_per_unit_for_inventory}/"
                f"{'G' if is_mat else effective_unit} (material: {is_mat})"
            )

        # Convert to transaction unit (GRAMS for materials, native for others)
        transaction_quantity = quantity_for_inventory
        if is_material(product):
            if product_unit == "KG":
                transaction_quantity = quantity_for_inventory * Decimal("1000")
            elif product_unit == "G":
                transaction_quantity = quantity_for_inventory
            elif product_unit == "LB":
                transaction_quantity = quantity_for_inventory * Decimal("453.592")
            elif product_unit == "OZ":
                transaction_quantity = quantity_for_inventory * Decimal("28.3495")
            else:
                logger.warning(
                    f"Material {product.sku} has unknown unit '{product_unit}', assuming grams"
                )
                transaction_quantity = quantity_for_inventory

            logger.info(
                f"Material conversion for transaction: {quantity_for_inventory} {product_unit} -> "
                f"{transaction_quantity} G (product: {product.sku}, purchased in: {purchase_unit})"
            )

            # Ensure cost is ALWAYS in $/G for materials
            if purchase_unit == product_unit:
                if product_unit == "KG":
                    cost_per_unit_for_inventory = line.unit_cost / Decimal("1000")
                    logger.info(
                        f"Material cost normalization (KG->G): ${line.unit_cost}/KG -> "
                        f"${cost_per_unit_for_inventory}/G"
                    )
                elif product_unit == "LB":
                    cost_per_unit_for_inventory = line.unit_cost / Decimal("453.592")
                    logger.info(
                        f"Material cost normalization (LB->G): ${line.unit_cost}/LB -> "
                        f"${cost_per_unit_for_inventory}/G"
                    )
                elif product_unit == "OZ":
                    cost_per_unit_for_inventory = line.unit_cost / Decimal("28.3495")
                    logger.info(
                        f"Material cost normalization (OZ->G): ${line.unit_cost}/OZ -> "
                        f"${cost_per_unit_for_inventory}/G"
                    )
                elif product_unit == "G":
                    logger.info(
                        f"Material cost already in $/G: ${cost_per_unit_for_inventory}/G"
                    )
                else:
                    logger.warning(
                        f"Material {product.sku} has unknown unit '{product_unit}', "
                        f"cost not normalized. This may cause incorrect COGS calculations!"
                    )

        # Collect for TransactionService
        transaction_unit = "G" if is_mat else effective_unit
        receipt_items_for_service.append(
            ReceiptItem(
                product_id=line.product_id,
                quantity=transaction_quantity,
                unit_cost=cost_per_unit_for_inventory,
                unit=transaction_unit,
                lot_number=item.get("lot_number"),
            )
        )

        # Update product average cost (weighted average)
        # When the same product appears on multiple lines in one receipt, the DB
        # on_hand_quantity doesn't reflect earlier lines yet (no commit between lines).
        # Use product_receipt_accum to track cumulative receipt within this batch.
        #
        # Skip if units are incompatible and we fell back to purchase_unit — the
        # cost is in the purchase unit (e.g. $/M), not in the product unit (e.g.
        # per-EA), so writing it to average_cost/last_cost would corrupt costing.
        if product and effective_unit == product_unit:
            pid = product.id

            if pid not in product_receipt_accum:
                # First time seeing this product in this receipt — read DB baseline
                total_on_hand = db.query(
                    sql_func.coalesce(sql_func.sum(Inventory.on_hand_quantity), 0)
                ).filter(Inventory.product_id == product.id).scalar()

                product_receipt_accum[pid] = {
                    "base_qty": Decimal(str(total_on_hand)),
                    "base_cost": Decimal(str(product.average_cost or 0)),
                    "receipt_qty": Decimal("0"),
                    "receipt_cost_total": Decimal("0"),
                }

            accum = product_receipt_accum[pid]
            accum["receipt_qty"] += transaction_quantity
            accum["receipt_cost_total"] += transaction_quantity * cost_per_unit_for_inventory

            old_qty = accum["base_qty"]
            old_cost = accum["base_cost"]
            total_new_qty = accum["receipt_qty"]
            total_qty = old_qty + total_new_qty

            if total_qty > 0:
                weighted_avg = (
                    old_qty * old_cost + accum["receipt_cost_total"]
                ) / total_qty
                product.average_cost = float(
                    weighted_avg.quantize(Decimal("0.0001"))
                )
                logger.debug(
                    f"Weighted avg for {product.sku}: "
                    f"({old_qty}×${old_cost} + batch_cost ${accum['receipt_cost_total']}) "
                    f"/ {total_qty} = ${product.average_cost}"
                )
            elif total_new_qty > 0:
                product.average_cost = float(cost_per_unit_for_inventory)

            product.last_cost = float(cost_per_unit_for_inventory)
            product.last_cost_date = datetime.now(timezone.utc)
            product.updated_at = datetime.now(timezone.utc)

        # MaterialLot creation (traceability)
        if product.item_type in ("supply", "component", "material") or product.material_type_id:
            year = datetime.now(timezone.utc).year
            existing_count = db.query(MaterialLot).filter(
                MaterialLot.product_id == product.id,
                extract("year", MaterialLot.received_date) == year,
            ).count()

            lot_number = f"{product.sku}-{year}-{existing_count + 1:04d}"

            location = (
                db.query(InventoryLocation)
                .filter(InventoryLocation.id == location_id)
                .first()
                if location_id
                else None
            )

            material_lot = MaterialLot(
                lot_number=lot_number,
                product_id=product.id,
                vendor_id=po.vendor_id,
                purchase_order_id=po.id,
                vendor_lot_number=item.get("vendor_lot_number") or item.get("lot_number"),
                quantity_received=transaction_quantity,
                quantity_consumed=Decimal("0"),
                quantity_scrapped=Decimal("0"),
                quantity_adjusted=Decimal("0"),
                status="active",
                inspection_status="pending",
                received_date=actual_received_date,
                unit_cost=cost_per_unit_for_inventory,
                location=location.code if location else "MAIN",
            )
            db.add(material_lot)
            db.flush()
            material_lots_created.append(lot_number)

            logger.info(
                f"Created MaterialLot {lot_number} for {product.sku}: "
                f"{transaction_quantity} units @ ${cost_per_unit_for_inventory}/unit "
                f"(vendor lot: {material_lot.vendor_lot_number or 'N/A'})"
            )

        # Spool creation
        create_spools = item.get("create_spools", False)
        spools_data = item.get("spools", [])
        if create_spools and spools_data:
            if product.item_type not in ("supply", "material") or not product.material_type_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Spool creation only available for material products with material_type. "
                        f"{product.sku} is type '{product.item_type}'"
                    ),
                )

            received_qty_g = quantity_for_inventory
            product_unit_upper = (product.unit or "EA").upper().strip()

            if product_unit_upper == "KG":
                received_qty_g = quantity_for_inventory * Decimal("1000")
            elif product_unit_upper == "LB":
                received_qty_g = quantity_for_inventory * Decimal("453.59237")
            elif product_unit_upper == "OZ":
                received_qty_g = quantity_for_inventory * Decimal("28.34952")
            elif product_unit_upper != "G":
                logger.warning(
                    f"Material product {product.sku} has unexpected unit: {product.unit}, assuming grams"
                )

            spool_weight_sum_g = sum(
                Decimal(str(s["weight_g"])) for s in spools_data
            )
            tolerance = Decimal("0.1")

            if abs(spool_weight_sum_g - received_qty_g) > tolerance:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Spool weights sum ({spool_weight_sum_g}g) must equal "
                        f"received quantity ({received_qty_g}g) for product {product.sku}. "
                        f"Difference: {abs(spool_weight_sum_g - received_qty_g):.2f}g"
                    ),
                )

            for idx, spool_data in enumerate(spools_data, start=1):
                spool_number = (
                    spool_data.get("spool_number")
                    or f"{po.po_number}-L{line.line_number}-{idx:03d}"
                )

                existing = db.query(MaterialSpool).filter(
                    MaterialSpool.spool_number == spool_number
                ).first()
                if existing:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Spool number '{spool_number}' already exists",
                    )

                # Note: *_weight_kg columns actually store grams (legacy naming)
                # This is consistent with how all MaterialSpool code treats these fields
                spool = MaterialSpool(
                    spool_number=spool_number,
                    product_id=line.product_id,
                    initial_weight_kg=spool_data["weight_g"],
                    current_weight_kg=spool_data["weight_g"],
                    status="active",
                    location_id=location_id,
                    supplier_lot_number=(
                        spool_data.get("supplier_lot_number") or item.get("lot_number")
                    ),
                    expiry_date=spool_data.get("expiry_date"),
                    notes=spool_data.get("notes"),
                    received_date=datetime.combine(
                        actual_received_date, datetime.min.time()
                    ),
                    created_by=user_email,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                db.add(spool)
                db.flush()
                spools_created.append(spool_number)

                logger.info(
                    f"Created spool {spool_number} for {product.sku}: {spool_data['weight_g']}g "
                    f"(lot: {spool.supplier_lot_number or 'N/A'})"
                )

    # PO receipt via TransactionService
    if receipt_items_for_service:
        txn_service = TransactionService(db)
        inv_txns, journal_entry = txn_service.receive_purchase_order(
            purchase_order_id=po.id,
            items=receipt_items_for_service,
            user_id=user_id,
        )
        transaction_ids = [txn.id for txn in inv_txns]

    # Check if fully received
    all_received = all(
        line.quantity_received >= line.quantity_ordered for line in po.lines
    )

    if all_received:
        po.status = "received"
        po.received_date = actual_received_date

    po.updated_at = datetime.now(timezone.utc)

    # Record receipt event
    event_type = "receipt" if all_received else "partial_receipt"
    event_title = "Items Received" if all_received else "Partial Receipt"
    event_description = (
        f"Received {total_received} units across {lines_received} line(s)"
    )
    if spools_created:
        event_description += f". Created {len(spools_created)} spool(s)."
    if material_lots_created:
        event_description += (
            f" Created {len(material_lots_created)} material lot(s) for traceability."
        )

    record_purchasing_event(
        db=db,
        purchase_order_id=po.id,
        event_type=event_type,
        title=event_title,
        description=event_description,
        event_date=actual_received_date,
        user_id=user_id,
        metadata_key="quantity_received",
        metadata_value=str(total_received),
    )

    if all_received:
        record_purchasing_event(
            db=db,
            purchase_order_id=po.id,
            event_type="status_change",
            title="Fully Received",
            description="All items received - PO status updated",
            old_value="ordered",
            new_value="received",
            event_date=actual_received_date,
            user_id=user_id,
        )

    db.commit()

    logger.info(f"Received {total_received} items on PO {po.po_number}")

    return {
        "po_number": po.po_number,
        "lines_received": lines_received,
        "total_quantity": total_received,
        "inventory_updated": True,
        "transactions_created": transaction_ids,
        "spools_created": spools_created,
        "material_lots_created": material_lots_created,
    }


# ---------------------------------------------------------------------------
# File Upload
# ---------------------------------------------------------------------------

def upload_po_document(
    db: Session,
    po_id: int,
    *,
    file_content: bytes,
    filename: str,
    content_type: str,
) -> dict:
    """Upload a document for a PO. Returns upload result dict."""
    po = get_or_404(db, PurchaseOrder, po_id, "Purchase order not found")

    # Limit file size to 10MB
    max_size_bytes = 10 * 1024 * 1024
    if len(file_content) > max_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {max_size_bytes // (1024*1024)}MB",
        )

    allowed_types = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/csv",
    ]

    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{content_type}' not allowed. Allowed: PDF, JPEG, PNG, XLSX, CSV",
        )

    ext = os.path.splitext(filename or "document")[1] or ".pdf"
    safe_filename = (
        f"{po.po_number}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}{ext}"
    )

    upload_dir = os.path.join("uploads", "purchase_orders")
    os.makedirs(upload_dir, exist_ok=True)

    local_path = os.path.join(upload_dir, safe_filename)
    with open(local_path, "wb") as f:
        f.write(file_content)

    po.document_url = f"/uploads/purchase_orders/{safe_filename}"
    po.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(f"Saved PO document locally: {local_path}")

    return {
        "success": True,
        "storage": "local",
        "url": po.document_url,
        "filename": safe_filename,
    }


# ---------------------------------------------------------------------------
# Event Timeline
# ---------------------------------------------------------------------------

def list_po_events(
    db: Session,
    po_id: int,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list, int]:
    """List purchasing events for a PO. Returns (events, total_count)."""
    from app.models.purchasing_event import PurchasingEvent

    get_or_404(db, PurchaseOrder, po_id, "Purchase order not found")

    query = db.query(PurchasingEvent).options(
        joinedload(PurchasingEvent.user)  # Eager load user for response building
    ).filter(
        PurchasingEvent.purchase_order_id == po_id
    ).order_by(desc(PurchasingEvent.created_at))

    total = query.count()
    events = query.offset(offset).limit(limit).all()
    return events, total


def add_po_event(
    db: Session,
    po_id: int,
    *,
    event_type: str,
    title: str,
    description: str | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    event_date: date | None = None,
    metadata_key: str | None = None,
    metadata_value: str | None = None,
    user_id: int,
) -> object:
    """Add a manual event to a PO. Returns the created event."""
    get_or_404(db, PurchaseOrder, po_id, "Purchase order not found")

    event = record_purchasing_event(
        db=db,
        purchase_order_id=po_id,
        event_type=event_type,
        title=title,
        description=description,
        old_value=old_value,
        new_value=new_value,
        event_date=event_date,
        user_id=user_id,
        metadata_key=metadata_key,
        metadata_value=metadata_value,
    )
    db.commit()
    db.refresh(event)

    logger.info(f"Added event '{event_type}' to PO {po_id}")
    return event


# ---------------------------------------------------------------------------
# PDF Generation
# ---------------------------------------------------------------------------

def generate_po_pdf(
    db: Session,
    po_id: int,
    po: Optional[PurchaseOrder] = None,
) -> io.BytesIO:
    """Generate a professional Purchase Order PDF using ReportLab.

    Layout mirrors generate_invoice_pdf(): branded header, HR separator,
    two-column Vendor / PO Details block, line-items table with alternating
    rows, totals block, and notes footer.

    Callers that already hold the PurchaseOrder can pass it in via `po=`
    to avoid a redundant fetch.
    """
    from xml.sax.saxutils import escape as _xml_escape

    def esc(value) -> str:
        return _xml_escape(str(value)) if value else ""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
        HRFlowable, KeepTogether,
    )

    if po is None:
        po = get_purchase_order(db, po_id)

    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()

    # -- Currency formatting --
    _CURRENCY_SYMBOLS = {
        "USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$",
        "GBP": "\u00a3", "EUR": "\u20ac", "CHF": "CHF\u00a0",
        "SEK": "kr\u00a0", "NOK": "kr\u00a0", "DKK": "kr\u00a0",
        "BRL": "R$", "MXN": "MX$", "INR": "\u20b9",
        "JPY": "\u00a5", "CNY": "\u00a5", "KRW": "\u20a9",
        "SGD": "S$", "HKD": "HK$", "ZAR": "R",
    }
    _currency = (settings.currency_code if settings and settings.currency_code else "USD")
    _sym = _CURRENCY_SYMBOLS.get(_currency, f"{_currency}\u00a0")

    def _fmt(amount) -> str:
        value = Decimal(str(amount or "0")).quantize(Decimal("0.01"))
        return f"{_sym}{value:,.2f}"

    # -- Brand colors (matches quote/invoice PDF) --
    BRAND_DARK = colors.HexColor('#0f172a')
    BRAND_ACCENT = colors.HexColor('#2563eb')
    BRAND_BORDER = colors.HexColor('#e2e8f0')
    BRAND_MUTED = colors.HexColor('#64748b')
    ROW_STRIPE = colors.HexColor('#f1f5f9')

    # -- PDF document --
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer, pagesize=letter,
        topMargin=0.4 * inch, bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
    )
    page_width = doc.width

    # -- Styles --
    styles = getSampleStyleSheet()
    s_normal = styles['Normal']

    s_doc_label = ParagraphStyle(
        'POLabel', parent=s_normal,
        fontSize=28, fontName='Helvetica-Bold', textColor=BRAND_DARK, spaceAfter=2,
    )
    s_section = ParagraphStyle(
        'POSection', parent=s_normal,
        fontSize=8, fontName='Helvetica-Bold', textColor=BRAND_MUTED,
        spaceBefore=4, spaceAfter=4,
    )
    s_company_name = ParagraphStyle(
        'POCompany', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
    )
    s_detail = ParagraphStyle(
        'PODetail', parent=s_normal,
        fontSize=9, textColor=BRAND_MUTED, leading=13,
    )
    s_detail_right = ParagraphStyle(
        'PODetailRight', parent=s_detail, alignment=TA_RIGHT,
    )
    s_po_number_right = ParagraphStyle(
        'PONumberRight', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
        alignment=TA_RIGHT,
    )
    s_vendor_name = ParagraphStyle(
        'POVendorName', parent=s_normal,
        fontSize=11, fontName='Helvetica-Bold', textColor=BRAND_DARK,
    )
    s_total_label = ParagraphStyle(
        'POTotalLabel', parent=s_normal,
        fontSize=14, fontName='Helvetica-Bold', textColor=BRAND_DARK,
        alignment=TA_RIGHT,
    )
    s_total_value = ParagraphStyle(
        'POTotalValue', parent=s_normal,
        fontSize=14, fontName='Helvetica-Bold', textColor=BRAND_ACCENT,
        alignment=TA_RIGHT,
    )
    s_notes_box = ParagraphStyle(
        'PONotesBox', parent=s_normal,
        fontSize=9, textColor=BRAND_DARK, leading=13,
        backColor=colors.HexColor('#eff6ff'),
        borderPadding=10,
    )
    s_footer = ParagraphStyle(
        'POFooter', parent=s_normal,
        fontSize=8, textColor=BRAND_MUTED, leading=11,
    )
    s_footer_center = ParagraphStyle(
        'POFooterCenter', parent=s_footer, alignment=TA_CENTER,
    )

    # Table cell styles
    th = ParagraphStyle('POTH', parent=s_normal, fontSize=7, fontName='Helvetica', textColor=BRAND_MUTED)
    th_right = ParagraphStyle('POTHRight', parent=th, alignment=TA_RIGHT)
    td = ParagraphStyle('POTD', parent=s_normal, fontSize=9, textColor=BRAND_DARK)
    td_right = ParagraphStyle('POTDRight', parent=td, alignment=TA_RIGHT)
    td_bold = ParagraphStyle('POTDBold', parent=td, fontName='Helvetica-Bold')
    td_bold_right = ParagraphStyle('POTDBoldRight', parent=td_bold, alignment=TA_RIGHT)
    td_muted = ParagraphStyle('POTDMuted', parent=td, textColor=BRAND_MUTED, fontSize=8)
    td_muted_right = ParagraphStyle('POTDMutedRight', parent=td_muted, alignment=TA_RIGHT)

    content = []

    # ================================================================
    # HEADER — Logo + Company (left) | PURCHASE ORDER + number/dates (right)
    # ================================================================
    company_lines = []
    if settings:
        if settings.company_name:
            company_lines.append(Paragraph(esc(settings.company_name), s_company_name))
        addr_parts = []
        if settings.company_address_line1:
            addr_parts.append(esc(settings.company_address_line1))
        city_state = ""
        if settings.company_city:
            city_state = esc(settings.company_city)
        if settings.company_state:
            city_state += f", {esc(settings.company_state)}"
        if settings.company_zip:
            city_state += f" {esc(settings.company_zip)}"
        if city_state:
            addr_parts.append(city_state)
        if settings.company_phone:
            addr_parts.append(esc(settings.company_phone))
        if settings.company_email:
            addr_parts.append(esc(settings.company_email))
        if addr_parts:
            company_lines.append(Paragraph("<br/>".join(addr_parts), s_detail))

    left_header = []
    if settings and settings.logo_data:
        try:
            logo_buffer = io.BytesIO(settings.logo_data)
            logo_img = Image(logo_buffer, width=1.2 * inch, height=1.2 * inch)
            logo_img.hAlign = 'LEFT'
            logo_row = Table(
                [[logo_img, company_lines]],
                colWidths=[1.4 * inch, 2.4 * inch],
            )
            logo_row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
            left_header.append(logo_row)
        except Exception:
            left_header.extend(company_lines)
    else:
        left_header.extend(company_lines)

    right_header = [
        Paragraph("PURCHASE ORDER", s_doc_label),
        Paragraph(esc(po.po_number), s_po_number_right),
        Spacer(1, 6),
        Paragraph(
            f"Order Date: {po.order_date.strftime('%B %d, %Y')}" if po.order_date else "Order Date: —",
            s_detail_right,
        ),
        Paragraph(
            f"Expected: {po.expected_date.strftime('%B %d, %Y')}" if po.expected_date else "Expected: —",
            s_detail_right,
        ),
        Paragraph(f"Status: {esc((po.status or '').replace('_', ' ').title())}", s_detail_right),
    ]

    header_table = Table(
        [[left_header, right_header]],
        colWidths=[page_width * 0.55, page_width * 0.45],
    )
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    content.append(header_table)
    content.append(Spacer(1, 0.15 * inch))
    content.append(HRFlowable(width="100%", thickness=1, color=BRAND_BORDER))
    content.append(Spacer(1, 0.2 * inch))

    # ================================================================
    # VENDOR — left column
    # ================================================================
    vendor = po.vendor
    vendor_lines = [Paragraph("VENDOR", s_section)]
    if vendor:
        vendor_lines.append(Paragraph(esc(vendor.name), s_vendor_name))
        if vendor.contact_name:
            vendor_lines.append(Paragraph(f"Attn: {esc(vendor.contact_name)}", s_detail))
        if vendor.address_line1:
            vendor_lines.append(Paragraph(esc(vendor.address_line1), s_detail))
        v_city_state = ""
        if vendor.city:
            v_city_state = esc(vendor.city)
        if vendor.state:
            v_city_state += f", {esc(vendor.state)}"
        if vendor.postal_code:
            v_city_state += f" {esc(vendor.postal_code)}"
        if v_city_state:
            vendor_lines.append(Paragraph(v_city_state, s_detail))
        if vendor.phone:
            vendor_lines.append(Paragraph(esc(vendor.phone), s_detail))
        if vendor.email:
            vendor_lines.append(Paragraph(esc(vendor.email), s_detail))

    # Right column — payment / shipping info
    po_details = [Paragraph("ORDER DETAILS", s_section)]
    if po.payment_method:
        po_details.append(Paragraph(f"Payment: {esc(po.payment_method)}", s_detail))
    if po.payment_reference:
        po_details.append(Paragraph(f"Reference: {esc(po.payment_reference)}", s_detail))
    if po.tracking_number:
        po_details.append(Paragraph(f"Tracking: {esc(po.tracking_number)}", s_detail))
    if po.carrier:
        po_details.append(Paragraph(f"Carrier: {esc(po.carrier)}", s_detail))

    vendor_table = Table(
        [[vendor_lines, po_details]],
        colWidths=[page_width * 0.5, page_width * 0.5],
    )
    vendor_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    content.append(vendor_table)
    content.append(Spacer(1, 0.25 * inch))

    # ================================================================
    # LINE ITEMS TABLE
    # ================================================================
    lines = sorted(po.lines, key=lambda ln: ln.line_number)

    table_data = [[
        Paragraph('#', th),
        Paragraph('PRODUCT', th),
        Paragraph('SKU', th),
        Paragraph('QTY ORDERED', th_right),
        Paragraph('QTY RECEIVED', th_right),
        Paragraph('UNIT', th),
        Paragraph('UNIT COST', th_right),
        Paragraph('TOTAL', th_right),
    ]]

    for line in lines:
        qty_ord = float(line.quantity_ordered or 0)
        qty_ord_str = str(int(qty_ord)) if qty_ord == int(qty_ord) else f"{qty_ord:g}"
        qty_rec = float(line.quantity_received or 0)
        qty_rec_str = str(int(qty_rec)) if qty_rec == int(qty_rec) else f"{qty_rec:g}"
        unit_str = esc(line.purchase_unit) if line.purchase_unit else "ea"
        product_name = line.product.name if line.product else "—"
        product_sku = line.product.sku if line.product else "—"
        table_data.append([
            Paragraph(str(line.line_number), td_muted),
            Paragraph(esc(product_name), td),
            Paragraph(esc(product_sku), td_muted),
            Paragraph(qty_ord_str, td_right),
            Paragraph(qty_rec_str, td_right),
            Paragraph(unit_str, td_muted),
            Paragraph(_fmt(line.unit_cost), td_right),
            Paragraph(_fmt(line.line_total), td_bold_right),
        ])

    col_widths = [0.3 * inch, 1.6 * inch, 0.8 * inch, 0.75 * inch, 0.75 * inch, 0.5 * inch, 0.75 * inch, 0.75 * inch]
    items_table = Table(table_data, colWidths=col_widths)
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('LINEBELOW', (0, 0), (-1, 0), 1, BRAND_BORDER),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, BRAND_BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]
    for i in range(1, len(table_data)):
        if i % 2 == 0:
            ts.append(('BACKGROUND', (0, i), (-1, i), ROW_STRIPE))
    items_table.setStyle(TableStyle(ts))
    content.append(items_table)
    content.append(Spacer(1, 0.15 * inch))

    # ================================================================
    # TOTALS — right-aligned summary block
    # ================================================================
    totals_data = []
    totals_data.append([
        Paragraph('Subtotal', td_muted_right),
        Paragraph(_fmt(po.subtotal), td_right),
    ])
    if po.tax_amount and Decimal(str(po.tax_amount or "0")) > 0:
        tax_label = "Tax"
        if settings and settings.tax_name:
            tax_label = esc(settings.tax_name)
        totals_data.append([
            Paragraph(tax_label, td_muted_right),
            Paragraph(_fmt(po.tax_amount), td_right),
        ])
    if po.shipping_cost and Decimal(str(po.shipping_cost or "0")) > 0:
        totals_data.append([
            Paragraph('Shipping', td_muted_right),
            Paragraph(_fmt(po.shipping_cost), td_right),
        ])
    totals_data.append([
        Paragraph('Total', s_total_label),
        Paragraph(_fmt(po.total_amount), s_total_value),
    ])

    totals_width = 3.0 * inch
    spacer_width = page_width - totals_width
    totals_table = Table(
        [[Spacer(spacer_width, 1), Table(
            totals_data,
            colWidths=[1.6 * inch, 1.4 * inch],
            style=TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LINEABOVE', (0, -1), (-1, -1), 1.5, BRAND_DARK),
                ('TOPPADDING', (0, -1), (-1, -1), 8),
                ('BOTTOMPADDING', (0, -1), (-1, -1), 4),
            ]),
        )]],
        colWidths=[spacer_width, totals_width],
    )
    totals_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    content.append(totals_table)
    content.append(Spacer(1, 0.3 * inch))

    # ================================================================
    # NOTES (if present)
    # ================================================================
    if po.notes:
        content.append(KeepTogether([
            HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER),
            Spacer(1, 0.1 * inch),
            Paragraph("NOTES", s_section),
            Paragraph(esc(po.notes), s_notes_box),
            Spacer(1, 0.2 * inch),
        ]))

    # ================================================================
    # FOOTER
    # ================================================================
    content.append(HRFlowable(width="100%", thickness=0.5, color=BRAND_BORDER))
    content.append(Spacer(1, 0.1 * inch))
    company_name = esc(settings.company_name) if settings and settings.company_name else "us"
    content.append(Paragraph(
        f"This purchase order was generated by {company_name}. "
        "Please reference the PO number on all correspondence and shipping documents.",
        s_footer_center,
    ))

    doc.build(content)
    pdf_buffer.seek(0)
    return pdf_buffer
