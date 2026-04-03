"""Add fulfillment_status to sales_order_lines

Revision ID: 076
Revises: 075
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sales_order_lines",
        sa.Column("fulfillment_status", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sales_order_lines", "fulfillment_status")
