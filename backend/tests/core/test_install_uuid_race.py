"""Tests for get_install_uuid concurrency safety (cortex_observe #51).

Pre-fix history: a check-then-write pattern let two cold-start callers
generate distinct UUIDs and silently clobber each other via os.replace.
A first-pass O_EXCL fix closed that, but reviewers (Copilot, CodeRabbit)
correctly identified two follow-on races:

  1. Read-after-create: between the winner's ``os.open(O_EXCL)`` and its
     ``os.write``, the file exists at size 0. A loser observing
     ``FileExistsError`` and reading immediately gets ``""``.
  2. Empty-file split-brain: a fast-path reader that sees the size-0
     window can interpret it as corruption and unlink the file —
     clobbering the winner before its write lands.

Final design: ``_await_uuid_content`` polls for non-empty content rather
than acting on a single ambiguous read. Cold-start losers wait for the
winner's write. Fast-path observers of an empty file wait too — and
only after a generous timeout does the function bail with a loud
``RuntimeError``. Silent regeneration is gone, because under PR-05's
encryption-at-rest it would invalidate the key any existing ciphertext
was sealed with.
"""
from __future__ import annotations

import os
import stat
import sys
import threading
import time
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


# ---------------------------------------------------------------------------
# Single-caller behavior
# ---------------------------------------------------------------------------


def test_first_call_creates_file_and_returns_uuid():
    """Cold start — the file does not exist, function generates and persists."""
    path = _uuid_path()
    assert not os.path.exists(path)

    result = license_cache.get_install_uuid()

    assert result, "expected a non-empty UUID string"
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


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_concurrent_callers_all_observe_same_uuid():
    """Cold-start race: 16 threads at a barrier, all returning the same UUID.

    Pre-fix this fails because losers of the O_EXCL race would either
    generate their own UUID (the original bug) or read an empty file
    (the read-after-create regression that survived the first fix).
    Post-fix, losers poll via ``_await_uuid_content`` and converge.
    """
    n_threads = 16
    barrier = threading.Barrier(n_threads)
    results: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker():
        try:
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
    assert "" not in results, (
        "loser observed empty file (read-after-create race not closed)"
    )
    assert len(set(results)) == 1, (
        f"race detected — threads observed {len(set(results))} distinct UUIDs: "
        f"{set(results)!r}"
    )

    with open(_uuid_path(), "r", encoding="utf-8") as fh:
        on_disk = fh.read().strip()
    assert on_disk == results[0]


def test_loser_polls_through_winners_write_window(monkeypatch):
    """Read-after-create: explicitly inflate the winner's open→write window
    and verify losers wait for the content rather than returning "".

    This is the deterministic version of the race the barrier test catches
    statistically. We monkeypatch ``os.write`` so the very first write
    (the winner's UUID payload) sleeps for a measurable period. During
    that sleep, several reader threads are launched; each must hit the
    ``FileExistsError`` branch and poll until the winner finishes,
    converging on the winner's UUID.
    """
    real_write = os.write
    write_started = threading.Event()
    written_once = threading.Event()
    delay_seconds = 0.2

    def slow_first_write(fd: int, data):
        # Only stall the install-UUID payload: a UUID4 encodes to exactly
        # 36 bytes and parses as UUID. Anything else (pytest output,
        # logging, etc.) passes through unmodified.
        if not written_once.is_set() and len(data) == 36:
            try:
                uuid_module.UUID(data.decode("utf-8"))
                is_uuid_payload = True
            except (ValueError, UnicodeDecodeError):
                is_uuid_payload = False
            if is_uuid_payload:
                write_started.set()
                time.sleep(delay_seconds)
                written_once.set()
        return real_write(fd, data)

    monkeypatch.setattr(os, "write", slow_first_write)

    n_callers = 7
    barrier = threading.Barrier(n_callers)
    results: list[str] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def caller():
        try:
            barrier.wait(timeout=10)
            value = license_cache.get_install_uuid()
            with lock:
                results.append(value)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    # All callers self-gate at the barrier; main thread only joins.
    threads = [threading.Thread(target=caller) for _ in range(n_callers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"worker(s) raised: {errors!r}"
    assert write_started.is_set(), "expected a winner to have entered os.write"
    assert "" not in results, (
        "a loser returned empty — _await_uuid_content did not wait for the "
        "winner's write to be visible"
    )
    assert len(set(results)) == 1, (
        f"split-brain: {len(set(results))} distinct UUIDs returned across "
        f"{n_callers} callers: {set(results)!r}"
    )


# ---------------------------------------------------------------------------
# Corruption / failure modes
# ---------------------------------------------------------------------------


def test_empty_file_raises_after_polling_corruption():
    """A pre-existing empty file (corruption-by-truncation) must NOT be
    silently regenerated — that would invalidate the key any encrypted-
    at-rest data was sealed with. Function polls briefly (in case it is
    actually a cold-start writer mid-write) and then raises clearly.

    The override on ``_AWAIT_UUID_TIMEOUT_SECONDS`` keeps the test fast.
    """
    path = _uuid_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("")

    # Patch the timeout to a tiny value so the test doesn't sit on the
    # real 5s default. Production behavior tested separately via
    # _await_uuid_content unit tests below.
    import unittest.mock as mock

    with mock.patch.object(license_cache, "_AWAIT_UUID_TIMEOUT_SECONDS", 0.05):
        with pytest.raises(RuntimeError, match="empty after polling"):
            license_cache.get_install_uuid()

    # File untouched — the function did not regenerate over the corruption.
    assert os.path.getsize(path) == 0


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX permission bits are not enforced on Windows",
)
def test_file_permissions_are_0o600():
    """The UUID file holds the seed for token encryption — restrict mode."""
    license_cache.get_install_uuid()
    mode = stat.S_IMODE(os.stat(_uuid_path()).st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# _await_uuid_content unit tests (the polling primitive itself)
# ---------------------------------------------------------------------------


def test_await_uuid_content_returns_value_when_present(tmp_path):
    """Direct unit test: returns the trimmed content immediately."""
    p = tmp_path / "u"
    p.write_text("  abc-123  \n", encoding="utf-8")
    assert license_cache._await_uuid_content(p, timeout_seconds=0.1) == "abc-123"


def test_await_uuid_content_returns_none_on_timeout(tmp_path):
    """Direct unit test: timeout returns None instead of raising."""
    p = tmp_path / "u"
    p.write_text("", encoding="utf-8")
    started = time.monotonic()
    result = license_cache._await_uuid_content(
        p, timeout_seconds=0.05, poll_seconds=0.005
    )
    elapsed = time.monotonic() - started
    assert result is None
    assert elapsed >= 0.05, f"polled for only {elapsed:.3f}s"


def test_await_uuid_content_picks_up_late_writer(tmp_path):
    """A delayed writer's content becomes visible mid-poll."""
    p = tmp_path / "u"
    p.write_text("", encoding="utf-8")
    expected = "deadbeef-cafe"

    def late_writer():
        time.sleep(0.05)
        p.write_text(expected, encoding="utf-8")

    threading.Thread(target=late_writer).start()

    result = license_cache._await_uuid_content(
        p, timeout_seconds=2.0, poll_seconds=0.005
    )
    assert result == expected
