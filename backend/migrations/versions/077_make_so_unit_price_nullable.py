"""Make sales_orders.unit_price nullable

Multi-line (line_item) orders do not have a single unit price — pricing lives on
the individual SalesOrderLine rows. The NOT NULL constraint on the header column
prevented quote-to-order conversion for portal/multi-line quotes.

Revision ID: 077
Revises: 076
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sales_orders",
        "unit_price",
        existing_type=sa.Numeric(10, 2),
        nullable=True,
    )


def downgrade() -> None:
    # Back-fill NULL rows with 0 before re-adding the constraint
    op.execute("UPDATE sales_orders SET unit_price = 0 WHERE unit_price IS NULL")
    op.alter_column(
        "sales_orders",
        "unit_price",
        existing_type=sa.Numeric(10, 2),
        nullable=False,
    )
