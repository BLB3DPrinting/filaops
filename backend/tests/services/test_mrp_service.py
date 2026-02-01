"""
Unit tests for MRP (Material Requirements Planning) Service

Tests verify:
1. UOM conversion (same unit, known conversions, unknown/incompatible units)
2. BOM explosion (single-level, multi-level, circular reference, scrap factor, UOM)
3. Net requirements calculation (netting formula, clamping, safety stock)
4. Planned order generation (purchase vs production, min order qty, date logic)
5. Firm and release lifecycle (status transitions, validation errors)
6. Full MRP run (end-to-end with MRPRun record management)

Run with:
    cd backend
    pytest tests/services/test_mrp_service.py -v

Run with coverage:
    pytest tests/services/test_mrp_service.py -v --cov=app/services/mrp
"""
import uuid
import pytest
from decimal import Decimal
from datetime import date, timedelta, datetime, timezone

from app.services.mrp import MRPService, convert_uom, ComponentRequirement, NetRequirement
from app.models.mrp import MRPRun, PlannedOrder
from app.models.bom import BOM, BOMLine
from app.models.inventory import Inventory
from app.models.production_order import ProductionOrder
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine


# =============================================================================
# convert_uom — standalone UOM conversion function
# =============================================================================

class TestConvertUom:
    """Tests for the standalone convert_uom function."""

    def test_same_unit_returns_unchanged(self):
        """Same from/to unit returns the quantity as-is."""
        result = convert_uom(Decimal("500"), "G", "G")
        assert result == Decimal("500")

    def test_same_unit_case_insensitive(self):
        """Unit comparison is case-insensitive after uppercasing."""
        result = convert_uom(Decimal("10"), "kg", "KG")
        assert result == Decimal("10")

    def test_grams_to_kilograms(self):
        """1000 G should convert to 1 KG."""
        result = convert_uom(Decimal("1000"), "G", "KG")
        assert result == Decimal("1")

    def test_kilograms_to_grams(self):
        """1 KG should convert to 1000 G."""
        result = convert_uom(Decimal("1"), "KG", "G")
        assert result == Decimal("1000")

    def test_fractional_grams_to_kilograms(self):
        """50 G should convert to 0.05 KG."""
        result = convert_uom(Decimal("50"), "G", "KG")
        assert result == Decimal("0.05")

    def test_pounds_to_kilograms(self):
        """LB to KG uses correct conversion factor."""
        result = convert_uom(Decimal("1"), "LB", "KG")
        assert result == Decimal("0.453592")

    def test_millimeters_to_meters(self):
        """1000 MM should convert to 1 M."""
        result = convert_uom(Decimal("1000"), "MM", "M")
        assert result == Decimal("1")

    def test_unknown_from_unit_returns_unchanged(self):
        """Unknown source unit returns original quantity."""
        result = convert_uom(Decimal("10"), "UNKNOWN", "KG")
        assert result == Decimal("10")

    def test_unknown_to_unit_returns_unchanged(self):
        """Unknown target unit returns original quantity."""
        result = convert_uom(Decimal("10"), "KG", "ZORK")
        assert result == Decimal("10")

    def test_incompatible_bases_returns_unchanged(self):
        """Units with different bases (mass vs length) return quantity as-is."""
        result = convert_uom(Decimal("10"), "KG", "M")
        assert result == Decimal("10")

    def test_ea_to_kg_incompatible(self):
        """EA and KG have different bases; returns unchanged."""
        result = convert_uom(Decimal("5"), "EA", "KG")
        assert result == Decimal("5")

    def test_none_units_default_to_ea(self):
        """None units are treated as EA."""
        result = convert_uom(Decimal("7"), None, None)
        assert result == Decimal("7")

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped from units."""
        result = convert_uom(Decimal("1000"), " G ", " KG ")
        assert result == Decimal("1")

    def test_zero_quantity(self):
        """Zero quantity converts correctly."""
        result = convert_uom(Decimal("0"), "G", "KG")
        assert result == Decimal("0")


# =============================================================================
# BOM Explosion
# =============================================================================

class TestExplodeBom:
    """Tests for MRPService.explode_bom."""

    def test_single_level_bom(self, db, make_product, make_bom):
        """Single-level BOM returns one requirement per component."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(
            item_type="supply", unit="G", is_raw_material=True,
        )
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        svc = MRPService(db)
        reqs = svc.explode_bom(
            product_id=fg.id,
            quantity=Decimal("5"),
            source_demand_type="production_order",
            source_demand_id=1,
            due_date=date.today(),
        )

        assert len(reqs) == 1
        req = reqs[0]
        assert req.product_id == raw.id
        # 5 units * 100 G per unit = 500 G
        assert req.gross_quantity == Decimal("500")
        assert req.bom_level == 0
        assert req.source_demand_type == "production_order"

    def test_no_bom_returns_empty(self, db, make_product):
        """Product with no BOM returns empty list."""
        product = make_product(item_type="supply", unit="EA")

        svc = MRPService(db)
        reqs = svc.explode_bom(
            product_id=product.id,
            quantity=Decimal("10"),
        )

        assert reqs == []

    def test_multi_level_bom(self, db, make_product, make_bom):
        """Multi-level BOM recurses into sub-assemblies."""
        # Top-level finished good
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        # Sub-assembly (has its own BOM)
        sub = make_product(
            item_type="component", procurement_type="make",
            has_bom=True, unit="EA",
        )
        # Raw material used by sub-assembly
        raw = make_product(
            item_type="supply", unit="G", is_raw_material=True,
        )

        # FG BOM: 1 FG needs 2 sub-assemblies
        make_bom(product_id=fg.id, lines=[
            {"component_id": sub.id, "quantity": Decimal("2"), "unit": "EA"},
        ])
        # Sub-assembly BOM: 1 sub needs 50 G raw material
        make_bom(product_id=sub.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("50"), "unit": "G"},
        ])

        svc = MRPService(db)
        reqs = svc.explode_bom(
            product_id=fg.id,
            quantity=Decimal("3"),
        )

        # Level 0: sub-assembly requirement = 3 * 2 = 6 EA
        # Level 1: raw material requirement = 6 * 50 = 300 G
        assert len(reqs) == 2

        sub_req = next(r for r in reqs if r.product_id == sub.id)
        raw_req = next(r for r in reqs if r.product_id == raw.id)

        assert sub_req.gross_quantity == Decimal("6")
        assert sub_req.bom_level == 0

        assert raw_req.gross_quantity == Decimal("300")
        assert raw_req.bom_level == 1

    def test_circular_reference_detection(self, db, make_product, make_bom):
        """Circular BOM references are detected and return empty for the cycle."""
        product_a = make_product(
            item_type="component", procurement_type="make",
            has_bom=True, unit="EA",
        )
        product_b = make_product(
            item_type="component", procurement_type="make",
            has_bom=True, unit="EA",
        )

        # A uses B, B uses A (circular)
        make_bom(product_id=product_a.id, lines=[
            {"component_id": product_b.id, "quantity": Decimal("1"), "unit": "EA"},
        ])
        make_bom(product_id=product_b.id, lines=[
            {"component_id": product_a.id, "quantity": Decimal("1"), "unit": "EA"},
        ])

        svc = MRPService(db)
        reqs = svc.explode_bom(
            product_id=product_a.id,
            quantity=Decimal("1"),
        )

        # Should get B at level 0 (direct component of A)
        # A appears at level 1 (component of B) but recursion stops there
        product_ids = [r.product_id for r in reqs]
        assert product_b.id in product_ids
        # A appears as B's component before the cycle is detected at the next level
        assert product_a.id in product_ids
        # But recursion does not continue beyond the cycle — no deeper levels
        assert len(reqs) == 2

    def test_scrap_factor_applied(self, db, make_product, make_bom):
        """Scrap factor increases the gross quantity requirement."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(
            item_type="supply", unit="G", is_raw_material=True,
        )

        # BOM line with 10% scrap factor
        bom = BOM(
            product_id=fg.id, name="BOM-scrap-test", active=True,
        )
        db.add(bom)
        db.flush()
        line = BOMLine(
            bom_id=bom.id, component_id=raw.id,
            quantity=Decimal("100"), unit="G",
            scrap_factor=Decimal("10"),  # 10%
            sequence=10,
        )
        db.add(line)
        db.flush()

        svc = MRPService(db)
        reqs = svc.explode_bom(
            product_id=fg.id,
            quantity=Decimal("2"),
        )

        assert len(reqs) == 1
        # adjusted_qty = 2 * 100 * (1 + 10/100) = 2 * 100 * 1.1 = 220
        assert reqs[0].gross_quantity == Decimal("220")
        assert reqs[0].scrap_factor == Decimal("10")

    def test_uom_conversion_in_explosion(self, db, make_product, make_bom):
        """BOM line unit is converted to component base unit during explosion."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        # Component tracked in KG
        component = make_product(
            item_type="supply", unit="KG", is_raw_material=True,
        )

        # BOM specifies 500 G, but component tracks in KG
        make_bom(product_id=fg.id, lines=[
            {"component_id": component.id, "quantity": Decimal("500"), "unit": "G"},
        ])

        svc = MRPService(db)
        reqs = svc.explode_bom(
            product_id=fg.id,
            quantity=Decimal("4"),
        )

        assert len(reqs) == 1
        # 500 G -> 0.5 KG, then 4 * 0.5 = 2.0 KG
        assert reqs[0].gross_quantity == Decimal("2.0")

    def test_due_date_propagated(self, db, make_product, make_bom):
        """Due date is passed through to component requirements."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(item_type="supply", unit="EA")
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("1"), "unit": "EA"},
        ])

        target_date = date.today() + timedelta(days=30)
        svc = MRPService(db)
        reqs = svc.explode_bom(
            product_id=fg.id,
            quantity=Decimal("1"),
            due_date=target_date,
        )

        assert reqs[0].due_date == target_date


# =============================================================================
# Net Requirements Calculation
# =============================================================================

class TestCalculateNetRequirements:
    """Tests for MRPService.calculate_net_requirements."""

    def _make_component_req(self, product):
        """Helper to build a ComponentRequirement from a product."""
        return ComponentRequirement(
            product_id=product.id,
            product_sku=product.sku,
            product_name=product.name,
            bom_level=0,
            gross_quantity=Decimal("100"),
        )

    def test_full_shortage_no_inventory(self, db, make_product):
        """No inventory means full shortage equals gross requirement."""
        product = make_product(item_type="supply", unit="EA")
        req = self._make_component_req(product)

        svc = MRPService(db)
        net_reqs = svc.calculate_net_requirements([req])

        assert len(net_reqs) == 1
        nr = net_reqs[0]
        assert nr.gross_quantity == Decimal("100")
        assert nr.on_hand_quantity == Decimal("0")
        assert nr.incoming_quantity == Decimal("0")
        assert nr.net_shortage == Decimal("100")

    def test_on_hand_reduces_shortage(self, db, make_product):
        """On-hand inventory reduces the net shortage."""
        product = make_product(item_type="supply", unit="EA")

        # Add inventory
        inv = Inventory(
            product_id=product.id, location_id=1,
            on_hand_quantity=Decimal("40"), allocated_quantity=Decimal("0"),
        )
        db.add(inv)
        db.flush()

        req = self._make_component_req(product)
        svc = MRPService(db)
        net_reqs = svc.calculate_net_requirements([req])

        nr = net_reqs[0]
        assert nr.on_hand_quantity == Decimal("40")
        # Net = 100 - 40 - 0 + 0 = 60
        assert nr.net_shortage == Decimal("60")

    def test_incoming_supply_reduces_shortage(self, db, make_product, make_vendor, make_purchase_order):
        """Open purchase orders reduce the net shortage."""
        product = make_product(item_type="supply", unit="EA")
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")

        # PO line with 30 ordered, 0 received
        po_line = PurchaseOrderLine(
            purchase_order_id=po.id, product_id=product.id,
            line_number=1,
            quantity_ordered=Decimal("30"), quantity_received=Decimal("0"),
            unit_cost=Decimal("1"), line_total=Decimal("30"),
        )
        db.add(po_line)
        db.flush()

        req = self._make_component_req(product)
        svc = MRPService(db)
        net_reqs = svc.calculate_net_requirements([req])

        nr = net_reqs[0]
        assert nr.incoming_quantity == Decimal("30")
        # Net = 100 - 0 - 30 + 0 = 70
        assert nr.net_shortage == Decimal("70")

    def test_safety_stock_increases_shortage(self, db, make_product):
        """Safety stock is added to the shortage calculation."""
        product = make_product(
            item_type="supply", unit="EA", safety_stock=Decimal("25"),
        )

        # Add inventory to partially cover
        inv = Inventory(
            product_id=product.id, location_id=1,
            on_hand_quantity=Decimal("80"), allocated_quantity=Decimal("0"),
        )
        db.add(inv)
        db.flush()

        req = self._make_component_req(product)
        svc = MRPService(db)
        net_reqs = svc.calculate_net_requirements([req])

        nr = net_reqs[0]
        assert nr.safety_stock == Decimal("25")
        # Net = 100 - 80 - 0 + 25 = 45
        assert nr.net_shortage == Decimal("45")

    def test_negative_shortage_clamped_to_zero(self, db, make_product):
        """Excess inventory clamps shortage to zero (no negative shortage)."""
        product = make_product(item_type="supply", unit="EA")

        # More inventory than needed
        inv = Inventory(
            product_id=product.id, location_id=1,
            on_hand_quantity=Decimal("200"), allocated_quantity=Decimal("0"),
        )
        db.add(inv)
        db.flush()

        req = self._make_component_req(product)
        svc = MRPService(db)
        net_reqs = svc.calculate_net_requirements([req])

        nr = net_reqs[0]
        assert nr.net_shortage == Decimal("0")

    def test_combined_on_hand_and_incoming(self, db, make_product, make_vendor, make_purchase_order):
        """Both on-hand and incoming supply reduce the shortage together."""
        product = make_product(item_type="supply", unit="EA")
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="ordered")

        # 40 on hand
        inv = Inventory(
            product_id=product.id, location_id=1,
            on_hand_quantity=Decimal("40"), allocated_quantity=Decimal("0"),
        )
        db.add(inv)

        # 30 incoming
        po_line = PurchaseOrderLine(
            purchase_order_id=po.id, product_id=product.id,
            line_number=1,
            quantity_ordered=Decimal("30"), quantity_received=Decimal("0"),
            unit_cost=Decimal("1"), line_total=Decimal("30"),
        )
        db.add(po_line)
        db.flush()

        req = self._make_component_req(product)
        svc = MRPService(db)
        net_reqs = svc.calculate_net_requirements([req])

        nr = net_reqs[0]
        # Net = 100 - 40 - 30 + 0 = 30
        assert nr.net_shortage == Decimal("30")

    def test_empty_requirements_returns_empty(self, db):
        """Empty input list returns empty output."""
        svc = MRPService(db)
        assert svc.calculate_net_requirements([]) == []


# =============================================================================
# Planned Order Generation
# =============================================================================

class TestGeneratePlannedOrders:
    """Tests for MRPService.generate_planned_orders."""

    def _make_shortage(self, product, shortage_qty, has_bom=False, min_order_qty=None):
        """Helper to build a NetRequirement representing a shortage."""
        return NetRequirement(
            product_id=product.id,
            product_sku=product.sku,
            product_name=product.name,
            gross_quantity=shortage_qty,
            on_hand_quantity=Decimal("0"),
            allocated_quantity=Decimal("0"),
            available_quantity=Decimal("0"),
            incoming_quantity=Decimal("0"),
            safety_stock=Decimal("0"),
            net_shortage=shortage_qty,
            lead_time_days=7,
            has_bom=has_bom,
            min_order_qty=min_order_qty,
        )

    def test_purchase_order_for_raw_material(self, db, make_product):
        """Raw material without BOM generates a purchase planned order."""
        raw = make_product(
            item_type="supply", unit="G", is_raw_material=True,
        )

        # Create MRP run record
        mrp_run = MRPRun(
            run_date=datetime.now(timezone.utc),
            planning_horizon_days=30, status="running",
        )
        db.add(mrp_run)
        db.flush()

        shortage = self._make_shortage(raw, Decimal("500"))
        svc = MRPService(db)
        orders = svc.generate_planned_orders([shortage], int(mrp_run.id), user_id=1)

        assert len(orders) == 1
        order = orders[0]
        assert order.order_type == "purchase"
        assert order.product_id == raw.id
        assert order.quantity == Decimal("500")
        assert order.status == "planned"
        assert order.mrp_run_id == mrp_run.id

    def test_production_order_for_item_with_bom(self, db, make_product):
        """Item with has_bom=True generates a production planned order."""
        sub_assy = make_product(
            item_type="component", unit="EA",
            procurement_type="make", has_bom=True,
        )

        mrp_run = MRPRun(
            run_date=datetime.now(timezone.utc),
            planning_horizon_days=30, status="running",
        )
        db.add(mrp_run)
        db.flush()

        shortage = self._make_shortage(sub_assy, Decimal("10"), has_bom=True)
        svc = MRPService(db)
        orders = svc.generate_planned_orders([shortage], int(mrp_run.id))

        assert len(orders) == 1
        assert orders[0].order_type == "production"

    def test_min_order_qty_applied(self, db, make_product):
        """Minimum order quantity is enforced when shortage is smaller."""
        raw = make_product(
            item_type="supply", unit="EA", min_order_qty=Decimal("100"),
        )

        mrp_run = MRPRun(
            run_date=datetime.now(timezone.utc),
            planning_horizon_days=30, status="running",
        )
        db.add(mrp_run)
        db.flush()

        # Shortage is only 25, but min order qty is 100
        shortage = self._make_shortage(
            raw, Decimal("25"), min_order_qty=Decimal("100"),
        )
        svc = MRPService(db)
        orders = svc.generate_planned_orders([shortage], int(mrp_run.id))

        assert orders[0].quantity == Decimal("100")

    def test_start_date_not_in_past(self, db, make_product):
        """Planned order start dates are never before today."""
        raw = make_product(item_type="supply", unit="EA")

        mrp_run = MRPRun(
            run_date=datetime.now(timezone.utc),
            planning_horizon_days=30, status="running",
        )
        db.add(mrp_run)
        db.flush()

        shortage = self._make_shortage(raw, Decimal("50"))
        svc = MRPService(db)
        orders = svc.generate_planned_orders([shortage], int(mrp_run.id))

        assert orders[0].start_date >= date.today()

    def test_zero_shortage_skipped(self, db, make_product):
        """Zero-shortage items do not produce planned orders."""
        raw = make_product(item_type="supply", unit="EA")

        mrp_run = MRPRun(
            run_date=datetime.now(timezone.utc),
            planning_horizon_days=30, status="running",
        )
        db.add(mrp_run)
        db.flush()

        shortage = self._make_shortage(raw, Decimal("0"))
        svc = MRPService(db)
        orders = svc.generate_planned_orders([shortage], int(mrp_run.id))

        assert orders == []


# =============================================================================
# Firm Planned Order
# =============================================================================

class TestFirmPlannedOrder:
    """Tests for MRPService.firm_planned_order."""

    def _create_planned_order(self, db, product, status="planned"):
        """Helper to insert a PlannedOrder."""
        order = PlannedOrder(
            order_type="purchase",
            product_id=product.id,
            quantity=Decimal("100"),
            due_date=date.today() + timedelta(days=14),
            start_date=date.today(),
            status=status,
            source_demand_type="mrp_calculation",
            created_at=datetime.now(timezone.utc),
        )
        db.add(order)
        db.flush()
        return order

    def test_firm_changes_status(self, db, make_product):
        """Firming a planned order sets status to 'firmed'."""
        product = make_product(item_type="supply", unit="EA")
        order = self._create_planned_order(db, product)

        svc = MRPService(db)
        firmed = svc.firm_planned_order(order.id, user_id=1)

        assert firmed.status == "firmed"
        assert firmed.firmed_at is not None

    def test_firm_with_notes(self, db, make_product):
        """Firming with notes appends to the order notes."""
        product = make_product(item_type="supply", unit="EA")
        order = self._create_planned_order(db, product)

        svc = MRPService(db)
        firmed = svc.firm_planned_order(order.id, notes="Approved by manager")

        assert "Approved by manager" in firmed.notes

    def test_firm_non_planned_raises(self, db, make_product):
        """Firming an already-firmed order raises ValueError."""
        product = make_product(item_type="supply", unit="EA")
        order = self._create_planned_order(db, product, status="firmed")

        svc = MRPService(db)
        with pytest.raises(ValueError, match="planned"):
            svc.firm_planned_order(order.id)

    def test_firm_nonexistent_raises(self, db):
        """Firming a non-existent order raises ValueError."""
        svc = MRPService(db)
        with pytest.raises(ValueError, match="not found"):
            svc.firm_planned_order(999999)


# =============================================================================
# Release Planned Order
# =============================================================================

class TestReleasePlannedOrder:
    """Tests for MRPService.release_planned_order."""

    def _create_planned_order(self, db, product, order_type="purchase", status="planned"):
        """Helper to insert a PlannedOrder."""
        order = PlannedOrder(
            order_type=order_type,
            product_id=product.id,
            quantity=Decimal("50"),
            due_date=date.today() + timedelta(days=14),
            start_date=date.today(),
            status=status,
            source_demand_type="mrp_calculation",
            created_at=datetime.now(timezone.utc),
        )
        db.add(order)
        db.flush()
        return order

    def _cleanup_purchase_orders(self, db):
        """Remove leftover POs from previous test runs to avoid po_number collision."""
        from sqlalchemy import text
        year = datetime.now(timezone.utc).year
        pattern = f"PO-{year}-%"
        # Null out FKs referencing these POs, then delete lines, then POs
        db.execute(text(
            "UPDATE material_lots SET purchase_order_id = NULL "
            "WHERE purchase_order_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :pattern)"
        ), {"pattern": pattern})
        db.execute(text(
            "UPDATE planned_orders SET converted_to_po_id = NULL "
            "WHERE converted_to_po_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :pattern)"
        ), {"pattern": pattern})
        db.execute(text(
            "DELETE FROM purchase_order_lines WHERE purchase_order_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :pattern)"
        ), {"pattern": pattern})
        db.execute(text(
            "DELETE FROM purchase_order_documents WHERE purchase_order_id IN "
            "(SELECT id FROM purchase_orders WHERE po_number LIKE :pattern)"
        ), {"pattern": pattern})
        db.execute(text(
            "DELETE FROM purchase_orders WHERE po_number LIKE :pattern"
        ), {"pattern": pattern})
        db.commit()

    def test_release_purchase_creates_po(self, db, make_product, make_vendor):
        """Releasing a purchase planned order creates a real PurchaseOrder."""
        self._cleanup_purchase_orders(db)

        product = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("2.50"),
        )
        vendor = make_vendor()
        order = self._create_planned_order(db, product, order_type="purchase")

        svc = MRPService(db)
        released, created_id = svc.release_planned_order(
            order.id, vendor_id=vendor.id, user_id=1,
        )

        assert released.status == "released"
        assert released.released_at is not None
        assert created_id is not None

        # Verify the actual PO was created
        po = db.query(PurchaseOrder).get(created_id)
        assert po is not None
        assert po.vendor_id == vendor.id
        assert po.status == "draft"

        # Verify PO line
        po_line = db.query(PurchaseOrderLine).filter(
            PurchaseOrderLine.purchase_order_id == po.id,
        ).first()
        assert po_line is not None
        assert po_line.product_id == product.id
        assert po_line.quantity_ordered == Decimal("50")

    def test_release_production_creates_mo(self, db, make_product, make_bom):
        """Releasing a production planned order creates a ProductionOrder."""
        fg = make_product(
            item_type="finished_good", unit="EA",
            procurement_type="make", has_bom=True,
            standard_cost=Decimal("5.00"),
        )
        raw = make_product(item_type="supply", unit="G")
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("100"), "unit": "G"},
        ])

        order = self._create_planned_order(db, fg, order_type="production")

        svc = MRPService(db)
        released, created_id = svc.release_planned_order(order.id, user_id=1)

        assert released.status == "released"
        assert created_id is not None

        mo = db.query(ProductionOrder).get(created_id)
        assert mo is not None
        assert mo.product_id == fg.id
        assert mo.quantity_ordered == Decimal("50")
        assert mo.status == "draft"
        assert mo.source == "mrp_planned"

    def test_release_purchase_without_vendor_raises(self, db, make_product):
        """Releasing a purchase order without vendor_id raises ValueError."""
        product = make_product(item_type="supply", unit="EA")
        order = self._create_planned_order(db, product, order_type="purchase")

        svc = MRPService(db)
        with pytest.raises(ValueError, match="vendor_id"):
            svc.release_planned_order(order.id)

    def test_release_already_released_raises(self, db, make_product):
        """Releasing an already-released order raises ValueError."""
        product = make_product(item_type="supply", unit="EA")
        order = self._create_planned_order(db, product, status="released")

        svc = MRPService(db)
        with pytest.raises(ValueError, match="status"):
            svc.release_planned_order(order.id, vendor_id=1)

    def test_release_nonexistent_raises(self, db):
        """Releasing a non-existent order raises ValueError."""
        svc = MRPService(db)
        with pytest.raises(ValueError, match="not found"):
            svc.release_planned_order(999999, vendor_id=1)

    def test_release_firmed_order_succeeds(self, db, make_product, make_vendor):
        """Firmed orders can also be released (not just planned)."""
        self._cleanup_purchase_orders(db)

        product = make_product(
            item_type="supply", unit="EA",
            standard_cost=Decimal("1.00"),
        )
        vendor = make_vendor()
        order = self._create_planned_order(db, product, status="firmed")

        svc = MRPService(db)
        released, created_id = svc.release_planned_order(
            order.id, vendor_id=vendor.id,
        )

        assert released.status == "released"
        assert created_id is not None


# =============================================================================
# Full MRP Run (end-to-end)
# =============================================================================

class TestRunMrp:
    """Tests for MRPService.run_mrp (end-to-end)."""

    def test_creates_mrp_run_record(self, db, make_product):
        """Running MRP creates an MRPRun record with completed status."""
        # No demand, so it should complete quickly with zero results
        svc = MRPService(db)
        result = svc.run_mrp(
            planning_horizon_days=30,
            user_id=1,
        )

        mrp_run = db.query(MRPRun).get(result.run_id)
        assert mrp_run is not None
        assert mrp_run.status == "completed"
        assert mrp_run.planning_horizon_days == 30

    def test_processes_production_orders(self, db, make_product, make_bom):
        """MRP processes production orders within horizon and generates planned orders."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(
            item_type="supply", unit="G", is_raw_material=True,
        )
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("200"), "unit": "G"},
        ])

        # Create a production order within planning horizon
        prod_order = ProductionOrder(
            code=f"PO-TEST-MRP-{uuid.uuid4().hex[:8]}",
            product_id=fg.id,
            quantity_ordered=Decimal("10"),
            quantity_completed=Decimal("0"),
            quantity_scrapped=Decimal("0"),
            status="released",
            source="manual",
            due_date=date.today() + timedelta(days=7),
        )
        db.add(prod_order)
        db.flush()

        svc = MRPService(db)
        result = svc.run_mrp(
            planning_horizon_days=30,
            user_id=1,
        )

        assert result.orders_processed >= 1
        assert result.components_analyzed >= 1
        # No inventory means full shortage
        assert result.shortages_found >= 1
        assert result.planned_orders_created >= 1

        # Verify planned order was created for the raw material
        planned = db.query(PlannedOrder).filter(
            PlannedOrder.mrp_run_id == result.run_id,
            PlannedOrder.product_id == raw.id,
        ).first()
        assert planned is not None
        assert planned.order_type == "purchase"
        # 10 * 200 G = 2000 G
        assert planned.quantity == Decimal("2000")

    def test_regenerate_deletes_unfirmed(self, db, make_product):
        """With regenerate_planned=True, existing unfirmed planned orders are deleted."""
        product = make_product(item_type="supply", unit="EA")

        # Insert a planned order that should be deleted
        old_planned = PlannedOrder(
            order_type="purchase",
            product_id=product.id,
            quantity=Decimal("999"),
            due_date=date.today() + timedelta(days=14),
            start_date=date.today(),
            status="planned",
            source_demand_type="mrp_calculation",
            created_at=datetime.now(timezone.utc),
        )
        db.add(old_planned)
        db.flush()
        old_id = old_planned.id

        svc = MRPService(db)
        svc.run_mrp(planning_horizon_days=30, regenerate_planned=True, user_id=1)

        # The old planned order should be deleted
        deleted = db.query(PlannedOrder).get(old_id)
        assert deleted is None

    def test_firmed_orders_preserved_on_regenerate(self, db, make_product):
        """Firmed planned orders are NOT deleted during regeneration."""
        product = make_product(item_type="supply", unit="EA")

        firmed_order = PlannedOrder(
            order_type="purchase",
            product_id=product.id,
            quantity=Decimal("500"),
            due_date=date.today() + timedelta(days=14),
            start_date=date.today(),
            status="firmed",
            source_demand_type="mrp_calculation",
            created_at=datetime.now(timezone.utc),
        )
        db.add(firmed_order)
        db.flush()
        firmed_id = firmed_order.id

        svc = MRPService(db)
        svc.run_mrp(planning_horizon_days=30, regenerate_planned=True, user_id=1)

        # Firmed order should still exist
        preserved = db.query(PlannedOrder).get(firmed_id)
        assert preserved is not None
        assert preserved.status == "firmed"

    def test_mrp_run_completed_status(self, db):
        """Successful MRP run sets status to completed with timestamp."""
        svc = MRPService(db)
        result = svc.run_mrp(planning_horizon_days=14, user_id=1)

        mrp_run = db.query(MRPRun).get(result.run_id)
        assert mrp_run.status == "completed"
        assert mrp_run.completed_at is not None

    def test_draft_production_orders_included(self, db, make_product, make_bom):
        """Draft production orders are included when include_draft_orders=True."""
        fg = make_product(
            item_type="finished_good", procurement_type="make",
            has_bom=True, unit="EA",
        )
        raw = make_product(
            item_type="supply", unit="EA", is_raw_material=True,
        )
        make_bom(product_id=fg.id, lines=[
            {"component_id": raw.id, "quantity": Decimal("1"), "unit": "EA"},
        ])

        # Draft production order
        prod_order = ProductionOrder(
            code=f"PO-TEST-DRAFT-{uuid.uuid4().hex[:8]}",
            product_id=fg.id,
            quantity_ordered=Decimal("5"),
            quantity_completed=Decimal("0"),
            quantity_scrapped=Decimal("0"),
            status="draft",
            source="manual",
            due_date=date.today() + timedelta(days=7),
        )
        db.add(prod_order)
        db.flush()

        svc = MRPService(db)
        result = svc.run_mrp(
            planning_horizon_days=30,
            include_draft_orders=True,
            user_id=1,
        )

        assert result.orders_processed >= 1
        assert result.components_analyzed >= 1
