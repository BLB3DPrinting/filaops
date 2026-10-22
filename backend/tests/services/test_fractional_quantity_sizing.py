"""
Fractional production-order quantities size materials from the exact quantity.

``ProductionOrder.quantity_ordered`` is Numeric(18,4) and the create endpoint
accepts a fractional Decimal, but routing materials used to be sized from
``int(quantity_ordered)``: a 1.5-piece order was sized, and its materials
reserved, for 1 piece. These tests pin the Decimal-end-to-end rule for the
three places that size a routing material onto an order:

- ``RoutingOperationMaterial.calculate_required_quantity``
- creating an order (``copy_routing_to_operations`` + reservation)
- changing an order's quantity (``split_production_order`` rescale)

Whole quantities must keep their results, so the scrap-factor cases that float
math is most likely to disturb (37 g x 5 at 0% / 7.5%) are asserted too.
"""
from decimal import Decimal

import pytest

from app.models import ProductionOrder
from app.models.inventory import Inventory
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.production_order import (
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.services import production_order_service as svc
from app.services.inventory_service import (
    _get_net_reserved_by_component,
    get_or_create_default_location,
)


USER = "test@filaops.dev"


def _rom(quantity, *, scrap_factor=None, quantity_per="unit", unit="G"):
    """A transient routing material: no session needed to size it."""
    return RoutingOperationMaterial(
        quantity=Decimal(str(quantity)),
        scrap_factor=None if scrap_factor is None else Decimal(str(scrap_factor)),
        quantity_per=quantity_per,
        unit=unit,
    )


def _routing_with_material(
    db,
    finished_good,
    component,
    *,
    quantity,
    unit="G",
    scrap_factor=None,
    quantity_per="unit",
    run_minutes="22",
):
    """A one-operation routing (``run_minutes`` per unit) consuming ``component``."""
    routing = Routing(
        product_id=finished_good.id,
        code=f"RT-FRAC-{finished_good.sku}",
        name="Fractional routing",
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
        run_time_minutes=Decimal(run_minutes),
    )
    db.add(rop)
    db.flush()
    db.add(RoutingOperationMaterial(
        routing_operation_id=rop.id,
        component_id=component.id,
        quantity=Decimal(str(quantity)),
        unit=unit,
        scrap_factor=None if scrap_factor is None else Decimal(str(scrap_factor)),
        quantity_per=quantity_per,
    ))
    db.flush()
    return routing


def _stock(db, component, on_hand="10000"):
    location = get_or_create_default_location(db)
    inv = Inventory(
        product_id=component.id,
        location_id=location.id,
        on_hand_quantity=Decimal(on_hand),
        allocated_quantity=Decimal("0"),
    )
    db.add(inv)
    db.flush()
    return inv


def _bare_order(db, finished_good, routing, quantity):
    """A draft order inserted directly: no operations, no reservation yet."""
    order = ProductionOrder(
        code=svc.generate_production_order_code(db),
        product_id=finished_good.id,
        routing_id=routing.id,
        quantity_ordered=quantity,
        quantity_completed=0,
        quantity_scrapped=0,
        source="manual",
        status="draft",
        created_by=USER,
    )
    db.add(order)
    db.flush()
    return order


def _create_order(db, finished_good, routing, quantity):
    order = svc.create_production_order(
        db,
        product_id=finished_good.id,
        quantity_ordered=quantity,
        created_by=USER,
        routing_id=routing.id,
    )
    db.flush()
    return order


def _only_material(order):
    assert len(order.operations) == 1
    assert len(order.operations[0].materials) == 1
    return order.operations[0].materials[0]


def _dec(value):
    return Decimal(str(value))


# =============================================================================
# calculate_required_quantity
# =============================================================================

class TestCalculateRequiredQuantity:
    """The routing material's own rule, in Decimal from base to result."""

    def test_returns_decimal(self):
        result = _rom(37, scrap_factor="7.5").calculate_required_quantity(5)
        assert isinstance(result, Decimal)

    @pytest.mark.parametrize(
        "base, scrap, order_qty, expected",
        [
            (37, None, 5, "185"),
            (37, "0", 5, "185"),
            (37, "7.5", 5, "198.875"),
            (18, None, 10, "180"),
            # float math: 5 * 10 * (1 + 10/100) == 55.00000000000001
            (5, "10", 10, "55"),
        ],
    )
    def test_whole_quantities_are_exact(self, base, scrap, order_qty, expected):
        assert _rom(base, scrap_factor=scrap).calculate_required_quantity(order_qty) == Decimal(expected)

    @pytest.mark.parametrize(
        "base, scrap, order_qty, expected",
        [
            (18, None, "1.5", "27"),
            (37, "0", "1.5", "55.5"),
            (37, "7.5", "1.5", "59.6625"),
            (18, None, "0.25", "4.5"),
        ],
    )
    def test_fractional_quantities_use_the_exact_quantity(self, base, scrap, order_qty, expected):
        result = _rom(base, scrap_factor=scrap).calculate_required_quantity(Decimal(order_qty))
        assert result == Decimal(expected)

    @pytest.mark.parametrize("quantity_per", ["batch", "order"])
    def test_per_batch_ignores_quantity_but_keeps_scrap(self, quantity_per):
        rom = _rom(10, scrap_factor="10", quantity_per=quantity_per)
        assert rom.calculate_required_quantity(Decimal("1.5")) == Decimal("11")
        assert rom.calculate_required_quantity(5) == Decimal("11")


# =============================================================================
# Creating an order
# =============================================================================

class TestCreateSizesFromExactQuantity:

    def test_copy_sizes_material_from_fractional_quantity(self, db, finished_good, raw_material):
        routing = _routing_with_material(db, finished_good, raw_material, quantity=18)
        order = _bare_order(db, finished_good, routing, Decimal("1.5"))

        ops = svc.copy_routing_to_operations(db, order, routing.id)

        assert _dec(ops[0].materials[0].quantity_required) == Decimal("27")
        assert _dec(ops[0].planned_run_minutes) == Decimal("33")

    def test_sales_order_copy_sizes_by_the_same_rule(self, db, finished_good, raw_material):
        """sales_order_production_service keeps its own routing copy; it must
        size a fractional order the same way."""
        from app.services import sales_order_production_service as sops

        routing = _routing_with_material(db, finished_good, raw_material, quantity=18)
        order = _bare_order(db, finished_good, routing, Decimal("1.5"))

        ops = sops.copy_routing_to_operations(db, order, routing.id)

        assert _dec(ops[0].materials[0].quantity_required) == Decimal("27")

    @pytest.mark.parametrize(
        "quantity, scrap, order_qty, expected",
        [
            (1, None, "1.5", "2"),    # 1.5 EA is two whole pieces
            (5, "10", "10", "55"),    # exactly 55 EA: no float overshoot to 56
        ],
    )
    def test_sales_order_copy_rounds_counted_units_up_exactly(
        self, db, finished_good, make_product, quantity, scrap, order_qty, expected
    ):
        from app.services import sales_order_production_service as sops

        insert = make_product(item_type="component", unit="EA")
        routing = _routing_with_material(
            db, finished_good, insert, quantity=quantity, unit="EA", scrap_factor=scrap
        )
        order = _bare_order(db, finished_good, routing, Decimal(order_qty))

        ops = sops.copy_routing_to_operations(db, order, routing.id)

        assert _dec(ops[0].materials[0].quantity_required) == Decimal(expected)

    def test_create_reserves_fractional_quantity(self, db, finished_good, raw_material):
        routing = _routing_with_material(db, finished_good, raw_material, quantity=18)
        inv = _stock(db, raw_material)

        order = _create_order(db, finished_good, routing, Decimal("1.5"))

        assert _dec(_only_material(order).quantity_required) == Decimal("27")
        assert _get_net_reserved_by_component(db, order.id)[raw_material.id] == Decimal("27")
        db.refresh(inv)
        assert _dec(inv.allocated_quantity) == Decimal("27")

    @pytest.mark.parametrize(
        "scrap, expected",
        [(None, "185"), ("0", "185"), ("7.5", "198.875")],
    )
    def test_whole_quantity_is_unchanged(self, db, finished_good, raw_material, scrap, expected):
        """37 g x 5 pieces: scrap must not turn a clean figure into float noise."""
        routing = _routing_with_material(
            db, finished_good, raw_material, quantity=37, scrap_factor=scrap
        )
        _stock(db, raw_material)

        order = _create_order(db, finished_good, routing, 5)

        mat = _only_material(order)
        assert _dec(mat.quantity_required) == Decimal(expected)
        assert _get_net_reserved_by_component(db, order.id)[raw_material.id] == Decimal(expected)

    def test_counted_units_round_up_the_exact_fractional_requirement(
        self, db, finished_good, make_product
    ):
        """1 EA per piece x 1.5 pieces is 1.5 EA: a whole 2, not the 1 that
        truncating the quantity first would have given."""
        insert = make_product(item_type="component", unit="EA")
        routing = _routing_with_material(
            db, finished_good, insert, quantity=1, unit="EA"
        )

        order = _create_order(db, finished_good, routing, Decimal("1.5"))

        assert _dec(_only_material(order).quantity_required) == Decimal("2")

    def test_counted_units_are_not_rounded_up_by_float_noise(
        self, db, finished_good, make_product
    ):
        """5 EA per piece x 10 pieces at 10% scrap is exactly 55 EA. In float
        it is 55.00000000000001, which rounds up to 56."""
        insert = make_product(item_type="component", unit="EA")
        routing = _routing_with_material(
            db, finished_good, insert, quantity=5, unit="EA", scrap_factor="10"
        )

        order = _create_order(db, finished_good, routing, 10)

        assert _dec(_only_material(order).quantity_required) == Decimal("55")


# =============================================================================
# Changing an order's quantity (split)
# =============================================================================

def _ops(order):
    assert len(order.operations) == 1
    return order.operations[0]


class TestSplitSizesFromExactQuantity:

    def test_split_fractional_parent_keeps_the_fraction(self, db, finished_good, raw_material):
        """3.5 split 1 + 2.5: the parent keeps 2.5, not int(3.5) - 1 == 2."""
        routing = _routing_with_material(db, finished_good, raw_material, quantity=18)
        _stock(db, raw_material)
        order = _create_order(db, finished_good, routing, Decimal("3.5"))
        assert _get_net_reserved_by_component(db, order.id)[raw_material.id] == Decimal("63")

        parent, child = svc.split_production_order(db, order.id, split_quantity=1, user_email=USER)

        assert _dec(parent.quantity_ordered) == Decimal("2.5")
        assert _dec(child.quantity_ordered) == Decimal("1")

        db.expire(parent, ["operations"])
        parent_op = _ops(parent)
        assert _dec(parent_op.planned_run_minutes) == Decimal("55")
        assert _dec(parent_op.materials[0].quantity_required) == Decimal("45")
        assert _dec(_ops(child).materials[0].quantity_required) == Decimal("18")
        assert _get_net_reserved_by_component(db, parent.id)[raw_material.id] == Decimal("45")
        assert _get_net_reserved_by_component(db, child.id)[raw_material.id] == Decimal("18")

    def test_split_fractional_quantity_sizes_both_orders(self, db, finished_good, raw_material):
        """3 split 1.5 + 1.5: each order is sized and reserved for 1.5, not 1."""
        routing = _routing_with_material(db, finished_good, raw_material, quantity=18)
        inv = _stock(db, raw_material)
        order = _create_order(db, finished_good, routing, 3)

        parent, child = svc.split_production_order(
            db, order.id, split_quantity=Decimal("1.5"), user_email=USER
        )

        assert _dec(parent.quantity_ordered) == Decimal("1.5")
        assert _dec(child.quantity_ordered) == Decimal("1.5")

        db.expire(parent, ["operations"])
        parent_op = _ops(parent)
        assert _dec(parent_op.planned_run_minutes) == Decimal("33")
        assert _dec(parent_op.materials[0].quantity_required) == Decimal("27")
        assert _dec(_ops(child).planned_run_minutes) == Decimal("33")
        assert _dec(_ops(child).materials[0].quantity_required) == Decimal("27")
        assert _get_net_reserved_by_component(db, parent.id)[raw_material.id] == Decimal("27")
        assert _get_net_reserved_by_component(db, child.id)[raw_material.id] == Decimal("27")

        # 27 g + 27 g: the pool still holds the original 3 pieces' 54 g.
        db.refresh(inv)
        assert _dec(inv.allocated_quantity) == Decimal("54")

    def test_split_scales_unlinked_rows_by_the_exact_ratio(
        self, db, finished_good, raw_material, make_production_order
    ):
        """10 split 2.5 + 7.5: an operation with no routing link scales by
        7.5 / 10, not 7 / 10."""
        order = make_production_order(product_id=finished_good.id, quantity=10)
        op = ProductionOrderOperation(
            production_order_id=order.id,
            routing_operation_id=None,
            work_center_id=1,
            sequence=10,
            operation_code="PRINT",
            operation_name="Print",
            planned_setup_minutes=Decimal("0"),
            planned_run_minutes=Decimal("100"),
            status="pending",
        )
        db.add(op)
        db.flush()
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=raw_material.id,
            quantity_required=Decimal("50"),
            unit="G",
            status="pending",
        )
        db.add(mat)
        db.flush()

        svc.split_production_order(
            db, order.id, split_quantity=Decimal("2.5"), user_email=USER
        )

        db.refresh(op)
        db.refresh(mat)
        assert _dec(op.planned_run_minutes) == Decimal("75")
        assert _dec(mat.quantity_required) == Decimal("37.5")

    def test_split_unlinked_counted_row_is_not_rounded_up_by_the_ratio(
        self, db, finished_good, make_product, make_production_order
    ):
        """18 EA on an order of 6 is 3 EA for the 1 unit that stays. Dividing
        1 / 6 first gives 0.1666...67, and 18 x that is 3.000...001, which a
        counted unit rounds up to 4."""
        insert = make_product(item_type="component", unit="EA")
        order = make_production_order(product_id=finished_good.id, quantity=6)
        op = ProductionOrderOperation(
            production_order_id=order.id,
            routing_operation_id=None,
            work_center_id=1,
            sequence=10,
            operation_code="ASSEMBLE",
            operation_name="Assemble",
            planned_setup_minutes=Decimal("0"),
            planned_run_minutes=Decimal("60"),
            status="pending",
        )
        db.add(op)
        db.flush()
        mat = ProductionOrderOperationMaterial(
            production_order_operation_id=op.id,
            component_id=insert.id,
            quantity_required=Decimal("18"),
            unit="EA",
            status="pending",
        )
        db.add(mat)
        db.flush()

        svc.split_production_order(db, order.id, split_quantity=5, user_email=USER)

        db.refresh(op)
        db.refresh(mat)
        assert _dec(op.planned_run_minutes) == Decimal("10")
        assert _dec(mat.quantity_required) == Decimal("3")

    def test_split_rejects_a_quantity_that_leaves_nothing(self, db, finished_good, raw_material):
        from fastapi import HTTPException

        routing = _routing_with_material(db, finished_good, raw_material, quantity=18)
        _stock(db, raw_material)
        order = _create_order(db, finished_good, routing, Decimal("2.5"))

        with pytest.raises(HTTPException) as exc:
            svc.split_production_order(
                db, order.id, split_quantity=Decimal("2.5"), user_email=USER
            )
        assert exc.value.status_code == 400


# =============================================================================
# Quantities the order column can store
# =============================================================================

class TestStorableQuantity:
    """``quantity_ordered`` is Numeric(18,4). A quantity with more places than
    that is stored rounded (0.00001 becomes 0) while the sizing code would still
    see the longer figure, so it is refused before anything is created or
    changed."""

    @pytest.mark.parametrize("value", ["1", "1.5", "2.5000", "0.0001", "999999", 3, 0.25])
    def test_accepts_what_the_column_stores(self, value):
        from app.services.production_order_quantity_change import require_storable_order_quantity

        assert require_storable_order_quantity(value) == Decimal(str(value))

    @pytest.mark.parametrize("value", ["0.00001", "1.23456", "NaN", "Infinity", "1E+30"])
    def test_rejects_what_the_column_would_change(self, value):
        from fastapi import HTTPException

        from app.services.production_order_quantity_change import require_storable_order_quantity

        with pytest.raises(HTTPException) as exc:
            require_storable_order_quantity(Decimal(value))
        assert exc.value.status_code == 400

    def test_create_rejects_an_unstorable_quantity_before_creating_anything(
        self, db, finished_good, raw_material
    ):
        from fastapi import HTTPException

        routing = _routing_with_material(db, finished_good, raw_material, quantity=18)
        inv = _stock(db, raw_material)
        orders_before = db.query(ProductionOrder).count()

        with pytest.raises(HTTPException) as exc:
            _create_order(db, finished_good, routing, Decimal("0.00001"))

        assert exc.value.status_code == 400
        assert db.query(ProductionOrder).count() == orders_before
        db.refresh(inv)
        assert _dec(inv.allocated_quantity) == Decimal("0")

    def test_split_rejects_an_unstorable_quantity_before_changing_either_order(
        self, db, finished_good, raw_material
    ):
        from fastapi import HTTPException

        routing = _routing_with_material(db, finished_good, raw_material, quantity=18)
        _stock(db, raw_material)
        order = _create_order(db, finished_good, routing, 3)
        orders_before = db.query(ProductionOrder).count()

        with pytest.raises(HTTPException) as exc:
            svc.split_production_order(
                db, order.id, split_quantity=Decimal("0.00001"), user_email=USER
            )

        assert exc.value.status_code == 400
        assert db.query(ProductionOrder).count() == orders_before
        assert _dec(order.quantity_ordered) == Decimal("3")
        assert _dec(_only_material(order).quantity_required) == Decimal("54")
        assert _get_net_reserved_by_component(db, order.id)[raw_material.id] == Decimal("54")
