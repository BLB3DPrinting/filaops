"""Add unique constraints to prevent duplicate materials on BOMs and routing operations.

bom_lines: (bom_id, component_id) must be unique — the same component cannot
appear twice on the same BOM. Users should adjust the quantity on the existing
line instead of adding a second line.

routing_operation_materials: (routing_operation_id, component_id) must be unique
for the same reason.

Before creating the constraints, any duplicate rows are consolidated: all rows
beyond the first (lowest id) for each duplicate group are deleted. This prevents
the migration from failing on existing environments that already contain duplicates.

Revision ID: 068
Revises: 066
"""
from alembic import op

revision = "068"
down_revision = "066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove duplicate bom_lines rows — keep the one with the lowest id per group
    op.execute("""
        DELETE FROM bom_lines
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM bom_lines
            GROUP BY bom_id, component_id
        )
    """)

    # Remove duplicate routing_operation_materials rows — same strategy
    op.execute("""
        DELETE FROM routing_operation_materials
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM routing_operation_materials
            GROUP BY routing_operation_id, component_id
        )
    """)

    op.create_unique_constraint(
        "uq_bom_lines_bom_component",
        "bom_lines",
        ["bom_id", "component_id"],
    )
    op.create_unique_constraint(
        "uq_routing_op_materials_op_component",
        "routing_operation_materials",
        ["routing_operation_id", "component_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_routing_op_materials_op_component", "routing_operation_materials", type_="unique")
    op.drop_constraint("uq_bom_lines_bom_component", "bom_lines", type_="unique")
