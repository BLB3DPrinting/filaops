"""Add baseline_on_hand to inventory table.

Revision ID: 087
Revises: 086
Create Date: 2026-06-10

Part of HARD-4c: reconciliation count-entry tool.

baseline_on_hand stores the physically-counted quantity at the moment of the
last reconciliation_baseline transaction.  The reconciliation report (4b)
uses it as the epoch opening balance:

    drift = stored_on_hand - (baseline_on_hand + sum(post-baseline txns))

This makes zero-delta baselines correct: if the count matched stored exactly,
baseline_on_hand == stored, no post-baseline transactions exist yet, so
drift == 0 immediately after counting.

Legacy rows (NULL baseline_on_hand, NULL baseline_timestamp) fall back to the
old at-or-after sum formula so pre-4c history is never reinterpreted.

NO data is written by this migration -- column addition only.
"""
from alembic import op
import sqlalchemy as sa


revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _column_exists("inventory", "baseline_on_hand"):
        op.add_column(
            "inventory",
            sa.Column(
                "baseline_on_hand",
                sa.Numeric(18, 4),
                nullable=True,
                comment=(
                    "on_hand_quantity snapshotted at the last reconciliation_baseline "
                    "(physical count). Used by the reconciliation report as the epoch "
                    "opening balance: drift = stored - (baseline_on_hand + sum(post-baseline txns)). "
                    "NULL when baseline_timestamp IS NULL (item never counted)."
                ),
            ),
        )


def downgrade() -> None:
    if _column_exists("inventory", "baseline_on_hand"):
        op.drop_column("inventory", "baseline_on_hand")
