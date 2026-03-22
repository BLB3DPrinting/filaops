"""Add variant matrix support to products and routing_operation_materials.

Adds parent_product_id, is_template, and variant_metadata to products table
for template/variant relationships. Adds is_variable to routing_operation_materials
to mark which materials get swapped per variant.

Revision ID: 067
Revises: 066
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


def upgrade():
    # Products: variant support
    op.add_column("products", sa.Column(
        "parent_product_id", sa.Integer,
        sa.ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.create_index("ix_products_parent_product_id", "products", ["parent_product_id"])
    op.add_column("products", sa.Column(
        "is_template", sa.Boolean, nullable=False, server_default="false",
    ))
    op.add_column("products", sa.Column(
        "variant_metadata", JSONB, nullable=True,
    ))

    # RoutingOperationMaterial: variable flag
    op.add_column("routing_operation_materials", sa.Column(
        "is_variable", sa.Boolean, nullable=False, server_default="false",
    ))


def downgrade():
    op.drop_column("routing_operation_materials", "is_variable")
    op.drop_column("products", "variant_metadata")
    op.drop_column("products", "is_template")
    op.drop_index("ix_products_parent_product_id", table_name="products")
    op.drop_column("products", "parent_product_id")
