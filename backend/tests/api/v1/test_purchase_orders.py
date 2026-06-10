"""
Tests for Purchase Orders API endpoints (app/api/v1/endpoints/purchase_orders.py)

Covers:
- GET /api/v1/purchase-orders/ (list with pagination, filters, search)
- GET /api/v1/purchase-orders/{id} (get single with lines)
- POST /api/v1/purchase-orders/ (create with auto-generated PO number)
- PUT /api/v1/purchase-orders/{id} (update PO fields)
- POST /api/v1/purchase-orders/{id}/status (status transitions)
- POST /api/v1/purchase-orders/{id}/lines (add line to PO)
- POST /api/v1/purchase-orders/{id}/receive (receive items, inventory updates)
- DELETE /api/v1/purchase-orders/{id} (delete draft PO only)
- Auth: 401 without token
"""
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/purchase-orders"


# =============================================================================
# Auth tests -- endpoints requiring authentication
# =============================================================================

class TestPurchaseOrderAuth:
    """Verify auth is required on all protected endpoints."""

    def test_list_requires_auth(self, unauthed_client):
        response = unauthed_client.get(BASE_URL)
        assert response.status_code == 401

    def test_get_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_create_requires_auth(self, unauthed_client):
        response = unauthed_client.post(BASE_URL, json={
            "vendor_id": 1,
            "lines": [],
        })
        assert response.status_code == 401

    def test_update_requires_auth(self, unauthed_client):
        response = unauthed_client.put(f"{BASE_URL}/1", json={
            "notes": "updated",
        })
        assert response.status_code == 401

    def test_status_update_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/status", json={
            "status": "ordered",
        })
        assert response.status_code == 401

    def test_add_line_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/lines", json={
            "product_id": 1,
            "quantity_ordered": "10",
            "unit_cost": "5.00",
        })
        assert response.status_code == 401

    def test_receive_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/receive", json={
            "lines": [{"line_id": 1, "quantity_received": "5"}],
        })
        assert response.status_code == 401

    def test_delete_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/1")
        assert response.status_code == 401


# =============================================================================
# List -- GET /api/v1/purchase-orders/
# =============================================================================

class TestListPurchaseOrders:
    """Test GET /api/v1/purchase-orders/"""

    def test_list_returns_200(self, client):
        response = client.get(BASE_URL)
        assert response.status_code == 200

    def test_list_returns_paginated_response(self, client):
        response = client.get(BASE_URL)
        data = response.json()
        assert "items" in data
        assert "pagination" in data
        assert isinstance(data["items"], list)

    def test_list_includes_created_po(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()

        response = client.get(BASE_URL)
        assert response.status_code == 200
        data = response.json()
        po_numbers = [item["po_number"] for item in data["items"]]
        assert po.po_number in po_numbers

    def test_list_filter_by_status(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        draft_po = make_purchase_order(vendor_id=vendor.id, status="draft")
        ordered_po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.flush()

        response = client.get(f"{BASE_URL}?status=draft")
        assert response.status_code == 200
        data = response.json()
        statuses = {item["status"] for item in data["items"]}
        # All returned items should be draft
        assert statuses <= {"draft"}

    def test_list_filter_by_vendor_id(self, client, db, make_vendor, make_purchase_order):
        vendor_a = make_vendor(name="Vendor A")
        vendor_b = make_vendor(name="Vendor B")
        po_a = make_purchase_order(vendor_id=vendor_a.id)
        po_b = make_purchase_order(vendor_id=vendor_b.id)
        db.flush()

        response = client.get(f"{BASE_URL}?vendor_id={vendor_a.id}")
        assert response.status_code == 200
        data = response.json()
        vendor_ids = {item["vendor_id"] for item in data["items"]}
        assert vendor_ids <= {vendor_a.id}

    def test_list_search_by_po_number(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, po_number="PO-SEARCH-999")
        db.flush()

        response = client.get(f"{BASE_URL}?search=SEARCH-999")
        assert response.status_code == 200
        data = response.json()
        assert any(item["po_number"] == "PO-SEARCH-999" for item in data["items"])

    def test_list_pagination_offset_limit(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        for _ in range(3):
            make_purchase_order(vendor_id=vendor.id)
        db.flush()

        response = client.get(f"{BASE_URL}?offset=0&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) <= 2
        assert data["pagination"]["limit"] == 2


# =============================================================================
# Get -- GET /api/v1/purchase-orders/{id}
# =============================================================================

class TestGetPurchaseOrder:
    """Test GET /api/v1/purchase-orders/{id}"""

    def test_get_existing_po(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        db.flush()
        db.expire_all()

        response = client.get(f"{BASE_URL}/{po.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == po.id
        assert data["po_number"] == po.po_number
        assert data["status"] == "draft"
        assert data["vendor_id"] == vendor.id

    def test_get_po_includes_lines(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        db.flush()
        db.expire_all()

        response = client.get(f"{BASE_URL}/{po.id}")
        assert response.status_code == 200
        data = response.json()
        assert "lines" in data
        assert isinstance(data["lines"], list)

    def test_get_po_includes_vendor_name(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor(name="Acme Supplies")
        po = make_purchase_order(vendor_id=vendor.id)
        db.flush()
        db.expire_all()

        response = client.get(f"{BASE_URL}/{po.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["vendor_name"] == "Acme Supplies"

    def test_get_nonexistent_returns_404(self, client):
        response = client.get(f"{BASE_URL}/999999")
        assert response.status_code == 404


# =============================================================================
# Create -- POST /api/v1/purchase-orders/
# =============================================================================

class TestCreatePurchaseOrder:
    """Test POST /api/v1/purchase-orders/"""

    def test_create_minimal_po(self, client, db, make_vendor):
        vendor = make_vendor()
        db.flush()

        response = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [],
        })
        assert response.status_code == 201
        data = response.json()
        assert data["po_number"].startswith("PO-")
        assert data["status"] == "draft"
        assert data["vendor_id"] == vendor.id

    def test_create_po_auto_generates_po_number(self, client, db, make_vendor):
        vendor = make_vendor()
        db.flush()

        response = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [],
        })
        assert response.status_code == 201
        data = response.json()
        # PO number should follow PO-YYYY-NNNN format (4-digit zero-padded — HARD-10)
        parts = data["po_number"].split("-")
        assert len(parts) == 3
        assert parts[0] == "PO"
        assert len(parts[1]) == 4  # year
        assert len(parts[2]) >= 4  # zero-padded sequence (at least 4 digits)

    def test_create_po_with_lines(self, client, db, make_vendor, make_product):
        vendor = make_vendor()
        product = make_product()
        db.flush()

        response = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [
                {
                    "product_id": product.id,
                    "quantity_ordered": "10",
                    "unit_cost": "5.50",
                },
            ],
        })
        assert response.status_code == 201
        data = response.json()
        assert len(data["lines"]) == 1
        line = data["lines"][0]
        assert line["product_id"] == product.id
        assert Decimal(str(line["quantity_ordered"])) == Decimal("10")
        assert Decimal(str(line["unit_cost"])) == Decimal("5.50")
        assert Decimal(str(line["line_total"])) == Decimal("55.00")

    def test_create_po_with_multiple_lines(self, client, db, make_vendor, make_product):
        vendor = make_vendor()
        p1 = make_product()
        p2 = make_product()
        db.flush()

        response = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [
                {"product_id": p1.id, "quantity_ordered": "5", "unit_cost": "10.00"},
                {"product_id": p2.id, "quantity_ordered": "2", "unit_cost": "25.00"},
            ],
        })
        assert response.status_code == 201
        data = response.json()
        assert len(data["lines"]) == 2
        # Subtotal = (5 * 10) + (2 * 25) = 100
        assert Decimal(str(data["subtotal"])) == Decimal("100.00")

    def test_create_po_with_notes_and_expected_date(self, client, db, make_vendor):
        vendor = make_vendor()
        db.flush()

        response = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "notes": "Rush order for production",
            "expected_date": "2026-03-15",
            "lines": [],
        })
        assert response.status_code == 201
        data = response.json()
        assert data["notes"] == "Rush order for production"
        assert data["expected_date"] == "2026-03-15"

    def test_create_po_with_tax_and_shipping(self, client, db, make_vendor, make_product):
        vendor = make_vendor()
        product = make_product()
        db.flush()

        response = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "tax_amount": "8.50",
            "shipping_cost": "12.00",
            "lines": [
                {"product_id": product.id, "quantity_ordered": "10", "unit_cost": "10.00"},
            ],
        })
        assert response.status_code == 201
        data = response.json()
        # Subtotal = 100, tax = 8.50, shipping = 12.00, total = 120.50
        assert Decimal(str(data["subtotal"])) == Decimal("100.00")
        assert Decimal(str(data["tax_amount"])) == Decimal("8.50")
        assert Decimal(str(data["shipping_cost"])) == Decimal("12.00")
        assert Decimal(str(data["total_amount"])) == Decimal("120.50")

    def test_create_po_invalid_vendor_returns_404(self, client):
        response = client.post(BASE_URL, json={
            "vendor_id": 999999,
            "lines": [],
        })
        assert response.status_code == 404
        assert "vendor" in response.json()["detail"].lower()

    def test_create_po_invalid_product_returns_404(self, client, db, make_vendor):
        vendor = make_vendor()
        db.flush()

        response = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [
                {"product_id": 999999, "quantity_ordered": "1", "unit_cost": "1.00"},
            ],
        })
        assert response.status_code == 404
        assert "product" in response.json()["detail"].lower()

    def test_create_po_defaults_to_draft(self, client, db, make_vendor):
        vendor = make_vendor()
        db.flush()

        response = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [],
        })
        assert response.status_code == 201
        assert response.json()["status"] == "draft"


# =============================================================================
# Update -- PUT /api/v1/purchase-orders/{id}
# =============================================================================

class TestUpdatePurchaseOrder:
    """Test PUT /api/v1/purchase-orders/{id}"""

    def test_update_notes(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        db.flush()

        response = client.put(f"{BASE_URL}/{po.id}", json={
            "notes": "Updated notes for this PO",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["notes"] == "Updated notes for this PO"

    def test_update_expected_date(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        db.flush()

        response = client.put(f"{BASE_URL}/{po.id}", json={
            "expected_date": "2026-06-01",
        })
        assert response.status_code == 200
        assert response.json()["expected_date"] == "2026-06-01"

    def test_update_tax_and_shipping(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        db.flush()

        response = client.put(f"{BASE_URL}/{po.id}", json={
            "tax_amount": "15.00",
            "shipping_cost": "9.99",
        })
        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["tax_amount"])) == Decimal("15.00")
        assert Decimal(str(data["shipping_cost"])) == Decimal("9.99")

    def test_update_nonexistent_po_returns_404(self, client):
        response = client.put(f"{BASE_URL}/999999", json={
            "notes": "will not work",
        })
        assert response.status_code == 404

    def test_update_received_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        db.flush()

        response = client.put(f"{BASE_URL}/{po.id}", json={
            "notes": "cannot update received PO",
        })
        assert response.status_code == 400

    def test_update_cancelled_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        db.flush()

        response = client.put(f"{BASE_URL}/{po.id}", json={
            "notes": "cannot update cancelled PO",
        })
        assert response.status_code == 400

    def test_update_closed_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="closed")
        db.flush()

        response = client.put(f"{BASE_URL}/{po.id}", json={
            "notes": "cannot update closed PO",
        })
        assert response.status_code == 400


# =============================================================================
# Add line -- POST /api/v1/purchase-orders/{id}/lines
# =============================================================================

class TestAddPOLine:
    """Test POST /api/v1/purchase-orders/{id}/lines"""

    def test_add_line_to_draft_po(self, client, db, make_vendor, make_purchase_order, make_product):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        product = make_product()
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/lines", json={
            "product_id": product.id,
            "quantity_ordered": "20",
            "unit_cost": "3.50",
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["lines"]) == 1
        line = data["lines"][0]
        assert line["product_id"] == product.id
        assert Decimal(str(line["quantity_ordered"])) == Decimal("20")
        assert Decimal(str(line["unit_cost"])) == Decimal("3.50")
        assert Decimal(str(line["line_total"])) == Decimal("70.00")

    def test_add_line_to_ordered_po(self, client, db, make_vendor, make_purchase_order, make_product):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        product = make_product()
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/lines", json={
            "product_id": product.id,
            "quantity_ordered": "5",
            "unit_cost": "10.00",
        })
        assert response.status_code == 200

    def test_add_line_recalculates_totals(self, client, db, make_vendor, make_purchase_order, make_product):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        p1 = make_product()
        p2 = make_product()
        db.flush()

        # Add first line
        client.post(f"{BASE_URL}/{po.id}/lines", json={
            "product_id": p1.id,
            "quantity_ordered": "10",
            "unit_cost": "5.00",
        })

        # Add second line
        response = client.post(f"{BASE_URL}/{po.id}/lines", json={
            "product_id": p2.id,
            "quantity_ordered": "3",
            "unit_cost": "20.00",
        })
        assert response.status_code == 200
        data = response.json()
        # Subtotal = (10 * 5) + (3 * 20) = 110
        assert Decimal(str(data["subtotal"])) == Decimal("110.00")

    def test_add_line_to_received_po_returns_400(
        self, client, db, make_vendor, make_purchase_order, make_product,
    ):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        product = make_product()
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/lines", json={
            "product_id": product.id,
            "quantity_ordered": "1",
            "unit_cost": "1.00",
        })
        assert response.status_code == 400

    def test_add_line_to_cancelled_po_returns_400(
        self, client, db, make_vendor, make_purchase_order, make_product,
    ):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        product = make_product()
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/lines", json={
            "product_id": product.id,
            "quantity_ordered": "1",
            "unit_cost": "1.00",
        })
        assert response.status_code == 400

    def test_add_line_nonexistent_po_returns_404(self, client, db, make_product):
        product = make_product()
        db.flush()

        response = client.post(f"{BASE_URL}/999999/lines", json={
            "product_id": product.id,
            "quantity_ordered": "1",
            "unit_cost": "1.00",
        })
        assert response.status_code == 404

    def test_add_line_nonexistent_product_returns_404(
        self, client, db, make_vendor, make_purchase_order,
    ):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id)
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/lines", json={
            "product_id": 999999,
            "quantity_ordered": "1",
            "unit_cost": "1.00",
        })
        assert response.status_code == 404


# =============================================================================
# Status transitions -- POST /api/v1/purchase-orders/{id}/status
# =============================================================================

class TestPurchaseOrderStatusTransitions:
    """Test POST /api/v1/purchase-orders/{id}/status"""

    def test_draft_to_ordered(self, client, db, make_vendor, make_product):
        """Draft PO with lines can be moved to ordered."""
        vendor = make_vendor()
        product = make_product()
        db.flush()

        # Create PO with a line (ordered requires at least one line)
        create_resp = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [
                {"product_id": product.id, "quantity_ordered": "10", "unit_cost": "5.00"},
            ],
        })
        po_id = create_resp.json()["id"]

        response = client.post(f"{BASE_URL}/{po_id}/status", json={
            "status": "ordered",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "ordered"

    def test_draft_to_ordered_no_lines_returns_400(self, client, db, make_vendor):
        """Cannot order a PO with no lines."""
        vendor = make_vendor()
        db.flush()

        create_resp = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [],
        })
        po_id = create_resp.json()["id"]

        response = client.post(f"{BASE_URL}/{po_id}/status", json={
            "status": "ordered",
        })
        assert response.status_code == 400
        assert "no lines" in response.json()["detail"].lower()

    def test_draft_to_cancelled(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "cancelled",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_ordered_to_shipped(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "shipped",
            "tracking_number": "1Z999AA10123456784",
            "carrier": "UPS",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "shipped"
        assert data["tracking_number"] == "1Z999AA10123456784"
        assert data["carrier"] == "UPS"

    def test_ordered_to_received_via_status_patch_is_blocked(
        self, client, db, make_vendor, make_purchase_order
    ):
        """HARD-2: Direct status PATCH to 'received' is forbidden; use /receive."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "received",
        })
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "Receive" in detail or "receive" in detail

    def test_ordered_to_cancelled(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "cancelled",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_shipped_to_received_via_status_patch_is_blocked(
        self, client, db, make_vendor, make_purchase_order
    ):
        """HARD-2: Direct status PATCH to 'received' is forbidden even from shipped."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="shipped")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "received",
        })
        assert response.status_code == 400
        detail = response.json()["detail"]
        assert "Receive" in detail or "receive" in detail

    def test_received_to_closed(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "closed",
        })
        assert response.status_code == 200
        assert response.json()["status"] == "closed"

    def test_invalid_transition_draft_to_received(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "received",
        })
        assert response.status_code == 400
        assert "cannot transition" in response.json()["detail"].lower()

    def test_invalid_transition_draft_to_shipped(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "shipped",
        })
        assert response.status_code == 400

    def test_invalid_transition_draft_to_closed(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/status", json={
            "status": "closed",
        })
        assert response.status_code == 400

    def test_invalid_transition_closed_to_any(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="closed")
        db.flush()

        for target_status in ["draft", "ordered", "shipped", "received", "cancelled"]:
            response = client.post(f"{BASE_URL}/{po.id}/status", json={
                "status": target_status,
            })
            assert response.status_code in (400, 422), (
                f"Expected 400 or 422 for closed->{target_status}, got {response.status_code}"
            )

    def test_invalid_transition_cancelled_to_any(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        db.flush()

        for target_status in ["draft", "ordered", "shipped", "received", "closed"]:
            response = client.post(f"{BASE_URL}/{po.id}/status", json={
                "status": target_status,
            })
            assert response.status_code in (400, 422), (
                f"Expected 400 or 422 for cancelled->{target_status}, got {response.status_code}"
            )

    def test_status_update_nonexistent_po_returns_404(self, client):
        response = client.post(f"{BASE_URL}/999999/status", json={
            "status": "ordered",
        })
        assert response.status_code == 404


# =============================================================================
# Receive -- POST /api/v1/purchase-orders/{id}/receive
# =============================================================================

class TestReceivePurchaseOrder:
    """Test POST /api/v1/purchase-orders/{id}/receive"""

    def _create_ordered_po_with_line(self, client, db, make_vendor, make_product):
        """Helper: create a vendor, product, and an ordered PO with one line."""
        vendor = make_vendor()
        product = make_product(
            item_type="finished_good",
            unit="EA",
            purchase_uom="EA",
        )
        db.flush()

        # Create PO with a line
        create_resp = client.post(BASE_URL, json={
            "vendor_id": vendor.id,
            "lines": [
                {"product_id": product.id, "quantity_ordered": "10", "unit_cost": "5.00"},
            ],
        })
        assert create_resp.status_code == 201
        po_data = create_resp.json()
        po_id = po_data["id"]
        line_id = po_data["lines"][0]["id"]

        # Move to ordered
        status_resp = client.post(f"{BASE_URL}/{po_id}/status", json={
            "status": "ordered",
        })
        assert status_resp.status_code == 200

        return po_id, line_id, product

    def test_receive_full_quantity(self, client, db, make_vendor, make_product):
        po_id, line_id, product = self._create_ordered_po_with_line(
            client, db, make_vendor, make_product,
        )

        response = client.post(f"{BASE_URL}/{po_id}/receive", json={
            "lines": [
                {"line_id": line_id, "quantity_received": "10"},
            ],
        })
        assert response.status_code == 200
        data = response.json()
        assert data["lines_received"] == 1
        assert Decimal(str(data["total_quantity"])) == Decimal("10")
        assert data["inventory_updated"] is True

    def test_receive_partial_quantity(self, client, db, make_vendor, make_product):
        po_id, line_id, product = self._create_ordered_po_with_line(
            client, db, make_vendor, make_product,
        )

        response = client.post(f"{BASE_URL}/{po_id}/receive", json={
            "lines": [
                {"line_id": line_id, "quantity_received": "4"},
            ],
        })
        assert response.status_code == 200
        data = response.json()
        assert Decimal(str(data["total_quantity"])) == Decimal("4")

    def test_receive_over_quantity_returns_400(self, client, db, make_vendor, make_product):
        po_id, line_id, product = self._create_ordered_po_with_line(
            client, db, make_vendor, make_product,
        )

        response = client.post(f"{BASE_URL}/{po_id}/receive", json={
            "lines": [
                {"line_id": line_id, "quantity_received": "999"},
            ],
        })
        assert response.status_code == 400
        assert "remaining" in response.json()["detail"].lower()

    def test_receive_invalid_line_id_returns_404(self, client, db, make_vendor, make_product):
        po_id, line_id, product = self._create_ordered_po_with_line(
            client, db, make_vendor, make_product,
        )

        response = client.post(f"{BASE_URL}/{po_id}/receive", json={
            "lines": [
                {"line_id": 999999, "quantity_received": "1"},
            ],
        })
        assert response.status_code == 404

    def test_receive_draft_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/receive", json={
            "lines": [
                {"line_id": 1, "quantity_received": "1"},
            ],
        })
        assert response.status_code == 400

    def test_receive_cancelled_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        db.flush()

        response = client.post(f"{BASE_URL}/{po.id}/receive", json={
            "lines": [
                {"line_id": 1, "quantity_received": "1"},
            ],
        })
        assert response.status_code == 400

    def test_receive_nonexistent_po_returns_404(self, client):
        response = client.post(f"{BASE_URL}/999999/receive", json={
            "lines": [
                {"line_id": 1, "quantity_received": "1"},
            ],
        })
        assert response.status_code == 404

    def test_full_receive_sets_status_to_received(self, client, db, make_vendor, make_product):
        """Fully receiving all lines should auto-transition PO to 'received'."""
        po_id, line_id, product = self._create_ordered_po_with_line(
            client, db, make_vendor, make_product,
        )

        client.post(f"{BASE_URL}/{po_id}/receive", json={
            "lines": [
                {"line_id": line_id, "quantity_received": "10"},
            ],
        })

        # Verify PO status changed to received
        get_resp = client.get(f"{BASE_URL}/{po_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "received"

    def test_partial_receive_keeps_ordered_status(self, client, db, make_vendor, make_product):
        """Partial receive should not change PO status."""
        po_id, line_id, product = self._create_ordered_po_with_line(
            client, db, make_vendor, make_product,
        )

        client.post(f"{BASE_URL}/{po_id}/receive", json={
            "lines": [
                {"line_id": line_id, "quantity_received": "3"},
            ],
        })

        get_resp = client.get(f"{BASE_URL}/{po_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["status"] == "ordered"

    def test_receive_shipped_po(self, client, db, make_vendor, make_product):
        """Can receive items on a shipped PO."""
        po_id, line_id, product = self._create_ordered_po_with_line(
            client, db, make_vendor, make_product,
        )

        # Move to shipped
        client.post(f"{BASE_URL}/{po_id}/status", json={
            "status": "shipped",
        })

        response = client.post(f"{BASE_URL}/{po_id}/receive", json={
            "lines": [
                {"line_id": line_id, "quantity_received": "10"},
            ],
        })
        assert response.status_code == 200
        assert Decimal(str(response.json()["total_quantity"])) == Decimal("10")

    def test_receive_creates_transactions(self, client, db, make_vendor, make_product):
        po_id, line_id, product = self._create_ordered_po_with_line(
            client, db, make_vendor, make_product,
        )

        response = client.post(f"{BASE_URL}/{po_id}/receive", json={
            "lines": [
                {"line_id": line_id, "quantity_received": "5"},
            ],
        })
        assert response.status_code == 200
        data = response.json()
        assert len(data["transactions_created"]) > 0


# =============================================================================
# Delete -- DELETE /api/v1/purchase-orders/{id}
# =============================================================================

class TestDeletePurchaseOrder:
    """Test DELETE /api/v1/purchase-orders/{id}"""

    def test_delete_draft_po(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()

        response = client.delete(f"{BASE_URL}/{po.id}")
        assert response.status_code == 200
        assert "deleted" in response.json()["message"].lower()

        # Verify it is gone
        get_resp = client.get(f"{BASE_URL}/{po.id}")
        assert get_resp.status_code == 404

    def test_delete_ordered_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")
        db.flush()

        response = client.delete(f"{BASE_URL}/{po.id}")
        assert response.status_code == 400
        assert "cancel" in response.json()["detail"].lower()

    def test_delete_received_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="received")
        db.flush()

        response = client.delete(f"{BASE_URL}/{po.id}")
        assert response.status_code == 400

    def test_delete_cancelled_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="cancelled")
        db.flush()

        response = client.delete(f"{BASE_URL}/{po.id}")
        assert response.status_code == 400

    def test_delete_closed_po_returns_400(self, client, db, make_vendor, make_purchase_order):
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="closed")
        db.flush()

        response = client.delete(f"{BASE_URL}/{po.id}")
        assert response.status_code == 400

    def test_delete_nonexistent_returns_404(self, client):
        response = client.delete(f"{BASE_URL}/999999")
        assert response.status_code == 404
