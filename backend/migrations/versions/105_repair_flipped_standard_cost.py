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

Step 2, standard costs that match the average cost.
    For an item whose purchase unit holds at least 10 stock units, a correct
    standard cost is about (units x average cost). A standard cost within 0.5x
    to 2x of the average cost itself can only be the per-stock-unit copy, and is
    multiplied back up by the units. The repaired value is built from the stored
    4-decimal average, so $12.67/KG comes back as $12.70.

Left alone, and listed in the upgrade output:
    - items where the two ranges are too close to tell apart (fewer than 10
      stock units per purchase unit);
    - items whose standard cost fits neither pattern;
    - items with no average cost, or a pack purchase unit with no pack size.
    Nothing is guessed.

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

# Below this many stock units per purchase unit, "equal to the average" and
# "units x the average" are too close to tell apart, so the item is left alone.
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

    Returns one of:
      "flipped"   - standard cost equals the per-stock-unit average: repair it
      "ok"        - standard cost is about units x average: per purchase unit
      "ambiguous" - fits neither pattern: leave alone and report
      "skip"      - not enough information, or the ranges overlap: leave alone
    """
    if standard_cost is None or average_cost is None:
        return "skip"
    standard = Decimal(str(standard_cost))
    average = Decimal(str(average_cost))
    if standard <= 0 or average <= 0:
        return "skip"
    units = stock_units_per_purchase_unit(unit, purchase_uom, purchase_factor)
    if units is None or units < MIN_UNITS:
        return "skip"
    ratio = standard / average
    if Decimal("0.5") <= ratio <= Decimal("2"):
        return "flipped"
    if units * Decimal("0.5") <= ratio <= units * Decimal("2"):
        return "ok"
    return "ambiguous"


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
    """Multiply flipped standard costs back up to per purchase unit.

    Returns ``{"repaired": [...], "ambiguous": [...]}``; each entry is a dict
    with the sku, the old and (for repairs) new standard cost, and the units.
    """
    rows = bind.execute(
        sa.text(
            "SELECT id, sku, unit, purchase_uom, purchase_factor, "
            "standard_cost, average_cost FROM products "
            "WHERE standard_cost IS NOT NULL AND average_cost IS NOT NULL "
            "AND UPPER(TRIM(COALESCE(purchase_uom, unit, 'EA'))) "
            "<> UPPER(TRIM(COALESCE(unit, 'EA'))) "
            "ORDER BY id"
        )
    ).mappings().all()

    report = {"repaired": [], "ambiguous": []}
    for row in rows:
        kind = classify(
            row["unit"], row["purchase_uom"], row["purchase_factor"],
            row["standard_cost"], row["average_cost"],
        )
        if kind == "ambiguous":
            report["ambiguous"].append(
                {"sku": row["sku"], "standard_cost": row["standard_cost"],
                 "average_cost": row["average_cost"]}
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
             "units": units}
        )
    return report


def upgrade() -> None:
    """Fix material purchase units, then repair flipped standard costs."""
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("products"):
        return

    changed_units = fix_material_purchase_units(bind)
    log.info("105: %d material(s) changed from purchase unit EA to KG", changed_units)

    report = repair_standard_costs(bind)
    for item in report["repaired"]:
        log.info(
            "105: %s standard_cost %s -> %s (x%s, back to per purchase unit)",
            item["sku"], item["old"], item["new"], item["units"],
        )
    for item in report["ambiguous"]:
        log.warning(
            "105: %s left alone: standard_cost %s fits neither pattern against "
            "average_cost %s. Check it by hand.",
            item["sku"], item["standard_cost"], item["average_cost"],
        )
    log.info(
        "105: repaired %d standard cost(s); %d left for a manual check",
        len(report["repaired"]), len(report["ambiguous"]),
    )


def downgrade() -> None:
    """No-op: the upgrade restores overwritten values; there is no 'before'."""
