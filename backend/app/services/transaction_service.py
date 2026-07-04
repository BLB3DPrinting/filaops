"""
Transaction Service - Atomic inventory + accounting transactions

All physical inventory movements MUST go through this service to ensure:
1. InventoryTransaction record created
2. Inventory quantity updated
3. GLJournalEntry + lines created
4. All linked together
5. Single commit (atomic)

Usage:
    txn_service = TransactionService(db)
    inv_txn, journal_entry = txn_service.receipt_finished_good(...)
    db.commit()  # Caller commits
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Tuple, Optional, NamedTuple

from sqlalchemy.orm import Session
from sqlalchemy import func, text

from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.models.inventory import InventoryTransaction
from app.models.production_order import ScrapRecord
from app.models.product import Product
from app.models.sales_order import SalesOrder
from app.services import inventory_ledger

_JOURNAL_ENTRY_NUMBER_LOCK_NAMESPACE = 74002
# Distinct namespace so ship-guard locks never collide with entry-number locks.
_SHIPMENT_GUARD_LOCK_NAMESPACE = 74003


class DuplicateShipmentError(Exception):
    """Raised when ship_order is retried for a sales order that already has a
    non-voided shipment journal entry or shipment inventory transaction.

    A retry that skipped the JE but still posted inventory would silently
    double-decrement finished goods, so the guard raises BEFORE any inventory
    transaction is posted (#880). Callers convert this to HTTP 409.
    """


class MaterialConsumption(NamedTuple):
    """Material to consume in an operation"""
    product_id: int
    quantity: Decimal
    unit_cost: Decimal
    unit: str = "EA"


class ShipmentItem(NamedTuple):
    """Item being shipped"""
    product_id: int
    quantity: Decimal
    unit_cost: Decimal


class PackagingUsed(NamedTuple):
    """Packaging consumed in shipment"""
    product_id: int
    quantity: int  # Whole units only
    unit_cost: Decimal


class ReceiptItem(NamedTuple):
    """Item being received from PO"""
    product_id: int
    quantity: Decimal
    unit_cost: Decimal
    unit: str = "EA"
    lot_number: Optional[str] = None


class TransactionService:
    """
    Atomic transaction handler for inventory + accounting.

    IMPORTANT: This service does NOT commit. Caller is responsible for commit.
    This allows multiple operations to be grouped in a single transaction.
    """

    def __init__(self, db: Session):
        self.db = db
        self._account_cache: dict[str, int] = {}  # code -> id cache

    # === INTERNAL HELPERS ===

    def _get_account_id(self, account_code: str) -> int:
        """Get account ID by code, with caching"""
        if account_code not in self._account_cache:
            account = self.db.query(GLAccount).filter(
                GLAccount.account_code == account_code
            ).first()
            if not account:
                raise ValueError(f"Account {account_code} not found in chart of accounts")
            self._account_cache[account_code] = account.id
        return self._account_cache[account_code]

    def _next_entry_number(self) -> str:
        """Generate next journal entry number under a transaction-scoped DB lock."""
        year = datetime.now(timezone.utc).year

        self.db.execute(
            text(
                """
                SELECT pg_advisory_xact_lock(
                    CAST(:namespace AS integer),
                    CAST(:year AS integer)
                )
                """
            ),
            {"namespace": _JOURNAL_ENTRY_NUMBER_LOCK_NAMESPACE, "year": year},
        )

        # Find max entry number for this year
        pattern = f"JE-{year}-%"
        result = self.db.query(func.max(GLJournalEntry.entry_number)).filter(
            GLJournalEntry.entry_number.like(pattern),
            GLJournalEntry.entry_number.op("~")(rf"^JE-{year}-\d{{6}}$"),
        ).scalar()

        if result:
            # Extract sequence from "JE-2026-000042"
            seq = int(result.split("-")[2]) + 1
        else:
            seq = 1

        return f"JE-{year}-{seq:06d}"

    def create_journal_entry(
        self,
        description: str,
        lines: List[Tuple[str, Decimal, str]],
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
        user_id: Optional[int] = None,
        entry_date: Optional[date] = None,
    ) -> GLJournalEntry:
        """Create a balanced posted journal entry for service-level callers."""
        return self._create_journal_entry(
            description=description,
            lines=lines,
            source_type=source_type,
            source_id=source_id,
            user_id=user_id,
            entry_date=entry_date,
        )

    def _create_journal_entry(
        self,
        description: str,
        lines: List[Tuple[str, Decimal, str]],  # (account_code, amount, 'DR'|'CR')
        source_type: str = None,
        source_id: int = None,
        user_id: int = None,
        entry_date: Optional[date] = None,
    ) -> GLJournalEntry:
        """
        Create balanced journal entry with lines.

        Args:
            description: Entry description/memo
            lines: List of (account_code, amount, 'DR'|'CR') tuples
            source_type: 'production_order', 'sales_order', 'purchase_order', etc.
            source_id: ID of source document
            user_id: Creating user ID
            entry_date: Entry date; defaults to today. Lets correction posters
                (e.g. the #880 completion-GL backfill) backdate entries.

        Returns:
            GLJournalEntry with lines attached

        Raises:
            ValueError: If entry doesn't balance
        """
        je = GLJournalEntry(
            entry_number=self._next_entry_number(),
            entry_date=entry_date or date.today(),
            description=description,
            source_type=source_type,
            source_id=source_id,
            status="posted",  # Auto-post for system transactions
            created_by=user_id,
            posted_by=user_id,
            posted_at=datetime.now(timezone.utc),
        )
        self.db.add(je)
        self.db.flush()  # Get ID for lines

        total_dr = Decimal("0")
        total_cr = Decimal("0")

        for idx, (account_code, amount, dr_cr) in enumerate(lines):
            account_id = self._get_account_id(account_code)

            line = GLJournalEntryLine(
                journal_entry_id=je.id,
                account_id=account_id,
                debit_amount=amount if dr_cr == 'DR' else Decimal("0"),
                credit_amount=amount if dr_cr == 'CR' else Decimal("0"),
                line_order=idx,
            )
            self.db.add(line)

            if dr_cr == 'DR':
                total_dr += amount
            else:
                total_cr += amount

        # Validate balanced (within penny for rounding)
        if abs(total_dr - total_cr) > Decimal("0.01"):
            raise ValueError(f"Journal entry not balanced: DR={total_dr}, CR={total_cr}")

        return je

    def _post_inventory(
        self,
        *,
        product_id: int,
        transaction_type: str,
        quantity_delta: Decimal,
        unit_cost: Decimal,
        reference_type: str = None,
        reference_id: int = None,
        lot_number: str = None,
        notes: str = None,
        unit: str = "EA",
        location_id: int = None,
    ) -> InventoryTransaction:
        """
        Post an inventory movement through the canonical ledger (HARD-4a).

        Signed delta: positive increases stock. Writes the transaction row
        and mutates on_hand together; no commit (caller owns the boundary).
        """
        if location_id is None:
            # Resolve the real default warehouse — the old helpers assumed
            # primary key 1, which is wrong on any DB where MAIN isn't id 1.
            from app.services.inventory_service import (
                get_or_create_default_location,
            )
            location_id = get_or_create_default_location(self.db).id

        return inventory_ledger.post(
            self.db,
            product_id=product_id,
            location_id=location_id,
            transaction_type=transaction_type,
            quantity_delta=quantity_delta,
            cost_per_unit=unit_cost,
            reference_type=reference_type,
            reference_id=reference_id,
            lot_number=lot_number,
            notes=notes,
            unit=unit,
        )

    def _create_inventory_transaction(
        self,
        product_id: int,
        transaction_type: str,
        quantity: Decimal,
        unit_cost: Decimal,
        reference_type: str = None,
        reference_id: int = None,
        lot_number: str = None,
        notes: str = None,
        unit: str = "EA",
        location_id: int = None,
    ) -> InventoryTransaction:
        """Create a ledger ROW without touching on_hand.

        Only legitimate use: WIP-side audit rows (scrap_materials), where
        the material already left inventory at issue time so on_hand must
        NOT change again. Every on-hand-affecting movement goes through
        _post_inventory / inventory_ledger.post instead (HARD-4a).
        HARD-4b reconciliation must exclude these rows; HARD-11 revisits
        whether WIP scrap should write to the inventory ledger at all.
        """
        txn = InventoryTransaction(
            product_id=product_id,
            location_id=location_id or 1,
            transaction_type=transaction_type,
            quantity=quantity,
            cost_per_unit=unit_cost,
            total_cost=abs(quantity) * unit_cost,
            unit=unit,
            reference_type=reference_type,
            reference_id=reference_id,
            lot_number=lot_number,
            notes=notes,
            transaction_date=date.today(),
        )
        self.db.add(txn)
        return txn

    # === PRODUCTION TRANSACTIONS ===

    def issue_materials_for_operation(
        self,
        production_order_id: int,
        operation_sequence: int,
        materials: List[MaterialConsumption],
        user_id: int = None,
    ) -> Tuple[List[InventoryTransaction], GLJournalEntry]:
        """
        Issue raw materials when production operation starts.

        Inventory: CONSUMPTION for each material (negative qty)
        Accounting: DR WIP (1210), CR Raw Materials (1200)

        Returns:
            Tuple of (list of inventory transactions, journal entry)
        """
        inv_txns = []
        total_cost = Decimal("0")

        for mat in materials:
            inv_txn = self._post_inventory(
                product_id=mat.product_id,
                transaction_type="consumption",
                quantity_delta=-mat.quantity,
                unit_cost=mat.unit_cost,
                reference_type="production_order",
                reference_id=production_order_id,
                notes=f"Material issue for operation {operation_sequence}",
                unit=mat.unit,
            )
            inv_txns.append(inv_txn)

            total_cost += mat.quantity * mat.unit_cost

        # Create journal entry: DR WIP, CR Raw Materials
        # Skip GL entry if total cost is zero (no monetary value to record)
        je = None
        if total_cost > 0:
            je = self._create_journal_entry(
                description=f"Material issue for PO#{production_order_id} op {operation_sequence}",
                lines=[
                    ("1210", total_cost, "DR"),  # WIP Inventory
                    ("1200", total_cost, "CR"),  # Raw Materials Inventory
                ],
                source_type="production_order",
                source_id=production_order_id,
                user_id=user_id,
            )

            # Link transactions to journal entry
            for inv_txn in inv_txns:
                inv_txn.journal_entry_id = je.id

        return inv_txns, je

    def receipt_finished_good(
        self,
        production_order_id: int,
        product_id: int,
        quantity: Decimal,
        unit_cost: Decimal,
        lot_number: str = None,
        user_id: int = None,
    ) -> Tuple[InventoryTransaction, GLJournalEntry]:
        """
        Receipt FG into inventory when QC passes.

        Inventory: RECEIPT (positive qty)
        Accounting: DR FG Inventory (1220), CR WIP (1210)

        Returns:
            Tuple of (inventory transaction, journal entry)
        """
        total_cost = quantity * unit_cost

        inv_txn = self._post_inventory(
            product_id=product_id,
            transaction_type="receipt",
            quantity_delta=quantity,
            unit_cost=unit_cost,
            reference_type="production_order",
            reference_id=production_order_id,
            lot_number=lot_number,
            notes="FG receipt from production",
        )

        # Create journal entry: DR FG Inventory, CR WIP
        # Skip GL entry if total cost is zero (no monetary value to record)
        je = None
        if total_cost > 0:
            je = self._create_journal_entry(
                description=f"FG receipt from PO#{production_order_id}",
                lines=[
                    ("1220", total_cost, "DR"),  # FG Inventory
                    ("1210", total_cost, "CR"),  # WIP Inventory
                ],
                source_type="production_order",
                source_id=production_order_id,
                user_id=user_id,
            )

            inv_txn.journal_entry_id = je.id

        return inv_txn, je

    def scrap_materials(
        self,
        production_order_id: int,
        operation_sequence: int,
        product_id: int,
        quantity: Decimal,
        unit_cost: Decimal,
        reason_code: str,
        reason_id: int = None,
        notes: str = None,
        user_id: int = None,
    ) -> Tuple[InventoryTransaction, GLJournalEntry, ScrapRecord]:
        """
        Write off scrapped materials or failed parts.

        Inventory: SCRAP (negative qty)
        Accounting: DR Scrap Expense (5020), CR WIP (1210)

        Returns:
            Tuple of (inventory transaction, journal entry, scrap record)
        """
        total_cost = quantity * unit_cost

        # Create inventory transaction
        inv_txn = self._create_inventory_transaction(
            product_id=product_id,
            transaction_type="scrap",
            quantity=-quantity,  # Negative = removal
            unit_cost=unit_cost,
            reference_type="production_order",
            reference_id=production_order_id,
            notes=f"Scrap: {reason_code}",
        )
        self.db.flush()  # Get inv_txn.id for scrap record

        # WIP doesn't need quantity update (not in inventory yet)
        # Only update if scrapping FG that was already receipted

        # Create journal entry: DR Scrap Expense, CR WIP
        # Skip GL entry if total cost is zero (no monetary value to record)
        je = None
        if total_cost > 0:
            je = self._create_journal_entry(
                description=f"Scrap at PO#{production_order_id} op {operation_sequence}: {reason_code}",
                lines=[
                    ("5020", total_cost, "DR"),  # Scrap Expense
                    ("1210", total_cost, "CR"),  # WIP Inventory
                ],
                source_type="production_order",
                source_id=production_order_id,
                user_id=user_id,
            )

            inv_txn.journal_entry_id = je.id

        # Create scrap record
        scrap = ScrapRecord(
            production_order_id=production_order_id,
            operation_sequence=operation_sequence,
            product_id=product_id,
            quantity=quantity,
            unit_cost=unit_cost,
            total_cost=total_cost,
            scrap_reason_id=reason_id,
            scrap_reason_code=reason_code,
            notes=notes,
            inventory_transaction_id=inv_txn.id,
            journal_entry_id=je.id if je else None,
            created_by_user_id=user_id,
        )
        self.db.add(scrap)

        return inv_txn, je, scrap

    def scrap_finished_goods(
        self,
        production_order_id: int,
        product_id: int,
        quantity: Decimal,
        unit_cost: Decimal,
        reason_code: str,
        reason_id: int = None,
        notes: str = None,
        user_id: int = None,
    ) -> Tuple[InventoryTransaction, Optional[GLJournalEntry], ScrapRecord]:
        """
        Scrap finished goods that were already received into inventory.

        Unlike scrap_materials (WIP-side audit row, on_hand already gone), the
        units here are physically on hand, so the movement goes through the
        canonical ledger (HARD-4a) and decrements on_hand.

        Inventory: SCRAP (negative qty); on_hand decremented.
        Accounting: DR Scrap Expense (5020), CR FG Inventory (1220).

        Returns:
            Tuple of (inventory transaction, journal entry, scrap record)
        """
        # Boundary validation: a non-positive quantity would bypass the
        # on-hand guard (a zero/negative delta can't make stock go negative)
        # and a negative unit_cost would post a backwards GL entry. Reject
        # both at the service boundary.
        if quantity <= 0:
            raise ValueError(
                f"Scrap quantity must be positive, got {quantity}"
            )
        if unit_cost < 0:
            raise ValueError(
                f"Scrap unit_cost must be non-negative, got {unit_cost}"
            )

        total_cost = quantity * unit_cost

        # Policy gate: refuse to drive on_hand negative.  inventory_ledger.post
        # is mechanism-only; stock-sufficiency checks live in callers.
        # Acquiring FOR UPDATE here serializes with the identical lock in
        # _post_inventory so there is no TOCTOU window.
        from app.services.inventory_service import get_or_create_default_location
        resolved_location_id = get_or_create_default_location(self.db).id
        inv_row = inventory_ledger.get_or_create_inventory_row(
            self.db, product_id, resolved_location_id
        )
        current_on_hand = Decimal(str(inv_row.on_hand_quantity or 0))
        if quantity > current_on_hand:
            raise ValueError(
                f"Cannot scrap {quantity} units of product {product_id}: "
                f"only {current_on_hand} on hand"
            )

        inv_txn = self._post_inventory(
            product_id=product_id,
            transaction_type="scrap",
            quantity_delta=-quantity,  # Negative = removal from stock
            unit_cost=unit_cost,
            reference_type="production_order",
            reference_id=production_order_id,
            notes=f"Scrap (finished goods): {reason_code}",
            location_id=resolved_location_id,
        )
        self.db.flush()  # Get inv_txn.id for the scrap record

        je = None
        if total_cost > 0:
            je = self._create_journal_entry(
                description=f"Scrap finished goods at PO#{production_order_id}: {reason_code}",
                lines=[
                    ("5020", total_cost, "DR"),  # Scrap Expense
                    ("1220", total_cost, "CR"),  # Finished Goods Inventory
                ],
                source_type="production_order",
                source_id=production_order_id,
                user_id=user_id,
            )
            inv_txn.journal_entry_id = je.id

        scrap = ScrapRecord(
            production_order_id=production_order_id,
            product_id=product_id,
            quantity=quantity,
            unit_cost=unit_cost,
            total_cost=total_cost,
            scrap_reason_id=reason_id,
            scrap_reason_code=reason_code,
            notes=notes,
            inventory_transaction_id=inv_txn.id,
            journal_entry_id=je.id if je else None,
            created_by_user_id=user_id,
        )
        self.db.add(scrap)

        return inv_txn, je, scrap

    # === SHIPPING TRANSACTIONS ===

    def ship_order(
        self,
        sales_order_id: int,
        items: List[ShipmentItem],
        packaging: List[PackagingUsed] = None,
        user_id: int = None,
    ) -> Tuple[List[InventoryTransaction], GLJournalEntry]:
        """
        Ship FG to customer, consume packaging.

        Inventory:
            - SHIPMENT for each FG item (negative qty)
            - CONSUMPTION for packaging (negative qty)
        Accounting:
            - DR COGS (5000), CR FG Inventory (1220) for products
            - DR Shipping Supplies (5010), CR Packaging Inv (1230) for packaging

        Returns:
            Tuple of (list of inventory transactions, journal entry)

        Raises:
            DuplicateShipmentError: If a non-voided shipment journal entry OR
                a non-voided shipment inventory transaction already exists for
                this sales order (retry would double-relieve FG inventory).
                Raised BEFORE any inventory transaction posts.
        """
        # Serialize concurrent ships of the same order (#880 CodeRabbit): the
        # existing-JE lookup below is a plain SELECT with no uniqueness
        # constraint on (source_type, source_id), so two concurrent requests
        # could both pass it and double-post. Transaction-scoped advisory lock
        # keyed by sales_order_id — same pattern as _next_entry_number, but a
        # distinct namespace so ship locks never collide with entry-number
        # locks. Released automatically at commit/rollback.
        self.db.execute(
            text(
                """
                SELECT pg_advisory_xact_lock(
                    CAST(:namespace AS integer),
                    CAST(:key AS integer)
                )
                """
            ),
            {"namespace": _SHIPMENT_GUARD_LOCK_NAMESPACE, "key": sales_order_id},
        )

        # Idempotency guard (#880): same predicate as _create_shipment_gl_entry
        # in sales_order_fulfillment_service. A skip-and-continue retry would
        # still double-decrement FG, so raise before touching inventory.
        existing_je = self.db.query(GLJournalEntry.id).filter(
            GLJournalEntry.source_type == "sales_order",
            GLJournalEntry.source_id == sales_order_id,
            GLJournalEntry.status != "voided",
        ).first()
        if existing_je:
            raise DuplicateShipmentError(
                f"Sales order {sales_order_id} already has a shipment journal "
                f"entry (id {existing_je.id}); refusing to ship again"
            )

        # Zero-cost shipments post NO journal entry (total_amount == 0 below),
        # so the JE guard alone can't see them — a retry would double-relieve
        # FG. Also refuse when a non-voided shipment inventory transaction
        # already exists for this order.
        existing_ship_txn = self.db.query(InventoryTransaction.id).filter(
            InventoryTransaction.transaction_type == "shipment",
            InventoryTransaction.reference_type == "sales_order",
            InventoryTransaction.reference_id == sales_order_id,
            InventoryTransaction.voided_by.is_(None),
        ).first()
        if existing_ship_txn:
            raise DuplicateShipmentError(
                f"Sales order {sales_order_id} already has a shipment "
                f"inventory transaction (id {existing_ship_txn.id}); "
                f"refusing to ship again"
            )

        # Unify JE description with the fulfillment path's order_number format
        # (falls back to the numeric id when no SalesOrder row exists).
        order = self.db.get(SalesOrder, sales_order_id)
        order_ref = order.order_number if order and order.order_number else sales_order_id

        inv_txns = []
        je_lines = []

        # Process FG items
        fg_total = Decimal("0")
        for item in items:
            cost = item.quantity * item.unit_cost
            fg_total += cost

            inv_txn = self._post_inventory(
                product_id=item.product_id,
                transaction_type="shipment",
                quantity_delta=-item.quantity,
                unit_cost=item.unit_cost,
                reference_type="sales_order",
                reference_id=sales_order_id,
                notes="Shipped to customer",
            )
            inv_txns.append(inv_txn)

        je_lines.append(("5000", fg_total, "DR"))   # COGS
        je_lines.append(("1220", fg_total, "CR"))   # FG Inventory

        # Process packaging
        pkg_total = Decimal("0")
        if packaging:
            for pkg in packaging:
                cost = Decimal(pkg.quantity) * pkg.unit_cost
                pkg_total += cost

                inv_txn = self._post_inventory(
                    product_id=pkg.product_id,
                    transaction_type="consumption",
                    quantity_delta=-Decimal(pkg.quantity),
                    unit_cost=pkg.unit_cost,
                    reference_type="sales_order",
                    reference_id=sales_order_id,
                    notes="Packaging for shipment",
                )
                inv_txns.append(inv_txn)

        if pkg_total > 0:
            je_lines.append(("5010", pkg_total, "DR"))   # Shipping Supplies
            je_lines.append(("1230", pkg_total, "CR"))   # Packaging Inventory

        # Create journal entry (skip if all amounts are zero)
        je = None
        total_amount = fg_total + pkg_total
        if total_amount > 0:
            je = self._create_journal_entry(
                description=f"Shipment for SO#{order_ref}",
                lines=je_lines,
                source_type="sales_order",
                source_id=sales_order_id,
                user_id=user_id,
            )

            for inv_txn in inv_txns:
                inv_txn.journal_entry_id = je.id

        return inv_txns, je

    # === PURCHASING TRANSACTIONS ===

    def receive_purchase_order(
        self,
        purchase_order_id: int,
        items: List[ReceiptItem],
        user_id: int = None,
    ) -> Tuple[List[InventoryTransaction], GLJournalEntry]:
        """
        Receive materials from vendor.

        Inventory: RECEIPT for each item (positive qty)
        Accounting: DR inventory account by item_type — packaging (1230),
            finished goods (1220), default Raw Materials (1200) — CR
            Accounts Payable (2000)

        Returns:
            Tuple of (list of inventory transactions, journal entry)
        """
        inv_txns = []
        total_cost = Decimal("0")
        cost_by_account: dict[str, Decimal] = {}

        # Batch-load products once (CodeRabbit: avoid N+1 db.get per item).
        product_ids = {item.product_id for item in items}
        products_by_id: dict[int, Product] = {
            p.id: p
            for p in self.db.query(Product).filter(Product.id.in_(product_ids))
        } if product_ids else {}

        for item in items:
            cost = item.quantity * item.unit_cost
            total_cost += cost

            # Same item_type -> account map as cycle_count_adjustment (#880):
            # a flat DR 1200 sends packaging purchases to Raw Materials while
            # shipping credits 1230, driving Packaging Inventory negative.
            product = products_by_id.get(item.product_id)
            inv_account = "1200"  # Default: Raw Materials
            if product and product.item_type == "finished_good":
                inv_account = "1220"
            elif product and product.item_type == "packaging":
                inv_account = "1230"
            cost_by_account[inv_account] = (
                cost_by_account.get(inv_account, Decimal("0")) + cost
            )

            inv_txn = self._post_inventory(
                product_id=item.product_id,
                transaction_type="receipt",
                quantity_delta=item.quantity,
                unit_cost=item.unit_cost,
                reference_type="purchase_order",
                reference_id=purchase_order_id,
                lot_number=item.lot_number,
                notes="PO receipt",
                unit=item.unit,
            )
            inv_txns.append(inv_txn)

        # Create journal entry: DR inventory accounts by item_type, CR AP
        je_lines: List[Tuple[str, Decimal, str]] = [
            (account, amount, "DR")
            for account, amount in sorted(cost_by_account.items())
        ]
        je_lines.append(("2000", total_cost, "CR"))  # Accounts Payable

        je = self._create_journal_entry(
            description=f"PO#{purchase_order_id} receipt",
            lines=je_lines,
            source_type="purchase_order",
            source_id=purchase_order_id,
            user_id=user_id,
        )

        for inv_txn in inv_txns:
            inv_txn.journal_entry_id = je.id

        return inv_txns, je

    # === ADJUSTMENT TRANSACTIONS ===

    def cycle_count_adjustment(
        self,
        product_id: int,
        expected_qty: Decimal,
        actual_qty: Decimal,
        reason: str,
        location_id: int = None,
        user_id: int = None,
    ) -> Tuple[InventoryTransaction, GLJournalEntry]:
        """
        Adjust inventory based on physical count.

        Inventory: ADJUSTMENT (+ or -)
        Accounting:
            - If shortage: DR Inv Adjustment (5030), CR Inventory
            - If overage: DR Inventory, CR Inv Adjustment (5030)

        Returns:
            Tuple of (inventory transaction, journal entry)
        """
        variance = actual_qty - expected_qty
        if variance == 0:
            raise ValueError("No variance to adjust")

        # Determine inventory account based on product type
        product = self.db.get(Product, product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        # Map product type to inventory account
        inv_account = "1200"  # Default: Raw Materials
        if product.item_type == "finished_good":
            inv_account = "1220"
        elif product.item_type == "packaging":
            inv_account = "1230"

        unit_cost = product.standard_cost or product.average_cost or Decimal("0")
        total_cost = abs(variance) * unit_cost

        # Signed variance posts through the canonical ledger: overage adds,
        # shortage subtracts — the sign ambiguity that caused cycle-count
        # drift before HARD-4a is gone.
        inv_txn = self._post_inventory(
            product_id=product_id,
            transaction_type="adjustment",
            quantity_delta=variance,
            unit_cost=unit_cost,
            notes=f"Cycle count: {reason}",
            location_id=location_id,
        )

        # Create journal entry
        if variance > 0:
            # Found more than expected (overage)
            je_lines = [
                (inv_account, total_cost, "DR"),
                ("5030", total_cost, "CR"),
            ]
        else:
            # Found less than expected (shortage)
            je_lines = [
                ("5030", total_cost, "DR"),
                (inv_account, total_cost, "CR"),
            ]

        je = self._create_journal_entry(
            description=f"Cycle count adjustment: {reason}",
            lines=je_lines,
            source_type="adjustment",
            user_id=user_id,
        )

        inv_txn.journal_entry_id = je.id

        return inv_txn, je
