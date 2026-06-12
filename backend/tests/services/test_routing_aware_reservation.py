"""
Tests for RESERVE-1 — routing-aware material reservation + release-time
self-heal.

Covers:
- Routing-only products (empty/no-production-line BOM): creation-time
  reservation reserves from op-material rows, ledger txns exist,
  allocated == required.
- BOM-only products (no routing/op rows): legacy BOM walk regression.
- Mixed-source products: op rows present -> routing-first totals only,
  no double reservation.
- Delta idempotency: re-running reserve_production_materials never
  double-reserves; partial pre-reservations are topped up by the delta only.
- Release-time level-2 self-heal: draft WO with op rows and zero
  reservations releases successfully, creating the reservations.
- HARD-5 zero-stock semantics: reservation proceeds flagged, release
  proceeds (flag, not block).

All fixtures are created locally per test (fresh products per test via the
conftest factories) — no assertions on global table counts, since the local
dev/CI databases accumulate data across runs.
"""
from decimal import Decimal

from app.models import ProductionOrder
from app.models.inventory import Inventory, InventoryTransaction
from app.models.manufacturing import (
    Routing,
    RoutingOperation,
    RoutingOperationMaterial,
)
from app.services import production_order_service as po_svc
from app.services.inventory_service import (
    _get_net_reserved_by_component,
    get_or_create_default_location,
    reserve_production_materials,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_routing_with_materials(db, product, materials, *, code_suffix=""):
    """Create a routing with one operation carrying the given materials.

    materials: list of dicts with keys:
        component_id (required), quantity (required Decimal),
        unit (default "G"), scrap_factor (optional), is_cost_only (optional)
    """
    routing = Routing(
        product_id=product.id,
        code=f"RT-{product.sku}{code_suffix}",
        name=f"Routing for {product.name}",
        is_active=True,
    )
    db.add(routing)
    db.flush()

    rop = RoutingOperation(
        routing_id=routing.id,
        work_center_id=1,
        sequence=10,
        operation_code="PRINT",
        operation_name="Print",
        setup_time_minutes=0,
        run_time_minutes=Decimal("10"),
    )
    db.add(rop)
    db.flush()

    for m in materials:
        rom = RoutingOperationMaterial(
            routing_operation_id=rop.id,
            component_id=m["component_id"],
            quantity=m["quantity"],
            unit=m.get("unit", "G"),
            scrap_factor=m.get("scrap_factor"),
            is_cost_only=m.get("is_cost_only", False),
        )
        db.add(rom)
    db.flush()

    return routing, rop


def _make_draft_order_with_ops(db, product, routing, *, quantity=10):
    """Insert a draft ProductionOrder directly (NO service reservation) and
    materialize op-material rows from the routing — simulates a brownfield
    draft WO created before RESERVE-1."""
    code = po_svc.generate_production_order_code(db)
    order = ProductionOrder(
        code=code,
        product_id=product.id,
        routing_id=routing.id,
        quantity_ordered=quantity,
        quantity_completed=0,
        quantity_scrapped=0,
        source="manual",
        status="draft",
        priority=3,
        created_by="test@filaops.dev",
    )
    db.add(order)
    db.flush()
    po_svc.copy_routing_to_operations(db, order, routing.id)
    db.flush()
    return order


def _get_inventory(db, product_id):
    location = get_or_create_default_location(db)
    return db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.location_id == location.id,
    ).first()


def _seed_inventory(db, product_id, on_hand, allocated=Decimal("0")):
    location = get_or_create_default_location(db)
    inv = Inventory(
        product_id=product_id,
        location_id=location.id,
        on_hand_quantity=on_hand,
        allocated_quantity=allocated,
    )
    db.add(inv)
    db.flush()
    return inv


def _reservation_txns(db, order_id, product_id):
    """All reservation ledger rows for (order, component) — scoped, never global."""
    return db.query(InventoryTransaction).filter(
        InventoryTransaction.reference_type == "production_order",
        InventoryTransaction.reference_id == order_id,
        InventoryTransaction.product_id == product_id,
        InventoryTransaction.transaction_type == "reservation",
    ).all()


def _op_material_rows(db, order):
    db.expire(order, ["operations"])
    return [mat for op in order.operations for mat in op.materials]


# =============================================================================
# 1. Routing-only product (the PO-2026-0032 / FG-002 case)
# =============================================================================

class TestRoutingOnlyReservation:
    """Products whose materials live on the routing, with an empty BOM."""

    def test_creation_reserves_from_op_rows_with_empty_bom(
        self, db, finished_good, raw_material, make_bom
    ):
        """Active but EMPTY BOM + routing materials: creation-time reservation
        must reserve from op-material rows (previously reserved nothing)."""
        # Active BOM with zero lines — the FG-002 configuration
        make_bom(finished_good.id, lines=[])
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("0.2"), "unit": "G"},
        ])
        _seed_inventory(db, raw_material.id, Decimal("1000"))

        order = po_svc.create_production_order(
            db,
            product_id=finished_good.id,
            quantity_ordered=10,
            created_by="test@filaops.dev",
            routing_id=routing.id,
        )

        # Op rows fully allocated (0.2 g * 10 = 2 g)
        rows = _op_material_rows(db, order)
        assert len(rows) == 1
        assert Decimal(str(rows[0].quantity_required)) == Decimal("2")
        assert Decimal(str(rows[0].quantity_allocated)) == Decimal("2")

        # Ledger audit row exists with the routing-derived quantity
        txns = _reservation_txns(db, order.id, raw_material.id)
        assert len(txns) == 1
        assert Decimal(str(txns[0].quantity)) == Decimal("2")

        # inventory.allocated_quantity reflects the reservation
        inv = _get_inventory(db, raw_material.id)
        assert Decimal(str(inv.allocated_quantity)) == Decimal("2")

    def test_creation_reserves_from_op_rows_with_no_bom(
        self, db, finished_good, raw_material
    ):
        """No BOM at all + routing materials: reservation still happens."""
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("0.12"), "unit": "G"},
        ])
        _seed_inventory(db, raw_material.id, Decimal("1000"))

        order = po_svc.create_production_order(
            db,
            product_id=finished_good.id,
            quantity_ordered=10,
            created_by="test@filaops.dev",
            routing_id=routing.id,
        )

        rows = _op_material_rows(db, order)
        assert len(rows) == 1
        assert Decimal(str(rows[0].quantity_allocated)) == Decimal(
            str(rows[0].quantity_required)
        )
        net = _get_net_reserved_by_component(db, order.id)
        assert net.get(raw_material.id) == Decimal(str(rows[0].quantity_required))

    def test_cost_only_routing_materials_not_reserved(
        self, db, finished_good, raw_material, make_product
    ):
        """Cost-only routing materials are excluded at copy time and must not
        be reserved (no double-exclusion either — real materials reserve)."""
        cost_only = make_product(unit="EA", name="Machine Time (cost only)")
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("5"), "unit": "G"},
            {"component_id": cost_only.id, "quantity": Decimal("1"),
             "unit": "EA", "is_cost_only": True},
        ])
        _seed_inventory(db, raw_material.id, Decimal("1000"))

        order = po_svc.create_production_order(
            db,
            product_id=finished_good.id,
            quantity_ordered=2,
            created_by="test@filaops.dev",
            routing_id=routing.id,
        )

        # Only the real material got an op row and a reservation
        rows = _op_material_rows(db, order)
        assert [r.component_id for r in rows] == [raw_material.id]
        assert _reservation_txns(db, order.id, cost_only.id) == []
        assert len(_reservation_txns(db, order.id, raw_material.id)) == 1


# =============================================================================
# 2. BOM-only product — legacy walk regression
# =============================================================================

class TestBomOnlyReservation:
    """Products with a BOM but no routing materials keep the legacy path."""

    def test_bom_walk_still_reserves(
        self, db, finished_good, raw_material, make_bom
    ):
        make_bom(finished_good.id, lines=[
            {"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        _seed_inventory(db, raw_material.id, Decimal("1000"))

        order = po_svc.create_production_order(
            db,
            product_id=finished_good.id,
            quantity_ordered=5,
            created_by="test@filaops.dev",
        )

        txns = _reservation_txns(db, order.id, raw_material.id)
        assert len(txns) == 1
        assert Decimal(str(txns[0].quantity)) == Decimal("500")
        inv = _get_inventory(db, raw_material.id)
        assert Decimal(str(inv.allocated_quantity)) == Decimal("500")

    def test_no_bom_no_routing_reserves_nothing(self, db, finished_good):
        order = po_svc.create_production_order(
            db,
            product_id=finished_good.id,
            quantity_ordered=5,
            created_by="test@filaops.dev",
        )
        reservations = reserve_production_materials(db, order)
        assert reservations == []


# =============================================================================
# 3. Mixed-source product — routing-first, no double reservation
# =============================================================================

class TestMixedSourceReservation:
    """When op rows exist they REPLACE the BOM walk entirely (HARD-12
    routing-first semantics) — the same component must not be reserved from
    both sources."""

    def test_op_rows_replace_bom_walk(
        self, db, finished_good, raw_material, make_bom
    ):
        # BOM says 100 g/unit; routing says 80 g/unit — routing wins.
        make_bom(finished_good.id, lines=[
            {"component_id": raw_material.id, "quantity": Decimal("100"), "unit": "G"},
        ])
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("80"), "unit": "G"},
        ])
        _seed_inventory(db, raw_material.id, Decimal("10000"))

        order = po_svc.create_production_order(
            db,
            product_id=finished_good.id,
            quantity_ordered=2,
            created_by="test@filaops.dev",
            routing_id=routing.id,
        )

        # Routing-first: 80 * 2 = 160 g — NOT 200 (BOM), NOT 360 (both)
        net = _get_net_reserved_by_component(db, order.id)
        assert net.get(raw_material.id) == Decimal("160")
        inv = _get_inventory(db, raw_material.id)
        assert Decimal(str(inv.allocated_quantity)) == Decimal("160")


# =============================================================================
# 4. Delta idempotency
# =============================================================================

class TestDeltaIdempotency:
    """reserve_production_materials must be safely re-runnable."""

    def test_second_run_is_noop(
        self, db, finished_good, raw_material
    ):
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("0.5"), "unit": "G"},
        ])
        _seed_inventory(db, raw_material.id, Decimal("1000"))

        order = po_svc.create_production_order(
            db,
            product_id=finished_good.id,
            quantity_ordered=10,
            created_by="test@filaops.dev",
            routing_id=routing.id,
        )

        inv = _get_inventory(db, raw_material.id)
        allocated_after_first = Decimal(str(inv.allocated_quantity))
        assert allocated_after_first == Decimal("5")

        # Second run: no new reservations, nothing changes
        second = reserve_production_materials(db, order, created_by="test@filaops.dev")
        assert second == []

        db.refresh(inv)
        assert Decimal(str(inv.allocated_quantity)) == allocated_after_first
        txns = _reservation_txns(db, order.id, raw_material.id)
        assert len(txns) == 1  # still only the original ledger row

        rows = _op_material_rows(db, order)
        assert Decimal(str(rows[0].quantity_allocated)) == Decimal("5")

    def test_partial_prereservation_topped_up_by_delta_only(
        self, db, finished_good, raw_material
    ):
        """Brownfield mixed case (PO-2026-0026 shape): some quantity was
        reserved at creation, the rest never was — re-run must reserve only
        the delta and mark it as a top-up."""
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("0.5"), "unit": "G"},
        ])
        inv = _seed_inventory(
            db, raw_material.id, Decimal("1000"), allocated=Decimal("2")
        )

        # Draft order with op rows (requirement: 0.5 * 10 = 5 g), plus a
        # pre-existing partial reservation of 2 g.
        order = _make_draft_order_with_ops(db, finished_good, routing, quantity=10)
        location = get_or_create_default_location(db)
        db.add(InventoryTransaction(
            product_id=raw_material.id,
            location_id=location.id,
            transaction_type="reservation",
            quantity=Decimal("2"),
            reference_type="production_order",
            reference_id=order.id,
            unit="G",
            notes="Pre-existing partial reservation (brownfield)",
        ))
        db.flush()

        reservations = reserve_production_materials(
            db, order, created_by="test@filaops.dev"
        )

        assert len(reservations) == 1
        assert reservations[0]["quantity_reserved"] == 3.0  # delta only
        assert reservations[0]["already_reserved"] == 2.0
        assert reservations[0]["is_topup"] is True

        # Ledger net = 2 + 3 = 5; inventory allocated topped up to 5
        net = _get_net_reserved_by_component(db, order.id)
        assert net.get(raw_material.id) == Decimal("5")
        db.refresh(inv)
        assert Decimal(str(inv.allocated_quantity)) == Decimal("5")

        # The top-up ledger row is marked as such
        txns = _reservation_txns(db, order.id, raw_material.id)
        topups = [t for t in txns if "Top-up reservation" in (t.notes or "")]
        assert len(topups) == 1
        assert Decimal(str(topups[0].quantity)) == Decimal("3")

        # Op rows fully allocated
        rows = _op_material_rows(db, order)
        assert Decimal(str(rows[0].quantity_allocated)) == Decimal("5")


# =============================================================================
# 5. Release-time level-2 self-heal
# =============================================================================

class TestReleaseSelfHealLevel2:
    """Draft WOs with op rows and ZERO reservations (reservation never ran)
    must heal at release time — no migration, no user action."""

    def test_release_heals_never_reserved_order(
        self, db, finished_good, raw_material
    ):
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("0.2"), "unit": "G"},
        ])
        _seed_inventory(db, raw_material.id, Decimal("1000"))

        order = _make_draft_order_with_ops(db, finished_good, routing, quantity=10)

        # Sanity: nothing reserved yet
        assert _reservation_txns(db, order.id, raw_material.id) == []
        rows = _op_material_rows(db, order)
        assert all(
            Decimal(str(r.quantity_allocated)) == Decimal("0") for r in rows
        )

        # Release WITHOUT force — self-heal reserves, gate passes
        released = po_svc.release_production_order(
            db, order.id, "test@filaops.dev", force=False
        )
        assert released.status == "released"

        # Reservations were created at release time
        txns = _reservation_txns(db, order.id, raw_material.id)
        assert len(txns) == 1
        assert Decimal(str(txns[0].quantity)) == Decimal("2")

        rows = _op_material_rows(db, order)
        assert Decimal(str(rows[0].quantity_allocated)) == Decimal("2")

        inv = _get_inventory(db, raw_material.id)
        assert Decimal(str(inv.allocated_quantity)) == Decimal("2")

    def test_release_heals_partially_reserved_order(
        self, db, finished_good, raw_material
    ):
        """Mixed brownfield: partial ledger reservation, rows out of sync —
        level 1 backfills, level 2 tops up the remainder, release proceeds."""
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("0.5"), "unit": "G"},
        ])
        inv = _seed_inventory(
            db, raw_material.id, Decimal("1000"), allocated=Decimal("2")
        )
        order = _make_draft_order_with_ops(db, finished_good, routing, quantity=10)

        location = get_or_create_default_location(db)
        db.add(InventoryTransaction(
            product_id=raw_material.id,
            location_id=location.id,
            transaction_type="reservation",
            quantity=Decimal("2"),
            reference_type="production_order",
            reference_id=order.id,
            unit="G",
            notes="Pre-existing partial reservation (brownfield)",
        ))
        db.flush()

        released = po_svc.release_production_order(
            db, order.id, "test@filaops.dev", force=False
        )
        assert released.status == "released"

        net = _get_net_reserved_by_component(db, order.id)
        assert net.get(raw_material.id) == Decimal("5")
        db.refresh(inv)
        assert Decimal(str(inv.allocated_quantity)) == Decimal("5")
        rows = _op_material_rows(db, order)
        assert Decimal(str(rows[0].quantity_allocated)) == Decimal("5")


# =============================================================================
# 6. HARD-5: zero-stock components — flag, not block
# =============================================================================

class TestZeroStockHard5:
    """Reservations may exceed on_hand (ahead-of-receipt) — flagged, never
    blocked, and release proceeds."""

    def test_zero_stock_reservation_flagged_and_release_proceeds(
        self, db, finished_good, raw_material
    ):
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("10"), "unit": "G"},
        ])
        # NO inventory seeded — component has zero stock

        order = po_svc.create_production_order(
            db,
            product_id=finished_good.id,
            quantity_ordered=3,
            created_by="test@filaops.dev",
            routing_id=routing.id,
        )

        # Reservation happened despite zero stock and is flagged as shortage
        txns = _reservation_txns(db, order.id, raw_material.id)
        assert len(txns) == 1
        assert Decimal(str(txns[0].quantity)) == Decimal("30")
        inv = _get_inventory(db, raw_material.id)
        assert Decimal(str(inv.allocated_quantity)) == Decimal("30")
        assert Decimal(str(inv.on_hand_quantity)) == Decimal("0")

        # Release proceeds — HARD-5 is flag-not-block
        released = po_svc.release_production_order(
            db, order.id, "test@filaops.dev", force=False
        )
        assert released.status == "released"

    def test_zero_stock_self_heal_at_release(self, db, finished_good, raw_material):
        """Never-reserved draft + zero stock: self-heal reserves ahead of
        receipt and release proceeds."""
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("10"), "unit": "G"},
        ])
        order = _make_draft_order_with_ops(db, finished_good, routing, quantity=3)

        released = po_svc.release_production_order(
            db, order.id, "test@filaops.dev", force=False
        )
        assert released.status == "released"
        net = _get_net_reserved_by_component(db, order.id)
        assert net.get(raw_material.id) == Decimal("30")

    def test_shortage_flag_in_reservation_result(
        self, db, finished_good, raw_material
    ):
        """Direct call surface: is_shortage=True when reserving past on_hand."""
        routing, _ = _make_routing_with_materials(db, finished_good, [
            {"component_id": raw_material.id, "quantity": Decimal("10"), "unit": "G"},
        ])
        _seed_inventory(db, raw_material.id, Decimal("5"))
        order = _make_draft_order_with_ops(db, finished_good, routing, quantity=3)

        reservations = reserve_production_materials(
            db, order, created_by="test@filaops.dev"
        )
        assert len(reservations) == 1
        assert reservations[0]["is_shortage"] is True
        assert reservations[0]["quantity_reserved"] == 30.0
        assert reservations[0]["available_after"] < 0
