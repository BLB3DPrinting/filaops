"""Add catalog system + extend price_levels columns

PR-06 Phase 1 (Core). Brings Core's schema in line with what PRO routes
expect. Additive only:

- price_levels: ADD COLUMN code, ADD COLUMN sort_order, plus a one-way
  rename guard for the `active` → `is_active` legacy drift.
- catalogs / catalog_products / customer_catalogs: CREATE TABLE if absent.
- pro_customer_price_levels: CREATE TABLE if absent — junction owned by
  PRO, declared in Core so a Core-only install has the schema available
  even before PRO is installed.

All CREATE TABLE statements are guarded by a runtime existence check so
the migration is idempotent against databases where PRO migrations
002/003 already created the tables. Same idempotency pattern PRO
migration 001 uses for gl_accounts.

The junction-table UniqueConstraints are also added retroactively for
DBs where PRO migration 003 created the tables without them — so the
post-082 state is identical regardless of which migration created the
table first.

Revision ID: 082
Revises: 081
Create Date: 2026-05-05
"""
from alembic import op
import sqlalchemy as sa


revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # ------------------------------------------------------------------
    # 1. price_levels — additive columns + legacy-drift rename guard
    # ------------------------------------------------------------------
    pl_cols = {c["name"] for c in inspector.get_columns("price_levels")}
    if "code" not in pl_cols:
        op.add_column(
            "price_levels",
            sa.Column("code", sa.String(10), nullable=True),
        )
        op.create_index(
            "ix_price_levels_code", "price_levels", ["code"], unique=True
        )
    if "sort_order" not in pl_cols:
        op.add_column(
            "price_levels",
            sa.Column(
                "sort_order",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    # Legacy drift: a removed Core migration (041_add_price_levels_and_customers)
    # created price_levels with column 'active' (PRO-style naming) instead of
    # the canonical Core 'is_active'. Any DB that bypassed Core migration 078
    # because the table already existed will have the wrong column name. Rename
    # only when the drift is observable; this is a one-way fix and intentionally
    # not reflected in downgrade() (un-renaming on a fresh DB would corrupt it).
    if "active" in pl_cols and "is_active" not in pl_cols:
        op.alter_column(
            "price_levels", "active", new_column_name="is_active"
        )
        # Defensive backfill: the legacy schema may have allowed NULLs or
        # lacked a server default. Match the canonical Core model
        # (Boolean, default=True, nullable=False) explicitly. Same pattern
        # other Core migrations (077, 079) use after schema-shape changes.
        op.execute(
            "UPDATE price_levels SET is_active = TRUE WHERE is_active IS NULL"
        )
        op.alter_column(
            "price_levels",
            "is_active",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        )

    # ------------------------------------------------------------------
    # 2. catalogs — UniqueConstraint("code") provides the backing index;
    #    no need for a separate ix_catalogs_code. PK is auto-indexed too.
    # ------------------------------------------------------------------
    if "catalogs" not in existing_tables:
        op.create_table(
            "catalogs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "is_default", sa.Boolean(), nullable=False, server_default="false"
            ),
            sa.Column(
                "is_public", sa.Boolean(), nullable=False, server_default="true"
            ),
            sa.Column(
                "sort_order", sa.Integer(), nullable=False, server_default="0"
            ),
            sa.Column(
                "active", sa.Boolean(), nullable=False, server_default="true"
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code", name="uq_catalogs_code"),
        )
        op.create_index("ix_catalogs_active", "catalogs", ["active"])
        op.create_index("ix_catalogs_is_public", "catalogs", ["is_public"])

    # ------------------------------------------------------------------
    # 3. catalog_products — junction table; UC enforces one row per pair.
    # ------------------------------------------------------------------
    if "catalog_products" not in existing_tables:
        op.create_table(
            "catalog_products",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("catalog_id", sa.Integer(), nullable=False),
            sa.Column("product_id", sa.Integer(), nullable=False),
            sa.Column("price_override", sa.Numeric(12, 4), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["catalog_id"],
                ["catalogs.id"],
                name="fk_catalog_products_catalog",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["product_id"],
                ["products.id"],
                name="fk_catalog_products_product",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "catalog_id",
                "product_id",
                name="uq_catalog_products_catalog_product",
            ),
        )
        op.create_index(
            "ix_catalog_products_catalog_id", "catalog_products", ["catalog_id"]
        )
        op.create_index(
            "ix_catalog_products_product_id", "catalog_products", ["product_id"]
        )
    # Retro UC-add: PRO migration 003 created this table without a
    # uniqueness constraint on (catalog_id, product_id). Add it now if
    # missing, so the post-082 state matches the Core model regardless
    # of who created the table first.
    cp_uniques = {
        c["name"] for c in inspector.get_unique_constraints("catalog_products")
    }
    if "uq_catalog_products_catalog_product" not in cp_uniques:
        op.create_unique_constraint(
            "uq_catalog_products_catalog_product",
            "catalog_products",
            ["catalog_id", "product_id"],
        )

    # ------------------------------------------------------------------
    # 4. customer_catalogs — FK customer_id → users.id (Core stores
    #    customers as User records with account_type='customer'; the
    #    PRO migration's customers.id target was wrong)
    # ------------------------------------------------------------------
    if "customer_catalogs" not in existing_tables:
        op.create_table(
            "customer_catalogs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("catalog_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["users.id"],
                name="fk_customer_catalogs_customer",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["catalog_id"],
                ["catalogs.id"],
                name="fk_customer_catalogs_catalog",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "customer_id",
                "catalog_id",
                name="uq_customer_catalogs_customer_catalog",
            ),
        )
        op.create_index(
            "ix_customer_catalogs_customer_id",
            "customer_catalogs",
            ["customer_id"],
        )
        op.create_index(
            "ix_customer_catalogs_catalog_id",
            "customer_catalogs",
            ["catalog_id"],
        )
    # Retro UC-add for the same reason as catalog_products above.
    cc_uniques = {
        c["name"] for c in inspector.get_unique_constraints("customer_catalogs")
    }
    if "uq_customer_catalogs_customer_catalog" not in cc_uniques:
        op.create_unique_constraint(
            "uq_customer_catalogs_customer_catalog",
            "customer_catalogs",
            ["customer_id", "catalog_id"],
        )

    # ------------------------------------------------------------------
    # 5. pro_customer_price_levels — junction for PRO customer-tier
    #    assignment. Created in Core so the schema is consistent across
    #    Core-only and Core+PRO installs. PRO routes read/write; Core
    #    never references this table directly.
    # ------------------------------------------------------------------
    if "pro_customer_price_levels" not in existing_tables:
        op.create_table(
            "pro_customer_price_levels",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("customer_id", sa.Integer(), nullable=False),
            sa.Column("price_level_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["customer_id"],
                ["users.id"],
                name="fk_pro_customer_price_levels_customer",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["price_level_id"],
                ["price_levels.id"],
                name="fk_pro_customer_price_levels_level",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "customer_id", name="uq_pro_customer_price_level_customer"
            ),
        )
        op.create_index(
            "ix_pro_customer_price_levels_customer_id",
            "pro_customer_price_levels",
            ["customer_id"],
        )
        op.create_index(
            "ix_pro_customer_price_levels_level_id",
            "pro_customer_price_levels",
            ["price_level_id"],
        )


def downgrade() -> None:
    """Reverse the additive changes.

    Asymmetry note: this migration may run on DBs where some tables already
    existed (created by PRO migration 002/003 before 082 ran). The downgrade
    drops those tables anyway — if you're rolling Core back past 082, the
    PRO migrations are also out of scope, so removing the schema is correct.
    Index drops use ``if_exists=True`` to tolerate cases where indexes were
    created with different names by PRO migrations.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "pro_customer_price_levels" in existing_tables:
        op.drop_index(
            "ix_pro_customer_price_levels_level_id",
            table_name="pro_customer_price_levels",
            if_exists=True,
        )
        op.drop_index(
            "ix_pro_customer_price_levels_customer_id",
            table_name="pro_customer_price_levels",
            if_exists=True,
        )
        op.drop_table("pro_customer_price_levels")

    if "customer_catalogs" in existing_tables:
        op.drop_index(
            "ix_customer_catalogs_catalog_id",
            table_name="customer_catalogs",
            if_exists=True,
        )
        op.drop_index(
            "ix_customer_catalogs_customer_id",
            table_name="customer_catalogs",
            if_exists=True,
        )
        op.drop_table("customer_catalogs")

    if "catalog_products" in existing_tables:
        op.drop_index(
            "ix_catalog_products_product_id",
            table_name="catalog_products",
            if_exists=True,
        )
        op.drop_index(
            "ix_catalog_products_catalog_id",
            table_name="catalog_products",
            if_exists=True,
        )
        op.drop_table("catalog_products")

    if "catalogs" in existing_tables:
        op.drop_index(
            "ix_catalogs_is_public", table_name="catalogs", if_exists=True
        )
        op.drop_index(
            "ix_catalogs_active", table_name="catalogs", if_exists=True
        )
        op.drop_table("catalogs")

    pl_cols = {c["name"] for c in inspector.get_columns("price_levels")}
    if "sort_order" in pl_cols:
        op.drop_column("price_levels", "sort_order")
    if "code" in pl_cols:
        op.drop_index(
            "ix_price_levels_code", table_name="price_levels", if_exists=True
        )
        op.drop_column("price_levels", "code")
