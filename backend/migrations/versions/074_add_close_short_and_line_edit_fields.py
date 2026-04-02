"""Add close_short fields to sales_orders and original_quantity to sales_order_lines

Revision ID: 074
Revises: 073
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Sales order header: close-short tracking
    op.add_column(
        "sales_orders",
        sa.Column("closed_short", sa.Boolean, server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "sales_orders",
        sa.Column("closed_short_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sales_orders",
        sa.Column("close_short_reason", sa.Text, nullable=True),
    )

    # Sales order lines: preserve original quantity on edit
    op.add_column(
        "sales_order_lines",
        sa.Column("original_quantity", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sales_order_lines", "original_quantity")
    op.drop_column("sales_orders", "close_short_reason")
    op.drop_column("sales_orders", "closed_short_at")
    op.drop_column("sales_orders", "closed_short")
