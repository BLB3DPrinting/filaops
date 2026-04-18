"""
Safety guards for seed_demo.

- check_db_name: refuse unless DB name contains 'demo' or 'test'
  (override with FILAOPS_DEMO_OVERRIDE=1).
- check_alembic_head: refuse if DB is behind latest migration.
  Rationale: silent auto-migration hides schema drift; better to
  fail loud with 'run alembic upgrade head'.
- confirm_wipe: interactive prompt unless --yes passed.
- wipe_all_tables: TRUNCATE ... RESTART IDENTITY CASCADE for
  determinism (including auto-increment ID resets).
- validate_enum_fields: catch invalid enum-backed strings in fixtures
  at seed time rather than at first API call. Every seed module with
  status/type/brand fields should call this before the first db.add().
"""
import os
import subprocess
import sys
from enum import Enum
from pathlib import Path
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


# Invoke alembic via the same Python interpreter (python -m alembic) so that
# running the seed with an explicit venv path like
#   /path/to/venv/Scripts/python.exe -m scripts.seed_demo
# still works without the venv being on PATH. Shelling out to bare `alembic`
# would require activation.
_ALEMBIC_CMD = [sys.executable, "-m", "alembic"]


def check_db_name(db_name: str) -> None:
    override = os.environ.get("FILAOPS_DEMO_OVERRIDE") == "1"
    if override:
        print(f"[seed] FILAOPS_DEMO_OVERRIDE=1 — bypassing DB name guard.")
        return
    lowered = db_name.lower()
    if "demo" not in lowered and "test" not in lowered:
        print(
            f"[seed] REFUSING TO RUN: database name {db_name!r} does not contain "
            f"'demo' or 'test'.\n"
            f"       Set FILAOPS_DEMO_OVERRIDE=1 only if you really mean to seed "
            f"a non-demo database.",
            file=sys.stderr,
        )
        sys.exit(1)


def check_alembic_head() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    try:
        current = subprocess.run(
            [*_ALEMBIC_CMD, "current"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        heads = subprocess.run(
            [*_ALEMBIC_CMD, "heads"],
            cwd=backend_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except FileNotFoundError:
        print(
            "[seed] REFUSING TO RUN: alembic module not available in this "
            "Python environment.\n"
            f"       Tried: {' '.join(_ALEMBIC_CMD)} current\n"
            "       Install dev requirements: pip install -r requirements-dev.txt",
            file=sys.stderr,
        )
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(
            f"[seed] REFUSING TO RUN: alembic check failed.\n"
            f"       stdout: {e.stdout}\n"
            f"       stderr: {e.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)

    current_rev = current.split()[0] if current else ""
    head_rev = heads.split()[0] if heads else ""

    if not current_rev or current_rev != head_rev:
        print(
            f"[seed] REFUSING TO RUN: database is not at the latest migration.\n"
            f"       current: {current_rev or '(none)'}\n"
            f"       head:    {head_rev or '(none)'}\n"
            f"       Run:     cd backend && alembic upgrade head",
            file=sys.stderr,
        )
        sys.exit(1)


def confirm_wipe(db_name: str, yes: bool) -> None:
    if yes:
        return
    print(f"[seed] This will WIPE ALL DATA in {db_name!r}.")
    resp = input("[seed] Type 'yes' to continue: ").strip().lower()
    if resp != "yes":
        print("[seed] Aborted.")
        sys.exit(1)


def validate_enum_fields(
    fixtures: Iterable[dict],
    field_map: dict[str, type[Enum]],
    *,
    fixture_label: str = "fixture",
) -> None:
    """
    Verify every fixture value for the named fields is a valid enum member.

    Why this exists: the DB layer often accepts free-form strings for columns
    the schema/API layer later validates as strict enums. A bad value survives
    the INSERT and blows up at GET time (FastAPI 500). This helper moves the
    failure to seed time with a clear message, before anything hits the DB.

    Args:
        fixtures: iterable of dicts (e.g. PRINTER_FIXTURES).
        field_map: {field_name: EnumClass}. Values are matched against
            `member.value` (not `member.name`).
        fixture_label: label for error messages (e.g. "printer").

    Raises:
        ValueError with the offending index + field + value + valid options.
    """
    for i, fx in enumerate(fixtures):
        for field_name, enum_cls in field_map.items():
            value = fx.get(field_name)
            if value is None:
                continue
            valid = {member.value for member in enum_cls}
            if value not in valid:
                raise ValueError(
                    f"[seed] Invalid {fixture_label}[{i}].{field_name} = "
                    f"{value!r}. Must be one of: {sorted(valid)}"
                )


def wipe_all_tables(db: Session) -> None:
    result = db.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
        )
    )
    tables = [row[0] for row in result]
    if not tables:
        return
    joined = ", ".join(f'"{t}"' for t in tables)
    db.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))
    db.commit()
