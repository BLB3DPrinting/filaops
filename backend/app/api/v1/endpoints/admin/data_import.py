"""
Import functionality for products, inventory

Business logic lives in ``app.services.data_import_service``.
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.models.user import User
from app.services import data_import_service as svc

router = APIRouter(prefix="/import", tags=["import"])


@router.post("/products")
async def import_products(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Import products from CSV."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be CSV")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    if text.startswith("\ufeff"):
        text = text[1:]

    return svc.import_products(db, text)


@router.post("/inventory")
async def import_inventory(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Import inventory from CSV.

    Expected columns:
    - SKU (required): Product SKU
    - Quantity (required): Quantity to set/add
    - Location: Warehouse/location code (defaults to MAIN)
    - Lot Number: Lot number for tracking (optional)
    - Mode: 'set' to set quantity, 'add' to add to existing (default: set)
    """
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be CSV")

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    if text.startswith("\ufeff"):
        text = text[1:]

    return svc.import_inventory(db, text)
