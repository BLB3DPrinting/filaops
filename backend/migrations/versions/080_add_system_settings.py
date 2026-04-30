"""Add system_settings table

Generic key/value store for admin-editable configuration. First launch use is
PRO CORS origins; subsequent PRs may add their own keys (each requiring a
server-side validator registered in the endpoint module).

This migration seeds the two PRO CORS origin keys with empty lists so the
GET endpoint succeeds immediately after the migration runs, before any
operator has saved values via the admin UI.

Revision ID: 080
Revises: 079
Create Date: 2026-04-30
"""
from alembic import op
import sqlalchemy as sa


revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_by", sa.String(), nullable=True),
    )
    # Seed the two PRO CORS origin keys with empty lists. This makes
    # `GET /api/v1/system/settings/pro_portal_origins` return immediately after
    # migration, before any operator has saved values via the admin UI.
    op.execute(
        "INSERT INTO system_settings (key, value) VALUES "
        "('pro_portal_origins', '[]'::json), "
        "('pro_quoter_origins', '[]'::json)"
    )


def downgrade() -> None:
    op.drop_table("system_settings")
