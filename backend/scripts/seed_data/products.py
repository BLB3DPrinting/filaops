"""
Seed 30 products across 4 categories, plus their BOMs and routings.

Shape per the spec:
- 8 Signage + 7 Display Hardware + 10 Branded Keepsakes = 25 finished goods.
- 5 Raw Components (filament spools) = raw materials, no BOM, no routing.
- Each finished good gets a BOM with 1-3 raw material lines.
- 3 designated finished goods ALSO include a sub-assembly line (another
  finished good as a component) — exercises the multi-level BOM explosion.
- Each finished good gets a routing with 2-4 operations across PRINT, QA,
  PACK (and ASSEMBLE for items with sub-assemblies).

Infrastructure this module recreates after the wipe (migrations seeded them
initially, but wipe_all_tables clears them):
- 4 ItemCategory rows (SIGN, DISPLAY, KEEPSAKE, RAW)
- 3 WorkCenter rows (PRINT, QA, PACK)

Determinism: all quantities/operations use _time.rng() so output is stable
across reseeds with the same FILAOPS_DEMO_SEED.
"""
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.bom import BOM
from app.models.item_category import ItemCategory
from app.models.manufacturing import RoutingOperationMaterial
from app.models.product import Product
from app.models.work_center import WorkCenter
from app.schemas.bom import BOMCreate, BOMLineCreate
from app.services import bom_management_service, routing_service

from scripts.seed_data import _time


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

CATEGORY_DEFS = [
    ("SIGN",     "Signage",           "Venue signs, directional markers, event placards"),
    ("DISPLAY",  "Display Hardware",  "Easels, counter stands, brochure holders"),
    ("KEEPSAKE", "Branded Keepsakes", "Logo tags, coins, badges, awards"),
    ("RAW",      "Raw Components",    "Filament spools and raw materials"),
]


# ---------------------------------------------------------------------------
# Work centers — referenced by routing operations
# ---------------------------------------------------------------------------

WORK_CENTER_DEFS = [
    # code,    name,           center_type,  machine_rate, labor_rate, overhead_rate
    ("PRINT", "FDM Print Pool", "machine",    Decimal("8.00"),  Decimal("0.00"),  Decimal("3.00")),
    ("QA",    "Quality Check",  "station",    Decimal("0.00"),  Decimal("22.00"), Decimal("3.00")),
    ("PACK",  "Packing Bench",  "station",    Decimal("0.00"),  Decimal("18.00"), Decimal("3.00")),
]


# ---------------------------------------------------------------------------
# Product catalog
# ---------------------------------------------------------------------------

# (sku, name, cat_code, is_raw_material, unit, purchase_uom, purchase_factor,
#  standard_cost, selling_price, reorder_point)
#
# Raw materials: unit='G' / purchase='KG' (spec uom_config.py: $/KG, grams).
# Finished goods: unit='EA'.

SIGNAGE_PRODUCTS = [
    ("SIGN-001", "Venue Sign 12in",          12.00, 32.00),
    ("SIGN-002", "Venue Sign 18in",          18.00, 46.00),
    ("SIGN-003", "Directional Marker Small",  4.50, 12.00),
    ("SIGN-004", "Directional Marker Large",  9.00, 24.00),
    ("SIGN-005", "Aisle Placard",             6.00, 16.00),
    ("SIGN-006", "Wall Plaque 6x8",          10.00, 26.00),
    ("SIGN-007", "Wall Plaque 12x16",        22.00, 58.00),
    ("SIGN-008", "Event Badge Holder",        2.00,  6.00),
]

DISPLAY_PRODUCTS = [
    ("DISP-001", "Tabletop Easel Small",     5.00, 14.00),
    ("DISP-002", "Tabletop Easel Large",    10.00, 28.00),
    ("DISP-003", "Counter Stand Medium",    14.00, 38.00),
    ("DISP-004", "Retail Shelf Bracket",     7.00, 18.00),
    ("DISP-005", "Brochure Holder Single",   8.00, 22.00),
    ("DISP-006", "Brochure Holder Triple",  16.00, 44.00),
    ("DISP-007", "Price Tag Stand",          3.00,  9.00),
]

KEEPSAKE_PRODUCTS = [
    ("KEEP-001", "Logo Tag Round",            1.00,  4.00),
    ("KEEP-002", "Logo Tag Square",           1.00,  4.00),
    ("KEEP-003", "Welcome Coin",              1.50,  5.00),
    ("KEEP-004", "Desk Paperweight",          4.00, 12.00),
    ("KEEP-005", "Keychain Fob",              0.80,  3.50),
    ("KEEP-006", "Name Tag Badge",            1.20,  4.50),
    ("KEEP-007", "Award Medallion",           3.50, 11.00),
    ("KEEP-008", "Gift Box Insert",           2.50,  8.00),
    ("KEEP-009", "Magnet Backer",             0.60,  2.50),
    ("KEEP-010", "Pin Blank",                 0.40,  2.00),
]

# Raw filament spools: costs are per-KG (purchase unit), stored in grams.
# selling_price left as cost (we don't resell raw filament to customers).
RAW_PRODUCTS = [
    # sku, name, cost_per_kg, reorder_point_grams
    ("RAW-PLA-BLK", "Raw PLA Spool - Black (1kg)",  Decimal("20.00"),  500),
    ("RAW-PLA-WHT", "Raw PLA Spool - White (1kg)",  Decimal("20.00"),  500),
    ("RAW-PLA-RED", "Raw PLA Spool - Red (1kg)",    Decimal("22.00"),  500),
    ("RAW-PETG-CLR","Raw PETG Spool - Clear (1kg)", Decimal("25.00"), 1200),
    ("RAW-ABS-BLK", "Raw ABS Spool - Black (1kg)",  Decimal("28.00"), 1200),
]


# ---------------------------------------------------------------------------
# Multi-level BOM wiring: 3 finished goods whose BOM includes another
# finished good as a sub-assembly. Each tuple is (parent_sku, sub_sku).
# ---------------------------------------------------------------------------

MULTI_LEVEL_BOMS = [
    ("DISP-003", "KEEP-001"),   # Counter Stand Medium uses Logo Tag Round
    ("DISP-002", "KEEP-004"),   # Tabletop Easel Large uses Desk Paperweight
    ("SIGN-007", "KEEP-009"),   # Wall Plaque 12x16 uses Magnet Backer
]


# ---------------------------------------------------------------------------

def _seed_categories(db: Session, now) -> dict[str, int]:
    cat_ids: dict[str, int] = {}
    for idx, (code, name, description) in enumerate(CATEGORY_DEFS):
        cat = ItemCategory(
            code=code,
            name=name,
            description=description,
            sort_order=idx,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(cat)
        db.flush()
        cat_ids[code] = cat.id
    return cat_ids


def _seed_work_centers(db: Session, now) -> dict[str, int]:
    wc_ids: dict[str, int] = {}
    for code, name, center_type, machine_rate, labor_rate, overhead_rate in WORK_CENTER_DEFS:
        wc = WorkCenter(
            code=code,
            name=name,
            center_type=center_type,
            capacity_hours_per_day=Decimal("16.00"),
            machine_rate_per_hour=machine_rate,
            labor_rate_per_hour=labor_rate,
            overhead_rate_per_hour=overhead_rate,
            hourly_rate=machine_rate + labor_rate + overhead_rate,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(wc)
        db.flush()
        wc_ids[code] = wc.id
    return wc_ids


def _seed_finished_good(db, now, sku, name, cat_id, cost, price):
    p = Product(
        sku=sku,
        name=name,
        item_type="finished_good",
        procurement_type="make",
        category_id=cat_id,
        unit="EA",
        purchase_uom="EA",
        standard_cost=Decimal(str(cost)),
        average_cost=Decimal(str(cost)),
        last_cost=Decimal(str(cost)),
        selling_price=Decimal(str(price)),
        has_bom=True,
        is_raw_material=False,
        active=True,
        is_public=True,
        stocking_policy="on_demand",
        created_at=now,
        updated_at=now,
    )
    db.add(p)
    db.flush()
    return p


def _seed_raw_material(db, now, sku, name, cat_id, cost_per_kg, reorder_g):
    p = Product(
        sku=sku,
        name=name,
        item_type="supply",
        procurement_type="buy",
        category_id=cat_id,
        unit="G",
        purchase_uom="KG",
        purchase_factor=Decimal("1000"),
        standard_cost=cost_per_kg,
        average_cost=cost_per_kg,
        last_cost=cost_per_kg,
        selling_price=None,
        has_bom=False,
        is_raw_material=True,
        active=True,
        is_public=False,
        reorder_point=Decimal(str(reorder_g)),
        safety_stock=Decimal("200"),
        lead_time_days=7,
        stocking_policy="stocked",
        created_at=now,
        updated_at=now,
    )
    db.add(p)
    db.flush()
    return p


def _build_bom_lines(
    rng,
    product_sku: str,
    raw_ids: list[int],
    finished_good_ids: dict[str, int],
) -> list[BOMLineCreate]:
    """One BOM: 1-3 raw material lines + optional sub-assembly for
    multi-level BOMs."""
    num_raw = rng.randint(1, 3)
    chosen = rng.sample(raw_ids, k=num_raw)
    lines: list[BOMLineCreate] = []
    for i, raw_id in enumerate(chosen, start=1):
        lines.append(
            BOMLineCreate(
                component_id=raw_id,
                quantity=Decimal(str(rng.randint(5, 80))),  # grams of filament
                unit="G",
                sequence=i,
                consume_stage="production",
            )
        )

    sub_sku = next((sub for parent, sub in MULTI_LEVEL_BOMS if parent == product_sku), None)
    if sub_sku:
        lines.append(
            BOMLineCreate(
                component_id=finished_good_ids[sub_sku],
                quantity=Decimal("1"),
                unit="EA",
                sequence=len(lines) + 1,
                consume_stage="production",
            )
        )
    return lines


def _build_routing_ops(rng, wc_ids: dict[str, int], has_subassembly: bool) -> list[dict]:
    """2-4 operations: PRINT always; then either [QA, PACK] or
    [QA, ASSEMBLE, PACK] for multi-level BOMs, or just [PACK] for 2-op
    routings."""
    ops: list[dict] = []
    seq = 1

    ops.append({
        "sequence": seq,
        "work_center_id": wc_ids["PRINT"],
        "operation_code": "PRINT",
        "operation_name": "Print",
        "setup_time_minutes": Decimal("2"),
        "run_time_minutes": Decimal(str(rng.randint(60, 180))),
    })
    seq += 1

    if has_subassembly:
        ops.append({
            "sequence": seq,
            "work_center_id": wc_ids["QA"],
            "operation_code": "QA",
            "operation_name": "Quality Check",
            "setup_time_minutes": Decimal("0"),
            "run_time_minutes": Decimal("5"),
        })
        seq += 1
        ops.append({
            "sequence": seq,
            "work_center_id": wc_ids["PACK"],
            "operation_code": "ASSEMBLE",
            "operation_name": "Assemble sub-components",
            "setup_time_minutes": Decimal("1"),
            "run_time_minutes": Decimal("8"),
        })
        seq += 1
        ops.append({
            "sequence": seq,
            "work_center_id": wc_ids["PACK"],
            "operation_code": "PACK",
            "operation_name": "Pack",
            "setup_time_minutes": Decimal("0"),
            "run_time_minutes": Decimal("3"),
        })
    else:
        op_count = rng.choice([2, 3, 3, 3])  # bias toward 3-op routings
        if op_count == 3:
            ops.append({
                "sequence": seq,
                "work_center_id": wc_ids["QA"],
                "operation_code": "QA",
                "operation_name": "Quality Check",
                "setup_time_minutes": Decimal("0"),
                "run_time_minutes": Decimal("5"),
            })
            seq += 1
        ops.append({
            "sequence": seq,
            "work_center_id": wc_ids["PACK"],
            "operation_code": "PACK",
            "operation_name": "Pack",
            "setup_time_minutes": Decimal("0"),
            "run_time_minutes": Decimal("3"),
        })
    return ops


def seed(db: Session, context: dict[str, Any]) -> None:
    now = _time.now()
    rng = _time.rng()

    cat_ids = _seed_categories(db, now)
    wc_ids = _seed_work_centers(db, now)

    raw_ids: list[int] = []
    for sku, name, cost_per_kg, reorder_g in RAW_PRODUCTS:
        p = _seed_raw_material(db, now, sku, name, cat_ids["RAW"], cost_per_kg, reorder_g)
        raw_ids.append(p.id)

    finished_good_ids: dict[str, int] = {}
    for sku, name, cost, price in SIGNAGE_PRODUCTS:
        p = _seed_finished_good(db, now, sku, name, cat_ids["SIGN"], cost, price)
        finished_good_ids[sku] = p.id
    for sku, name, cost, price in DISPLAY_PRODUCTS:
        p = _seed_finished_good(db, now, sku, name, cat_ids["DISPLAY"], cost, price)
        finished_good_ids[sku] = p.id
    for sku, name, cost, price in KEEPSAKE_PRODUCTS:
        p = _seed_finished_good(db, now, sku, name, cat_ids["KEEPSAKE"], cost, price)
        finished_good_ids[sku] = p.id

    multi_level_parents = {parent for parent, _ in MULTI_LEVEL_BOMS}

    for sku, fg_id in finished_good_ids.items():
        bom_data = BOMCreate(
            product_id=fg_id,
            code=f"BOM-{sku}",
            name=f"{sku} BOM",
            version=1,
            lines=_build_bom_lines(rng, sku, raw_ids, finished_good_ids),
        )
        bom_management_service.create_bom(db, bom_data)

    for sku, fg_id in finished_good_ids.items():
        has_sub = sku in multi_level_parents
        routing = routing_service.create_routing(
            db,
            data={
                "product_id": fg_id,
                "code": f"RTG-{sku}",
                "name": f"{sku} Routing",
                "version": 1,
                "effective_date": date.today(),
                "is_active": True,
            },
            operations=_build_routing_ops(rng, wc_ids, has_subassembly=has_sub),
        )

        # Mirror the BOM line materials onto the routing operations so the
        # PO detail's per-operation 'Materials' sub-row is populated. BOM
        # lines drive inventory reservation (reserve_production_materials);
        # routing_operation_materials drive per-op execution tracking and
        # get copied to production_order_operation_materials by
        # copy_routing_to_operations. Without these rows, the PO detail
        # UI shows 'No materials assigned to this operation' on every op.
        bom = (
            db.query(BOM)
            .filter(BOM.product_id == fg_id, BOM.active.is_(True))
            .first()
        )
        if bom is None:
            continue
        print_op = next((op for op in routing.operations if op.operation_code == "PRINT"), None)
        assemble_op = next((op for op in routing.operations if op.operation_code == "ASSEMBLE"), None)
        for line in bom.lines:
            component = db.get(Product, line.component_id)
            if component is None:
                continue
            # Raw materials go on the PRINT op; sub-assemblies go on the
            # ASSEMBLE op (if the routing has one), else PRINT.
            if component.is_raw_material:
                target = print_op
            else:
                target = assemble_op or print_op
            if target is None:
                continue
            db.add(RoutingOperationMaterial(
                routing_operation_id=target.id,
                component_id=line.component_id,
                quantity=line.quantity,
                quantity_per="unit",
                unit=line.unit or component.unit or "EA",
                scrap_factor=line.scrap_factor or Decimal("0"),
            ))
        db.flush()

    context["category_ids"] = cat_ids
    context["work_center_ids"] = wc_ids
    context["raw_material_ids"] = raw_ids
    context["finished_good_ids"] = finished_good_ids
    context["multi_level_bom_parents"] = sorted(multi_level_parents)

    print(
        f"[seed]   {len(CATEGORY_DEFS)} categories, {len(WORK_CENTER_DEFS)} work "
        f"centers, {len(raw_ids)} raw materials, "
        f"{len(finished_good_ids)} finished goods, "
        f"{len(finished_good_ids)} BOMs ({len(multi_level_parents)} multi-level), "
        f"{len(finished_good_ids)} routings"
    )
