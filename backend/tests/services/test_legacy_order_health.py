"""
Tests for LEGACY-1 — brownfield order data health.

Covers:
- generate_production_orders: legacy NULL-linked WO coverage fallback
  (pre-#713 production orders have sales_order_line_id = NULL)
- resolve_legacy_fulfillment: close_out and reopen actions + 409 guard,
  including the no-inventory / no-GL design decision for close_out
- get_material_requirements: "historical" summary flag for terminal /
  short-closed orders

All tests create their own fixtures — no assertions on global counts
(the dev/CI databases accumulate data across runs).
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.models.accounting import GLJournalEntry
from app.models.inventory import InventoryTransaction
from app.models.production_order import ProductionOrder
from app.models.sales_order import SalesOrderLine
from app.services import sales_order_service


# =============================================================================
# Helpers
# =============================================================================

def _make_order_line(db, sales_order_id, product_id, quantity=1, unit_price=Decimal("10.00")):
    """Create a SalesOrderLine directly."""
    line = SalesOrderLine(
        sales_order_id=sales_order_id,
        product_id=product_id,
        quantity=quantity,
        unit_price=unit_price,
        total=unit_price * quantity,
        discount=Decimal("0"),
        tax_rate=Decimal("0"),
    )
    db.add(line)
    db.flush()
    return line


def _make_legacy_wo(db, *, so_id, product_id, code, status="complete", quantity=1):
    """Create a production order with NO line linkage (pre-#713 legacy shape)."""
    po = ProductionOrder(
        code=code,
        product_id=product_id,
        sales_order_id=so_id,
        sales_order_line_id=None,
        quantity_ordered=quantity,
        quantity_completed=quantity,
        quantity_scrapped=0,
        status=status,
        created_by="legacy-test",
    )
    db.add(po)
    db.flush()
    return po


def _make_legacy_completed_order(db, make_sales_order, make_product, *, n_lines=2):
    """A completed line_item order with legacy NULL-linked complete WOs.

    Mirrors the verified SO-2026-0041 shape: status=completed, lines with
    shipped_quantity=0, fulfillment_status=pending, shipped_at=None, WOs
    complete but unlinked.
    """
    so = make_sales_order(
        status="completed",
        order_type="line_item",
        fulfillment_status="pending",
    )
    lines = []
    for i in range(n_lines):
        product = make_product(selling_price=Decimal("10.00"))
        line = _make_order_line(db, so.id, product.id, quantity=2)
        lines.append(line)
        _make_legacy_wo(
            db,
            so_id=so.id,
            product_id=product.id,
            code=f"WO-LEG-{so.id}-{i}",
            quantity=2,
        )
    db.flush()
    return so, lines


# =============================================================================
# generate_production_orders — legacy coverage fallback
# =============================================================================

class TestLegacyWOCoverage:
    """Legacy NULL-linked WOs must count as line coverage."""

    def test_legacy_null_linked_wos_return_already_exist(
        self, db, make_sales_order, make_product
    ):
        """Completed legacy order with NULL-linked WOs covering all lines
        returns the friendly 'already exist' message instead of the
        misleading status-must-be-confirmed 400."""
        so, _lines = _make_legacy_completed_order(db, make_sales_order, make_product)

        result = sales_order_service.generate_production_orders(
            db, so.id, "test@filaops.dev"
        )

        assert result["message"] == "Production orders already exist"
        assert result["created_orders"] == []
        assert len(result["existing_orders"]) == 2

    def test_single_legacy_wo_covers_all_lines_of_its_product(
        self, db, make_sales_order, make_product
    ):
        """One NULL-linked WO covers every line of its product (coverage
        check, not assignment)."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="completed", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=1)
        _make_order_line(db, so.id, product.id, quantity=3)
        _make_legacy_wo(
            db, so_id=so.id, product_id=product.id, code=f"WO-LEG-MULTI-{so.id}"
        )

        result = sales_order_service.generate_production_orders(
            db, so.id, "test@filaops.dev"
        )
        assert result["message"] == "Production orders already exist"

    def test_legacy_wo_does_not_cover_other_products(
        self, db, make_sales_order, make_product
    ):
        """A NULL-linked WO only covers lines with a matching product_id;
        uncovered lines still get new WOs on a confirmed order."""
        p1 = make_product(selling_price=Decimal("10.00"))
        p2 = make_product(selling_price=Decimal("20.00"))
        so = make_sales_order(status="confirmed", order_type="line_item")
        _make_order_line(db, so.id, p1.id, quantity=1)
        line2 = _make_order_line(db, so.id, p2.id, quantity=2)
        _make_legacy_wo(
            db, so_id=so.id, product_id=p1.id, code=f"WO-LEG-P1-{so.id}", status="draft"
        )

        result = sales_order_service.generate_production_orders(
            db, so.id, "test@filaops.dev"
        )

        assert len(result["created_orders"]) == 1
        created = db.query(ProductionOrder).filter(
            ProductionOrder.code == result["created_orders"][0]
        ).one()
        assert created.sales_order_line_id == line2.id
        assert created.product_id == p2.id

    def test_cancelled_wos_are_not_coverage(
        self, db, make_sales_order, make_product
    ):
        """Cancelled WOs (linked or legacy NULL-linked) must not block
        regeneration — an order whose WOs were all cancelled gets new ones."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="confirmed", order_type="line_item")
        line = _make_order_line(db, so.id, product.id, quantity=2)
        _make_legacy_wo(
            db,
            so_id=so.id,
            product_id=product.id,
            code=f"WO-LEG-CANC-{so.id}",
            status="cancelled",
        )

        result = sales_order_service.generate_production_orders(
            db, so.id, "test@filaops.dev"
        )

        assert len(result["created_orders"]) == 1
        created = db.query(ProductionOrder).filter(
            ProductionOrder.code == result["created_orders"][0]
        ).one()
        assert created.sales_order_line_id == line.id

    def test_unconfirmed_order_without_any_wos_still_rejected(
        self, db, make_sales_order, make_product
    ):
        """The fallback must not weaken the confirmation gate when no WOs
        exist at all."""
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="pending", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=1)

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.generate_production_orders(
                db, so.id, "test@filaops.dev"
            )
        assert exc_info.value.status_code == 400
        assert "confirm" in exc_info.value.detail.lower()


# =============================================================================
# resolve_legacy_fulfillment
# =============================================================================

class TestResolveLegacyFulfillment:
    """close_out / reopen actions and the server-side mismatch guard."""

    def test_close_out_records_fulfillment_paperwork_only(
        self, db, make_sales_order, make_product
    ):
        so, lines = _make_legacy_completed_order(db, make_sales_order, make_product)

        order = sales_order_service.resolve_legacy_fulfillment(
            db, order_id=so.id, action="close_out", user_email="admin@filaops.dev"
        )
        db.flush()

        assert order.shipped_at is not None
        assert order.fulfillment_status == "shipped"
        assert order.status == "completed"  # status untouched
        for line in lines:
            db.refresh(line)
            assert line.shipped_quantity == line.quantity
        assert "Legacy fulfillment closed out by admin@filaops.dev" in order.internal_notes

        # DESIGN DECISION: paperwork only — no inventory movements, no GL.
        txns = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "sales_order",
            InventoryTransaction.reference_id == so.id,
        ).count()
        assert txns == 0
        gl = db.query(GLJournalEntry).filter(
            GLJournalEntry.source_type == "sales_order",
            GLJournalEntry.source_id == so.id,
        ).count()
        assert gl == 0

    def test_close_out_uses_actual_completion_date_when_present(
        self, db, make_sales_order, make_product
    ):
        completed_at = datetime(2026, 1, 15, 12, 0, 0)
        so, _ = _make_legacy_completed_order(db, make_sales_order, make_product)
        so.actual_completion_date = completed_at
        db.flush()

        order = sales_order_service.resolve_legacy_fulfillment(
            db, order_id=so.id, action="close_out", user_email="admin@filaops.dev"
        )
        assert order.shipped_at == completed_at

    def test_close_out_on_delivered_order_sets_delivered_fulfillment(
        self, db, make_sales_order, make_product
    ):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            status="delivered", order_type="line_item", fulfillment_status="pending"
        )
        _make_order_line(db, so.id, product.id, quantity=1)

        order = sales_order_service.resolve_legacy_fulfillment(
            db, order_id=so.id, action="close_out", user_email="admin@filaops.dev"
        )
        assert order.fulfillment_status == "delivered"

    def test_reopen_sets_ready_to_ship(self, db, make_sales_order, make_product):
        so, lines = _make_legacy_completed_order(db, make_sales_order, make_product)

        order = sales_order_service.resolve_legacy_fulfillment(
            db, order_id=so.id, action="reopen", user_email="admin@filaops.dev"
        )
        db.flush()

        assert order.status == "ready_to_ship"
        assert order.fulfillment_status == "ready"
        assert order.shipped_at is None
        for line in lines:
            db.refresh(line)
            assert (line.shipped_quantity or Decimal("0")) == Decimal("0")
        assert "Legacy fulfillment reopened" in order.internal_notes

    def test_409_when_shipment_evidence_exists(
        self, db, make_sales_order, make_product
    ):
        """shipped_at present → not a legacy mismatch → 409."""
        so, _ = _make_legacy_completed_order(db, make_sales_order, make_product)
        so.shipped_at = datetime.now(timezone.utc)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.resolve_legacy_fulfillment(
                db, order_id=so.id, action="close_out", user_email="admin@filaops.dev"
            )
        assert exc_info.value.status_code == 409

    def test_409_when_line_shipped_quantity_present(
        self, db, make_sales_order, make_product
    ):
        so, lines = _make_legacy_completed_order(db, make_sales_order, make_product)
        lines[0].shipped_quantity = Decimal("1")
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.resolve_legacy_fulfillment(
                db, order_id=so.id, action="reopen", user_email="admin@filaops.dev"
            )
        assert exc_info.value.status_code == 409

    def test_409_when_status_not_in_shipped_set(
        self, db, make_sales_order, make_product
    ):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status="in_production", order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=1)

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.resolve_legacy_fulfillment(
                db, order_id=so.id, action="close_out", user_email="admin@filaops.dev"
            )
        assert exc_info.value.status_code == 409

    def test_400_for_unknown_action(self, db, make_sales_order, make_product):
        so, _ = _make_legacy_completed_order(db, make_sales_order, make_product)

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.resolve_legacy_fulfillment(
                db, order_id=so.id, action="explode", user_email="admin@filaops.dev"
            )
        assert exc_info.value.status_code == 400


# =============================================================================
# get_material_requirements — historical flag
# =============================================================================

class TestHistoricalRequirementsFlag:
    """Terminal/short-closed orders are flagged historical in the summary."""

    @pytest.mark.parametrize(
        "status", ["completed", "cancelled", "shipped", "delivered"]
    )
    def test_terminal_statuses_are_historical(
        self, db, make_sales_order, make_product, status
    ):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status=status, order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=1)

        result = sales_order_service.get_material_requirements(db, so.id)
        assert result["summary"]["historical"] is True

    @pytest.mark.parametrize("status", ["confirmed", "in_production", "pending"])
    def test_active_statuses_are_not_historical(
        self, db, make_sales_order, make_product, status
    ):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(status=status, order_type="line_item")
        _make_order_line(db, so.id, product.id, quantity=1)

        result = sales_order_service.get_material_requirements(db, so.id)
        assert result["summary"]["historical"] is False

    def test_closed_short_order_is_historical(
        self, db, make_sales_order, make_product
    ):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            status="ready_to_ship", order_type="line_item", closed_short=True
        )
        _make_order_line(db, so.id, product.id, quantity=1)

        result = sales_order_service.get_material_requirements(db, so.id)
        assert result["summary"]["historical"] is True
