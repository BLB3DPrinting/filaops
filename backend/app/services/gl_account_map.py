"""
Single source of truth for the item_type -> inventory GL account map (#910).

For years this 3-way map was hand-copied into every poster that touches
inventory value. When one copy drifted the ledger corrupted silently: a
manufactured ``component`` was received into Finished Goods (1220) by the
production-completion poster while every downstream flow (cycle count,
reconciliation, valuation) relieved/valued it at Raw Materials (1200), so
1200 went negative for value it never held and 1220 stayed overstated
forever (#894 item 4, #892).

The canonical map — matching the four surfaces that were already correct
(``receive_purchase_order``, ``cycle_count_adjustment``,
``post_reconciliation_baseline``, ``get_inventory_valuation``):

    packaging     -> 1230  Packaging Inventory
    finished_good -> 1220  Finished Goods Inventory
    everything else (component / material / supply / service / None)
                  -> 1200  Raw Materials / Inventory

Manufactured sub-assemblies are materials-in-waiting, not finished goods,
so ``component`` deliberately maps to 1200.

This helper is the ONLY place the map may live. Every poster that debits or
credits an inventory account by item_type MUST call ``inventory_account_for``.
"""
from __future__ import annotations

# Inventory GL account codes (asset side). Kept here so the map and the codes
# it emits share one definition.
RAW_MATERIALS_ACCOUNT = "1200"
FINISHED_GOODS_ACCOUNT = "1220"
PACKAGING_ACCOUNT = "1230"

# item_type -> inventory account. Only the two non-default types are listed;
# every other (or missing) item_type falls through to Raw Materials.
_INVENTORY_ACCOUNT_BY_ITEM_TYPE = {
    "packaging": PACKAGING_ACCOUNT,
    "finished_good": FINISHED_GOODS_ACCOUNT,
}


def inventory_account_for(item_type: str | None) -> str:
    """Return the inventory GL account code for a product's ``item_type``.

    packaging -> 1230, finished_good -> 1220, everything else (component,
    material, supply, service, unknown, or None) -> 1200. This is the single
    source of truth referenced by every inventory-value poster (#910).
    """
    return _INVENTORY_ACCOUNT_BY_ITEM_TYPE.get(item_type or "", RAW_MATERIALS_ACCOUNT)
