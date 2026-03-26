"""Merge migration heads 069 and 070.

069 (customer payment terms) and 070 (invoices) both descended from 068
on separate feature branches. This merge migration collapses them back
into a single Alembic head.

Revision ID: 071
Revises: 069, 070
"""

revision = "071"
down_revision = ("069", "070")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
