"""add qc_inspections table

Revision ID: 093
Revises: 092
Create Date: 2026-06-23

#783: QC state lived only in four last-write-wins ``ProductionOrder.qc_*``
columns — no re-inspection history, no audit trail, and true first-pass yield
was impossible. This append-only table records every inspection (PO FK,
optional operation FK, inspector user FK + denormalized name, result, qty
passed/failed, reason, notes, timestamp). ``ProductionOrder.qc_*`` stays as a
denormalized latest-result cache.

The ``result`` column is CHECK-constrained so values cannot drift the way the
unconstrained ``ProductionOrder.qc_status`` VARCHAR can.

Additive table — no existing data touched.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "093"
down_revision = "092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qc_inspections",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "production_order_id",
            sa.Integer,
            sa.ForeignKey("production_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "production_operation_id",
            sa.Integer,
            sa.ForeignKey("production_order_operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("result", sa.String(20), nullable=False),
        sa.Column("quantity_passed", sa.Integer, nullable=True),
        sa.Column("quantity_failed", sa.Integer, nullable=True),
        sa.Column(
            "inspector_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("inspector_name", sa.String(100), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("inspected_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "result IN ('passed', 'failed', 'waived', 'conditional')",
            name="ck_qc_inspections_result",
        ),
    )
    op.create_index(
        "ix_qc_inspections_production_order_id",
        "qc_inspections",
        ["production_order_id"],
    )
    # History reads order by (order, time); index supports the audit-trail query.
    op.create_index(
        "ix_qc_inspections_order_inspected_at",
        "qc_inspections",
        ["production_order_id", "inspected_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_qc_inspections_order_inspected_at", table_name="qc_inspections"
    )
    op.drop_index(
        "ix_qc_inspections_production_order_id", table_name="qc_inspections"
    )
    op.drop_table("qc_inspections")
