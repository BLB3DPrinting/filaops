"""
Seed inventory state.

- 1 InventoryLocation ('MAIN' / Main Warehouse) — wipe cleared any
  migration-seeded locations, so we recreate here. inventory_service
  has a get_or_create_default_location helper but we want a stable,
  named fixture for screenshots.
- Raw materials: mix of healthy stock, 2 intentionally below
  reorder_point to drive the Low Stock alerts + MRP suggestions.
- Finished goods: varied on_hand quantities (10-150 EA) to populate
  Stock on Hand widgets with a believable spread.
- 1 finished good flagged for cycle count via last_counted = 120d ago.

Allocated quantities are LEFT AT 0 here. They rise naturally when
sales_orders.py creates Confirmed / In-Production orders that
reserve inventory via the service layer.
"""
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.models.inventory import Inventory, InventoryLocation

from scripts.seed_data import _time


LOW_STOCK_SKUS = ["RAW-PLA-BLK", "RAW-PLA-WHT"]
LOW_STOCK_ON_HAND_G = {
    "RAW-PLA-BLK": Decimal("200"),   # below reorder_point (500g)
    "RAW-PLA-WHT": Decimal("350"),   # below reorder_point (500g)
}
HEALTHY_RAW_ON_HAND_G = {
    "RAW-PLA-RED":  Decimal("2400"),
    "RAW-PETG-CLR": Decimal("3600"),
    "RAW-ABS-BLK":  Decimal("1800"),
}
CYCLE_COUNT_SKU = "KEEP-005"  # Keychain Fob — flagged for cycle count


def seed(db: Session, context: dict[str, Any]) -> None:
    now = _time.now()
    rng = _time.rng()

    location = InventoryLocation(
        name="Main Warehouse",
        code="MAIN",
        type="warehouse",
        active=True,
    )
    db.add(location)
    db.flush()

    raw_material_ids = context["raw_material_ids"]
    finished_good_ids = context["finished_good_ids"]

    from app.models.product import Product
    raw_products = db.query(Product).filter(Product.id.in_(raw_material_ids)).all()
    raw_by_id = {p.id: p for p in raw_products}
    sku_by_id = {p.id: p.sku for p in raw_products}

    for raw_id in raw_material_ids:
        sku = sku_by_id[raw_id]
        if sku in LOW_STOCK_ON_HAND_G:
            on_hand = LOW_STOCK_ON_HAND_G[sku]
        else:
            on_hand = HEALTHY_RAW_ON_HAND_G[sku]
        db.add(Inventory(
            product_id=raw_id,
            location_id=location.id,
            on_hand_quantity=on_hand,
            allocated_quantity=Decimal("0"),
            created_at=now,
            updated_at=now,
        ))

    for sku, fg_id in finished_good_ids.items():
        on_hand = Decimal(str(rng.randint(10, 150)))
        last_counted = None
        if sku == CYCLE_COUNT_SKU:
            last_counted = now - timedelta(days=120)
        db.add(Inventory(
            product_id=fg_id,
            location_id=location.id,
            on_hand_quantity=on_hand,
            allocated_quantity=Decimal("0"),
            last_counted=last_counted,
            created_at=now,
            updated_at=now,
        ))

    db.flush()

    context["inventory_location_id"] = location.id
    low_count = len(LOW_STOCK_SKUS)
    print(
        f"[seed]   {len(raw_material_ids) + len(finished_good_ids)} inventory rows "
        f"(location=MAIN, {low_count} raws below reorder, 1 cycle-count flag)"
    )
