"""
Deterministic time + RNG + Faker helpers for seed_demo.

Call `initialize(seed)` once at the top of the seed run. All modules
then call `now()`, `rng()`, `fake()`, `days_ago(n)` to get values that
are stable across re-runs with the same seed.

NOW is frozen to today's UTC midnight, so two runs on the same UTC day
produce identical row state. For strict cross-day determinism in tests,
set FILAOPS_DEMO_NOW_ISO (e.g. "2026-04-17T00:00:00+00:00").
"""
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

try:
    from faker import Faker
except ImportError as e:
    raise SystemExit(
        "faker is required for seed_demo. Install with: "
        "pip install -r requirements-dev.txt"
    ) from e


_NOW: Optional[datetime] = None
_RNG: Optional[random.Random] = None
_FAKE: Optional[Faker] = None


def initialize(seed: int) -> None:
    global _NOW, _RNG, _FAKE

    now_override = os.environ.get("FILAOPS_DEMO_NOW_ISO")
    if now_override:
        _NOW = datetime.fromisoformat(now_override)
    else:
        _NOW = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0,
        )

    _RNG = random.Random(seed)
    _FAKE = Faker("en_US")
    _FAKE.seed_instance(seed)


def now() -> datetime:
    if _NOW is None:
        raise RuntimeError("_time.initialize() not called before now()")
    return _NOW


def rng() -> random.Random:
    if _RNG is None:
        raise RuntimeError("_time.initialize() not called before rng()")
    return _RNG


def fake() -> Faker:
    if _FAKE is None:
        raise RuntimeError("_time.initialize() not called before fake()")
    return _FAKE


def days_ago(n: int) -> datetime:
    return now() - timedelta(days=n)


def random_day_in_last(days: int) -> datetime:
    """Uniform random day within the last `days` days (inclusive)."""
    return days_ago(rng().randint(0, days))
