"""Add close_short_records audit table

Revision ID: 075
Revises: 074
Create Date: 2026-04-03
"""
from alembic import op
import sqlalchemy as sa

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "close_short_records",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("entity_type", sa.String(20), nullable=False, index=True),
        sa.Column("entity_id", sa.Integer, nullable=False, index=True),
        sa.Column(
            "performed_by",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("line_adjustments", sa.JSON, nullable=True),
        sa.Column("linked_po_states", sa.JSON, nullable=True),
        sa.Column("inventory_snapshot", sa.JSON, nullable=True),
    )
    op.create_index(
        "ix_close_short_records_entity_type_entity_id",
        "close_short_records",
        ["entity_type", "entity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_close_short_records_entity_type_entity_id")
    op.drop_table("close_short_records")
