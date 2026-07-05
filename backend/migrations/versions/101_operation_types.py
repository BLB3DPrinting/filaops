"""operation-type catalog: schema + seed + backfill (#876 PR-1, inert)

Revision ID: 101
Revises: 100
Create Date: 2026-07-04

#876 PR-1 — every routing/production-order operation will eventually declare
a Type, and the Type decides WHEN its materials count as used (production
completion vs. ship vs. never-automatic), replacing the current runtime
guess from the free-text operation_code (operation_material_mapping.
OPERATION_CONSUME_STAGES). This migration ships the schema, the 9 system
type rows, and an EXACT-code-only backfill. It is a NO-OP for behavior:
no consumer reads operation_type yet (that's #876 PR-2), and the backfill
only types rows whose operation_code is byte-identical to one of the 18
legacy dict keys — proven behavior-neutral by the predicate-equivalence
test in tests/services/test_operation_type_catalog.py.

Steps:
1. CREATE TABLE operation_types — inspector-guarded (has-table check).
2. Seed the 9 system rows — INSERT-if-missing on unique code (mirrors
   seed_routing_templates's skip-existing pattern, routing_service.py).
3. ADD COLUMN operation_type VARCHAR(30) NULL on routing_operations and
   production_order_operations — inspector-guarded (has-column check).
4. Backfill: EXACT legacy-code matches ONLY (WHERE operation_type IS NULL,
   re-runnable), on both tables, using the alias map below. FINISH and POST
   get NO rule — deliberately excluded (live-ambiguous; see design §4a/§4d).
5. NO name-based classification here. A brownfield `alembic upgrade` must
   never auto-reclassify anyone's in-flight orders with only stdout as the
   record — that ships later as a human-gated endpoint (#876 PR-3).

Downgrade: drop the added columns + the operation_types table (never run on
the live 129 brownfield).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None


# Verbatim from app.services.operation_material_mapping.OPERATION_CONSUME_STAGES
# — reused so a typed op is byte-identical in behavior to its equivalent
# coded op. See design doc #876 comment §2c.
SEED_OPERATION_TYPES = [
    # code, label, description, category, consume_stages, is_qc, sort_order
    (
        "FDM_PRINT", "FDM Print",
        "Materials count when the production order completes.",
        "print", ["production", "any"], False, 10,
    ),
    (
        "RESIN_PRINT", "Resin Print",
        "Materials count when the production order completes.",
        "print", ["production", "any"], False, 20,
    ),
    (
        "ASSEMBLY", "Assembly",
        "Materials count when the production order completes.",
        "assembly", ["assembly", "production", "any"], False, 30,
    ),
    (
        "QUALITY_CONTROL", "Quality Control",
        "Materials count for nothing automatically.",
        "quality", ["any"], True, 40,
    ),
    (
        "SUPPORT_REMOVAL", "Support Removal / Cleanup",
        "Materials count for nothing automatically.",
        "finishing", ["any"], False, 50,
    ),
    (
        "SANDING", "Sanding",
        "Materials count for nothing automatically.",
        "finishing", ["any"], False, 60,
    ),
    (
        "PAINTING", "Painting",
        "Materials count for nothing automatically.",
        "finishing", ["finishing", "any"], False, 70,
    ),
    (
        "PACK_SHIP", "Pack / Ship",
        "Materials count when the order ships.",
        "shipping", ["shipping", "any"], False, 80,
    ),
    (
        "GENERAL", "Other (consumes at production)",
        "Materials count when the production order completes.",
        "other", ["production", "any"], False, 90,
    ),
]

# Exact operation_code -> operation_type alias map for the backfill.
# FINISH and POST are deliberately excluded — the live census shows FINISH
# spans shipping/quality/blank names, classifiable only per-row by name via
# the human-gated classifier (#876 PR-3), never by a migration.
BACKFILL_ALIAS_MAP = {
    "PRINT": "FDM_PRINT",
    "EXTRUDE": "GENERAL",
    "MOLD": "GENERAL",
    "CUT": "GENERAL",
    "MACHINE": "GENERAL",
    "ASSEMBLE": "ASSEMBLY",
    "BUILD": "ASSEMBLY",
    "WELD": "ASSEMBLY",
    "QC": "QUALITY_CONTROL",
    "INSPECT": "QUALITY_CONTROL",
    "TEST": "QUALITY_CONTROL",
    "CLEAN": "SUPPORT_REMOVAL",
    "SAND": "SANDING",
    "PAINT": "PAINTING",
    "COAT": "PAINTING",
    "PACK": "PACK_SHIP",
    "SHIP": "PACK_SHIP",
    "LABEL": "PACK_SHIP",
}


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return table in insp.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c["name"] for c in insp.get_columns(table)]
    return column in cols


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. CREATE TABLE operation_types
    # ------------------------------------------------------------------
    if not _has_table("operation_types"):
        op.create_table(
            "operation_types",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(30), nullable=False),
            sa.Column("label", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(20), nullable=True),
            sa.Column("consume_stages", sa.JSON(), nullable=False),
            sa.Column(
                "is_qc", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column(
                "is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")
            ),
            sa.Column(
                "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
            ),
            sa.Column(
                "sort_order", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.Column(
                "updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_operation_types_code"),
        )
        op.create_index("ix_operation_types_code", "operation_types", ["code"])

    # ------------------------------------------------------------------
    # 2. Seed the 9 system rows — INSERT-if-missing on unique code
    # ------------------------------------------------------------------
    bind = op.get_bind()
    operation_types_table = sa.table(
        "operation_types",
        sa.column("code", sa.String),
        sa.column("label", sa.String),
        sa.column("description", sa.Text),
        sa.column("category", sa.String),
        sa.column("consume_stages", sa.JSON),
        sa.column("is_qc", sa.Boolean),
        sa.column("is_system", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
    )

    existing_codes = {
        row[0]
        for row in bind.execute(sa.text("SELECT code FROM operation_types")).fetchall()
    }
    for code, label, description, category, consume_stages, is_qc, sort_order in SEED_OPERATION_TYPES:
        if code in existing_codes:
            continue
        bind.execute(
            operation_types_table.insert().values(
                code=code,
                label=label,
                description=description,
                category=category,
                consume_stages=consume_stages,
                is_qc=is_qc,
                is_system=True,
                is_active=True,
                sort_order=sort_order,
            )
        )

    # ------------------------------------------------------------------
    # 3. ADD COLUMN operation_type on both operation tables
    # ------------------------------------------------------------------
    for table in ("routing_operations", "production_order_operations"):
        if not _has_column(table, "operation_type"):
            op.add_column(
                table,
                sa.Column("operation_type", sa.String(30), nullable=True),
            )

    # ------------------------------------------------------------------
    # 4. Backfill: EXACT legacy-code matches ONLY, re-runnable.
    #    FINISH and POST get no rule (see module docstring).
    # ------------------------------------------------------------------
    for table in ("routing_operations", "production_order_operations"):
        for legacy_code, type_code in BACKFILL_ALIAS_MAP.items():
            bind.execute(
                sa.text(
                    f"""
                    UPDATE {table}
                    SET operation_type = :type_code
                    WHERE operation_type IS NULL
                      AND UPPER(operation_code) = :legacy_code
                    """
                ),
                {"type_code": type_code, "legacy_code": legacy_code},
            )

    # 5. NO name-based classification here — deliberately. See docstring.


def downgrade() -> None:
    for table in ("routing_operations", "production_order_operations"):
        if _has_column(table, "operation_type"):
            op.drop_column(table, "operation_type")

    if _has_table("operation_types"):
        op.drop_index("ix_operation_types_code", table_name="operation_types", if_exists=True)
        op.drop_table("operation_types")
