"""
Lot Policy Service

Determines when material lot capture is required based on:
1. Global admin policies (by item category/type, location, transaction type)
2. Customer traceability profiles
3. Sales order overrides

Policy is checked at:
- PO receiving (when receiving materials)
- Production consumption (when consuming materials in production)
"""
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.traceability import CustomerTraceabilityProfile, MaterialLot
from app.models.sales_order import SalesOrder
from app.logging_config import get_logger

logger = get_logger(__name__)


class LotPolicyService:
    """Service for determining lot capture requirements."""

    # Global policy: product types/categories that always require lot tracking
    # This can be configured via admin settings in the future
    REQUIRED_PRODUCT_TYPES = ["material", "raw_material", "filament", "resin"]
    REQUIRED_CATEGORIES = []  # Can be populated from admin config

    @staticmethod
    def is_lot_required_for_product(
        product: Product,
        db: Session,
        customer_id: Optional[int] = None,
        sales_order_id: Optional[int] = None,
        transaction_type: str = "receiving"  # "receiving" or "consumption"
    ) -> bool:
        """
        Check if lot capture is required for a product.
        
        Priority:
        1. Sales order override (if sales_order_id provided)
        2. Customer traceability profile (if customer_id provided)
        3. Global admin policy (product type/category)
        
        Args:
            product: The product to check
            db: Database session
            customer_id: Optional customer ID (for customer-specific policy)
            sales_order_id: Optional sales order ID (for order-specific override)
            transaction_type: "receiving" or "consumption"
        
        Returns:
            True if lot capture is required, False otherwise
        """
        # 1. Check sales order override (highest priority)
        if sales_order_id:
            sales_order = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()
            if sales_order:
                # Check if customer has traceability profile
                customer_profile = db.query(CustomerTraceabilityProfile).filter(
                    CustomerTraceabilityProfile.user_id == sales_order.customer_id
                ).first()
                
                if customer_profile:
                    # If customer requires lot traceability, enforce it
                    if customer_profile.traceability_level in ["lot", "full"]:
                        logger.info(
                            f"Lot required for product {product.sku} due to customer "
                            f"traceability level: {customer_profile.traceability_level}"
                        )
                        return True
        
        # 2. Check customer traceability profile
        if customer_id:
            customer_profile = db.query(CustomerTraceabilityProfile).filter(
                CustomerTraceabilityProfile.user_id == customer_id
            ).first()
            
            if customer_profile:
                if customer_profile.traceability_level in ["lot", "full"]:
                    logger.info(
                        f"Lot required for product {product.sku} due to customer "
                        f"traceability level: {customer_profile.traceability_level}"
                    )
                    return True
        
        # 3. Check global admin policy (product type/category)
        product_type = getattr(product, "type", None) or getattr(product, "item_type", None)
        if product_type and product_type.lower() in LotPolicyService.REQUIRED_PRODUCT_TYPES:
            logger.info(
                f"Lot required for product {product.sku} due to product type: {product_type}"
            )
            return True
        
        # Default: not required
        return False

    @staticmethod
    def get_required_lots_for_production_order(
        production_order_id: int,
        db: Session
    ) -> List[Dict[str, Any]]:
        """
        Get list of materials that require lot capture for a production order.
        
        Returns list of dicts with:
        - component_id
        - component_sku
        - component_name
        - lot_required (bool)
        - reason (str) - why lot is required
        """
        from app.models.production_order import ProductionOrder
        from app.models.bom import BOM
        
        po = db.query(ProductionOrder).filter(ProductionOrder.id == production_order_id).first()
        if not po:
            return []
        
        # Get BOM
        bom = None
        if po.bom_id:
            bom = db.query(BOM).filter(BOM.id == po.bom_id).first()
        elif po.product_id:
            bom = db.query(BOM).filter(
                BOM.product_id == po.product_id,
                BOM.active.is_(True)
            ).first()
        
        if not bom or not bom.lines:
            return []
        
        required_lots = []
        customer_id = None
        sales_order_id = po.sales_order_id
        
        # Get customer ID from sales order if available
        if sales_order_id:
            from app.models.sales_order import SalesOrder
            so = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()
            if so:
                customer_id = so.customer_id
        
        for line in bom.lines:
            component = line.component
            if not component:
                continue
            
            # Skip non-inventory items
            component_sku = component.sku or ""
            if component_sku.startswith(("SVC-", "MFG-")):
                continue
            
            lot_required = LotPolicyService.is_lot_required_for_product(
                product=component,
                db=db,
                customer_id=customer_id,
                sales_order_id=sales_order_id,
                transaction_type="consumption"
            )
            
            if lot_required:
                reason = "Customer traceability requirement" if customer_id else "Global policy (material type)"
                required_lots.append({
                    "component_id": component.id,
                    "component_sku": component.sku,
                    "component_name": component.name,
                    "lot_required": True,
                    "reason": reason
                })
        
        return required_lots

    @staticmethod
    def validate_lot_selection(
        product_id: int,
        lot_id: Optional[int],
        db: Session,
        customer_id: Optional[int] = None,
        sales_order_id: Optional[int] = None,
        transaction_type: str = "receiving"
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that lot selection is provided when required.
        
        Returns:
            (is_valid, error_message)
        """
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return False, f"Product {product_id} not found"
        
        lot_required = LotPolicyService.is_lot_required_for_product(
            product=product,
            db=db,
            customer_id=customer_id,
            sales_order_id=sales_order_id,
            transaction_type=transaction_type
        )
        
        if lot_required and not lot_id:
            return False, (
                f"Lot selection is required for product {product.sku} "
                f"(policy: {'customer traceability' if customer_id else 'global admin policy'})"
            )
        
        # Validate lot exists and matches product
        if lot_id:
            lot = db.query(MaterialLot).filter(MaterialLot.id == lot_id).first()
            if not lot:
                return False, f"Lot {lot_id} not found"
            
            if lot.product_id != product_id:
                return False, f"Lot {lot.lot_number} does not match product {product.sku}"
        
        return True, None

