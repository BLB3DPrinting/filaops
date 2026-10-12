"""SEC: outbound guard for user-configured URLs (app.core.outbound_guard).

Link-local and cloud metadata addresses are refused, judged on the address the
server actually connects to. Loopback, LAN, ULA and CGNAT (Tailscale) stay
allowed, because that is where self-hosted services such as Ollama run.

Nothing here touches the network. DNS is a fake table (socket.getaddrinfo is
patched; numeric hosts are parsed locally with AI_NUMERICHOST), the only
servers are stubs on 127.0.0.1, and a socket connect to any other address
fails the test instead of leaving the machine.
"""
import datetime
import socket
import socketserver
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_address

import pytest
import requests

from app.core.outbound_guard import (
    BlockedDestinationError,
    guarded_session,
    is_blocked_destination,
    parse_ip_literal,
)

_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect


# =============================================================================
# Fixtures: no real DNS, no connections beyond 127.0.0.1
# =============================================================================

@pytest.fixture(autouse=True)
def connects(monkeypatch):
    """Every address a socket connects to. Anything but 127.0.0.1 fails the test."""
    seen = []

    def connect(sock, address):
        seen.append(address[0])
        if address[0] != "127.0.0.1":
            raise AssertionError(f"test tried to connect to {address[0]}")
        return _real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
    return seen


@pytest.fixture
def dns(monkeypatch):
    """Fake resolver. Yields (table, lookups).

    table maps a host name to a list of IPs, or to a function returning one
    per lookup. Hosts not in the table must be numeric; anything else fails
    to resolve without a DNS query.
    """
    table = {}
    lookups = []

    def getaddrinfo(host, port, family=0, socktype=0, proto=0, flags=0):
        lookups.append(host)
        answers = table.get(host)
        if answers is None:
            return _real_getaddrinfo(host, port, family, socktype, proto, flags | socket.AI_NUMERICHOST)
        if callable(answers):
            answers = answers()
        result = []
        for ip in answers:
            # family 0: IPv6 answers stay usable on hosts without IPv6.
            result += _real_getaddrinfo(ip, port, 0, socktype, proto, socket.AI_NUMERICHOST)
        return result

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return table, lookups


class _LocalServer(ThreadingHTTPServer):
    def server_bind(self):
        # HTTPServer.server_bind does a reverse lookup of the address; skip it.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def handle_error(self, request, client_address):
        pass


@pytest.fixture
def make_server():
    """Start stub servers on 127.0.0.1. make_server(tls=ctx) -> (port, hits)."""
    servers = []

    def start(tls=None):
        hits = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                hits.append((self.path, self.headers.get("Host")))
                if self.path == "/redirect-to-link-local":
                    self.send_response(302)
                    self.send_header("Location", "http://169.254.169.254/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                body = b'{"models": []}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        srv = _LocalServer(("127.0.0.1", 0), Handler)
        if tls is not None:
            srv.socket = tls.wrap_socket(srv.socket, server_side=True)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        return srv.server_address[1], hits

    yield start

    for srv in servers:
        srv.shutdown()
        srv.server_close()


@pytest.fixture
def server(make_server):
    return make_server()


def _get(url, **kwargs):
    with guarded_session() as session:
        return session.get(url, timeout=5, allow_redirects=False, **kwargs)


# =============================================================================
# Address rules
# =============================================================================

BLOCKED = [
    # IPv4 and IPv6 link-local (most clouds' metadata lives at 169.254.169.254)
    "169.254.169.254", "169.254.0.1", "169.254.170.2", "169.254.255.255",
    "fe80::1", "fe80::1%eth0", "febf:ffff::1",
    # IPv4 carried inside IPv6
    "::ffff:169.254.169.254", "::ffff:a9fe:a9fe", "::169.254.169.254",
    "64:ff9b::a9fe:a9fe", "64:ff9b::169.254.169.254",
    # local-use NAT64 (64:ff9b:1::/48), /96 layout, including a /96 inside it
    "64:ff9b:1::a9fe:a9fe", "64:ff9b:1:ab:cd::a9fe:a9fe",
    "64:ff9b:1::6464:64c8", "64:ff9b:1::a83f:8110",
    # metadata addresses outside link-local
    "fd00:ec2::254", "100.100.100.200", "168.63.129.16",
    "::ffff:100.100.100.200", "64:ff9b::6464:64c8", "::ffff:168.63.129.16",
    # multicast, reserved and broadcast
    "224.0.0.1", "239.255.255.250", "ff02::1", "ff05::c", "::ffff:224.0.0.1",
    "240.0.0.1", "255.255.255.255",
]

ALLOWED = [
    "127.0.0.1", "127.8.9.10", "::1", "::ffff:127.0.0.1",                 # loopback
    "0.0.0.0", "::", "::ffff:0.0.0.0",                                    # unspecified: this host
    "10.0.0.5", "172.16.0.5", "172.31.255.254", "192.168.1.50",          # RFC 1918
    "::ffff:192.168.1.50", "64:ff9b::a00:5",                             # LAN inside IPv6
    # LAN addresses through a local-use NAT64: /96 layout, then the /48 and
    # /64 layouts (192.168.1.50, 10.0.0.240), whose last 32 bits read as
    # 0.0.0.0 and 240.0.0.0 and must not be mistaken for blocked addresses
    "64:ff9b:1::c0a8:132", "64:ff9b:1:c0a8:1:3200::", "64:ff9b:1:0:a:0:f000:0",
    "100.64.0.1", "100.100.100.199", "100.127.255.254",                  # CGNAT / Tailscale
    "fd12::1", "fc00::1", "fd00:ec2::1", "fd00:ec2::253",                # ULA
    "8.8.8.8", "2001:db8::1",                                            # not this guard's concern
]


@pytest.mark.parametrize("ip", BLOCKED)
def test_blocked_addresses(ip):
    assert is_blocked_destination(ip) is True


@pytest.mark.parametrize("ip", ALLOWED)
def test_allowed_addresses(ip):
    assert is_blocked_destination(ip) is False


def test_accepts_address_objects():
    assert is_blocked_destination(ip_address("169.254.169.254")) is True
    assert is_blocked_destination(ip_address("fe80::1%3")) is True
    assert is_blocked_destination(ip_address("192.168.1.50")) is False


def test_not_an_address_raises():
    with pytest.raises(ValueError):
        is_blocked_destination("ollama.lan")


@pytest.mark.parametrize("host,expected", [
    ("169.254.169.254", "169.254.169.254"),
    ("[fe80::1]", "fe80::1"),
    ("fe80::1%25eth0", "fe80::1"),
    ("[::ffff:169.254.169.254]", "::ffff:169.254.169.254"),
    ("2852039166", "169.254.169.254"),
    ("0xa9fea9fe", "169.254.169.254"),
    ("0251.0376.0251.0376", "169.254.169.254"),
    ("169.254.43518", "169.254.169.254"),
    ("192.168.1.50", "192.168.1.50"),
])
def test_parse_ip_literal(host, expected):
    assert parse_ip_literal(host) == ip_address(expected)


@pytest.mark.parametrize("host", ["localhost", "ollama.lan", "cafe", "host.docker.internal", "1.2.3.4 x", ""])
def test_parse_ip_literal_leaves_names_alone(host):
    assert parse_ip_literal(host) is None


# =============================================================================
# Allowed destinations work end to end
# =============================================================================

def test_session_ignores_environment():
    with guarded_session() as session:
        assert session.trust_env is False


def test_loopback_literal_reaches_local_server(dns, server, connects):
    port, hits = server
    resp = _get(f"http://127.0.0.1:{port}/api/tags")
    assert resp.status_code == 200
    assert resp.json() == {"models": []}
    assert hits == [("/api/tags", f"127.0.0.1:{port}")]
    assert connects == ["127.0.0.1"]


@pytest.mark.parametrize("name", ["localhost", "ollama.lan.test"])
def test_name_resolving_to_loopback_works(dns, server, connects, name):
    table, lookups = dns
    table[name] = ["127.0.0.1"]
    port, hits = server
    resp = _get(f"http://{name}:{port}/api/tags")
    assert resp.status_code == 200
    assert hits == [("/api/tags", f"{name}:{port}")]  # Host header keeps the name
    assert lookups == [name]
    assert connects == ["127.0.0.1"]


# =============================================================================
# Blocked destinations are refused before any connection
# =============================================================================

@pytest.mark.parametrize("host", [
    "169.254.169.254", "169.254.0.1", "[fe80::1]", "[::ffff:169.254.169.254]",
    "[::ffff:a9fe:a9fe]", "[64:ff9b::a9fe:a9fe]", "[64:ff9b:1::a9fe:a9fe]", "[fd00:ec2::254]",
    "100.100.100.200", "168.63.129.16", "224.0.0.1",
    "[ff02::1]", "255.255.255.255",
])
def test_blocked_literal_refused(dns, connects, host):
    with pytest.raises(BlockedDestinationError):
        _get(f"http://{host}:11434/api/tags")
    assert connects == []


@pytest.mark.parametrize("answers", [
    ["169.254.169.254"],
    ["169.254.169.254", "fe80::1"],  # every answer blocked
    ["fd00:ec2::254", "100.100.100.200"],
    ["::ffff:169.254.169.254"],
    ["64:ff9b::a9fe:a9fe"],
    ["64:ff9b:1::a9fe:a9fe"],  # what a local-use DNS64 would synthesize
])
def test_name_resolving_only_to_blocked_addresses_refused(dns, server, connects, answers):
    table, _ = dns
    table["metadata.example.test"] = answers
    port, hits = server
    with pytest.raises(BlockedDestinationError):
        _get(f"http://metadata.example.test:{port}/api/tags")
    assert connects == []
    assert hits == []


@pytest.mark.parametrize("answers", [
    # mDNS (.local) and Windows LLMNR names often come back with the host's
    # LAN address and its fe80:: address. The fe80:: answer is dropped.
    ["127.0.0.1", "fe80::1c2d:3e4f:5a6b:7c8d"],
    ["fe80::1c2d:3e4f:5a6b:7c8d", "127.0.0.1"],
    ["169.254.169.254", "127.0.0.1"],
    ["127.0.0.1", "fd00:ec2::254"],
])
def test_name_with_an_allowed_answer_connects_to_that_one_only(dns, server, connects, answers):
    table, lookups = dns
    table["ollama-mac.local"] = answers
    port, hits = server
    resp = _get(f"http://ollama-mac.local:{port}/api/tags")
    assert resp.status_code == 200
    assert hits == [("/api/tags", f"ollama-mac.local:{port}")]
    assert lookups == ["ollama-mac.local"]
    # A blocked answer is never tried (the connects fixture fails the test if
    # it is), including when it comes first.
    assert connects == ["127.0.0.1"]


def test_blocked_answer_not_tried_when_the_allowed_one_fails(dns, connects):
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    closed_port = probe.getsockname()[1]
    probe.close()
    table, _ = dns
    table["mixed.example.test"] = ["127.0.0.1", "169.254.169.254", "fe80::1"]
    with pytest.raises(requests.exceptions.ConnectionError) as info:
        _get(f"http://mixed.example.test:{closed_port}/api/tags")
    # An ordinary "could not connect", not a refusal: the allowed address was
    # tried and nothing else was.
    assert not isinstance(info.value, BlockedDestinationError)
    assert connects == ["127.0.0.1"]


@pytest.mark.parametrize("spelling", ["2852039166", "0xa9fea9fe", "0251.0376.0251.0376", "169.254.43518"])
def test_numeric_spelling_judged_by_resolved_address(dns, connects, spelling):
    # Linux's resolver reads these as 169.254.169.254; the fake one does too.
    table, _ = dns
    table[spelling] = ["169.254.169.254"]
    with pytest.raises(BlockedDestinationError):
        _get(f"http://{spelling}/api/tags")
    assert connects == []


def test_dns_rebinding_cannot_swap_the_checked_address(dns, server, connects):
    table, lookups = dns
    first = iter([["127.0.0.1"]])
    table["rebind.example.test"] = lambda: next(first, ["169.254.169.254"])
    port, hits = server
    url = f"http://rebind.example.test:{port}/api/tags"

    # One lookup per connection, and the socket connects to that lookup's
    # checked answer: the resolver's next (blocked) answer never reaches it.
    assert _get(url).status_code == 200
    assert lookups == ["rebind.example.test"]
    assert connects == ["127.0.0.1"]

    # The next connection resolves again, sees the blocked answer and stops.
    with pytest.raises(BlockedDestinationError):
        _get(url)
    assert lookups == ["rebind.example.test"] * 2
    assert connects == ["127.0.0.1"]
    assert len(hits) == 1


def test_followed_redirect_is_checked_too(dns, server, connects):
    port, _ = server
    with guarded_session() as session, pytest.raises(BlockedDestinationError):
        session.get(f"http://127.0.0.1:{port}/redirect-to-link-local", timeout=5)
    assert connects == ["127.0.0.1"]


# =============================================================================
# Proxies
# =============================================================================

def test_proxy_environment_variables_are_ignored(dns, make_server, connects, monkeypatch):
    port, hits = make_server()
    proxy_port, proxy_hits = make_server()
    table, _ = dns
    table["ollama.proxied.test"] = ["127.0.0.1"]
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(var, f"http://127.0.0.1:{proxy_port}")
    for var in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(var, raising=False)
    url = f"http://ollama.proxied.test:{port}/api/tags"

    # Control: a plain requests session sends this through the proxy.
    with requests.Session() as plain:
        assert plain.get(url, timeout=5).status_code == 200
    assert [path for path, _ in proxy_hits] == [url]
    assert hits == []

    # The guarded session goes straight to the checked address.
    assert _get(url).status_code == 200
    assert len(proxy_hits) == 1
    assert hits == [("/api/tags", f"ollama.proxied.test:{port}")]


def test_explicit_proxy_refused(dns, server, connects):
    port, hits = server
    with pytest.raises(BlockedDestinationError):
        _get(f"http://127.0.0.1:{port}/api/tags", proxies={"http": f"http://127.0.0.1:{port}"})
    assert connects == []
    assert hits == []


# =============================================================================
# Ordinary failures stay ordinary
# =============================================================================

def test_unreachable_and_unknown_hosts_are_plain_connection_errors(dns, connects):
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    closed_port = probe.getsockname()[1]
    probe.close()
    for url in (f"http://127.0.0.1:{closed_port}/", "http://no-such-host.example.test/"):
        with pytest.raises(requests.exceptions.ConnectionError) as info:
            _get(url)
        assert not isinstance(info.value, BlockedDestinationError)


# =============================================================================
# HTTPS keeps using the host name
# =============================================================================

def _tls_files(tmp_path, name):
    """A throwaway CA and a certificate for *name* it signed. -> (ca, cert, key) paths."""
    pytest.importorskip("cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = datetime.datetime.now(datetime.timezone.utc)

    def build(subject, issuer, public_key, signing_key, *extensions):
        builder = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)]))
            .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer)]))
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
        )
        for ext, critical in extensions:
            builder = builder.add_extension(ext, critical=critical)
        return builder.sign(signing_key, hashes.SHA256())

    def usage(**flags):
        names = ("digital_signature", "content_commitment", "key_encipherment",
                 "data_encipherment", "key_agreement", "key_cert_sign", "crl_sign",
                 "encipher_only", "decipher_only")
        return x509.KeyUsage(**{n: flags.get(n, False) for n in names})

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca = build("outbound-guard test CA", "outbound-guard test CA", ca_key.public_key(), ca_key,
               (x509.BasicConstraints(ca=True, path_length=0), True),
               (usage(key_cert_sign=True, crl_sign=True), True))
    key = ec.generate_private_key(ec.SECP256R1())
    cert = build(name, "outbound-guard test CA", key.public_key(), ca_key,
                 (x509.BasicConstraints(ca=False, path_length=None), True),
                 (usage(digital_signature=True), True),
                 (x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False),
                 (x509.SubjectAlternativeName([x509.DNSName(name)]), False),
                 (x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), False))

    paths = tmp_path / "ca.pem", tmp_path / "cert.pem", tmp_path / "key.pem"
    paths[0].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths[1].write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    paths[2].write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    return tuple(str(p) for p in paths)


def test_https_uses_the_host_name_for_sni_and_certificate(dns, make_server, connects, tmp_path):
    ca, cert, key = _tls_files(tmp_path, "ollama.tls.test")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    sni = []
    context.sni_callback = lambda _sock, server_name, _ctx: sni.append(server_name)
    port, hits = make_server(tls=context)
    table, _ = dns
    table["ollama.tls.test"] = ["127.0.0.1"]
    table["other-name.test"] = ["127.0.0.1"]

    with guarded_session() as session:
        resp = session.get(f"https://ollama.tls.test:{port}/api/tags", verify=ca, timeout=5)
    assert resp.status_code == 200
    assert sni == ["ollama.tls.test"]
    assert connects == ["127.0.0.1"]

    # Same server under another name: the certificate is checked against the
    # name in the URL, not the address, so this one fails.
    with guarded_session() as session, pytest.raises(requests.exceptions.SSLError):
        session.get(f"https://other-name.test:{port}/api/tags", verify=ca, timeout=5)
    assert len(hits) == 1
