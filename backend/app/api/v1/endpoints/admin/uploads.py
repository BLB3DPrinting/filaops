"""
File Upload Endpoints for Admin

Handles product image uploads and other file uploads.
Files are stored locally and served via static file serving.
"""
import re
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel

from app.core.paths import (
    resolve_legacy_product_images_dir,
    resolve_static_dir,
    resolve_upload_products_dir,
)
from app.core.settings import settings
from app.models.user import User
from app.api.v1.deps import get_current_staff_user
from app.logging_config import get_logger
router = APIRouter()
logger = get_logger(__name__)

# Upload configuration.
#
# Images are written to UPLOAD_DIR (by default <backend>/uploads/products,
# which is /app/uploads/products on Docker's persistent uploads volume) and
# served at /static/uploads/products/<name> by a dedicated mount in app.main.
# LEGACY_DIR is the old in-container default; it is only read (by that mount)
# and cleaned up (by delete), never written.
#
# A packaged install can override STATIC_DIR and/or UPLOAD_PRODUCTS_DIR to
# point at writable per-user directories (see app.core.paths).
UPLOAD_DIR = resolve_upload_products_dir(
    settings.UPLOAD_PRODUCTS_DIR, static_override=settings.STATIC_DIR
)
LEGACY_DIR = resolve_legacy_product_images_dir(
    resolve_static_dir(settings.STATIC_DIR)
)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


class UploadResponse(BaseModel):
    """Response for successful file upload"""
    filename: str
    url: str
    size: int


def get_file_extension(filename: str) -> str:
    """Get lowercase file extension"""
    return Path(filename).suffix.lower()


def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


# Exactly the names upload_product_image generates: uuid4().hex plus a
# lowercased allowed extension. Anything else (including "." and "..") was
# never stored by this endpoint and is refused before any path is built.
_STORED_IMAGE_NAME = re.compile(
    r"[0-9a-f]{32}(?:"
    + "|".join(re.escape(ext) for ext in sorted(ALLOWED_EXTENSIONS))
    + r")"
)


def _find_stored_image(filename: str) -> Path | None:
    """Return the stored image file for ``filename``, or None.

    Looks in UPLOAD_DIR, then LEGACY_DIR (images saved before the move to the
    uploads volume). Each candidate is resolved and must stay inside its
    resolved base directory.
    """
    for base in (UPLOAD_DIR, LEGACY_DIR):
        base_dir = base.resolve()
        candidate = (base_dir / filename).resolve()
        if not candidate.is_relative_to(base_dir):
            continue
        if candidate.is_file():
            return candidate
    return None


@router.post("/product-image", response_model=UploadResponse)
async def upload_product_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_staff_user)
):
    """
    Upload a product image.

    Accepts: JPG, JPEG, PNG, WEBP, GIF
    Max size: 5MB

    Returns the URL to access the uploaded image.
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not is_allowed_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Accepted: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Validate file size
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)}MB"
        )

    # Generate unique filename
    ext = get_file_extension(file.filename)
    unique_filename = f"{uuid.uuid4().hex}{ext}"

    # Ensure upload directory exists
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Save file
    file_path = UPLOAD_DIR / unique_filename
    try:
        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"Uploaded product image: {unique_filename} ({file_size} bytes) by user {current_user.id}")

        # Build URL - uses the static file serving path
        image_url = f"/static/uploads/products/{unique_filename}"

        return UploadResponse(
            filename=unique_filename,
            url=image_url,
            size=file_size
        )

    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        # Clean up partial file if it exists
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail="Failed to save file")


@router.delete("/product-image/{filename}")
async def delete_product_image(
    filename: str,
    current_user: User = Depends(get_current_staff_user)
):
    """
    Delete a previously uploaded product image.

    Accepts only names this endpoint's upload generates, and only deletes
    files inside UPLOAD_DIR or LEGACY_DIR (prevents path traversal).
    """
    if not _STORED_IMAGE_NAME.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = _find_stored_image(filename)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()
        logger.info(f"Deleted product image: {filename} by user {current_user.id}")
        return {"message": "File deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete file {filename}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete file")
