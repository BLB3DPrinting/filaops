"""
Tests for admin user management endpoints.

Endpoints under test:
    GET    /api/v1/admin/users/                    — List admin/operator users
    GET    /api/v1/admin/users/stats/summary       — User stats summary
    GET    /api/v1/admin/users/{user_id}           — Get single user
    POST   /api/v1/admin/users/                    — Create admin/operator user
    PATCH  /api/v1/admin/users/{user_id}           — Update user
    POST   /api/v1/admin/users/{user_id}/reset-password  — Reset password
    DELETE /api/v1/admin/users/{user_id}           — Deactivate user (soft delete)
    POST   /api/v1/admin/users/{user_id}/reactivate      — Reactivate user
"""
import uuid

import pytest

from app.core import plugin_registry

BASE_URL = "/api/v1/admin/users"


# =============================================================================
# Tier control for seat caps
# =============================================================================

@pytest.fixture
def set_tier():
    """Set the plugin_registry tier for a test, restoring the default after.

    Seat-cap enforcement (app.core.seat_limits) reads the live tier from
    plugin_registry. Tests that want to exercise a specific tier call this;
    the registry is reset to community defaults on teardown so tests stay
    isolated.
    """
    def _apply(tier: str) -> None:
        plugin_registry.set_tier(tier)

    yield _apply
    plugin_registry.reset()


@pytest.fixture(autouse=True)
def _unlimited_seats_for_crud_tests(request):
    """Give the general CRUD suite an unlimited (professional) seat tier.

    The default community tier caps active staff at 1 seat, which would block
    the many operators/admins these CRUD tests create. The dedicated seat-cap
    suite (TestMultiUserSeatCaps) opts out via the ``seat_caps`` marker so it
    can drive the tier itself.
    """
    if request.node.get_closest_marker("seat_caps"):
        yield
        return
    plugin_registry.set_tier("professional")
    try:
        yield
    finally:
        plugin_registry.reset()


# =============================================================================
# Helpers
# =============================================================================

def _unique_email() -> str:
    """Generate a unique email address for test user creation."""
    return f"test-{uuid.uuid4().hex[:8]}@filaops.dev"


def _create_operator(client, **overrides) -> dict:
    """Create an operator user via the API and return the response JSON."""
    payload = {
        "email": _unique_email(),
        "password": "Temporary1!",
        "first_name": "Op",
        "last_name": "User",
        "account_type": "operator",
        **overrides,
    }
    resp = client.post(f"{BASE_URL}/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_admin(client, **overrides) -> dict:
    """Create an admin user via the API and return the response JSON."""
    payload = {
        "email": _unique_email(),
        "password": "Temporary1!",
        "first_name": "Admin",
        "last_name": "Extra",
        "account_type": "admin",
        **overrides,
    }
    resp = client.post(f"{BASE_URL}/", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# =============================================================================
# 1. TestAdminUserList — GET /
# =============================================================================

class TestAdminUserList:
    """GET /api/v1/admin/users/ — list admin and operator users."""

    def test_returns_200_with_seeded_admin(self, client):
        resp = client.get(f"{BASE_URL}/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # At minimum, the seeded admin (id=1) should be present
        ids = [u["id"] for u in data]
        assert 1 in ids

    def test_seeded_admin_has_expected_fields(self, client):
        resp = client.get(f"{BASE_URL}/")
        data = resp.json()
        admin = next(u for u in data if u["id"] == 1)
        assert admin["email"] == "test@filaops.dev"
        assert admin["account_type"] == "admin"
        assert admin["status"] == "active"
        assert "full_name" in admin
        assert "created_at" in admin

    def test_filter_by_account_type_admin(self, client):
        # Create an operator so both types exist
        _create_operator(client)
        resp = client.get(f"{BASE_URL}/", params={"account_type": "admin"})
        assert resp.status_code == 200
        for user in resp.json():
            assert user["account_type"] == "admin"

    def test_filter_by_account_type_operator(self, client):
        _create_operator(client)
        resp = client.get(f"{BASE_URL}/", params={"account_type": "operator"})
        assert resp.status_code == 200
        data = resp.json()
        for user in data:
            assert user["account_type"] == "operator"

    def test_never_returns_customer_type(self, client):
        resp = client.get(f"{BASE_URL}/", params={"include_inactive": True})
        assert resp.status_code == 200
        for user in resp.json():
            assert user["account_type"] in ("admin", "operator")

    def test_include_inactive_false_excludes_deactivated(self, client):
        op = _create_operator(client)
        # Deactivate the operator
        client.delete(f"{BASE_URL}/{op['id']}")
        # Default listing (include_inactive=False) should not include them
        resp = client.get(f"{BASE_URL}/")
        assert resp.status_code == 200
        ids = [u["id"] for u in resp.json()]
        assert op["id"] not in ids

    def test_include_inactive_true_shows_deactivated(self, client):
        op = _create_operator(client)
        client.delete(f"{BASE_URL}/{op['id']}")
        resp = client.get(f"{BASE_URL}/", params={"include_inactive": True})
        assert resp.status_code == 200
        ids = [u["id"] for u in resp.json()]
        assert op["id"] in ids

    def test_pagination_skip_and_limit(self, client):
        resp = client.get(f"{BASE_URL}/", params={"skip": 0, "limit": 1})
        assert resp.status_code == 200
        assert len(resp.json()) <= 1

    def test_pagination_skip_past_results(self, client):
        resp = client.get(f"{BASE_URL}/", params={"skip": 9999})
        assert resp.status_code == 200
        assert len(resp.json()) == 0


# =============================================================================
# 2. TestAdminUserStats — GET /stats/summary
# =============================================================================

class TestAdminUserStats:
    """GET /api/v1/admin/users/stats/summary — user stat counters."""

    def test_returns_200_with_expected_keys(self, client):
        resp = client.get(f"{BASE_URL}/stats/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "active_admins" in data
        assert "active_operators" in data
        assert "inactive_users" in data
        assert "total_active" in data

    def test_total_active_equals_admins_plus_operators(self, client):
        resp = client.get(f"{BASE_URL}/stats/summary")
        data = resp.json()
        assert data["total_active"] == data["active_admins"] + data["active_operators"]

    def test_at_least_one_admin(self, client):
        resp = client.get(f"{BASE_URL}/stats/summary")
        data = resp.json()
        assert data["active_admins"] >= 1

    def test_stats_reflect_new_operator(self, client):
        before = client.get(f"{BASE_URL}/stats/summary").json()
        _create_operator(client)
        after = client.get(f"{BASE_URL}/stats/summary").json()
        assert after["active_operators"] == before["active_operators"] + 1
        assert after["total_active"] == before["total_active"] + 1


# =============================================================================
# 3. TestAdminUserGet — GET /{user_id}
# =============================================================================

class TestAdminUserGet:
    """GET /api/v1/admin/users/{user_id} — single user detail."""

    def test_get_seeded_admin(self, client):
        resp = client.get(f"{BASE_URL}/1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == 1
        assert data["email"] == "test@filaops.dev"
        assert data["account_type"] == "admin"
        assert "full_name" in data
        assert "updated_at" in data

    def test_get_created_operator(self, client):
        op = _create_operator(client, first_name="Jane", last_name="Doe")
        resp = client.get(f"{BASE_URL}/{op['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == op["id"]
        assert data["full_name"] == "Jane Doe"

    def test_404_for_nonexistent_user(self, client):
        resp = client.get(f"{BASE_URL}/999999")
        assert resp.status_code == 404

    def test_404_for_customer_type_user(self, client, db):
        """A user with account_type='customer' should not be found by this endpoint."""
        from app.models.user import User
        customer = User(
            email=_unique_email(),
            password_hash="fake-hash",
            account_type="customer",
            status="active",
        )
        db.add(customer)
        db.flush()
        customer_id = customer.id

        resp = client.get(f"{BASE_URL}/{customer_id}")
        assert resp.status_code == 404

    def test_response_includes_full_name_from_parts(self, client):
        op = _create_operator(client, first_name="Alice", last_name="Smith")
        resp = client.get(f"{BASE_URL}/{op['id']}")
        assert resp.json()["full_name"] == "Alice Smith"

    def test_response_full_name_first_only(self, client):
        op = _create_operator(client, first_name="Solo", last_name=None)
        resp = client.get(f"{BASE_URL}/{op['id']}")
        assert resp.json()["full_name"] == "Solo"

    def test_response_full_name_none_when_no_names(self, client):
        op = _create_operator(client, first_name=None, last_name=None)
        resp = client.get(f"{BASE_URL}/{op['id']}")
        assert resp.json()["full_name"] is None


# =============================================================================
# 4. TestAdminUserCreate — POST /
# =============================================================================

class TestAdminUserCreate:
    """POST /api/v1/admin/users/ — create admin or operator."""

    def test_create_operator_returns_201(self, client):
        email = _unique_email()
        payload = {
            "email": email,
            "password": "SecurePass1!",
            "first_name": "New",
            "last_name": "Operator",
            "account_type": "operator",
        }
        resp = client.post(f"{BASE_URL}/", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == email
        assert data["account_type"] == "operator"
        assert data["status"] == "active"
        assert data["full_name"] == "New Operator"
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    def test_create_admin_returns_201(self, client):
        email = _unique_email()
        payload = {
            "email": email,
            "password": "SecurePass1!",
            "first_name": "Extra",
            "last_name": "Admin",
            "account_type": "admin",
        }
        resp = client.post(f"{BASE_URL}/", json=payload)
        assert resp.status_code == 201
        assert resp.json()["account_type"] == "admin"

    def test_duplicate_email_returns_400(self, client):
        email = _unique_email()
        _create_operator(client, email=email)
        # Second creation with the same email
        payload = {
            "email": email,
            "password": "AnotherPass1!",
            "first_name": "Dup",
            "last_name": "User",
            "account_type": "operator",
        }
        resp = client.post(f"{BASE_URL}/", json=payload)
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    def test_missing_required_fields_returns_422(self, client):
        resp = client.post(f"{BASE_URL}/", json={})
        assert resp.status_code == 422

    def test_invalid_account_type_returns_422(self, client):
        payload = {
            "email": _unique_email(),
            "password": "SecurePass1!",
            "account_type": "customer",
        }
        resp = client.post(f"{BASE_URL}/", json=payload)
        assert resp.status_code == 422

    def test_password_too_short_returns_422(self, client):
        payload = {
            "email": _unique_email(),
            "password": "short",
            "account_type": "operator",
        }
        resp = client.post(f"{BASE_URL}/", json=payload)
        assert resp.status_code == 422

    def test_response_does_not_expose_password(self, client):
        op = _create_operator(client)
        assert "password" not in op
        assert "password_hash" not in op


# =============================================================================
# 5. TestAdminUserUpdate — PATCH /{user_id}
# =============================================================================

class TestAdminUserUpdate:
    """PATCH /api/v1/admin/users/{user_id} — update user fields."""

    def test_update_name_fields(self, client):
        op = _create_operator(client)
        resp = client.patch(
            f"{BASE_URL}/{op['id']}",
            json={"first_name": "Updated", "last_name": "Name"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Name"
        assert data["full_name"] == "Updated Name"

    def test_update_email(self, client):
        op = _create_operator(client)
        new_email = _unique_email()
        resp = client.patch(
            f"{BASE_URL}/{op['id']}",
            json={"email": new_email},
        )
        assert resp.status_code == 200
        assert resp.json()["email"] == new_email

    def test_update_duplicate_email_returns_400(self, client):
        op1 = _create_operator(client)
        op2 = _create_operator(client)
        resp = client.patch(
            f"{BASE_URL}/{op2['id']}",
            json={"email": op1["email"]},
        )
        assert resp.status_code == 400
        assert "already in use" in resp.json()["detail"].lower()

    def test_self_demote_blocked(self, client):
        """Authenticated user (id=1) cannot demote themselves to operator."""
        resp = client.patch(
            f"{BASE_URL}/1",
            json={"account_type": "operator"},
        )
        assert resp.status_code == 400
        assert "cannot demote yourself" in resp.json()["detail"].lower()

    def test_self_deactivate_via_update_blocked(self, client):
        """Authenticated user (id=1) cannot set their own status to inactive."""
        resp = client.patch(
            f"{BASE_URL}/1",
            json={"status": "inactive"},
        )
        assert resp.status_code == 400
        assert "cannot deactivate" in resp.json()["detail"].lower()

    def test_self_suspend_via_update_blocked(self, client):
        """Authenticated user (id=1) cannot suspend themselves."""
        resp = client.patch(
            f"{BASE_URL}/1",
            json={"status": "suspended"},
        )
        assert resp.status_code == 400

    def test_last_admin_demote_blocked(self, client):
        """When user id=1 is the only admin, demoting them should fail.
        This test uses a second admin to try demoting id=1 indirectly.
        Since id=1 is the caller and cannot demote self, we instead verify
        that demoting the only *other* admin (when no others remain) fails."""
        # Create a second admin, then demote the original to operator
        # Since id=1 is last admin and self-demote is already blocked,
        # test that demoting a non-self admin who is the last fails.
        # First, make a second admin so id=1 is no longer the only one
        extra = _create_admin(client)
        # Now try to demote id=1 — still blocked by self-demotion check
        resp = client.patch(
            f"{BASE_URL}/1",
            json={"account_type": "operator"},
        )
        assert resp.status_code == 400
        # Clean up: deactivate extra admin so future tests stay consistent
        client.delete(f"{BASE_URL}/{extra['id']}")

    def test_demote_last_remaining_admin_blocked(self, client):
        """Create a second admin, deactivate it, then try to demote id=1.
        Since id=1 is both caller AND last admin, self-demotion blocks it."""
        extra = _create_admin(client)
        client.delete(f"{BASE_URL}/{extra['id']}")
        resp = client.patch(
            f"{BASE_URL}/1",
            json={"account_type": "operator"},
        )
        assert resp.status_code == 400

    def test_404_for_nonexistent_user(self, client):
        resp = client.patch(
            f"{BASE_URL}/999999",
            json={"first_name": "Ghost"},
        )
        assert resp.status_code == 404

    def test_promote_operator_to_admin(self, client):
        op = _create_operator(client)
        resp = client.patch(
            f"{BASE_URL}/{op['id']}",
            json={"account_type": "admin"},
        )
        assert resp.status_code == 200
        assert resp.json()["account_type"] == "admin"
        # Cleanup: deactivate so we don't leave extra admins
        client.delete(f"{BASE_URL}/{op['id']}")


# =============================================================================
# 6. TestAdminUserResetPassword — POST /{user_id}/reset-password
# =============================================================================

class TestAdminUserResetPassword:
    """POST /api/v1/admin/users/{user_id}/reset-password."""

    def test_reset_password_success(self, client):
        op = _create_operator(client)
        resp = client.post(
            f"{BASE_URL}/{op['id']}/reset-password",
            json={"new_password": "NewSecure99!"},
        )
        assert resp.status_code == 200
        assert "reset" in resp.json()["message"].lower()

    def test_reset_password_for_seeded_admin(self, client):
        resp = client.post(
            f"{BASE_URL}/1/reset-password",
            json={"new_password": "AdminNew99!"},
        )
        assert resp.status_code == 200

    def test_reset_password_404_for_nonexistent_user(self, client):
        resp = client.post(
            f"{BASE_URL}/999999/reset-password",
            json={"new_password": "Whatever99!"},
        )
        assert resp.status_code == 404

    def test_reset_password_too_short_returns_422(self, client):
        op = _create_operator(client)
        resp = client.post(
            f"{BASE_URL}/{op['id']}/reset-password",
            json={"new_password": "short"},
        )
        assert resp.status_code == 422

    def test_reset_password_missing_body_returns_422(self, client):
        op = _create_operator(client)
        resp = client.post(f"{BASE_URL}/{op['id']}/reset-password", json={})
        assert resp.status_code == 422


# =============================================================================
# 7. TestAdminUserDeactivate — DELETE /{user_id}
# =============================================================================

class TestAdminUserDeactivate:
    """DELETE /api/v1/admin/users/{user_id} — soft deactivate."""

    def test_deactivate_operator_returns_200(self, client):
        op = _create_operator(client)
        resp = client.delete(f"{BASE_URL}/{op['id']}")
        assert resp.status_code == 200
        assert "deactivated" in resp.json()["message"].lower()

    def test_deactivated_user_status_is_inactive(self, client):
        op = _create_operator(client)
        client.delete(f"{BASE_URL}/{op['id']}")
        # Fetch with include_inactive to see the deactivated user
        resp = client.get(f"{BASE_URL}/{op['id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "inactive"

    def test_self_deactivate_blocked(self, client):
        """Authenticated admin (id=1) cannot deactivate themselves."""
        resp = client.delete(f"{BASE_URL}/1")
        assert resp.status_code == 400
        assert "cannot deactivate" in resp.json()["detail"].lower()

    def test_last_admin_deactivate_blocked(self, client):
        """Cannot deactivate the last active admin user.
        Create and then deactivate a second admin, leaving only id=1.
        Then try to deactivate id=1 — blocked by self-deactivation rule.
        To truly test the 'last admin' path, we need a non-self admin
        who is the sole admin."""
        # Create two extra admins
        a1 = _create_admin(client)
        a2 = _create_admin(client)
        # Deactivate a2, leaving a1 and id=1
        client.delete(f"{BASE_URL}/{a2['id']}")
        # Deactivate a1, leaving only id=1
        client.delete(f"{BASE_URL}/{a1['id']}")
        # Now id=1 is the last admin. Self-deactivation is blocked.
        resp = client.delete(f"{BASE_URL}/1")
        assert resp.status_code == 400

    def test_deactivate_nonexistent_user_returns_404(self, client):
        resp = client.delete(f"{BASE_URL}/999999")
        assert resp.status_code == 404

    def test_deactivate_admin_when_another_admin_exists(self, client):
        """If there are multiple admins, deactivating one should succeed."""
        extra = _create_admin(client)
        resp = client.delete(f"{BASE_URL}/{extra['id']}")
        assert resp.status_code == 200


# =============================================================================
# 8. TestAdminUserReactivate — POST /{user_id}/reactivate
# =============================================================================

class TestAdminUserReactivate:
    """POST /api/v1/admin/users/{user_id}/reactivate."""

    def test_reactivate_inactive_user(self, client):
        op = _create_operator(client)
        client.delete(f"{BASE_URL}/{op['id']}")
        resp = client.post(f"{BASE_URL}/{op['id']}/reactivate")
        assert resp.status_code == 200
        assert "reactivated" in resp.json()["message"].lower()

    def test_reactivated_user_status_is_active(self, client):
        op = _create_operator(client)
        client.delete(f"{BASE_URL}/{op['id']}")
        client.post(f"{BASE_URL}/{op['id']}/reactivate")
        resp = client.get(f"{BASE_URL}/{op['id']}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_reactivate_already_active_returns_400(self, client):
        op = _create_operator(client)
        resp = client.post(f"{BASE_URL}/{op['id']}/reactivate")
        assert resp.status_code == 400
        assert "already active" in resp.json()["detail"].lower()

    def test_reactivate_nonexistent_user_returns_404(self, client):
        resp = client.post(f"{BASE_URL}/999999/reactivate")
        assert resp.status_code == 404


# =============================================================================
# 10. TestMultiUserSeatCaps — PR-D2: multi_user seat enforcement
# =============================================================================

def _seat_error(resp) -> str:
    """Extract the detail string from a seat-cap 403 response."""
    detail = resp.json().get("detail")
    return detail if isinstance(detail, str) else str(detail)


@pytest.mark.seat_caps
class TestMultiUserSeatCaps:
    """Seat-cap enforcement: community = 1 staff seat, PRO/enterprise unlimited.

    These tests drive the license tier directly via the ``set_tier`` fixture
    (the seeded admin id=1 is the single existing active staff seat). The
    ``seat_caps`` marker opts out of the module's default unlimited tier.
    """

    # ---- (a) community + 1 active staff -> 2nd staff blocked ----------------

    def test_community_second_staff_create_returns_403(self, client, set_tier):
        set_tier("community")
        # Seeded admin (id=1) already occupies the single community seat.
        payload = {
            "email": _unique_email(),
            "password": "SecurePass1!",
            "account_type": "operator",
        }
        resp = client.post(f"{BASE_URL}/", json=payload)
        assert resp.status_code == 403, resp.text
        assert "upgrade to pro" in _seat_error(resp).lower()

    def test_community_second_admin_create_returns_403(self, client, set_tier):
        set_tier("community")
        payload = {
            "email": _unique_email(),
            "password": "SecurePass1!",
            "account_type": "admin",
        }
        resp = client.post(f"{BASE_URL}/", json=payload)
        assert resp.status_code == 403, resp.text

    def test_community_reactivate_second_staff_returns_403(self, client, set_tier, db):
        """An inactive staff user cannot be reactivated when the single seat is
        already taken by the active seeded admin."""
        from app.models.user import User
        inactive = User(
            email=_unique_email(),
            password_hash="fake-hash",
            account_type="operator",
            status="inactive",
        )
        db.add(inactive)
        db.flush()

        set_tier("community")
        resp = client.post(f"{BASE_URL}/{inactive.id}/reactivate")
        assert resp.status_code == 403, resp.text
        assert "upgrade to pro" in _seat_error(resp).lower()

    def test_community_activate_via_patch_returns_403(self, client, set_tier, db):
        """PATCH status='active' on an inactive staff user is blocked at the cap."""
        from app.models.user import User
        inactive = User(
            email=_unique_email(),
            password_hash="fake-hash",
            account_type="operator",
            status="inactive",
        )
        db.add(inactive)
        db.flush()

        set_tier("community")
        resp = client.patch(f"{BASE_URL}/{inactive.id}", json={"status": "active"})
        assert resp.status_code == 403, resp.text

    # ---- (b) professional -> Nth staff allowed ------------------------------

    def test_professional_second_staff_create_allowed(self, client, set_tier):
        set_tier("professional")
        resp = client.post(
            f"{BASE_URL}/",
            json={
                "email": _unique_email(),
                "password": "SecurePass1!",
                "account_type": "operator",
            },
        )
        assert resp.status_code == 201, resp.text

    def test_professional_many_staff_allowed(self, client, set_tier):
        set_tier("professional")
        for _ in range(3):
            resp = client.post(
                f"{BASE_URL}/",
                json={
                    "email": _unique_email(),
                    "password": "SecurePass1!",
                    "account_type": "operator",
                },
            )
            assert resp.status_code == 201, resp.text

    def test_enterprise_second_staff_create_allowed(self, client, set_tier):
        set_tier("enterprise")
        resp = client.post(
            f"{BASE_URL}/",
            json={
                "email": _unique_email(),
                "password": "SecurePass1!",
                "account_type": "admin",
            },
        )
        assert resp.status_code == 201, resp.text

    # ---- (c) grandfather: community over cap keeps all users, blocks new ----

    def test_community_grandfathered_users_stay_usable(self, client, set_tier, db):
        """A community install already holding N (>1) active staff keeps every
        user active/usable; only ADDING the N+1th seat is blocked."""
        from app.models.user import User
        # Seed two extra active staff (id=1 seeded admin => 3 active total),
        # simulating a pre-existing multi-user community install.
        extra_ids = []
        for _ in range(2):
            u = User(
                email=_unique_email(),
                password_hash="fake-hash",
                account_type="operator",
                status="active",
            )
            db.add(u)
            db.flush()
            extra_ids.append(u.id)

        set_tier("community")

        # Grandfathered users remain fully usable: they are listed active,
        # readable, and editable — enforcement never deactivates them.
        listed = client.get(f"{BASE_URL}/", params={"account_type": "operator"}).json()
        listed_ids = {u["id"] for u in listed if u["status"] == "active"}
        assert set(extra_ids).issubset(listed_ids)

        for uid in extra_ids:
            got = client.get(f"{BASE_URL}/{uid}")
            assert got.status_code == 200
            assert got.json()["status"] == "active"
            # A non-status edit on an existing active user is not blocked.
            edit = client.patch(f"{BASE_URL}/{uid}", json={"first_name": "Kept"})
            assert edit.status_code == 200, edit.text

        # But adding the N+1th staff seat is blocked.
        resp = client.post(
            f"{BASE_URL}/",
            json={
                "email": _unique_email(),
                "password": "SecurePass1!",
                "account_type": "operator",
            },
        )
        assert resp.status_code == 403, resp.text

    def test_community_reactivate_over_cap_blocked_but_existing_untouched(
        self, client, set_tier, db
    ):
        """Over-cap community install: reactivating an inactive user is blocked,
        and the existing active users are left untouched."""
        from app.models.user import User
        active_extra = User(
            email=_unique_email(),
            password_hash="fake-hash",
            account_type="operator",
            status="active",
        )
        inactive_extra = User(
            email=_unique_email(),
            password_hash="fake-hash",
            account_type="operator",
            status="inactive",
        )
        db.add_all([active_extra, inactive_extra])
        db.flush()

        set_tier("community")
        resp = client.post(f"{BASE_URL}/{inactive_extra.id}/reactivate")
        assert resp.status_code == 403, resp.text

        # Existing active user is untouched (still active).
        got = client.get(f"{BASE_URL}/{active_extra.id}")
        assert got.status_code == 200
        assert got.json()["status"] == "active"

    # ---- (d) customer/portal accounts never consume a seat ------------------

    def test_community_customer_creation_not_blocked_by_seat_cap(
        self, client, set_tier, db
    ):
        """Creating a customer/portal account is NOT a staff seat and must not
        be blocked by the community cap, even when the staff seat is full.

        This endpoint only manages admin/operator, so we assert directly that a
        customer row can be created at community tier without seat enforcement
        touching it (customers are created via /admin/customers in production).
        """
        from app.models.user import User
        set_tier("community")

        # The staff seat is already full (seeded admin). Creating a customer
        # must still succeed — customers are not seats.
        customer = User(
            email=_unique_email(),
            password_hash="fake-hash",
            account_type="customer",
            status="active",
        )
        db.add(customer)
        db.flush()
        assert customer.id is not None

        # And a customer does not count against the staff seat cap: an admin
        # user create is still blocked purely by staff count, unaffected by the
        # newly added customer.
        from app.core.seat_limits import count_active_staff
        # Only the seeded admin counts as staff; the customer does not.
        assert count_active_staff(db) == 1


# =============================================================================
# 10b. TestSeatCapAdvisoryLock — TOCTOU serialization (no DB required)
# =============================================================================

class _FakeDialect:
    def __init__(self, name):
        self.name = name


class _FakeBind:
    def __init__(self, dialect_name):
        self.dialect = _FakeDialect(dialect_name)


class _FakeQuery:
    def __init__(self, count):
        self._count = count

    def filter(self, *a, **k):
        return self

    def count(self):
        return self._count


class _SpyDB:
    """Minimal stand-in for a Session that records execute() calls and reports a
    chosen SQL dialect, so we can assert the advisory-lock SQL is issued on the
    seat-check path without needing a live database."""

    def __init__(self, dialect_name="postgresql", active_staff=0):
        self.bind = _FakeBind(dialect_name)
        self._active_staff = active_staff
        self.executed = []  # list of (sql_text, params)

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        return None

    def query(self, *a, **k):
        return _FakeQuery(self._active_staff)


@pytest.mark.seat_caps
class TestSeatCapAdvisoryLock:
    """The seat check must serialize itself with a transaction-scoped advisory
    lock on Postgres to close the check-then-write TOCTOU window."""

    def test_advisory_lock_issued_on_postgres(self, set_tier):
        from app.core import seat_limits

        set_tier("community")
        spy = _SpyDB(dialect_name="postgresql", active_staff=0)
        # active_staff=0 under community cap of 1 -> allowed, no raise.
        seat_limits.enforce_seat_cap(spy)

        lock_calls = [sql for sql, _ in spy.executed if "pg_advisory_xact_lock" in sql]
        assert lock_calls, "expected a pg_advisory_xact_lock on the seat-check path"

    def test_advisory_lock_uses_module_key(self, set_tier):
        from app.core import seat_limits

        set_tier("community")
        spy = _SpyDB(dialect_name="postgresql", active_staff=0)
        seat_limits.enforce_seat_cap(spy)

        lock_params = [
            params for sql, params in spy.executed
            if "pg_advisory_xact_lock" in sql
        ]
        assert lock_params and lock_params[0]["key"] == seat_limits._SEAT_LOCK_KEY

    def test_no_advisory_lock_on_non_postgres(self, set_tier):
        """The lock is Postgres-only; other dialects must no-op (not error)."""
        from app.core import seat_limits

        set_tier("community")
        spy = _SpyDB(dialect_name="sqlite", active_staff=0)
        seat_limits.enforce_seat_cap(spy)

        lock_calls = [sql for sql, _ in spy.executed if "pg_advisory_xact_lock" in sql]
        assert not lock_calls, "advisory lock must not be issued on non-Postgres"

    def test_no_lock_when_tier_unlimited(self, set_tier):
        """Uncapped tiers short-circuit before any DB work — no lock taken."""
        from app.core import seat_limits

        set_tier("professional")
        spy = _SpyDB(dialect_name="postgresql", active_staff=99)
        seat_limits.enforce_seat_cap(spy)

        assert spy.executed == [], "unlimited tier must not touch the DB"


# =============================================================================
# 9. TestAdminUserAuth — 401 tests
# =============================================================================

class TestAdminUserAuth:
    """All admin user endpoints require authentication."""

    def test_list_returns_401_without_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/")
        assert resp.status_code == 401

    def test_stats_returns_401_without_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/stats/summary")
        assert resp.status_code == 401

    def test_get_user_returns_401_without_auth(self, unauthed_client):
        resp = unauthed_client.get(f"{BASE_URL}/1")
        assert resp.status_code == 401

    def test_create_returns_401_without_auth(self, unauthed_client):
        payload = {
            "email": _unique_email(),
            "password": "SecurePass1!",
            "account_type": "operator",
        }
        resp = unauthed_client.post(f"{BASE_URL}/", json=payload)
        assert resp.status_code == 401

    def test_update_returns_401_without_auth(self, unauthed_client):
        resp = unauthed_client.patch(f"{BASE_URL}/1", json={"first_name": "Nope"})
        assert resp.status_code == 401

    def test_reset_password_returns_401_without_auth(self, unauthed_client):
        resp = unauthed_client.post(
            f"{BASE_URL}/1/reset-password",
            json={"new_password": "Whatever99!"},
        )
        assert resp.status_code == 401

    def test_deactivate_returns_401_without_auth(self, unauthed_client):
        resp = unauthed_client.delete(f"{BASE_URL}/1")
        assert resp.status_code == 401

    def test_reactivate_returns_401_without_auth(self, unauthed_client):
        resp = unauthed_client.post(f"{BASE_URL}/1/reactivate")
        assert resp.status_code == 401
