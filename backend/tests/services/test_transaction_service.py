r"""
Unit tests for TransactionService

Tests verify:
1. Inventory transactions created with correct type/quantity
2. Journal entries created with correct debits/credits
3. Entries are balanced (DR = CR)
4. InventoryTransaction linked to JournalEntry via FK
5. Inventory quantities updated correctly
6. ScrapRecord created when scrapping

Run with:
    cd backend
    pytest tests/services/test_transaction_service.py -v

Run with coverage:
    pytest tests/services/test_transaction_service.py -v --cov=app/services/transaction_service
"""
import uuid

import pytest
from decimal import Decimal
from datetime import date
from typing import Generator
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.transaction_service import (
    DuplicateShipmentError,
    TransactionService,
    MaterialConsumption,
    ShipmentItem,
    PackagingUsed,
    ReceiptItem,
)
from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.models.inventory import Inventory, InventoryTransaction
from app.models.production_order import ProductionOrder, ScrapRecord
from app.models.product import Product
from app.models.sales_order import SalesOrder


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def db():
    """Create a database session for testing."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def test_finished_good(db: Session) -> Product:
    """Create a test finished good product."""
    product = Product(
        sku=f"TEST-FG-{date.today().isoformat()}-001",
        name="Test Finished Good",
        item_type="finished_good",
        standard_cost=Decimal("10.00"),
        unit="EA",
    )
    db.add(product)
    db.flush()
    yield product
    # Cleanup
    db.rollback()


@pytest.fixture
def test_material(db: Session) -> Generator[Product, None, None]:
    """Create a test raw material."""
    product = Product(
        sku=f"TEST-MAT-{date.today().isoformat()}-001",
        name="Test Material (Filament)",
        item_type="supply",
        is_raw_material=True,
        standard_cost=Decimal("0.02"),
        unit="G",
    )
    db.add(product)
    db.flush()
    yield product
    # Cleanup
    db.rollback()


@pytest.fixture
def test_packaging(db: Session) -> Generator[Product, None, None]:
    """Create a test packaging item."""
    product = Product(
        sku=f"TEST-PKG-{date.today().isoformat()}-001",
        name="Test Box",
        item_type="packaging",
        standard_cost=Decimal("2.50"),
        unit="EA",
    )
    db.add(product)
    db.flush()
    yield product
    # Cleanup
    db.rollback()


@pytest.fixture
def test_material_with_inventory(db: Session) -> Generator[Product, None, None]:
    """Create a test raw material with existing inventory."""
    product = Product(
        sku=f"TEST-MAT-INV-{date.today().isoformat()}-001",
        name="Test Material with Inventory",
        item_type="supply",
        is_raw_material=True,
        standard_cost=Decimal("0.02"),
        unit="G",
    )
    db.add(product)
    db.flush()

    # Create inventory record with starting quantity
    inv = Inventory(
        product_id=product.id,
        location_id=1,  # Default location
        on_hand_quantity=Decimal("1000"),
        allocated_quantity=Decimal("0"),
    )
    db.add(inv)
    db.flush()

    yield product
    # Cleanup
    db.rollback()


@pytest.fixture
def test_production_order(db: Session, test_finished_good: Product) -> Generator[ProductionOrder, None, None]:
    """Create a test production order (needed for ScrapRecord FK)."""
    po = ProductionOrder(
        code=f"PO-TEST-{date.today().isoformat()}-001",
        product_id=test_finished_good.id,
        quantity_ordered=10,
        status="in_progress",
    )
    db.add(po)
    db.flush()
    yield po
    db.rollback()


# ============================================================================
# Helper Method Tests
# ============================================================================

class TestTransactionServiceHelpers:
    """Test internal helper methods"""

    def test_get_account_id_valid(self, db: Session):
        """Should return account ID for valid code"""
        ts = TransactionService(db)
        account_id = ts._get_account_id("1200")  # Raw Materials
        assert isinstance(account_id, int)
        assert account_id > 0

    def test_get_account_id_invalid(self, db: Session):
        """Should raise ValueError for invalid code"""
        ts = TransactionService(db)
        with pytest.raises(ValueError, match="not found"):
            ts._get_account_id("9999")

    def test_get_account_id_caching(self, db: Session):
        """Should cache account lookups"""
        ts = TransactionService(db)
        id1 = ts._get_account_id("1200")
        id2 = ts._get_account_id("1200")
        assert id1 == id2
        assert "1200" in ts._account_cache

    def test_next_entry_number_format(self, db: Session):
        """Should generate JE-YYYY-NNNNNN format"""
        ts = TransactionService(db)
        entry_num = ts._next_entry_number()
        assert entry_num.startswith(f"JE-{date.today().year}-")
        assert len(entry_num) == 14  # JE-2026-000001

    def test_next_entry_number_increments(self, db: Session):
        """Should increment sequence number"""
        ts = TransactionService(db)
        num1 = ts._next_entry_number()

        # Create a JE to consume the number
        je = GLJournalEntry(
            entry_number=num1,
            entry_date=date.today(),
            description="Test entry for sequence test",
            status="posted"
        )
        db.add(je)
        db.flush()

        try:
            num2 = ts._next_entry_number()
            seq1 = int(num1.split("-")[2])
            seq2 = int(num2.split("-")[2])
            assert seq2 == seq1 + 1
        finally:
            # Cleanup
            db.rollback()


# ============================================================================
# Journal Entry Date Tests (#880 PR-2)
# ============================================================================

class TestJournalEntryDate:
    """Test the optional entry_date parameter on create_journal_entry"""

    def test_entry_date_defaults_to_today(self, db: Session):
        """Omitting entry_date should keep the existing today() behavior"""
        ts = TransactionService(db)

        try:
            je = ts.create_journal_entry(
                description="Entry date default test",
                lines=[
                    ("1200", Decimal("10.00"), "DR"),
                    ("2000", Decimal("10.00"), "CR"),
                ],
            )
            db.flush()

            assert je.entry_date == date.today()
        finally:
            db.rollback()

    def test_explicit_entry_date_lands_on_journal_entry(self, db: Session):
        """An explicit (backdated) entry_date should land on the JE"""
        ts = TransactionService(db)
        backdated = date(2026, 4, 15)

        try:
            je = ts.create_journal_entry(
                description="Backdated entry test",
                lines=[
                    ("1200", Decimal("10.00"), "DR"),
                    ("2000", Decimal("10.00"), "CR"),
                ],
                entry_date=backdated,
            )
            db.flush()

            assert je.entry_date == backdated
        finally:
            db.rollback()


# ============================================================================
# Receipt Finished Good Tests
# ============================================================================

class TestReceiptFinishedGood:
    """Test receipt_finished_good method"""

    def test_creates_inventory_transaction(self, db: Session, test_finished_good: Product):
        """Should create RECEIPT inventory transaction"""
        ts = TransactionService(db)

        try:
            assert test_finished_good.id is not None
            inv_txn, je = ts.receipt_finished_good(
                production_order_id=1,
                product_id=test_finished_good.id,
                quantity=Decimal("10"),
                unit_cost=Decimal("5.00"),
            )
            db.flush()

            assert inv_txn.transaction_type == "receipt"
            assert inv_txn.quantity == Decimal("10")
            assert inv_txn.cost_per_unit == Decimal("5.00")
            assert inv_txn.total_cost == Decimal("50.00")
            assert inv_txn.reference_type == "production_order"
            assert inv_txn.reference_id == 1
        finally:
            db.rollback()

    def test_creates_balanced_journal_entry(self, db: Session, test_finished_good: Product):
        """Should create balanced JE: DR FG Inv, CR WIP"""
        ts = TransactionService(db)

        try:
            assert test_finished_good.id is not None
            inv_txn, je = ts.receipt_finished_good(
                production_order_id=1,
                product_id=int(test_finished_good.id),
                quantity=Decimal("10"),
                unit_cost=Decimal("5.00"),
            )
            db.flush()

            assert je.status == "posted"
            assert je.is_balanced
            assert je.total_debits == 50.00
            assert je.total_credits == 50.00

            # Verify line accounts
            lines = sorted(je.lines, key=lambda l: l.line_order)
            assert lines[0].account.account_code == "1220"  # FG Inventory (DR)
            assert lines[0].debit_amount == Decimal("50.00")
            assert lines[1].account.account_code == "1210"  # WIP (CR)
            assert lines[1].credit_amount == Decimal("50.00")
        finally:
            db.rollback()

    def test_links_transaction_to_journal_entry(self, db: Session, test_finished_good: Product):
        """Should link InventoryTransaction to JournalEntry"""
        ts = TransactionService(db)

        try:
            assert test_finished_good.id is not None
            inv_txn, je = ts.receipt_finished_good(
                production_order_id=1,
                product_id=int(test_finished_good.id),
                quantity=Decimal("10"),
                unit_cost=Decimal("5.00"),
            )
            db.flush()

            assert inv_txn.journal_entry_id == je.id
        finally:
            db.rollback()

    def test_updates_inventory_quantity(self, db: Session, test_finished_good: Product):
        """Should increase on_hand_quantity"""
        ts = TransactionService(db)

        try:
            assert test_finished_good.id is not None
            # Get initial quantity
            inv = db.query(Inventory).filter(
                Inventory.product_id == test_finished_good.id
            ).first()
            initial_qty = inv.on_hand_quantity if inv else Decimal("0")

            ts.receipt_finished_good(
                production_order_id=1,
                product_id=test_finished_good.id,
                quantity=Decimal("10"),
                unit_cost=Decimal("5.00"),
            )
            db.flush()

            inv = db.query(Inventory).filter(
                Inventory.product_id == test_finished_good.id
            ).first()
            assert inv is not None
            assert inv.on_hand_quantity == initial_qty + Decimal("10")
        finally:
            db.rollback()


# ============================================================================
# Issue Materials for Operation Tests
# ============================================================================

class TestIssueMaterialsForOperation:
    """Test issue_materials_for_operation method"""

    def test_creates_consumption_transactions(self, db: Session, test_material_with_inventory: Product):
        """Should create CONSUMPTION transactions for each material"""
        ts = TransactionService(db)

        try:
            materials = [
                MaterialConsumption(
                    product_id=test_material_with_inventory.id,
                    quantity=Decimal("100"),
                    unit_cost=Decimal("0.02"),
                    unit="G"
                )
            ]

            inv_txns, je = ts.issue_materials_for_operation(
                production_order_id=1,
                operation_sequence=1,
                materials=materials,
            )
            db.flush()

            assert len(inv_txns) == 1
            assert inv_txns[0].transaction_type == "consumption"
            assert inv_txns[0].quantity == Decimal("-100")  # Negative for issue
            assert inv_txns[0].total_cost == Decimal("2.00")
        finally:
            db.rollback()

    def test_creates_balanced_journal_entry(self, db: Session, test_material_with_inventory: Product):
        """Should create balanced JE: DR WIP, CR Raw Materials"""
        ts = TransactionService(db)

        try:
            materials = [
                MaterialConsumption(
                    product_id=test_material_with_inventory.id,
                    quantity=Decimal("100"),
                    unit_cost=Decimal("0.02"),
                    unit="G"
                )
            ]

            inv_txns, je = ts.issue_materials_for_operation(
                production_order_id=1,
                operation_sequence=1,
                materials=materials,
            )
            db.flush()

            assert je.is_balanced

            # Find DR and CR lines
            dr_line = next(l for l in je.lines if l.debit_amount > 0)
            cr_line = next(l for l in je.lines if l.credit_amount > 0)

            assert dr_line.account.account_code == "1210"  # WIP
            assert cr_line.account.account_code == "1200"  # Raw Materials
        finally:
            db.rollback()

    def test_links_all_transactions_to_journal_entry(self, db: Session, test_material_with_inventory: Product):
        """Should link all inventory transactions to the journal entry"""
        ts = TransactionService(db)

        try:
            materials = [
                MaterialConsumption(
                    product_id=test_material_with_inventory.id,
                    quantity=Decimal("100"),
                    unit_cost=Decimal("0.02"),
                    unit="G"
                )
            ]

            inv_txns, je = ts.issue_materials_for_operation(
                production_order_id=1,
                operation_sequence=1,
                materials=materials,
            )
            db.flush()

            for inv_txn in inv_txns:
                assert inv_txn.journal_entry_id == je.id
        finally:
            db.rollback()


# ============================================================================
# Scrap Materials Tests
# ============================================================================

class TestScrapMaterials:
    """Test scrap_materials method"""

    def test_creates_scrap_transaction(self, db: Session, test_production_order: ProductionOrder, test_finished_good: Product):
        """Should create SCRAP inventory transaction"""
        ts = TransactionService(db)

        try:
            inv_txn, je, scrap = ts.scrap_materials(
                production_order_id=test_production_order.id,
                operation_sequence=3,
                product_id=test_finished_good.id,
                quantity=Decimal("2"),
                unit_cost=Decimal("10.00"),
                reason_code="QC_FAIL",
            )
            db.flush()

            assert inv_txn.transaction_type == "scrap"
            assert inv_txn.quantity == Decimal("-2")
        finally:
            db.rollback()

    def test_creates_scrap_record(self, db: Session, test_production_order: ProductionOrder, test_finished_good: Product):
        """Should create ScrapRecord with cost tracking"""
        ts = TransactionService(db)

        try:
            inv_txn, je, scrap = ts.scrap_materials(
                production_order_id=test_production_order.id,
                operation_sequence=3,
                product_id=test_finished_good.id,
                quantity=Decimal("2"),
                unit_cost=Decimal("10.00"),
                reason_code="QC_FAIL",
                notes="Failed dimensional check",
            )
            db.flush()

            assert scrap.quantity == Decimal("2")
            assert scrap.unit_cost == Decimal("10.00")
            assert scrap.total_cost == Decimal("20.00")
            assert scrap.scrap_reason_code == "QC_FAIL"
            assert scrap.notes == "Failed dimensional check"
            assert scrap.inventory_transaction_id == inv_txn.id
            assert scrap.journal_entry_id == je.id
        finally:
            db.rollback()

    def test_creates_balanced_journal_entry(self, db: Session, test_production_order: ProductionOrder, test_finished_good: Product):
        """Should create balanced JE: DR Scrap Expense, CR WIP"""
        ts = TransactionService(db)

        try:
            inv_txn, je, scrap = ts.scrap_materials(
                production_order_id=test_production_order.id,
                operation_sequence=3,
                product_id=test_finished_good.id,
                quantity=Decimal("2"),
                unit_cost=Decimal("10.00"),
                reason_code="QC_FAIL",
            )
            db.flush()

            assert je.is_balanced

            dr_line = next(l for l in je.lines if l.debit_amount > 0)
            cr_line = next(l for l in je.lines if l.credit_amount > 0)

            assert dr_line.account.account_code == "5020"  # Scrap Expense
            assert cr_line.account.account_code == "1210"  # WIP
        finally:
            db.rollback()


class TestScrapFinishedGoods:
    """Test scrap_finished_goods method (units already on hand)."""

    def test_decrements_onhand_and_posts_fg_gl(self, db: Session, test_production_order: ProductionOrder, test_finished_good: Product):
        """Should decrement on_hand and post DR Scrap Expense / CR FG Inventory."""
        ts = TransactionService(db)
        try:
            inv = Inventory(
                product_id=test_finished_good.id,
                location_id=1,
                on_hand_quantity=Decimal("10"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv)
            db.flush()

            inv_txn, je, scrap = ts.scrap_finished_goods(
                production_order_id=test_production_order.id,
                product_id=test_finished_good.id,
                quantity=Decimal("2"),
                unit_cost=Decimal("10.00"),
                reason_code="QC_FAIL",
                notes="Failed final inspection",
            )
            db.flush()

            # Inventory: SCRAP removal through the canonical ledger (on_hand 10 -> 8)
            assert inv_txn.transaction_type == "scrap"
            assert inv_txn.quantity == Decimal("-2")
            db.refresh(inv)
            assert inv.on_hand_quantity == Decimal("8")

            # Accounting: balanced DR Scrap Expense (5020) / CR FG Inventory (1220)
            assert je is not None and je.is_balanced
            dr_line = next(l for l in je.lines if l.debit_amount > 0)
            cr_line = next(l for l in je.lines if l.credit_amount > 0)
            assert dr_line.account.account_code == "5020"
            assert cr_line.account.account_code == "1220"

            # ScrapRecord links both the inventory txn and the journal entry
            assert scrap.total_cost == Decimal("20.00")
            assert scrap.inventory_transaction_id == inv_txn.id
            assert scrap.journal_entry_id == je.id
        finally:
            db.rollback()

    def test_raises_when_quantity_exceeds_onhand(self, db: Session, test_production_order: ProductionOrder, test_finished_good: Product):
        """Should raise ValueError when scrap qty would drive on_hand negative."""
        ts = TransactionService(db)
        try:
            inv = Inventory(
                product_id=test_finished_good.id,
                location_id=1,
                on_hand_quantity=Decimal("1"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv)
            db.flush()

            with pytest.raises(ValueError, match="only 1"):
                ts.scrap_finished_goods(
                    production_order_id=test_production_order.id,
                    product_id=test_finished_good.id,
                    quantity=Decimal("5"),
                    unit_cost=Decimal("10.00"),
                    reason_code="QC_FAIL",
                )
        finally:
            db.rollback()

    @pytest.mark.parametrize("bad_qty", [Decimal("0"), Decimal("-1")])
    def test_rejects_non_positive_quantity(self, db: Session, test_production_order: ProductionOrder, test_finished_good: Product, bad_qty):
        """Should raise ValueError for zero AND negative scrap quantity (boundary guard)."""
        ts = TransactionService(db)
        try:
            with pytest.raises(ValueError, match="quantity must be positive"):
                ts.scrap_finished_goods(
                    production_order_id=test_production_order.id,
                    product_id=test_finished_good.id,
                    quantity=bad_qty,
                    unit_cost=Decimal("10.00"),
                    reason_code="QC_FAIL",
                )
        finally:
            db.rollback()

    def test_rejects_negative_unit_cost(self, db: Session, test_production_order: ProductionOrder, test_finished_good: Product):
        """Should raise ValueError for negative unit_cost (would post a backwards GL entry)."""
        ts = TransactionService(db)
        try:
            with pytest.raises(ValueError, match="unit_cost must be non-negative"):
                ts.scrap_finished_goods(
                    production_order_id=test_production_order.id,
                    product_id=test_finished_good.id,
                    quantity=Decimal("1"),
                    unit_cost=Decimal("-5.00"),
                    reason_code="QC_FAIL",
                )
        finally:
            db.rollback()


# ============================================================================
# Ship Order Tests
# ============================================================================

class TestShipOrder:
    """Test ship_order method"""

    def test_creates_shipment_transactions(self, db: Session, test_finished_good: Product):
        """Should create SHIPMENT transaction for FG"""
        ts = TransactionService(db)

        try:
            # First, create some inventory
            inv = Inventory(
                product_id=test_finished_good.id,
                location_id=1,
                on_hand_quantity=Decimal("100"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv)
            db.flush()

            items = [ShipmentItem(
                product_id=test_finished_good.id,
                quantity=Decimal("5"),
                unit_cost=Decimal("20.00"),
            )]

            inv_txns, je = ts.ship_order(
                sales_order_id=1,
                items=items,
            )
            db.flush()

            assert len(inv_txns) == 1
            assert inv_txns[0].transaction_type == "shipment"
            assert inv_txns[0].quantity == Decimal("-5")
        finally:
            db.rollback()

    def test_creates_cogs_journal_entry(self, db: Session, test_finished_good: Product):
        """Should create JE: DR COGS, CR FG Inventory"""
        ts = TransactionService(db)

        try:
            # Create inventory
            inv = Inventory(
                product_id=test_finished_good.id,
                location_id=1,
                on_hand_quantity=Decimal("100"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv)
            db.flush()

            items = [ShipmentItem(
                product_id=test_finished_good.id,
                quantity=Decimal("5"),
                unit_cost=Decimal("20.00"),
            )]

            inv_txns, je = ts.ship_order(
                sales_order_id=1,
                items=items,
            )
            db.flush()

            assert je.is_balanced
            assert je.total_debits == 100.00

            dr_line = next(l for l in je.lines if l.debit_amount > 0)
            cr_line = next(l for l in je.lines if l.credit_amount > 0)

            assert dr_line.account.account_code == "5000"  # COGS
            assert cr_line.account.account_code == "1220"  # FG Inventory
        finally:
            db.rollback()

    def test_handles_packaging(self, db: Session, test_finished_good: Product, test_packaging: Product):
        """Should handle FG + packaging in one journal entry"""
        ts = TransactionService(db)

        try:
            # Create inventory for both
            inv_fg = Inventory(
                product_id=test_finished_good.id,
                location_id=1,
                on_hand_quantity=Decimal("100"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv_fg)

            inv_pkg = Inventory(
                product_id=test_packaging.id,
                location_id=1,
                on_hand_quantity=Decimal("100"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv_pkg)
            db.flush()

            items = [ShipmentItem(
                product_id=test_finished_good.id,
                quantity=Decimal("5"),
                unit_cost=Decimal("20.00"),
            )]
            packaging = [PackagingUsed(
                product_id=test_packaging.id,
                quantity=1,
                unit_cost=Decimal("2.50"),
            )]
            inv_txns, je = ts.ship_order(
                sales_order_id=1,
                items=items,
                packaging=packaging,
            )
            db.flush()

            assert len(inv_txns) == 2  # FG + packaging
            assert je.is_balanced
            assert je.total_debits == 102.50  # 100 FG + 2.50 packaging
        finally:
            db.rollback()

    def _make_sales_order(self, db: Session, status: str = "ready_to_ship") -> SalesOrder:
        """Create a SalesOrder row (guard + description tests need a real SO)."""
        uid = uuid.uuid4().hex[:8]
        so = SalesOrder(
            order_number=f"SO-TEST-{uid}",
            user_id=1,
            product_name=f"Test Product {uid}",
            quantity=5,
            material_type="PLA",
            unit_price=Decimal("20.00"),
            total_price=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            status=status,
        )
        db.add(so)
        db.flush()
        return so

    def test_je_description_uses_order_number(self, db: Session, test_finished_good: Product):
        """JE description should use the order_number format shared with the
        fulfillment path, not the numeric sales order id (#880)"""
        ts = TransactionService(db)

        try:
            so = self._make_sales_order(db)
            inv = Inventory(
                product_id=test_finished_good.id,
                location_id=1,
                on_hand_quantity=Decimal("100"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv)
            db.flush()

            items = [ShipmentItem(
                product_id=test_finished_good.id,
                quantity=Decimal("5"),
                unit_cost=Decimal("20.00"),
            )]

            inv_txns, je = ts.ship_order(
                sales_order_id=so.id,
                items=items,
            )
            db.flush()

            assert je.description == f"Shipment for SO#{so.order_number}"
        finally:
            db.rollback()

    def test_second_ship_raises_and_posts_no_inventory(self, db: Session, test_finished_good: Product):
        """Retrying ship_order for an already-shipped SO must raise
        DuplicateShipmentError BEFORE posting any inventory transaction (#880)"""
        ts = TransactionService(db)

        try:
            so = self._make_sales_order(db)
            inv = Inventory(
                product_id=test_finished_good.id,
                location_id=1,
                on_hand_quantity=Decimal("100"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv)
            db.flush()

            items = [ShipmentItem(
                product_id=test_finished_good.id,
                quantity=Decimal("5"),
                unit_cost=Decimal("20.00"),
            )]

            # First ship posts inventory + JE
            inv_txns, je = ts.ship_order(sales_order_id=so.id, items=items)
            db.flush()
            assert je is not None

            def txn_count() -> int:
                return db.query(InventoryTransaction).filter(
                    InventoryTransaction.reference_type == "sales_order",
                    InventoryTransaction.reference_id == so.id,
                ).count()

            count_before = txn_count()
            on_hand_before = db.query(Inventory).filter(
                Inventory.product_id == test_finished_good.id
            ).first().on_hand_quantity

            # Retry raises and posts ZERO new inventory transactions
            with pytest.raises(DuplicateShipmentError, match="already has a shipment"):
                ts.ship_order(sales_order_id=so.id, items=items)
            db.flush()

            assert txn_count() == count_before
            on_hand_after = db.query(Inventory).filter(
                Inventory.product_id == test_finished_good.id
            ).first().on_hand_quantity
            assert on_hand_after == on_hand_before
        finally:
            db.rollback()

    def test_voided_shipment_je_does_not_block_reship(self, db: Session, test_finished_good: Product):
        """A voided shipment JE is a correction artifact — it must not trip
        the duplicate-shipment guard (#880)"""
        ts = TransactionService(db)

        try:
            so = self._make_sales_order(db)
            inv = Inventory(
                product_id=test_finished_good.id,
                location_id=1,
                on_hand_quantity=Decimal("100"),
                allocated_quantity=Decimal("0"),
            )
            db.add(inv)
            db.flush()

            voided_je = GLJournalEntry(
                entry_number=f"JE-TEST-{uuid.uuid4().hex[:8]}",
                entry_date=date.today(),
                description=f"Shipment for SO#{so.order_number}",
                source_type="sales_order",
                source_id=so.id,
                status="voided",
            )
            db.add(voided_je)
            db.flush()

            items = [ShipmentItem(
                product_id=test_finished_good.id,
                quantity=Decimal("5"),
                unit_cost=Decimal("20.00"),
            )]

            inv_txns, je = ts.ship_order(sales_order_id=so.id, items=items)
            db.flush()

            assert je is not None
            assert je.id != voided_je.id
        finally:
            db.rollback()


# ============================================================================
# Receive Purchase Order Tests
# ============================================================================

class TestReceivePurchaseOrder:
    """Test receive_purchase_order method"""

    def test_creates_receipt_transactions(self, db: Session, test_material: Product):
        """Should create RECEIPT transactions"""
        ts = TransactionService(db)

        try:
            items = [ReceiptItem(
                product_id=test_material.id,
                quantity=Decimal("1000"),
                unit_cost=Decimal("0.02"),
                unit="G",
                lot_number="LOT-2026-001",
            )]

            inv_txns, je = ts.receive_purchase_order(
                purchase_order_id=1,
                items=items,
            )
            db.flush()

            assert len(inv_txns) == 1
            assert inv_txns[0].transaction_type == "receipt"
            assert inv_txns[0].quantity == Decimal("1000")
            assert inv_txns[0].lot_number == "LOT-2026-001"
        finally:
            db.rollback()

    def test_creates_ap_journal_entry(self, db: Session, test_material: Product):
        """Should create JE: DR Raw Materials, CR AP"""
        ts = TransactionService(db)

        try:
            items = [ReceiptItem(
                product_id=test_material.id,
                quantity=Decimal("1000"),
                unit_cost=Decimal("0.02"),
                unit="G",
            )]

            inv_txns, je = ts.receive_purchase_order(
                purchase_order_id=1,
                items=items,
            )
            db.flush()

            assert je.is_balanced

            dr_line = next(l for l in je.lines if l.debit_amount > 0)
            cr_line = next(l for l in je.lines if l.credit_amount > 0)

            assert dr_line.account.account_code == "1200"  # Raw Materials
            assert cr_line.account.account_code == "2000"  # AP
        finally:
            db.rollback()

    def test_updates_inventory_quantity(self, db: Session, test_material: Product):
        """Should increase on_hand_quantity"""
        ts = TransactionService(db)

        try:
            items = [ReceiptItem(
                product_id=test_material.id,
                quantity=Decimal("1000"),
                unit_cost=Decimal("0.02"),
                unit="G",
            )]

            ts.receive_purchase_order(
                purchase_order_id=1,
                items=items,
            )
            db.flush()

            inv = db.query(Inventory).filter(
                Inventory.product_id == test_material.id
            ).first()
            assert inv is not None
            assert inv.on_hand_quantity == Decimal("1000")
        finally:
            db.rollback()

    def test_packaging_receipt_debits_1230(self, db: Session, test_packaging: Product):
        """Packaging PO receipt should debit Packaging Inventory (1230), not
        Raw Materials — otherwise 1230 goes negative at ship (#880)"""
        ts = TransactionService(db)

        try:
            items = [ReceiptItem(
                product_id=test_packaging.id,
                quantity=Decimal("100"),
                unit_cost=Decimal("2.50"),
            )]

            inv_txns, je = ts.receive_purchase_order(
                purchase_order_id=1,
                items=items,
            )
            db.flush()

            assert je.is_balanced

            dr_line = next(line for line in je.lines if line.debit_amount > 0)
            cr_line = next(line for line in je.lines if line.credit_amount > 0)

            assert dr_line.account.account_code == "1230"  # Packaging Inventory
            assert dr_line.debit_amount == Decimal("250.00")
            assert cr_line.account.account_code == "2000"  # AP
        finally:
            db.rollback()

    def test_finished_good_receipt_debits_1220(self, db: Session, test_finished_good: Product):
        """Purchased finished-good receipt should debit FG Inventory (1220)"""
        ts = TransactionService(db)

        try:
            items = [ReceiptItem(
                product_id=test_finished_good.id,
                quantity=Decimal("10"),
                unit_cost=Decimal("10.00"),
            )]

            inv_txns, je = ts.receive_purchase_order(
                purchase_order_id=1,
                items=items,
            )
            db.flush()

            assert je.is_balanced

            dr_line = next(line for line in je.lines if line.debit_amount > 0)
            cr_line = next(line for line in je.lines if line.credit_amount > 0)

            assert dr_line.account.account_code == "1220"  # FG Inventory
            assert cr_line.account.account_code == "2000"  # AP
        finally:
            db.rollback()

    def test_mixed_po_receipt_multi_line_je_balances(
        self,
        db: Session,
        test_material: Product,
        test_packaging: Product,
        test_finished_good: Product,
    ):
        """Mixed PO produces ONE JE with a DR line per inventory account and
        a single CR 2000 for the total"""
        ts = TransactionService(db)

        try:
            items = [
                ReceiptItem(
                    product_id=test_material.id,
                    quantity=Decimal("1000"),
                    unit_cost=Decimal("0.02"),
                    unit="G",
                ),
                ReceiptItem(
                    product_id=test_packaging.id,
                    quantity=Decimal("10"),
                    unit_cost=Decimal("2.50"),
                ),
                ReceiptItem(
                    product_id=test_finished_good.id,
                    quantity=Decimal("5"),
                    unit_cost=Decimal("10.00"),
                ),
            ]

            inv_txns, je = ts.receive_purchase_order(
                purchase_order_id=1,
                items=items,
            )
            db.flush()

            assert je.is_balanced

            dr_by_account = {
                line.account.account_code: line.debit_amount
                for line in je.lines if line.debit_amount > 0
            }
            cr_lines = [line for line in je.lines if line.credit_amount > 0]

            assert dr_by_account == {
                "1200": Decimal("20.00"),   # 1000g @ 0.02
                "1230": Decimal("25.00"),   # 10 @ 2.50
                "1220": Decimal("50.00"),   # 5 @ 10.00
            }
            assert len(cr_lines) == 1
            assert cr_lines[0].account.account_code == "2000"
            assert cr_lines[0].credit_amount == Decimal("95.00")
        finally:
            db.rollback()


# ============================================================================
# Cycle Count Adjustment Tests
# ============================================================================

class TestCycleCountAdjustment:
    """Test cycle_count_adjustment method"""

    def test_shortage_adjustment(self, db: Session, test_material_with_inventory: Product):
        """Should handle shortage: DR Adjustment, CR Inventory"""
        ts = TransactionService(db)

        try:
            inv_txn, je = ts.cycle_count_adjustment(
                product_id=test_material_with_inventory.id,
                expected_qty=Decimal("100"),
                actual_qty=Decimal("95"),  # 5 short
                reason="Cycle count variance",
            )
            db.flush()

            assert inv_txn.transaction_type == "adjustment"
            assert inv_txn.quantity == Decimal("-5")

            dr_line = next(l for l in je.lines if l.debit_amount > 0)
            assert dr_line.account.account_code == "5030"  # Adjustment expense
        finally:
            db.rollback()

    def test_overage_adjustment(self, db: Session, test_material_with_inventory: Product):
        """Should handle overage: DR Inventory, CR Adjustment"""
        ts = TransactionService(db)

        try:
            inv_txn, je = ts.cycle_count_adjustment(
                product_id=test_material_with_inventory.id,
                expected_qty=Decimal("100"),
                actual_qty=Decimal("105"),  # 5 over
                reason="Found extra stock",
            )
            db.flush()

            assert inv_txn.quantity == Decimal("5")

            cr_line = next(l for l in je.lines if l.credit_amount > 0)
            assert cr_line.account.account_code == "5030"  # Adjustment expense
        finally:
            db.rollback()

    def test_zero_variance_raises(self, db: Session, test_material_with_inventory: Product):
        """Should raise error for zero variance"""
        ts = TransactionService(db)

        with pytest.raises(ValueError, match="No variance"):
            ts.cycle_count_adjustment(
                product_id=test_material_with_inventory.id,
                expected_qty=Decimal("100"),
                actual_qty=Decimal("100"),
                reason="No change",
            )

    def test_all_entries_balanced(self, db: Session, test_material_with_inventory: Product):
        """All journal entries should be balanced"""
        ts = TransactionService(db)

        try:
            inv_txn, je = ts.cycle_count_adjustment(
                product_id=test_material_with_inventory.id,
                expected_qty=Decimal("100"),
                actual_qty=Decimal("90"),
                reason="Test variance",
            )
            db.flush()

            assert je.is_balanced
            assert je.total_debits == je.total_credits
        finally:
            db.rollback()


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests verifying full transaction flows"""

    def test_full_production_cycle(self, db: Session):
        """Test complete production cycle: receive materials -> produce -> ship"""
        ts = TransactionService(db)

        try:
            # Create products
            material = Product(
                sku=f"INT-MAT-{date.today().isoformat()}",
                name="Integration Test Material",
                item_type="supply",
                is_raw_material=True,
                standard_cost=Decimal("0.02"),
                unit="G",
            )
            db.add(material)

            finished_good = Product(
                sku=f"INT-FG-{date.today().isoformat()}",
                name="Integration Test FG",
                item_type="finished_good",
                standard_cost=Decimal("5.00"),
                unit="EA",
            )
            db.add(finished_good)
            db.flush()

            # Step 1: Receive raw materials (PO receipt)
            po_items = [ReceiptItem(
                product_id=material.id,
                quantity=Decimal("1000"),
                unit_cost=Decimal("0.02"),
                unit="G",
            )]
            po_txns, po_je = ts.receive_purchase_order(
                purchase_order_id=99,
                items=po_items,
            )
            db.flush()
            assert po_je.is_balanced, "PO receipt JE should be balanced"

            # Step 2: Issue materials for production
            materials = [MaterialConsumption(
                product_id=material.id,
                quantity=Decimal("500"),
                unit_cost=Decimal("0.02"),
                unit="G",
            )]
            issue_txns, issue_je = ts.issue_materials_for_operation(
                production_order_id=99,
                operation_sequence=1,
                materials=materials,
            )
            db.flush()
            assert issue_je.is_balanced, "Material issue JE should be balanced"

            # Step 3: Receipt finished goods
            fg_txn, fg_je = ts.receipt_finished_good(
                production_order_id=99,
                product_id=finished_good.id,
                quantity=Decimal("10"),
                unit_cost=Decimal("1.00"),  # 500g @ $0.02 = $10 / 10 units = $1/unit
            )
            db.flush()
            assert fg_je.is_balanced, "FG receipt JE should be balanced"

            # Step 4: Ship to customer
            ship_items = [ShipmentItem(
                product_id=finished_good.id,
                quantity=Decimal("5"),
                unit_cost=Decimal("1.00"),
            )]
            ship_txns, ship_je = ts.ship_order(
                sales_order_id=99,
                items=ship_items,
            )
            db.flush()
            assert ship_je.is_balanced, "Shipment JE should be balanced"

            # Verify inventory quantities
            mat_inv = db.query(Inventory).filter(
                Inventory.product_id == material.id
            ).first()
            assert mat_inv.on_hand_quantity == Decimal("500"), "Material should have 1000-500=500 remaining"

            fg_inv = db.query(Inventory).filter(
                Inventory.product_id == finished_good.id
            ).first()
            assert fg_inv.on_hand_quantity == Decimal("5"), "FG should have 10-5=5 remaining"

        finally:
            db.rollback()


# ============================================================================
# Smoke Test
# ============================================================================

def test_smoke_transaction_service(db: Session):
    """Quick smoke test to verify TransactionService can be instantiated."""
    ts = TransactionService(db)
    assert ts is not None
    assert ts.db == db
    assert ts._account_cache == {}
    print("\n  TransactionService smoke test passed!")


if __name__ == "__main__":
    # Run quick smoke test
    db = SessionLocal()
    try:
        test_smoke_transaction_service(db)
    finally:
        db.close()
