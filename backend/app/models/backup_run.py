"""
BackupRun model

One row per database backup attempt, scheduled or started by an admin. The
Backups page lists these rows, and the Security Audit's ``backup_configured``
check reads them instead of guessing from files on disk.

The dump itself lives on disk in the backup directory (see
``app.services.database_backup``); ``filename`` names it. ``file_deleted_at``
is set when retention removes the file, so the row survives as history.
"""
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text, func

from app.db.base import Base


class BackupRun(Base):
    __tablename__ = "backup_runs"

    id = Column(Integer, primary_key=True, index=True)
    # running | ok | failed
    status = Column(String(20), nullable=False, default="running", index=True)
    # scheduled | manual
    trigger = Column(String(20), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    filename = Column(String(255), nullable=True)
    size_bytes = Column(BigInteger, nullable=True)
    # COPY sections found in the dump, and ordinary tables in the public
    # schema when the dump started. A dump is OK only if found >= expected.
    table_count = Column(Integer, nullable=True)
    expected_tables = Column(Integer, nullable=True)
    pg_dump_version = Column(String(100), nullable=True)
    server_version = Column(String(100), nullable=True)
    error = Column(Text, nullable=True)
    triggered_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    file_deleted_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<BackupRun(id={self.id}, status={self.status!r}, trigger={self.trigger!r})>"
