"""Quality gate evaluation (#784 PR-7).

Computes whether a recorded QC *pass* actually satisfies the product's active
quality plan: every plan characteristic measured (completeness) and conformant
(variable in-spec / attribute Go). Conformance is derived SERVER-SIDE from the
raw values — the client-supplied ``conforms`` is only trusted for attribute
(subjective Go/No-Go) characteristics, never for variable ones.

Pure functions; the gate ENFORCEMENT (off / warn / block) lives in
``record_qc_inspection`` and consults ``quality_policy``. Core-only — SPC
analytics and certs are PRO.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass(frozen=True)
class GateEvaluation:
    """Result of comparing an active plan to an inspection's measurements."""
    missing: list  # plan characteristics with no usable measurement
    failing: list  # measured characteristics that are out of spec / nonconforming

    @property
    def is_clean(self) -> bool:
        return not self.missing and not self.failing

    def summary(self) -> str:
        parts = []
        if self.missing:
            parts.append(f"{len(self.missing)} unmeasured ({', '.join(self.missing)})")
        if self.failing:
            parts.append(
                f"{len(self.failing)} out of spec/nonconforming ({', '.join(self.failing)})"
            )
        return "; ".join(parts)


def _to_decimal(value) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    # NaN/Infinity would raise on comparison — treat as "no usable value".
    return d if d.is_finite() else None


def evaluate_inspection(plan, measurements) -> GateEvaluation:
    """Compare a product's active ``plan`` against an inspection's ``measurements``.

    ``measurements`` is the list of dicts as passed to ``record_qc_inspection``
    (each may carry ``quality_plan_characteristic_id``, ``measured_value``,
    ``conforms``, ``lower_limit``, ``upper_limit``). Returns the unmeasured plan
    characteristics and the measured-but-nonconforming ones. Manual rows (no plan
    link) don't count toward the plan contract.
    """
    chars = {c.id: c for c in plan.characteristics}
    by_char = {}
    for m in measurements:
        cid = m.get("quality_plan_characteristic_id")
        if cid is not None:
            by_char[cid] = m

    missing = []
    failing = []
    for cid, c in chars.items():
        m = by_char.get(cid)
        if m is None:
            missing.append(c.characteristic)
            continue

        if c.characteristic_type == "attribute":
            # Subjective Go/No-Go — the inspector's recorded conforms is the truth.
            conforms = m.get("conforms")
            if conforms is None:
                missing.append(c.characteristic)   # row exists but unanswered
            elif conforms is not True:
                failing.append(c.characteristic)   # explicitly rejected
            continue

        # Variable: a value is required; conformance is derived SERVER-SIDE from
        # the PLAN's spec limits — NEVER the client-supplied measurement limits
        # (a client could otherwise clear the gate with an out-of-spec value and
        # its own wide limits). Mirrors how client `conforms` is ignored here.
        measured = _to_decimal(m.get("measured_value"))
        if measured is None:
            missing.append(c.characteristic)
            continue
        lower = _to_decimal(c.lower_limit)
        upper = _to_decimal(c.upper_limit)
        # No limits => a recorded value with no spec to violate (conformant).
        if lower is not None and measured < lower:
            failing.append(c.characteristic)
        elif upper is not None and measured > upper:
            failing.append(c.characteristic)

    return GateEvaluation(missing=missing, failing=failing)
