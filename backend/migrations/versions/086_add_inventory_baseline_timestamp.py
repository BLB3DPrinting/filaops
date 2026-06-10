"""Add baseline_timestamp to inventory table.

Revision ID: 086
Revises: 085
Create Date: 2026-06-10

Part of HARD-4b: inventory reconciliation report.

NULL baseline_timestamp means the item has never been baselined (counted).
The reconciliation service (4b) sums ALL transactions for those items and
displays them as "uncounted".  When a physical count posts a
reconciliation_baseline transaction (4c) the poster stamps this column with
the transaction timestamp so all SUBSEQUENT sums start from that epoch.

NO data is written by this migration — column addition only.
"""
from alembic import op
import sqlalchemy as sa


revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def upgrade() -> None:
    if not _column_exists("inventory", "baseline_timestamp"):
        op.add_column(
            "inventory",
            sa.Column(
                "baseline_timestamp",
                sa.DateTime(timezone=True),
                nullable=True,
                comment=(
                    "UTC timestamp of the last physical count / reconciliation_baseline "
                    "transaction. NULL = never baselined. The reconciliation report sums "
                    "only transactions at-or-after this timestamp; NULL rows sum ALL "
                    "transactions and are shown as uncounted."
                ),
            ),
        )


def downgrade() -> None:
    if _column_exists("inventory", "baseline_timestamp"):
        op.drop_column("inventory", "baseline_timestamp")
