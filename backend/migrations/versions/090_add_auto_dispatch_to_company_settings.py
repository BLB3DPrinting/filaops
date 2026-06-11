"""add auto_dispatch to company_settings

Revision ID: 090
Revises: 089
Create Date: 2026-06-11

SCHED-3: Adds the ``auto_dispatch`` boolean column to ``company_settings``.
When True the frontend auto-confirms the top dispatch suggestion per idle
printer on each polling cycle, EXCEPT when a maintenance_warning is present
(that override is a hard rule enforced in the frontend and tested).

Additive column — default FALSE is correct for all existing installations
(opt-in behaviour; nothing changes unless the operator explicitly enables it).
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "090"
down_revision = "089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_settings",
        sa.Column(
            "auto_dispatch",
            sa.Boolean,
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("company_settings", "auto_dispatch")
