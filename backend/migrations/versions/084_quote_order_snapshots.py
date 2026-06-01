"""Add durable quote and order handoff snapshots.

Revision ID: 084
Revises: 083
Create Date: 2026-06-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None


SNAPSHOT_COLUMNS = (
    "pricing_snapshot",
    "component_snapshot",
    "packaging_snapshot",
    "shipping_snapshot",
    "artifact_snapshot",
    "slicer_diagnostics",
)
SNAPSHOT_JSON_TYPE = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in set(inspector.get_table_names())


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    for table_name in ("quotes", "sales_orders"):
        if not _table_exists(table_name):
            continue
        for column_name in SNAPSHOT_COLUMNS:
            if not _column_exists(table_name, column_name):
                op.add_column(table_name, sa.Column(column_name, SNAPSHOT_JSON_TYPE, nullable=True))


def downgrade() -> None:
    for table_name in ("sales_orders", "quotes"):
        if not _table_exists(table_name):
            continue
        for column_name in reversed(SNAPSHOT_COLUMNS):
            if _column_exists(table_name, column_name):
                op.drop_column(table_name, column_name)
