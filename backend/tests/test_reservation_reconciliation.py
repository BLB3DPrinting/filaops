"""
Tests for HARD-5: Reservation reconciliation and stranded allocation repair.

Covers:
1. get_allocation_reconciliation_report — drift detection and stranded identification
2. release_stranded_allocations — repair path (terminal PO, deleted PO, live PO guard)
3. check_allocation_guard — write-time flag (not block)
4. Terminal-state release for complete, cancel, accept-short paths
5. API endpoints (GET reconciliation, POST repair)
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.models.inventory import Inventory, InventoryTransaction, InventoryLocation
from app.models.production_order import ProductionOrder
from app.models.product import Product
from app.services.reservation_reconciliation_service import (
    get_allocation_reconciliation_report,
    release_stranded_allocations,
    check_allocation_guard,
    TERMINAL_PO_STATUSES,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_inventory(db, product_id: int, on_hand: Decimal, allocated: Decimal) -> Inventory:
    """Create or return inventory row with specified quantities."""
    loc = db.query(InventoryLocation).filter(InventoryLocation.id == 1).first()
    inv = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.location_id == loc.id,
    ).first()
    if inv is None:
        inv = Inventory(
            product_id=product_id,
            location_id=loc.id,
            on_hand_quantity=on_hand,
            allocated_quantity=allocated,
        )
        db.add(inv)
    else:
        inv.on_hand_quantity = on_hand
        inv.allocated_quantity = allocated
    db.flush()
    return inv


def _make_reservation_txn(
    db,
    product_id: int,
    location_id: int,
    production_order_id: int,
    quantity: Decimal,
    txn_type: str = "reservation",
) -> InventoryTransaction:
    txn = InventoryTransaction(
        product_id=product_id,
        location_id=location_id,
        transaction_type=txn_type,
        quantity=quantity,
        reference_type="production_order",
        reference_id=production_order_id,
        notes=f"Test {txn_type}",
        created_at=datetime.now(timezone.utc),
    )
    db.add(txn)
    db.flush()
    return txn


# =============================================================================
# 1. check_allocation_guard
# =============================================================================

class TestCheckAllocationGuard:
    """Write-time guard: LOG + FLAG, never hard block."""

    def test_no_shortage(self):
        would_exceed, available_after = check_allocation_guard(
            Decimal("100"), Decimal("30"), Decimal("20")
        )
        assert not would_exceed
        assert available_after == Decimal("50")

    def test_exact_match_not_exceed(self):
        """Reserving exactly up to on_hand is allowed (available_after == 0)."""
        would_exceed, available_after = check_allocation_guard(
            Decimal("50"), Decimal("0"), Decimal("50")
        )
        assert not would_exceed
        assert available_after == Decimal("0")

    def test_shortage_flagged(self):
        """Reserving more than available flags would_exceed = True."""
        would_exceed, available_after = check_allocation_guard(
            Decimal("50"), Decimal("40"), Decimal("20")
        )
        assert would_exceed
        assert available_after == Decimal("-10")

    def test_zero_on_hand(self):
        """Zero on_hand with any reservation is a shortage."""
        would_exceed, available_after = check_allocation_guard(
            Decimal("0"), Decimal("0"), Decimal("5")
        )
        assert would_exceed
        assert available_after == Decimal("-5")


# =============================================================================
# 2. get_allocation_reconciliation_report — drift detection
# =============================================================================

class TestAllocationDriftReport:
    """Derive truth from ledger and compare to stored allocated_quantity."""

    def test_no_drift_when_in_sync(self, db, make_product, make_production_order):
        """When stored == ledger-derived, no drift reported."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="draft")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("40"))

        # Ledger: 40 reserved, none released
        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("40"))

        report = get_allocation_reconciliation_report(db)
        matching = [d for d in report.drift_items if d.inventory_id == inv.id]
        assert len(matching) == 1
        assert not matching[0].has_drift
        assert matching[0].drift == Decimal("0")

    def test_drift_detected_stored_higher(self, db, make_product, make_production_order):
        """Stored allocated > ledger sum → positive drift (phantom allocation)."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="cancelled")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("500"))

        # Ledger: 500 reserved, 500 released  → net = 0
        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("500"))
        _make_reservation_txn(
            db, product.id, inv.location_id, po.id, Decimal("500"), "reservation_release"
        )

        report = get_allocation_reconciliation_report(db)
        matching = [d for d in report.drift_items if d.inventory_id == inv.id]
        assert len(matching) == 1
        assert matching[0].has_drift
        # stored=500, ledger_net=0 → drift=500
        assert matching[0].drift == Decimal("500")
        assert matching[0].stored_allocated == Decimal("500")
        assert matching[0].ledger_allocated == Decimal("0")

    def test_drift_detected_stored_lower(self, db, make_product, make_production_order):
        """Stored allocated < ledger sum → negative drift."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="released")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("10"))

        # Ledger: 40 reserved → net = 40
        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("40"))

        report = get_allocation_reconciliation_report(db)
        matching = [d for d in report.drift_items if d.inventory_id == inv.id]
        assert len(matching) == 1
        assert matching[0].has_drift
        # stored=10, ledger_net=40 → drift = -30
        assert matching[0].drift == Decimal("-30")

    def test_drifted_only_filter(self, db, make_product, make_production_order):
        """drifted_only=True returns only rows with non-zero drift."""
        product1 = make_product()
        product2 = make_product()
        po1 = make_production_order(product_id=product1.id, status="draft")
        po2 = make_production_order(product_id=product2.id, status="cancelled")

        inv1 = _make_inventory(db, product1.id, Decimal("100"), Decimal("40"))
        inv2 = _make_inventory(db, product2.id, Decimal("100"), Decimal("500"))

        # inv1 in sync: 40 reserved
        _make_reservation_txn(db, product1.id, inv1.location_id, po1.id, Decimal("40"))
        # inv2 drifted: 0 ledger, 500 stored
        # (no reservation transactions for product2)

        report = get_allocation_reconciliation_report(db, drifted_only=True)
        inv1_rows = [d for d in report.drift_items if d.inventory_id == inv1.id]
        inv2_rows = [d for d in report.drift_items if d.inventory_id == inv2.id]
        assert not inv1_rows  # in-sync row filtered out
        assert len(inv2_rows) == 1
        assert inv2_rows[0].has_drift


# =============================================================================
# 3. get_allocation_reconciliation_report — stranded detection
# =============================================================================

class TestStrandedAllocationDetection:
    """Stranded = positive net reservation + terminal or deleted PO."""

    def test_stranded_terminal_status(self, db, make_product, make_production_order):
        """Cancelled PO with remaining reservations appears in stranded_items."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="cancelled")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("50"))

        # Partial release: 50 reserved, 10 released → 40 stranded
        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("50"))
        _make_reservation_txn(
            db, product.id, inv.location_id, po.id, Decimal("10"), "reservation_release"
        )

        report = get_allocation_reconciliation_report(db)
        stranded = [s for s in report.stranded_items if s.production_order_id == po.id]
        assert len(stranded) == 1
        assert stranded[0].stranded_reason == "terminal_status"
        assert stranded[0].net_reserved == Decimal("40")
        assert stranded[0].status == "cancelled"

    def test_complete_po_stranded(self, db, make_product, make_production_order):
        """Complete PO with remaining reservations is also stranded."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="complete")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("30"))

        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("30"))

        report = get_allocation_reconciliation_report(db)
        stranded = [s for s in report.stranded_items if s.production_order_id == po.id]
        assert len(stranded) == 1
        assert stranded[0].status == "complete"

    def test_live_po_not_stranded(self, db, make_product, make_production_order):
        """Live (in_progress) PO with reservations is NOT stranded."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="in_progress")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("60"))

        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("60"))

        report = get_allocation_reconciliation_report(db)
        stranded = [s for s in report.stranded_items if s.production_order_id == po.id]
        assert not stranded

    def test_fully_released_not_stranded(self, db, make_product, make_production_order):
        """Cancelled PO that was fully released is not stranded."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="cancelled")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("0"))

        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("50"))
        _make_reservation_txn(
            db, product.id, inv.location_id, po.id, Decimal("50"), "reservation_release"
        )

        report = get_allocation_reconciliation_report(db)
        stranded = [s for s in report.stranded_items if s.production_order_id == po.id]
        assert not stranded

    def test_deleted_po_stranded(self, db, make_product):
        """Reservation for a non-existent PO id appears as stranded (order_missing)."""
        product = make_product()
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("25"))
        ghost_po_id = 999999

        _make_reservation_txn(db, product.id, inv.location_id, ghost_po_id, Decimal("25"))

        report = get_allocation_reconciliation_report(db)
        stranded = [s for s in report.stranded_items if s.production_order_id == ghost_po_id]
        assert len(stranded) == 1
        assert stranded[0].stranded_reason == "order_missing"


# =============================================================================
# 4. release_stranded_allocations — repair path
# =============================================================================

class TestReleaseStrandedAllocations:
    """Repair action: releases net reservations for terminal/deleted POs."""

    def test_release_cancelled_po(self, db, make_product, make_production_order):
        """Release stranded allocations for a cancelled PO."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="cancelled")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("50"))

        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("50"))

        result = release_stranded_allocations(db, po.id, "test@filaops.dev")

        assert result["total_released_items"] == 1
        assert not result["errors"]
        assert len(result["releases"]) == 1
        assert result["releases"][0]["quantity_released"] == 50.0

        # Verify inventory updated
        db.refresh(inv)
        assert inv.allocated_quantity == Decimal("0")

    def test_release_complete_po(self, db, make_product, make_production_order):
        """Release stranded allocations for a complete PO."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="complete")
        inv = _make_inventory(db, product.id, Decimal("200"), Decimal("75"))

        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("75"))

        result = release_stranded_allocations(db, po.id, "staff@test.dev")

        assert result["total_released_items"] == 1
        assert result["releases"][0]["new_allocated"] == 0.0

    def test_partial_release_only_net_positive(self, db, make_product, make_production_order):
        """Only the net-positive amount is released (partially released PO)."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="cancelled")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("30"))

        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("50"))
        _make_reservation_txn(
            db, product.id, inv.location_id, po.id, Decimal("20"), "reservation_release"
        )
        # Net = 30 remaining

        result = release_stranded_allocations(db, po.id, "staff@test.dev")

        assert result["releases"][0]["quantity_released"] == 30.0
        db.refresh(inv)
        assert inv.allocated_quantity == Decimal("0")

    def test_live_po_rejected(self, db, make_product, make_production_order):
        """Attempting to repair a live (in_progress) PO returns an error."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="in_progress")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("60"))
        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("60"))

        result = release_stranded_allocations(db, po.id, "staff@test.dev")

        assert len(result["errors"]) == 1
        assert "not a terminal status" in result["errors"][0]
        assert result["total_released_items"] == 0

        # Inventory unchanged
        db.refresh(inv)
        assert inv.allocated_quantity == Decimal("60")

    def test_release_deleted_po(self, db, make_product):
        """Release for a non-existent PO id works (order_missing path)."""
        product = make_product()
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("25"))
        ghost_po_id = 888888

        _make_reservation_txn(db, product.id, inv.location_id, ghost_po_id, Decimal("25"))

        result = release_stranded_allocations(db, ghost_po_id, "staff@test.dev")

        assert result["total_released_items"] == 1
        assert not result["errors"]
        db.refresh(inv)
        assert inv.allocated_quantity == Decimal("0")

    def test_idempotent_already_released(self, db, make_product, make_production_order):
        """Calling repair on a fully-released PO is a no-op (no errors, 0 releases)."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="cancelled")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("0"))

        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("40"))
        _make_reservation_txn(
            db, product.id, inv.location_id, po.id, Decimal("40"), "reservation_release"
        )

        result = release_stranded_allocations(db, po.id, "staff@test.dev")

        assert result["total_released_items"] == 0
        assert not result["errors"]

    def test_audit_transaction_created(self, db, make_product, make_production_order):
        """A reservation_release audit transaction is written after repair."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="cancelled")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("35"))

        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("35"))

        before_count = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_id == po.id,
            InventoryTransaction.transaction_type == "reservation_release",
        ).count()

        release_stranded_allocations(db, po.id, "auditor@test.dev")

        after_count = db.query(InventoryTransaction).filter(
            InventoryTransaction.reference_id == po.id,
            InventoryTransaction.transaction_type == "reservation_release",
        ).count()
        assert after_count == before_count + 1


# =============================================================================
# 5. Terminal-state release verification (via service layer calls)
# =============================================================================

class TestTerminalStateReleases:
    """Verify every terminal path calls release_production_reservations."""

    def test_cancel_releases_reservations(self, db, make_product, make_production_order):
        """cancel_production_order releases reservations before setting cancelled."""
        from app.services.production_order_service import cancel_production_order
        from app.services.inventory_service import reserve_production_materials
        from app.models.bom import BOM, BOMLine

        product_fg = make_product(item_type="finished_good", unit="EA", procurement_type="make")
        product_rm = make_product(item_type="supply", unit="EA")

        # Setup BOM
        bom = BOM(product_id=product_fg.id, active=True, name="Test BOM")
        db.add(bom)
        db.flush()
        bom_line = BOMLine(
            bom_id=bom.id,
            component_id=product_rm.id,
            quantity=Decimal("5"),
            unit="EA",
            consume_stage="production",
            is_cost_only=False,
        )
        db.add(bom_line)
        db.flush()

        inv = _make_inventory(db, product_rm.id, Decimal("100"), Decimal("0"))

        po = make_production_order(product_id=product_fg.id, status="released", quantity=2)

        # Reserve materials
        reserve_production_materials(db, po, "test@filaops.dev")
        db.flush()

        db.refresh(inv)
        assert inv.allocated_quantity > Decimal("0"), "Should have reserved materials"

        # Cancel should release
        cancel_production_order(db, po.id, "test@filaops.dev", notes="Test cancel")
        db.flush()

        db.refresh(inv)
        assert inv.allocated_quantity == Decimal("0"), (
            "cancel_production_order must release reservations"
        )

    def test_delete_draft_releases_reservations(self, db, make_product, make_production_order):
        """delete_production_order (draft only) releases reservations."""
        from app.services.production_order_service import delete_production_order

        product_fg = make_product(item_type="finished_good", unit="EA", procurement_type="make")
        product_rm = make_product(item_type="supply", unit="EA")
        inv = _make_inventory(db, product_rm.id, Decimal("100"), Decimal("40"))

        po = make_production_order(product_id=product_fg.id, status="draft")

        # Manually inject a reservation (simulating a previously-reserved draft)
        _make_reservation_txn(db, product_rm.id, inv.location_id, po.id, Decimal("40"))

        delete_production_order(db, po.id)
        db.flush()

        db.refresh(inv)
        # allocated_quantity should have been decremented
        assert inv.allocated_quantity == Decimal("0"), (
            "delete_production_order must release reservations"
        )


# =============================================================================
# 6. API endpoint tests
# =============================================================================

class TestReservationReconciliationAPI:
    """Integration tests for the admin reservation reconciliation endpoints."""

    def test_get_reconciliation_returns_200(self, client):
        response = client.get("/api/v1/admin/inventory/reservations/reconciliation")
        assert response.status_code == 200
        data = response.json()
        assert "drift_items" in data
        assert "stranded_items" in data
        assert "total_inventory_rows" in data
        assert "stranded_po_count" in data

    def test_get_reconciliation_drifted_only(self, client):
        response = client.get(
            "/api/v1/admin/inventory/reservations/reconciliation?drifted_only=true"
        )
        assert response.status_code == 200
        data = response.json()
        # All returned drift_items should have has_drift == True
        for item in data["drift_items"]:
            assert item["has_drift"] is True

    def test_repair_requires_confirm_true(self, client):
        """POST repair with confirm=false must return 400."""
        response = client.post(
            "/api/v1/admin/inventory/reservations/repair/1",
            json={"confirm": False, "reason": "test"},
        )
        assert response.status_code == 400

    def test_repair_live_po_returns_errors(self, client, db, make_product, make_production_order):
        """Repair a live PO via API returns errors list (not 4xx)."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="released")
        inv = _make_inventory(db, product.id, Decimal("50"), Decimal("30"))
        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("30"))
        db.commit()

        response = client.post(
            f"/api/v1/admin/inventory/reservations/repair/{po.id}",
            json={"confirm": True, "reason": "test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["errors"]) > 0
        assert data["total_released_items"] == 0

    def test_repair_cancelled_po_succeeds(self, client, db, make_product, make_production_order):
        """Repair a cancelled PO with stranded reservations succeeds via API."""
        product = make_product()
        po = make_production_order(product_id=product.id, status="cancelled")
        inv = _make_inventory(db, product.id, Decimal("100"), Decimal("45"))
        _make_reservation_txn(db, product.id, inv.location_id, po.id, Decimal("45"))
        db.commit()

        response = client.post(
            f"/api/v1/admin/inventory/reservations/repair/{po.id}",
            json={"confirm": True, "reason": "Clearing stranded allocation from test"},
        )
        assert response.status_code == 200
        data = response.json()
        assert not data["errors"]
        assert data["total_released_items"] == 1
        assert data["releases"][0]["new_allocated"] == 0.0
