"""
Import functionality for products, inventory

Business logic lives in ``app.services.data_import_service``.
"""
import logging

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.deps import get_current_staff_user
from app.core.limiter import limiter
from app.models.user import User
from app.services import data_import_service as svc

logger = logging.getLogger(__name__)

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
@limiter.limit("30/minute")  # type: ignore
async def import_products(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_staff_user),
    db: Session = Depends(get_db),
):
    """Import products from CSV."""
    text = await _read_csv_upload(file)
    try:
        return svc.import_products(db, text)
    except HTTPException:
        raise
    except Exception:
        logger.error("Product import failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Product import failed. Check server logs for details.")


@router.post("/inventory")
@limiter.limit("30/minute")  # type: ignore
async def import_inventory(
    request: Request,
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
    try:
        return svc.import_inventory(db, text)
    except HTTPException:
        raise
    except Exception:
        logger.error("Inventory import failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Inventory import failed. Check server logs for details.")
