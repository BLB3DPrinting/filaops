"""SEC: the server fetches ai_ollama_url (low-severity SSRF hardening).

Ollama normally runs on localhost or the LAN, so private addresses must keep
working. These must not work: other schemes, credentials in the URL, query or
fragment tricks that change the fetched path, redirects, link-local and cloud
metadata addresses (literal, or a host name that resolves to one), and echoing
back whatever the URL answered with. Customers must not read the AI settings.

Stub servers bind 127.0.0.1 on ephemeral ports only. Tests that use host
names get a fake resolver (the `net` fixture), so no DNS query leaves.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import pytest

from app.api.v1.endpoints.settings import (
    _OLLAMA_BLOCKED_HELP,
    _OLLAMA_URL_HELP,
    _normalize_ollama_url,
    _ollama_is_up,
    get_or_create_settings,
)

SETTINGS_URL = "/api/v1/settings"
MARK = "INTERNAL-SECRET-7f3a"


# =============================================================================
# URL rules
# =============================================================================

@pytest.mark.parametrize("raw,expected", [
    ("http://localhost:11434", "http://localhost:11434"),
    ("http://localhost:11434/", "http://localhost:11434"),
    ("http://127.0.0.1:11434", "http://127.0.0.1:11434"),
    ("http://192.168.1.50:11434", "http://192.168.1.50:11434"),
    ("http://10.0.0.5:11434", "http://10.0.0.5:11434"),
    ("http://[::1]:11434", "http://[::1]:11434"),
    ("http://host.docker.internal:11434", "http://host.docker.internal:11434"),
    ("http://myhost:11434", "http://myhost:11434"),
    ("https://ollama.lan", "https://ollama.lan"),
    ("https://proxy.lan/ollama/", "https://proxy.lan/ollama"),
])
def test_local_and_lan_urls_are_allowed(raw, expected):
    assert _normalize_ollama_url(raw) == expected


@pytest.mark.parametrize("raw", [
    None, "",
    "localhost:11434", "127.0.0.1:11434",            # no scheme
    "file:///etc/passwd", "gopher://127.0.0.1:6379/_x", "ftp://host", "dict://host:11211/",
    "javascript:alert(1)",
    "http://", "http://:11434", "http:///x",          # no host
    "http://user:pass@host:11434", "http://host:11434@evil.example", "http://@host",
    "http://host/x?y=", "http://host?", "http://host/x#", "http://host#frag",
    "http://host:99999", "http://host:abc",
    "http://host/a b", " http://host", "http://host\t", "http://host\r\nX: y",
    "http://host\\@evil", "http://hóst", "http://host＠evil",
    "http://host/%3F", "http://host/;x",
])
def test_other_urls_are_refused(raw):
    assert _normalize_ollama_url(raw) is None


# =============================================================================
# Local stub servers
# =============================================================================

@pytest.fixture
def stubs():
    """Start one stub per behaviour. Yields ({kind: base_url}, hits list)."""
    hits = []
    urls = {}
    servers = []

    def handler(kind):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                hits.append((kind, self.path))
                if kind == "redirect":
                    self.send_response(302)
                    self.send_header("Location", f"{urls['ollama']}/leak")
                    self.end_headers()
                    return
                if kind == "404":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = {
                    "ollama": json.dumps({"models": [{"name": "llama3.2:latest"}, {"name": "mistral:7b"}]}),
                    "json_secret": json.dumps({"secret": MARK, "models": "nope"}),
                    "html_secret": f"<html>{MARK}</html>",
                    "big": '{"models": [' + " " * (2 * 1024 * 1024) + "]}",
                }[kind].encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return H

    for kind in ("ollama", "json_secret", "html_secret", "big", "redirect", "404"):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), handler(kind))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        urls[kind] = f"http://127.0.0.1:{srv.server_address[1]}"

    yield urls, hits

    for srv in servers:
        srv.shutdown()
        srv.server_close()


def _store(db, url, provider="ollama"):
    """Write straight to the row, as a value saved before the fix would be."""
    settings = get_or_create_settings(db)
    settings.ai_provider = provider
    settings.ai_ollama_url = url
    settings.ai_ollama_model = "llama3.2"
    db.flush()
    return settings


# =============================================================================
# PATCH /settings/ai
# =============================================================================

class TestOllamaUrlOnSave:
    @pytest.mark.parametrize("bad", [
        "http://169.254.169.254/latest/meta-data?x=",
        "http://127.0.0.1:6379/#",
        "file:///etc/passwd",
        "http://user:pass@ollama.lan:11434",
        "ollama.lan:11434",
    ])
    def test_bad_url_rejected_and_not_stored(self, client, db, bad):
        _store(db, "http://localhost:11434")
        resp = client.patch(f"{SETTINGS_URL}/ai", json={"ai_ollama_url": bad})
        assert resp.status_code == 400
        assert resp.json()["detail"] == _OLLAMA_URL_HELP  # a string, so the toast can show it
        assert client.get(f"{SETTINGS_URL}/ai").json()["ai_ollama_url"] == "http://localhost:11434"

    def test_lan_url_saved_without_trailing_slash(self, client):
        resp = client.patch(f"{SETTINGS_URL}/ai", json={
            "ai_provider": "ollama", "ai_ollama_url": "http://192.168.1.50:11434/",
        })
        assert resp.status_code == 200
        assert resp.json()["ai_ollama_url"] == "http://192.168.1.50:11434"

    def test_empty_url_resets_to_default(self, client):
        client.patch(f"{SETTINGS_URL}/ai", json={"ai_ollama_url": "http://myhost:11434"})
        resp = client.patch(f"{SETTINGS_URL}/ai", json={"ai_ollama_url": ""})
        assert resp.status_code == 200
        assert resp.json()["ai_ollama_url"] == "http://localhost:11434"


# =============================================================================
# POST /settings/ai/test
# =============================================================================

class TestOllamaConnectionTest:
    def test_real_ollama_only_api_tags_fetched(self, client, db, stubs):
        urls, hits = stubs
        _store(db, urls["ollama"])
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data["success"] is True
        assert "available" in data["message"]
        assert hits == [("ollama", "/api/tags")]

    def test_missing_model_lists_names(self, client, db, stubs):
        urls, _ = stubs
        settings = _store(db, urls["ollama"])
        settings.ai_ollama_model = "phi3"
        db.flush()
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data["success"] is True
        assert "llama3.2" in data["message"] and "mistral" in data["message"]

    def test_redirect_not_followed(self, client, db, stubs):
        urls, hits = stubs
        _store(db, urls["redirect"])
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data["success"] is False
        assert "302" in data["message"]
        assert ("ollama", "/leak") not in hits

    @pytest.mark.parametrize("kind", ["json_secret", "html_secret"])
    def test_non_ollama_answer_not_echoed(self, client, db, stubs, kind):
        urls, _ = stubs
        _store(db, urls[kind])
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data["success"] is False
        assert MARK not in data["message"]

    def test_oversized_answer_refused(self, client, db, stubs):
        urls, _ = stubs
        _store(db, urls["big"])
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data["success"] is False

    def test_status_reported_without_body(self, client, db, stubs):
        urls, _ = stubs
        _store(db, urls["404"])
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data["success"] is False
        assert "404" in data["message"]

    @pytest.mark.parametrize("suffix", ["/internal/admin?x=", "/internal#"])
    def test_legacy_stored_url_refused_before_any_request(self, client, db, stubs, suffix):
        urls, hits = stubs
        _store(db, urls["ollama"] + suffix)
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data == {"success": False, "provider": "ollama", "message": _OLLAMA_URL_HELP}
        assert hits == []

    def test_exception_text_not_echoed(self, client, db):
        _store(db, "http://localhost:11434")
        with patch("requests.Session.get", side_effect=RuntimeError(f"boom {MARK}")):
            data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data["message"] == "Connection test failed"


# =============================================================================
# POST /settings/ai/start-ollama
# =============================================================================

class TestStartOllamaUrl:
    def test_legacy_bad_url_no_request_no_spawn(self, client, db, stubs):
        urls, hits = stubs
        _store(db, urls["ollama"] + "/x?y=")
        with patch("subprocess.Popen") as popen:
            data = client.post(f"{SETTINGS_URL}/ai/start-ollama").json()
        assert data["success"] is False
        assert not popen.called
        assert hits == []

    def test_running_ollama_detected_without_spawn(self, client, db, stubs):
        urls, _ = stubs
        _store(db, urls["ollama"])
        with patch("subprocess.Popen") as popen:
            data = client.post(f"{SETTINGS_URL}/ai/start-ollama").json()
        assert data["success"] is True
        assert not popen.called


# =============================================================================
# Link-local and cloud metadata addresses (app.core.outbound_guard)
# =============================================================================

_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect


@pytest.fixture
def net(monkeypatch):
    """Fake DNS plus a connect guard. Yields (table, lookups, connects).

    Host names resolve only from `table`; numeric hosts are parsed locally.
    A socket connect to anything but 127.0.0.1 fails the test. Request it
    after client/db so the database connection is already open.
    """
    table = {"localhost": ["127.0.0.1"]}
    lookups = []
    connects = []

    def getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
        lookups.append(host)
        if host not in table:
            return _real_getaddrinfo(host, port, family, socktype, proto, flags | socket.AI_NUMERICHOST)
        return [
            info
            for ip in table[host]
            for info in _real_getaddrinfo(ip, port, 0, socktype, proto, socket.AI_NUMERICHOST)
        ]

    def connect(sock, address):
        connects.append(address[0])
        if address[0] != "127.0.0.1":
            raise AssertionError(f"test tried to connect to {address[0]}")
        return _real_connect(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)
    return table, lookups, connects


def _port(base_url):
    return base_url.rsplit(":", 1)[1]


class TestBlockedOllamaAddresses:
    @pytest.mark.parametrize("url", [
        "http://169.254.169.254",
        "http://169.254.169.254:11434",
        "https://169.254.0.1/ollama",
        "http://[fe80::1]:11434",
        "http://[fe80::1%25eth0]:11434",
        "http://[::ffff:169.254.169.254]:11434",
        "http://[64:ff9b::a9fe:a9fe]:11434",
        "http://[64:ff9b:1::a9fe:a9fe]:11434",
        "http://[fd00:ec2::254]",
        "http://100.100.100.200",
        "http://168.63.129.16",
        "http://224.0.0.251:11434",
        "http://2852039166:11434",
        "http://0xa9fea9fe:11434",
    ])
    def test_literal_blocked_address_rejected_on_save(self, client, db, net, url):
        _store(db, "http://localhost:11434")
        resp = client.patch(f"{SETTINGS_URL}/ai", json={"ai_ollama_url": url})
        assert resp.status_code == 400
        assert resp.json()["detail"] == _OLLAMA_BLOCKED_HELP
        assert client.get(f"{SETTINGS_URL}/ai").json()["ai_ollama_url"] == "http://localhost:11434"
        _, lookups, connects = net
        assert lookups == [] and connects == []

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:11434",
        "http://[::1]:11434",
        "http://10.0.0.5:11434",
        "http://172.16.0.5:11434",
        "http://192.168.1.50:11434",
        "http://100.64.0.1:11434",         # Tailscale (CGNAT range)
        "http://100.101.102.103:11434",
        "http://[fd12::1]:11434",          # IPv6 ULA
        "http://[fd7a:115c:a1e0::1]:11434",  # Tailscale IPv6
        "http://0.0.0.0:11434",            # reaches this host, like localhost
        "http://[::]:11434",
    ])
    def test_lan_tailscale_and_ula_addresses_saved(self, client, url):
        resp = client.patch(f"{SETTINGS_URL}/ai", json={"ai_provider": "ollama", "ai_ollama_url": url})
        assert resp.status_code == 200
        assert resp.json()["ai_ollama_url"] == url

    def test_stored_0000_url_does_not_block_saving_other_ai_settings(self, client, db):
        # The settings page sends the stored URL back on every save, so a URL
        # refused on save would make every AI setting unsaveable.
        _store(db, "http://0.0.0.0:11434")
        resp = client.patch(f"{SETTINGS_URL}/ai", json={
            "ai_provider": "ollama",
            "ai_ollama_url": "http://0.0.0.0:11434",
            "ai_ollama_model": "mistral",
        })
        assert resp.status_code == 200
        assert resp.json()["ai_ollama_model"] == "mistral"

    def test_host_name_saved_without_dns(self, client, db, net):
        # Host names are judged when the server connects, not when saved.
        table, lookups, _ = net
        table["metadata.example.test"] = ["169.254.169.254"]
        resp = client.patch(f"{SETTINGS_URL}/ai", json={"ai_ollama_url": "http://metadata.example.test:11434"})
        assert resp.status_code == 200
        assert lookups == []

    @pytest.mark.parametrize("url", [
        "http://169.254.169.254",
        "http://[fd00:ec2::254]:11434",
        "http://[::ffff:100.100.100.200]:11434",
    ])
    def test_stored_blocked_address_reported_on_test(self, client, db, net, url):
        _store(db, url)  # saved before this check existed
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data == {"success": False, "provider": "ollama", "message": _OLLAMA_BLOCKED_HELP}
        assert net[2] == []

    @pytest.mark.parametrize("answers", [
        ["169.254.169.254"],
        ["169.254.169.254", "fe80::1"],  # every answer blocked
        ["::ffff:169.254.169.254"],
    ])
    def test_name_resolving_only_to_blocked_addresses_reported_on_test(
        self, client, db, stubs, net, answers
    ):
        urls, hits = stubs
        table, _, connects = net
        table["ollama.example.test"] = answers
        _store(db, f"http://ollama.example.test:{_port(urls['ollama'])}")
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data == {"success": False, "provider": "ollama", "message": _OLLAMA_BLOCKED_HELP}
        assert hits == [] and connects == []

    @pytest.mark.parametrize("answers", [
        ["127.0.0.1"],
        # mDNS (.local) and Windows LLMNR names often resolve to the LAN
        # address plus an fe80:: address; only the LAN address is used.
        ["127.0.0.1", "fe80::1c2d:3e4f:5a6b:7c8d"],
        ["fe80::1c2d:3e4f:5a6b:7c8d", "127.0.0.1"],
        ["169.254.169.254", "127.0.0.1"],
    ])
    def test_name_with_a_lan_address_works(self, client, db, stubs, net, answers):
        urls, hits = stubs
        table, lookups, connects = net
        table["ollama-mac.local"] = answers
        _store(db, f"http://ollama-mac.local:{_port(urls['ollama'])}")
        data = client.post(f"{SETTINGS_URL}/ai/test").json()
        assert data["success"] is True
        assert hits == [("ollama", "/api/tags")]
        assert lookups == ["ollama-mac.local"]
        assert connects == ["127.0.0.1"]

    def test_blocked_message_is_not_the_not_running_message(self, client, db, net):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        closed_port = probe.getsockname()[1]
        probe.close()
        _store(db, f"http://127.0.0.1:{closed_port}")
        not_running = client.post(f"{SETTINGS_URL}/ai/test").json()["message"]
        assert "not running" in not_running
        assert not_running != _OLLAMA_BLOCKED_HELP

    @pytest.mark.parametrize("stored,name,answers", [
        ("http://169.254.169.254:11434", None, None),
        ("http://[fe80::1]:11434", None, None),
        ("http://metadata.example.test:11434", "metadata.example.test", ["169.254.169.254"]),
        ("http://mixed.example.test:11434", "mixed.example.test", ["fe80::1", "169.254.169.254"]),
    ])
    def test_start_ollama_does_not_spawn_for_blocked_address(self, client, db, net, stored, name, answers):
        table, _, connects = net
        if name:
            table[name] = answers
        _store(db, stored)
        with patch("subprocess.Popen") as popen:
            data = client.post(f"{SETTINGS_URL}/ai/start-ollama").json()
        assert data == {"success": False, "message": _OLLAMA_BLOCKED_HELP}
        assert not popen.called
        assert connects == []

    def test_start_ollama_finds_ollama_behind_a_name_with_an_fe80_answer(self, client, db, stubs, net):
        urls, _ = stubs
        table, _, connects = net
        table["ollama-mac.local"] = ["fe80::1", "127.0.0.1"]
        _store(db, f"http://ollama-mac.local:{_port(urls['ollama'])}")
        with patch("subprocess.Popen") as popen:
            data = client.post(f"{SETTINGS_URL}/ai/start-ollama").json()
        assert data == {"success": True, "message": "Ollama is already running!"}
        assert not popen.called
        assert connects == ["127.0.0.1"]

    def test_ollama_is_up_false_for_blocked_address(self, net):
        table, _, connects = net
        table["metadata.example.test"] = ["169.254.169.254"]
        assert _ollama_is_up("http://169.254.169.254", timeout=1) is False
        assert _ollama_is_up("http://metadata.example.test:11434", timeout=1) is False
        assert connects == []


# =============================================================================
# Who can read AI settings
# =============================================================================

class TestAiSettingsReadAccess:
    @pytest.mark.parametrize("path", ["/ai", "/ai/anthropic-status"])
    def test_customer_forbidden(self, unauthed_client, role_headers, path):
        resp = unauthed_client.get(f"{SETTINGS_URL}{path}", headers=role_headers("customer"))
        assert resp.status_code == 403

    @pytest.mark.parametrize("path", ["/ai", "/ai/anthropic-status"])
    def test_operator_allowed(self, unauthed_client, role_headers, path):
        # AdminLayout's security badge reads GET /settings/ai for every staff user.
        resp = unauthed_client.get(f"{SETTINGS_URL}{path}", headers=role_headers("operator"))
        assert resp.status_code == 200

    @pytest.mark.parametrize("method,path", [
        ("patch", "/ai"), ("post", "/ai/test"), ("post", "/ai/start-ollama"),
    ])
    def test_operator_cannot_set_or_trigger_fetch(self, unauthed_client, role_headers, method, path):
        kwargs = {"json": {"ai_ollama_url": "http://x:1"}} if method == "patch" else {}
        resp = getattr(unauthed_client, method)(
            f"{SETTINGS_URL}{path}", headers=role_headers("operator"), **kwargs
        )
        assert resp.status_code == 403
