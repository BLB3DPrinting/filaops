"""Add submitted_at to sales_orders and create notifications table

Revision ID: 072
Revises: 071
Create Date: 2026-03-26
"""
from alembic import op
import sqlalchemy as sa

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add submitted_at to sales_orders
    op.add_column(
        "sales_orders",
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Create notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(36), nullable=False),
        sa.Column("thread_subject", sa.String(200), nullable=True),
        sa.Column(
            "sales_order_id",
            sa.Integer(),
            sa.ForeignKey("sales_orders.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "sender_type",
            sa.String(20),
            nullable=False,
            server_default="system",
        ),
        sa.Column("sender_name", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "source", sa.String(20), nullable=True, server_default="system"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "idx_notifications_thread",
        "notifications",
        ["thread_id", "created_at"],
    )
    op.create_index(
        "idx_notifications_unread",
        "notifications",
        ["read_at"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    op.create_index(
        "idx_notifications_sales_order",
        "notifications",
        ["sales_order_id"],
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_column("sales_orders", "submitted_at")
