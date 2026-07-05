"""
COGS reporting from the persisted GL (#880 PR-5).

One COGS story everywhere: the accounting dashboard, the COGS summary tab,
and the freemium profit summary all derive their COGS numbers from the SAME
posted `gl_journal_entry_lines` — no more parallel InventoryTransaction
re-sums that can (and did) disagree with the GL.

Anchor: shipped/completed/delivered sales orders in a window (status in
shipped/completed/delivered, shipped_at >= cutoff). A delivered order was
shipped — its ship JE already exists — so it belongs in the same anchor set
revenue uses; excluding it left delivered orders with revenue but zero COGS
in gross_profit/gross_margin. For each anchor order:

- Ship-side (5000, 5010): sum DEBIT lines on posted journal entries with
  source_type='sales_order' AND source_id IN (anchor ids). These are the
  shipment GL entries posted by `_create_shipment_gl_entry`
  (sales_order_fulfillment_service.py) — 5000 = COGS at FG cost, 5010 =
  shipping supplies (packaging).
- Completion-variance side (5200): for the anchor orders' linked production
  orders (production_orders.sales_order_id IN anchor ids), sum posted
  journal entries with source_type='production_order' AND source_id IN
  (those PO ids), net CREDIT minus DEBIT on 5200. Scoped STRICTLY to POs
  linked to an anchor order — a cancelled order's PO variance must never
  leak into another order's window (live data has exactly this case).

Two headline numbers:
- out_of_pocket_cogs = (5000 + 5010 debits) - (net linked 5200 credits)
  ~= actual materials + packaging spend (labor/machine value backed out).
- full_product_cogs = Σ 5000 debits (margin-analysis view, full FG cost).

Draft/voided journal entries are excluded (status == 'posted' only).
"""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, Iterable, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.models.production_order import ProductionOrder
from app.models.sales_order import SalesOrder

SHIP_COGS_ACCOUNT = "5000"
SHIP_PACKAGING_ACCOUNT = "5010"
COMPLETION_VARIANCE_ACCOUNT = "5200"

_MONEY = Decimal("0.01")


@dataclass
class COGSReconciliation:
    """The GL identity behind the two headline numbers.

    ship_cogs_5000 + packaging_5010 - completion_variance_5200 (net linked
        credit) == out_of_pocket_cogs
    """
    ship_cogs_5000: Decimal = Decimal("0.00")
    packaging_5010: Decimal = Decimal("0.00")
    completion_variance_5200: Decimal = Decimal("0.00")

    @property
    def out_of_pocket_cogs(self) -> Decimal:
        return (
            self.ship_cogs_5000 + self.packaging_5010 - self.completion_variance_5200
        ).quantize(_MONEY)

    @property
    def full_product_cogs(self) -> Decimal:
        return self.ship_cogs_5000.quantize(_MONEY)


@dataclass
class GLDerivedCOGS:
    """GL-derived COGS for a set of anchor (shipped) sales orders."""
    order_ids: List[int] = field(default_factory=list)
    reconciliation: COGSReconciliation = field(default_factory=COGSReconciliation)

    # Legacy buckets, computed from the SAME anchor set, preserved so
    # existing API consumers keep working for one release. These are NOT
    # GL-derived (the GL doesn't split materials vs labor vs packaging by
    # component) — they are the pre-#880 InventoryTransaction re-sum, kept
    # verbatim for backward compatibility. New code should use
    # out_of_pocket_cogs / full_product_cogs / reconciliation instead.
    legacy_materials: Decimal = Decimal("0.00")
    legacy_labor: Decimal = Decimal("0.00")
    legacy_packaging: Decimal = Decimal("0.00")

    @property
    def out_of_pocket_cogs(self) -> Decimal:
        return self.reconciliation.out_of_pocket_cogs

    @property
    def full_product_cogs(self) -> Decimal:
        return self.reconciliation.full_product_cogs

    @property
    def legacy_total(self) -> Decimal:
        return (
            self.legacy_materials + self.legacy_labor + self.legacy_packaging
        ).quantize(_MONEY)


def _sum_ship_side(db: Session, order_ids: List[int]) -> Dict[str, Decimal]:
    """Σ DEBIT lines on posted ship JEs for these orders, by account code."""
    totals = {SHIP_COGS_ACCOUNT: Decimal("0.00"), SHIP_PACKAGING_ACCOUNT: Decimal("0.00")}
    if not order_ids:
        return totals

    rows = (
        db.query(
            GLAccount.account_code,
            func.coalesce(func.sum(GLJournalEntryLine.debit_amount), 0),
        )
        .join(GLJournalEntryLine, GLJournalEntryLine.account_id == GLAccount.id)
        .join(GLJournalEntry, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id)
        .filter(
            GLJournalEntry.source_type == "sales_order",
            GLJournalEntry.source_id.in_(order_ids),
            GLJournalEntry.status == "posted",
            GLAccount.account_code.in_([SHIP_COGS_ACCOUNT, SHIP_PACKAGING_ACCOUNT]),
        )
        .group_by(GLAccount.account_code)
        .all()
    )
    for code, total in rows:
        totals[code] = Decimal(str(total or 0)).quantize(_MONEY)
    return totals


def _linked_production_order_ids(db: Session, order_ids: List[int]) -> List[int]:
    if not order_ids:
        return []
    return [
        row[0]
        for row in db.query(ProductionOrder.id).filter(
            ProductionOrder.sales_order_id.in_(order_ids)
        )
    ]


def _sum_completion_variance(db: Session, production_order_ids: List[int]) -> Decimal:
    """Net CREDIT - DEBIT on 5200 for posted completion JEs of these POs only.

    Scoped strictly to production_order_ids linked to the anchor sales
    orders — a cancelled order's own PO variance must not count toward a
    different order's window (live data: PO-0001 belongs to cancelled
    SO-0001, and must not leak into other orders' out_of_pocket_cogs).
    """
    if not production_order_ids:
        return Decimal("0.00")

    row = (
        db.query(
            func.coalesce(func.sum(GLJournalEntryLine.credit_amount), 0),
            func.coalesce(func.sum(GLJournalEntryLine.debit_amount), 0),
        )
        .join(GLJournalEntry, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id)
        .join(GLAccount, GLJournalEntryLine.account_id == GLAccount.id)
        .filter(
            GLJournalEntry.source_type == "production_order",
            GLJournalEntry.source_id.in_(production_order_ids),
            GLJournalEntry.status == "posted",
            GLAccount.account_code == COMPLETION_VARIANCE_ACCOUNT,
        )
        .first()
    )
    credit_total, debit_total = row if row else (0, 0)
    net = Decimal(str(credit_total or 0)) - Decimal(str(debit_total or 0))
    return net.quantize(_MONEY)


def _legacy_buckets(db, order_ids: List[int]) -> Dict[str, Decimal]:
    """Pre-#880 InventoryTransaction re-sum, preserved verbatim for the
    legacy response keys (materials/labor/packaging split the GL doesn't
    carry). Mirrors the exact filters get_cogs_summary used before this PR.
    """
    from app.models.inventory import InventoryTransaction

    materials = Decimal("0.00")
    labor = Decimal("0.00")
    packaging = Decimal("0.00")

    if not order_ids:
        return {"materials": materials, "labor": labor, "packaging": packaging}

    po_ids = _linked_production_order_ids(db, order_ids)

    if po_ids:
        consumptions = db.query(InventoryTransaction).options(
            joinedload(InventoryTransaction.product)
        ).filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id.in_(po_ids),
            InventoryTransaction.transaction_type.in_(["consumption", "scrap"]),
            ~(
                InventoryTransaction.requires_approval.is_(True)
                & InventoryTransaction.approved_by.is_(None)
            ),
            InventoryTransaction.voided_by.is_(None),
        ).all()
        for txn in consumptions:
            product = txn.product
            sku = product.sku if product else ""
            qty = abs(Decimal(str(txn.quantity))) if txn.quantity else Decimal("0")
            unit_cost = Decimal(str(txn.cost_per_unit)) if txn.cost_per_unit else Decimal("0")
            value = qty * unit_cost
            if sku.startswith("SVC-"):
                labor += value
            else:
                materials += value

    pkg_consumptions = db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type.in_(["shipment", "consolidated_shipment"]),
        InventoryTransaction.reference_id.in_(order_ids),
        InventoryTransaction.transaction_type == "consumption",
        ~(
            InventoryTransaction.requires_approval.is_(True)
            & InventoryTransaction.approved_by.is_(None)
        ),
        InventoryTransaction.voided_by.is_(None),
    ).all()
    for txn in pkg_consumptions:
        qty = abs(Decimal(str(txn.quantity))) if txn.quantity else Decimal("0")
        unit_cost = Decimal(str(txn.cost_per_unit)) if txn.cost_per_unit else Decimal("0")
        packaging += qty * unit_cost

    return {
        "materials": materials.quantize(_MONEY),
        "labor": labor.quantize(_MONEY),
        "packaging": packaging.quantize(_MONEY),
    }


def gl_derived_cogs_for_orders(
    db: Session, order_ids: Iterable[int], include_legacy: bool = True
) -> GLDerivedCOGS:
    """GL-derived COGS for an arbitrary set of anchor (shipped) sales order ids.

    Callers pass whatever window/anchor query they need (cogs-summary's
    `days` window, the accounting dashboard's MTD window, or the freemium
    profit-summary's month/YTD windows) — this function only needs the
    resulting order ids, so all three surfaces share one derivation.
    """
    ids = sorted({int(i) for i in order_ids})

    ship_totals = _sum_ship_side(db, ids)
    po_ids = _linked_production_order_ids(db, ids)
    variance = _sum_completion_variance(db, po_ids)

    reconciliation = COGSReconciliation(
        ship_cogs_5000=ship_totals[SHIP_COGS_ACCOUNT],
        packaging_5010=ship_totals[SHIP_PACKAGING_ACCOUNT],
        completion_variance_5200=variance,
    )

    legacy = (
        _legacy_buckets(db, ids)
        if include_legacy
        else {"materials": Decimal("0.00"), "labor": Decimal("0.00"), "packaging": Decimal("0.00")}
    )

    return GLDerivedCOGS(
        order_ids=ids,
        reconciliation=reconciliation,
        legacy_materials=legacy["materials"],
        legacy_labor=legacy["labor"],
        legacy_packaging=legacy["packaging"],
    )


def shipped_order_ids_in_window(
    db: Session, *, start: Optional[datetime] = None, end: Optional[datetime] = None
) -> List[int]:
    """Anchor query shared by callers: shipped/completed/delivered orders
    whose shipped_at falls in [start, end). Either bound may be omitted.

    `delivered` is included alongside `shipped`/`completed` because a
    delivered order was shipped — its ship JE (5000/5010) already posted —
    so it must anchor COGS the same way it anchors revenue. Dropping it here
    left delivered orders contributing revenue with zero COGS in the
    dashboard's gross_profit/gross_margin (CodeRabbit #897).
    """
    query = db.query(SalesOrder.id).filter(
        SalesOrder.status.in_(["shipped", "completed", "delivered"])
    )
    if start is not None:
        query = query.filter(SalesOrder.shipped_at >= start)
    if end is not None:
        query = query.filter(SalesOrder.shipped_at < end)
    return [row[0] for row in query.all()]
