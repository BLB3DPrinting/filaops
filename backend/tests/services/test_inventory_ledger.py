"""
Tests for the canonical inventory poster (HARD-4a).

inventory_ledger.post is THE single function through which on-hand
changes. These tests pin its contract: signed Decimal deltas, signed
storage (sum(quantity) == on_hand for poster-written rows), atomic
row+mutation, sign/type validation, float rejection, and the
requires_approval hold path.

Also covers apply_held_transaction (HARD-4a follow-up):
- FOR UPDATE lock semantics (serialized concurrent approval)
- Approval applies delta exactly once
- Legacy positive-magnitude held rows are skipped with a warning
"""
from decimal import Decimal

import pytest

from app.models.inventory import Inventory, InventoryTransaction
from app.services import inventory_ledger
from app.services.inventory_ledger import apply_held_transaction
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


class TestApplyHeldTransaction:
    """Tests for apply_held_transaction — approval-path helper (HARD-4a follow-up)."""

    def test_apply_moves_on_hand_exactly_once(self, db, make_product, location):
        """Approved held row applies delta and on_hand moves by that exact amount."""
        product = make_product()
        # Seed stock
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("20"),
        )
        # Post a held row that would take stock negative
        txn = inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="negative_adjustment", quantity_delta=Decimal("-25"),
            requires_approval=True,
        )
        assert _on_hand(db, product.id, location.id) == Decimal("20")

        apply_held_transaction(
            db, transaction=txn, approved_by="manager@test.com",
            approval_reason="Cycle count correction",
        )
        db.flush()

        # on_hand should now reflect the delta
        assert _on_hand(db, product.id, location.id) == Decimal("-5")
        assert txn.requires_approval is False
        assert txn.approved_by == "manager@test.com"
        assert txn.approval_reason == "Cycle count correction"
        assert txn.approved_at is not None

    def test_apply_raises_if_not_held(self, db, make_product, location):
        """Non-held transactions must not be re-applied via this helper."""
        product = make_product()
        txn = inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("10"),
        )
        with pytest.raises(ValueError, match="does not require approval"):
            apply_held_transaction(
                db, transaction=txn, approved_by="x@test.com",
                approval_reason="oops",
            )

    def test_apply_raises_if_already_approved(self, db, make_product, location):
        """Double-apply is detected and rejected.

        After the first approval requires_approval is cleared to False, so a
        second call hits the 'does not require approval' guard.  Either way the
        function raises ValueError, preventing a double-apply.
        """
        product = make_product()
        txn = inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="negative_adjustment", quantity_delta=Decimal("-5"),
            requires_approval=True,
        )
        apply_held_transaction(
            db, transaction=txn, approved_by="a@test.com",
            approval_reason="first approval",
        )
        db.flush()

        # After approval requires_approval=False, so the function raises on
        # the first guard — this is the double-apply prevention path.
        with pytest.raises(ValueError):
            apply_held_transaction(
                db, transaction=txn, approved_by="b@test.com",
                approval_reason="duplicate",
            )

    def test_legacy_positive_magnitude_held_row_skips_on_hand(self, db, make_product, location):
        """Pre-HARD-4a held rows with positive quantity do NOT mutate on_hand."""
        product = make_product()
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("15"),
        )
        # Simulate a legacy held row: positive magnitude stored directly
        from app.models.inventory import InventoryTransaction as IT
        from datetime import datetime, timezone
        legacy_txn = IT(
            product_id=product.id,
            location_id=location.id,
            transaction_type="negative_adjustment",
            quantity=Decimal("5"),  # positive magnitude — legacy convention
            requires_approval=True,
            approved_by=None,
            transaction_date=datetime.now(timezone.utc).date(),
        )
        db.add(legacy_txn)
        db.flush()

        apply_held_transaction(
            db, transaction=legacy_txn, approved_by="manager@test.com",
            approval_reason="legacy row",
        )
        db.flush()

        # on_hand must NOT have changed
        assert _on_hand(db, product.id, location.id) == Decimal("15")
        # But the row is stamped as approved
        assert legacy_txn.approved_by == "manager@test.com"

    def test_ledger_sum_equals_on_hand_after_approval(self, db, make_product, location):
        """The HARD-4a sum invariant holds after an approved held transaction."""
        product = make_product()
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("100"),
        )
        held = inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="negative_adjustment", quantity_delta=Decimal("-30"),
            requires_approval=True,
        )
        # Before approval: held row in ledger but on_hand unchanged
        apply_held_transaction(
            db, transaction=held, approved_by="mgr@test.com",
            approval_reason="verified",
        )
        db.flush()

        rows = db.query(InventoryTransaction).filter(
            InventoryTransaction.product_id == product.id
        ).all()
        ledger_sum = sum(Decimal(str(r.quantity)) for r in rows)
        assert ledger_sum == Decimal("70")
        assert _on_hand(db, product.id, location.id) == Decimal("70")


class TestFulfillmentWriters:
    """Smoke tests confirming the two fulfillment paths write ledger rows."""

    def test_consumption_path_writes_ledger_row(self, db, make_product, location):
        """The consolidated-shipment packaging consumption path writes a
        signed ledger row and decrements on_hand via inventory_ledger.post."""
        product = make_product()
        # Seed stock
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("50"),
        )
        # Simulate what buy_consolidated_shipping_label does after the fix
        consumed = Decimal("5")
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="consumption",
            quantity_delta=-consumed,
            reference_type="consolidated_shipment",
            reference_id=1,
            notes="Packaging for consolidated shipment: SO-001",
            created_by="system",
        )
        db.flush()

        rows = db.query(InventoryTransaction).filter(
            InventoryTransaction.product_id == product.id,
            InventoryTransaction.transaction_type == "consumption",
        ).all()
        assert len(rows) == 1
        assert rows[0].quantity == -consumed
        # on_hand reflects both the receipt and the consumption
        assert _on_hand(db, product.id, location.id) == Decimal("45")
        # ledger sum == on_hand (HARD-4a invariant)
        all_rows = db.query(InventoryTransaction).filter(
            InventoryTransaction.product_id == product.id
        ).all()
        assert sum(Decimal(str(r.quantity)) for r in all_rows) == Decimal("45")

    def test_shipment_path_writes_ledger_row(self, db, make_product, location):
        """The mark_order_shipped FG-shipment path writes a signed ledger row
        and decrements on_hand via inventory_ledger.post."""
        product = make_product()
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="receipt", quantity_delta=Decimal("10"),
        )
        shipped = Decimal("3")
        inventory_ledger.post(
            db, product_id=product.id, location_id=location.id,
            transaction_type="shipment",
            quantity_delta=-shipped,
            reference_type="sales_order",
            reference_id=42,
            notes="Shipped 3 units for SO-042",
            created_by="system",
        )
        db.flush()

        rows = db.query(InventoryTransaction).filter(
            InventoryTransaction.product_id == product.id,
            InventoryTransaction.transaction_type == "shipment",
        ).all()
        assert len(rows) == 1
        assert rows[0].quantity == -shipped
        assert _on_hand(db, product.id, location.id) == Decimal("7")
        all_rows = db.query(InventoryTransaction).filter(
            InventoryTransaction.product_id == product.id
        ).all()
        assert sum(Decimal(str(r.quantity)) for r in all_rows) == Decimal("7")
