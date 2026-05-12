"""
Tests for Material Spool API endpoints (/api/v1/spools).

Focuses on the JSON-body refactor landed alongside the canonical ?? null
form-state pattern: ``PATCH {"location_id": null}`` must clear the column,
while ``PATCH {}`` must leave it unchanged. This was the Copilot finding
on PR #603 that the original URLSearchParams-based PATCH could not satisfy.

Covers:
- Auth requirements (POST and PATCH)
- Create happy path + duplicate / unknown product validation
- Create with location_id null
- Update location_id (set + clear + leave-unchanged)
- Update notes (set + clear via null + clear via empty string)
- Update status (truthy-preserved — null does NOT clear)
- Weight update validation (missing reason, null weight)
"""
from decimal import Decimal

import pytest

from app.models import InventoryLocation, MaterialSpool


BASE_URL = "/api/v1/spools"


# =============================================================================
# Helpers
# =============================================================================

@pytest.fixture
def location(db):
    """Create a storage location for spool placement."""
    loc = InventoryLocation(name="Test Warehouse A", code="WHA")
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@pytest.fixture
def other_location(db):
    """A second location, for tests that move a spool between locations."""
    loc = InventoryLocation(name="Test Warehouse B", code="WHB")
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc


@pytest.fixture
def material_product(make_product):
    """A material-type product so MaterialSpool FK is valid."""
    return make_product(item_type="supply", unit="G")


@pytest.fixture
def spool(db, material_product, location):
    """Persist a MaterialSpool directly so PATCH tests can target it."""
    s = MaterialSpool(
        spool_number=f"SP-{material_product.id}-A",
        product_id=material_product.id,
        initial_weight_kg=Decimal("1000"),
        current_weight_kg=Decimal("950"),
        status="active",
        location_id=location.id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# =============================================================================
# Authentication
# =============================================================================

class TestAuth:
    def test_create_requires_auth(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/",
            json={"spool_number": "X", "product_id": 1, "initial_weight_kg": 1.0},
        )
        assert resp.status_code == 401

    def test_update_requires_auth(self, unauthed_client):
        resp = unauthed_client.patch(f"{BASE_URL}/1", json={"location_id": None})
        assert resp.status_code == 401


# =============================================================================
# Create (POST /spools/)
# =============================================================================

class TestCreate:
    def test_create_happy_path(self, client, material_product, location):
        resp = client.post(
            f"{BASE_URL}/",
            json={
                "spool_number": "SP-CREATE-001",
                "product_id": material_product.id,
                "initial_weight_kg": 1000.0,
                "current_weight_kg": 950.0,
                "location_id": location.id,
                "supplier_lot_number": "LOT-123",
                "notes": "fresh spool",
            },
        )
        assert resp.status_code in (200, 201), resp.text
        data = resp.json()
        assert data["spool_number"] == "SP-CREATE-001"
        assert "id" in data

    def test_create_without_optional_fields(self, client, material_product):
        resp = client.post(
            f"{BASE_URL}/",
            json={
                "spool_number": "SP-CREATE-002",
                "product_id": material_product.id,
                "initial_weight_kg": 1000.0,
            },
        )
        assert resp.status_code in (200, 201), resp.text

    def test_create_with_explicit_null_location(self, client, material_product):
        """location_id=null at create time is valid (spool with no location)."""
        resp = client.post(
            f"{BASE_URL}/",
            json={
                "spool_number": "SP-CREATE-003",
                "product_id": material_product.id,
                "initial_weight_kg": 1000.0,
                "location_id": None,
            },
        )
        assert resp.status_code in (200, 201), resp.text

    def test_create_duplicate_spool_number_400(self, client, material_product, spool):
        resp = client.post(
            f"{BASE_URL}/",
            json={
                "spool_number": spool.spool_number,
                "product_id": material_product.id,
                "initial_weight_kg": 1000.0,
            },
        )
        assert resp.status_code == 400

    def test_create_unknown_product_404(self, client):
        resp = client.post(
            f"{BASE_URL}/",
            json={
                "spool_number": "SP-CREATE-004",
                "product_id": 999_999,
                "initial_weight_kg": 1000.0,
            },
        )
        assert resp.status_code == 404


# =============================================================================
# Update (PATCH /spools/{id}) — the core of this PR
# =============================================================================

class TestUpdateLocation:
    """The Copilot fix: explicit-null in JSON body must clear location_id."""

    def test_patch_explicit_null_clears_location(self, client, db, spool):
        assert spool.location_id is not None  # baseline

        resp = client.patch(f"{BASE_URL}/{spool.id}", json={"location_id": None})
        assert resp.status_code == 200, resp.text

        db.refresh(spool)
        assert spool.location_id is None, "PATCH location_id=null must clear the column"

    def test_patch_empty_body_leaves_location_unchanged(self, client, db, spool):
        original_location_id = spool.location_id
        assert original_location_id is not None

        resp = client.patch(f"{BASE_URL}/{spool.id}", json={})
        assert resp.status_code == 200, resp.text

        db.refresh(spool)
        assert spool.location_id == original_location_id, (
            "PATCH {} must leave location_id untouched (exclude_unset semantics)"
        )

    def test_patch_sets_new_location(self, client, db, spool, other_location):
        resp = client.patch(
            f"{BASE_URL}/{spool.id}",
            json={"location_id": other_location.id},
        )
        assert resp.status_code == 200, resp.text

        db.refresh(spool)
        assert spool.location_id == other_location.id


class TestUpdateNotes:
    def test_patch_explicit_null_clears_notes(self, client, db, spool):
        spool.notes = "some text"
        db.commit()
        db.refresh(spool)

        resp = client.patch(f"{BASE_URL}/{spool.id}", json={"notes": None})
        assert resp.status_code == 200

        db.refresh(spool)
        assert spool.notes is None

    def test_patch_empty_string_clears_notes(self, client, db, spool):
        spool.notes = "some text"
        db.commit()
        db.refresh(spool)

        resp = client.patch(f"{BASE_URL}/{spool.id}", json={"notes": ""})
        assert resp.status_code == 200

        db.refresh(spool)
        assert spool.notes == ""

    def test_patch_empty_body_leaves_notes_unchanged(self, client, db, spool):
        spool.notes = "keep me"
        db.commit()
        db.refresh(spool)

        resp = client.patch(f"{BASE_URL}/{spool.id}", json={})
        assert resp.status_code == 200

        db.refresh(spool)
        assert spool.notes == "keep me"


class TestUpdateStatus:
    """Status preserves the truthy check — null does NOT clear (no meaningful null state)."""

    def test_patch_sets_status(self, client, db, spool):
        resp = client.patch(f"{BASE_URL}/{spool.id}", json={"status": "empty"})
        assert resp.status_code == 200

        db.refresh(spool)
        assert spool.status == "empty"

    def test_patch_null_status_does_not_clear(self, client, db, spool):
        original_status = spool.status
        assert original_status is not None

        resp = client.patch(f"{BASE_URL}/{spool.id}", json={"status": None})
        assert resp.status_code == 200

        db.refresh(spool)
        assert spool.status == original_status, (
            "Status uses truthy-preserve; null must not clear it"
        )


class TestUpdateWeight:
    """Weight-adjustment validation that the refactor must preserve."""

    def test_patch_weight_requires_reason(self, client, spool):
        resp = client.patch(
            f"{BASE_URL}/{spool.id}",
            json={"current_weight_g": 900.0},
        )
        assert resp.status_code == 400
        assert "reason" in resp.text.lower()

    def test_patch_null_weight_400(self, client, spool):
        """Sending current_weight_g: null is nonsensical — must 400, not no-op."""
        resp = client.patch(
            f"{BASE_URL}/{spool.id}",
            json={"current_weight_g": None, "reason": "test"},
        )
        assert resp.status_code == 400


class TestFrontendBodyShape:
    """Guards against the regression CodeRabbit caught: AdminSpools modal
    used to send current_weight_g on every edit (no reason), which 400'd
    the backend before reaching the location_id branch and silently
    blocked the whole modal. The frontend now omits current_weight_g
    unless the user actually edited it. These tests pin the body shapes
    the modal sends after that fix."""

    def test_modal_edit_clearing_location(self, client, db, spool):
        """Body shape when user picks "No location" without touching weight."""
        resp = client.patch(
            f"{BASE_URL}/{spool.id}",
            json={
                "status": "active",
                "location_id": None,
                "notes": None,
            },
        )
        assert resp.status_code == 200, resp.text
        db.refresh(spool)
        assert spool.location_id is None

    def test_modal_edit_moving_location(self, client, db, spool, other_location):
        """Body shape when user changes location to a different value."""
        resp = client.patch(
            f"{BASE_URL}/{spool.id}",
            json={
                "status": "active",
                "location_id": other_location.id,
                "notes": "moved to WHB",
            },
        )
        assert resp.status_code == 200, resp.text
        db.refresh(spool)
        assert spool.location_id == other_location.id
        assert spool.notes == "moved to WHB"


# =============================================================================
# 404 behavior
# =============================================================================

class TestNotFound:
    def test_patch_unknown_spool_404(self, client):
        resp = client.patch(f"{BASE_URL}/999999", json={"location_id": None})
        assert resp.status_code == 404
