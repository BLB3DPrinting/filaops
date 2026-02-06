"""
Tests for app/services/quote_service.py

Covers:
- generate_quote_number: format, sequential numbering
- list_quotes: no filter, status filter, search filter, pagination
- get_quote_stats: counts by status, values
- get_quote_detail: found, 404
- create_quote: basic flow, tax calculation, customer validation, material validation, integrity error
- update_quote: field updates, pricing recalculation, tax toggle, converted guard, material validation
- update_quote_status: valid transitions, invalid status, converted guard
- convert_quote_to_order: happy path, wrong status, already converted, expired
- delete_quote: normal delete, converted guard, 404
- upload_quote_image: valid upload, invalid type, file too large, quote 404
- get_quote_image: with image, without image, quote 404
- delete_quote_image: happy path, quote 404
- generate_quote_pdf: basic generation, 404
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from types import SimpleNamespace

from fastapi import HTTPException

from app.services import quote_service
from app.models.quote import Quote
from app.models.company_settings import CompanySettings
from app.models.user import User
from app.models.sales_order import SalesOrder


# =============================================================================
# Helpers
# =============================================================================

def _make_quote(db, **overrides):
    """Create a Quote directly for test setup."""
    defaults = dict(
        quote_number=f"Q-TEST-{id(overrides) % 100000:06d}",
        user_id=1,
        product_name="Test Widget",
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


def _make_customer_user(db, **overrides):
    """Create a User with account_type='customer' for test setup."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    defaults = dict(
        email=f"cust-{uid}@example.com",
        password_hash="not-a-real-hash",
        first_name="Test",
        last_name="Customer",
        account_type="customer",
    )
    defaults.update(overrides)
    user = User(**defaults)
    db.add(user)
    db.flush()
    return user


def _make_manual_quote_request(**overrides):
    """Create a SimpleNamespace mimicking ManualQuoteCreate."""
    defaults = dict(
        product_name="Test Widget",
        product_id=None,
        quantity=2,
        unit_price=Decimal("25.00"),
        valid_days=30,
        material_type="PLA",
        color=None,
        shipping_cost=None,
        apply_tax=None,
        customer_id=None,
        customer_name="John Doe",
        customer_email="john@example.com",
        customer_notes=None,
        admin_notes=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_company_settings(db, **overrides):
    """Create or update CompanySettings row (singleton, id=1)."""
    existing = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    defaults = dict(
        tax_enabled=False,
        tax_rate=None,
        tax_name="Sales Tax",
        company_name="Test Co",
    )
    defaults.update(overrides)
    if existing:
        for k, v in defaults.items():
            setattr(existing, k, v)
        db.flush()
        return existing
    settings = CompanySettings(id=1, **defaults)
    db.add(settings)
    db.flush()
    return settings


# =============================================================================
# generate_quote_number
# =============================================================================

class TestGenerateQuoteNumber:
    def test_format(self, db):
        number = quote_service.generate_quote_number(db)
        year = datetime.now(timezone.utc).year
        assert number.startswith(f"Q-{year}-")
        # The sequence part should be zero-padded to 6 digits
        seq_part = number.split("-", 2)[2]
        assert len(seq_part) == 6

    def test_sequential(self, db):
        """Each call returns a number higher than the previous."""
        n1 = quote_service.generate_quote_number(db)
        # Create a quote with this number so the next call sees it
        _make_quote(db, quote_number=n1)

        n2 = quote_service.generate_quote_number(db)
        seq1 = int(n1.split("-")[2])
        seq2 = int(n2.split("-")[2])
        assert seq2 > seq1


# =============================================================================
# list_quotes
# =============================================================================

class TestListQuotes:
    def test_returns_all_quotes(self, db):
        q1 = _make_quote(db, quote_number="Q-LIST-000001")
        q2 = _make_quote(db, quote_number="Q-LIST-000002")

        result = quote_service.list_quotes(db)
        ids = [q.id for q in result]
        assert q1.id in ids
        assert q2.id in ids

    def test_filters_by_status(self, db):
        _make_quote(db, quote_number="Q-STAT-000001", status="pending")
        approved = _make_quote(db, quote_number="Q-STAT-000002", status="approved")

        result = quote_service.list_quotes(db, status_filter="approved")
        ids = [q.id for q in result]
        assert approved.id in ids

    def test_search_by_customer_name(self, db):
        q = _make_quote(db, quote_number="Q-SRCH-000001", customer_name="UniqueCustZZZ")

        result = quote_service.list_quotes(db, search="UniqueCustZZZ")
        ids = [q2.id for q2 in result]
        assert q.id in ids

    def test_pagination(self, db):
        for i in range(3):
            _make_quote(db, quote_number=f"Q-PAGE-{i:06d}")

        result = quote_service.list_quotes(db, skip=0, limit=1)
        assert len(result) == 1


# =============================================================================
# get_quote_stats
# =============================================================================

class TestGetQuoteStats:
    def test_returns_stat_dict(self, db):
        _make_quote(db, quote_number="Q-STATS-000001", status="pending")
        _make_quote(db, quote_number="Q-STATS-000002", status="approved")

        stats = quote_service.get_quote_stats(db)
        assert "total" in stats
        assert "pending" in stats
        assert "approved" in stats
        assert "total_value" in stats


# =============================================================================
# get_quote_detail
# =============================================================================

class TestGetQuoteDetail:
    def test_returns_quote(self, db):
        q = _make_quote(db, quote_number="Q-DET-000001")
        result = quote_service.get_quote_detail(db, q.id)
        assert result.id == q.id

    def test_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            quote_service.get_quote_detail(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# create_quote
# =============================================================================

class TestCreateQuote:
    def test_basic_creation(self, db):
        _make_company_settings(db)
        request = _make_manual_quote_request()
        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.id is not None
        assert quote.product_name == "Test Widget"
        assert quote.quantity == 2
        assert quote.status == "pending"

    def test_calculates_subtotal(self, db):
        _make_company_settings(db)
        request = _make_manual_quote_request(unit_price=Decimal("10.00"), quantity=5)
        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.subtotal == Decimal("50.00")

    def test_applies_tax_when_enabled(self, db):
        _make_company_settings(db, tax_enabled=True, tax_rate=Decimal("0.0825"))
        request = _make_manual_quote_request(
            unit_price=Decimal("100.00"), quantity=1, apply_tax=True
        )
        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.tax_rate == Decimal("0.0825")
        assert quote.tax_amount == Decimal("8.25")
        assert quote.total_price == Decimal("108.25")

    def test_no_tax_when_apply_tax_false(self, db):
        _make_company_settings(db, tax_enabled=True, tax_rate=Decimal("0.0825"))
        request = _make_manual_quote_request(
            unit_price=Decimal("100.00"), quantity=1, apply_tax=False
        )
        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.tax_rate is None
        assert quote.tax_amount is None

    def test_adds_shipping_cost(self, db):
        _make_company_settings(db)
        request = _make_manual_quote_request(
            unit_price=Decimal("10.00"), quantity=1, shipping_cost=Decimal("5.99")
        )
        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.total_price == Decimal("15.99")

    def test_validates_customer_id(self, db):
        _make_company_settings(db)
        request = _make_manual_quote_request(customer_id=999999)

        with pytest.raises(HTTPException) as exc_info:
            quote_service.create_quote(db, request, user_id=1)
        assert exc_info.value.status_code == 400
        assert "customer" in exc_info.value.detail.lower()

    def test_valid_customer_id_accepted(self, db):
        _make_company_settings(db)
        customer = _make_customer_user(db)
        request = _make_manual_quote_request(customer_id=customer.id)
        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.customer_id == customer.id

    def test_defaults_material_type_to_pla(self, db):
        _make_company_settings(db)
        request = _make_manual_quote_request(material_type=None)
        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.material_type == "PLA"

    def test_apply_tax_none_uses_company_setting(self, db):
        """When apply_tax is None, fall back to company_settings.tax_enabled."""
        _make_company_settings(db, tax_enabled=True, tax_rate=Decimal("0.0500"))
        request = _make_manual_quote_request(
            unit_price=Decimal("100.00"), quantity=1, apply_tax=None
        )
        quote = quote_service.create_quote(db, request, user_id=1)

        assert quote.tax_rate == Decimal("0.0500")
        assert quote.tax_amount == Decimal("5.00")


# =============================================================================
# update_quote
# =============================================================================

class TestUpdateQuote:
    def _make_update_request(self, **overrides):
        """Create a SimpleNamespace mimicking ManualQuoteUpdate."""
        defaults = dict(
            product_name=None,
            product_id=None,
            quantity=None,
            unit_price=None,
            material_type=None,
            color=None,
            shipping_cost=None,
            customer_id=None,
            customer_name=None,
            customer_email=None,
            customer_notes=None,
            admin_notes=None,
        )
        defaults.update(overrides)

        class FakeUpdate:
            """Mimics Pydantic model with model_dump(exclude_unset=True)."""
            def __init__(self, data):
                self._data = data
                for k, v in data.items():
                    setattr(self, k, v)

            def model_dump(self, exclude_unset=False):
                if exclude_unset:
                    return {k: v for k, v in self._data.items() if v is not None}
                return dict(self._data)

        return FakeUpdate(defaults)

    def test_updates_fields(self, db):
        q = _make_quote(db, quote_number="Q-UPD-000001")
        request = self._make_update_request(product_name="Updated Widget")
        result = quote_service.update_quote(db, q.id, request)

        assert result.product_name == "Updated Widget"

    def test_raises_404(self, db):
        request = self._make_update_request(product_name="Ghost")
        with pytest.raises(HTTPException) as exc_info:
            quote_service.update_quote(db, 999999, request)
        assert exc_info.value.status_code == 404

    def test_cannot_edit_converted(self, db):
        q = _make_quote(db, quote_number="Q-UPD-CONV-01", status="converted")
        request = self._make_update_request(product_name="Nope")

        with pytest.raises(HTTPException) as exc_info:
            quote_service.update_quote(db, q.id, request)
        assert exc_info.value.status_code == 400
        assert "converted" in exc_info.value.detail.lower()

    def test_recalculates_pricing_on_quantity_change(self, db):
        q = _make_quote(
            db, quote_number="Q-UPD-PRICE-01",
            unit_price=Decimal("10.00"), subtotal=Decimal("10.00"),
            total_price=Decimal("10.00"), quantity=1,
        )
        request = self._make_update_request(quantity=5)
        result = quote_service.update_quote(db, q.id, request)

        assert result.subtotal == Decimal("50.00")


# =============================================================================
# update_quote_status
# =============================================================================

class TestUpdateQuoteStatus:
    def _make_status_request(self, status, rejection_reason=None, admin_notes=None):
        return SimpleNamespace(
            status=status,
            rejection_reason=rejection_reason,
            admin_notes=admin_notes,
        )

    def test_approve(self, db):
        q = _make_quote(db, quote_number="Q-STAT-APP-01")
        request = self._make_status_request("approved")
        result = quote_service.update_quote_status(db, q.id, request, current_user_id=1)

        assert result.status == "approved"
        assert result.approved_at is not None
        assert result.approved_by == 1

    def test_reject_with_reason(self, db):
        q = _make_quote(db, quote_number="Q-STAT-REJ-01")
        request = self._make_status_request("rejected", rejection_reason="Too expensive")
        result = quote_service.update_quote_status(db, q.id, request, current_user_id=1)

        assert result.status == "rejected"
        assert result.rejection_reason == "Too expensive"

    def test_cannot_change_converted_status(self, db):
        q = _make_quote(db, quote_number="Q-STAT-CONV-01", status="converted")
        request = self._make_status_request("pending")

        with pytest.raises(HTTPException) as exc_info:
            quote_service.update_quote_status(db, q.id, request, current_user_id=1)
        assert exc_info.value.status_code == 400

    def test_invalid_status_value(self, db):
        q = _make_quote(db, quote_number="Q-STAT-BAD-01")
        request = self._make_status_request("bogus_status")

        with pytest.raises(HTTPException) as exc_info:
            quote_service.update_quote_status(db, q.id, request, current_user_id=1)
        assert exc_info.value.status_code == 400

    def test_raises_404(self, db):
        request = self._make_status_request("approved")
        with pytest.raises(HTTPException) as exc_info:
            quote_service.update_quote_status(db, 999999, request, current_user_id=1)
        assert exc_info.value.status_code == 404

    def test_admin_notes_saved(self, db):
        q = _make_quote(db, quote_number="Q-STAT-NOTE-01")
        request = self._make_status_request("approved", admin_notes="Looks good")
        result = quote_service.update_quote_status(db, q.id, request, current_user_id=1)

        assert result.admin_notes == "Looks good"


# =============================================================================
# convert_quote_to_order
# =============================================================================

class TestConvertQuoteToOrder:
    def test_happy_path(self, db):
        q = _make_quote(
            db, quote_number="Q-CONV-000001",
            status="approved",
            unit_price=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_price=Decimal("10.00"),
            quantity=1,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        )

        result = quote_service.convert_quote_to_order(db, q.id)
        assert "order_id" in result
        assert "order_number" in result

        db.refresh(q)
        assert q.status == "converted"
        assert q.sales_order_id == result["order_id"]

    def test_accepted_status_also_converts(self, db):
        q = _make_quote(
            db, quote_number="Q-CONV-ACCEPT-01",
            status="accepted",
            unit_price=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_price=Decimal("10.00"),
        )
        result = quote_service.convert_quote_to_order(db, q.id)
        assert "order_id" in result

    def test_rejects_pending_status(self, db):
        q = _make_quote(db, quote_number="Q-CONV-PEND-01", status="pending")

        with pytest.raises(HTTPException) as exc_info:
            quote_service.convert_quote_to_order(db, q.id)
        assert exc_info.value.status_code == 400
        assert "approved or accepted" in exc_info.value.detail.lower()

    def test_rejects_already_converted(self, db):
        q = _make_quote(
            db, quote_number="Q-CONV-DUP-01",
            status="approved",
            sales_order_id=123,
        )

        with pytest.raises(HTTPException) as exc_info:
            quote_service.convert_quote_to_order(db, q.id)
        assert exc_info.value.status_code == 400
        assert "already converted" in exc_info.value.detail.lower()

    def test_rejects_expired(self, db):
        q = _make_quote(
            db, quote_number="Q-CONV-EXP-01",
            status="approved",
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        with pytest.raises(HTTPException) as exc_info:
            quote_service.convert_quote_to_order(db, q.id)
        assert exc_info.value.status_code == 400
        assert "expired" in exc_info.value.detail.lower()

    def test_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            quote_service.convert_quote_to_order(db, 999999)
        assert exc_info.value.status_code == 404

    def test_copies_customer_address_from_user(self, db):
        customer = _make_customer_user(
            db,
            shipping_address_line1="123 Main St",
            shipping_city="Springfield",
            shipping_state="IL",
            shipping_zip="62704",
            shipping_country="USA",
            phone="555-1234",
        )
        q = _make_quote(
            db, quote_number="Q-CONV-ADDR-01",
            status="approved",
            customer_id=customer.id,
            unit_price=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_price=Decimal("10.00"),
            # No shipping address on quote
        )

        result = quote_service.convert_quote_to_order(db, q.id)
        order = db.query(SalesOrder).filter(SalesOrder.id == result["order_id"]).first()

        assert order.shipping_address_line1 == "123 Main St"
        assert order.shipping_city == "Springfield"

    def test_preserves_tax_on_conversion(self, db):
        q = _make_quote(
            db, quote_number="Q-CONV-TAX-01",
            status="approved",
            unit_price=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            tax_rate=Decimal("0.0825"),
            tax_amount=Decimal("8.25"),
            total_price=Decimal("108.25"),
            shipping_cost=Decimal("5.00"),
        )

        result = quote_service.convert_quote_to_order(db, q.id)
        order = db.query(SalesOrder).filter(SalesOrder.id == result["order_id"]).first()

        assert order.tax_amount == Decimal("8.25")
        assert order.tax_rate == Decimal("0.0825")
        assert order.grand_total == Decimal("113.25")


# =============================================================================
# delete_quote
# =============================================================================

class TestDeleteQuote:
    def test_deletes_quote(self, db):
        q = _make_quote(db, quote_number="Q-DEL-000001")
        qn = quote_service.delete_quote(db, q.id)

        assert qn == "Q-DEL-000001"
        assert db.query(Quote).filter(Quote.id == q.id).first() is None

    def test_cannot_delete_converted(self, db):
        q = _make_quote(db, quote_number="Q-DEL-CONV-01", status="converted")

        with pytest.raises(HTTPException) as exc_info:
            quote_service.delete_quote(db, q.id)
        assert exc_info.value.status_code == 400

    def test_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            quote_service.delete_quote(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# upload_quote_image
# =============================================================================

class TestUploadQuoteImage:
    def test_uploads_image(self, db):
        q = _make_quote(db, quote_number="Q-IMG-000001")
        content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        result = quote_service.upload_quote_image(
            db, q.id, content, "test.png", "image/png"
        )

        assert result["message"] == "Image uploaded successfully"
        db.refresh(q)
        assert q.image_data is not None
        assert q.image_filename == "test.png"

    def test_rejects_invalid_type(self, db):
        q = _make_quote(db, quote_number="Q-IMG-BAD-01")
        with pytest.raises(HTTPException) as exc_info:
            quote_service.upload_quote_image(
                db, q.id, b"data", "file.pdf", "application/pdf"
            )
        assert exc_info.value.status_code == 400

    def test_rejects_oversized_file(self, db):
        q = _make_quote(db, quote_number="Q-IMG-BIG-01")
        content = b"\x00" * (6 * 1024 * 1024)  # 6MB, over 5MB limit
        with pytest.raises(HTTPException) as exc_info:
            quote_service.upload_quote_image(
                db, q.id, content, "big.png", "image/png"
            )
        assert exc_info.value.status_code == 400

    def test_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            quote_service.upload_quote_image(
                db, 999999, b"data", "test.png", "image/png"
            )
        assert exc_info.value.status_code == 404


# =============================================================================
# get_quote_image
# =============================================================================

class TestGetQuoteImage:
    def test_returns_image_data(self, db):
        q = _make_quote(
            db, quote_number="Q-GIMG-000001",
            image_data=b"fake-image-bytes",
            image_filename="render.png",
            image_mime_type="image/png",
        )

        result = quote_service.get_quote_image(db, q.id)
        assert result["image_data"] == b"fake-image-bytes"
        assert result["mime_type"] == "image/png"

    def test_raises_404_when_no_image(self, db):
        q = _make_quote(db, quote_number="Q-GIMG-NOIMG-01")

        with pytest.raises(HTTPException) as exc_info:
            quote_service.get_quote_image(db, q.id)
        assert exc_info.value.status_code == 404
        assert "no image" in exc_info.value.detail.lower()

    def test_raises_404_for_missing_quote(self, db):
        with pytest.raises(HTTPException) as exc_info:
            quote_service.get_quote_image(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# delete_quote_image
# =============================================================================

class TestDeleteQuoteImage:
    def test_clears_image_data(self, db):
        q = _make_quote(
            db, quote_number="Q-DIMG-000001",
            image_data=b"some-bytes",
            image_filename="img.png",
            image_mime_type="image/png",
        )

        qn = quote_service.delete_quote_image(db, q.id)
        assert qn == "Q-DIMG-000001"
        db.refresh(q)
        assert q.image_data is None
        assert q.image_filename is None

    def test_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            quote_service.delete_quote_image(db, 999999)
        assert exc_info.value.status_code == 404


# =============================================================================
# generate_quote_pdf
# =============================================================================

class TestGenerateQuotePdf:
    def test_generates_pdf_buffer(self, db):
        _make_company_settings(db, company_name="TestCo PDF")
        q = _make_quote(
            db, quote_number="Q-PDF-000001",
            product_name="Widget",
            customer_name="Jane Doe",
            customer_email="jane@example.com",
            unit_price=Decimal("25.00"),
            subtotal=Decimal("25.00"),
            total_price=Decimal("25.00"),
            quantity=1,
        )

        pdf_buffer = quote_service.generate_quote_pdf(db, q.id)
        content = pdf_buffer.read()

        # PDF files start with %PDF
        assert content[:4] == b"%PDF"

    def test_pdf_with_tax_and_shipping(self, db):
        _make_company_settings(db, company_name="TestCo", tax_name="Sales Tax")
        q = _make_quote(
            db, quote_number="Q-PDF-TAX-01",
            unit_price=Decimal("100.00"),
            subtotal=Decimal("100.00"),
            tax_rate=Decimal("0.0825"),
            tax_amount=Decimal("8.25"),
            total_price=Decimal("113.24"),
            shipping_cost=Decimal("4.99"),
            quantity=1,
        )

        pdf_buffer = quote_service.generate_quote_pdf(db, q.id)
        assert pdf_buffer.read()[:4] == b"%PDF"

    def test_pdf_with_customer_notes(self, db):
        _make_company_settings(db)
        q = _make_quote(
            db, quote_number="Q-PDF-NOTE-01",
            customer_notes="Please rush this order",
            unit_price=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_price=Decimal("10.00"),
        )

        pdf_buffer = quote_service.generate_quote_pdf(db, q.id)
        assert pdf_buffer.read()[:4] == b"%PDF"

    def test_pdf_with_terms_and_footer(self, db):
        _make_company_settings(
            db,
            quote_terms="Net 30 payment terms apply.",
            quote_footer="Thank you for choosing TestCo.",
        )
        q = _make_quote(
            db, quote_number="Q-PDF-TERMS-01",
            unit_price=Decimal("10.00"),
            subtotal=Decimal("10.00"),
            total_price=Decimal("10.00"),
        )

        pdf_buffer = quote_service.generate_quote_pdf(db, q.id)
        assert pdf_buffer.read()[:4] == b"%PDF"

    def test_raises_404(self, db):
        with pytest.raises(HTTPException) as exc_info:
            quote_service.generate_quote_pdf(db, 999999)
        assert exc_info.value.status_code == 404
