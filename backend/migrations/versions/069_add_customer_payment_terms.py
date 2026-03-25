"""Add customer payment terms columns to users table.

New columns (used for account_type='customer' rows):
- payment_terms: COD, prepay, net15, net30, card_on_file
- credit_limit: maximum credit amount
- approved_for_terms: admin approval flag for net terms
- approved_for_terms_at: timestamp of approval
- approved_for_terms_by: admin user ID who approved

Revision ID: 069
Revises: 068
"""
import sqlalchemy as sa
from alembic import op

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("payment_terms", sa.String(20), server_default="cod"))
    op.add_column("users", sa.Column("credit_limit", sa.Numeric(12, 2), nullable=True))
    op.add_column("users", sa.Column("approved_for_terms", sa.Boolean(), server_default=sa.text("false")))
    op.add_column("users", sa.Column("approved_for_terms_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("approved_for_terms_by", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "approved_for_terms_by")
    op.drop_column("users", "approved_for_terms_at")
    op.drop_column("users", "approved_for_terms")
    op.drop_column("users", "credit_limit")
    op.drop_column("users", "payment_terms")
