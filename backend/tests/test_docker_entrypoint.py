"""Behavior tests for backend/scripts/docker-entrypoint.sh.

The script runs under bash with stub ``curl``/``pip``/``python`` commands on
PATH, so no network, license server or real pip is involved. The stub
command after the script (``$# -gt 0`` branch) just prints the plugin env
var the script exports, which is what Core's load_plugin() reads.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "scripts" / "docker-entrypoint.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    BASH is None or os.name == "nt",
    reason="entrypoint runs under bash in a Linux container",
)

_STUBS = {
    # Wheel download succeeds (unless STUB_DOWNLOAD_FAILS); the portal
    # download always fails so the script never writes to /app.
    "curl": """#!/bin/sh
out=""
url=""
while [ $# -gt 0 ]; do
    case "$1" in
        -o) out="$2"; shift ;;
        http*) url="$1" ;;
    esac
    shift
done
case "$url" in
    *filaops-portal*) exit 22 ;;
esac
[ -n "$STUB_DOWNLOAD_FAILS" ] && exit 22
echo wheel-bytes > "$out"
""",
    # pip prints like pip and exits $STUB_PIP_EXIT; success marks the
    # plugin as importable for the stub python below.
    "pip": """#!/bin/sh
echo "Processing /tmp/filaops_pro-0.1.0-py3-none-any.whl"
if [ "${STUB_PIP_EXIT:-0}" -ne 0 ]; then
    echo "ERROR: Could not find a version that satisfies the requirement httpx>=99"
    exit "$STUB_PIP_EXIT"
fi
echo "Successfully installed filaops-pro-0.1.0"
touch "$STUB_STATE/installed"
""",
    "python": """#!/bin/sh
[ -f "$STUB_STATE/installed" ]
""",
}


def _run(tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    for name, body in _STUBS.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)

    run_env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "STUB_STATE": str(state),
        "LICENSE_SERVER_URL": "http://license.invalid",
        **env,
    }
    return subprocess.run(
        [BASH, str(ENTRYPOINT), "sh", "-c", 'echo "PLUGIN_MODULE=${FILAOPS_PRO_MODULE}"'],
        env=run_env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_successful_install_enables_plugin(tmp_path):
    result = _run(tmp_path, FILAOPS_LICENSE_KEY="<license-key>")

    assert result.returncode == 0, result.stderr
    assert "FilaOps: PRO plugin installed." in result.stdout
    assert "PLUGIN_MODULE=filaops_pro" in result.stdout


def test_failed_pip_install_is_reported_and_core_still_starts(tmp_path):
    """`pip install ... | tail -1` took tail's exit status, so a failed
    install printed "PRO plugin installed." and started Core without it."""
    result = _run(tmp_path, FILAOPS_LICENSE_KEY="<license-key>", STUB_PIP_EXIT="1")
    output = result.stdout + result.stderr

    assert result.returncode == 0, output  # Core must still boot
    assert "PRO plugin installed." not in output
    assert "PRO plugin install failed (pip exit 1)" in result.stderr
    # pip's actual error reaches the logs, not just its last line
    assert "Could not find a version that satisfies" in result.stderr
    assert "Starting in Community mode." in result.stderr
    assert "PLUGIN_MODULE=\n" in result.stdout


def test_failed_download_starts_in_community_mode(tmp_path):
    result = _run(tmp_path, FILAOPS_LICENSE_KEY="<license-key>", STUB_DOWNLOAD_FAILS="1")

    assert result.returncode == 0, result.stderr
    assert "Could not download PRO plugin" in result.stdout
    assert "PLUGIN_MODULE=\n" in result.stdout


def test_no_license_key_skips_plugin(tmp_path):
    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "Downloading PRO plugin" not in result.stdout
    assert "PLUGIN_MODULE=\n" in result.stdout
