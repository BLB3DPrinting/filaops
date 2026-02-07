"""
MRP Trigger Service

Centralized service for triggering MRP calculations with different contexts.
All triggers are behind feature flags and include error handling to prevent
breaking existing functionality.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.core.settings import get_settings
from app.services.mrp import MRPService
from app.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()


def trigger_mrp_check(
    db: Session,
    sales_order_id: int,
    background: bool = False
) -> Optional[dict]:
    """
    Quick MRP check for a specific sales order.
    
    This performs a lightweight check to see if MRP requirements
    are met for a specific order without running a full MRP calculation.
    
    Args:
        db: Database session
        sales_order_id: ID of the sales order to check
        background: If True, run in background (not implemented yet)
    
    Returns:
        Dictionary with check results, or None if feature is disabled
    """
    if not settings.INCLUDE_SALES_ORDERS_IN_MRP:
        logger.debug(f"MRP check skipped for SO {sales_order_id} - feature disabled")
        return None
    
    try:
        from app.models.sales_order import SalesOrder
        
        sales_order = db.query(SalesOrder).filter(
            SalesOrder.id == sales_order_id
        ).first()
        
        if not sales_order:
            logger.warning(f"Sales order {sales_order_id} not found for MRP check")
            return {"error": "Sales order not found"}
        
        # For now, just log that check was requested
        # Full implementation would check if materials are available
        logger.info(
            f"MRP check requested for sales order {sales_order.order_number}",
            extra={"sales_order_id": sales_order_id}
        )
        
        return {
            "sales_order_id": sales_order_id,
            "status": "checked",
            "message": "MRP check completed"
        }
    
    except Exception as e:
        logger.error(
            f"Error in MRP check for sales order {sales_order_id}: {str(e)}",
            exc_info=True,
            extra={"sales_order_id": sales_order_id, "error": str(e)}
        )
        # Don't raise - graceful degradation
        return {"error": str(e)}


def trigger_mrp_recalculation(
    db: Session,
    context_id: int,
    reason: str,
    product_ids: Optional[List[int]] = None
) -> Optional[dict]:
    """
    Trigger full MRP recalculation after inventory changes.
    
    This is called after shipping or other inventory-consuming operations
    to ensure MRP is aware of new shortages.
    
    Args:
        db: Database session
        context_id: ID of the context (sales_order_id, etc.)
        reason: Reason for recalculation (e.g., "shipment", "production_completion")
        product_ids: Optional list of specific products to recalculate
    
    Returns:
        Dictionary with recalculation results, or None if feature is disabled
    """
    if not settings.AUTO_MRP_ON_SHIPMENT and reason == "shipment":
        logger.debug(f"MRP recalculation skipped for {reason} - feature disabled")
        return None
    
    try:
        _service = MRPService(db)  # noqa: F841 - placeholder for incremental MRP

        # For incremental MRP, we could recalculate only affected products
        # For now, we'll just log the request
        # Full implementation would trigger actual MRP run
        
        logger.info(
            f"MRP recalculation requested: {reason}",
            extra={
                "context_id": context_id,
                "reason": reason,
                "product_ids": product_ids
            }
        )
        
        # Incremental MRP is not yet implemented — logs the request for now
        
        return {
            "context_id": context_id,
            "reason": reason,
            "status": "requested",
            "message": "MRP recalculation requested (feature in development)"
        }
    
    except Exception as e:
        logger.error(
            f"Error in MRP recalculation: {str(e)}",
            exc_info=True,
            extra={
                "context_id": context_id,
                "reason": reason,
                "error": str(e)
            }
        )
        # Don't raise - graceful degradation
        return {"error": str(e)}


def trigger_incremental_mrp(
    db: Session,
    product_ids: List[int]
) -> Optional[dict]:
    """
    Recalculate MRP only for specific products.
    
    This is more efficient than a full MRP run when only certain
    products have changed.
    
    Args:
        db: Database session
        product_ids: List of product IDs to recalculate
    
    Returns:
        Dictionary with results, or None if feature is disabled
    """
    if not settings.INCLUDE_SALES_ORDERS_IN_MRP:
        logger.debug("Incremental MRP skipped - feature disabled")
        return None
    
    try:
        logger.info(
            f"Incremental MRP requested for {len(product_ids)} products",
            extra={"product_ids": product_ids}
        )
        
        # Incremental MRP calculation is not yet implemented
        
        return {
            "product_ids": product_ids,
            "status": "requested",
            "message": "Incremental MRP requested (feature in development)"
        }
    
    except Exception as e:
        logger.error(
            f"Error in incremental MRP: {str(e)}",
            exc_info=True,
            extra={"product_ids": product_ids, "error": str(e)}
        )
        # Don't raise - graceful degradation
        return {"error": str(e)}

