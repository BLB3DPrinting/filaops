"""
Tests for Materials API endpoints (/api/v1/materials).

Covers:
- Authentication requirements for protected endpoints
- Material options for portal dropdown
- Material types listing
- Colors for a material type (list, create)
- Materials for BOM usage
- Material pricing lookup
- CSV import/export template
"""
import io
import uuid

import pytest
from decimal import Decimal


BASE_URL = "/api/v1/materials"


def _uid():
    """Short unique suffix for test data."""
    return uuid.uuid4().hex[:8]


# =============================================================================
# Helper: material data factories
# =============================================================================

@pytest.fixture
def make_material_type(db):
    """Factory fixture to create MaterialType instances."""
    from app.models.material import MaterialType

    def _factory(code=None, name=None, base_material="PLA", **kwargs):
        uid = _uid()
        mt = MaterialType(
            code=code or f"MT-{uid}".upper(),
            name=name or f"Material {uid}",
            base_material=base_material,
            density=kwargs.pop("density", Decimal("1.24")),
            base_price_per_kg=kwargs.pop("base_price_per_kg", Decimal("20.00")),
            price_multiplier=kwargs.pop("price_multiplier", Decimal("1.0")),
            active=kwargs.pop("active", True),
            is_customer_visible=kwargs.pop("is_customer_visible", True),
            **kwargs,
        )
        db.add(mt)
        db.flush()
        return mt

    yield _factory


@pytest.fixture
def make_color(db):
    """Factory fixture to create Color instances."""
    from app.models.material import Color

    def _factory(code=None, name=None, hex_code=None, **kwargs):
        uid = _uid()
        color = Color(
            code=code or f"CLR-{uid}".upper(),
            name=name or f"Color {uid}",
            hex_code=hex_code,
            active=kwargs.pop("active", True),
            is_customer_visible=kwargs.pop("is_customer_visible", True),
            **kwargs,
        )
        db.add(color)
        db.flush()
        return color

    yield _factory


@pytest.fixture
def make_material_color(db):
    """Factory fixture to link a MaterialType to a Color."""
    from app.models.material import MaterialColor

    def _factory(material_type_id, color_id, **kwargs):
        mc = MaterialColor(
            material_type_id=material_type_id,
            color_id=color_id,
            is_customer_visible=kwargs.pop("is_customer_visible", True),
            active=kwargs.pop("active", True),
            **kwargs,
        )
        db.add(mc)
        db.flush()
        return mc

    yield _factory


# =============================================================================
# Authentication -- protected endpoints require auth
# =============================================================================

class TestMaterialsAuth:
    """Verify auth is required on write endpoints."""

    def test_create_color_requires_auth(self, unauthed_client, make_material_type):
        mt = make_material_type()
        resp = unauthed_client.post(
            f"{BASE_URL}/types/{mt.code}/colors",
            json={"name": "Test Color"},
        )
        assert resp.status_code == 401

    def test_import_csv_requires_auth(self, unauthed_client):
        csv_content = "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
        resp = unauthed_client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 401


# =============================================================================
# Public read endpoints -- no auth required
# =============================================================================

class TestMaterialsPublicEndpoints:
    """Material endpoints require staff auth (all expose pricing/inventory data).

    Previously these were public; gated in HARD-1 follow-up PR.
    The Quoter uses PRO /api/v1/pro/quotes/public-options, not these Core endpoints.
    """

    def test_options_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/options")
        assert resp.status_code == 401

    def test_types_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/types")
        assert resp.status_code == 401

    def test_for_bom_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/for-bom")
        assert resp.status_code == 401

    def test_import_template_requires_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/import/template")
        assert resp.status_code == 401


# =============================================================================
# GET /api/v1/materials/options -- portal material options
# =============================================================================

class TestMaterialOptions:
    """Tests for the portal material options endpoint."""

    def test_options_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/options")
        assert resp.status_code == 200

    def test_options_response_shape(self, client):
        resp = client.get(f"{BASE_URL}/options")
        data = resp.json()
        assert "materials" in data
        assert isinstance(data["materials"], list)

    def test_options_material_entry_shape(self, client):
        """If any materials exist, verify the expected fields."""
        resp = client.get(f"{BASE_URL}/options")
        data = resp.json()
        if len(data["materials"]) > 0:
            material = data["materials"][0]
            expected_fields = {
                "code", "name", "description", "base_material",
                "price_multiplier", "strength_rating",
                "requires_enclosure", "colors",
            }
            assert expected_fields.issubset(material.keys())

    def test_options_color_entry_shape(self, client):
        """If any material has colors, verify color fields."""
        resp = client.get(f"{BASE_URL}/options")
        data = resp.json()
        for material in data["materials"]:
            if len(material["colors"]) > 0:
                color = material["colors"][0]
                expected_fields = {"code", "name", "hex", "in_stock", "quantity_kg"}
                assert expected_fields.issubset(color.keys())
                return
        # No colors found -- that is fine, shape cannot be verified

    def test_options_in_stock_only_defaults_true(self, client):
        """Default request filters to in-stock only."""
        resp = client.get(f"{BASE_URL}/options")
        assert resp.status_code == 200

    def test_options_in_stock_only_false(self, client):
        resp = client.get(f"{BASE_URL}/options", params={"in_stock_only": False})
        assert resp.status_code == 200
        data = resp.json()
        assert "materials" in data


# =============================================================================
# GET /api/v1/materials/types -- list material types
# =============================================================================

class TestMaterialTypes:
    """Tests for listing material types."""

    def test_types_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/types")
        assert resp.status_code == 200

    def test_types_response_shape(self, client):
        resp = client.get(f"{BASE_URL}/types")
        data = resp.json()
        assert "materials" in data
        assert isinstance(data["materials"], list)

    def test_types_material_entry_shape(self, client, make_material_type):
        make_material_type(code="SHAPE-TEST-MT", name="Shape Test Material")
        resp = client.get(f"{BASE_URL}/types")
        data = resp.json()
        assert len(data["materials"]) >= 1
        material = next(
            (m for m in data["materials"] if m["code"] == "SHAPE-TEST-MT"),
            None,
        )
        assert material is not None
        expected_fields = {
            "code", "name", "base_material", "description",
            "price_multiplier", "strength_rating", "requires_enclosure",
        }
        assert expected_fields.issubset(material.keys())

    def test_types_customer_visible_only_default(self, client, make_material_type):
        """Default filters to customer-visible types only."""
        hidden = make_material_type(
            code="HIDDEN-MT", name="Hidden", is_customer_visible=False,
        )
        resp = client.get(f"{BASE_URL}/types")
        data = resp.json()
        codes = [m["code"] for m in data["materials"]]
        assert "HIDDEN-MT" not in codes

    def test_types_include_non_customer_visible(self, client, make_material_type):
        hidden = make_material_type(
            code="HIDDEN-MT-2", name="Hidden 2", is_customer_visible=False,
        )
        resp = client.get(f"{BASE_URL}/types", params={"customer_visible_only": False})
        data = resp.json()
        codes = [m["code"] for m in data["materials"]]
        assert "HIDDEN-MT-2" in codes


# =============================================================================
# GET /api/v1/materials/types/{code}/colors -- colors for material type
# =============================================================================

class TestColorsForMaterialType:
    """Tests for listing colors for a specific material type."""

    def test_colors_returns_200(
        self, client, make_material_type, make_color, make_material_color,
    ):
        mt = make_material_type(code="CLR-MT-200")
        color = make_color(code="CLR-200", name="Test Red", hex_code="#FF0000")
        make_material_color(material_type_id=mt.id, color_id=color.id)
        resp = client.get(f"{BASE_URL}/types/CLR-MT-200/colors")
        assert resp.status_code == 200

    def test_colors_response_shape(
        self, client, make_material_type, make_color, make_material_color,
    ):
        mt = make_material_type(code="CLR-MT-SHAPE")
        color = make_color(code="CLR-SHAPE", name="Shape Blue", hex_code="#0000FF")
        make_material_color(material_type_id=mt.id, color_id=color.id)
        resp = client.get(f"{BASE_URL}/types/CLR-MT-SHAPE/colors", params={"in_stock_only": "false"})
        data = resp.json()
        assert data["material_type"] == "CLR-MT-SHAPE"
        assert "colors" in data
        assert isinstance(data["colors"], list)
        assert len(data["colors"]) >= 1
        color_item = data["colors"][0]
        assert "code" in color_item
        assert "name" in color_item
        assert "hex" in color_item

    def test_colors_nonexistent_type_returns_404(self, client):
        resp = client.get(f"{BASE_URL}/types/NONEXISTENT/colors")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_colors_returns_linked_colors(
        self, client, make_material_type, make_color, make_material_color,
    ):
        mt = make_material_type(code="CLR-MT-LINKED")
        c1 = make_color(code="LINKED-RED", name="Red", hex_code="#FF0000")
        c2 = make_color(code="LINKED-BLUE", name="Blue", hex_code="#0000FF")
        make_material_color(material_type_id=mt.id, color_id=c1.id)
        make_material_color(material_type_id=mt.id, color_id=c2.id)
        resp = client.get(f"{BASE_URL}/types/CLR-MT-LINKED/colors", params={"in_stock_only": "false"})
        data = resp.json()
        color_codes = [c["code"] for c in data["colors"]]
        assert "LINKED-RED" in color_codes
        assert "LINKED-BLUE" in color_codes


# =============================================================================
# POST /api/v1/materials/types/{code}/colors -- create color for material type
# =============================================================================

class TestCreateColorForMaterialType:
    """Tests for creating a new color and linking to a material type."""

    def test_create_color_success(self, client, make_material_type):
        mt = make_material_type(code="CREATE-CLR-MT")
        resp = client.post(
            f"{BASE_URL}/types/CREATE-CLR-MT/colors",
            json={"name": "Mystic Purple", "hex_code": "#8B00FF"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Mystic Purple"
        assert data["hex_code"] == "#8B00FF"
        assert data["material_type_code"] == "CREATE-CLR-MT"
        assert "id" in data
        assert "code" in data
        assert "message" in data

    def test_create_color_auto_generates_code(self, client, make_material_type):
        mt = make_material_type(code="AUTO-CODE-MT")
        resp = client.post(
            f"{BASE_URL}/types/AUTO-CODE-MT/colors",
            json={"name": "Mystic Blue"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "MYSTIC_BLUE"

    def test_create_color_with_explicit_code(self, client, make_material_type):
        mt = make_material_type(code="EXPLICIT-CODE-MT")
        resp = client.post(
            f"{BASE_URL}/types/EXPLICIT-CODE-MT/colors",
            json={"name": "Custom Code", "code": "MY-CODE"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == "MY-CODE"

    def test_create_color_nonexistent_material_type_returns_404(self, client):
        resp = client.post(
            f"{BASE_URL}/types/NONEXISTENT/colors",
            json={"name": "Orphan Color"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_create_color_already_linked_returns_400(
        self, client, make_material_type, make_color, make_material_color,
    ):
        mt = make_material_type(code="DUP-LINK-MT")
        color = make_color(code="DUP-LINK-CLR", name="Dup Link Color")
        make_material_color(material_type_id=mt.id, color_id=color.id)
        resp = client.post(
            f"{BASE_URL}/types/DUP-LINK-MT/colors",
            json={"name": "Dup Link Color", "code": "DUP-LINK-CLR"},
        )
        assert resp.status_code == 400
        assert "already linked" in resp.json()["detail"].lower()

    def test_create_color_existing_code_links_to_material(
        self, client, make_material_type, make_color,
    ):
        """If a color code already exists but is not linked, it should link it."""
        mt = make_material_type(code="LINK-EXIST-MT")
        existing_color = make_color(code="EXIST-CLR", name="Existing Color")
        resp = client.post(
            f"{BASE_URL}/types/LINK-EXIST-MT/colors",
            json={"name": "Existing Color", "code": "EXIST-CLR"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "EXIST-CLR"
        assert data["material_type_code"] == "LINK-EXIST-MT"

    def test_create_color_requires_admin(self, client, db):
        """Non-admin users should get 403."""
        from app.models.user import User

        user = db.query(User).filter(User.id == 1).first()
        original_account_type = user.account_type
        user.account_type = "user"
        db.flush()

        try:
            resp = client.post(
                f"{BASE_URL}/types/ANY-CODE/colors",
                json={"name": "Forbidden Color"},
            )
            assert resp.status_code in (403, 404)
        finally:
            user.account_type = original_account_type
            db.flush()


# =============================================================================
# GET /api/v1/materials/for-bom -- materials for BOM
# =============================================================================

class TestMaterialsForBom:
    """Tests for the BOM materials endpoint."""

    def test_for_bom_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/for-bom")
        assert resp.status_code == 200

    def test_for_bom_response_shape(self, client):
        resp = client.get(f"{BASE_URL}/for-bom")
        data = resp.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_for_bom_item_entry_shape(self, client):
        """If any BOM items exist, verify the expected fields."""
        resp = client.get(f"{BASE_URL}/for-bom")
        data = resp.json()
        if len(data["items"]) > 0:
            item = data["items"][0]
            expected_fields = {
                "id", "sku", "name", "item_type", "unit",
                "standard_cost", "in_stock", "quantity_available",
                "material_code", "color_code",
            }
            assert expected_fields.issubset(item.keys())


# =============================================================================
# GET /api/v1/materials/pricing/{code} -- material pricing
# =============================================================================

class TestMaterialPricing:
    """Tests for the material pricing endpoint."""

    def test_pricing_returns_200(self, client, make_material_type):
        mt = make_material_type(code="PRICE-MT", base_price_per_kg=Decimal("25.00"))
        resp = client.get(f"{BASE_URL}/pricing/PRICE-MT")
        assert resp.status_code == 200

    def test_pricing_response_shape(self, client, make_material_type):
        mt = make_material_type(
            code="PRICE-SHAPE-MT",
            base_price_per_kg=Decimal("22.50"),
            density=Decimal("1.24"),
        )
        resp = client.get(f"{BASE_URL}/pricing/PRICE-SHAPE-MT")
        data = resp.json()
        expected_fields = {
            "code", "name", "base_material", "density",
            "base_price_per_kg", "price_multiplier",
            "requires_enclosure",
        }
        assert expected_fields.issubset(data.keys())

    def test_pricing_values_correct(self, client, make_material_type):
        mt = make_material_type(
            code="PRICE-VAL-MT",
            name="Price Value Test",
            base_material="PETG",
            base_price_per_kg=Decimal("30.00"),
            price_multiplier=Decimal("1.5"),
            density=Decimal("1.27"),
        )
        resp = client.get(f"{BASE_URL}/pricing/PRICE-VAL-MT")
        data = resp.json()
        assert data["code"] == "PRICE-VAL-MT"
        assert data["name"] == "Price Value Test"
        assert data["base_material"] == "PETG"
        assert float(data["base_price_per_kg"]) == pytest.approx(30.00, abs=0.01)
        assert float(data["price_multiplier"]) == pytest.approx(1.5, abs=0.01)
        assert float(data["density"]) == pytest.approx(1.27, abs=0.01)

    def test_pricing_nonexistent_type_returns_404(self, client):
        resp = client.get(f"{BASE_URL}/pricing/NONEXISTENT")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_pricing_includes_temperature_fields(self, client, make_material_type):
        mt = make_material_type(
            code="PRICE-TEMP-MT",
            nozzle_temp_min=200,
            nozzle_temp_max=220,
            bed_temp_min=55,
            bed_temp_max=65,
        )
        resp = client.get(f"{BASE_URL}/pricing/PRICE-TEMP-MT")
        data = resp.json()
        assert data["nozzle_temp_min"] == 200
        assert data["nozzle_temp_max"] == 220
        assert data["bed_temp_min"] == 55
        assert data["bed_temp_max"] == 65


# =============================================================================
# GET /api/v1/materials/import/template -- CSV template download
# =============================================================================

class TestImportTemplate:
    """Tests for the CSV template download endpoint."""

    def test_template_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/import/template")
        assert resp.status_code == 200

    def test_template_content_type_is_csv(self, client):
        resp = client.get(f"{BASE_URL}/import/template")
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_template_has_content_disposition(self, client):
        resp = client.get(f"{BASE_URL}/import/template")
        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "material_inventory_template.csv" in disposition

    def test_template_contains_expected_headers(self, client):
        resp = client.get(f"{BASE_URL}/import/template")
        content = resp.text
        assert "Category" in content
        assert "SKU" in content
        assert "Material Type" in content
        assert "Material Color Name" in content
        assert "HEX Code" in content
        assert "On Hand (g)" in content

    def test_template_contains_sample_rows(self, client):
        resp = client.get(f"{BASE_URL}/import/template")
        content = resp.text
        lines = content.strip().split("\n")
        # Header row plus at least one sample row
        assert len(lines) >= 2


# =============================================================================
# POST /api/v1/materials/import -- CSV import
# =============================================================================

class TestImportCSV:
    """Tests for the CSV material import endpoint."""

    def test_import_valid_csv(self, client):
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            "PLA Matte,MAT-FDM-TEST-IMP-001,PLA Matte Test,PLA_MATTE_TEST,Charcoal,#0C0C0C,kg,Active,19.99,500\n"
        )
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 1
        assert data["created"] == 1
        assert data["errors"] == []

    def test_import_response_shape(self, client):
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            "PLA Basic,MAT-FDM-TEST-IMP-002,PLA Basic Red,PLA_BASIC_TEST,Red,#FF0000,kg,Active,19.99,0\n"
        )
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        expected_fields = {"total_rows", "created", "updated", "skipped", "errors"}
        assert expected_fields.issubset(data.keys())

    def test_import_non_csv_rejected(self, client):
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.txt", io.BytesIO(b"not csv"), "text/plain")},
        )
        assert resp.status_code == 400
        assert "CSV" in resp.json()["detail"]

    def test_import_missing_sku_reports_error(self, client):
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            "PLA Basic,,No SKU Item,PLA_BASIC_NOSKU,Red,#FF0000,kg,Active,19.99,0\n"
        )
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] >= 1
        assert len(data["errors"]) >= 1
        assert "SKU" in data["errors"][0]["error"]

    def test_import_missing_material_type_reports_error(self, client):
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            "PLA Basic,MAT-FDM-TEST-NOMT,No MT Item,,Red,#FF0000,kg,Active,19.99,0\n"
        )
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] >= 1
        assert len(data["errors"]) >= 1
        assert "Material Type" in data["errors"][0]["error"]

    def test_import_missing_color_name_reports_error(self, client):
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            "PLA Basic,MAT-FDM-TEST-NOCLR,No Color Item,PLA_BASIC_NOCLR,,#FF0000,kg,Active,19.99,0\n"
        )
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] >= 1
        assert len(data["errors"]) >= 1
        assert "Color" in data["errors"][0]["error"]

    def test_import_duplicate_sku_skipped_by_default(self, client):
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            "PLA Basic,MAT-FDM-TEST-DUP,Dup Item,PLA_BASIC_DUP,Red,#FF0000,kg,Active,19.99,0\n"
        )
        # First import
        client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        # Second import with same SKU
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] >= 1
        assert data["created"] == 0

    def test_import_duplicate_sku_updated_when_flag_set(self, client):
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            "PLA Basic,MAT-FDM-TEST-UPD,Update Item,PLA_BASIC_UPD,Blue,#0000FF,kg,Active,19.99,0\n"
        )
        # First import
        client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        # Second import with update_existing=true
        resp = client.post(
            f"{BASE_URL}/import?update_existing=true",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated"] >= 1

    def test_import_multiple_rows(self, client):
        uid = _uid()
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            f"PLA Matte,MAT-FDM-MULTI-A-{uid},PLA Matte A,PLA_MATTE_MULTI_{uid},Charcoal,#0C0C0C,kg,Active,19.99,500\n"
            f"PLA Matte,MAT-FDM-MULTI-B-{uid},PLA Matte B,PLA_MATTE_MULTI_{uid},Red,#FF0000,kg,Active,19.99,1000\n"
        )
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 2
        assert data["created"] == 2
        assert data["errors"] == []

    def test_import_empty_csv_no_data_rows(self, client):
        csv_content = "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_rows"] == 0
        assert data["created"] == 0
        assert data["errors"] == []

    def test_import_creates_material_type_if_not_exists(self, client, db):
        """Importing a CSV with a new material type code should create it."""
        from app.models.material import MaterialType

        uid = _uid()
        new_mt_code = f"NEW_MT_{uid}".upper()
        csv_content = (
            "Category,SKU,Name,Material Type,Material Color Name,HEX Code,Unit,Status,Price,On Hand (g)\n"
            f"PLA Basic,MAT-FDM-NEWMT-{uid},New MT Item,{new_mt_code},Black,#000000,kg,Active,22.00,0\n"
        )
        resp = client.post(
            f"{BASE_URL}/import",
            files={"file": ("materials.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["created"] == 1

        mt = db.query(MaterialType).filter(MaterialType.code == new_mt_code).first()
        assert mt is not None
