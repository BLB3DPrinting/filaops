"""
Tests for supply_netting.get_projected_available and compute_quantity_short.

Covers:
- No inventory + no POs  → zeros throughout
- On-hand only (no POs)
- Open POs add to projected balance
- Fully-received PO lines are excluded
- Closed/cancelled/received PO statuses are excluded
- Multiple open PO lines are summed
- compute_quantity_short: short projected vs short now vs fully covered

HARD-6: These tests are the canonical verification that all three shortage-
calculation sites (sales_order_service, blocking_issues, production_order_service)
will net correctly once they call get_projected_available.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.inventory import Inventory
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine

from app.services.supply_netting import (
    compute_quantity_short,
    get_projected_available,
    get_projected_available_bulk,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid():
    return uuid.uuid4().hex[:8]


def _make_inventory(db, product_id, on_hand, allocated=Decimal("0"), location_id=1):
    inv = Inventory(
        product_id=product_id,
        location_id=location_id,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


def _make_po_with_line(
    db,
    vendor_id,
    product_id,
    qty_ordered,
    qty_received=Decimal("0"),
    status="ordered",
    expected_date=None,
):
    po = PurchaseOrder(
        po_number=f"PO-SN-{_uid()}",
        vendor_id=vendor_id,
        status=status,
        created_by="1",
        expected_date=expected_date,
    )
    db.add(po)
    db.flush()
    pol = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=product_id,
        line_number=1,
        quantity_ordered=qty_ordered,
        quantity_received=qty_received,
        unit_cost=Decimal("1.00"),
        line_total=qty_ordered * Decimal("1.00"),
    )
    db.add(pol)
    db.flush()
    return po, pol


# ---------------------------------------------------------------------------
# get_projected_available
# ---------------------------------------------------------------------------

class TestGetProjectedAvailable:
    """get_projected_available returns correct on_hand, available, incoming, projected."""

    def test_no_inventory_no_pos_all_zeros(self, db, make_product):
        product = make_product()
        result = get_projected_available(db, product.id)
        assert result.on_hand == Decimal("0")
        assert result.allocated == Decimal("0")
        assert result.available == Decimal("0")
        assert result.incoming_qty == Decimal("0")
        assert result.projected == Decimal("0")
        assert result.details == []
        assert result.best_detail is None

    def test_on_hand_only(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, Decimal("200"), allocated=Decimal("50"))
        result = get_projected_available(db, product.id)
        assert result.on_hand == Decimal("200")
        assert result.allocated == Decimal("50")
        assert result.available == Decimal("150")
        assert result.incoming_qty == Decimal("0")
        assert result.projected == Decimal("150")

    def test_open_po_adds_to_projected(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("100"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("500"), qty_received=Decimal("0"),
            status="ordered",
        )
        result = get_projected_available(db, product.id)
        assert result.available == Decimal("100")
        assert result.incoming_qty == Decimal("500")
        assert result.projected == Decimal("600")
        assert len(result.details) == 1

    def test_partially_received_po_only_counts_remainder(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("50"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("1000"), qty_received=Decimal("300"),
            status="shipped",
        )
        result = get_projected_available(db, product.id)
        assert result.incoming_qty == Decimal("700")
        assert result.projected == Decimal("750")

    def test_fully_received_po_excluded(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("100"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("500"), qty_received=Decimal("500"),
            status="ordered",
        )
        result = get_projected_available(db, product.id)
        assert result.incoming_qty == Decimal("0")
        assert result.projected == Decimal("100")

    def test_closed_po_excluded(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("100"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("500"), qty_received=Decimal("0"),
            status="closed",
        )
        result = get_projected_available(db, product.id)
        assert result.incoming_qty == Decimal("0")

    def test_cancelled_po_excluded(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("500"), qty_received=Decimal("0"),
            status="cancelled",
        )
        result = get_projected_available(db, product.id)
        assert result.incoming_qty == Decimal("0")

    def test_received_status_po_excluded(self, db, make_product, make_vendor):
        """PO with status='received' is NOT open — stock was already received."""
        product = make_product()
        vendor = make_vendor()
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("500"), qty_received=Decimal("0"),
            status="received",
        )
        result = get_projected_available(db, product.id)
        assert result.incoming_qty == Decimal("0")

    def test_multiple_open_pos_summed(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("50"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("200"), qty_received=Decimal("0"),
            status="ordered",
        )
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("300"), qty_received=Decimal("0"),
            status="shipped",
        )
        result = get_projected_available(db, product.id)
        assert result.incoming_qty == Decimal("500")
        assert result.projected == Decimal("550")
        assert len(result.details) == 2

    def test_details_sorted_by_expected_date_asc(self, db, make_product, make_vendor):
        """Details are ordered earliest expected date first."""
        product = make_product()
        vendor = make_vendor()
        today = date.today()
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("100"), qty_received=Decimal("0"),
            status="ordered",
            expected_date=today + timedelta(days=14),
        )
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("200"), qty_received=Decimal("0"),
            status="ordered",
            expected_date=today + timedelta(days=3),
        )
        result = get_projected_available(db, product.id)
        assert result.details[0].expected_date == today + timedelta(days=3)
        assert result.best_detail.expected_date == today + timedelta(days=3)

    def test_draft_po_is_counted(self, db, make_product, make_vendor):
        """Draft POs are open supply (ordered at supplier but not confirmed)."""
        product = make_product()
        vendor = make_vendor()
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("400"), qty_received=Decimal("0"),
            status="draft",
        )
        result = get_projected_available(db, product.id)
        assert result.incoming_qty == Decimal("400")

    def test_is_short_now_and_is_short_projected_properties(self, db, make_product, make_vendor):
        """is_short_now and is_short_projected reflect correct states."""
        product = make_product()
        vendor = make_vendor()
        # available = -10 (more allocated than on-hand), incoming = 20
        _make_inventory(db, product.id, Decimal("10"), allocated=Decimal("20"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("20"), qty_received=Decimal("0"),
            status="ordered",
        )
        result = get_projected_available(db, product.id)
        # available = 10 - 20 = -10
        assert result.available == Decimal("-10")
        assert result.is_short_now is True
        # projected = -10 + 20 = 10
        assert result.projected == Decimal("10")
        assert result.is_short_projected is False

    def test_ignores_other_products(self, db, make_product, make_vendor):
        p1 = make_product()
        p2 = make_product()
        vendor = make_vendor()
        _make_inventory(db, p1.id, Decimal("100"))
        _make_po_with_line(
            db, vendor.id, p2.id,
            qty_ordered=Decimal("500"), qty_received=Decimal("0"),
            status="ordered",
        )
        result = get_projected_available(db, p1.id)
        # p2 PO should not affect p1
        assert result.incoming_qty == Decimal("0")
        assert result.projected == Decimal("100")


# ---------------------------------------------------------------------------
# compute_quantity_short
# ---------------------------------------------------------------------------

class TestComputeQuantityShort:
    """compute_quantity_short uses projected balance, not current available."""

    def test_no_shortage_when_projected_covers(self, db, make_product, make_vendor):
        """
        SHORT NOW but covered by incoming PO → projected shortage = 0.
        This is the double-order trap: without HARD-6 fix, qty_short would be
        positive here causing unnecessary reorders.
        """
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("10"))  # only 10 on hand
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("500"), qty_received=Decimal("0"),
            status="ordered",
        )
        proj = get_projected_available(db, product.id)
        # require 200 — more than the 10 on hand, but well within the 510 projected
        short = compute_quantity_short(Decimal("200"), proj)
        assert short == Decimal("0"), (
            "Projected balance covers the requirement; quantity_short must be 0"
        )

    def test_shortage_when_po_still_insufficient(self, db, make_product, make_vendor):
        """
        Required > projected: there is a real net shortage even with incoming POs.
        """
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("0"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("100"), qty_received=Decimal("0"),
            status="ordered",
        )
        proj = get_projected_available(db, product.id)
        # require 300, projected = 100
        short = compute_quantity_short(Decimal("300"), proj)
        assert short == Decimal("200")

    def test_shortage_with_no_incoming_po(self, db, make_product):
        """
        Required > available with zero incoming supply → full shortage.
        """
        product = make_product()
        _make_inventory(db, product.id, Decimal("50"))
        proj = get_projected_available(db, product.id)
        short = compute_quantity_short(Decimal("200"), proj)
        assert short == Decimal("150")

    def test_zero_shortage_when_all_available(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, Decimal("500"))
        proj = get_projected_available(db, product.id)
        short = compute_quantity_short(Decimal("100"), proj)
        assert short == Decimal("0")

    def test_never_negative(self, db, make_product):
        """Surplus supply must not produce a negative shortage."""
        product = make_product()
        _make_inventory(db, product.id, Decimal("1000"))
        proj = get_projected_available(db, product.id)
        short = compute_quantity_short(Decimal("10"), proj)
        assert short >= Decimal("0")


# ---------------------------------------------------------------------------
# get_projected_available_bulk (N+1 batch path)
# ---------------------------------------------------------------------------

class TestGetProjectedAvailableBulk:
    """Batch version returns the same values as per-product calls, in two queries."""

    def test_empty_list_returns_empty_dict(self, db):
        result = get_projected_available_bulk(db, [])
        assert result == {}

    def test_missing_product_returns_zeros(self, db, make_product):
        product = make_product()
        # No inventory row, no PO
        result = get_projected_available_bulk(db, [product.id])
        assert product.id in result
        a = result[product.id]
        assert a.on_hand == Decimal("0")
        assert a.allocated == Decimal("0")
        assert a.incoming_qty == Decimal("0")
        assert a.projected == Decimal("0")

    def test_matches_single_call_no_pos(self, db, make_product):
        product = make_product()
        _make_inventory(db, product.id, Decimal("300"), allocated=Decimal("50"))

        single = get_projected_available(db, product.id)
        bulk = get_projected_available_bulk(db, [product.id])

        a = bulk[product.id]
        assert a.on_hand == single.on_hand
        assert a.allocated == single.allocated
        assert a.available == single.available
        assert a.incoming_qty == single.incoming_qty
        assert a.projected == single.projected

    def test_matches_single_call_with_open_po(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("100"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("400"), qty_received=Decimal("50"),
            status="ordered",
        )

        single = get_projected_available(db, product.id)
        bulk = get_projected_available_bulk(db, [product.id])

        a = bulk[product.id]
        assert a.on_hand == single.on_hand
        assert a.incoming_qty == single.incoming_qty
        assert a.projected == single.projected
        assert len(a.details) == len(single.details)

    def test_multiple_products_in_one_call(self, db, make_product, make_vendor):
        p1 = make_product()
        p2 = make_product()
        p3 = make_product()
        vendor = make_vendor()

        _make_inventory(db, p1.id, Decimal("50"), allocated=Decimal("10"))
        _make_inventory(db, p2.id, Decimal("200"))
        # p3 has no inventory
        _make_po_with_line(
            db, vendor.id, p2.id,
            qty_ordered=Decimal("100"), qty_received=Decimal("0"),
            status="shipped",
        )

        result = get_projected_available_bulk(db, [p1.id, p2.id, p3.id])
        assert set(result.keys()) == {p1.id, p2.id, p3.id}

        assert result[p1.id].on_hand == Decimal("50")
        assert result[p1.id].allocated == Decimal("10")
        assert result[p1.id].available == Decimal("40")
        assert result[p1.id].incoming_qty == Decimal("0")

        assert result[p2.id].on_hand == Decimal("200")
        assert result[p2.id].incoming_qty == Decimal("100")
        assert result[p2.id].projected == Decimal("300")  # available(200) + incoming(100)

        assert result[p3.id].on_hand == Decimal("0")
        assert result[p3.id].projected == Decimal("0")

    def test_fully_received_po_excluded_in_bulk(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("100"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("500"), qty_received=Decimal("500"),
            status="ordered",
        )
        result = get_projected_available_bulk(db, [product.id])
        assert result[product.id].incoming_qty == Decimal("0")

    def test_closed_and_cancelled_pos_excluded_in_bulk(self, db, make_product, make_vendor):
        product = make_product()
        vendor = make_vendor()
        _make_inventory(db, product.id, Decimal("50"))
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("200"), qty_received=Decimal("0"),
            status="closed",
        )
        _make_po_with_line(
            db, vendor.id, product.id,
            qty_ordered=Decimal("300"), qty_received=Decimal("0"),
            status="cancelled",
        )
        result = get_projected_available_bulk(db, [product.id])
        assert result[product.id].incoming_qty == Decimal("0")
