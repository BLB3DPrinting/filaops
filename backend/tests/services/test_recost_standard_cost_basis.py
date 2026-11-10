"""
Recost keeps standard_cost per purchase unit.

For a purchased item with no standard cost, Recost falls back to the average
cost (or the last cost) and writes it as the standard cost. Those two are per
STOCK unit ($/G); standard cost is per PURCHASE unit ($/KG). The fallback must
scale the value up, or Recost writes a per-gram figure into a per-KG field, the
same error the PO receipt sync used to make.
"""
from decimal import Decimal

import pytest

from app.services import item_service
from app.services.cost_basis import cost_per_stock_unit


@pytest.fixture
def received_filament_without_standard(make_product):
    """Filament stocked in G, bought in KG, average $0.02/G, no standard cost."""
    return make_product(
        item_type="material", unit="G", purchase_uom="KG",
        purchase_factor=Decimal("1000"), is_raw_material=True,
        average_cost=Decimal("0.02"),
    )


class TestCalculateItemCostPurchasedFallback:
    """calculate_item_cost for a purchased item with no standard cost."""

    def test_average_cost_is_scaled_to_the_purchase_unit(
        self, db, received_filament_without_standard,
    ):
        """$0.02/G average is a $20.00 standard cost, not $0.02."""
        result = item_service.calculate_item_cost(received_filament_without_standard, db)

        assert result["cost_source"] == "purchased"
        assert result["purchase_cost"] == pytest.approx(20.0)
        assert result["total_cost"] == pytest.approx(20.0)

    def test_last_cost_is_scaled_to_the_purchase_unit(self, db, make_product):
        """No standard or average cost: the per-gram last cost is scaled the same way."""
        item = make_product(
            item_type="material", unit="G", purchase_uom="KG",
            purchase_factor=Decimal("1000"), last_cost=Decimal("0.025"),
        )
        result = item_service.calculate_item_cost(item, db)

        assert result["purchase_cost"] == pytest.approx(25.0)

    def test_existing_standard_cost_is_used_as_it_is(self, db, make_product):
        """A standard cost that is already set is per purchase unit: no scaling."""
        item = make_product(
            item_type="material", unit="G", purchase_uom="KG",
            purchase_factor=Decimal("1000"),
            standard_cost=Decimal("22.99"), average_cost=Decimal("0.02"),
        )
        result = item_service.calculate_item_cost(item, db)

        assert result["purchase_cost"] == pytest.approx(22.99)

    def test_box_of_12_average_is_scaled_by_the_pack_size(self, db, make_product):
        """$2 each on average is $24 per box of 12."""
        item = make_product(
            item_type="component", unit="EA", purchase_uom="BOX",
            purchase_factor=Decimal("12"), average_cost=Decimal("2.00"),
        )
        result = item_service.calculate_item_cost(item, db)

        assert result["purchase_cost"] == pytest.approx(24.0)

    def test_each_item_average_is_unchanged(self, db, make_product):
        """Bought and stocked in EA: the average is the standard cost."""
        item = make_product(average_cost=Decimal("8.00"))
        result = item_service.calculate_item_cost(item, db)

        assert result["purchase_cost"] == pytest.approx(8.0)


class TestRecostItem:
    """recost_item writes a standard cost that reads back as the same stock cost."""

    def test_recost_does_not_write_a_per_gram_standard_cost(
        self, db, received_filament_without_standard,
    ):
        """After Recost the item costs $0.02/G whichever cost field is read."""
        item = received_filament_without_standard
        item_service.recost_item(db, item.id)
        db.refresh(item)

        assert item.standard_cost == Decimal("20")
        item.cost_method = "standard"
        assert cost_per_stock_unit(item) == Decimal("0.02")
