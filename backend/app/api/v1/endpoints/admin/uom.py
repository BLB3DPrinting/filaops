"""
Unit of Measure (UOM) Management Endpoints

Provides CRUD operations for units of measure and conversion utilities.
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.uom import UnitOfMeasure
from app.api.v1.deps import get_current_admin_user
from app.models.user import User
from app.logging_config import get_logger
from app.schemas.uom import (
    UOMResponse,
    UOMListResponse,
    UOMClassResponse,
    UOMCreate,
    UOMUpdate,
    ConvertRequest,
    ConvertResponse,
)
from app.services.uom_service import (
    get_all_uom_classes,
    get_units_by_class,
    UOMConversionError,
)
from app.services.unit_conversion import physical_factor, tidy_unit_code
from app.services.unit_table_rules import check_unit_update, find_unit, new_unit_values

router = APIRouter(prefix="/uom", tags=["Admin - Units of Measure"])

logger = get_logger(__name__)


def _base_code(db: Session, uom: UnitOfMeasure):
    """The code of a unit's base unit, or None."""
    if not uom.base_unit_id:
        return None
    base = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom.base_unit_id).first()
    return base.code if base else None


# ============================================================================
# LIST UNITS
# ============================================================================

@router.get("/", response_model=List[UOMListResponse])
async def list_units(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    uom_class: str = None,
    active_only: bool = True,
):
    """
    List all units of measure.

    Optional filter by class (quantity, weight, length, time).
    """
    query = db.query(UnitOfMeasure)

    if active_only:
        query = query.filter(UnitOfMeasure.active.is_(True))  # noqa: E712

    if uom_class:
        query = query.filter(UnitOfMeasure.uom_class == uom_class)

    query = query.order_by(UnitOfMeasure.uom_class, UnitOfMeasure.code)

    return query.all()


@router.get("/classes", response_model=List[UOMClassResponse])
async def list_unit_classes(
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    List all UOM classes with their units.

    Returns grouped response for UI dropdowns.
    """
    classes = get_all_uom_classes(db)
    result = []

    for uom_class in sorted(classes):
        units = get_units_by_class(db, uom_class)
        result.append(UOMClassResponse(
            uom_class=uom_class,
            units=[UOMListResponse(
                id=u.id,
                code=u.code,
                name=u.name,
                symbol=u.symbol,
                uom_class=u.uom_class,
            ) for u in units]
        ))

    return result


# ============================================================================
# CONVERT QUANTITY
# ============================================================================

@router.post("/convert", response_model=ConvertResponse)
async def convert_units(
    request: ConvertRequest,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Convert a quantity from one unit to another.

    Units must be in the same class (e.g., weight, length).
    """
    try:
        factor = physical_factor(db, request.from_unit, request.to_unit)
        return ConvertResponse(
            original_quantity=request.quantity,
            original_unit=tidy_unit_code(db, request.from_unit),
            converted_quantity=request.quantity * factor,
            converted_unit=tidy_unit_code(db, request.to_unit),
            conversion_factor=factor,
        )
    except UOMConversionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


# ============================================================================
# GET UNIT
# ============================================================================

@router.get("/{code}", response_model=UOMResponse)
async def get_unit(
    code: str,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Get a single unit of measure by code, switched on or off.
    """
    uom = find_unit(db, code)
    if not uom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit not found: {code}"
        )

    # Add base unit code if applicable
    base_code = None
    if uom.base_unit_id:
        base_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom.base_unit_id).first()
        if base_unit:
            base_code = base_unit.code

    return UOMResponse(
        id=uom.id,
        code=uom.code,
        name=uom.name,
        symbol=uom.symbol,
        uom_class=uom.uom_class,
        base_unit_id=uom.base_unit_id,
        base_unit_code=base_code,
        to_base_factor=uom.to_base_factor,
        active=uom.active,
    )


# ============================================================================
# CREATE UNIT
# ============================================================================

@router.post("/", response_model=UOMResponse, status_code=status.HTTP_201_CREATED)
async def create_unit(
    request: UOMCreate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Create a new unit of measure.

    For derived units (non-base units), provide base_unit_code.
    """
    # The unit rules: a pack, or a weight, length, area, volume or time unit
    # with its factor to that kind's base. See app/services/unit_table_rules.py.
    values = new_unit_values(
        db,
        code=request.code,
        kind=request.uom_class,
        factor=request.to_base_factor if request.uom_class.strip().lower() != "pack" else None,
        base_unit_code=request.base_unit_code,
    )
    uom = UnitOfMeasure(name=request.name, symbol=request.symbol, active=True, **values)
    db.add(uom)
    db.commit()
    db.refresh(uom)

    logger.info(f"Created UOM: {uom.code} ({uom.name})")

    return UOMResponse(
        id=uom.id,
        code=uom.code,
        name=uom.name,
        symbol=uom.symbol,
        uom_class=uom.uom_class,
        base_unit_id=uom.base_unit_id,
        base_unit_code=_base_code(db, uom),
        to_base_factor=uom.to_base_factor,
        active=uom.active,
    )


# ============================================================================
# UPDATE UNIT
# ============================================================================

@router.patch("/{code}", response_model=UOMResponse)
async def update_unit(
    code: str,
    request: UOMUpdate,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Update an existing unit of measure.
    
    Note: Changing base_unit_code or uom_class is not allowed.
    These structural properties cannot be modified after creation
    to maintain data integrity and prevent conversion errors.
    """
    uom = find_unit(db, code)
    if not uom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unit not found: {code}"
        )

    # Explicitly reject attempts to change structural fields
    # These fields are not in UOMUpdate schema, but this protects
    # against future schema changes or direct API manipulation
    update_dict = request.model_dump(exclude_unset=True)
    forbidden_fields = {'base_unit_code', 'base_unit_id', 'uom_class', 'code'}
    attempted_forbidden = forbidden_fields.intersection(update_dict.keys())
    
    if attempted_forbidden:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify structural fields via PATCH: {', '.join(sorted(attempted_forbidden))}. "
                   f"Base unit and UOM class cannot be changed after creation to maintain data integrity."
        )

    # A standard unit keeps its factor and stays on; a unit in use stays on.
    new_factor = check_unit_update(db, uom, factor=request.to_base_factor, active=request.active)

    if request.name is not None:
        uom.name = request.name
    if request.symbol is not None:
        uom.symbol = request.symbol
    if new_factor is not None:
        uom.to_base_factor = new_factor
    if request.active is not None:
        uom.active = request.active

    db.commit()
    db.refresh(uom)

    logger.info(f"Updated UOM: {uom.code}")

    base_code = None
    if uom.base_unit_id:
        base_unit = db.query(UnitOfMeasure).filter(UnitOfMeasure.id == uom.base_unit_id).first()
        if base_unit:
            base_code = base_unit.code

    return UOMResponse(
        id=uom.id,
        code=uom.code,
        name=uom.name,
        symbol=uom.symbol,
        uom_class=uom.uom_class,
        base_unit_id=uom.base_unit_id,
        base_unit_code=base_code,
        to_base_factor=uom.to_base_factor,
        active=uom.active,
    )
