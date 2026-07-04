"""
Integration Tests for Transaction Flows

Tests the complete production paths with GL journal entry verification:
1. Make-to-Order (MTO): PO receive → reserve → complete_print → pass_qc → ship
2. Make-to-Stock (MTS): PO receive → reserve → complete_print → pass_qc (FG sits)
3. Ship-from-Stock (SFS): Existing FG → ship_from_stock
4. Scrap path: complete_print → fail_qc → scrap

Each test verifies:
- Inventory quantities are correct
- GL journal entries are created
- Journal entries balance (DR = CR)
- InventoryTransactions link to JournalEntries
"""
import pytest
import uuid
from decimal import Decimal
from datetime import date, timezone
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine
from app.models.inventory import Inventory, InventoryTransaction
from app.models.product import Product
from app.models.production_order import ProductionOrder, ScrapRecord
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.sales_order import SalesOrder
from app.models.bom import BOM, BOMLine
from app.services.transaction_service import (
    TransactionService,
    MaterialConsumption,
    ReceiptItem,
    ShipmentItem,
    PackagingUsed,
)


# =============================================================================
# FIXTURES
# =============================================================================

def _unique_so_id() -> int:
    """Unique fake sales-order id for ship_order calls.

    These tests commit, and the #880 duplicate-shipment guard checks
    committed shipment JEs by source_id — so reruns against a non-fresh
    database must not reuse hardcoded ids.
    """
    return uuid.uuid4().int % 1_000_000_000 + 1_000_000


@pytest.fixture
def db():
    """Create a database session for testing."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def gl_accounts(db: Session):
    """Ensure all required GL accounts exist"""
    accounts = [
        ("1200", "Raw Materials Inventory", "asset"),
        ("1210", "WIP Inventory", "asset"),
        ("1220", "Finished Goods Inventory", "asset"),
        ("1230", "Packaging Inventory", "asset"),
        ("2000", "Accounts Payable", "liability"),
        ("5000", "Cost of Goods Sold", "expense"),
        ("5010", "Shipping Expense", "expense"),
        ("5020", "Scrap Expense", "expense"),
        ("5030", "Inventory Adjustment", "expense"),
    ]
    for code, acct_name, acct_type in accounts:
        existing = db.query(GLAccount).filter(GLAccount.account_code == code).first()
        if not existing:
            db.add(GLAccount(account_code=code, name=acct_name, account_type=acct_type, active=True))
    db.flush()
    yield {code: db.query(GLAccount).filter(GLAccount.account_code == code).first() for code, _, _ in accounts}
    db.rollback()


@pytest.fixture
def test_material(db: Session):
    """Create a raw material product"""
    uid = str(uuid.uuid4())[:8]
    product = Product(
        sku=f"TEST-MAT-{uid}",
        name="Test Filament",
        item_type="supply",
        is_raw_material=True,
        unit="G",
        standard_cost=Decimal("0.02"),  # $0.02/gram
    )
    db.add(product)
    db.flush()
    yield product
    db.rollback()


@pytest.fixture
def test_finished_good(db: Session):
    """Create a finished good product"""
    uid = str(uuid.uuid4())[:8]
    product = Product(
        sku=f"TEST-FG-{uid}",
        name="Test Widget",
        item_type="finished_good",
        unit="EA",
        standard_cost=Decimal("15.00"),
    )
    db.add(product)
    db.flush()
    yield product
    db.rollback()


@pytest.fixture
def test_packaging(db: Session):
    """Create a packaging product"""
    uid = str(uuid.uuid4())[:8]
    product = Product(
        sku=f"TEST-PKG-{uid}",
        name="Shipping Box",
        item_type="packaging",
        unit="EA",
        standard_cost=Decimal("2.50"),
    )
    db.add(product)
    db.flush()
    yield product
    db.rollback()


@pytest.fixture
def test_production_order(db: Session, test_finished_good):
    """Create a test production order for scrap tests"""
    po = ProductionOrder(
        code=f"PO-TEST-{uuid.uuid4().hex[:8]}",
        product_id=test_finished_good.id,
        quantity_ordered=Decimal("10"),
        status="in_progress",
    )
    db.add(po)
    db.flush()
    yield po
    db.rollback()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_account_balance(db: Session, account_code: str) -> Decimal:
    """Calculate current balance for a GL account from all journal entries"""
    account = db.query(GLAccount).filter(GLAccount.account_code == account_code).first()
    if not account:
        return Decimal("0")

    lines = db.query(GLJournalEntryLine).filter(
        GLJournalEntryLine.account_id == account.id
    ).all()

    total_dr = sum(line.debit_amount or Decimal("0") for line in lines)
    total_cr = sum(line.credit_amount or Decimal("0") for line in lines)

    # For assets: balance = DR - CR
    # For liabilities/equity: balance = CR - DR
    # For expenses: balance = DR - CR
    if account.account_type in ("asset", "expense"):
        return total_dr - total_cr
    else:
        return total_cr - total_dr


def verify_journal_entry_balanced(je: GLJournalEntry) -> bool:
    """Verify a journal entry has equal debits and credits"""
    total_dr = sum(line.debit_amount or Decimal("0") for line in je.lines)
    total_cr = sum(line.credit_amount or Decimal("0") for line in je.lines)
    return abs(total_dr - total_cr) < Decimal("0.01")


def get_inventory_qty(db: Session, product_id: int) -> Decimal:
    """Get on-hand quantity for a product"""
    inv = db.query(Inventory).filter(Inventory.product_id == product_id).first()
    return Decimal(str(inv.on_hand_quantity)) if inv else Decimal("0")


# =============================================================================
# TEST: PO RECEIPT FLOW
# =============================================================================

class TestPOReceiptFlow:
    """Test purchase order receiving creates proper GL entries"""

    def test_receive_materials_creates_gl_entry(self, db: Session, gl_accounts, test_material):
        """
        Receiving materials should:
        - Increase inventory on_hand
        - Create InventoryTransaction with type='receipt'
        - Create GLJournalEntry: DR 1200, CR 2000
        - Link transaction to journal entry
        """
        # Arrange
        txn_service = TransactionService(db)
        receipt_qty = Decimal("1000")  # 1000 grams
        unit_cost = Decimal("0.02")  # $0.02/gram
        expected_total = receipt_qty * unit_cost  # $20.00

        initial_raw_mat_balance = get_account_balance(db, "1200")
        initial_ap_balance = get_account_balance(db, "2000")
        initial_inventory = get_inventory_qty(db, test_material.id)

        # Act
        inv_txns, je = txn_service.receive_purchase_order(
            purchase_order_id=999,  # Fake PO ID for test
            items=[ReceiptItem(
                product_id=test_material.id,
                quantity=receipt_qty,
                unit_cost=unit_cost,
                unit="G",
                lot_number="LOT-001",
            )],
            user_id=None,
        )
        db.commit()

        # Assert - Inventory updated
        final_inventory = get_inventory_qty(db, test_material.id)
        assert final_inventory == initial_inventory + receipt_qty

        # Assert - Transaction created and linked
        assert len(inv_txns) == 1
        assert inv_txns[0].transaction_type == "receipt"
        assert inv_txns[0].journal_entry_id == je.id

        # Assert - Journal entry balanced
        assert verify_journal_entry_balanced(je)

        # Assert - GL balances updated
        final_raw_mat_balance = get_account_balance(db, "1200")
        final_ap_balance = get_account_balance(db, "2000")

        assert final_raw_mat_balance == initial_raw_mat_balance + expected_total
        assert final_ap_balance == initial_ap_balance + expected_total


# =============================================================================
# TEST: MATERIAL CONSUMPTION FLOW
# =============================================================================

class TestMaterialConsumptionFlow:
    """Test material issue to production creates proper GL entries"""

    def test_issue_materials_creates_gl_entry(self, db: Session, gl_accounts, test_material):
        """
        Issuing materials to production should:
        - Decrease inventory on_hand
        - Create InventoryTransaction with type='consumption'
        - Create GLJournalEntry: DR 1210 WIP, CR 1200 Raw Materials
        """
        # Arrange - First add some inventory
        txn_service = TransactionService(db)

        # Receipt first
        txn_service.receive_purchase_order(
            purchase_order_id=998,
            items=[ReceiptItem(
                product_id=test_material.id,
                quantity=Decimal("500"),
                unit_cost=Decimal("0.02"),
                unit="G",
            )],
        )
        db.commit()

        initial_inventory = get_inventory_qty(db, test_material.id)
        initial_wip = get_account_balance(db, "1210")
        initial_raw = get_account_balance(db, "1200")

        # Act - Issue materials
        issue_qty = Decimal("100")
        issue_cost = Decimal("0.02")
        expected_total = issue_qty * issue_cost  # $2.00

        inv_txns, je = txn_service.issue_materials_for_operation(
            production_order_id=999,
            operation_sequence=10,
            materials=[MaterialConsumption(
                product_id=test_material.id,
                quantity=issue_qty,
                unit_cost=issue_cost,
                unit="G",
            )],
        )
        db.commit()

        # Assert - Inventory decreased
        final_inventory = get_inventory_qty(db, test_material.id)
        assert final_inventory == initial_inventory - issue_qty

        # Assert - Transaction created
        assert len(inv_txns) == 1
        assert inv_txns[0].transaction_type == "consumption"
        assert inv_txns[0].quantity < 0  # Negative for issue

        # Assert - GL entries correct
        assert verify_journal_entry_balanced(je)

        final_wip = get_account_balance(db, "1210")
        final_raw = get_account_balance(db, "1200")

        assert final_wip == initial_wip + expected_total  # WIP increased
        assert final_raw == initial_raw - expected_total  # Raw decreased


# =============================================================================
# TEST: FG RECEIPT FLOW
# =============================================================================

class TestFGReceiptFlow:
    """Test finished goods receipt from production creates proper GL entries"""

    def test_receipt_fg_creates_gl_entry(self, db: Session, gl_accounts, test_finished_good):
        """
        Receiving FG from production should:
        - Increase FG inventory on_hand
        - Create InventoryTransaction with type='receipt'
        - Create GLJournalEntry: DR 1220 FG, CR 1210 WIP
        """
        # Arrange
        txn_service = TransactionService(db)

        initial_fg_inv = get_inventory_qty(db, test_finished_good.id)
        initial_fg_balance = get_account_balance(db, "1220")
        initial_wip_balance = get_account_balance(db, "1210")

        qty = Decimal("10")
        unit_cost = Decimal("15.00")
        expected_total = qty * unit_cost  # $150.00

        # Act
        inv_txn, je = txn_service.receipt_finished_good(
            production_order_id=999,
            product_id=test_finished_good.id,
            quantity=qty,
            unit_cost=unit_cost,
        )
        db.commit()

        # Assert - Inventory increased
        final_fg_inv = get_inventory_qty(db, test_finished_good.id)
        assert final_fg_inv == initial_fg_inv + qty

        # Assert - Transaction linked
        assert inv_txn.transaction_type == "receipt"
        assert inv_txn.journal_entry_id == je.id

        # Assert - GL entries correct
        assert verify_journal_entry_balanced(je)

        final_fg_balance = get_account_balance(db, "1220")
        final_wip_balance = get_account_balance(db, "1210")

        assert final_fg_balance == initial_fg_balance + expected_total  # FG increased
        assert final_wip_balance == initial_wip_balance - expected_total  # WIP decreased


# =============================================================================
# TEST: SHIPMENT FLOW
# =============================================================================

class TestShipmentFlow:
    """Test shipping creates proper GL entries"""

    def test_ship_order_creates_gl_entry(self, db: Session, gl_accounts, test_finished_good, test_packaging):
        """
        Shipping an order should:
        - Decrease FG inventory
        - Decrease packaging inventory (if used)
        - Create GLJournalEntry: DR 5000 COGS, CR 1220 FG + DR 5010, CR 1230
        """
        # Arrange - Add FG and packaging inventory first
        txn_service = TransactionService(db)

        # Add FG inventory via receipt
        txn_service.receipt_finished_good(
            production_order_id=997,
            product_id=test_finished_good.id,
            quantity=Decimal("20"),
            unit_cost=Decimal("15.00"),
        )

        # Add packaging inventory via PO receipt
        txn_service.receive_purchase_order(
            purchase_order_id=996,
            items=[ReceiptItem(
                product_id=test_packaging.id,
                quantity=Decimal("10"),
                unit_cost=Decimal("2.50"),
                unit="EA",
            )],
        )
        db.commit()

        initial_fg_inv = get_inventory_qty(db, test_finished_good.id)
        initial_pkg_inv = get_inventory_qty(db, test_packaging.id)
        initial_cogs = get_account_balance(db, "5000")
        initial_shipping = get_account_balance(db, "5010")

        # Act - Ship order
        ship_qty = Decimal("5")
        fg_cost = Decimal("15.00")
        pkg_qty = 1
        pkg_cost = Decimal("2.50")

        expected_cogs = ship_qty * fg_cost  # $75.00
        expected_shipping = pkg_qty * pkg_cost  # $2.50

        inv_txns, je = txn_service.ship_order(
            sales_order_id=_unique_so_id(),
            items=[ShipmentItem(
                product_id=test_finished_good.id,
                quantity=ship_qty,
                unit_cost=fg_cost,
            )],
            packaging=[PackagingUsed(
                product_id=test_packaging.id,
                quantity=pkg_qty,
                unit_cost=pkg_cost,
            )],
        )
        db.commit()

        # Assert - Inventories decreased
        final_fg_inv = get_inventory_qty(db, test_finished_good.id)
        final_pkg_inv = get_inventory_qty(db, test_packaging.id)

        assert final_fg_inv == initial_fg_inv - ship_qty
        assert final_pkg_inv == initial_pkg_inv - pkg_qty

        # Assert - Transactions created
        assert len(inv_txns) == 2  # FG shipment + packaging consumption

        # Assert - GL entries correct
        assert verify_journal_entry_balanced(je)

        final_cogs = get_account_balance(db, "5000")
        final_shipping = get_account_balance(db, "5010")

        assert final_cogs == initial_cogs + expected_cogs
        assert final_shipping == initial_shipping + expected_shipping


# =============================================================================
# TEST: SCRAP FLOW
# =============================================================================

class TestScrapFlow:
    """Test scrap recording creates proper GL entries"""

    def test_scrap_materials_creates_gl_entry(self, db: Session, gl_accounts, test_production_order):
        """
        Scrapping WIP should:
        - Create ScrapRecord
        - Create InventoryTransaction with type='scrap'
        - Create GLJournalEntry: DR 5020 Scrap Expense, CR 1210 WIP
        """
        # Arrange
        txn_service = TransactionService(db)

        initial_scrap_expense = get_account_balance(db, "5020")
        initial_wip = get_account_balance(db, "1210")

        qty = Decimal("2")
        unit_cost = Decimal("15.00")
        expected_total = qty * unit_cost  # $30.00

        # Act - use real production order from fixture (test_finished_good is dependency)
        inv_txn, je, scrap_rec = txn_service.scrap_materials(
            production_order_id=test_production_order.id,
            operation_sequence=30,
            product_id=test_production_order.product_id,
            quantity=qty,
            unit_cost=unit_cost,
            reason_code="QC_FAIL",
            notes="Test scrap",
        )
        db.commit()

        # Assert - ScrapRecord created
        assert scrap_rec is not None
        assert scrap_rec.quantity == qty
        assert scrap_rec.scrap_reason_code == "QC_FAIL"

        # Assert - Transaction linked
        assert inv_txn.transaction_type == "scrap"
        assert inv_txn.journal_entry_id == je.id

        # Assert - GL entries correct
        assert verify_journal_entry_balanced(je)

        final_scrap_expense = get_account_balance(db, "5020")
        final_wip = get_account_balance(db, "1210")

        assert final_scrap_expense == initial_scrap_expense + expected_total  # Expense increased
        assert final_wip == initial_wip - expected_total  # WIP decreased


# =============================================================================
# TEST: FULL MTO FLOW
# =============================================================================

class TestFullMTOFlow:
    """Test complete Make-to-Order flow with all GL entries"""

    def test_complete_mto_flow(self, db: Session, gl_accounts, test_material, test_finished_good, test_packaging):
        """
        Full MTO flow:
        1. Receive raw materials (DR 1200, CR 2000)
        2. Issue to production (DR 1210, CR 1200)
        3. Receipt FG from production (DR 1220, CR 1210)
        4. Ship to customer (DR 5000, CR 1220)

        Verify all GL balances are correct at end.
        """
        txn_service = TransactionService(db)

        # Track initial balances
        initial_balances = {
            "1200": get_account_balance(db, "1200"),
            "1210": get_account_balance(db, "1210"),
            "1220": get_account_balance(db, "1220"),
            "2000": get_account_balance(db, "2000"),
            "5000": get_account_balance(db, "5000"),
        }

        # Step 1: Receive materials ($20 worth)
        mat_qty = Decimal("1000")
        mat_cost = Decimal("0.02")
        txn_service.receive_purchase_order(
            purchase_order_id=100,
            items=[ReceiptItem(
                product_id=test_material.id,
                quantity=mat_qty,
                unit_cost=mat_cost,
                unit="G",
            )],
        )
        db.commit()

        # Step 2: Issue materials to production ($10 worth)
        issue_qty = Decimal("500")
        txn_service.issue_materials_for_operation(
            production_order_id=200,
            operation_sequence=10,
            materials=[MaterialConsumption(
                product_id=test_material.id,
                quantity=issue_qty,
                unit_cost=mat_cost,
                unit="G",
            )],
        )
        db.commit()

        # Step 3: Receipt FG (1 unit @ $15)
        fg_qty = Decimal("1")
        fg_cost = Decimal("15.00")
        txn_service.receipt_finished_good(
            production_order_id=200,
            product_id=test_finished_good.id,
            quantity=fg_qty,
            unit_cost=fg_cost,
        )
        db.commit()

        # Step 4: Ship to customer
        txn_service.ship_order(
            sales_order_id=_unique_so_id(),
            items=[ShipmentItem(
                product_id=test_finished_good.id,
                quantity=fg_qty,
                unit_cost=fg_cost,
            )],
        )
        db.commit()

        # Verify final balances
        final_balances = {
            "1200": get_account_balance(db, "1200"),
            "1210": get_account_balance(db, "1210"),
            "1220": get_account_balance(db, "1220"),
            "2000": get_account_balance(db, "2000"),
            "5000": get_account_balance(db, "5000"),
        }

        # Raw Materials: +$20 (receipt) - $10 (issue) = +$10
        assert final_balances["1200"] == initial_balances["1200"] + Decimal("10.00")

        # WIP: +$10 (material issue) - $15 (FG receipt) = -$5
        # Note: WIP goes negative because FG cost > material cost (labor not tracked yet)
        assert final_balances["1210"] == initial_balances["1210"] + Decimal("10.00") - Decimal("15.00")

        # FG: +$15 (receipt) - $15 (ship) = $0
        assert final_balances["1220"] == initial_balances["1220"]

        # AP: +$20 (PO receipt)
        assert final_balances["2000"] == initial_balances["2000"] + Decimal("20.00")

        # COGS: +$15 (shipment)
        assert final_balances["5000"] == initial_balances["5000"] + Decimal("15.00")
