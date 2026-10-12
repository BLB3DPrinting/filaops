"""GHSA-vmrm-qwq2-8xj3: authenticated SSRF through the AI settings Ollama URL.

Endpoint-level: every check goes through the settings API.

No real network traffic: socket.socket.connect/connect_ex/create_connection are
replaced by a spy that records the destination and refuses, and
socket.getaddrinfo is faked. Loopback and LAN addresses are deliberately still
allowed by the fix, so nothing here expects them to be refused.
"""
import socket
from unittest.mock import patch

import pytest

SETTINGS_URL = "/api/v1/settings"
METADATA_HOST = "169.254.169.254"
FAKE_NAME = "metadata-alias.invalid"

METADATA_URLS = [
    "http://169.254.169.254",
    "http://169.254.169.254/",
    "http://169.254.169.254:80",
    "http://169.254.170.2",           # ECS task metadata, link-local
    "http://[fe80::1]:11434",         # IPv6 link-local
    "http://[fd00:ec2::254]",         # AWS IPv6 metadata
]


def _is_blocked_host(host):
    return str(host).startswith(("169.254.", "fe80", "fd00:ec2"))


@pytest.fixture
def net_spy():
    """Record every attempted socket connection; make none of them real."""
    attempts = []

    def _record(address):
        host = address[0] if isinstance(address, tuple) else address
        attempts.append(str(host))

    def fake_connect(self, address):
        _record(address)
        raise ConnectionRefusedError("blocked by test spy")

    def fake_connect_ex(self, address):
        _record(address)
        return 111

    def fake_create_connection(address, *a, **k):
        _record(address)
        raise ConnectionRefusedError("blocked by test spy")

    def fake_getaddrinfo(host, port, *a, **k):
        ip = METADATA_HOST if host == FAKE_NAME else (
            host if host and host.replace(".", "").isdigit() else "127.0.0.1"
        )
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 80))]

    with patch.object(socket.socket, "connect", fake_connect), \
         patch.object(socket.socket, "connect_ex", fake_connect_ex), \
         patch.object(socket, "create_connection", fake_create_connection), \
         patch.object(socket, "getaddrinfo", fake_getaddrinfo):
        yield attempts


def _stored_url(db):
    from app.api.v1.endpoints.settings import get_or_create_settings
    db.expire_all()
    return get_or_create_settings(db).ai_ollama_url


def _seed(db, url):
    """Put a URL in the settings row directly, as if saved before the fix."""
    from app.api.v1.endpoints.settings import get_or_create_settings
    s = get_or_create_settings(db)
    s.ai_provider = "ollama"
    s.ai_ollama_url = url
    db.flush()


@pytest.mark.parametrize("url", METADATA_URLS)
def test_admin_cannot_save_metadata_or_link_local_url(client, db, net_spy, url):
    before = _stored_url(db)
    resp = client.patch(
        f"{SETTINGS_URL}/ai", json={"ai_provider": "ollama", "ai_ollama_url": url}
    )
    assert 400 <= resp.status_code < 500, (
        f"SSRF: PATCH /settings/ai accepted {url!r} with {resp.status_code}"
    )
    assert _stored_url(db) == before, f"SSRF: {url!r} was persisted"
    assert not [a for a in net_spy if _is_blocked_host(a)]


@pytest.mark.parametrize("url", ["http://169.254.169.254", "http://[fe80::1]:11434"])
def test_test_connection_makes_no_outbound_call_to_metadata(client, db, net_spy, url):
    _seed(db, url)
    resp = client.post(f"{SETTINGS_URL}/ai/test")
    assert resp.status_code in (200, 400, 403, 422), resp.text
    hits = [a for a in net_spy if _is_blocked_host(a)]
    assert not hits, f"SSRF: server connected to {hits} on POST /settings/ai/test"
    if resp.status_code == 200:
        assert resp.json().get("success") is not True


def test_start_ollama_makes_no_outbound_call_to_metadata(client, db, net_spy):
    _seed(db, "http://169.254.169.254")
    client.post(f"{SETTINGS_URL}/ai/start-ollama")
    hits = [a for a in net_spy if _is_blocked_host(a)]
    assert not hits, f"SSRF: server connected to {hits} on POST /settings/ai/start-ollama"


def test_hostname_resolving_to_metadata_is_not_connected(client, db, net_spy):
    """A name that resolves to 169.254.169.254 (DNS rebinding style)."""
    resp = client.patch(
        f"{SETTINGS_URL}/ai",
        json={"ai_provider": "ollama", "ai_ollama_url": f"http://{FAKE_NAME}:11434"},
    )
    if resp.status_code >= 400:
        return  # refused at save time: fine
    client.post(f"{SETTINGS_URL}/ai/test")
    hits = [a for a in net_spy if _is_blocked_host(a)]
    assert not hits, f"SSRF: {FAKE_NAME} resolved to and connected to {hits}"


@pytest.mark.parametrize("url", [
    "http://user:pass@127.0.0.1:11434",
    "http://127.0.0.1:11434/?x=1",
    "http://127.0.0.1:11434/#frag",
])
def test_credentials_query_fragment_urls_refused(client, db, net_spy, url):
    resp = client.patch(f"{SETTINGS_URL}/ai", json={"ai_ollama_url": url})
    assert 400 <= resp.status_code < 500, f"{url!r} accepted with {resp.status_code}"


@pytest.mark.parametrize("account_type", ["operator", "customer"])
def test_non_admin_cannot_save_url(unauthed_client, role_headers, db, net_spy, account_type):
    before = _stored_url(db)
    resp = unauthed_client.patch(
        f"{SETTINGS_URL}/ai",
        json={"ai_provider": "ollama", "ai_ollama_url": "http://127.0.0.1:11434"},
        headers=role_headers(account_type),
    )
    assert resp.status_code in (401, 403), (
        f"{account_type} PATCH /settings/ai returned {resp.status_code}"
    )
    assert _stored_url(db) == before
