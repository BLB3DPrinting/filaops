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
from app.models.inventory import Inventory, InventoryTransaction
from app.models.production_order import ScrapRecord
from app.models.product import Product

_JOURNAL_ENTRY_NUMBER_LOCK_NAMESPACE = 74002


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
    ) -> GLJournalEntry:
        """Create a balanced posted journal entry for service-level callers."""
        return self._create_journal_entry(
            description=description,
            lines=lines,
            source_type=source_type,
            source_id=source_id,
            user_id=user_id,
        )

    def _create_journal_entry(
        self,
        description: str,
        lines: List[Tuple[str, Decimal, str]],  # (account_code, amount, 'DR'|'CR')
        source_type: str = None,
        source_id: int = None,
        user_id: int = None,
    ) -> GLJournalEntry:
        """
        Create balanced journal entry with lines.

        Args:
            description: Entry description/memo
            lines: List of (account_code, amount, 'DR'|'CR') tuples
            source_type: 'production_order', 'sales_order', 'purchase_order', etc.
            source_id: ID of source document
            user_id: Creating user ID

        Returns:
            GLJournalEntry with lines attached

        Raises:
            ValueError: If entry doesn't balance
        """
        je = GLJournalEntry(
            entry_number=self._next_entry_number(),
            entry_date=date.today(),
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

    def _update_inventory_quantity(
        self,
        product_id: int,
        quantity_delta: Decimal,
        location_id: int = None,
    ) -> None:
        """
        Update inventory on-hand quantity.

        Args:
            product_id: Product to update
            quantity_delta: Positive to add, negative to subtract
            location_id: Specific location (uses default if None)
        """
        # Get or create inventory record
        # Default location_id = 1 (main warehouse) if not specified
        loc_id = location_id or 1

        inv = self.db.query(Inventory).filter(
            Inventory.product_id == product_id,
            Inventory.location_id == loc_id
        ).first()

        if inv:
            inv.on_hand_quantity = (inv.on_hand_quantity or 0) + quantity_delta
        else:
            # Create new inventory record
            inv = Inventory(
                product_id=product_id,
                location_id=loc_id,
                on_hand_quantity=quantity_delta,
                allocated_quantity=0,
            )
            self.db.add(inv)

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
        """Create inventory transaction record"""
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
            # Create inventory transaction (negative quantity = issue)
            inv_txn = self._create_inventory_transaction(
                product_id=mat.product_id,
                transaction_type="consumption",
                quantity=-mat.quantity,  # Negative = issue
                unit_cost=mat.unit_cost,
                reference_type="production_order",
                reference_id=production_order_id,
                notes=f"Material issue for operation {operation_sequence}",
                unit=mat.unit,
            )
            inv_txns.append(inv_txn)

            # Update inventory quantity
            self._update_inventory_quantity(mat.product_id, -mat.quantity)

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

        # Create inventory transaction
        inv_txn = self._create_inventory_transaction(
            product_id=product_id,
            transaction_type="receipt",
            quantity=quantity,  # Positive = receipt
            unit_cost=unit_cost,
            reference_type="production_order",
            reference_id=production_order_id,
            lot_number=lot_number,
            notes="FG receipt from production",
        )

        # Update inventory quantity
        self._update_inventory_quantity(product_id, quantity)

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
        """
        inv_txns = []
        je_lines = []

        # Process FG items
        fg_total = Decimal("0")
        for item in items:
            cost = item.quantity * item.unit_cost
            fg_total += cost

            inv_txn = self._create_inventory_transaction(
                product_id=item.product_id,
                transaction_type="shipment",
                quantity=-item.quantity,  # Negative = ship out
                unit_cost=item.unit_cost,
                reference_type="sales_order",
                reference_id=sales_order_id,
                notes="Shipped to customer",
            )
            inv_txns.append(inv_txn)

            self._update_inventory_quantity(item.product_id, -item.quantity)

        je_lines.append(("5000", fg_total, "DR"))   # COGS
        je_lines.append(("1220", fg_total, "CR"))   # FG Inventory

        # Process packaging
        pkg_total = Decimal("0")
        if packaging:
            for pkg in packaging:
                cost = Decimal(pkg.quantity) * pkg.unit_cost
                pkg_total += cost

                inv_txn = self._create_inventory_transaction(
                    product_id=pkg.product_id,
                    transaction_type="consumption",
                    quantity=-pkg.quantity,
                    unit_cost=pkg.unit_cost,
                    reference_type="sales_order",
                    reference_id=sales_order_id,
                    notes="Packaging for shipment",
                )
                inv_txns.append(inv_txn)

                self._update_inventory_quantity(pkg.product_id, -pkg.quantity)

        if pkg_total > 0:
            je_lines.append(("5010", pkg_total, "DR"))   # Shipping Supplies
            je_lines.append(("1230", pkg_total, "CR"))   # Packaging Inventory

        # Create journal entry (skip if all amounts are zero)
        je = None
        total_amount = fg_total + pkg_total
        if total_amount > 0:
            je = self._create_journal_entry(
                description=f"Shipment for SO#{sales_order_id}",
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
        Accounting: DR Raw Materials (1200), CR Accounts Payable (2000)

        Returns:
            Tuple of (list of inventory transactions, journal entry)
        """
        inv_txns = []
        total_cost = Decimal("0")

        for item in items:
            cost = item.quantity * item.unit_cost
            total_cost += cost

            inv_txn = self._create_inventory_transaction(
                product_id=item.product_id,
                transaction_type="receipt",
                quantity=item.quantity,
                unit_cost=item.unit_cost,
                reference_type="purchase_order",
                reference_id=purchase_order_id,
                lot_number=item.lot_number,
                notes="PO receipt",
                unit=item.unit,
            )
            inv_txns.append(inv_txn)

            self._update_inventory_quantity(item.product_id, item.quantity)

        # Create journal entry: DR Raw Materials, CR AP
        je = self._create_journal_entry(
            description=f"PO#{purchase_order_id} receipt",
            lines=[
                ("1200", total_cost, "DR"),  # Raw Materials
                ("2000", total_cost, "CR"),  # Accounts Payable
            ],
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

        # Create inventory transaction
        inv_txn = self._create_inventory_transaction(
            product_id=product_id,
            transaction_type="adjustment",
            quantity=variance,
            unit_cost=unit_cost,
            notes=f"Cycle count: {reason}",
            location_id=location_id,
        )

        # Update inventory
        self._update_inventory_quantity(product_id, variance, location_id)

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
