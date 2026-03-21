"""Increase cost column precision from Numeric(10,2) to Numeric(18,4).

Unit costs like $0.0642/ea (from $8.99 / 140pcs) cannot be stored
accurately with only 2 decimal places. PO line costs already use
Numeric(18,4); this aligns the product cost columns to match.

Note: Downgrade truncates Numeric(18,4) back to Numeric(10,2), so any
costs stored with >2 decimals (e.g., $0.0642 → $0.06) will lose precision.

Revision ID: 065
Revises: 064
"""
from alembic import op
import sqlalchemy as sa

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None

# Columns to widen: all on the 'products' table
COST_COLUMNS = ["standard_cost", "average_cost", "last_cost"]


def upgrade() -> None:
    for col in COST_COLUMNS:
        op.alter_column(
            "products",
            col,
            existing_type=sa.Numeric(10, 2),
            type_=sa.Numeric(18, 4),
            existing_nullable=True,
        )


def downgrade() -> None:
    for col in COST_COLUMNS:
        op.alter_column(
            "products",
            col,
            existing_type=sa.Numeric(18, 4),
            type_=sa.Numeric(10, 2),
            existing_nullable=True,
        )
