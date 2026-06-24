"""partial unique index on sales_orders.source_order_id

Revision ID: 094
Revises: 093
Create Date: 2026-06-24

#785: the order CSV importer dedups on source_order_id with a check-then-act
query, so two concurrent imports of the same marketplace file could both pass
the check and create duplicate sales orders — the column had only a plain
(non-unique) index. Replace it with a partial UNIQUE index (excluding NULLs, so
portal/manual orders without a source id are unaffected) to make the dedup
race-safe at the database.

NOTE: if a database already contains duplicate non-null source_order_id values
(from the previous racy path), this index creation will fail — resolve those
duplicates before upgrading.

Depends on 093 (qc_inspections); merge that first.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "094"
down_revision = "093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old plain index (auto-named by the column's index=True) if present,
    # then create the partial unique index in its place.
    op.execute("DROP INDEX IF EXISTS ix_sales_orders_source_order_id")
    op.create_index(
        "uq_sales_orders_source_order_id",
        "sales_orders",
        ["source_order_id"],
        unique=True,
        postgresql_where=sa.text("source_order_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_sales_orders_source_order_id", table_name="sales_orders")
    op.create_index(
        "ix_sales_orders_source_order_id",
        "sales_orders",
        ["source_order_id"],
    )
