"""company_settings.serial_number_prefix: shop-wide serial-number prefix

Revision ID: 104
Revises: 102
Create Date: 2026-10-13

Serial numbers used a hard-coded "BLB-" prefix. They now take a prefix from
Company Settings, so each shop can brand its own serials.

Numbering on existing installs must not change silently:
- an install that already has serials starting with "BLB-" gets "BLB-", so
  its next serial carries on the same sequence;
- every other install gets the neutral default "SN-".

Existing serial numbers are never rewritten.

If an install has BLB- serials but has never saved Company Settings (no row
yet), the row is created here with "BLB-". Otherwise the app would later
create it with the neutral default and the numbering would switch.

Numbering: revision "103" is taken by an unmerged branch (backup runs), so
this is "104" and revises "102". If 103 merges first, point down_revision at
"103" before merging so the history keeps a single head.

ADD COLUMN only (nullable) plus a one-row data update: safe on the live
brownfield. Inspector-guarded and idempotent, so a rerun is a no-op.

Downgrade: drop the column (never run on the live DB).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "104"
down_revision = "102"
branch_labels = None
depends_on = None


# Frozen copies: a migration must not import app code that can change later.
LEGACY_SERIAL_PREFIX = "BLB-"
DEFAULT_SERIAL_PREFIX = "SN-"

# company_settings columns that are NOT NULL with no database default, and the
# values the app's ORM defaults would give them. Used only when this migration
# has to create the settings row itself.
_REQUIRED_ROW_VALUES = {
    "tax_enabled": False,
    "default_quote_validity_days": 30,
    "external_ai_blocked": False,
    "auto_dispatch": False,
}


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def choose_serial_prefix(bind) -> str:
    """BLB- when the install already issued BLB- serials, else the default."""
    if not sa.inspect(bind).has_table("serial_numbers"):
        return DEFAULT_SERIAL_PREFIX
    has_legacy = bind.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM serial_numbers "
            "WHERE serial_number LIKE :pattern)"
        ),
        {"pattern": LEGACY_SERIAL_PREFIX + "%"},
    ).scalar()
    return LEGACY_SERIAL_PREFIX if has_legacy else DEFAULT_SERIAL_PREFIX


def _insert_settings_row(bind, prefix: str) -> None:
    values = {"id": 1, "serial_number_prefix": prefix}
    for col in sa.inspect(bind).get_columns("company_settings"):
        name = col["name"]
        if name in values or col["nullable"] or col.get("default") is not None:
            continue
        if col.get("autoincrement") is True:
            continue
        if name not in _REQUIRED_ROW_VALUES:
            # Fail loudly rather than let the app create the row later with
            # the neutral default and silently switch the numbering.
            raise RuntimeError(
                "Migration 104 needs to create the company_settings row to "
                f"keep the {prefix} serial prefix, but does not know a value "
                f"for required column {name!r}. Save Company Settings once in "
                "the app, then rerun the upgrade."
            )
        values[name] = _REQUIRED_ROW_VALUES[name]
    columns = ", ".join(values)
    params = ", ".join(f":{name}" for name in values)
    bind.execute(
        sa.text(f"INSERT INTO company_settings ({columns}) VALUES ({params})"),
        values,
    )


def backfill_serial_prefix(bind) -> str | None:
    """Set the prefix on installs that have not got one yet.

    Returns the prefix written, or None when nothing needed writing (value
    already set, or a fresh install where the app's default applies anyway).
    """
    prefix = choose_serial_prefix(bind)
    updated = bind.execute(
        sa.text(
            "UPDATE company_settings SET serial_number_prefix = :prefix "
            "WHERE serial_number_prefix IS NULL"
        ),
        {"prefix": prefix},
    ).rowcount
    if updated:
        return prefix

    has_row = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM company_settings)")
    ).scalar()
    if has_row or prefix == DEFAULT_SERIAL_PREFIX:
        return None

    _insert_settings_row(bind, prefix)
    return prefix


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_column(bind, "company_settings", "serial_number_prefix"):
        op.add_column(
            "company_settings",
            sa.Column("serial_number_prefix", sa.String(length=20), nullable=True),
        )
    backfill_serial_prefix(bind)


def downgrade() -> None:
    bind = op.get_bind()
    if _has_column(bind, "company_settings", "serial_number_prefix"):
        op.drop_column("company_settings", "serial_number_prefix")
