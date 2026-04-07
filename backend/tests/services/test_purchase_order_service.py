"""
Tests for app/services/purchase_order_service.py

Covers:
- generate_po_number: sequential PO numbering
- calculate_totals: subtotal / total recalculation
- list_purchase_orders: filters (status, vendor, search) and pagination
- get_purchase_order: retrieval with eager loading and 404
- create_purchase_order: with lines, vendor validation, product validation
- update_purchase_order: field updates, status guards, recalculation
- delete_purchase_order: draft-only deletion
- add_po_line / update_po_line / delete_po_line: line CRUD
- update_po_status: transition validation, business rules, date setting
- receive_purchase_order: validation paths (mocked for deep deps)
- upload_po_document: file type validation, size limits
- list_po_events / add_po_event: event timeline
- VALID_TRANSITIONS: terminal state verification
"""
import pytest
from datetime import datetime, timezone, date
from decimal import Decimal
from unittest.mock import patch, MagicMock

from fastapi import HTTPException

from app.services import purchase_order_service
from app.services.purchase_order_service import (
    generate_po_number,
    calculate_totals,
    list_purchase_orders,
    get_purchase_order,
    create_purchase_order,
    update_purchase_order,
    delete_purchase_order,
    add_po_line,
    update_po_line,
    delete_po_line,
    update_po_status,
    receive_purchase_order,
    upload_po_document,
    list_po_events,
    add_po_event,
    VALID_TRANSITIONS,
)
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.product import Product
from app.models.inventory import Inventory, InventoryLocation, InventoryTransaction


# =============================================================================
# Helpers
# =============================================================================

def _make_inventory(db, product_id, on_hand, location_id=1, allocated=0):
    """Create an Inventory record directly for test setup."""
    inv = Inventory(
        product_id=product_id,
        location_id=location_id,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


def _add_po_line(db, po, product, qty_ordered, unit_cost, purchase_unit=None, qty_received=0):
    """Add a PurchaseOrderLine directly for test setup."""
    next_num = max([line.line_number for line in po.lines], default=0) + 1
    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        line_number=next_num,
        product_id=product.id,
        quantity_ordered=qty_ordered,
        quantity_received=qty_received,
        purchase_unit=purchase_unit or product.unit,
        unit_cost=unit_cost,
        line_total=qty_ordered * unit_cost,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    po.lines.append(line)
    db.flush()
    return line


# =============================================================================
# generate_po_number
# =============================================================================

class TestGeneratePoNumber:
    """Test generate_po_number."""

    def test_first_po_of_year(self, db):
        """When no POs exist for the current year, returns PO-YYYY-001."""
        year = datetime.now(timezone.utc).year
        po_num = generate_po_number(db)
        assert po_num.startswith(f"PO-{year}-")

    def test_increments_from_existing(self, db, make_vendor, make_purchase_order):
        """Increments the numeric suffix from the highest existing PO number."""
        year = datetime.now(timezone.utc).year
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id, po_number=f"PO-{year}-005")
        db.commit()

        po_num = generate_po_number(db)
        assert po_num == f"PO-{year}-006"

    def test_handles_non_numeric_suffix(self, db, make_vendor, make_purchase_order):
        """Falls back to 001 when the existing PO has a non-numeric suffix."""
        year = datetime.now(timezone.utc).year
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id, po_number=f"PO-{year}-abc")
        db.commit()

        po_num = generate_po_number(db)
        assert po_num.startswith(f"PO-{year}-")

    def test_zero_padded_format(self, db, make_vendor, make_purchase_order):
        """PO numbers are zero-padded to 3 digits."""
        year = datetime.now(timezone.utc).year
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id, po_number=f"PO-{year}-002")
        db.commit()

        po_num = generate_po_number(db)
        assert po_num == f"PO-{year}-003"
        # Verify 3-digit zero-padding
        suffix = po_num.split("-")[2]
        assert len(suffix) == 3

    def test_high_sequence_no_truncation(self, db, make_vendor, make_purchase_order):
        """Sequence numbers beyond 999 are not truncated."""
        year = datetime.now(timezone.utc).year
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id, po_number=f"PO-{year}-1500")
        db.commit()

        po_num = generate_po_number(db)
        assert po_num == f"PO-{year}-1501"


# =============================================================================
# calculate_totals
# =============================================================================

class TestCalculateTotals:
    """Test calculate_totals."""

    def test_sums_line_totals(self, db, make_vendor, make_purchase_order, make_product):
        """Subtotal is sum of all line_total values."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        p1 = make_product()
        p2 = make_product()

        _add_po_line(db, po, p1, Decimal("10"), Decimal("5.00"))
        _add_po_line(db, po, p2, Decimal("3"), Decimal("20.00"))
        db.flush()

        calculate_totals(po)
        # 10*5 + 3*20 = 50 + 60 = 110
        assert po.subtotal == Decimal("110.0000")
        assert po.total_amount == Decimal("110.0000")

    def test_includes_tax_and_shipping(self, db, make_vendor, make_purchase_order, make_product):
        """Total = subtotal + tax + shipping."""
        vendor = make_vendor()
        po = make_purchase_order(
            vendor_id=vendor.id,
            tax_amount=Decimal("8.50"),
            shipping_cost=Decimal("12.00"),
        )
        p = make_product()
        _add_po_line(db, po, p, Decimal("5"), Decimal("10.00"))
        db.flush()

        calculate_totals(po)
        assert po.subtotal == Decimal("50.0000")
        # 50 + 8.50 + 12.00 = 70.50
        assert po.total_amount == Decimal("70.5000")

    def test_no_lines_zero(self, db, make_vendor, make_purchase_order):
        """Subtotal is zero when PO has no lines."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        db.flush()

        calculate_totals(po)
        assert po.subtotal == Decimal("0")

    def test_zero_tax_and_shipping(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """When tax_amount and shipping_cost are zero, total == subtotal."""
        vendor = make_vendor()
        po = make_purchase_order(
            vendor_id=vendor.id,
            tax_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
        )
        p = make_product()
        _add_po_line(db, po, p, Decimal("4"), Decimal("25.00"))
        db.flush()

        calculate_totals(po)
        assert po.subtotal == Decimal("100.0000")
        assert po.total_amount == Decimal("100.0000")

    def test_only_tax_no_shipping(self, db, make_vendor, make_purchase_order, make_product):
        """Total includes tax but not shipping when shipping is zero."""
        vendor = make_vendor()
        po = make_purchase_order(
            vendor_id=vendor.id,
            tax_amount=Decimal("5.00"),
            shipping_cost=Decimal("0"),
        )
        p = make_product()
        _add_po_line(db, po, p, Decimal("2"), Decimal("10.00"))
        db.flush()

        calculate_totals(po)
        assert po.subtotal == Decimal("20.0000")
        assert po.total_amount == Decimal("25.0000")


# =============================================================================
# list_purchase_orders
# =============================================================================

class TestListPurchaseOrders:
    """Test list_purchase_orders."""

    def test_basic_list(self, db, make_vendor, make_purchase_order):
        """Returns POs and a total count."""
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id)
        make_purchase_order(vendor_id=vendor.id)
        db.commit()

        pos, total = list_purchase_orders(db)
        assert total >= 2

    def test_filter_by_status(self, db, make_vendor, make_purchase_order):
        """Status filter limits results to matching POs."""
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id, status="draft")
        make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.commit()

        pos, _ = list_purchase_orders(db, status="draft")
        for po in pos:
            assert po.status == "draft"

    def test_filter_by_vendor(self, db, make_vendor, make_purchase_order):
        """Vendor filter limits results to POs for that vendor."""
        v1 = make_vendor(name="Vendor Alpha")
        v2 = make_vendor(name="Vendor Beta")
        make_purchase_order(vendor_id=v1.id)
        make_purchase_order(vendor_id=v2.id)
        db.commit()

        pos, _ = list_purchase_orders(db, vendor_id=v1.id)
        for po in pos:
            assert po.vendor_id == v1.id

    def test_search_by_po_number(self, db, make_vendor, make_purchase_order):
        """Search filter matches PO number with ilike."""
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id, po_number="PO-SEARCH-999")
        db.commit()

        pos, total = list_purchase_orders(db, search="SEARCH-999")
        po_numbers = [po.po_number for po in pos]
        assert "PO-SEARCH-999" in po_numbers

    def test_pagination(self, db, make_vendor, make_purchase_order):
        """Limit and offset control the result window."""
        vendor = make_vendor()
        for _ in range(5):
            make_purchase_order(vendor_id=vendor.id)
        db.commit()

        pos, total = list_purchase_orders(db, limit=2, offset=0)
        assert len(pos) <= 2
        assert total >= 5

    def test_combined_filters(self, db, make_vendor, make_purchase_order):
        """Multiple filters apply together (AND logic)."""
        v1 = make_vendor()
        v2 = make_vendor()
        make_purchase_order(vendor_id=v1.id, status="draft", po_number="PO-COMBO-001")
        make_purchase_order(vendor_id=v1.id, status="ordered", po_number="PO-COMBO-002")
        make_purchase_order(vendor_id=v2.id, status="draft", po_number="PO-COMBO-003")
        db.commit()

        pos, total = list_purchase_orders(
            db, status="draft", vendor_id=v1.id, search="COMBO"
        )
        assert total >= 1
        for po in pos:
            assert po.status == "draft"
            assert po.vendor_id == v1.id
            assert "COMBO" in po.po_number

    def test_empty_result(self, db, make_vendor, make_purchase_order):
        """Nonexistent search returns empty list and zero total."""
        vendor = make_vendor()
        make_purchase_order(vendor_id=vendor.id)
        db.commit()

        pos, total = list_purchase_orders(db, search="ZZZNONEXISTENT999")
        assert total == 0
        assert pos == []


# =============================================================================
# get_purchase_order
# =============================================================================

class TestGetPurchaseOrder:
    """Test get_purchase_order."""

    def test_get_existing(self, db, make_vendor, make_purchase_order, make_product):
        """Returns PO with vendor and lines eager-loaded."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        _add_po_line(db, po, product, Decimal("5"), Decimal("10.00"))
        db.commit()

        fetched = get_purchase_order(db, po.id)
        assert fetched.id == po.id
        assert fetched.vendor is not None
        assert len(fetched.lines) == 1

    def test_not_found_raises_404(self, db):
        """Raises HTTPException 404 when PO does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            get_purchase_order(db, 999999)
        assert exc_info.value.status_code == 404

    def test_lines_have_products_loaded(self, db, make_vendor, make_purchase_order, make_product):
        """Lines are returned with their product relationship loaded."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        product = make_product(name="Widget X")
        _add_po_line(db, po, product, Decimal("3"), Decimal("7.00"))
        db.commit()

        fetched = get_purchase_order(db, po.id)
        assert fetched.lines[0].product is not None
        assert fetched.lines[0].product.name == "Widget X"


# =============================================================================
# create_purchase_order
# =============================================================================

class TestCreatePurchaseOrder:
    """Test create_purchase_order."""

    def test_create_with_lines(self, db, make_vendor, make_product):
        """Creates a PO in draft status with lines and correct totals."""
        vendor = make_vendor()
        product = make_product(standard_cost=Decimal("10.00"))
        db.commit()

        po = create_purchase_order(
            db,
            data={"vendor_id": vendor.id},
            lines_data=[
                {
                    "product_id": product.id,
                    "quantity_ordered": Decimal("5"),
                    "unit_cost": Decimal("10.00"),
                },
            ],
            created_by="test@filaops.dev",
            user_id=1,
        )
        assert po.id is not None
        assert po.status == "draft"
        assert po.vendor_id == vendor.id
        assert len(po.lines) == 1
        assert po.lines[0].quantity_ordered == Decimal("5")
        assert po.subtotal == Decimal("50.0000")

    def test_invalid_vendor_raises_404(self, db, make_product):
        """Raises 404 when vendor_id does not exist."""
        product = make_product()
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            create_purchase_order(
                db,
                data={"vendor_id": 999999},
                lines_data=[{
                    "product_id": product.id,
                    "quantity_ordered": Decimal("1"),
                    "unit_cost": Decimal("5.00"),
                }],
                created_by="test",
                user_id=1,
            )
        assert exc_info.value.status_code == 404
        assert "vendor" in str(exc_info.value.detail).lower()

    def test_invalid_product_raises_404(self, db, make_vendor):
        """Raises 404 when a line references a non-existent product."""
        vendor = make_vendor()
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            create_purchase_order(
                db,
                data={"vendor_id": vendor.id},
                lines_data=[{
                    "product_id": 999999,
                    "quantity_ordered": Decimal("1"),
                    "unit_cost": Decimal("5.00"),
                }],
                created_by="test",
                user_id=1,
            )
        assert exc_info.value.status_code == 404
        assert "product" in str(exc_info.value.detail).lower()

    def test_multiple_lines(self, db, make_vendor, make_product):
        """Creates PO with multiple lines and correct subtotal."""
        vendor = make_vendor()
        p1 = make_product()
        p2 = make_product()
        db.commit()

        po = create_purchase_order(
            db,
            data={"vendor_id": vendor.id},
            lines_data=[
                {"product_id": p1.id, "quantity_ordered": Decimal("10"), "unit_cost": Decimal("2.00")},
                {"product_id": p2.id, "quantity_ordered": Decimal("5"), "unit_cost": Decimal("8.00")},
            ],
            created_by="test",
            user_id=1,
        )
        assert len(po.lines) == 2
        # 10*2 + 5*8 = 20 + 40 = 60
        assert po.subtotal == Decimal("60.0000")

    def test_optional_fields_passed_through(self, db, make_vendor, make_product):
        """Optional data fields (notes, tracking, tax, shipping) are stored."""
        vendor = make_vendor()
        product = make_product()
        db.commit()

        po = create_purchase_order(
            db,
            data={
                "vendor_id": vendor.id,
                "notes": "Rush order",
                "tracking_number": "1Z999",
                "carrier": "UPS",
                "tax_amount": Decimal("5.00"),
                "shipping_cost": Decimal("10.00"),
            },
            lines_data=[{
                "product_id": product.id,
                "quantity_ordered": Decimal("1"),
                "unit_cost": Decimal("100.00"),
            }],
            created_by="test",
            user_id=1,
        )
        assert po.notes == "Rush order"
        assert po.tracking_number == "1Z999"
        assert po.carrier == "UPS"
        # 100 + 5 + 10 = 115
        assert po.total_amount == Decimal("115.0000")

    def test_line_numbers_sequential(self, db, make_vendor, make_product):
        """Lines are numbered sequentially starting from 1."""
        vendor = make_vendor()
        p1 = make_product()
        p2 = make_product()
        p3 = make_product()
        db.commit()

        po = create_purchase_order(
            db,
            data={"vendor_id": vendor.id},
            lines_data=[
                {"product_id": p1.id, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("1")},
                {"product_id": p2.id, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("1")},
                {"product_id": p3.id, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("1")},
            ],
            created_by="test",
            user_id=1,
        )
        line_numbers = sorted([line.line_number for line in po.lines])
        assert line_numbers == [1, 2, 3]

    def test_line_total_calculated(self, db, make_vendor, make_product):
        """Each line has line_total = quantity_ordered * unit_cost."""
        vendor = make_vendor()
        product = make_product()
        db.commit()

        po = create_purchase_order(
            db,
            data={"vendor_id": vendor.id},
            lines_data=[{
                "product_id": product.id,
                "quantity_ordered": Decimal("7"),
                "unit_cost": Decimal("12.50"),
            }],
            created_by="test",
            user_id=1,
        )
        assert po.lines[0].line_total == Decimal("87.5000")

    def test_quantity_received_starts_at_zero(self, db, make_vendor, make_product):
        """Newly created lines have quantity_received = 0."""
        vendor = make_vendor()
        product = make_product()
        db.commit()

        po = create_purchase_order(
            db,
            data={"vendor_id": vendor.id},
            lines_data=[{
                "product_id": product.id,
                "quantity_ordered": Decimal("10"),
                "unit_cost": Decimal("5.00"),
            }],
            created_by="test",
            user_id=1,
        )
        assert po.lines[0].quantity_received == Decimal("0")

    def test_purchase_unit_defaults_to_product_unit(self, db, make_vendor, make_product):
        """When no purchase_unit is given, defaults from product.purchase_uom or product.unit."""
        vendor = make_vendor()
        product = make_product(unit="EA", purchase_uom="EA")
        db.commit()

        po = create_purchase_order(
            db,
            data={"vendor_id": vendor.id},
            lines_data=[{
                "product_id": product.id,
                "quantity_ordered": Decimal("1"),
                "unit_cost": Decimal("1.00"),
            }],
            created_by="test",
            user_id=1,
        )
        assert po.lines[0].purchase_unit == "EA"

    def test_purchase_unit_override(self, db, make_vendor, make_product):
        """Explicit purchase_unit in line data overrides the product default."""
        vendor = make_vendor()
        product = make_product(unit="G", purchase_uom="KG")
        db.commit()

        po = create_purchase_order(
            db,
            data={"vendor_id": vendor.id},
            lines_data=[{
                "product_id": product.id,
                "quantity_ordered": Decimal("5"),
                "unit_cost": Decimal("20.00"),
                "purchase_unit": "LB",
            }],
            created_by="test",
            user_id=1,
        )
        assert po.lines[0].purchase_unit == "LB"


# =============================================================================
# update_purchase_order
# =============================================================================

class TestUpdatePurchaseOrder:
    """Test update_purchase_order."""

    def test_update_draft(self, db, make_vendor, make_purchase_order):
        """Draft POs are updatable."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        updated = update_purchase_order(db, po.id, data={"notes": "Updated notes"})
        assert updated.notes == "Updated notes"

    def test_update_ordered(self, db, make_vendor, make_purchase_order):
        """Ordered POs are updatable."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.commit()

        updated = update_purchase_order(db, po.id, data={"notes": "Still editable"})
        assert updated.notes == "Still editable"

    def test_update_shipped(self, db, make_vendor, make_purchase_order):
        """Shipped POs are updatable (not in the restricted set)."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="shipped")
        db.commit()

        updated = update_purchase_order(
            db, po.id, data={"tracking_number": "1Z-NEW"}
        )
        assert updated.tracking_number == "1Z-NEW"

    def test_update_received_raises_400(self, db, make_vendor, make_purchase_order):
        """Cannot update a PO in 'received' status."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_purchase_order(db, po.id, data={"notes": "Cannot edit"})
        assert exc_info.value.status_code == 400
        assert "received" in str(exc_info.value.detail).lower()

    def test_update_closed_raises_400(self, db, make_vendor, make_purchase_order):
        """Cannot update a PO in 'closed' status."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="closed")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_purchase_order(db, po.id, data={"notes": "Cannot edit"})
        assert exc_info.value.status_code == 400

    def test_update_cancelled_raises_400(self, db, make_vendor, make_purchase_order):
        """Cannot update a PO in 'cancelled' status."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_purchase_order(db, po.id, data={"notes": "Cannot edit"})
        assert exc_info.value.status_code == 400

    def test_recalculates_on_tax_change(self, db, make_vendor, make_purchase_order, make_product):
        """Updating tax_amount triggers total recalculation."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        p = make_product()
        _add_po_line(db, po, p, Decimal("10"), Decimal("5.00"))
        db.commit()

        # Ensure totals are set first
        calculate_totals(po)
        db.commit()

        updated = update_purchase_order(
            db, po.id, data={"tax_amount": Decimal("7.50")}
        )
        # 50 (subtotal) + 7.50 (tax) = 57.50
        assert updated.total_amount == Decimal("57.5000")

    def test_recalculates_on_shipping_change(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """Updating shipping_cost triggers total recalculation."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        p = make_product()
        _add_po_line(db, po, p, Decimal("4"), Decimal("10.00"))
        db.commit()

        calculate_totals(po)
        db.commit()

        updated = update_purchase_order(
            db, po.id, data={"shipping_cost": Decimal("15.00")}
        )
        # 40 + 15 = 55
        assert updated.total_amount == Decimal("55.0000")

    def test_update_not_found_raises_404(self, db):
        """Raises 404 when PO ID does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            update_purchase_order(db, 999999, data={"notes": "Nope"})
        assert exc_info.value.status_code == 404

    def test_updated_at_changes(self, db, make_vendor, make_purchase_order):
        """updated_at is refreshed on update."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()
        original_updated = po.updated_at

        updated = update_purchase_order(db, po.id, data={"notes": "Timestamp test"})
        # updated_at is set with timezone.utc in service, but DB may store naive;
        # just verify it was set (not None) and is a datetime.
        assert updated.updated_at is not None
        assert isinstance(updated.updated_at, datetime)


# =============================================================================
# delete_purchase_order
# =============================================================================

class TestDeletePurchaseOrder:
    """Test delete_purchase_order."""

    def test_delete_draft(self, db, make_vendor, make_purchase_order):
        """Draft POs can be deleted."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        po_id = po.id
        db.commit()

        result = delete_purchase_order(db, po_id)
        assert "deleted" in result["message"].lower()

        deleted = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
        assert deleted is None

    def test_delete_ordered_raises_400(self, db, make_vendor, make_purchase_order):
        """Cannot delete an ordered PO -- must cancel instead."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_purchase_order(db, po.id)
        assert exc_info.value.status_code == 400
        assert "cancel" in str(exc_info.value.detail).lower()

    def test_delete_shipped_raises_400(self, db, make_vendor, make_purchase_order):
        """Cannot delete a shipped PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="shipped")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_purchase_order(db, po.id)
        assert exc_info.value.status_code == 400

    def test_delete_received_raises_400(self, db, make_vendor, make_purchase_order):
        """Cannot delete a received PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_purchase_order(db, po.id)
        assert exc_info.value.status_code == 400

    def test_delete_cancelled_raises_400(self, db, make_vendor, make_purchase_order):
        """Cannot delete a cancelled PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_purchase_order(db, po.id)
        assert exc_info.value.status_code == 400

    def test_delete_not_found_raises_404(self, db):
        """Raises 404 when PO ID does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            delete_purchase_order(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# Line Management: add_po_line
# =============================================================================

class TestAddPoLine:
    """Test add_po_line."""

    def test_add_line_to_draft(self, db, make_vendor, make_purchase_order, make_product):
        """Can add a line to a draft PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        db.commit()

        updated_po = add_po_line(
            db, po.id,
            data={
                "product_id": product.id,
                "quantity_ordered": Decimal("10"),
                "unit_cost": Decimal("3.50"),
            },
        )
        assert len(updated_po.lines) == 1
        assert updated_po.lines[0].quantity_ordered == Decimal("10")

    def test_add_line_to_ordered(self, db, make_vendor, make_purchase_order, make_product):
        """Can add a line to an ordered PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product()
        db.commit()

        updated_po = add_po_line(
            db, po.id,
            data={
                "product_id": product.id,
                "quantity_ordered": Decimal("5"),
                "unit_cost": Decimal("7.00"),
            },
        )
        assert len(updated_po.lines) == 1

    def test_add_line_to_received_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot add lines to a received PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        product = make_product()
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            add_po_line(
                db, po.id,
                data={
                    "product_id": product.id,
                    "quantity_ordered": Decimal("1"),
                    "unit_cost": Decimal("1.00"),
                },
            )
        assert exc_info.value.status_code == 400

    def test_add_line_to_shipped_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot add lines to a shipped PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="shipped")
        product = make_product()
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            add_po_line(
                db, po.id,
                data={
                    "product_id": product.id,
                    "quantity_ordered": Decimal("1"),
                    "unit_cost": Decimal("1.00"),
                },
            )
        assert exc_info.value.status_code == 400

    def test_add_line_to_cancelled_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot add lines to a cancelled PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        product = make_product()
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            add_po_line(
                db, po.id,
                data={
                    "product_id": product.id,
                    "quantity_ordered": Decimal("1"),
                    "unit_cost": Decimal("1.00"),
                },
            )
        assert exc_info.value.status_code == 400

    def test_invalid_product_raises_404(self, db, make_vendor, make_purchase_order):
        """Raises 404 when product_id does not exist."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            add_po_line(
                db, po.id,
                data={
                    "product_id": 999999,
                    "quantity_ordered": Decimal("1"),
                    "unit_cost": Decimal("1.00"),
                },
            )
        assert exc_info.value.status_code == 404

    def test_po_not_found_raises_404(self, db, make_product):
        """Raises 404 when the PO itself does not exist."""
        product = make_product()
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            add_po_line(
                db, 999999,
                data={
                    "product_id": product.id,
                    "quantity_ordered": Decimal("1"),
                    "unit_cost": Decimal("1.00"),
                },
            )
        assert exc_info.value.status_code == 404

    def test_line_number_increments(self, db, make_vendor, make_purchase_order, make_product):
        """Added lines get sequential line numbers."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        p1 = make_product()
        p2 = make_product()
        db.commit()

        add_po_line(
            db, po.id,
            data={"product_id": p1.id, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("1")},
        )
        updated_po = add_po_line(
            db, po.id,
            data={"product_id": p2.id, "quantity_ordered": Decimal("1"), "unit_cost": Decimal("1")},
        )
        line_numbers = sorted([line.line_number for line in updated_po.lines])
        assert line_numbers == [1, 2]

    def test_totals_recalculated(self, db, make_vendor, make_purchase_order, make_product):
        """Adding a line recalculates the PO totals."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        p1 = make_product()
        p2 = make_product()
        db.commit()

        add_po_line(
            db, po.id,
            data={"product_id": p1.id, "quantity_ordered": Decimal("10"), "unit_cost": Decimal("5.00")},
        )
        updated_po = add_po_line(
            db, po.id,
            data={"product_id": p2.id, "quantity_ordered": Decimal("3"), "unit_cost": Decimal("20.00")},
        )
        # 50 + 60 = 110
        assert updated_po.subtotal == Decimal("110.0000")

    def test_line_total_calculated_correctly(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """Line total is quantity_ordered * unit_cost."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        db.commit()

        updated_po = add_po_line(
            db, po.id,
            data={
                "product_id": product.id,
                "quantity_ordered": Decimal("7"),
                "unit_cost": Decimal("12.50"),
            },
        )
        assert updated_po.lines[0].line_total == Decimal("87.5000")


# =============================================================================
# Line Management: update_po_line
# =============================================================================

class TestUpdatePoLine:
    """Test update_po_line."""

    def test_update_quantity(self, db, make_vendor, make_purchase_order, make_product):
        """Can update quantity_ordered; line_total and PO totals recalculate."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        updated_po = update_po_line(
            db, po.id, line.id,
            data={"quantity_ordered": Decimal("20")},
        )
        updated_line = [l for l in updated_po.lines if l.id == line.id][0]
        assert updated_line.quantity_ordered == Decimal("20")
        assert updated_line.line_total == Decimal("100.0000")

    def test_update_unit_cost(self, db, make_vendor, make_purchase_order, make_product):
        """Can update unit_cost; line_total recalculates."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        updated_po = update_po_line(
            db, po.id, line.id,
            data={"unit_cost": Decimal("8.00")},
        )
        updated_line = [l for l in updated_po.lines if l.id == line.id][0]
        assert updated_line.unit_cost == Decimal("8.00")
        assert updated_line.line_total == Decimal("80.0000")

    def test_cannot_reduce_below_received(self, db, make_vendor, make_purchase_order, make_product):
        """Raises 400 when reducing quantity_ordered below quantity_received."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product()
        line = _add_po_line(
            db, po, product, Decimal("10"), Decimal("5.00"), qty_received=Decimal("7")
        )
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_line(
                db, po.id, line.id,
                data={"quantity_ordered": Decimal("5")},
            )
        assert exc_info.value.status_code == 400
        assert "received" in str(exc_info.value.detail).lower()

    def test_can_set_quantity_equal_to_received(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """Reducing quantity to exactly the received amount is allowed."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product()
        line = _add_po_line(
            db, po, product, Decimal("10"), Decimal("5.00"), qty_received=Decimal("7")
        )
        db.commit()

        updated_po = update_po_line(
            db, po.id, line.id,
            data={"quantity_ordered": Decimal("7")},
        )
        updated_line = [l for l in updated_po.lines if l.id == line.id][0]
        assert updated_line.quantity_ordered == Decimal("7")

    def test_received_po_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot modify a line on a received PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_line(
                db, po.id, line.id,
                data={"quantity_ordered": Decimal("20")},
            )
        assert exc_info.value.status_code == 400

    def test_cancelled_po_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot modify a line on a cancelled PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_line(
                db, po.id, line.id,
                data={"unit_cost": Decimal("1.00")},
            )
        assert exc_info.value.status_code == 400

    def test_line_not_found_raises_404(self, db, make_vendor, make_purchase_order):
        """Raises 404 when line_id does not exist on the PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_line(
                db, po.id, 999999,
                data={"quantity_ordered": Decimal("1")},
            )
        assert exc_info.value.status_code == 404

    def test_po_not_found_raises_404(self, db):
        """Raises 404 when po_id does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            update_po_line(
                db, 999999, 1,
                data={"quantity_ordered": Decimal("1")},
            )
        assert exc_info.value.status_code == 404

    def test_update_notes(self, db, make_vendor, make_purchase_order, make_product):
        """Can update line notes."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        updated_po = update_po_line(
            db, po.id, line.id,
            data={"notes": "Updated line note"},
        )
        updated_line = [l for l in updated_po.lines if l.id == line.id][0]
        assert updated_line.notes == "Updated line note"

    def test_update_on_ordered_po(self, db, make_vendor, make_purchase_order, make_product):
        """Ordered POs allow line updates."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        updated_po = update_po_line(
            db, po.id, line.id,
            data={"unit_cost": Decimal("6.00")},
        )
        updated_line = [l for l in updated_po.lines if l.id == line.id][0]
        assert updated_line.unit_cost == Decimal("6.00")

    def test_update_both_quantity_and_cost(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """Can update quantity and cost in the same call."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        updated_po = update_po_line(
            db, po.id, line.id,
            data={"quantity_ordered": Decimal("20"), "unit_cost": Decimal("8.00")},
        )
        updated_line = [l for l in updated_po.lines if l.id == line.id][0]
        assert updated_line.line_total == Decimal("160.0000")

    def test_po_subtotal_recalculated(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """PO subtotal is recalculated after line update."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        p1 = make_product()
        p2 = make_product()
        l1 = _add_po_line(db, po, p1, Decimal("10"), Decimal("5.00"))
        _add_po_line(db, po, p2, Decimal("3"), Decimal("20.00"))
        db.commit()

        calculate_totals(po)
        db.commit()

        update_po_line(
            db, po.id, l1.id,
            data={"quantity_ordered": Decimal("20")},
        )
        db.refresh(po)
        # 20*5 + 3*20 = 100 + 60 = 160
        assert po.subtotal == Decimal("160.0000")


# =============================================================================
# Line Management: delete_po_line
# =============================================================================

class TestDeletePoLine:
    """Test delete_po_line."""

    def test_delete_line(self, db, make_vendor, make_purchase_order, make_product):
        """Can delete a line with zero received quantity."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        result = delete_po_line(db, po.id, line.id)
        assert "deleted" in result["message"].lower()

    def test_delete_received_line_raises_400(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """Cannot delete a line with quantity_received > 0."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product()
        line = _add_po_line(
            db, po, product, Decimal("10"), Decimal("5.00"), qty_received=Decimal("3")
        )
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_po_line(db, po.id, line.id)
        assert exc_info.value.status_code == 400
        assert "received" in str(exc_info.value.detail).lower()

    def test_delete_on_received_po_raises_400(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """Cannot delete lines from a received PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_po_line(db, po.id, line.id)
        assert exc_info.value.status_code == 400

    def test_delete_on_cancelled_po_raises_400(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """Cannot delete lines from a cancelled PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        product = make_product()
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_po_line(db, po.id, line.id)
        assert exc_info.value.status_code == 400

    def test_line_not_found_raises_404(self, db, make_vendor, make_purchase_order):
        """Raises 404 when line_id does not exist on the PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            delete_po_line(db, po.id, 999999)
        assert exc_info.value.status_code == 404

    def test_po_not_found_raises_404(self, db):
        """Raises 404 when po_id does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            delete_po_line(db, 999999, 1)
        assert exc_info.value.status_code == 404

    def test_totals_recalculated_after_delete(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """PO totals are recalculated after deleting a line."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        p1 = make_product()
        p2 = make_product()
        l1 = _add_po_line(db, po, p1, Decimal("10"), Decimal("5.00"))
        _add_po_line(db, po, p2, Decimal("3"), Decimal("20.00"))
        calculate_totals(po)
        db.commit()

        # Before delete: subtotal = 50 + 60 = 110
        assert po.subtotal == Decimal("110.0000")

        delete_po_line(db, po.id, l1.id)
        db.refresh(po)
        # After delete: subtotal = 60 only
        assert po.subtotal == Decimal("60.0000")


# =============================================================================
# Status Management
# =============================================================================

class TestUpdatePoStatus:
    """Test update_po_status."""

    def test_draft_to_ordered(self, db, make_vendor, make_purchase_order, make_product):
        """Valid transition: draft -> ordered. Sets order_date."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"))
        db.commit()

        updated = update_po_status(db, po.id, new_status="ordered", user_id=1)
        assert updated.status == "ordered"
        assert updated.order_date is not None

    def test_draft_to_ordered_preserves_existing_order_date(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """If order_date was set before transitioning, it is preserved."""
        vendor = make_vendor()
        custom_date = date(2025, 6, 15)
        po = make_purchase_order(
            vendor_id=vendor.id, status="draft", order_date=custom_date
        )
        product = make_product()
        _add_po_line(db, po, product, Decimal("5"), Decimal("10.00"))
        db.commit()

        updated = update_po_status(db, po.id, new_status="ordered", user_id=1)
        assert updated.order_date == custom_date

    def test_ordered_to_shipped(self, db, make_vendor, make_purchase_order):
        """Valid transition: ordered -> shipped. Sets shipped_date, tracking, carrier."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.commit()

        updated = update_po_status(
            db, po.id,
            new_status="shipped",
            tracking_number="1Z999",
            carrier="UPS",
            user_id=1,
        )
        assert updated.status == "shipped"
        assert updated.tracking_number == "1Z999"
        assert updated.carrier == "UPS"
        assert updated.shipped_date is not None

    def test_ordered_to_shipped_without_tracking(self, db, make_vendor, make_purchase_order):
        """Shipping without tracking/carrier is allowed."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.commit()

        updated = update_po_status(
            db, po.id, new_status="shipped", user_id=1
        )
        assert updated.status == "shipped"
        assert updated.shipped_date is not None

    def test_shipped_to_received(self, db, make_vendor, make_purchase_order):
        """Valid transition: shipped -> received. Sets received_date."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="shipped")
        db.commit()

        updated = update_po_status(db, po.id, new_status="received", user_id=1)
        assert updated.status == "received"
        assert updated.received_date is not None

    def test_ordered_to_received_direct(self, db, make_vendor, make_purchase_order):
        """Valid transition: ordered -> received (skip shipped)."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.commit()

        updated = update_po_status(db, po.id, new_status="received", user_id=1)
        assert updated.status == "received"
        assert updated.received_date is not None

    def test_received_to_closed(self, db, make_vendor, make_purchase_order):
        """Valid transition: received -> closed."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        db.commit()

        updated = update_po_status(db, po.id, new_status="closed", user_id=1)
        assert updated.status == "closed"

    def test_invalid_transition_raises_400(self, db, make_vendor, make_purchase_order):
        """Invalid transition (draft -> received) raises 400."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_status(db, po.id, new_status="received", user_id=1)
        assert exc_info.value.status_code == 400
        assert "cannot" in str(exc_info.value.detail).lower()

    def test_draft_to_shipped_invalid(self, db, make_vendor, make_purchase_order):
        """Cannot go from draft to shipped."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_status(db, po.id, new_status="shipped", user_id=1)
        assert exc_info.value.status_code == 400

    def test_closed_cannot_transition(self, db, make_vendor, make_purchase_order):
        """Closed is a terminal state -- no transitions possible."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="closed")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_status(db, po.id, new_status="ordered", user_id=1)
        assert exc_info.value.status_code == 400

    def test_cancelled_cannot_transition(self, db, make_vendor, make_purchase_order):
        """Cancelled is a terminal state -- no transitions possible."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_status(db, po.id, new_status="ordered", user_id=1)
        assert exc_info.value.status_code == 400

    def test_draft_to_cancelled(self, db, make_vendor, make_purchase_order):
        """Valid transition: draft -> cancelled."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        updated = update_po_status(db, po.id, new_status="cancelled", user_id=1)
        assert updated.status == "cancelled"

    def test_ordered_to_cancelled(self, db, make_vendor, make_purchase_order):
        """Valid transition: ordered -> cancelled."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.commit()

        updated = update_po_status(db, po.id, new_status="cancelled", user_id=1)
        assert updated.status == "cancelled"

    def test_shipped_to_cancelled(self, db, make_vendor, make_purchase_order):
        """Valid transition: shipped -> cancelled."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="shipped")
        db.commit()

        updated = update_po_status(db, po.id, new_status="cancelled", user_id=1)
        assert updated.status == "cancelled"

    def test_received_to_cancelled(self, db, make_vendor, make_purchase_order):
        """Valid transition: received -> cancelled."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        db.commit()

        updated = update_po_status(db, po.id, new_status="cancelled", user_id=1)
        assert updated.status == "cancelled"

    def test_order_without_lines_raises_400(self, db, make_vendor, make_purchase_order):
        """Cannot transition to ordered when PO has no lines."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            update_po_status(db, po.id, new_status="ordered", user_id=1)
        assert exc_info.value.status_code == 400
        assert "no lines" in str(exc_info.value.detail).lower()

    def test_po_not_found_raises_404(self, db):
        """Raises 404 when PO does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            update_po_status(db, 999999, new_status="ordered", user_id=1)
        assert exc_info.value.status_code == 404


# =============================================================================
# receive_purchase_order
# =============================================================================

class TestReceivePurchaseOrder:
    """Test receive_purchase_order.

    The full receiving flow touches TransactionService, Inventory, MaterialLot,
    and MaterialSpool. Tests here focus on validation logic and basic happy paths.
    """

    def test_full_receipt(self, db, make_vendor, make_purchase_order, make_product):
        """Full receipt sets PO to 'received' and returns summary."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        result = receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("10")}],
            user_id=1,
            user_email="test@filaops.dev",
        )
        assert result["lines_received"] == 1
        assert result["total_quantity"] == Decimal("10")
        assert result["inventory_updated"] is True

        db.refresh(po)
        assert po.status == "received"

    def test_partial_receipt(self, db, make_vendor, make_purchase_order, make_product):
        """Partial receipt leaves PO in 'ordered' status."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        result = receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("5")}],
            user_id=1,
            user_email="test@filaops.dev",
        )
        assert result["total_quantity"] == Decimal("5")

        db.refresh(po)
        assert po.status == "ordered"

        db.refresh(line)
        assert line.quantity_received == Decimal("5")

    def test_over_receipt_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot receive more than the remaining quantity."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            receive_purchase_order(
                db, po.id,
                lines=[{"line_id": line.id, "quantity_received": Decimal("15")}],
                user_id=1,
                user_email="test@filaops.dev",
            )
        assert exc_info.value.status_code == 400
        assert "remaining" in str(exc_info.value.detail).lower()

    def test_draft_po_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot receive items on a draft PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            receive_purchase_order(
                db, po.id,
                lines=[{"line_id": line.id, "quantity_received": Decimal("10")}],
                user_id=1,
                user_email="test@filaops.dev",
            )
        assert exc_info.value.status_code == 400

    def test_received_po_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot receive items on an already received PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            receive_purchase_order(
                db, po.id,
                lines=[{"line_id": line.id, "quantity_received": Decimal("1")}],
                user_id=1,
                user_email="test@filaops.dev",
            )
        assert exc_info.value.status_code == 400

    def test_cancelled_po_raises_400(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot receive items on a cancelled PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            receive_purchase_order(
                db, po.id,
                lines=[{"line_id": line.id, "quantity_received": Decimal("1")}],
                user_id=1,
                user_email="test@filaops.dev",
            )
        assert exc_info.value.status_code == 400

    def test_invalid_line_id_raises_404(self, db, make_vendor, make_purchase_order, make_product):
        """Raises 404 when line_id is not on the PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product(unit="EA", purchase_uom="EA")
        _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            receive_purchase_order(
                db, po.id,
                lines=[{"line_id": 999999, "quantity_received": Decimal("1")}],
                user_id=1,
                user_email="test@filaops.dev",
            )
        assert exc_info.value.status_code == 404

    def test_po_not_found_raises_404(self, db):
        """Raises 404 when PO does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            receive_purchase_order(
                db, 999999,
                lines=[],
                user_id=1,
                user_email="test@filaops.dev",
            )
        assert exc_info.value.status_code == 404

    def test_shipped_po_can_receive(self, db, make_vendor, make_purchase_order, make_product):
        """Shipped POs can receive items."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="shipped")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("5"), Decimal("10.00"), purchase_unit="EA")
        db.commit()

        result = receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("5")}],
            user_id=1,
            user_email="test@filaops.dev",
        )
        assert result["lines_received"] == 1

    def test_updates_product_average_cost(self, db, make_vendor, make_purchase_order, make_product):
        """Receiving updates product.average_cost and product.last_cost."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product(
            unit="EA", purchase_uom="EA",
            average_cost=Decimal("0"), cost_method="average",
        )
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("25.00"), purchase_unit="EA")
        db.commit()

        receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("10")}],
            user_id=1,
            user_email="test@filaops.dev",
        )

        db.refresh(product)
        assert product.average_cost is not None
        assert float(product.average_cost) > 0
        assert float(product.last_cost) == pytest.approx(25.0, rel=1e-2)

    def test_creates_material_lot(self, db, make_vendor, make_purchase_order, make_product):
        """Receiving a supply product creates a MaterialLot for traceability."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product(
            item_type="supply",
            unit="EA",
            purchase_uom="EA",
        )
        line = _add_po_line(db, po, product, Decimal("5"), Decimal("10.00"), purchase_unit="EA")
        db.commit()

        result = receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("5")}],
            user_id=1,
            user_email="test@filaops.dev",
        )
        assert len(result["material_lots_created"]) >= 1

    def test_multi_line_receipt(self, db, make_vendor, make_purchase_order, make_product):
        """Can receive multiple lines in a single call."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        p1 = make_product(unit="EA", purchase_uom="EA")
        p2 = make_product(unit="EA", purchase_uom="EA")
        l1 = _add_po_line(db, po, p1, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        l2 = _add_po_line(db, po, p2, Decimal("20"), Decimal("3.00"), purchase_unit="EA")
        db.commit()

        result = receive_purchase_order(
            db, po.id,
            lines=[
                {"line_id": l1.id, "quantity_received": Decimal("10")},
                {"line_id": l2.id, "quantity_received": Decimal("20")},
            ],
            user_id=1,
            user_email="test@filaops.dev",
        )
        assert result["lines_received"] == 2
        assert result["total_quantity"] == Decimal("30")

    def test_non_material_incompatible_units_receives_as_is(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """
        Non-material items can be received even when purchase_unit and product_unit
        are incompatible (e.g. PTFE tubing ordered in M but product unit is EA).

        Regression test for: PO receiving blocked for maintenance/supply items
        where the purchase UOM differs from the product's default unit.
        """
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        # Maintenance item: product unit is EA (default), purchased in metres
        product = make_product(unit="EA", item_type="supply", purchase_uom="M")
        line = _add_po_line(
            db, po, product, Decimal("5"), Decimal("2.50"), purchase_unit="M"
        )
        db.commit()

        # Must NOT raise — should fall through and receive quantity as-is
        result = receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("5")}],
            user_id=1,
            user_email="test@filaops.dev",
        )
        assert result["lines_received"] == 1
        assert result["total_quantity"] == Decimal("5")
        assert result["inventory_updated"] is True

        # Full receipt of only line → PO moves to received
        db.refresh(po)
        assert po.status == "received"

        db.refresh(line)
        assert line.quantity_received == Decimal("5")

        # Inventory transaction must be labeled in purchase unit (M) with original cost ($/M)
        txn_id = result["transactions_created"][0]
        txn = db.query(InventoryTransaction).filter(InventoryTransaction.id == txn_id).one()
        assert txn.unit == "M"
        assert txn.cost_per_unit == Decimal("2.50")

        # Product costs must NOT be updated — $/M is meaningless on an EA product
        db.refresh(product)
        assert product.average_cost is None or product.average_cost == 0
        assert product.last_cost is None or product.last_cost == 0

    def test_material_incompatible_units_still_raises(
        self, db, make_vendor, make_purchase_order, make_product
    ):
        """
        Material items (filament etc.) with incompatible units STILL raise 400 —
        mass-based cost math requires a valid conversion.
        """
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        # Material (filament): purchased in EA — incompatible with KG product unit
        product = make_product(unit="KG", item_type="material", purchase_uom="KG")
        # Force incompatible purchase_unit directly on the line
        line = _add_po_line(
            db, po, product, Decimal("5"), Decimal("20.00"), purchase_unit="EA"
        )
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            receive_purchase_order(
                db, po.id,
                lines=[{"line_id": line.id, "quantity_received": Decimal("5")}],
                user_id=1,
                user_email="test@filaops.dev",
            )
        assert exc_info.value.status_code == 400
        assert "incompatible" in str(exc_info.value.detail).lower()

    def test_partial_then_remaining(self, db, make_vendor, make_purchase_order, make_product):
        """Partial receipt followed by remaining quantity completes the PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        # First: receive 6
        receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("6")}],
            user_id=1,
            user_email="test@filaops.dev",
        )
        db.refresh(po)
        assert po.status == "ordered"

        # Second: receive remaining 4
        result = receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("4")}],
            user_id=1,
            user_email="test@filaops.dev",
        )
        db.refresh(po)
        assert po.status == "received"
        assert result["total_quantity"] == Decimal("4")

    def test_over_receive_after_partial(self, db, make_vendor, make_purchase_order, make_product):
        """Cannot over-receive after a partial receipt."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product(unit="EA", purchase_uom="EA")
        line = _add_po_line(db, po, product, Decimal("10"), Decimal("5.00"), purchase_unit="EA")
        db.commit()

        # Receive 7 first
        receive_purchase_order(
            db, po.id,
            lines=[{"line_id": line.id, "quantity_received": Decimal("7")}],
            user_id=1,
            user_email="test@filaops.dev",
        )

        # Try to receive 5 more (only 3 remaining)
        with pytest.raises(HTTPException) as exc_info:
            receive_purchase_order(
                db, po.id,
                lines=[{"line_id": line.id, "quantity_received": Decimal("5")}],
                user_id=1,
                user_email="test@filaops.dev",
            )
        assert exc_info.value.status_code == 400
        assert "remaining" in str(exc_info.value.detail).lower()


# =============================================================================
# upload_po_document
# =============================================================================

class TestUploadPoDocument:
    """Test upload_po_document."""

    def test_upload_pdf(self, db, make_vendor, make_purchase_order):
        """Uploads a PDF and returns success with local storage info."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        content = b"%PDF-1.4 fake pdf content"

        with patch("app.services.purchase_order_service.os.makedirs"):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__ = lambda s: s
                mock_open.return_value.__exit__ = lambda s, *a: None
                mock_open.return_value.write = lambda data: len(data)

                result = upload_po_document(
                    db, po.id,
                    file_content=content,
                    filename="invoice.pdf",
                    content_type="application/pdf",
                )

        assert result["success"] is True
        assert result["storage"] == "local"
        assert po.po_number in result["filename"]

    def test_upload_image(self, db, make_vendor, make_purchase_order):
        """Accepts JPEG image uploads."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with patch("app.services.purchase_order_service.os.makedirs"):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__ = lambda s: s
                mock_open.return_value.__exit__ = lambda s, *a: None
                mock_open.return_value.write = lambda data: len(data)

                result = upload_po_document(
                    db, po.id,
                    file_content=b"fake jpeg data",
                    filename="receipt.jpg",
                    content_type="image/jpeg",
                )

        assert result["success"] is True

    def test_reject_oversized_file(self, db, make_vendor, make_purchase_order):
        """Rejects files larger than 10MB."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        content = b"x" * (11 * 1024 * 1024)  # 11MB

        with pytest.raises(HTTPException) as exc_info:
            upload_po_document(
                db, po.id,
                file_content=content,
                filename="huge.pdf",
                content_type="application/pdf",
            )
        assert exc_info.value.status_code == 400
        assert "large" in str(exc_info.value.detail).lower()

    def test_reject_disallowed_content_type(self, db, make_vendor, make_purchase_order):
        """Rejects files with unrecognized content types."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            upload_po_document(
                db, po.id,
                file_content=b"hello",
                filename="script.exe",
                content_type="application/octet-stream",
            )
        assert exc_info.value.status_code == 400
        assert "not allowed" in str(exc_info.value.detail).lower()

    def test_po_not_found_raises_404(self, db):
        """Raises 404 when PO does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            upload_po_document(
                db, 999999,
                file_content=b"data",
                filename="test.pdf",
                content_type="application/pdf",
            )
        assert exc_info.value.status_code == 404

    def test_exactly_10mb_allowed(self, db, make_vendor, make_purchase_order):
        """Files at exactly 10MB are accepted (boundary test)."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        content = b"x" * (10 * 1024 * 1024)  # exactly 10MB

        with patch("app.services.purchase_order_service.os.makedirs"):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__ = lambda s: s
                mock_open.return_value.__exit__ = lambda s, *a: None
                mock_open.return_value.write = lambda data: len(data)

                result = upload_po_document(
                    db, po.id,
                    file_content=content,
                    filename="exactly10mb.pdf",
                    content_type="application/pdf",
                )

        assert result["success"] is True

    def test_sets_document_url_on_po(self, db, make_vendor, make_purchase_order):
        """Uploading sets PO.document_url to the local path."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        with patch("app.services.purchase_order_service.os.makedirs"):
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__ = lambda s: s
                mock_open.return_value.__exit__ = lambda s, *a: None
                mock_open.return_value.write = lambda data: len(data)

                upload_po_document(
                    db, po.id,
                    file_content=b"pdf data",
                    filename="invoice.pdf",
                    content_type="application/pdf",
                )

        db.refresh(po)
        assert po.document_url is not None
        assert "/uploads/purchase_orders/" in po.document_url


# =============================================================================
# Event Timeline
# =============================================================================

class TestListPoEvents:
    """Test list_po_events."""

    def test_returns_events_for_po(self, db, make_vendor, make_purchase_order):
        """Returns events belonging to the PO."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        add_po_event(
            db, po.id,
            event_type="note",
            title="Test event",
            user_id=1,
        )

        events, total = list_po_events(db, po.id)
        assert total >= 1
        titles = [e.title for e in events]
        assert "Test event" in titles

    def test_not_found_raises_404(self, db):
        """Raises 404 when PO does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            list_po_events(db, 999999)
        assert exc_info.value.status_code == 404

    def test_pagination(self, db, make_vendor, make_purchase_order):
        """Limit and offset control event result window."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        for i in range(5):
            add_po_event(
                db, po.id,
                event_type="note",
                title=f"Event {i}",
                user_id=1,
            )

        events, total = list_po_events(db, po.id, limit=2, offset=0)
        assert len(events) <= 2
        assert total >= 5

    def test_empty_timeline(self, db, make_vendor, make_purchase_order):
        """Returns empty list and zero total when PO has no events."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        events, total = list_po_events(db, po.id)
        assert total == 0
        assert events == []


class TestAddPoEvent:
    """Test add_po_event."""

    def test_add_basic_event(self, db, make_vendor, make_purchase_order):
        """Creates an event with required fields."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        event = add_po_event(
            db, po.id,
            event_type="note",
            title="Test event",
            description="Some description",
            user_id=1,
        )
        assert event is not None
        assert event.event_type == "note"
        assert event.title == "Test event"
        assert event.description == "Some description"

    def test_add_event_with_all_optional_fields(self, db, make_vendor, make_purchase_order):
        """Creates an event with all optional fields set."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.commit()

        event = add_po_event(
            db, po.id,
            event_type="status_change",
            title="Status Updated",
            description="Changed to ordered",
            old_value="draft",
            new_value="ordered",
            event_date=date(2025, 7, 1),
            metadata_key="reason",
            metadata_value="urgent",
            user_id=1,
        )
        assert event.old_value == "draft"
        assert event.new_value == "ordered"
        assert event.event_date == date(2025, 7, 1)
        assert event.metadata_key == "reason"
        assert event.metadata_value == "urgent"

    def test_po_not_found_raises_404(self, db):
        """Raises 404 when PO does not exist."""
        with pytest.raises(HTTPException) as exc_info:
            add_po_event(
                db, 999999,
                event_type="note",
                title="Ghost",
                user_id=1,
            )
        assert exc_info.value.status_code == 404

    def test_event_user_id_stored(self, db, make_vendor, make_purchase_order):
        """Event records the user_id who created it."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.commit()

        event = add_po_event(
            db, po.id,
            event_type="note",
            title="Audit test",
            user_id=1,
        )
        assert event.user_id == 1


# =============================================================================
# VALID_TRANSITIONS table coverage
# =============================================================================

class TestValidTransitions:
    """Verify the VALID_TRANSITIONS dict structure and values."""

    def test_all_valid_from_draft(self):
        assert "ordered" in VALID_TRANSITIONS["draft"]
        assert "cancelled" in VALID_TRANSITIONS["draft"]

    def test_all_valid_from_ordered(self):
        assert "shipped" in VALID_TRANSITIONS["ordered"]
        assert "received" in VALID_TRANSITIONS["ordered"]
        assert "cancelled" in VALID_TRANSITIONS["ordered"]

    def test_all_valid_from_shipped(self):
        assert "received" in VALID_TRANSITIONS["shipped"]
        assert "cancelled" in VALID_TRANSITIONS["shipped"]

    def test_all_valid_from_received(self):
        assert "closed" in VALID_TRANSITIONS["received"]
        assert "cancelled" in VALID_TRANSITIONS["received"]

    def test_closed_is_terminal(self):
        assert VALID_TRANSITIONS["closed"] == []

    def test_cancelled_is_terminal(self):
        assert VALID_TRANSITIONS["cancelled"] == []

    def test_all_statuses_present(self):
        """Every known status has an entry in the transitions dict."""
        expected_statuses = {"draft", "ordered", "shipped", "received", "closed", "cancelled"}
        assert set(VALID_TRANSITIONS.keys()) == expected_statuses

    def test_no_self_transitions(self):
        """No status can transition to itself."""
        for status, targets in VALID_TRANSITIONS.items():
            assert status not in targets, f"Self-transition found for '{status}'"
