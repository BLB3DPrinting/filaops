"""
Tests for mrp_trigger_service.py — HARD-3 honest-stub contract.

Contract (see mrp_trigger_service module docstring):
- When the governing flag is OFF  → function returns None (no work attempted).
- When the governing flag is ON   → function returns {"status": "not_implemented", ...}
  and NEVER claims completion for work it did not do.

Any test asserting "status": "checked" or "status": "requested" would be
testing a lie — those statuses are gone.
"""
from unittest.mock import patch

from app.services.mrp_trigger_service import (
    trigger_mrp_check,
    trigger_mrp_recalculation,
    trigger_incremental_mrp,
)


class TestTriggerMRPCheck:
    """trigger_mrp_check is gated by AUTO_MRP_ON_ORDER_CREATE."""

    def test_returns_none_when_flag_disabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_ORDER_CREATE = False
            result = trigger_mrp_check(db, sales_order_id=1)
        assert result is None

    def test_returns_not_implemented_when_flag_enabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_ORDER_CREATE = True
            result = trigger_mrp_check(db, sales_order_id=42)
        assert result is not None
        assert result["status"] == "not_implemented", (
            "trigger_mrp_check must not claim completion — stub returns not_implemented"
        )
        assert result["sales_order_id"] == 42

    def test_never_claims_checked_or_completed(self, db):
        """Guard: no success-shaped status may escape this function."""
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_ORDER_CREATE = True
            result = trigger_mrp_check(db, sales_order_id=1)
        assert result["status"] not in ("checked", "completed", "requested"), (
            "Stub must not return a success-shaped status while doing nothing"
        )


class TestTriggerMRPRecalculation:
    """trigger_mrp_recalculation is gated by AUTO_MRP_ON_SHIPMENT for reason='shipment'."""

    def test_shipment_returns_none_when_flag_disabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_SHIPMENT = False
            result = trigger_mrp_recalculation(db, context_id=1, reason="shipment")
        assert result is None

    def test_shipment_returns_not_implemented_when_flag_enabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_SHIPMENT = True
            result = trigger_mrp_recalculation(
                db, context_id=99, reason="shipment", product_ids=[1, 2]
            )
        assert result is not None
        assert result["status"] == "not_implemented", (
            "trigger_mrp_recalculation must not claim completion — stub returns not_implemented"
        )
        assert result["context_id"] == 99
        assert result["reason"] == "shipment"

    def test_non_shipment_reason_not_gated_by_shipment_flag(self, db):
        """Non-shipment reasons bypass the AUTO_MRP_ON_SHIPMENT gate."""
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_SHIPMENT = False
            result = trigger_mrp_recalculation(
                db, context_id=1, reason="production_completion"
            )
        assert result is not None
        assert result["status"] == "not_implemented"
        assert result["reason"] == "production_completion"

    def test_never_claims_requested_or_completed(self, db):
        """Guard: no success-shaped status may escape this function."""
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.AUTO_MRP_ON_SHIPMENT = True
            result = trigger_mrp_recalculation(db, context_id=1, reason="shipment")
        assert result["status"] not in ("checked", "completed", "requested"), (
            "Stub must not return a success-shaped status while doing nothing"
        )


class TestTriggerIncrementalMRP:
    """trigger_incremental_mrp is gated by INCLUDE_SALES_ORDERS_IN_MRP."""

    def test_returns_none_when_flag_disabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = False
            result = trigger_incremental_mrp(db, product_ids=[1, 2])
        assert result is None

    def test_returns_not_implemented_when_flag_enabled(self, db):
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = True
            result = trigger_incremental_mrp(db, product_ids=[1, 2, 3])
        assert result is not None
        assert result["status"] == "not_implemented", (
            "trigger_incremental_mrp must not claim completion — stub returns not_implemented"
        )
        assert result["product_ids"] == [1, 2, 3]

    def test_never_claims_requested_or_completed(self, db):
        """Guard: no success-shaped status may escape this function."""
        with patch("app.services.mrp_trigger_service.settings") as mock_settings:
            mock_settings.INCLUDE_SALES_ORDERS_IN_MRP = True
            result = trigger_incremental_mrp(db, product_ids=[5])
        assert result["status"] not in ("checked", "completed", "requested"), (
            "Stub must not return a success-shaped status while doing nothing"
        )
