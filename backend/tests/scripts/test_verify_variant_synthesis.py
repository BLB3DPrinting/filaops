"""Smoke that the pre-merge guard script runs cleanly under CI."""
import os
import subprocess
import sys
from pathlib import Path


def test_script_exits_zero():
    """Run the verify script as a subprocess; assert exit-zero.

    Inherits parent env (DB_PASSWORD, DATABASE_URL etc). Runs from
    backend/ so 'scripts/verify_variant_synthesis.py' resolves.
    """
    backend_dir = Path(__file__).resolve().parents[2]  # backend/
    result = subprocess.run(
        [sys.executable, "scripts/verify_variant_synthesis.py"],
        cwd=str(backend_dir),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, (
        f"verify_variant_synthesis.py failed:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
