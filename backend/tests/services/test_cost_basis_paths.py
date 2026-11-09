"""
The shared cost-basis rule on the real cost-reading paths, driven end to end.

Each test sets up filament the way FilaOps really stores it (stock in G, bought
in KG, purchase_factor 1000) and drives the real service. Two states matter:

  - never received: only standard_cost exists, per KG ($20.00)
  - received:       average_cost exists, per G ($0.02); standard_cost may have
                    been overwritten per G by the receipt sync

Before this PR every site below read the cost its own way and was 1000x off in
one of the two states.
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.accounting import GLJournalEntry, GLJournalEntryLine
from app.models.manufacturing import RoutingOperationMaterial
from app.models.mrp import PlannedOrder
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.services.inventory_ledger import post as ledger_post
from app.services.mrp import MRPService
from app.services.reconciliation_service import post_reconciliation_baseline
from app.services.transaction_service import TransactionService


@pytest.fixture
def unreceived_filament(make_product):
    """Filament that has never been received: standard_cost only, $20 per KG."""
    return make_product(
        item_type="material", unit="G", purchase_uom="KG",
        purchase_factor=Decimal("1000"), is_raw_material=True,
        standard_cost=Decimal("20.00"),
    )


@pytest.fixture
def received_filament(make_product):
    """Filament after a receipt: average $0.02/G, and standard_cost already
    overwritten per G by the receipt sync."""
    return make_product(
        item_type="material", unit="G", purchase_uom="KG",
        purchase_factor=Decimal("1000"), is_raw_material=True,
        standard_cost=Decimal("0.02"), average_cost=Decimal("0.02"),
        last_cost=Decimal("0.02"),
    )


def _je_total_debits(db, journal_entry_id):
    lines = db.query(GLJournalEntryLine).filter(
        GLJournalEntryLine.journal_entry_id == journal_entry_id
    ).all()
    return sum((line.debit_amount or Decimal("0") for line in lines), Decimal("0"))


# ---------------------------------------------------------------------------
# Cycle count GL
# ---------------------------------------------------------------------------

class TestCycleCountCost:
    def test_unreceived_filament_shortage_posts_dollars_not_thousands(
        self, db, unreceived_filament, location,
    ):
        """-100 G at $20/KG is $2.00, not $2,000."""
        ledger_post(db, product_id=unreceived_filament.id, location_id=location.id,
                    transaction_type="receipt", quantity_delta=Decimal("1000"))

        inv_txn, je = TransactionService(db).cycle_count_adjustment(
            product_id=unreceived_filament.id,
            expected_qty=Decimal("1000"), actual_qty=Decimal("900"),
            reason="count", location_id=location.id,
        )
        db.flush()

        assert _je_total_debits(db, je.id) == Decimal("2.00")
        assert Decimal(str(inv_txn.cost_per_unit)) == Decimal("0.02")

    def test_received_filament_shortage_uses_average_cost(
        self, db, received_filament, location,
    ):
        ledger_post(db, product_id=received_filament.id, location_id=location.id,
                    transaction_type="receipt", quantity_delta=Decimal("1000"))

        _, je = TransactionService(db).cycle_count_adjustment(
            product_id=received_filament.id,
            expected_qty=Decimal("1000"), actual_qty=Decimal("900"),
            reason="count", location_id=location.id,
        )
        db.flush()

        assert _je_total_debits(db, je.id) == Decimal("2.00")


class TestReconciliationCountCost:
    def test_unreceived_filament_count_posts_dollars_not_thousands(
        self, db, unreceived_filament, location,
    ):
        ledger_post(db, product_id=unreceived_filament.id, location_id=location.id,
                    transaction_type="receipt", quantity_delta=Decimal("1000"))

        txn = post_reconciliation_baseline(
            db, product_id=unreceived_filament.id, location_id=location.id,
            counted_qty=Decimal("900"), user="counter@example.com",
        )

        assert txn is not None and txn.journal_entry_id is not None
        je = db.get(GLJournalEntry, txn.journal_entry_id)
        assert _je_total_debits(db, je.id) == Decimal("2.00")

    def test_average_cost_product_is_valued_at_average_not_standard(
        self, db, make_product, location,
    ):
        """An average-cost item's count is valued at average cost, the same cost
        consumption and shipment relieve inventory at. It used to take
        standard_cost first, so the count and the ledger could disagree."""
        part = make_product(item_type="component", cost_method="average",
                            standard_cost=Decimal("4.00"), average_cost=Decimal("5.00"))
        ledger_post(db, product_id=part.id, location_id=location.id,
                    transaction_type="receipt", quantity_delta=Decimal("100"))

        txn = post_reconciliation_baseline(
            db, product_id=part.id, location_id=location.id,
            counted_qty=Decimal("110"), user="counter@example.com",
        )

        je = db.get(GLJournalEntry, txn.journal_entry_id)
        assert _je_total_debits(db, je.id) == Decimal("50.00")


# ---------------------------------------------------------------------------
# Routing material cost
# ---------------------------------------------------------------------------

class TestRoutingMaterialUnitCost:
    def _material(self, component, quantity="50"):
        mat = RoutingOperationMaterial(quantity=Decimal(quantity), unit="G",
                                       scrap_factor=Decimal("0"))
        mat.component = component
        return mat

    def test_unreceived_filament_converts_standard_cost(self, unreceived_filament):
        mat = self._material(unreceived_filament)
        assert mat.unit_cost == Decimal("0.02")
        assert mat.extended_cost == Decimal("1.00")

    def test_received_filament_is_not_divided_twice(self, received_filament):
        """Was (0.02 / 1000) = $0.00002/G, so 50 G cost $0.001 instead of $1.00."""
        mat = self._material(received_filament)
        assert mat.unit_cost == Decimal("0.02")
        assert mat.extended_cost == Decimal("1.00")

    def test_no_component_or_cost_is_zero(self, make_product):
        assert RoutingOperationMaterial(quantity=Decimal("1")).unit_cost == Decimal("0")
        assert self._material(make_product(unit="G", purchase_uom="KG")).unit_cost == Decimal("0")


# ---------------------------------------------------------------------------
# MRP planned purchase release
# ---------------------------------------------------------------------------

class TestMrpPurchaseRelease:
    def _planned_purchase(self, db, product, quantity):
        order = PlannedOrder(
            order_type="purchase", product_id=product.id,
            quantity=Decimal(str(quantity)),
            due_date=date.today() + timedelta(days=14), start_date=date.today(),
            status="planned", source_demand_type="mrp_calculation",
            created_at=datetime.now(timezone.utc),
        )
        db.add(order)
        db.flush()
        return order

    def _line(self, db, po_id):
        po = db.get(PurchaseOrder, po_id)
        line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po_id
        ).one()
        return po, line

    def test_filament_po_line_is_in_kg_at_cost_per_kg(
        self, db, unreceived_filament, make_vendor,
    ):
        """5000 G planned at $20/KG: a 5 KG line for $100, not 5000 x $20 = $100,000."""
        planned = self._planned_purchase(db, unreceived_filament, 5000)
        _, po_id = MRPService(db).release_planned_order(
            planned.id, vendor_id=make_vendor().id, user_id=1)

        po, line = self._line(db, po_id)
        assert line.purchase_unit == "KG"
        assert line.quantity_ordered == Decimal("5")
        assert line.unit_cost == Decimal("20")
        assert line.line_total == Decimal("100")
        assert po.total_amount == Decimal("100")

    def test_received_filament_po_line_uses_average_cost_per_kg(
        self, db, received_filament, make_vendor,
    ):
        planned = self._planned_purchase(db, received_filament, 5000)
        _, po_id = MRPService(db).release_planned_order(
            planned.id, vendor_id=make_vendor().id, user_id=1)

        _, line = self._line(db, po_id)
        assert (line.purchase_unit, line.quantity_ordered) == ("KG", Decimal("5"))
        assert line.unit_cost == Decimal("20")
        assert line.line_total == Decimal("100")

    def test_each_item_po_line_is_unchanged(self, db, make_product, make_vendor):
        part = make_product(item_type="component", standard_cost=Decimal("1.50"))
        planned = self._planned_purchase(db, part, 40)
        _, po_id = MRPService(db).release_planned_order(
            planned.id, vendor_id=make_vendor().id, user_id=1)

        _, line = self._line(db, po_id)
        assert (line.purchase_unit, line.quantity_ordered) == ("EA", Decimal("40"))
        assert line.unit_cost == Decimal("1.5")
        assert line.line_total == Decimal("60")


# ---------------------------------------------------------------------------
# Cycle-count screen cost, and inventory valuation
# ---------------------------------------------------------------------------

class TestInventorySummaryUnitCost:
    def _row(self, db, product, location):
        from app.services.inventory_transaction_service import get_inventory_summary

        ledger_post(db, product_id=product.id, location_id=location.id,
                    transaction_type="receipt", quantity_delta=Decimal("1000"))
        summary = get_inventory_summary(db, search=product.sku)
        return next(i for i in summary["items"] if i["product_id"] == product.id)

    def test_unreceived_filament_cost_matches_the_gram_quantity(
        self, db, unreceived_filament, location,
    ):
        """The screen multiplies variance (G) by this value: it must be $/G."""
        row = self._row(db, unreceived_filament, location)
        assert row["unit"] == "G"
        assert row["unit_cost"] == pytest.approx(0.02)

    def test_received_filament_cost_is_per_gram(self, db, received_filament, location):
        assert self._row(db, received_filament, location)["unit_cost"] == pytest.approx(0.02)

    def test_item_with_no_cost_is_none(self, db, make_product, location):
        assert self._row(db, make_product(), location)["unit_cost"] is None


class TestInventoryByAccountValuation:
    def test_unreceived_filament_is_valued_in_dollars_not_thousands(
        self, client, db, unreceived_filament, location,
    ):
        """5000 G at $20/KG is $100, not $100,000."""
        ledger_post(db, product_id=unreceived_filament.id, location_id=location.id,
                    transaction_type="receipt", quantity_delta=Decimal("5000"))
        db.flush()

        resp = client.get("/api/v1/admin/accounting/inventory-by-account")
        assert resp.status_code == 200
        items = [i for a in resp.json()["accounts"] for i in a["items"]]
        row = next(i for i in items if i["product_id"] == unreceived_filament.id)
        assert row["unit_cost"] == pytest.approx(0.02)
        assert row["total_value"] == pytest.approx(100.0)

    def test_item_with_only_average_cost_is_not_valued_at_zero(
        self, client, db, make_product, location,
    ):
        part = make_product(item_type="component", average_cost=Decimal("1.25"))
        ledger_post(db, product_id=part.id, location_id=location.id,
                    transaction_type="receipt", quantity_delta=Decimal("8"))
        db.flush()

        resp = client.get("/api/v1/admin/accounting/inventory-by-account")
        items = [i for a in resp.json()["accounts"] for i in a["items"]]
        row = next(i for i in items if i["product_id"] == part.id)
        assert row["total_value"] == pytest.approx(10.0)
