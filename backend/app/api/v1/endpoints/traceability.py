"""
Material Traceability API Endpoints

Provides forward and backward traceability for quality management.
Enables DHR (Device History Record) generation and recall impact analysis.
Business logic lives in ``app.services.traceability_service``.
"""
from fastapi import APIRouter, Depends
from typing import List
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.logging_config import get_logger
from app.services import traceability_service as svc

router = APIRouter()
logger = get_logger(__name__)

# ============================================================================
# Forward Traceability (Spool -> Products -> Customers)
# ============================================================================

@router.get("/forward/spool/{spool_id}")
async def trace_forward_from_spool(
    spool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trace a spool forward to all products and customers.

    Returns:
    - Spool details (material, lot, vendor)
    - All production orders that used this spool
    - All sales orders linked to those production orders
    - Serial numbers produced
    - Customer information
    """
    return svc.trace_forward_from_spool(db, spool_id)

# ============================================================================
# Backward Traceability (Product -> Spools -> Vendor)
# ============================================================================

@router.get("/backward/serial/{serial_number}")
async def trace_backward_from_serial(
    serial_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trace a serial number back to source materials and vendor.

    Returns:
    - Serial number details
    - Production order details
    - Product details
    - All spools used in production
    - Purchase order and vendor info for each spool
    - Sales order info
    """
    return svc.trace_backward_from_serial(db, serial_number)

@router.get("/backward/sales-order/{so_id}")
async def trace_backward_from_sales_order(
    so_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trace a sales order back to all source materials.

    Useful for: "What materials went into this entire order?"
    """
    return svc.trace_backward_from_sales_order(db, so_id)

# ============================================================================
# Recall Impact Analysis
# ============================================================================

@router.post("/recall-impact")
async def calculate_recall_impact(
    spool_ids: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calculate the impact of recalling specific spools.

    Returns:
    - All affected production orders
    - All affected sales orders
    - All affected customers
    - All affected serial numbers
    """
    return svc.calculate_recall_impact(db, spool_ids)
