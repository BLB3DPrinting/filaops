"""Add filament_diameter to material_types

Standard FDM filament diameters: 1.75mm (most common), 2.85mm (legacy/industrial).
Used for material-printer compatibility validation.

Revision ID: 079
Revises: 078
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "material_types",
        sa.Column(
            "filament_diameter",
            sa.Numeric(4, 2),
            nullable=True,
            server_default="1.75",
            comment="Filament diameter in mm (1.75 or 2.85)",
        ),
    )
    # Backfill existing rows
    op.execute("UPDATE material_types SET filament_diameter = 1.75 WHERE filament_diameter IS NULL")


def downgrade() -> None:
    op.drop_column("material_types", "filament_diameter")
