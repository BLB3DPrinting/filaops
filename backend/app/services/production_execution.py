"""
Production Execution Service

Centralized service for production order execution workflows:
- BOM explosion and material reservation
- Material consumption
- Production order state transitions (schedule, start, complete print, QC)

This service unifies production execution logic that was previously split
between fulfillment and production order endpoints.
"""
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.production_order import ProductionOrder
from app.models.bom import BOM
from app.models.product import Product
from app.models.inventory import Inventory, InventoryTransaction, InventoryLocation
from app.models.traceability import MaterialLot, ProductionLotConsumption
from app.services.lot_policy import LotPolicyService
from app.logging_config import get_logger

logger = get_logger(__name__)


class ProductionExecutionService:
    """Service for production order execution workflows."""

    @staticmethod
    def get_default_location(db: Session) -> InventoryLocation:
        """Get or create the default inventory location (MAIN warehouse)."""
        location = db.query(InventoryLocation).filter(
            InventoryLocation.code == 'MAIN'
        ).first()
        
        if not location:
            # Try to get any active location
            location = db.query(InventoryLocation).filter(
                InventoryLocation.active.is_(True)
            ).first()
        
        if not location:
            # Create default location if none exists
            location = InventoryLocation(
                code="MAIN",
                name="Main Warehouse",
                type="warehouse",
                active=True
            )
            db.add(location)
            db.flush()
        
        return location

    @staticmethod
    def get_bom_for_production_order(po: ProductionOrder, db: Session) -> Optional[BOM]:
        """Get the BOM for a production order."""
        if po.bom_id:
            return db.query(BOM).filter(BOM.id == po.bom_id).first()
        elif po.product_id:
            return db.query(BOM).filter(
                BOM.product_id == po.product_id,
                BOM.active.is_(True)
            ).first()
        return None

    @staticmethod
    def ensure_inventory_records_exist(bom: BOM, db: Session) -> List[Dict[str, Any]]:
        """
        Ensure Inventory records exist for all BOM components.
        
        Returns list of materials that were synced (created).
        """
        synced_materials = []
        default_location = ProductionExecutionService.get_default_location(db)

        for line in bom.lines:
            component = line.component
            if component:
                # Find or create Inventory record
                inv = db.query(Inventory).filter(
                    Inventory.product_id == component.id
                ).first()
                
                if not inv:
                    # Create Inventory record with zero quantity
                    inv = Inventory(
                        product_id=component.id,
                        location_id=default_location.id,
                        on_hand_quantity=Decimal("0"),
                        allocated_quantity=Decimal("0"),
                    )
                    db.add(inv)
                    synced_materials.append({
                        "sku": component.sku,
                        "name": component.name,
                        "action": "created",
                        "quantity": 0.0,
                    })
        
        # Flush to ensure Inventory records are available
        db.flush()
        return synced_materials

    @staticmethod
    def explode_bom_and_reserve_materials(
        po: ProductionOrder,
        db: Session,
        created_by: str = "system",
        lot_selections: Optional[Dict[int, int]] = None  # component_id -> lot_id mapping
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Explode BOM and reserve materials for a production order.
        
        Returns:
            Tuple of (reserved_materials, insufficient_materials)
        """
        bom = ProductionExecutionService.get_bom_for_production_order(po, db)
        
        if not bom or not bom.lines:
            logger.warning(f"No BOM found for production order {po.code}")
            return [], [], []  # Return 3 empty lists: reserved, insufficient, lot_requirements

        # Ensure inventory records exist
        ProductionExecutionService.ensure_inventory_records_exist(bom, db)

        reserved_materials = []
        insufficient_materials = []
        lot_requirements = []  # Materials that require lot selection
        production_qty = float(po.quantity_ordered or po.quantity)
        
        # Get customer ID from sales order if available
        customer_id = None
        if po.sales_order_id:
            from app.models.sales_order import SalesOrder
            so = db.query(SalesOrder).filter(SalesOrder.id == po.sales_order_id).first()
            if so:
                customer_id = so.customer_id

        for line in bom.lines:
            component = line.component
            if not component:
                continue

            component_name = component.name
            component_sku = component.sku

            # Skip non-inventory cost items - they're for job costing, not physical inventory
            # SVC-* = legacy services, MFG-* = manufacturing overhead (machine time)
            if component_sku.startswith(("SVC-", "MFG-")):
                continue

            # Check if lot is required for this component
            lot_required = LotPolicyService.is_lot_required_for_product(
                product=component,
                db=db,
                customer_id=customer_id,
                sales_order_id=po.sales_order_id,
                transaction_type="consumption"
            )
            
            selected_lot_id = None
            lot = None
            if lot_required:
                # Validate lot selection was provided
                selected_lot_id = lot_selections.get(line.component_id) if lot_selections else None
                if not selected_lot_id:
                    lot_requirements.append({
                        "component_id": line.component_id,
                        "component_sku": component_sku,
                        "component_name": component_name,
                        "lot_required": True,
                        "reason": "Customer traceability requirement" if customer_id else "Global policy (material type)"
                    })
                    # Don't reserve if lot is required but not provided
                    continue
                
                # Validate lot exists and matches product
                lot = db.query(MaterialLot).filter(MaterialLot.id == selected_lot_id).first()
                if not lot or lot.product_id != line.component_id:
                    insufficient_materials.append({
                        "component_id": line.component_id,
                        "component_sku": component_sku,
                        "component_name": component_name,
                        "quantity_required": 0,  # Not a quantity issue
                        "quantity_available": 0,
                        "shortage": 0,
                        "error": f"Invalid lot selection for {component_sku}"
                    })
                    continue

            # Calculate required quantity (BOM line qty * production order qty)
            required_qty = float(line.quantity) * production_qty

            # Apply scrap factor if any
            if line.scrap_factor:
                required_qty *= (1 + float(line.scrap_factor) / 100)

            # Find inventory for this component (any location for now)
            inventory = db.query(Inventory).filter(
                Inventory.product_id == line.component_id
            ).first()

            if inventory and float(inventory.available_quantity) >= required_qty:
                # Reserve the material - only update allocated_quantity
                # available_quantity is a computed column (on_hand - allocated)
                new_allocated = float(inventory.allocated_quantity) + required_qty
                inventory.allocated_quantity = Decimal(str(new_allocated))
                # Calculate what available will be after this update
                new_available = float(inventory.on_hand_quantity) - new_allocated

                # Create reservation transaction with cost for accounting
                from app.services.inventory_service import get_effective_cost_per_inventory_unit
                unit_cost = get_effective_cost_per_inventory_unit(component)
                total_cost = Decimal(str(required_qty)) * unit_cost if unit_cost else None
                transaction = InventoryTransaction(
                    product_id=line.component_id,
                    location_id=inventory.location_id,
                    transaction_type="reservation",
                    reference_type="production_order",
                    reference_id=po.id,
                    quantity=Decimal(str(-required_qty)),  # Negative = reserved/out
                    cost_per_unit=unit_cost,
                    total_cost=total_cost,
                    unit=component.unit,
                    notes=f"Reserved for {po.code}: {required_qty:.2f} units of {component_sku}",
                    created_by=created_by,
                )
                db.add(transaction)

                reserved_materials.append({
                    "component_id": line.component_id,
                    "component_sku": component_sku,
                    "component_name": component_name,
                    "quantity_reserved": round(required_qty, 4),
                    "inventory_remaining": round(new_available, 4),
                    "lot_id": selected_lot_id,
                    "lot_number": lot.lot_number if lot else None,
                })
                
                # Record lot consumption link (if lot was selected)
                if selected_lot_id and lot:
                    lot_consumption = ProductionLotConsumption(
                        production_order_id=po.id,
                        material_lot_id=selected_lot_id,
                        bom_line_id=line.id,
                        quantity_consumed=Decimal(str(required_qty)),
                    )
                    db.add(lot_consumption)
            else:
                # Insufficient inventory - log but continue (warn, don't block)
                available = float(inventory.available_quantity) if inventory else 0
                insufficient_materials.append({
                    "component_id": line.component_id,
                    "component_sku": component_sku,
                    "component_name": component_name,
                    "quantity_required": round(required_qty, 4),
                    "quantity_available": round(available, 4),
                    "shortage": round(required_qty - available, 4),
                })

        return reserved_materials, insufficient_materials, lot_requirements

    @staticmethod
    def consume_production_stage_materials(
        po: ProductionOrder,
        good_quantity: float,
        bad_quantity: float,
        db: Session,
        created_by: str = "system"
    ) -> List[Dict[str, Any]]:
        """
        Consume production-stage materials (not shipping-stage like boxes).
        
        Only consumes materials that were reserved and have consume_stage='production'.
        Shipping-stage materials (boxes, packaging) are consumed at shipping time.
        
        Returns list of consumed materials.
        """
        bom = ProductionExecutionService.get_bom_for_production_order(po, db)
        if not bom or not bom.lines:
            return []

        # Build a set of component_ids that should be consumed at production stage
        production_stage_components = set()
        for line in bom.lines:
            # Default is 'production', so consume if not explicitly 'shipping'
            if getattr(line, 'consume_stage', 'production') != 'shipping':
                production_stage_components.add(line.component_id)

        # Find all reservation transactions for this production order
        reservation_txns = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == po.id,
            InventoryTransaction.transaction_type == "reservation"
        ).all()

        consumed_materials = []
        total_quantity = good_quantity + bad_quantity
        production_qty = float(po.quantity_ordered or po.quantity)

        for res_txn in reservation_txns:
            # Skip shipping-stage items (boxes, packaging) - they're consumed at buy_label
            if res_txn.product_id not in production_stage_components:
                continue

            # Find the BOM line to get the per-unit quantity
            bom_line = None
            for line in bom.lines:
                if line.component_id == res_txn.product_id:
                    bom_line = line
                    break

            if not bom_line:
                continue

            # Calculate consumed quantity based on actual production
            # Scale reservation by actual production ratio
            reserved_qty = abs(float(res_txn.quantity))
            if production_qty > 0:
                consumption_ratio = total_quantity / production_qty
                consumed_qty = reserved_qty * consumption_ratio
            else:
                consumed_qty = reserved_qty

            # Find the inventory record
            inventory = db.query(Inventory).filter(
                Inventory.product_id == res_txn.product_id,
                Inventory.location_id == res_txn.location_id
            ).first()

            if inventory:
                # Release reservation (reduce allocated by the FULL reserved amount)
                # This ensures allocated is properly released even if we consumed less
                current_allocated = float(inventory.allocated_quantity)
                new_allocated = max(0, current_allocated - reserved_qty)
                inventory.allocated_quantity = Decimal(str(new_allocated))

                # Consume from on_hand (use the service function for consistency and validation)
                from app.services.inventory_service import create_inventory_transaction
                try:
                    _consumption_txn = create_inventory_transaction(
                        db=db,
                        product_id=res_txn.product_id,
                        location_id=res_txn.location_id,
                        transaction_type="consumption",
                        quantity=Decimal(str(consumed_qty)),
                        reference_type="production_order",
                        reference_id=po.id,
                        notes=f"Consumed for {po.code}: {consumed_qty:.2f} units (good: {good_quantity}, bad: {bad_quantity})",
                        created_by=created_by,
                        allow_negative=False,  # Don't allow negative without approval in this workflow
                    )
                except Exception as e:
                    # If transaction requires approval, log warning but continue
                    # The transaction was created but inventory wasn't updated
                    logger.warning(
                        f"Inventory transaction requires approval for PO {po.code}: {str(e)}"
                    )
                    # Still delete the reservation since materials were physically consumed
                    db.delete(res_txn)
                    continue

                # Delete or mark reservation as consumed
                db.delete(res_txn)

                consumed_materials.append({
                    "component_id": res_txn.product_id,
                    "component_sku": bom_line.component.sku if bom_line.component else "N/A",
                    "component_name": bom_line.component.name if bom_line.component else "N/A",
                    "quantity_consumed": round(consumed_qty, 4),
                })

        return consumed_materials

    @staticmethod
    def produce_finished_goods(
        po: ProductionOrder,
        good_quantity: float,
        db: Session,
        location_id: Optional[int] = None,
        created_by: str = "system"
    ) -> Dict[str, Any]:
        """
        Add finished goods to inventory after production completion.
        
        Returns dict with production details.
        """
        if not po.product_id:
            raise ValueError(f"Production order {po.code} has no product_id")

        product = db.query(Product).filter(Product.id == po.product_id).first()
        if not product:
            raise ValueError(f"Product {po.product_id} not found")

        # Use provided location or default
        if not location_id:
            default_location = ProductionExecutionService.get_default_location(db)
            location_id = default_location.id

        # Find or create inventory record for finished goods
        inventory = db.query(Inventory).filter(
            Inventory.product_id == po.product_id,
            Inventory.location_id == location_id
        ).first()

        if not inventory:
            inventory = Inventory(
                product_id=po.product_id,
                location_id=location_id,
                on_hand_quantity=Decimal("0"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inventory)
            db.flush()

        # Get cost per unit for accounting (standard cost or average cost)
        from app.services.inventory_service import get_effective_cost
        production_cost_per_unit = get_effective_cost(product)

        # Add finished goods through the canonical ledger (HARD-4a):
        # transaction row + on_hand mutated together, Decimal-only.
        from app.services import inventory_ledger
        inventory_ledger.post(
            db,
            product_id=po.product_id,
            location_id=location_id,
            transaction_type="production",
            quantity_delta=Decimal(str(good_quantity)),
            cost_per_unit=production_cost_per_unit,
            reference_type="production_order",
            reference_id=po.id,
            unit=product.unit or "EA",
            notes=f"Produced {good_quantity:.2f} units for {po.code}",
            created_by=created_by,
        )

        return {
            "product_id": po.product_id,
            "product_sku": product.sku,
            "product_name": product.name,
            "quantity_produced": good_quantity,
            "location_id": location_id,
        }

