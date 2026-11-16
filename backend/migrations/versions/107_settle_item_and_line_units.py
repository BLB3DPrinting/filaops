"""Purchase units, item units and line units settled against the unit table

Revision ID: 107
Revises: 106
Create Date: 2026-11-16

Migration 106 made the unit table the one source of unit factors and tidied
every unit code. This one settles what the items and the lines say with those
codes. It changes no schema.

A "material" below is what the code at this revision treats as one: an item
whose item type is Material, or one linked to a material type.

Data, in this order
    1. Gram filament bought "by the each of 1000". The item form saved a new
       material as stock unit G, purchase unit EA, size 1000, which is a
       kilogram under another name: an EA line cannot be received for it. Its
       purchase unit becomes KG. The size stays 1000, so every cost keeps its
       meaning. Migration 105 made this change only where the item's purchase
       orders were in KG and none in EA; the report marks the ones it left.
       An open purchase order line in EA on such an item is not changed, and
       is listed: receiving refused it before and still does.
    2. Item units worked out. An item bought in a unit the unit table cannot
       convert to its stock unit (a BOX of 12 on an item stocked by the each,
       an EA of 750 G on gram filament) gets that unit as one of its own, with
       the size the item already holds. No size, a size of 1, or a unit the
       table does not know gets no row and is listed. An item that already has
       a row for the unit keeps it; it is listed when the sizes differ.
    3. Line units, on BOM lines, routing material lines, and production order
       material rows not yet consumed (pending, allocated, or failed). A line
       is rewritten to the component's stock unit, with the same quantity, in
       one case only: the line is in EA, the component is not stocked by the
       each, and the readers that give a number already take it as the stock
       unit. That is a material stocked in G, or an item that is not a
       material and cannot be entered by the each. EA is what a line gets when
       nobody picks a unit.

       For such a line cost and planning already took the number as the stock
       unit, while reserving or consuming stock for it failed, because EA does
       not convert to G. After the rewrite stock is reserved and consumed for
       the same number the cost was worked out from. One more thing changes
       with it: a requirement in EA is rounded up to a whole number when a
       production order is sized, and a requirement in grams or metres is
       not.

       Every other line the unit table cannot convert is left as written and
       listed with what each reader makes of it, because rewriting it would
       change a cost or lose what the line meant. A line in a code the unit
       table does not know is not looked at: migration 106 lists those.
    4. The item units from step 2 are written.

Safe to run twice: the second run changes nothing, and lists again what it
left.

How it is written
    The same five functions as migration 106: ``read_state``, ``plan``,
    ``project``, ``apply`` and ``report_lines``. ``scripts/uom_preflight.py``
    runs this plan on the rows migration 106 would leave, so an install sees
    both reports before it upgrades.

Downgrade: nothing. No schema changes here, and the data steps are not undone.
The way back from an upgrade is the backup taken before it (docs/ROLLBACK.md).
"""
import copy
import logging
from decimal import Decimal, localcontext

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "107"
down_revision = "106"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Frozen copies: a migration must not import app code that can change later.
# A test fails if these differ from app.services.unit_conversion.
_SPELLINGS = {
    "PCS": "EA", "PC": "EA", "EACH": "EA", "UNIT": "EA", "UNITS": "EA",
    "PACK": "PK", "PACKS": "PK",
    "GRAM": "G", "GRAMS": "G",
    "KILOGRAM": "KG", "KILOGRAMS": "KG",
    "MILLIGRAM": "MG", "MILLIGRAMS": "MG",
}
_PACK = "pack"

_NAMED_ROWS = 25
# product_units holds a size to ten decimal places.
_SIZE_PLACES = Decimal("0.0000000001")

# state key -> the table its lines live in
_LINES = {
    "bom_lines": "bom_lines",
    "routing_lines": "routing_operation_materials",
    "order_lines": "production_order_operation_materials",
}
_LINE_WORDS = {
    "bom_lines": "BOM line(s)",
    "routing_lines": "routing material line(s)",
    "order_lines": "production order material row(s)",
}
# What happens to stock for a line the unit table cannot convert.
_STOCK_READING = {
    "bom_lines": "reserving or consuming stock for it fails",
    "routing_lines": "a production order made from it keeps the unit, and consuming stock for that row fails",
    "order_lines": "consuming stock for it fails",
}
_STATE_KEYS = (
    "units", "items", "bom_lines", "routing_lines", "order_lines", "po_lines", "item_units", "po_line_units",
)


def _rows(bind, sql) -> list:
    return [dict(row) for row in bind.execute(sa.text(sql)).mappings().all()]


def read_state(bind) -> dict:
    """Read every row this migration decides from."""
    has = sa.inspect(bind).has_table
    state = {key: [] for key in _STATE_KEYS}
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
    if has("routing_operation_materials") and has("routing_operations") and has("routings"):
        state["routing_lines"] = _rows(
            bind,
            "SELECT m.id, m.component_id, m.quantity, m.unit, r.code AS routing_code "
            "FROM routing_operation_materials m "
            "LEFT JOIN routing_operations o ON o.id = m.routing_operation_id "
            "LEFT JOIN routings r ON r.id = o.routing_id ORDER BY m.id",
        )
    if has("production_order_operation_materials") and has("production_order_operations") \
            and has("production_orders"):
        # Rows not yet consumed: pending, allocated, and ones whose consumption failed.
        state["order_lines"] = _rows(
            bind,
            "SELECT m.id, m.component_id, m.quantity_required, m.unit, m.status, p.code AS order_code "
            "FROM production_order_operation_materials m "
            "LEFT JOIN production_order_operations o ON o.id = m.production_order_operation_id "
            "LEFT JOIN production_orders p ON p.id = o.production_order_id "
            "WHERE m.status NOT IN ('consumed', 'returned') ORDER BY m.id",
        )
    if has("purchase_order_lines") and has("purchase_orders"):
        state["po_lines"] = _rows(
            bind,
            "SELECT l.id, l.product_id, l.line_number, l.purchase_unit, o.po_number "
            "FROM purchase_order_lines l JOIN purchase_orders o ON o.id = l.purchase_order_id "
            "WHERE o.status NOT IN ('received', 'closed', 'cancelled') ORDER BY l.id",
        )
        # Every unit an item was ever ordered in, open or not: what migration 105 decided from.
        state["po_line_units"] = _rows(
            bind,
            "SELECT product_id, UPPER(BTRIM(purchase_unit)) AS unit FROM purchase_order_lines "
            "WHERE purchase_unit IS NOT NULL AND BTRIM(purchase_unit) <> '' "
            "GROUP BY product_id, UPPER(BTRIM(purchase_unit)) ORDER BY 1, 2",
        )
    if has("product_units"):
        state["item_units"] = _rows(
            bind,
            "SELECT id, product_id, unit_code, stock_units_per_unit, units_per_stock_unit "
            "FROM product_units ORDER BY id",
        )
    return state


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Divide without the default 28-digit limit getting in the way of 15-place factors."""
    with localcontext() as context:
        context.prec = 50
        return numerator / denominator


def _positive(value):
    """The value as a Decimal when it is greater than zero, otherwise None."""
    if value is None:
        return None
    number = Decimal(str(value))
    return number if number > 0 else None


class _UnitTable:
    """The unit table as the application reads it: the rows in use, by code."""

    def __init__(self, rows: list):
        self.units, seen = {}, set()
        for row in rows:
            code = (row["code"] or "").strip().upper()
            if not code:
                continue
            seen.add(code)
            # A row typed in upper case wins over the same code in another spelling.
            if row["active"] and (code not in self.units or row["code"] == code):
                kind = (row["uom_class"] or "").strip().lower()
                self.units[code] = (kind, Decimal(str(row["to_base_factor"])))
        # Codes whose only rows are switched off.
        self.off = seen - set(self.units)

    def code(self, typed) -> str:
        """The unit a typed code means. A unit the table holds under that code wins over a spelling."""
        tidy = (typed or "").strip().upper()
        if tidy in self.units or tidy in self.off:
            return tidy
        return _SPELLINGS.get(tidy, tidy)

    def kind(self, code: str):
        row = self.units.get(code)
        return row[0] if row else None

    def factor(self, source: str, target: str):
        """How many ``target`` are in one ``source``, or None when the table cannot convert them.

        Never for a pack: a pack has no size until an item gives it one.
        """
        if source == target:
            return Decimal("1")
        from_row, to_row = self.units.get(source), self.units.get(target)
        if not from_row or not to_row:
            return None
        if from_row[0] != to_row[0] or from_row[0] == _PACK or to_row[1] <= 0:
            return None
        return _divide(from_row[1], to_row[1])


def _is_material(item: dict) -> bool:
    """A material as the code at this revision tests for one."""
    return str(item["item_type"] or "").strip().lower() == "material" or item["material_type_id"] is not None


def _own_size(row: dict):
    """Stock units in one of an item's own units, whichever way round the size was typed."""
    direct = _positive(row["stock_units_per_unit"])
    if direct is not None:
        return direct
    inverse = _positive(row["units_per_stock_unit"])
    return _divide(Decimal("1"), inverse) if inverse is not None else None


def _through_own_units(table: _UnitTable, own: dict, unit: str):
    """Stock units in one ``unit`` by the item's own units, or None.

    The item has the unit itself, or one of the same kind that the unit table
    converts it to. This is the application's reading of an item's own units.
    """
    if unit in own:
        return own[unit]
    for code, size in own.items():
        through = table.factor(unit, code)
        if through is not None and code != unit:
            return through * size
    return None


def _line_name(key: str, row: dict) -> str:
    """What a person can find a line by."""
    if key == "bom_lines":
        return "BOM %s line %s" % (row["bom_id"], row["id"])
    if key == "routing_lines":
        return "routing %s material %s" % (row.get("routing_code") or "(no code)", row["id"])
    return "order %s material row %s" % (row.get("order_code") or "(no code)", row["id"])


def _cost_reading(key: str, table: _UnitTable, item: dict, unit: str) -> tuple:
    """What cost makes of one ``unit`` on a line of this kind: (how many, of which unit).

    A BOM line on a material is turned into grams: KG is 1000, any other unit
    goes through the unit table, and one it cannot convert is taken as grams.
    A BOM line on anything else in the item's purchase unit is multiplied by
    the item's size; any other is taken as the stock unit. A routing material's
    cost never looks at its unit.
    """
    if key == "bom_lines" and item["material"]:
        grams = Decimal("1000") if unit == "KG" else (table.factor(unit, "G") or Decimal("1"))
        return grams, "G"
    if key == "bom_lines" and unit == item["purchase"] and item["size"] is not None:
        return item["size"], item["stock"]
    return Decimal("1"), item["stock"]


def plan(state: dict) -> dict:
    """Decide every change and every list. Touches nothing."""
    table = _UnitTable(state["units"])
    result = {
        "purchase_units": [], "purchase_units_left": [], "po_lines_left": [],
        "item_units": [], "kept": [], "no_item_unit": [],
        "lines": [], "failed_rows": [], "left": {},
    }

    bought = {}
    for row in state["po_line_units"]:
        bought.setdefault(row["product_id"], set()).add(table.code(row["unit"]))
    own = {}
    for row in state["item_units"]:
        size = _own_size(row)
        if size is not None:
            own.setdefault(row["product_id"], {})[table.code(row["unit_code"])] = size

    items = {}
    for row in state["items"]:
        item = {
            "sku": row["sku"], "stock": table.code(row["unit"]), "purchase": table.code(row["purchase_uom"]),
            "size": _positive(row["purchase_factor"]), "material": _is_material(row),
        }
        items[row["id"]] = item

        # 1. Gram filament bought by the each of 1000 is bought by the KG.
        if item["material"] and item["stock"] == "G" and item["purchase"] == "EA" and item["size"] == 1000:
            if table.factor("KG", "G") == 1000:
                ordered_in = bought.get(row["id"], set())
                why_105_left_it = "ea_lines" if "EA" in ordered_in else (
                    None if "KG" in ordered_in else "no_kg_lines")
                result["purchase_units"].append((row["id"], row["sku"], why_105_left_it))
                item["purchase"] = "KG"
            else:
                result["purchase_units_left"].append(row["sku"])

        # 2. A purchase unit the unit table cannot convert becomes one of the item's own units.
        stock, purchase = item["stock"], item["purchase"]
        if not stock or not purchase or purchase == stock or table.factor(purchase, stock) is not None:
            continue
        unknown = next((code for code in (purchase, stock) if code not in table.units), None)
        if unknown:
            result["no_item_unit"].append((row["sku"], purchase, stock, "unknown", unknown))
        elif item["size"] is None:
            result["no_item_unit"].append((row["sku"], purchase, stock, "no_size", ""))
        elif item["size"] == 1:
            result["no_item_unit"].append((row["sku"], purchase, stock, "size_one", ""))
        else:
            existing = own.get(row["id"], {}).get(purchase)
            if existing is None:
                result["item_units"].append((row["id"], row["sku"], purchase, item["size"], stock))
                own.setdefault(row["id"], {})[purchase] = item["size"]
            elif existing.quantize(_SIZE_PLACES) != item["size"].quantize(_SIZE_PLACES):
                result["kept"].append((row["sku"], purchase, existing, item["size"], stock))

    # An open purchase order line in EA on filament that is now bought by the KG.
    for row in state["po_lines"]:
        item = items.get(row["product_id"])
        if item and item["material"] and item["stock"] == "G" and table.code(row["purchase_unit"]) == "EA":
            result["po_lines_left"].append(("%s line %s" % (row["po_number"], row["line_number"]), item["sku"]))

    # 3. Line units.
    for key in _LINES:
        for row in state[key]:
            item = items.get(row["component_id"])
            if not item:
                continue
            stock, unit = item["stock"], table.code(row["unit"])
            if not unit or not stock or unit == stock:
                continue
            # A code the unit table does not know says nothing about what the line means.
            if unit not in table.units or stock not in table.units:
                continue
            if table.factor(unit, stock) is not None:
                continue
            own_size = _through_own_units(table, own.get(row["component_id"], {}), unit)
            gram_material = item["material"] and stock == "G"
            by_the_each_is_meaningless = not item["material"] and own_size is None
            if unit == "EA" and (gram_material or by_the_each_is_meaningless):
                result["lines"].append((key, row["id"], row["unit"], stock))
                if key == "order_lines" and row.get("status") == "error":
                    result["failed_rows"].append((_line_name(key, row), item["sku"], stock))
                continue
            group = result["left"].setdefault((key, item["sku"], unit, stock), {
                "names": [], "cost": _cost_reading(key, table, item, unit), "own_size": own_size,
            })
            group["names"].append(_line_name(key, row))
    return result


def project(state: dict, planned: dict) -> dict:
    """The state as it will be once ``planned`` is applied. Touches nothing."""
    after = copy.deepcopy(state)
    items = {row["id"]: row for row in after["items"]}
    for item_id, _sku, _why in planned["purchase_units"]:
        items[item_id]["purchase_uom"] = "KG"
    rows = {key: {row["id"]: row for row in after[key]} for key in _LINES}
    for key, row_id, _old, new in planned["lines"]:
        rows[key][row_id]["unit"] = new
    for item_id, _sku, unit, size, _stock in planned["item_units"]:
        after["item_units"].append({
            "id": None, "product_id": item_id, "unit_code": unit,
            "stock_units_per_unit": size.quantize(_SIZE_PLACES), "units_per_stock_unit": None,
        })
    return after


def _in_batches(ids: list):
    for start in range(0, len(ids), 1000):
        yield ids[start:start + 1000]


def apply(bind, planned: dict) -> None:
    """Write the plan."""
    products = sa.table("products", sa.column("id"), sa.column("purchase_uom"))
    for ids in _in_batches([item_id for item_id, _sku, _why in planned["purchase_units"]]):
        bind.execute(sa.update(products).where(products.c.id.in_(ids)).values(purchase_uom="KG"))

    # One statement per table and new unit, a thousand rows at a time.
    rewrites = {}
    for key, row_id, _old, new in planned["lines"]:
        rewrites.setdefault((_LINES[key], new), []).append(row_id)
    for (table_name, new), all_ids in rewrites.items():
        lines = sa.table(table_name, sa.column("id"), sa.column("unit"))
        for ids in _in_batches(all_ids):
            bind.execute(sa.update(lines).where(lines.c.id.in_(ids)).values(unit=new))

    insert = sa.text(
        "INSERT INTO product_units (product_id, unit_code, stock_units_per_unit, created_at, updated_at) "
        "VALUES (:product_id, :unit_code, :size, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    for item_id, _sku, unit, size, _stock in planned["item_units"]:
        bind.execute(insert, {"product_id": item_id, "unit_code": unit, "size": size.quantize(_SIZE_PLACES)})


def _plain(number) -> str:
    """A number without exponent notation or trailing zeros."""
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

    changed = planned["purchase_units"]
    if changed:
        lines.append((logging.INFO, (
            "107: %d gram-stocked material(s) bought by the EA of 1000 G: purchase unit EA -> KG. The size stays "
            "1000, so no cost changes. A purchase order made from planning for them is now written in KG: %s"
        ) % (len(changed), _named([sku for _id, sku, _why in changed]))))
        for why, said in (
            ("ea_lines", "they have purchase order lines in EA"),
            ("no_kg_lines", "they have no purchase order lines in KG"),
        ):
            left_by_105 = [sku for _id, sku, reason in changed if reason == why]
            if left_by_105:
                lines.append((logging.WARNING, (
                    "107: of those, migration 105 left %d for a person to set, because %s. They are KG now: %s"
                ) % (len(left_by_105), said, _named(left_by_105))))
    if planned["purchase_units_left"]:
        lines.append((logging.WARNING, (
            "107: LEFT %d gram-stocked material(s) at purchase unit EA with size 1000: the unit table here does "
            "not hold a KG of 1000 G to change them to: %s"
        ) % (len(planned["purchase_units_left"]), _named(planned["purchase_units_left"]))))
    if planned["po_lines_left"]:
        lines.append((logging.WARNING, (
            "107: LEFT %d open purchase order line(s) in EA on gram-stocked material: receiving refuses them, as "
            "before. Change each line to KG, with the quantity and the price per KG, before receiving it: %s"
        ) % (len(planned["po_lines_left"]), _named(
            ["%s (%s)" % (name, sku) for name, sku in planned["po_lines_left"]]))))

    made = {}
    for _id, sku, unit, size, stock in planned["item_units"]:
        made.setdefault((unit, _plain(size), stock), []).append(sku)
    for (unit, size, stock), skus in sorted(made.items()):
        lines.append((logging.INFO, (
            "107: %d item(s) now have %s as a unit of their own, 1 %s = %s %s, from the purchase unit and size "
            "they already held: %s"
        ) % (len(skus), unit, unit, size, stock, _named(skus))))
    for sku, unit, existing, size, stock in planned["kept"]:
        lines.append((logging.WARNING, (
            "107: KEPT item %s's own unit as it is, 1 %s = %s %s, although its purchase size says %s. "
            "Check which is right."
        ) % (sku, unit, _plain(existing), stock, _plain(size))))
    no_size = {}
    for sku, purchase, stock, why, unknown in planned["no_item_unit"]:
        no_size.setdefault((why, purchase, stock, unknown), []).append(sku)
    for (why, purchase, stock, unknown), skus in sorted(no_size.items()):
        because = {
            "unknown": "the unit %s is not in the unit table. Add it under Units, or change the item's unit" % unknown,
            "no_size": "they hold no size. Set how many %s are in one %s on each item" % (stock, purchase),
            "size_one": "they hold a size of 1, which was filled in when nobody typed one. "
                        "Set how many %s are in one %s on each item" % (stock, purchase),
        }[why]
        lines.append((logging.WARNING, (
            "107: NO SIZE for %d item(s) stocked by the %s and bought by the %s, so %s cannot be converted for "
            "them: %s: %s"
        ) % (len(skus), stock, purchase, purchase, because, _named(skus))))

    rewritten = {}
    for key, _id, old, new in planned["lines"]:
        rewritten[(key, old, new)] = rewritten.get((key, old, new), 0) + 1
    for (key, old, new), count in sorted(rewritten.items()):
        lines.append((logging.INFO, (
            "107: %d %s in %s on a component stocked by the %s now say %s, with the same quantity. Cost and "
            "planning already took the number as %s. Stock could not be reserved or consumed for these lines "
            "before, and now is. Their requirement on a production order is no longer rounded up to a whole "
            "number."
        ) % (count, _LINE_WORDS[key], old, new, new, new)))
    for name, sku, stock in planned["failed_rows"]:
        lines.append((logging.WARNING, (
            "107: %s (%s) had failed to be consumed. Its unit is now %s like the rest; the row is still marked "
            "as failed."
        ) % (name, sku, stock)))

    for (key, sku, unit, stock), group in sorted(planned["left"].items()):
        cost_quantity, cost_unit = group["cost"]
        if group["own_size"] is not None:
            fix = "%s has %s as a unit of its own (1 %s = %s %s), which these readers do not use yet." % (
                sku, unit, unit, _plain(group["own_size"]), stock)
        else:
            fix = "It converts once %s has %s as a unit of its own with its size, or the line is changed to %s." % (
                sku, unit, stock)
        lines.append((logging.WARNING, (
            "107: LEFT %d %s in %s on %s, which is stocked by the %s. The unit table cannot convert %s to %s. "
            "As FilaOps reads such a line: cost takes 1 %s as %s %s, planning takes 1 %s as 1 %s, and %s. %s "
            "Lines: %s"
        ) % (
            len(group["names"]), _LINE_WORDS[key], unit, sku, stock, unit, stock,
            unit, _plain(cost_quantity), cost_unit, unit, stock, _STOCK_READING[key], fix,
            _named(group["names"]),
        )))

    if not lines:
        lines.append((logging.INFO, "107: purchase units, item units and line units needed no change"))
    return lines


def changes(planned: dict) -> int:
    """How many rows the plan writes. Zero means a run would change nothing."""
    return len(planned["purchase_units"]) + len(planned["item_units"]) + len(planned["lines"])


def upgrade() -> None:
    """Run the data steps. No schema changes."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("products"):
        return
    planned = plan(read_state(bind))
    apply(bind, planned)
    for level, line in report_lines(planned):
        log.log(level, line)


def downgrade() -> None:
    """Nothing to undo: no schema changed, and the data steps are not reversed."""
