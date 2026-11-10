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
