"""
Additional tests for inventory_service.py and inventory_transaction_service.py
to cover gaps identified by coverage analysis.

Covers:
- inventory_service: unknown cost method fallbacks, allocations by PO,
  convert_and_generate_notes, adjustment transactions, reservation edge cases,
  consume_from_material_lots (FIFO), consume_operation_material,
  consume_shipping_materials, issue_shipped_goods, process_shipment
- inventory_transaction_service: normalize_unit, convert_quantity_to_kg_for_cost,
  list_transactions with legacy cost calculation, get_inventory_summary,
  create_transaction (transfers, adjustments, default location),
  batch_update_inventory error handling
"""
import pytest
from datetime import datetime, timezone, date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.models.bom import BOM, BOMLine
from app.models.inventory import Inventory, InventoryLocation, InventoryTransaction
from app.models.product import Product
from app.models.production_order import ProductionOrder
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.traceability import MaterialLot
from app.services import inventory_service, inventory_transaction_service


# =============================================================================
# Helpers
# =============================================================================

def _make_location(db, name="Test WH", code="TWH", loc_type="warehouse"):
    """Create an inventory location."""
    loc = InventoryLocation(name=name, code=code, type=loc_type, active=True)
    db.add(loc)
    db.flush()
    return loc


def _make_inventory(db, product_id, location_id, on_hand, allocated=Decimal("0")):
    """Create an inventory record (never set available_quantity -- it is computed)."""
    inv = Inventory(
        product_id=product_id,
        location_id=location_id,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


def _make_material_lot(db, product_id, lot_number, qty_received, qty_consumed=Decimal("0")):
    """Create a material lot for FIFO consumption testing."""
    lot = MaterialLot(
        lot_number=lot_number,
        product_id=product_id,
        quantity_received=qty_received,
        quantity_consumed=qty_consumed,
        quantity_scrapped=Decimal("0"),
        quantity_adjusted=Decimal("0"),
        status="active",
        received_date=date.today(),
    )
    db.add(lot)
    db.flush()
    return lot


def _make_production_order(db, product_id, qty_ordered=10, code=None, status="in_progress"):
    """Create a production order."""
    import uuid
    po = ProductionOrder(
        code=code or f"PO-TEST-{uuid.uuid4().hex[:8]}",
        product_id=product_id,
        quantity_ordered=qty_ordered,
        status=status,
    )
    db.add(po)
    db.flush()
    return po


def _make_bom_with_lines(db, product_id, lines, active=True):
    """Create a BOM with lines, supporting consume_stage and is_cost_only."""
    import uuid
    bom = BOM(
        product_id=product_id,
        name=f"BOM-{uuid.uuid4().hex[:8]}",
        active=active,
    )
    db.add(bom)
    db.flush()
    for i, ld in enumerate(lines):
        line = BOMLine(
            bom_id=bom.id,
            component_id=ld["component_id"],
            quantity=ld.get("quantity", Decimal("1")),
            unit=ld.get("unit", "EA"),
            sequence=(i + 1) * 10,
            consume_stage=ld.get("consume_stage", "production"),
            is_cost_only=ld.get("is_cost_only", False),
            scrap_factor=ld.get("scrap_factor", Decimal("0")),
        )
        db.add(line)
    db.flush()
    return bom


# =============================================================================
# inventory_service.get_effective_cost — unknown method fallbacks
# =============================================================================

class TestGetEffectiveCostUnknownMethod:
    """Cover lines 88-90: unknown cost_method falls back to last_cost then None."""

    def test_unknown_method_fallback_to_last_cost(self, make_product):
        product = make_product(cost_method="bogus", last_cost=Decimal("7.77"))
        result = inventory_service.get_effective_cost(product)
        assert result == Decimal("7.77")

    def test_unknown_method_no_cost_returns_none(self, make_product):
        product = make_product(cost_method="bogus")
        # No average_cost, no last_cost
        result = inventory_service.get_effective_cost(product)
        assert result is None


# =============================================================================
# inventory_service.get_allocations_by_production_order
# =============================================================================

class TestGetAllocationsByProductionOrder:
    """Cover lines 118-151: query reservation transactions grouped by PO."""

    def test_empty_product_ids_returns_empty(self, db):
        result = inventory_service.get_allocations_by_production_order(db, [])
        assert result == {}

    def test_no_reservations_returns_empty(self, db, make_product):
        product = make_product()
        result = inventory_service.get_allocations_by_production_order(db, [product.id])
        assert product.id not in result

    def test_returns_net_reservations(self, db, make_product):
        product = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))
        location = inventory_service.get_or_create_default_location(db)
        po = _make_production_order(db, product.id, qty_ordered=5)

        # Create a reservation transaction
        txn1 = InventoryTransaction(
            product_id=product.id,
            location_id=location.id,
            transaction_type="reservation",
            quantity=Decimal("100"),
            reference_type="production_order",
            reference_id=po.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(txn1)
        db.flush()

        result = inventory_service.get_allocations_by_production_order(db, [product.id])
        assert product.id in result
        assert po.id in result[product.id]
        assert result[product.id][po.id] == Decimal("100")

    def test_reservation_release_reduces_allocation(self, db, make_product):
        product = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))
        location = inventory_service.get_or_create_default_location(db)
        po = _make_production_order(db, product.id, qty_ordered=5)

        # Reserve 100
        db.add(InventoryTransaction(
            product_id=product.id, location_id=location.id,
            transaction_type="reservation", quantity=Decimal("100"),
            reference_type="production_order", reference_id=po.id,
            created_at=datetime.now(timezone.utc),
        ))
        # Release 100
        db.add(InventoryTransaction(
            product_id=product.id, location_id=location.id,
            transaction_type="reservation_release", quantity=Decimal("100"),
            reference_type="production_order", reference_id=po.id,
            created_at=datetime.now(timezone.utc),
        ))
        db.flush()

        result = inventory_service.get_allocations_by_production_order(db, [product.id])
        # Net allocation is 0, so product should not appear (only positive allocations)
        if product.id in result:
            assert po.id not in result[product.id]


# =============================================================================
# inventory_service.convert_and_generate_notes
# =============================================================================

class TestConvertAndGenerateNotes:
    """Cover lines 255-269: UOM conversion and error paths."""

    def test_same_unit_no_conversion(self, db):
        total_qty, notes = inventory_service.convert_and_generate_notes(
            db=db,
            bom_qty=Decimal("100"),
            line_unit="G",
            component_unit="G",
            component_name="Filament",
            component_sku="FIL-001",
            reference_prefix="Consumed for PO#",
            reference_code="WO-001",
        )
        assert total_qty == Decimal("100")
        assert "Consumed for PO#WO-001" in notes
        assert "Filament" in notes

    def test_incompatible_units_raises_error(self, db):
        """Units like EA and G are incompatible -- should raise UOMConversionError."""
        from app.services.uom_service import UOMConversionError
        with pytest.raises(UOMConversionError):
            inventory_service.convert_and_generate_notes(
                db=db,
                bom_qty=Decimal("5"),
                line_unit="EA",
                component_unit="G",
                component_name="Widget",
                component_sku="WDG-001",
                reference_prefix="Consumed for PO#",
                reference_code="WO-999",
            )


# =============================================================================
# inventory_service.validate_inventory_consistency — location filter
# =============================================================================

class TestValidateConsistencyLocationFilter:
    """Cover line 348: filter by location_id."""

    def test_filter_by_location_id(self, db, make_product):
        product = make_product()
        loc = _make_location(db, name="Shelf A", code="SA")
        inv = _make_inventory(db, product.id, loc.id, Decimal("10"), Decimal("20"))

        issues = inventory_service.validate_inventory_consistency(
            db, location_id=loc.id
        )
        found = [i for i in issues if i["product_id"] == product.id]
        assert len(found) == 1
        assert found[0]["issue"] == "allocated_exceeds_on_hand"


# =============================================================================
# inventory_service.create_inventory_transaction — adjustment type
# =============================================================================

class TestCreateInventoryTransactionAdjustment:
    """Cover line 481: adjustment transaction subtracts quantity from on_hand."""

    def test_adjustment_changes_on_hand(self, db, make_product):
        product = make_product()
        location = inventory_service.get_or_create_default_location(db)
        # Seed with 500 on_hand
        inventory_service.create_inventory_transaction(
            db=db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity=Decimal("500"),
            reference_type="purchase_order", reference_id=1,
        )
        db.flush()

        # Adjustment of 200 means the service subtracts 200 from current on_hand
        txn = inventory_service.create_inventory_transaction(
            db=db, product_id=product.id, location_id=location.id,
            transaction_type="adjustment", quantity=Decimal("200"),
            reference_type="adjustment", reference_id=1,
            notes="Cycle count correction",
        )
        db.flush()

        inv = db.query(Inventory).filter(
            Inventory.product_id == product.id,
            Inventory.location_id == location.id,
        ).first()
        # 500 - 200 = 300
        assert inv.on_hand_quantity == Decimal("300")
        assert txn.transaction_type == "adjustment"

    def test_scrap_decreases_on_hand(self, db, make_product):
        product = make_product()
        location = inventory_service.get_or_create_default_location(db)
        inventory_service.create_inventory_transaction(
            db=db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity=Decimal("100"),
            reference_type="purchase_order", reference_id=1,
        )
        db.flush()

        inventory_service.create_inventory_transaction(
            db=db, product_id=product.id, location_id=location.id,
            transaction_type="scrap", quantity=Decimal("25"),
            reference_type="production_order", reference_id=1,
        )
        db.flush()

        inv = db.query(Inventory).filter(
            Inventory.product_id == product.id,
            Inventory.location_id == location.id,
        ).first()
        assert inv.on_hand_quantity == Decimal("75")


# =============================================================================
# inventory_service.reserve_production_materials — edge cases
# =============================================================================

class TestReserveProductionMaterials:
    """Cover lines 541, 546, 570-572, 624."""

    def test_skips_cost_only_lines(self, db, make_product):
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        component = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))

        _make_bom_with_lines(db, fg.id, [
            {"component_id": component.id, "quantity": Decimal("100"), "unit": "G",
             "consume_stage": "production", "is_cost_only": True},
        ])

        po = _make_production_order(db, fg.id, qty_ordered=5)
        reservations = inventory_service.reserve_production_materials(db, po)
        # cost_only line should be skipped
        assert len(reservations) == 0

    def test_reservation_with_scrap_factor(self, db, make_product):
        """Scrap factor increases reserved quantity."""
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        component = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))

        _make_bom_with_lines(db, fg.id, [
            {"component_id": component.id, "quantity": Decimal("100"), "unit": "G",
             "consume_stage": "production", "scrap_factor": Decimal("10")},  # 10% scrap
        ])
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, component.id, location.id, Decimal("5000"))

        po = _make_production_order(db, fg.id, qty_ordered=5)
        reservations = inventory_service.reserve_production_materials(db, po)

        assert len(reservations) == 1
        # 100 * (1 + 0.10) * 5 = 550
        assert reservations[0]["quantity_reserved"] == 550.0

    def test_no_bom_returns_empty(self, db, make_product):
        fg = make_product(item_type="finished_good")
        po = _make_production_order(db, fg.id, qty_ordered=5)
        reservations = inventory_service.reserve_production_materials(db, po)
        assert reservations == []

    def test_successful_reservation(self, db, make_product):
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        component = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))

        _make_bom_with_lines(db, fg.id, [
            {"component_id": component.id, "quantity": Decimal("100"), "unit": "G",
             "consume_stage": "production"},
        ])
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, component.id, location.id, Decimal("1000"))

        po = _make_production_order(db, fg.id, qty_ordered=5)
        reservations = inventory_service.reserve_production_materials(db, po)

        assert len(reservations) == 1
        assert reservations[0]["product_id"] == component.id
        assert reservations[0]["quantity_reserved"] == 500.0  # 100 * 5
        assert reservations[0]["is_shortage"] is False

    def test_reservation_with_shortage(self, db, make_product):
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        component = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))

        _make_bom_with_lines(db, fg.id, [
            {"component_id": component.id, "quantity": Decimal("100"), "unit": "G",
             "consume_stage": "production"},
        ])
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, component.id, location.id, Decimal("200"))

        po = _make_production_order(db, fg.id, qty_ordered=5)
        reservations = inventory_service.reserve_production_materials(db, po)

        assert len(reservations) == 1
        assert reservations[0]["is_shortage"] is True
        assert reservations[0]["available_after"] < 0


# =============================================================================
# inventory_service.release_production_reservations
# =============================================================================

class TestReleaseProductionReservations:
    """Test releasing reservations after they are created."""

    def test_release_reduces_allocated(self, db, make_product):
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        component = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))

        _make_bom_with_lines(db, fg.id, [
            {"component_id": component.id, "quantity": Decimal("100"), "unit": "G",
             "consume_stage": "production"},
        ])
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, component.id, location.id, Decimal("1000"))

        po = _make_production_order(db, fg.id, qty_ordered=5)
        inventory_service.reserve_production_materials(db, po)
        db.flush()

        releases = inventory_service.release_production_reservations(db, po)
        assert len(releases) == 1
        assert releases[0]["quantity_released"] == 500.0
        assert releases[0]["new_allocated"] == 0.0


# =============================================================================
# inventory_service.consume_from_material_lots — FIFO
# =============================================================================

class TestConsumeFromMaterialLots:
    """Cover lines 747-803: FIFO lot consumption."""

    def test_no_lots_returns_empty(self, db, make_product):
        component = make_product(unit="G")
        po = _make_production_order(db, component.id, qty_ordered=1)

        consumptions = inventory_service.consume_from_material_lots(
            db, component.id, Decimal("100"), po.id
        )
        assert consumptions == []

    def test_single_lot_full_consumption(self, db, make_product):
        component = make_product(unit="G")
        lot = _make_material_lot(db, component.id, "LOT-001", Decimal("500"))
        po = _make_production_order(db, component.id, qty_ordered=1)

        consumptions = inventory_service.consume_from_material_lots(
            db, component.id, Decimal("200"), po.id
        )
        db.flush()

        assert len(consumptions) == 1
        assert consumptions[0].quantity_consumed == Decimal("200")
        db.refresh(lot)
        assert lot.quantity_consumed == Decimal("200")
        assert lot.status == "active"

    def test_fifo_consumes_oldest_first(self, db, make_product):
        component = make_product(unit="G")
        lot1 = _make_material_lot(db, component.id, "LOT-FIFO-1", Decimal("100"))
        lot2 = _make_material_lot(db, component.id, "LOT-FIFO-2", Decimal("200"))
        po = _make_production_order(db, component.id, qty_ordered=1)

        consumptions = inventory_service.consume_from_material_lots(
            db, component.id, Decimal("150"), po.id
        )
        db.flush()

        # Should consume all of lot1 (100) then 50 from lot2
        assert len(consumptions) == 2
        assert consumptions[0].quantity_consumed == Decimal("100")
        assert consumptions[1].quantity_consumed == Decimal("50")

        db.refresh(lot1)
        assert lot1.status == "depleted"
        db.refresh(lot2)
        assert lot2.status == "active"

    def test_partial_consumption_warning(self, db, make_product):
        """When total lot availability is less than requested, a warning is logged."""
        component = make_product(unit="G")
        _make_material_lot(db, component.id, "LOT-PARTIAL", Decimal("50"))
        po = _make_production_order(db, component.id, qty_ordered=1)

        consumptions = inventory_service.consume_from_material_lots(
            db, component.id, Decimal("200"), po.id
        )

        # Only 50 available, so only one consumption record for 50
        assert len(consumptions) == 1
        assert consumptions[0].quantity_consumed == Decimal("50")

    def test_skips_depleted_lots(self, db, make_product):
        component = make_product(unit="G")
        # Lot with all quantity already consumed
        _make_material_lot(db, component.id, "LOT-DEPLETED", Decimal("100"), qty_consumed=Decimal("100"))
        lot_fresh = _make_material_lot(db, component.id, "LOT-FRESH", Decimal("200"))
        po = _make_production_order(db, component.id, qty_ordered=1)

        consumptions = inventory_service.consume_from_material_lots(
            db, component.id, Decimal("50"), po.id
        )

        assert len(consumptions) == 1
        assert consumptions[0].material_lot_id == lot_fresh.id


# =============================================================================
# inventory_service.consume_production_materials — edge cases
# =============================================================================

class TestConsumeProductionMaterials:
    """Cover lines 964, 969: skip cost_only and missing component."""

    def test_skips_cost_only_bom_lines(self, db, make_product):
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        component = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))

        _make_bom_with_lines(db, fg.id, [
            {"component_id": component.id, "quantity": Decimal("100"), "unit": "G",
             "consume_stage": "production", "is_cost_only": True},
        ])

        po = _make_production_order(db, fg.id, qty_ordered=5)
        txns = inventory_service.consume_production_materials(
            db, po, Decimal("5"), release_reservations=False
        )
        assert len(txns) == 0

    def test_consumes_with_scrap_factor(self, db, make_product):
        """Scrap factor increases consumed quantity."""
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        component = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))

        _make_bom_with_lines(db, fg.id, [
            {"component_id": component.id, "quantity": Decimal("100"), "unit": "G",
             "consume_stage": "production", "scrap_factor": Decimal("10")},  # 10% scrap
        ])
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, component.id, location.id, Decimal("5000"))

        po = _make_production_order(db, fg.id, qty_ordered=5)
        txns = inventory_service.consume_production_materials(
            db, po, Decimal("5"), release_reservations=False
        )

        assert len(txns) == 1
        # 100 * (1 + 0.10) * 5 = 550
        assert txns[0].quantity == Decimal("550.0000")

    def test_consumes_materials_successfully(self, db, make_product):
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        component = make_product(unit="G", cost_method="average", average_cost=Decimal("0.02"))

        _make_bom_with_lines(db, fg.id, [
            {"component_id": component.id, "quantity": Decimal("100"), "unit": "G",
             "consume_stage": "production"},
        ])
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, component.id, location.id, Decimal("2000"))

        po = _make_production_order(db, fg.id, qty_ordered=5)
        txns = inventory_service.consume_production_materials(
            db, po, Decimal("5"), release_reservations=False
        )

        assert len(txns) == 1
        assert txns[0].quantity == Decimal("500")  # 100 * 5
        assert txns[0].transaction_type == "consumption"


# =============================================================================
# inventory_service.consume_shipping_materials
# =============================================================================

class TestConsumeShippingMaterials:
    """Cover lines 1182-1227: shipping BOM line consumption."""

    def test_consumes_shipping_stage_materials(self, db, make_product):
        fg = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        box = make_product(
            item_type="packaging", unit="EA", cost_method="average",
            average_cost=Decimal("1.50"),
        )

        _make_bom_with_lines(db, fg.id, [
            {"component_id": box.id, "quantity": Decimal("1"), "unit": "EA",
             "consume_stage": "shipping"},
        ])

        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, box.id, location.id, Decimal("100"))

        so = SalesOrder(
            order_number="SO-SHIP-TEST-001",
            user_id=1,
            product_id=fg.id,
            product_name="Test FG",
            quantity=3,
            material_type="PLA",
            unit_price=Decimal("10.00"),
            total_price=Decimal("30.00"),
            grand_total=Decimal("30.00"),
            status="ready_to_ship",
        )
        db.add(so)
        db.flush()

        txns = inventory_service.consume_shipping_materials(db, so)
        assert len(txns) == 1
        assert txns[0].quantity == Decimal("3")  # 1 box per unit * 3 units

    def test_no_bom_skips_product(self, db, make_product):
        fg = make_product(item_type="finished_good")
        so = SalesOrder(
            order_number="SO-NOBOM-001",
            user_id=1,
            product_id=fg.id,
            product_name="Test FG",
            quantity=1,
            material_type="PLA",
            unit_price=Decimal("10.00"),
            total_price=Decimal("10.00"),
            grand_total=Decimal("10.00"),
            status="ready_to_ship",
        )
        db.add(so)
        db.flush()

        txns = inventory_service.consume_shipping_materials(db, so)
        assert txns == []

    def test_shipping_with_order_lines(self, db, make_product):
        fg1 = make_product(item_type="finished_good", cost_method="standard", standard_cost=Decimal("5.00"))
        box = make_product(item_type="packaging", unit="EA", cost_method="average", average_cost=Decimal("1.50"))

        _make_bom_with_lines(db, fg1.id, [
            {"component_id": box.id, "quantity": Decimal("1"), "unit": "EA", "consume_stage": "shipping"},
        ])

        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, box.id, location.id, Decimal("50"))

        so = SalesOrder(
            order_number="SO-LINES-001",
            user_id=1,
            product_name="Multi-item",
            quantity=1,
            material_type="PLA",
            unit_price=Decimal("10.00"),
            total_price=Decimal("10.00"),
            grand_total=Decimal("10.00"),
            status="ready_to_ship",
        )
        db.add(so)
        db.flush()

        line = SalesOrderLine(
            sales_order_id=so.id,
            product_id=fg1.id,
            quantity=Decimal("2"),
            unit_price=Decimal("5.00"),
            total=Decimal("10.00"),
        )
        db.add(line)
        db.flush()

        txns = inventory_service.consume_shipping_materials(db, so)
        assert len(txns) == 1
        assert txns[0].quantity == Decimal("2")


# =============================================================================
# inventory_service.issue_shipped_goods
# =============================================================================

class TestIssueShippedGoods:
    """Cover line 1267: product not found skip."""

    def test_issues_goods_from_inventory(self, db, make_product):
        fg = make_product(
            item_type="finished_good", cost_method="standard",
            standard_cost=Decimal("5.00"),
        )
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, fg.id, location.id, Decimal("50"))

        so = SalesOrder(
            order_number="SO-ISSUE-001",
            user_id=1,
            product_id=fg.id,
            product_name="Test FG",
            quantity=3,
            material_type="PLA",
            unit_price=Decimal("10.00"),
            total_price=Decimal("30.00"),
            grand_total=Decimal("30.00"),
            status="ready_to_ship",
        )
        db.add(so)
        db.flush()

        txns = inventory_service.issue_shipped_goods(db, so)
        assert len(txns) == 1
        assert txns[0].transaction_type == "shipment"
        assert txns[0].quantity == Decimal("3")

    def test_issues_from_order_lines(self, db, make_product):
        """issue_shipped_goods reads from sales_order.lines when present."""
        fg = make_product(
            item_type="finished_good", cost_method="standard",
            standard_cost=Decimal("5.00"),
        )
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, fg.id, location.id, Decimal("50"))

        so = SalesOrder(
            order_number="SO-LINES-ISSUE-001",
            user_id=1,
            product_name="Multi-item Order",
            quantity=1,
            material_type="PLA",
            unit_price=Decimal("10.00"),
            total_price=Decimal("10.00"),
            grand_total=Decimal("10.00"),
            status="ready_to_ship",
        )
        db.add(so)
        db.flush()

        line = SalesOrderLine(
            sales_order_id=so.id,
            product_id=fg.id,
            quantity=Decimal("4"),
            unit_price=Decimal("5.00"),
            total=Decimal("20.00"),
        )
        db.add(line)
        db.flush()

        txns = inventory_service.issue_shipped_goods(db, so)
        assert len(txns) == 1
        assert txns[0].quantity == Decimal("4")
        assert txns[0].transaction_type == "shipment"


# =============================================================================
# inventory_service.process_shipment — MRP tracking
# =============================================================================

class TestProcessShipment:
    """Cover lines 1329, 1333: consumed product MRP tracking."""

    def test_process_shipment_returns_both_lists(self, db, make_product):
        fg = make_product(
            item_type="finished_good", cost_method="standard",
            standard_cost=Decimal("5.00"),
        )
        box = make_product(
            item_type="packaging", unit="EA", cost_method="average",
            average_cost=Decimal("1.50"),
        )

        _make_bom_with_lines(db, fg.id, [
            {"component_id": box.id, "quantity": Decimal("1"), "unit": "EA", "consume_stage": "shipping"},
        ])

        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, fg.id, location.id, Decimal("50"))
        _make_inventory(db, box.id, location.id, Decimal("50"))

        so = SalesOrder(
            order_number="SO-FULL-001",
            user_id=1,
            product_id=fg.id,
            product_name="Test FG",
            quantity=2,
            material_type="PLA",
            unit_price=Decimal("10.00"),
            total_price=Decimal("20.00"),
            grand_total=Decimal("20.00"),
            status="ready_to_ship",
        )
        db.add(so)
        db.flush()

        packaging_txns, issue_txns = inventory_service.process_shipment(db, so)
        assert len(packaging_txns) == 1  # box consumed
        assert len(issue_txns) == 1  # FG shipped

    def test_process_shipment_no_packaging(self, db, make_product):
        fg = make_product(
            item_type="finished_good", cost_method="standard",
            standard_cost=Decimal("5.00"),
        )
        location = inventory_service.get_or_create_default_location(db)
        _make_inventory(db, fg.id, location.id, Decimal("50"))

        so = SalesOrder(
            order_number="SO-NOPKG-001",
            user_id=1,
            product_id=fg.id,
            product_name="Test FG",
            quantity=1,
            material_type="PLA",
            unit_price=Decimal("10.00"),
            total_price=Decimal("10.00"),
            grand_total=Decimal("10.00"),
            status="ready_to_ship",
        )
        db.add(so)
        db.flush()

        packaging_txns, issue_txns = inventory_service.process_shipment(db, so)
        assert len(packaging_txns) == 0
        assert len(issue_txns) == 1


# =============================================================================
# inventory_transaction_service.normalize_unit
# =============================================================================

class TestNormalizeUnit:
    """Cover lines 45-57."""

    def test_none_returns_none(self):
        assert inventory_transaction_service.normalize_unit(None) is None

    def test_gram_variants(self):
        assert inventory_transaction_service.normalize_unit("gram") == "G"
        assert inventory_transaction_service.normalize_unit("grams") == "G"
        assert inventory_transaction_service.normalize_unit("g") == "G"
        assert inventory_transaction_service.normalize_unit("  G  ") == "G"

    def test_kilogram_variants(self):
        assert inventory_transaction_service.normalize_unit("kilogram") == "KG"
        assert inventory_transaction_service.normalize_unit("kilograms") == "KG"
        assert inventory_transaction_service.normalize_unit("kg") == "KG"

    def test_milligram_variants(self):
        assert inventory_transaction_service.normalize_unit("milligram") == "MG"
        assert inventory_transaction_service.normalize_unit("milligrams") == "MG"
        assert inventory_transaction_service.normalize_unit("mg") == "MG"

    def test_other_units_uppercased(self):
        assert inventory_transaction_service.normalize_unit("ea") == "EA"
        assert inventory_transaction_service.normalize_unit("  box  ") == "BOX"


# =============================================================================
# inventory_transaction_service.convert_quantity_to_kg_for_cost
# =============================================================================

class TestConvertQuantityToKgForCost:
    """Cover lines 72-114."""

    def test_kg_returns_float_directly(self, db, make_product):
        result = inventory_transaction_service.convert_quantity_to_kg_for_cost(
            db, Decimal("5.0"), "KG", 1, "TEST"
        )
        assert result == 5.0

    def test_no_unit_warns_and_returns_quantity(self, db, make_product):
        result = inventory_transaction_service.convert_quantity_to_kg_for_cost(
            db, Decimal("10"), None, 1, "TEST"
        )
        assert result == 10.0

    def test_grams_converted_to_kg(self, db, make_product):
        result = inventory_transaction_service.convert_quantity_to_kg_for_cost(
            db, Decimal("1000"), "G", 1, "TEST"
        )
        assert abs(result - 1.0) < 0.01

    def test_milligrams_converted_to_kg(self, db, make_product):
        result = inventory_transaction_service.convert_quantity_to_kg_for_cost(
            db, Decimal("1000000"), "MG", 1, "TEST"
        )
        assert abs(result - 1.0) < 0.01

    def test_incompatible_unit_raises_error(self, db):
        with pytest.raises(ValueError, match="Cannot convert"):
            inventory_transaction_service.convert_quantity_to_kg_for_cost(
                db, Decimal("10"), "FATHOMS", 1, "TEST"
            )


# =============================================================================
# inventory_transaction_service.list_transactions
# =============================================================================

class TestListTransactions:
    """Cover lines 172-182, 191: legacy cost calculation and display_unit."""

    def test_lists_transactions_with_filters(self, db, make_product):
        product = make_product(unit="EA")
        location = inventory_transaction_service._get_or_create_default_location(db)

        txn = InventoryTransaction(
            product_id=product.id,
            location_id=location.id,
            transaction_type="receipt",
            quantity=Decimal("10"),
            reference_type="purchase_order",
            reference_id=1,
            cost_per_unit=Decimal("5.00"),
            total_cost=Decimal("50.00"),
            unit="EA",
            created_at=datetime.now(timezone.utc),
        )
        db.add(txn)
        db.flush()

        results = inventory_transaction_service.list_transactions(
            db, product_id=product.id
        )
        found = [r for r in results if r["product_id"] == product.id]
        assert len(found) >= 1
        assert found[0]["unit"] == "EA"
        assert found[0]["total_cost"] == Decimal("50.00")

    def test_legacy_transaction_without_stored_total(self, db, make_product):
        """Transaction without stored total_cost falls back to calculation."""
        product = make_product(unit="EA", item_type="finished_good")
        location = inventory_transaction_service._get_or_create_default_location(db)

        txn = InventoryTransaction(
            product_id=product.id,
            location_id=location.id,
            transaction_type="receipt",
            quantity=Decimal("10"),
            reference_type="purchase_order",
            reference_id=1,
            cost_per_unit=Decimal("5.00"),
            total_cost=None,
            unit=None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(txn)
        db.flush()

        results = inventory_transaction_service.list_transactions(
            db, product_id=product.id
        )
        found = [r for r in results if r["product_id"] == product.id]
        assert len(found) >= 1
        # Non-material product: total_cost = cost_per_unit * quantity = 50
        assert found[0]["total_cost"] == Decimal("50.0")
        # No stored unit, product is not material, so display_unit from product.unit
        assert found[0]["unit"] == "EA"


# =============================================================================
# inventory_transaction_service.get_inventory_summary
# =============================================================================

class TestGetInventorySummary:
    """Cover lines 246, 290-297."""

    def test_summary_returns_items(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        location = inventory_transaction_service._get_or_create_default_location(db)
        _make_inventory(db, product.id, location.id, Decimal("50"))

        result = inventory_transaction_service.get_inventory_summary(
            db, show_zero=False, search=product.name
        )
        assert "items" in result
        assert "total" in result
        found = [i for i in result["items"] if i["product_id"] == product.id]
        assert len(found) >= 1
        assert found[0]["on_hand_quantity"] == 50.0

    def test_summary_show_zero(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        location = inventory_transaction_service._get_or_create_default_location(db)
        _make_inventory(db, product.id, location.id, Decimal("0"))

        result = inventory_transaction_service.get_inventory_summary(
            db, show_zero=True, search=product.name,
        )
        # Should include zero-quantity items
        found = [i for i in result["items"] if i["product_id"] == product.id]
        assert len(found) >= 1

    def test_summary_search_filter(self, db, make_product):
        product = make_product(unit="EA", name="UniqueSearchableName99", item_type="finished_good")
        location = inventory_transaction_service._get_or_create_default_location(db)
        _make_inventory(db, product.id, location.id, Decimal("10"))

        result = inventory_transaction_service.get_inventory_summary(
            db, search="UniqueSearchableName99"
        )
        found = [i for i in result["items"] if i["product_id"] == product.id]
        assert len(found) >= 1


# =============================================================================
# inventory_transaction_service.create_transaction — transfers and defaults
# =============================================================================

class TestCreateTransactionAdmin:
    """Cover lines 355, 385, 467-475."""

    def test_receipt_with_default_location(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        result = inventory_transaction_service.create_transaction(
            db,
            product_id=product.id,
            transaction_type="receipt",
            quantity=Decimal("10"),
            created_by="test-user",
        )
        assert result["transaction"] is not None
        assert result["location"] is not None

    def test_transfer_success(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        loc_from = _make_location(db, name="From WH", code="FROM")
        loc_to = _make_location(db, name="To WH", code="TO")
        _make_inventory(db, product.id, loc_from.id, Decimal("50"))

        result = inventory_transaction_service.create_transaction(
            db,
            product_id=product.id,
            transaction_type="transfer",
            quantity=Decimal("20"),
            created_by="test-user",
            location_id=loc_from.id,
            to_location_id=loc_to.id,
        )
        assert result["original_type"] == "transfer"
        assert result["to_location"] is not None

    def test_transfer_insufficient_inventory(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        loc_from = _make_location(db, name="Empty WH", code="EMPTY")
        loc_to = _make_location(db, name="Dest WH", code="DEST")
        _make_inventory(db, product.id, loc_from.id, Decimal("5"))

        with pytest.raises(ValueError, match="Insufficient inventory"):
            inventory_transaction_service.create_transaction(
                db,
                product_id=product.id,
                transaction_type="transfer",
                quantity=Decimal("20"),
                created_by="test-user",
                location_id=loc_from.id,
                to_location_id=loc_to.id,
            )

    def test_transfer_same_location_error(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        loc = _make_location(db, name="Same WH", code="SAME")
        _make_inventory(db, product.id, loc.id, Decimal("50"))

        with pytest.raises(ValueError, match="Cannot transfer to the same location"):
            inventory_transaction_service.create_transaction(
                db,
                product_id=product.id,
                transaction_type="transfer",
                quantity=Decimal("10"),
                created_by="test-user",
                location_id=loc.id,
                to_location_id=loc.id,
            )

    def test_invalid_transaction_type(self, db, make_product):
        product = make_product(unit="EA")
        with pytest.raises(ValueError, match="Invalid transaction_type"):
            inventory_transaction_service.create_transaction(
                db,
                product_id=product.id,
                transaction_type="magic",
                quantity=Decimal("10"),
                created_by="test-user",
            )

    def test_product_not_found(self, db):
        with pytest.raises(ValueError, match="not found"):
            inventory_transaction_service.create_transaction(
                db,
                product_id=999999,
                transaction_type="receipt",
                quantity=Decimal("10"),
                created_by="test-user",
            )

    def test_issue_insufficient_inventory(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        loc = _make_location(db, name="Low WH", code="LOW")
        _make_inventory(db, product.id, loc.id, Decimal("3"))

        with pytest.raises(ValueError, match="Insufficient inventory"):
            inventory_transaction_service.create_transaction(
                db,
                product_id=product.id,
                transaction_type="issue",
                quantity=Decimal("10"),
                created_by="test-user",
                location_id=loc.id,
            )

    def test_adjustment_sets_on_hand(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        loc = _make_location(db, name="Adjust WH", code="ADJ")
        _make_inventory(db, product.id, loc.id, Decimal("100"))

        result = inventory_transaction_service.create_transaction(
            db,
            product_id=product.id,
            transaction_type="adjustment",
            quantity=Decimal("75"),
            created_by="test-user",
            location_id=loc.id,
            notes="Cycle count",
        )

        inv = db.query(Inventory).filter(
            Inventory.product_id == product.id,
            Inventory.location_id == loc.id,
        ).first()
        # Admin service adjustment sets on_hand to quantity directly
        assert float(inv.on_hand_quantity) == 75.0

    def test_transfer_missing_to_location(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        loc = _make_location(db, name="Src WH", code="SRC")
        _make_inventory(db, product.id, loc.id, Decimal("50"))

        with pytest.raises(ValueError, match="to_location_id required"):
            inventory_transaction_service.create_transaction(
                db,
                product_id=product.id,
                transaction_type="transfer",
                quantity=Decimal("10"),
                created_by="test-user",
                location_id=loc.id,
            )

    def test_transfer_to_nonexistent_location(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        loc = _make_location(db, name="Real WH", code="REAL")
        _make_inventory(db, product.id, loc.id, Decimal("50"))

        with pytest.raises(ValueError, match="To location .* not found"):
            inventory_transaction_service.create_transaction(
                db,
                product_id=product.id,
                transaction_type="transfer",
                quantity=Decimal("10"),
                created_by="test-user",
                location_id=loc.id,
                to_location_id=999999,
            )


# =============================================================================
# inventory_transaction_service.list_locations
# =============================================================================

class TestListLocations:
    """Test listing active locations."""

    def test_returns_active_locations(self, db):
        loc = _make_location(db, name="Active Loc", code="ACT")
        results = inventory_transaction_service.list_locations(db)
        found = [r for r in results if r["id"] == loc.id]
        assert len(found) == 1
        assert found[0]["name"] == "Active Loc"


# =============================================================================
# inventory_transaction_service.batch_update_inventory — error paths
# =============================================================================

class TestBatchUpdateInventory:
    """Cover lines 516-518, 595-624: default location and error handling."""

    def test_product_not_found_in_batch(self, db):
        result = inventory_transaction_service.batch_update_inventory(
            db,
            items=[
                {"product_id": 999999, "counted_quantity": Decimal("10"), "reason": "test"},
            ],
            admin_id=1,
        )
        assert result["failed"] == 1
        assert result["successful"] == 0
        assert result["results"][0]["success"] is False
        assert "not found" in result["results"][0]["error"]

    def test_zero_variance_succeeds_no_transaction(self, db, make_product):
        product = make_product(unit="EA", item_type="finished_good")
        loc = inventory_transaction_service._get_or_create_default_location(db)
        _make_inventory(db, product.id, loc.id, Decimal("50"))

        result = inventory_transaction_service.batch_update_inventory(
            db,
            items=[
                {"product_id": product.id, "counted_quantity": Decimal("50"), "reason": "no change"},
            ],
            admin_id=1,
        )
        assert result["successful"] == 1
        assert result["results"][0]["transaction_id"] is None
        assert result["results"][0]["variance"] == Decimal("0")

    def test_nonexistent_location_raises(self, db, make_product):
        product = make_product(unit="EA")
        with pytest.raises(ValueError, match="not found"):
            inventory_transaction_service.batch_update_inventory(
                db,
                items=[
                    {"product_id": product.id, "counted_quantity": Decimal("10"), "reason": "test"},
                ],
                location_id=999999,
                admin_id=1,
            )
