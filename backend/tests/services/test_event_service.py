"""Tests for event_service.py — purchasing and shipping event recording."""
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal

from app.services.event_service import record_purchasing_event, record_shipping_event


class TestRecordPurchasingEvent:
    def test_basic_event(self, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        event = record_purchasing_event(
            db, po.id, "status_change", "Order placed",
        )
        assert event.purchase_order_id == po.id
        assert event.event_type == "status_change"
        assert event.title == "Order placed"
        assert event.event_date == date.today()

    def test_event_with_all_fields(self, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        event = record_purchasing_event(
            db, po.id, "receipt", "Partial receipt",
            description="Received 50 of 100 units",
            old_value="draft",
            new_value="partial",
            event_date=date(2026, 1, 15),
            user_id=1,
            metadata_key="qty_received",
            metadata_value="50",
        )
        assert event.description == "Received 50 of 100 units"
        assert event.old_value == "draft"
        assert event.new_value == "partial"
        assert event.event_date == date(2026, 1, 15)
        assert event.user_id == 1
        assert event.metadata_key == "qty_received"


class TestRecordShippingEvent:
    def test_basic_event(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        event = record_shipping_event(
            db, so.id, "label_purchased", "Shipping label created",
        )
        assert event.sales_order_id == so.id
        assert event.event_type == "label_purchased"
        assert event.source == "manual"

    def test_event_with_tracking(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, quantity=1, unit_price=Decimal("10.00"))
        now = datetime.now(timezone.utc)
        event = record_shipping_event(
            db, so.id, "in_transit", "Package picked up",
            description="Carrier scanned package",
            tracking_number="1Z999AA10123456784",
            carrier="UPS",
            location_city="Austin",
            location_state="TX",
            location_zip="78701",
            event_date=date.today(),
            event_timestamp=now,
            user_id=1,
            metadata_key="weight",
            metadata_value="2.5 lbs",
            source="carrier_api",
        )
        assert event.tracking_number == "1Z999AA10123456784"
        assert event.carrier == "UPS"
        assert event.location_city == "Austin"
        assert event.source == "carrier_api"
