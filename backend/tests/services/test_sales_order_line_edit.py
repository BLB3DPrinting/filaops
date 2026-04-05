"""
Tests for sales order line editing and close-short functionality.

Covers:
- edit_sales_order_lines: Quantity changes, validation, totals, events
- close_short_sales_order: Partial fulfillment acceptance, totals, status
- _recalculate_order_totals: Total recalculation logic
"""
import pytest
from decimal import Decimal

from fastapi import HTTPException

from app.models.user import User
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.production_order import ProductionOrder
from app.models.order_event import OrderEvent
from app.services import sales_order_service


# =============================================================================
# Helpers
# =============================================================================

def _make_user(db, *, account_type="admin"):
    """Create a User record for testing."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    user = User(
        email=f"test-{uid}@filaops.dev",
        password_hash="not-a-real-hash",
        first_name="Test",
        last_name="User",
        status="active",
        account_type=account_type,
    )
    db.add(user)
    db.flush()
    return user


def _make_order(db, user_id, *, status="confirmed", quantity=100,
                unit_price=Decimal("10.00"), order_type="line_item"):
    """Create a SalesOrder directly with minimal required fields."""
    import uuid
    total = unit_price * quantity
    order = SalesOrder(
        user_id=user_id,
        order_number=f"SO-TEST-{uuid.uuid4().hex[:8]}",
        order_type=order_type,
        source="manual",
        product_name="Test Product",
        quantity=quantity,
        material_type="PLA",
        finish="standard",
        unit_price=unit_price,
        total_price=total,
        tax_amount=Decimal("0"),
        tax_rate=Decimal("0"),
        is_taxable=False,
        shipping_cost=Decimal("0"),
        grand_total=total,
        status=status,
    )
    db.add(order)
    db.flush()
    return order


def _make_line(db, order_id, product_id, *, quantity=100,
               unit_price=Decimal("10.00"), shipped_quantity=Decimal("0")):
    """Create a SalesOrderLine directly."""
    total = unit_price * quantity
    line = SalesOrderLine(
        sales_order_id=order_id,
        product_id=product_id,
        quantity=Decimal(str(quantity)),
        unit_price=unit_price,
        total=total,
        discount=Decimal("0"),
        tax_rate=Decimal("0"),
        shipped_quantity=shipped_quantity,
        allocated_quantity=Decimal("0"),
    )
    db.add(line)
    db.flush()
    return line


# =============================================================================
# Edit Sales Order Lines
# =============================================================================

class TestEditSalesOrderLines:
    """Test line quantity editing."""

    def test_reduces_quantity_and_recalculates(self, db, make_product):
        """Reducing a line quantity updates line total and order totals."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, quantity=144)
        line = _make_line(db, order.id, product.id, quantity=144, unit_price=Decimal("10.00"))
        db.commit()

        updated = sales_order_service.edit_sales_order_lines(
            db,
            order_id=order.id,
            line_updates=[{"line_id": line.id, "new_quantity": Decimal("104"), "reason": "Customer agreed"}],
            user_id=user.id,
        )

        db.refresh(line)
        assert line.quantity == Decimal("104")
        assert line.total == Decimal("1040.00")
        assert updated.total_price == Decimal("1040.00")
        assert updated.grand_total == Decimal("1040.00")

    def test_stores_original_quantity_on_first_edit(self, db, make_product):
        """original_quantity is set on first edit and not overwritten on subsequent edits."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, quantity=100)
        line = _make_line(db, order.id, product.id, quantity=100)
        db.commit()

        # First edit
        sales_order_service.edit_sales_order_lines(
            db, order_id=order.id,
            line_updates=[{"line_id": line.id, "new_quantity": Decimal("80"), "reason": "First edit"}],
            user_id=user.id,
        )
        db.refresh(line)
        assert line.original_quantity == Decimal("100")

        # Second edit — original should NOT change
        sales_order_service.edit_sales_order_lines(
            db, order_id=order.id,
            line_updates=[{"line_id": line.id, "new_quantity": Decimal("60"), "reason": "Second edit"}],
            user_id=user.id,
        )
        db.refresh(line)
        assert line.original_quantity == Decimal("100")  # Still 100, not 80

    def test_cannot_go_below_shipped_quantity(self, db, make_product):
        """Raises 400 if new quantity < shipped quantity."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, quantity=100)
        line = _make_line(db, order.id, product.id, quantity=100, shipped_quantity=Decimal("50"))
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.edit_sales_order_lines(
                db, order_id=order.id,
                line_updates=[{"line_id": line.id, "new_quantity": Decimal("30"), "reason": "Too low"}],
                user_id=user.id,
            )
        assert exc_info.value.status_code == 400
        assert "shipped quantity" in exc_info.value.detail.lower()

    def test_rejects_invalid_status(self, db, make_product):
        """Cannot edit lines on completed or cancelled orders."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))

        for bad_status in ["completed", "cancelled", "shipped", "delivered"]:
            order = _make_order(db, user.id, status=bad_status)
            line = _make_line(db, order.id, product.id)
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                sales_order_service.edit_sales_order_lines(
                    db, order_id=order.id,
                    line_updates=[{"line_id": line.id, "new_quantity": Decimal("50"), "reason": "test"}],
                    user_id=user.id,
                )
            assert exc_info.value.status_code == 400

    def test_records_event(self, db, make_product):
        """An order event is created for each line edit."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, quantity=100)
        line = _make_line(db, order.id, product.id, quantity=100)
        db.commit()

        sales_order_service.edit_sales_order_lines(
            db, order_id=order.id,
            line_updates=[{"line_id": line.id, "new_quantity": Decimal("75"), "reason": "Adjusted per customer"}],
            user_id=user.id,
        )

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == order.id,
            OrderEvent.event_type == "line_edited",
        ).all()
        assert len(events) >= 1
        assert "100" in events[0].description
        assert "75" in events[0].description

    def test_rejects_nonexistent_line(self, db, make_product):
        """Raises 404 if line_id doesn't belong to the order."""
        user = _make_user(db)
        order = _make_order(db, user.id)
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            sales_order_service.edit_sales_order_lines(
                db, order_id=order.id,
                line_updates=[{"line_id": 99999, "new_quantity": Decimal("50"), "reason": "test"}],
                user_id=user.id,
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# Close Short
# =============================================================================

class TestCloseShortSalesOrder:
    """Test close-short functionality."""

    def test_closes_short_and_completes(self, db, make_product):
        """Close short transitions to completed with closed_short flag."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, status="in_production", quantity=144)
        _make_line(db, order.id, product.id, quantity=144, shipped_quantity=Decimal("104"))
        db.commit()

        updated = sales_order_service.close_short_sales_order(
            db, order_id=order.id, user_id=user.id, reason="Customer accepted partial"
        )

        assert updated.status == "ready_to_ship"
        assert updated.fulfillment_status == "ready"
        assert updated.closed_short is True
        assert updated.closed_short_at is not None
        assert updated.close_short_reason == "Customer accepted partial"

    def test_adjusts_line_quantities_to_shipped(self, db, make_product):
        """Lines are adjusted to shipped quantities and totals recalculated."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, status="in_production", quantity=144)
        line = _make_line(db, order.id, product.id, quantity=144, shipped_quantity=Decimal("104"))
        db.commit()

        updated = sales_order_service.close_short_sales_order(
            db, order_id=order.id, user_id=user.id, reason="Short close"
        )

        db.refresh(line)
        assert line.quantity == Decimal("104")
        assert line.original_quantity == Decimal("144")
        assert line.total == Decimal("1040.00")
        assert updated.grand_total == Decimal("1040.00")

    def test_records_event_with_totals(self, db, make_product):
        """Close short records an event with original and adjusted totals."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, status="in_production", quantity=100)
        _make_line(db, order.id, product.id, quantity=100, shipped_quantity=Decimal("75"))
        db.commit()

        sales_order_service.close_short_sales_order(
            db, order_id=order.id, user_id=user.id, reason="Agreed to close"
        )

        events = db.query(OrderEvent).filter(
            OrderEvent.sales_order_id == order.id,
            OrderEvent.event_type == "closed_short",
        ).all()
        assert len(events) == 1
        assert "Reason: Agreed to close" in events[0].description

    def test_rejects_invalid_status(self, db, make_product):
        """Cannot close short on completed or cancelled orders."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))

        for bad_status in ["completed", "cancelled", "shipped", "delivered"]:
            order = _make_order(db, user.id, status=bad_status)
            _make_line(db, order.id, product.id, quantity=100, shipped_quantity=Decimal("50"))
            db.commit()

            with pytest.raises(HTTPException) as exc_info:
                sales_order_service.close_short_sales_order(
                    db, order_id=order.id, user_id=user.id, reason="test"
                )
            assert exc_info.value.status_code == 400

    def test_uses_po_completed_qty_when_not_shipped(self, db, make_product):
        """When shipped_quantity is 0, falls back to PO completed quantity."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, status="in_production", quantity=144)
        line = _make_line(db, order.id, product.id, quantity=144, shipped_quantity=Decimal("0"))

        # Create a linked production order with quantity_completed
        import uuid
        po = ProductionOrder(
            code=f"WO-TEST-{uuid.uuid4().hex[:8]}",
            sales_order_id=order.id,
            sales_order_line_id=line.id,
            product_id=product.id,
            quantity_ordered=144,
            quantity_completed=Decimal("104"),
            status="complete",
            created_by="test@filaops.dev",
        )
        db.add(po)
        db.commit()

        updated = sales_order_service.close_short_sales_order(
            db, order_id=order.id, user_id=user.id, reason="Production done, close it"
        )

        db.refresh(line)
        assert line.quantity == Decimal("104")
        assert line.fulfillment_status == "short_closed"
        assert updated.status == "ready_to_ship"
        assert updated.fulfillment_status == "ready"

    def test_falls_back_to_product_id_when_line_id_null(self, db, make_product):
        """POs without sales_order_line_id match to lines by product_id."""
        user = _make_user(db)
        product = make_product(selling_price=Decimal("10.00"))
        order = _make_order(db, user.id, status="confirmed", quantity=15)
        _make_line(db, order.id, product.id, quantity=15, shipped_quantity=Decimal("0"))

        # PO linked to order but NOT to the specific line (legacy pattern)
        import uuid
        po = ProductionOrder(
            code=f"WO-TEST-{uuid.uuid4().hex[:8]}",
            sales_order_id=order.id,
            sales_order_line_id=None,  # No direct line linkage
            product_id=product.id,
            quantity_ordered=15,
            quantity_completed=Decimal("12"),
            status="complete",
            created_by="test@filaops.dev",
        )
        db.add(po)
        db.commit()

        updated = sales_order_service.close_short_sales_order(
            db, order_id=order.id, user_id=user.id, reason="Customer accepts 12"
        )

        line = db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == order.id
        ).first()
        assert line.quantity == Decimal("12")
        assert line.original_quantity == Decimal("15")
        assert line.fulfillment_status == "short_closed"
        assert updated.status == "ready_to_ship"
        assert updated.fulfillment_status == "ready"
        assert updated.closed_short is True
