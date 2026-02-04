"""
BOM Management Endpoints (Admin Only)

Handles Bill of Materials viewing, editing, and approval.
Business logic lives in ``app.services.bom_management_service``.
"""
from typing import Optional, List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.api.v1.deps import get_current_staff_user
from app.logging_config import get_logger
from app.schemas.bom import (
    BOMCreate,
    BOMUpdate,
    BOMListResponse,
    BOMResponse,
    BOMLineCreate,
    BOMLineUpdate,
    BOMLineResponse,
    BOMRecalculateResponse,
    BOMCopyRequest,
)
from app.services import bom_management_service as svc

router = APIRouter(prefix="/bom", tags=["Admin - BOM Management"])

logger = get_logger(__name__)


# ============================================================================
# LIST & GET ENDPOINTS
# ============================================================================

@router.get("/", response_model=List[BOMListResponse])
async def list_boms(
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    product_id: Optional[int] = None,
    active_only: bool = True,
    search: Optional[str] = None,
):
    """
    List all BOMs with summary info.

    Admin only. Supports filtering by product, active status, and search.
    """
    return svc.list_boms(
        db,
        product_id=product_id,
        active_only=active_only,
        search=search,
        skip=skip,
        limit=limit,
    )


@router.get("/{bom_id}", response_model=BOMResponse)
async def get_bom(
    bom_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Get a single BOM with all lines and component details.

    Admin only.
    """
    return svc.get_bom_detail(db, bom_id)


# ============================================================================
# CREATE & UPDATE ENDPOINTS
# ============================================================================

@router.post("/", response_model=BOMResponse, status_code=status.HTTP_201_CREATED)
async def create_bom(
    bom_data: BOMCreate,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
    force_new: bool = Query(False, description="Force creating a new BOM version even if one exists"),
):
    """
    Create or update a BOM for a product.

    Admin only. If an active BOM already exists for the product:
    - By default, adds the provided lines to the existing BOM (upsert behavior)
    - If force_new=True, deactivates the old BOM and creates a new version

    This prevents accidental creation of duplicate BOMs.
    """
    result = svc.create_bom(db, bom_data, force_new)

    logger.info(
        "BOM created/upserted",
        extra={
            "bom_id": result["id"],
            "product_id": result["product_id"],
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
        }
    )

    return result


@router.patch("/{bom_id}", response_model=BOMResponse)
async def update_bom(
    bom_id: int,
    bom_data: BOMUpdate,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Update BOM header fields (not lines).

    Admin only. Use line-specific endpoints to modify lines.
    """
    result = svc.update_bom_header(db, bom_id, bom_data)

    logger.info(
        "BOM updated",
        extra={
            "bom_id": bom_id,
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
        }
    )

    return result


@router.delete("/{bom_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bom(
    bom_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Delete a BOM (soft delete by setting active=False).

    Admin only.
    """
    svc.deactivate_bom(db, bom_id)

    logger.info(
        "BOM deactivated",
        extra={
            "bom_id": bom_id,
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
        }
    )


# ============================================================================
# BOM LINE ENDPOINTS
# ============================================================================

@router.post("/{bom_id}/lines", response_model=BOMLineResponse, status_code=status.HTTP_201_CREATED)
async def add_bom_line(
    bom_id: int,
    line_data: BOMLineCreate,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Add a new line to a BOM.

    Admin only.
    """
    result = svc.add_bom_line(db, bom_id, line_data)

    logger.info(
        "BOM line added",
        extra={
            "bom_id": bom_id,
            "line_id": result["id"],
            "component_id": result["component_id"],
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
        }
    )

    return result


@router.patch("/{bom_id}/lines/{line_id}", response_model=BOMLineResponse)
async def update_bom_line(
    bom_id: int,
    line_id: int,
    line_data: BOMLineUpdate,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Update a BOM line.

    Admin only.
    """
    result = svc.update_bom_line(db, bom_id, line_id, line_data)

    logger.info(
        "BOM line updated",
        extra={
            "bom_id": bom_id,
            "line_id": line_id,
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
        }
    )

    return result


@router.delete("/{bom_id}/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bom_line(
    bom_id: int,
    line_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Delete a BOM line.

    Admin only.
    """
    svc.delete_bom_line(db, bom_id, line_id)

    logger.info(
        "BOM line deleted",
        extra={
            "bom_id": bom_id,
            "line_id": line_id,
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
        }
    )


# ============================================================================
# BULK & UTILITY ENDPOINTS
# ============================================================================

@router.post("/{bom_id}/recalculate", response_model=BOMRecalculateResponse)
async def recalculate_bom(
    bom_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Recalculate BOM total cost from current component costs.

    Admin only. Useful after component prices change.
    """
    result = svc.recalculate_bom_endpoint(db, bom_id)

    logger.info(
        "BOM recalculated",
        extra={
            "bom_id": bom_id,
            "previous_cost": str(result["previous_cost"]),
            "new_cost": str(result["new_cost"]),
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
        }
    )

    return result


@router.post("/{bom_id}/copy", response_model=BOMResponse, status_code=status.HTTP_201_CREATED)
async def copy_bom(
    bom_id: int,
    copy_data: BOMCopyRequest,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Copy a BOM to another product.

    Admin only. Useful for creating similar products.
    """
    result = svc.copy_bom(db, bom_id, copy_data)

    logger.info(
        "BOM copied",
        extra={
            "source_bom_id": bom_id,
            "new_bom_id": result["id"],
            "target_product_id": result["product_id"],
            "admin_id": current_admin.id,
            "admin_email": current_admin.email,
        }
    )

    return result


@router.get("/product/{product_id}", response_model=BOMResponse)
async def get_bom_by_product(
    product_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Get the active BOM for a product.

    Admin only. Returns the most recent active BOM.
    """
    return svc.get_bom_by_product(db, product_id)


# ============================================================================
# SUB-ASSEMBLY / MULTI-LEVEL BOM ENDPOINTS
# ============================================================================

@router.get("/{bom_id}/explode")
async def explode_bom(
    bom_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
    max_depth: int = Query(10, ge=1, le=20),
    flatten: bool = Query(False, description="If true, aggregate quantities for duplicate components"),
):
    """
    Explode a BOM to show all components at all levels.

    This recursively expands sub-assemblies to show the full material requirements.

    - **max_depth**: Maximum levels to expand (default 10, max 20)
    - **flatten**: If true, consolidates duplicate components into single rows with summed quantities
    """
    return svc.explode_bom(db, bom_id, max_depth=max_depth, flatten=flatten)


@router.get("/{bom_id}/cost-rollup")
async def get_cost_rollup(
    bom_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Get a detailed cost breakdown with sub-assembly costs rolled up.

    Shows each component's contribution to total cost, including nested sub-assemblies.
    """
    return svc.get_cost_rollup(db, bom_id)


@router.get("/where-used/{product_id}")
async def where_used(
    product_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
    include_inactive: bool = False,
):
    """
    Find all BOMs that use a specific product as a component.

    Useful for understanding impact of component changes.

    - **product_id**: The component to search for
    - **include_inactive**: Include inactive BOMs in results
    """
    return svc.where_used(db, product_id, include_inactive=include_inactive)


@router.post("/{bom_id}/validate")
async def validate_bom(
    bom_id: int,
    current_admin: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """
    Validate a BOM for issues like circular references, missing costs, etc.

    Returns a list of warnings and errors.
    """
    return svc.validate_bom(db, bom_id)
