"""qc defect reasons, inspection measurements & photos

Revision ID: 095
Revises: 094
Create Date: 2026-06-25

#784 step 3 — schema foundation for the remaining Quality capabilities:
- ``defect_reasons``: a configurable defect taxonomy (free-form category +
  CHECK-constrained severity). Distinct from ``scrap_reasons`` (which explains
  why material was destroyed); this classifies what was wrong at inspection.
- ``qc_inspections`` gains ``defect_reason_id`` (FK SET NULL) and
  ``waiver_user_id`` (FK SET NULL). The attributed waive stays on the immutable
  inspection row; NCR / hold-and-disposition is PRO scope.
- ``qc_inspection_measurements``: SPC-ready Numeric measurements per inspection.
- ``qc_inspection_photos``: photo evidence per inspection (its own table — NOT
  a reuse of ``purchase_order_documents``).

Additive — no existing data touched. Index names and constraints mirror the
model declarations so ``create_all`` (tests/self-host) and Alembic (deploy)
produce identical schema.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "095"
down_revision = "094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Defect taxonomy. severity is CHECK-constrained at the DB so it cannot
    #    drift the way an unconstrained VARCHAR could.
    op.create_table(
        "defect_reasons",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("sequence", sa.Integer, nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "severity IN ('minor', 'major', 'critical')",
            name="ck_defect_reasons_severity",
        ),
    )
    op.create_index("ix_defect_reasons_code", "defect_reasons", ["code"], unique=True)

    # 2) qc_inspections: structured defect link + attributed waiver.
    #    defect_reasons must exist before the FK column is added (above).
    op.add_column(
        "qc_inspections",
        sa.Column(
            "defect_reason_id",
            sa.Integer,
            sa.ForeignKey("defect_reasons.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "qc_inspections",
        sa.Column(
            "waiver_user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_qc_inspections_defect_reason_id", "qc_inspections", ["defect_reason_id"]
    )

    # 3) Measurements — Numeric (not Float) so values are exact / SPC-ready.
    op.create_table(
        "qc_inspection_measurements",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "qc_inspection_id",
            sa.Integer,
            sa.ForeignKey("qc_inspections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("characteristic", sa.String(100), nullable=False),
        sa.Column("nominal", sa.Numeric(18, 4), nullable=True),
        sa.Column("lower_limit", sa.Numeric(18, 4), nullable=True),
        sa.Column("upper_limit", sa.Numeric(18, 4), nullable=True),
        sa.Column("measured_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("sequence", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_qc_inspection_measurements_qc_inspection_id",
        "qc_inspection_measurements",
        ["qc_inspection_id"],
    )

    # 4) Photos — own table; column conventions mirror purchase_order_documents.
    op.create_table(
        "qc_inspection_photos",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "qc_inspection_id",
            sa.Integer,
            sa.ForeignKey("qc_inspections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("file_url", sa.String(1000), nullable=True),
        sa.Column("storage_type", sa.String(50), nullable=False, server_default="local"),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("file_size", sa.Integer, nullable=True),
        sa.Column("caption", sa.String(255), nullable=True),
        sa.Column("uploaded_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_qc_inspection_photos_qc_inspection_id",
        "qc_inspection_photos",
        ["qc_inspection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_qc_inspection_photos_qc_inspection_id", table_name="qc_inspection_photos"
    )
    op.drop_table("qc_inspection_photos")

    op.drop_index(
        "ix_qc_inspection_measurements_qc_inspection_id",
        table_name="qc_inspection_measurements",
    )
    op.drop_table("qc_inspection_measurements")

    op.drop_index(
        "ix_qc_inspections_defect_reason_id", table_name="qc_inspections"
    )
    op.drop_column("qc_inspections", "waiver_user_id")
    op.drop_column("qc_inspections", "defect_reason_id")

    op.drop_index("ix_defect_reasons_code", table_name="defect_reasons")
    op.drop_table("defect_reasons")
