"""
MRP Trigger Service

Centralised entry points for automatic MRP checks that are wired to business
events (sales-order creation, shipment).  These are *feature-flagged stubs*.
The underlying MRP engine (MRPService.run_mrp) is a full, regenerative run
that commits its own transactions and is too heavyweight to invoke inside an
order-creation or shipment request without dedicated background-task wiring.

Until that wiring is built (follow-up task), every function in this module
returns ``{"status": "not_implemented"}`` when the flag is enabled so that
callers can see the flag is on without being misled into thinking work was done.
When the flag is off the functions return ``None`` as before.

Flags:
- AUTO_MRP_ON_ORDER_CREATE  governs trigger_mrp_check
- AUTO_MRP_ON_SHIPMENT      governs trigger_mrp_recalculation (reason="shipment")
- INCLUDE_SALES_ORDERS_IN_MRP governs trigger_incremental_mrp

No function may claim completion for work it did not perform.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from app.core.settings import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()

_NOT_IMPLEMENTED = {
    "status": "not_implemented",
    "message": (
        "Automatic MRP runs are not yet implemented. "
        "Enable AUTO_MRP_ON_ORDER_CREATE / AUTO_MRP_ON_SHIPMENT only after "
        "background-task wiring is complete."
    ),
}


def trigger_mrp_check(
    db: Session,
    sales_order_id: int,
    background: bool = False
) -> Optional[dict]:
    """
    Stub: intended to trigger a scoped MRP check for a specific sales order.

    STUB — automatic MRP runs are not yet implemented.  When
    AUTO_MRP_ON_ORDER_CREATE is enabled this function acknowledges the request
    but performs no calculation and returns ``{"status": "not_implemented"}``.
    Returns ``None`` when the flag is off.

    Args:
        db: Database session (unused by stub; retained for future wiring)
        sales_order_id: ID of the sales order that triggered the check
        background: Reserved for future background-task routing
    """
    if not settings.AUTO_MRP_ON_ORDER_CREATE:
        logger.debug(
            "MRP check skipped for SO %s — AUTO_MRP_ON_ORDER_CREATE is disabled",
            sales_order_id,
        )
        return None

    logger.debug(
        "MRP check requested for SO %s — stub, no calculation performed",
        sales_order_id,
    )
    return {"sales_order_id": sales_order_id, **_NOT_IMPLEMENTED}


def trigger_mrp_recalculation(
    db: Session,
    context_id: int,
    reason: str,
    product_ids: Optional[List[int]] = None
) -> Optional[dict]:
    """
    Stub: intended to trigger MRP recalculation after inventory-consuming events.

    STUB — automatic MRP runs are not yet implemented.  When
    AUTO_MRP_ON_SHIPMENT is enabled and reason is ``"shipment"`` this function
    acknowledges the request but performs no calculation and returns
    ``{"status": "not_implemented"}``.  Returns ``None`` when the flag is off.

    Args:
        db: Database session (unused by stub; retained for future wiring)
        context_id: ID of the context object (e.g., sales_order_id)
        reason: Trigger reason — currently only "shipment" is flag-gated
        product_ids: Reserved for future incremental-scope wiring
    """
    if reason == "shipment" and not settings.AUTO_MRP_ON_SHIPMENT:
        logger.debug(
            "MRP recalculation skipped for %s (%s) — AUTO_MRP_ON_SHIPMENT is disabled",
            context_id,
            reason,
        )
        return None

    logger.debug(
        "MRP recalculation requested for %s (%s) — stub, no calculation performed",
        context_id,
        reason,
    )
    return {"context_id": context_id, "reason": reason, **_NOT_IMPLEMENTED}


def trigger_incremental_mrp(
    db: Session,
    product_ids: List[int]
) -> Optional[dict]:
    """
    Stub: intended to trigger a product-scoped incremental MRP recalculation.

    STUB — incremental (scoped) MRP runs are not yet implemented.  When
    INCLUDE_SALES_ORDERS_IN_MRP is enabled this function acknowledges the
    request but performs no calculation and returns
    ``{"status": "not_implemented"}``.  Returns ``None`` when the flag is off.

    Args:
        db: Database session (unused by stub; retained for future wiring)
        product_ids: Products whose requirements should be recalculated
    """
    if not settings.INCLUDE_SALES_ORDERS_IN_MRP:
        logger.debug("Incremental MRP skipped — INCLUDE_SALES_ORDERS_IN_MRP is disabled")
        return None

    logger.debug(
        "Incremental MRP requested for %d product(s) — stub, no calculation performed",
        len(product_ids),
    )
    return {"product_ids": product_ids, **_NOT_IMPLEMENTED}
