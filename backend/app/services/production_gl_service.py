"""
Production completion GL poster (#880).

When a production order completes, the inventory ledger records material
consumption and finished-goods receipts — but historically nothing posted
those movements to the general ledger, so Raw Materials (1200) was never
relieved and Finished Goods (1220) went negative the moment shipping
credited it.

This service sweeps a production order's UNJOURNALED consumption/receipt
inventory transactions and posts ONE journal entry that moves actual
material cost through WIP (1210) into Finished Goods (1220) at the
receipt values, routing the difference to 5200 "COGS - Other" as a
production variance:

    DR 1210  total consumption (materials + packaging + labor + FG inputs)
    CR 1200  component / material / supply consumption
    CR 1230  packaging consumption
    CR 1220  purchased finished-good BOM-input consumption
    CR 5100  SVC- labor consumption
    DR acct  receipts by item_type (1200/1220/1230 per #910 map) / CR 1210 same
    V = R + S - C   (R = receipts total; S = this PO's scrap-JE 1210 credits;
                     C = total consumption)
      V > 0:  DR 1210 V / CR 5200 V
      V < 0:  DR 5200 |V| / CR 1210 |V|

The S term guarantees 1210 nets to exactly zero for every completed
production order even when operation scrap posted DR 5020 / CR 1210
mid-order.

Why 5200 and not 5030: 5030 "Inventory Adjustment" is seeded at
Schedule C line '27a' — a persistent credit there surfaces as a negative
other-expense on the tax export. 5200 "COGS - Other" sits at Schedule C
line '38', so the variance credit nets INSIDE the Schedule C COGS
section where it belongs, and 5030 keeps a clean shrinkage-only meaning.

IDEMPOTENCY IS THE SWEEP ITSELF: only transactions with
journal_entry_id IS NULL are picked up, and every swept transaction is
linked to the created entry. Re-running is a no-op; per-op consumption
followed by bulk completion posts each transaction exactly once.

Deliberately NOT a source_type/source_id existence check: scrap journal
entries share source_type='production_order' AND the same source_id, so
an existence check would wrongly skip the completion entry for any
order that scrapped mid-run (pinned by test).
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session, joinedload

from app.logging_config import get_logger
from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.models.inventory import InventoryTransaction
from app.models.production_order import ProductionOrder, ScrapRecord
from app.services.gl_account_map import inventory_account_for

logger = get_logger(__name__)

# Advisory-lock namespace for the completion poster. Distinct from the
# entry-number lock (74002) and the ship guard (74003) in
# transaction_service so completion locks never collide with either.
_COMPLETION_GUARD_LOCK_NAMESPACE = 74004

RAW_MATERIALS_ACCOUNT = "1200"
WIP_ACCOUNT = "1210"
FINISHED_GOODS_ACCOUNT = "1220"
PACKAGING_ACCOUNT = "1230"
DIRECT_LABOR_ACCOUNT = "5100"
COGS_OTHER_ACCOUNT = "5200"

# Convention shared with the COGS summary (admin/accounting.py): consumption
# rows whose product SKU starts with SVC- are built-in labor, not materials.
LABOR_SKU_PREFIX = "SVC-"

_MONEY = Decimal("0.01")

# Account attributes mirror migrations 045/052 so older local databases that
# predate those migrations can still post (same pattern as
# payment_service._ensure_core_sales_accounts).
_COMPLETION_GL_ACCOUNTS = {
    "1200": ("Inventory", "asset", None, True, "Raw materials and finished goods"),
    "1210": ("WIP Inventory", "asset", None, True, "Work-in-progress: Parts currently in production"),
    "1220": ("Finished Goods Inventory", "asset", None, True, "Completed parts on shelf, ready to ship"),
    "1230": ("Packaging Inventory", "asset", None, True, "Boxes, labels, tape for shipping"),
    "5100": ("COGS - Direct Labor", "expense", "37", False, "Direct labor costs for production"),
    "5200": ("COGS - Other", "expense", "38", False, "Other production costs"),
}


@dataclass
class CompletionGLPreview:
    """What create_production_completion_gl_entry would post for one PO.

    Built by the same code the poster runs, so the backfill script's
    dry-run output can never drift from the real posting.

    Consumption and receipts are held as account-keyed maps (#910) so a
    manufactured component consumed/received routes to its own inventory
    account instead of a hard-coded 1200/1220. The named scalar properties
    (material_cost/packaging_cost/labor_cost/finished_goods_value) are kept
    as views over those maps for the logging + backfill call sites.
    """
    production_order_id: int
    production_order_code: str
    transaction_ids: List[int]
    consumption_by_account: dict[str, Decimal]  # CR side: account -> amount
    receipt_by_account: dict[str, Decimal]      # DR side: account -> amount
    scrap_wip_credits: Decimal    # S: prior scrap-JE 1210 credits
    variance: Decimal             # V = receipts + S − consumption
    lines: List[Tuple[str, Decimal, str]]

    @property
    def material_cost(self) -> Decimal:
        """Consumption credited to Raw Materials (1200)."""
        return self.consumption_by_account.get(RAW_MATERIALS_ACCOUNT, Decimal("0.00"))

    @property
    def packaging_cost(self) -> Decimal:
        """Consumption credited to Packaging (1230)."""
        return self.consumption_by_account.get(PACKAGING_ACCOUNT, Decimal("0.00"))

    @property
    def labor_cost(self) -> Decimal:
        """SVC- consumption credited to Direct Labor (5100)."""
        return self.consumption_by_account.get(DIRECT_LABOR_ACCOUNT, Decimal("0.00"))

    @property
    def finished_goods_value(self) -> Decimal:
        """Total production receipts (DR by item_type map, CR 1210)."""
        return sum(self.receipt_by_account.values(), Decimal("0.00"))

    @property
    def total_consumption(self) -> Decimal:
        return sum(self.consumption_by_account.values(), Decimal("0.00"))


def _ensure_completion_gl_accounts(db: Session) -> None:
    """Create any missing accounts the completion entry posts to."""
    existing = {
        row[0]
        for row in db.query(GLAccount.account_code).filter(
            GLAccount.account_code.in_(_COMPLETION_GL_ACCOUNTS.keys())
        )
    }
    for code, (name, account_type, schedule_c_line, is_system, description) in (
        _COMPLETION_GL_ACCOUNTS.items()
    ):
        if code in existing:
            continue
        db.add(GLAccount(
            account_code=code,
            name=name,
            account_type=account_type,
            schedule_c_line=schedule_c_line,
            is_system=is_system,
            active=True,
            description=description,
        ))
    db.flush()


def _sweep_unjournaled_transactions(
    db: Session, production_order_id: int
) -> List[InventoryTransaction]:
    """This production order's GL-eligible, not-yet-journaled ledger rows.

    Held (requires_approval without approved_by) and voided rows never
    affected on_hand and are excluded, mirroring the COGS summary and
    shipment-GL filters. Scrap rows are excluded by type — the scrap
    poster creates and links its own journal entry.
    """
    return (
        db.query(InventoryTransaction)
        .options(joinedload(InventoryTransaction.product))
        .filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == production_order_id,
            InventoryTransaction.transaction_type.in_(["consumption", "receipt"]),
            InventoryTransaction.journal_entry_id.is_(None),
            InventoryTransaction.voided_by.is_(None),
            ~(
                InventoryTransaction.requires_approval.is_(True)
                & InventoryTransaction.approved_by.is_(None)
            ),
        )
        .order_by(InventoryTransaction.id)
        .all()
    )


def _txn_cost(txn: InventoryTransaction) -> Decimal:
    """Value one ledger row at its frozen cost.

    total_cost when set, else abs(quantity) × cost_per_unit — the abs()
    neutralizes legacy positive-sign consumption rows (pre-HARD-4a rows
    stored magnitudes, modern rows store signed deltas).
    """
    if txn.total_cost is not None:
        return Decimal(str(txn.total_cost or 0)).quantize(_MONEY)
    quantity = abs(Decimal(str(txn.quantity or 0)))
    unit_cost = Decimal(str(txn.cost_per_unit or 0))
    return (quantity * unit_cost).quantize(_MONEY)


def _scrap_wip_credits(db: Session, production_order_id: int) -> Decimal:
    """S term: 1210 credits already posted by this PO's scrap journal entries.

    Scoped to journal entries referenced by ScrapRecord rows (not by
    source_type/source_id alone) so a prior completion entry's own 1210
    credits can never leak into S on any re-entry path.
    """
    scrap_je_ids = [
        row[0]
        for row in db.query(ScrapRecord.journal_entry_id).filter(
            ScrapRecord.production_order_id == production_order_id,
            ScrapRecord.journal_entry_id.isnot(None),
        )
    ]
    if not scrap_je_ids:
        return Decimal("0.00")

    total = (
        db.query(func.coalesce(func.sum(GLJournalEntryLine.credit_amount), 0))
        .join(GLJournalEntry, GLJournalEntryLine.journal_entry_id == GLJournalEntry.id)
        .join(GLAccount, GLJournalEntryLine.account_id == GLAccount.id)
        .filter(
            GLJournalEntryLine.journal_entry_id.in_(scrap_je_ids),
            GLJournalEntry.source_type == "production_order",
            GLJournalEntry.source_id == production_order_id,
            GLJournalEntry.status != "voided",
            GLAccount.account_code == WIP_ACCOUNT,
            GLJournalEntryLine.credit_amount > 0,
        )
        .scalar()
    )
    return Decimal(str(total or 0)).quantize(_MONEY)


def _build_preview(
    db: Session,
    production_order: ProductionOrder,
    txns: List[InventoryTransaction],
) -> CompletionGLPreview:
    # CR side (consumption) and DR side (receipts), each keyed by the account
    # the shared item_type map (#910) routes the row to. A manufactured
    # component consumed as a BOM input credits 1200; a purchased finished_good
    # BOM input credits 1220; packaging credits 1230; SVC- labor credits 5100.
    # Receipts debit their mapped inventory account (component->1200,
    # packaging->1230, finished_good->1220) instead of a flat DR 1220.
    consumption_by_account: dict[str, Decimal] = {}
    receipt_by_account: dict[str, Decimal] = {}

    for txn in txns:
        cost = _txn_cost(txn)
        product = txn.product
        item_type = (product.item_type if product else "") or ""
        if txn.transaction_type == "receipt":
            # Includes overrun receipts — both rows receive at the product's
            # effective cost frozen on the transaction.
            account = inventory_account_for(item_type)
            receipt_by_account[account] = (
                receipt_by_account.get(account, Decimal("0.00")) + cost
            )
            continue
        sku = (product.sku if product else "") or ""
        if sku.startswith(LABOR_SKU_PREFIX):
            account = DIRECT_LABOR_ACCOUNT
        else:
            account = inventory_account_for(item_type)
        consumption_by_account[account] = (
            consumption_by_account.get(account, Decimal("0.00")) + cost
        )

    scrap_credits = _scrap_wip_credits(db, production_order.id)
    total_consumption = sum(consumption_by_account.values(), Decimal("0.00"))
    total_receipts = sum(receipt_by_account.values(), Decimal("0.00"))
    variance = total_receipts + scrap_credits - total_consumption

    lines: List[Tuple[str, Decimal, str]] = []
    if total_consumption > 0:
        lines.append((WIP_ACCOUNT, total_consumption, "DR"))
    for account, amount in sorted(consumption_by_account.items()):
        if amount > 0:
            lines.append((account, amount, "CR"))
    for account, amount in sorted(receipt_by_account.items()):
        if amount > 0:
            lines.append((account, amount, "DR"))
    if total_receipts > 0:
        lines.append((WIP_ACCOUNT, total_receipts, "CR"))
    # Variance so WIP nets to exactly zero per completed order — the S term
    # offsets scrap entries that already credited 1210 mid-order.
    if variance > 0:
        lines.append((WIP_ACCOUNT, variance, "DR"))
        lines.append((COGS_OTHER_ACCOUNT, variance, "CR"))
    elif variance < 0:
        lines.append((COGS_OTHER_ACCOUNT, -variance, "DR"))
        lines.append((WIP_ACCOUNT, -variance, "CR"))

    return CompletionGLPreview(
        production_order_id=production_order.id,
        production_order_code=production_order.code,
        transaction_ids=[txn.id for txn in txns],
        consumption_by_account=consumption_by_account,
        receipt_by_account=receipt_by_account,
        scrap_wip_credits=scrap_credits,
        variance=variance,
        lines=lines,
    )


def compute_completion_gl_preview(
    db: Session, production_order: ProductionOrder
) -> Optional[CompletionGLPreview]:
    """Preview the completion entry without posting (backfill dry-run).

    Returns None when the order has no sweepable transactions.
    """
    txns = _sweep_unjournaled_transactions(db, production_order.id)
    if not txns:
        return None
    return _build_preview(db, production_order, txns)


def find_unjournaled_production_order_ids(
    db: Session, production_order_ids: Optional[List[int]] = None
) -> List[int]:
    """Production orders that have at least one sweepable ledger row.

    Used by the backfill script (candidate discovery) and mirrors the
    GL-health counter's predicate on the accounting dashboard.
    """
    query = db.query(InventoryTransaction.reference_id).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.transaction_type.in_(["consumption", "receipt"]),
        InventoryTransaction.journal_entry_id.is_(None),
        InventoryTransaction.voided_by.is_(None),
        ~(
            InventoryTransaction.requires_approval.is_(True)
            & InventoryTransaction.approved_by.is_(None)
        ),
    )
    if production_order_ids:
        query = query.filter(
            InventoryTransaction.reference_id.in_(production_order_ids)
        )
    return sorted({row[0] for row in query.distinct() if row[0] is not None})


def create_production_completion_gl_entry(
    db: Session,
    production_order: ProductionOrder,
    user_id: Optional[int] = None,
    entry_date: Optional[date] = None,
) -> Optional[GLJournalEntry]:
    """Post the completion journal entry for one production order.

    Thin wrapper over create_production_completion_gl_entry_with_preview
    for callers that only need the entry (the app completion paths).
    Returns the created entry, or None when there is nothing to post.
    """
    journal_entry, _ = create_production_completion_gl_entry_with_preview(
        db, production_order, user_id=user_id, entry_date=entry_date
    )
    return journal_entry


def create_production_completion_gl_entry_with_preview(
    db: Session,
    production_order: ProductionOrder,
    user_id: Optional[int] = None,
    entry_date: Optional[date] = None,
) -> Tuple[Optional[GLJournalEntry], Optional[CompletionGLPreview]]:
    """Post the completion journal entry for one production order.

    Sweeps the order's unjournaled consumption/receipt transactions,
    posts a single balanced entry (see module docstring for the shape),
    and links every swept transaction to it.

    Returns (journal_entry, preview). The preview is built from the SAME
    sweep the entry posted — computed after the advisory lock below — so
    a caller recording what was posted (the backfill manifest) uses this
    instead of calling compute_completion_gl_preview first, which would
    both duplicate the sweep and race the lock (#892 round 2).
    journal_entry is None when nothing posted; preview is None when no
    rows were sweepable at all (and carries empty lines when the swept
    rows were all zero-cost).

    Runs in the caller's session/transaction — no commit here. The call
    sites run this strictly AFTER consumption + receipts succeed in the
    SAME transaction, so a poster failure rolls everything back together
    (no half-posted state).

    Args:
        db: Database session (caller owns the commit boundary)
        production_order: The production order to journal
        user_id: Creating user id, if known
        entry_date: Entry date; defaults to today. The live-books backfill
            passes the PO's completed_at date to backdate corrections.
    """
    # Serialize concurrent completions of the same production order (#892
    # CodeRabbit): the sweep predicate (journal_entry_id IS NULL) is a plain
    # SELECT with no uniqueness constraint on GLJournalEntry
    # (source_type, source_id), and the per-op auto-complete path
    # (operation_status -> process_production_completion) reaches here
    # without a ProductionOrder row lock — so two concurrent completions
    # could both sweep the same rows and double-post. Transaction-scoped
    # advisory lock keyed by production_order.id, same pattern as
    # transaction_service.ship_order (74003) and _next_entry_number (74002).
    # Living INSIDE the poster covers every caller (bulk complete, per-op
    # auto-complete, accept-short, backfill script) regardless of its own
    # locking. Released automatically at commit/rollback.
    db.execute(
        text(
            """
            SELECT pg_advisory_xact_lock(
                CAST(:namespace AS integer),
                CAST(:key AS integer)
            )
            """
        ),
        {
            "namespace": _COMPLETION_GUARD_LOCK_NAMESPACE,
            "key": production_order.id,
        },
    )

    txns = _sweep_unjournaled_transactions(db, production_order.id)
    if not txns:
        return None, None

    preview = _build_preview(db, production_order, txns)
    if not preview.lines:
        # Every swept row carries zero cost — nothing to post. Leaving the
        # rows unjournaled is deliberate: they surface in the GL-health
        # counter instead of being silently linked to nothing.
        logger.info(
            "Production completion GL skipped for PO %s: %d transaction(s) "
            "swept but all zero-cost",
            production_order.code,
            len(txns),
        )
        return None, preview

    # Lazy import to keep service-layer import graphs acyclic (pattern from
    # sales_order_fulfillment_service).
    from app.services.transaction_service import TransactionService

    _ensure_completion_gl_accounts(db)
    ts = TransactionService(db)
    journal_entry = ts.create_journal_entry(
        description=f"Production completion for PO#{production_order.code}",
        lines=preview.lines,
        source_type="production_order",
        source_id=production_order.id,
        user_id=user_id,
        entry_date=entry_date,
    )

    for txn in txns:
        txn.journal_entry_id = journal_entry.id
    db.flush()

    logger.info(
        "Posted production completion GL entry %s for PO %s: "
        "materials=%s packaging=%s labor=%s fg=%s scrap_credits=%s variance=%s "
        "(%d transactions linked)",
        journal_entry.entry_number,
        production_order.code,
        preview.material_cost,
        preview.packaging_cost,
        preview.labor_cost,
        preview.finished_goods_value,
        preview.scrap_wip_credits,
        preview.variance,
        len(txns),
    )
    return journal_entry, preview
