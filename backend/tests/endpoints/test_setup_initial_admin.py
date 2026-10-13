"""
POST /api/v1/setup/initial-admin saves the customer contact email.

Customer emails tell people which address to contact. A fresh install must
not leave Company Settings without one, so the setup wizard's "Customer
Contact Email" is stored, and when it is left blank the new admin's own
email is used.
"""
import uuid

import pytest
from sqlalchemy import text

SETUP_URL = "/api/v1/setup/initial-admin"
PASSWORD = "Abcdefg1!xyz"


@pytest.fixture
def fresh_install(db, monkeypatch):
    """No users and no Company Settings row, inside the test transaction."""
    from app.core.config import settings
    from app.core.limiter import limiter

    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(settings, "AUTH_MODE", "header")
    db.execute(text("DELETE FROM company_settings"))
    try:
        with db.begin_nested():
            db.execute(text("DELETE FROM users"))
    except Exception as exc:  # pragma: no cover - depends on seeded rows
        pytest.skip(f"seeded users cannot be removed in this database: {exc}")
    return db


def _admin_email():
    return f"owner-{uuid.uuid4().hex[:8]}@filaops.dev"


def _company_settings(db):
    from app.models.company_settings import CompanySettings

    db.expire_all()
    return db.query(CompanySettings).filter(CompanySettings.id == 1).first()


def test_saves_the_contact_email_given(fresh_install, unauthed_client):
    resp = unauthed_client.post(SETUP_URL, json={
        "email": _admin_email(),
        "password": PASSWORD,
        "full_name": "Shop Owner",
        "company_name": "Acme Print Works",
        "company_email": "help@acmeprint.works",
    })

    assert resp.status_code == 200, resp.text
    row = _company_settings(fresh_install)
    assert row.company_name == "Acme Print Works"
    assert row.company_email == "help@acmeprint.works"


def test_blank_contact_email_uses_the_admin_email(fresh_install, unauthed_client):
    admin_email = _admin_email()

    resp = unauthed_client.post(SETUP_URL, json={
        "email": admin_email,
        "password": PASSWORD,
        "full_name": "Shop Owner",
    })

    assert resp.status_code == 200, resp.text
    row = _company_settings(fresh_install)
    assert row.company_email == admin_email
    assert row.company_name is None


def test_invalid_contact_email_is_rejected(fresh_install, unauthed_client):
    resp = unauthed_client.post(SETUP_URL, json={
        "email": _admin_email(),
        "password": PASSWORD,
        "full_name": "Shop Owner",
        "company_email": "not-an-email",
    })

    assert resp.status_code == 422
    assert _company_settings(fresh_install) is None
