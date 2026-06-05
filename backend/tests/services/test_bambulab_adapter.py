import socket

import pytest

from app.services.printer_discovery.adapters.bambulab import BambuLabAdapter


class FakeDiscoverySocket:
    def __init__(self):
        self.bound_address = None
        self.sent_addresses = []
        self.closed = False

    def setsockopt(self, *_args):
        pass

    def settimeout(self, _timeout):
        pass

    def bind(self, address):
        self.bound_address = address

    def sendto(self, _data, address):
        self.sent_addresses.append(address)

    def recvfrom(self, _buffer_size):
        raise socket.timeout

    def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_discover_local_binds_to_specific_local_interface(monkeypatch):
    adapter = BambuLabAdapter()
    fake_socket = FakeDiscoverySocket()

    monkeypatch.setattr(adapter, "_get_ssdp_bind_host", lambda: "192.168.1.25")
    monkeypatch.setattr(
        "app.services.printer_discovery.adapters.bambulab.socket.socket",
        lambda *_args, **_kwargs: fake_socket,
    )

    discovered = await adapter.discover_local(timeout_seconds=0.01)

    assert discovered == []
    assert fake_socket.bound_address == ("192.168.1.25", 0)
    assert fake_socket.bound_address[0] not in ("", "0.0.0.0")
    assert fake_socket.closed is True


def test_get_ssdp_bind_host_uses_non_loopback_ipv4(monkeypatch):
    adapter = BambuLabAdapter()

    monkeypatch.setattr(
        "app.services.printer_discovery.adapters.bambulab.socket.getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("127.0.0.1", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("0.0.0.0", 0)),
            (socket.AF_INET, socket.SOCK_DGRAM, 0, "", ("192.168.1.25", 0)),
        ],
    )

    assert adapter._get_ssdp_bind_host() == "192.168.1.25"
