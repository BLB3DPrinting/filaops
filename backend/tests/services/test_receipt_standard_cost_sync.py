"""
PO receipt keeps standard_cost per purchase unit.

Receiving a purchase order updates average_cost (per stock unit, $/G) and then
syncs standard_cost for purchased items. standard_cost is per PURCHASE unit
($/KG), so the sync must scale the average back up. It used to copy the
per-gram average straight in, which silently changed a filament's standard cost
from $20.00 to $0.0200 on its first receipt.

These tests drive the real receive_purchase_order service.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.purchase_order import PurchaseOrderLine
from app.models.uom import UnitOfMeasure
from app.services.cost_basis import cost_per_stock_unit
from app.services.purchase_order_service import receive_purchase_order


def _add_line(db, po, product, quantity, unit_cost, purchase_unit):
    """Add one PO line for the product."""
    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        line_number=len(po.lines) + 1,
        product_id=product.id,
        quantity_ordered=quantity,
        quantity_received=Decimal("0"),
        purchase_unit=purchase_unit,
        unit_cost=unit_cost,
        line_total=quantity * unit_cost,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    po.lines.append(line)
    db.flush()
    return line


def _receive(db, make_vendor, make_purchase_order, product, quantity, unit_cost, purchase_unit):
    """Create an ordered PO with one line, receive it in full, refresh the product."""
    po = make_purchase_order(vendor_id=make_vendor().id, status="ordered")
    line = _add_line(db, po, product, Decimal(str(quantity)), Decimal(str(unit_cost)), purchase_unit)
    receive_purchase_order(
        db, po.id,
        lines=[{"line_id": line.id, "quantity_received": line.quantity_ordered}],
        user_id=1, user_email="test@filaops.dev",
    )
    db.refresh(product)
    return product


@pytest.fixture
def filament(make_product):
    """Filament stocked in G, bought in KG, with a $20.00/KG standard cost."""
    return make_product(
        item_type="material", unit="G", purchase_uom="KG",
        purchase_factor=Decimal("1000"), is_raw_material=True,
        standard_cost=Decimal("20.00"),
    )


class TestReceiptStandardCostSync:
    """standard_cost after a receipt is still per purchase unit."""

    def test_filament_standard_cost_stays_per_kg(
        self, db, filament, make_vendor, make_purchase_order,
    ):
        """3 KG at $12.67/KG: average is $0.0127/G and standard is $12.67/KG, not $0.0127."""
        _receive(db, make_vendor, make_purchase_order, filament, 3, "12.67", "KG")

        assert Decimal(str(filament.average_cost)) == Decimal("0.0127")
        assert Decimal(str(filament.standard_cost)) == Decimal("12.67")

    def test_standard_cost_comes_from_the_unrounded_average(
        self, db, filament, make_vendor, make_purchase_order,
    ):
        """$14.99/KG stores a per-gram average of $0.0150 (4 decimal places).
        Standard cost is built from the unrounded $0.01499, so it is $14.99 and
        not the $15.00 that scaling the rounded average would give."""
        _receive(db, make_vendor, make_purchase_order, filament, 1, "14.99", "KG")

        assert Decimal(str(filament.average_cost)) == Decimal("0.015")
        assert Decimal(str(filament.standard_cost)) == Decimal("14.99")

    def test_both_cost_fields_give_the_same_cost_per_gram(
        self, db, filament, make_vendor, make_purchase_order,
    ):
        """An average-cost and a standard-cost reading of the item agree after a receipt."""
        _receive(db, make_vendor, make_purchase_order, filament, 3, "20.00", "KG")

        as_average = cost_per_stock_unit(filament)
        filament.cost_method = "standard"
        as_standard = cost_per_stock_unit(filament)
        assert as_average == Decimal("0.02")
        assert as_standard == Decimal("0.02")

    def test_second_receipt_uses_the_weighted_average(
        self, db, filament, make_vendor, make_purchase_order,
    ):
        """1 KG at $20 then 1 KG at $30: average $0.025/G, standard $25.00/KG."""
        _receive(db, make_vendor, make_purchase_order, filament, 1, "20.00", "KG")
        _receive(db, make_vendor, make_purchase_order, filament, 1, "30.00", "KG")

        assert Decimal(str(filament.average_cost)) == Decimal("0.025")
        assert Decimal(str(filament.standard_cost)) == Decimal("25")

    def test_material_saved_as_g_ea_1000_scales_by_its_factor(
        self, db, make_product, make_vendor, make_purchase_order,
    ):
        """A G / EA / 1000 material received in grams at $0.02/G: standard is $20 per EA (1000 G)."""
        material = make_product(
            item_type="material", unit="G", purchase_uom="EA",
            purchase_factor=Decimal("1000"), is_raw_material=True,
        )
        _receive(db, make_vendor, make_purchase_order, material, 5000, "0.02", "G")

        assert Decimal(str(material.average_cost)) == Decimal("0.02")
        assert Decimal(str(material.standard_cost)) == Decimal("20")

    def test_each_item_is_unchanged(self, db, make_product, make_vendor, make_purchase_order):
        """Bought and stocked in EA: standard cost equals the average, as before."""
        part = make_product(item_type="component", unit="EA", purchase_uom="EA")
        _receive(db, make_vendor, make_purchase_order, part, 10, "5.00", "EA")

        assert Decimal(str(part.average_cost)) == Decimal("5")
        assert Decimal(str(part.standard_cost)) == Decimal("5")


@pytest.fixture
def weight_units(db):
    """The weight rows of the unit table, as the standard unit seed creates them.

    Receiving a material bought in one weight unit and stocked in another reads
    the purchase-unit-to-gram cost factor from the unit table, with no built-in
    fallback, so a line in LB needs these rows to be received at all.
    """
    for code, name, factor in (
        ("KG", "Kilogram", "1"), ("G", "Gram", "0.001"), ("LB", "Pound", "0.453592"),
    ):
        if not db.query(UnitOfMeasure).filter(UnitOfMeasure.code == code).first():
            db.add(UnitOfMeasure(
                code=code, name=name, uom_class="weight", to_base_factor=Decimal(factor),
            ))
    db.flush()


class TestReceiptStandardCostSyncMaterialStockedByWeight:
    """A material stocked in KG, LB or OZ.

    Receiving posts it in grams and stores its average cost per gram, whatever
    the stock unit. The standard cost is still per purchase unit, so it must be
    the per-gram average times the grams in one purchase unit. Scaling by the
    stock-to-purchase conversion alone (1 for KG / KG) left $0.0200 where
    $20.00 belongs.
    """

    def test_kg_stocked_kg_bought_stays_per_kg(
        self, db, make_product, make_vendor, make_purchase_order,
    ):
        """3 KG at $20.00/KG: average is $0.02/G and standard is $20.00/KG, not $0.0200."""
        material = make_product(
            item_type="material", unit="KG", purchase_uom="KG",
            is_raw_material=True, standard_cost=Decimal("20.00"),
        )
        _receive(db, make_vendor, make_purchase_order, material, 3, "20.00", "KG")

        assert Decimal(str(material.average_cost)) == Decimal("0.02")
        assert Decimal(str(material.standard_cost)) == Decimal("20")

    def test_next_receipt_corrects_a_standard_cost_saved_per_gram(
        self, db, make_product, make_vendor, make_purchase_order,
    ):
        """A standard cost an earlier receipt saved as $0.0200 is $20.00 after the next receipt."""
        material = make_product(
            item_type="material", unit="KG", purchase_uom="KG", is_raw_material=True,
            standard_cost=Decimal("0.02"), average_cost=Decimal("0.02"),
        )
        _receive(db, make_vendor, make_purchase_order, material, 1, "20.00", "KG")

        assert Decimal(str(material.standard_cost)) == Decimal("20")

    def test_kg_stocked_standard_cost_comes_from_the_unrounded_average(
        self, db, make_product, make_vendor, make_purchase_order,
    ):
        """$12.67/KG stores $0.0127/G; standard is $12.67, not $12.70."""
        material = make_product(
            item_type="material", unit="KG", purchase_uom="KG", is_raw_material=True,
        )
        _receive(db, make_vendor, make_purchase_order, material, 3, "12.67", "KG")

        assert Decimal(str(material.average_cost)) == Decimal("0.0127")
        assert Decimal(str(material.standard_cost)) == Decimal("12.67")

    def test_kg_stocked_second_receipt_uses_the_weighted_average(
        self, db, make_product, make_vendor, make_purchase_order,
    ):
        """1 KG at $20 then 1 KG at $30: average $0.025/G, standard $25.00/KG."""
        material = make_product(
            item_type="material", unit="KG", purchase_uom="KG", is_raw_material=True,
        )
        _receive(db, make_vendor, make_purchase_order, material, 1, "20.00", "KG")
        _receive(db, make_vendor, make_purchase_order, material, 1, "30.00", "KG")

        assert Decimal(str(material.average_cost)) == Decimal("0.025")
        assert Decimal(str(material.standard_cost)) == Decimal("25")

    def test_lb_stocked_lb_bought_stays_per_lb(
        self, db, make_product, make_vendor, make_purchase_order,
    ):
        """2 LB at $9.07/LB: average is $0.02/G and standard is $9.07/LB."""
        material = make_product(
            item_type="material", unit="LB", purchase_uom="LB", is_raw_material=True,
        )
        _receive(db, make_vendor, make_purchase_order, material, 2, "9.07", "LB")

        assert Decimal(str(material.average_cost)) == Decimal("0.02")
        assert Decimal(str(material.standard_cost)) == Decimal("9.07")

    def test_oz_stocked_oz_bought_stays_per_oz(
        self, db, make_product, make_vendor, make_purchase_order,
    ):
        """16 OZ at $0.57/OZ: average is $0.0201/G and standard is $0.57/OZ."""
        material = make_product(
            item_type="material", unit="OZ", purchase_uom="OZ", is_raw_material=True,
        )
        _receive(db, make_vendor, make_purchase_order, material, 16, "0.57", "OZ")

        assert Decimal(str(material.average_cost)) == Decimal("0.0201")
        assert Decimal(str(material.standard_cost)) == Decimal("0.57")

    def test_kg_stocked_lb_bought_is_per_lb(
        self, db, make_product, make_vendor, make_purchase_order, weight_units,
    ):
        """Stocked by the KG, bought by the LB at $9.07/LB: standard is $9.07/LB."""
        material = make_product(
            item_type="material", unit="KG", purchase_uom="LB", is_raw_material=True,
        )
        _receive(db, make_vendor, make_purchase_order, material, 2, "9.07", "LB")

        assert Decimal(str(material.average_cost)) == Decimal("0.02")
        assert Decimal(str(material.standard_cost)) == Decimal("9.07")

    def test_non_material_stocked_in_kg_is_unchanged(
        self, db, make_product, make_vendor, make_purchase_order,
    ):
        """A supply stocked by the KG is received in KG: average and standard are both $20.00/KG."""
        supply = make_product(item_type="supply", unit="KG", purchase_uom="KG")
        _receive(db, make_vendor, make_purchase_order, supply, 3, "20.00", "KG")

        assert Decimal(str(supply.average_cost)) == Decimal("20")
        assert Decimal(str(supply.standard_cost)) == Decimal("20")
