"""invoice void audit columns: voided_at, voided_by_id, void_reason (#894 PR-A)

Revision ID: 102
Revises: 101
Create Date: 2026-07-12

#894 PR-A — adds the void audit trail to invoices so POST /invoices/{id}/void
can record who voided an invoice, when, and why. A voided invoice is terminal
and out of the AR picture; if it had a posted receivable JE, the void posts a
mirror reversal (source_type='invoice_void') — that ledger work needs no schema
change, only these three metadata columns.

ADD COLUMN only (all nullable) — no table rewrite, safe on the live brownfield.
Inspector-guarded so a re-run (or an accumulated create_all() test DB that
already has the columns) is a no-op.

Downgrade: drop the three columns (never run on the live DB).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols


def _has_fk(table: str, name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names = {fk.get("name") for fk in insp.get_foreign_keys(table)}
    return name in names


def upgrade() -> None:
    if not _has_column("invoices", "voided_at"):
        op.add_column(
            "invoices",
            sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        )
    if not _has_column("invoices", "voided_by_id"):
        op.add_column(
            "invoices",
            sa.Column("voided_by_id", sa.Integer(), nullable=True),
        )
        if not _has_fk("invoices", "fk_invoices_voided_by_id_users"):
            op.create_foreign_key(
                "fk_invoices_voided_by_id_users",
                "invoices",
                "users",
                ["voided_by_id"],
                ["id"],
            )
    if not _has_column("invoices", "void_reason"):
        op.add_column(
            "invoices",
            sa.Column("void_reason", sa.String(length=255), nullable=True),
        )


def downgrade() -> None:
    if _has_fk("invoices", "fk_invoices_voided_by_id_users"):
        op.drop_constraint(
            "fk_invoices_voided_by_id_users", "invoices", type_="foreignkey"
        )
    for column in ("void_reason", "voided_by_id", "voided_at"):
        if _has_column("invoices", column):
            op.drop_column("invoices", column)
