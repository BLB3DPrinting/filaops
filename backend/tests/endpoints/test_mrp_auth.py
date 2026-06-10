"""
Auth tests for MRP endpoints (/api/v1/mrp/).

All MRP read endpoints must require staff authentication and return 401
when accessed without a valid Bearer token.
"""
import pytest


class TestMRPUnauthenticated:
    """All /mrp read endpoints must reject unauthenticated requests with 401."""

    def test_list_runs_requires_auth(self, unauthed_client):
        """GET /mrp/runs returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/mrp/runs")
        assert resp.status_code == 401

    def test_get_run_requires_auth(self, unauthed_client):
        """GET /mrp/runs/{run_id} returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/mrp/runs/1")
        assert resp.status_code == 401

    def test_list_planned_orders_requires_auth(self, unauthed_client):
        """GET /mrp/planned-orders returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/mrp/planned-orders")
        assert resp.status_code == 401

    def test_get_planned_order_requires_auth(self, unauthed_client):
        """GET /mrp/planned-orders/{order_id} returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/mrp/planned-orders/1")
        assert resp.status_code == 401

    def test_requirements_requires_auth(self, unauthed_client):
        """GET /mrp/requirements returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/mrp/requirements?product_id=1")
        assert resp.status_code == 401

    def test_supply_demand_requires_auth(self, unauthed_client):
        """GET /mrp/supply-demand/{product_id} returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/mrp/supply-demand/1")
        assert resp.status_code == 401

    def test_explode_bom_requires_auth(self, unauthed_client):
        """GET /mrp/explode-bom/{product_id} returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/mrp/explode-bom/1")
        assert resp.status_code == 401

    def test_post_run_requires_auth(self, unauthed_client):
        """POST /mrp/run returns 401 without auth."""
        resp = unauthed_client.post("/api/v1/mrp/run", json={
            "planning_horizon_days": 30,
            "include_draft_orders": False,
            "regenerate_planned": True,
        })
        assert resp.status_code == 401


class TestMRPAuthenticated:
    """Authenticated staff users can reach MRP endpoints (no 401/403)."""

    def test_list_runs_accessible_with_auth(self, client):
        """GET /mrp/runs returns 200 with valid auth."""
        resp = client.get("/api/v1/mrp/runs")
        assert resp.status_code == 200

    def test_list_planned_orders_accessible_with_auth(self, client):
        """GET /mrp/planned-orders returns 200 with valid auth."""
        resp = client.get("/api/v1/mrp/planned-orders")
        assert resp.status_code == 200
