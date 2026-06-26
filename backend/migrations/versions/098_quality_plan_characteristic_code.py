"""quality plan characteristic stable code (SPC key)

Revision ID: 098
Revises: 097
Create Date: 2026-06-26

#784 — SPC series must be keyed on a stable identifier. The display
`characteristic` text is rename- AND edit-fragile (the plan editor replaces
characteristic rows wholesale, minting new ids). A nullable `code` gives each
characteristic a durable, rename-proof key; SPC keys on `(product_id, code)`.

The same code recurs across plan versions on purpose (same series), so the
unique index is scoped per-plan and only over non-null codes — manual/ad-hoc
rows keep `code` NULL and fall back to text grouping.

Additive.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "098"
down_revision = "097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "quality_plan_characteristics",
        sa.Column("code", sa.String(50), nullable=True),
    )
    op.create_index(
        "uq_quality_plan_characteristics_plan_code",
        "quality_plan_characteristics",
        ["quality_plan_id", "code"],
        unique=True,
        postgresql_where=sa.text("code IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_quality_plan_characteristics_plan_code",
        table_name="quality_plan_characteristics",
    )
    op.drop_column("quality_plan_characteristics", "code")
