"""
Unit preflight: what the pending unit migrations will do to this database.

Run it with the NEW version's code against the database BEFORE it is upgraded.
It changes nothing. It prints what each pending migration would report: the
units it would add or correct, the unit codes it would rewrite, and every item
or line it would leave for you to look at.

Run from the ``backend`` folder:

    python scripts/uom_preflight.py

It reads the same database settings as the application.

How it works
    It holds no checks of its own. A data migration that can be reported on
    has five functions: ``read_state``, ``plan``, ``project``, ``apply`` and
    ``report_lines``. This script reads the database's revision, finds every
    newer migration with those functions, and for each one in upgrade order
    prints its plan and works out the rows as that migration would leave them.
    The next migration plans from those rows, so a later migration is reported
    as if the earlier ones had already run. Everything happens inside a
    read-only transaction that is rolled back.
"""
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import sqlalchemy as sa  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

_NEEDED = ("read_state", "plan", "project", "report_lines")


def current_revision(bind) -> Optional[str]:
    """The database's migration revision, or None when it has never been migrated."""
    if not sa.inspect(bind).has_table("alembic_version"):
        return None
    return bind.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()


def pending_migrations(revision: Optional[str]) -> list:
    """The migrations newer than ``revision`` that can be reported on, oldest first."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    script = ScriptDirectory.from_config(config)
    newer = list(script.iterate_revisions("heads", revision or "base"))
    return [
        step.module for step in reversed(newer)
        if all(hasattr(step.module, name) for name in _NEEDED)
    ]


def report(bind, modules: Optional[list] = None) -> list:
    """The lines each pending migration would log, in upgrade order. Writes nothing."""
    if modules is None:
        modules = pending_migrations(current_revision(bind))
    lines = []
    state = {}
    for module in modules:
        # Rows an earlier migration has already projected win over the database's.
        state = {**module.read_state(bind), **state}
        planned = module.plan(state)
        lines.extend(line for _level, line in module.report_lines(planned))
        state = module.project(state, planned)
    return lines


@contextmanager
def read_only_connection(engine):
    """A connection whose one transaction cannot write, rolled back at the end."""
    with engine.connect() as bind:
        bind.execute(sa.text("SET TRANSACTION READ ONLY"))
        try:
            yield bind
        finally:
            bind.rollback()


def main(argv: Optional[list] = None) -> int:
    """Print the report for the configured database."""
    from app.core.config import settings

    engine = sa.create_engine(settings.database_url)
    try:
        with read_only_connection(engine) as bind:
            revision = current_revision(bind)
            try:
                modules = pending_migrations(revision)
            except Exception as error:  # alembic raises its own types for an unknown revision
                print(f"This database is at revision {revision}, which this version of FilaOps "
                      f"does not know: {error}")
                return 1
            print("FilaOps unit preflight")
            print(f"Database revision: {revision or 'never migrated'}")
            if not modules:
                print("No pending migration has a unit report. Nothing to do.")
                return 0
            print("Reporting on: " + ", ".join(str(module.revision) for module in modules))
            print()
            for line in report(bind, modules):
                print(line)
            print()
            print("Nothing was changed.")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
