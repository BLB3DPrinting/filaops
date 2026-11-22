"""Quote descriptions, notes and discounts, end to end through the services.

The stored quote total must equal the PDF total, and the discount must carry
through to the sales order (including later line edits) and the invoice.

Golden quote (a real one): 2 x $42.56 = $85.12, 10% quote discount -$8.51,
subtotal $76.61, tax 7% $5.36, total $81.97.
"""
import uuid
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.quotes import ManualQuoteCreate, ManualQuoteUpdate, QuoteLineCreate
from app.models.invoice import InvoiceLine
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.tax_rate import TaxRate
from app.services import invoice_service, quote_service, sales_order_service
from tests.pdf_text import pdf_text

D = Decimal


@pytest.fixture
def tax_7(db):
    rate = TaxRate(name=f"Test 7% {uuid.uuid4().hex[:6]}", rate=D("0.0700"), is_default=False, is_active=True)
    db.add(rate)
    db.flush()
    return rate


@pytest.fixture
def trophy(make_product):
    return make_product(
        name="Custom Trophy",
        selling_price=D("42.56"),
        description="Custom trophy\nBlack Base (PLA Matte Charcoal)\nGold Top (PLA Silk Gold)\nGold Plate with words",
    )


def _golden_quote(db, tax_7, trophy, **overrides):
    fields = dict(
        lines=[QuoteLineCreate(product_id=trophy.id, product_name=trophy.name, quantity=2, unit_price=D("42.56"))],
        tax_rate_id=tax_7.id,
        discount_type="percent",
        discount_value=D("10"),
        discount_label="10% discount",
        customer_notes="Pickup Friday after 3pm.",
        admin_notes="INTERNAL: margin is thin on this one",
    )
    fields.update(overrides)
    return quote_service.create_quote(db, ManualQuoteCreate(**fields), user_id=1)


def _assert_in_order(text, tokens):
    """Each token appears after the previous one (the rows print in this order)."""
    pos = 0
    for token in tokens:
        found = text.find(token, pos)
        assert found >= 0, f"{token!r} not found after position {pos} in:\n{text}"
        pos = found + len(token)


def _approve(db, quote):
    quote.status = "approved"
    db.flush()


class TestCreate:
    def test_golden_totals_stored(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy)
        assert q.discount_amount == D("8.51")
        assert q.subtotal == D("76.61")
        assert q.tax_amount == D("5.36")
        assert q.total_price == D("81.97")
        assert q.lines[0].total == D("85.12")
        assert q.discount_label == "10% discount"

    def test_line_description_defaults_from_item(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy)
        assert q.lines[0].description == trophy.description

    def test_line_description_override_and_explicit_empty(self, db, tax_7, trophy):
        q = _golden_quote(
            db, tax_7, trophy,
            lines=[
                QuoteLineCreate(product_id=trophy.id, product_name="A", quantity=1, unit_price=D("1"), description="Custom text"),
                QuoteLineCreate(product_id=trophy.id, product_name="B", quantity=1, unit_price=D("1"), description=""),
                QuoteLineCreate(product_name="Setup fee", quantity=1, unit_price=D("5")),
            ],
        )
        assert [ln.description for ln in q.lines] == ["Custom text", None, None]

    def test_line_discounts_then_quote_discount(self, db, tax_7, trophy):
        q = _golden_quote(
            db, tax_7, trophy,
            lines=[
                QuoteLineCreate(product_name="A", quantity=2, unit_price=D("10.00"), discount_type="percent", discount_value=D("10")),
                QuoteLineCreate(product_name="B", quantity=1, unit_price=D("30.00"), discount_type="amount", discount_value=D("5"), discount_label="Loyalty"),
            ],
            discount_type="amount",
            discount_value=D("4"),
            tax_rate_id=None,
            apply_tax=False,
        )
        a, b = q.lines
        assert (a.total, a.discount_amount) == (D("18.00"), D("2.00"))
        assert (b.total, b.discount_amount, b.discount_label) == (D("25.00"), D("5.00"), "Loyalty")
        assert q.discount_amount == D("4.00")
        assert q.subtotal == D("39.00")
        assert q.total_price == D("39.00")

    def test_no_discount_quote_unchanged(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy, discount_type=None, discount_value=None, discount_label=None)
        assert q.discount_type is None and q.discount_amount is None
        assert q.subtotal == D("85.12")
        assert q.tax_amount == D("5.96")
        assert q.total_price == D("91.08")

    def test_single_item_quote_discount(self, db, tax_7):
        q = quote_service.create_quote(
            db,
            ManualQuoteCreate(
                product_name="Widget", quantity=2, unit_price=D("42.56"),
                tax_rate_id=tax_7.id, discount_type="percent", discount_value=D("10"),
            ),
            user_id=1,
        )
        assert (q.subtotal, q.discount_amount, q.tax_amount, q.total_price) == (
            D("76.61"), D("8.51"), D("5.36"), D("81.97"),
        )

    def test_invalid_discount_rejected(self, db, tax_7, trophy):
        with pytest.raises(ValueError):
            ManualQuoteCreate(product_name="X", unit_price=D("1"), discount_type="percent", discount_value=D("150"))


class TestUpdate:
    def test_adding_quote_discount_recomputes(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy, discount_type=None, discount_value=None, discount_label=None)
        q = quote_service.update_quote(
            db, q.id, ManualQuoteUpdate(discount_type="percent", discount_value=D("10"))
        )
        assert (q.subtotal, q.tax_amount, q.total_price) == (D("76.61"), D("5.36"), D("81.97"))

    def test_removing_quote_discount_recomputes(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy)
        q = quote_service.update_quote(db, q.id, ManualQuoteUpdate(discount_type=None, discount_value=None))
        assert q.discount_type is None and q.discount_amount is None and q.discount_label is None
        assert q.total_price == D("91.08")

    def test_replacing_lines_keeps_quote_discount_and_descriptions(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy)
        q = quote_service.update_quote(
            db, q.id,
            ManualQuoteUpdate(lines=[QuoteLineCreate(product_id=trophy.id, product_name=trophy.name, quantity=2, unit_price=D("42.56"))]),
        )
        assert q.total_price == D("81.97")
        assert q.lines[0].description == trophy.description

    def test_shipping_change_keeps_discount(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy)
        q = quote_service.update_quote(db, q.id, ManualQuoteUpdate(shipping_cost=D("10.00")))
        assert q.subtotal == D("76.61")
        assert q.total_price == D("76.61") + q.tax_amount + D("10.00")

    def test_invalid_partial_discount_400(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy, discount_type=None, discount_value=None, discount_label=None)
        with pytest.raises(HTTPException) as exc:
            quote_service.update_quote(db, q.id, ManualQuoteUpdate(discount_type="percent"))
        assert exc.value.status_code == 400


class TestPdf:
    def test_golden_pdf_rows_and_total_match_record(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy)
        text = pdf_text(quote_service.generate_quote_pdf(db, q.id).read())

        _assert_in_order(text, ["Items total", "$85.12", "10% discount", "$8.51", "Subtotal", "$76.61", "$5.36", "Total Due", "$81.97"])
        assert f"${q.total_price}" in text

    def test_description_and_customer_notes_printed(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy)
        text = pdf_text(quote_service.generate_quote_pdf(db, q.id).read())
        for part in ("Black Base (PLA Matte Charcoal)", "Gold Plate with words", "NOTES", "Pickup Friday after 3pm."):
            assert part in text

    def test_internal_notes_never_printed(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy)
        q.internal_notes = "INTERNAL2: do not print"
        db.flush()
        text = pdf_text(quote_service.generate_quote_pdf(db, q.id).read())
        assert "INTERNAL" not in text and "margin is thin" not in text

    def test_line_discount_printed_under_item(self, db, tax_7, trophy):
        q = _golden_quote(
            db, tax_7, trophy,
            lines=[QuoteLineCreate(product_name="A", quantity=1, unit_price=D("30.00"), discount_type="amount", discount_value=D("5"), discount_label="Loyalty")],
            discount_type=None, discount_value=None, discount_label=None,
        )
        text = pdf_text(quote_service.generate_quote_pdf(db, q.id).read())
        assert "Loyalty" in text and "Line discounts" in text
        assert text.index("Line discounts") < text.index("Subtotal")

    def test_undiscounted_quote_prints_no_discount_rows(self, db, tax_7, trophy):
        q = _golden_quote(db, tax_7, trophy, discount_type=None, discount_value=None, discount_label=None)
        text = pdf_text(quote_service.generate_quote_pdf(db, q.id).read())
        assert "Items total" not in text and "discount" not in text.lower()
        assert "$85.12" in text and "$91.08" in text


class TestCarryThrough:
    def _order(self, db, tax_7, trophy, **overrides):
        q = _golden_quote(db, tax_7, trophy, **overrides)
        _approve(db, q)
        result = quote_service.convert_quote_to_order(db, q.id)
        order = db.query(SalesOrder).filter(SalesOrder.id == result["order_id"]).one()
        return q, order

    def test_order_matches_quote(self, db, tax_7, trophy):
        q, order = self._order(db, tax_7, trophy)
        assert order.total_price == D("76.61")
        assert order.tax_amount == D("5.36")
        assert order.grand_total == D("81.97") == q.total_price
        assert (order.discount_type, order.discount_value, order.discount_amount, order.discount_label) == (
            "percent", D("10.00"), D("8.51"), "10% discount",
        )
        line = order.lines[0]
        assert line.long_description == trophy.description
        assert line.total == D("85.12")
        assert order.customer_notes == "Pickup Friday after 3pm."

    def test_line_edit_reapplies_order_discount(self, db, tax_7, trophy):
        _q, order = self._order(db, tax_7, trophy)
        order.is_taxable = True
        order.status = "confirmed"
        db.flush()
        line = order.lines[0]
        updated = sales_order_service.edit_sales_order_lines(
            db, order_id=order.id,
            line_updates=[{"line_id": line.id, "new_quantity": D("3"), "reason": "Customer added one"}],
            user_id=1,
        )
        # 3 x 42.56 = 127.68; 10% = 12.77; subtotal 114.91; 7% = 8.04
        assert updated.discount_amount == D("12.77")
        assert updated.total_price == D("114.91")
        assert updated.tax_amount == D("8.04")
        assert updated.grand_total == D("122.95")

    def test_line_edit_keeps_line_discount(self, db, tax_7, trophy):
        _q, order = self._order(
            db, tax_7, trophy,
            lines=[QuoteLineCreate(product_id=trophy.id, product_name=trophy.name, quantity=2, unit_price=D("42.56"), discount_type="percent", discount_value=D("50"))],
            discount_type=None, discount_value=None, discount_label=None,
        )
        order.status = "confirmed"
        db.flush()
        line = order.lines[0]
        assert (line.total, line.discount_amount) == (D("42.56"), D("42.56"))
        sales_order_service.edit_sales_order_lines(
            db, order_id=order.id,
            line_updates=[{"line_id": line.id, "new_quantity": D("4"), "reason": "More"}],
            user_id=1,
        )
        db.refresh(line)
        assert (line.total, line.discount_amount) == (D("85.12"), D("85.12"))

    def test_invoice_total_equals_quote_total(self, db, tax_7, trophy):
        q, order = self._order(db, tax_7, trophy)
        order.status = "confirmed"
        db.flush()
        invoice = invoice_service.create_invoice(db, order.id)
        assert invoice.subtotal == D("85.12")
        assert invoice.discount_amount == D("8.51")
        assert invoice.discount_label == "10% discount"
        assert invoice.tax_amount == D("5.36")
        assert invoice.total == D("81.97") == q.total_price == order.grand_total
        assert invoice.notes == "Pickup Friday after 3pm."
        inv_line = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).one()
        assert inv_line.long_description == trophy.description

        text = pdf_text(invoice_service.generate_invoice_pdf(db, invoice.id).read())
        _assert_in_order(text, ["Items total", "$85.12", "10% discount", "$8.51", "Subtotal", "$76.61", "$5.36", "Total Due", "$81.97"])
        assert "Gold Top (PLA Silk Gold)" in text
        assert "Pickup Friday after 3pm." in text
        assert "INTERNAL" not in text

    def test_payment_and_gl_use_discounted_total(self, db, tax_7, trophy):
        from app.models.accounting import GLAccount, GLJournalEntry, GLJournalEntryLine

        _q, order = self._order(db, tax_7, trophy)
        order.status = "confirmed"
        db.flush()
        invoice = invoice_service.create_invoice(db, order.id)
        invoice = invoice_service.record_payment(db, invoice.id, D("81.97"), "check", reference="1001")
        assert invoice.status == "paid"
        assert invoice.amount_paid == D("81.97")

        entry = db.query(GLJournalEntry).filter(
            GLJournalEntry.source_type == "invoice", GLJournalEntry.source_id == invoice.id
        ).one()
        amounts = {
            code: (debit, credit)
            for code, debit, credit in db.query(GLAccount.account_code, GLJournalEntryLine.debit_amount, GLJournalEntryLine.credit_amount)
            .join(GLJournalEntryLine, GLJournalEntryLine.account_id == GLAccount.id)
            .filter(GLJournalEntryLine.journal_entry_id == entry.id)
        }
        assert amounts["1100"][0] == D("81.97")   # AR
        assert amounts["4000"][1] == D("76.61")   # revenue, net of the discount
        assert amounts["2100"][1] == D("5.36")    # sales tax payable

    def test_invoice_with_line_discount(self, db, tax_7, trophy):
        q, order = self._order(
            db, tax_7, trophy,
            lines=[QuoteLineCreate(product_name="A", quantity=1, unit_price=D("30.00"), discount_type="amount", discount_value=D("5"), discount_label="Loyalty")],
            discount_type=None, discount_value=None, discount_label=None, tax_rate_id=None, apply_tax=False,
        )
        order.status = "confirmed"
        db.flush()
        invoice = invoice_service.create_invoice(db, order.id)
        assert invoice.total == q.total_price == D("25.00")
        inv_line = db.query(InvoiceLine).filter(InvoiceLine.invoice_id == invoice.id).one()
        assert (inv_line.line_total, inv_line.discount_amount, inv_line.discount_label) == (D("25.00"), D("5.00"), "Loyalty")

    def test_customer_convert_path_carries_discount(self, db, tax_7):
        q = quote_service.create_quote(
            db,
            ManualQuoteCreate(product_name="Widget", quantity=2, unit_price=D("42.56"), tax_rate_id=tax_7.id,
                              discount_type="percent", discount_value=D("10")),
            user_id=1,
        )
        q.status = "accepted"
        q.product_id = None
        db.flush()
        from app.models.product import Product
        product = Product(sku=f"CV-{uuid.uuid4().hex[:6]}", name="Widget", item_type="finished_good", unit="EA")
        db.add(product)
        db.flush()
        q.product_id = product.id
        db.flush()
        order = sales_order_service.convert_quote_to_sales_order(
            db, quote_id=q.id, user_id=1,
            shipping_address_line1="1 Main", shipping_city="Town", shipping_state="OH", shipping_zip="43000",
        )
        assert order.grand_total == q.total_price == D("81.97")
        assert order.discount_amount == D("8.51")


class TestDirectSalesOrderDescription:
    def test_item_description_copied_to_order_line(self, db, trophy):
        order = sales_order_service.create_sales_order(
            db,
            customer_id=None,
            lines=[{"product_id": trophy.id, "quantity": D("1"), "line_type": "product"}],
            created_by_user_id=1,
        )
        line = db.query(SalesOrderLine).filter(SalesOrderLine.sales_order_id == order.id).one()
        assert line.long_description == trophy.description
