"""Tests for vendor_service.py — vendor CRUD, metrics, and code generation."""
import pytest
from datetime import date
from decimal import Decimal

from fastapi import HTTPException

from app.services import vendor_service


class TestGenerateVendorCode:
    def test_first_code(self, db):
        code = vendor_service.generate_vendor_code(db)
        assert code.startswith("VND-")

    def test_sequential_increment(self, db, make_vendor):
        make_vendor(code="VND-005")
        code = vendor_service.generate_vendor_code(db)
        assert code == "VND-006"


class TestListVendors:
    def test_list_returns_vendors(self, db, make_vendor):
        make_vendor(name="List Test Vendor")
        vendors, total, po_counts = vendor_service.list_vendors(db)
        assert total >= 1
        names = [v.name for v in vendors]
        assert "List Test Vendor" in names

    def test_search_filter(self, db, make_vendor):
        make_vendor(name="Unique Search Vendor XYZ")
        vendors, total, _ = vendor_service.list_vendors(db, search="Unique Search Vendor XYZ")
        assert total >= 1

    def test_active_only_filter(self, db, make_vendor):
        v = make_vendor(name="Inactive Vendor Test")
        v.is_active = False
        db.flush()
        vendors, total, _ = vendor_service.list_vendors(db, active_only=True)
        names = [v.name for v in vendors]
        assert "Inactive Vendor Test" not in names

    def test_include_inactive(self, db, make_vendor):
        v = make_vendor(name="Inactive Vendor Include")
        v.is_active = False
        db.flush()
        vendors, total, _ = vendor_service.list_vendors(db, active_only=False)
        names = [v.name for v in vendors]
        assert "Inactive Vendor Include" in names

    def test_pagination(self, db, make_vendor):
        for i in range(3):
            make_vendor(name=f"PaginationVendor-{i}")
        vendors, total, _ = vendor_service.list_vendors(db, offset=0, limit=2)
        assert len(vendors) <= 2


class TestGetVendor:
    def test_get_existing(self, db, make_vendor):
        v = make_vendor(name="Get Test Vendor")
        result = vendor_service.get_vendor(db, v.id)
        assert result.name == "Get Test Vendor"

    def test_get_nonexistent_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            vendor_service.get_vendor(db, 999999)
        assert exc_info.value.status_code == 404


class TestCreateVendor:
    def test_create_basic(self, db):
        vendor = vendor_service.create_vendor(db, data={
            "name": "New Vendor Create Test",
        })
        assert vendor.id is not None
        assert vendor.name == "New Vendor Create Test"
        assert vendor.code.startswith("VND-")

    def test_create_with_explicit_code(self, db):
        vendor = vendor_service.create_vendor(db, data={
            "code": "CUST-VND-001",
            "name": "Custom Code Vendor",
        })
        assert vendor.code == "CUST-VND-001"

    def test_create_duplicate_code_raises_400(self, db, make_vendor):
        make_vendor(code="DUP-VND")
        with pytest.raises(HTTPException) as exc_info:
            vendor_service.create_vendor(db, data={
                "code": "DUP-VND",
                "name": "Duplicate Vendor",
            })
        assert exc_info.value.status_code == 400


class TestUpdateVendor:
    def test_update_name(self, db, make_vendor):
        v = make_vendor(name="Original Vendor Name")
        updated = vendor_service.update_vendor(db, v.id, data={"name": "Updated Vendor Name"})
        assert updated.name == "Updated Vendor Name"

    def test_update_code_unique_check(self, db, make_vendor):
        v1 = make_vendor(code="VND-UPD-A")
        v2 = make_vendor(code="VND-UPD-B")
        with pytest.raises(HTTPException) as exc_info:
            vendor_service.update_vendor(db, v2.id, data={"code": "VND-UPD-A"})
        assert exc_info.value.status_code == 400

    def test_update_nonexistent_raises_404(self, db):
        with pytest.raises(HTTPException):
            vendor_service.update_vendor(db, 999999, data={"name": "Nope"})


class TestGetVendorMetrics:
    def test_metrics_no_pos(self, db, make_vendor):
        v = make_vendor(name="Metrics No PO Vendor")
        result = vendor_service.get_vendor_metrics(db, v.id)
        assert result["vendor_id"] == v.id
        assert result["total_pos"] == 0
        assert result["total_spend"] == 0
        assert result["avg_lead_time_days"] is None
        assert result["on_time_delivery_pct"] is None
        assert result["recent_pos"] == []

    def test_metrics_with_pos(self, db, make_vendor, make_purchase_order):
        v = make_vendor(name="Metrics PO Vendor")
        po = make_purchase_order(vendor_id=v.id, status="received")
        po.total_amount = Decimal("500.00")
        po.order_date = date(2025, 1, 1)
        po.received_date = date(2025, 1, 10)
        po.expected_date = date(2025, 1, 15)
        db.flush()
        result = vendor_service.get_vendor_metrics(db, v.id)
        assert result["total_pos"] >= 1
        assert result["total_spend"] >= 500
        assert result["avg_lead_time_days"] == 9.0
        assert result["on_time_delivery_pct"] == 100.0

    def test_metrics_nonexistent_raises_404(self, db):
        with pytest.raises(HTTPException):
            vendor_service.get_vendor_metrics(db, 999999)


class TestDeleteVendor:
    def test_delete_no_pos_hard_delete(self, db, make_vendor):
        v = make_vendor(name="Hard Delete Vendor")
        vid = v.id
        result = vendor_service.delete_vendor(db, vid)
        assert "deleted" in result["message"]

    def test_delete_with_pos_soft_delete(self, db, make_vendor, make_purchase_order):
        v = make_vendor(name="Soft Delete Vendor")
        make_purchase_order(vendor_id=v.id)
        result = vendor_service.delete_vendor(db, v.id)
        assert "deactivated" in result["message"]

    def test_delete_nonexistent_raises_404(self, db):
        with pytest.raises(HTTPException):
            vendor_service.delete_vendor(db, 999999)
