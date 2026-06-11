"""backfill legacy production_orders.sales_order_line_id links

Revision ID: 091
Revises: 090
Create Date: 2026-06-11

LEGACY-1: Production orders created before sales_order_line_id linkage
existed (PR #713 gating) have ``sales_order_line_id = NULL`` even though
they were generated from a specific sales order line. That breaks the
workflow UI ("Not released" on completed orders) and the existing-PO check
in ``generate_production_orders``.

This pure data migration backfills the link where it is UNAMBIGUOUS:
the parent sales order is ``order_type = 'line_item'`` and EXACTLY ONE
``sales_order_lines`` row on that order has the same ``product_id`` as the
production order. Rows with zero or multiple candidate lines are left
NULL (runtime fallback logic handles those).

Idempotent: backfilled rows are no longer NULL, so re-running the UPDATE
matches nothing. Server-side SQL only — no ORM, no Python row loops.
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE production_orders AS po
        SET sales_order_line_id = candidate.line_id
        FROM (
            SELECT
                po2.id AS po_id,
                MIN(sol.id) AS line_id
            FROM production_orders AS po2
            JOIN sales_orders AS so
              ON so.id = po2.sales_order_id
            JOIN sales_order_lines AS sol
              ON sol.sales_order_id = so.id
             AND sol.product_id = po2.product_id
            WHERE po2.sales_order_line_id IS NULL
              AND so.order_type = 'line_item'
            GROUP BY po2.id
            HAVING COUNT(sol.id) = 1
        ) AS candidate
        WHERE po.id = candidate.po_id
        """
    )


def downgrade() -> None:
    # Intentional no-op: once backfilled, the rows are indistinguishable
    # from organically created line-linked production orders, so we cannot
    # safely null out only the values this migration set. Reverting would
    # risk destroying legitimate linkage data.
    pass
