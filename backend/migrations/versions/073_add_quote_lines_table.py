"""Add quote_lines table and discount_percent to quotes

Revision ID: 073
Revises: 072
Create Date: 2026-03-30
"""
from alembic import op
import sqlalchemy as sa

revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add discount_percent to quotes header
    op.add_column(
        "quotes",
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=True),
    )

    # Create quote_lines table
    op.create_table(
        "quote_lines",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column(
            "quote_id",
            sa.Integer,
            sa.ForeignKey("quotes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "product_id",
            sa.Integer,
            sa.ForeignKey("products.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("line_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("product_name", sa.String(255), nullable=True),
        sa.Column("quantity", sa.Integer, nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("total", sa.Numeric(10, 2), nullable=False),
        sa.Column("material_type", sa.String(50), nullable=True),
        sa.Column("color", sa.String(50), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("quote_lines")
    op.drop_column("quotes", "discount_percent")
