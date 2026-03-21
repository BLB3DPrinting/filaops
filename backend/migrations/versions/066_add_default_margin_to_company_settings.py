"""Add default_margin_percent to company_settings.

Stores the default target profit margin used by the Suggest Prices tool.
Backfills to 71.43 (equivalent to the existing 3.5x markup constant).

Revision ID: 066
Revises: 065
"""
from alembic import op
import sqlalchemy as sa

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_settings",
        sa.Column("default_margin_percent", sa.Numeric(5, 2), nullable=True),
    )
    # Backfill: 3.5x markup = 1 - 1/3.5 = 71.43% margin
    op.execute(
        "UPDATE company_settings SET default_margin_percent = 71.43 WHERE id = 1"
    )


def downgrade() -> None:
    op.drop_column("company_settings", "default_margin_percent")
