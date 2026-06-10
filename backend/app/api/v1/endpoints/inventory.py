"""
Inventory API Endpoints

Handles inventory transactions, negative inventory approvals, and reporting.
"""
from typing import Optional
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, or_

from app.db.session import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models import User, InventoryTransaction, Inventory, Product
from app.services import inventory_ledger
from app.services.inventory_ledger import apply_held_transaction
from app.services.inventory_service import get_or_create_inventory
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/transactions/{transaction_id}/approve-negative")
async def approve_negative_inventory(
    transaction_id: int,
    approval_reason: str = Query(..., description="Reason for approving negative inventory"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Approve a negative inventory transaction that requires approval.
    
    This allows inventory to go negative with proper documentation and audit trail.
    """
    transaction = db.query(InventoryTransaction).filter(
        InventoryTransaction.id == transaction_id
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    if not transaction.requires_approval:
        raise HTTPException(
            status_code=400,
            detail="Transaction does not require approval"
        )
    
    if transaction.approved_by:
        raise HTTPException(
            status_code=400,
            detail="Transaction already approved"
        )
    
    # Stamp the type before apply so the ledger row carries the correct
    # semantic.  apply_held_transaction acquires a FOR UPDATE lock on the
    # inventory row (via inventory_ledger.get_or_create_inventory_row)
    # before mutating on_hand, which prevents the concurrent-approval
    # double-add race (HARD-4a follow-up).
    transaction.transaction_type = "negative_adjustment"

    approver = current_user.email if current_user else "system"
    apply_held_transaction(
        db,
        transaction=transaction,
        approved_by=approver,
        approval_reason=approval_reason,
    )

    db.commit()
    db.refresh(transaction)
    
    logger.info(
        f"Negative inventory transaction {transaction_id} approved by {current_user.email if current_user else 'system'}: "
        f"Product {transaction.product_id}, Quantity: {transaction.quantity}, Reason: {approval_reason}"
    )
    
    return {
        "success": True,
        "transaction_id": transaction_id,
        "message": "Negative inventory transaction approved",
        "product_id": transaction.product_id,
        "quantity": float(transaction.quantity),
        "approved_by": transaction.approved_by,
        "approved_at": transaction.approved_at.isoformat() if transaction.approved_at else None,
    }


@router.get("/negative-inventory-report")
async def get_negative_inventory_report(
    start_date: Optional[datetime] = Query(None, description="Start date for report"),
    end_date: Optional[datetime] = Query(None, description="End date for report"),
    include_approved: bool = Query(True, description="Include approved transactions"),
    include_pending: bool = Query(True, description="Include pending approvals"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate negative inventory report showing all negative inventory occurrences.
    
    Shows:
    - All negative inventory transactions
    - Approval history
    - Reasons for adjustments
    - Impact on inventory levels
    """
    # OPTIMIZED: Use joinedload to eager load product relationship
    query = db.query(InventoryTransaction).options(
        joinedload(InventoryTransaction.product)
    ).filter(
        or_(
            InventoryTransaction.transaction_type == "negative_adjustment",
            InventoryTransaction.requires_approval.is_(True),
        )
    )

    if start_date:
        query = query.filter(InventoryTransaction.created_at >= start_date)
    if end_date:
        query = query.filter(InventoryTransaction.created_at <= end_date)

    if not include_approved:
        query = query.filter(InventoryTransaction.approved_by.is_(None))
    if not include_pending:
        query = query.filter(InventoryTransaction.requires_approval.is_(False))

    transactions = query.order_by(desc(InventoryTransaction.created_at)).all()
    
    # Get current inventory levels for affected products
    product_ids = list(set([t.product_id for t in transactions]))
    inventory_levels = {}
    if product_ids:
        inv_query = db.query(
            Inventory.product_id,
            func.sum(Inventory.on_hand_quantity).label("on_hand"),
            func.sum(Inventory.allocated_quantity).label("allocated"),
        ).filter(
            Inventory.product_id.in_(product_ids)
        ).group_by(Inventory.product_id).all()
        
        for row in inv_query:
            inventory_levels[row.product_id] = {
                "on_hand": float(row.on_hand or 0),
                "allocated": float(row.allocated or 0),
                "available": float(row.on_hand or 0) - float(row.allocated or 0),
            }
    
    report_items = []
    for txn in transactions:
        # OPTIMIZED: Use eager-loaded product relationship (no additional query)
        product = txn.product
        inv_level = inventory_levels.get(txn.product_id, {
            "on_hand": 0,
            "allocated": 0,
            "available": 0,
        })

        report_items.append({
            "transaction_id": txn.id,
            "created_at": txn.created_at.isoformat() if txn.created_at else None,
            "product_id": txn.product_id,
            "product_sku": product.sku if product else None,
            "product_name": product.name if product else None,
            "quantity": float(txn.quantity),
            "transaction_type": txn.transaction_type,
            "reference_type": txn.reference_type,
            "reference_id": txn.reference_id,
            "requires_approval": txn.requires_approval,
            "approval_reason": txn.approval_reason,
            "approved_by": txn.approved_by,
            "approved_at": txn.approved_at.isoformat() if txn.approved_at else None,
            "created_by": txn.created_by,
            "notes": txn.notes,
            "current_inventory": inv_level,
        })
    
    return {
        "report_period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
        "total_transactions": len(report_items),
        "pending_approvals": len([t for t in report_items if t["requires_approval"] and not t["approved_by"]]),
        "approved_transactions": len([t for t in report_items if t["approved_by"]]),
        "transactions": report_items,
    }


@router.post("/validate-consistency")
async def validate_inventory_consistency_endpoint(
    product_id: Optional[int] = Query(None, description="Filter by product ID"),
    location_id: Optional[int] = Query(None, description="Filter by location ID"),
    auto_fix: bool = Query(False, description="Automatically fix inconsistencies"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Validate inventory consistency: check that allocated doesn't exceed on_hand.
    
    Optionally auto-fix by reducing allocated to match on_hand.
    """
    from app.services.inventory_service import validate_inventory_consistency
    
    inconsistencies = validate_inventory_consistency(
        db=db,
        product_id=product_id,
        location_id=location_id,
        auto_fix=auto_fix,
    )
    
    return {
        "total_checked": len(inconsistencies),
        "inconsistencies_found": len([i for i in inconsistencies if not i.get("fixed", False)]),
        "inconsistencies_fixed": len([i for i in inconsistencies if i.get("fixed", False)]),
        "inconsistencies": inconsistencies,
    }


@router.post("/adjust-quantity")
async def adjust_inventory_quantity(
    product_id: int = Query(..., description="Product ID to adjust"),
    location_id: int = Query(1, description="Location ID (defaults to 1)"),
    new_on_hand_quantity: float = Query(..., description="New on-hand quantity (in product's base unit)"),
    adjustment_reason: str = Query(..., description="Reason for adjustment (e.g., 'Physical count', 'Found inventory', 'Damaged goods')"),
    input_unit: Optional[str] = Query(None, description="Unit of the input quantity (e.g., 'G' for grams, 'KG' for kilograms)"),
    cost_per_unit: Optional[float] = Query(None, description="Cost per unit for accounting (optional, defaults to product's effective cost)"),
    notes: Optional[str] = Query(None, description="Additional notes"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Adjust inventory on-hand quantity and create an adjustment transaction.
    
    This endpoint:
    1. Gets current on-hand quantity
    2. Calculates the difference (adjustment amount)
    3. Creates an inventory transaction of type 'adjustment'
    4. Updates the inventory on-hand quantity
    5. Ensures MRP calculations will reflect the change
    
    The adjustment transaction will be:
    - Positive quantity if increasing inventory (receipt/adjustment)
    - Negative quantity if decreasing inventory (issue/adjustment)
    """
    from app.services.inventory_helpers import is_material
    
    # Get product to check unit
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    
    # Get or create inventory record
    inventory = get_or_create_inventory(db, product_id, location_id)
    
    # Check if this is a material
    is_mat = is_material(product)
    
    # Get current on-hand quantity (in transaction unit: GRAMS for materials)
    current_qty_transaction_unit = float(inventory.on_hand_quantity or 0)
    
    # Convert input quantity to transaction unit (GRAMS for materials, product_unit for others)
    input_qty = Decimal(str(new_on_hand_quantity))
    product_unit = (product.unit or "EA").upper()
    
    # Handle unit conversion if input_unit is provided
    if input_unit and input_unit.upper() != (product_unit if not is_mat else "G"):
        from app.services.uom_service import convert_quantity_safe
        
        # Target unit: GRAMS for materials, product_unit for others
        target_unit = "G" if is_mat else product_unit
        
        try:
            # Convert from input unit to target unit
            converted_qty, was_converted = convert_quantity_safe(
                db, 
                input_qty, 
                input_unit.upper(), 
                target_unit
            )
            if was_converted:
                new_qty_transaction_unit = converted_qty
                logger.info(
                    f"Converted {input_qty} {input_unit} to {new_qty_transaction_unit} {target_unit} "
                    f"for product {product.sku} (material: {is_mat})"
                )
            else:
                # Conversion failed - try simple conversion for common cases
                if input_unit.upper() == "G" and target_unit == "KG":
                    new_qty_transaction_unit = input_qty / Decimal("1000")
                elif input_unit.upper() == "KG" and target_unit == "G":
                    new_qty_transaction_unit = input_qty * Decimal("1000")
                elif input_unit.upper() == "LB" and target_unit == "G":
                    new_qty_transaction_unit = input_qty * Decimal("453.592")
                else:
                    new_qty_transaction_unit = input_qty
                    logger.warning(
                        f"Could not convert {input_qty} {input_unit} to {target_unit} for product {product.sku}, using as-is"
                    )
        except Exception as e:
            # Simple conversion fallback
            if input_unit.upper() == "KG" and target_unit == "G":
                new_qty_transaction_unit = input_qty * Decimal("1000")
                logger.info(f"Simple conversion: {input_qty} KG = {new_qty_transaction_unit} G")
            elif input_unit.upper() == "G" and target_unit == "KG":
                new_qty_transaction_unit = input_qty / Decimal("1000")
                logger.info(f"Simple conversion: {input_qty} G = {new_qty_transaction_unit} KG")
            else:
                new_qty_transaction_unit = input_qty
                logger.warning(f"Could not convert units, using input as-is: {e}")
    else:
        # No conversion needed - input is already in target unit
        new_qty_transaction_unit = input_qty
    
    adjustment_qty = new_qty_transaction_unit - Decimal(str(current_qty_transaction_unit))
    
    if adjustment_qty == 0:
        # No change needed
        return {
            "success": True,
            "message": "No adjustment needed - quantity unchanged",
            "product_id": product_id,
            "current_quantity": float(current_qty_transaction_unit),  # Already in transaction unit
            "new_quantity": float(new_qty_transaction_unit),  # Already in transaction unit
            "adjustment": 0,
        }
    
    # Store original adjustment amount for response
    original_adjustment = float(adjustment_qty)

    direction = "increase" if adjustment_qty > 0 else "decrease"
    transaction_notes = (
        f"Quantity adjustment ({direction}): {adjustment_reason}. {notes or ''}"
    )

    # Get cost per unit for accounting
    # Use cost per inventory unit ($/gram for materials, $/unit for others)
    # This matches the transaction quantity unit for correct total_cost calculation
    from app.services.inventory_service import get_effective_cost_per_inventory_unit
    transaction_cost_per_unit = None
    if cost_per_unit is not None:
        transaction_cost_per_unit = Decimal(str(cost_per_unit))
    else:
        # Use product's effective cost per inventory unit
        transaction_cost_per_unit = get_effective_cost_per_inventory_unit(product)

    # Post through the canonical ledger (HARD-4a): one signed "adjustment"
    # delta replaces the old SET-on_hand + receipt/adjustment row split.
    # Quantity is in the transaction unit (GRAMS for materials).
    transaction = inventory_ledger.post(
        db,
        product_id=product_id,
        location_id=location_id,
        transaction_type="adjustment",
        quantity_delta=adjustment_qty,
        cost_per_unit=transaction_cost_per_unit,
        reference_type="manual_adjustment",
        reference_id=0,  # No specific reference document
        notes=transaction_notes,
        created_by=current_user.email if current_user else "system",
    )

    # Commit to ensure inventory is updated
    db.commit()
    
    # Refresh inventory to get updated values
    db.refresh(inventory)
    db.refresh(transaction)
    
    unit_label = "g" if is_mat else product_unit
    logger.info(
        f"Inventory quantity adjusted by {current_user.email if current_user else 'system'}: "
        f"Product {product_id} ({product.sku if product else 'N/A'}), "
        f"Location {location_id}, "
        f"Old: {current_qty_transaction_unit:.1f}{unit_label}, New: {float(new_qty_transaction_unit):.1f}{unit_label}, "
        f"Adjustment: {original_adjustment:+.1f}{unit_label}, "
        f"Reason: {adjustment_reason}"
    )
    
    return {
        "success": True,
        "message": "Inventory quantity adjusted successfully",
        "transaction_id": transaction.id,
        "product_id": product_id,
        "product_sku": product.sku if product else None,
        "product_name": product.name if product else None,
        "location_id": location_id,
        "previous_quantity": float(current_qty_transaction_unit),  # In transaction unit (GRAMS for materials)
        "new_quantity": float(inventory.on_hand_quantity or 0),  # In transaction unit (GRAMS for materials)
        "adjustment_amount": original_adjustment,  # In transaction unit (GRAMS for materials)
        "transaction_type": transaction.transaction_type,
        "adjustment_reason": adjustment_reason,
        "allocated_quantity": float(inventory.allocated_quantity or 0),
        "available_quantity": float((inventory.on_hand_quantity or 0) - (inventory.allocated_quantity or 0)),
    }
