"""add landed_cost_allocated to purchase_orders

Revision ID: 089
Revises: 088
Create Date: 2026-06-10

Adds a Decimal(18,4) column `landed_cost_allocated` (default 0, not nullable)
to purchase_orders.  The receive_purchase_order flow accumulates the freight +
tax already capitalised across all prior receipts so the final receipt can
absorb the Decimal residual and guarantee:

    total capitalised == po.shipping_cost + po.tax_amount EXACTLY ONCE

No-op additive migration: default 0 is valid for all existing POs (freight was
never correctly tracked before this column, so 0 is the correct starting state
for re-receives; fully-received POs are already closed or marked received and
will not be re-received).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "purchase_orders",
        sa.Column(
            "landed_cost_allocated",
            sa.Numeric(18, 4),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("purchase_orders", "landed_cost_allocated")
