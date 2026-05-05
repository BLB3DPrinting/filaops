"""
Tests for app.core.crypto — Fernet+HKDF token encryption foundation (PR-05).

Coverage:
- encrypt_token / decrypt_token round-trip
- Empty string and None passthrough
- Different install_uuid produces different ciphertext (key isolation)
- decrypt_token gracefully handles corrupted ciphertext
- EncryptedString TypeDecorator: encrypt-on-write, decrypt-on-read via SQLAlchemy
- EncryptedString migration grace: plaintext value reads back as plaintext
"""
import logging

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, insert, select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.crypto import (
    EncryptedString,
    _TOKEN_ENCRYPTION_INFO,
    _derive_key,
    decrypt_token,
    encrypt_token,
)
from app.core.settings import settings


@pytest.fixture(autouse=True)
def _isolated_install_uuid(monkeypatch, tmp_path):
    """Each test gets a fresh LICENSE_CONFIG_DIR so install_uuid is regenerated.

    Without this, all tests would share the host's persistent install_uuid,
    making 'different uuid produces different ciphertext' impossible to
    verify and leaking encryption state between test runs.
    """
    monkeypatch.setattr(
        settings, "LICENSE_CONFIG_DIR", str(tmp_path), raising=False
    )
    yield tmp_path


# ---------------------------------------------------------------------------
# encrypt_token / decrypt_token
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_round_trip():
    """Round-trip: plaintext → ciphertext → plaintext."""
    plaintext = "sk-ant-api-key-supersecret"
    ciphertext = encrypt_token(plaintext)

    assert ciphertext != plaintext
    assert decrypt_token(ciphertext) == plaintext


def test_encrypt_token_returns_different_ciphertext_each_call():
    """Fernet includes a random IV → same plaintext encrypts to different ciphertext."""
    plaintext = "hello"
    c1 = encrypt_token(plaintext)
    c2 = encrypt_token(plaintext)

    assert c1 != c2
    assert decrypt_token(c1) == plaintext
    assert decrypt_token(c2) == plaintext


def test_encrypt_empty_string_passthrough():
    """encrypt_token('') returns '' — falsy values bypass Fernet."""
    assert encrypt_token("") == ""


def test_encrypt_none_passthrough():
    """encrypt_token(None) returns None — falsy values bypass Fernet."""
    assert encrypt_token(None) is None


def test_decrypt_empty_string_passthrough():
    assert decrypt_token("") == ""


def test_decrypt_none_passthrough():
    assert decrypt_token(None) is None


def test_decrypt_unicode_round_trip():
    """Non-ASCII plaintext survives encrypt → decrypt."""
    plaintext = "café-token-™-日本語"
    ciphertext = encrypt_token(plaintext)
    assert decrypt_token(ciphertext) == plaintext


# ---------------------------------------------------------------------------
# Key derivation isolation
# ---------------------------------------------------------------------------


def test_different_install_uuid_produces_different_ciphertext(monkeypatch):
    """Key isolation — changing install_uuid changes the derived Fernet key,
    so a token encrypted under one UUID cannot be decrypted under another.

    NOTE: crypto.py does `from app.core.license_cache import get_install_uuid`
    at import time, binding the name into the crypto module's namespace.
    Monkeypatching license_cache.get_install_uuid does NOT affect crypto's
    bound reference — we have to patch crypto.get_install_uuid directly.
    """
    plaintext = "shared-plaintext"

    monkeypatch.setattr(crypto, "get_install_uuid", lambda: "uuid-a" * 4)
    ciphertext_a = encrypt_token(plaintext)
    key_a = _derive_key()

    monkeypatch.setattr(crypto, "get_install_uuid", lambda: "uuid-b" * 4)
    ciphertext_b = encrypt_token(plaintext)
    key_b = _derive_key()

    assert key_a != key_b
    assert ciphertext_a != ciphertext_b

    # And ciphertext_a cannot be decrypted under key_b — raw decrypt_token
    # raises InvalidToken (the EncryptedString TypeDecorator is what swallows
    # this for migration grace, not the bare function).
    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        decrypt_token(ciphertext_a)  # current key is uuid-b, ciphertext was uuid-a


def test_derive_key_raises_when_install_uuid_missing(monkeypatch):
    """If install_uuid resolves empty, _derive_key raises with a clear message."""
    monkeypatch.setattr(crypto, "get_install_uuid", lambda: "")
    with pytest.raises(RuntimeError, match="install_uuid not available"):
        _derive_key()


def test_derive_key_uses_domain_separation_constant():
    """Sanity-check: the info parameter that gives us key isolation across
    encryption contexts is the documented constant. Future PRs that add a
    second context (e.g. backup encryption) must use a different `info`."""
    assert _TOKEN_ENCRYPTION_INFO == b"filaops-token-encryption-v1"


# ---------------------------------------------------------------------------
# Corrupted / plaintext input handling
# ---------------------------------------------------------------------------


def test_decrypt_corrupted_ciphertext_raises():
    """Raw decrypt_token raises InvalidToken on garbage — the EncryptedString
    type decorator is what swallows this for migration grace, not the bare
    function."""
    from cryptography.fernet import InvalidToken

    with pytest.raises(InvalidToken):
        decrypt_token("not-a-real-fernet-token")


# ---------------------------------------------------------------------------
# EncryptedString TypeDecorator (SQLAlchemy round-trip)
# ---------------------------------------------------------------------------


@pytest.fixture
def sqlite_engine():
    """In-memory SQLite engine + a single test table with one EncryptedString column.

    Using SQLite (not the shared filaops_test PG) keeps the test self-contained
    and avoids leaking a junk table into the dev DB.
    """
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    table = Table(
        "secrets_test",
        metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("token", EncryptedString, nullable=True),
    )
    metadata.create_all(engine)
    return engine, table


def test_encrypted_string_round_trip(sqlite_engine):
    """INSERT plaintext → DB stores ciphertext → SELECT returns plaintext."""
    engine, table = sqlite_engine
    plaintext = "sk-ant-roundtrip-12345"

    with Session(engine) as session:
        session.execute(insert(table).values(token=plaintext))
        session.commit()

        # Read back through ORM/Core — TypeDecorator decrypts
        row = session.execute(select(table.c.token)).scalar_one()
        assert row == plaintext

    # Read raw column bypassing the type decorator: should be ciphertext.
    # Underlying impl is now Text, so the raw view types it as plain Text too.
    from sqlalchemy import Text as _PlainText

    raw_meta = MetaData()
    raw_table = Table(
        "secrets_test",
        raw_meta,
        Column("id", Integer, primary_key=True),
        Column("token", _PlainText()),
    )
    with engine.connect() as conn:
        raw = conn.execute(select(raw_table.c.token)).scalar_one()
        assert raw != plaintext
        assert raw.startswith("gAAAAA")  # Fernet token signature


def test_encrypted_string_handles_long_plaintext(sqlite_engine):
    """Text-backed impl accepts long plaintext that VARCHAR(500) wouldn't fit
    after Fernet expansion. Guards against the PR-05 sizing-trap regression
    flagged by reviewers."""
    engine, table = sqlite_engine
    # 1500 chars — would produce ~2300+ bytes of Fernet ciphertext, well past
    # any reasonable VARCHAR cap.
    plaintext = "x" * 1500

    with Session(engine) as session:
        session.execute(insert(table).values(token=plaintext))
        session.commit()
        assert session.execute(select(table.c.token)).scalar_one() == plaintext


def test_encrypted_string_none_passthrough(sqlite_engine):
    """NULL stays NULL through the TypeDecorator — no encryption attempt."""
    engine, table = sqlite_engine
    with Session(engine) as session:
        session.execute(insert(table).values(token=None))
        session.commit()
        row = session.execute(select(table.c.token)).scalar_one()
        assert row is None


def test_encrypted_string_empty_string_passthrough(sqlite_engine):
    """Empty string stays empty — no encryption attempt."""
    engine, table = sqlite_engine
    with Session(engine) as session:
        session.execute(insert(table).values(token=""))
        session.commit()
        row = session.execute(select(table.c.token)).scalar_one()
        assert row == ""


def _seed_raw(engine, value):
    """Insert *value* into the test table bypassing the TypeDecorator.

    Used to simulate two distinct corruption modes: legacy plaintext (which
    won't have a Fernet prefix) and Fernet-shaped-but-undecryptable (which
    will, but won't decode under the active key)."""
    from sqlalchemy import Text as _PlainText

    raw_meta = MetaData()
    raw_table = Table(
        "secrets_test",
        raw_meta,
        Column("id", Integer, primary_key=True),
        Column("token", _PlainText()),
    )
    with engine.connect() as conn:
        conn.execute(insert(raw_table).values(token=value))
        conn.commit()


def test_encrypted_string_migration_grace_plaintext(sqlite_engine, caplog):
    """Migration grace: a row that contains legacy plaintext (no Fernet
    prefix) must read back as the raw value with a warning. The next save
    will re-encrypt it."""
    engine, table = sqlite_engine
    legacy_plaintext = "legacy-plaintext-api-key"  # no "gAAAAA" prefix
    _seed_raw(engine, legacy_plaintext)

    with caplog.at_level(logging.WARNING, logger="app.core.crypto"):
        with Session(engine) as session:
            row = session.execute(select(table.c.token)).scalar_one()

    assert row == legacy_plaintext
    assert any(
        "lacks Fernet prefix" in rec.message for rec in caplog.records
    ), "expected a migration-grace warning to be logged"


def test_encrypted_string_corrupted_fernet_returns_none(sqlite_engine, caplog):
    """A Fernet-shaped value that fails to decrypt (corrupted ciphertext,
    install_uuid drift) must NOT be returned as raw — that would hand the
    application a ciphertext blob masquerading as a plaintext key. Return
    None and log an error instead, so the app surfaces "not configured"
    rather than misuse the value. This is the behavior change requested by
    PR-05 review."""
    engine, table = sqlite_engine
    # Looks like a Fernet token (right prefix) but the body is junk.
    fake_fernet = "gAAAAAabc-not-real-ciphertext-but-prefix-matches"
    _seed_raw(engine, fake_fernet)

    with caplog.at_level(logging.ERROR, logger="app.core.crypto"):
        with Session(engine) as session:
            row = session.execute(select(table.c.token)).scalar_one()

    assert row is None, "corrupted Fernet ciphertext should NOT be returned raw"
    assert any(
        "failed to decrypt" in rec.message for rec in caplog.records
    ), "expected an error log for Fernet-shaped-but-undecryptable input"


def test_encrypted_string_propagates_install_uuid_missing(
    sqlite_engine, monkeypatch
):
    """If install_uuid is unavailable at read time, _derive_key raises
    RuntimeError. The TypeDecorator must NOT swallow it — operational
    failures need to be loud, not masked as 'not configured'."""
    engine, table = sqlite_engine

    # First, write a real Fernet token under the normal install_uuid.
    plaintext = "configured-key"
    with Session(engine) as session:
        session.execute(insert(table).values(token=plaintext))
        session.commit()

    # Now break the install_uuid resolution and try to read.
    monkeypatch.setattr(crypto, "get_install_uuid", lambda: "")
    with pytest.raises(RuntimeError, match="install_uuid not available"):
        with Session(engine) as session:
            session.execute(select(table.c.token)).scalar_one()


def test_encrypted_string_overwrite_re_encrypts(sqlite_engine):
    """Writing a new value to a row that previously held plaintext stores
    proper ciphertext on the next save — confirming the migration completes
    naturally on the next user save."""
    engine, table = sqlite_engine

    from sqlalchemy import Text as _PlainText, update

    raw_meta = MetaData()
    raw_table = Table(
        "secrets_test",
        raw_meta,
        Column("id", Integer, primary_key=True),
        Column("token", _PlainText()),
    )

    # Seed plaintext directly
    with engine.connect() as conn:
        result = conn.execute(insert(raw_table).values(token="old-plaintext"))
        row_id = result.inserted_primary_key[0]
        conn.commit()

    # Update via the EncryptedString-typed table
    new_value = "freshly-encrypted-key"
    with Session(engine) as session:
        session.execute(
            update(table).where(table.c.id == row_id).values(token=new_value)
        )
        session.commit()

        # Read back through encrypted column → plaintext
        assert (
            session.execute(
                select(table.c.token).where(table.c.id == row_id)
            ).scalar_one()
            == new_value
        )

    # Read back raw → ciphertext, not plaintext
    with engine.connect() as conn:
        raw = conn.execute(
            select(raw_table.c.token).where(raw_table.c.id == row_id)
        ).scalar_one()
        assert raw != new_value
        assert raw.startswith("gAAAAA")
