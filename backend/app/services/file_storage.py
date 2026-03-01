"""
File Storage Service for Quote Files

Handles local filesystem storage with Google Cloud Storage backup
"""
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class FileStorageService:
    """
    Manages file storage for quote uploads

    Features:
    - Local filesystem storage with year/month organization
    - SHA256 hashing for deduplication
    - Optional GCS backup (async)
    - File validation (format, size)
    """

    def __init__(self):
        # Resolve upload directory - use configured path or default to backend/uploads/quotes
        upload_dir_setting = (settings.UPLOAD_DIR or "").strip()
        if upload_dir_setting:
            self.upload_dir = Path(upload_dir_setting)
        else:
            # Default: <repo>/backend/uploads/quotes (absolute, works in Docker and CI)
            self.upload_dir = Path(__file__).resolve().parent.parent.parent / "uploads" / "quotes"
        self.max_file_size = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        self.allowed_formats = settings.ALLOWED_FILE_FORMATS

        # GCS client (lazy loaded)
        self._gcs_client = None
        self._gcs_bucket = None

        # Ensure upload directory exists (don't crash app startup on failure)
        try:
            self.upload_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error(f"Upload directory unavailable at startup: {self.upload_dir} ({exc})")

    async def save_file(
        self,
        file: UploadFile,
        user_id: int,
        quote_id: Optional[int] = None
    ) -> dict:
        """
        Save uploaded file to local storage and optionally backup to GCS

        Args:
            file: FastAPI uploaded file
            user_id: ID of user uploading
            quote_id: Optional quote ID (if known)

        Returns:
            Dictionary with file metadata:
            {
                'original_filename': str,
                'stored_filename': str,
                'file_path': str,
                'file_size_bytes': int,
                'file_format': str,
                'file_hash': str,
                'mime_type': str,
                'gcs_backed_up': bool
            }

        Raises:
            ValueError: If file validation fails
        """
        # Validate file format
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.allowed_formats:
            raise ValueError(
                f"Invalid file format: {file_ext}. "
                f"Allowed formats: {', '.join(self.allowed_formats)}"
            )

        # Read file content
        content = await file.read()
        file_size = len(content)

        # Validate file size
        if file_size > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            raise ValueError(
                f"File too large: {actual_mb:.2f}MB. "
                f"Maximum allowed: {max_mb:.0f}MB"
            )

        # Calculate SHA256 hash
        file_hash = hashlib.sha256(content).hexdigest()

        # Generate storage filename with UUID to prevent collisions
        stored_filename = f"{uuid4().hex}{file_ext}"

        # Organize by year/month for better filesystem performance
        now = datetime.now(timezone.utc)
        year_month_dir = self.upload_dir / str(now.year) / f"{now.month:02d}"
        year_month_dir.mkdir(parents=True, exist_ok=True)

        # Full file path
        file_path = year_month_dir / stored_filename

        # Save to local filesystem
        try:
            with open(file_path, "wb") as f:
                f.write(content)
            logger.info(f"Saved file locally: {file_path} (user_id={user_id})")
        except Exception as e:
            logger.error(f"Failed to save file locally: {e}")
            raise ValueError(f"Failed to save file: {str(e)}")

        # Backup to GCS (if enabled)
        gcs_backed_up = False
        if settings.GCS_ENABLED:
            try:
                gcs_path = await self._backup_to_gcs(
                    content=content,
                    filename=stored_filename,
                    year=now.year,
                    month=now.month
                )
                gcs_backed_up = True
                logger.info(f"Backed up to GCS: {gcs_path}")
            except Exception as e:
                # Log error but don't fail - local storage is primary
                logger.error(f"GCS backup failed (non-critical): {e}")

        return {
            'original_filename': file.filename,
            'stored_filename': stored_filename,
            'file_path': str(file_path),
            'file_size_bytes': file_size,
            'file_format': file_ext,
            'file_hash': file_hash,
            'mime_type': file.content_type or 'application/octet-stream',
            'gcs_backed_up': gcs_backed_up
        }

    def get_file_path(self, stored_filename: str) -> Optional[Path]:
        """
        Get full path to a stored file by searching year/month directories

        Args:
            stored_filename: The UUID-based filename

        Returns:
            Path object if file exists, None otherwise
        """
        # Search through year/month directories
        for year_dir in self.upload_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                file_path = month_dir / stored_filename
                if file_path.exists():
                    return file_path
        return None

    def delete_file(self, stored_filename: str) -> bool:
        """
        Delete file from local storage

        Args:
            stored_filename: The UUID-based filename

        Returns:
            True if deleted, False if not found
        """
        file_path = self.get_file_path(stored_filename)
        if file_path and file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"Deleted file: {file_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to delete file {file_path}: {e}")
                return False
        return False

    async def _backup_to_gcs(
        self,
        content: bytes,
        filename: str,
        year: int,
        month: int
    ) -> str:
        """
        Backup file to Google Cloud Storage

        Args:
            content: File bytes
            filename: Stored filename
            year: Year for organization
            month: Month for organization

        Returns:
            GCS blob path

        Raises:
            Exception: If GCS upload fails
        """
        # Lazy load GCS client
        if self._gcs_client is None:
            from google.cloud import storage

            # Use credentials file if specified, otherwise use default
            if settings.GCS_CREDENTIALS_PATH:
                self._gcs_client = storage.Client.from_service_account_json(
                    settings.GCS_CREDENTIALS_PATH,
                    project=settings.GCS_PROJECT_ID
                )
            else:
                # Use default credentials (from gcloud or Workspace account)
                self._gcs_client = storage.Client(project=settings.GCS_PROJECT_ID)

            self._gcs_bucket = self._gcs_client.bucket(settings.GCS_BUCKET_NAME)

        # GCS path: quotes/{year}/{month}/{filename}
        blob_name = f"quotes/{year}/{month:02d}/{filename}"
        blob = self._gcs_bucket.blob(blob_name)

        # Upload with Nearline storage class for cost savings
        blob.upload_from_string(
            content,
            content_type='application/octet-stream'
        )

        # Set to Nearline storage class (cold storage, accessed < 1/month)
        blob.update_storage_class('NEARLINE')

        return blob_name

    def validate_file(self, file: UploadFile) -> Tuple[bool, Optional[str]]:
        """
        Validate file before upload (synchronous check)

        Args:
            file: FastAPI uploaded file

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check filename
        if not file.filename:
            return False, "No filename provided"

        # Check file format
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in self.allowed_formats:
            return False, f"Invalid format: {file_ext}. Allowed: {', '.join(self.allowed_formats)}"

        # Check content type
        if file.content_type:
            valid_mime_types = [
                'application/octet-stream',
                'application/vnd.ms-package.3dmanufacturing-3dmodel+xml',  # .3mf
                'model/stl',  # .stl
                'application/sla'  # .stl
            ]
            if file.content_type not in valid_mime_types:
                logger.warning(f"Unusual MIME type: {file.content_type} for {file.filename}")

        return True, None


# Singleton instance
file_storage = FileStorageService()
