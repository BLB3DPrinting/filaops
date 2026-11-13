"""
scripts/uom_preflight.py: the report an install reads before it upgrades.

The script holds no checks of its own. It asks each pending migration for its
plan, and hands the rows that migration would leave to the next one.
"""
import importlib.util
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.models.uom import UnitOfMeasure

_BACKEND = Path(__file__).resolve().parents[2]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def preflight():
    return _load("uom_preflight", _BACKEND / "scripts" / "uom_preflight.py")


@pytest.fixture(scope="module")
def migration_106():
    return _load("migration_106", _BACKEND / "migrations" / "versions" / "106_unit_table_and_item_units.py")


def _older_unit_table(db):
    """Leave only a rounded pound in the unit table, as an older install might have."""
    db.query(UnitOfMeasure).delete()
    db.flush()
    kilo = UnitOfMeasure(code="KG", name="Kilogram", symbol="kg", uom_class="weight", to_base_factor=D("1"))
    db.add(kilo)
    db.flush()
    db.add(UnitOfMeasure(code="LB", name="Pound", symbol="lb", uom_class="weight",
                         base_unit_id=kilo.id, to_base_factor=D("0.453592")))
    db.flush()


def _run(preflight, db, monkeypatch, revisions):
    """Run the report as if the database recorded ``revisions``, and return (exit code, lines)."""
    monkeypatch.setattr(preflight, "current_revisions", lambda bind: list(revisions))
    lines = []
    return preflight.run(db.connection(), out=lines.append), lines


class TestPendingSteps:
    def test_106_is_the_first_step_for_a_database_at_105(self, preflight):
        first = preflight.pending_steps("105")[0]
        assert (first.revision, first.reportable) == ("106", True)

    def test_older_migrations_are_pending_but_not_reportable(self, preflight):
        steps = {step.revision: step.reportable for step in preflight.pending_steps("102")}
        assert steps["105"] is False and steps["106"] is True

    def test_an_upgraded_database_no_longer_has_106_pending(self, preflight):
        assert "106" not in [step.revision for step in preflight.pending_steps("106")]


class TestReport:
    def test_it_prints_what_the_migration_would_report(self, db, preflight, migration_106, make_product):
        _older_unit_table(db)
        make_product(unit="pcs")
        db.flush()
        bind = db.connection()

        lines = preflight.report(bind, [migration_106])

        planned = migration_106.plan(migration_106.read_state(bind))
        assert lines == [line for _level, line in migration_106.report_lines(planned)]
        assert any("LB factor made exact: 0.453592 -> 0.45359237" in line for line in lines)
        assert any("item unit code(s) 'pcs' rewritten as EA" in line for line in lines)

    def test_it_changes_nothing(self, db, preflight, migration_106, make_product):
        _older_unit_table(db)
        item = make_product(unit="pcs")
        db.flush()
        preflight.report(db.connection(), [migration_106])
        db.expire_all()
        assert item.unit == "pcs"
        pound = db.query(UnitOfMeasure).filter(UnitOfMeasure.code == "LB").one()
        assert D(str(pound.to_base_factor)) == D("0.453592")

    def test_a_later_migration_plans_from_what_the_earlier_one_leaves(self, db, preflight, migration_106,
                                                                     make_product):
        """The later migration reads a column and a row the earlier one does not."""
        _older_unit_table(db)
        tidied, untouched = make_product(unit="pcs"), make_product(unit="EA")
        db.flush()
        seen = {}

        def read_state(bind):
            return {"items": [
                {"id": tidied.id, "sku": tidied.sku, "unit": "pcs", "standard_cost": D("2")},
                {"id": -1, "sku": "ONLY-THE-LATER-READ", "unit": "EA", "standard_cost": D("3")},
            ]}

        def plan(state):
            seen["items"] = {row["id"]: row for row in state["items"]}
            seen["pound"] = next(row["to_base_factor"] for row in state["units"] if row["code"] == "LB")
            return {}

        later = SimpleNamespace(
            revision="later", read_state=read_state, plan=plan,
            project=lambda state, planned: state,
            report_lines=lambda planned: [(20, "later: saw the projected rows")],
        )
        lines = preflight.report(db.connection(), [migration_106, later])

        assert seen["items"][tidied.id]["unit"] == "EA"
        assert seen["items"][tidied.id]["standard_cost"] == D("2")
        assert seen["items"][-1]["sku"] == "ONLY-THE-LATER-READ"
        assert untouched.id not in seen["items"]
        assert seen["pound"] == D("0.45359237")
        assert lines[-1] == "later: saw the projected rows"


class TestRun:
    def test_a_database_at_105_gets_the_report(self, db, preflight, monkeypatch, make_product):
        _older_unit_table(db)
        make_product(unit="pcs")
        db.flush()
        code, lines = _run(preflight, db, monkeypatch, ["105"])
        assert code == 0
        assert "Reporting on: 106" in lines
        assert any("LB factor made exact" in line for line in lines)
        assert lines[-1] == "Nothing was changed."

    def test_an_older_database_is_told_to_upgrade_first(self, db, preflight, monkeypatch):
        code, lines = _run(preflight, db, monkeypatch, ["102"])
        assert code == 1
        assert any("Upgrade it to revision 105 first" in line for line in lines)
        assert not any(line.startswith("106:") for line in lines)

    def test_an_upgraded_database_has_nothing_to_report(self, db, preflight, monkeypatch):
        code, lines = _run(preflight, db, monkeypatch, ["106"])
        assert code == 0
        assert "No pending migration has a unit report. Nothing to do." in lines

    def test_an_unknown_revision_is_said_plainly(self, db, preflight, monkeypatch):
        code, lines = _run(preflight, db, monkeypatch, ["not-a-revision"])
        assert code == 1
        assert "does not know" in lines[0]

    def test_two_recorded_revisions_stop_the_report(self, db, preflight, monkeypatch):
        code, lines = _run(preflight, db, monkeypatch, ["105", "103"])
        assert code == 1
        assert "more than one migration revision" in lines[0]

    def test_it_reads_a_database_that_has_no_item_unit_table_yet(self, db, preflight, monkeypatch):
        """A database at 105 has no product_units table. The drop is rolled back with the test."""
        db.execute(sa.text("DROP TABLE product_units"))
        code, lines = _run(preflight, db, monkeypatch, ["105"])
        assert code == 0
        assert lines[-1] == "Nothing was changed."


class TestReadOnly:
    def test_a_write_inside_the_report_connection_fails(self, preflight):
        from app.db.session import engine

        with preflight.read_only_connection(engine) as bind:
            assert bind.execute(sa.text("SELECT 1")).scalar() == 1
            with pytest.raises(sa.exc.DBAPIError):
                bind.execute(sa.text("UPDATE units_of_measure SET name = name"))
