"""Regression tests for the quote-discount review findings (PR #1091 review).

1. A 100%-discounted quote converts to a $0 order, not a full-price one.
2. Reopening and saving a quote does not apply the customer's price-level
   discount a second time (save and preview alike).
3. A fully discounted order line reports a $0 line total.
4. The quote-totals preview keeps a saved quote's discount when the request
   leaves the discount fields out.
5. Discount values with more than two decimal places are rejected.
6. The price-level step rounds an exact half cent up.
7. A header-only order's invoice total equals the order total.
"""
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.quotes import (
    ManualQuoteCreate,
    ManualQuoteUpdate,
    QuoteLineCreate,
    QuoteTotalsPreview,
)
from app.models.sales_order import SalesOrder
from app.models.user import User
from app.services import invoice_service, quote_service, quote_totals

D = Decimal


@pytest.fixture
def item(make_product):
    return make_product(name="Bracket", selling_price=D("100.00"))


@pytest.fixture
def price_level_10(monkeypatch):
    """The customer is on a 10% price level (PRO price levels, stubbed)."""
    monkeypatch.setattr(quote_service, "_get_customer_discount", lambda db, customer_id: D("10"))


@pytest.fixture
def customer(db):
    uid = uuid.uuid4().hex[:8]
    user = User(
        customer_number=f"CUST-R-{uid}",
        email=f"review-{uid}@test.com",
        password_hash="not-real-hash",
        status="active",
        account_type="customer",
        email_verified=False,
    )
    db.add(user)
    db.flush()
    return user


def _line(item, **kw):
    fields = dict(product_id=item.id, product_name=item.name, quantity=1, unit_price=D("100.00"))
    fields.update(kw)
    return QuoteLineCreate(**fields)


def _reopened(saved_line, item):
    """The line the quote form sends back after reopening a saved quote."""
    return QuoteLineCreate(
        product_id=item.id,
        product_name=item.name,
        quantity=saved_line.quantity,
        unit_price=saved_line.unit_price,
        price_level_percent_applied=saved_line.discount_percent,
    )


class TestFullyDiscountedQuoteConversion:
    def test_100_percent_quote_discount_converts_to_zero_order(self, db, item):
        q = quote_service.create_quote(
            db,
            ManualQuoteCreate(lines=[_line(item)], apply_tax=False, shipping_cost=D("10.00"),
                              discount_type="percent", discount_value=D("100")),
            user_id=1,
        )
        assert q.subtotal == D("0.00")
        assert q.total_price == D("10.00")  # shipping only
        q.status = "approved"
        db.flush()
        result = quote_service.convert_quote_to_order(db, q.id)
        order = db.query(SalesOrder).filter(SalesOrder.id == result["order_id"]).one()
        assert order.total_price == D("0.00")
        assert order.grand_total == D("10.00") == q.total_price

    def test_100_percent_single_item_quote_converts_to_zero_order(self, db):
        q = quote_service.create_quote(
            db,
            ManualQuoteCreate(product_name="Part", quantity=1, unit_price=D("100.00"), apply_tax=False,
                              discount_type="percent", discount_value=D("100")),
            user_id=1,
        )
        q.status = "approved"
        db.flush()
        result = quote_service.convert_quote_to_order(db, q.id)
        order = db.query(SalesOrder).filter(SalesOrder.id == result["order_id"]).one()
        assert order.grand_total == D("0.00")

    def test_fully_discounted_order_line_reports_zero(self, db, client, item):
        q = quote_service.create_quote(
            db,
            ManualQuoteCreate(lines=[_line(item, discount_type="percent", discount_value=D("100"))], apply_tax=False),
            user_id=1,
        )
        q.status = "approved"
        db.flush()
        order_id = quote_service.convert_quote_to_order(db, q.id)["order_id"]
        resp = client.get(f"/api/v1/sales-orders/{order_id}")
        assert resp.status_code == 200, resp.text
        line = resp.json()["lines"][0]
        assert D(str(line["total"])) == D("0")


class TestPriceLevelAppliedOnce:
    def test_unchanged_reopen_and_save_keeps_line_totals(self, db, item, customer, price_level_10):
        q = quote_service.create_quote(
            db, ManualQuoteCreate(lines=[_line(item)], customer_id=customer.id, apply_tax=False), user_id=1
        )
        saved = q.lines[0]
        assert (saved.unit_price, saved.total, saved.discount_percent) == (D("90.00"), D("90.00"), D("10.00"))

        for _ in range(2):  # every save, not just the first
            q = quote_service.update_quote(
                db, q.id, ManualQuoteUpdate(lines=[_reopened(q.lines[0], item)])
            )
            line = q.lines[0]
            assert (line.unit_price, line.total, line.discount_percent) == (D("90.00"), D("90.00"), D("10.00"))
            assert q.total_price == D("90.00")

    def test_preview_of_reopened_quote_matches_saved(self, db, item, customer, price_level_10):
        q = quote_service.create_quote(
            db, ManualQuoteCreate(lines=[_line(item)], customer_id=customer.id, apply_tax=False), user_id=1
        )
        preview = quote_totals.preview_for_request(
            db, QuoteTotalsPreview(quote_id=q.id, lines=[_reopened(q.lines[0], item)])
        )
        assert preview["subtotal"] == D("90.00")
        assert preview["total"] == q.total_price

    def test_list_price_still_gets_the_price_level(self, db, item, customer, price_level_10):
        q = quote_service.create_quote(
            db, ManualQuoteCreate(lines=[_line(item)], customer_id=customer.id, apply_tax=False), user_id=1
        )
        # A newly typed price (no marker) is a list price: the level applies once.
        q = quote_service.update_quote(db, q.id, ManualQuoteUpdate(lines=[_line(item, unit_price=D("50.00"))]))
        assert q.lines[0].unit_price == D("45.00")


class TestPreviewKeepsStoredDiscount:
    def test_omitted_discount_fields_use_the_saved_discount(self, db, item):
        q = quote_service.create_quote(
            db,
            ManualQuoteCreate(lines=[_line(item)], apply_tax=False, discount_type="percent", discount_value=D("10")),
            user_id=1,
        )
        preview = quote_totals.preview_for_request(db, QuoteTotalsPreview(quote_id=q.id, lines=[_line(item)]))
        assert preview["discount_amount"] == D("10.00")
        assert preview["total"] == D("90.00")

        saved = quote_service.update_quote(db, q.id, ManualQuoteUpdate(lines=[_line(item)]))
        assert saved.total_price == preview["total"]

    def test_explicit_null_previews_removing_the_discount(self, db, item):
        q = quote_service.create_quote(
            db,
            ManualQuoteCreate(lines=[_line(item)], apply_tax=False, discount_type="percent", discount_value=D("10")),
            user_id=1,
        )
        preview = quote_totals.preview_for_request(
            db, QuoteTotalsPreview(quote_id=q.id, lines=[_line(item)], discount_type=None, discount_value=None)
        )
        assert preview["discount_amount"] == D("0")
        assert preview["total"] == D("100.00")


class TestDiscountPrecision:
    @pytest.mark.parametrize("model, extra", [
        (QuoteLineCreate, {"product_name": "A", "unit_price": D("1000")}),
        (ManualQuoteCreate, {}),
        (ManualQuoteUpdate, {}),
    ])
    def test_three_decimal_places_rejected(self, model, extra):
        with pytest.raises(ValidationError):
            model(discount_type="percent", discount_value=D("0.005"), **extra)

    def test_preview_rejects_three_decimal_places(self):
        with pytest.raises(ValidationError):
            QuoteTotalsPreview(
                lines=[QuoteLineCreate(product_name="A", unit_price=D("1"))],
                discount_type="amount", discount_value=D("1.005"),
            )

    def test_two_decimal_places_accepted(self):
        assert ManualQuoteUpdate(discount_type="percent", discount_value=D("12.50")).discount_value == D("12.50")


class TestHalfCentRounding:
    def test_price_level_rounds_half_up(self):
        # $2.01 at 50% is $1.005: half up gives $1.01 (half even gave $1.00).
        assert quote_totals.apply_price_level(D("2.01"), 1, D("50")) == D("1.01")


class TestHeaderOnlyInvoice:
    def test_invoice_total_equals_order_total_when_unit_price_does_not_divide(self, db):
        # A multi-line portal quote becomes a header-only order whose unit
        # price is the subtotal divided by the quantity: 100.00 / 3 = 33.33.
        order = SalesOrder(
            order_number=f"SO-R-{uuid.uuid4().hex[:8]}",
            user_id=1,
            order_type="quote_based",
            product_name="Mixed parts",
            material_type="PLA",
            quantity=3,
            unit_price=D("33.33"),
            total_price=D("100.00"),
            tax_amount=D("0"),
            shipping_cost=D("0"),
            grand_total=D("100.00"),
            status="confirmed",
        )
        db.add(order)
        db.flush()
        invoice = invoice_service.create_invoice(db, order.id)
        assert invoice.subtotal == D("100.00")
        assert invoice.total == order.grand_total

    def test_header_only_invoice_with_order_discount(self, db):
        order = SalesOrder(
            order_number=f"SO-R-{uuid.uuid4().hex[:8]}",
            user_id=1,
            order_type="quote_based",
            product_name="Mixed parts",
            material_type="PLA",
            quantity=3,
            unit_price=D("33.33"),
            total_price=D("90.00"),  # after the 10% order discount
            discount_type="percent",
            discount_value=D("10"),
            discount_amount=D("10.00"),
            tax_amount=D("0"),
            shipping_cost=D("0"),
            grand_total=D("90.00"),
            status="confirmed",
        )
        db.add(order)
        db.flush()
        invoice = invoice_service.create_invoice(db, order.id)
        assert invoice.subtotal == D("100.00")
        assert invoice.discount_amount == D("10.00")
        assert invoice.total == D("90.00") == order.grand_total


    def test_pre_1090_portal_order_keeps_unit_price_invoicing(self, db):
        # Before PR #1090 a portal order stored the whole quote total (tax and
        # shipping included) as its subtotal. That is not a rounding residue,
        # so the invoice keeps quantity x unit price rather than billing the
        # tax and shipping twice.
        order = SalesOrder(
            order_number=f"SO-R-{uuid.uuid4().hex[:8]}",
            user_id=1,
            order_type="quote_based",
            product_name="Widget",
            material_type="PLA",
            quantity=2,
            unit_price=D("45.00"),
            total_price=D("105.93"),  # 90.00 + 7.43 tax + 8.50 shipping
            tax_amount=D("0"),
            shipping_cost=D("8.50"),
            grand_total=D("114.43"),
            status="confirmed",
        )
        db.add(order)
        db.flush()
        invoice = invoice_service.create_invoice(db, order.id)
        assert invoice.subtotal == D("90.00")
