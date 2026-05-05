"""Tests for get_install_uuid concurrency safety (cortex_observe #51).

Pre-fix: ``get_install_uuid`` did a check-then-write — two concurrent first
callers could both see the file missing and each generate a different UUID,
then one ``os.replace`` would silently clobber the other. Under PR-05's
encryption-at-rest, that means ciphertext written by the loser becomes
permanently undecryptable once the winner's UUID survives on disk.

Post-fix: the file is created with ``O_CREAT | O_EXCL`` so the kernel
serializes the create. Only one caller's create succeeds; concurrent
callers see ``FileExistsError`` and read back the winner's UUID.
"""
from __future__ import annotations

import os
import stat
import sys
import threading
import uuid as uuid_module

import pytest

from app.core import license_cache
from app.core.config import settings


@pytest.fixture(autouse=True)
def _isolated_config_dir(monkeypatch, tmp_path):
    """Each test gets a fresh LICENSE_CONFIG_DIR so install_uuid starts clean."""
    monkeypatch.setattr(
        settings, "LICENSE_CONFIG_DIR", str(tmp_path), raising=False
    )
    yield tmp_path


def _uuid_path() -> str:
    return os.path.join(
        settings.LICENSE_CONFIG_DIR, license_cache.INSTALL_UUID_FILENAME
    )


def test_first_call_creates_file_and_returns_uuid(tmp_path):
    """Cold start — the file does not exist, function generates and persists."""
    path = _uuid_path()
    assert not os.path.exists(path)

    result = license_cache.get_install_uuid()

    assert result, "expected a non-empty UUID string"
    # Must be a parseable UUID4 string
    parsed = uuid_module.UUID(result)
    assert parsed.version == 4

    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as fh:
        on_disk = fh.read().strip()
    assert on_disk == result


def test_second_call_returns_same_uuid():
    """Idempotent — once written, every subsequent call reads the same value."""
    first = license_cache.get_install_uuid()
    second = license_cache.get_install_uuid()
    third = license_cache.get_install_uuid()

    assert first == second == third


def test_concurrent_callers_all_observe_same_uuid():
    """The race test.

    Spawn N threads, gate them all at a barrier so they unblock together,
    and verify every thread observes the same UUID. Pre-fix, this fails
    intermittently because threads racing past the barrier can each see
    the file missing and each generate a distinct UUID before any of them
    finishes writing. Post-fix, the O_EXCL create lets exactly one writer
    succeed; the others read back the winner's value.
    """
    n_threads = 16
    barrier = threading.Barrier(n_threads)
    results: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        try:
            # Wait at the barrier so all threads unblock simultaneously,
            # maximising overlap on the create call.
            barrier.wait(timeout=10)
            value = license_cache.get_install_uuid()
            with lock:
                results.append(value)
        except BaseException as exc:  # noqa: BLE001 — capture for assertion
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"worker(s) raised: {errors!r}"
    assert len(results) == n_threads
    assert len(set(results)) == 1, (
        f"race detected — threads observed {len(set(results))} distinct UUIDs: "
        f"{set(results)!r}"
    )

    # And the file on disk must equal what every caller saw.
    with open(_uuid_path(), "r", encoding="utf-8") as fh:
        on_disk = fh.read().strip()
    assert on_disk == results[0]


def test_empty_file_triggers_regeneration():
    """A pre-existing empty file (corruption-by-truncation) is regenerated.

    Without this, the encrypted-at-rest path would be left without a key
    source and every Fernet derive would raise.
    """
    path = _uuid_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Create the file but leave it empty.
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("")
    assert os.path.exists(path)
    assert os.path.getsize(path) == 0

    result = license_cache.get_install_uuid()

    assert result, "expected a non-empty UUID after regeneration"
    uuid_module.UUID(result)  # parses as a real UUID
    with open(path, "r", encoding="utf-8") as fh:
        on_disk = fh.read().strip()
    assert on_disk == result, "regenerated UUID must be persisted to disk"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX permission bits are not enforced on Windows; O_EXCL still applies but mode is ignored",
)
def test_file_permissions_are_0o600():
    """The UUID file is created with mode 0o600 (owner read/write only).

    The file holds a value that derives the encryption key for any data
    encrypted with EncryptedString. Even though defense-in-depth says the
    container's filesystem ACLs should already restrict it, the explicit
    mode bit is cheap and documents intent.
    """
    license_cache.get_install_uuid()
    mode = stat.S_IMODE(os.stat(_uuid_path()).st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
