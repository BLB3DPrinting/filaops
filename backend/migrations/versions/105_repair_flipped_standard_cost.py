"""Repair standard costs that a PO receipt rewrote per stock unit

Revision ID: 105
Revises: 104
Create Date: 2026-11-09

``products.standard_cost`` is per PURCHASE unit ($/KG for filament).
``average_cost`` and ``last_cost`` are per STOCK unit ($/G). Until this
release, receiving a purchase order copied the per-gram average straight into
``standard_cost``, so a filament's $20.00 standard cost became $0.0200 on its
first receipt. Anything that reads standard cost as per purchase unit (BOM cost
rollups, the item screen's "/KG" label) was then 1000x low for that item.

The receipt code is fixed in the same release. This migration repairs the items
it already changed. Data only: no schema change.

Step 1, materials saved with a purchase unit of EA.
    The item form saved materials as stock G, purchase EA, factor 1000. EA
    cannot be converted to G, so these are set to purchase KG. 1 KG is 1000 G,
    so the meaning of the factor and of every cost is unchanged. Only rows that
    are exactly G / EA / 1000 materials are touched.

Step 2, standard costs the old receipt sync or Recost wrote.
    The old receipt sync did exactly ``standard_cost = average_cost``. Recost
    did the same for a purchased item with no standard cost, using the average
    cost, or the last cost when there was no average. Both only wrote to items
    with no active BOM and no active routing of their own. So a standard cost
    is repaired only when all of these hold:
      - it EQUALS the average cost (or, when the item has no average cost, the
        last cost), to the 4 decimal places the columns store;
      - the purchase unit holds at least 10 stock units, so an equal value
        cannot be a real per-purchase-unit price;
      - the item has no active BOM and no active routing (the sync never wrote
        to those; their standard cost comes from a cost rollup).
    It is then multiplied back up by the units. A ratio that is merely close is
    never enough. The repaired value is built from the stored 4-decimal
    average, so $12.67/KG comes back as $12.70.

Left alone, and listed in the upgrade output for a manual check:
    - a standard cost that equals the average on an item with fewer than 10
      stock units per purchase unit, with an active BOM or routing, or whose
      purchase unit is a pack with no pack size recorded;
    - a standard cost that is neither equal to the average nor about
      (units x average).
"The average" above means the last cost for an item with no average cost.
Left alone silently: items with no standard cost, or with neither an average
nor a last cost, and a pack with no pack size whose two costs differ (there is
nothing to compare them by). Nothing is guessed.

Idempotent: a repaired item no longer matches, so a rerun changes nothing.

Numbering: revision "103" is still held by an unmerged branch (see 104). This
is "105" and revises "104".

Downgrade: no-op. The upgrade restores values an earlier bug overwrote; there is
no correct "before" to return to.
"""
import logging
from decimal import ROUND_HALF_UP, Decimal

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "105"
down_revision = "104"
branch_labels = None
depends_on = None

log = logging.getLogger("alembic.runtime.migration")

# Frozen copies: a migration must not import app code that can change later.
# unit -> (class base unit, factor to that base)
_UNIT_CLASSES = {
    "G": ("KG", Decimal("0.001")),
    "KG": ("KG", Decimal("1")),
    "LB": ("KG", Decimal("0.453592")),
    "OZ": ("KG", Decimal("0.0283495")),
    "MM": ("M", Decimal("0.001")),
    "CM": ("M", Decimal("0.01")),
    "M": ("M", Decimal("1")),
    "IN": ("M", Decimal("0.0254")),
    "FT": ("M", Decimal("0.3048")),
    "ML": ("L", Decimal("0.001")),
    "L": ("L", Decimal("1")),
}
_COUNT_SYNONYMS = {"PCS", "PC", "EACH", "UNIT", "UNITS"}

# Below this many stock units per purchase unit, a standard cost equal to the
# average could be a real (if stale) per-purchase-unit price, so the item is
# reported for a manual check instead of repaired.
MIN_UNITS = Decimal("10")
_FOUR_DP = Decimal("0.0001")


def _unit(code) -> str:
    """Upper-case and trim a unit code; missing or a count synonym is EA."""
    unit = (code or "EA").upper().strip() or "EA"
    return "EA" if unit in _COUNT_SYNONYMS else unit


def stock_units_per_purchase_unit(unit, purchase_uom, purchase_factor):
    """Stock units in one purchase unit, or None when it cannot be known.

    Same unit is 1; units in the same measurement class use the physical
    conversion; otherwise the item's purchase_factor (a pack size).
    """
    stock = _unit(unit)
    purchase = _unit(purchase_uom or stock)
    if purchase == stock:
        return Decimal("1")
    purchase_info = _UNIT_CLASSES.get(purchase)
    stock_info = _UNIT_CLASSES.get(stock)
    if purchase_info and stock_info and purchase_info[0] == stock_info[0]:
        return purchase_info[1] / stock_info[1]
    if purchase_factor is not None and Decimal(str(purchase_factor)) > 0:
        return Decimal(str(purchase_factor))
    return None


def classify(unit, purchase_uom, purchase_factor, standard_cost, average_cost) -> str:
    """Say what a product's standard cost looks like.

    ``average_cost`` is the per-stock-unit cost to compare with: the item's
    average cost, or its last cost when it has no average (see ``stock_cost``).

    Returns one of:
      "flipped"   - standard cost EQUALS that per-stock-unit cost, which is
                    what the old receipt sync and Recost wrote: a candidate for
                    repair
      "ok"        - standard cost is about units x average: per purchase unit
      "ambiguous" - neither: leave alone and report for a manual check
      "skip"      - not enough information to say anything: leave alone

    Only exact equality (at the 4 decimal places the columns store) counts as
    flipped. A standard cost that is merely close to the average may have been
    set on purpose, so it is "ambiguous".
    """
    if standard_cost is None or average_cost is None:
        return "skip"
    standard = Decimal(str(standard_cost)).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)
    average = Decimal(str(average_cost)).quantize(_FOUR_DP, rounding=ROUND_HALF_UP)
    if standard <= 0 or average <= 0:
        return "skip"
    units = stock_units_per_purchase_unit(unit, purchase_uom, purchase_factor)
    if units == 1:
        return "skip"
    if units is None:
        # A pack with no pack size: nothing can be computed, but an equal value
        # is still worth a look, so it is reported instead of passed over.
        return "ambiguous" if standard == average else "skip"
    if standard == average:
        return "flipped" if units >= MIN_UNITS else "ambiguous"
    ratio = standard / average
    if units * Decimal("0.5") <= ratio <= units * Decimal("2"):
        return "ok"
    return "ambiguous"


def stock_cost(average_cost, last_cost):
    """The per-stock-unit cost to compare a standard cost with, and its name.

    Returns ``(value, "average")`` when the item has a positive average cost,
    else ``(value, "last")`` for a positive last cost, else ``(None, None)``.
    This is the order Recost used to fill in a missing standard cost.
    """
    for value, name in ((average_cost, "average"), (last_cost, "last")):
        if value is not None and Decimal(str(value)) > 0:
            return value, name
    return None, None


def products_with_own_costing(bind) -> set:
    """Ids of products with an active BOM or an active routing of their own.

    The old receipt sync skipped these, so it never wrote their standard cost;
    theirs comes from a cost rollup.
    """
    inspector = sa.inspect(bind)
    ids = set()
    if inspector.has_table("boms"):
        ids.update(
            row[0] for row in bind.execute(
                sa.text("SELECT DISTINCT product_id FROM boms WHERE active")
            )
        )
    if inspector.has_table("routings"):
        ids.update(
            row[0] for row in bind.execute(
                sa.text(
                    "SELECT DISTINCT product_id FROM routings "
                    "WHERE is_active AND product_id IS NOT NULL"
                )
            )
        )
    return ids


def fix_material_purchase_units(bind) -> int:
    """Set G / EA / 1000 materials to purchase unit KG. Returns the row count."""
    result = bind.execute(
        sa.text(
            "UPDATE products SET purchase_uom = 'KG' "
            "WHERE UPPER(TRIM(unit)) = 'G' "
            "AND UPPER(TRIM(purchase_uom)) = 'EA' "
            "AND purchase_factor = 1000 "
            "AND (item_type = 'material' OR material_type_id IS NOT NULL)"
        )
    )
    return result.rowcount or 0


def repair_standard_costs(bind) -> dict:
    """Multiply standard costs the old sync or Recost wrote back up to per purchase unit.

    Returns ``{"repaired": [...], "ambiguous": [...]}``. A repaired entry has
    the sku, the old and new standard cost and the units. An ambiguous entry
    has the sku, the standard cost, the cost it was compared with
    (``stock_cost``, and ``basis``: "average" or "last") and the reason it was
    left for a manual check.
    """
    own_costing = products_with_own_costing(bind)
    rows = bind.execute(
        sa.text(
            "SELECT id, sku, unit, purchase_uom, purchase_factor, "
            "standard_cost, average_cost, last_cost FROM products "
            "WHERE standard_cost IS NOT NULL "
            "AND (average_cost IS NOT NULL OR last_cost IS NOT NULL) "
            "AND UPPER(TRIM(COALESCE(purchase_uom, unit, 'EA'))) "
            "<> UPPER(TRIM(COALESCE(unit, 'EA'))) "
            "ORDER BY id"
        )
    ).mappings().all()

    report = {"repaired": [], "ambiguous": []}
    for row in rows:
        compare_cost, basis = stock_cost(row["average_cost"], row["last_cost"])
        if compare_cost is None:
            continue
        kind = classify(
            row["unit"], row["purchase_uom"], row["purchase_factor"],
            row["standard_cost"], compare_cost,
        )
        reason = None
        if kind == "ambiguous":
            reason = (
                f"standard cost is neither equal to the {basis} cost "
                f"nor about units x the {basis} cost"
            )
            if Decimal(str(row["standard_cost"])) == Decimal(str(compare_cost)):
                known_units = stock_units_per_purchase_unit(
                    row["unit"], row["purchase_uom"], row["purchase_factor"]
                )
                reason = (
                    f"equals the {basis} cost, but too few stock units per "
                    "purchase unit to be sure"
                    if known_units is not None
                    else f"equals the {basis} cost, and the purchase unit is a "
                    "pack with no pack size"
                )
        elif kind == "flipped" and row["id"] in own_costing:
            reason = f"equals the {basis} cost, but the item has an active BOM or routing"
        if reason:
            report["ambiguous"].append(
                {"sku": row["sku"], "standard_cost": row["standard_cost"],
                 "stock_cost": compare_cost, "basis": basis, "reason": reason}
            )
            continue
        if kind != "flipped":
            continue
        units = stock_units_per_purchase_unit(
            row["unit"], row["purchase_uom"], row["purchase_factor"]
        )
        new_cost = (Decimal(str(row["standard_cost"])) * units).quantize(
            _FOUR_DP, rounding=ROUND_HALF_UP
        )
        bind.execute(
            sa.text("UPDATE products SET standard_cost = :cost WHERE id = :id"),
            {"cost": new_cost, "id": row["id"]},
        )
        report["repaired"].append(
            {"sku": row["sku"], "old": row["standard_cost"], "new": new_cost,
             "units": units, "basis": basis}
        )
    return report


def report_lines(report: dict) -> list:
    """Turn a repair report into ``(logging level, message)`` pairs for the upgrade log."""
    lines = []
    for item in report["repaired"]:
        lines.append((
            logging.INFO,
            f"105: {item['sku']} standard_cost {item['old']} -> {item['new']} "
            f"(x{item['units']}, back to per purchase unit; it equalled the "
            f"{item['basis']} cost)",
        ))
    for item in report["ambiguous"]:
        lines.append((
            logging.WARNING,
            f"105: {item['sku']} left alone (standard_cost {item['standard_cost']}, "
            f"{item['basis']}_cost {item['stock_cost']}): {item['reason']}. "
            "Check it by hand.",
        ))
    lines.append((
        logging.INFO,
        f"105: repaired {len(report['repaired'])} standard cost(s); "
        f"{len(report['ambiguous'])} left for a manual check",
    ))
    return lines


def upgrade() -> None:
    """Fix material purchase units, then repair flipped standard costs."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("products"):
        return

    changed_units = fix_material_purchase_units(bind)
    log.info("105: %d material(s) changed from purchase unit EA to KG", changed_units)

    report = repair_standard_costs(bind)
    for level, line in report_lines(report):
        log.log(level, line)


def downgrade() -> None:
    """No-op: the upgrade restores overwritten values; there is no 'before'."""
