"""The database container must never be published on a non-loopback interface.

Every compose file the repo ships is parsed, and each database service (named
``db`` or running a ``postgres`` image) must either publish no ports or bind
every published port to a loopback address. A short mapping without a host IP
("5432:5432", or just "5432") binds all interfaces, so it fails here.
"""
import ipaddress
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
_SKIP_DIRS = {".git", ".github", "node_modules", "venv", ".venv", "site"}
_COMPOSE_NAME = re.compile(r"^(docker-)?compose([.-][\w.-]+)?\.ya?ml$")
_INTERPOLATION = re.compile(r"\$\{(?P<name>\w+)(?::?-(?P<default>[^}]*))?\}")


def _compose_files():
    found = []
    for path in REPO_ROOT.rglob("*.y*ml"):
        if _SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts):
            continue
        if _COMPOSE_NAME.match(path.name):
            found.append(path)
    return sorted(found)


def _interpolate(value):
    """Resolve ${VAR:-default} to its default. Return None when a variable
    has no default, since then the bind address can't be known here."""
    unresolved = False

    def repl(match):
        nonlocal unresolved
        if match.group("default") is None:
            unresolved = True
            return ""
        return match.group("default")

    resolved = _INTERPOLATION.sub(repl, str(value))
    return None if unresolved else resolved


def _is_loopback(host):
    if host is None:
        return False
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _host_ip(port):
    """The host address a compose port entry binds to, or None for all
    interfaces or anything this check can't read."""
    if isinstance(port, dict):
        host_ip = port.get("host_ip")
        return _interpolate(host_ip) if host_ip is not None else None
    spec = _interpolate(port)
    if spec is None:
        return None
    spec = spec.split("/", 1)[0]
    if spec.startswith("["):
        host, _, rest = spec[1:].partition("]")
        return host if rest.startswith(":") and rest.count(":") == 2 else None
    parts = spec.split(":")
    return parts[0] if len(parts) == 3 else None


def _db_service_problems(name, service):
    is_db = name == "db" or str(service.get("image", "")).startswith("postgres")
    if not is_db:
        return []
    problems = []
    if service.get("network_mode") == "host":
        problems.append(f"{name}: network_mode: host exposes every port")
    for port in service.get("ports") or []:
        if not _is_loopback(_host_ip(port)):
            problems.append(f"{name}: port {port!r} is not bound to a loopback address")
    return problems


@pytest.mark.parametrize(
    "port, loopback",
    [
        ("5432:5432", False),
        ("5432", False),
        ("0.0.0.0:5432:5432", False),
        ("192.168.1.20:5432:5432", False),
        ("${DB_BIND}:5432:5432", False),
        ({"target": 5432, "published": 5432}, False),
        ({"target": 5432, "published": 5432, "host_ip": "0.0.0.0"}, False),
        ("127.0.0.1:5432:5432", True),
        ("127.0.0.1:5432:5432/tcp", True),
        ("[::1]:5432:5432", True),
        ("${DB_BIND:-127.0.0.1}:5432:5432", True),
        ({"target": 5432, "published": 5432, "host_ip": "127.0.0.1"}, True),
    ],
)
def test_port_parser(port, loopback):
    assert _is_loopback(_host_ip(port)) is loopback


def test_compose_files_are_found():
    names = [p.relative_to(REPO_ROOT).as_posix() for p in _compose_files()]
    assert "docker-compose.yml" in names


@pytest.mark.parametrize(
    "compose_file",
    _compose_files(),
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_db_service_binds_only_to_loopback(compose_file):
    config = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    problems = []
    for name, service in (config.get("services") or {}).items():
        problems.extend(_db_service_problems(name, service or {}))
    assert not problems, "\n".join(problems)
