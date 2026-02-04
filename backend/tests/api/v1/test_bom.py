"""
Tests for BOM Management API endpoints and BOM Service functions.

Covers:
- CRUD operations on BOMs and BOM lines via /api/v1/admin/bom
- Authentication requirements for all endpoints
- BOM service utility functions (parse_box_dimensions)
- Multi-level BOM scenarios (sub-assemblies)
- Scrap factor calculations
- Copy, validate, where-used, and cost-rollup endpoints
"""
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/admin/bom"


# =============================================================================
# BOM Service — Unit Tests (parse_box_dimensions)
# =============================================================================

class TestParseBoxDimensions:
    """Unit tests for parse_box_dimensions from bom_service."""

    def test_standard_format_with_in_suffix(self):
        from app.services.bom_service import parse_box_dimensions

        result = parse_box_dimensions("4x4x4in")
        assert result == (4.0, 4.0, 4.0)

    def test_larger_box_with_in_suffix(self):
        from app.services.bom_service import parse_box_dimensions

        result = parse_box_dimensions("8x8x16in")
        assert result == (8.0, 8.0, 16.0)

    def test_dimensions_with_name_suffix(self):
        from app.services.bom_service import parse_box_dimensions

        result = parse_box_dimensions("9x6x4 Black Shipping Box")
        assert result == (9.0, 6.0, 4.0)

    def test_unparseable_string_returns_none(self):
        from app.services.bom_service import parse_box_dimensions

        result = parse_box_dimensions("Not a box")
        assert result is None

    def test_empty_string_returns_none(self):
        from app.services.bom_service import parse_box_dimensions

        result = parse_box_dimensions("")
        assert result is None

    def test_dimensions_with_spaces_and_in_suffix(self):
        from app.services.bom_service import parse_box_dimensions

        result = parse_box_dimensions("12 x 9 x 4in")
        assert result == (12.0, 9.0, 4.0)

    def test_dimensions_with_decimal_values(self):
        from app.services.bom_service import parse_box_dimensions

        result = parse_box_dimensions("5.5x3.5x2.5in")
        assert result == (5.5, 3.5, 2.5)

    def test_plural_box_name(self):
        from app.services.bom_service import parse_box_dimensions

        result = parse_box_dimensions("12x9x4 Black Shipping Boxes")
        assert result == (12.0, 9.0, 4.0)


# =============================================================================
# Authentication — All endpoints require auth
# =============================================================================

class TestBOMAuthRequired:
    """Verify all BOM endpoints return 401 without authentication."""

    def test_list_boms_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/")
        assert response.status_code == 401

    def test_get_bom_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_create_bom_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/", json={
            "product_id": 1,
            "lines": [{"component_id": 1, "quantity": "1", "unit": "EA"}],
        })
        assert response.status_code == 401

    def test_update_bom_requires_auth(self, unauthed_client):
        response = unauthed_client.patch(f"{BASE_URL}/1", json={"name": "Updated"})
        assert response.status_code == 401

    def test_delete_bom_requires_auth(self, unauthed_client):
        response = unauthed_client.delete(f"{BASE_URL}/1")
        assert response.status_code == 401

    def test_add_line_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/lines", json={
            "component_id": 1, "quantity": "10", "unit": "EA",
        })
        assert response.status_code == 401

    def test_get_bom_by_product_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/product/1")
        assert response.status_code == 401

    def test_explode_bom_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1/explode")
        assert response.status_code == 401

    def test_validate_bom_requires_auth(self, unauthed_client):
        response = unauthed_client.post(f"{BASE_URL}/1/validate")
        assert response.status_code == 401

    def test_where_used_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/where-used/1")
        assert response.status_code == 401


# =============================================================================
# List BOMs — GET /admin/bom/
# =============================================================================

class TestListBOMs:
    """Tests for listing BOMs with filtering."""

    def test_list_boms_empty(self, client):
        response = client.get(f"{BASE_URL}/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_boms_returns_created_bom(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.get(f"{BASE_URL}/")
        assert response.status_code == 200

        data = response.json()
        bom_ids = [b["id"] for b in data]
        assert bom.id in bom_ids

    def test_list_boms_filter_by_product_id(self, client, make_product, raw_material, make_bom):
        fg_a = make_product(item_type="finished_good", procurement_type="make")
        fg_b = make_product(item_type="finished_good", procurement_type="make")

        make_bom(
            product_id=fg_a.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("50"), "unit": "G"}],
        )
        make_bom(
            product_id=fg_b.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("75"), "unit": "G"}],
        )

        response = client.get(f"{BASE_URL}/", params={"product_id": fg_a.id})
        assert response.status_code == 200

        data = response.json()
        for bom in data:
            assert bom["product_id"] == fg_a.id

    def test_list_boms_excludes_inactive_by_default(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
            active=False,
        )
        response = client.get(f"{BASE_URL}/")
        assert response.status_code == 200

        data = response.json()
        bom_ids = [b["id"] for b in data]
        assert bom.id not in bom_ids


# =============================================================================
# Get BOM — GET /admin/bom/{id}
# =============================================================================

class TestGetBOM:
    """Tests for retrieving a single BOM with all lines."""

    def test_get_bom_success(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("200"), "unit": "G"}],
        )
        response = client.get(f"{BASE_URL}/{bom.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == bom.id
        assert data["product_id"] == finished_good.id
        assert data["active"] is True
        assert len(data["lines"]) == 1
        assert data["lines"][0]["component_id"] == raw_material.id

    def test_get_bom_not_found(self, client):
        response = client.get(f"{BASE_URL}/999999")
        assert response.status_code == 404

    def test_get_bom_includes_product_info(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("50"), "unit": "G"}],
        )
        response = client.get(f"{BASE_URL}/{bom.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["product_sku"] is not None
        assert data["product_name"] is not None

    def test_get_bom_includes_component_details_on_lines(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.get(f"{BASE_URL}/{bom.id}")
        assert response.status_code == 200

        line = response.json()["lines"][0]
        assert line["component_sku"] is not None
        assert line["component_name"] is not None
        assert line["component_unit"] is not None


# =============================================================================
# Create BOM — POST /admin/bom/
# =============================================================================

class TestCreateBOM:
    """Tests for creating BOMs via the API."""

    def test_create_simple_bom(self, client, finished_good, raw_material):
        payload = {
            "product_id": finished_good.id,
            "lines": [
                {
                    "component_id": raw_material.id,
                    "quantity": "250",
                    "unit": "G",
                },
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["product_id"] == finished_good.id
        assert data["active"] is True
        assert len(data["lines"]) == 1
        assert data["lines"][0]["component_id"] == raw_material.id

    def test_create_bom_with_multiple_lines(self, client, make_product):
        fg = make_product(item_type="finished_good", procurement_type="make")
        comp_a = make_product(
            item_type="supply", unit="G", is_raw_material=True,
            average_cost=Decimal("0.03"),
        )
        comp_b = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("0.50"),
        )

        payload = {
            "product_id": fg.id,
            "lines": [
                {"component_id": comp_a.id, "quantity": "500", "unit": "G"},
                {"component_id": comp_b.id, "quantity": "2", "unit": "EA"},
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert len(data["lines"]) == 2

    def test_create_bom_product_not_found(self, client, raw_material):
        payload = {
            "product_id": 999999,
            "lines": [
                {"component_id": raw_material.id, "quantity": "100", "unit": "G"},
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload)
        assert response.status_code == 404

    def test_create_bom_component_not_found(self, client, finished_good):
        payload = {
            "product_id": finished_good.id,
            "lines": [
                {"component_id": 999999, "quantity": "100", "unit": "G"},
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload)
        assert response.status_code == 400

    def test_create_bom_with_scrap_factor(self, client, finished_good, raw_material):
        payload = {
            "product_id": finished_good.id,
            "lines": [
                {
                    "component_id": raw_material.id,
                    "quantity": "100",
                    "unit": "G",
                    "scrap_factor": "5",
                },
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload)
        assert response.status_code == 201

        line = response.json()["lines"][0]
        assert Decimal(str(line["scrap_factor"])) == Decimal("5")
        # Effective qty should be 100 * 1.05 = 105
        assert float(line["qty_needed"]) == pytest.approx(105.0, rel=1e-2)

    def test_create_bom_with_different_units(self, client, make_product):
        fg = make_product(item_type="finished_good", procurement_type="make")
        material_g = make_product(
            item_type="supply", unit="G", is_raw_material=True,
            average_cost=Decimal("0.025"),
        )
        packaging_ea = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("1.00"),
        )
        labor_hr = make_product(
            item_type="overhead", unit="HR",
            standard_cost=Decimal("1.50"),
        )

        payload = {
            "product_id": fg.id,
            "lines": [
                {"component_id": material_g.id, "quantity": "300", "unit": "G"},
                {"component_id": packaging_ea.id, "quantity": "1", "unit": "EA"},
                {"component_id": labor_hr.id, "quantity": "2.5", "unit": "HR", "is_cost_only": True},
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert len(data["lines"]) == 3
        units = {line["unit"] for line in data["lines"]}
        assert units == {"G", "EA", "HR"}

    def test_create_bom_upserts_existing_active_bom(self, client, finished_good, raw_material, make_bom):
        """When an active BOM exists, creating another should upsert lines."""
        existing_bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )

        new_component = raw_material  # same component, should add quantity
        payload = {
            "product_id": finished_good.id,
            "lines": [
                {"component_id": new_component.id, "quantity": "50", "unit": "G"},
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload)
        assert response.status_code == 201

        data = response.json()
        # Should be same BOM (upsert), not a new one
        assert data["id"] == existing_bom.id

    def test_create_bom_force_new_version(self, client, finished_good, raw_material, make_bom):
        """With force_new=True, should create a new BOM and deactivate old one."""
        old_bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )

        payload = {
            "product_id": finished_good.id,
            "lines": [
                {"component_id": raw_material.id, "quantity": "200", "unit": "G"},
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload, params={"force_new": True})
        assert response.status_code == 201

        data = response.json()
        assert data["id"] != old_bom.id
        assert data["active"] is True

    def test_create_bom_with_consume_stage(self, client, finished_good, make_product):
        packaging = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("2.00"),
        )
        payload = {
            "product_id": finished_good.id,
            "lines": [
                {
                    "component_id": packaging.id,
                    "quantity": "1",
                    "unit": "EA",
                    "consume_stage": "shipping",
                },
            ],
        }
        response = client.post(f"{BASE_URL}/", json=payload)
        assert response.status_code == 201

        line = response.json()["lines"][0]
        assert line["consume_stage"] == "shipping"


# =============================================================================
# Update BOM — PATCH /admin/bom/{id}
# =============================================================================

class TestUpdateBOM:
    """Tests for updating BOM header fields."""

    def test_update_bom_name(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.patch(f"{BASE_URL}/{bom.id}", json={"name": "Updated BOM Name"})
        assert response.status_code == 200
        assert response.json()["name"] == "Updated BOM Name"

    def test_update_bom_notes(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.patch(f"{BASE_URL}/{bom.id}", json={"notes": "Revised for v2"})
        assert response.status_code == 200
        assert response.json()["notes"] == "Revised for v2"

    def test_update_bom_not_found(self, client):
        response = client.patch(f"{BASE_URL}/999999", json={"name": "Nope"})
        assert response.status_code == 404

    def test_update_bom_deactivate(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.patch(f"{BASE_URL}/{bom.id}", json={"active": False})
        assert response.status_code == 200
        assert response.json()["active"] is False


# =============================================================================
# Delete BOM — DELETE /admin/bom/{id}
# =============================================================================

class TestDeleteBOM:
    """Tests for BOM deletion (soft delete)."""

    def test_delete_bom_success(self, client, db, finished_good, raw_material, make_bom):
        from app.models.bom import BOM

        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        bom_id = bom.id

        response = client.delete(f"{BASE_URL}/{bom_id}")
        assert response.status_code == 204

        # Verify soft-deleted (active=False)
        db.expire_all()
        deleted = db.query(BOM).filter(BOM.id == bom_id).first()
        assert deleted is not None
        assert deleted.active is False

    def test_delete_bom_not_found(self, client):
        response = client.delete(f"{BASE_URL}/999999")
        assert response.status_code == 404

    def test_delete_bom_lines_still_exist(self, client, db, finished_good, raw_material, make_bom):
        """Soft delete deactivates BOM but lines remain."""
        from app.models.bom import BOMLine

        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        bom_id = bom.id

        response = client.delete(f"{BASE_URL}/{bom_id}")
        assert response.status_code == 204

        db.expire_all()
        lines = db.query(BOMLine).filter(BOMLine.bom_id == bom_id).all()
        assert len(lines) >= 1


# =============================================================================
# BOM Lines — POST/PATCH/DELETE /admin/bom/{id}/lines
# =============================================================================

class TestBOMLines:
    """Tests for individual BOM line operations."""

    def test_add_line_to_existing_bom(self, client, finished_good, raw_material, make_product, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        new_component = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("0.75"),
        )

        response = client.post(f"{BASE_URL}/{bom.id}/lines", json={
            "component_id": new_component.id,
            "quantity": "5",
            "unit": "EA",
        })
        assert response.status_code == 201

        data = response.json()
        assert data["component_id"] == new_component.id

    def test_add_line_bom_not_found(self, client, raw_material):
        response = client.post(f"{BASE_URL}/999999/lines", json={
            "component_id": raw_material.id,
            "quantity": "10",
            "unit": "G",
        })
        assert response.status_code == 404

    def test_add_line_component_not_found(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.post(f"{BASE_URL}/{bom.id}/lines", json={
            "component_id": 999999,
            "quantity": "10",
            "unit": "EA",
        })
        assert response.status_code == 400

    def test_update_line_quantity(self, client, db, finished_good, raw_material, make_bom):
        from app.models.bom import BOMLine

        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        line = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).first()

        response = client.patch(f"{BASE_URL}/{bom.id}/lines/{line.id}", json={
            "quantity": "250",
        })
        assert response.status_code == 200
        assert Decimal(str(response.json()["quantity"])) == Decimal("250")

    def test_update_line_not_found(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.patch(f"{BASE_URL}/{bom.id}/lines/999999", json={
            "quantity": "250",
        })
        assert response.status_code == 404

    def test_delete_line(self, client, db, finished_good, raw_material, make_product, make_bom):
        from app.models.bom import BOMLine

        comp_a = raw_material
        comp_b = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("1.00"),
        )

        bom = make_bom(
            product_id=finished_good.id,
            lines=[
                {"component_id": comp_a.id, "quantity": Decimal("100"), "unit": "G"},
                {"component_id": comp_b.id, "quantity": Decimal("2"), "unit": "EA"},
            ],
        )
        line_to_delete = db.query(BOMLine).filter(
            BOMLine.bom_id == bom.id,
            BOMLine.component_id == comp_b.id,
        ).first()

        response = client.delete(f"{BASE_URL}/{bom.id}/lines/{line_to_delete.id}")
        assert response.status_code == 204

    def test_delete_line_not_found(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.delete(f"{BASE_URL}/{bom.id}/lines/999999")
        assert response.status_code == 404


# =============================================================================
# Get BOM by Product — GET /admin/bom/product/{product_id}
# =============================================================================

class TestGetBOMByProduct:
    """Tests for retrieving the active BOM for a product."""

    def test_get_bom_by_product_success(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.get(f"{BASE_URL}/product/{finished_good.id}")
        assert response.status_code == 200
        assert response.json()["id"] == bom.id

    def test_get_bom_by_product_no_active_bom(self, client, make_product):
        product_without_bom = make_product(item_type="finished_good")
        response = client.get(f"{BASE_URL}/product/{product_without_bom.id}")
        assert response.status_code == 404


# =============================================================================
# BOM Copy — POST /admin/bom/{id}/copy
# =============================================================================

class TestCopyBOM:
    """Tests for copying a BOM to another product."""

    def test_copy_bom_with_lines(self, client, finished_good, raw_material, make_product, make_bom):
        source_bom = make_bom(
            product_id=finished_good.id,
            lines=[
                {"component_id": raw_material.id, "quantity": Decimal("150"), "unit": "G"},
            ],
        )
        target = make_product(item_type="finished_good", procurement_type="make")

        response = client.post(f"{BASE_URL}/{source_bom.id}/copy", json={
            "target_product_id": target.id,
            "include_lines": True,
        })
        assert response.status_code == 201

        data = response.json()
        assert data["product_id"] == target.id
        assert data["id"] != source_bom.id
        assert len(data["lines"]) == 1
        assert data["lines"][0]["component_id"] == raw_material.id

    def test_copy_bom_without_lines(self, client, finished_good, raw_material, make_product, make_bom):
        source_bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        target = make_product(item_type="finished_good", procurement_type="make")

        response = client.post(f"{BASE_URL}/{source_bom.id}/copy", json={
            "target_product_id": target.id,
            "include_lines": False,
        })
        assert response.status_code == 201

        data = response.json()
        assert data["product_id"] == target.id
        assert len(data["lines"]) == 0

    def test_copy_bom_source_not_found(self, client, make_product):
        target = make_product(item_type="finished_good")
        response = client.post(f"{BASE_URL}/999999/copy", json={
            "target_product_id": target.id,
            "include_lines": True,
        })
        assert response.status_code == 404

    def test_copy_bom_target_product_not_found(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.post(f"{BASE_URL}/{bom.id}/copy", json={
            "target_product_id": 999999,
            "include_lines": True,
        })
        assert response.status_code == 404


# =============================================================================
# BOM Recalculate — POST /admin/bom/{id}/recalculate
# =============================================================================

class TestRecalculateBOM:
    """Tests for recalculating BOM cost."""

    def test_recalculate_bom(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.post(f"{BASE_URL}/{bom.id}/recalculate")
        assert response.status_code == 200

        data = response.json()
        assert data["bom_id"] == bom.id
        assert "new_cost" in data
        assert "previous_cost" in data
        assert isinstance(data["line_costs"], list)

    def test_recalculate_bom_not_found(self, client):
        response = client.post(f"{BASE_URL}/999999/recalculate")
        assert response.status_code == 404


# =============================================================================
# BOM Validate — POST /admin/bom/{id}/validate
# =============================================================================

class TestValidateBOM:
    """Tests for BOM validation endpoint."""

    def test_validate_valid_bom(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.post(f"{BASE_URL}/{bom.id}/validate")
        assert response.status_code == 200

        data = response.json()
        assert data["bom_id"] == bom.id
        assert "is_valid" in data
        assert "issues" in data

    def test_validate_empty_bom(self, client, finished_good, make_bom):
        bom = make_bom(product_id=finished_good.id, lines=[])

        response = client.post(f"{BASE_URL}/{bom.id}/validate")
        assert response.status_code == 200

        data = response.json()
        assert data["warning_count"] >= 1
        codes = [i["code"] for i in data["issues"]]
        assert "empty_bom" in codes

    def test_validate_bom_not_found(self, client):
        response = client.post(f"{BASE_URL}/999999/validate")
        assert response.status_code == 404


# =============================================================================
# Where Used — GET /admin/bom/where-used/{product_id}
# =============================================================================

class TestWhereUsed:
    """Tests for finding BOMs that use a component."""

    def test_where_used_returns_parent_boms(self, client, raw_material, make_product, make_bom):
        fg_a = make_product(item_type="finished_good", procurement_type="make")
        fg_b = make_product(item_type="finished_good", procurement_type="make")

        make_bom(
            product_id=fg_a.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        make_bom(
            product_id=fg_b.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("200"), "unit": "G"}],
        )

        response = client.get(f"{BASE_URL}/where-used/{raw_material.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["component_id"] == raw_material.id
        assert data["used_in_count"] >= 2

    def test_where_used_component_not_found(self, client):
        response = client.get(f"{BASE_URL}/where-used/999999")
        assert response.status_code == 404

    def test_where_used_component_unused(self, client, make_product):
        unused = make_product(item_type="supply", unit="EA")
        response = client.get(f"{BASE_URL}/where-used/{unused.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["used_in_count"] == 0
        assert data["used_in"] == []


# =============================================================================
# BOM Explode — GET /admin/bom/{id}/explode
# =============================================================================

class TestExplodeBOM:
    """Tests for multi-level BOM explosion."""

    def test_explode_single_level_bom(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.get(f"{BASE_URL}/{bom.id}/explode")
        assert response.status_code == 200

        data = response.json()
        assert data["bom_id"] == bom.id
        assert data["total_components"] >= 1

    def test_explode_multi_level_bom(self, client, raw_material, make_product, make_bom):
        """Finished good -> sub-assembly -> raw material."""
        sub_assembly = make_product(
            item_type="finished_good", procurement_type="make",
            name="Sub-Assembly Widget",
            standard_cost=Decimal("2.00"),
        )
        finished = make_product(
            item_type="finished_good", procurement_type="make",
            name="Top-Level Assembly",
        )

        # Sub-assembly BOM: uses raw material
        make_bom(
            product_id=sub_assembly.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("50"), "unit": "G"}],
        )

        # Top-level BOM: uses sub-assembly
        top_bom = make_bom(
            product_id=finished.id,
            lines=[{"component_id": sub_assembly.id, "quantity": Decimal("2"), "unit": "EA"}],
        )

        response = client.get(f"{BASE_URL}/{top_bom.id}/explode")
        assert response.status_code == 200

        data = response.json()
        # Should contain the sub-assembly and its raw material
        assert data["total_components"] >= 2
        component_ids = [c["component_id"] for c in data["components"]]
        assert sub_assembly.id in component_ids
        assert raw_material.id in component_ids

    def test_explode_bom_not_found(self, client):
        response = client.get(f"{BASE_URL}/999999/explode")
        assert response.status_code == 404


# =============================================================================
# Cost Rollup — GET /admin/bom/{id}/cost-rollup
# =============================================================================

class TestCostRollup:
    """Tests for cost rollup endpoint."""

    def test_cost_rollup_single_level(self, client, finished_good, raw_material, make_bom):
        bom = make_bom(
            product_id=finished_good.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"}],
        )
        response = client.get(f"{BASE_URL}/{bom.id}/cost-rollup")
        assert response.status_code == 200

        data = response.json()
        assert data["bom_id"] == bom.id
        assert "rolled_up_cost" in data
        assert "breakdown" in data
        assert isinstance(data["breakdown"], list)
        assert len(data["breakdown"]) >= 1

    def test_cost_rollup_not_found(self, client):
        response = client.get(f"{BASE_URL}/999999/cost-rollup")
        assert response.status_code == 404

    def test_cost_rollup_with_sub_assembly(self, client, raw_material, make_product, make_bom):
        sub = make_product(
            item_type="finished_good", procurement_type="make",
            standard_cost=Decimal("3.00"),
        )
        top = make_product(
            item_type="finished_good", procurement_type="make",
        )

        make_bom(
            product_id=sub.id,
            lines=[{"component_id": raw_material.id, "quantity": Decimal("50"), "unit": "G"}],
        )
        top_bom = make_bom(
            product_id=top.id,
            lines=[{"component_id": sub.id, "quantity": Decimal("1"), "unit": "EA"}],
        )

        response = client.get(f"{BASE_URL}/{top_bom.id}/cost-rollup")
        assert response.status_code == 200

        data = response.json()
        assert data["has_sub_assemblies"] is True
        assert data["sub_assembly_count"] >= 1


# =============================================================================
# BOM Service — get_effective_cost helper
# =============================================================================

class TestGetEffectiveCost:
    """Tests for the get_effective_cost priority logic."""

    def test_standard_cost_takes_priority(self, make_product):
        from app.services.bom_management_service import get_effective_cost

        product = make_product(
            standard_cost=Decimal("10.00"),
            average_cost=Decimal("8.00"),
        )
        assert get_effective_cost(product) == Decimal("10.00")

    def test_falls_back_to_average_cost(self, make_product):
        from app.services.bom_management_service import get_effective_cost

        product = make_product(
            standard_cost=None,
            average_cost=Decimal("8.50"),
        )
        assert get_effective_cost(product) == Decimal("8.50")

    def test_returns_zero_when_no_cost(self, make_product):
        from app.services.bom_management_service import get_effective_cost

        product = make_product(
            standard_cost=None,
            average_cost=None,
        )
        assert get_effective_cost(product) == Decimal("0")


# =============================================================================
# BOM Service — calculate_material_line_cost helper
# =============================================================================

class TestCalculateMaterialLineCost:
    """Tests for material line cost calculation."""

    def test_grams_unit(self):
        from app.services.bom_management_service import calculate_material_line_cost

        # 500 G at $20/KG = (500/1000) * 20 = $10.00
        result = calculate_material_line_cost(
            effective_qty=Decimal("500"),
            line_unit="G",
            cost_per_kg=Decimal("20"),
        )
        assert result == Decimal("10")

    def test_kg_unit(self):
        from app.services.bom_management_service import calculate_material_line_cost

        # 2 KG at $20/KG = (2000/1000) * 20 = $40.00
        result = calculate_material_line_cost(
            effective_qty=Decimal("2"),
            line_unit="KG",
            cost_per_kg=Decimal("20"),
        )
        assert result == Decimal("40")

    def test_none_unit_treated_as_grams(self):
        from app.services.bom_management_service import calculate_material_line_cost

        # None unit -> treated as grams: 1000 G at $25/KG = $25.00
        result = calculate_material_line_cost(
            effective_qty=Decimal("1000"),
            line_unit=None,
            cost_per_kg=Decimal("25"),
        )
        assert result == Decimal("25")
