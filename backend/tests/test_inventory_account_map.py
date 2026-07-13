"""
#910: one shared item_type -> inventory-account map, and the three posters
that used to disagree with it.

Canonical map (app.services.gl_account_map.inventory_account_for):
    packaging -> 1230, finished_good -> 1220, everything else -> 1200.

Behavior changes pinned here (the bugs #910 fixes):
  (a) A manufactured `component` received by the production-completion sweep
      lands in Raw Materials (1200), not Finished Goods (1220) — so cycle
      count / reconciliation / valuation, which all relieve it at 1200, no
      longer drive 1200 negative and 1220 overstated.
  (b) issue_materials_for_operation credits the SAME account the purchase
      debited: packaging -> 1230, purchased finished_good BOM input -> 1220.
  (c) The completion-sweep consumption classifier sends a purchased
      finished_good consumed as a BOM input to 1220, not 1200.

Unchanged-behavior regressions (this is a refactor to the shared helper for
the four already-correct surfaces — identical output asserted):
  (d) receive_purchase_order and cycle_count_adjustment still book each
      item_type to the same account as before.
  (e) the #897 COGS identity (net 5000+5010+5030+5200 == material consumed)
      still holds on a produce -> ship flow.

Delta-based, per-run unique fixtures (filaops_test accumulates state), so
every assertion looks at an INDIVIDUAL entry's per-account nets.
"""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.accounting import GLAccount, GLJournalEntryLine
from app.services import inventory_service
from app.services.gl_account_map import inventory_account_for
from app.services.production_gl_service import create_production_completion_gl_entry
from app.services.transaction_service import (
    MaterialConsumption,
    ReceiptItem,
    ShipmentItem,
    TransactionService,
)


# =============================================================================
# Helpers (mirror test_production_completion_gl / test_cogs_gl_derivation)
# =============================================================================

def _location(db):
    return inventory_service.get_or_create_default_location(db)


def _seed_stock(db, product, qty, cost):
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="receipt",
        quantity=Decimal(str(qty)),
        reference_type="test_seed",
        reference_id=0,
        cost_per_unit=Decimal(str(cost)),
    )


def _consume(db, product, po, qty, cost):
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="consumption",
        quantity=Decimal(str(qty)),
        reference_type="production_order",
        reference_id=po.id,
        cost_per_unit=Decimal(str(cost)),
    )


def _receive_production(db, product, po, qty, cost):
    return inventory_service.create_inventory_transaction(
        db=db,
        product_id=product.id,
        location_id=_location(db).id,
        transaction_type="receipt",
        quantity=Decimal(str(qty)),
        reference_type="production_order",
        reference_id=po.id,
        cost_per_unit=Decimal(str(cost)),
    )


def _je_net(db, *jes):
    """account_code -> net (DR - CR) aggregated across one or more entries."""
    net = defaultdict(lambda: Decimal("0"))
    je_ids = [je.id for je in jes]
    rows = (
        db.query(
            GLAccount.account_code,
            GLJournalEntryLine.debit_amount,
            GLJournalEntryLine.credit_amount,
        )
        .join(GLJournalEntryLine, GLJournalEntryLine.account_id == GLAccount.id)
        .filter(GLJournalEntryLine.journal_entry_id.in_(je_ids))
        .all()
    )
    for code, debit, credit in rows:
        net[code] += Decimal(str(debit or 0)) - Decimal(str(credit or 0))
    return net


# =============================================================================
# The shared helper itself
# =============================================================================

class TestInventoryAccountForHelper:

    @pytest.mark.parametrize(
        "item_type,expected",
        [
            ("packaging", "1230"),
            ("finished_good", "1220"),
            ("component", "1200"),
            ("material", "1200"),
            ("supply", "1200"),
            ("service", "1200"),
            ("", "1200"),
            (None, "1200"),
            ("some_future_type", "1200"),
        ],
    )
    def test_maps_item_type_to_account(self, item_type, expected):
        assert inventory_account_for(item_type) == expected


# =============================================================================
# (a) Completion sweep: manufactured component receipt -> DR 1200, not 1220
# =============================================================================

class TestComponentCompletionReceipt:

    def test_component_receipt_debits_raw_materials_not_finished_goods(
        self, db, make_product, make_production_order
    ):
        """A production order that MAKES a `component` receives it into Raw
        Materials (1200) — the account every downstream flow relieves it at —
        instead of the flat DR 1220 that used to overstate Finished Goods."""
        raw = make_product(item_type="supply", average_cost=Decimal("0.50"))
        comp = make_product(item_type="component", average_cost=Decimal("2.00"))
        po = make_production_order(
            product_id=comp.id, status="in_progress", quantity=5
        )

        _seed_stock(db, raw, 100, "0.50")
        _consume(db, raw, po, 8, "0.50")        # 4.00 material  -> CR 1200
        _receive_production(db, comp, po, 5, "2.00")  # 10.00 component -> DR 1200

        je = create_production_completion_gl_entry(db, po)
        assert je is not None

        net = _je_net(db, je)
        # THE FIX: the manufactured component never touches Finished Goods.
        assert net["1220"] == Decimal("0")
        # Receipt (DR 10) minus consumption (CR 4) both net inside 1200.
        assert net["1200"] == Decimal("6.00")
        # WIP still nets to zero; variance = receipts(10) - consumption(4) = 6.
        assert net["1210"] == Decimal("0")
        assert net["5200"] == Decimal("-6.00")


# =============================================================================
# (c) Completion sweep: purchased finished_good BOM input -> CR 1220
# =============================================================================

class TestFinishedGoodConsumedAsBomInput:

    def test_finished_good_bom_input_credits_finished_goods_not_raw(
        self, db, make_product, make_production_order
    ):
        """A purchased `finished_good` consumed as a BOM input is relieved
        from Finished Goods (1220) — where its PO receipt debited it — not
        wrongly credited to Raw Materials (1200)."""
        fg_input = make_product(item_type="finished_good", average_cost=Decimal("2.00"))
        out_fg = make_product(item_type="finished_good", average_cost=Decimal("5.00"))
        po = make_production_order(
            product_id=out_fg.id, status="in_progress", quantity=2
        )

        _seed_stock(db, fg_input, 100, "2.00")
        _consume(db, fg_input, po, 2, "2.00")      # 4.00 FG input -> CR 1220
        _receive_production(db, out_fg, po, 2, "5.00")  # 10.00 out FG -> DR 1220

        je = create_production_completion_gl_entry(db, po)
        assert je is not None

        net = _je_net(db, je)
        # THE FIX: the finished_good BOM input is not miscredited to 1200.
        assert net["1200"] == Decimal("0")
        # Out-FG receipt (DR 10) minus FG-input consumption (CR 4) net in 1220.
        assert net["1220"] == Decimal("6.00")
        assert net["1210"] == Decimal("0")
        assert net["5200"] == Decimal("-6.00")


# =============================================================================
# (b) issue_materials_for_operation credits by item_type
# =============================================================================

class TestIssueMaterialsAccountMap:

    def _issue(self, db, product, po, qty, cost):
        _seed_stock(db, product, qty * 10, cost)  # ensure on-hand
        ts = TransactionService(db)
        _txns, je = ts.issue_materials_for_operation(
            production_order_id=po.id,
            operation_sequence=10,
            materials=[
                MaterialConsumption(
                    product_id=product.id,
                    quantity=Decimal(str(qty)),
                    unit_cost=Decimal(str(cost)),
                )
            ],
        )
        db.flush()
        return je

    def test_packaging_consumed_at_operation_credits_1230(
        self, db, make_product, make_production_order
    ):
        """Packaging consumed at a production stage credits Packaging (1230),
        matching the 1230 its PO receipt debited — not a flat CR 1200."""
        pkg = make_product(item_type="packaging", average_cost=Decimal("2.50"))
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)

        je = self._issue(db, pkg, po, qty=4, cost="2.50")  # 10.00

        net = _je_net(db, je)
        assert net["1210"] == Decimal("10.00")   # DR WIP
        assert net["1230"] == Decimal("-10.00")  # CR Packaging
        assert net["1200"] == Decimal("0")       # NOT Raw Materials

    def test_finished_good_bom_input_at_operation_credits_1220(
        self, db, make_product, make_production_order
    ):
        """A purchased finished_good issued as a BOM input at an operation
        credits Finished Goods (1220), not Raw Materials."""
        fg_input = make_product(item_type="finished_good", average_cost=Decimal("3.00"))
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)

        je = self._issue(db, fg_input, po, qty=2, cost="3.00")  # 6.00

        net = _je_net(db, je)
        assert net["1210"] == Decimal("6.00")    # DR WIP
        assert net["1220"] == Decimal("-6.00")   # CR Finished Goods
        assert net["1200"] == Decimal("0")

    def test_supply_at_operation_still_credits_1200(
        self, db, make_product, make_production_order
    ):
        """Regression: the common raw-material case is unchanged (CR 1200)."""
        raw = make_product(item_type="supply", average_cost=Decimal("0.02"))
        fg = make_product(item_type="finished_good")
        po = make_production_order(product_id=fg.id, status="in_progress", quantity=1)

        je = self._issue(db, raw, po, qty=100, cost="0.02")  # 2.00

        net = _je_net(db, je)
        assert net["1210"] == Decimal("2.00")
        assert net["1200"] == Decimal("-2.00")


# =============================================================================
# (d) Unchanged-behavior regressions for the already-correct posters
# =============================================================================

class TestPurchaseOrderReceiptRegression:

    @pytest.mark.parametrize(
        "item_type,expected_account",
        [
            ("supply", "1200"),
            ("component", "1200"),
            ("packaging", "1230"),
            ("finished_good", "1220"),
        ],
    )
    def test_receipt_debits_expected_inventory_account(
        self, db, make_product, make_vendor, make_purchase_order,
        item_type, expected_account,
    ):
        product = make_product(item_type=item_type, standard_cost=Decimal("4.00"))
        po = make_purchase_order(vendor_id=make_vendor().id, status="approved")

        ts = TransactionService(db)
        _txns, je = ts.receive_purchase_order(
            purchase_order_id=po.id,
            items=[ReceiptItem(
                product_id=product.id,
                quantity=Decimal("3"),
                unit_cost=Decimal("4.00"),
            )],
        )
        db.flush()

        net = _je_net(db, je)
        assert net[expected_account] == Decimal("12.00")   # DR inventory
        assert net["2000"] == Decimal("-12.00")            # CR Accounts Payable


class TestCycleCountAdjustmentRegression:

    @pytest.mark.parametrize(
        "item_type,expected_account",
        [
            ("supply", "1200"),
            ("component", "1200"),
            ("packaging", "1230"),
            ("finished_good", "1220"),
        ],
    )
    def test_shortage_credits_expected_inventory_account(
        self, db, make_product, item_type, expected_account,
    ):
        product = make_product(item_type=item_type, standard_cost=Decimal("5.00"))
        _seed_stock(db, product, 10, "5.00")

        ts = TransactionService(db)
        _txn, je = ts.cycle_count_adjustment(
            product_id=product.id,
            expected_qty=Decimal("10"),
            actual_qty=Decimal("8"),      # shortage of 2 -> 10.00
            reason="regression",
        )
        db.flush()

        net = _je_net(db, je)
        # Shortage: DR 5030 Inventory Adjustment, CR the inventory account.
        assert net["5030"] == Decimal("10.00")
        assert net[expected_account] == Decimal("-10.00")


# =============================================================================
# (e) #897 identity still holds on a produce -> ship flow
# =============================================================================

class TestProduceShipCogsIdentity:

    def test_net_cogs_accounts_equal_material_consumed(
        self, db, make_product, make_sales_order, make_production_order
    ):
        """#897: across a produce->ship cycle the net of the COGS/expense
        accounts (5000 ship-COGS + 5010 packaging + 5030 adjustment + 5200
        completion-variance, DR-CR) collapses to exactly the out-of-pocket
        material actually consumed. The item_type->account refactor must not
        disturb this — a normal finished_good still receipts to 1220."""
        raw = make_product(item_type="supply", average_cost=Decimal("0.50"))
        fg = make_product(item_type="finished_good", average_cost=Decimal("12.00"))

        so = make_sales_order(
            product_id=fg.id, quantity=1, unit_price=Decimal("24.00"),
            status="shipped", shipped_at=datetime.now(timezone.utc),
        )
        po = make_production_order(
            product_id=fg.id, status="completed", quantity=1, sales_order_id=so.id,
        )

        _seed_stock(db, raw, 1000, "0.50")
        _consume(db, raw, po, 10, "0.50")            # 5.00 material consumed
        _receive_production(db, fg, po, 1, "12.00")  # 12.00 FG -> DR 1220

        completion_je = create_production_completion_gl_entry(db, po)
        db.flush()

        _seed_stock(db, fg, 1, "12.00")  # FG on-hand so ship isn't held
        ts = TransactionService(db)
        _inv, ship_je = ts.ship_order(
            sales_order_id=so.id,
            items=[ShipmentItem(
                product_id=fg.id, quantity=Decimal("1"), unit_cost=Decimal("12.00"),
            )],
        )
        db.flush()

        net = _je_net(db, completion_je, ship_je)
        identity = net["5000"] + net["5010"] + net["5030"] + net["5200"]
        assert identity == Decimal("5.00")  # == material consumed (out of pocket)
        # Sanity on the individual legs.
        assert net["5000"] == Decimal("12.00")   # ship COGS
        assert net["5200"] == Decimal("-7.00")   # completion variance credit
