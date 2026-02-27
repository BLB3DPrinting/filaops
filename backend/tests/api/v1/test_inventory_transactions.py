"""
Tests for admin inventory transactions API endpoints.

Endpoints under: /api/v1/admin/inventory/transactions
"""
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/admin/inventory/transactions"


# =============================================================================
# Helpers
# =============================================================================

def _create_receipt(client, product_id, quantity, location_id=1, cost_per_unit=None):
    """Create a receipt transaction and assert success."""
    payload = {
        "product_id": product_id,
        "location_id": location_id,
        "transaction_type": "receipt",
        "quantity": str(quantity),
    }
    if cost_per_unit is not None:
        payload["cost_per_unit"] = str(cost_per_unit)
    response = client.post(BASE_URL, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_second_location(db):
    """Create and return a second InventoryLocation for transfer tests."""
    from app.models.inventory import InventoryLocation

    loc = InventoryLocation(
        name="Secondary Warehouse",
        code="SEC",
        type="warehouse",
        active=True,
    )
    db.add(loc)
    db.flush()
    return loc


# =============================================================================
# Authentication
# =============================================================================

class TestAuth:
    """Unauthenticated requests must return 401."""

    def test_list_transactions_requires_auth(self, unauthed_client):
        response = unauthed_client.get(BASE_URL)
        assert response.status_code == 401

    def test_create_transaction_requires_auth(self, unauthed_client):
        response = unauthed_client.post(BASE_URL, json={
            "product_id": 1,
            "transaction_type": "receipt",
            "quantity": "10",
        })
        assert response.status_code == 401

    def test_locations_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/locations")
        assert response.status_code == 401

    def test_batch_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/batch", json={
            "items": [],
        })
        assert response.status_code == 401

    def test_inventory_summary_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/inventory-summary")
        assert response.status_code == 401


# =============================================================================
# POST /transactions — Create transaction
# =============================================================================

class TestCreateReceipt:
    """Receipt transactions increase on-hand inventory."""

    def test_receipt_creates_transaction(self, client, finished_good):
        data = _create_receipt(client, finished_good.id, 10)

        assert data["product_id"] == finished_good.id
        assert data["transaction_type"] == "receipt"
        assert Decimal(data["quantity"]) == Decimal("10")
        assert data["location_id"] is not None

    def test_receipt_increases_inventory(self, client, finished_good):
        _create_receipt(client, finished_good.id, 5)
        _create_receipt(client, finished_good.id, 3)

        # List transactions to verify both recorded
        resp = client.get(BASE_URL, params={"product_id": finished_good.id})
        assert resp.status_code == 200
        txns = resp.json()
        receipt_txns = [t for t in txns if t["transaction_type"] == "receipt"]
        assert len(receipt_txns) >= 2

    def test_receipt_with_cost(self, client, finished_good):
        data = _create_receipt(client, finished_good.id, 4, cost_per_unit=5)

        assert data["cost_per_unit"] is not None
        assert Decimal(data["cost_per_unit"]) == Decimal("5")

    def test_receipt_with_optional_fields(self, client, finished_good):
        payload = {
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "receipt",
            "quantity": "7",
            "reference_type": "purchase_order",
            "reference_id": 42,
            "lot_number": "LOT-001",
            "serial_number": "SN-001",
            "notes": "Test receipt note",
        }
        resp = client.post(BASE_URL, json=payload)
        assert resp.status_code == 201

        data = resp.json()
        assert data["reference_type"] == "purchase_order"
        assert data["reference_id"] == 42
        assert data["lot_number"] == "LOT-001"
        assert data["serial_number"] == "SN-001"
        assert data["notes"] == "Test receipt note"


class TestCreateIssue:
    """Issue transactions decrease on-hand inventory."""

    def test_issue_with_sufficient_inventory(self, client, finished_good):
        _create_receipt(client, finished_good.id, 20)

        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "issue",
            "quantity": "5",
        })
        assert resp.status_code == 201
        assert resp.json()["transaction_type"] == "issue"

    def test_issue_insufficient_inventory(self, client, finished_good):
        # No inventory received, so issue should fail
        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "issue",
            "quantity": "100",
        })
        assert resp.status_code == 400
        assert "Insufficient inventory" in resp.json()["detail"]

    def test_consumption_with_sufficient_inventory(self, client, raw_material):
        _create_receipt(client, raw_material.id, 500)

        resp = client.post(BASE_URL, json={
            "product_id": raw_material.id,
            "location_id": 1,
            "transaction_type": "consumption",
            "quantity": "200",
        })
        assert resp.status_code == 201
        assert resp.json()["transaction_type"] == "consumption"

    def test_scrap_with_sufficient_inventory(self, client, finished_good):
        _create_receipt(client, finished_good.id, 10)

        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "scrap",
            "quantity": "2",
        })
        assert resp.status_code == 201
        assert resp.json()["transaction_type"] == "scrap"

    def test_scrap_insufficient_inventory(self, client, finished_good):
        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "scrap",
            "quantity": "9999",
        })
        assert resp.status_code == 400
        assert "Insufficient inventory" in resp.json()["detail"]


class TestCreateAdjustment:
    """Adjustment transactions set on-hand to the specified quantity."""

    def test_adjustment_sets_quantity(self, client, finished_good):
        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "adjustment",
            "quantity": "42",
        })
        assert resp.status_code == 201
        assert resp.json()["transaction_type"] == "adjustment"
        assert Decimal(resp.json()["quantity"]) == Decimal("42")


class TestCreateTransfer:
    """Transfer transactions move inventory between locations."""

    def test_transfer_requires_to_location_id(self, client, finished_good):
        _create_receipt(client, finished_good.id, 10)

        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "transfer",
            "quantity": "5",
        })
        assert resp.status_code == 400
        assert "to_location_id" in resp.json()["detail"].lower()

    def test_transfer_same_location_rejected(self, client, finished_good):
        _create_receipt(client, finished_good.id, 10)

        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "transfer",
            "quantity": "5",
            "to_location_id": 1,
        })
        assert resp.status_code == 400
        assert "same location" in resp.json()["detail"].lower()

    def test_transfer_success(self, client, db, finished_good):
        second_loc = _create_second_location(db)
        _create_receipt(client, finished_good.id, 20)

        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "transfer",
            "quantity": "8",
            "to_location_id": second_loc.id,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["transaction_type"] == "transfer"
        assert data["to_location_id"] == second_loc.id
        assert data["to_location_name"] == "Secondary Warehouse"

    def test_transfer_insufficient_inventory(self, client, db, finished_good):
        second_loc = _create_second_location(db)

        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "transfer",
            "quantity": "999",
            "to_location_id": second_loc.id,
        })
        assert resp.status_code == 400
        assert "Insufficient inventory" in resp.json()["detail"]

    def test_transfer_to_nonexistent_location(self, client, finished_good):
        _create_receipt(client, finished_good.id, 10)

        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "transfer",
            "quantity": "5",
            "to_location_id": 99999,
        })
        assert resp.status_code == 404
        assert "location" in resp.json()["detail"].lower()


# =============================================================================
# Validation errors
# =============================================================================

class TestValidation:
    """Transaction creation validates inputs and returns appropriate errors."""

    def test_invalid_transaction_type(self, client, finished_good):
        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "invalid_type",
            "quantity": "1",
        })
        assert resp.status_code == 400
        assert "Invalid transaction_type" in resp.json()["detail"]

    def test_product_not_found(self, client):
        resp = client.post(BASE_URL, json={
            "product_id": 999999,
            "location_id": 1,
            "transaction_type": "receipt",
            "quantity": "1",
        })
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_location_not_found(self, client, finished_good):
        resp = client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 999999,
            "transaction_type": "receipt",
            "quantity": "1",
        })
        assert resp.status_code == 404
        assert "Location" in resp.json()["detail"]


# =============================================================================
# GET /transactions — List with filters
# =============================================================================

class TestListTransactions:
    """Listing and filtering inventory transactions."""

    def test_list_returns_200(self, client):
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_filter_by_product_id(self, client, finished_good, raw_material):
        _create_receipt(client, finished_good.id, 1)
        _create_receipt(client, raw_material.id, 100)

        resp = client.get(BASE_URL, params={"product_id": finished_good.id})
        assert resp.status_code == 200
        txns = resp.json()
        assert all(t["product_id"] == finished_good.id for t in txns)

    def test_filter_by_transaction_type(self, client, finished_good):
        _create_receipt(client, finished_good.id, 10)
        client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "adjustment",
            "quantity": "5",
        })

        resp = client.get(BASE_URL, params={
            "product_id": finished_good.id,
            "transaction_type": "adjustment",
        })
        assert resp.status_code == 200
        txns = resp.json()
        assert len(txns) >= 1
        assert all(t["transaction_type"] == "adjustment" for t in txns)

    def test_filter_by_location_id(self, client, finished_good):
        _create_receipt(client, finished_good.id, 5, location_id=1)

        resp = client.get(BASE_URL, params={"location_id": 1})
        assert resp.status_code == 200

    def test_filter_by_reference(self, client, finished_good):
        client.post(BASE_URL, json={
            "product_id": finished_good.id,
            "location_id": 1,
            "transaction_type": "receipt",
            "quantity": "3",
            "reference_type": "purchase_order",
            "reference_id": 77,
        })

        resp = client.get(BASE_URL, params={
            "reference_type": "purchase_order",
            "reference_id": 77,
        })
        assert resp.status_code == 200
        txns = resp.json()
        assert len(txns) >= 1
        assert all(t["reference_type"] == "purchase_order" for t in txns)

    def test_pagination(self, client, finished_good):
        # Create a few transactions
        for _ in range(3):
            _create_receipt(client, finished_good.id, 1)

        resp = client.get(BASE_URL, params={
            "product_id": finished_good.id,
            "limit": 2,
            "offset": 0,
        })
        assert resp.status_code == 200
        assert len(resp.json()) <= 2

    def test_response_fields(self, client, finished_good):
        _create_receipt(client, finished_good.id, 5, cost_per_unit=5)

        resp = client.get(BASE_URL, params={"product_id": finished_good.id})
        assert resp.status_code == 200
        txns = resp.json()
        assert len(txns) >= 1

        txn = txns[0]
        expected_fields = [
            "id", "product_id", "product_sku", "product_name", "product_unit",
            "location_id", "location_name", "transaction_type", "quantity",
            "unit", "cost_per_unit", "total_cost", "reference_type",
            "reference_id", "lot_number", "serial_number", "notes",
            "created_at", "created_by", "to_location_id", "to_location_name",
        ]
        for field in expected_fields:
            assert field in txn, f"Missing field: {field}"


# =============================================================================
# GET /transactions/locations — List locations
# =============================================================================

class TestListLocations:
    """Listing active inventory locations."""

    def test_locations_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/locations")
        assert resp.status_code == 200
        locations = resp.json()
        assert isinstance(locations, list)
        assert len(locations) >= 1  # At least the seeded Default Warehouse

    def test_location_fields(self, client):
        resp = client.get(f"{BASE_URL}/locations")
        assert resp.status_code == 200
        loc = resp.json()[0]
        assert "id" in loc
        assert "name" in loc
        assert "code" in loc
        assert "type" in loc


# =============================================================================
# POST /transactions/batch — Batch cycle count
# =============================================================================

class TestBatchUpdate:
    """Batch cycle count adjustment endpoint."""

    def test_batch_with_variance(self, client, finished_good):
        # Seed some inventory first
        _create_receipt(client, finished_good.id, 10)

        resp = client.post(f"{BASE_URL}/batch", json={
            "items": [
                {
                    "product_id": finished_good.id,
                    "counted_quantity": "7",
                    "reason": "Damaged units removed",
                },
            ],
            "location_id": 1,
            "count_reference": "Test Cycle Count",
        })
        assert resp.status_code == 200

        data = resp.json()
        assert data["total_items"] == 1
        assert data["successful"] == 1
        assert data["failed"] == 0
        assert data["count_reference"] == "Test Cycle Count"

        result = data["results"][0]
        assert result["product_id"] == finished_good.id
        assert result["success"] is True
        assert Decimal(result["counted_quantity"]) == Decimal("7")
        assert result["transaction_id"] is not None

    def test_batch_zero_variance_skipped(self, client, finished_good):
        # Seed exactly 10
        _create_receipt(client, finished_good.id, 10)

        resp = client.post(f"{BASE_URL}/batch", json={
            "items": [
                {
                    "product_id": finished_good.id,
                    "counted_quantity": "10",
                    "reason": "Verified count",
                },
            ],
            "location_id": 1,
        })
        assert resp.status_code == 200

        data = resp.json()
        assert data["successful"] == 1
        result = data["results"][0]
        assert result["success"] is True
        assert Decimal(result["variance"]) == Decimal("0")
        # No transaction created for zero variance
        assert result["transaction_id"] is None

    def test_batch_nonexistent_product(self, client):
        resp = client.post(f"{BASE_URL}/batch", json={
            "items": [
                {
                    "product_id": 999999,
                    "counted_quantity": "5",
                    "reason": "Ghost product",
                },
            ],
            "location_id": 1,
        })
        assert resp.status_code == 200

        data = resp.json()
        assert data["failed"] == 1
        result = data["results"][0]
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_batch_generates_count_reference(self, client, finished_good):
        """When no count_reference provided, the server generates one."""
        _create_receipt(client, finished_good.id, 5)

        resp = client.post(f"{BASE_URL}/batch", json={
            "items": [
                {
                    "product_id": finished_good.id,
                    "counted_quantity": "3",
                    "reason": "Recount",
                },
            ],
            "location_id": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["count_reference"] is not None
        assert "Cycle Count" in data["count_reference"]


# =============================================================================
# GET /transactions/inventory-summary — Inventory summary
# =============================================================================

class TestInventorySummary:
    """Inventory summary endpoint for cycle counting."""

    def test_summary_returns_structure(self, client, finished_good):
        _create_receipt(client, finished_good.id, 15)

        resp = client.get(f"{BASE_URL}/inventory-summary")
        assert resp.status_code == 200

        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

    def test_summary_includes_product_with_inventory(self, client, finished_good):
        _create_receipt(client, finished_good.id, 25)

        # Search by SKU to avoid pagination issues with pre-existing data
        resp = client.get(f"{BASE_URL}/inventory-summary", params={
            "location_id": 1,
            "search": finished_good.sku,
        })
        assert resp.status_code == 200

        items = resp.json()["items"]
        product_ids = [item["product_id"] for item in items]
        assert finished_good.id in product_ids

        item = next(i for i in items if i["product_id"] == finished_good.id)
        assert item["product_sku"] == finished_good.sku
        assert item["on_hand_quantity"] > 0

    def test_summary_search_filter(self, client, finished_good):
        _create_receipt(client, finished_good.id, 5)

        # Search by the unique SKU to reliably find this specific product
        resp = client.get(f"{BASE_URL}/inventory-summary", params={
            "search": finished_good.sku,
        })
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(i["product_id"] == finished_good.id for i in items)

    def test_summary_search_no_match(self, client, finished_good):
        _create_receipt(client, finished_good.id, 5)

        resp = client.get(f"{BASE_URL}/inventory-summary", params={
            "search": "ZZZZNONEXISTENT",
        })
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_summary_show_zero_false_excludes_empty(self, client):
        resp = client.get(f"{BASE_URL}/inventory-summary", params={
            "show_zero": False,
        })
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            assert item["on_hand_quantity"] > 0

    def test_summary_item_fields(self, client, finished_good):
        _create_receipt(client, finished_good.id, 10)

        # Search by SKU to avoid pagination issues with pre-existing data
        resp = client.get(f"{BASE_URL}/inventory-summary", params={
            "location_id": 1,
            "search": finished_good.sku,
        })
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1

        item = next(i for i in items if i["product_id"] == finished_good.id)
        expected_fields = [
            "inventory_id", "product_id", "product_sku", "product_name",
            "category_name", "unit", "location_id", "location_name",
            "on_hand_quantity", "allocated_quantity", "available_quantity",
            "last_counted",
        ]
        for field in expected_fields:
            assert field in item, f"Missing field: {field}"
