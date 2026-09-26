"""SEC-409: operators keep every staff route they could use before the gates.

The v4.2.0 security release puts get_current_staff_user (admin or operator) on
every staff router so a self-registered customer can no longer use them. That
must be invisible to operators: a representative route in each newly gated
module still answers 200 (or 404 for an id that does not exist), and the
routes that were already admin-only still refuse operators with 403.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.sales_order import SalesOrder
from app.models.scrap_reason import ScrapReason
from app.models.tax_rate import TaxRate

MISSING = 999_999_999

_now = datetime.now(timezone.utc).replace(microsecond=0)
_WINDOW = {
    "start_date": (_now - timedelta(days=1)).isoformat(),
    "end_date": (_now + timedelta(days=7)).isoformat(),
}

# (label, path, query params, accepted status codes)
OPERATOR_READS = [
    # production
    ("production_orders_list", "/api/v1/production-orders/", None, {200}),
    ("production_order_detail_missing", f"/api/v1/production-orders/{MISSING}", None, {404}),
    ("production_scrap_reasons", "/api/v1/production-orders/scrap-reasons", None, {200}),
    ("production_status_transitions", "/api/v1/production-orders/status-transitions", None, {200}),
    ("operations_missing_po", f"/api/v1/production-orders/{MISSING}/operations", None, {404}),
    ("qc_photos_missing_inspection",
     f"/api/v1/production-orders/qc-inspections/{MISSING}/photos", None, {404}),
    # items, routings, work centres, maintenance
    ("items_list", "/api/v1/items", None, {200}),
    ("item_categories", "/api/v1/items/categories", None, {200}),
    ("routings_list", "/api/v1/routings/", None, {200}),
    ("work_centers_list", "/api/v1/work-centers/", None, {200}),
    ("maintenance_list", "/api/v1/maintenance/", None, {200}),
    ("maintenance_windows_list", "/api/v1/maintenance-windows", None, {200}),
    # purchasing and payments
    ("vendors_list", "/api/v1/vendors/", None, {200}),
    ("vendor_items_search", "/api/v1/purchase-orders/vendor-items/search", {"q": "pla"}, {200}),
    ("purchase_orders_list", "/api/v1/purchase-orders/", None, {200}),
    ("payments_list", "/api/v1/payments", None, {200}),
    # builder w6 modules
    ("products_list", "/api/v1/products", None, {200}),
    ("product_missing", f"/api/v1/products/{MISSING}", None, {404}),
    ("spools_list", "/api/v1/spools/", None, {200}),
    ("spool_missing", f"/api/v1/spools/{MISSING}", None, {404}),
    ("quality_policy", "/api/v1/quality/policy", None, {200}),
    ("quality_inspection_queue", "/api/v1/quality/inspection-queue", None, {200}),
    ("quality_plans_list", "/api/v1/quality-plans", None, {200}),
    ("scheduling_board", "/api/v1/scheduling/board", _WINDOW, {200}),
    ("resource_schedule_missing", f"/api/v1/resources/{MISSING}/schedule", None, {404}),
    ("operation_types_list", "/api/v1/operation-types", None, {200}),
    ("traceability_spool_missing", f"/api/v1/traceability/forward/spool/{MISSING}", None, {404}),
    ("price_levels_list", "/api/v1/price-levels", None, {200}),
    ("tax_rates_list", "/api/v1/tax-rates", None, {200}),
    ("sales_orders_status_transitions", "/api/v1/sales-orders/status-transitions", None, {200}),
    ("sales_orders_payment_statuses", "/api/v1/sales-orders/payment-statuses", None, {200}),
    ("sales_orders_list", "/api/v1/sales-orders/", None, {200}),
    # settings and quotes
    ("settings_company", "/api/v1/settings/company", None, {200}),
    ("settings_ai", "/api/v1/settings/ai", None, {200}),
    ("quotes_list", "/api/v1/quotes/", None, {200}),
]


@pytest.fixture
def operator_headers(role_headers):
    return role_headers("operator")


@pytest.mark.parametrize(
    "label,path,params,accepted", OPERATOR_READS, ids=[r[0] for r in OPERATOR_READS]
)
def test_operator_keeps_staff_read(unauthed_client, operator_headers, label, path, params, accepted):
    resp = unauthed_client.get(path, params=params, headers=operator_headers)
    assert resp.status_code in accepted, f"{label}: {resp.status_code} {resp.text[:300]}"


def test_operator_keeps_sales_order_staff_reads(
    unauthed_client, operator_headers, make_product, make_sales_order
):
    product = make_product(selling_price=Decimal("10.00"))
    so = make_sales_order(product_id=product.id, status="confirmed")
    for suffix in ("blocking-issues", "fulfillment-status"):
        resp = unauthed_client.get(f"/api/v1/sales-orders/{so.id}/{suffix}", headers=operator_headers)
        assert resp.status_code == 200, f"{suffix}: {resp.status_code} {resp.text[:300]}"


def test_operator_can_still_create_a_spool(
    unauthed_client, operator_headers, make_product
):
    # Spools are day-to-day operator work; the gate must not turn writes into 403.
    material = make_product(item_type="supply", unit="G", is_raw_material=True)
    resp = unauthed_client.post(
        "/api/v1/spools/",
        json={
            "spool_number": f"SPL-OP-{uuid.uuid4().hex[:6]}",
            "product_id": material.id,
            "initial_weight_kg": 1.0,
            "current_weight_kg": 1.0,
        },
        headers=operator_headers,
    )
    assert resp.status_code == 200, resp.text


class TestAdminOnlyRoutesStillRefuseOperators:
    """Routes that were already admin-only keep refusing operators."""

    def test_sales_order_status_change(self, unauthed_client, db, operator_headers, make_product, make_sales_order):
        product = make_product(selling_price=Decimal("10.00"))
        so = make_sales_order(product_id=product.id, status="confirmed")
        resp = unauthed_client.patch(
            f"/api/v1/sales-orders/{so.id}/status",
            json={"status": "in_production"},
            headers=operator_headers,
        )
        assert resp.status_code == 403
        db.expire_all()
        assert db.get(SalesOrder, so.id).status == "confirmed"

    def test_create_tax_rate(self, unauthed_client, db, operator_headers):
        name = f"Operator tax {uuid.uuid4().hex[:6]}"
        resp = unauthed_client.post(
            "/api/v1/tax-rates",
            json={"name": name, "rate_percent": 5.0},
            headers=operator_headers,
        )
        assert resp.status_code == 403
        assert db.query(TaxRate).filter(TaxRate.name == name).count() == 0

    def test_update_company_settings(self, unauthed_client, operator_headers):
        resp = unauthed_client.patch(
            "/api/v1/settings/company",
            json={"company_name": "Operator Was Here"},
            headers=operator_headers,
        )
        assert resp.status_code == 403

    def test_security_status(self, unauthed_client, operator_headers):
        resp = unauthed_client.get("/api/v1/security/status", headers=operator_headers)
        assert resp.status_code == 403


class TestScrapReasonWritesAreAdminOnly:
    """Intentional change (owner decision 3): scrap-reason writes are admin-only.

    Their only UI (AdminScrapReasons) is admin-only already; operators keep
    reading the list they pick from when scrapping an operation.
    """

    def _reason(self, db):
        reason = ScrapReason(
            code=f"op-test-{uuid.uuid4().hex[:8]}",
            name="Operator regression reason",
            active=True,
            sequence=0,
        )
        db.add(reason)
        db.flush()
        return reason

    def test_operator_can_still_read_scrap_reasons(self, unauthed_client, operator_headers):
        resp = unauthed_client.get("/api/v1/production-orders/scrap-reasons", headers=operator_headers)
        assert resp.status_code == 200, resp.text

    def test_operator_cannot_create_scrap_reason(self, unauthed_client, db, operator_headers):
        code = f"op-new-{uuid.uuid4().hex[:8]}"
        resp = unauthed_client.post(
            "/api/v1/production-orders/scrap-reasons",
            json={"code": code, "name": "Operator reason"},
            headers=operator_headers,
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin access required"
        assert db.query(ScrapReason).filter(ScrapReason.code == code).count() == 0

    def test_operator_cannot_update_or_delete_scrap_reason(self, unauthed_client, db, operator_headers):
        reason = self._reason(db)
        resp = unauthed_client.put(
            f"/api/v1/production-orders/scrap-reasons/{reason.id}",
            json={"name": "Renamed by operator", "active": False},
            headers=operator_headers,
        )
        assert resp.status_code == 403
        resp = unauthed_client.delete(
            f"/api/v1/production-orders/scrap-reasons/{reason.id}", headers=operator_headers
        )
        assert resp.status_code == 403
        db.expire_all()
        refreshed = db.get(ScrapReason, reason.id)
        assert refreshed is not None
        assert refreshed.name == "Operator regression reason"
        assert refreshed.active is True
