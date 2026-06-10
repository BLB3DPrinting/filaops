"""
Auth tests for materials endpoints (/api/v1/materials/).

The materials router carries a router-level get_current_user dependency:
the catalog, stock levels, and pricing data are internal, so every route
must return 401 without a valid token.
"""


class TestMaterialsUnauthenticated:
    """All /materials endpoints must reject unauthenticated requests with 401."""

    def test_options_requires_auth(self, unauthed_client):
        """GET /materials/options returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/materials/options")
        assert resp.status_code == 401

    def test_types_requires_auth(self, unauthed_client):
        """GET /materials/types returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/materials/types")
        assert resp.status_code == 401

    def test_colors_requires_auth(self, unauthed_client):
        """GET /materials/types/{code}/colors returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/materials/types/PLA_BASIC/colors")
        assert resp.status_code == 401

    def test_for_bom_requires_auth(self, unauthed_client):
        """GET /materials/for-bom returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/materials/for-bom")
        assert resp.status_code == 401

    def test_for_order_requires_auth(self, unauthed_client):
        """GET /materials/for-order returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/materials/for-order")
        assert resp.status_code == 401

    def test_pricing_requires_auth(self, unauthed_client):
        """GET /materials/pricing/{code} returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/materials/pricing/PLA_BASIC")
        assert resp.status_code == 401

    def test_import_template_requires_auth(self, unauthed_client):
        """GET /materials/import/template returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/materials/import/template")
        assert resp.status_code == 401

    def test_patch_type_requires_auth(self, unauthed_client):
        """PATCH /materials/types/{code} returns 401 without auth."""
        resp = unauthed_client.patch(
            "/api/v1/materials/types/PLA_BASIC",
            json={"filament_diameter": 1.75},
        )
        assert resp.status_code == 401

    def test_create_color_requires_auth(self, unauthed_client):
        """POST /materials/types/{code}/colors returns 401 without auth."""
        resp = unauthed_client.post(
            "/api/v1/materials/types/PLA_BASIC/colors",
            json={"name": "Test Red"},
        )
        assert resp.status_code == 401

    def test_import_requires_auth(self, unauthed_client):
        """POST /materials/import returns 401 without auth."""
        resp = unauthed_client.post(
            "/api/v1/materials/import",
            files={"file": ("materials.csv", b"a,b\n", "text/csv")},
        )
        assert resp.status_code == 401


class TestMaterialsAuthenticated:
    """Authenticated users can still reach the materials read endpoints."""

    def test_options_accessible_with_auth(self, client):
        """GET /materials/options returns 200 with valid auth."""
        resp = client.get("/api/v1/materials/options")
        assert resp.status_code == 200

    def test_types_accessible_with_auth(self, client):
        """GET /materials/types returns 200 with valid auth."""
        resp = client.get("/api/v1/materials/types")
        assert resp.status_code == 200

    def test_for_bom_accessible_with_auth(self, client):
        """GET /materials/for-bom returns 200 with valid auth."""
        resp = client.get("/api/v1/materials/for-bom")
        assert resp.status_code == 200

    def test_import_template_accessible_with_auth(self, client):
        """GET /materials/import/template returns 200 with valid auth."""
        resp = client.get("/api/v1/materials/import/template")
        assert resp.status_code == 200
