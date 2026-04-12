"""
Tests for Purchase Order PDF generation.

Covers:
- GET /api/v1/purchase-orders/{id}/pdf (endpoint)
- generate_po_pdf() service function
"""
import pytest
from decimal import Decimal
from datetime import date

from app.models.purchase_order import PurchaseOrderLine


BASE_URL = "/api/v1/purchase-orders"


def _create_po_with_lines(db, make_vendor, make_product, make_purchase_order, **po_kwargs):
    """Helper: create a PO with vendor and a couple of line items."""
    vendor = make_vendor(
        name="Acme Supplies",
        contact_name="Jane Doe",
        email="jane@acme.test",
        phone="555-0100",
        address_line1="123 Supplier St",
        city="Supplyville",
        state="CA",
        postal_code="90210",
    )
    prod1 = make_product(name="Widget A", sku="WA-001")
    prod2 = make_product(name="Widget B", sku="WB-002")

    defaults = dict(
        vendor_id=vendor.id,
        status="ordered",
        order_date=date(2025, 6, 1),
        expected_date=date(2025, 6, 15),
        subtotal=Decimal("200.00"),
        tax_amount=Decimal("16.00"),
        shipping_cost=Decimal("10.00"),
        total_amount=Decimal("226.00"),
    )
    defaults.update(po_kwargs)
    po = make_purchase_order(**defaults)

    line1 = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=prod1.id,
        line_number=1,
        quantity_ordered=Decimal("50"),
        quantity_received=Decimal("0"),
        unit_cost=Decimal("2.00"),
        line_total=Decimal("100.00"),
    )
    line2 = PurchaseOrderLine(
        purchase_order_id=po.id,
        product_id=prod2.id,
        line_number=2,
        quantity_ordered=Decimal("20"),
        quantity_received=Decimal("10"),
        purchase_unit="KG",
        unit_cost=Decimal("5.00"),
        line_total=Decimal("100.00"),
    )
    db.add_all([line1, line2])
    db.flush()

    return po


# =============================================================================
# Endpoint tests — GET /api/v1/purchase-orders/{id}/pdf
# =============================================================================

class TestPurchaseOrderPDF:
    """Test GET /api/v1/purchase-orders/{id}/pdf."""

    def test_generate_pdf(self, client, db, make_vendor, make_product, make_purchase_order):
        po = _create_po_with_lines(db, make_vendor, make_product, make_purchase_order)
        response = client.get(f"{BASE_URL}/{po.id}/pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.content[:5] == b"%PDF-"

    def test_pdf_filename_matches_po_number(self, client, db, make_vendor, make_product, make_purchase_order):
        po = _create_po_with_lines(db, make_vendor, make_product, make_purchase_order)
        response = client.get(f"{BASE_URL}/{po.id}/pdf")
        content_disposition = response.headers.get("content-disposition", "")
        assert po.po_number in content_disposition

    def test_pdf_nonexistent_po_returns_404(self, client):
        response = client.get(f"{BASE_URL}/999999/pdf")
        assert response.status_code == 404

    def test_pdf_with_notes(self, client, db, make_vendor, make_product, make_purchase_order):
        """PO with notes should still generate a valid PDF."""
        po = _create_po_with_lines(
            db, make_vendor, make_product, make_purchase_order,
            notes="Rush order — please prioritise shipping",
        )
        response = client.get(f"{BASE_URL}/{po.id}/pdf")
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"

    def test_pdf_with_payment_info(self, client, db, make_vendor, make_product, make_purchase_order):
        """PO with payment & tracking info should generate a valid PDF."""
        po = _create_po_with_lines(
            db, make_vendor, make_product, make_purchase_order,
            payment_method="Net 30",
            payment_reference="PO-REF-12345",
            tracking_number="1Z999AA10123456784",
            carrier="UPS",
        )
        response = client.get(f"{BASE_URL}/{po.id}/pdf")
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"

    def test_pdf_draft_po_no_lines(self, client, db, make_vendor, make_purchase_order):
        """A draft PO with zero lines should still produce a valid PDF."""
        vendor = make_vendor()
        po = make_purchase_order(vendor_id=vendor.id, status="draft")
        db.flush()

        response = client.get(f"{BASE_URL}/{po.id}/pdf")
        assert response.status_code == 200
        assert response.content[:5] == b"%PDF-"

    def test_pdf_requires_auth(self, unauthed_client):
        response = unauthed_client.get(f"{BASE_URL}/1/pdf")
        assert response.status_code == 401


# =============================================================================
# Service-level tests — generate_po_pdf()
# =============================================================================

class TestGeneratePoPdf:
    """Test purchase_order_service.generate_po_pdf() directly."""

    def test_returns_bytes_io(self, db, make_vendor, make_product, make_purchase_order):
        import io
        from app.services.purchase_order_service import generate_po_pdf

        po = _create_po_with_lines(db, make_vendor, make_product, make_purchase_order)
        result = generate_po_pdf(db, po.id)
        assert isinstance(result, io.BytesIO)
        assert result.read(5) == b"%PDF-"

    def test_raises_404_for_missing_po(self, db):
        from fastapi import HTTPException
        from app.services.purchase_order_service import generate_po_pdf

        with pytest.raises(HTTPException) as exc_info:
            generate_po_pdf(db, 999999)
        assert exc_info.value.status_code == 404

    def test_pdf_with_zero_amounts(self, db, make_vendor, make_product, make_purchase_order):
        """PO with all-zero financials should still generate."""
        import io
        from app.services.purchase_order_service import generate_po_pdf

        po = _create_po_with_lines(
            db, make_vendor, make_product, make_purchase_order,
            subtotal=Decimal("0"),
            tax_amount=Decimal("0"),
            shipping_cost=Decimal("0"),
            total_amount=Decimal("0"),
        )
        result = generate_po_pdf(db, po.id)
        assert isinstance(result, io.BytesIO)
        assert result.read(5) == b"%PDF-"

    def test_pdf_without_company_settings(self, db, make_vendor, make_product, make_purchase_order):
        """If no CompanySettings row exists, PDF generation should still work."""
        import io
        from app.services.purchase_order_service import generate_po_pdf
        from app.models.company_settings import CompanySettings

        # Remove company settings if present
        db.query(CompanySettings).delete()
        db.flush()

        po = _create_po_with_lines(db, make_vendor, make_product, make_purchase_order)
        result = generate_po_pdf(db, po.id)
        assert isinstance(result, io.BytesIO)
        assert result.read(5) == b"%PDF-"
