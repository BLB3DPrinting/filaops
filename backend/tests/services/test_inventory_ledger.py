"""
Tests for the canonical inventory poster (HARD-4a).

inventory_ledger.post is THE single function through which on-hand
changes. These tests pin its contract: signed Decimal deltas, signed
storage (sum(quantity) == on_hand for poster-written rows), atomic
row+mutation, sign/type validation, float rejection, and the
requires_approval hold path.
"""
from decimal import Decimal

import pytest

from app.models.inventory import Inventory, InventoryTransaction
from app.services import inventory_ledger
from app.services.inventory_service import get_or_create_default_location


@pytest.fixture
def location(db):
    return get_or_create_default_location(db)


def _on_hand(db, product_id, location_id):
    inv = db.query(Inventory).filter(
        Inventory.product_id == product_id,
        Inventory.location_id == location_id,
    ).first()
    return Decimal(str(inv.on_hand_quantity)) if inv else None


class TestPostBasics:
    def test_receipt_increases_on_hand(self, db, make_product, location):
        product = make_product()
        txn = inventory_ledger.post(
            db,
            product_id=product.id,
            location_id=location.id,
            transaction_type="receipt",
            quantity_delta=Decimal("250"),
            reference_type="purchase_order",
            reference_id=1,
        )
        assert txn.id is not None
        assert txn.quantity == Decimal("250")
        assert _on_hand(db, product.id, location.id) == Decimal("250")

    def test_consumption_decreases_on_hand(self, db, make_product, location):
        product = make_product()
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("100"),
        )
        txn = inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="consumption", quantity_delta=Decimal("-40"),
        )
        assert txn.quantity == Decimal("-40")
        assert _on_hand(db, product.id, location.id) == Decimal("60")

    def test_adjustment_accepts_both_signs(self, db, make_product, location):
        product = make_product()
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="adjustment", quantity_delta=Decimal("30"),
        )
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="adjustment", quantity_delta=Decimal("-10"),
        )
        assert _on_hand(db, product.id, location.id) == Decimal("20")

    def test_creates_inventory_row_when_missing(self, db, make_product, location):
        product = make_product()
        assert _on_hand(db, product.id, location.id) is None
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="initial", quantity_delta=Decimal("5"),
        )
        assert _on_hand(db, product.id, location.id) == Decimal("5")

    def test_ledger_sum_equals_on_hand(self, db, make_product, location):
        """The HARD-4a invariant: poster-written rows sum to on_hand."""
        product = make_product()
        deltas = [
            ("receipt", Decimal("100")),
            ("consumption", Decimal("-30")),
            ("adjustment", Decimal("12.5")),
            ("shipment", Decimal("-50")),
            ("adjustment", Decimal("-2.5")),
        ]
        for ttype, delta in deltas:
            inventory_ledger.post(
                db, product_id=product.id, location_id=location.id,
                transaction_type=ttype, quantity_delta=delta,
            )
        rows = db.query(InventoryTransaction).filter(
            InventoryTransaction.product_id == product.id
        ).all()
        ledger_sum = sum(Decimal(str(r.quantity)) for r in rows)
        assert ledger_sum == Decimal("30")
        assert _on_hand(db, product.id, location.id) == Decimal("30")

    def test_total_cost_uses_magnitude(self, db, make_product, location):
        product = make_product()
        txn = inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="consumption", quantity_delta=Decimal("-4"),
            cost_per_unit=Decimal("2.50"),
        )
        assert txn.total_cost == Decimal("10.00")


class TestValidation:
    def test_zero_delta_rejected(self, db, make_product, location):
        product = make_product()
        with pytest.raises(ValueError, match="Zero-quantity"):
            inventory_ledger.post(
                db, product_id=product.id, location_id=location.id,
                transaction_type="adjustment", quantity_delta=Decimal("0"),
            )

    def test_unknown_type_rejected(self, db, make_product, location):
        product = make_product()
        with pytest.raises(ValueError, match="Unknown transaction_type"):
            inventory_ledger.post(
                db, product_id=product.id, location_id=location.id,
                transaction_type="teleport", quantity_delta=Decimal("1"),
            )

    def test_receipt_must_be_positive(self, db, make_product, location):
        product = make_product()
        with pytest.raises(ValueError, match="must increase"):
            inventory_ledger.post(
                db, product_id=product.id, location_id=location.id,
                transaction_type="receipt", quantity_delta=Decimal("-1"),
            )

    def test_consumption_must_be_negative(self, db, make_product, location):
        product = make_product()
        with pytest.raises(ValueError, match="must decrease"):
            inventory_ledger.post(
                db, product_id=product.id, location_id=location.id,
                transaction_type="consumption", quantity_delta=Decimal("1"),
            )

    def test_float_delta_rejected(self, db, make_product, location):
        product = make_product()
        with pytest.raises(TypeError, match="Decimal"):
            inventory_ledger.post(
                db, product_id=product.id, location_id=location.id,
                transaction_type="receipt", quantity_delta=1.5,
            )

    def test_float_cost_rejected(self, db, make_product, location):
        product = make_product()
        with pytest.raises(TypeError, match="Decimal"):
            inventory_ledger.post(
                db, product_id=product.id, location_id=location.id,
                transaction_type="receipt", quantity_delta=Decimal("1"),
                cost_per_unit=2.5,
            )


class TestApprovalHold:
    def test_held_row_does_not_mutate_on_hand(self, db, make_product, location):
        product = make_product()
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("10"),
        )
        txn = inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="negative_adjustment", quantity_delta=Decimal("-50"),
            requires_approval=True,
        )
        assert txn.requires_approval is True
        assert txn.quantity == Decimal("-50")
        # on_hand untouched by the held row
        assert _on_hand(db, product.id, location.id) == Decimal("10")
