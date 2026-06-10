"""
Auth tests for admin accounting, audit, traceability, and uploads endpoints.

All admin/* endpoints must require staff authentication and return 401
when accessed without a valid Bearer token or session cookie.

Covers the security gaps identified in the #683 sibling audit:
- /admin/accounting/*  (financial data: sales journal, payments, COGS, tax)
- /admin/audit/*       (transaction audit log — internal ops data)
- /admin/traceability/* (serial numbers, material lots — previously allowed any user)
- /admin/uploads/*     (file write endpoint — previously allowed any user)
"""


class TestAccountingUnauthenticated:
    """All /admin/accounting endpoints must reject unauthenticated requests with 401."""

    def test_sales_journal_requires_auth(self, unauthed_client):
        """GET /admin/accounting/sales-journal returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/accounting/sales-journal")
        assert resp.status_code == 401

    def test_sales_journal_export_requires_auth(self, unauthed_client):
        """GET /admin/accounting/sales-journal/export returns 401 without auth."""
        resp = unauthed_client.get(
            "/api/v1/admin/accounting/sales-journal/export"
            "?start_date=2025-01-01T00:00:00Z&end_date=2025-12-31T00:00:00Z"
        )
        assert resp.status_code == 401

    def test_payments_journal_requires_auth(self, unauthed_client):
        """GET /admin/accounting/payments-journal returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/accounting/payments-journal")
        assert resp.status_code == 401

    def test_dashboard_requires_auth(self, unauthed_client):
        """GET /admin/accounting/dashboard returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/accounting/dashboard")
        assert resp.status_code == 401

    def test_tax_summary_requires_auth(self, unauthed_client):
        """GET /admin/accounting/tax-summary returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/accounting/tax-summary")
        assert resp.status_code == 401

    def test_cogs_summary_requires_auth(self, unauthed_client):
        """GET /admin/accounting/cogs-summary returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/accounting/cogs-summary")
        assert resp.status_code == 401

    def test_inventory_by_account_requires_auth(self, unauthed_client):
        """GET /admin/accounting/inventory-by-account returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/accounting/inventory-by-account")
        assert resp.status_code == 401

    def test_transactions_journal_requires_auth(self, unauthed_client):
        """GET /admin/accounting/transactions-journal returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/accounting/transactions-journal")
        assert resp.status_code == 401


class TestAccountingAuthenticated:
    """Authenticated staff users can reach accounting endpoints (no 401/403)."""

    def test_sales_journal_accessible_with_auth(self, client):
        """GET /admin/accounting/sales-journal returns 200 with valid auth."""
        resp = client.get("/api/v1/admin/accounting/sales-journal")
        assert resp.status_code == 200

    def test_payments_journal_accessible_with_auth(self, client):
        """GET /admin/accounting/payments-journal returns 200 with valid auth."""
        resp = client.get("/api/v1/admin/accounting/payments-journal")
        assert resp.status_code == 200


class TestAuditUnauthenticated:
    """All /admin/audit endpoints must reject unauthenticated requests with 401."""

    def test_transactions_audit_requires_auth(self, unauthed_client):
        """GET /admin/audit/transactions returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/audit/transactions")
        assert resp.status_code == 401

    def test_audit_summary_requires_auth(self, unauthed_client):
        """GET /admin/audit/transactions/summary returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/audit/transactions/summary")
        assert resp.status_code == 401


class TestAuditAuthenticated:
    """Authenticated staff users can reach audit endpoints (no 401/403)."""

    def test_audit_summary_accessible_with_auth(self, client):
        """GET /admin/audit/transactions/summary returns 200 with valid auth."""
        resp = client.get("/api/v1/admin/audit/transactions/summary")
        assert resp.status_code == 200


class TestTraceabilityUnauthenticated:
    """All /admin/traceability endpoints must reject unauthenticated requests with 401."""

    def test_profiles_requires_auth(self, unauthed_client):
        """GET /admin/traceability/profiles returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/traceability/profiles")
        assert resp.status_code == 401

    def test_lots_requires_auth(self, unauthed_client):
        """GET /admin/traceability/lots returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/traceability/lots")
        assert resp.status_code == 401

    def test_serials_requires_auth(self, unauthed_client):
        """GET /admin/traceability/serials returns 401 without auth."""
        resp = unauthed_client.get("/api/v1/admin/traceability/serials")
        assert resp.status_code == 401


class TestTraceabilityAuthenticated:
    """Authenticated staff users can reach traceability endpoints (no 401/403)."""

    def test_profiles_accessible_with_auth(self, client):
        """GET /admin/traceability/profiles returns 200 with valid auth."""
        resp = client.get("/api/v1/admin/traceability/profiles")
        assert resp.status_code == 200
