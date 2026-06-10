"""
Consolidated Buy List Service — HARD-7, Layer 1 (live view).

Answers: "Across ALL open demand, what do I buy, how much, and by when?"

Design
------
- COMPUTED-ON-DEMAND: no stored MRP run artifact; the view is always current.
- ZERO WRITES: pure read path; never calls run_mrp (which self-commits and
  deletes/regenerates planned orders, per PR #688).
- Single-bucket netting (no time-phasing) — MVP per owner-approved design.
- Reuses MRPService.explode_bom for BOM/routing-operation explosion (same
  routing-first / BOM-fallback semantics as the full MRP engine).
- Reuses supply_netting.get_projected_available for on-hand + open-PO netting
  (same helper wired into blocking_issues / HARD-6 shortage fixes).

Open-order scope
----------------
Sales orders:   status NOT IN ('cancelled', 'completed', 'delivered', 'shipped')
                (order types: quote_based with product_id, or line_item orders)
Production orders: status IN ('draft', 'released', 'in_progress')
                   remaining qty = quantity_ordered − quantity_completed

Safety stock treatment
----------------------
  net_shortage = max(0, gross_demand − projected + safety_stock)
  suggested_qty = max(net_shortage, min_order_qty or 0)

where safety_stock = Product.safety_stock and min_order_qty = Product.min_order_qty.
The safety-stock floor mirrors mrp.calculate_net_requirements.

Vendor preference
-----------------
Uses Product.preferred_vendor_id (FK to vendors table, set NULL on delete).
This is what exists; HARD-13 will later wire VendorItem catalog pricing.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.production_order import ProductionOrder
from app.models.product import Product
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.vendor import Vendor
from app.schemas.buy_list import (
    BuyListIncomingDetail,
    BuyListItem,
    BuyListResponse,
    BuyListSummary,
)
from app.services.mrp import MRPService
from app.services.supply_netting import get_projected_available, get_projected_available_bulk
from app.logging_config import get_logger

logger = get_logger(__name__)

# Sales order statuses that represent open/active demand.
# Cancelled, completed, delivered, and shipped orders are not outstanding demand.
_OPEN_SO_STATUSES_EXCLUDE = frozenset(
    ["cancelled", "completed", "delivered", "shipped"]
)

# Production order statuses considered open (same as MRPService._get_production_orders
# with include_draft=True).
_OPEN_WO_STATUSES = frozenset(["draft", "released", "in_progress"])


@dataclass
class _DemandSource:
    """Internal: one open order contributing to a component's gross demand."""
    order_type: str          # "sales_order" or "production_order"
    order_id: int
    order_ref: str           # order_number / production code
    due_date: Optional[date]


@dataclass
class _ComponentDemand:
    """Internal: aggregated gross demand for one component."""
    product_id: int
    gross_quantity: Decimal = Decimal("0")
    earliest_need: Optional[date] = None
    sources: List[_DemandSource] = field(default_factory=list)

    def add(self, qty: Decimal, source: _DemandSource) -> None:
        self.gross_quantity += qty
        if source.due_date:
            if self.earliest_need is None or source.due_date < self.earliest_need:
                self.earliest_need = source.due_date
        self.sources.append(source)


def _collect_open_so_demand(
    db: Session,
    mrp_service: MRPService,
    demand: Dict[int, _ComponentDemand],
) -> int:
    """
    Explode all open sales orders and add component demand to *demand* dict.

    Returns the count of sales orders included.
    """
    sos = (
        db.query(SalesOrder)
        .filter(SalesOrder.status.notin_(list(_OPEN_SO_STATUSES_EXCLUDE)))
        .all()
    )
    count = 0
    for so in sos:
        due = (
            so.estimated_completion_date.date()
            if so.estimated_completion_date
            else None
        )
        source = _DemandSource(
            order_type="sales_order",
            order_id=so.id,
            order_ref=so.order_number or str(so.id),
            due_date=due,
        )
        exploded = False

        if so.order_type == "quote_based" and so.product_id:
            qty = Decimal(str(so.quantity or 1))
            reqs = mrp_service.explode_bom(
                product_id=int(so.product_id),
                quantity=qty,
                source_demand_type="sales_order",
                source_demand_id=int(so.id),
                due_date=due,
            )
            for req in reqs:
                if req.product_id not in demand:
                    demand[req.product_id] = _ComponentDemand(
                        product_id=req.product_id
                    )
                demand[req.product_id].add(req.gross_quantity, source)
            exploded = bool(reqs)

        elif so.order_type == "line_item":
            lines = (
                db.query(SalesOrderLine)
                .filter(
                    SalesOrderLine.sales_order_id == so.id,
                    SalesOrderLine.product_id.isnot(None),
                )
                .all()
            )
            for line in lines:
                qty = Decimal(str(line.quantity or 0))
                if qty <= Decimal("0"):
                    continue
                reqs = mrp_service.explode_bom(
                    product_id=int(line.product_id),
                    quantity=qty,
                    source_demand_type="sales_order",
                    source_demand_id=int(so.id),
                    due_date=due,
                )
                for req in reqs:
                    if req.product_id not in demand:
                        demand[req.product_id] = _ComponentDemand(
                            product_id=req.product_id
                        )
                    demand[req.product_id].add(req.gross_quantity, source)
                if reqs:
                    exploded = True

        if exploded:
            count += 1

    return count


def _collect_open_wo_demand(
    db: Session,
    mrp_service: MRPService,
    demand: Dict[int, _ComponentDemand],
) -> int:
    """
    Explode all open production orders (remaining qty only) and add to *demand*.

    Returns the count of production orders included.
    """
    wos = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.status.in_(list(_OPEN_WO_STATUSES)))
        .all()
    )
    count = 0
    for wo in wos:
        ordered = Decimal(str(wo.quantity_ordered or 0))
        completed = Decimal(str(wo.quantity_completed or 0))
        remaining = ordered - completed
        if remaining <= Decimal("0"):
            continue

        source = _DemandSource(
            order_type="production_order",
            order_id=wo.id,
            order_ref=wo.code or str(wo.id),
            due_date=wo.due_date,
        )
        reqs = mrp_service.explode_bom(
            product_id=int(wo.product_id),
            quantity=remaining,
            source_demand_type="production_order",
            source_demand_id=int(wo.id),
            due_date=wo.due_date,
        )
        for req in reqs:
            if req.product_id not in demand:
                demand[req.product_id] = _ComponentDemand(product_id=req.product_id)
            demand[req.product_id].add(req.gross_quantity, source)

        if reqs:
            count += 1

    return count


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_buy_list(
    db: Session,
    vendor_id: Optional[int] = None,
) -> BuyListResponse:
    """
    Compute and return the consolidated buy list.

    Parameters
    ----------
    db:
        SQLAlchemy session.  NEVER committed — pure reads.
    vendor_id:
        Optional filter.  When provided, only return items whose
        preferred_vendor_id matches.

    Returns
    -------
    BuyListResponse with summary + list of short components sorted by
    (preferred_vendor_name ASC, earliest_need ASC NULLS LAST, sku ASC).
    """
    mrp_service = MRPService(db)

    # ------------------------------------------------------------------ #
    # Step 1: Collect gross demand from all open orders                   #
    # ------------------------------------------------------------------ #
    demand: Dict[int, _ComponentDemand] = {}
    so_count = _collect_open_so_demand(db, mrp_service, demand)
    wo_count = _collect_open_wo_demand(db, mrp_service, demand)

    if not demand:
        return BuyListResponse(
            summary=BuyListSummary(
                components_short=0,
                total_estimated_buy_value=Decimal("0"),
                open_sales_orders_included=so_count,
                open_production_orders_included=wo_count,
                draft_incoming_qty=Decimal("0"),
            ),
            items=[],
        )

    # ------------------------------------------------------------------ #
    # Step 2: Load products in bulk                                        #
    # ------------------------------------------------------------------ #
    product_ids = list(demand.keys())
    products: Dict[int, Product] = {
        p.id: p
        for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
    }

    # Vendor name lookup (only preferred_vendor_ids that appear)
    vendor_ids = {
        p.preferred_vendor_id
        for p in products.values()
        if p.preferred_vendor_id
    }
    vendors: Dict[int, Vendor] = {}
    if vendor_ids:
        vendors = {
            v.id: v
            for v in db.query(Vendor).filter(Vendor.id.in_(vendor_ids)).all()
        }

    # ------------------------------------------------------------------ #
    # Step 3: Net each component and build output rows                     #
    # ------------------------------------------------------------------ #

    # Batch-load projected availability for ALL components in two queries
    # instead of 2·N individual queries.  See supply_netting.get_projected_available_bulk.
    availability_map = get_projected_available_bulk(db, product_ids)

    items: List[BuyListItem] = []
    total_buy_value = Decimal("0")
    total_draft_incoming = Decimal("0")

    for pid, comp_demand in demand.items():
        product = products.get(pid)
        if not product:
            continue

        # get_projected_available_bulk guarantees a key for every product_id
        # in product_ids, so this fallback is a safety net for edge cases where
        # a product entered demand after the bulk call.
        avail = availability_map.get(pid)
        if avail is None:
            avail = get_projected_available(db, pid)

        safety_stock = Decimal(str(product.safety_stock or 0))
        gross = comp_demand.gross_quantity

        # Aggregate MRP netting — net against on_hand + incoming, NOT
        # available (= on_hand − allocated).
        #
        # Why: gross_demand already includes the open WOs that created the
        # allocated quantities.  Using `available` (on_hand − allocated) would
        # subtract those allocations from supply while their corresponding WO
        # demand also appears in gross — double-counting that overstates
        # shortages.
        #
        # Contrast with blocking_issues / per-order checks (e.g. line ~200,
        # ~541) where `available` IS correct: those check a single order
        # against current availability and the question is "is there stock free
        # to fill *this* specific order right now?"  Here we ask "across all
        # open demand, how much more do we need to buy?" — the allocations are
        # already captured inside gross_demand.
        #
        # Formula: net_shortage = max(0, gross − (on_hand + incoming) + safety_stock)
        mrp_projected = avail.on_hand + avail.incoming_qty
        raw_short = gross - mrp_projected + safety_stock
        net_shortage = max(Decimal("0"), raw_short)

        if net_shortage <= Decimal("0"):
            # Component is covered — not on the buy list
            continue

        # Suggested order qty respects min_order_qty
        min_oq = Decimal(str(product.min_order_qty or 0))
        suggested_qty = max(net_shortage, min_oq) if min_oq > Decimal("0") else net_shortage

        # Vendor filter
        pref_vendor_id = product.preferred_vendor_id
        if vendor_id is not None and pref_vendor_id != vendor_id:
            continue
        pref_vendor_name: Optional[str] = None
        if pref_vendor_id and pref_vendor_id in vendors:
            pref_vendor_name = vendors[pref_vendor_id].name

        # Unit cost (standard preferred; fall back to last_cost)
        raw_cost = Decimal(str(product.standard_cost or product.last_cost or 0))

        # Apply UOM cost conversion (filament costs stored per KG, inventory in grams)
        try:
            from app.services.uom_service import get_cost_reference_unit, convert_cost_for_unit
            product_unit = (product.unit or "EA").upper().strip()
            cost_ref_unit = get_cost_reference_unit(product_unit)
            converted_cost = convert_cost_for_unit(raw_cost, cost_ref_unit, product_unit)
            unit_cost = converted_cost if converted_cost is not None else raw_cost
        except Exception:
            unit_cost = raw_cost

        est_buy_value = suggested_qty * unit_cost
        total_buy_value += est_buy_value

        # Draft incoming accumulator for summary transparency
        draft_incoming = sum(
            d.quantity for d in avail.details if d.status == "draft"
        )
        total_draft_incoming += draft_incoming

        # Build incoming detail list (adds "(draft)" visibility to UI)
        incoming_details = [
            BuyListIncomingDetail(
                purchase_order_id=d.purchase_order_id,
                po_number=d.po_number,
                quantity=d.quantity,
                expected_date=d.expected_date,
                status=d.status,
            )
            for d in avail.details
        ]

        items.append(
            BuyListItem(
                product_id=pid,
                sku=product.sku,
                name=product.name,
                unit=product.unit or "EA",
                gross_demand=gross,
                on_hand=avail.on_hand,
                allocated=avail.allocated,
                available=avail.available,
                incoming_qty=avail.incoming_qty,
                projected=mrp_projected,
                safety_stock=safety_stock,
                net_shortage=net_shortage,
                suggested_qty=suggested_qty,
                preferred_vendor_id=pref_vendor_id,
                preferred_vendor_name=pref_vendor_name,
                unit_cost=unit_cost,
                estimated_buy_value=est_buy_value,
                earliest_need=comp_demand.earliest_need,
                incoming_details=incoming_details,
            )
        )

    # ------------------------------------------------------------------ #
    # Step 4: Sort — vendor name, earliest need, then SKU                 #
    # ------------------------------------------------------------------ #
    items.sort(
        key=lambda i: (
            i.preferred_vendor_name or "\xff",  # no-vendor last
            i.earliest_need or date.max,
            i.sku,
        )
    )

    summary = BuyListSummary(
        components_short=len(items),
        total_estimated_buy_value=total_buy_value,
        open_sales_orders_included=so_count,
        open_production_orders_included=wo_count,
        draft_incoming_qty=total_draft_incoming,
    )

    return BuyListResponse(summary=summary, items=items)
