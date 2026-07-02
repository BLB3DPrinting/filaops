"""
Tests for Production Orders API endpoints (app/api/v1/endpoints/production_orders.py)

Covers:
- GET /api/v1/production-orders/ (list with pagination, filters)
- GET /api/v1/production-orders/{id} (get single)
- POST /api/v1/production-orders/ (create with auto BOM lookup)
- PUT /api/v1/production-orders/{id} (update fields)
- POST /api/v1/production-orders/{id}/release (draft -> released)
- POST /api/v1/production-orders/{id}/start (released -> in_progress)
- POST /api/v1/production-orders/{id}/complete (in_progress -> complete)
- POST /api/v1/production-orders/{id}/cancel (cancel order)
- POST /api/v1/production-orders/{id}/hold (put on hold)
- DELETE /api/v1/production-orders/{id} (delete draft only)
- Auth: 401 without token
"""
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/production-orders"


# =============================================================================
# Helpers
# =============================================================================

def _create_product_with_bom(make_product, make_bom, db):
    """Create a finished good with a raw material and active BOM."""
    fg = make_product(
        item_type="finished_good",
        procurement_type="make",
        selling_price=Decimal("15.00"),
    )
    raw = make_product(
        item_type="supply",
        unit="G",
        is_raw_material=True,
    )
    bom = make_bom(
        product_id=fg.id,
        lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ],
    )
    db.flush()
    return fg, raw, bom


def _create_draft_order(client, product_id):
    """POST a new production order and return the response JSON."""
    response = client.post(BASE_URL, json={
        "product_id": product_id,
        "quantity_ordered": "10",
    })
    assert response.status_code == 200, response.text
    return response.json()


# =============================================================================
# Auth tests -- endpoints requiring authentication
# =============================================================================

class TestProductionOrderAuth:
    """Verify auth is required on protected endpoints."""

    def test_list_requires_auth(self, unauthed_client):
        response = unauthed_client.get(BASE_URL)
        assert response.status_code == 401

    def test_create_requires_auth(self, unauthed_client):
        response = unauthed_client.post(BASE_URL, json={
            "product_id": 1,
            "quantity_ordered": "5",
        })
        assert response.status_code == 401

    def test_get_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_update_requires_auth(self, unauthed_client):
        response = unauthed_client.put(f"{BASE_URL}/1", json={
            "notes": "test",
        })
        assert response.status_code == 401

    def test_delete_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_release_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/release")
        assert response.status_code == 401

    def test_complete_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/complete")
        assert response.status_code == 401

    def test_cancel_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/cancel")
        assert response.status_code == 401


# =============================================================================
# List -- GET /api/v1/production-orders/
# =============================================================================

class TestListProductionOrders:
    """Test GET /api/v1/production-orders/"""

    def test_list_returns_200(self, client):
        response = client.get(BASE_URL)
        assert response.status_code == 200

    def test_list_returns_array(self, client):
        response = client.get(BASE_URL)
        data = response.json()
        assert isinstance(data, list)

    def test_list_includes_created_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.get(BASE_URL)
        assert response.status_code == 200
        codes = [o["code"] for o in response.json()]
        assert order_data["code"] in codes

    def test_list_with_status_filter(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        _create_draft_order(client, fg.id)

        response = client.get(f"{BASE_URL}?status=draft")
        assert response.status_code == 200
        for order in response.json():
            assert order["status"] == "draft"

    def test_list_with_pagination(self, client):
        response = client.get(f"{BASE_URL}?offset=0&limit=5")
        assert response.status_code == 200
        assert len(response.json()) <= 5

    def test_list_with_priority_filter(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "5",
            "priority": 1,
        })

        response = client.get(f"{BASE_URL}?priority=1")
        assert response.status_code == 200
        for order in response.json():
            assert order["priority"] == 1

    def test_list_with_product_filter(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        _create_draft_order(client, fg.id)

        response = client.get(f"{BASE_URL}?product_id={fg.id}")
        assert response.status_code == 200
        for order in response.json():
            assert order["product_id"] == fg.id

    def test_list_with_search(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.get(f"{BASE_URL}?search={order_data['code']}")
        assert response.status_code == 200
        codes = [o["code"] for o in response.json()]
        assert order_data["code"] in codes


# =============================================================================
# Get single -- GET /api/v1/production-orders/{id}
# =============================================================================

class TestGetProductionOrder:
    """Test GET /api/v1/production-orders/{id}"""

    def test_get_existing_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.get(f"{BASE_URL}/{order_data['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == order_data["id"]
        assert data["code"] == order_data["code"]
        assert data["product_id"] == fg.id

    def test_get_includes_product_info(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.get(f"{BASE_URL}/{order_data['id']}")
        data = response.json()
        assert data["product_name"] is not None
        assert data["product_sku"] is not None

    def test_get_nonexistent_returns_404(self, client):
        response = client.get(f"{BASE_URL}/999999")
        assert response.status_code == 404

    def test_get_includes_quantity_fields(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.get(f"{BASE_URL}/{order_data['id']}")
        data = response.json()
        assert Decimal(str(data["quantity_ordered"])) == Decimal("10")
        assert Decimal(str(data["quantity_completed"])) == Decimal("0")
        assert Decimal(str(data["quantity_remaining"])) == Decimal("10")
        assert data["completion_percent"] == 0.0


# =============================================================================
# Create -- POST /api/v1/production-orders/
# =============================================================================

class TestCreateProductionOrder:
    """Test POST /api/v1/production-orders/"""

    def test_create_basic_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "10",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["code"].startswith("PO-")
        assert data["status"] == "draft"
        assert Decimal(str(data["quantity_ordered"])) == Decimal("10")
        assert data["product_id"] == fg.id

    def test_create_auto_generates_code(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        # PO-YYYY-NNNN format
        code = order_data["code"]
        parts = code.split("-")
        assert len(parts) == 3
        assert parts[0] == "PO"
        assert len(parts[1]) == 4  # year
        assert parts[2].isdigit()

    def test_create_auto_assigns_bom(self, client, db, make_product, make_bom):
        fg, _, bom = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        assert order_data["bom_id"] == bom.id

    def test_create_defaults_to_manual_source(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        assert order_data["source"] == "manual"

    def test_create_defaults_priority_3(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        assert order_data["priority"] == 3

    def test_create_with_priority(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "5",
            "priority": 1,
        })
        assert response.status_code == 200
        assert response.json()["priority"] == 1

    def test_create_with_due_date(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "5",
            "due_date": "2026-03-15",
        })
        assert response.status_code == 200
        assert response.json()["due_date"] == "2026-03-15"

    def test_create_with_notes(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "5",
            "notes": "Rush order for customer",
        })
        assert response.status_code == 200
        assert response.json()["notes"] == "Rush order for customer"

    def test_create_with_source_sales_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "5",
            "source": "sales_order",
        })
        assert response.status_code == 200
        assert response.json()["source"] == "sales_order"

    def test_create_nonexistent_product_returns_404(self, client):
        response = client.post(BASE_URL, json={
            "product_id": 999999,
            "quantity_ordered": "10",
        })
        assert response.status_code == 404

    def test_create_missing_product_id_returns_422(self, client):
        response = client.post(BASE_URL, json={
            "quantity_ordered": "10",
        })
        assert response.status_code == 422

    def test_create_missing_quantity_returns_422(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
        })
        assert response.status_code == 422

    def test_create_zero_quantity_returns_422(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "0",
        })
        assert response.status_code == 422

    def test_create_negative_quantity_returns_422(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "-5",
        })
        assert response.status_code == 422

    def test_create_without_bom_succeeds(self, client, db, make_product):
        """A product without a BOM can still have a production order created."""
        fg = make_product(
            item_type="finished_good",
            procurement_type="make",
        )
        db.flush()

        response = client.post(BASE_URL, json={
            "product_id": fg.id,
            "quantity_ordered": "5",
        })
        assert response.status_code == 200
        assert response.json()["bom_id"] is None


# =============================================================================
# Update -- PUT /api/v1/production-orders/{id}
# =============================================================================

class TestUpdateProductionOrder:
    """Test PUT /api/v1/production-orders/{id}"""

    def test_update_notes(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.put(f"{BASE_URL}/{order_data['id']}", json={
            "notes": "Updated notes",
        })
        assert response.status_code == 200
        assert response.json()["notes"] == "Updated notes"

    def test_update_priority(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.put(f"{BASE_URL}/{order_data['id']}", json={
            "priority": 1,
        })
        assert response.status_code == 200
        assert response.json()["priority"] == 1

    def test_update_due_date(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.put(f"{BASE_URL}/{order_data['id']}", json={
            "due_date": "2026-06-01",
        })
        assert response.status_code == 200
        assert response.json()["due_date"] == "2026-06-01"

    def test_update_quantity(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.put(f"{BASE_URL}/{order_data['id']}", json={
            "quantity_ordered": "20",
        })
        assert response.status_code == 200
        assert Decimal(str(response.json()["quantity_ordered"])) == Decimal("20")

    def test_update_nonexistent_returns_404(self, client):
        response = client.put(f"{BASE_URL}/999999", json={
            "notes": "test",
        })
        assert response.status_code == 404

    def test_update_completed_order_returns_400(self, client, db, make_product, make_bom):
        """Cannot update a completed production order."""
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        # Directly set status to complete in DB to bypass transition logic
        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "complete"
        db.flush()

        response = client.put(f"{BASE_URL}/{order_data['id']}", json={
            "notes": "should fail",
        })
        assert response.status_code == 400

    def test_update_cancelled_order_returns_400(self, client, db, make_product, make_bom):
        """Cannot update a cancelled production order."""
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "cancelled"
        db.flush()

        response = client.put(f"{BASE_URL}/{order_data['id']}", json={
            "notes": "should fail",
        })
        assert response.status_code == 400


# =============================================================================
# Release -- POST /api/v1/production-orders/{id}/release
# =============================================================================

class TestReleaseProductionOrder:
    """Test POST /api/v1/production-orders/{id}/release"""

    def test_release_draft_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(f"{BASE_URL}/{order_data['id']}/release")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "released"

    def test_release_sets_released_at(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(f"{BASE_URL}/{order_data['id']}/release")
        data = response.json()
        assert data["released_at"] is not None

    def test_release_nonexistent_returns_404(self, client):
        response = client.post(f"{BASE_URL}/999999/release")
        assert response.status_code == 404

    def test_release_already_released_is_idempotent(self, client, db, make_product, make_bom):
        """Releasing an already-released order is a no-op (same-state transition allowed)."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        # Release once
        first = client.post(f"{BASE_URL}/{order_data['id']}/release")
        assert first.status_code == 200
        assert first.json()["status"] == "released"

        # Second release is idempotent — returns 200
        response = client.post(f"{BASE_URL}/{order_data['id']}/release")
        assert response.status_code == 200
        assert response.json()["status"] == "released"

    def test_release_completed_order_returns_400(self, client, db, make_product, make_bom):
        """Cannot release a completed order."""
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "complete"
        db.flush()

        response = client.post(f"{BASE_URL}/{order_data['id']}/release")
        assert response.status_code == 400

    def test_release_cancelled_order_returns_400(self, client, db, make_product, make_bom):
        """Cannot release a cancelled order."""
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "cancelled"
        db.flush()

        response = client.post(f"{BASE_URL}/{order_data['id']}/release")
        assert response.status_code == 400


# =============================================================================
# Start -- POST /api/v1/production-orders/{id}/start
# =============================================================================

class TestStartProductionOrder:
    """Test POST /api/v1/production-orders/{id}/start"""

    def test_start_released_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")

        response = client.post(f"{BASE_URL}/{order_data['id']}/start")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert data["actual_start"] is not None

    def test_start_draft_returns_400(self, client, db, make_product, make_bom):
        """Cannot start a draft order -- must release first."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(f"{BASE_URL}/{order_data['id']}/start")
        assert response.status_code == 400

    def test_start_nonexistent_returns_404(self, client):
        response = client.post(f"{BASE_URL}/999999/start")
        assert response.status_code == 404

    def test_start_completed_order_returns_400(self, client, db, make_product, make_bom):
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "complete"
        db.flush()

        response = client.post(f"{BASE_URL}/{order_data['id']}/start")
        assert response.status_code == 400


# =============================================================================
# Complete -- POST /api/v1/production-orders/{id}/complete
# =============================================================================

class TestCompleteProductionOrder:
    """Test POST /api/v1/production-orders/{id}/complete"""

    def test_complete_in_progress_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")
        client.post(f"{BASE_URL}/{order_data['id']}/start")

        response = client.post(f"{BASE_URL}/{order_data['id']}/complete")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"
        assert data["completed_at"] is not None

    def test_complete_with_quantity(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")
        client.post(f"{BASE_URL}/{order_data['id']}/start")

        response = client.post(
            f"{BASE_URL}/{order_data['id']}/complete",
            json={"quantity_completed": "10"},
        )
        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["quantity_completed"])) == Decimal("10")

    def test_complete_short_without_force_returns_400(self, client, db, make_product, make_bom):
        """Completing short without force_close_short should be rejected."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")
        client.post(f"{BASE_URL}/{order_data['id']}/start")

        response = client.post(
            f"{BASE_URL}/{order_data['id']}/complete",
            json={"quantity_completed": "5"},
        )
        assert response.status_code == 400
        assert "short" in response.json()["detail"].lower()

    def test_complete_short_with_force_succeeds(self, client, db, make_product, make_bom):
        """Force-closing short should succeed."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")
        client.post(f"{BASE_URL}/{order_data['id']}/start")

        response = client.post(
            f"{BASE_URL}/{order_data['id']}/complete",
            json={
                "quantity_completed": "5",
                "force_close_short": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "complete"

    def test_complete_draft_returns_400(self, client, db, make_product, make_bom):
        """Cannot complete a draft order directly."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(f"{BASE_URL}/{order_data['id']}/complete")
        assert response.status_code == 400

    def test_complete_nonexistent_returns_404(self, client):
        response = client.post(f"{BASE_URL}/999999/complete")
        assert response.status_code == 404

    def test_complete_already_completed_is_idempotent(self, client, db, make_product, make_bom):
        """Completing an already-completed order is a no-op (same-state allowed)."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        # Drive through the full lifecycle via API
        client.post(f"{BASE_URL}/{order_data['id']}/release")
        client.post(f"{BASE_URL}/{order_data['id']}/start")
        first = client.post(
            f"{BASE_URL}/{order_data['id']}/complete",
            json={"quantity_completed": "10"},
        )
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "complete"

        # Second complete is idempotent — same-state transition allowed
        response = client.post(f"{BASE_URL}/{order_data['id']}/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "complete"


class TestQCInspectionEndpoint:
    """Test POST /api/v1/production-orders/{id}/qc"""

    def test_qc_conditional_result_accepted(self, client, db, make_product, make_bom):
        """'conditional' is a valid QC result — the endpoint must bind it (A6).
        It previously 422'd because QCStatus lacked the member, even though the
        service and DB CHECK already accept it."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")
        client.post(f"{BASE_URL}/{order_data['id']}/start")
        client.post(
            f"{BASE_URL}/{order_data['id']}/complete",
            json={"quantity_completed": "10"},
        )

        response = client.post(
            f"{BASE_URL}/{order_data['id']}/qc",
            json={"result": "conditional", "notes": "Accepted with minor cosmetic deviation"},
        )
        assert response.status_code == 200, response.text


class TestSplitProductionOrder:
    """Test POST /api/v1/production-orders/{id}/split (#858 A3).

    The endpoint previously read request.split_quantity/request.reason —
    fields that don't exist on ProductionOrderSplitRequest (which carries
    splits: List[SplitQuantity]) — and built the response with kwargs that
    don't match ProductionOrderSplitResponse, so every split 500'd twice.
    """

    def test_split_two_ways(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)  # qty 10

        response = client.post(
            f"{BASE_URL}/{order_data['id']}/split",
            json={"splits": [{"quantity": 6}, {"quantity": 4}]},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["parent_order_id"] == order_data["id"]
        assert data["parent_order_code"] == order_data["code"]
        assert len(data["child_orders"]) == 1
        child = data["child_orders"][0]
        assert Decimal(str(child["quantity_ordered"])) == Decimal("4")
        assert child["code"] != order_data["code"]

        # Parent keeps the first split quantity.
        parent = client.get(f"{BASE_URL}/{order_data['id']}").json()
        assert Decimal(str(parent["quantity_ordered"])) == Decimal("6")

    def test_split_three_ways(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)  # qty 10

        response = client.post(
            f"{BASE_URL}/{order_data['id']}/split",
            json={"splits": [{"quantity": 4}, {"quantity": 3}, {"quantity": 3}]},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert len(data["child_orders"]) == 2
        parent = client.get(f"{BASE_URL}/{order_data['id']}").json()
        assert Decimal(str(parent["quantity_ordered"])) == Decimal("4")

    def test_split_sum_mismatch_returns_400(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)  # qty 10

        response = client.post(
            f"{BASE_URL}/{order_data['id']}/split",
            json={"splits": [{"quantity": 5}, {"quantity": 4}]},
        )
        assert response.status_code == 400
        assert "total" in response.json()["detail"].lower()

    def test_split_single_entry_rejected(self, client, db, make_product, make_bom):
        """The schema requires at least 2 splits."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(
            f"{BASE_URL}/{order_data['id']}/split",
            json={"splits": [{"quantity": 10}]},
        )
        assert response.status_code == 422


class TestOperationScrapEndpoints:
    """Test the operation-level scrap routes (#858 B1).

    ScrapEntryModal and OperationCompletionModal called
    /{po}/operations/{op}/scrap and .../scrap-cascade, but neither route
    existed — the scrap_service functions were built (and covered by
    tests/services/test_scrap_service.py, incl. GL balance) yet never routed.
    """

    def _setup(self, db, make_product, make_production_order, make_work_center):
        """PO in progress with one complete operation (10 good units) that
        consumed a material, plus an active scrap reason."""
        from app.models.production_order import (
            ProductionOrderOperation,
            ProductionOrderOperationMaterial,
        )
        from app.models.scrap_reason import ScrapReason

        fg = make_product(item_type="finished_good", standard_cost=Decimal("10.00"))
        material = make_product(item_type="supply", is_raw_material=True,
                                standard_cost=Decimal("2.50"))
        wc = make_work_center()
        po = make_production_order(
            product_id=fg.id, status="in_progress", quantity=10,
        )
        op = ProductionOrderOperation(
            production_order_id=po.id,
            work_center_id=wc.id,
            sequence=10,
            operation_code="PRINT",
            operation_name="Print",
            status="complete",
            quantity_completed=Decimal("10"),
            quantity_scrapped=Decimal("0"),
            planned_setup_minutes=Decimal("0"),
            planned_run_minutes=Decimal("30"),
        )
        db.add(op)
        db.flush()
        db.add(ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=material.id,
            quantity_required=Decimal("10"),
            quantity_allocated=Decimal("0"),
            quantity_consumed=Decimal("0"),
            unit="EA",
            status="pending",
        ))
        reason = db.query(ScrapReason).filter(ScrapReason.code == "op-scrap-test").first()
        if not reason:
            db.add(ScrapReason(code="op-scrap-test", name="Op Scrap Test", active=True))
        db.flush()
        return po, op

    def test_cascade_preview_returns_costs(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        po, op = self._setup(db, make_product, make_production_order, make_work_center)

        response = client.get(
            f"{BASE_URL}/{po.id}/operations/{op.id}/scrap-cascade",
            params={"quantity": 2},
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["production_order_id"] == po.id
        assert data["operation_id"] == op.id
        assert data["quantity_scrapped"] == 2
        # 2 units × (10 EA / 10 ordered) × $2.50 material + labor share
        assert data["total_cost"] > 0
        assert len(data["materials_consumed"]) == 1

    def test_scrap_records_and_updates_quantities(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        po, op = self._setup(db, make_product, make_production_order, make_work_center)

        response = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/scrap",
            json={
                "quantity_scrapped": 2,
                "scrap_reason_code": "op-scrap-test",
                "create_replacement": False,
            },
        )
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True
        assert data["scrap_records_created"] >= 1
        assert data["replacement_order"] is None

        db.refresh(po)
        db.refresh(op)
        assert int(po.quantity_scrapped) == 2
        assert int(op.quantity_scrapped) == 2

    def test_scrap_invalid_reason_returns_400(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        po, op = self._setup(db, make_product, make_production_order, make_work_center)

        response = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/scrap",
            json={
                "quantity_scrapped": 1,
                "scrap_reason_code": "no-such-reason",
                "create_replacement": False,
            },
        )
        assert response.status_code == 400
        assert "scrap reason" in response.json()["detail"].lower()

    def test_scrap_over_available_returns_400(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        po, op = self._setup(db, make_product, make_production_order, make_work_center)

        response = client.post(
            f"{BASE_URL}/{po.id}/operations/{op.id}/scrap",
            json={
                "quantity_scrapped": 11,  # only 10 completed
                "scrap_reason_code": "op-scrap-test",
                "create_replacement": False,
            },
        )
        assert response.status_code == 400

    def test_cascade_op_not_in_po_returns_400(
        self, client, db, make_product, make_production_order, make_work_center
    ):
        po, op = self._setup(db, make_product, make_production_order, make_work_center)
        other_po = make_production_order(
            product_id=make_product().id, status="in_progress", quantity=5,
        )
        db.flush()

        response = client.get(
            f"{BASE_URL}/{other_po.id}/operations/{op.id}/scrap-cascade",
            params={"quantity": 1},
        )
        assert response.status_code == 400


# =============================================================================
# Cancel -- POST /api/v1/production-orders/{id}/cancel
# =============================================================================

class TestCancelProductionOrder:
    """Test POST /api/v1/production-orders/{id}/cancel"""

    def test_cancel_draft_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(f"{BASE_URL}/{order_data['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_released_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")

        response = client.post(f"{BASE_URL}/{order_data['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_in_progress_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")
        client.post(f"{BASE_URL}/{order_data['id']}/start")

        response = client.post(f"{BASE_URL}/{order_data['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_with_notes(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(f"{BASE_URL}/{order_data['id']}/cancel?notes=Material%20shortage")
        assert response.status_code == 200
        assert "Material shortage" in response.json()["notes"]

    def test_cancel_completed_order_returns_400(self, client, db, make_product, make_bom):
        """Cannot cancel a completed order -- it is a terminal state."""
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "complete"
        db.flush()

        response = client.post(f"{BASE_URL}/{order_data['id']}/cancel")
        assert response.status_code == 400

    def test_cancel_already_cancelled_is_idempotent(self, client, db, make_product, make_bom):
        """Cancelling an already-cancelled order is a no-op (same-state allowed)."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        # Cancel via API
        first = client.post(f"{BASE_URL}/{order_data['id']}/cancel")
        assert first.status_code == 200
        assert first.json()["status"] == "cancelled"

        # Second cancel is idempotent — same-state transition allowed
        response = client.post(f"{BASE_URL}/{order_data['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_cancel_nonexistent_returns_404(self, client):
        response = client.post(f"{BASE_URL}/999999/cancel")
        assert response.status_code == 404


# =============================================================================
# Hold -- POST /api/v1/production-orders/{id}/hold
# =============================================================================

class TestHoldProductionOrder:
    """Test POST /api/v1/production-orders/{id}/hold"""

    def test_hold_released_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")

        response = client.post(f"{BASE_URL}/{order_data['id']}/hold")
        assert response.status_code == 200
        assert response.json()["status"] == "on_hold"

    def test_hold_in_progress_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")
        client.post(f"{BASE_URL}/{order_data['id']}/start")

        response = client.post(f"{BASE_URL}/{order_data['id']}/hold")
        assert response.status_code == 200
        assert response.json()["status"] == "on_hold"

    def test_hold_draft_returns_400(self, client, db, make_product, make_bom):
        """Cannot hold a draft order -- must release first."""
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(f"{BASE_URL}/{order_data['id']}/hold")
        assert response.status_code == 400

    def test_hold_nonexistent_returns_404(self, client):
        response = client.post(f"{BASE_URL}/999999/hold")
        assert response.status_code == 404


# =============================================================================
# Delete -- DELETE /api/v1/production-orders/{id}
# =============================================================================

class TestDeleteProductionOrder:
    """Test DELETE /api/v1/production-orders/{id} (draft only)"""

    def test_delete_draft_order(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.delete(f"{BASE_URL}/{order_data['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Production order deleted"

        # Verify it is gone
        get_response = client.get(f"{BASE_URL}/{order_data['id']}")
        assert get_response.status_code == 404

    def test_delete_released_order_returns_400(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        client.post(f"{BASE_URL}/{order_data['id']}/release")

        response = client.delete(f"{BASE_URL}/{order_data['id']}")
        assert response.status_code == 400

    def test_delete_in_progress_order_returns_400(self, client, db, make_product, make_bom):
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "in_progress"
        db.flush()

        response = client.delete(f"{BASE_URL}/{order_data['id']}")
        assert response.status_code == 400

    def test_delete_completed_order_returns_400(self, client, db, make_product, make_bom):
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "complete"
        db.flush()

        response = client.delete(f"{BASE_URL}/{order_data['id']}")
        assert response.status_code == 400

    def test_delete_cancelled_order_returns_400(self, client, db, make_product, make_bom):
        from app.models.production_order import ProductionOrder
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        order = db.query(ProductionOrder).filter(ProductionOrder.id == order_data["id"]).first()
        order.status = "cancelled"
        db.flush()

        response = client.delete(f"{BASE_URL}/{order_data['id']}")
        assert response.status_code == 400

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete(f"{BASE_URL}/999999")
        assert response.status_code == 404


# =============================================================================
# Full lifecycle -- draft -> released -> in_progress -> complete
# =============================================================================

class TestProductionOrderLifecycle:
    """Test the full status progression of a production order."""

    def test_full_lifecycle(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)

        # 1. Create (draft)
        order_data = _create_draft_order(client, fg.id)
        assert order_data["status"] == "draft"
        order_id = order_data["id"]

        # 2. Release
        response = client.post(f"{BASE_URL}/{order_id}/release")
        assert response.status_code == 200
        assert response.json()["status"] == "released"

        # 3. Start
        response = client.post(f"{BASE_URL}/{order_id}/start")
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"

        # 4. Complete
        response = client.post(
            f"{BASE_URL}/{order_id}/complete",
            json={"quantity_completed": "10"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "complete"
        assert Decimal(str(data["quantity_completed"])) == Decimal("10")
        assert data["completed_at"] is not None

    def test_draft_to_cancelled(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)

        response = client.post(f"{BASE_URL}/{order_data['id']}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_released_to_hold_and_back(self, client, db, make_product, make_bom):
        fg, _, _ = _create_product_with_bom(make_product, make_bom, db)
        order_data = _create_draft_order(client, fg.id)
        order_id = order_data["id"]

        # Release
        client.post(f"{BASE_URL}/{order_id}/release")

        # Hold
        response = client.post(f"{BASE_URL}/{order_id}/hold")
        assert response.status_code == 200
        assert response.json()["status"] == "on_hold"

        # Resume (on_hold -> released is allowed)
        response = client.post(f"{BASE_URL}/{order_id}/release")
        assert response.status_code == 200
        assert response.json()["status"] == "released"


# =============================================================================
# Status transitions endpoint -- GET /api/v1/production-orders/status-transitions
# =============================================================================

class TestStatusTransitionsEndpoint:
    """Test GET /api/v1/production-orders/status-transitions"""

    def test_get_status_transitions(self, client):
        response = client.get(f"{BASE_URL}/status-transitions")
        assert response.status_code == 200
        data = response.json()
        # Should contain transition mappings
        assert isinstance(data, dict)
