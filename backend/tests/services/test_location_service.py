"""Tests for location_service.py — inventory location CRUD."""
import pytest
from fastapi import HTTPException

from app.services import location_service


class TestListLocations:
    def test_list_returns_seeded_location(self, db):
        locations = location_service.list_locations(db)
        assert len(locations) >= 1
        codes = [loc.code for loc in locations]
        assert "DEFAULT" in codes

    def test_list_excludes_inactive_by_default(self, db):
        from app.models.inventory import InventoryLocation
        loc = InventoryLocation(code="INACTIVE-LOC", name="Inactive", type="warehouse", active=False)
        db.add(loc)
        db.flush()
        locations = location_service.list_locations(db)
        codes = [l.code for l in locations]
        assert "INACTIVE-LOC" not in codes

    def test_list_includes_inactive_when_requested(self, db):
        from app.models.inventory import InventoryLocation
        loc = InventoryLocation(code="INACTIVE-LOC2", name="Inactive 2", type="warehouse", active=False)
        db.add(loc)
        db.flush()
        locations = location_service.list_locations(db, include_inactive=True)
        codes = [l.code for l in locations]
        assert "INACTIVE-LOC2" in codes


class TestGetLocation:
    def test_get_existing(self, db):
        loc = location_service.get_location(db, 1)
        assert loc.code == "DEFAULT"

    def test_get_nonexistent_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            location_service.get_location(db, 999999)
        assert exc_info.value.status_code == 404


class TestCreateLocation:
    def test_create_basic(self, db):
        loc = location_service.create_location(db, code="SHELF-A", name="Shelf A")
        assert loc.id is not None
        assert loc.code == "SHELF-A"
        assert loc.type == "warehouse"
        assert loc.active is True

    def test_create_with_parent(self, db):
        parent = location_service.create_location(db, code="AREA-1", name="Area 1")
        child = location_service.create_location(db, code="BIN-1A", name="Bin 1A", parent_id=parent.id)
        assert child.parent_id == parent.id

    def test_create_duplicate_code_raises_400(self, db):
        location_service.create_location(db, code="DUP-CODE", name="First")
        with pytest.raises(HTTPException) as exc_info:
            location_service.create_location(db, code="DUP-CODE", name="Second")
        assert exc_info.value.status_code == 400

    def test_create_with_invalid_parent_raises_400(self, db):
        with pytest.raises(HTTPException) as exc_info:
            location_service.create_location(db, code="ORPHAN", name="Orphan", parent_id=999999)
        assert exc_info.value.status_code == 400


class TestUpdateLocation:
    def test_update_name(self, db):
        loc = location_service.create_location(db, code="UPD-LOC", name="Original")
        updated = location_service.update_location(db, loc.id, name="Updated")
        assert updated.name == "Updated"

    def test_update_code_unique_check(self, db):
        loc1 = location_service.create_location(db, code="LOC-A", name="A")
        loc2 = location_service.create_location(db, code="LOC-B", name="B")
        with pytest.raises(HTTPException) as exc_info:
            location_service.update_location(db, loc2.id, code="LOC-A")
        assert exc_info.value.status_code == 400

    def test_update_self_parent_raises_400(self, db):
        loc = location_service.create_location(db, code="SELF-REF", name="Self")
        with pytest.raises(HTTPException) as exc_info:
            location_service.update_location(db, loc.id, parent_id=loc.id)
        assert exc_info.value.status_code == 400

    def test_update_clear_parent(self, db):
        parent = location_service.create_location(db, code="PAR-CLR", name="Parent")
        child = location_service.create_location(db, code="CHD-CLR", name="Child", parent_id=parent.id)
        assert child.parent_id == parent.id
        updated = location_service.update_location(db, child.id, parent_id=None)
        assert updated.parent_id is None


class TestDeleteLocation:
    def test_delete_deactivates(self, db):
        loc = location_service.create_location(db, code="DEL-LOC", name="Delete Me")
        result = location_service.delete_location(db, loc.id)
        assert result["message"] == "Location deactivated"
        refreshed = location_service.get_location(db, loc.id)
        assert refreshed.active is False

    def test_delete_main_raises_400(self, db):
        from app.models.inventory import InventoryLocation
        main = InventoryLocation(code="MAIN", name="Main Warehouse", type="warehouse", active=True)
        db.add(main)
        db.flush()
        with pytest.raises(HTTPException) as exc_info:
            location_service.delete_location(db, main.id)
        assert exc_info.value.status_code == 400

    def test_delete_nonexistent_raises_404(self, db):
        with pytest.raises(HTTPException):
            location_service.delete_location(db, 999999)
