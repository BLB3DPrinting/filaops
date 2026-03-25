"""Create invoices and invoice_lines tables.

Revision ID: 070
Revises: 068
"""
import sqlalchemy as sa
from alembic import op

revision = "070"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_number", sa.String(20), nullable=False, unique=True),
        sa.Column("sales_order_id", sa.Integer(), sa.ForeignKey("sales_orders.id"), nullable=True),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("customer_name", sa.String(200), nullable=True),
        sa.Column("customer_email", sa.String(200), nullable=True),
        sa.Column("customer_company", sa.String(200), nullable=True),
        sa.Column("bill_to_line1", sa.String(200), nullable=True),
        sa.Column("bill_to_city", sa.String(100), nullable=True),
        sa.Column("bill_to_state", sa.String(50), nullable=True),
        sa.Column("bill_to_zip", sa.String(20), nullable=True),
        sa.Column("payment_terms", sa.String(20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 2), server_default="0"),
        sa.Column("tax_rate", sa.Numeric(5, 4), server_default="0"),
        sa.Column("tax_amount", sa.Numeric(12, 2), server_default="0"),
        sa.Column("shipping_amount", sa.Numeric(12, 2), server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("amount_paid", sa.Numeric(12, 2), server_default="0"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("payment_reference", sa.String(200), nullable=True),
        sa.Column("external_invoice_id", sa.String(100), nullable=True),
        sa.Column("external_invoice_url", sa.String(500), nullable=True),
        sa.Column("external_provider", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pdf_path", sa.String(500), nullable=True),
    )
    op.create_index("ix_invoices_sales_order_id", "invoices", ["sales_order_id"])
    op.create_index("ix_invoices_customer_id", "invoices", ["customer_id"])
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_due_date", "invoices", ["due_date"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("sku", sa.String(50), nullable=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("base_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("discount_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_table("invoice_lines")
    op.drop_table("invoices")
