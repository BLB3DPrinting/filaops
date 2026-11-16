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
       meaning. Migration 105 (4.4.0) made this change only where the item had
       purchase order lines in KG and none in EA. The report marks the ones
       105's rule leaves, so someone who was told to set them by hand knows it
       is done. An open purchase order line in EA on a gram-stocked material is
       not changed, and is listed: receiving refused it before and still does.
    2. Item units worked out. An item bought in a unit the unit table cannot
       convert to its stock unit (a BOX of 12 on an item stocked by the each,
       an EA of 750 G on gram filament) gets that unit as one of its own, with
       the size the item already holds. No size, a size of 1, or a unit the
       table does not know gets no row and is listed. An item that already has
       a row for the unit keeps it; it is listed when the sizes differ. Where
       the unit table does convert the purchase unit but the item holds a
       different size (BOX filed as a counting unit of 12, and an item that
       says 10), nothing is changed and the item is listed: receiving uses the
       table and cost uses the item's size.
    3. Line units, on BOM lines, routing material lines, and production order
       material rows not yet consumed (pending, allocated, or failed).

       A line is rewritten to the component's stock unit, with the same
       quantity, in one case only. All of these hold:
       - the line is in EA, which is what a line gets when nobody picks a unit;
       - the component is a material stocked in G, or is not a material;
       - the component is not stocked by the each, and EA does not convert to
         its stock unit;
       - no reader takes the line by a size of the component's own. A
         component that is not a material and has a size for EA among its own
         units is left on every kind of line. A gram-stocked material that has
         one (a spool of 750 G bought by the each) is left on a BOM line only,
         because the BOM page's needed and shortage figures read that line as
         750 G. On a routing material line or a production order row nothing
         does, so the line is rewritten there, and the report names it in case
         it meant spools;
       - its stock unit is not a pack that requirements are not rounded for
         (ROLL, SPOOL): see the last point below.

       For such a line cost and planning already took the number as the stock
       unit, and so did the fulfilment queue when it reserved and consumed. On
       a production order no stock was reserved for it, and completing or
       shipping the order failed, because EA does not convert to G. After the
       rewrite those work, for the number the cost was worked out from. Two
       figures change with it:
       - a routing material's requirement in EA is rounded up to a whole
         number when a production order is sized. One in grams or metres is
         not;
       - on a material that step 1 moved from EA to KG, the BOM page showed
         each EA of such a line as 1000 G needed. It now shows the number as
         grams.

       Every other line the unit table cannot convert is left as written and
       listed with what each reader makes of it, because rewriting it would
       change a number or lose what the line meant. A line in a code the unit
       table does not know is not looked at: migration 106 lists those. A line
       with no unit at all is listed.

       The readers named in the report are the ones at this revision. Planning
       converts with its own short table of weights, lengths and volumes, not
       the unit table, so on an install that filed a standard code under
       another kind it can read a line differently from what is printed here.
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
# A test fails if these differ from the application's.
_SPELLINGS = {  # app.services.unit_conversion.UNIT_SPELLINGS
    "PCS": "EA", "PC": "EA", "EACH": "EA", "UNIT": "EA", "UNITS": "EA",
    "PACK": "PK", "PACKS": "PK",
    "GRAM": "G", "GRAMS": "G",
    "KILOGRAM": "KG", "KILOGRAMS": "KG",
    "MILLIGRAM": "MG", "MILLIGRAMS": "MG",
}
_PACK = "pack"  # app.services.unit_conversion.PACK
# A requirement in one of these is rounded up to a whole number when a production order is sized.
_COUNTED_UNITS = ("EA", "EACH", "PCS", "UNIT", "BOX", "BOXES")  # production_order_quantity_change.COUNTED_UNITS
# The units cost converts between by itself; for any other pair it uses the item's own size.
_COST_CLASSES = (  # the measurement classes of app.services.uom_service.INLINE_UOM_CONVERSIONS
    frozenset({"G", "KG", "LB", "OZ"}),
    frozenset({"MM", "CM", "M", "IN", "FT"}),
    frozenset({"ML", "L"}),
)
# What migration 105 read as EA on a purchase order line, besides EA itself and a blank.
_COUNT_SYNONYMS_105 = frozenset({"PCS", "PC", "EACH", "UNIT", "UNITS"})

_NAMED_ROWS = 25
# product_units holds a size to ten decimal places, in NUMERIC(20, 10).
_SIZE_PLACES = Decimal("0.0000000001")
_SIZE_LIMIT = Decimal("10000000000")
# products.purchase_factor holds six.
_FACTOR_PLACES = Decimal("0.000001")

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
        # A blank unit is kept, because 105 read it as EA.
        state["po_line_units"] = _rows(
            bind,
            "SELECT product_id, UPPER(BTRIM(purchase_unit)) AS unit FROM purchase_order_lines "
            "WHERE purchase_unit IS NOT NULL "
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


def _rounded(number: Decimal, places: Decimal) -> Decimal:
    """Round to ``places``. A ratio of two 15-place factors can be longer than the default 28 digits."""
    with localcontext() as context:
        context.prec = 80
        return number.quantize(places)


def _same_size(one: Decimal, other: Decimal) -> bool:
    """Whether two sizes agree to the six places an item's purchase size holds.

    A size typed the other way round (1 EA = 0.0833333333 BOX) is the same BOX of 12.
    """
    return _rounded(one, _FACTOR_PLACES) == _rounded(other, _FACTOR_PLACES)


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
    """A material as the application tests for one: the item type in any case, or a material type."""
    return str(item["item_type"] or "").lower() == "material" or item["material_type_id"] is not None


def _left_by_105(row: dict, ordered_in: set):
    """Why migration 105's rule leaves this gram / EA / 1000 material at EA, or None when it changes it.

    105 looked at items typed exactly ``material`` or linked to a material type, and changed
    one only when it had purchase order lines in KG and none in EA.
    """
    if not (row["item_type"] == "material" or row["material_type_id"] is not None):
        return None
    if "EA" in ordered_in:
        return "ea_lines"
    return None if "KG" in ordered_in else "no_kg_lines"


def _own_size(row: dict):
    """Stock units in one of an item's own units, whichever way round the size was typed."""
    direct = _positive(row["stock_units_per_unit"])
    if direct is not None:
        return direct
    inverse = _positive(row["units_per_stock_unit"])
    return _divide(Decimal("1"), inverse) if inverse is not None else None


def _through_own_units(table: _UnitTable, own: dict, unit: str):
    """Stock units in one ``unit`` by the item's own units: ``(size, the own unit it came through)``.

    The item has the unit itself, or one of the same kind that the unit table
    converts it to. This is the application's reading of an item's own units.
    ``(None, None)`` when it has neither.
    """
    if unit in own:
        return own[unit], unit
    for code, size in own.items():
        through = table.factor(unit, code)
        if through is not None:
            return through * size, code
    return None, None


def _cost_uses_item_size(purchase: str, stock: str) -> bool:
    """Whether cost takes the item's own size for this pair, not a conversion of its own."""
    return not any(purchase in units and stock in units for units in _COST_CLASSES)


def _line_name(key: str, row: dict) -> str:
    """What a person can find a line by."""
    if key == "bom_lines":
        return "BOM %s line %s" % (row["bom_id"], row["id"])
    if key == "routing_lines":
        return "routing %s material %s" % (row.get("routing_code") or "(no code)", row["id"])
    return "order %s material row %s" % (row.get("order_code") or "(no code)", row["id"])


def _plain(number) -> str:
    """A number without exponent notation or trailing zeros, to at most ten decimal places."""
    text = format(_rounded(Decimal(str(number)), _SIZE_PLACES), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _readings(key: str, table: _UnitTable, item: dict, unit: str) -> str:
    """What each reader at this revision makes of one ``unit`` on a line of this kind.

    BOM line, cost: on a material the line is turned into grams (KG is 1000,
    another unit goes through the unit table, one it cannot convert is taken as
    grams). On anything else a line in the item's purchase unit is multiplied
    by the item's size and any other is taken as the stock unit; the cost
    roll-up of a component with a BOM of its own ignores the unit. The BOM
    page's needed and shortage figures use the purchase-unit rule for every
    item. Planning takes the bare number. A production order refuses to
    convert; the fulfilment queue does not look at the unit.

    Routing material line and production order row: cost is the quantity times
    the cost per stock unit, whatever the line says.
    """
    stock = item["stock"]
    if key == "order_lines":
        return "cost takes 1 %s as 1 %s, no stock is reserved for it and consuming it fails" % (unit, stock)
    if key == "routing_lines":
        return (
            "cost takes 1 %s as 1 %s, planning takes 1 %s as 1 %s, and a production order made from it keeps "
            "the unit: no stock is reserved for that row and consuming it fails"
        ) % (unit, stock, unit, stock)

    by_purchase_size = item["size"] if (unit == item["purchase"] and item["size"] is not None) else Decimal("1")
    parts = []
    if item["material"]:
        grams = Decimal("1000") if unit == "KG" else (table.factor(unit, "G") or Decimal("1"))
        if table.kind(stock) == "weight":
            parts.append("cost takes 1 %s as %s G" % (unit, _plain(grams)))
        else:
            parts.append(
                "cost turns 1 %s into %s G and prices it per KG, which is not a real figure for an item "
                "stocked by the %s" % (unit, _plain(grams), stock)
            )
        parts.append("the BOM page's needed and shortage figures take 1 %s as %s %s" % (
            unit, _plain(by_purchase_size), stock))
    else:
        cost = "cost takes 1 %s as %s %s" % (unit, _plain(by_purchase_size), stock)
        if by_purchase_size != 1:
            cost += " (1 %s in the cost roll-up, if %s has a BOM of its own)" % (stock, item["sku"])
        parts.append(cost)
    parts.append("planning takes 1 %s as 1 %s" % (unit, stock))
    parts.append(
        "on a production order no stock is reserved for it and completing or shipping the order fails, while the "
        "fulfilment queue reserves and consumes 1 %s as 1 %s" % (unit, stock)
    )
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def plan(state: dict) -> dict:
    """Decide every change and every list. Touches nothing."""
    table = _UnitTable(state["units"])
    result = {
        "purchase_units": [], "purchase_units_left": [], "po_lines_left": [],
        "item_units": [], "kept": [], "no_item_unit": [], "sizes_differ": [],
        "lines": [], "lines_on_changed_materials": 0, "lines_despite_own_size": {}, "failed_rows": [],
        "left": {}, "no_unit_lines": {},
    }

    bought = {}
    for row in state["po_line_units"]:
        # As migration 105 read a purchase order line's unit: blank and the count spellings are EA.
        unit = (row["unit"] or "").strip().upper() or "EA"
        bought.setdefault(row["product_id"], set()).add("EA" if unit in _COUNT_SYNONYMS_105 else unit)
    own = {}
    for row in state["item_units"]:
        size = _own_size(row)
        if size is not None:
            own.setdefault(row["product_id"], {})[table.code(row["unit_code"])] = size

    items, changed_materials = {}, set()
    for row in state["items"]:
        item = {
            "sku": row["sku"], "stock": table.code(row["unit"]), "purchase": table.code(row["purchase_uom"]),
            "size": _positive(row["purchase_factor"]), "material": _is_material(row),
        }
        items[row["id"]] = item

        # 1. Gram filament bought by the each of 1000 is bought by the KG.
        if item["material"] and item["stock"] == "G" and item["purchase"] == "EA" and item["size"] == 1000:
            if table.factor("KG", "G") == 1000:
                result["purchase_units"].append(
                    (row["id"], row["sku"], _left_by_105(row, bought.get(row["id"], set())))
                )
                item["purchase"] = "KG"
                changed_materials.add(row["id"])
            else:
                result["purchase_units_left"].append(row["sku"])

        # 2. A purchase unit the unit table cannot convert becomes one of the item's own units.
        stock, purchase, size = item["stock"], item["purchase"], item["size"]
        if not stock or not purchase or purchase == stock:
            continue
        by_the_table = table.factor(purchase, stock)
        if by_the_table is not None:
            # The table converts it. Where cost takes the item's own size for this pair, the two have to agree.
            if _cost_uses_item_size(purchase, stock) and (size is None or not _same_size(size, by_the_table)):
                result["sizes_differ"].append((row["sku"], purchase, stock, by_the_table, size))
            continue
        unknown = next((code for code in (purchase, stock) if code not in table.units), None)
        if unknown:
            which = "purchase" if unknown == purchase else "stock"
            why = "%s_%s" % (which, "off" if unknown in table.off else "unknown")
            result["no_item_unit"].append((row["sku"], purchase, stock, why, unknown))
        elif size is None:
            result["no_item_unit"].append((row["sku"], purchase, stock, "no_size", ""))
        elif size == 1:
            result["no_item_unit"].append((row["sku"], purchase, stock, "size_one", ""))
        elif size >= _SIZE_LIMIT:
            result["no_item_unit"].append((row["sku"], purchase, stock, "too_large", _plain(size)))
        else:
            existing = own.get(row["id"], {}).get(purchase)
            if existing is None:
                result["item_units"].append((row["id"], row["sku"], purchase, size, stock))
                own.setdefault(row["id"], {})[purchase] = size
            elif not _same_size(existing, size):
                result["kept"].append((row["sku"], purchase, existing, size, stock))

    # An open purchase order line in EA on a gram-stocked material, whatever the item is bought by now.
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
            if not unit:
                result["no_unit_lines"].setdefault(key, []).append(_line_name(key, row))
                continue
            if not stock or unit == stock:
                continue
            # A code the unit table does not know says nothing about what the line means.
            if unit not in table.units or stock not in table.units:
                continue
            if table.factor(unit, stock) is not None:
                continue
            own_size, through = _through_own_units(table, own.get(row["component_id"], {}), unit)
            # A requirement in EA is rounded up for a production order; one in ROLL or SPOOL is not.
            rounding_would_stop = table.kind(stock) == _PACK and stock not in _COUNTED_UNITS
            note = ""
            if unit == "EA" and (not item["material"] or stock == "G"):
                # A size of the item's own for EA stands in the way where a reader uses it: every
                # line of a non-material, and a material's BOM line (the BOM page's figures).
                read_by_own_size = own_size is not None and (key == "bom_lines" or not item["material"])
                if not read_by_own_size and not rounding_would_stop:
                    result["lines"].append((key, row["id"], unit, stock))
                    if key == "bom_lines" and row["component_id"] in changed_materials:
                        result["lines_on_changed_materials"] += 1
                    if own_size is not None:
                        result["lines_despite_own_size"].setdefault(
                            (key, item["sku"], _plain(own_size), stock), []
                        ).append(_line_name(key, row))
                    if key == "order_lines" and row.get("status") == "error":
                        result["failed_rows"].append((_line_name(key, row), item["sku"], stock))
                    continue
                if own_size is None:
                    note = "rounding"
            group = result["left"].setdefault((key, item["sku"], unit, stock), {
                "names": [], "readings": _readings(key, table, item, unit),
                "own_size": own_size, "through": through, "note": note,
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


def _in_batches(rows: list):
    for start in range(0, len(rows), 1000):
        yield rows[start:start + 1000]


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
    new_rows = [
        {"product_id": item_id, "unit_code": unit, "size": size.quantize(_SIZE_PLACES)}
        for item_id, _sku, unit, size, _stock in planned["item_units"]
    ]
    for batch in _in_batches(new_rows):
        bind.execute(insert, batch)


def _named(names: list) -> str:
    """The first rows by name, and how many more there are."""
    shown = ", ".join(str(name) for name in names[:_NAMED_ROWS])
    more = len(names) - _NAMED_ROWS
    return shown + (" and %d more" % more if more > 0 else "")


def _as_text(key) -> tuple:
    """A sort key for a tuple that may hold numbers and None beside strings."""
    return tuple(map(str, key))


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
            ("ea_lines", "has purchase order lines in EA"),
            ("no_kg_lines", "has no purchase order lines in KG"),
        ):
            left_by_105 = [sku for _id, sku, reason in changed if reason == why]
            if left_by_105:
                lines.append((logging.WARNING, (
                    "107: %d of those: the 4.4.0 upgrade (migration 105) leaves a material at purchase unit EA "
                    "when it %s. If its output listed any of these for you to set by hand, that is done now: %s"
                ) % (len(left_by_105), said, _named(left_by_105))))
    if planned["purchase_units_left"]:
        lines.append((logging.WARNING, (
            "107: LEFT %d gram-stocked material(s) at purchase unit EA with size 1000: the unit table here does "
            "not hold a KG of 1000 G to change them to: %s"
        ) % (len(planned["purchase_units_left"]), _named(planned["purchase_units_left"]))))
    if planned["po_lines_left"]:
        lines.append((logging.WARNING, (
            "107: LEFT %d open purchase order line(s) in EA on gram-stocked material: receiving refuses them, as "
            "before. Change each line to a unit of weight (KG or G), with the quantity and the price in that "
            "unit, before receiving it: %s"
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
            "One of the two is wrong."
        ) % (sku, unit, _plain(existing), stock, _plain(size))))

    differ = {}
    for sku, purchase, stock, by_the_table, size in planned["sizes_differ"]:
        differ.setdefault((purchase, stock, _plain(by_the_table), _plain(size) if size is not None else ""), []
                          ).append(sku)
    for (purchase, stock, by_the_table, size), skus in sorted(differ.items()):
        theirs = "these items say %s" % size if size else "these items hold no size"
        lines.append((logging.WARNING, (
            "107: DIFFERENT SIZES for %d item(s) stocked by the %s and bought by the %s: the unit table says "
            "1 %s = %s %s, and %s. Receiving uses the unit table; cost uses the item's size. Nothing was "
            "changed. One of the two is wrong: %s"
        ) % (len(skus), stock, purchase, purchase, by_the_table, stock, theirs, _named(skus))))

    no_size = {}
    for sku, purchase, stock, why, detail in planned["no_item_unit"]:
        no_size.setdefault((why, purchase, stock, detail), []).append(sku)
    for (why, purchase, stock, detail), skus in sorted(no_size.items()):
        because = {
            "purchase_unknown": "their purchase unit %s is not in the unit table. Add %s under Units" % (
                detail, detail),
            "purchase_off": "their purchase unit %s is switched off in the unit table. Switch it back on under "
                            "Units" % detail,
            "stock_unknown": "their stock unit %s is not in the unit table. Add %s under Units" % (detail, detail),
            "stock_off": "their stock unit %s is switched off in the unit table. Switch it back on under "
                         "Units" % detail,
            "no_size": "they hold no size. Each needs how many %s are in one %s" % (stock, purchase),
            "size_one": "they hold a size of 1, which is often a default nobody typed, so no unit of their own "
                        "was made. Each needs how many %s are in one %s, also where it really is 1" % (
                            stock, purchase),
            "too_large": "their size, %s, is too large to record. Check it" % detail,
        }[why]
        lines.append((logging.WARNING, (
            "107: NO SIZE for %d item(s) stocked by the %s and bought by the %s, so %s cannot be converted for "
            "them: %s: %s"
        ) % (len(skus), stock, purchase, purchase, because, _named(skus))))

    rewritten = {}
    for key, _id, _old, new in planned["lines"]:
        rewritten[(key, new)] = rewritten.get((key, new), 0) + 1
    for (key, new), count in sorted(rewritten.items()):
        line = (
            "107: %d %s in EA on a component stocked by the %s now say %s, with the same quantity. Cost, "
            "planning and the fulfilment queue already took the number as %s. On a production order no stock "
            "was reserved for these lines and completing or shipping the order failed; both work now."
        ) % (count, _LINE_WORDS[key], new, new, new)
        if key != "bom_lines" and new not in _COUNTED_UNITS:
            line += " Their requirement is no longer rounded up to a whole number when an order is sized."
        lines.append((logging.INFO, line))
    if planned["lines_on_changed_materials"]:
        lines.append((logging.INFO, (
            "107: %d of those BOM line(s) are on the materials whose purchase unit became KG. The BOM page showed "
            "each EA on them as 1000 G needed; it now shows the number as grams, as cost and planning took it."
        ) % planned["lines_on_changed_materials"]))
    for (key, sku, own_size, stock), names in sorted(planned["lines_despite_own_size"].items()):
        lines.append((logging.WARNING, (
            "107: CHECK %d of those %s, on %s, which has EA as a unit of its own (1 EA = %s %s). They were "
            "taken as %s, which is how cost and planning already took them. If a line meant that many of the "
            "item, change its quantity: %s"
        ) % (len(names), _LINE_WORDS[key], sku, own_size, stock, stock, _named(names))))
    for name, sku, stock in planned["failed_rows"]:
        lines.append((logging.WARNING, (
            "107: %s (%s) had failed to be consumed and is still marked as failed. Its unit is now %s, so it "
            "goes through the next time its order is completed or shipped. If its stock was already corrected "
            "by hand, undo that correction first, or the item is deducted twice."
        ) % (name, sku, stock)))

    for (key, sku, unit, stock), group in sorted(planned["left"].items(), key=lambda entry: _as_text(entry[0])):
        if group["own_size"] is not None:
            if group["through"] == unit:
                has = "%s has %s as a unit of its own: 1 %s = %s %s." % (
                    sku, unit, unit, _plain(group["own_size"]), stock)
            else:
                has = "%s has %s as a unit of its own, which makes 1 %s = %s %s." % (
                    sku, group["through"], unit, _plain(group["own_size"]), stock)
            fix = (
                "%s Lines do not read an item's own units yet. If the line means that, leave it. If its number "
                "was meant in %s, change the line's unit to %s."
            ) % (has, stock, stock)
        else:
            fix = "To settle it, change the line's unit to %s and enter its quantity in %s." % (stock, stock)
            if group["note"] == "rounding":
                fix += (
                    " It was not rewritten for you because a requirement in EA is rounded up to a whole number "
                    "on a production order, and one in %s is not." % stock
                )
        lines.append((logging.WARNING, (
            "107: LEFT %d %s in %s on %s, which is stocked by the %s. The unit table cannot convert %s to %s. "
            "As FilaOps reads such a line: %s. %s Lines: %s"
        ) % (
            len(group["names"]), _LINE_WORDS[key], unit, sku, stock, unit, stock,
            group["readings"], fix, _named(group["names"]),
        )))

    for key, names in sorted(planned["no_unit_lines"].items()):
        advice = "" if key == "order_lines" else " Open each line and pick its unit."
        lines.append((logging.WARNING, (
            "107: LEFT %d %s with no unit at all. Some parts of FilaOps read a missing unit as EA and others as "
            "the component's stock unit.%s Lines: %s"
        ) % (len(names), _LINE_WORDS[key], advice, _named(names))))

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
