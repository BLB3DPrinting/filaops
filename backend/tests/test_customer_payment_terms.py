"""
Tests for Customer Payment Terms CRUD

Verifies that:
- New customers default to COD payment terms
- Customers can be created with explicit payment terms + credit limit
- Payment terms can be updated on existing customers
- Approving terms sets timestamp and approver
- Revoking terms clears timestamp and approver
- Payment terms appear in customer list responses
"""
import uuid
import pytest


def _unique_email():
    """Generate a unique email for test isolation."""
    return f"cpt-{uuid.uuid4().hex[:8]}@test.filaops.dev"


class TestCustomerPaymentTerms:
    """Payment terms CRUD via /api/v1/admin/customers."""

    # ------------------------------------------------------------------ #
    # 1. Default terms
    # ------------------------------------------------------------------ #
    def test_create_customer_default_terms(self, client):
        """New customers without explicit terms default to COD."""
        resp = client.post("/api/v1/admin/customers/", json={
            "email": _unique_email(),
            "first_name": "Default",
            "last_name": "Terms",
            "company_name": "DefaultCo",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["payment_terms"] == "cod"
        assert data["credit_limit"] is None
        assert data["approved_for_terms"] is False

    # ------------------------------------------------------------------ #
    # 2. Explicit terms on create
    # ------------------------------------------------------------------ #
    def test_create_customer_with_terms(self, client):
        """Create a customer with net30 payment terms and credit limit."""
        resp = client.post("/api/v1/admin/customers/", json={
            "email": _unique_email(),
            "first_name": "Net30",
            "last_name": "Customer",
            "company_name": "CreditCo",
            "payment_terms": "net30",
            "credit_limit": 5000.00,
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["payment_terms"] == "net30"
        assert float(data["credit_limit"]) == 5000.00
        assert data["approved_for_terms"] is False

    # ------------------------------------------------------------------ #
    # 3. Update payment terms
    # ------------------------------------------------------------------ #
    def test_update_customer_payment_terms(self, client):
        """Update payment terms on an existing customer."""
        # Create with default
        create_resp = client.post("/api/v1/admin/customers/", json={
            "email": _unique_email(),
            "first_name": "Update",
            "last_name": "Terms",
            "company_name": "UpdateCo",
        })
        assert create_resp.status_code == 201, create_resp.text
        customer_id = create_resp.json()["id"]

        # Update to net15 with credit limit (requires approval)
        update_resp = client.patch(f"/api/v1/admin/customers/{customer_id}", json={
            "payment_terms": "net15",
            "credit_limit": 2500.00,
            "approved_for_terms": True,
        })
        assert update_resp.status_code == 200, update_resp.text
        data = update_resp.json()
        assert data["payment_terms"] == "net15"
        assert float(data["credit_limit"]) == 2500.00

    # ------------------------------------------------------------------ #
    # 4. Approve sets timestamp
    # ------------------------------------------------------------------ #
    def test_approve_for_terms_sets_timestamp(self, client):
        """Approving a customer for terms sets approved_for_terms_at and _by."""
        create_resp = client.post("/api/v1/admin/customers/", json={
            "email": _unique_email(),
            "first_name": "Approve",
            "last_name": "Test",
            "company_name": "ApproveCo",
            "payment_terms": "net30",
        })
        assert create_resp.status_code == 201, create_resp.text
        customer_id = create_resp.json()["id"]
        assert create_resp.json()["approved_for_terms"] is False
        assert create_resp.json()["approved_for_terms_at"] is None

        # Approve
        approve_resp = client.patch(f"/api/v1/admin/customers/{customer_id}", json={
            "approved_for_terms": True,
        })
        assert approve_resp.status_code == 200, approve_resp.text
        data = approve_resp.json()
        assert data["approved_for_terms"] is True
        assert data["approved_for_terms_at"] is not None
        assert data["approved_for_terms_by"] is not None

    # ------------------------------------------------------------------ #
    # 5. Revoke clears timestamp
    # ------------------------------------------------------------------ #
    def test_revoke_terms_clears_timestamp(self, client):
        """Revoking terms approval clears approved_for_terms_at and _by."""
        # Create and approve
        create_resp = client.post("/api/v1/admin/customers/", json={
            "email": _unique_email(),
            "first_name": "Revoke",
            "last_name": "Test",
            "company_name": "RevokeCo",
            "payment_terms": "net30",
        })
        assert create_resp.status_code == 201, create_resp.text
        customer_id = create_resp.json()["id"]

        approve_resp = client.patch(f"/api/v1/admin/customers/{customer_id}", json={
            "approved_for_terms": True,
        })
        assert approve_resp.status_code == 200, approve_resp.text
        assert approve_resp.json()["approved_for_terms"] is True
        assert approve_resp.json()["approved_for_terms_at"] is not None

        # Revoke
        revoke_resp = client.patch(f"/api/v1/admin/customers/{customer_id}", json={
            "approved_for_terms": False,
        })
        assert revoke_resp.status_code == 200, revoke_resp.text
        data = revoke_resp.json()
        assert data["approved_for_terms"] is False
        assert data["approved_for_terms_at"] is None
        assert data["approved_for_terms_by"] is None

    # ------------------------------------------------------------------ #
    # 6. Net terms without approval is rejected
    # ------------------------------------------------------------------ #
    def test_net_terms_without_approval_rejected(self, client):
        """Setting net terms without approved_for_terms is rejected."""
        create_resp = client.post("/api/v1/admin/customers/", json={
            "email": _unique_email(),
            "first_name": "Bypass",
            "last_name": "Test",
            "company_name": "BypassCo",
        })
        assert create_resp.status_code == 201
        customer_id = create_resp.json()["id"]

        # Try to set net30 without approval — should fail
        resp = client.patch(f"/api/v1/admin/customers/{customer_id}", json={
            "payment_terms": "net30",
        })
        assert resp.status_code == 422

    # ------------------------------------------------------------------ #
    # 7. Payment terms in list response
    # ------------------------------------------------------------------ #
    def test_payment_terms_in_list_response(self, client):
        """Payment terms field appears in customer list endpoint."""
        email = _unique_email()
        create_resp = client.post("/api/v1/admin/customers/", json={
            "email": email,
            "first_name": "List",
            "last_name": "Check",
            "company_name": "ListCo",
            "payment_terms": "net30",
        })
        assert create_resp.status_code == 201, create_resp.text

        # List and find our customer
        list_resp = client.get("/api/v1/admin/customers/", params={"search": email})
        assert list_resp.status_code == 200, list_resp.text
        customers = list_resp.json()
        match = [c for c in customers if c["email"] == email]
        assert len(match) == 1
        assert match[0]["payment_terms"] == "net30"
