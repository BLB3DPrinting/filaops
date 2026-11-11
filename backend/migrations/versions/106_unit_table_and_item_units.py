"""Unit table: the standard units with exact factors on every install, and a table for an item's own units

Revision ID: 106
Revises: 105
Create Date: 2026-11-11

Until now no upgrade filled ``units_of_measure``. Only the setup wizard's
example data did, with a pound of 0.453592 KG and an ounce of 0.0283495 KG.
An install set up without the example data had an empty table, and the
application fell back on copies of those rounded numbers written in the code.

This migration makes the table the one source of unit factors.

Schema
    ``units_of_measure.to_base_factor`` goes from NUMERIC(18, 8) to
    NUMERIC(30, 15). The exact ounce is 0.028349523125 KG, which is 12 decimal
    places.

    ``product_units`` is created: a unit that belongs to one item, with its
    size in the item's stock unit (a BOX of 12). Nothing fills it here.

Data, in this order
    1. The unit table.
       - Standard units the install lacks are added.
       - A standard weight, length, area or volume unit whose factor is a
         rounding of the exact one (0.453592 for the pound) is made exact. A
         factor that is not a rounding of it is left and listed: that install
         may measure the kind from another base unit.
       - A standard unit that was switched off is switched on and listed.
       - A code typed in lower case or with spaces is rewritten in upper case.
         Where the same code exists in two spellings (``kg`` and ``KG``) the
         upper-case row is kept and the other is switched off and listed. If
         the upper-case row is the one switched off, both are left and listed.
       - A standard code the install filed under a different kind (BOX as a
         counting unit of 12, OZ as a volume) is left exactly as it is and
         listed. It goes on converting as that install filed it.
       - Hours and minutes are added when missing. An existing HR or MIN row
         is never changed.
       - Any other row the install added keeps its kind, factor and state.
    2. Unit codes on items, BOM lines, routing material lines, vendor items,
       open purchase order lines and production order material rows not yet
       consumed are tidied: trimmed, upper-cased, and a known spelling read as
       its code (``pcs`` is EA). A unit the table holds under the typed code
       wins over a spelling: an install with its own PACK unit keeps it. A
       code the unit table does not know is listed with the rows that carry
       it, and left alone. Ledger rows are not touched.
    3. An item with no unit gets EA, which is what receiving already assumes.
       An item with no purchase unit gets its stock unit.

Safe to run twice: the second run changes nothing.

How it is written
    ``read_state`` reads the rows, ``plan`` decides every change and every
    list without touching the database, ``project`` returns the rows as they
    will be afterwards, ``apply`` writes, ``report_lines`` prints.
    ``scripts/uom_preflight.py`` runs read, plan and project against a
    database before it is upgraded, so an install can see this report first.
    Later migrations that follow the same shape plan from the projected state.

Downgrade: drops ``product_units`` and narrows the factor column again, which
rounds the exact factors. The data steps are not undone. The way back from an
upgrade is the backup taken before it (docs/ROLLBACK.md).
"""
import copy
import logging
from decimal import ROUND_HALF_UP, Decimal

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "106"
down_revision = "105"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Frozen copies: a migration must not import app code that can change later.
# A test fails if these differ from app.services.unit_conversion.
# (code, name, symbol, kind, base code, factor to the base)
_STANDARD_UNITS = (
    ("KG", "Kilogram", "kg", "weight", None, "1"),
    ("G", "Gram", "g", "weight", "KG", "0.001"),
    ("MG", "Milligram", "mg", "weight", "KG", "0.000001"),
    ("LB", "Pound", "lb", "weight", "KG", "0.45359237"),
    ("OZ", "Ounce", "oz", "weight", "KG", "0.028349523125"),
    ("M", "Meter", "m", "length", None, "1"),
    ("CM", "Centimeter", "cm", "length", "M", "0.01"),
    ("MM", "Millimeter", "mm", "length", "M", "0.001"),
    ("IN", "Inch", "in", "length", "M", "0.0254"),
    ("FT", "Foot", "ft", "length", "M", "0.3048"),
    ("M2", "Square meter", "m2", "area", None, "1"),
    ("CM2", "Square centimeter", "cm2", "area", "M2", "0.0001"),
    ("MM2", "Square millimeter", "mm2", "area", "M2", "0.000001"),
    ("IN2", "Square inch", "in2", "area", "M2", "0.00064516"),
    ("FT2", "Square foot", "ft2", "area", "M2", "0.09290304"),
    ("L", "Liter", "L", "volume", None, "1"),
    ("ML", "Milliliter", "mL", "volume", "L", "0.001"),
    ("EA", "Each", "ea", "quantity", None, "1"),
    ("HR", "Hour", "hr", "time", None, "1"),
    ("MIN", "Minute", "min", "time", "HR", "0.016666666666667"),
    ("BOX", "Box", "box", "pack", None, "1"),
    ("PK", "Pack", "pk", "pack", None, "1"),
    ("ROLL", "Roll", "roll", "pack", None, "1"),
    ("SPOOL", "Spool", "spool", "pack", None, "1"),
    ("SHEET", "Sheet", "sheet", "pack", None, "1"),
    ("CASE", "Case", "case", "pack", None, "1"),
    ("BAG", "Bag", "bag", "pack", None, "1"),
)

_SPELLINGS = {
    "PCS": "EA", "PC": "EA", "EACH": "EA", "UNIT": "EA", "UNITS": "EA",
    "PACK": "PK", "PACKS": "PK",
    "GRAM": "G", "GRAMS": "G",
    "KILOGRAM": "KG", "KILOGRAMS": "KG",
    "MILLIGRAM": "MG", "MILLIGRAMS": "MG",
}

# Kinds whose standard factors are exact by definition and are corrected.
_EXACT_KINDS = ("weight", "length", "area", "volume")
_TIME = "time"
_NAMED_ROWS = 25

# state key -> (table, the columns that hold a unit code)
_CODE_COLUMNS = {
    "items": ("products", ("unit", "purchase_uom")),
    "bom_lines": ("bom_lines", ("unit",)),
    "routing_lines": ("routing_operation_materials", ("unit",)),
    "order_lines": ("production_order_operation_materials", ("unit",)),
    "po_lines": ("purchase_order_lines", ("purchase_unit",)),
    "vendor_items": ("vendor_items", ("default_purchase_unit",)),
}

_WHAT = {
    ("items", "unit"): "item(s) with the stock unit",
    ("items", "purchase_uom"): "item(s) with the purchase unit",
    ("bom_lines", "unit"): "BOM line(s) in the unit",
    ("routing_lines", "unit"): "routing material line(s) in the unit",
    ("order_lines", "unit"): "production order material row(s) in the unit",
    ("po_lines", "purchase_unit"): "open purchase order line(s) in the unit",
    ("vendor_items", "default_purchase_unit"): "vendor item(s) with the purchase unit",
}
_TIDIED = {
    "items": "item", "bom_lines": "BOM line", "routing_lines": "routing material line",
    "order_lines": "production order material row", "po_lines": "open purchase order line",
    "vendor_items": "vendor item",
}


def tidy_code(code) -> str:
    """Trim and upper-case a unit code, and read a known spelling as its code."""
    tidy = (code or "").strip().upper()
    return _SPELLINGS.get(tidy, tidy)


def _is_rounding_of(stored: Decimal, exact: Decimal) -> bool:
    """True when ``stored`` is ``exact`` rounded to some number of decimal places."""
    for places in range(16):
        if exact.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP) == stored:
            return True
    return False


def _row_name(key: str, row: dict) -> str:
    """What a person can find a row by."""
    if key == "items":
        return str(row["sku"])
    if key == "bom_lines":
        return "BOM %s line %s" % (row["bom_id"], row["id"])
    if key == "po_lines":
        return "%s line %s" % (row["po_number"], row["id"])
    return "%s %s" % (_TIDIED[key], row["id"])


def _rows(bind, sql) -> list:
    return [dict(row) for row in bind.execute(sa.text(sql)).mappings().all()]


def read_state(bind) -> dict:
    """Read every row this migration, and the ones planned after it, decide from."""
    has = sa.inspect(bind).has_table
    state = {key: [] for key in (*_CODE_COLUMNS, "units", "item_units")}
    if has("units_of_measure"):
        state["units"] = _rows(
            bind,
            "SELECT u.id, u.code, u.name, u.symbol, u.uom_class, u.base_unit_id, b.code AS base_code, "
            "u.to_base_factor, u.active "
            "FROM units_of_measure u LEFT JOIN units_of_measure b ON b.id = u.base_unit_id ORDER BY u.id",
        )
    if has("products"):
        state["items"] = _rows(
            bind,
            "SELECT id, sku, unit, purchase_uom, purchase_factor, item_type, material_type_id "
            "FROM products ORDER BY id",
        )
    if has("bom_lines"):
        state["bom_lines"] = _rows(
            bind, "SELECT id, bom_id, component_id, quantity, unit FROM bom_lines ORDER BY id"
        )
    if has("routing_operation_materials"):
        state["routing_lines"] = _rows(
            bind,
            "SELECT id, component_id, quantity, unit FROM routing_operation_materials ORDER BY id",
        )
    if has("production_order_operation_materials"):
        # Rows not yet consumed: pending, allocated, and ones whose consumption failed.
        state["order_lines"] = _rows(
            bind,
            "SELECT id, component_id, quantity_required, unit, status "
            "FROM production_order_operation_materials "
            "WHERE status NOT IN ('consumed', 'returned') ORDER BY id",
        )
    if has("purchase_order_lines") and has("purchase_orders"):
        state["po_lines"] = _rows(
            bind,
            "SELECT l.id, l.product_id, l.purchase_unit, o.po_number "
            "FROM purchase_order_lines l JOIN purchase_orders o ON o.id = l.purchase_order_id "
            "WHERE o.status NOT IN ('received', 'closed', 'cancelled') ORDER BY l.id",
        )
    if has("vendor_items"):
        state["vendor_items"] = _rows(
            bind, "SELECT id, default_purchase_unit FROM vendor_items ORDER BY id"
        )
    if has("product_units"):
        state["item_units"] = _rows(
            bind,
            "SELECT id, product_id, unit_code, stock_units_per_unit, units_per_stock_unit "
            "FROM product_units ORDER BY id",
        )
    return state


def _plan_units(units: list) -> tuple:
    """Decide what happens to the unit table.

    Returns the plan, the codes that convert afterwards, and the codes whose
    only rows are switched off.
    """
    planned = {
        "add": [], "fix": [], "reactivate": [], "rename": [], "switch_off": [],
        "conflicts": [], "odd_factors": [], "spellings_left": [],
    }
    standard = {row[0]: row for row in _STANDARD_UNITS}
    by_code = {}
    for row in units:
        by_code.setdefault((row["code"] or "").strip().upper(), []).append(row)

    known, switched_off = set(), set()
    for code, rows in by_code.items():
        if not code:
            continue
        active = [row for row in rows if row["active"]]
        exact = [row for row in rows if row["code"] == code]
        # The row conversions use today: the upper-case one if it is in use, else the oldest in use.
        in_use = ([row for row in active if row["code"] == code] or active or [None])[0]
        keep = in_use or (exact or rows)[0]
        here = (keep["uom_class"] or "").strip().lower()
        usable = bool(active)
        wanted = standard.get(code)

        if wanted and wanted[3] == _TIME:
            pass  # hours and minutes are never changed
        elif wanted and here != wanted[3]:
            planned["conflicts"].append((code, here, wanted[3], Decimal(str(keep["to_base_factor"]))))
        elif exact and not exact[0]["active"] and active:
            planned["spellings_left"].append((code, in_use["code"]))
        else:
            if active and keep["code"] != code:
                planned["rename"].append((keep["id"], keep["code"], code))
            for other in active:
                if other["id"] != keep["id"]:
                    planned["switch_off"].append((other["id"], other["code"], code))
            if wanted:
                stored, exact_factor = Decimal(str(keep["to_base_factor"])), Decimal(wanted[5])
                if wanted[3] in _EXACT_KINDS and stored != exact_factor:
                    if _is_rounding_of(stored, exact_factor):
                        planned["fix"].append((keep["id"], code, stored, exact_factor))
                    else:
                        planned["odd_factors"].append((code, stored, exact_factor))
                if not usable:
                    planned["reactivate"].append((keep["id"], code))
                    usable = True
        (known if usable else switched_off).add(code)

    for row in _STANDARD_UNITS:
        if row[0] not in by_code:
            planned["add"].append(row)
            known.add(row[0])
    return planned, known, switched_off


def plan(state: dict) -> dict:
    """Decide every change and every list. Touches nothing."""
    units, known, switched_off = _plan_units(state["units"])
    result = {"units": units, "codes": [], "unknown": {}, "no_unit": [], "no_purchase_unit": []}

    def settle(key, row, column):
        """Return the code a column will hold, recording a rewrite or an unknown code."""
        raw = row[column]
        upper = (raw or "").strip().upper()
        if not upper:
            return ""
        # A unit the table holds under the typed code wins over a spelling.
        tidy = upper if upper in known else _SPELLINGS.get(upper, upper)
        if tidy not in known:
            entry = result["unknown"].setdefault(
                (key, column, raw), {"off": tidy in switched_off, "rows": []}
            )
            entry["rows"].append(_row_name(key, row))
            return raw
        if tidy != raw:
            result["codes"].append((key, row["id"], column, raw, tidy))
        return tidy

    for key, (_table, columns) in _CODE_COLUMNS.items():
        for row in state[key]:
            settled = {column: settle(key, row, column) for column in columns}
            if key != "items":
                continue
            stock = settled["unit"]
            if not stock:
                result["no_unit"].append((row["id"], row["sku"]))
                stock = "EA"
            if not settled["purchase_uom"]:
                result["no_purchase_unit"].append((row["id"], row["sku"], stock))
    return result


def project(state: dict, planned: dict) -> dict:
    """The state as it will be once ``planned`` is applied. Touches nothing."""
    after = copy.deepcopy(state)
    units = {row["id"]: row for row in after["units"]}
    for unit_id, _old, new in planned["units"]["rename"]:
        units[unit_id]["code"] = new
        for row in after["units"]:
            if row["base_unit_id"] == unit_id:
                row["base_code"] = new
    for unit_id, _code, _kept in planned["units"]["switch_off"]:
        units[unit_id]["active"] = False
    for unit_id, _code, _old, new in planned["units"]["fix"]:
        units[unit_id]["to_base_factor"] = new
    for unit_id, _code in planned["units"]["reactivate"]:
        units[unit_id]["active"] = True
    for code, name, symbol, kind, base, factor in planned["units"]["add"]:
        after["units"].append({
            "id": None, "code": code, "name": name, "symbol": symbol, "uom_class": kind,
            "base_unit_id": None, "base_code": base, "to_base_factor": Decimal(factor), "active": True,
        })

    rows = {key: {row["id"]: row for row in after[key]} for key in _CODE_COLUMNS}
    for key, row_id, column, _old, new in planned["codes"]:
        rows[key][row_id][column] = new
    for item_id, _sku in planned["no_unit"]:
        rows["items"][item_id]["unit"] = "EA"
    for item_id, _sku, stock in planned["no_purchase_unit"]:
        rows["items"][item_id]["purchase_uom"] = stock
    return after


def apply(bind, planned: dict) -> None:
    """Write the plan."""
    units = planned["units"]
    for unit_id, _code, _kept in units["switch_off"]:
        bind.execute(sa.text("UPDATE units_of_measure SET active = false WHERE id = :id"), {"id": unit_id})
    for unit_id, _old, new in units["rename"]:
        bind.execute(sa.text("UPDATE units_of_measure SET code = :code WHERE id = :id"), {"id": unit_id, "code": new})
    for unit_id, _code, _old, new in units["fix"]:
        bind.execute(
            sa.text("UPDATE units_of_measure SET to_base_factor = :factor WHERE id = :id"),
            {"id": unit_id, "factor": new},
        )
    for unit_id, _code in units["reactivate"]:
        bind.execute(sa.text("UPDATE units_of_measure SET active = true WHERE id = :id"), {"id": unit_id})

    insert = sa.text(
        "INSERT INTO units_of_measure (code, name, symbol, uom_class, base_unit_id, to_base_factor, active) "
        "VALUES (:code, :name, :symbol, :kind, "
        "(SELECT id FROM units_of_measure WHERE code = :base), :factor, true)"
    )
    # Base units first, so the others can point at them.
    for wants_base in (False, True):
        for code, name, symbol, kind, base, factor in units["add"]:
            if (base is not None) == wants_base:
                bind.execute(insert, {
                    "code": code, "name": name, "symbol": symbol, "kind": kind,
                    "base": base, "factor": Decimal(factor),
                })

    # One statement per table, column and new code, a thousand rows at a time.
    rewrites = {}
    for key, row_id, column, _old, new in planned["codes"]:
        rewrites.setdefault((_CODE_COLUMNS[key][0], column, new), []).append(row_id)
    for (table_name, column, new), ids in rewrites.items():
        table = sa.table(table_name, sa.column("id"), sa.column(column))
        for start in range(0, len(ids), 1000):
            bind.execute(
                sa.update(table).where(table.c.id.in_(ids[start:start + 1000])).values({column: new})
            )
    for item_id, _sku in planned["no_unit"]:
        bind.execute(sa.text("UPDATE products SET unit = 'EA' WHERE id = :id"), {"id": item_id})
    for item_id, _sku, stock in planned["no_purchase_unit"]:
        bind.execute(
            sa.text("UPDATE products SET purchase_uom = :unit WHERE id = :id"), {"id": item_id, "unit": stock}
        )


def _plain(number) -> str:
    """A factor without exponent notation or trailing zeros."""
    text = format(Decimal(str(number)), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _named(names: list) -> str:
    """The first rows by name, and how many more there are."""
    shown = ", ".join(str(name) for name in names[:_NAMED_ROWS])
    more = len(names) - _NAMED_ROWS
    return shown + (" and %d more" % more if more > 0 else "")


def report_lines(planned: dict) -> list:
    """The report as ``(logging level, line)`` pairs."""
    lines = []
    units = planned["units"]
    if units["add"]:
        lines.append((logging.INFO, "106: added %d standard unit(s): %s" % (
            len(units["add"]), ", ".join(row[0] for row in units["add"]))))
    for _id, code, old, new in units["fix"]:
        lines.append((logging.INFO, "106: %s factor made exact: %s -> %s" % (code, _plain(old), _plain(new))))
    for _id, old, new in units["rename"]:
        lines.append((logging.INFO, "106: unit code %r rewritten as %s" % (old, new)))
    for _id, code in units["reactivate"]:
        lines.append((logging.WARNING, "106: standard unit %s was switched off and is switched on again" % code))
    for _id, code, kept in units["switch_off"]:
        lines.append((logging.WARNING, "106: unit %r is the same code as %s and was switched off" % (code, kept)))
    for code, in_use in units["spellings_left"]:
        lines.append((logging.WARNING, (
            "106: LEFT unit %s: the row in use is spelled %r, and a row spelled %s exists but is switched off. "
            "Both are left as they are; conversions use the row in use."
        ) % (code, in_use, code)))
    for code, here, wanted, factor in units["conflicts"]:
        lines.append((logging.WARNING, (
            "106: LEFT unit %s: this install has it as a %s unit (factor %s); FilaOps reads %s as a %s unit. "
            "It is left exactly as it is and converts as this install filed it."
        ) % (code, here or "(no kind)", _plain(factor), code, wanted)))
    for code, stored, exact in units["odd_factors"]:
        lines.append((logging.WARNING, (
            "106: LEFT unit %s: its factor %s is not a rounding of the exact %s. This install may measure "
            "that kind from another base unit, so the row is left as it is."
        ) % (code, _plain(stored), _plain(exact))))

    tidied = {}
    for key, _id, _column, old, new in planned["codes"]:
        tidied[(key, old, new)] = tidied.get((key, old, new), 0) + 1
    for (key, old, new), count in sorted(tidied.items()):
        lines.append((logging.INFO, "106: %d %s unit code(s) %r rewritten as %s" % (count, _TIDIED[key], old, new)))
    for (key, column, code), entry in sorted(planned["unknown"].items(), key=lambda item: tuple(map(str, item[0]))):
        why = (
            "which is switched off in the unit table. Switch that unit back on, or change these to another unit"
            if entry["off"] else
            "which is not in the unit table. Add it under Units, or change these to a unit that is"
        )
        lines.append((logging.WARNING, "106: LEFT %d %s %r, %s: %s" % (
            len(entry["rows"]), _WHAT[(key, column)], code, why, _named(entry["rows"]))))
    for _id, sku in planned["no_unit"]:
        lines.append((logging.WARNING, "106: item %s had no unit and is set to EA" % sku))
    if planned["no_purchase_unit"]:
        lines.append((logging.INFO, "106: %d item(s) had no purchase unit and now have their stock unit: %s" % (
            len(planned["no_purchase_unit"]), _named([sku for _id, sku, _unit in planned["no_purchase_unit"]]))))
    if not lines:
        lines.append((logging.INFO, "106: the unit table and unit codes needed no change"))
    return lines


def changes(planned: dict) -> int:
    """How many rows the plan writes. Zero means a run would change nothing."""
    units = planned["units"]
    written = sum(len(units[name]) for name in ("add", "fix", "reactivate", "rename", "switch_off"))
    return written + len(planned["codes"]) + len(planned["no_unit"]) + len(planned["no_purchase_unit"])


def upgrade() -> None:
    """Widen the factor column, create ``product_units``, then run the data steps."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("units_of_measure"):
        return

    op.alter_column(
        "units_of_measure", "to_base_factor",
        type_=sa.Numeric(30, 15), existing_type=sa.Numeric(18, 8), existing_nullable=False,
    )
    if not inspector.has_table("product_units"):
        op.create_table(
            "product_units",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
            sa.Column("unit_code", sa.String(10), nullable=False),
            sa.Column("stock_units_per_unit", sa.Numeric(20, 10), nullable=True),
            sa.Column("units_per_stock_unit", sa.Numeric(20, 10), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("product_id", "unit_code", name="uq_product_units_product_unit"),
            sa.CheckConstraint(
                "(stock_units_per_unit IS NULL) <> (units_per_stock_unit IS NULL)",
                name="ck_product_units_one_size",
            ),
            sa.CheckConstraint(
                "COALESCE(stock_units_per_unit, units_per_stock_unit) > 0",
                name="ck_product_units_size_positive",
            ),
            sa.CheckConstraint("unit_code = UPPER(BTRIM(unit_code))", name="ck_product_units_code_tidy"),
        )
        op.create_index("ix_product_units_id", "product_units", ["id"])
        op.create_index("ix_product_units_product_id", "product_units", ["product_id"])

    planned = plan(read_state(bind))
    apply(bind, planned)
    for level, line in report_lines(planned):
        log.log(level, line)


def downgrade() -> None:
    """Undo the schema changes only. The data steps are not reversed."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("product_units"):
        op.drop_index("ix_product_units_product_id", table_name="product_units")
        op.drop_index("ix_product_units_id", table_name="product_units")
        op.drop_table("product_units")
    if inspector.has_table("units_of_measure"):
        op.alter_column(
            "units_of_measure", "to_base_factor",
            type_=sa.Numeric(18, 8), existing_type=sa.Numeric(30, 15), existing_nullable=False,
            postgresql_using="round(to_base_factor, 8)",
        )
