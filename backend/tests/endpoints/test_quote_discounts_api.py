"""API: quote line descriptions, quote notes and discounts (/api/v1/quotes)."""
import uuid
from decimal import Decimal

import pytest

from app.models.tax_rate import TaxRate
from tests.pdf_text import pdf_text

BASE_URL = "/api/v1/quotes"


@pytest.fixture
def tax_7(db):
    rate = TaxRate(name=f"API 7% {uuid.uuid4().hex[:6]}", rate=Decimal("0.0700"), is_default=False, is_active=True)
    db.add(rate)
    db.flush()
    return rate


@pytest.fixture
def trophy(make_product):
    return make_product(name="Custom Trophy", selling_price=Decimal("42.56"),
                        description="Custom trophy\nGold Top (PLA Silk Gold)")


def _golden_payload(trophy, tax_7, **overrides):
    payload = {
        "lines": [{"product_id": trophy.id, "product_name": trophy.name, "quantity": 2, "unit_price": "42.56"}],
        "tax_rate_id": tax_7.id,
        "discount_type": "percent",
        "discount_value": "10",
        "discount_label": "10% discount",
        "customer_notes": "Thanks for the order!",
        "admin_notes": "internal only",
    }
    payload.update(overrides)
    return payload


class TestCreateAndRead:
    def test_create_returns_discounted_totals_and_fields(self, client, trophy, tax_7):
        resp = client.post(BASE_URL, json=_golden_payload(trophy, tax_7))
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert Decimal(data["subtotal"]) == Decimal("76.61")
        assert Decimal(data["tax_amount"]) == Decimal("5.36")
        assert Decimal(data["total_price"]) == Decimal("81.97")
        assert data["discount_type"] == "percent"
        assert Decimal(data["discount_amount"]) == Decimal("8.51")
        assert data["discount_label"] == "10% discount"
        assert data["lines"][0]["description"] == trophy.description

        fetched = client.get(f"{BASE_URL}/{data['id']}").json()
        assert fetched["lines"][0]["description"] == trophy.description
        assert Decimal(fetched["total_price"]) == Decimal("81.97")

    def test_line_discount_and_description_round_trip(self, client, trophy, tax_7):
        payload = _golden_payload(
            trophy, tax_7,
            lines=[{
                "product_name": "Plate engraving", "quantity": 1, "unit_price": "30.00",
                "description": "Line one\nLine two",
                "discount_type": "amount", "discount_value": "5", "discount_label": "Loyalty",
            }],
            discount_type=None, discount_value=None, discount_label=None,
        )
        data = client.post(BASE_URL, json=payload).json()
        line = data["lines"][0]
        assert line["description"] == "Line one\nLine two"
        assert Decimal(line["total"]) == Decimal("25.00")
        assert Decimal(line["discount_amount"]) == Decimal("5.00")
        assert line["discount_label"] == "Loyalty"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"discount_type": "percent", "discount_value": "101"},
            {"discount_type": "bogus", "discount_value": "5"},
            {"discount_type": None, "discount_value": "5"},
            {"discount_type": "amount", "discount_value": "-1"},
        ],
    )
    def test_invalid_quote_discount_422(self, client, trophy, tax_7, overrides):
        resp = client.post(BASE_URL, json=_golden_payload(trophy, tax_7, **overrides))
        assert resp.status_code == 422, resp.text

    def test_invalid_line_discount_422(self, client, trophy, tax_7):
        payload = _golden_payload(trophy, tax_7, lines=[{
            "product_name": "X", "quantity": 1, "unit_price": "1", "discount_type": "percent", "discount_value": "200",
        }])
        assert client.post(BASE_URL, json=payload).status_code == 422


class TestUpdate:
    def test_patch_discount_recomputes(self, client, trophy, tax_7):
        created = client.post(BASE_URL, json=_golden_payload(trophy, tax_7, discount_type=None, discount_value=None)).json()
        assert Decimal(created["total_price"]) == Decimal("91.08")
        resp = client.patch(f"{BASE_URL}/{created['id']}", json={"discount_type": "percent", "discount_value": "10"})
        assert resp.status_code == 200, resp.text
        assert Decimal(resp.json()["total_price"]) == Decimal("81.97")

    def test_patch_incomplete_discount_400(self, client, trophy, tax_7):
        created = client.post(BASE_URL, json=_golden_payload(trophy, tax_7, discount_type=None, discount_value=None)).json()
        resp = client.patch(f"{BASE_URL}/{created['id']}", json={"discount_type": "percent"})
        assert resp.status_code == 400


class TestPreview:
    def test_preview_matches_saved_quote(self, client, trophy, tax_7):
        payload = _golden_payload(trophy, tax_7)
        preview = client.post(f"{BASE_URL}/preview-totals", json=payload)
        assert preview.status_code == 200, preview.text
        p = preview.json()
        assert Decimal(p["items_gross"]) == Decimal("85.12")
        assert Decimal(p["discount_amount"]) == Decimal("8.51")
        assert Decimal(p["subtotal"]) == Decimal("76.61")
        assert Decimal(p["tax_amount"]) == Decimal("5.36")
        assert Decimal(p["total"]) == Decimal("81.97")
        assert p["lines"][0]["description"] == trophy.description

        saved = client.post(BASE_URL, json=payload).json()
        assert Decimal(saved["total_price"]) == Decimal(p["total"])

    def test_preview_for_existing_quote_uses_stored_tax(self, client, trophy, tax_7):
        saved = client.post(BASE_URL, json=_golden_payload(trophy, tax_7)).json()
        p = client.post(f"{BASE_URL}/preview-totals", json={
            "quote_id": saved["id"],
            "lines": [{"product_id": trophy.id, "product_name": trophy.name, "quantity": 2, "unit_price": "42.56"}],
            "discount_type": "percent", "discount_value": "10",
        }).json()
        assert Decimal(p["total"]) == Decimal("81.97")

    def test_preview_saves_nothing(self, client, db, trophy, tax_7):
        from app.models.quote import Quote
        before = db.query(Quote).count()
        client.post(f"{BASE_URL}/preview-totals", json=_golden_payload(trophy, tax_7))
        assert db.query(Quote).count() == before

    def test_preview_requires_staff(self, unauthed_client, trophy, tax_7):
        resp = unauthed_client.post(f"{BASE_URL}/preview-totals", json=_golden_payload(trophy, tax_7))
        assert resp.status_code == 401


class TestPdfEndpoint:
    def test_pdf_total_matches_stored_total(self, client, trophy, tax_7):
        data = client.post(BASE_URL, json=_golden_payload(trophy, tax_7)).json()
        resp = client.get(f"{BASE_URL}/{data['id']}/pdf")
        assert resp.status_code == 200
        text = pdf_text(resp.content)
        assert "Total Due" in text and f"${Decimal(data['total_price']):.2f}" in text
        assert "internal only" not in text
        assert "Thanks for the order!" in text
