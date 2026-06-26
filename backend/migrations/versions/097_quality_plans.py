"""quality plans + plan characteristics

Revision ID: 097
Revises: 096
Create Date: 2026-06-26

#784 — a per-product Quality Plan defines WHAT to inspect: a header (mirroring
Routing, with a nullable product_id so a plan can be a reusable template) and
child characteristic rows (nominal + spec limits + unit, optionally pinned to a
routing operation). Core owns the tables; a later PR seeds QC measurements from
the active plan, and PRO references it via FK for approval / AQL / certs.

Additive. Index names + the severity CHECK mirror the model so create_all
(tests/self-host) and Alembic (deploy) produce identical schema.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quality_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "product_id",
            sa.Integer,
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("revision", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_template", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        # A template has no product; a product-specific plan must name one.
        sa.CheckConstraint(
            "(is_template AND product_id IS NULL) OR "
            "(NOT is_template AND product_id IS NOT NULL)",
            name="ck_quality_plans_template_scope",
        ),
    )
    op.create_index("ix_quality_plans_product_id", "quality_plans", ["product_id"])
    op.create_index("ix_quality_plans_code", "quality_plans", ["code"])

    op.create_table(
        "quality_plan_characteristics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "quality_plan_id",
            sa.Integer,
            sa.ForeignKey("quality_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("characteristic", sa.String(100), nullable=False),
        sa.Column("nominal", sa.Numeric(18, 4), nullable=True),
        sa.Column("lower_limit", sa.Numeric(18, 4), nullable=True),
        sa.Column("upper_limit", sa.Numeric(18, 4), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("sequence", sa.Integer, nullable=False, server_default="0"),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column(
            "routing_operation_id",
            sa.Integer,
            sa.ForeignKey("routing_operations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "severity IN ('minor', 'major', 'critical')",
            name="ck_quality_plan_characteristics_severity",
        ),
    )
    op.create_index(
        "ix_quality_plan_characteristics_quality_plan_id",
        "quality_plan_characteristics",
        ["quality_plan_id"],
    )
    op.create_index(
        "ix_quality_plan_characteristics_routing_operation_id",
        "quality_plan_characteristics",
        ["routing_operation_id"],
    )


def downgrade() -> None:
    op.drop_table("quality_plan_characteristics")
    op.drop_table("quality_plans")
