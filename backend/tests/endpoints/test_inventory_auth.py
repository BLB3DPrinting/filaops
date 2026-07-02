"""
Auth tests for inventory mutation endpoints (/api/v1/inventory/).

Regression coverage for the PR-D0 security fix. Four endpoints previously
depended on ``get_current_user`` (ANY authenticated user, including
``account_type='customer'`` portal/buyer accounts) instead of
``get_current_staff_user``. That let a non-staff account rewrite on-hand
inventory and approve/void negative-inventory transactions.

These tests lock in that:
  * an unauthenticated request is rejected with 401, and
  * an authenticated NON-STAFF (customer) user is rejected with 403,
matching the rest of the admin/inventory surface (e.g. reject-held).
"""
import pytest

# The four endpoints hardened by PR-D0, keyed by (method, path).
MUTATION_ENDPOINTS = [
    ("post", "/api/v1/inventory/transactions/1/approve-negative?approval_reason=x"),
    ("get", "/api/v1/inventory/negative-inventory-report"),
    ("post", "/api/v1/inventory/validate-consistency"),
    (
        "post",
        "/api/v1/inventory/adjust-quantity"
        "?product_id=1&new_on_hand_quantity=5&adjustment_reason=count",
    ),
]


@pytest.fixture
def customer_client(db):
    """TestClient authenticated as a NON-STAFF (account_type='customer') user.

    Mirrors the conftest ``client`` fixture (DB override + Bearer token) but
    the token is minted for a freshly created customer account so the
    ``get_current_staff_user`` role check is exercised, not just auth.
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.db.session import get_db
    from app.models.user import User
    from app.core.security import create_access_token

    customer = User(
        email=f"buyer-{id(db)}@example.com",
        password_hash="not-a-real-hash",
        account_type="customer",
        status="active",
    )
    db.add(customer)
    db.flush()
    token = create_access_token(user_id=customer.id)

    def _override_get_db():
        try:
            yield db
        finally:
            pass  # db fixture handles rollback

    app.dependency_overrides[get_db] = _override_get_db

    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c

    app.dependency_overrides.clear()


class TestInventoryMutationsUnauthenticated:
    """Inventory mutation endpoints reject unauthenticated requests with 401."""

    @pytest.mark.parametrize("method,path", MUTATION_ENDPOINTS)
    def test_requires_auth(self, unauthed_client, method, path):
        resp = getattr(unauthed_client, method)(path)
        assert resp.status_code == 401


class TestInventoryMutationsNonStaffForbidden:
    """Authenticated non-staff (customer) users are rejected with 403.

    This is the PR-D0 regression: before the fix these resolved via
    ``get_current_user`` and a customer account could reach the handler.
    """

    @pytest.mark.parametrize("method,path", MUTATION_ENDPOINTS)
    def test_non_staff_forbidden(self, customer_client, method, path):
        resp = getattr(customer_client, method)(path)
        assert resp.status_code == 403
