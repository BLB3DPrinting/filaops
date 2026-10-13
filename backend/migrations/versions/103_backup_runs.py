"""backup_runs: one row per database backup attempt

Revision ID: 103
Revises: 102
Create Date: 2026-10-13

Admins set up, run and download database backups from the Backups page. Each
attempt (scheduled or "Run backup now") is recorded here with its outcome, so
the page can list them and the Security Audit's backup_configured check can
read real results instead of guessing from files on disk.

The schedule itself is a system_settings row (key ``database_backup``); a
missing row means the defaults in app.services.database_backup apply, so no
seed is needed here.

CREATE TABLE only — no change to existing tables, safe on the live brownfield.
Inspector-guarded so a re-run (or a create_all() test DB) is a no-op.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "103"
down_revision = "102"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if _has_table("backup_runs"):
        return
    op.create_table(
        "backup_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=20), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("table_count", sa.Integer(), nullable=True),
        sa.Column("expected_tables", sa.Integer(), nullable=True),
        sa.Column("pg_dump_version", sa.String(length=100), nullable=True),
        sa.Column("server_version", sa.String(length=100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "triggered_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("file_deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_backup_runs_id", "backup_runs", ["id"])
    op.create_index("ix_backup_runs_status", "backup_runs", ["status"])
    op.create_index("ix_backup_runs_started_at", "backup_runs", ["started_at"])


def downgrade() -> None:
    if _has_table("backup_runs"):
        op.drop_table("backup_runs")
