"""add maintenance_windows table

Revision ID: 092
Revises: 091
Create Date: 2026-06-12

SCHED-7: Planned maintenance becomes a first-class time block the
scheduling engine respects. A window targets EXACTLY ONE machine —
either a printer (dispatch path) or a machine resource (scheduler
modal path) — enforced by a CHECK constraint, mirroring the engine's
``is_printer`` duality.

Lifecycle: scheduled → in_progress → completed | cancelled.
Completion links the MaintenanceLog entry written for printer windows.

Additive table — no existing data touched.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "092"
down_revision = "091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "maintenance_windows",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "printer_id",
            sa.Integer,
            sa.ForeignKey("printers.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "resource_id",
            sa.Integer,
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("starts_at", sa.DateTime, nullable=False),
        sa.Column("ends_at", sa.DateTime, nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="scheduled",
        ),
        sa.Column(
            "maintenance_log_id",
            sa.Integer,
            sa.ForeignKey("maintenance_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "(printer_id IS NOT NULL) != (resource_id IS NOT NULL)",
            name="ck_maintenance_windows_one_machine",
        ),
        sa.CheckConstraint(
            "ends_at > starts_at",
            name="ck_maintenance_windows_valid_range",
        ),
    )
    op.create_index(
        "ix_maintenance_windows_printer_starts",
        "maintenance_windows",
        ["printer_id", "starts_at"],
    )
    op.create_index(
        "ix_maintenance_windows_resource_starts",
        "maintenance_windows",
        ["resource_id", "starts_at"],
    )
    op.create_index(
        "ix_maintenance_windows_status",
        "maintenance_windows",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_maintenance_windows_status", table_name="maintenance_windows")
    op.drop_index(
        "ix_maintenance_windows_resource_starts", table_name="maintenance_windows"
    )
    op.drop_index(
        "ix_maintenance_windows_printer_starts", table_name="maintenance_windows"
    )
    op.drop_table("maintenance_windows")
