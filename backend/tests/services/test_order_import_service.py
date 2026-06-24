"""Tests for order_import_service correctness fixes (#785).

Covers: canonical customer-number format, canonical :03d SO numbers,
quantity validation as row errors, and source_order_id dedup.

The importer commits per order, so assertions look up the specific row by its
unique source_order_id and check formats (not exact sequence values), which is
robust to the shared test DB accumulating data across runs.
"""
import re
import uuid

import pytest

from app.models.sales_order import SalesOrder
from app.services.order_import_service import (
    find_or_create_customer,
    import_orders_from_csv,
)


def _uniq(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


class TestFindOrCreateCustomer:
    def test_uses_canonical_customer_number_format(self, db):
        """New import customers get the canonical CUST-NNN number (regex
        generator), not the old two-hyphen CUST-YYYY-NNNNNN format."""
        email = f"{_uniq('importcust')}@example.com"
        cust = find_or_create_customer(db, email, name="Jane Doe")
        db.flush()
        assert cust is not None
        assert re.match(r"^CUST-\d+$", cust.customer_number or ""), cust.customer_number


class TestImportOrdersCorrectness:
    def _csv(self, *, src_id, sku, qty="2", price="10.00", email=None):
        email = email or f"{_uniq('buyer')}@example.com"
        return (
            "Order ID,Email,SKU,Quantity,Unit Price\n"
            f"{src_id},{email},{sku},{qty},{price}\n"
        )

    def test_generates_canonical_so_number(self, db, make_product):
        """Imported orders get a canonical :03d SO number, not the :06d format."""
        sku = _uniq("IMP")
        make_product(sku=sku, name="Imported Widget")
        src_id = _uniq("SRC")
        res = import_orders_from_csv(
            db, self._csv(src_id=src_id, sku=sku), current_user_id=1
        )
        assert res["created"] == 1, res
        so = db.query(SalesOrder).filter(SalesOrder.source_order_id == src_id).first()
        assert so is not None
        # SO-YYYY-NNN — exactly three digits in the sequence segment (the old
        # bug zero-padded to six: SO-YYYY-000001).
        assert re.match(r"^SO-\d{4}-\d{3}$", so.order_number), so.order_number

    def test_rejects_fractional_quantity(self, db, make_product):
        """A fractional quantity is a row error, not silently truncated."""
        sku = _uniq("IMP")
        make_product(sku=sku, name="Imported Widget")
        src_id = _uniq("SRC")
        res = import_orders_from_csv(
            db, self._csv(src_id=src_id, sku=sku, qty="2.5"), current_user_id=1
        )
        assert res["created"] == 0, res
        assert db.query(SalesOrder).filter(SalesOrder.source_order_id == src_id).first() is None
        assert any("quantity" in (e.get("error", "").lower()) for e in res["errors"]), res["errors"]

    def test_rejects_nonpositive_quantity(self, db, make_product):
        """A zero/negative quantity is a row error, not coerced to 1."""
        sku = _uniq("IMP")
        make_product(sku=sku, name="Imported Widget")
        src_id = _uniq("SRC")
        res = import_orders_from_csv(
            db, self._csv(src_id=src_id, sku=sku, qty="0"), current_user_id=1
        )
        assert res["created"] == 0, res
        assert any("quantity" in (e.get("error", "").lower()) for e in res["errors"]), res["errors"]

    def test_dedupes_source_order_id(self, db, make_product):
        """Re-importing the same source_order_id is skipped, not duplicated."""
        sku = _uniq("IMP")
        make_product(sku=sku, name="Imported Widget")
        src_id = _uniq("SRC")
        csv_text = self._csv(src_id=src_id, sku=sku)

        first = import_orders_from_csv(db, csv_text, current_user_id=1)
        assert first["created"] == 1, first

        second = import_orders_from_csv(db, csv_text, current_user_id=1)
        assert second["created"] == 0, second
        assert second["skipped"] >= 1
        # Exactly one order persisted for this source id.
        assert (
            db.query(SalesOrder).filter(SalesOrder.source_order_id == src_id).count() == 1
        )
