"""
Operation-type audit + human-gated classifier (#876 PR-3).

This module NEVER auto-reclassifies anything on its own. It only:
  1. Produces a read-only, re-runnable audit of every distinct
     (operation_code, operation_name) pair seen across
     ``routing_operations`` and ``production_order_operations``, with the
     resolved consume stages (via the #898 resolver), a name-rule
     classification proposal, and an in-flight exposure rollup.
  2. Proposes NULL-only type assignments from a name-matching rule set —
     writes nothing unless explicitly told to apply, and even then only
     touches rows where ``operation_type IS NULL``.

Nothing in Core calls this automatically. It is reached only through the
staff-gated admin endpoints in
``app/api/v1/endpoints/admin/operation_types.py``.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.manufacturing import (
    RoutingOperation,
    RoutingOperationMaterial,
)
from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.services.operation_material_mapping import (
    load_operation_type_stage_map,
    resolve_consume_stages,
)

# ---------------------------------------------------------------------------
# PO-level terminal statuses.
#
# NOTE the #850 fork: the ProductionOrder.status docstring describes an
# aspirational lifecycle ending in "completed" / "closed" / "scrapped", but
# every place in the codebase that actually WRITES or FILTERS on terminal
# status uses "complete" (production_order_service.py get_schedule_summary
# and its siblings: `ProductionOrder.status.notin_(["complete",
# "cancelled"])`). We mirror that exact, live convention here rather than
# the docstring's aspirational vocabulary, so "non-terminal" in this audit
# means precisely what it means everywhere else in the running system.
# ---------------------------------------------------------------------------
PO_TERMINAL_STATUSES = ("complete", "cancelled")

# Types that mean "materials count for nothing automatically" — an op
# carrying material rows may NEVER be auto-proposed one of these (the
# material-bearing safety rule).
NO_CONSUME_TYPE_CODES = ("QUALITY_CONTROL", "SANDING", "SUPPORT_REMOVAL")

MANUAL_DECISION_REASON = (
    "needs manual decision — op carries material rows but matched a "
    "no-consume type"
)
NO_MATCH_REASON = "no rule matched — blank or unrecognized name"
MIXED_NAME_REASON = "mixed-name — priority applied"


# ---------------------------------------------------------------------------
# Name-classification rules, in priority order. First match wins. Matching
# is case-insensitive against operation_name. A name matching more than one
# rule is "mixed-name"; the first (highest-priority) match is applied and
# flagged.
# ---------------------------------------------------------------------------
_NAME_RULES: List[Tuple[str, str]] = [
    (r"pack|ship|label|packag|box|mail", "PACK_SHIP"),
    (r"\bqc\b|quality|inspect", "QUALITY_CONTROL"),
    (r"assembl", "ASSEMBLY"),
    (r"print", "FDM_PRINT"),
    (r"sand", "SANDING"),
    (r"paint", "PAINTING"),
    (r"support|clean|post.?process", "SUPPORT_REMOVAL"),
]
_COMPILED_NAME_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(pattern, re.IGNORECASE), type_code) for pattern, type_code in _NAME_RULES
]


@dataclass
class NameClassification:
    """Result of running the name rules against an operation_name."""
    proposed_type: Optional[str]
    matched_rule_count: int
    reason: Optional[str] = None
    mixed: bool = False


def classify_name(operation_name: Optional[str]) -> NameClassification:
    """
    Run the priority-ordered name rules against ``operation_name``.

    Blank/whitespace-only names propose nothing. A name matching more than
    one rule's pattern is "mixed" — the highest-priority match is proposed,
    flagged with MIXED_NAME_REASON. A name matching no rule proposes
    nothing (NO_MATCH_REASON).
    """
    if not operation_name or not operation_name.strip():
        return NameClassification(proposed_type=None, matched_rule_count=0, reason=NO_MATCH_REASON)

    matches = [type_code for pattern, type_code in _COMPILED_NAME_RULES if pattern.search(operation_name)]
    if not matches:
        return NameClassification(proposed_type=None, matched_rule_count=0, reason=NO_MATCH_REASON)

    proposed = matches[0]
    mixed = len(matches) > 1
    return NameClassification(
        proposed_type=proposed,
        matched_rule_count=len(matches),
        reason=MIXED_NAME_REASON if mixed else None,
        mixed=mixed,
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@dataclass
class AuditRow:
    operation_code: Optional[str]
    operation_name: Optional[str]
    routing_op_count: int
    po_op_count: int
    stored_operation_type: Optional[str]
    match_source: str  # "stored-type" | "legacy-dict" | "default"
    current_consume_stages: List[str]
    proposed_type: Optional[str]
    proposed_consume_stages: Optional[List[str]]
    behavior_changed: bool
    material_bearing: bool
    classification_reason: Optional[str]
    in_flight_non_terminal_po_count: int


def _match_source(operation_type: Optional[str], operation_code: Optional[str]) -> str:
    if operation_type:
        return "stored-type"
    from app.services.operation_material_mapping import OPERATION_CONSUME_STAGES

    if operation_code and operation_code.upper() in OPERATION_CONSUME_STAGES:
        return "legacy-dict"
    return "default"


def _distinct_pairs_with_counts(db: Session):
    """
    Every distinct (operation_code, operation_name) pair across BOTH
    routing_operations and production_order_operations, with per-table
    counts and one representative stored operation_type per pair (routing
    table wins ties; falls back to the PO-op table if the pair only exists
    there).
    """
    routing_rows = (
        db.query(
            RoutingOperation.operation_code,
            RoutingOperation.operation_name,
            RoutingOperation.operation_type,
            func.count(RoutingOperation.id),
        )
        .group_by(
            RoutingOperation.operation_code,
            RoutingOperation.operation_name,
            RoutingOperation.operation_type,
        )
        .all()
    )
    po_rows = (
        db.query(
            ProductionOrderOperation.operation_code,
            ProductionOrderOperation.operation_name,
            ProductionOrderOperation.operation_type,
            func.count(ProductionOrderOperation.id),
        )
        .group_by(
            ProductionOrderOperation.operation_code,
            ProductionOrderOperation.operation_name,
            ProductionOrderOperation.operation_type,
        )
        .all()
    )

    # key = (operation_code, operation_name) — the pair identity for the
    # audit. Aggregate multiple stored-type rows for the same pair (e.g. a
    # pair typed on some rows and NULL on others) by preferring any non-NULL
    # type over NULL, routing table first.
    pairs: Dict[Tuple[Optional[str], Optional[str]], dict] = {}

    def _ingest(rows, table_key):
        for code, name, op_type, count in rows:
            key = (code, name)
            entry = pairs.setdefault(
                key,
                {"routing_op_count": 0, "po_op_count": 0, "operation_type": None},
            )
            entry[table_key] += count
            if op_type and not entry["operation_type"]:
                entry["operation_type"] = op_type

    _ingest(routing_rows, "routing_op_count")
    _ingest(po_rows, "po_op_count")

    return pairs


def _material_bearing_codes(db: Session) -> set:
    """
    Set of (operation_code, operation_name) pairs that have at least one
    material row attached, on EITHER the routing template
    (RoutingOperationMaterial) or the production-order instance
    (ProductionOrderOperationMaterial) side.
    """
    bearing = set()

    routing_bearing = (
        db.query(RoutingOperation.operation_code, RoutingOperation.operation_name)
        .join(
            RoutingOperationMaterial,
            RoutingOperationMaterial.routing_operation_id == RoutingOperation.id,
        )
        .distinct()
        .all()
    )
    bearing.update(routing_bearing)

    po_bearing = (
        db.query(ProductionOrderOperation.operation_code, ProductionOrderOperation.operation_name)
        .join(
            ProductionOrderOperationMaterial,
            ProductionOrderOperationMaterial.production_order_operation_id == ProductionOrderOperation.id,
        )
        .distinct()
        .all()
    )
    bearing.update(po_bearing)

    return bearing


def _in_flight_counts(db: Session) -> Dict[Tuple[Optional[str], Optional[str]], int]:
    """
    Count of DISTINCT non-terminal ProductionOrders whose operations carry
    each (operation_code, operation_name) pair. "Non-terminal" = PO.status
    NOT IN PO_TERMINAL_STATUSES (see module docstring re: #850 fork).
    """
    rows = (
        db.query(
            ProductionOrderOperation.operation_code,
            ProductionOrderOperation.operation_name,
            func.count(func.distinct(ProductionOrderOperation.production_order_id)),
        )
        .join(ProductionOrder, ProductionOrder.id == ProductionOrderOperation.production_order_id)
        .filter(ProductionOrder.status.notin_(PO_TERMINAL_STATUSES))
        .group_by(
            ProductionOrderOperation.operation_code,
            ProductionOrderOperation.operation_name,
        )
        .all()
    )
    return {(code, name): count for code, name, count in rows}


def build_audit(db: Session) -> List[AuditRow]:
    """
    Build the full, read-only audit of every distinct (operation_code,
    operation_name) pair across both operation tables. Re-runnable —
    queries only, no writes.
    """
    type_map = load_operation_type_stage_map(db)
    pairs = _distinct_pairs_with_counts(db)
    material_bearing_pairs = _material_bearing_codes(db)
    in_flight = _in_flight_counts(db)

    rows: List[AuditRow] = []
    for (code, name), info in sorted(pairs.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")):
        stored_type = info["operation_type"]
        current_stages = resolve_consume_stages(type_map, stored_type, code)
        source = _match_source(stored_type, code)
        is_material_bearing = (code, name) in material_bearing_pairs

        name_result = classify_name(name)
        proposed_type = name_result.proposed_type
        reason = name_result.reason

        # Material-bearing safety rule: never auto-propose a no-consume
        # type for an op that carries material rows.
        if proposed_type in NO_CONSUME_TYPE_CODES and is_material_bearing:
            proposed_type = None
            reason = MANUAL_DECISION_REASON

        proposed_stages = None
        behavior_changed = False
        if proposed_type is not None and stored_type is None:
            proposed_stages = resolve_consume_stages(type_map, proposed_type, code)
            behavior_changed = list(proposed_stages) != list(current_stages)

        rows.append(
            AuditRow(
                operation_code=code,
                operation_name=name,
                routing_op_count=info["routing_op_count"],
                po_op_count=info["po_op_count"],
                stored_operation_type=stored_type,
                match_source=source,
                current_consume_stages=current_stages,
                proposed_type=proposed_type,
                proposed_consume_stages=proposed_stages,
                behavior_changed=behavior_changed,
                material_bearing=is_material_bearing,
                classification_reason=reason,
                in_flight_non_terminal_po_count=in_flight.get((code, name), 0),
            )
        )

    return rows


# ---------------------------------------------------------------------------
# Classifier apply / dry-run
# ---------------------------------------------------------------------------

@dataclass
class ProposalRow:
    table: str  # "routing_operations" | "production_order_operations"
    row_id: int
    operation_code: Optional[str]
    operation_name: Optional[str]
    proposed_type: Optional[str]
    reason: Optional[str]
    material_bearing: bool
    before_stages: List[str]
    after_stages: Optional[List[str]]
    production_order_id: Optional[int] = None
    production_order_status: Optional[str] = None


@dataclass
class ClassifyResult:
    dry_run: bool
    proposals: List[ProposalRow] = field(default_factory=list)
    applied_count: int = 0
    skipped_manual_decision_count: int = 0
    skipped_no_match_count: int = 0
    non_terminal_exposure_count: int = 0


def _iter_null_typed_routing_ops(db: Session):
    return (
        db.query(RoutingOperation)
        .filter(RoutingOperation.operation_type.is_(None))
        .all()
    )


def _iter_null_typed_po_ops(db: Session):
    return (
        db.query(ProductionOrderOperation)
        .filter(ProductionOrderOperation.operation_type.is_(None))
        .all()
    )


def run_classifier(db: Session, dry_run: bool = True) -> ClassifyResult:
    """
    Human-gated classifier over NULL-``operation_type`` rows in BOTH
    ``routing_operations`` and ``production_order_operations``.

    dry_run=True (default): builds and returns the full proposal report —
    WRITES NOTHING.

    dry_run=False: applies NULL -> proposed_type ONLY where a safe
    unambiguous proposal exists. Never overwrites a non-NULL
    operation_type (the WHERE clause guarantees this — rows are only
    selected because operation_type IS NULL). Idempotent: running again
    after an apply finds zero NULL rows left to propose for, so it is a
    no-op.

    Material-bearing rows that would otherwise match a no-consume type
    (QUALITY_CONTROL / SANDING / SUPPORT_REMOVAL) are never auto-applied —
    they are surfaced as "needs manual decision" and skipped in both
    dry-run and apply.

    Recording WHO applied a run and WHEN is the caller's responsibility
    (the admin endpoint stamps the authenticated staff user's email +
    current UTC time onto the response) — this function only knows about
    rows and proposals, not the requesting identity.
    """
    type_map = load_operation_type_stage_map(db)
    material_bearing_pairs = _material_bearing_codes(db)

    # PO id -> status, for stamping production_order_status onto PO-op
    # proposal rows and for the row-level non-terminal-exposure count,
    # without a per-row query.
    po_status_by_id: Dict[int, str] = dict(db.query(ProductionOrder.id, ProductionOrder.status).all())

    result = ClassifyResult(dry_run=dry_run)

    def _process(row, table_name: str):
        code = row.operation_code
        name = row.operation_name
        is_material_bearing = (code, name) in material_bearing_pairs

        name_result = classify_name(name)
        proposed_type = name_result.proposed_type
        reason = name_result.reason

        if proposed_type in NO_CONSUME_TYPE_CODES and is_material_bearing:
            proposed_type = None
            reason = MANUAL_DECISION_REASON

        before_stages = resolve_consume_stages(type_map, None, code)
        after_stages = None
        if proposed_type is not None:
            after_stages = resolve_consume_stages(type_map, proposed_type, code)

        po_id = None
        po_status = None
        row_is_non_terminal_po = False
        if table_name == "production_order_operations":
            po_id = row.production_order_id
            po_status = po_status_by_id.get(po_id)
            row_is_non_terminal_po = po_status is not None and po_status not in PO_TERMINAL_STATUSES

        proposal = ProposalRow(
            table=table_name,
            row_id=row.id,
            operation_code=code,
            operation_name=name,
            proposed_type=proposed_type,
            reason=reason,
            material_bearing=is_material_bearing,
            before_stages=before_stages,
            after_stages=after_stages,
            production_order_id=po_id,
            production_order_status=po_status,
        )
        result.proposals.append(proposal)

        if proposed_type is None:
            if reason == MANUAL_DECISION_REASON:
                result.skipped_manual_decision_count += 1
            else:
                result.skipped_no_match_count += 1
            return

        if row_is_non_terminal_po:
            result.non_terminal_exposure_count += 1

        if not dry_run:
            row.operation_type = proposed_type
            db.add(row)
            result.applied_count += 1

    for row in _iter_null_typed_routing_ops(db):
        _process(row, "routing_operations")

    for row in _iter_null_typed_po_ops(db):
        _process(row, "production_order_operations")

    if not dry_run and result.applied_count:
        db.commit()

    return result
