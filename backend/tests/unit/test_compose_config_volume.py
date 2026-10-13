"""Every shipped compose file that runs the backend must persist its config dir.

The backend keeps ``install_uuid`` in ``LICENSE_CONFIG_DIR`` (default
``/var/lib/filaops/config``). ``app.core.crypto`` derives the key for
encrypted columns (``company_settings.ai_api_key``) from it, so if the
directory lives only in the container, recreating the container (as
``docker compose up -d --build`` does on every upgrade) creates a new
install_uuid and stored secrets can no longer be decrypted.

A service "runs the backend" when it is built from ``backend/`` and keeps the
image's default command (or runs uvicorn). One-shot services built from the
same image with their own command, such as ``migrate``, never read
install_uuid and are not checked. The directory must be mounted from a named
volume or a host path; an anonymous volume is dropped by ``docker compose
down`` and is not enough.
"""
import posixpath
from pathlib import PurePosixPath

import pytest
import yaml

from tests.unit.test_compose_db_port_binding import REPO_ROOT, _compose_files

DEFAULT_CONFIG_DIR = "/var/lib/filaops/config"


def _build_context(service):
    build = service.get("build")
    if isinstance(build, str):
        return build
    if isinstance(build, dict):
        return build.get("context")
    return None


def _runs_backend(service, compose_file):
    context = _build_context(service)
    if context is None:
        return False
    resolved = (compose_file.parent / context).resolve()
    if resolved != (REPO_ROOT / "backend").resolve():
        return False
    command = service.get("command")
    if command is None:
        return True
    text = command if isinstance(command, str) else " ".join(map(str, command))
    return "uvicorn" in text


def _environment(service):
    env = service.get("environment") or {}
    if isinstance(env, dict):
        return {k: ("" if v is None else str(v)) for k, v in env.items()}
    parsed = {}
    for item in env:
        key, _, value = str(item).partition("=")
        parsed[key] = value
    return parsed


def _config_dir(service):
    value = _environment(service).get("LICENSE_CONFIG_DIR", "").strip()
    return value or DEFAULT_CONFIG_DIR


def _mount(entry):
    """Return (source, target, type) for a compose volume entry. Source is
    None for an anonymous volume."""
    if isinstance(entry, dict):
        return entry.get("source"), entry.get("target"), entry.get("type", "volume")
    parts = str(entry).split(":")
    if len(parts) == 1:
        return None, parts[0], "volume"
    source, target = parts[0], parts[1]
    is_path = source.startswith((".", "/", "~", "$"))
    return source, target, "bind" if is_path else "volume"


def _norm(path):
    return posixpath.normpath(str(PurePosixPath(path)))


def _config_dir_problems(name, service, top_level_volumes):
    target_dir = _norm(_config_dir(service))
    for entry in service.get("volumes") or []:
        source, target, kind = _mount(entry)
        if target is None or _norm(target) != target_dir:
            continue
        if kind == "tmpfs" or not source:
            return [f"{name}: {target_dir} is mounted without a persistent source ({entry!r})"]
        if kind == "volume" and source not in top_level_volumes:
            return [f"{name}: volume {source!r} for {target_dir} is not declared under top-level volumes"]
        return []
    return [f"{name}: {target_dir} (install_uuid) is not on a volume; it is lost when the container is recreated"]


@pytest.mark.parametrize(
    "entry, expected",
    [
        ("filaops_config:/var/lib/filaops/config", ("filaops_config", "/var/lib/filaops/config", "volume")),
        ("./config:/var/lib/filaops/config:rw", ("./config", "/var/lib/filaops/config", "bind")),
        ("/var/lib/filaops/config", (None, "/var/lib/filaops/config", "volume")),
        (
            {"type": "volume", "source": "cfg", "target": "/var/lib/filaops/config"},
            ("cfg", "/var/lib/filaops/config", "volume"),
        ),
        ({"type": "tmpfs", "target": "/var/lib/filaops/config"}, (None, "/var/lib/filaops/config", "tmpfs")),
    ],
)
def test_mount_parser(entry, expected):
    assert _mount(entry) == expected


@pytest.mark.parametrize(
    "service, ok",
    [
        ({"volumes": ["cfg:/var/lib/filaops/config"]}, True),
        ({"volumes": ["cfg:/var/lib/filaops/config/"]}, True),
        ({"volumes": ["./uploads:/app/uploads"]}, False),
        ({"volumes": ["/var/lib/filaops/config"]}, False),
        ({"volumes": ["undeclared:/var/lib/filaops/config"]}, False),
        ({"volumes": [{"type": "tmpfs", "target": "/var/lib/filaops/config"}]}, False),
        (
            {"environment": {"LICENSE_CONFIG_DIR": "/data/cfg"}, "volumes": ["cfg:/var/lib/filaops/config"]},
            False,
        ),
        ({"environment": ["LICENSE_CONFIG_DIR=/data/cfg"], "volumes": ["./cfg:/data/cfg"]}, True),
    ],
)
def test_config_dir_check(service, ok):
    assert (not _config_dir_problems("backend", service, {"cfg": None})) is ok


def test_stock_compose_backend_is_checked():
    """Guard the detector: if it stopped recognising the stock backend
    service, the check below would pass without checking anything."""
    compose_file = REPO_ROOT / "docker-compose.yml"
    services = yaml.safe_load(compose_file.read_text(encoding="utf-8"))["services"]
    checked = {name for name, svc in services.items() if _runs_backend(svc or {}, compose_file)}
    assert checked == {"backend"}


@pytest.mark.parametrize(
    "compose_file",
    _compose_files(),
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
def test_backend_config_dir_is_persisted(compose_file):
    config = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    top_level_volumes = config.get("volumes") or {}
    problems = []
    for name, service in (config.get("services") or {}).items():
        service = service or {}
        if _runs_backend(service, compose_file):
            problems.extend(_config_dir_problems(name, service, top_level_volumes))
    assert not problems, "\n".join(problems)
