"""qc inspection grouping keys (denormalized printer / work-center / operator)

Revision ID: 096
Revises: 095
Create Date: 2026-06-26

#784 — grouped QC metrics (by printer / work-center / operator) would otherwise
join through ``qc_inspections.production_operation_id``, which is NULL for
order-level inspections (no QC-coded op). That silently DROPS those rows from
grouped results. Denormalizing the keys onto ``qc_inspections`` at record time
lets grouping read them directly: a null-keyed inspection groups as
"unassigned" instead of vanishing, and the queries avoid the operation join.

``operator_id`` is a plain user id with NO FK, mirroring
``production_order_operations.operator_id`` (the unconstrained source column), so
copying it at record time can never fail a constraint.

Additive, all nullable — no existing data touched. Index names mirror the model
declarations so create_all (tests/self-host) and Alembic (deploy) match.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "096"
down_revision = "095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qc_inspections",
        sa.Column(
            "printer_id",
            sa.Integer,
            sa.ForeignKey("printers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "qc_inspections",
        sa.Column(
            "work_center_id",
            sa.Integer,
            sa.ForeignKey("work_centers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "qc_inspections",
        sa.Column("operator_id", sa.Integer, nullable=True),
    )
    op.create_index("ix_qc_inspections_printer_id", "qc_inspections", ["printer_id"])
    op.create_index(
        "ix_qc_inspections_work_center_id", "qc_inspections", ["work_center_id"]
    )
    op.create_index("ix_qc_inspections_operator_id", "qc_inspections", ["operator_id"])


def downgrade() -> None:
    op.drop_index("ix_qc_inspections_operator_id", table_name="qc_inspections")
    op.drop_index("ix_qc_inspections_work_center_id", table_name="qc_inspections")
    op.drop_index("ix_qc_inspections_printer_id", table_name="qc_inspections")
    op.drop_column("qc_inspections", "operator_id")
    op.drop_column("qc_inspections", "work_center_id")
    op.drop_column("qc_inspections", "printer_id")
