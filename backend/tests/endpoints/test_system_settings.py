"""
Tests for the system_settings admin endpoints (PR-01).

Covers:
- GET /system/settings/{key} — happy path, unknown key, missing row, auth/permission
- GET /system/settings (list) — filtered to registered keys only
- PUT /system/settings/{key} — validation matrix, unknown key, auth/permission,
  row-missing -> create path, IntegrityError race fallback
- is_valid_origin — boundary cases for the strict origin shape check
"""
import uuid

import pytest
from sqlalchemy import text

from app.api.v1.endpoints.system_settings import is_valid_origin
from app.models.system_setting import SystemSetting
from app.models.user import User


SETTINGS_URL = "/api/v1/system/settings"
PORTAL_KEY = "pro_portal_origins"
QUOTER_KEY = "pro_quoter_origins"


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(autouse=True)
def _disable_rate_limits():
    """Disable slowapi rate limiting for all tests in this module."""
    from app.core.limiter import limiter

    original_enabled = getattr(limiter, "_enabled", True)
    limiter.enabled = False
    yield
    limiter.enabled = original_enabled


@pytest.fixture
def seeded_settings(db):
    """Ensure the two PRO origin rows exist (idempotent ON CONFLICT)."""
    db.execute(
        text(
            "INSERT INTO system_settings (key, value, updated_at) VALUES "
            "(:k1, '[]'::json, now()), (:k2, '[]'::json, now()) "
            "ON CONFLICT (key) DO NOTHING"
        ),
        {"k1": PORTAL_KEY, "k2": QUOTER_KEY},
    )
    db.flush()
    yield


@pytest.fixture
def unseeded_settings(db):
    """Force the two PRO origin rows to be ABSENT for tests that need empty DB.

    Necessary because the CI test DB is migrated (alembic upgrade head) before
    pytest runs, which seeds these rows via migration 080's INSERT. The
    transaction-isolated ``db`` fixture rolls back the DELETE at test end,
    restoring the migration-seeded state for subsequent tests.
    """
    db.execute(
        text("DELETE FROM system_settings WHERE key IN (:k1, :k2)"),
        {"k1": PORTAL_KEY, "k2": QUOTER_KEY},
    )
    db.flush()
    yield


@pytest.fixture
def non_admin_user(db):
    """Create a non-admin user for 403 tests."""
    from app.core.security import hash_password

    uid = uuid.uuid4().hex[:8]
    user = User(
        email=f"nonadmin-{uid}@filaops.dev",
        password_hash=hash_password("TestPass123!"),
        first_name="NonAdmin",
        last_name="User",
        account_type="customer",
        status="active",
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def non_admin_client(db, non_admin_user):
    """TestClient authenticated as a non-admin user."""
    from fastapi.testclient import TestClient
    from app.core.security import create_access_token
    from app.db.session import get_db
    from app.main import app

    def _override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    token = create_access_token(user_id=non_admin_user.id)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
    app.dependency_overrides.clear()


# =============================================================================
# is_valid_origin (strict shape check)
# =============================================================================


@pytest.mark.parametrize(
    "value",
    [
        "https://shop.example.com",
        "http://localhost:3000",
        "https://192.168.1.50",
        "https://example.com:8080",
        "http://erp",  # single-word intranet hostname is a valid origin
    ],
)
def test_is_valid_origin_accepts_real_origins(value):
    assert is_valid_origin(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "shop.example.com",                     # no scheme
        "ftp://shop.example.com",               # wrong scheme
        "https://",                             # no host
        "http://",                              # no host
        "https://shop.example.com/",            # trailing slash
        "https://shop.example.com/path",        # has path
        "https://shop.example.com?x=1",         # query string
        "https://shop.example.com#frag",        # fragment
        "https://user@shop.example.com",        # userinfo
        "",                                     # empty
        "   ",                                  # whitespace-only
        None,                                   # not a string
        123,                                    # not a string
        ["https://shop.example.com"],           # not a string
    ],
)
def test_is_valid_origin_rejects_malformed(value):
    assert is_valid_origin(value) is False


# =============================================================================
# GET /{key}
# =============================================================================


def test_get_setting_happy_path(client, seeded_settings):
    resp = client.get(f"{SETTINGS_URL}/{PORTAL_KEY}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"] == PORTAL_KEY
    assert body["value"] == []
    assert body["updated_at"] is not None


def test_get_setting_unknown_key_returns_404(client, seeded_settings):
    resp = client.get(f"{SETTINGS_URL}/foo_bar")
    assert resp.status_code == 404
    assert "unknown setting key" in resp.json()["detail"]


def test_get_setting_registered_but_unseeded_returns_404(client, unseeded_settings):
    # Endpoint should distinguish "unknown key" (key not in SETTING_VALIDATORS)
    # from "registered key with no row" — the latter is the migration-not-run
    # or row-manually-deleted case.
    resp = client.get(f"{SETTINGS_URL}/{PORTAL_KEY}")
    assert resp.status_code == 404
    assert "has no row" in resp.json()["detail"]


def test_get_setting_no_auth_returns_401(unauthed_client, seeded_settings):
    resp = unauthed_client.get(f"{SETTINGS_URL}/{PORTAL_KEY}")
    assert resp.status_code == 401


def test_get_setting_non_admin_returns_403(non_admin_client, seeded_settings):
    resp = non_admin_client.get(f"{SETTINGS_URL}/{PORTAL_KEY}")
    assert resp.status_code == 403


# =============================================================================
# GET / (list)
# =============================================================================


def test_list_settings_returns_only_registered_keys(client, seeded_settings, db):
    # Inject an unregistered row to confirm the filter excludes it.
    db.execute(
        text(
            "INSERT INTO system_settings (key, value, updated_at) "
            "VALUES ('legacy_orphan', '\"junk\"'::json, now())"
        ),
    )
    db.flush()

    resp = client.get(SETTINGS_URL)
    assert resp.status_code == 200
    keys = [row["key"] for row in resp.json()]
    assert PORTAL_KEY in keys
    assert QUOTER_KEY in keys
    assert "legacy_orphan" not in keys


def test_list_settings_orders_by_key(client, seeded_settings):
    resp = client.get(SETTINGS_URL)
    assert resp.status_code == 200
    keys = [row["key"] for row in resp.json()]
    assert keys == sorted(keys)


def test_list_settings_no_auth_returns_401(unauthed_client, seeded_settings):
    resp = unauthed_client.get(SETTINGS_URL)
    assert resp.status_code == 401


def test_list_settings_non_admin_returns_403(non_admin_client, seeded_settings):
    resp = non_admin_client.get(SETTINGS_URL)
    assert resp.status_code == 403


# =============================================================================
# PUT /{key}
# =============================================================================


def test_put_valid_origins_persists(client, seeded_settings):
    payload = {"value": ["https://shop.example.com", "http://localhost:3000"]}
    resp = client.put(f"{SETTINGS_URL}/{PORTAL_KEY}", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["value"] == payload["value"]
    assert body["updated_by"] is not None  # captures admin email

    # Round-trip: GET should now return the persisted value
    resp = client.get(f"{SETTINGS_URL}/{PORTAL_KEY}")
    assert resp.status_code == 200
    assert resp.json()["value"] == payload["value"]


def test_put_empty_list_is_valid(client, seeded_settings):
    """Empty list = 'no origins listed' is a legitimate config."""
    resp = client.put(f"{SETTINGS_URL}/{PORTAL_KEY}", json={"value": []})
    assert resp.status_code == 200
    assert resp.json()["value"] == []


@pytest.mark.parametrize(
    "bad_origin",
    [
        "shop.example.com",                     # no scheme
        "ftp://shop.example.com",
        "https://shop.example.com/",            # trailing slash
        "https://shop.example.com/path",
        "https://shop.example.com?x=1",         # query string
        "https://shop.example.com#frag",        # fragment
        "https://user@shop.example.com",        # userinfo
    ],
)
def test_put_rejects_malformed_origin_with_400(client, seeded_settings, bad_origin):
    resp = client.put(f"{SETTINGS_URL}/{PORTAL_KEY}", json={"value": [bad_origin]})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "invalid origin" in detail
    assert bad_origin in detail


def test_put_rejects_non_list_with_400(client, seeded_settings):
    resp = client.put(f"{SETTINGS_URL}/{PORTAL_KEY}", json={"value": "not-a-list"})
    assert resp.status_code == 400
    assert "must be a list of origin strings" in resp.json()["detail"]


def test_put_rejects_non_string_in_list_with_400(client, seeded_settings):
    resp = client.put(f"{SETTINGS_URL}/{PORTAL_KEY}", json={"value": [123]})
    assert resp.status_code == 400
    assert "must be a string" in resp.json()["detail"]


def test_put_unknown_key_returns_404(client, seeded_settings):
    resp = client.put(f"{SETTINGS_URL}/foo_bar", json={"value": []})
    assert resp.status_code == 404
    assert "unknown setting key" in resp.json()["detail"]


def test_put_no_auth_returns_401(unauthed_client, seeded_settings):
    resp = unauthed_client.put(
        f"{SETTINGS_URL}/{PORTAL_KEY}", json={"value": []}
    )
    assert resp.status_code == 401


def test_put_non_admin_returns_403(non_admin_client, seeded_settings):
    resp = non_admin_client.put(
        f"{SETTINGS_URL}/{PORTAL_KEY}", json={"value": []}
    )
    assert resp.status_code == 403


def test_put_creates_row_when_missing(client, unseeded_settings, db):
    """Spec: if the seeded row is missing (manually deleted, never seeded),
    PUT recreates it instead of 404ing. Mirrors get_or_create_settings."""
    # unseeded_settings fixture deleted both PRO rows for this test.
    existing = (
        db.query(SystemSetting).filter(SystemSetting.key == PORTAL_KEY).first()
    )
    assert existing is None  # precondition

    resp = client.put(
        f"{SETTINGS_URL}/{PORTAL_KEY}",
        json={"value": ["https://shop.example.com"]},
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == ["https://shop.example.com"]


def test_put_updates_existing_row(client, seeded_settings, db):
    """Sanity: existing row gets updated, not duplicated."""
    pre_count = (
        db.query(SystemSetting).filter(SystemSetting.key == PORTAL_KEY).count()
    )
    assert pre_count == 1

    client.put(
        f"{SETTINGS_URL}/{PORTAL_KEY}",
        json={"value": ["https://shop.example.com"]},
    )

    post_count = (
        db.query(SystemSetting).filter(SystemSetting.key == PORTAL_KEY).count()
    )
    assert post_count == 1
