"""Add void fields to inventory_transactions (HARD-11).

Revision ID: 088
Revises: 087
Create Date: 2026-06-10

A rejected held transaction (requires_approval=True that staff explicitly
rejects) is voided in-place: the row is kept for audit, on_hand is never
mutated, and the row is excluded from COGS and ledger totals.

Fields added:
  voided_by   — email/username of the staff member who voided the row
  voided_at   — UTC timestamp of the void action
  void_reason — human-readable reason for the void (required on rejection)

A "pending" held row: requires_approval=True, approved_by IS NULL, voided_by IS NULL.
An "approved" row:    requires_approval=False, approved_by IS NOT NULL.
A "voided" row:       voided_by IS NOT NULL (regardless of requires_approval).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols


def upgrade() -> None:
    if not _column_exists("inventory_transactions", "voided_by"):
        op.add_column(
            "inventory_transactions",
            sa.Column("voided_by", sa.String(100), nullable=True),
        )
    if not _column_exists("inventory_transactions", "voided_at"):
        op.add_column(
            "inventory_transactions",
            sa.Column("voided_at", sa.DateTime, nullable=True),
        )
    if not _column_exists("inventory_transactions", "void_reason"):
        op.add_column(
            "inventory_transactions",
            sa.Column("void_reason", sa.Text, nullable=True),
        )


def downgrade() -> None:
    for col in ("void_reason", "voided_at", "voided_by"):
        if _column_exists("inventory_transactions", col):
            op.drop_column("inventory_transactions", col)
