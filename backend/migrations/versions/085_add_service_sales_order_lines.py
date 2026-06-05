"""Allow service and fee sales order lines.

Revision ID: 085
Revises: 084
Create Date: 2026-06-05
"""
from alembic import op
import sqlalchemy as sa


revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None


CHECK_EXPR = (
    "(line_type = 'product' AND product_id IS NOT NULL AND material_inventory_id IS NULL) OR "
    "(line_type = 'material' AND product_id IS NULL AND material_inventory_id IS NOT NULL) OR "
    "(line_type = 'service' AND product_id IS NULL AND material_inventory_id IS NULL)"
)
OLD_CHECK_EXPR = (
    "(product_id IS NOT NULL AND material_inventory_id IS NULL) OR "
    "(product_id IS NULL AND material_inventory_id IS NOT NULL)"
)


def _column_exists(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return constraint_name in {
        constraint["name"]
        for constraint in inspector.get_check_constraints(table_name)
    }


def upgrade() -> None:
    if not _column_exists("sales_order_lines", "line_type"):
        op.add_column(
            "sales_order_lines",
            sa.Column(
                "line_type",
                sa.String(length=20),
                nullable=False,
                server_default="product",
            ),
        )

    if not _index_exists("sales_order_lines", "ix_sales_order_lines_line_type"):
        op.create_index(
            "ix_sales_order_lines_line_type",
            "sales_order_lines",
            ["line_type"],
        )

    if not _column_exists("sales_order_lines", "description"):
        op.add_column(
            "sales_order_lines",
            sa.Column("description", sa.String(length=255), nullable=True),
        )

    op.execute(
        "UPDATE sales_order_lines "
        "SET line_type = 'material' "
        "WHERE product_id IS NULL AND material_inventory_id IS NOT NULL"
    )
    op.execute(
        "UPDATE sales_order_lines "
        "SET line_type = 'product' "
        "WHERE product_id IS NOT NULL AND material_inventory_id IS NULL"
    )

    if _constraint_exists("sales_order_lines", "ck_sol_product_or_material"):
        op.drop_constraint(
            "ck_sol_product_or_material",
            "sales_order_lines",
            type_="check",
        )
    op.create_check_constraint(
        "ck_sol_product_or_material",
        "sales_order_lines",
        CHECK_EXPR,
    )


def downgrade() -> None:
    bind = op.get_bind()
    has_service_lines = bind.execute(
        sa.text(
            "SELECT 1 FROM sales_order_lines "
            "WHERE line_type = 'service' "
            "LIMIT 1"
        )
    ).first()
    if has_service_lines:
        raise RuntimeError(
            "Cannot downgrade: sales_order_lines with line_type='service' exist. "
            "Delete or convert those rows before downgrading past revision 085."
        )

    if _constraint_exists("sales_order_lines", "ck_sol_product_or_material"):
        op.drop_constraint(
            "ck_sol_product_or_material",
            "sales_order_lines",
            type_="check",
        )
    op.create_check_constraint(
        "ck_sol_product_or_material",
        "sales_order_lines",
        OLD_CHECK_EXPR,
    )

    if _column_exists("sales_order_lines", "description"):
        op.drop_column("sales_order_lines", "description")
    if _column_exists("sales_order_lines", "line_type"):
        if _index_exists("sales_order_lines", "ix_sales_order_lines_line_type"):
            op.drop_index("ix_sales_order_lines_line_type", table_name="sales_order_lines")
        op.drop_column("sales_order_lines", "line_type")
