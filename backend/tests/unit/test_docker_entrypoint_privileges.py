"""The container entrypoint must not start the app or migrations as root.

The entrypoint starts as root so it can install plugins and fix ownership of
the directories the app writes, then drops to appuser through ``RUN_AS``.
Running the drop needs a real container (root plus the image's appuser), so
the docker compose smoke test covers the behaviour; this test guards the
script against a new command that skips ``RUN_AS``.
"""
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[2] / "scripts" / "docker-entrypoint.sh"


def _code_lines():
    for raw in ENTRYPOINT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            yield line


def test_every_exec_goes_through_run_as():
    execs = [line for line in _code_lines() if line.startswith("exec ")]
    assert execs, "entrypoint has no exec lines; this test no longer checks anything"
    for line in execs:
        assert line.startswith('exec "${RUN_AS[@]}" '), line


def test_migrations_run_through_run_as():
    alembic = [line for line in _code_lines() if "alembic" in line and not line.startswith("echo")]
    assert alembic
    for line in alembic:
        assert line.startswith('"${RUN_AS[@]}" '), line


def test_drop_target_is_appuser():
    text = ENTRYPOINT.read_text(encoding="utf-8")
    assert "APP_USER=appuser" in text
    assert 'setpriv --reuid="$APP_USER" --regid="$APP_GROUP" --init-groups' in text
