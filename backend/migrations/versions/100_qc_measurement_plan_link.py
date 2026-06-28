"""qc measurement -> quality plan characteristic link + conformance

Revision ID: 100
Revises: 099
Create Date: 2026-06-27

#784 PR-6 — when the QC inspection form is seeded from a product's active
quality plan, each measurement links back to its plan characteristic and (for
attribute / Go-No-Go characteristics) records a pass/fail.

- quality_plan_characteristic_id: FK -> quality_plan_characteristics, SET NULL
  so deleting a plan never destroys inspection history.
- characteristic_code: denormalized stable SPC key copied at record time, so
  (product_id, code) series survive the FK being nulled.
- conforms: pass/fail for an attribute characteristic; NULL for variable rows
  (their conformance is computed from measured_value vs spec limits).

Additive; all nullable.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "qc_inspection_measurements",
        sa.Column("quality_plan_characteristic_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "qc_inspection_measurements",
        sa.Column("characteristic_code", sa.String(50), nullable=True),
    )
    op.add_column(
        "qc_inspection_measurements",
        sa.Column("conforms", sa.Boolean(), nullable=True),
    )
    op.create_index(
        "ix_qc_inspection_measurements_quality_plan_characteristic_id",
        "qc_inspection_measurements",
        ["quality_plan_characteristic_id"],
    )
    op.create_foreign_key(
        "fk_qc_measurement_plan_characteristic",
        "qc_inspection_measurements",
        "quality_plan_characteristics",
        ["quality_plan_characteristic_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_qc_measurement_plan_characteristic",
        "qc_inspection_measurements",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_qc_inspection_measurements_quality_plan_characteristic_id",
        table_name="qc_inspection_measurements",
    )
    op.drop_column("qc_inspection_measurements", "conforms")
    op.drop_column("qc_inspection_measurements", "characteristic_code")
    op.drop_column("qc_inspection_measurements", "quality_plan_characteristic_id")
