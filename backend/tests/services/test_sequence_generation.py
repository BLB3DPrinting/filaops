"""
Unit tests for HARD-10: hardened document-number sequence generators.

Covers:
- generate_po_number (purchase_order_service): regex+numeric-cast generator
- generate_production_order_code (production_order_service): same pattern

Key scenarios:
- Empty table → returns YYYY-0001
- Normal sequence → increments correctly
- Mixed-width existing data (3-digit 027 + 4-digit 0026) → picks numeric max
- Gap in sequence (no 999→1000 lexicographic failure) → correct next value
- Year rollover → starts fresh at 0001 for new year
- Non-conforming rows filtered by regex → do not corrupt sequence
- 4-digit zero-padding enforced
"""
from datetime import datetime, timezone

from app.services.purchase_order_service import generate_po_number
from app.services.production_order_service import generate_production_order_code
from app.models.purchase_order import PurchaseOrder
from app.models.production_order import ProductionOrder


CURRENT_YEAR = datetime.now(timezone.utc).year


# =============================================================================
# Helpers
# =============================================================================

def _make_po(db, po_number, vendor_id=None):
    """Insert a bare PurchaseOrder with the given po_number."""
    po = PurchaseOrder(
        po_number=po_number,
        vendor_id=vendor_id,
        status="draft",
        created_by="1",
    )
    db.add(po)
    db.flush()
    return po


def _make_prod_order(db, code, product_id):
    """Insert a bare ProductionOrder with the given code."""
    po = ProductionOrder(
        code=code,
        product_id=product_id,
        quantity_ordered=1,
        status="draft",
        source="manual",
    )
    db.add(po)
    db.flush()
    return po


# =============================================================================
# generate_po_number
# =============================================================================

class TestGeneratePoNumberHardened:
    """Tests for the hardened generate_po_number."""

    def test_empty_table_returns_0001(self, db, make_vendor):
        """With no matching POs, the first number is PO-YYYY-0001."""
        result = generate_po_number(db)
        assert result == f"PO-{CURRENT_YEAR}-0001"

    def test_four_digit_padding(self, db, make_vendor):
        """Generated numbers use 4-digit zero-padding."""
        suffix = generate_po_number(db).split("-")[2]
        assert len(suffix) == 4

    def test_normal_increment(self, db, make_vendor):
        """Normal case: PO-YYYY-0005 → PO-YYYY-0006."""
        vendor = make_vendor()
        _make_po(db, f"PO-{CURRENT_YEAR}-0005", vendor.id)
        db.commit()
        assert generate_po_number(db) == f"PO-{CURRENT_YEAR}-0006"

    def test_mixed_width_picks_numeric_max(self, db, make_vendor):
        """Mixed-width data: 3-digit 027 and 4-digit 0026 → next is 0028.

        Lexicographic sort would give 027 > 0026 → next = 028 (wrong).
        Numeric max gives max(27, 26) = 27 → next = 28.
        """
        vendor = make_vendor()
        _make_po(db, f"PO-{CURRENT_YEAR}-027", vendor.id)
        _make_po(db, f"PO-{CURRENT_YEAR}-0026", vendor.id)
        db.commit()
        result = generate_po_number(db)
        assert result == f"PO-{CURRENT_YEAR}-0028"

    def test_high_sequence_999_to_1000(self, db, make_vendor):
        """Sequence rolls past 999 → 1000 without lexicographic failure."""
        vendor = make_vendor()
        _make_po(db, f"PO-{CURRENT_YEAR}-0999", vendor.id)
        db.commit()
        result = generate_po_number(db)
        assert result == f"PO-{CURRENT_YEAR}-1000"

    def test_non_conforming_rows_ignored(self, db, make_vendor):
        """Rows that don't match ^PO-YYYY-[digits]+$ are excluded by the regex filter."""
        vendor = make_vendor()
        # These should not affect the sequence
        _make_po(db, f"PO-{CURRENT_YEAR}-abc", vendor.id)
        _make_po(db, f"PO-{CURRENT_YEAR}-027-extra", vendor.id)
        db.commit()
        result = generate_po_number(db)
        # Should start at 0001 since no conforming rows exist
        assert result == f"PO-{CURRENT_YEAR}-0001"

    def test_year_rollover_starts_fresh(self, db, make_vendor):
        """POs from a different year do not affect the current year's sequence."""
        vendor = make_vendor()
        prev_year = CURRENT_YEAR - 1
        _make_po(db, f"PO-{prev_year}-0999", vendor.id)
        db.commit()
        result = generate_po_number(db)
        assert result == f"PO-{CURRENT_YEAR}-0001"

    def test_year_suffix_in_result(self, db):
        """Result always contains current year as second segment."""
        result = generate_po_number(db)
        parts = result.split("-")
        assert len(parts) == 3
        assert parts[0] == "PO"
        assert parts[1] == str(CURRENT_YEAR)
        assert parts[2].isdigit()


# =============================================================================
# generate_production_order_code
# =============================================================================

class TestGenerateProductionOrderCodeHardened:
    """Tests for the hardened generate_production_order_code."""

    def test_empty_table_returns_0001(self, db):
        """With no matching production orders, the first code is PO-YYYY-0001."""
        result = generate_production_order_code(db)
        assert result == f"PO-{CURRENT_YEAR}-0001"

    def test_four_digit_padding(self, db):
        """Generated codes use 4-digit zero-padding."""
        suffix = generate_production_order_code(db).split("-")[2]
        assert len(suffix) == 4

    def test_normal_increment(self, db, make_product):
        """Normal case: PO-YYYY-0010 → PO-YYYY-0011."""
        product = make_product()
        _make_prod_order(db, f"PO-{CURRENT_YEAR}-0010", product.id)
        db.commit()
        assert generate_production_order_code(db) == f"PO-{CURRENT_YEAR}-0011"

    def test_mixed_width_picks_numeric_max(self, db, make_product):
        """Mixed-width data handled correctly using numeric max not lexicographic."""
        product = make_product()
        _make_prod_order(db, f"PO-{CURRENT_YEAR}-027", product.id)
        _make_prod_order(db, f"PO-{CURRENT_YEAR}-0026", product.id)
        db.commit()
        result = generate_production_order_code(db)
        assert result == f"PO-{CURRENT_YEAR}-0028"

    def test_high_sequence_999_to_1000(self, db, make_product):
        """Sequence correctly increments from 999 to 1000."""
        product = make_product()
        _make_prod_order(db, f"PO-{CURRENT_YEAR}-0999", product.id)
        db.commit()
        result = generate_production_order_code(db)
        assert result == f"PO-{CURRENT_YEAR}-1000"

    def test_non_conforming_rows_ignored(self, db, make_product):
        """Non-conforming codes excluded by regex filter."""
        product = make_product()
        # "abc" suffix is non-numeric → filtered by regex
        _make_prod_order(db, f"PO-{CURRENT_YEAR}-abc", product.id)
        # WO- prefix doesn't match PO- pattern at all
        _make_prod_order(db, f"WO-{CURRENT_YEAR}-0050", product.id)
        db.commit()
        result = generate_production_order_code(db)
        assert result == f"PO-{CURRENT_YEAR}-0001"

    def test_year_rollover_starts_fresh(self, db, make_product):
        """Codes from a prior year do not pollute the current year's sequence."""
        product = make_product()
        prev_year = CURRENT_YEAR - 1
        _make_prod_order(db, f"PO-{prev_year}-0999", product.id)
        db.commit()
        result = generate_production_order_code(db)
        assert result == f"PO-{CURRENT_YEAR}-0001"

    def test_wo_prefixed_codes_not_counted(self, db, make_product):
        """WO-prefixed production orders (e.g. from test fixtures) are ignored."""
        product = make_product()
        _make_prod_order(db, f"WO-{CURRENT_YEAR}-0100", product.id)
        _make_prod_order(db, f"WO-{CURRENT_YEAR}-0200", product.id)
        db.commit()
        result = generate_production_order_code(db)
        assert result == f"PO-{CURRENT_YEAR}-0001"
