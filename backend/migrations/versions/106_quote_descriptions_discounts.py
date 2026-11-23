"""Quote, order and invoice line descriptions and discounts

Revision ID: 106
Revises: 105
Create Date: 2026-11-22

Adds, all nullable and with no backfill:

- quotes, sales_orders: a document-level discount (type, value, label, and
  the computed amount in money).
- quote_lines: a multi-line item description and a per-line discount.
- sales_order_lines: the item description (``long_description``, because
  ``description`` already holds a service line's name) and a per-line
  discount.
- invoices: the discount label and the customer-facing notes.
- invoice_lines: the item description, the line discount label and amount.

A NULL discount computes as zero (app/services/discount_math.py), so every
existing quote, order and invoice keeps exactly the totals it has today.

The existing ``discount_percent`` columns (customer price level, baked into
unit prices) and the legacy ``sales_order_lines.discount`` column are not
touched.

ADD COLUMN only (nullable): safe on the live brownfield. Inspector-guarded and
idempotent, so a rerun is a no-op.

Downgrade: drop the columns (never run on the live DB).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "106"
down_revision = "105"
branch_labels = None
depends_on = None


_DISCOUNT_COLUMNS = [
    ("discount_type", lambda: sa.String(length=10)),
    ("discount_value", lambda: sa.Numeric(10, 2)),
    ("discount_label", lambda: sa.String(length=100)),
    ("discount_amount", lambda: sa.Numeric(10, 2)),
]

# Frozen column lists: a migration must not import app code that can change.
NEW_COLUMNS = {
    "quotes": _DISCOUNT_COLUMNS,
    "quote_lines": [("description", sa.Text), *_DISCOUNT_COLUMNS],
    "sales_orders": _DISCOUNT_COLUMNS,
    "sales_order_lines": [("long_description", sa.Text), *_DISCOUNT_COLUMNS],
    "invoices": [
        ("discount_label", lambda: sa.String(length=100)),
        ("notes", sa.Text),
    ],
    "invoice_lines": [
        ("long_description", sa.Text),
        ("discount_label", lambda: sa.String(length=100)),
        ("discount_amount", lambda: sa.Numeric(12, 2)),
    ],
}


def _existing_columns(bind, table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    for table, columns in NEW_COLUMNS.items():
        existing = _existing_columns(bind, table)
        for name, make_type in columns:
            if name not in existing:
                op.add_column(table, sa.Column(name, make_type(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for table, columns in NEW_COLUMNS.items():
        existing = _existing_columns(bind, table)
        for name, _make_type in columns:
            if name in existing:
                op.drop_column(table, name)
