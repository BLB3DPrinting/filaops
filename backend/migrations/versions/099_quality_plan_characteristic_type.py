"""quality plan characteristic type (variable vs attribute)

Revision ID: 099
Revises: 098
Create Date: 2026-06-27

#784 — characteristics come in two flavors: VARIABLE (a measured value judged
against nominal + spec limits) and ATTRIBUTE (a pass/fail / Go-No-Go judgement
with no limits, e.g. "no visible defects"). Add a `characteristic_type`
discriminator (default "variable" so existing plans are unchanged) plus an
optional `acceptance_criteria` describing what counts as a pass for attribute
characteristics.

Additive; server_default backfills existing rows to "variable".
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quality_plan_characteristics",
        sa.Column(
            "characteristic_type",
            sa.String(20),
            nullable=False,
            server_default="variable",
        ),
    )
    op.add_column(
        "quality_plan_characteristics",
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "ck_quality_plan_characteristics_type",
        "quality_plan_characteristics",
        "characteristic_type IN ('variable', 'attribute')",
    )
    # Field coupling: attribute rows have no spec limits/unit; variable rows
    # have no acceptance criteria. Existing rows are all variable with a NULL
    # acceptance_criteria (just added), so they satisfy this.
    op.create_check_constraint(
        "ck_quality_plan_characteristics_type_fields",
        "quality_plan_characteristics",
        "(characteristic_type = 'attribute' "
        "AND nominal IS NULL AND lower_limit IS NULL "
        "AND upper_limit IS NULL AND unit IS NULL) "
        "OR (characteristic_type = 'variable' AND acceptance_criteria IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_quality_plan_characteristics_type_fields",
        "quality_plan_characteristics",
        type_="check",
    )
    op.drop_constraint(
        "ck_quality_plan_characteristics_type",
        "quality_plan_characteristics",
        type_="check",
    )
    op.drop_column("quality_plan_characteristics", "acceptance_criteria")
    op.drop_column("quality_plan_characteristics", "characteristic_type")
