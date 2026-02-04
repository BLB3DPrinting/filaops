"""
Traceability API Endpoints - Serial Numbers, Material Lots, and Recall Queries

Supports tiered traceability for B2B compliance:
- NONE: No tracking (B2C default)
- LOT: Batch tracking only
- SERIAL: Individual part tracking
- FULL: LOT + SERIAL + Certificate of Conformance

Business logic lives in ``app.services.traceability_service``.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.schemas.traceability import (
    # Customer Profiles
    CustomerTraceabilityProfileCreate,
    CustomerTraceabilityProfileUpdate,
    CustomerTraceabilityProfileResponse,
    # Material Lots
    MaterialLotCreate,
    MaterialLotUpdate,
    MaterialLotResponse,
    MaterialLotListResponse,
    # Serial Numbers
    SerialNumberCreate,
    SerialNumberUpdate,
    SerialNumberResponse,
    SerialNumberListResponse,
    # Lot Consumption
    ProductionLotConsumptionCreate,
    ProductionLotConsumptionResponse,
    # Recall Queries
    RecallForwardQueryResponse,
    RecallBackwardQueryResponse,
)
from app.services import traceability_service as svc

router = APIRouter(prefix="/traceability", tags=["Traceability"])


# =============================================================================
# Customer Traceability Profiles
# =============================================================================

@router.get("/profiles", response_model=List[CustomerTraceabilityProfileResponse])
async def list_traceability_profiles(
    traceability_level: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all customer traceability profiles."""
    return svc.list_traceability_profiles(db, traceability_level=traceability_level)


@router.get("/profiles/{user_id}", response_model=CustomerTraceabilityProfileResponse)
async def get_traceability_profile(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get traceability profile for a specific customer."""
    return svc.get_traceability_profile(db, user_id)


@router.post("/profiles", response_model=CustomerTraceabilityProfileResponse)
async def create_traceability_profile(
    request: CustomerTraceabilityProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a traceability profile for a customer."""
    return svc.create_traceability_profile(db, request)


@router.patch("/profiles/{user_id}", response_model=CustomerTraceabilityProfileResponse)
async def update_traceability_profile(
    user_id: int,
    request: CustomerTraceabilityProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a customer's traceability profile."""
    return svc.update_traceability_profile(db, user_id, request)


# =============================================================================
# Material Lots
# =============================================================================

@router.get("/lots", response_model=MaterialLotListResponse)
async def list_material_lots(
    product_id: Optional[int] = None,
    status: Optional[str] = None,
    vendor_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List material lots with filtering and pagination."""
    return svc.list_material_lots(
        db,
        product_id=product_id,
        status=status,
        vendor_id=vendor_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/lots/{lot_id}", response_model=MaterialLotResponse)
async def get_material_lot(
    lot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific material lot by ID."""
    return svc.get_material_lot(db, lot_id)


@router.post("/lots", response_model=MaterialLotResponse)
async def create_material_lot(
    request: MaterialLotCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new material lot (typically when receiving materials)."""
    return svc.create_material_lot(db, request)


@router.patch("/lots/{lot_id}", response_model=MaterialLotResponse)
async def update_material_lot(
    lot_id: int,
    request: MaterialLotUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a material lot."""
    return svc.update_material_lot(db, lot_id, request)


@router.post("/lots/generate-number")
async def generate_lot_number(
    material_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate the next lot number for a material."""
    return svc.generate_lot_number(db, material_code)


# =============================================================================
# Serial Numbers
# =============================================================================

@router.get("/serials", response_model=SerialNumberListResponse)
async def list_serial_numbers(
    product_id: Optional[int] = None,
    production_order_id: Optional[int] = None,
    status: Optional[str] = None,
    sales_order_id: Optional[int] = None,
    search: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List serial numbers with filtering and pagination."""
    return svc.list_serial_numbers(
        db,
        product_id=product_id,
        production_order_id=production_order_id,
        status=status,
        sales_order_id=sales_order_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/serials/{serial_id}", response_model=SerialNumberResponse)
async def get_serial_number(
    serial_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific serial number by ID."""
    return svc.get_serial_number(db, serial_id)


@router.get("/serials/lookup/{serial_number}", response_model=SerialNumberResponse)
async def lookup_serial_number(
    serial_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Look up a serial number by the serial string."""
    return svc.lookup_serial_number(db, serial_number)


@router.post("/serials", response_model=List[SerialNumberResponse])
async def create_serial_numbers(
    request: SerialNumberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate serial numbers for a production order."""
    return svc.create_serial_numbers(db, request)


@router.patch("/serials/{serial_id}", response_model=SerialNumberResponse)
async def update_serial_number(
    serial_id: int,
    request: SerialNumberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a serial number (e.g., mark as sold, shipped, returned)."""
    return svc.update_serial_number(db, serial_id, request)


# =============================================================================
# Lot Consumption Recording
# =============================================================================

@router.post("/consumptions", response_model=ProductionLotConsumptionResponse)
async def record_lot_consumption(
    request: ProductionLotConsumptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record material lot consumption for a production order."""
    return svc.record_lot_consumption(db, request)


@router.get("/consumptions/production/{production_order_id}")
async def get_production_lot_consumptions(
    production_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all lot consumptions for a production order."""
    return svc.get_production_lot_consumptions(db, production_order_id)


# =============================================================================
# Recall Queries
# =============================================================================

@router.get("/recall/forward/{lot_number}", response_model=RecallForwardQueryResponse)
async def recall_forward_query(
    lot_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Forward recall query: What did we make with this lot?

    Returns all products/serial numbers that used material from this lot.
    """
    return svc.recall_forward_query(db, lot_number)


@router.get("/recall/backward/{serial_number}", response_model=RecallBackwardQueryResponse)
async def recall_backward_query(
    serial_number: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Backward recall query: What material lots went into this serial number?

    Returns all material lots used to produce this unit.
    """
    return svc.recall_backward_query(db, serial_number)
