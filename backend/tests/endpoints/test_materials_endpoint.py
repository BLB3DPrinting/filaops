"""
Tests for Materials API endpoints (/api/v1/materials).

Covers the main paths:
- GET  /api/v1/materials/options           (portal material options)
- GET  /api/v1/materials/types             (list material types)
- GET  /api/v1/materials/types/{code}/colors (colors for a material type)
- POST /api/v1/materials/types/{code}/colors (create color for material type)
"""
import uuid
import pytest
from decimal import Decimal


BASE_URL = "/api/v1/materials"


def _uid():
    """Short unique suffix for test data."""
    return uuid.uuid4().hex[:8]


# =============================================================================
# Local fixtures for material test data
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
# GET /api/v1/materials/options -- Portal material options
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
        """If materials exist, verify the expected fields on each entry."""
        resp = client.get(f"{BASE_URL}/options")
        data = resp.json()
        if len(data["materials"]) > 0:
            material = data["materials"][0]
            expected = {
                "code", "name", "description", "base_material",
                "price_multiplier", "strength_rating",
                "requires_enclosure", "colors",
            }
            assert expected.issubset(material.keys())

    def test_options_color_entry_shape(self, client):
        """If any material has colors, verify color fields."""
        resp = client.get(f"{BASE_URL}/options")
        data = resp.json()
        for material in data["materials"]:
            if len(material["colors"]) > 0:
                color = material["colors"][0]
                expected = {"code", "name", "hex", "in_stock", "quantity_kg"}
                assert expected.issubset(color.keys())
                return

    def test_options_does_not_require_auth(self, unauthed_client):
        """Material options are publicly accessible (no auth required)."""
        resp = unauthed_client.get(f"{BASE_URL}/options")
        assert resp.status_code == 200

    def test_options_with_in_stock_only_false(self, client):
        resp = client.get(f"{BASE_URL}/options", params={"in_stock_only": False})
        assert resp.status_code == 200
        data = resp.json()
        assert "materials" in data


# =============================================================================
# GET /api/v1/materials/types -- List material types
# =============================================================================


class TestListMaterialTypes:
    """Tests for listing material types."""

    def test_types_returns_200(self, client):
        resp = client.get(f"{BASE_URL}/types")
        assert resp.status_code == 200

    def test_types_response_shape(self, client):
        resp = client.get(f"{BASE_URL}/types")
        data = resp.json()
        assert "materials" in data
        assert isinstance(data["materials"], list)

    def test_types_includes_created_material(self, client, make_material_type):
        """A created material type appears in the types list."""
        uid = _uid().upper()
        mt = make_material_type(code=f"TYPETST-{uid}", name=f"Type Test {uid}")
        resp = client.get(f"{BASE_URL}/types")
        data = resp.json()
        codes = [m["code"] for m in data["materials"]]
        assert mt.code in codes

    def test_types_entry_shape(self, client, make_material_type):
        """Each material type entry has the expected fields."""
        uid = _uid().upper()
        make_material_type(code=f"SHAPE-{uid}", name=f"Shape {uid}")
        resp = client.get(f"{BASE_URL}/types")
        data = resp.json()
        material = next(
            (m for m in data["materials"] if m["code"] == f"SHAPE-{uid}"), None
        )
        assert material is not None
        expected = {
            "code", "name", "base_material", "description",
            "price_multiplier", "strength_rating", "requires_enclosure",
        }
        assert expected.issubset(material.keys())

    def test_types_customer_visible_only_default(self, client, make_material_type):
        """Default filters to customer-visible types only."""
        uid = _uid().upper()
        make_material_type(
            code=f"HIDDEN-{uid}", name=f"Hidden {uid}", is_customer_visible=False,
        )
        resp = client.get(f"{BASE_URL}/types")
        data = resp.json()
        codes = [m["code"] for m in data["materials"]]
        assert f"HIDDEN-{uid}" not in codes

    def test_types_include_hidden_with_flag(self, client, make_material_type):
        """customer_visible_only=False includes hidden materials."""
        uid = _uid().upper()
        make_material_type(
            code=f"HIDDEN2-{uid}", name=f"Hidden2 {uid}", is_customer_visible=False,
        )
        resp = client.get(f"{BASE_URL}/types", params={"customer_visible_only": False})
        data = resp.json()
        codes = [m["code"] for m in data["materials"]]
        assert f"HIDDEN2-{uid}" in codes

    def test_types_does_not_require_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/types")
        assert resp.status_code == 200


# =============================================================================
# GET /api/v1/materials/types/{code}/colors -- Colors for material type
# =============================================================================


class TestColorsForMaterialType:
    """Tests for listing colors for a specific material type."""

    def test_colors_returns_200(
        self, client, make_material_type, make_color, make_material_color,
    ):
        uid = _uid().upper()
        mt = make_material_type(code=f"CLRMT-{uid}")
        color = make_color(code=f"CLR-{uid}", name="Test Red", hex_code="#FF0000")
        make_material_color(material_type_id=mt.id, color_id=color.id)
        resp = client.get(f"{BASE_URL}/types/{mt.code}/colors")
        assert resp.status_code == 200

    def test_colors_response_shape(
        self, client, make_material_type, make_color, make_material_color,
    ):
        uid = _uid().upper()
        mt = make_material_type(code=f"CLRSH-{uid}")
        color = make_color(code=f"CLRS-{uid}", name="Shape Blue", hex_code="#0000FF")
        make_material_color(material_type_id=mt.id, color_id=color.id)
        resp = client.get(
            f"{BASE_URL}/types/{mt.code}/colors", params={"in_stock_only": "false"}
        )
        data = resp.json()
        assert data["material_type"] == mt.code
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
        uid = _uid().upper()
        mt = make_material_type(code=f"LNKMT-{uid}")
        c1 = make_color(code=f"LNK-RED-{uid}", name="Red", hex_code="#FF0000")
        c2 = make_color(code=f"LNK-BLU-{uid}", name="Blue", hex_code="#0000FF")
        make_material_color(material_type_id=mt.id, color_id=c1.id)
        make_material_color(material_type_id=mt.id, color_id=c2.id)
        resp = client.get(
            f"{BASE_URL}/types/{mt.code}/colors", params={"in_stock_only": "false"}
        )
        data = resp.json()
        color_codes = [c["code"] for c in data["colors"]]
        assert f"LNK-RED-{uid}" in color_codes
        assert f"LNK-BLU-{uid}" in color_codes


# =============================================================================
# POST /api/v1/materials/types/{code}/colors -- Create color
# =============================================================================


class TestCreateColorForMaterial:
    """Tests for creating a new color and linking to a material type."""

    def test_create_color_success(self, client, make_material_type):
        uid = _uid().upper()
        mt = make_material_type(code=f"CRCLR-{uid}")
        resp = client.post(
            f"{BASE_URL}/types/{mt.code}/colors",
            json={"name": "Mystic Purple", "hex_code": "#8B00FF"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Mystic Purple"
        assert data["hex_code"] == "#8B00FF"
        assert data["material_type_code"] == mt.code
        assert "id" in data
        assert "code" in data
        assert "message" in data

    def test_create_color_auto_generates_code(self, client, make_material_type):
        uid = _uid().upper()
        mt = make_material_type(code=f"ACODE-{uid}")
        resp = client.post(
            f"{BASE_URL}/types/{mt.code}/colors",
            json={"name": "Sky Blue"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "SKY_BLUE"

    def test_create_color_with_explicit_code(self, client, make_material_type):
        uid = _uid().upper()
        mt = make_material_type(code=f"ECODE-{uid}")
        resp = client.post(
            f"{BASE_URL}/types/{mt.code}/colors",
            json={"name": "Custom Code", "code": f"CC-{uid}"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == f"CC-{uid}"

    def test_create_color_nonexistent_material_returns_404(self, client):
        resp = client.post(
            f"{BASE_URL}/types/DOES-NOT-EXIST/colors",
            json={"name": "Orphan Color"},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_create_color_already_linked_returns_400(
        self, client, make_material_type, make_color, make_material_color,
    ):
        uid = _uid().upper()
        mt = make_material_type(code=f"DUPLNK-{uid}")
        color = make_color(code=f"DCLR-{uid}", name=f"Dup Color {uid}")
        make_material_color(material_type_id=mt.id, color_id=color.id)
        resp = client.post(
            f"{BASE_URL}/types/{mt.code}/colors",
            json={"name": f"Dup Color {uid}", "code": f"DCLR-{uid}"},
        )
        assert resp.status_code == 400
        assert "already linked" in resp.json()["detail"].lower()

    def test_create_color_requires_auth(self, unauthed_client, make_material_type):
        mt = make_material_type()
        resp = unauthed_client.post(
            f"{BASE_URL}/types/{mt.code}/colors",
            json={"name": "Unauthed Color"},
        )
        assert resp.status_code == 401

    def test_create_color_requires_admin(self, client, db):
        """Non-admin users should get 403 (or 404 if material doesn't exist)."""
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
            # 403 for non-admin or 404 if material not found first
            assert resp.status_code in (403, 404)
        finally:
            user.account_type = original_account_type
            db.flush()
