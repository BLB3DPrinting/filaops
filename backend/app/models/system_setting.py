"""
SystemSetting model

Generic key-value store for system-level configuration that needs to be editable
from an admin UI rather than from `.env` files. The first launch use is PRO CORS
origins (`pro_portal_origins`, `pro_quoter_origins`); the table is intentionally
generic so subsequent PRs can add their own keys without schema changes.

Each setting key has a server-side validator registered in
``app.api.v1.endpoints.system_settings.SETTING_VALIDATORS``. Unknown keys are
rejected at the endpoint, so this table cannot be used as a generic JSON dump.

The endpoint and middleware that read these values live elsewhere; this module
defines storage only.
"""
from sqlalchemy import Column, DateTime, JSON, String, func

from app.db.base import Base


class SystemSetting(Base):
    """One row per registered setting key. Value is JSON for flexibility."""
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by = Column(String, nullable=True)

    def __repr__(self) -> str:
        return f"<SystemSetting(key={self.key!r})>"
