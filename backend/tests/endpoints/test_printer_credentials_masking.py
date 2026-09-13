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
        },
    }
    create_resp = client.post("/api/v1/printers", json=payload)
    assert create_resp.status_code == 200
    printer_id = create_resp.json()["id"]

    # Update with masked access_code and new host
    update_payload = {
        "connection_config": {
            "access_code": "********",
            "host": "printer-updated.local",
        }
    }
    update_resp = client.put(f"/api/v1/printers/{printer_id}", json=update_payload)
    assert update_resp.status_code == 200
    update_data = update_resp.json()
    assert update_data["connection_config"]["access_code"] == "********"
    assert update_data["connection_config"]["host"] == "printer-updated.local"

    # Verify database preserved original secret
    db.expire_all()
    printer_in_db = db.query(Printer).filter(Printer.id == printer_id).first()
    assert printer_in_db.connection_config["access_code"] == "original-secret-code"
    assert printer_in_db.connection_config["host"] == "printer-updated.local"


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
