"""Outbound HTTP guard for URLs that users configure.

SEC: when the server fetches a URL that an admin typed in (today: the Ollama
URL in the AI settings), that fetch must not reach link-local or cloud
metadata addresses. The metadata service hands out cloud credentials, and no
one runs a real service there. Loopback, private LAN (RFC 1918), IPv6 ULA and
CGNAT (100.64.0.0/10, which Tailscale uses) stay allowed, because self-hosted
services such as Ollama live there.

The check runs when the socket is opened, on the addresses the host name
actually resolved to:

* the host is resolved once and every address is checked. Blocked answers
  are dropped and never contacted; if every answer is blocked the request is
  refused. A name that also has an allowed answer connects to that one only,
  so an mDNS (.local) or Windows LLMNR name that comes back with both its LAN
  address and its fe80:: address still works;
* the socket connects only to the addresses that were checked and allowed,
  so a second DNS answer (DNS rebinding) cannot swap in another one;
* numeric spellings, IPv4-mapped/-compatible and NAT64 IPv6 forms are caught
  because the check sees the address the OS resolved, not the text of the URL;
* TLS still uses the host name for SNI and certificate checks;
* proxies are refused and proxy environment variables are ignored, because a
  proxy would pick the address itself;
* every redirect a caller chooses to follow opens its connection through the
  same check.

Use it through guarded_session()::

    with guarded_session() as session:
        session.get(url, timeout=5, allow_redirects=False)

A refused destination raises BlockedDestinationError. It subclasses requests'
ConnectionError, so code that already handles connection errors fails closed,
and code that wants its own message catches BlockedDestinationError first.

This hooks urllib3 2.x's HTTPConnection._new_conn (the one place a connection
opens its socket). tests/core/test_outbound_guard.py fails if an upgrade
stops routing connections through it.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import sys
from typing import Optional, Union

import requests
from requests.adapters import HTTPAdapter
from requests.utils import select_proxy
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import (
    ConnectTimeoutError,
    LocationParseError,
    NameResolutionError,
    NewConnectionError,
)
from urllib3.util.connection import allowed_gai_family
from urllib3.util.timeout import Timeout

IPAddress = Union[ipaddress.IPv4Address, ipaddress.IPv6Address]

_LINK_LOCAL_V4 = ipaddress.ip_network("169.254.0.0/16")
_LINK_LOCAL_V6 = ipaddress.ip_network("fe80::/10")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
# RFC 8215 local-use NAT64 prefix. The operator picks where the IPv4 address
# sits inside it (RFC 6052); the usual /96 layout puts it in the last 32 bits.
_NAT64_LOCAL_USE = ipaddress.ip_network("64:ff9b:1::/48")
_V4_COMPATIBLE = ipaddress.ip_network("::/96")

# Metadata endpoints outside the link-local ranges above. AWS, Google Cloud,
# Azure IMDS, Oracle Cloud, DigitalOcean, Hetzner and OpenStack all answer on
# 169.254.169.254, which the link-local range already covers. Single
# addresses only: the ULA and CGNAT ranges around them stay usable.
_METADATA_ADDRESSES = frozenset(ipaddress.ip_address(a) for a in (
    "fd00:ec2::254",        # AWS instance metadata over IPv6 (Nitro)
    "fd00:ec2::23",         # AWS EKS Pod Identity agent over IPv6
    "fd20:ce::254",         # Google Cloud metadata server over IPv6
    "fd00:c1::a9fe:a9fe",   # Oracle Cloud instance metadata over IPv6
    "100.100.100.200",      # Alibaba Cloud metadata
    "168.63.129.16",        # Azure WireServer (host agent)
))

# Short, decimal, octal and hex IPv4 spellings (2852039166, 0xa9fea9fe, ...)
# that the C resolver treats as addresses. Checked with inet_aton, no DNS.
_NUMERIC_V4_RE = re.compile(r"[0-9A-Fa-fXx.]+")


class BlockedDestinationError(requests.exceptions.ConnectionError):
    """The URL's host is, or resolves only to, addresses outbound fetches may not reach."""


class _BlockedAtConnect(Exception):
    """Raised inside urllib3 when a host resolves only to blocked addresses.

    Deliberately not an OSError: urllib3 retries and re-wraps OSErrors, which
    would bury it. _GuardedAdapter.send turns it into BlockedDestinationError.
    """


# =============================================================================
# Address rules
# =============================================================================

def _as_address(ip: Union[str, IPAddress]) -> IPAddress:
    # Drop an IPv6 zone ("fe80::1%eth0"): it names an interface, not an address.
    return ipaddress.ip_address(str(ip).split("%", 1)[0])


def _embedded_ipv4(addr: ipaddress.IPv6Address) -> Optional[ipaddress.IPv4Address]:
    """The IPv4 address an IPv4-mapped, IPv4-compatible or NAT64 address carries."""
    if addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    if addr in _NAT64 or addr in _V4_COMPATIBLE:
        return ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    return None


def _ipv4_is_link_local_or_metadata(addr: ipaddress.IPv4Address) -> bool:
    return addr in _LINK_LOCAL_V4 or addr in _METADATA_ADDRESSES


def _ipv4_is_blocked(addr: ipaddress.IPv4Address) -> bool:
    return (
        _ipv4_is_link_local_or_metadata(addr)
        or addr.is_multicast            # 224.0.0.0/4
        or addr.is_reserved             # 240.0.0.0/4, including 255.255.255.255
    )


def _local_use_nat64_is_blocked(addr: ipaddress.IPv6Address) -> bool:
    """Judge a 64:ff9b:1::/48 address by its last 32 bits, the /96 layout.

    Only link-local and metadata are checked there. In the other RFC 6052
    layouts (/48 to /64) those bits are zero or hold one stray octet (d.0.0.0),
    which is never link-local or metadata, so a working translation of a LAN
    address is not refused by mistake.
    """
    return addr in _NAT64_LOCAL_USE and _ipv4_is_link_local_or_metadata(
        ipaddress.IPv4Address(int(addr) & 0xFFFFFFFF)
    )


def is_blocked_destination(ip: Union[str, IPAddress]) -> bool:
    """True if a fetch of a user-configured URL must not connect to *ip*.

    Blocked: IPv4 and IPv6 link-local (169.254.0.0/16, fe80::/10), known cloud
    metadata addresses, multicast, and reserved IPv4 (240.0.0.0/4, which
    includes the broadcast address). IPv4-mapped, IPv4-compatible and NAT64
    (64:ff9b::/96) IPv6 addresses are also judged by the IPv4 address they
    carry, and local-use NAT64 (64:ff9b:1::/48) addresses carrying a
    link-local or metadata address in the usual /96 layout are blocked too.

    Allowed: everything else, including loopback, RFC 1918, ULA (fc00::/7)
    and CGNAT (100.64.0.0/10), apart from the metadata addresses in them.

    The unspecified addresses 0.0.0.0 and :: are allowed because they count
    as loopback: connecting to them reaches this host (Linux, macOS) or
    fails, depending on the OS, and never reaches another machine. People
    copy http://0.0.0.0:11434 from OLLAMA_HOST=0.0.0.0. A future policy that
    blocks loopback must block 0.0.0.0 and :: (and their IPv4-mapped forms)
    as well.

    Raises ValueError if *ip* is not an IP address.
    """
    addr = _as_address(ip)
    if isinstance(addr, ipaddress.IPv4Address):
        return _ipv4_is_blocked(addr)
    embedded = _embedded_ipv4(addr)
    if embedded is not None and _ipv4_is_blocked(embedded):
        return True
    if _local_use_nat64_is_blocked(addr):
        return True
    return (
        addr in _LINK_LOCAL_V6
        or addr in _METADATA_ADDRESSES
        or addr.is_multicast
    )


def parse_ip_literal(host: str) -> Optional[IPAddress]:
    """The address *host* spells out, or None if it is a host name. Never uses DNS.

    Accepts what ipaddress accepts (IPv6 with or without brackets, any zone is
    ignored) and the numeric IPv4 forms the C resolver accepts. Use it to
    refuse a blocked literal early (for example when a URL is saved); the
    connect-time check in guarded_session() is what enforces the rule.
    """
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return _as_address(host)
    except ValueError:
        pass
    if _NUMERIC_V4_RE.fullmatch(host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            pass
    return None


# =============================================================================
# Connect-time check
# =============================================================================

def _resolve_checked(host: str, port: int) -> list:
    """Resolve *host* once and return only the answers that may be contacted.

    Blocked answers are dropped, so they are never tried, not even after the
    allowed ones fail. Refuses the request if every answer is blocked.
    """
    infos = socket.getaddrinfo(host, port, allowed_gai_family(), socket.SOCK_STREAM)
    allowed, blocked = [], []
    for info in infos:
        try:
            refused = is_blocked_destination(info[4][0])
        except ValueError:
            refused = True  # not an IP we can judge: fail closed
        (blocked if refused else allowed).append(info)
    if blocked and not allowed:
        addresses = ", ".join(dict.fromkeys(str(info[4][0]) for info in blocked))
        raise _BlockedAtConnect(f"{host} resolves only to blocked addresses ({addresses})")
    return allowed


def _connect_to_checked(infos: list, timeout, source_address, socket_options) -> socket.socket:
    """Connect to the first reachable address in *infos*, the way urllib3 does.

    Only the socket addresses already checked are used, so nothing here can
    resolve the name again.
    """
    err: Optional[OSError] = None
    for family, socktype, proto, _canonname, sockaddr in infos:
        sock = None
        try:
            sock = socket.socket(family, socktype, proto)
            for option in socket_options or ():
                sock.setsockopt(*option)
            sock.settimeout(Timeout.resolve_default_timeout(timeout))
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            return sock
        except OSError as exc:
            err = exc
            if sock is not None:
                sock.close()
    if err is not None:
        raise err
    raise OSError("getaddrinfo returns an empty list")


class _GuardedConnectMixin:
    """Replaces urllib3's HTTPConnection._new_conn: check, then connect."""

    def _new_conn(self) -> socket.socket:
        host = self._dns_host
        if host.startswith("["):
            host = host.strip("[]")
        try:
            host.encode("idna")
        except UnicodeError:
            raise LocationParseError(f"'{host}', label empty or too long") from None

        # Same error mapping as urllib3's HTTPConnection._new_conn, so requests
        # still reports ConnectTimeout / ConnectionError as before.
        try:
            infos = _resolve_checked(host, self.port)
            sock = _connect_to_checked(
                infos, self.timeout, self.source_address, self.socket_options
            )
        except socket.gaierror as exc:
            raise NameResolutionError(self.host, self, exc) from exc
        except TimeoutError as exc:
            raise ConnectTimeoutError(
                self,
                f"Connection to {self.host} timed out. (connect timeout={self.timeout})",
            ) from exc
        except OSError as exc:
            raise NewConnectionError(
                self, f"Failed to establish a new connection: {exc}"
            ) from exc

        sys.audit("http.client.connect", self, self.host, self.port)
        return sock


class _GuardedHTTPConnection(_GuardedConnectMixin, HTTPConnection):
    pass


class _GuardedHTTPSConnection(_GuardedConnectMixin, HTTPSConnection):
    pass


class _GuardedHTTPConnectionPool(HTTPConnectionPool):
    ConnectionCls = _GuardedHTTPConnection


class _GuardedHTTPSConnectionPool(HTTPSConnectionPool):
    ConnectionCls = _GuardedHTTPSConnection


_GUARDED_POOLS = {"http": _GuardedHTTPConnectionPool, "https": _GuardedHTTPSConnectionPool}


class _GuardedAdapter(HTTPAdapter):
    """HTTPAdapter whose connections all go through the connect-time check."""

    def init_poolmanager(self, *args, **kwargs) -> None:
        super().init_poolmanager(*args, **kwargs)
        self.poolmanager.pool_classes_by_scheme = _GUARDED_POOLS

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        if select_proxy(request.url, proxies or {}):
            # A proxy resolves and connects on our behalf, so the check would
            # only see the proxy's address.
            raise BlockedDestinationError(
                "guarded requests cannot go through a proxy", request=request
            )
        try:
            return super().send(
                request, stream=stream, timeout=timeout, verify=verify,
                cert=cert, proxies=proxies,
            )
        except _BlockedAtConnect as exc:
            raise BlockedDestinationError(str(exc), request=request) from None


def guarded_session() -> requests.Session:
    """A requests Session whose every connection passes the connect-time check.

    It ignores proxy environment variables and ~/.netrc (trust_env=False).
    REQUESTS_CA_BUNDLE / CURL_CA_BUNDLE are still honoured, since they only
    change which certificates are trusted.
    """
    session = requests.Session()
    session.trust_env = False
    ca_bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("CURL_CA_BUNDLE")
    if ca_bundle:
        session.verify = ca_bundle
    adapter = _GuardedAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
