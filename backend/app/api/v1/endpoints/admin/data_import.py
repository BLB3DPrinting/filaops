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

MAX_CSV_SIZE = 10 * 1024 * 1024  # 10 MB


async def _read_csv_upload(file: UploadFile) -> str:
    """Validate and read a CSV upload, returning decoded text."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv file")

    if file.content_type and file.content_type not in ("text/csv", "application/octet-stream", "application/vnd.ms-excel"):
        raise HTTPException(status_code=400, detail="Invalid file type. Expected CSV.")

    content = await file.read()

    if len(content) > MAX_CSV_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Maximum size is {MAX_CSV_SIZE // (1024 * 1024)} MB.")

    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    if text.startswith("\ufeff"):
        text = text[1:]

    return text


@router.post("/products")
async def import_products(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Import products from CSV."""
    text = await _read_csv_upload(file)
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
    text = await _read_csv_upload(file)
    return svc.import_inventory(db, text)
