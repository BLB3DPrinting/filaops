"""Quality policy read-model — the QC rigor "dial" (#784 QMS).

The whole quality module is *selectable*: some shops do no formal QC, others run
regulated-grade inspection. This module resolves the company's chosen rigor from
the ``system_settings`` KV store into a small, immutable snapshot that every
quality surface consults before doing anything.

Modes (key ``quality_mode``):
- ``off``   — no QC surfaces at all; the shop never sees the module.
- ``basic`` — the historical behaviour: pass/fail + notes on a work order.
- ``full``  — plan-driven inspection (characteristics, measurements, defects,
              photos) with optional completion gating.

The default is ``basic`` so an install that has never touched the setting behaves
exactly as it did before this dial existed — a hard requirement: turning the dial
on must be opt-in, and a missing/garbage value must never brick QC.

Keys are registered (with validators) in
``app.api.v1.endpoints.system_settings.SETTING_VALIDATORS``:
- ``quality_mode``       : "off" | "basic" | "full"   (default "basic")
- ``quality_gate_close`` : bool                         (default False)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from sqlalchemy.orm import Session

from app.models.system_setting import SystemSetting


class QualityMode(str, Enum):
    """Company-wide QC rigor level."""
    OFF = "off"
    BASIC = "basic"
    FULL = "full"


QUALITY_MODE_KEY = "quality_mode"
QUALITY_GATE_CLOSE_KEY = "quality_gate_close"

DEFAULT_QUALITY_MODE = QualityMode.BASIC


@dataclass(frozen=True)
class QualityPolicy:
    """Immutable snapshot of a company's QC configuration.

    The derived properties are the questions surfaces actually ask, so callers
    never branch on the raw enum/flag themselves.
    """
    mode: QualityMode
    gate_close: bool

    @property
    def is_off(self) -> bool:
        return self.mode is QualityMode.OFF

    @property
    def is_basic(self) -> bool:
        return self.mode is QualityMode.BASIC

    @property
    def is_full(self) -> bool:
        return self.mode is QualityMode.FULL

    @property
    def surfaces_enabled(self) -> bool:
        """Whether QC surfaces (UI + endpoints) should appear at all.

        True for ``basic`` and ``full``; False only when the shop turned QC off.
        """
        return self.mode is not QualityMode.OFF

    @property
    def plan_driven(self) -> bool:
        """Whether quality plans, measurements and defect capture apply.

        Only ``full`` mode is plan-driven; ``basic`` keeps simple pass/fail.
        """
        return self.mode is QualityMode.FULL

    @property
    def gates_close(self) -> bool:
        """Whether a failed inspection HARD-blocks op/order close.

        Only meaningful in ``full`` mode, and only when the shop opted into it
        via ``quality_gate_close``. The default holds/flags instead of blocking.
        """
        return self.mode is QualityMode.FULL and self.gate_close


def _read_setting(db: Session, key: str):
    """Return the JSON value for ``key`` or None if unset. Read-only, never raises."""
    row = (
        db.query(SystemSetting.value)
        .filter(SystemSetting.key == key)
        .first()
    )
    return row[0] if row is not None else None


def get_quality_policy(db: Session) -> QualityPolicy:
    """Resolve the company QC policy from ``system_settings``, with safe defaults.

    A missing key, an unknown mode string, or a non-boolean gate flag all fall
    back to the historical ``basic`` behaviour — the dial must fail safe, never
    crash the quality path on a corrupt or partially-configured value.
    """
    raw_mode = _read_setting(db, QUALITY_MODE_KEY)
    try:
        mode = QualityMode(raw_mode) if raw_mode is not None else DEFAULT_QUALITY_MODE
    except ValueError:
        mode = DEFAULT_QUALITY_MODE

    # Strict: only the JSON boolean ``true`` enables hard-block gating. Anything
    # else (missing, null, "true", 1) is treated as not-enabled.
    gate_close = _read_setting(db, QUALITY_GATE_CLOSE_KEY) is True

    return QualityPolicy(mode=mode, gate_close=gate_close)
