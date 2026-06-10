"""
Reservation reconciliation service (HARD-5).

Responsibilities:
1. Derive allocation truth — compute per-item allocated_quantity from the
   reservation / reservation_release ledger and compare against the stored
   ``Inventory.allocated_quantity`` lump-sum column.

2. Identify stranded allocations — ledger rows whose production_order is in a
   terminal state (complete, cancelled, closed) or no longer exists, but whose
   net reservation quantity is still > 0.

3. Repair path — release stranded allocations for a specific production order
   (staff-gated, explicit confirm required, no silent auto-repair).

4. Write-time guard hint — utility to check whether a proposed allocated_quantity
   increase would exceed on_hand, for use by reserve_production_materials.

DESIGN DECISIONS (document for PR body):
- Allocation ahead of receipt is legitimate (production reserves before PO
  arrives), so the write-time guard is a LOG + FLAG, not a hard block.
  ``reserve_production_materials`` already logs a shortage warning; this module
  adds an explicit flag to the reservation return dict so callers/UIs can surface
  it without coupling to the log.
- The "derive truth" function re-uses the logic from
  ``get_allocations_by_production_order`` but aggregates across all products
  to produce a per-inventory-row comparison (one round-trip vs N).
- Stranded = net reservation > 0 AND production order is terminal or missing.
  Terminal statuses: complete, completed, cancelled, closed.  "Short" is NOT
  terminal — the production order may still have reservations legitimately
  while the operator is deciding how to proceed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Inventory, InventoryTransaction, InventoryLocation
from app.models.production_order import ProductionOrder
from app.models.product import Product
from app.logging_config import get_logger

logger = get_logger(__name__)

# Terminal production-order statuses: reservations held by these orders are
# candidates for stranded-allocation repair.
TERMINAL_PO_STATUSES = frozenset({"complete", "completed", "cancelled", "closed"})


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AllocationDriftItem:
    """Per-inventory-row comparison between stored and ledger-derived allocation."""

    # Identity
    inventory_id: int
    product_id: int
    sku: str
    name: str
    location_id: int
    location_name: Optional[str]

    # Quantities (Decimal)
    on_hand: Decimal
    stored_allocated: Decimal      # Inventory.allocated_quantity
    ledger_allocated: Decimal      # Σ(reservation) - Σ(reservation_release)
    drift: Decimal                 # stored_allocated - ledger_allocated

    @property
    def has_drift(self) -> bool:
        return self.drift != Decimal("0")

    @property
    def stored_available(self) -> Decimal:
        return self.on_hand - self.stored_allocated

    @property
    def ledger_available(self) -> Decimal:
        return self.on_hand - self.ledger_allocated


@dataclass
class StrandedAllocationItem:
    """A production order whose net reservation is still positive but the order is terminal."""

    production_order_id: int
    production_order_code: str
    status: str                        # terminal status that triggered flag
    product_id: int
    sku: str
    name: str
    location_id: int
    net_reserved: Decimal              # Σ(reservation) - Σ(reservation_release) for this PO
    stranded_reason: str               # "terminal_status" | "order_missing"

    # Populated only for terminal_status items
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


@dataclass
class AllocationReconciliationReport:
    """Full reservation reconciliation report returned to the endpoint."""

    drift_items: List[AllocationDriftItem]
    stranded_items: List[StrandedAllocationItem]

    # Aggregate counts
    total_inventory_rows: int
    drifted_rows: int
    stranded_po_count: int
    total_stranded_quantity: Decimal

    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# 1. Derive allocation truth — per-inventory-row comparison
# ---------------------------------------------------------------------------

def get_allocation_reconciliation_report(
    db: Session,
    *,
    drifted_only: bool = False,
) -> AllocationReconciliationReport:
    """
    Compare stored Inventory.allocated_quantity with the ledger-derived sum
    for every inventory row, and identify stranded allocations.

    Returns:
        AllocationReconciliationReport with drift_items and stranded_items.
    """
    # ------------------------------------------------------------------
    # Step 1: all inventory rows with product/location info
    # ------------------------------------------------------------------
    inv_rows = (
        db.query(
            Inventory,
            Product,
            InventoryLocation.name.label("location_name"),
        )
        .join(Product, Inventory.product_id == Product.id)
        .outerjoin(InventoryLocation, Inventory.location_id == InventoryLocation.id)
        .all()
    )

    if not inv_rows:
        return AllocationReconciliationReport(
            drift_items=[],
            stranded_items=[],
            total_inventory_rows=0,
            drifted_rows=0,
            stranded_po_count=0,
            total_stranded_quantity=Decimal("0"),
        )

    product_ids = [r.Inventory.product_id for r in inv_rows]

    # ------------------------------------------------------------------
    # Step 2: aggregate reservation / reservation_release per
    # (product_id, location_id, reference_id) in one query
    # ------------------------------------------------------------------
    from sqlalchemy import case as sa_case

    agg_rows = (
        db.query(
            InventoryTransaction.product_id,
            InventoryTransaction.location_id,
            InventoryTransaction.reference_id.label("production_order_id"),
            func.sum(
                sa_case(
                    (
                        InventoryTransaction.transaction_type == "reservation",
                        InventoryTransaction.quantity,
                    ),
                    (
                        InventoryTransaction.transaction_type == "reservation_release",
                        -InventoryTransaction.quantity,
                    ),
                    else_=Decimal("0"),
                )
            ).label("net_qty"),
        )
        .filter(
            InventoryTransaction.product_id.in_(product_ids),
            InventoryTransaction.transaction_type.in_(
                ["reservation", "reservation_release"]
            ),
        )
        .group_by(
            InventoryTransaction.product_id,
            InventoryTransaction.location_id,
            InventoryTransaction.reference_id,
        )
        .all()
    )

    # Index: (product_id, location_id) -> total net reserved (across all POs)
    # Also: (product_id, location_id, po_id) -> net reserved per PO
    ledger_by_inv: Dict[Tuple[int, int], Decimal] = {}
    per_po: Dict[Tuple[int, int, Optional[int]], Decimal] = {}

    for row in agg_rows:
        net = Decimal(str(row.net_qty)) if row.net_qty is not None else Decimal("0")
        loc = row.location_id
        pid = row.product_id
        po_id = row.production_order_id

        key = (pid, loc)
        ledger_by_inv[key] = ledger_by_inv.get(key, Decimal("0")) + net

        po_key = (pid, loc, po_id)
        per_po[po_key] = per_po.get(po_key, Decimal("0")) + net

    # ------------------------------------------------------------------
    # Step 3: build drift items
    # ------------------------------------------------------------------
    drift_items: List[AllocationDriftItem] = []

    for r in inv_rows:
        inv = r.Inventory
        prod = r.Product
        stored = Decimal(str(inv.allocated_quantity or 0))
        on_hand = Decimal(str(inv.on_hand_quantity or 0))
        key = (inv.product_id, inv.location_id)
        ledger_alloc = ledger_by_inv.get(key, Decimal("0"))
        drift = stored - ledger_alloc

        item = AllocationDriftItem(
            inventory_id=inv.id,
            product_id=prod.id,
            sku=prod.sku,
            name=prod.name,
            location_id=inv.location_id,
            location_name=r.location_name,
            on_hand=on_hand,
            stored_allocated=stored,
            ledger_allocated=ledger_alloc,
            drift=drift,
        )
        drift_items.append(item)

    if drifted_only:
        drift_items = [d for d in drift_items if d.has_drift]

    drift_items.sort(key=lambda d: (-abs(d.drift), d.sku))

    # ------------------------------------------------------------------
    # Step 4: identify stranded allocations
    # Only positive net reservations are actionable (negatives mean over-release,
    # which is a separate kind of drift already captured in drift_items).
    # ------------------------------------------------------------------
    stranded_items: List[StrandedAllocationItem] = []

    # Collect all unique PO IDs with positive net reservations
    positive_po_keys = [
        (pid, loc, po_id)
        for (pid, loc, po_id), net in per_po.items()
        if net > Decimal("0") and po_id is not None
    ]

    if positive_po_keys:
        po_ids = list({pk[2] for pk in positive_po_keys})

        # Fetch PO records in bulk
        po_records = (
            db.query(ProductionOrder)
            .filter(ProductionOrder.id.in_(po_ids))
            .all()
        )
        po_by_id: Dict[int, ProductionOrder] = {po.id: po for po in po_records}

        # Build product lookup for display names
        prod_ids_needed = {pk[0] for pk in positive_po_keys}
        prod_records = (
            db.query(Product).filter(Product.id.in_(prod_ids_needed)).all()
        )
        prod_by_id: Dict[int, Product] = {p.id: p for p in prod_records}

        for pid, loc, po_id in positive_po_keys:
            net = per_po[(pid, loc, po_id)]
            po = po_by_id.get(po_id)
            prod = prod_by_id.get(pid)

            if po is None:
                # Production order no longer exists — definitely stranded
                stranded_items.append(
                    StrandedAllocationItem(
                        production_order_id=po_id,
                        production_order_code=f"(deleted PO #{po_id})",
                        status="deleted",
                        product_id=pid,
                        sku=prod.sku if prod else f"(product #{pid})",
                        name=prod.name if prod else f"(product #{pid})",
                        location_id=loc or 0,
                        net_reserved=net,
                        stranded_reason="order_missing",
                    )
                )
            elif po.status in TERMINAL_PO_STATUSES:
                stranded_items.append(
                    StrandedAllocationItem(
                        production_order_id=po.id,
                        production_order_code=po.code,
                        status=po.status,
                        product_id=pid,
                        sku=prod.sku if prod else f"(product #{pid})",
                        name=prod.name if prod else f"(product #{pid})",
                        location_id=loc or 0,
                        net_reserved=net,
                        stranded_reason="terminal_status",
                        completed_at=getattr(po, "completed_at", None),
                        cancelled_at=None,
                    )
                )

    stranded_items.sort(key=lambda s: (-s.net_reserved, s.production_order_code))

    total_stranded_qty = sum(
        (s.net_reserved for s in stranded_items), Decimal("0")
    )

    logger.debug(
        "Allocation reconciliation: %d rows, %d drifted, %d stranded POs, "
        "total stranded qty=%s",
        len(inv_rows),
        sum(1 for d in drift_items if d.has_drift),
        len(stranded_items),
        total_stranded_qty,
    )

    return AllocationReconciliationReport(
        drift_items=drift_items,
        stranded_items=stranded_items,
        total_inventory_rows=len(inv_rows),
        drifted_rows=sum(1 for d in drift_items if d.has_drift),
        stranded_po_count=len(stranded_items),
        total_stranded_quantity=total_stranded_qty,
    )


# ---------------------------------------------------------------------------
# 2. Repair path — release stranded allocations for a specific PO
# ---------------------------------------------------------------------------

def release_stranded_allocations(
    db: Session,
    production_order_id: int,
    released_by: str,
    reason: str = "Staff-initiated stranded allocation release (HARD-5)",
) -> Dict:
    """
    Release all remaining reservations for a specific production order that
    is in a terminal state or no longer exists.

    This is the repair action for stranded allocations.  It must be called
    explicitly (staff-gated endpoint with confirmation); it does NOT run
    automatically.

    The function:
    1. Verifies the PO is terminal or missing (guards against releasing live orders).
    2. Computes the net reservation from the ledger for each (product, location).
    3. For each net-positive pair, decreases Inventory.allocated_quantity by the
       net amount (floored at 0) and writes a reservation_release transaction.

    Returns:
        Dict with keys: production_order_id, production_order_code, releases (list),
        total_released_items, errors (list).
    """
    result = {
        "production_order_id": production_order_id,
        "production_order_code": None,
        "releases": [],
        "total_released_items": 0,
        "errors": [],
    }

    # -- Guard: PO must be terminal or absent --
    po = db.query(ProductionOrder).filter(
        ProductionOrder.id == production_order_id
    ).first()

    if po is not None:
        result["production_order_code"] = po.code
        if po.status not in TERMINAL_PO_STATUSES:
            result["errors"].append(
                f"Production order {po.code} is in status '{po.status}', "
                f"which is not a terminal status. Only orders in "
                f"{sorted(TERMINAL_PO_STATUSES)} can have stranded allocations "
                f"force-released. Cancel or complete the order first."
            )
            return result
    else:
        result["production_order_code"] = f"(deleted PO #{production_order_id})"
        logger.warning(
            "Releasing stranded allocations for deleted PO #%d by %s",
            production_order_id,
            released_by,
        )

    # -- Find all reservation transactions for this PO --
    reservation_txns = (
        db.query(InventoryTransaction)
        .filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == production_order_id,
            InventoryTransaction.transaction_type == "reservation",
        )
        .all()
    )

    if not reservation_txns:
        logger.info(
            "No reservation transactions found for PO #%d — nothing to release.",
            production_order_id,
        )
        return result

    # Compute net per (product_id, location_id) — subtract existing releases
    release_txns = (
        db.query(InventoryTransaction)
        .filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == production_order_id,
            InventoryTransaction.transaction_type == "reservation_release",
        )
        .all()
    )

    # Build net-reservation map
    net_map: Dict[Tuple[int, int], Decimal] = {}
    for txn in reservation_txns:
        k = (txn.product_id, txn.location_id)
        net_map[k] = net_map.get(k, Decimal("0")) + Decimal(str(txn.quantity))
    for txn in release_txns:
        k = (txn.product_id, txn.location_id)
        net_map[k] = net_map.get(k, Decimal("0")) - Decimal(str(txn.quantity))

    now = datetime.now(timezone.utc)

    for (product_id, location_id), net_qty in net_map.items():
        if net_qty <= Decimal("0"):
            # Already fully released — skip
            continue

        # Fetch inventory row with a row-level lock to prevent concurrent
        # repair calls on the same (product, location) from racing and
        # double-releasing the allocated_quantity.
        inventory = (
            db.query(Inventory)
            .filter(
                Inventory.product_id == product_id,
                Inventory.location_id == location_id,
            )
            .with_for_update()
            .first()
        )

        if not inventory:
            result["errors"].append(
                f"No inventory row for product_id={product_id}, "
                f"location_id={location_id}. Reservation transaction exists "
                f"but inventory row is missing — skipping."
            )
            continue

        current_allocated = Decimal(str(inventory.allocated_quantity or 0))
        new_allocated = max(Decimal("0"), current_allocated - net_qty)

        inventory.allocated_quantity = new_allocated
        inventory.updated_at = now

        # Write audit transaction
        release_txn = InventoryTransaction(
            product_id=product_id,
            location_id=location_id,
            transaction_type="reservation_release",
            quantity=net_qty,
            reference_type="production_order",
            reference_id=production_order_id,
            notes=(
                f"Stranded-allocation repair by {released_by}: {reason}. "
                f"PO code: {result['production_order_code']}"
            ),
            created_by=released_by,
            created_at=now,
        )
        db.add(release_txn)

        # Build product info for response
        prod = db.query(Product).filter(Product.id == product_id).first()

        result["releases"].append(
            {
                "product_id": product_id,
                "sku": prod.sku if prod else f"(product #{product_id})",
                "name": prod.name if prod else f"(product #{product_id})",
                "location_id": location_id,
                "quantity_released": float(net_qty),
                "old_allocated": float(current_allocated),
                "new_allocated": float(new_allocated),
            }
        )
        result["total_released_items"] += 1

        logger.info(
            "Released stranded allocation for PO #%d (%s), product %s: "
            "qty=%s, allocated %s → %s, by %s",
            production_order_id,
            result["production_order_code"],
            prod.sku if prod else f"#{product_id}",
            net_qty,
            current_allocated,
            new_allocated,
            released_by,
        )

    db.flush()
    return result


# ---------------------------------------------------------------------------
# 3. Write-time guard — called from reserve_production_materials
# ---------------------------------------------------------------------------

def check_allocation_guard(
    on_hand: Decimal,
    current_allocated: Decimal,
    additional: Decimal,
) -> Tuple[bool, Decimal]:
    """
    Check whether increasing allocated_quantity by `additional` would exceed on_hand.

    DESIGN CHOICE (HARD-5): This is a FLAG, not a hard block.
    Rationale: production legitimately reserves ahead of receipt.  A shortage at
    reserve-time means the PO will need incoming stock; blocking the reservation
    prevents the MRP signal entirely, which is worse.  The caller should log a
    shortage warning and include ``is_shortage=True`` in the reservation result.

    Args:
        on_hand: Current on_hand_quantity.
        current_allocated: Current allocated_quantity.
        additional: Quantity being reserved.

    Returns:
        Tuple (would_exceed: bool, available_after: Decimal).
    """
    new_allocated = current_allocated + additional
    available_after = on_hand - new_allocated
    return available_after < Decimal("0"), available_after
