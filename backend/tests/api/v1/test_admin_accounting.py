"""
Tests for Admin Accounting API endpoints.

Tests the admin-scoped accounting view endpoints at /api/v1/admin/accounting/:
- Inventory by account (GL-mapped inventory balances)
- Transactions journal (inventory transactions as journal entries)
- Order cost breakdown (per-order COGS analysis)
- COGS summary (period aggregation)
- Financial dashboard (MTD/YTD metrics)
- Sales journal (accrual-basis sales listing + CSV export)
- Tax summary (tax collected, by rate, by period + CSV export)
- Payments journal (payment transactions + CSV export)
- Sales export for tax time (CSV with auth required)

These endpoints are view-only (GET) and sit under the /api/v1/admin/ router.
Only /export/sales requires explicit staff auth; others rely on router-level access.
"""
import pytest
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date

BASE = "/api/v1/admin/accounting"


# =============================================================================
# HELPERS
# =============================================================================

def _uid():
    return uuid.uuid4().hex[:8]


# =============================================================================
# TEST: Inventory By Account
# =============================================================================

class TestInventoryByAccount:
    """Tests for GET /admin/accounting/inventory-by-account"""

    def test_success_returns_accounts(self, client):
        """Should return inventory balances grouped by GL account."""
        resp = client.get(f"{BASE}/inventory-by-account")
        assert resp.status_code == 200
        data = resp.json()

        assert "as_of" in data
        assert "accounts" in data
        assert "summary" in data
        assert isinstance(data["accounts"], list)

    def test_response_has_expected_account_codes(self, client):
        """Response should contain the three inventory asset accounts."""
        resp = client.get(f"{BASE}/inventory-by-account")
        data = resp.json()

        codes = {a["account_code"] for a in data["accounts"]}
        # Should have raw materials (1300), WIP (1310), finished goods (1320)
        assert "1300" in codes
        assert "1310" in codes
        assert "1320" in codes

    def test_summary_contains_expected_fields(self, client):
        """Summary should include raw_materials, wip, finished_goods, total_inventory."""
        resp = client.get(f"{BASE}/inventory-by-account")
        data = resp.json()
        summary = data["summary"]

        assert "raw_materials" in summary
        assert "wip" in summary
        assert "finished_goods" in summary
        assert "total_inventory" in summary

    def test_summary_total_is_sum_of_parts(self, client):
        """total_inventory should equal sum of raw_materials + wip + finished_goods."""
        resp = client.get(f"{BASE}/inventory-by-account")
        summary = resp.json()["summary"]

        expected = summary["raw_materials"] + summary["wip"] + summary["finished_goods"]
        assert abs(summary["total_inventory"] - expected) < 0.01

    def test_account_items_structure(self, client):
        """Each account entry should have account_code, account_name, total_value, items."""
        resp = client.get(f"{BASE}/inventory-by-account")
        data = resp.json()

        for account in data["accounts"]:
            assert "account_code" in account
            assert "account_name" in account
            assert "total_value" in account
            assert "total_units" in account
            assert "items" in account
            assert isinstance(account["items"], list)


# =============================================================================
# TEST: Transactions Journal
# =============================================================================

class TestTransactionsJournal:
    """Tests for GET /admin/accounting/transactions-journal"""

    def test_success_default_params(self, client):
        """Should return journal entries for the default 30-day period."""
        resp = client.get(f"{BASE}/transactions-journal")
        assert resp.status_code == 200
        data = resp.json()

        assert "period" in data
        assert "transaction_count" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)
        assert "Last 30 days" in data["period"]

    def test_custom_days_parameter(self, client):
        """Should accept custom days parameter."""
        resp = client.get(f"{BASE}/transactions-journal", params={"days": 7})
        assert resp.status_code == 200
        data = resp.json()
        assert "Last 7 days" in data["period"]

    def test_filter_by_order_id(self, client):
        """Should accept order_id filter parameter."""
        # Use an order_id that likely doesn't exist -- should still return 200
        resp = client.get(f"{BASE}/transactions-journal", params={"order_id": 999999})
        assert resp.status_code == 200
        data = resp.json()
        assert data["transaction_count"] == 0

    def test_entry_structure(self, client):
        """Journal entries should have required accounting fields."""
        resp = client.get(f"{BASE}/transactions-journal", params={"days": 365})
        data = resp.json()

        if data["entries"]:
            entry = data["entries"][0]
            assert "date" in entry
            assert "transaction_id" in entry
            assert "transaction_type" in entry
            assert "value" in entry
            assert "debit_account" in entry
            assert "credit_account" in entry

    def test_journal_entry_has_debit_credit_accounts(self, client):
        """Entries with known transaction types should map to DR/CR accounts."""
        resp = client.get(f"{BASE}/transactions-journal", params={"days": 365})
        data = resp.json()

        for entry in data["entries"]:
            # At least one account should be populated for known types
            if entry["transaction_type"] in ("reservation", "consumption", "receipt", "scrap", "release"):
                # debit or credit should be non-null
                has_accounts = entry["debit_account"] is not None or entry["credit_account"] is not None
                assert has_accounts, (
                    f"Transaction type {entry['transaction_type']} should map to accounts"
                )


# =============================================================================
# TEST: Order Cost Breakdown
# =============================================================================

class TestOrderCostBreakdown:
    """Tests for GET /admin/accounting/order-cost-breakdown/{order_id}"""

    def test_nonexistent_order_returns_error(self, client):
        """Should return 404 for a missing order."""
        resp = client.get(f"{BASE}/order-cost-breakdown/999999")
        assert resp.status_code == 404
        data = resp.json()
        assert "not found" in data["detail"].lower()

    def test_existing_order_returns_breakdown(self, client, db, make_sales_order):
        """Should return cost breakdown structure for a valid order."""
        so = make_sales_order(
            quantity=2,
            unit_price=Decimal("25.00"),
            status="draft",
        )
        db.commit()

        resp = client.get(f"{BASE}/order-cost-breakdown/{so.id}")
        assert resp.status_code == 200
        data = resp.json()

        assert data["order_id"] == so.id
        assert "revenue" in data
        assert "costs" in data
        assert "total_cogs" in data
        assert "gross_profit" in data
        assert "gross_margin_pct" in data
        assert "note" in data

    def test_cost_breakdown_structure(self, client, db, make_sales_order):
        """Cost breakdown should include materials, labor, and packaging sections."""
        so = make_sales_order(quantity=1, unit_price=Decimal("10.00"))
        db.commit()

        resp = client.get(f"{BASE}/order-cost-breakdown/{so.id}")
        data = resp.json()
        costs = data["costs"]

        assert "materials" in costs
        assert "labor" in costs
        assert "packaging" in costs
        assert "total" in costs["materials"]
        assert "items" in costs["materials"]
        assert "total" in costs["packaging"]
        assert "items" in costs["packaging"]

    def test_revenue_excludes_tax(self, client, db, make_sales_order):
        """Revenue should exclude tax amount per GAAP."""
        so = make_sales_order(
            quantity=1,
            unit_price=Decimal("100.00"),
            tax_amount=Decimal("8.00"),
        )
        # grand_total includes tax
        so.grand_total = Decimal("108.00")
        db.commit()

        resp = client.get(f"{BASE}/order-cost-breakdown/{so.id}")
        data = resp.json()

        # Revenue = grand_total - tax_amount = 108 - 8 = 100
        assert data["revenue"] == 100.0


# =============================================================================
# TEST: COGS Summary
# =============================================================================

class TestCOGSSummary:
    """Tests for GET /admin/accounting/cogs-summary"""

    def test_success_default_period(self, client):
        """Should return COGS summary for default 30-day period."""
        resp = client.get(f"{BASE}/cogs-summary")
        assert resp.status_code == 200
        data = resp.json()

        assert "period" in data
        assert "orders_shipped" in data
        assert "revenue" in data
        assert "cogs" in data
        assert "gross_profit" in data
        assert "gross_margin_pct" in data

    def test_custom_days_parameter(self, client):
        """Should accept custom days parameter."""
        resp = client.get(f"{BASE}/cogs-summary", params={"days": 90})
        assert resp.status_code == 200
        data = resp.json()
        assert "Last 90 days" in data["period"]

    def test_cogs_has_breakdown(self, client):
        """COGS should break down into materials, labor, packaging, and total."""
        resp = client.get(f"{BASE}/cogs-summary")
        data = resp.json()
        cogs = data["cogs"]

        assert "materials" in cogs
        assert "labor" in cogs
        assert "packaging" in cogs
        assert "total" in cogs

    def test_cogs_total_is_sum_of_components(self, client):
        """COGS total should equal materials + labor + packaging."""
        resp = client.get(f"{BASE}/cogs-summary")
        cogs = resp.json()["cogs"]

        expected = cogs["materials"] + cogs["labor"] + cogs["packaging"]
        assert abs(cogs["total"] - expected) < 0.01

    def test_shipping_is_separate(self, client):
        """Shipping should be reported separately as operating expense, not COGS."""
        resp = client.get(f"{BASE}/cogs-summary")
        data = resp.json()

        assert "shipping_expense" in data
        # Shipping should NOT be included in COGS
        assert isinstance(data["shipping_expense"], (int, float))


# =============================================================================
# TEST: Financial Dashboard
# =============================================================================

class TestFinancialDashboard:
    """Tests for GET /admin/accounting/dashboard"""

    def test_success(self, client):
        """Should return dashboard with financial metrics."""
        resp = client.get(f"{BASE}/dashboard")
        assert resp.status_code == 200
        data = resp.json()

        assert "as_of" in data
        assert "fiscal_year_start" in data
        assert "revenue" in data
        assert "payments" in data
        assert "tax" in data
        assert "cogs" in data
        assert "profit" in data

    def test_revenue_section_structure(self, client):
        """Revenue section should have MTD and YTD metrics."""
        resp = client.get(f"{BASE}/dashboard")
        revenue = resp.json()["revenue"]

        assert "mtd" in revenue
        assert "mtd_orders" in revenue
        assert "ytd" in revenue
        assert "ytd_orders" in revenue

    def test_payments_section_structure(self, client):
        """Payments section should have received amounts and outstanding."""
        resp = client.get(f"{BASE}/dashboard")
        payments = resp.json()["payments"]

        assert "mtd_received" in payments
        assert "ytd_received" in payments
        assert "outstanding" in payments
        assert "outstanding_orders" in payments

    def test_tax_section_structure(self, client):
        """Tax section should have MTD and YTD collected amounts."""
        resp = client.get(f"{BASE}/dashboard")
        tax = resp.json()["tax"]

        assert "mtd_collected" in tax
        assert "ytd_collected" in tax

    def test_profit_section_structure(self, client):
        """Profit section should have gross profit and margin percentage."""
        resp = client.get(f"{BASE}/dashboard")
        profit = resp.json()["profit"]

        assert "mtd_gross" in profit
        assert "mtd_margin_pct" in profit

    def test_cogs_section_structure(self, client):
        """COGS section should have MTD amount."""
        resp = client.get(f"{BASE}/dashboard")
        cogs = resp.json()["cogs"]

        assert "mtd" in cogs

    def test_numeric_values_are_numbers(self, client):
        """All numeric fields should be actual numbers, not strings."""
        resp = client.get(f"{BASE}/dashboard")
        data = resp.json()

        assert isinstance(data["revenue"]["mtd"], (int, float))
        assert isinstance(data["revenue"]["ytd"], (int, float))
        assert isinstance(data["payments"]["mtd_received"], (int, float))
        assert isinstance(data["payments"]["outstanding"], (int, float))
        assert isinstance(data["profit"]["mtd_gross"], (int, float))


# =============================================================================
# TEST: Sales Journal
# =============================================================================

class TestSalesJournal:
    """Tests for GET /admin/accounting/sales-journal"""

    def test_success_default_params(self, client):
        """Should return sales journal for the default 30-day period."""
        resp = client.get(f"{BASE}/sales-journal")
        assert resp.status_code == 200
        data = resp.json()

        assert "period" in data
        assert "totals" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_period_section_structure(self, client):
        """Period section should have start and end dates."""
        resp = client.get(f"{BASE}/sales-journal")
        period = resp.json()["period"]

        assert "start" in period
        assert "end" in period

    def test_totals_section_structure(self, client):
        """Totals section should include subtotal, tax, shipping, grand_total, order_count."""
        resp = client.get(f"{BASE}/sales-journal")
        totals = resp.json()["totals"]

        assert "subtotal" in totals
        assert "tax" in totals
        assert "shipping" in totals
        assert "grand_total" in totals
        assert "order_count" in totals

    def test_custom_date_range(self, client):
        """Should accept start_date and end_date parameters."""
        params = {
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2025-12-31T23:59:59",
        }
        resp = client.get(f"{BASE}/sales-journal", params=params)
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        """Should accept status filter parameter."""
        resp = client.get(f"{BASE}/sales-journal", params={"status": "shipped"})
        assert resp.status_code == 200
        data = resp.json()
        # All entries should have the filtered status
        for entry in data["entries"]:
            assert entry["status"] == "shipped"

    def test_entry_structure(self, client):
        """Sales journal entries should have all required fields."""
        # Use wide date range to try to find entries
        params = {
            "start_date": "2020-01-01T00:00:00",
            "end_date": "2030-12-31T23:59:59",
        }
        resp = client.get(f"{BASE}/sales-journal", params=params)
        data = resp.json()

        if data["entries"]:
            entry = data["entries"][0]
            expected_fields = [
                "date", "order_number", "order_id", "status",
                "payment_status", "subtotal", "tax_amount",
                "shipping", "grand_total",
            ]
            for field in expected_fields:
                assert field in entry, f"Missing field: {field}"

    def test_totals_match_entry_sum(self, client):
        """Totals should be consistent with the sum of entries."""
        params = {
            "start_date": "2020-01-01T00:00:00",
            "end_date": "2030-12-31T23:59:59",
        }
        resp = client.get(f"{BASE}/sales-journal", params=params)
        data = resp.json()

        if data["entries"]:
            entry_subtotal_sum = sum(e["subtotal"] for e in data["entries"])
            assert abs(data["totals"]["subtotal"] - entry_subtotal_sum) < 0.01

            entry_count = len(data["entries"])
            assert data["totals"]["order_count"] == entry_count


# =============================================================================
# TEST: Sales Journal Export (CSV)
# =============================================================================

class TestSalesJournalExport:
    """Tests for GET /admin/accounting/sales-journal/export"""

    def test_returns_csv(self, client):
        """Should return a CSV file response."""
        resp = client.get(f"{BASE}/sales-journal/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_content_disposition(self, client):
        """Response should have Content-Disposition header for download."""
        resp = client.get(f"{BASE}/sales-journal/export")
        assert "content-disposition" in resp.headers
        assert "attachment" in resp.headers["content-disposition"]
        assert "sales_journal_" in resp.headers["content-disposition"]

    def test_csv_has_header_row(self, client):
        """CSV should contain a header row with column names."""
        resp = client.get(f"{BASE}/sales-journal/export")
        content = resp.text
        # Should contain disclaimer header and column headers
        assert "FilaOps Sales Journal" in content
        assert "Date" in content
        assert "Order Number" in content

    def test_custom_date_range(self, client):
        """Should accept start_date and end_date for CSV export."""
        params = {
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2025-06-30T23:59:59",
        }
        resp = client.get(f"{BASE}/sales-journal/export", params=params)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")


# =============================================================================
# TEST: Tax Summary
# =============================================================================

class TestTaxSummary:
    """Tests for GET /admin/accounting/tax-summary"""

    def test_success_default_period(self, client):
        """Should return tax summary for the default month period."""
        resp = client.get(f"{BASE}/tax-summary")
        assert resp.status_code == 200
        data = resp.json()

        assert "period" in data
        assert "period_start" in data
        assert "period_end" in data
        assert "summary" in data
        assert "by_rate" in data
        assert "monthly_breakdown" in data

    def test_month_period(self, client):
        """Should accept period=month."""
        resp = client.get(f"{BASE}/tax-summary", params={"period": "month"})
        assert resp.status_code == 200

    def test_quarter_period(self, client):
        """Should accept period=quarter."""
        resp = client.get(f"{BASE}/tax-summary", params={"period": "quarter"})
        assert resp.status_code == 200

    def test_year_period(self, client):
        """Should accept period=year."""
        resp = client.get(f"{BASE}/tax-summary", params={"period": "year"})
        assert resp.status_code == 200

    def test_summary_section_structure(self, client):
        """Summary should have total_sales, taxable_sales, non_taxable_sales, tax_collected."""
        resp = client.get(f"{BASE}/tax-summary")
        summary = resp.json()["summary"]

        assert "total_sales" in summary
        assert "taxable_sales" in summary
        assert "non_taxable_sales" in summary
        assert "tax_collected" in summary
        assert "order_count" in summary

    def test_total_sales_equals_sum(self, client):
        """total_sales should equal taxable_sales + non_taxable_sales."""
        resp = client.get(f"{BASE}/tax-summary")
        summary = resp.json()["summary"]

        expected = summary["taxable_sales"] + summary["non_taxable_sales"]
        assert abs(summary["total_sales"] - expected) < 0.01

    def test_pending_section(self, client):
        """Should include pending tax information."""
        resp = client.get(f"{BASE}/tax-summary")
        data = resp.json()

        assert "pending" in data
        assert "tax_amount" in data["pending"]
        assert "order_count" in data["pending"]

    def test_by_rate_structure(self, client):
        """by_rate entries should have rate_pct, taxable_sales, tax_collected."""
        resp = client.get(f"{BASE}/tax-summary")
        data = resp.json()

        for rate in data["by_rate"]:
            assert "rate_pct" in rate
            assert "taxable_sales" in rate
            assert "tax_collected" in rate
            assert "order_count" in rate

    def test_monthly_breakdown_structure(self, client):
        """Monthly breakdown entries should have month, taxable_sales, tax_collected."""
        resp = client.get(f"{BASE}/tax-summary")
        data = resp.json()

        for month in data["monthly_breakdown"]:
            assert "month" in month
            assert "taxable_sales" in month
            assert "tax_collected" in month
            assert "order_count" in month


# =============================================================================
# TEST: Tax Summary Export (CSV)
# =============================================================================

class TestTaxSummaryExport:
    """Tests for GET /admin/accounting/tax-summary/export"""

    def test_returns_csv(self, client):
        """Should return a CSV file response."""
        resp = client.get(f"{BASE}/tax-summary/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_content_disposition(self, client):
        """Response should have Content-Disposition header for download."""
        resp = client.get(f"{BASE}/tax-summary/export")
        assert "content-disposition" in resp.headers
        assert "attachment" in resp.headers["content-disposition"]
        assert "tax_summary_" in resp.headers["content-disposition"]

    def test_csv_has_disclaimer(self, client):
        """CSV should contain disclaimer header."""
        resp = client.get(f"{BASE}/tax-summary/export")
        content = resp.text
        assert "FilaOps Tax Summary" in content
        assert "NOT a tax filing" in content

    def test_csv_has_column_headers(self, client):
        """CSV should contain expected column headers."""
        resp = client.get(f"{BASE}/tax-summary/export")
        content = resp.text
        assert "Date" in content
        assert "Order Number" in content
        assert "Taxable" in content
        assert "Tax Amount" in content

    def test_custom_period_parameter(self, client):
        """Should accept period parameter for export."""
        resp = client.get(f"{BASE}/tax-summary/export", params={"period": "year"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_totals_row(self, client):
        """CSV should contain a TOTALS summary row."""
        resp = client.get(f"{BASE}/tax-summary/export")
        content = resp.text
        assert "TOTALS" in content


# =============================================================================
# TEST: Payments Journal
# =============================================================================

class TestPaymentsJournal:
    """Tests for GET /admin/accounting/payments-journal"""

    def test_success_default_params(self, client):
        """Should return payments journal for the default period."""
        resp = client.get(f"{BASE}/payments-journal")
        assert resp.status_code == 200
        data = resp.json()

        assert "period" in data
        assert "totals" in data
        assert "by_method" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_period_section(self, client):
        """Period section should have start and end dates."""
        resp = client.get(f"{BASE}/payments-journal")
        period = resp.json()["period"]

        assert "start" in period
        assert "end" in period

    def test_totals_section_structure(self, client):
        """Totals section should have payments, refunds, net, and count."""
        resp = client.get(f"{BASE}/payments-journal")
        totals = resp.json()["totals"]

        assert "payments" in totals
        assert "refunds" in totals
        assert "net" in totals
        assert "count" in totals

    def test_net_equals_payments_minus_refunds(self, client):
        """Net should equal payments minus refunds."""
        resp = client.get(f"{BASE}/payments-journal")
        totals = resp.json()["totals"]

        expected_net = totals["payments"] - totals["refunds"]
        assert abs(totals["net"] - expected_net) < 0.01

    def test_custom_date_range(self, client):
        """Should accept start_date and end_date parameters."""
        params = {
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2025-12-31T23:59:59",
        }
        resp = client.get(f"{BASE}/payments-journal", params=params)
        assert resp.status_code == 200

    def test_filter_by_payment_method(self, client):
        """Should accept payment_method filter parameter."""
        resp = client.get(
            f"{BASE}/payments-journal",
            params={"payment_method": "credit_card"},
        )
        assert resp.status_code == 200

    def test_entry_structure(self, client):
        """Payment entries should have expected fields."""
        # Use wide date range
        params = {
            "start_date": "2020-01-01T00:00:00",
            "end_date": "2030-12-31T23:59:59",
        }
        resp = client.get(f"{BASE}/payments-journal", params=params)
        data = resp.json()

        if data["entries"]:
            entry = data["entries"][0]
            expected_fields = [
                "date", "payment_number", "order_number",
                "payment_method", "payment_type", "amount",
            ]
            for field in expected_fields:
                assert field in entry, f"Missing field: {field}"

    def test_by_method_is_dict(self, client):
        """by_method should be a dictionary of payment method totals."""
        resp = client.get(f"{BASE}/payments-journal")
        data = resp.json()
        assert isinstance(data["by_method"], dict)


# =============================================================================
# TEST: Payments Journal Export (CSV)
# =============================================================================

class TestPaymentsJournalExport:
    """Tests for GET /admin/accounting/payments-journal/export"""

    def test_returns_csv(self, client):
        """Should return a CSV file response."""
        resp = client.get(f"{BASE}/payments-journal/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_csv_has_content_disposition(self, client):
        """Response should have Content-Disposition header for download."""
        resp = client.get(f"{BASE}/payments-journal/export")
        assert "content-disposition" in resp.headers
        assert "attachment" in resp.headers["content-disposition"]
        assert "payments_" in resp.headers["content-disposition"]

    def test_csv_has_disclaimer(self, client):
        """CSV should contain disclaimer header."""
        resp = client.get(f"{BASE}/payments-journal/export")
        content = resp.text
        assert "FilaOps Payments Journal" in content
        assert "Verify with qualified accountant" in content

    def test_csv_has_column_headers(self, client):
        """CSV should contain expected column headers."""
        resp = client.get(f"{BASE}/payments-journal/export")
        content = resp.text
        assert "Date" in content
        assert "Payment Number" in content
        assert "Order Number" in content
        assert "Amount" in content

    def test_custom_date_range(self, client):
        """Should accept start_date and end_date for CSV export."""
        params = {
            "start_date": "2025-01-01T00:00:00",
            "end_date": "2025-12-31T23:59:59",
        }
        resp = client.get(f"{BASE}/payments-journal/export", params=params)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")


# =============================================================================
# TEST: Sales Export (Tax Time) -- requires auth
# =============================================================================

class TestSalesExport:
    """Tests for GET /admin/accounting/export/sales (requires staff auth)"""

    def test_requires_auth(self, unauthed_client):
        """Should return 401 without authentication."""
        resp = unauthed_client.get(
            f"{BASE}/export/sales",
            params={"start_date": "2025-01-01", "end_date": "2025-12-31"},
        )
        assert resp.status_code == 401

    def test_success_with_auth(self, client):
        """Should return CSV when authenticated."""
        params = {
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        }
        resp = client.get(f"{BASE}/export/sales", params=params)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

    def test_requires_start_date(self, client):
        """Should require start_date parameter."""
        resp = client.get(f"{BASE}/export/sales", params={"end_date": "2025-12-31"})
        assert resp.status_code == 422

    def test_requires_end_date(self, client):
        """Should require end_date parameter."""
        resp = client.get(f"{BASE}/export/sales", params={"start_date": "2025-01-01"})
        assert resp.status_code == 422

    def test_csv_has_disclaimer(self, client):
        """CSV should contain disclaimer header."""
        params = {"start_date": "2025-01-01", "end_date": "2025-12-31"}
        resp = client.get(f"{BASE}/export/sales", params=params)
        content = resp.text
        assert "FilaOps Sales Export" in content
        assert "For Reference Only" in content

    def test_csv_has_column_headers(self, client):
        """CSV should contain expected column headers."""
        params = {"start_date": "2025-01-01", "end_date": "2025-12-31"}
        resp = client.get(f"{BASE}/export/sales", params=params)
        content = resp.text
        assert "Order Number" in content
        assert "Subtotal" in content
        assert "Tax Amount" in content
        assert "Shipping" in content
        assert "Total" in content

    def test_csv_filename_includes_dates(self, client):
        """Content-Disposition filename should include the date range."""
        params = {"start_date": "2025-01-01", "end_date": "2025-12-31"}
        resp = client.get(f"{BASE}/export/sales", params=params)
        disposition = resp.headers.get("content-disposition", "")
        assert "sales_export_" in disposition
        assert "20250101" in disposition
        assert "20251231" in disposition

    def test_csv_contains_order_data(self, client, db, make_sales_order):
        """CSV should include sales orders from the requested date range."""
        so = make_sales_order(
            quantity=3,
            unit_price=Decimal("20.00"),
            status="shipped",
        )
        db.commit()

        # Use a wide date range to capture the order
        params = {"start_date": "2020-01-01", "end_date": "2030-12-31"}
        resp = client.get(f"{BASE}/export/sales", params=params)
        content = resp.text

        # The order number should appear in the CSV
        assert so.order_number in content


# =============================================================================
# TEST: Dashboard with Seeded Data
# =============================================================================

class TestDashboardWithData:
    """Tests for dashboard behavior with actual order data."""

    def test_shipped_order_appears_in_revenue(self, client, db, make_sales_order):
        """Shipped orders should contribute to revenue metrics."""
        now = datetime.now(timezone.utc)
        so = make_sales_order(
            quantity=1,
            unit_price=Decimal("50.00"),
            status="shipped",
        )
        so.shipped_at = now
        db.commit()

        resp = client.get(f"{BASE}/dashboard")
        data = resp.json()

        # Revenue MTD should be at least 50
        assert data["revenue"]["mtd"] >= 50.0

    def test_outstanding_payments_tracked(self, client, db, make_sales_order):
        """Orders with pending payment should show in outstanding."""
        so = make_sales_order(
            quantity=1,
            unit_price=Decimal("75.00"),
            status="confirmed",
            payment_status="pending",
        )
        db.commit()

        resp = client.get(f"{BASE}/dashboard")
        data = resp.json()

        # Should have at least one outstanding order
        assert data["payments"]["outstanding_orders"] >= 1
        assert data["payments"]["outstanding"] >= 75.0


# =============================================================================
# TEST: COGS Summary with Shipped Orders
# =============================================================================

class TestCOGSWithData:
    """Tests for COGS summary with shipped order data."""

    def test_shipped_order_counted(self, client, db, make_sales_order):
        """Shipped orders within the period should be counted."""
        now = datetime.now(timezone.utc)
        so = make_sales_order(
            quantity=2,
            unit_price=Decimal("30.00"),
            status="shipped",
        )
        so.shipped_at = now
        db.commit()

        resp = client.get(f"{BASE}/cogs-summary", params={"days": 30})
        data = resp.json()

        assert data["orders_shipped"] >= 1
        assert data["revenue"] >= 60.0

    def test_revenue_calculation(self, client, db, make_sales_order):
        """Revenue should use total_price (excludes tax per GAAP)."""
        now = datetime.now(timezone.utc)
        so = make_sales_order(
            quantity=1,
            unit_price=Decimal("100.00"),
            status="shipped",
        )
        so.shipped_at = now
        so.total_price = Decimal("100.00")
        db.commit()

        resp = client.get(f"{BASE}/cogs-summary", params={"days": 30})
        data = resp.json()

        assert data["revenue"] >= 100.0


# =============================================================================
# TEST: Cross-Endpoint Consistency
# =============================================================================

class TestCrossEndpointConsistency:
    """Tests that verify data consistency across related endpoints."""

    def test_inventory_accounts_are_assets(self, client):
        """Inventory accounts (1300, 1310, 1320) should be asset accounts."""
        resp = client.get(f"{BASE}/inventory-by-account")
        data = resp.json()

        for account in data["accounts"]:
            # All inventory accounts should be in the 1xxx range (assets)
            code = account["account_code"]
            assert code.startswith("1"), (
                f"Account {code} ({account['account_name']}) should be an asset account"
            )

    def test_cogs_summary_values_non_negative(self, client):
        """All COGS values should be non-negative."""
        resp = client.get(f"{BASE}/cogs-summary")
        data = resp.json()

        assert data["orders_shipped"] >= 0
        assert data["revenue"] >= 0
        assert data["cogs"]["materials"] >= 0
        assert data["cogs"]["labor"] >= 0
        assert data["cogs"]["packaging"] >= 0
        assert data["cogs"]["total"] >= 0
        assert data["shipping_expense"] >= 0

    def test_dashboard_values_non_negative(self, client):
        """Dashboard metric values should be non-negative."""
        resp = client.get(f"{BASE}/dashboard")
        data = resp.json()

        assert data["revenue"]["mtd"] >= 0
        assert data["revenue"]["ytd"] >= 0
        assert data["revenue"]["mtd_orders"] >= 0
        assert data["revenue"]["ytd_orders"] >= 0
        assert data["payments"]["mtd_received"] >= 0
        assert data["payments"]["ytd_received"] >= 0
        assert data["payments"]["outstanding"] >= 0

    def test_tax_summary_values_non_negative(self, client):
        """Tax summary values should be non-negative."""
        resp = client.get(f"{BASE}/tax-summary")
        summary = resp.json()["summary"]

        assert summary["total_sales"] >= 0
        assert summary["taxable_sales"] >= 0
        assert summary["non_taxable_sales"] >= 0
        assert summary["tax_collected"] >= 0
        assert summary["order_count"] >= 0


# =============================================================================
# TEST: Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_transactions_journal_zero_days(self, client):
        """Should handle days=0 gracefully."""
        resp = client.get(f"{BASE}/transactions-journal", params={"days": 0})
        assert resp.status_code == 200
        data = resp.json()
        assert "Last 0 days" in data["period"]

    def test_transactions_journal_large_days(self, client):
        """Should handle very large day ranges."""
        resp = client.get(f"{BASE}/transactions-journal", params={"days": 3650})
        assert resp.status_code == 200

    def test_cogs_summary_single_day(self, client):
        """Should handle days=1."""
        resp = client.get(f"{BASE}/cogs-summary", params={"days": 1})
        assert resp.status_code == 200

    def test_order_cost_breakdown_string_id(self, client):
        """Should return 422 for non-integer order_id."""
        resp = client.get(f"{BASE}/order-cost-breakdown/not-a-number")
        assert resp.status_code == 422

    def test_sales_journal_no_results(self, client):
        """Should return empty entries for a period with no shipped orders."""
        params = {
            "start_date": "2000-01-01T00:00:00",
            "end_date": "2000-01-02T00:00:00",
        }
        resp = client.get(f"{BASE}/sales-journal", params=params)
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert data["totals"]["order_count"] == 0
        assert data["totals"]["subtotal"] == 0
        assert data["totals"]["grand_total"] == 0

    def test_payments_journal_no_results(self, client):
        """Should return empty entries for a period with no payments."""
        params = {
            "start_date": "2000-01-01T00:00:00",
            "end_date": "2000-01-02T00:00:00",
        }
        resp = client.get(f"{BASE}/payments-journal", params=params)
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"] == []
        assert data["totals"]["count"] == 0
        assert data["totals"]["payments"] == 0
        assert data["totals"]["refunds"] == 0
        assert data["totals"]["net"] == 0

    def test_sales_export_invalid_date_format(self, client):
        """Should return 422 for invalid date format."""
        params = {"start_date": "not-a-date", "end_date": "2025-12-31"}
        resp = client.get(f"{BASE}/export/sales", params=params)
        assert resp.status_code == 422

    def test_multiple_endpoints_dont_error(self, client):
        """Smoke test: all major endpoints should return 200."""
        endpoints = [
            f"{BASE}/inventory-by-account",
            f"{BASE}/transactions-journal",
            f"{BASE}/cogs-summary",
            f"{BASE}/dashboard",
            f"{BASE}/sales-journal",
            f"{BASE}/sales-journal/export",
            f"{BASE}/tax-summary",
            f"{BASE}/tax-summary/export",
            f"{BASE}/payments-journal",
            f"{BASE}/payments-journal/export",
        ]
        for endpoint in endpoints:
            resp = client.get(endpoint)
            assert resp.status_code == 200, (
                f"Endpoint {endpoint} returned {resp.status_code}: {resp.text[:200]}"
            )
