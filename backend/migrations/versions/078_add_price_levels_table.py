"""Add price_levels table

Price level management (CRUD) moves to Core. Customer assignment
remains a PRO feature (pro_customer_price_levels, managed by filaops-pro).

Revision ID: 078
Revises: 077
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_levels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    # Drop the redundant ix_price_levels_id if it was created by a previous version
    # of this migration. Primary keys are already indexed by PostgreSQL.
    # IF EXISTS keeps the transaction healthy on fresh installs where the index
    # was never created (try/except doesn't work — Postgres aborts the transaction).
    op.execute("DROP INDEX IF EXISTS ix_price_levels_id")


def downgrade() -> None:
    op.drop_table("price_levels")
