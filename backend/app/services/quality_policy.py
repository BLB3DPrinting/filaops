"""Quality policy read-model — the QC rigor "dial" (#784 QMS).

The whole quality module is *selectable*: some shops do no formal QC, others run
regulated-grade inspection. This module resolves the company's chosen rigor from
the ``system_settings`` KV store into a small, immutable snapshot that every
quality surface consults before doing anything.

Modes (key ``quality_mode``):
- ``off``   — no QC surfaces at all; the shop never sees the module.
- ``basic`` — the historical behaviour: pass/fail + notes on a work order.
- ``full``  — plan-driven inspection (characteristics, measurements, defects,
              photos) with a configurable inspection-result gate.

The default is ``basic`` so an install that has never touched the setting behaves
exactly as it did before this dial existed — a hard requirement: turning the dial
on must be opt-in, and a missing/garbage value must never brick QC.

Keys are registered (with validators) in
``app.api.v1.endpoints.system_settings.SETTING_VALIDATORS``:
- ``quality_mode``        : "off" | "basic" | "full"      (default "basic")
- ``quality_gate_action`` : "off" | "warn" | "block"      (default "warn")
- ``quality_gate_close``  : bool — LEGACY, read only as a back-compat fallback
                            for ``quality_gate_action`` (true -> "block").
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


class GateAction(str, Enum):
    """What the Full-mode inspection gate does when a recorded *pass* is
    incomplete (not every plan characteristic measured) or out of spec.

    Only meaningful in ``full`` mode; ``basic``/``off`` never gate.
    """
    OFF = "off"      # record as-is, no enforcement
    WARN = "warn"    # record, but return a warning — the default: flag, don't block
    BLOCK = "block"  # reject the pass; the inspector must complete it or fail it


QUALITY_MODE_KEY = "quality_mode"
QUALITY_GATE_ACTION_KEY = "quality_gate_action"
QUALITY_GATE_CLOSE_KEY = "quality_gate_close"  # legacy bool, back-compat fallback

DEFAULT_QUALITY_MODE = QualityMode.BASIC
DEFAULT_GATE_ACTION = GateAction.WARN


@dataclass(frozen=True)
class QualityPolicy:
    """Immutable snapshot of a company's QC configuration.

    The derived properties are the questions surfaces actually ask, so callers
    never branch on the raw enum/flag themselves.
    """
    mode: QualityMode
    gate_action: GateAction
    gate_close: bool  # raw legacy setting, surfaced for back-compat consumers

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
    def gate_enforced(self) -> bool:
        """Whether the inspection gate does anything (warn OR block).

        Only in ``full`` mode and only when the action isn't ``off``.
        """
        return self.mode is QualityMode.FULL and self.gate_action is not GateAction.OFF

    @property
    def gates_close(self) -> bool:
        """Whether the gate HARD-blocks (``block`` action in ``full`` mode).

        Kept as a named property for the policy response + back-compat; ``warn``
        flags without blocking.
        """
        return self.mode is QualityMode.FULL and self.gate_action is GateAction.BLOCK


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

    A missing key, an unknown mode/action string, or a non-boolean legacy flag all
    fall back to safe values — the dial must fail safe, never crash the quality
    path on a corrupt or partially-configured value, and never *block* by accident.
    """
    raw_mode = _read_setting(db, QUALITY_MODE_KEY)
    try:
        mode = QualityMode(raw_mode) if raw_mode is not None else DEFAULT_QUALITY_MODE
    except ValueError:
        mode = DEFAULT_QUALITY_MODE

    # Strict: only the JSON boolean ``true`` counts (no truthy coercion).
    legacy_close = _read_setting(db, QUALITY_GATE_CLOSE_KEY) is True

    raw_action = _read_setting(db, QUALITY_GATE_ACTION_KEY)
    if raw_action is not None:
        try:
            gate_action = GateAction(raw_action)
        except ValueError:
            gate_action = DEFAULT_GATE_ACTION
    else:
        # Back-compat with the legacy boolean: only literal ``true`` meant "block".
        # Anything else (missing/false/garbage) -> the default (warn), so an
        # unconfigured install never hard-blocks.
        gate_action = GateAction.BLOCK if legacy_close else DEFAULT_GATE_ACTION

    return QualityPolicy(mode=mode, gate_action=gate_action, gate_close=legacy_close)
