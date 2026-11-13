"""
Unit preflight: what the pending unit migrations will do to this database.

Run it with the NEW version's code against the database BEFORE it is upgraded.
It changes nothing. It prints what each pending migration would report: the
units it would add or correct, the unit codes it would rewrite, and every item
or line it would leave for you to look at.

Manual install, from the ``backend`` folder, before ``alembic upgrade head``:

    python scripts/uom_preflight.py

Docker install, after fetching the new version and before ``docker compose up``
(which upgrades the database as it starts):

    docker compose build migrate
    docker compose run --rm --no-deps migrate python scripts/uom_preflight.py

It reads the same database settings as the application. The database has to be
on the last revision of the previous release first; the script says so if it
is older.

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
from typing import Any, NamedTuple, Optional

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import sqlalchemy as sa  # noqa: E402
from alembic.config import Config  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from alembic.script.revision import RevisionError  # noqa: E402
from alembic.util import CommandError  # noqa: E402

_NEEDED = ("read_state", "plan", "project", "report_lines")


class Step(NamedTuple):
    """A migration still to run, and whether it can be reported on."""
    revision: str
    module: Any
    reportable: bool


def current_revisions(bind) -> list:
    """The migration revisions the database records. Empty when it has never been migrated."""
    if not sa.inspect(bind).has_table("alembic_version"):
        return []
    return [row[0] for row in bind.execute(sa.text("SELECT version_num FROM alembic_version"))]


def pending_steps(revision: Optional[str]) -> list:
    """Every migration newer than ``revision``, oldest first."""
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    script = ScriptDirectory.from_config(config)
    newer = list(script.iterate_revisions("heads", revision or "base"))
    return [
        Step(str(step.revision), step.module, all(hasattr(step.module, name) for name in _NEEDED))
        for step in reversed(newer)
    ]


def _merge(fresh: dict, projected: dict) -> dict:
    """A migration's own read, with the rows the earlier migrations would leave laid over it.

    Rows are matched by id. A row an earlier migration would add has no id yet
    and is carried over as it is. Columns and rows that only this migration
    reads are kept.
    """
    merged = dict(fresh)
    for key, rows in projected.items():
        if key not in fresh:
            merged[key] = rows
            continue
        own = {row["id"]: row for row in fresh[key] if row.get("id") is not None}
        laid_over, seen = [], set()
        for row in rows:
            row_id = row.get("id")
            if row_id is None:
                laid_over.append(row)
            elif row_id in own:
                laid_over.append({**own[row_id], **row})
                seen.add(row_id)
        laid_over.extend(row for row_id, row in own.items() if row_id not in seen)
        merged[key] = laid_over
    return merged


def report(bind, modules: list) -> list:
    """The lines each migration would log, in the order given. Writes nothing."""
    lines = []
    state = {}
    for module in modules:
        state = _merge(module.read_state(bind), state)
        planned = module.plan(state)
        lines.extend(line for _level, line in module.report_lines(planned))
        state = module.project(state, planned)
    return lines


def run(bind, out=print) -> int:
    """Print the report for the database behind ``bind``. Returns the exit code."""
    revisions = current_revisions(bind)
    if len(revisions) > 1:
        out("This database records more than one migration revision (%s). "
            "Finish its upgrade before running this report." % ", ".join(revisions))
        return 1
    revision = revisions[0] if revisions else None
    try:
        steps = pending_steps(revision)
    except (CommandError, RevisionError) as error:
        out(f"This database is at revision {revision}, which this version of FilaOps does not know: {error}")
        return 1

    out("FilaOps unit preflight")
    out(f"Database revision: {revision or 'never migrated'}")
    reportable = [step for step in steps if step.reportable]
    if not reportable:
        out("No pending migration has a unit report. Nothing to do.")
        return 0

    first = steps.index(reportable[0])
    if first > 0:
        out(
            f"This database still has {first} older migration(s) to run before the first one this report "
            f"covers ({reportable[0].revision}). Upgrade it to revision {steps[first - 1].revision} first, "
            f"then run this report again."
        )
        return 1

    out("Reporting on: " + ", ".join(step.revision for step in reportable))
    unreported = [step.revision for step in steps if not step.reportable]
    if unreported:
        out("Also pending, with nothing to report: " + ", ".join(unreported))
    out("")
    try:
        lines = report(bind, [step.module for step in reportable])
    except sa.exc.SQLAlchemyError as error:
        out(f"The report could not read this database ({type(error).__name__}). Nothing was changed.")
        out(str(error).splitlines()[0])
        return 1
    for line in lines:
        out(line)
    out("")
    out("Nothing was changed.")
    return 0


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
            return run(bind)
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
