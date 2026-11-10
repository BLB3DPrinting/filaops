"""Behavior tests for backend/scripts/docker-migrate.sh.

The script runs under bash with stub ``alembic``/``docker``/``python`` commands
first on PATH, so no database, no Docker daemon and no real alembic are
involved. The stub ``alembic`` can be told to report a database revision the
code does not have, which is what an operator sees after going back to an
older version without restoring the backup taken before the upgrade.

What matters in that case: the script still stops with a non-zero exit, but
what it prints must not tell the operator to delete their data first, and it
must never change anything by itself.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "docker-migrate.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    BASH is None,
    reason="docker-migrate.sh runs under bash in a Linux container",
)

_STUBS = {
    # `alembic current` either reports the revision as unknown (the way alembic
    # does when the database is ahead of the code) or prints the head.
    # Every call is recorded so a test can see what the script ran.
    "alembic": """#!/bin/sh
echo "$*" >> "$STUB_STATE/alembic-calls"
if [ "$1" = "current" ]; then
    if [ -n "$STUB_UNKNOWN_REVISION" ]; then
        # Same lines real alembic prints: log chatter, then the error twice.
        echo "INFO  [alembic.runtime.migration] Context impl PostgresqlImpl."
        echo "ERROR [alembic.util.messaging] Can't locate revision identified by '$STUB_UNKNOWN_REVISION'"
        echo "FAILED: Can't locate revision identified by '$STUB_UNKNOWN_REVISION'"
        exit 255
    fi
    echo "105 (head)"
fi
exit 0
""",
    # Nothing in the script may touch Docker. If it ever does, the call is
    # recorded and the test fails.
    "docker": """#!/bin/sh
echo "$*" >> "$STUB_STATE/docker-calls"
exit 0
""",
    # `python -c "import filaops_pro"` fails: no PRO plugin installed.
    "python": """#!/bin/sh
exit 1
""",
}


def _run(tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess, Path]:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    for name, body in _STUBS.items():
        stub = bin_dir / name
        # Bytes, not write_text: on Windows write_text would turn the LF line
        # endings into CRLF and break the shebang line.
        stub.write_bytes(body.encode())
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    run_env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_STATE": state.as_posix(),
        **env,
    }
    result = subprocess.run(
        [BASH, SCRIPT.as_posix()],
        env=run_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, state


def _calls(state: Path, name: str) -> list[str]:
    path = state / name
    return path.read_text().splitlines() if path.exists() else []


def _mismatch(tmp_path: Path) -> tuple[subprocess.CompletedProcess, str, Path]:
    result, state = _run(tmp_path, STUB_UNKNOWN_REVISION="105")
    return result, result.stdout + result.stderr, state


def test_database_ahead_of_code_still_stops_the_migrate_step(tmp_path):
    result, output, state = _mismatch(tmp_path)

    assert result.returncode == 1, output
    assert "DATABASE MIGRATION MISMATCH DETECTED" in output
    # Detection must not let the script go on to upgrade a database it cannot read.
    assert _calls(state, "alembic-calls") == ["current"]


def test_message_says_what_happened_and_which_revision(tmp_path):
    _, output, _ = _mismatch(tmp_path)

    assert re.search(r"upgraded by a newer version", output), output
    # The alembic line that names the revision is shown, so the operator can
    # see which revision the database is on.
    # (once, though alembic prints it twice).
    assert output.count("Can't locate revision identified by '105'") == 1, output
    # Not alembic's unrelated log chatter, or its log prefixes.
    assert "Context impl PostgresqlImpl" not in output
    assert "alembic.util.messaging" not in output


def test_first_advice_is_to_restore_not_to_delete(tmp_path):
    _, output, _ = _mismatch(tmp_path)

    assert "To fix this, remove the database volume" not in output
    assert "start fresh" not in output.lower()
    # Safe options first: the newer version again, or the backup, by way of
    # section 3 of the rollback guide.
    assert "check out the newer version" in output.lower()
    assert "restore the database backup" in output.lower()
    assert "section 3 of docs/ROLLBACK.md" in output
    assert "https://blb3dprinting.github.io/filaops/ROLLBACK/" in output


def test_volume_removal_is_a_last_resort_next_to_a_data_loss_warning(tmp_path):
    _, output, _ = _mismatch(tmp_path)
    lines = output.splitlines()

    def line_of(needle: str) -> int:
        for i, line in enumerate(lines):
            if needle in line.lower():
                return i
        raise AssertionError(f"{needle!r} not printed:\n{output}")

    remove = line_of("docker volume rm filaops_pgdata")
    restore = line_of("rollback")
    check_out = line_of("check out the newer version")

    # The destructive command comes after both safe options...
    assert check_out < restore < remove, output
    # ...and right after wording that says it deletes everything.
    just_before = "\n".join(lines[max(0, remove - 5):remove]).lower()
    assert "deletes all data" in just_before, output
    assert "test install" in just_before, output


def test_script_changes_nothing_by_itself(tmp_path):
    _, _, state = _mismatch(tmp_path)

    assert _calls(state, "docker-calls") == []
    # Only the read-only `alembic current` ran: no upgrade, no stamp.
    assert _calls(state, "alembic-calls") == ["current"]


def test_database_that_matches_the_code_still_migrates(tmp_path):
    """The detection stays narrow: only an unknown revision stops the script."""
    result, state = _run(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "MISMATCH" not in result.stdout
    assert _calls(state, "alembic-calls") == ["current", "upgrade head"]
    assert "FilaOps: Migrations complete." in result.stdout
