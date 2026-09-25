"""SEC-403: Printer credential masking tests."""

import uuid
from app.models.printer import Printer


def test_printer_credentials_masked_in_response(client, db):
    """Sensitive keys in connection_config must be masked in API responses."""
    uid = uuid.uuid4().hex[:6]
    payload = {
        "code": f"PRT-SEC-{uid}",
        "name": f"Secure Printer {uid}",
        "brand": "generic",
        "model": "Test Model",
        "ip_address": "192.168.1.50",
        "connection_config": {
            "access_code": "super-secret-code",
            "api_key": "my-secret-api-key",
            "non_sensitive_field": "visible_value",
        },
    }
    create_resp = client.post("/api/v1/printers", json=payload)
    assert create_resp.status_code == 200, create_resp.text
    data = create_resp.json()
    printer_id = data["id"]

    # Verify response is masked
    assert data["connection_config"]["access_code"] == "********"
    assert data["connection_config"]["api_key"] == "********"
    assert data["connection_config"]["non_sensitive_field"] == "visible_value"

    # Verify GET by ID is also masked
    get_resp = client.get(f"/api/v1/printers/{printer_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["connection_config"]["access_code"] == "********"
    assert get_data["connection_config"]["api_key"] == "********"

    # Verify database still stores the raw secret values
    printer_in_db = db.query(Printer).filter(Printer.id == printer_id).first()
    assert printer_in_db is not None
    assert printer_in_db.connection_config["access_code"] == "super-secret-code"
    assert printer_in_db.connection_config["api_key"] == "my-secret-api-key"
    assert printer_in_db.connection_config["non_sensitive_field"] == "visible_value"


def test_printer_update_preserves_masked_credentials(client, db):
    """Submitting '********' on update preserves the stored secret."""
    uid = uuid.uuid4().hex[:6]
    payload = {
        "code": f"PRT-SEC-{uid}",
        "name": f"Secure Printer {uid}",
        "brand": "generic",
        "model": "Test Model",
        "ip_address": "192.168.1.51",
        "connection_config": {
            "access_code": "original-secret-code",
            "host": "printer.local",
            "serial": "SN-OLD",
        },
    }
    create_resp = client.post("/api/v1/printers", json=payload)
    assert create_resp.status_code == 200
    printer_id = create_resp.json()["id"]

    # Update with masked access_code and a new non-address field. The same
    # IP is sent back, as the Edit Printer form does.
    update_payload = {
        "ip_address": "192.168.1.51",
        "connection_config": {
            "access_code": "********",
            "host": "printer.local",
            "serial": "SN-NEW",
        },
    }
    update_resp = client.put(f"/api/v1/printers/{printer_id}", json=update_payload)
    assert update_resp.status_code == 200, update_resp.text
    update_data = update_resp.json()
    assert update_data["connection_config"]["access_code"] == "********"
    assert update_data["connection_config"]["serial"] == "SN-NEW"

    # Verify database preserved original secret
    db.expire_all()
    printer_in_db = db.query(Printer).filter(Printer.id == printer_id).first()
    assert printer_in_db.connection_config["access_code"] == "original-secret-code"
    assert printer_in_db.connection_config["serial"] == "SN-NEW"


def test_printer_update_can_change_credentials(client, db):
    """Submitting a new secret value updates the secret in DB."""
    uid = uuid.uuid4().hex[:6]
    payload = {
        "code": f"PRT-SEC-{uid}",
        "name": f"Secure Printer {uid}",
        "brand": "generic",
        "model": "Test Model",
        "ip_address": "192.168.1.52",
        "connection_config": {
            "access_code": "original-secret-code",
        },
    }
    create_resp = client.post("/api/v1/printers", json=payload)
    assert create_resp.status_code == 200
    printer_id = create_resp.json()["id"]

    # Update with brand-new access_code
    update_payload = {
        "connection_config": {
            "access_code": "brand-new-secret-code",
        }
    }
    update_resp = client.put(f"/api/v1/printers/{printer_id}", json=update_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["connection_config"]["access_code"] == "********"

    # Verify database has new secret
    db.expire_all()
    printer_in_db = db.query(Printer).filter(Printer.id == printer_id).first()
    assert printer_in_db.connection_config["access_code"] == "brand-new-secret-code"


# ---------------------------------------------------------------------------
# Nested secrets (CodeRabbit review on PR #973)
# ---------------------------------------------------------------------------

_NESTED_SECRETS = ("mqtt-secret", "12345678", "cloud-token")


def _nested_config():
    return {
        "host": "printer.local",
        "mqtt": {"username": "bblp", "password": "mqtt-secret"},
        "mqtt_access_code": "12345678",
        "accounts": [{"name": "cloud", "token": "cloud-token"}],
        "api_key": "",
    }


def _create_printer(client, connection_config):
    uid = uuid.uuid4().hex[:6]
    resp = client.post("/api/v1/printers", json={
        "code": f"PRT-NEST-{uid}",
        "name": f"Nested Secret Printer {uid}",
        "brand": "generic",
        "model": "Test Model",
        "ip_address": "192.168.1.60",
        "connection_config": connection_config,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


def _stored_config(db, printer_id):
    db.expire_all()
    return db.query(Printer).filter(Printer.id == printer_id).first().connection_config


def test_nested_printer_secrets_masked_in_responses(client, db):
    """Secrets under nested dicts, lists and prefixed keys are masked."""
    created = _create_printer(client, _nested_config())
    printer_id = created["id"]

    for resp in (
        client.get(f"/api/v1/printers/{printer_id}"),
        client.get("/api/v1/printers"),
    ):
        assert resp.status_code == 200
        for secret in _NESTED_SECRETS:
            assert secret not in resp.text

    config = client.get(f"/api/v1/printers/{printer_id}").json()["connection_config"]
    assert config["mqtt"] == {"username": "bblp", "password": "********"}
    assert config["mqtt_access_code"] == "********"
    assert config["accounts"] == [{"name": "cloud", "token": "********"}]
    assert config["host"] == "printer.local"
    # Empty secrets stay empty so the UI can tell "not set" from "set".
    assert config["api_key"] == ""

    assert _stored_config(db, printer_id) == _nested_config()


def test_update_round_trip_keeps_nested_secrets(client, db):
    """Sending the masked config back keeps every stored nested secret."""
    created = _create_printer(client, _nested_config())
    printer_id = created["id"]

    masked = created["connection_config"]
    masked["mqtt"]["username"] = "operator"
    resp = client.put(f"/api/v1/printers/{printer_id}", json={"connection_config": masked})
    assert resp.status_code == 200, resp.text
    for secret in _NESTED_SECRETS:
        assert secret not in resp.text

    expected = _nested_config()
    expected["mqtt"]["username"] = "operator"
    assert _stored_config(db, printer_id) == expected


def test_update_can_change_a_nested_secret(client, db):
    """A real new value for a nested secret replaces the stored one."""
    created = _create_printer(client, _nested_config())
    printer_id = created["id"]

    config = created["connection_config"]
    config["mqtt"]["password"] = "rotated-secret"
    resp = client.put(f"/api/v1/printers/{printer_id}", json={"connection_config": config})
    assert resp.status_code == 200, resp.text
    assert resp.json()["connection_config"]["mqtt"]["password"] == "********"

    stored = _stored_config(db, printer_id)
    assert stored["mqtt"]["password"] == "rotated-secret"
    assert stored["accounts"][0]["token"] == "cloud-token"
    assert stored["mqtt_access_code"] == "12345678"


def test_mask_placeholder_is_never_stored_as_a_secret(client, db):
    """A masked value with nothing stored at that path is dropped."""
    created = _create_printer(client, {"host": "printer.local", "mqtt": {"password": "********"}})
    printer_id = created["id"]
    assert _stored_config(db, printer_id) == {"host": "printer.local", "mqtt": {}}

    resp = client.put(f"/api/v1/printers/{printer_id}", json={
        "connection_config": {"host": "printer.local", "access_code": "********"},
    })
    assert resp.status_code == 200, resp.text
    assert _stored_config(db, printer_id) == {"host": "printer.local"}


# ---------------------------------------------------------------------------
# Re-pointing a printer must not carry its stored secret along (review on
# PR #973). PRO's Bambu fleet and Core's MQTT monitor send access_code as
# the MQTT password to printer.ip_address / connection_config hosts.
# ---------------------------------------------------------------------------

def _bambu_style_printer(client):
    created = _create_printer(client, {"access_code": "SECRET12", "serial": "01P00A000000001"})
    return created["id"]


def _assert_unchanged(db, printer_id):
    db.expire_all()
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    assert printer.ip_address == "192.168.1.60"
    assert printer.connection_config == {"access_code": "SECRET12", "serial": "01P00A000000001"}


def test_new_ip_without_config_is_rejected_while_a_secret_is_stored(client, db):
    printer_id = _bambu_style_printer(client)

    resp = client.put(f"/api/v1/printers/{printer_id}", json={"ip_address": "203.0.113.66"})

    assert resp.status_code == 400, resp.text
    assert "access_code" in resp.json()["detail"]
    assert "SECRET12" not in resp.text
    _assert_unchanged(db, printer_id)


def test_new_ip_with_masked_secret_is_rejected(client, db):
    """The Edit Printer form sends the mask back; a new IP needs the real code."""
    printer_id = _bambu_style_printer(client)

    resp = client.put(f"/api/v1/printers/{printer_id}", json={
        "ip_address": "203.0.113.66",
        "connection_config": {"access_code": "********", "serial": "01P00A000000001"},
    })

    assert resp.status_code == 400, resp.text
    _assert_unchanged(db, printer_id)


def test_new_host_inside_config_with_masked_secret_is_rejected(client, db):
    printer_id = _bambu_style_printer(client)

    resp = client.put(f"/api/v1/printers/{printer_id}", json={
        "connection_config": {
            "access_code": "********",
            "serial": "01P00A000000001",
            "mqtt_host": "203.0.113.66",
        },
    })

    assert resp.status_code == 400, resp.text
    _assert_unchanged(db, printer_id)


def test_new_ip_with_the_secret_sent_again_is_saved(client, db):
    printer_id = _bambu_style_printer(client)

    resp = client.put(f"/api/v1/printers/{printer_id}", json={
        "ip_address": "192.168.1.61",
        "connection_config": {"access_code": "NEWCODE9", "serial": "01P00A000000001"},
    })

    assert resp.status_code == 200, resp.text
    db.expire_all()
    printer = db.query(Printer).filter(Printer.id == printer_id).first()
    assert printer.ip_address == "192.168.1.61"
    assert printer.connection_config["access_code"] == "NEWCODE9"


def test_new_ip_is_fine_when_no_secret_is_stored(client, db):
    created = _create_printer(client, {"serial": "01P00A000000002"})

    resp = client.put(f"/api/v1/printers/{created['id']}", json={"ip_address": "192.168.1.62"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["ip_address"] == "192.168.1.62"
