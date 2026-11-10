"""Recost All costs a component before the items built from it.

``calculate_item_cost`` prices an assembly from the stored standard cost of
its direct components, so the order of the run decides whether an assembly
sees its sub-assembly's new cost or the old one.
"""
import uuid
from decimal import Decimal

import pytest

from app.models.item_category import ItemCategory
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.services import item_cost_service
from app.services.item_cost_service import components_first, recost_all_items


@pytest.fixture
def category(db):
    """A category of its own, so a run covers only this test's items."""
    uid = uuid.uuid4().hex[:8].upper()
    cat = ItemCategory(code=f"RECOST-{uid}", name=f"Recost order {uid}")
    db.add(cat)
    db.flush()
    return cat


def _made(make_product, category, stale_cost):
    """A made item carrying a standard cost from before its parts changed."""
    return make_product(
        item_type="component",
        procurement_type="make",
        standard_cost=Decimal(stale_cost),
        category_id=category.id,
    )


def _bought(make_product, category, cost):
    """A purchased part with a standard cost."""
    return make_product(
        item_type="component", standard_cost=Decimal(cost), category_id=category.id
    )


def _routing_consuming(
    db, make_work_center, product, component, quantity, version=1, operation_active=True
):
    """Give ``product`` an active routing whose one operation uses ``component``."""
    work_center = make_work_center(center_type="assembly")
    routing = Routing(
        product_id=product.id,
        code=f"RTG-{uuid.uuid4().hex[:8]}",
        name="Assemble",
        is_active=True,
        version=version,
    )
    db.add(routing)
    db.flush()
    operation = RoutingOperation(
        routing_id=routing.id,
        work_center_id=work_center.id,
        sequence=10,
        operation_code="OP10",
        operation_name="Assemble",
        setup_time_minutes=Decimal("0"),
        run_time_minutes=Decimal("0"),
        is_active=operation_active,
    )
    db.add(operation)
    db.flush()
    db.add(
        RoutingOperationMaterial(
            routing_operation_id=operation.id,
            component_id=component.id,
            quantity=Decimal(quantity),
            unit="EA",
        )
    )
    db.flush()
    return routing


def _costs(db, *products):
    """The standard costs of ``products`` as stored after the run."""
    for product in products:
        db.refresh(product)
    return [float(product.standard_cost) for product in products]


class TestComponentsFirst:
    """The ordering rule on its own: ids in, ids out."""

    def test_no_dependencies_keeps_the_given_order(self):
        """With nothing built from anything, the order is left alone."""
        order, circular = components_first([3, 1, 2], {})
        assert order == [3, 1, 2]
        assert circular == set()

    def test_component_comes_before_its_parent(self):
        """A component moves ahead of the item built from it."""
        order, circular = components_first([1, 2], {1: {2}})
        assert order == [2, 1]
        assert circular == set()

    def test_every_level_of_a_chain_is_ordered(self):
        """A four-level chain comes out deepest component first."""
        # 1 is built from 2, 2 from 3, 3 from 4.
        order, _ = components_first([1, 2, 3, 4], {1: {2}, 2: {3}, 3: {4}})
        assert order == [4, 3, 2, 1]

    def test_shared_component_is_listed_once(self):
        """A component used by two items appears once, ahead of both."""
        order, _ = components_first([1, 2, 3], {1: {3}, 2: {3}})
        assert order == [3, 1, 2]

    def test_component_outside_the_run_is_ignored(self):
        """A component that is not in the run does not affect the order."""
        order, circular = components_first([1, 2], {1: {99}})
        assert order == [1, 2]
        assert circular == set()

    def test_two_items_built_from_each_other_are_both_kept_and_reported(self):
        """A circular pair is still returned, and both are reported."""
        order, circular = components_first([1, 2, 3], {1: {2}, 2: {1}})
        assert sorted(order) == [1, 2, 3]
        assert circular == {1, 2}

    def test_item_built_from_itself_is_reported(self):
        """An item listed as its own component is reported as circular."""
        order, circular = components_first([1, 2], {1: {1, 2}})
        assert order == [2, 1]
        assert circular == {1}

    def test_item_below_a_circular_pair_is_still_costed_first(self):
        """A component of a circular pair is ordered ahead of the pair."""
        # 1 and 2 are built from each other; both use 3.
        order, circular = components_first([1, 2, 3], {1: {2, 3}, 2: {1, 3}})
        assert order.index(3) < order.index(1)
        assert order.index(3) < order.index(2)
        assert circular == {1, 2}

    def test_circle_member_reached_after_another_member_is_finished(self):
        """Every member of a three-item circle is reported."""
        # 1 is built from 3, 3 from 2, 2 from 1. Walking 1 -> 2 first finishes 2
        # before 3 is looked at; 3 is on the circle all the same.
        order, circular = components_first([1, 2, 3], {1: {2, 3}, 2: {1}, 3: {2}})
        assert sorted(order) == [1, 2, 3]
        assert circular == {1, 2, 3}

    def test_item_above_a_circle_is_not_circular(self):
        """Items that only use a circle are not reported as part of it."""
        # 2 and 4 are built from each other. 1 and 3 use them but are not
        # part of the circle, and are costed after it.
        order, circular = components_first([1, 2, 3, 4], {1: {2, 3}, 2: {4}, 3: {4}, 4: {2}})
        assert order == [2, 4, 3, 1]
        assert circular == {2, 4}

    def test_a_very_deep_chain_does_not_hit_the_recursion_limit(self):
        """A 5,000-level chain is ordered without recursion errors."""
        depth = 5000
        ids = list(range(depth))
        dependencies = {i: {i + 1} for i in range(depth - 1)}
        order, circular = components_first(ids, dependencies)
        assert order == list(reversed(ids))
        assert circular == set()


class TestRecostAllOrder:
    """The whole run, against real products, BOMs and routings."""

    def test_parent_created_before_its_sub_assembly(self, db, make_product, make_bom, category):
        """A parent created first is priced from its sub-assembly's new cost."""
        top = _made(make_product, category, "5.00")
        sub = _made(make_product, category, "1.00")
        part = _bought(make_product, category, "2.00")
        make_bom(top.id, lines=[{"component_id": sub.id, "quantity": Decimal("2")}])
        make_bom(sub.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])

        recost_all_items(db, category_id=category.id)

        assert _costs(db, sub, top) == pytest.approx([6.00, 12.00])

    def test_sub_assembly_created_before_its_parent(self, db, make_product, make_bom, category):
        """The result is the same when the sub-assembly was created first."""
        part = _bought(make_product, category, "2.00")
        sub = _made(make_product, category, "1.00")
        top = _made(make_product, category, "5.00")
        make_bom(sub.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])
        make_bom(top.id, lines=[{"component_id": sub.id, "quantity": Decimal("2")}])

        recost_all_items(db, category_id=category.id)

        assert _costs(db, sub, top) == pytest.approx([6.00, 12.00])

    def test_three_levels_settle_in_one_run(self, db, make_product, make_bom, category):
        """Three levels are right after one run, and a second run changes nothing."""
        top = _made(make_product, category, "9.00")
        mid = _made(make_product, category, "9.00")
        sub = _made(make_product, category, "9.00")
        part = _bought(make_product, category, "2.00")
        make_bom(top.id, lines=[{"component_id": mid.id, "quantity": Decimal("2")}])
        make_bom(mid.id, lines=[{"component_id": sub.id, "quantity": Decimal("2")}])
        make_bom(sub.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])

        recost_all_items(db, category_id=category.id)
        assert _costs(db, sub, mid, top) == pytest.approx([6.00, 12.00, 24.00])

        second = recost_all_items(db, category_id=category.id)
        changed = [row["sku"] for row in second["items"] if row["old_cost"] != row["new_cost"]]
        assert changed == []

    def test_sub_assembly_used_through_a_routing(
        self, db, make_product, make_bom, make_work_center, category
    ):
        """A sub-assembly used as a routing material is costed before its parent."""
        top = _made(make_product, category, "5.00")
        sub = _made(make_product, category, "1.00")
        part = _bought(make_product, category, "2.00")
        _routing_consuming(db, make_work_center, top, sub, "2")
        make_bom(sub.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])

        recost_all_items(db, category_id=category.id)

        assert _costs(db, sub, top) == pytest.approx([6.00, 12.00])

    def test_items_built_from_each_other_are_costed_once_and_reported(
        self, db, make_product, make_bom, category
    ):
        """A circular pair is costed once each and listed in circular_skus."""
        first = _made(make_product, category, "4.00")
        second = _made(make_product, category, "7.00")
        make_bom(first.id, lines=[{"component_id": second.id, "quantity": Decimal("1")}])
        make_bom(second.id, lines=[{"component_id": first.id, "quantity": Decimal("1")}])

        result = recost_all_items(db, category_id=category.id)

        assert sorted(row["sku"] for row in result["items"]) == sorted([first.sku, second.sku])
        assert sorted(result["circular_skus"]) == sorted([first.sku, second.sku])

    def test_no_circular_items_gives_an_empty_list(self, db, make_product, make_bom, category):
        """circular_skus is an empty list when nothing is circular."""
        sub = _made(make_product, category, "1.00")
        part = _bought(make_product, category, "2.00")
        make_bom(sub.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])

        result = recost_all_items(db, category_id=category.id)

        assert result["circular_skus"] == []

    def test_circular_items_are_logged(self, db, make_product, make_bom, category, monkeypatch):
        """A circular item's SKU is written to the warning log."""
        first = _made(make_product, category, "4.00")
        make_bom(first.id, lines=[{"component_id": first.id, "quantity": Decimal("1")}])
        warnings = []
        monkeypatch.setattr(
            item_cost_service.logger,
            "warning",
            lambda message, *args: warnings.append(message % args),
        )

        recost_all_items(db, category_id=category.id)

        assert any(first.sku in message for message in warnings)

    def test_manufactured_only_run_is_ordered_too(self, db, make_product, make_bom, category):
        """A run filtered to manufactured items is still components first."""
        top = _made(make_product, category, "5.00")
        sub = _made(make_product, category, "1.00")
        part = _bought(make_product, category, "2.00")
        make_bom(top.id, lines=[{"component_id": sub.id, "quantity": Decimal("2")}])
        make_bom(sub.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])

        recost_all_items(db, category_id=category.id, cost_source_filter="manufactured")

        assert _costs(db, sub, top) == pytest.approx([6.00, 12.00])

    def test_inactive_bom_is_not_a_dependency(self, db, make_product, make_bom, category):
        """A line on an inactive BOM does not count as a dependency."""
        # An old, inactive BOM of the sub-assembly lists the top item. Costing
        # does not read it, so it must not make the pair look circular.
        top = _made(make_product, category, "5.00")
        sub = _made(make_product, category, "1.00")
        part = _bought(make_product, category, "2.00")
        make_bom(top.id, lines=[{"component_id": sub.id, "quantity": Decimal("2")}])
        make_bom(sub.id, lines=[{"component_id": top.id, "quantity": Decimal("1")}], active=False)
        make_bom(sub.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])

        result = recost_all_items(db, category_id=category.id)

        assert result["circular_skus"] == []
        assert _costs(db, sub, top) == pytest.approx([6.00, 12.00])

    def test_inactive_operation_is_not_a_dependency(
        self, db, make_product, make_bom, make_work_center, category
    ):
        """A material on an inactive operation does not count as a dependency."""
        # ``first`` has a switched-off operation that used ``second``; costing
        # skips it. ``second`` really is built from ``first``.
        first = _made(make_product, category, "9.00")
        second = _made(make_product, category, "9.00")
        part = _bought(make_product, category, "2.00")
        _routing_consuming(db, make_work_center, first, second, "1", operation_active=False)
        make_bom(first.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])
        make_bom(second.id, lines=[{"component_id": first.id, "quantity": Decimal("2")}])

        result = recost_all_items(db, category_id=category.id)

        assert result["circular_skus"] == []
        assert _costs(db, first, second) == pytest.approx([6.00, 12.00])

    def test_older_routing_version_is_not_a_dependency(
        self, db, make_product, make_bom, make_work_center, category
    ):
        """Only the highest active routing version counts as a dependency."""
        # ``first`` has two active routings. Costing reads only version 2, which
        # uses a bought part. Version 1 used ``second``, which is built from
        # ``first``: that old edge must not make the pair look circular.
        first = _made(make_product, category, "9.00")
        second = _made(make_product, category, "9.00")
        part = _bought(make_product, category, "2.00")
        _routing_consuming(db, make_work_center, first, second, "1", version=1)
        _routing_consuming(db, make_work_center, first, part, "3", version=2)
        make_bom(second.id, lines=[{"component_id": first.id, "quantity": Decimal("2")}])

        result = recost_all_items(db, category_id=category.id)

        assert result["circular_skus"] == []
        assert _costs(db, first, second) == pytest.approx([6.00, 12.00])

    def test_routing_prices_a_sub_assembly_at_its_average_cost(
        self, db, make_product, make_bom, make_work_center, category
    ):
        """A routing uses a sub-assembly's average cost when it has one."""
        # A routing prices a component by its cost method. This sub-assembly
        # has an average cost, so the routing uses that, not the standard
        # cost the run has just given it.
        top = _made(make_product, category, "5.00")
        sub = make_product(
            item_type="component",
            procurement_type="make",
            standard_cost=Decimal("1.00"),
            average_cost=Decimal("4.00"),
            category_id=category.id,
        )
        part = _bought(make_product, category, "2.00")
        _routing_consuming(db, make_work_center, top, sub, "2")
        make_bom(sub.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])

        recost_all_items(db, category_id=category.id)

        assert _costs(db, sub, top) == pytest.approx([6.00, 8.00])

    def test_sub_assembly_outside_the_filter_keeps_its_stored_cost(
        self, db, make_product, make_bom, category
    ):
        """A sub-assembly outside the filter is not recosted."""
        # Recost All covers only the items the filter selects. A sub-assembly
        # outside it is not recosted, and its parent is costed from what is stored.
        top = _made(make_product, category, "5.00")
        outside = make_product(
            item_type="component", procurement_type="make", standard_cost=Decimal("1.00")
        )
        part = _bought(make_product, category, "2.00")
        make_bom(top.id, lines=[{"component_id": outside.id, "quantity": Decimal("2")}])
        make_bom(outside.id, lines=[{"component_id": part.id, "quantity": Decimal("3")}])

        recost_all_items(db, category_id=category.id)

        assert _costs(db, outside, top) == pytest.approx([1.00, 2.00])
