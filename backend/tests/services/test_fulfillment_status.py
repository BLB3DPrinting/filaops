"""Tests for fulfillment status calculation."""
from decimal import Decimal

from app.models.sales_order import SalesOrderLine
from app.schemas.fulfillment_status import FulfillmentState
from app.services.fulfillment_status import get_fulfillment_status


class TestFulfillmentStatusService:
    def test_service_line_does_not_block_fulfillment(self, db, make_product, make_sales_order):
        product = make_product(name="Fulfillable Widget")
        order = make_sales_order(
            product_id=None,
            product_name="Manual order",
            quantity=2,
            unit_price=Decimal("17.50"),
            status="pending",
        )

        db.add_all([
            SalesOrderLine(
                sales_order_id=order.id,
                line_type="product",
                product_id=product.id,
                quantity=Decimal("1.00"),
                unit_price=Decimal("25.00"),
                total=Decimal("25.00"),
                allocated_quantity=Decimal("1.00"),
                shipped_quantity=Decimal("0.00"),
            ),
            SalesOrderLine(
                sales_order_id=order.id,
                line_type="service",
                description="Design Fee",
                quantity=Decimal("1.00"),
                unit_price=Decimal("10.00"),
                total=Decimal("10.00"),
                allocated_quantity=Decimal("0.00"),
                shipped_quantity=Decimal("0.00"),
            ),
        ])
        db.flush()

        status = get_fulfillment_status(db, order.id)

        assert status is not None
        assert status.summary.state == FulfillmentState.READY_TO_SHIP
        assert status.summary.lines_total == 2
        assert status.summary.lines_ready == 2

        fee_line = next(line for line in status.lines if line.product_name == "Design Fee")
        assert fee_line.product_id is None
        assert fee_line.product_sku == "SERVICE"
        assert fee_line.quantity_allocated == 0
        assert fee_line.is_ready is True
        assert fee_line.shortage == 0
