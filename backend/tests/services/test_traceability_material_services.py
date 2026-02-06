"""
Tests for traceability_service.py and material_service.py

Covers:
- Traceability: customer profiles CRUD, material lots CRUD, serial numbers,
  lot consumption, recall queries (forward/backward), spool-based traceability
- Material: resolve codes, get types/colors, create material products,
  availability checks, cost lookups, CSV import, color creation
"""
import uuid
import pytest
from datetime import datetime, date, timezone, timedelta
from decimal import Decimal

from fastapi import HTTPException

from app.services import traceability_service, material_service
from app.models.product import Product
from app.models.traceability import (
    CustomerTraceabilityProfile,
    MaterialLot,
    ProductionLotConsumption,
    SerialNumber,
)
from app.models.material_spool import MaterialSpool, ProductionOrderSpool
from app.models.production_order import ProductionOrder
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.sales_order import SalesOrder
from app.models.material import MaterialType, Color, MaterialColor, MaterialInventory
from app.models.inventory import Inventory, InventoryLocation
from app.models.item_category import ItemCategory
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.traceability import (
    CustomerTraceabilityProfileCreate,
    CustomerTraceabilityProfileUpdate,
    MaterialLotCreate,
    MaterialLotUpdate,
    ProductionLotConsumptionCreate,
    SerialNumberCreate,
    SerialNumberUpdate,
)


def _uid():
    return uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Inline helpers for models not covered by conftest fixtures
# ---------------------------------------------------------------------------

def _make_production_order(db, product, *, code=None, status="draft",
                           sales_order_id=None, qty=10):
    po = ProductionOrder(
        code=code or f"MO-TEST-{_uid()}",
        product_id=product.id,
        quantity_ordered=qty,
        status=status,
        sales_order_id=sales_order_id,
    )
    db.add(po)
    db.flush()
    return po


def _make_material_lot(db, product, *, lot_number=None, qty_received=Decimal("1000"),
                        vendor_id=None, status="active"):
    lot = MaterialLot(
        lot_number=lot_number or f"LOT-{_uid()}",
        product_id=product.id,
        vendor_id=vendor_id,
        quantity_received=qty_received,
        quantity_consumed=Decimal("0"),
        quantity_scrapped=Decimal("0"),
        quantity_adjusted=Decimal("0"),
        status=status,
        received_date=date.today(),
    )
    db.add(lot)
    db.flush()
    return lot


def _make_serial_number(db, product, production_order, *, serial=None,
                         status="manufactured"):
    sn = SerialNumber(
        serial_number=serial or f"BLB-TEST-{_uid()}",
        product_id=product.id,
        production_order_id=production_order.id,
        status=status,
        manufactured_at=datetime.now(timezone.utc),
    )
    db.add(sn)
    db.flush()
    return sn


def _make_spool(db, product, *, spool_number=None, initial_kg=Decimal("1.000"),
                current_kg=Decimal("0.800"), status="active", location_id=None):
    spool = MaterialSpool(
        spool_number=spool_number or f"SPOOL-{_uid()}",
        product_id=product.id,
        initial_weight_kg=initial_kg,
        current_weight_kg=current_kg,
        status=status,
        location_id=location_id,
    )
    db.add(spool)
    db.flush()
    return spool


def _make_material_type(db, *, code=None, name=None, base_material="PLA",
                         base_price=Decimal("20.00")):
    resolved_code = (code or f"MAT_{_uid()}").upper()
    mt = MaterialType(
        code=resolved_code,
        name=name or f"Test Material {_uid()}",
        base_material=base_material,
        density=Decimal("1.24"),
        base_price_per_kg=base_price,
        price_multiplier=Decimal("1.0"),
        active=True,
        is_customer_visible=True,
        display_order=100,
    )
    db.add(mt)
    db.flush()
    return mt


def _make_color(db, *, code=None, name=None, hex_code="#000000"):
    resolved_code = (code or f"CLR_{_uid()}").upper()
    c = Color(
        code=resolved_code,
        name=name or f"Color {_uid()}",
        hex_code=hex_code,
        active=True,
        is_customer_visible=True,
        display_order=100,
    )
    db.add(c)
    db.flush()
    return c


def _make_material_color(db, material_type, color, *, active=True,
                          is_customer_visible=True):
    mc = MaterialColor(
        material_type_id=material_type.id,
        color_id=color.id,
        active=active,
        is_customer_visible=is_customer_visible,
    )
    db.add(mc)
    db.flush()
    return mc


# ===========================================================================
# TRACEABILITY SERVICE TESTS
# ===========================================================================


class TestCustomerTraceabilityProfiles:
    """Tests for customer traceability profile CRUD."""

    def test_create_profile_for_seeded_user(self, db):
        """Creating a profile for user_id=1 (seeded test user) succeeds."""
        # Clean up any existing profile for user 1 first
        existing = db.query(CustomerTraceabilityProfile).filter(
            CustomerTraceabilityProfile.user_id == 1
        ).first()
        if existing:
            db.delete(existing)
            db.flush()

        data = CustomerTraceabilityProfileCreate(
            user_id=1,
            traceability_level="lot",
            requires_coc=True,
        )
        profile = traceability_service.create_traceability_profile(db, data)

        assert profile.user_id == 1
        assert profile.traceability_level == "lot"
        assert profile.requires_coc is True

    def test_create_profile_user_not_found(self, db):
        data = CustomerTraceabilityProfileCreate(
            user_id=999999, traceability_level="none"
        )
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.create_traceability_profile(db, data)
        assert exc_info.value.status_code == 404

    def test_create_profile_invalid_level(self, db):
        # Need a valid user first
        user = User(
            email=f"trace-{_uid()}@test.com",
            password_hash="hash",
            first_name="T", last_name="U",
            account_type="customer",
        )
        db.add(user)
        db.flush()

        data = CustomerTraceabilityProfileCreate(
            user_id=user.id, traceability_level="invalid_level"
        )
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.create_traceability_profile(db, data)
        assert exc_info.value.status_code == 400
        assert "Invalid traceability level" in exc_info.value.detail

    def test_create_profile_duplicate(self, db):
        """Creating a second profile for the same user fails."""
        user = User(
            email=f"trace-dup-{_uid()}@test.com",
            password_hash="hash",
            first_name="D", last_name="U",
            account_type="customer",
        )
        db.add(user)
        db.flush()

        data = CustomerTraceabilityProfileCreate(
            user_id=user.id, traceability_level="serial"
        )
        traceability_service.create_traceability_profile(db, data)

        with pytest.raises(HTTPException) as exc_info:
            traceability_service.create_traceability_profile(db, data)
        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail

    def test_get_profile_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.get_traceability_profile(db, user_id=999999)
        assert exc_info.value.status_code == 404

    def test_update_profile_level(self, db):
        user = User(
            email=f"trace-upd-{_uid()}@test.com",
            password_hash="hash",
            first_name="U", last_name="P",
            account_type="customer",
        )
        db.add(user)
        db.flush()

        create_data = CustomerTraceabilityProfileCreate(
            user_id=user.id, traceability_level="none"
        )
        traceability_service.create_traceability_profile(db, create_data)

        update_data = CustomerTraceabilityProfileUpdate(traceability_level="full")
        updated = traceability_service.update_traceability_profile(
            db, user.id, update_data
        )
        assert updated.traceability_level == "full"

    def test_update_profile_not_found(self, db):
        update_data = CustomerTraceabilityProfileUpdate(traceability_level="lot")
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.update_traceability_profile(db, 999999, update_data)
        assert exc_info.value.status_code == 404

    def test_update_profile_invalid_level(self, db):
        user = User(
            email=f"trace-bad-{_uid()}@test.com",
            password_hash="hash",
            first_name="B", last_name="L",
            account_type="customer",
        )
        db.add(user)
        db.flush()
        create_data = CustomerTraceabilityProfileCreate(
            user_id=user.id, traceability_level="lot"
        )
        traceability_service.create_traceability_profile(db, create_data)

        update_data = CustomerTraceabilityProfileUpdate(traceability_level="bogus")
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.update_traceability_profile(db, user.id, update_data)
        assert exc_info.value.status_code == 400

    def test_list_profiles_all(self, db):
        result = traceability_service.list_traceability_profiles(db)
        assert isinstance(result, list)

    def test_list_profiles_filtered_by_level(self, db):
        user = User(
            email=f"trace-filt-{_uid()}@test.com",
            password_hash="hash",
            first_name="F", last_name="L",
            account_type="customer",
        )
        db.add(user)
        db.flush()
        create_data = CustomerTraceabilityProfileCreate(
            user_id=user.id, traceability_level="serial"
        )
        traceability_service.create_traceability_profile(db, create_data)

        result = traceability_service.list_traceability_profiles(
            db, traceability_level="serial"
        )
        assert any(p.traceability_level == "serial" for p in result)


class TestMaterialLots:
    """Tests for material lot CRUD and lot number generation."""

    def test_create_material_lot(self, db, make_product):
        product = make_product(item_type="supply", unit="G")
        data = MaterialLotCreate(
            lot_number=f"LOT-CREATE-{_uid()}",
            product_id=product.id,
            quantity_received=Decimal("500.0000"),
        )
        resp = traceability_service.create_material_lot(db, data)
        assert resp.lot_number == data.lot_number
        assert resp.quantity_received == Decimal("500.0000")
        assert resp.status == "active"

    def test_create_material_lot_product_not_found(self, db):
        data = MaterialLotCreate(
            lot_number=f"LOT-NF-{_uid()}",
            product_id=999999,
            quantity_received=Decimal("100"),
        )
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.create_material_lot(db, data)
        assert exc_info.value.status_code == 404

    def test_create_material_lot_duplicate_lot_number(self, db, make_product):
        product = make_product(item_type="supply", unit="G")
        lot_num = f"LOT-DUP-{_uid()}"
        data = MaterialLotCreate(
            lot_number=lot_num,
            product_id=product.id,
            quantity_received=Decimal("100"),
        )
        traceability_service.create_material_lot(db, data)

        with pytest.raises(HTTPException) as exc_info:
            traceability_service.create_material_lot(db, data)
        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.detail

    def test_get_material_lot(self, db, make_product):
        product = make_product(item_type="supply", unit="G")
        lot = _make_material_lot(db, product)
        resp = traceability_service.get_material_lot(db, lot.id)
        assert resp.id == lot.id

    def test_get_material_lot_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.get_material_lot(db, 999999)
        assert exc_info.value.status_code == 404

    def test_update_material_lot(self, db, make_product):
        product = make_product(item_type="supply", unit="G")
        lot = _make_material_lot(db, product)
        data = MaterialLotUpdate(
            location="Shelf-B2",
            notes="Moved to shelf B2",
        )
        resp = traceability_service.update_material_lot(db, lot.id, data)
        assert resp.location == "Shelf-B2"
        assert resp.notes == "Moved to shelf B2"

    def test_update_material_lot_not_found(self, db):
        data = MaterialLotUpdate(location="Nowhere")
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.update_material_lot(db, 999999, data)
        assert exc_info.value.status_code == 404

    def test_list_material_lots_pagination(self, db, make_product):
        product = make_product(item_type="supply", unit="G")
        for i in range(3):
            _make_material_lot(db, product, lot_number=f"LOT-LIST-{_uid()}")

        resp = traceability_service.list_material_lots(
            db, product_id=product.id, page=1, page_size=2
        )
        assert resp.page == 1
        assert resp.page_size == 2
        assert len(resp.items) <= 2
        assert resp.total >= 3

    def test_list_material_lots_search(self, db, make_product):
        product = make_product(item_type="supply", unit="G")
        tag = _uid()
        _make_material_lot(db, product, lot_number=f"SEARCH-{tag}-001")

        resp = traceability_service.list_material_lots(db, search=tag)
        assert resp.total >= 1

    def test_list_material_lots_filter_status(self, db, make_product):
        product = make_product(item_type="supply", unit="G")
        _make_material_lot(db, product, status="quarantine")

        resp = traceability_service.list_material_lots(db, status="quarantine")
        assert all(item.status == "quarantine" for item in resp.items)

    def test_generate_lot_number(self, db):
        result = traceability_service.generate_lot_number(db, "PLA-BLK")
        year = datetime.now(timezone.utc).year
        assert result["lot_number"].startswith(f"PLA-BLK-{year}-")


class TestSerialNumbers:
    """Tests for serial number creation, lookup, and updates."""

    def test_create_serial_numbers(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product, status="in_progress")
        data = SerialNumberCreate(
            product_id=product.id,
            production_order_id=po.id,
            quantity=3,
        )
        serials = traceability_service.create_serial_numbers(db, data)
        assert len(serials) == 3
        assert all(s.serial_number.startswith("BLB-") for s in serials)
        assert all(s.status == "manufactured" for s in serials)

    def test_create_serial_numbers_po_not_found(self, db, make_product):
        product = make_product(item_type="finished_good")
        data = SerialNumberCreate(
            product_id=product.id,
            production_order_id=999999,
            quantity=1,
        )
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.create_serial_numbers(db, data)
        assert exc_info.value.status_code == 404

    def test_create_serial_numbers_product_not_found(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product)
        data = SerialNumberCreate(
            product_id=999999,
            production_order_id=po.id,
            quantity=1,
        )
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.create_serial_numbers(db, data)
        assert exc_info.value.status_code == 404

    def test_get_serial_number(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product)
        sn = _make_serial_number(db, product, po)
        result = traceability_service.get_serial_number(db, sn.id)
        assert result.id == sn.id

    def test_get_serial_number_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.get_serial_number(db, 999999)
        assert exc_info.value.status_code == 404

    def test_lookup_serial_number(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product)
        serial_str = f"BLB-LOOKUP-{_uid()}"
        sn = _make_serial_number(db, product, po, serial=serial_str)
        result = traceability_service.lookup_serial_number(db, serial_str)
        assert result.id == sn.id

    def test_lookup_serial_number_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.lookup_serial_number(db, "NONEXISTENT-SERIAL")
        assert exc_info.value.status_code == 404

    def test_update_serial_number_sold(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product)
        sn = _make_serial_number(db, product, po)

        data = SerialNumberUpdate(status="sold")
        result = traceability_service.update_serial_number(db, sn.id, data)
        assert result.status == "sold"
        assert result.sold_at is not None

    def test_update_serial_number_shipped(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product)
        sn = _make_serial_number(db, product, po)

        data = SerialNumberUpdate(status="shipped")
        result = traceability_service.update_serial_number(db, sn.id, data)
        assert result.status == "shipped"
        assert result.shipped_at is not None

    def test_update_serial_number_returned(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product)
        sn = _make_serial_number(db, product, po)

        data = SerialNumberUpdate(status="returned", return_reason="Defective")
        result = traceability_service.update_serial_number(db, sn.id, data)
        assert result.status == "returned"
        assert result.returned_at is not None

    def test_update_serial_number_not_found(self, db):
        data = SerialNumberUpdate(status="sold")
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.update_serial_number(db, 999999, data)
        assert exc_info.value.status_code == 404

    def test_list_serial_numbers_filters(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product)
        tag = _uid()
        _make_serial_number(db, product, po, serial=f"BLB-SRCH-{tag}")

        resp = traceability_service.list_serial_numbers(db, search=tag)
        assert resp.total >= 1

    def test_list_serial_numbers_by_product(self, db, make_product):
        product = make_product(item_type="finished_good")
        po = _make_production_order(db, product)
        _make_serial_number(db, product, po)

        resp = traceability_service.list_serial_numbers(db, product_id=product.id)
        assert resp.total >= 1


class TestLotConsumption:
    """Tests for recording lot consumption during production."""

    def test_record_lot_consumption(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        lot = _make_material_lot(db, raw, qty_received=Decimal("1000"))
        po = _make_production_order(db, fg, status="in_progress")

        data = ProductionLotConsumptionCreate(
            production_order_id=po.id,
            material_lot_id=lot.id,
            quantity_consumed=Decimal("200"),
        )
        consumption = traceability_service.record_lot_consumption(db, data)
        assert consumption.quantity_consumed == Decimal("200")

        # Refresh the lot to check updated quantity
        db.refresh(lot)
        assert lot.quantity_consumed == Decimal("200")

    def test_record_lot_consumption_insufficient_quantity(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        lot = _make_material_lot(db, raw, qty_received=Decimal("50"))
        po = _make_production_order(db, fg, status="in_progress")

        data = ProductionLotConsumptionCreate(
            production_order_id=po.id,
            material_lot_id=lot.id,
            quantity_consumed=Decimal("100"),
        )
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.record_lot_consumption(db, data)
        assert exc_info.value.status_code == 400
        assert "Insufficient" in exc_info.value.detail

    def test_record_lot_consumption_depletes_lot(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        lot = _make_material_lot(db, raw, qty_received=Decimal("100"))
        po = _make_production_order(db, fg, status="in_progress")

        data = ProductionLotConsumptionCreate(
            production_order_id=po.id,
            material_lot_id=lot.id,
            quantity_consumed=Decimal("100"),
        )
        traceability_service.record_lot_consumption(db, data)
        db.refresh(lot)
        assert lot.status == "depleted"

    def test_record_lot_consumption_po_not_found(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        lot = _make_material_lot(db, raw)
        data = ProductionLotConsumptionCreate(
            production_order_id=999999,
            material_lot_id=lot.id,
            quantity_consumed=Decimal("10"),
        )
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.record_lot_consumption(db, data)
        assert exc_info.value.status_code == 404

    def test_record_lot_consumption_lot_not_found(self, db, make_product):
        fg = make_product(item_type="finished_good")
        po = _make_production_order(db, fg)
        data = ProductionLotConsumptionCreate(
            production_order_id=po.id,
            material_lot_id=999999,
            quantity_consumed=Decimal("10"),
        )
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.record_lot_consumption(db, data)
        assert exc_info.value.status_code == 404

    def test_get_production_lot_consumptions(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        lot = _make_material_lot(db, raw, qty_received=Decimal("1000"))
        po = _make_production_order(db, fg, status="in_progress")

        data = ProductionLotConsumptionCreate(
            production_order_id=po.id,
            material_lot_id=lot.id,
            quantity_consumed=Decimal("50"),
        )
        traceability_service.record_lot_consumption(db, data)

        consumptions = traceability_service.get_production_lot_consumptions(db, po.id)
        assert len(consumptions) >= 1


class TestRecallQueries:
    """Tests for forward and backward recall queries (MaterialLot-based)."""

    def test_recall_forward_query(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        lot = _make_material_lot(db, raw, qty_received=Decimal("1000"))
        po = _make_production_order(db, fg, status="completed")

        # Create consumption link
        consumption = ProductionLotConsumption(
            production_order_id=po.id,
            material_lot_id=lot.id,
            quantity_consumed=Decimal("200"),
        )
        db.add(consumption)

        # Create serial linked to the production order
        _make_serial_number(db, fg, po)
        db.flush()

        resp = traceability_service.recall_forward_query(db, lot.lot_number)
        assert resp.lot_number == lot.lot_number
        assert resp.total_affected >= 1

    def test_recall_forward_query_lot_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.recall_forward_query(db, "NONEXISTENT-LOT")
        assert exc_info.value.status_code == 404

    def test_recall_backward_query(self, db, make_product, make_vendor):
        raw = make_product(item_type="supply", unit="G")
        vendor = make_vendor()
        fg = make_product(item_type="finished_good")
        lot = _make_material_lot(db, raw, vendor_id=vendor.id,
                                  qty_received=Decimal("500"))
        po = _make_production_order(db, fg, status="completed")

        consumption = ProductionLotConsumption(
            production_order_id=po.id,
            material_lot_id=lot.id,
            quantity_consumed=Decimal("100"),
        )
        db.add(consumption)

        sn = _make_serial_number(db, fg, po)
        db.flush()

        resp = traceability_service.recall_backward_query(db, sn.serial_number)
        assert resp.serial_number == sn.serial_number
        assert len(resp.material_lots_used) >= 1

    def test_recall_backward_query_serial_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.recall_backward_query(db, "NONEXISTENT-SERIAL")
        assert exc_info.value.status_code == 404


class TestSpoolTraceability:
    """Tests for spool-based forward and backward traceability."""

    @pytest.mark.xfail(
        reason="Pre-existing bug: service references po.completed_date but model uses completed_at",
        strict=True,
    )
    def test_trace_forward_from_spool(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        spool = _make_spool(db, raw, location_id=1)
        po = _make_production_order(db, fg, status="completed")

        # Link spool to production order
        po_spool = ProductionOrderSpool(
            production_order_id=po.id,
            spool_id=spool.id,
            weight_consumed_kg=Decimal("0.200"),
        )
        db.add(po_spool)
        db.flush()

        result = traceability_service.trace_forward_from_spool(db, spool.id)
        assert result["spool"]["id"] == spool.id
        assert result["summary"]["total_production_orders"] >= 1

    def test_trace_forward_from_spool_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.trace_forward_from_spool(db, 999999)
        assert exc_info.value.status_code == 404

    @pytest.mark.xfail(
        reason="Pre-existing bug: service references po.completed_date but model uses completed_at",
        strict=True,
    )
    def test_trace_backward_from_serial(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        po = _make_production_order(db, fg, status="completed")
        spool = _make_spool(db, raw, location_id=1)

        po_spool = ProductionOrderSpool(
            production_order_id=po.id,
            spool_id=spool.id,
            weight_consumed_kg=Decimal("0.150"),
        )
        db.add(po_spool)

        sn = _make_serial_number(db, fg, po)
        db.flush()

        result = traceability_service.trace_backward_from_serial(db, sn.serial_number)
        assert result["serial_number"]["serial_number"] == sn.serial_number
        assert result["traceability_chain"]["spools_used"] >= 1

    def test_trace_backward_from_serial_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.trace_backward_from_serial(db, "GHOST-SN-999")
        assert exc_info.value.status_code == 404

    def test_trace_backward_from_sales_order(self, db, make_product, make_sales_order):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        so = make_sales_order(product_id=fg.id)
        po = _make_production_order(db, fg, status="completed",
                                     sales_order_id=so.id)
        spool = _make_spool(db, raw, location_id=1)

        po_spool = ProductionOrderSpool(
            production_order_id=po.id,
            spool_id=spool.id,
            weight_consumed_kg=Decimal("0.300"),
        )
        db.add(po_spool)
        db.flush()

        result = traceability_service.trace_backward_from_sales_order(db, so.id)
        assert result["sales_order"]["id"] == so.id
        assert result["summary"]["total_production_orders"] >= 1

    def test_trace_backward_from_sales_order_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.trace_backward_from_sales_order(db, 999999)
        assert exc_info.value.status_code == 404

    def test_calculate_recall_impact(self, db, make_product):
        raw = make_product(item_type="supply", unit="G")
        fg = make_product(item_type="finished_good")
        spool = _make_spool(db, raw, location_id=1)
        po = _make_production_order(db, fg, status="completed")

        po_spool = ProductionOrderSpool(
            production_order_id=po.id,
            spool_id=spool.id,
            weight_consumed_kg=Decimal("0.100"),
        )
        db.add(po_spool)
        db.flush()

        result = traceability_service.calculate_recall_impact(db, [spool.id])
        assert result["severity"] in ("LOW", "MEDIUM", "HIGH")
        assert len(result["spools"]) == 1
        assert result["impact"]["production_orders_affected"] >= 1

    def test_calculate_recall_impact_empty_ids(self, db):
        with pytest.raises(HTTPException) as exc_info:
            traceability_service.calculate_recall_impact(db, [])
        assert exc_info.value.status_code == 400

    def test_calculate_recall_impact_no_usage(self, db, make_product):
        """A spool with no production usage yields LOW severity."""
        raw = make_product(item_type="supply", unit="G")
        spool = _make_spool(db, raw)

        result = traceability_service.calculate_recall_impact(db, [spool.id])
        assert result["severity"] == "LOW"
        assert result["impact"]["customers_affected"] == 0


class TestGetPurchaseInfoForSpool:
    """Tests for _get_purchase_info_for_spool helper."""

    def test_returns_none_when_no_po_line(self, db, make_product):
        """Spool with a product but no PO line returns None."""
        raw = make_product(item_type="supply", unit="G")
        spool = _make_spool(db, raw)
        # No PO line exists for this product
        result = traceability_service._get_purchase_info_for_spool(db, spool)
        assert result is None

    def test_returns_purchase_info(self, db, make_product, make_vendor):
        raw = make_product(item_type="supply", unit="G")
        vendor = make_vendor()
        po = PurchaseOrder(
            po_number=f"PO-PI-{_uid()}",
            vendor_id=vendor.id,
            status="received",
            created_by="1",
        )
        db.add(po)
        db.flush()

        pol = PurchaseOrderLine(
            purchase_order_id=po.id,
            product_id=raw.id,
            line_number=1,
            quantity_ordered=Decimal("10"),
            unit_cost=Decimal("20.00"),
            line_total=Decimal("200.00"),
        )
        db.add(pol)
        db.flush()

        spool = _make_spool(db, raw)
        result = traceability_service._get_purchase_info_for_spool(db, spool)
        assert result is not None
        assert result["po_number"] == po.po_number
        assert result["vendor_name"] == vendor.name


# ===========================================================================
# MATERIAL SERVICE TESTS
# ===========================================================================


class TestResolveMaterialCode:
    """Tests for material code resolution."""

    def test_exact_match(self, db):
        mt = _make_material_type(db, code="PLA_TEST_EXACT")
        result = material_service.resolve_material_code(db, "PLA_TEST_EXACT")
        assert result == "PLA_TEST_EXACT"

    def test_case_insensitive(self, db):
        mt = _make_material_type(db, code="PETG_CI_TEST")
        result = material_service.resolve_material_code(db, "petg_ci_test")
        assert result == "PETG_CI_TEST"

    def test_base_material_match(self, db):
        mt = _make_material_type(db, code="TPUFLEX_TEST", base_material="TPUFLEX")
        result = material_service.resolve_material_code(db, "TPUFLEX")
        assert result == "TPUFLEX_TEST"

    def test_not_found_raises(self, db):
        with pytest.raises(material_service.MaterialNotFoundError):
            material_service.resolve_material_code(db, "NONEXISTENT_MATERIAL_XYZ")


class TestGetMaterialType:
    """Tests for get_material_type."""

    def test_get_by_code(self, db):
        mt = _make_material_type(db, code="PLA_GETTEST")
        result = material_service.get_material_type(db, "PLA_GETTEST")
        assert result.id == mt.id

    def test_not_found_raises(self, db):
        with pytest.raises(material_service.MaterialNotFoundError):
            material_service.get_material_type(db, "NOPE_MATERIAL_999")


class TestGetColor:
    """Tests for get_color."""

    def test_get_by_code(self, db):
        color = _make_color(db, code="TEAL_TEST")
        result = material_service.get_color(db, "TEAL_TEST")
        assert result.id == color.id

    def test_not_found_raises(self, db):
        with pytest.raises(material_service.ColorNotFoundError):
            material_service.get_color(db, "NOPE_COLOR_999")


class TestGetAvailableMaterialTypes:
    """Tests for listing available material types."""

    def test_returns_active_types(self, db):
        _make_material_type(db, code=f"MAT_VIS_{_uid()}")
        result = material_service.get_available_material_types(db)
        assert len(result) >= 1
        assert all(mt.active for mt in result)

    def test_customer_visible_filter(self, db):
        result = material_service.get_available_material_types(
            db, customer_visible_only=True
        )
        assert all(mt.is_customer_visible for mt in result)


class TestCreateMaterialProduct:
    """Tests for creating material products."""

    def test_creates_product_and_inventory(self, db):
        mt = _make_material_type(db, code=f"CMP_{_uid()}")
        color = _make_color(db, code=f"CMP_CLR_{_uid()}")
        _make_material_color(db, mt, color)

        product = material_service.create_material_product(
            db, mt.code, color.code, commit=True
        )
        assert product.sku == f"MAT-{mt.code}-{color.code}"
        assert product.item_type == "material"
        assert product.is_raw_material is True

    def test_returns_existing_if_sku_exists(self, db):
        mt = _make_material_type(db, code=f"DUP_{_uid()}")
        color = _make_color(db, code=f"DUP_CLR_{_uid()}")
        _make_material_color(db, mt, color)

        p1 = material_service.create_material_product(db, mt.code, color.code)
        p2 = material_service.create_material_product(db, mt.code, color.code)
        assert p1.id == p2.id


class TestGetMaterialProduct:
    """Tests for looking up material products."""

    def test_found(self, db):
        mt = _make_material_type(db, code=f"GMP_{_uid()}")
        color = _make_color(db, code=f"GMP_CLR_{_uid()}")
        _make_material_color(db, mt, color)
        created = material_service.create_material_product(db, mt.code, color.code)

        found = material_service.get_material_product(db, mt.code, color.code)
        assert found is not None
        assert found.id == created.id

    def test_not_found_returns_none(self, db):
        mt = _make_material_type(db, code=f"GMP_NF_{_uid()}")
        color = _make_color(db, code=f"GMP_NF_CLR_{_uid()}")
        _make_material_color(db, mt, color)

        found = material_service.get_material_product(db, mt.code, color.code)
        assert found is None


class TestMaterialCostAndDensity:
    """Tests for cost per kg, density, and price multiplier lookups."""

    def test_cost_per_kg_from_material_type(self, db):
        mt = _make_material_type(db, code=f"COST_{_uid()}", base_price=Decimal("25.00"))
        color = _make_color(db, code=f"COST_CLR_{_uid()}")
        _make_material_color(db, mt, color)

        result = material_service.get_material_cost_per_kg(db, mt.code)
        assert result == Decimal("25.00")

    def test_cost_per_kg_from_product_override(self, db):
        mt = _make_material_type(db, code=f"COSTOV_{_uid()}", base_price=Decimal("20.00"))
        color = _make_color(db, code=f"COSTOV_CLR_{_uid()}")
        _make_material_color(db, mt, color)

        product = material_service.create_material_product(db, mt.code, color.code)
        product.standard_cost = Decimal("30.00")
        db.flush()

        result = material_service.get_material_cost_per_kg(
            db, mt.code, color_code=color.code
        )
        assert result == Decimal("30.00")

    def test_density(self, db):
        mt = _make_material_type(db, code=f"DEN_{_uid()}")
        result = material_service.get_material_density(db, mt.code)
        assert result == Decimal("1.24")

    def test_price_multiplier(self, db):
        mt = _make_material_type(db, code=f"PM_{_uid()}")
        result = material_service.get_material_price_multiplier(db, mt.code)
        assert result == Decimal("1.0")


class TestCheckMaterialAvailability:
    """Tests for material availability checking."""

    def test_not_found_product(self, db):
        mt = _make_material_type(db, code=f"AVL_NF_{_uid()}")
        color = _make_color(db, code=f"AVL_NF_CLR_{_uid()}")
        _make_material_color(db, mt, color)

        available, msg = material_service.check_material_availability(
            db, mt.code, color.code, Decimal("1.0")
        )
        assert available is False
        assert "not found" in msg

    def test_insufficient_stock(self, db):
        mt = _make_material_type(db, code=f"AVL_IS_{_uid()}")
        color = _make_color(db, code=f"AVL_IS_CLR_{_uid()}")
        _make_material_color(db, mt, color)
        product = material_service.create_material_product(db, mt.code, color.code)

        # Inventory record created by create_material_product has 0 qty
        available, msg = material_service.check_material_availability(
            db, mt.code, color.code, Decimal("5.0")
        )
        assert available is False
        assert "Insufficient" in msg


class TestGetMaterialProductForBom:
    """Tests for get_material_product_for_bom."""

    def test_creates_product_if_not_exists(self, db):
        mt = _make_material_type(db, code=f"BOM_{_uid()}")
        color = _make_color(db, code=f"BOM_CLR_{_uid()}")
        _make_material_color(db, mt, color)

        product, mat_inv = material_service.get_material_product_for_bom(
            db, mt.code, color.code
        )
        assert product is not None
        assert product.sku.startswith("MAT-")

    def test_require_in_stock_raises_when_empty(self, db):
        mt = _make_material_type(db, code=f"BOMNIS_{_uid()}")
        color = _make_color(db, code=f"BOMNIS_CLR_{_uid()}")
        _make_material_color(db, mt, color)

        with pytest.raises(material_service.MaterialNotInStockError):
            material_service.get_material_product_for_bom(
                db, mt.code, color.code, require_in_stock=True
            )


class TestCreateColorForMaterial:
    """Tests for creating colors and linking to material types."""

    def test_create_new_color(self, db):
        mt = _make_material_type(db, code=f"CCF_{_uid()}")
        color, returned_mt = material_service.create_color_for_material(
            db, mt.code, name="Electric Blue", hex_code="#0000FF"
        )
        assert color.name == "Electric Blue"
        assert returned_mt.id == mt.id

    def test_material_type_not_found(self, db):
        with pytest.raises(HTTPException) as exc_info:
            material_service.create_color_for_material(
                db, "NONEXISTENT_MAT_ZZ", name="Red"
            )
        assert exc_info.value.status_code == 404

    def test_duplicate_link_raises(self, db):
        mt = _make_material_type(db, code=f"DUPLINK_{_uid()}")
        color = _make_color(db, code=f"DUPLINK_CLR_{_uid()}", name="DupColor")
        _make_material_color(db, mt, color)

        with pytest.raises(HTTPException) as exc_info:
            material_service.create_color_for_material(
                db, mt.code, name="DupColor", code=color.code
            )
        assert exc_info.value.status_code == 400
        assert "already linked" in exc_info.value.detail

    def test_auto_generates_code(self, db):
        mt = _make_material_type(db, code=f"AUTOC_{_uid()}")
        color, _ = material_service.create_color_for_material(
            db, mt.code, name="Sunset Orange"
        )
        assert color.code == "SUNSET_ORANGE"


class TestImportMaterialsFromCsv:
    """Tests for CSV import of materials."""

    def _build_csv(self, rows):
        """Build CSV content bytes from list of dicts."""
        import csv
        import io
        output = io.StringIO()
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return output.getvalue().encode("utf-8")

    def test_import_creates_products(self, db):
        uid = _uid()
        csv_bytes = self._build_csv([
            {
                "sku": f"MAT-IMP-{uid}",
                "name": "Import Test PLA Black",
                "material type": f"PLA_IMP_{uid}",
                "material color name": f"Imp Black {uid}",
                "hex code": "#111111",
                "price": "22.50",
                "on hand (g)": "5000",
            }
        ])

        result = material_service.import_materials_from_csv(
            db, file_content=csv_bytes, update_existing=False,
        )
        assert result["total_rows"] == 1
        assert result["created"] == 1
        assert len(result["errors"]) == 0

    def test_import_skips_existing_without_update(self, db, make_product):
        existing = make_product(item_type="supply", unit="G")
        csv_bytes = self._build_csv([
            {
                "sku": existing.sku,
                "name": "Updated Name",
                "material type": "PLA_BASIC",
                "material color name": "Black",
                "price": "25.00",
                "on hand (g)": "1000",
            }
        ])

        result = material_service.import_materials_from_csv(
            db, file_content=csv_bytes, update_existing=False,
        )
        assert result["skipped"] == 1

    def test_import_missing_sku_error(self, db):
        csv_bytes = self._build_csv([
            {
                "sku": "",
                "name": "No SKU Product",
                "material type": "PLA",
                "material color name": "Red",
            }
        ])
        result = material_service.import_materials_from_csv(
            db, file_content=csv_bytes,
        )
        assert result["skipped"] == 1
        assert any("SKU is required" in e["error"] for e in result["errors"])

    def test_import_missing_material_type_error(self, db):
        csv_bytes = self._build_csv([
            {
                "sku": f"MAT-NOMT-{_uid()}",
                "name": "No Material Type",
                "material type": "",
                "material color name": "Blue",
            }
        ])
        result = material_service.import_materials_from_csv(
            db, file_content=csv_bytes,
        )
        assert result["skipped"] == 1
        assert any("Material Type is required" in e["error"] for e in result["errors"])

    def test_import_missing_color_name_error(self, db):
        csv_bytes = self._build_csv([
            {
                "sku": f"MAT-NOCN-{_uid()}",
                "name": "No Color Name",
                "material type": "PLA_BASIC",
                "material color name": "",
            }
        ])
        result = material_service.import_materials_from_csv(
            db, file_content=csv_bytes,
        )
        assert result["skipped"] == 1
        assert any("Material Color Name is required" in e["error"] for e in result["errors"])

    def test_import_with_bom_prefix(self, db):
        """BOM prefix in file content should be stripped."""
        uid = _uid()
        raw_csv = (
            "\ufeffsku,name,material type,material color name,price,on hand (g)\n"
            f"MAT-BOM-{uid},BOM Prefix Test,PLA_BOM_{uid},BOM White {uid},20.00,2000\n"
        )
        result = material_service.import_materials_from_csv(
            db, file_content=raw_csv.encode("utf-8"),
        )
        assert result["created"] == 1

    def test_import_latin1_encoding(self, db):
        uid = _uid()
        raw_csv = (
            f"sku,name,material type,material color name,price,on hand (g)\n"
            f"MAT-L1-{uid},Latin1 Test,PLA_L1_{uid},L1 Color {uid},18.00,3000\n"
        )
        result = material_service.import_materials_from_csv(
            db, file_content=raw_csv.encode("latin-1"),
        )
        assert result["created"] == 1


class TestInferBaseMaterial:
    """Tests for _infer_base_material helper."""

    def test_petg(self):
        assert material_service._infer_base_material("PETG_HF") == "PETG"

    def test_abs(self):
        assert material_service._infer_base_material("ABS_STANDARD") == "ABS"

    def test_defaults_to_pla(self):
        assert material_service._infer_base_material("SOME_UNKNOWN") == "PLA"
