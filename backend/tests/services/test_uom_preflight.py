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


class TestPendingMigrations:
    def test_106_is_pending_for_a_database_at_105(self, preflight):
        assert [module.revision for module in preflight.pending_migrations("105")][:1] == ["106"]

    def test_nothing_before_106_is_reported_on(self, preflight):
        revisions = [module.revision for module in preflight.pending_migrations(None)]
        assert revisions[0] == "106"

    def test_an_upgraded_database_has_nothing_pending_from_106(self, preflight):
        assert "106" not in [module.revision for module in preflight.pending_migrations("106")]


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
        _older_unit_table(db)
        item = make_product(unit="pcs")
        db.flush()
        seen = {}

        def plan(state):
            seen["unit"] = next(row["unit"] for row in state["items"] if row["id"] == item.id)
            seen["pound"] = next(row["to_base_factor"] for row in state["units"] if row["code"] == "LB")
            return {}

        later = SimpleNamespace(
            revision="later",
            read_state=migration_106.read_state,
            plan=plan,
            project=lambda state, planned: state,
            report_lines=lambda planned: [(20, "later: saw the projected rows")],
        )
        lines = preflight.report(db.connection(), [migration_106, later])

        assert seen == {"unit": "EA", "pound": D("0.45359237")}
        assert lines[-1] == "later: saw the projected rows"


class TestReadOnly:
    def test_a_write_inside_the_report_connection_fails(self, preflight):
        from app.db.session import engine

        with preflight.read_only_connection(engine) as bind:
            assert bind.execute(sa.text("SELECT 1")).scalar() == 1
            with pytest.raises(sa.exc.DBAPIError):
                bind.execute(sa.text("UPDATE units_of_measure SET name = name"))

    def test_the_script_runs_against_the_configured_database(self, preflight, capsys):
        assert preflight.main([]) == 0
        printed = capsys.readouterr().out
        assert "FilaOps unit preflight" in printed
        assert "Nothing was changed." in printed or "Nothing to do." in printed
