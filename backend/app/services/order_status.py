"""
Order Status Management Service

Provides status transition validation, automated status updates,
and workflow orchestration for Sales Orders and Production Orders.

This service ensures proper state machine flow and prevents invalid
status transitions.
"""
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.sales_order import SalesOrder
from app.models.production_order import ProductionOrder
from app.logging_config import get_logger

logger = get_logger(__name__)


class OrderStatusService:
    """
    Manages order status transitions and workflow automation.
    
    Responsibilities:
    - Validate status transitions (prevent invalid state changes)
    - Auto-update SO status based on WO completion
    - Handle scrap/remake workflows
    - Coordinate fulfillment readiness
    """
    
    # ========================================================================
    # SALES ORDER STATUS TRANSITIONS
    # ========================================================================
    
    VALID_SO_TRANSITIONS: Dict[str, List[str]] = {
        "draft": ["pending_payment", "cancelled"],
        "pending_payment": ["confirmed", "payment_failed", "cancelled"],
        "payment_failed": ["pending_payment", "cancelled"],  # Allow retry
        "confirmed": ["in_production", "ready_to_ship", "on_hold", "cancelled"],
        "in_production": ["ready_to_ship", "on_hold", "cancelled"],
        "ready_to_ship": ["shipped", "partially_shipped", "on_hold"],
        "partially_shipped": ["shipped", "on_hold"],
        "shipped": ["delivered"],
        "delivered": ["completed"],
        "on_hold": ["confirmed", "in_production", "ready_to_ship", "cancelled"],
        "cancelled": [],  # Terminal state
        "completed": [],  # Terminal state
    }
    
    # ========================================================================
    # PRODUCTION ORDER STATUS TRANSITIONS
    # ========================================================================
    
    VALID_WO_TRANSITIONS: Dict[str, List[str]] = {
        "draft": ["released", "cancelled"],
        "released": ["scheduled", "on_hold", "cancelled"],
        "scheduled": ["in_progress", "on_hold", "cancelled"],
        "in_progress": ["completed", "on_hold", "cancelled"],
        "completed": ["closed", "qc_hold"],  # QC decision point
        "qc_hold": ["scrapped", "in_progress", "closed"],  # Disposition: scrap, rework, or waive
        "scrapped": [],  # Terminal - remake WO will be created
        "closed": [],  # Terminal state
        "on_hold": ["released", "scheduled", "in_progress"],  # Resume from hold
        "cancelled": [],  # Terminal state
    }
    
    # ========================================================================
    # VALIDATION METHODS
    # ========================================================================
    
    def validate_so_transition(self, from_status: str, to_status: str) -> Tuple[bool, str]:
        """
        Validate Sales Order status transition.
        
        Args:
            from_status: Current SO status
            to_status: Desired SO status
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if from_status == to_status:
            return True, ""  # No change is always valid
        
        valid_next = self.VALID_SO_TRANSITIONS.get(from_status, [])
        
        if to_status not in valid_next:
            return False, f"Invalid SO status transition: '{from_status}' → '{to_status}'. Valid options: {', '.join(valid_next)}"
        
        return True, ""
    
    def validate_wo_transition(self, from_status: str, to_status: str) -> Tuple[bool, str]:
        """
        Validate Production Order status transition.
        
        Args:
            from_status: Current WO status
            to_status: Desired WO status
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if from_status == to_status:
            return True, ""  # No change is always valid
        
        valid_next = self.VALID_WO_TRANSITIONS.get(from_status, [])
        
        if to_status not in valid_next:
            return False, f"Invalid WO status transition: '{from_status}' → '{to_status}'. Valid options: {', '.join(valid_next)}"
        
        return True, ""
    
    # ========================================================================
    # SALES ORDER STATUS UPDATES
    # ========================================================================
    
    def update_so_status(
        self,
        db: Session,
        so: SalesOrder,
        new_status: str,
        skip_validation: bool = False
    ) -> SalesOrder:
        """
        Update Sales Order status with validation.
        
        Args:
            db: Database session
            so: Sales Order to update
            new_status: Desired new status
            skip_validation: Force update (use with caution!)
            
        Returns:
            Updated SalesOrder
            
        Raises:
            ValueError: If transition is invalid
        """
        if not skip_validation:
            is_valid, error = self.validate_so_transition(so.status, new_status)
            if not is_valid:
                raise ValueError(error)
        
        old_status = so.status
        so.status = new_status
        so.updated_at = datetime.now(timezone.utc)
        
        # Handle status-specific updates
        if new_status == "confirmed":
            so.confirmed_at = datetime.now(timezone.utc)
        elif new_status == "ready_to_ship":
            so.fulfillment_status = "ready"
        elif new_status == "shipped":
            so.shipped_at = datetime.now(timezone.utc)
            so.fulfillment_status = "shipped"
        elif new_status == "delivered":
            so.delivered_at = datetime.now(timezone.utc)
            so.fulfillment_status = "delivered"
        elif new_status == "cancelled":
            so.cancelled_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(so)
        
        logger.info(f"SO {so.order_number}: {old_status} → {new_status}")
        return so
    
    def auto_update_so_from_wos(self, db: Session, so: SalesOrder) -> SalesOrder:
        """
        Automatically update Sales Order status based on Production Order states.
        
        Logic:
        - If any WO is in_progress → SO = in_production
        - If all WOs are closed AND QC passed → SO = ready_to_ship
        - If mixed states → keep current status
        
        Args:
            db: Database session
            so: Sales Order to update
            
        Returns:
            Updated SalesOrder
        """
        # Get all WOs for this SO
        wos = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id == so.id
        ).all()
        
        if not wos:
            logger.warning(f"SO {so.order_number} has no Production Orders")
            return so
        
        # Determine appropriate SO status
        wo_statuses = [wo.status for wo in wos]
        
        # Any WO in progress → SO should be in_production
        if any(status in ["in_progress", "scheduled"] for status in wo_statuses):
            if so.status == "confirmed":
                self.update_so_status(db, so, "in_production")
        
        # All WOs closed → SO ready to ship
        elif all(status == "closed" for status in wo_statuses):
            # Also check QC status
            if all(wo.qc_status in ["passed", "not_required", "waived"] for wo in wos):
                if so.status == "in_production":
                    self.update_so_status(db, so, "ready_to_ship")
                    so.fulfillment_status = "ready"
                    db.commit()
        
        # Mixed states or waiting - no change needed
        
        return so
    
    # ========================================================================
    # PRODUCTION ORDER STATUS UPDATES
    # ========================================================================
    
    def update_wo_status(
        self,
        db: Session,
        wo: ProductionOrder,
        new_status: str,
        skip_validation: bool = False
    ) -> ProductionOrder:
        """
        Update Production Order status with validation and side effects.
        
        Args:
            db: Database session
            wo: Production Order to update
            new_status: Desired new status
            skip_validation: Force update (use with caution!)
            
        Returns:
            Updated ProductionOrder
            
        Raises:
            ValueError: If transition is invalid
        """
        if not skip_validation:
            is_valid, error = self.validate_wo_transition(wo.status, new_status)
            if not is_valid:
                raise ValueError(error)
        
        old_status = wo.status
        wo.status = new_status
        wo.updated_at = datetime.now(timezone.utc)
        
        # Handle status-specific timestamps
        if new_status == "in_progress" and not wo.actual_start:
            wo.actual_start = datetime.now(timezone.utc)
        elif new_status == "completed" and not wo.actual_end:
            wo.actual_end = datetime.now(timezone.utc)
            # Mark as pending QC if required
            if wo.qc_status == "not_required":
                pass  # Auto-closable
            else:
                wo.qc_status = "pending"
        elif new_status == "closed":
            wo.completed_at = datetime.now(timezone.utc)
        elif new_status == "scrapped":
            wo.scrapped_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(wo)
        
        logger.info(f"WO {wo.code}: {old_status} → {new_status}")
        
        # Update parent Sales Order if linked
        if wo.sales_order_id:
            so = db.query(SalesOrder).filter(SalesOrder.id == wo.sales_order_id).first()
            if so:
                self.auto_update_so_from_wos(db, so)
        
        return wo
    
    # ========================================================================
    # SCRAP & REMAKE WORKFLOWS
    # ========================================================================
    
    def scrap_wo_and_create_remake(
        self,
        db: Session,
        wo: ProductionOrder,
        scrap_reason: str,
        scrap_quantity: Optional[float] = None
    ) -> ProductionOrder:
        """
        Mark WO as scrapped and create remake WO.
        
        Args:
            db: Database session
            wo: Production Order to scrap
            scrap_reason: Reason for scrap (e.g., "layer_shift")
            scrap_quantity: Amount scrapped (None = all)
            
        Returns:
            New remake ProductionOrder
        """
        # Determine scrap quantity
        if scrap_quantity is None:
            scrap_quantity = float(wo.quantity_ordered)
        
        # Update original WO - follow proper workflow
        wo.quantity_scrapped = scrap_quantity
        wo.scrap_reason = scrap_reason
        
        # Transition through QC hold if needed
        if wo.status == "completed":
            self.update_wo_status(db, wo, "qc_hold")
        
        self.update_wo_status(db, wo, "scrapped")
        
        # Create remake WO
        remake_code = f"{wo.code}-R1"
        existing_remakes = db.query(ProductionOrder).filter(
            ProductionOrder.remake_of_id == wo.id
        ).count()
        if existing_remakes > 0:
            remake_code = f"{wo.code}-R{existing_remakes + 1}"
        
        remake = ProductionOrder(
            code=remake_code,
            product_id=wo.product_id,
            bom_id=wo.bom_id,
            routing_id=wo.routing_id,
            sales_order_id=wo.sales_order_id,
            sales_order_line_id=wo.sales_order_line_id,
            quantity_ordered=scrap_quantity,
            source=wo.source,
            status="draft",
            priority=wo.priority + 1,  # Higher priority for remakes
            due_date=wo.due_date,
            remake_of_id=wo.id,
            notes=f"Remake of {wo.code} - Original scrapped due to: {scrap_reason}",
            created_by="system_auto_remake"
        )
        
        db.add(remake)
        db.commit()
        db.refresh(remake)
        
        logger.info(f"Created remake WO {remake.code} for scrapped {wo.code}")
        return remake
    
    # ========================================================================
    # FULFILLMENT WORKFLOWS
    # ========================================================================
    
    def mark_ready_for_shipping(self, db: Session, so: SalesOrder) -> SalesOrder:
        """
        Mark Sales Order as ready for shipping queue.
        
        Validates:
        - All WOs are closed
        - All QC passed
        - Current status allows transition
        
        Args:
            db: Database session
            so: Sales Order to mark ready
            
        Returns:
            Updated SalesOrder
            
        Raises:
            ValueError: If order is not ready
        """
        # Verify all WOs are complete
        wos = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id == so.id
        ).all()
        
        if not wos:
            raise ValueError(f"SO {so.order_number} has no production orders")
        
        incomplete = [wo for wo in wos if wo.status != "closed"]
        if incomplete:
            raise ValueError(
                f"Cannot mark ready to ship: {len(incomplete)} WOs still in progress"
            )
        
        failed_qc = [wo for wo in wos if wo.qc_status == "failed"]
        if failed_qc:
            raise ValueError(
                f"Cannot mark ready to ship: {len(failed_qc)} WOs failed QC"
            )
        
        # Update status
        self.update_so_status(db, so, "ready_to_ship")
        so.fulfillment_status = "ready"
        db.commit()
        
        logger.info(f"SO {so.order_number} marked ready for shipping")
        return so


# Singleton instance
order_status_service = OrderStatusService()
