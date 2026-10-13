"""
Company Settings: the shop-wide serial-number prefix.

- GET /api/v1/settings/company reports serial_number_prefix (SN- by default)
- PATCH accepts letters/digits/dashes, adds the trailing dash, rejects the rest
- only admins can change it; operators can read it
- saving other company fields leaves the prefix alone
"""
import pytest
from sqlalchemy import text

from app.models.company_settings import CompanySettings

BASE_URL = "/api/v1/settings/company"


def _set_prefix(db, value):
    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if settings is None:
        settings = CompanySettings(id=1)
        db.add(settings)
    db.flush()
    # Raw UPDATE: on a new row the ORM would swap None for its "SN-" default.
    db.execute(
        text("UPDATE company_settings SET serial_number_prefix = :v WHERE id = 1"),
        {"v": value},
    )
    db.expire_all()


class TestSerialPrefixSetting:
    def test_get_reports_neutral_default_when_unset(self, client, db):
        _set_prefix(db, None)
        resp = client.get(BASE_URL)
        assert resp.status_code == 200
        assert resp.json()["serial_number_prefix"] == "SN-"

    def test_get_reports_stored_prefix(self, client, db):
        _set_prefix(db, "BLB-")
        assert client.get(BASE_URL).json()["serial_number_prefix"] == "BLB-"

    @pytest.mark.parametrize("raw, saved", [
        ("ACME", "ACME-"),
        ("ACME-", "ACME-"),
        (" joes-ps ", "joes-ps-"),
    ])
    def test_admin_saves_normalised_prefix(self, client, db, raw, saved):
        resp = client.patch(BASE_URL, json={"serial_number_prefix": raw})
        assert resp.status_code == 200, resp.text
        assert resp.json()["serial_number_prefix"] == saved
        db.expire_all()
        assert db.get(CompanySettings, 1).serial_number_prefix == saved

    @pytest.mark.parametrize("bad", [
        None, "", "  ", "-SN", "SN_1", "S/N", "SN 1", "TOOLONGPREFIX",
    ])
    def test_invalid_prefix_rejected_and_not_stored(self, client, db, bad):
        _set_prefix(db, "BLB-")
        resp = client.patch(BASE_URL, json={"serial_number_prefix": bad})
        assert resp.status_code == 422
        db.expire_all()
        assert db.get(CompanySettings, 1).serial_number_prefix == "BLB-"

    def test_other_fields_leave_prefix_alone(self, client, db):
        _set_prefix(db, "BLB-")
        resp = client.patch(BASE_URL, json={"company_name": "Joe's Print Shop"})
        assert resp.status_code == 200
        assert resp.json()["serial_number_prefix"] == "BLB-"

    def test_operator_can_read_but_not_change(self, unauthed_client, role_headers, db):
        _set_prefix(db, "SN-")
        headers = role_headers("operator")
        assert unauthed_client.get(BASE_URL, headers=headers).json()[
            "serial_number_prefix"
        ] == "SN-"
        resp = unauthed_client.patch(
            BASE_URL, json={"serial_number_prefix": "OPS-"}, headers=headers
        )
        assert resp.status_code == 403
        db.expire_all()
        assert db.get(CompanySettings, 1).serial_number_prefix == "SN-"
