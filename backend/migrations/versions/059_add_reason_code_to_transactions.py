"""
Add reason_code column to inventory_transactions.

Stores the adjustment reason code for inventory adjustments,
linking to adjustment_reasons.code without a FK constraint.

Revision ID: 059_reason_code
Revises: 058_adjustment_reasons
Create Date: 2026-02-08
"""
from alembic import op

# revision identifiers
revision = '059_reason_code'
down_revision = '058_adjustment_reasons'
branch_labels = None
depends_on = None


def upgrade():
    """Add reason_code column to inventory_transactions."""
    op.execute("""
        ALTER TABLE inventory_transactions ADD COLUMN IF NOT EXISTS reason_code VARCHAR(50);
    """)


def downgrade():
    """Remove reason_code column from inventory_transactions."""
    op.execute("""
        ALTER TABLE inventory_transactions DROP COLUMN IF EXISTS reason_code;
    """)
