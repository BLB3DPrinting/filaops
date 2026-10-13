"""
Database backup endpoints (admin only).

The Backups page reads status and run history here, starts a backup with
"Run backup now", and downloads finished backups. The schedule itself is the
``database_backup`` system setting, edited through ``PUT
/api/v1/system/settings/database_backup``.

Backups contain customer data and password hashes, so every route requires an
admin, and each download is written to the audit log.
"""
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_admin_user
from app.db.session import get_db
from app.logging_config import audit_log, get_logger
from app.models.backup_run import BackupRun
from app.models.user import User
from app.services import database_backup

logger = get_logger(__name__)

router = APIRouter(
    prefix="/backups",
    tags=["Admin - Backups"],
    dependencies=[Depends(get_current_admin_user)],
)


@router.get("")
def get_backup_status(db: Annotated[Session, Depends(get_db)]) -> dict[str, Any]:
    """Schedule, tool versions, storage and the latest runs."""
    return database_backup.get_status(db)


@router.get("/runs")
def list_backup_runs(
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[dict[str, Any]]:
    runs = db.query(BackupRun).order_by(BackupRun.started_at.desc(), BackupRun.id.desc()).limit(limit)
    return [database_backup.run_to_dict(run) for run in runs]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
def run_backup_now(
    request: Request,
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> dict[str, Any]:
    """Start a backup now. It runs in the background; poll GET /backups."""
    try:
        run_id = database_backup.start_backup("manual", triggered_by_id=current_user.id)
    except database_backup.BackupAlreadyRunning:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A backup is already running. Wait for it to finish.",
        )
    audit_log(
        "DATABASE_BACKUP_STARTED",
        user_id=current_user.id,
        resource_type="backup_run",
        resource_id=run_id,
        ip_address=request.client.host if request.client else None,
    )
    return {"id": run_id, "status": "running"}


@router.get("/runs/{run_id}/download")
def download_backup(
    run_id: int,
    request: Request,
    current_user: Annotated[User, Depends(get_current_admin_user)],
    db: Annotated[Session, Depends(get_db)],
) -> FileResponse:
    run = db.get(BackupRun, run_id)
    if (
        run is None
        or run.status != "ok"
        or run.file_deleted_at is not None
        or not database_backup.FILENAME_RE.match(run.filename or "")
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup file not available")
    path = database_backup.backup_dir() / run.filename
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Backup file is missing from the backup folder",
        )
    audit_log(
        "DATABASE_BACKUP_DOWNLOADED",
        user_id=current_user.id,
        resource_type="backup_run",
        resource_id=run.id,
        details={"filename": run.filename, "size_bytes": run.size_bytes},
        ip_address=request.client.host if request.client else None,
    )
    return FileResponse(
        path,
        media_type="application/gzip",
        filename=run.filename,
        headers={"Cache-Control": "no-store"},
    )
