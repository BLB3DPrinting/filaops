"""
Shop-wide serial-number prefix: validation, generation, and migration 104.

Generation is covered for the neutral default (SN-), a shop's own prefix,
and the legacy BLB- prefix that existing installs keep. The migration's data
step is imported straight from the migration file and run against the test
transaction, for a database with and without BLB- serials.
"""
import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.company_settings import CompanySettings
from app.models.production_order import ProductionOrder
from app.models.traceability import SerialNumber
from app.schemas.traceability import SerialNumberCreate
from app.services import traceability_service
from app.services.serial_prefix import (
    DEFAULT_SERIAL_PREFIX,
    MAX_SERIAL_PREFIX_LENGTH,
    get_serial_prefix,
    normalize_serial_prefix,
)


def _uid():
    return uuid.uuid4().hex[:8]


def _today():
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _set_prefix(db, value):
    """Put the Company Settings row into a known state for this test."""
    settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if settings is None:
        settings = CompanySettings(id=1)
        db.add(settings)
    db.flush()
    # Raw UPDATE: on a new row the ORM would swap None for its "SN-" default.
    db.execute(
        text("UPDATE company_settings SET serial_number_prefix = :v WHERE id = 1"),
        {"v": value},
    )
    db.expire_all()


def _production_order(db, make_product):
    product = make_product(item_type="finished_good")
    po = ProductionOrder(
        code=f"MO-SN-{_uid()}",
        product_id=product.id,
        quantity_ordered=5,
        status="in_progress",
        source="manual",
    )
    db.add(po)
    db.flush()
    return product, po


def _existing_serial(db, product, po, serial):
    db.add(SerialNumber(
        serial_number=serial,
        product_id=product.id,
        production_order_id=po.id,
        status="manufactured",
        manufactured_at=datetime.now(timezone.utc),
    ))
    db.flush()


def _generate(db, product, po, quantity=2):
    return [
        s.serial_number
        for s in traceability_service.create_serial_numbers(
            db,
            SerialNumberCreate(
                product_id=product.id, production_order_id=po.id, quantity=quantity
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestNormalizeSerialPrefix:
    @pytest.mark.parametrize("raw, expected", [
        ("SN-", "SN-"),
        ("SN", "SN-"),
        ("  acme  ", "acme-"),
        ("BLB-", "BLB-"),
        ("JOES-PS", "JOES-PS-"),
        ("A1", "A1-"),
        ("X" * (MAX_SERIAL_PREFIX_LENGTH - 1), "X" * (MAX_SERIAL_PREFIX_LENGTH - 1) + "-"),
    ])
    def test_valid_prefixes(self, raw, expected):
        assert normalize_serial_prefix(raw) == expected

    @pytest.mark.parametrize("raw", [
        None,
        "",
        "   ",
        "-SN",
        "SN_",
        "SN 1",
        "SN%",
        "S/N",
        "ÄBC",
        "X" * MAX_SERIAL_PREFIX_LENGTH,  # too long once the dash is added
    ])
    def test_invalid_prefixes(self, raw):
        with pytest.raises(ValueError):
            normalize_serial_prefix(raw)


class TestGetSerialPrefix:
    def test_unset_value_uses_neutral_default(self, db):
        _set_prefix(db, None)
        assert get_serial_prefix(db) == DEFAULT_SERIAL_PREFIX == "SN-"

    def test_missing_row_uses_neutral_default(self, db):
        db.execute(text("DELETE FROM company_settings"))
        assert get_serial_prefix(db) == "SN-"

    def test_configured_value_is_used(self, db):
        _set_prefix(db, "ACME-")
        assert get_serial_prefix(db) == "ACME-"

    def test_invalid_stored_value_never_reaches_a_serial(self, db):
        _set_prefix(db, "BAD PREFIX%")
        assert get_serial_prefix(db) == "SN-"

    def test_new_settings_row_defaults_to_neutral_prefix(self, db):
        db.execute(text("DELETE FROM company_settings"))
        settings = CompanySettings(id=1)
        db.add(settings)
        db.flush()
        assert settings.serial_number_prefix == "SN-"


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

class TestSerialGeneration:
    def test_default_prefix(self, db, make_product):
        _set_prefix(db, None)
        product, po = _production_order(db, make_product)
        serials = _generate(db, product, po)
        stem = f"SN-{_today()}-"
        assert all(s.startswith(stem) for s in serials)
        assert [int(s[len(stem):]) for s in serials] == [1, 2]

    def test_custom_prefix(self, db, make_product):
        _set_prefix(db, "JOES-")
        product, po = _production_order(db, make_product)
        assert _generate(db, product, po, quantity=1) == [f"JOES-{_today()}-0001"]

    def test_legacy_prefix_continues_existing_sequence(self, db, make_product):
        _set_prefix(db, "BLB-")
        product, po = _production_order(db, make_product)
        _existing_serial(db, product, po, f"BLB-{_today()}-0007")
        assert _generate(db, product, po) == [
            f"BLB-{_today()}-0008",
            f"BLB-{_today()}-0009",
        ]

    def test_sequence_is_per_prefix(self, db, make_product):
        """Changing the prefix starts a fresh sequence; old serials stay put."""
        product, po = _production_order(db, make_product)
        old = f"BLB-{_today()}-0042"
        _existing_serial(db, product, po, old)
        _set_prefix(db, "SN-")
        assert _generate(db, product, po, quantity=1) == [f"SN-{_today()}-0001"]
        assert db.query(SerialNumber).filter(SerialNumber.serial_number == old).count() == 1

    def test_non_numeric_tail_is_ignored(self, db, make_product):
        _set_prefix(db, "SN-")
        product, po = _production_order(db, make_product)
        _existing_serial(db, product, po, f"SN-{_today()}-0003")
        _existing_serial(db, product, po, f"SN-{_today()}-SPARE")
        assert _generate(db, product, po, quantity=1) == [f"SN-{_today()}-0004"]

    def test_tail_beyond_int32_does_not_overflow(self, db, make_product):
        """A stored tail past PostgreSQL's INTEGER range still sequences on."""
        _set_prefix(db, "SN-")
        product, po = _production_order(db, make_product)
        _existing_serial(db, product, po, f"SN-{_today()}-2147483648")
        assert _generate(db, product, po, quantity=1) == [f"SN-{_today()}-2147483649"]

    def test_generate_serial_stem(self):
        when = datetime(2026, 10, 13, tzinfo=timezone.utc)
        assert SerialNumber.generate_serial("ACME-", when) == "ACME-20261013-"


# ---------------------------------------------------------------------------
# Migration 104 data step
# ---------------------------------------------------------------------------

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations" / "versions" / "104_company_serial_number_prefix.py"
)


@pytest.fixture(scope="module")
def migration_104():
    spec = importlib.util.spec_from_file_location("migration_104", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _clear_blb_serials(db):
    db.execute(text(
        "DELETE FROM production_lot_consumptions WHERE serial_number_id IN "
        "(SELECT id FROM serial_numbers WHERE serial_number LIKE 'BLB-%')"
    ))
    db.execute(text("DELETE FROM serial_numbers WHERE serial_number LIKE 'BLB-%'"))


def _stored_prefix(db):
    return db.execute(
        text("SELECT serial_number_prefix FROM company_settings WHERE id = 1")
    ).scalar()


class TestMigration104:
    def test_revision_chain(self, migration_104):
        assert migration_104.revision == "104"
        assert migration_104.down_revision == "102"

    def test_install_without_blb_serials_gets_neutral_default(
        self, db, migration_104
    ):
        _clear_blb_serials(db)
        _set_prefix(db, None)
        assert migration_104.backfill_serial_prefix(db.connection()) == "SN-"
        assert _stored_prefix(db) == "SN-"

    def test_install_with_blb_serials_keeps_blb(self, db, make_product, migration_104):
        _set_prefix(db, None)
        product, po = _production_order(db, make_product)
        _existing_serial(db, product, po, "BLB-20251205-0001")
        assert migration_104.backfill_serial_prefix(db.connection()) == "BLB-"
        assert _stored_prefix(db) == "BLB-"
        # The existing serial is untouched.
        assert db.query(SerialNumber).filter(
            SerialNumber.serial_number == "BLB-20251205-0001"
        ).count() == 1

    def test_blb_install_then_generates_blb_serials(
        self, db, make_product, migration_104
    ):
        _set_prefix(db, None)
        product, po = _production_order(db, make_product)
        _existing_serial(db, product, po, f"BLB-{_today()}-0003")
        migration_104.backfill_serial_prefix(db.connection())
        db.expire_all()
        assert _generate(db, product, po, quantity=1) == [f"BLB-{_today()}-0004"]

    def test_existing_value_is_never_overwritten(self, db, make_product, migration_104):
        _set_prefix(db, "ACME-")
        product, po = _production_order(db, make_product)
        _existing_serial(db, product, po, "BLB-20251205-0001")
        assert migration_104.backfill_serial_prefix(db.connection()) is None
        assert _stored_prefix(db) == "ACME-"

    def test_rerun_is_a_no_op(self, db, migration_104):
        _clear_blb_serials(db)
        _set_prefix(db, None)
        migration_104.backfill_serial_prefix(db.connection())
        assert migration_104.backfill_serial_prefix(db.connection()) is None
        assert _stored_prefix(db) == "SN-"

    def test_blb_serials_but_no_settings_row_creates_row(
        self, db, make_product, migration_104
    ):
        product, po = _production_order(db, make_product)
        _existing_serial(db, product, po, "BLB-20251205-0001")
        db.execute(text("DELETE FROM company_settings"))
        assert migration_104.backfill_serial_prefix(db.connection()) == "BLB-"
        assert _stored_prefix(db) == "BLB-"
        db.expire_all()
        assert get_serial_prefix(db) == "BLB-"

    def test_fresh_install_creates_nothing(self, db, migration_104):
        _clear_blb_serials(db)
        db.execute(text("DELETE FROM company_settings"))
        assert migration_104.backfill_serial_prefix(db.connection()) is None
        assert db.execute(text("SELECT COUNT(*) FROM company_settings")).scalar() == 0
