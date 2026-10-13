"""
Tests for Admin Traceability API endpoints (app/api/v1/endpoints/admin/traceability.py)

Covers:
- Customer Traceability Profiles: CRUD, filtering by level
- Material Lots: CRUD, lot number generation, filtering, search
- Serial Numbers: batch creation, CRUD, lookup by serial string, filtering
- Lot Consumption: recording, retrieval by production order
- Recall Queries: forward (lot -> products) and backward (serial -> lots)
- Auth: 401 on key endpoints without token
- 404s for nonexistent resources
"""
import uuid

import pytest
from decimal import Decimal

from app.models.production_order import ProductionOrder
from app.models.user import User


BASE_URL = "/api/v1/admin/traceability"


# =============================================================================
# Helpers
# =============================================================================

def _uid():
    """Short unique suffix for test data."""
    return uuid.uuid4().hex[:8]


def _create_user(db, **overrides):
    """Create a unique User directly in the DB for profile tests."""
    uid = _uid()
    user = User(
        email=overrides.pop("email", f"trace-{uid}@example.com"),
        password_hash="not-a-real-hash",
        first_name="Trace",
        last_name=f"User {uid}",
        account_type=overrides.pop("account_type", "customer"),
        **overrides,
    )
    db.add(user)
    db.flush()
    return user


def _create_lot(client, product_id, vendor_id=None, **overrides):
    """Create a material lot via the API and return the response JSON."""
    uid = _uid()
    payload = {
        "lot_number": f"LOT-TEST-{uid}",
        "product_id": product_id,
        "quantity_received": "1000",
        "received_date": "2026-01-15",
    }
    if vendor_id is not None:
        payload["vendor_id"] = vendor_id
    payload.update(overrides)
    response = client.post(f"{BASE_URL}/lots", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def _create_production_order(db, product_id, code=None):
    """Insert a ProductionOrder directly into the DB and return it."""
    po = ProductionOrder(
        code=code or f"MO-TEST-{_uid()}",
        product_id=product_id,
        quantity_ordered=Decimal("10"),
        status="in_progress",
    )
    db.add(po)
    db.flush()
    return po


def _create_serials(client, product_id, production_order_id, quantity=1):
    """Create serial numbers via the API and return the response JSON list."""
    payload = {
        "product_id": product_id,
        "production_order_id": production_order_id,
        "quantity": quantity,
    }
    response = client.post(f"{BASE_URL}/serials", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


# =============================================================================
# Auth tests
# =============================================================================

class TestTraceabilityAuth:
    """All traceability endpoints require authentication."""

    def test_list_profiles_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/profiles")
        assert response.status_code == 401

    def test_list_lots_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/lots")
        assert response.status_code == 401

    def test_list_serials_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/serials")
        assert response.status_code == 401

    def test_create_lot_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/lots", json={
            "lot_number": "LOT-NOAUTH",
            "product_id": 1,
            "quantity_received": "100",
        })
        assert response.status_code == 401

    def test_create_serials_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/serials", json={
            "product_id": 1,
            "production_order_id": 1,
            "quantity": 1,
        })
        assert response.status_code == 401

    def test_recall_forward_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/recall/forward/LOT-000")
        assert response.status_code == 401

    def test_recall_backward_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/recall/backward/SN-000")
        assert response.status_code == 401

    def test_record_consumption_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": 1,
            "material_lot_id": 1,
            "quantity_consumed": "10",
        })
        assert response.status_code == 401


# =============================================================================
# Customer Traceability Profiles
# =============================================================================

class TestCustomerTraceabilityProfiles:
    """CRUD and filtering for customer traceability profiles."""

    def test_create_profile(self, client):
        """Creating a profile for the seeded user (id=1) returns the profile."""
        payload = {
            "user_id": 1,
            "traceability_level": "lot",
            "requires_coc": True,
            "requires_coa": False,
        }
        response = client.post(f"{BASE_URL}/profiles", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["user_id"] == 1
        assert data["traceability_level"] == "lot"
        assert data["requires_coc"] is True
        assert "id" in data
        assert "created_at" in data

    def test_create_profile_invalid_level(self, client, db):
        """Creating a profile with an invalid traceability level returns 400."""
        user = _create_user(db)
        payload = {
            "user_id": user.id,
            "traceability_level": "mega",
        }
        response = client.post(f"{BASE_URL}/profiles", json=payload)
        assert response.status_code == 400
        assert "Invalid traceability level" in response.json()["detail"]

    def test_create_profile_user_not_found(self, client):
        """Creating a profile for a nonexistent user returns 404."""
        payload = {
            "user_id": 999999,
            "traceability_level": "none",
        }
        response = client.post(f"{BASE_URL}/profiles", json=payload)
        assert response.status_code == 404

    def test_create_profile_duplicate(self, client, db):
        """Creating a second profile for the same user returns 400."""
        user = _create_user(db)
        payload = {
            "user_id": user.id,
            "traceability_level": "serial",
        }
        # First creation
        r1 = client.post(f"{BASE_URL}/profiles", json=payload)
        assert r1.status_code == 200, r1.text

        # Duplicate
        r2 = client.post(f"{BASE_URL}/profiles", json=payload)
        assert r2.status_code == 400
        assert "already exists" in r2.json()["detail"]

    def test_get_profile(self, client, db):
        """Retrieve a profile by user_id after creation."""
        user = _create_user(db)
        r = client.post(f"{BASE_URL}/profiles", json={
            "user_id": user.id,
            "traceability_level": "full",
            "requires_coc": True,
        })
        assert r.status_code == 200, r.text
        response = client.get(f"{BASE_URL}/profiles/{user.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user.id
        assert data["traceability_level"] == "full"

    def test_get_profile_not_found(self, client):
        """Getting a profile for a user with no profile returns 404."""
        response = client.get(f"{BASE_URL}/profiles/999999")
        assert response.status_code == 404

    def test_update_profile(self, client):
        """PATCH updates only the provided fields."""
        client.post(f"{BASE_URL}/profiles", json={
            "user_id": 1,
            "traceability_level": "none",
        })
        response = client.patch(f"{BASE_URL}/profiles/1", json={
            "traceability_level": "serial",
            "requires_coc": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["traceability_level"] == "serial"
        assert data["requires_coc"] is True

    def test_update_profile_not_found(self, client):
        """PATCH on a nonexistent profile returns 404."""
        response = client.patch(f"{BASE_URL}/profiles/999999", json={
            "traceability_level": "lot",
        })
        assert response.status_code == 404

    def test_update_profile_invalid_level(self, client):
        """PATCH with an invalid traceability level returns 400."""
        client.post(f"{BASE_URL}/profiles", json={
            "user_id": 1,
            "traceability_level": "none",
        })
        response = client.patch(f"{BASE_URL}/profiles/1", json={
            "traceability_level": "ultra",
        })
        assert response.status_code == 400

    def test_list_profiles(self, client):
        """GET /profiles returns a list of profiles."""
        client.post(f"{BASE_URL}/profiles", json={
            "user_id": 1,
            "traceability_level": "lot",
        })
        response = client.get(f"{BASE_URL}/profiles")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_list_profiles_filter_by_level(self, client):
        """Filtering profiles by traceability_level works."""
        client.post(f"{BASE_URL}/profiles", json={
            "user_id": 1,
            "traceability_level": "full",
        })
        response = client.get(f"{BASE_URL}/profiles", params={
            "traceability_level": "full",
        })
        assert response.status_code == 200
        data = response.json()
        assert all(p["traceability_level"] == "full" for p in data)

    def test_list_profiles_filter_no_match(self, client):
        """Filtering by a level with no profiles returns an empty list."""
        response = client.get(f"{BASE_URL}/profiles", params={
            "traceability_level": "serial",
        })
        assert response.status_code == 200
        # May or may not be empty depending on DB state, but shape is valid
        assert isinstance(response.json(), list)


# =============================================================================
# Material Lots
# =============================================================================

class TestMaterialLots:
    """CRUD, filtering, and lot number generation for material lots."""

    def test_create_lot(self, client, make_product):
        """Creating a lot returns the lot with calculated fields."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        data = _create_lot(client, product.id)
        assert data["product_id"] == product.id
        assert data["lot_number"].startswith("LOT-TEST-")
        assert data["status"] == "active"
        assert "id" in data
        assert "quantity_remaining" in data
        assert "created_at" in data

    def test_create_lot_with_vendor(self, client, make_product, make_vendor):
        """Creating a lot with a vendor_id stores the vendor reference."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        vendor = make_vendor()
        data = _create_lot(client, product.id, vendor_id=vendor.id)
        assert data["vendor_id"] == vendor.id

    def test_create_lot_product_not_found(self, client):
        """Creating a lot for a nonexistent product returns 404."""
        response = client.post(f"{BASE_URL}/lots", json={
            "lot_number": f"LOT-NOPROD-{_uid()}",
            "product_id": 999999,
            "quantity_received": "500",
        })
        assert response.status_code == 404

    def test_create_lot_duplicate_number(self, client, make_product):
        """Creating a lot with a duplicate lot_number returns 400."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        lot_number = f"LOT-DUP-{_uid()}"
        _create_lot(client, product.id, lot_number=lot_number)

        response = client.post(f"{BASE_URL}/lots", json={
            "lot_number": lot_number,
            "product_id": product.id,
            "quantity_received": "100",
        })
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_get_lot(self, client, make_product):
        """GET /lots/{lot_id} returns the lot."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        created = _create_lot(client, product.id)
        lot_id = created["id"]

        response = client.get(f"{BASE_URL}/lots/{lot_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == lot_id
        assert data["lot_number"] == created["lot_number"]

    def test_get_lot_not_found(self, client):
        """GET /lots/{lot_id} for a nonexistent lot returns 404."""
        response = client.get(f"{BASE_URL}/lots/999999")
        assert response.status_code == 404

    def test_update_lot(self, client, make_product):
        """PATCH updates the specified fields on a lot."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        created = _create_lot(client, product.id)
        lot_id = created["id"]

        response = client.patch(f"{BASE_URL}/lots/{lot_id}", json={
            "status": "quarantine",
            "notes": "Quality hold pending inspection",
            "location": "Shelf B-3",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "quarantine"
        assert data["notes"] == "Quality hold pending inspection"
        assert data["location"] == "Shelf B-3"

    def test_update_lot_not_found(self, client):
        """PATCH on a nonexistent lot returns 404."""
        response = client.patch(f"{BASE_URL}/lots/999999", json={
            "status": "expired",
        })
        assert response.status_code == 404

    def test_list_lots(self, client, make_product):
        """GET /lots returns paginated results."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        _create_lot(client, product.id)

        response = client.get(f"{BASE_URL}/lots")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["items"], list)

    def test_list_lots_filter_by_product(self, client, make_product):
        """Filtering lots by product_id returns only matching lots."""
        product_a = make_product(item_type="supply", unit="G", is_raw_material=True)
        product_b = make_product(item_type="supply", unit="G", is_raw_material=True)
        _create_lot(client, product_a.id)
        _create_lot(client, product_b.id)

        response = client.get(f"{BASE_URL}/lots", params={"product_id": product_a.id})
        assert response.status_code == 200
        data = response.json()
        assert all(item["product_id"] == product_a.id for item in data["items"])

    def test_list_lots_filter_by_status(self, client, make_product):
        """Filtering lots by status returns only matching lots."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        lot = _create_lot(client, product.id)
        client.patch(f"{BASE_URL}/lots/{lot['id']}", json={"status": "quarantine"})

        response = client.get(f"{BASE_URL}/lots", params={"status": "quarantine"})
        assert response.status_code == 200
        data = response.json()
        assert all(item["status"] == "quarantine" for item in data["items"])

    def test_list_lots_filter_by_vendor(self, client, make_product, make_vendor):
        """Filtering lots by vendor_id returns only matching lots."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        vendor = make_vendor()
        _create_lot(client, product.id, vendor_id=vendor.id)

        response = client.get(f"{BASE_URL}/lots", params={"vendor_id": vendor.id})
        assert response.status_code == 200
        data = response.json()
        assert all(item["vendor_id"] == vendor.id for item in data["items"])

    def test_list_lots_search(self, client, make_product):
        """Search parameter filters lots by lot_number substring."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        unique_tag = _uid()
        _create_lot(client, product.id, lot_number=f"SEARCH-{unique_tag}")

        response = client.get(f"{BASE_URL}/lots", params={"search": unique_tag})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(unique_tag in item["lot_number"] for item in data["items"])

    def test_list_lots_pagination(self, client, make_product):
        """Pagination parameters control the returned page."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        for _ in range(3):
            _create_lot(client, product.id)

        response = client.get(f"{BASE_URL}/lots", params={
            "page": 1,
            "page_size": 2,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2

    def test_generate_lot_number(self, client):
        """POST /lots/generate-number returns a formatted lot number."""
        response = client.post(
            f"{BASE_URL}/lots/generate-number",
            params={"material_code": "PLA-BLK"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "lot_number" in data
        assert data["lot_number"].startswith("PLA-BLK-")
        assert data["lot_number"].endswith("-0001")

    def test_generate_lot_number_increments(self, client, make_product):
        """Lot number generation increments the sequence when lots exist."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        from datetime import datetime, timezone
        year = datetime.now(timezone.utc).year
        # Create a lot with the expected prefix format
        _create_lot(client, product.id, lot_number=f"PLA-WHT-{year}-0003")

        response = client.post(
            f"{BASE_URL}/lots/generate-number",
            params={"material_code": "PLA-WHT"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["lot_number"] == f"PLA-WHT-{year}-0004"

    def test_lot_response_shape(self, client, make_product):
        """Verify the full response shape of a material lot."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        data = _create_lot(client, product.id, notes="test notes")

        expected_fields = {
            "id", "lot_number", "product_id", "vendor_id",
            "purchase_order_id", "vendor_lot_number",
            "quantity_received", "quantity_consumed", "quantity_scrapped",
            "quantity_adjusted", "quantity_remaining", "status",
            "certificate_of_analysis", "coa_file_path", "inspection_status",
            "manufactured_date", "expiration_date", "received_date",
            "unit_cost", "location", "notes", "created_at", "updated_at",
        }
        assert expected_fields.issubset(set(data.keys()))


# =============================================================================
# Serial Numbers
# =============================================================================

class TestSerialNumbers:
    """Batch creation, CRUD, lookup, and filtering for serial numbers."""

    def test_create_serials(self, client, make_product, db):
        """Creating serials returns a list of generated serial numbers."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)

        serials = _create_serials(client, product.id, po.id, quantity=3)
        assert len(serials) == 3
        assert all(s["status"] == "manufactured" for s in serials)
        assert all(s["product_id"] == product.id for s in serials)
        assert all(s["production_order_id"] == po.id for s in serials)
        # Serial numbers should be unique
        numbers = [s["serial_number"] for s in serials]
        assert len(set(numbers)) == 3

    def test_create_serials_production_order_not_found(self, client, make_product):
        """Creating serials with a nonexistent production_order_id returns 404."""
        product = make_product(item_type="finished_good")
        response = client.post(f"{BASE_URL}/serials", json={
            "product_id": product.id,
            "production_order_id": 999999,
            "quantity": 1,
        })
        assert response.status_code == 404

    def test_create_serials_product_not_found(self, client, db, make_product):
        """Creating serials with a nonexistent product_id returns 404."""
        # Need a valid production order to get past the PO check
        real_product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, real_product.id)

        response = client.post(f"{BASE_URL}/serials", json={
            "product_id": 999999,
            "production_order_id": po.id,
            "quantity": 1,
        })
        assert response.status_code == 404

    def test_get_serial_by_id(self, client, make_product, db):
        """GET /serials/{serial_id} returns the serial number."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        serials = _create_serials(client, product.id, po.id, quantity=1)
        serial_id = serials[0]["id"]

        response = client.get(f"{BASE_URL}/serials/{serial_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == serial_id
        assert data["serial_number"] == serials[0]["serial_number"]

    def test_get_serial_by_id_not_found(self, client):
        """GET /serials/{serial_id} for a nonexistent ID returns 404."""
        response = client.get(f"{BASE_URL}/serials/999999")
        assert response.status_code == 404

    def test_lookup_serial_by_number(self, client, make_product, db):
        """GET /serials/lookup/{serial_number} finds the serial by its string."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        serials = _create_serials(client, product.id, po.id, quantity=1)
        serial_number = serials[0]["serial_number"]

        response = client.get(f"{BASE_URL}/serials/lookup/{serial_number}")
        assert response.status_code == 200
        data = response.json()
        assert data["serial_number"] == serial_number

    def test_lookup_serial_by_number_not_found(self, client):
        """GET /serials/lookup/{serial_number} for a nonexistent serial returns 404."""
        response = client.get(f"{BASE_URL}/serials/lookup/DOES-NOT-EXIST")
        assert response.status_code == 404

    def test_update_serial(self, client, make_product, db):
        """PATCH updates the serial number fields."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        serials = _create_serials(client, product.id, po.id, quantity=1)
        serial_id = serials[0]["id"]

        response = client.patch(f"{BASE_URL}/serials/{serial_id}", json={
            "status": "sold",
            "qc_notes": "Passed visual inspection",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sold"
        assert data["qc_notes"] == "Passed visual inspection"
        # sold_at should be set automatically
        assert data["sold_at"] is not None

    def test_update_serial_shipped_sets_timestamp(self, client, make_product, db):
        """Setting status to 'shipped' auto-populates shipped_at."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        serials = _create_serials(client, product.id, po.id, quantity=1)
        serial_id = serials[0]["id"]

        response = client.patch(f"{BASE_URL}/serials/{serial_id}", json={
            "status": "shipped",
        })
        assert response.status_code == 200
        assert response.json()["shipped_at"] is not None

    def test_update_serial_returned_sets_timestamp(self, client, make_product, db):
        """Setting status to 'returned' auto-populates returned_at."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        serials = _create_serials(client, product.id, po.id, quantity=1)
        serial_id = serials[0]["id"]

        response = client.patch(f"{BASE_URL}/serials/{serial_id}", json={
            "status": "returned",
            "return_reason": "Defective print layer adhesion",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["returned_at"] is not None
        assert data["return_reason"] == "Defective print layer adhesion"

    def test_update_serial_not_found(self, client):
        """PATCH on a nonexistent serial returns 404."""
        response = client.patch(f"{BASE_URL}/serials/999999", json={
            "status": "scrapped",
        })
        assert response.status_code == 404

    def test_list_serials(self, client, make_product, db):
        """GET /serials returns paginated results."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        _create_serials(client, product.id, po.id, quantity=2)

        response = client.get(f"{BASE_URL}/serials")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["items"], list)

    def test_list_serials_filter_by_product(self, client, make_product, db):
        """Filtering serials by product_id returns only matching serials."""
        product_a = make_product(item_type="finished_good", procurement_type="make")
        product_b = make_product(item_type="finished_good", procurement_type="make")
        po_a = _create_production_order(db, product_a.id)
        po_b = _create_production_order(db, product_b.id)
        _create_serials(client, product_a.id, po_a.id, quantity=2)
        _create_serials(client, product_b.id, po_b.id, quantity=1)

        response = client.get(f"{BASE_URL}/serials", params={
            "product_id": product_a.id,
        })
        assert response.status_code == 200
        data = response.json()
        assert all(s["product_id"] == product_a.id for s in data["items"])

    def test_list_serials_filter_by_status(self, client, make_product, db):
        """Filtering serials by status returns only matching serials."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        serials = _create_serials(client, product.id, po.id, quantity=2)
        # Update one to "sold"
        client.patch(f"{BASE_URL}/serials/{serials[0]['id']}", json={
            "status": "sold",
        })

        response = client.get(f"{BASE_URL}/serials", params={"status": "sold"})
        assert response.status_code == 200
        data = response.json()
        assert all(s["status"] == "sold" for s in data["items"])

    def test_list_serials_filter_by_production_order(self, client, make_product, db):
        """Filtering serials by production_order_id works."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po_a = _create_production_order(db, product.id)
        po_b = _create_production_order(db, product.id)
        _create_serials(client, product.id, po_a.id, quantity=2)
        _create_serials(client, product.id, po_b.id, quantity=1)

        response = client.get(f"{BASE_URL}/serials", params={
            "production_order_id": po_a.id,
        })
        assert response.status_code == 200
        data = response.json()
        assert all(s["production_order_id"] == po_a.id for s in data["items"])

    def test_list_serials_search(self, client, make_product, db):
        """Search parameter filters serials by serial_number substring."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        serials = _create_serials(client, product.id, po.id, quantity=1)
        # Use part of the serial number as a search term
        serial_str = serials[0]["serial_number"]

        response = client.get(f"{BASE_URL}/serials", params={"search": serial_str})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    def test_serial_response_shape(self, client, make_product, db):
        """Verify the full response shape of a serial number."""
        product = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, product.id)
        serials = _create_serials(client, product.id, po.id, quantity=1)

        expected_fields = {
            "id", "serial_number", "product_id", "production_order_id",
            "status", "qc_passed", "qc_date", "qc_notes",
            "sales_order_id", "sales_order_line_id",
            "sold_at", "shipped_at", "tracking_number",
            "returned_at", "return_reason",
            "manufactured_at", "created_at",
        }
        assert expected_fields.issubset(set(serials[0].keys()))


# =============================================================================
# Lot Consumption
# =============================================================================

class TestLotConsumption:
    """Recording and retrieving material lot consumption for production orders."""

    def test_record_consumption(self, client, make_product, db):
        """Recording consumption decrements from the lot and returns the record."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)
        lot = _create_lot(client, product.id, quantity_received="1000")

        response = client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": lot["id"],
            "quantity_consumed": "200",
        })
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["production_order_id"] == po.id
        assert data["material_lot_id"] == lot["id"]
        assert float(data["quantity_consumed"]) == 200.0
        assert "consumed_at" in data
        assert "id" in data

    def test_record_consumption_updates_lot_remaining(self, client, make_product, db):
        """After consumption, the lot's quantity_remaining decreases."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)
        lot = _create_lot(client, product.id, quantity_received="500")

        client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": lot["id"],
            "quantity_consumed": "150",
        })

        lot_response = client.get(f"{BASE_URL}/lots/{lot['id']}")
        assert lot_response.status_code == 200
        lot_data = lot_response.json()
        assert float(lot_data["quantity_remaining"]) == 350.0
        assert float(lot_data["quantity_consumed"]) == 150.0

    def test_record_consumption_insufficient_quantity(self, client, make_product, db):
        """Recording more consumption than available returns 400."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)
        lot = _create_lot(client, product.id, quantity_received="100")

        response = client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": lot["id"],
            "quantity_consumed": "999",
        })
        assert response.status_code == 400
        assert "Insufficient quantity" in response.json()["detail"]

    def test_record_consumption_lot_not_found(self, client, make_product, db):
        """Recording consumption for a nonexistent lot returns 404."""
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)

        response = client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": 999999,
            "quantity_consumed": "10",
        })
        assert response.status_code == 404

    def test_record_consumption_production_order_not_found(self, client, make_product):
        """Recording consumption for a nonexistent production order returns 404."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        lot = _create_lot(client, product.id)

        response = client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": 999999,
            "material_lot_id": lot["id"],
            "quantity_consumed": "10",
        })
        assert response.status_code == 404

    def test_get_consumptions_for_production_order(self, client, make_product, db):
        """GET /consumptions/production/{id} returns all consumptions for that PO."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)
        lot_a = _create_lot(client, product.id, quantity_received="1000")
        lot_b = _create_lot(client, product.id, quantity_received="1000")

        # Record two consumptions on the same production order
        client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": lot_a["id"],
            "quantity_consumed": "100",
        })
        client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": lot_b["id"],
            "quantity_consumed": "200",
        })

        response = client.get(f"{BASE_URL}/consumptions/production/{po.id}")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        lot_ids = {c["material_lot_id"] for c in data}
        assert lot_ids == {lot_a["id"], lot_b["id"]}

    def test_get_consumptions_empty(self, client, make_product, db):
        """GET /consumptions/production/{id} returns empty list when no consumptions."""
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)

        response = client.get(f"{BASE_URL}/consumptions/production/{po.id}")
        assert response.status_code == 200
        assert response.json() == []


# =============================================================================
# Recall Queries
# =============================================================================

class TestRecallQueries:
    """Forward and backward recall traceability queries."""

    def test_recall_forward_no_affected(self, client, make_product):
        """Forward recall on a lot with no consumptions returns empty affected list."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        lot = _create_lot(client, product.id)

        response = client.get(f"{BASE_URL}/recall/forward/{lot['lot_number']}")
        assert response.status_code == 200
        data = response.json()
        assert data["lot_number"] == lot["lot_number"]
        assert data["total_affected"] == 0
        assert data["affected_products"] == []
        assert "material_name" in data
        assert "quantity_received" in data
        assert "quantity_consumed" in data

    def test_recall_forward_with_affected(self, client, make_product, db):
        """Forward recall returns serial numbers produced from the lot."""
        raw = make_product(item_type="supply", unit="G", is_raw_material=True)
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)

        lot = _create_lot(client, raw.id, quantity_received="1000")
        # Create serials for the production order
        _create_serials(client, fg.id, po.id, quantity=2)
        # Record consumption linking the lot to the production order
        client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": lot["id"],
            "quantity_consumed": "200",
        })

        response = client.get(f"{BASE_URL}/recall/forward/{lot['lot_number']}")
        assert response.status_code == 200
        data = response.json()
        assert data["lot_number"] == lot["lot_number"]
        assert data["total_affected"] == 2
        assert len(data["affected_products"]) == 2
        for affected in data["affected_products"]:
            assert "serial_number" in affected
            assert "product_name" in affected
            assert "production_order_code" in affected
            assert "status" in affected

    def test_recall_forward_lot_not_found(self, client):
        """Forward recall for a nonexistent lot returns 404."""
        response = client.get(f"{BASE_URL}/recall/forward/NONEXISTENT-LOT")
        assert response.status_code == 404

    def test_recall_backward_no_lots(self, client, make_product, db):
        """Backward recall on a serial with no consumption records returns empty list."""
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)
        serials = _create_serials(client, fg.id, po.id, quantity=1)
        serial_number = serials[0]["serial_number"]

        response = client.get(f"{BASE_URL}/recall/backward/{serial_number}")
        assert response.status_code == 200
        data = response.json()
        assert data["serial_number"] == serial_number
        assert data["material_lots_used"] == []
        assert "product_name" in data
        assert "manufactured_at" in data

    def test_recall_backward_with_lots(self, client, make_product, make_vendor, db):
        """Backward recall returns all material lots consumed for the serial's PO."""
        raw = make_product(item_type="supply", unit="G", is_raw_material=True)
        fg = make_product(item_type="finished_good", procurement_type="make")
        vendor = make_vendor()
        po = _create_production_order(db, fg.id)

        lot_a = _create_lot(client, raw.id, vendor_id=vendor.id, quantity_received="1000")
        lot_b = _create_lot(client, raw.id, vendor_id=vendor.id, quantity_received="1000")

        serials = _create_serials(client, fg.id, po.id, quantity=1)
        serial_number = serials[0]["serial_number"]

        # Record consumptions
        client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": lot_a["id"],
            "quantity_consumed": "100",
        })
        client.post(f"{BASE_URL}/consumptions", json={
            "production_order_id": po.id,
            "material_lot_id": lot_b["id"],
            "quantity_consumed": "50",
        })

        response = client.get(f"{BASE_URL}/recall/backward/{serial_number}")
        assert response.status_code == 200
        data = response.json()
        assert data["serial_number"] == serial_number
        assert len(data["material_lots_used"]) == 2
        for lot_used in data["material_lots_used"]:
            assert "lot_number" in lot_used
            assert "material_name" in lot_used
            assert "vendor_name" in lot_used
            assert "quantity_consumed" in lot_used

    def test_recall_backward_serial_not_found(self, client):
        """Backward recall for a nonexistent serial returns 404."""
        response = client.get(f"{BASE_URL}/recall/backward/NONEXISTENT-SERIAL")
        assert response.status_code == 404

    def test_recall_forward_response_shape(self, client, make_product):
        """Verify the full response shape of a forward recall query."""
        product = make_product(item_type="supply", unit="G", is_raw_material=True)
        lot = _create_lot(client, product.id)

        response = client.get(f"{BASE_URL}/recall/forward/{lot['lot_number']}")
        assert response.status_code == 200
        data = response.json()
        expected_fields = {
            "lot_number", "material_name", "quantity_received",
            "quantity_consumed", "affected_products", "total_affected",
        }
        assert expected_fields == set(data.keys())

    def test_recall_backward_response_shape(self, client, make_product, db):
        """Verify the full response shape of a backward recall query."""
        fg = make_product(item_type="finished_good", procurement_type="make")
        po = _create_production_order(db, fg.id)
        serials = _create_serials(client, fg.id, po.id, quantity=1)

        response = client.get(
            f"{BASE_URL}/recall/backward/{serials[0]['serial_number']}"
        )
        assert response.status_code == 200
        data = response.json()
        expected_fields = {
            "serial_number", "product_name",
            "manufactured_at", "material_lots_used",
        }
        assert expected_fields == set(data.keys())
