"""
Supply netting helper — shared by all shortage-calculation sites.

Single canonical place to answer:
  "How much of this component is available RIGHT NOW, how much is
   inbound on open POs, and what is the projected balance?"

Usage
-----
    from app.services.supply_netting import get_projected_available, IncomingSupplyDetail

    result = get_projected_available(db, component.id)
    # result.available     — on_hand − allocated (may be negative)
    # result.incoming_qty  — Σ remaining qty on open POs
    # result.projected     — available + incoming_qty
    # result.details       — list[IncomingSupplyDetail], sorted by expected_date
    # result.best_detail   — first detail (earliest-arriving PO), or None

Statuses that count as "open" match item_demand.get_incoming_supply:
  draft | ordered | shipped  (NOT received, closed, cancelled).

The "partially_received" label used by mrp.py is not a real PO status in the
PurchaseOrder model (status field is free-form string, model docstring says
draft → ordered → shipped → received → closed).  We intentionally do NOT
include it here; if that status ever becomes canonical it must be added in one
place — this file.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine


# Statuses that represent open / in-transit purchase orders.
# MUST match item_demand.get_incoming_supply exactly.
_OPEN_PO_STATUSES = ("draft", "ordered", "shipped")


@dataclass
class IncomingSupplyDetail:
    """One open PO line's contribution to projected supply."""
    purchase_order_id: int
    po_number: str
    quantity: Decimal
    expected_date: Optional[date]
    status: str


@dataclass
class ProjectedAvailability:
    """Projected availability for a single component."""
    product_id: int
    on_hand: Decimal
    allocated: Decimal
    available: Decimal          # on_hand − allocated (may be negative)
    incoming_qty: Decimal       # Σ remaining on open POs
    projected: Decimal          # available + incoming_qty
    details: List[IncomingSupplyDetail] = field(default_factory=list)

    @property
    def best_detail(self) -> Optional[IncomingSupplyDetail]:
        """Earliest-arriving open PO line, or None."""
        return self.details[0] if self.details else None

    @property
    def is_short_now(self) -> bool:
        """True when current available < 0 (more allocated than on-hand)."""
        return self.available < Decimal("0")

    @property
    def is_short_projected(self) -> bool:
        """True when projected balance is still negative (POs don't cover gap)."""
        return self.projected < Decimal("0")


def get_projected_available(db: Session, product_id: int) -> ProjectedAvailability:
    """
    Return current and projected availability for *product_id*.

    Performs two queries:
      1. Inventory table  → on_hand, allocated
      2. PurchaseOrderLine + PurchaseOrder → open-PO remaining quantities

    Returns a ProjectedAvailability dataclass.  Never raises; missing inventory
    or missing POs both return Decimal("0") for the relevant fields.
    """
    # --- 1. Current stock ---------------------------------------------------
    row = db.query(
        func.coalesce(func.sum(Inventory.on_hand_quantity), Decimal("0")),
        func.coalesce(func.sum(Inventory.allocated_quantity), Decimal("0")),
    ).filter(
        Inventory.product_id == product_id
    ).one()
    on_hand = Decimal(str(row[0] or 0))
    allocated = Decimal(str(row[1] or 0))
    available = on_hand - allocated

    # --- 2. Open POs --------------------------------------------------------
    po_rows = (
        db.query(PurchaseOrder, PurchaseOrderLine)
        .join(PurchaseOrderLine, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrderLine.product_id == product_id,
            PurchaseOrder.status.in_(_OPEN_PO_STATUSES),
        )
        .order_by(PurchaseOrder.expected_date.asc().nullslast())
        .all()
    )

    details: List[IncomingSupplyDetail] = []
    for po, pol in po_rows:
        ordered = pol.quantity_ordered or Decimal("0")
        received = pol.quantity_received or Decimal("0")
        remaining = Decimal(str(ordered)) - Decimal(str(received))
        if remaining <= Decimal("0"):
            continue  # fully received
        details.append(IncomingSupplyDetail(
            purchase_order_id=po.id,
            po_number=po.po_number,
            quantity=remaining,
            expected_date=po.expected_date,
            status=po.status,
        ))

    incoming_qty = sum((d.quantity for d in details), Decimal("0"))
    projected = available + incoming_qty

    return ProjectedAvailability(
        product_id=product_id,
        on_hand=on_hand,
        allocated=allocated,
        available=available,
        incoming_qty=incoming_qty,
        projected=projected,
        details=details,
    )


def compute_quantity_short(
    qty_required: Decimal,
    availability: ProjectedAvailability,
) -> Decimal:
    """
    Return the quantity still short after netting incoming supply.

    A component is short only when the projected balance (available + incoming)
    is less than what is required.  If POs fully cover the gap the shortage is
    zero even if the current available is negative.

    qty_required must be a non-negative Decimal.
    """
    return max(Decimal("0"), qty_required - availability.projected)


def get_projected_available_bulk(
    db: Session,
    product_ids: List[int],
) -> Dict[int, ProjectedAvailability]:
    """
    Batch version of get_projected_available for a list of product IDs.

    Executes exactly two queries regardless of the number of products:
      1. One grouped Inventory aggregate for on_hand + allocated sums.
      2. One PurchaseOrderLine + PurchaseOrder join for open-PO supply.

    Returns a dict mapping product_id → ProjectedAvailability.  Products with
    no inventory row and no open PO are included with all-zero values.

    Use this wherever get_projected_available would be called in a loop to
    avoid N+1 query patterns (e.g. the buy-list netting loop).

    Note: This function does NOT return per-PO IncomingSupplyDetail sorted by
    expected_date (that requires the full per-product query).  The bulk path
    returns detail lists sorted by expected_date per product, which is
    sufficient for the buy-list use case.
    """
    if not product_ids:
        return {}

    # --- 1. Inventory totals per product ------------------------------------
    inv_rows = (
        db.query(
            Inventory.product_id,
            func.coalesce(func.sum(Inventory.on_hand_quantity), Decimal("0")).label("on_hand"),
            func.coalesce(func.sum(Inventory.allocated_quantity), Decimal("0")).label("allocated"),
        )
        .filter(Inventory.product_id.in_(product_ids))
        .group_by(Inventory.product_id)
        .all()
    )
    inv_map: Dict[int, tuple] = {row.product_id: row for row in inv_rows}

    # --- 2. Open PO lines per product ---------------------------------------
    po_rows = (
        db.query(PurchaseOrder, PurchaseOrderLine)
        .join(PurchaseOrderLine, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrderLine.product_id.in_(product_ids),
            PurchaseOrder.status.in_(_OPEN_PO_STATUSES),
        )
        .order_by(
            PurchaseOrderLine.product_id,
            PurchaseOrder.expected_date.asc().nullslast(),
        )
        .all()
    )

    # Group PO details by product_id
    po_details_map: Dict[int, List[IncomingSupplyDetail]] = {pid: [] for pid in product_ids}
    for po, pol in po_rows:
        pid = pol.product_id
        ordered = pol.quantity_ordered or Decimal("0")
        received = pol.quantity_received or Decimal("0")
        remaining = Decimal(str(ordered)) - Decimal(str(received))
        if remaining <= Decimal("0"):
            continue  # fully received
        if pid not in po_details_map:
            po_details_map[pid] = []
        po_details_map[pid].append(IncomingSupplyDetail(
            purchase_order_id=po.id,
            po_number=po.po_number,
            quantity=remaining,
            expected_date=po.expected_date,
            status=po.status,
        ))

    # --- 3. Assemble results ------------------------------------------------
    result: Dict[int, ProjectedAvailability] = {}
    for pid in product_ids:
        if pid in inv_map:
            row = inv_map[pid]
            on_hand = Decimal(str(row.on_hand or 0))
            allocated = Decimal(str(row.allocated or 0))
        else:
            on_hand = Decimal("0")
            allocated = Decimal("0")

        available = on_hand - allocated
        details = po_details_map.get(pid, [])
        incoming_qty = sum((d.quantity for d in details), Decimal("0"))
        projected = available + incoming_qty

        result[pid] = ProjectedAvailability(
            product_id=pid,
            on_hand=on_hand,
            allocated=allocated,
            available=available,
            incoming_qty=incoming_qty,
            projected=projected,
            details=details,
        )

    return result
