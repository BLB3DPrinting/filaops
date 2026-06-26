"""QC Inspection Photos API endpoints (#784 QMS).

Multi-photo attachment for a QC inspection — defect/evidence images captured
during inspection. Its own table (``qc_inspection_photos``) and its own upload
directory; the column + upload conventions mirror ``purchase_order_documents``
but the two file sets never share storage.

Every route is gated by the quality "dial": when ``quality_mode`` is ``off`` the
surface is hidden (403), honoring the graceful-no-op contract. Photos are
available in ``basic`` and ``full``.
"""
import os
import uuid
import mimetypes
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.core.paths import resolve_upload_qc_photos_dir
from app.core.settings import settings
from app.db.session import get_db
from app.logging_config import get_logger
from app.models.production_order import QCInspection, QCInspectionPhoto
from app.models.user import User
from app.schemas.quality import QCPhotoResponse, QCPhotoUpdate
from app.services.quality_policy import get_quality_policy

router = APIRouter()
logger = get_logger(__name__)

# Dedicated upload directory (NOT shared with po_documents). Resolved at import;
# default <backend>/uploads/qc_photos, override via UPLOAD_QC_PHOTOS_DIR.
UPLOAD_DIR = resolve_upload_qc_photos_dir(settings.UPLOAD_QC_PHOTOS_DIR)

# Images only — QC evidence is photographic.
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"}
# Cap a single photo so storage stays bounded; phone photos are well under this.
MAX_PHOTO_BYTES = 25 * 1024 * 1024  # 25 MB


def _ensure_upload_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(original: str, inspection_id: int) -> str:
    """Unique on-disk name: qc<inspection>_<timestamp>_<rand>.<ext>."""
    ext = os.path.splitext(original)[1].lower() or ".jpg"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"qc{inspection_id}_{stamp}_{uuid.uuid4().hex[:8]}{ext}"


def _photo_to_response(photo: QCInspectionPhoto) -> QCPhotoResponse:
    return QCPhotoResponse(
        id=photo.id,
        qc_inspection_id=photo.qc_inspection_id,
        file_name=photo.file_name,
        caption=photo.caption,
        mime_type=photo.mime_type,
        file_size=photo.file_size,
        storage_type=photo.storage_type,
        uploaded_by=photo.uploaded_by,
        created_at=photo.created_at.isoformat() if photo.created_at else None,
        download_url=(
            f"/api/v1/production-orders/qc-inspections/"
            f"{photo.qc_inspection_id}/photos/{photo.id}/download"
        ),
    )


def _require_quality_enabled(db: Session) -> None:
    """403 when the QC dial is off — photos are a QC surface (graceful no-op)."""
    if get_quality_policy(db).is_off:
        raise HTTPException(
            status_code=403,
            detail="Quality module is disabled (quality_mode=off)",
        )


def _get_inspection_or_404(db: Session, inspection_id: int) -> QCInspection:
    inspection = (
        db.query(QCInspection).filter(QCInspection.id == inspection_id).first()
    )
    if inspection is None:
        raise HTTPException(status_code=404, detail="QC inspection not found")
    return inspection


def _get_photo_or_404(
    db: Session, inspection_id: int, photo_id: int
) -> QCInspectionPhoto:
    photo = (
        db.query(QCInspectionPhoto)
        .filter(
            QCInspectionPhoto.id == photo_id,
            QCInspectionPhoto.qc_inspection_id == inspection_id,
        )
        .first()
    )
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo


@router.post(
    "/{inspection_id}/photos", response_model=QCPhotoResponse, status_code=201
)
async def upload_photo(
    inspection_id: int,
    file: UploadFile = File(...),
    caption: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Attach a photo to a QC inspection. Images only, max 25 MB."""
    _require_quality_enabled(db)
    _get_inspection_or_404(db, inspection_id)

    # Bound the caption to the column width (String(255)) so an over-long value
    # fails fast with a 4xx instead of erroring at commit on a strict DB.
    if caption is not None and len(caption) > 255:
        raise HTTPException(
            status_code=400, detail="caption must be 255 characters or fewer"
        )

    original = file.filename or "photo"
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type {ext or '(none)'!r} not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
            ),
        )

    content = await file.read()
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Photo too large (max {MAX_PHOTO_BYTES // (1024 * 1024)} MB)",
        )

    mime_type = (
        file.content_type
        or mimetypes.guess_type(original)[0]
        or "application/octet-stream"
    )
    safe_name = _safe_filename(original, inspection_id)
    _ensure_upload_dir()
    local_path = os.path.join(UPLOAD_DIR, safe_name)
    # Write the blob and the row together: if the commit fails, remove the file
    # we just wrote so it can't orphan under uploads/qc_photos.
    try:
        with open(local_path, "wb") as fh:
            fh.write(content)

        photo = QCInspectionPhoto(
            qc_inspection_id=inspection_id,
            file_name=safe_name,
            file_path=local_path,
            storage_type="local",
            mime_type=mime_type,
            file_size=len(content),
            caption=caption,
            uploaded_by=current_user.email,
        )
        db.add(photo)
        db.commit()
        db.refresh(photo)
    except Exception:
        db.rollback()
        if os.path.exists(local_path):
            os.remove(local_path)
        raise
    logger.info("QC photo %s uploaded for inspection %s", photo.id, inspection_id)
    return _photo_to_response(photo)


@router.get("/{inspection_id}/photos", response_model=List[QCPhotoResponse])
def list_photos(
    inspection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List photos for a QC inspection, newest first."""
    _require_quality_enabled(db)
    _get_inspection_or_404(db, inspection_id)
    photos = (
        db.query(QCInspectionPhoto)
        .filter(QCInspectionPhoto.qc_inspection_id == inspection_id)
        .order_by(desc(QCInspectionPhoto.created_at), desc(QCInspectionPhoto.id))
        .all()
    )
    return [_photo_to_response(p) for p in photos]


@router.get("/{inspection_id}/photos/{photo_id}/download")
def download_photo(
    inspection_id: int,
    photo_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream the image bytes for a QC photo."""
    _require_quality_enabled(db)
    photo = _get_photo_or_404(db, inspection_id, photo_id)
    if photo.file_path and os.path.exists(photo.file_path):
        return FileResponse(
            path=photo.file_path,
            filename=photo.file_name,
            media_type=photo.mime_type or "application/octet-stream",
        )
    raise HTTPException(status_code=404, detail="File not found on storage")


@router.patch("/{inspection_id}/photos/{photo_id}", response_model=QCPhotoResponse)
def update_photo(
    inspection_id: int,
    photo_id: int,
    body: QCPhotoUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update a photo's caption."""
    _require_quality_enabled(db)
    photo = _get_photo_or_404(db, inspection_id, photo_id)
    if body.caption is not None:
        photo.caption = body.caption
    db.commit()
    db.refresh(photo)
    return _photo_to_response(photo)


@router.delete("/{inspection_id}/photos/{photo_id}")
def delete_photo(
    inspection_id: int,
    photo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a QC photo (DB row + local file)."""
    _require_quality_enabled(db)
    photo = _get_photo_or_404(db, inspection_id, photo_id)
    # Commit the row delete BEFORE removing the blob. If we removed the file first
    # and the commit then failed, the row would survive pointing at a missing file
    # — download would 404 forever. This ordering leaves the file intact on a
    # failed commit instead (a harmless orphan, recoverable).
    local_path = photo.file_path if photo.storage_type == "local" else None
    db.delete(photo)
    db.commit()
    if local_path:
        try:
            if os.path.exists(local_path):
                os.remove(local_path)
        except OSError as exc:
            logger.warning("Could not delete QC photo file %s: %s", local_path, exc)
    logger.info("QC photo %s deleted from inspection %s", photo_id, inspection_id)
    return {"message": "Photo deleted", "id": photo_id}
