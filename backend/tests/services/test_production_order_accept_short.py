"""
Tests for PO Accept Short (Feature A, Issue #496)

Tests accept_short_production_order() service function.
This action completes a "short" PO with its already-produced quantity,
processes inventory (material consumption, FG receipt, reservation release),
and writes a CloseShortRecord audit trail.
"""
import pytest
from decimal import Decimal

from fastapi import HTTPException

from app.models.production_order import ProductionOrder
from app.models.inventory import InventoryTransaction
from app.models.close_short_record import CloseShortRecord
from app.services import production_order_service as svc


class TestAcceptShortGuards:
    """Guards that prevent invalid accept-short calls."""

    def test_rejects_draft_status(self, db, make_product, make_production_order):
        """Cannot accept short on a draft PO."""
        product = make_product(item_type="finished_good", unit="EA")
        po = make_production_order(product_id=product.id, status="draft", quantity=10)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            svc.accept_short_production_order(
                db, po.id, "test@filaops.dev", user_id=1,
            )
        assert exc_info.value.status_code == 400
        assert "draft" in str(exc_info.value.detail).lower()

    def test_rejects_complete_status(self, db, make_product, make_production_order):
        """Cannot accept short on an already-complete PO."""
        product = make_product(item_type="finished_good", unit="EA")
        po = make_production_order(product_id=product.id, status="complete", quantity=10)
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            svc.accept_short_production_order(
                db, po.id, "test@filaops.dev", user_id=1,
            )
        assert exc_info.value.status_code == 400

    def test_rejects_zero_completed(self, db, make_product, make_production_order):
        """Cannot accept short when nothing has been produced."""
        product = make_product(item_type="finished_good", unit="EA")
        po = make_production_order(
            product_id=product.id, status="short", quantity=10,
            quantity_completed=0,
        )
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            svc.accept_short_production_order(
                db, po.id, "test@filaops.dev", user_id=1,
            )
        assert exc_info.value.status_code == 400
        assert "no units" in str(exc_info.value.detail).lower()

    def test_rejects_fully_completed(self, db, make_product, make_production_order):
        """Cannot accept short when order is fully completed — use complete instead."""
        product = make_product(item_type="finished_good", unit="EA")
        po = make_production_order(
            product_id=product.id, status="short", quantity=10,
            quantity_completed=10,
        )
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            svc.accept_short_production_order(
                db, po.id, "test@filaops.dev", user_id=1,
            )
        assert exc_info.value.status_code == 400
        assert "fully completed" in str(exc_info.value.detail).lower()

    def test_rejects_cancelled_status(self, db, make_product, make_production_order):
        """Cannot accept short on a cancelled PO."""
        product = make_product(item_type="finished_good", unit="EA")
        po = make_production_order(
            product_id=product.id, status="cancelled", quantity=10,
            quantity_completed=5,
        )
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            svc.accept_short_production_order(
                db, po.id, "test@filaops.dev", user_id=1,
            )
        assert exc_info.value.status_code == 400

    def test_rejects_nonexistent_order(self, db):
        """Returns 404 for nonexistent PO."""
        with pytest.raises(HTTPException) as exc_info:
            svc.accept_short_production_order(
                db, 999999, "test@filaops.dev", user_id=1,
            )
        assert exc_info.value.status_code == 404


class TestAcceptShortSuccess:
    """Happy path: accept short completes the PO and processes inventory."""

    def _make_short_po(self, db, make_product, make_production_order,
                       quantity_ordered=15, quantity_completed=12):
        """Create a PO in 'short' status with given completed/ordered quantities."""
        product = make_product(
            item_type="finished_good",
            unit="EA",
            cost_method="standard",
            standard_cost=Decimal("5.00"),
            selling_price=Decimal("15.00"),
            procurement_type="make",
        )
        po = make_production_order(
            product_id=product.id,
            status="short",
            quantity=quantity_ordered,
            quantity_completed=quantity_completed,
            quantity_scrapped=0,
        )
        db.flush()
        return product, po

    def test_sets_status_complete(self, db, make_product, make_production_order):
        """Accept short transitions PO from 'short' to 'complete'."""
        _, po = self._make_short_po(db, make_product, make_production_order)

        result = svc.accept_short_production_order(
            db, po.id, "test@filaops.dev", user_id=1,
        )
        assert result.status == "complete"

    def test_receipts_fg_for_completed_quantity(self, db, make_product, make_production_order):
        """FG inventory increases by quantity_completed, not quantity_ordered."""
        _, po = self._make_short_po(
            db, make_product, make_production_order,
            quantity_ordered=15, quantity_completed=12,
        )

        svc.accept_short_production_order(
            db, po.id, "test@filaops.dev", user_id=1,
        )

        receipt_txn = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == po.id,
            InventoryTransaction.transaction_type == "receipt",
        ).first()
        assert receipt_txn is not None
        assert receipt_txn.quantity == Decimal("12")  # completed qty, NOT ordered qty (15)

    def test_releases_reservations_without_error(self, db, make_product, make_production_order):
        """Accept short succeeds even when no reservations exist to release."""
        _, po = self._make_short_po(db, make_product, make_production_order)

        # Should not raise — gracefully handles no reservations
        result = svc.accept_short_production_order(
            db, po.id, "test@filaops.dev", user_id=1,
        )
        assert result.status == "complete"

    def test_creates_audit_record(self, db, make_product, make_production_order):
        """Accept short writes a CloseShortRecord with before/after state."""
        _, po = self._make_short_po(db, make_product, make_production_order)

        svc.accept_short_production_order(
            db, po.id, "test@filaops.dev", user_id=1,
            notes="Printer jammed, accepting 12 of 15",
        )

        record = db.query(CloseShortRecord).filter(
            CloseShortRecord.entity_type == "production_order",
            CloseShortRecord.entity_id == po.id,
        ).first()
        assert record is not None
        assert record.reason == "Printer jammed, accepting 12 of 15"
        assert record.line_adjustments is not None
        assert len(record.line_adjustments) == 1
        assert record.line_adjustments[0]["before_qty"] == "15"
        assert record.line_adjustments[0]["after_qty"] == "12"

    def test_preserves_quantity_completed(self, db, make_product, make_production_order):
        """quantity_completed stays at 12, not doubled to 24."""
        _, po = self._make_short_po(
            db, make_product, make_production_order,
            quantity_ordered=15, quantity_completed=12,
        )

        svc.accept_short_production_order(
            db, po.id, "test@filaops.dev", user_id=1,
        )

        db.expire_all()
        refreshed = db.query(ProductionOrder).filter(ProductionOrder.id == po.id).first()
        assert refreshed.quantity_completed == Decimal("12")  # NOT 24

    def test_accepts_notes(self, db, make_product, make_production_order):
        """Optional notes are appended to the PO."""
        _, po = self._make_short_po(db, make_product, make_production_order)

        result = svc.accept_short_production_order(
            db, po.id, "test@filaops.dev", user_id=1,
            notes="Material shortage, vendor delayed",
        )
        assert "Material shortage" in (result.notes or "")

    def test_rejects_in_progress_status(self, db, make_product, make_production_order):
        """Accept short requires 'short' status — 'in_progress' must use /complete."""
        product = make_product(
            item_type="finished_good", unit="EA",
            cost_method="standard", standard_cost=Decimal("5.00"),
        )
        po = make_production_order(
            product_id=product.id, status="in_progress", quantity=10,
            quantity_completed=7, quantity_scrapped=0,
        )
        db.flush()

        with pytest.raises(HTTPException) as exc_info:
            svc.accept_short_production_order(
                db, po.id, "test@filaops.dev", user_id=1,
            )
        assert exc_info.value.status_code == 400
        assert "short" in str(exc_info.value.detail).lower()
