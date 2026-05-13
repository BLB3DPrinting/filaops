"""
File Upload Endpoints for Admin

Handles product image uploads and other file uploads.
Files are stored locally and served via static file serving.
"""
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel

from app.core.paths import resolve_static_dir, resolve_upload_products_dir
from app.core.settings import settings
from app.models.user import User
from app.api.v1.deps import get_current_user
from app.logging_config import get_logger
router = APIRouter()
logger = get_logger(__name__)

# Upload configuration.
#
# Default resolves to ``<STATIC_DIR>/uploads/products`` (kept under the
# /static mount so images stay web-served). Compose with the resolved
# STATIC_DIR — without that, setting only STATIC_DIR (and leaving
# UPLOAD_PRODUCTS_DIR blank) would write images under <backend>/static/...
# while /static serves the overridden root, producing 404s on image URLs.
#
# A packaged install can override either env var (STATIC_DIR and/or
# UPLOAD_PRODUCTS_DIR) to point at writable per-user directories.
_STATIC_DIR = resolve_static_dir(settings.STATIC_DIR)
UPLOAD_DIR = resolve_upload_products_dir(
    settings.UPLOAD_PRODUCTS_DIR, static_dir=_STATIC_DIR
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


@router.post("/product-image", response_model=UploadResponse)
async def upload_product_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
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
    current_user: User = Depends(get_current_user)
):
    """
    Delete a previously uploaded product image.

    Only deletes files in the uploads directory (prevents path traversal).
    """
    # Sanitize filename to prevent path traversal
    safe_filename = Path(filename).name
    if safe_filename != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = UPLOAD_DIR / safe_filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()
        logger.info(f"Deleted product image: {safe_filename} by user {current_user.id}")
        return {"message": "File deleted successfully"}
    except Exception as e:
        logger.error(f"Failed to delete file {safe_filename}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete file")
