"""
Tests for the canonical requirement-explosion function — HARD-12.

Verifies:
1. BOM-only path (no routing) — same results as old MRPService.explode_bom
2. Routing-first path (routing present) — routing materials are used
3. Routing-first / BOM-fallback: product with BOTH routing AND BOM lines uses routing
4. Cycle detection preserved
5. Scrap factor applied correctly
6. UOM conversion applied correctly
7. CONVERGENCE test: product with both routing materials AND BOM lines produces
   identical results through every consumer entry-point
   (blocking_issues.get_material_requirements, buy_list via MRPService.explode_bom,
   mrp.py MRPService.explode_bom directly, sales_order_service.get_material_requirements)

Run with:
    cd backend && pytest tests/services/test_requirement_explosion.py -v
"""
import pytest
from decimal import Decimal
from typing import List

from app.services.requirement_explosion import explode_requirements, ComponentRequirement
from app.services.mrp import MRPService
from app.services.blocking_issues import get_material_requirements as bi_get_material_requirements
from app.models.bom import BOM, BOMLine
from app.models.inventory import Inventory


# ---------------------------------------------------------------------------
# Helpers / sub-fixtures
# ---------------------------------------------------------------------------

def _get_or_create_work_center(db):
    """Return a WorkCenter suitable for routing operations, creating one if needed."""
    from app.models.work_center import WorkCenter
    import uuid as _uuid

    wc = db.query(WorkCenter).filter(WorkCenter.is_active.is_(True)).first()
    if not wc:
        wc = WorkCenter(
            name="Test WC",
            code=f"WC-{_uuid.uuid4().hex[:6]}",
            center_type="printer",
            is_active=True,
        )
        db.add(wc)
        db.flush()
    return wc


def _make_routing_with_material(
    db,
    product_id: int,
    component_id: int,
    qty: Decimal,
    unit: str = "EA",
    scrap_factor: Decimal = Decimal("0"),
):
    """Create an active Routing + one RoutingOperation + one RoutingOperationMaterial."""
    import uuid as _uuid
    from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

    wc = _get_or_create_work_center(db)

    routing = Routing(
        product_id=product_id,
        code=f"RT-{_uuid.uuid4().hex[:8]}",
        name=f"Routing for {product_id}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    op = RoutingOperation(
        routing_id=routing.id,
        work_center_id=wc.id,
        operation_code="PRINT",
        operation_name="Print",
        sequence=10,
        run_time_minutes=Decimal("30"),
    )
    db.add(op)
    db.flush()

    mat = RoutingOperationMaterial(
        routing_operation_id=op.id,
        component_id=component_id,
        quantity=qty,
        unit=unit,
        scrap_factor=scrap_factor,
        is_cost_only=False,
    )
    db.add(mat)
    db.flush()
    return routing, op, mat


# ---------------------------------------------------------------------------
# 1. BOM-only path
# ---------------------------------------------------------------------------

class TestExplodeBomOnlyPath:
    """No routing exists — BOM lines are the source."""

    def test_no_bom_returns_empty(self, db, make_product):
        product = make_product()
        result = explode_requirements(db, product.id, Decimal("5"))
        assert result == []

    def test_single_level_bom(self, db, make_product, make_bom):
        fg = make_product(item_type="finished_good", has_bom=True)
        raw = make_product(item_type="supply", unit="EA")
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": raw.id, "quantity": Decimal("3"), "unit": "EA"}],
        )

        reqs = explode_requirements(db, fg.id, Decimal("2"))
        assert len(reqs) == 1
        assert reqs[0].product_id == raw.id
        assert reqs[0].gross_quantity == Decimal("6")  # 3 × 2

    def test_scrap_factor_applied(self, db, make_product, make_bom):
        fg = make_product(item_type="finished_good", has_bom=True)
        raw = make_product(item_type="supply", unit="EA")
        # 10% scrap
        bom = make_bom(product_id=fg.id, lines=[])
        line = BOMLine(
            bom_id=bom.id,
            component_id=raw.id,
            quantity=Decimal("10"),
            unit="EA",
            scrap_factor=Decimal("10"),
        )
        db.add(line)
        db.flush()

        reqs = explode_requirements(db, fg.id, Decimal("1"))
        assert len(reqs) == 1
        # 10 × (1 + 10/100) = 11
        assert reqs[0].gross_quantity == Decimal("11")

    def test_uom_conversion_g_to_kg(self, db, make_product, make_bom):
        """BOM line in G, component unit KG — should convert."""
        fg = make_product(item_type="finished_good", has_bom=True)
        filament = make_product(item_type="supply", unit="KG")
        # 500 G per unit
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": filament.id, "quantity": Decimal("500"), "unit": "G"}],
        )

        reqs = explode_requirements(db, fg.id, Decimal("1"))
        assert len(reqs) == 1
        # 500 G = 0.5 KG
        assert reqs[0].gross_quantity == Decimal("0.5")

    def test_cycle_detection_returns_empty(self, db, make_product):
        """Cycle in visited set → empty result (no infinite recursion)."""
        product = make_product()
        result = explode_requirements(db, product.id, Decimal("1"), visited={product.id})
        assert result == []

    def test_cost_only_lines_excluded(self, db, make_product, make_bom):
        fg = make_product(item_type="finished_good", has_bom=True)
        overhead = make_product(item_type="supply", unit="EA")
        bom = make_bom(product_id=fg.id, lines=[])
        line = BOMLine(
            bom_id=bom.id,
            component_id=overhead.id,
            quantity=Decimal("1"),
            unit="EA",
            is_cost_only=True,
        )
        db.add(line)
        db.flush()

        reqs = explode_requirements(db, fg.id, Decimal("5"))
        assert reqs == []


# ---------------------------------------------------------------------------
# 2. Routing-first path
# ---------------------------------------------------------------------------

class TestExplodeRoutingFirstPath:
    """Routing exists with materials — routing materials are used, not BOM."""

    def test_routing_materials_used_over_bom(self, db, make_product, make_bom):
        """When routing materials exist, BOM lines must be ignored."""
        fg = make_product(item_type="finished_good", has_bom=True)
        bom_component = make_product(item_type="supply", unit="EA")
        routing_component = make_product(item_type="supply", unit="EA")

        # BOM with a different component
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": bom_component.id, "quantity": Decimal("5"), "unit": "EA"}],
        )
        # Routing with a different component
        _make_routing_with_material(
            db, fg.id, routing_component.id, qty=Decimal("2")
        )

        reqs = explode_requirements(db, fg.id, Decimal("3"))

        product_ids = [r.product_id for r in reqs]
        assert routing_component.id in product_ids
        assert bom_component.id not in product_ids  # BOM skipped — routing present
        # 2 per unit × 3 units = 6
        assert reqs[0].gross_quantity == Decimal("6")

    def test_routing_scrap_factor_applied(self, db, make_product):
        fg = make_product(item_type="finished_good", has_bom=True)
        filament = make_product(item_type="supply", unit="G")
        _make_routing_with_material(
            db,
            fg.id,
            filament.id,
            qty=Decimal("100"),
            unit="G",
            scrap_factor=Decimal("5"),
        )

        reqs = explode_requirements(db, fg.id, Decimal("2"))
        assert len(reqs) == 1
        # (100 G × 2) × (1 + 5/100) = 210 G
        assert reqs[0].gross_quantity == Decimal("210")

    def test_cost_only_routing_material_excluded(self, db, make_product):
        import uuid as _uuid
        from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial

        fg = make_product(item_type="finished_good", has_bom=True)
        comp = make_product(item_type="supply", unit="EA")
        wc = _get_or_create_work_center(db)

        routing = Routing(
            product_id=fg.id,
            code=f"RT-{_uuid.uuid4().hex[:8]}",
            name="R",
            is_active=True,
        )
        db.add(routing)
        db.flush()

        op = RoutingOperation(
            routing_id=routing.id,
            work_center_id=wc.id,
            operation_code="OP",
            operation_name="Op",
            sequence=10,
            run_time_minutes=Decimal("5"),
        )
        db.add(op)
        db.flush()

        mat = RoutingOperationMaterial(
            routing_operation_id=op.id,
            component_id=comp.id,
            quantity=Decimal("10"),
            unit="EA",
            scrap_factor=Decimal("0"),
            is_cost_only=True,  # should be excluded
        )
        db.add(mat)
        db.flush()

        reqs = explode_requirements(db, fg.id, Decimal("1"))
        assert reqs == []


# ---------------------------------------------------------------------------
# 3. Routing-first / BOM-fallback: product with BOTH sources
# ---------------------------------------------------------------------------

class TestRoutingFirstBomFallback:
    """The core semantics: routing takes precedence when it has materials."""

    def test_product_with_both_routing_and_bom_uses_routing(
        self, db, make_product, make_bom
    ):
        """
        35 products in the live DB have BOTH routing materials AND BOM lines.
        This test documents that ROUTING wins — the displayed quantities on MRP,
        BlockingIssuesPanel, and SalesOrder materials panel all align to routing.
        This is the intentional fix: screens were disagreeing because three callers
        used BOM-only while MRP and buy-list used routing.
        """
        fg = make_product(item_type="finished_good", has_bom=True)
        bom_mat = make_product(sku="BOM-MAT", item_type="supply", unit="EA")
        routing_mat = make_product(sku="ROUTING-MAT", item_type="supply", unit="EA")

        # BOM line: 10 per unit
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": bom_mat.id, "quantity": Decimal("10"), "unit": "EA"}],
        )
        # Routing material: 7 per unit
        _make_routing_with_material(db, fg.id, routing_mat.id, qty=Decimal("7"))

        reqs = explode_requirements(db, fg.id, Decimal("2"))

        product_ids = [r.product_id for r in reqs]
        assert routing_mat.id in product_ids, "routing material must be present"
        assert bom_mat.id not in product_ids, "BOM material must be suppressed"
        routing_req = next(r for r in reqs if r.product_id == routing_mat.id)
        assert routing_req.gross_quantity == Decimal("14")  # 7 × 2

    def test_product_bom_only_falls_back_to_bom(self, db, make_product, make_bom):
        """If no routing materials, BOM lines are used even if a routing exists."""
        import uuid as _uuid
        from app.models.manufacturing import Routing

        fg = make_product(item_type="finished_good", has_bom=True)
        bom_mat = make_product(item_type="supply", unit="EA")

        make_bom(
            product_id=fg.id,
            lines=[{"component_id": bom_mat.id, "quantity": Decimal("4"), "unit": "EA"}],
        )
        # Routing with NO materials (zero non-cost-only entries)
        routing = Routing(
            product_id=fg.id,
            code=f"RT-{_uuid.uuid4().hex[:8]}",
            name="Empty routing",
            is_active=True,
        )
        db.add(routing)
        db.flush()

        reqs = explode_requirements(db, fg.id, Decimal("3"))
        assert len(reqs) == 1
        assert reqs[0].product_id == bom_mat.id
        assert reqs[0].gross_quantity == Decimal("12")  # 4 × 3


# ---------------------------------------------------------------------------
# 4. CONVERGENCE: every consumer produces identical results
# ---------------------------------------------------------------------------

class TestConvergenceAcrossConsumers:
    """
    A product with BOTH routing materials and BOM lines must produce the same
    component list through every call site after HARD-12.

    This is the primary regression test for the fix: before HARD-12, MRP/buy-list
    used routing and blocking_issues used BOM-only → numbers differed.
    """

    def _setup_product_with_both(self, db, make_product, make_bom):
        """Create a product with routing materials AND BOM lines (different components)."""
        fg = make_product(item_type="finished_good", has_bom=True)
        bom_mat = make_product(sku="CONV-BOM", item_type="supply", unit="EA")
        routing_mat = make_product(sku="CONV-ROUTING", item_type="supply", unit="EA")

        make_bom(
            product_id=fg.id,
            lines=[{"component_id": bom_mat.id, "quantity": Decimal("5"), "unit": "EA"}],
        )
        _make_routing_with_material(db, fg.id, routing_mat.id, qty=Decimal("3"))
        return fg, bom_mat, routing_mat

    def test_canonical_function_uses_routing(self, db, make_product, make_bom):
        fg, bom_mat, routing_mat = self._setup_product_with_both(db, make_product, make_bom)

        reqs = explode_requirements(db, fg.id, Decimal("4"))
        ids = {r.product_id for r in reqs}
        assert routing_mat.id in ids
        assert bom_mat.id not in ids

    def test_mrp_service_explode_bom_delegates_correctly(self, db, make_product, make_bom):
        """MRPService.explode_bom now delegates to canonical function — same result."""
        fg, bom_mat, routing_mat = self._setup_product_with_both(db, make_product, make_bom)

        mrp = MRPService(db)
        reqs = mrp.explode_bom(product_id=fg.id, quantity=Decimal("4"))
        ids = {r.product_id for r in reqs}
        assert routing_mat.id in ids
        assert bom_mat.id not in ids

    def test_blocking_issues_get_material_requirements_uses_routing(
        self, db, make_product, make_bom
    ):
        """blocking_issues.get_material_requirements now returns routing materials.

        SEMANTIC DELTA vs pre-HARD-12:
        Previously this function read BOM lines only and would have returned
        bom_mat.  After HARD-12 it returns routing_mat for products with routing
        materials — this is the intentional fix that aligns the BlockingIssuesPanel
        with the MRP engine.
        """
        fg, bom_mat, routing_mat = self._setup_product_with_both(db, make_product, make_bom)

        result = bi_get_material_requirements(db, fg.id, Decimal("4"))
        product_ids = [p.id for p, _ in result]
        assert routing_mat.id in product_ids, (
            "blocking_issues must return routing materials for products "
            "that have routing materials (HARD-12 convergence)"
        )
        assert bom_mat.id not in product_ids, (
            "blocking_issues must not return BOM materials when routing materials exist"
        )

    def test_all_consumers_return_same_component_set(self, db, make_product, make_bom):
        """
        Parametric convergence: canonical, MRPService, and blocking_issues all
        agree on which components are required.
        """
        fg, bom_mat, routing_mat = self._setup_product_with_both(db, make_product, make_bom)
        qty = Decimal("5")

        canonical_ids = {r.product_id for r in explode_requirements(db, fg.id, qty)}
        mrp_ids = {r.product_id for r in MRPService(db).explode_bom(fg.id, qty)}
        bi_ids = {p.id for p, _ in bi_get_material_requirements(db, fg.id, qty)}

        assert canonical_ids == mrp_ids == bi_ids, (
            f"Consumers disagree: canonical={canonical_ids}, mrp={mrp_ids}, bi={bi_ids}"
        )

    def test_all_consumers_return_same_quantities(self, db, make_product, make_bom):
        """Quantities must also agree across consumers."""
        fg, _bom_mat, routing_mat = self._setup_product_with_both(db, make_product, make_bom)
        qty = Decimal("6")

        canonical_reqs = explode_requirements(db, fg.id, qty)
        mrp_reqs = MRPService(db).explode_bom(fg.id, qty)
        bi_result = bi_get_material_requirements(db, fg.id, qty)

        # expected: routing_mat quantity = 3 × 6 = 18
        expected_qty = Decimal("18")

        canonical_qty = next(r.gross_quantity for r in canonical_reqs if r.product_id == routing_mat.id)
        mrp_qty = next(r.gross_quantity for r in mrp_reqs if r.product_id == routing_mat.id)
        bi_qty = next(q for p, q in bi_result if p.id == routing_mat.id)

        assert canonical_qty == mrp_qty == bi_qty == expected_qty


# ---------------------------------------------------------------------------
# 5. Source-demand metadata threading
# ---------------------------------------------------------------------------

class TestSourceDemandMetadata:
    def test_metadata_threaded_through(self, db, make_product, make_bom):
        fg = make_product(item_type="finished_good", has_bom=True)
        raw = make_product(item_type="supply", unit="EA")
        from datetime import date
        make_bom(
            product_id=fg.id,
            lines=[{"component_id": raw.id, "quantity": Decimal("1"), "unit": "EA"}],
        )
        due = date(2026, 7, 1)
        reqs = explode_requirements(
            db,
            fg.id,
            Decimal("1"),
            source_demand_type="production_order",
            source_demand_id=42,
            due_date=due,
        )
        assert len(reqs) == 1
        assert reqs[0].source_demand_type == "production_order"
        assert reqs[0].source_demand_id == 42
        assert reqs[0].due_date == due
