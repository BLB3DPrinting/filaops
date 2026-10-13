"""
In-process scheduler for database backups.

Once a minute it asks ``database_backup.is_due`` whether today's scheduled
backup still has to run, and starts it if so. The dump runs on its own
thread, so the event loop never waits on pg_dump. With several backend
processes, every one may tick; the advisory lock in ``start_backup`` lets only
one of them run the backup, and the others see it recorded and skip.

Set ``BACKUP_SCHEDULER_ENABLED=false`` to keep this process from scheduling
(for example when backups are scheduled outside FilaOps).
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone
from typing import Optional

from app.logging_config import get_logger
from app.services import database_backup

logger = get_logger(__name__)

TICK_SECONDS = 60
# Let startup (migrations, plugin load) settle before the first check.
INITIAL_DELAY_SECONDS = 30


def tick(now: Optional[datetime] = None) -> Optional[int]:
    """Start the scheduled backup if it is due; return its run id or None."""
    from app.db.session import SessionLocal

    current = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        if not database_backup.is_due(db, current, database_backup.get_backup_settings(db)):
            return None
    try:
        run_id = database_backup.start_backup("scheduled")
    except database_backup.BackupAlreadyRunning:
        return None
    if run_id is not None:
        logger.info("Scheduled database backup started", extra={"backup_run_id": run_id})
    return run_id


async def _loop(stop: asyncio.Event) -> None:
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(stop.wait(), INITIAL_DELAY_SECONDS)
    while not stop.is_set():
        try:
            await asyncio.to_thread(tick)
        except Exception:  # noqa: BLE001 — one bad tick must not end scheduling
            logger.exception("Backup scheduler tick failed")
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), TICK_SECONDS)


class BackupScheduler:
    """Owns the scheduler task for the app's lifespan."""

    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._task = asyncio.create_task(_loop(self._stop), name="backup-scheduler")
        logger.info("Backup scheduler started")

    async def stop(self) -> None:
        # A backup already running is left to finish on its daemon thread; if
        # the process exits first, the next status check records it as
        # interrupted and its partial file is cleaned up later.
        self._stop.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
