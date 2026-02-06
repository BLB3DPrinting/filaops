"""Tests for mrp_trigger_service.py — MRP trigger feature flags and routing."""
import pytest
from decimal import Decimal
from unittest.mock import patch

from app.services.mrp_trigger_service import (
    trigger_mrp_check,
    trigger_mrp_recalculation,
    trigger_incremental_mrp,
)


class TestTriggerMRPCheck:
    def test_returns_none_when_disabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = False
            result = trigger_mrp_check(db, sales_order_id=1)
            assert result is None

    def test_returns_error_for_missing_so(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = True
            result = trigger_mrp_check(db, sales_order_id=999999)
            assert result["error"] == "Sales order not found"

    def test_returns_checked_for_valid_so(self, db, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(
            product_id=product.id, quantity=1, unit_price=Decimal("10.00")
        )
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = True
            result = trigger_mrp_check(db, sales_order_id=so.id)
            assert result["status"] == "checked"
            assert result["sales_order_id"] == so.id


class TestTriggerMRPRecalculation:
    def test_shipment_returns_none_when_disabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_SHIPMENT = False
            result = trigger_mrp_recalculation(db, context_id=1, reason="shipment")
            assert result is None

    def test_returns_requested_for_shipment(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_SHIPMENT = True
            result = trigger_mrp_recalculation(
                db, context_id=1, reason="shipment", product_ids=[1, 2]
            )
            assert result["status"] == "requested"
            assert result["reason"] == "shipment"

    def test_non_shipment_reason_not_gated(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_SHIPMENT = False
            result = trigger_mrp_recalculation(
                db, context_id=1, reason="production_completion"
            )
            assert result["status"] == "requested"


class TestTriggerIncrementalMRP:
    def test_returns_none_when_disabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = False
            result = trigger_incremental_mrp(db, product_ids=[1, 2])
            assert result is None

    def test_returns_requested_when_enabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = True
            result = trigger_incremental_mrp(db, product_ids=[1, 2, 3])
            assert result["status"] == "requested"
            assert result["product_ids"] == [1, 2, 3]
