"""
Discount lines on manual quotes.

A discount line is a product-less quote line with a negative unit price. These
tests cover creating and updating quotes with one, tax on the discounted
subtotal, rejection of over-discounting, conversion to a sales order and PDF
generation.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.company_settings import CompanySettings
from app.models.quote import Quote, QuoteLine
from app.models.sales_order import SalesOrder
from app.services import quote_service


def _company_settings(db, **overrides):
    """Create or update the singleton CompanySettings row."""
    defaults = dict(tax_enabled=False, tax_rate=None, tax_name="Sales Tax", company_name="Test Co")
    defaults.update(overrides)
    existing = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if existing:
        for key, value in defaults.items():
            setattr(existing, key, value)
        db.flush()
        return existing
    settings = CompanySettings(id=1, **defaults)
    db.add(settings)
    db.flush()
    return settings


def _line_request(unit_price, product_name="Line", quantity=1, product_id=None):
    return SimpleNamespace(
        product_id=product_id,
        product_name=product_name,
        quantity=quantity,
        unit_price=Decimal(str(unit_price)),
        material_type=None,
        color=None,
        notes=None,
    )


def _create_request(lines, **overrides):
    """Stand-in for ManualQuoteCreate with line items."""
    defaults = dict(
        product_name=None,
        product_id=None,
        quantity=None,
        unit_price=None,
        valid_days=30,
        material_type="PLA",
        color=None,
        shipping_cost=None,
        apply_tax=None,
        customer_id=None,
        customer_name="Jane Doe",
        customer_email="jane@example.com",
        customer_notes=None,
        admin_notes=None,
        lines=lines,
        shipping_state=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_quote(db, **overrides):
    defaults = dict(
        quote_number="Q-DISC-000001",
        user_id=1,
        product_name="Widget",
        quantity=1,
        unit_price=Decimal("10.00"),
        subtotal=Decimal("10.00"),
        total_price=Decimal("10.00"),
        material_type="PLA",
        status="pending",
        file_format="manual",
        file_size_bytes=0,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    quote = Quote(**defaults)
    db.add(quote)
    db.flush()
    return quote


class _UpdateRequest:
    """Stand-in for ManualQuoteUpdate that only sets the given fields."""

    def __init__(self, **data):
        self._data = data
        self.customer_id = None
        self.unit_price = None
        self.quantity = None
        self.apply_tax = None
        self.tax_rate_id = None
        for key, value in data.items():
            setattr(self, key, value)

    def model_dump(self, exclude_unset=False):
        return dict(self._data)


class TestCreateQuoteWithDiscountLine:
    def test_discount_line_reduces_subtotal_and_total(self, db, make_product):
        _company_settings(db)
        product = make_product(name="Standard Widget", selling_price=Decimal("20.00"))
        request = _create_request([
            _line_request("20.00", "Standard Widget", quantity=2, product_id=product.id),
            _line_request("-5.00", "Multi-buy discount"),
        ])

        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.subtotal == Decimal("35.00")
        assert quote.total_price == Decimal("35.00")
        discount = next(line for line in quote.lines if line.product_id is None)
        assert discount.unit_price == Decimal("-5.00")
        assert discount.total == Decimal("-5.00")

    def test_tax_is_calculated_on_the_discounted_subtotal(self, db, make_product):
        _company_settings(db, tax_enabled=True, tax_rate=Decimal("0.10"))
        product = make_product(name="Standard Widget", selling_price=Decimal("100.00"))
        request = _create_request(
            [
                _line_request("100.00", "Standard Widget", product_id=product.id),
                _line_request("-20.00", "Loyalty discount"),
            ],
            apply_tax=True,
        )

        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.subtotal == Decimal("80.00")
        assert quote.tax_amount == Decimal("8.00")
        assert quote.total_price == Decimal("88.00")

    def test_discount_larger_than_subtotal_is_rejected(self, db, make_product):
        _company_settings(db)
        product = make_product(name="Standard Widget", selling_price=Decimal("20.00"))
        before = db.query(Quote).count()
        request = _create_request([
            _line_request("20.00", "Standard Widget", product_id=product.id),
            _line_request("-25.00", "Too generous"),
        ])

        with pytest.raises(HTTPException) as exc_info:
            quote_service.create_quote(db, request, user_id=1)

        assert exc_info.value.status_code == 400
        assert db.query(Quote).count() == before

    def test_negative_price_on_product_line_is_rejected(self, db, make_product):
        _company_settings(db)
        product = make_product(name="Standard Widget", selling_price=Decimal("20.00"))
        request = _create_request([
            _line_request("-5.00", "Standard Widget", product_id=product.id),
        ])

        with pytest.raises(HTTPException) as exc_info:
            quote_service.create_quote(db, request, user_id=1)

        assert exc_info.value.status_code == 400


class TestUpdateQuoteWithDiscountLine:
    def test_update_replaces_lines_including_a_discount(self, db, make_product):
        _company_settings(db)
        product = make_product(name="Standard Widget", selling_price=Decimal("20.00"))
        quote = _make_quote(db)

        request = _UpdateRequest(lines=[
            {
                "product_id": product.id, "product_name": "Standard Widget",
                "quantity": 3, "unit_price": Decimal("20.00"),
                "material_type": None, "color": None, "notes": None,
            },
            {
                "product_id": None, "product_name": "Repeat customer discount",
                "quantity": 1, "unit_price": Decimal("-10.00"),
                "material_type": None, "color": None, "notes": None,
            },
        ])

        updated = quote_service.update_quote(db, quote.id, request)

        assert updated.subtotal == Decimal("50.00")
        assert updated.total_price == Decimal("50.00")
        assert sorted(line.total for line in updated.lines) == [Decimal("-10.00"), Decimal("60.00")]

    def test_over_discount_is_rejected_and_existing_lines_are_kept(self, db, make_product):
        _company_settings(db)
        product = make_product(name="Standard Widget", selling_price=Decimal("20.00"))
        quote = _make_quote(db, quote_number="Q-DISC-000002", product_id=None)
        db.add(QuoteLine(
            quote_id=quote.id, product_id=product.id, line_number=1,
            product_name="Standard Widget", quantity=1,
            unit_price=Decimal("20.00"), total=Decimal("20.00"),
        ))
        db.flush()

        request = _UpdateRequest(lines=[
            {
                "product_id": product.id, "product_name": "Standard Widget",
                "quantity": 1, "unit_price": Decimal("20.00"),
                "material_type": None, "color": None, "notes": None,
            },
            {
                "product_id": None, "product_name": "Too generous",
                "quantity": 1, "unit_price": Decimal("-50.00"),
                "material_type": None, "color": None, "notes": None,
            },
        ])

        with pytest.raises(HTTPException) as exc_info:
            quote_service.update_quote(db, quote.id, request)

        assert exc_info.value.status_code == 400
        remaining = db.query(QuoteLine).filter(QuoteLine.quote_id == quote.id).all()
        assert len(remaining) == 1
        assert remaining[0].total == Decimal("20.00")


class TestDiscountLineDownstream:
    def test_discount_line_converts_to_a_service_order_line(self, db, make_product):
        product = make_product(name="Standard Widget", selling_price=Decimal("20.00"))
        quote = _make_quote(
            db,
            quote_number="Q-DISC-CONV-01",
            status="approved",
            product_name="Standard Widget",
            quantity=2,
            unit_price=None,
            subtotal=Decimal("35.00"),
            total_price=Decimal("35.00"),
        )
        db.add_all([
            QuoteLine(
                quote_id=quote.id, product_id=product.id, line_number=1,
                product_name="Standard Widget", quantity=2,
                unit_price=Decimal("20.00"), total=Decimal("40.00"),
            ),
            QuoteLine(
                quote_id=quote.id, product_id=None, line_number=2,
                product_name="Multi-buy discount", quantity=1,
                unit_price=Decimal("-5.00"), total=Decimal("-5.00"),
            ),
        ])
        db.flush()

        result = quote_service.convert_quote_to_order(db, quote.id)
        order = db.query(SalesOrder).filter(SalesOrder.id == result["order_id"]).first()

        assert order.total_price == Decimal("35.00")
        assert order.grand_total == Decimal("35.00")
        discount_line = next(line for line in order.lines if line.line_type == "service")
        assert discount_line.description == "Multi-buy discount"
        assert discount_line.unit_price == Decimal("-5.00")
        assert discount_line.total == Decimal("-5.00")

    def test_discount_carries_through_to_the_invoice(self, db, make_product):
        from app.services.invoice_service import create_invoice, generate_invoice_pdf

        _company_settings(db, company_name="TestCo Invoice")
        product = make_product(name="Standard Widget", selling_price=Decimal("20.00"))
        quote = _make_quote(
            db,
            quote_number="Q-DISC-INV-01",
            status="approved",
            product_name="Standard Widget",
            quantity=2,
            unit_price=None,
            subtotal=Decimal("35.00"),
            total_price=Decimal("35.00"),
        )
        db.add_all([
            QuoteLine(
                quote_id=quote.id, product_id=product.id, line_number=1,
                product_name="Standard Widget", quantity=2,
                unit_price=Decimal("20.00"), total=Decimal("40.00"),
            ),
            QuoteLine(
                quote_id=quote.id, product_id=None, line_number=2,
                product_name="Multi-buy discount", quantity=1,
                unit_price=Decimal("-5.00"), total=Decimal("-5.00"),
            ),
        ])
        db.flush()
        result = quote_service.convert_quote_to_order(db, quote.id)
        order = db.query(SalesOrder).filter(SalesOrder.id == result["order_id"]).first()
        order.status = "confirmed"
        db.flush()

        invoice = create_invoice(db, order.id)

        assert invoice.subtotal == Decimal("35.00")
        assert invoice.total == Decimal("35.00")
        discount_line = next(line for line in invoice.lines if line.product_id is None)
        assert discount_line.description == "Multi-buy discount"
        assert discount_line.line_total == Decimal("-5.00")
        assert generate_invoice_pdf(db, invoice.id).read()[:4] == b"%PDF"

    def test_quote_pdf_generates_with_a_discount_line(self, db, make_product):
        _company_settings(db, company_name="TestCo PDF")
        product = make_product(name="Standard Widget", selling_price=Decimal("20.00"))
        quote = _make_quote(
            db,
            quote_number="Q-DISC-PDF-01",
            product_name="Standard Widget",
            quantity=1,
            unit_price=None,
            subtotal=Decimal("15.00"),
            total_price=Decimal("15.00"),
        )
        db.add_all([
            QuoteLine(
                quote_id=quote.id, product_id=product.id, line_number=1,
                product_name="Standard Widget", quantity=1,
                unit_price=Decimal("20.00"), total=Decimal("20.00"),
            ),
            QuoteLine(
                quote_id=quote.id, product_id=None, line_number=2,
                product_name="Multi-buy discount", quantity=1,
                unit_price=Decimal("-5.00"), total=Decimal("-5.00"),
            ),
        ])
        db.flush()
        db.refresh(quote)

        pdf = quote_service.generate_quote_pdf(db, quote.id)

        assert pdf.read()[:4] == b"%PDF"
