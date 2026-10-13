"""Every shipped compose file that runs the backend must put backups on a volume.

The backend writes database backups to ``BACKUP_DIR`` (``/app/backups`` in
the image) and refuses to run them when, inside a container, that folder is
not a mounted volume: otherwise every upgrade, which recreates the container,
would delete them. A compose file shipped without the mount would leave the
Backups page permanently refusing, so this checks the shipped files the same
way ``test_compose_config_volume`` checks the install_uuid directory.
"""
import pytest
import yaml

from tests.unit.test_compose_config_volume import _environment, _mount, _norm, _runs_backend
from tests.unit.test_compose_db_port_binding import _compose_files

DEFAULT_BACKUP_DIR = "/app/backups"


def _backup_dir(service):
    value = _environment(service).get("BACKUP_DIR", "").strip()
    return value or DEFAULT_BACKUP_DIR


def _backup_dir_problems(name, service, top_level_volumes):
    target_dir = _norm(_backup_dir(service))
    for entry in service.get("volumes") or []:
        source, target, kind = _mount(entry)
        if target is None or _norm(target) != target_dir:
            continue
        if kind == "tmpfs" or not source:
            return [f"{name}: {target_dir} is mounted without a persistent source ({entry!r})"]
        if kind == "volume" and source not in top_level_volumes:
            return [f"{name}: volume {source!r} for {target_dir} is not declared under top-level volumes"]
        return []
    return [f"{name}: {target_dir} (database backups) is not on a volume; backups will refuse to run"]


@pytest.mark.parametrize(
    "service, ok",
    [
        ({"volumes": ["filaops_backups:/app/backups"]}, True),
        ({"volumes": ["./backups:/app/backups"]}, True),
        ({"volumes": ["/app/backups"]}, False),
        ({"volumes": [{"type": "tmpfs", "target": "/app/backups"}]}, False),
        ({"volumes": ["undeclared:/app/backups"]}, False),
        ({"volumes": ["./uploads:/app/uploads"]}, False),
        (
            {"environment": {"BACKUP_DIR": "/srv/backups"}, "volumes": ["filaops_backups:/srv/backups"]},
            True,
        ),
    ],
)
def test_backup_dir_check(service, ok):
    problems = _backup_dir_problems("backend", service, {"filaops_backups": None})
    assert (problems == []) is ok, problems


def test_stock_compose_backend_is_checked():
    files = _compose_files()
    assert any(f.name == "docker-compose.yml" for f in files)


@pytest.mark.parametrize("compose_file", _compose_files(), ids=lambda p: p.name)
def test_backend_backup_dir_is_persisted(compose_file):
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    top_level = data.get("volumes") or {}
    problems = []
    for name, service in (data.get("services") or {}).items():
        if _runs_backend(service, compose_file):
            problems += _backup_dir_problems(name, service, top_level)
    assert problems == []
