"""SEC-403: printer routes are staff-only.

Anyone can self-register a customer account, so a plain login must not be
able to read printers, edit where their credentials are sent, or make the
server probe the network. Every route should answer 403 for a customer
before it does anything.
"""
import uuid

import pytest

from app.models.printer import Printer


def _make_printer(db):
    printer = Printer(
        code=f"PRT-AUTH-{uuid.uuid4().hex[:6]}",
        name="Auth test printer",
        model="P1S",
        brand="bambulab",
        ip_address="192.168.1.70",
        connection_config={"access_code": "SECRET12"},
        status="offline",
        active=True,
    )
    db.add(printer)
    db.flush()
    return printer


def _routes(printer_id):
    base = "/api/v1/printers"
    new_printer = {"code": f"PRT-X-{uuid.uuid4().hex[:6]}", "name": "x", "model": "P1S", "brand": "bambulab"}
    return [
        ("list", "get", f"{base}/", {}),
        ("get", "get", f"{base}/{printer_id}", {}),
        ("generate_code", "get", f"{base}/generate-code", {}),
        ("brands", "get", f"{base}/brands/info", {}),
        ("active_work", "get", f"{base}/active-work", {}),
        ("create", "post", f"{base}/", {"json": new_printer}),
        ("update", "put", f"{base}/{printer_id}", {"json": {"ip_address": "203.0.113.66"}}),
        ("status", "patch", f"{base}/{printer_id}/status", {"json": {"status": "idle"}}),
        ("delete", "delete", f"{base}/{printer_id}", {}),
        ("discover", "post", f"{base}/discover", {"json": {"timeout_seconds": 1}}),
        ("probe_ip", "post", f"{base}/probe-ip?ip_address=203.0.113.66", {}),
        ("test_connection", "post", f"{base}/test-connection",
         {"json": {"brand": "bambulab", "ip_address": "203.0.113.66", "connection_config": {}}}),
        ("import_csv", "post", f"{base}/import-csv",
         {"json": {"csv_data": "code,name,model,brand\nPRT-CSV-1,x,P1S,bambulab\n"}}),
    ]


@pytest.mark.parametrize("name,method,url,kwargs", _routes(0))
def test_printer_routes_require_login(unauthed_client, name, method, url, kwargs):
    response = getattr(unauthed_client, method)(url, **kwargs)
    assert response.status_code == 401, f"{name}: {response.status_code}"


def test_customer_gets_403_on_every_printer_route(unauthed_client, role_headers, db):
    printer = _make_printer(db)
    headers = role_headers("customer")

    for name, method, url, kwargs in _routes(printer.id):
        response = getattr(unauthed_client, method)(url, headers=headers, **kwargs)
        assert response.status_code == 403, f"{name}: {response.status_code} {response.text}"

    db.expire_all()
    stored = db.query(Printer).filter(Printer.id == printer.id).first()
    assert stored is not None, "delete did not go through"
    assert stored.ip_address == "192.168.1.70"
    assert stored.status == "offline"
    assert db.query(Printer).filter(Printer.code == "PRT-CSV-1").first() is None


def test_operator_can_read_and_edit_printers(unauthed_client, role_headers, db):
    printer = _make_printer(db)
    headers = role_headers("operator")

    listed = unauthed_client.get("/api/v1/printers/", headers=headers)
    assert listed.status_code == 200, listed.text
    assert "SECRET12" not in listed.text

    renamed = unauthed_client.put(
        f"/api/v1/printers/{printer.id}",
        headers=headers,
        json={"name": "Renamed by operator"},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "Renamed by operator"
