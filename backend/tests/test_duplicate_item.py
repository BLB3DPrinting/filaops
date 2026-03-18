"""Tests for the duplicate item feature (#415)."""
import pytest
from fastapi import HTTPException

from app.services import item_service
from app.models.bom import BOM, BOMLine
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.work_center import WorkCenter


class TestDuplicateItemBasic:
    """Test item duplication without BOM."""

    def test_duplicate_basic_item(self, db):
        """Duplicate an item without a BOM — clones fields, new SKU/name."""
        source = item_service.create_item(db, data={
            "sku": "DUP-SRC-001",
            "name": "Test Source Item",
            "item_type": "finished_good",
            "procurement_type": "make",
            "standard_cost": 10.00,
            "weight_oz": 5.5,
            "category_id": None,
        })

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-CLN-001",
            new_name="Test Clone Item",
        )

        assert result["sku"] == "DUP-CLN-001"
        assert result["name"] == "Test Clone Item"
        assert result["has_bom"] is False
        assert result["bom_id"] is None

        # Verify cloned fields carried over
        clone = item_service.get_item(db, result["id"])
        assert clone.item_type == source.item_type
        assert clone.procurement_type == source.procurement_type
        assert float(clone.standard_cost) == float(source.standard_cost)
        assert float(clone.weight_oz) == float(source.weight_oz)
        assert clone.id != source.id

    def test_duplicate_sku_uppercased(self, db):
        """SKU should be uppercased automatically."""
        source = item_service.create_item(db, data={
            "sku": "DUP-CASE-SRC",
            "name": "Case Source",
        })

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="dup-case-cln",
            new_name="Case Clone",
        )
        assert result["sku"] == "DUP-CASE-CLN"

    def test_duplicate_rejects_existing_sku(self, db):
        """Duplicate should fail if new SKU already exists."""
        source = item_service.create_item(db, data={
            "sku": "DUP-EXIST-SRC",
            "name": "Existing Source",
        })
        item_service.create_item(db, data={
            "sku": "DUP-EXIST-TAKEN",
            "name": "Already Taken",
        })

        with pytest.raises(HTTPException) as exc_info:
            item_service.duplicate_item(
                db, source.id,
                new_sku="DUP-EXIST-TAKEN",
                new_name="Should Fail",
            )
        assert exc_info.value.status_code == 400

    def test_duplicate_nonexistent_source(self, db):
        """Duplicating a nonexistent item should 404."""
        with pytest.raises(HTTPException) as exc_info:
            item_service.duplicate_item(
                db, 999999,
                new_sku="DUP-GHOST",
                new_name="Ghost Clone",
            )
        assert exc_info.value.status_code == 404

    def test_duplicate_excludes_per_item_fields(self, db):
        """External IDs, purchase history, variant assets, and B2B restriction should NOT be copied."""
        source = item_service.create_item(db, data={
            "sku": "DUP-EXT-SRC",
            "name": "External ID Source",
            "legacy_sku": "OLD-SKU-123",
            "upc": "012345678901",
            "average_cost": 15.00,
            "last_cost": 12.50,
            "image_url": "https://example.com/red.jpg",
            "gcode_file_path": "/gcode/red-bear.gcode",
        })

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-EXT-CLN",
            new_name="External ID Clone",
        )

        clone = item_service.get_item(db, result["id"])
        # External IDs
        assert clone.legacy_sku is None
        assert clone.upc is None
        # Purchase history (no history for new item)
        assert clone.average_cost is None
        assert clone.last_cost is None
        # Per-variant assets (different per color)
        assert clone.image_url is None
        assert clone.gcode_file_path is None
        # B2B restriction (starts unrestricted)
        assert clone.customer_id is None


class TestDuplicateItemWithBOM:
    """Test item duplication with BOM copy and component overrides."""

    def test_duplicate_copies_bom(self, db):
        """Duplicate an item with a BOM — BOM lines should be copied."""
        source = item_service.create_item(db, data={
            "sku": "DUP-BOM-SRC",
            "name": "Source With BOM",
            "item_type": "finished_good",
            "procurement_type": "make",
        })
        component = item_service.create_item(db, data={
            "sku": "DUP-COMP-A",
            "name": "Component A",
            "item_type": "component",
            "standard_cost": 5.00,
        })

        bom = BOM(product_id=source.id, code="DUP-BOM-SRC-BOM", name="Test BOM", active=True)
        db.add(bom)
        db.flush()
        line = BOMLine(bom_id=bom.id, component_id=component.id, quantity=2, unit="EA", sequence=1)
        db.add(line)
        source.has_bom = True
        db.commit()

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-BOM-CLN",
            new_name="Clone With BOM",
        )

        assert result["has_bom"] is True
        assert result["bom_id"] is not None

        new_bom = db.query(BOM).filter(BOM.id == result["bom_id"]).first()
        assert new_bom is not None
        assert new_bom.product_id == result["id"]
        assert new_bom.active is True

        new_lines = db.query(BOMLine).filter(BOMLine.bom_id == new_bom.id).all()
        assert len(new_lines) == 1
        assert new_lines[0].component_id == component.id
        assert float(new_lines[0].quantity) == 2.0

    def test_duplicate_with_component_override(self, db):
        """Duplicate with a component swap in the BOM (color variant use case)."""
        source = item_service.create_item(db, data={
            "sku": "DUP-OVR-SRC",
            "name": "Gummy Bear - Red",
            "item_type": "finished_good",
            "procurement_type": "make",
        })
        fil_red = item_service.create_item(db, data={
            "sku": "FIL-PLA-RED",
            "name": "PLA Red",
            "item_type": "supply",
            "standard_cost": 20.00,
        })
        fil_blue = item_service.create_item(db, data={
            "sku": "FIL-PLA-BLU",
            "name": "PLA Blue",
            "item_type": "supply",
            "standard_cost": 20.00,
        })
        packaging = item_service.create_item(db, data={
            "sku": "PKG-BOX-SM",
            "name": "Small Box",
            "item_type": "supply",
            "standard_cost": 0.50,
        })

        bom = BOM(product_id=source.id, code="DUP-OVR-BOM", name="BOM", active=True)
        db.add(bom)
        db.flush()
        db.add(BOMLine(bom_id=bom.id, component_id=fil_red.id, quantity=500, unit="G", sequence=1))
        db.add(BOMLine(bom_id=bom.id, component_id=packaging.id, quantity=1, unit="EA", sequence=2))
        source.has_bom = True
        db.commit()

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-OVR-CLN",
            new_name="Gummy Bear - Blue",
            bom_line_overrides=[{
                "original_component_id": fil_red.id,
                "new_component_id": fil_blue.id,
            }],
        )

        new_lines = (
            db.query(BOMLine)
            .filter(BOMLine.bom_id == result["bom_id"])
            .order_by(BOMLine.sequence)
            .all()
        )
        assert len(new_lines) == 2
        # Filament line should be swapped to blue
        assert new_lines[0].component_id == fil_blue.id
        assert float(new_lines[0].quantity) == 500.0
        # Packaging line should be unchanged
        assert new_lines[1].component_id == packaging.id

    def test_duplicate_override_invalid_component(self, db):
        """Override with nonexistent component should fail."""
        source = item_service.create_item(db, data={
            "sku": "DUP-BADOVR-SRC",
            "name": "Bad Override Source",
            "procurement_type": "make",
        })
        component = item_service.create_item(db, data={
            "sku": "DUP-BADOVR-COMP",
            "name": "Original Component",
            "standard_cost": 5.00,
        })

        bom = BOM(product_id=source.id, code="DUP-BADOVR-BOM", name="BOM", active=True)
        db.add(bom)
        db.flush()
        db.add(BOMLine(bom_id=bom.id, component_id=component.id, quantity=1, unit="EA", sequence=1))
        source.has_bom = True
        db.commit()

        with pytest.raises(HTTPException) as exc_info:
            item_service.duplicate_item(
                db, source.id,
                new_sku="DUP-BADOVR-CLN",
                new_name="Bad Override Clone",
                bom_line_overrides=[{
                    "original_component_id": component.id,
                    "new_component_id": 999999,
                }],
            )
        assert exc_info.value.status_code == 400

    def test_duplicate_preserves_bom_line_details(self, db):
        """BOM line details (scrap_factor, consume_stage, notes) should carry over."""
        source = item_service.create_item(db, data={
            "sku": "DUP-DETAIL-SRC",
            "name": "Detail Source",
            "procurement_type": "make",
        })
        component = item_service.create_item(db, data={
            "sku": "DUP-DETAIL-COMP",
            "name": "Detail Component",
            "standard_cost": 10.00,
        })

        bom = BOM(
            product_id=source.id, code="DUP-DETAIL-BOM", name="BOM",
            active=True, assembly_time_minutes=45,
        )
        db.add(bom)
        db.flush()
        db.add(BOMLine(
            bom_id=bom.id, component_id=component.id, quantity=3, unit="EA",
            sequence=1, consume_stage="shipping", scrap_factor=5,
            is_cost_only=True, notes="Handle with care",
        ))
        source.has_bom = True
        db.commit()

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-DETAIL-CLN",
            new_name="Detail Clone",
        )

        new_bom = db.query(BOM).filter(BOM.id == result["bom_id"]).first()
        assert new_bom.assembly_time_minutes == 45

        new_line = db.query(BOMLine).filter(BOMLine.bom_id == new_bom.id).first()
        assert new_line.consume_stage == "shipping"
        assert float(new_line.scrap_factor) == 5.0
        assert new_line.is_cost_only is True
        assert new_line.notes == "Handle with care"


class TestDuplicateItemWithRouting:
    """Test item duplication with routing copy."""

    def _make_work_center(self, db, code="WC-DUP-TEST"):
        """Helper to create a work center for tests."""
        wc = db.query(WorkCenter).filter(WorkCenter.code == code).first()
        if not wc:
            wc = WorkCenter(code=code, name="Dup Test WC", center_type="production")
            db.add(wc)
            db.flush()
        return wc

    def test_duplicate_copies_routing(self, db):
        """Duplicate an item with a routing — operations should be copied."""
        source = item_service.create_item(db, data={
            "sku": "DUP-RTG-SRC",
            "name": "Source With Routing",
            "procurement_type": "make",
        })
        wc = self._make_work_center(db)

        routing = Routing(product_id=source.id, code="DUP-RTG-SRC-RTG", name="Test RTG", is_active=True)
        db.add(routing)
        db.flush()
        db.add(RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id,
            sequence=10, operation_code="PRINT", operation_name="Print Part",
            setup_time_minutes=5, run_time_minutes=30,
        ))
        db.add(RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id,
            sequence=20, operation_code="QC", operation_name="Inspect",
            setup_time_minutes=0, run_time_minutes=5,
        ))
        db.commit()

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-RTG-CLN",
            new_name="Clone With Routing",
        )

        assert result["routing_id"] is not None
        new_routing = db.query(Routing).filter(Routing.id == result["routing_id"]).first()
        assert new_routing.product_id == result["id"]
        assert new_routing.is_active is True

        new_ops = (
            db.query(RoutingOperation)
            .filter(RoutingOperation.routing_id == new_routing.id)
            .order_by(RoutingOperation.sequence)
            .all()
        )
        assert len(new_ops) == 2
        assert new_ops[0].operation_code == "PRINT"
        assert float(new_ops[0].run_time_minutes) == 30.0
        assert new_ops[1].operation_code == "QC"

    def test_duplicate_copies_routing_materials_with_override(self, db):
        """Routing operation materials should be copied and swapped like BOM lines."""
        source = item_service.create_item(db, data={
            "sku": "DUP-RTGMAT-SRC",
            "name": "Routing Material Source",
            "procurement_type": "make",
        })
        fil_red = item_service.create_item(db, data={
            "sku": "DUP-RTGM-RED",
            "name": "PLA Red (rtg test)",
            "item_type": "supply",
        })
        fil_blue = item_service.create_item(db, data={
            "sku": "DUP-RTGM-BLU",
            "name": "PLA Blue (rtg test)",
            "item_type": "supply",
        })
        wc = self._make_work_center(db, code="WC-DUP-MAT")

        # Create BOM (needed so override_map is populated)
        bom = BOM(product_id=source.id, code="DUP-RTGMAT-BOM", name="BOM", active=True)
        db.add(bom)
        db.flush()
        db.add(BOMLine(bom_id=bom.id, component_id=fil_red.id, quantity=25, unit="G", sequence=1))
        source.has_bom = True

        # Create routing with operation material referencing same component
        routing = Routing(product_id=source.id, code="DUP-RTGMAT-RTG", name="RTG", is_active=True)
        db.add(routing)
        db.flush()
        op = RoutingOperation(
            routing_id=routing.id, work_center_id=wc.id,
            sequence=10, operation_code="PRINT", operation_name="Print",
            setup_time_minutes=5, run_time_minutes=45,
        )
        db.add(op)
        db.flush()
        db.add(RoutingOperationMaterial(
            routing_operation_id=op.id, component_id=fil_red.id,
            quantity=25, unit="G", quantity_per="unit",
        ))
        db.commit()

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-RTGMAT-CLN",
            new_name="Routing Material Clone",
            bom_line_overrides=[{
                "original_component_id": fil_red.id,
                "new_component_id": fil_blue.id,
            }],
        )

        # Verify routing material was swapped to blue
        new_ops = (
            db.query(RoutingOperation)
            .filter(RoutingOperation.routing_id == result["routing_id"])
            .all()
        )
        assert len(new_ops) == 1
        new_mats = (
            db.query(RoutingOperationMaterial)
            .filter(RoutingOperationMaterial.routing_operation_id == new_ops[0].id)
            .all()
        )
        assert len(new_mats) == 1
        assert new_mats[0].component_id == fil_blue.id
        assert float(new_mats[0].quantity) == 25.0

    def test_duplicate_no_routing(self, db):
        """Item without routing should have routing_id=None in result."""
        source = item_service.create_item(db, data={
            "sku": "DUP-NORTG-SRC",
            "name": "No Routing Source",
        })

        result = item_service.duplicate_item(
            db, source.id,
            new_sku="DUP-NORTG-CLN",
            new_name="No Routing Clone",
        )

        assert result["routing_id"] is None
