"""
Maps operation codes to BOM consume stages.

This determines which materials are needed at each operation.
"""
from typing import Dict, List, Optional, Set

from sqlalchemy.orm import Session

# Operation code to consume stage mapping
# Multiple operation codes can map to the same consume stage
OPERATION_CONSUME_STAGES = {
    # Production operations - consume raw materials, filament
    "PRINT": ["production", "any"],
    "EXTRUDE": ["production", "any"],
    "MOLD": ["production", "any"],
    "CUT": ["production", "any"],
    "MACHINE": ["production", "any"],

    # Assembly operations - consume hardware, subassemblies
    "ASSEMBLE": ["assembly", "production", "any"],
    "BUILD": ["assembly", "production", "any"],
    "WELD": ["assembly", "production", "any"],

    # Finishing operations - typically no material consumption
    "CLEAN": ["any"],
    "SAND": ["any"],
    "PAINT": ["finishing", "any"],
    "COAT": ["finishing", "any"],

    # Quality operations - typically no material consumption
    "QC": ["any"],
    "INSPECT": ["any"],
    "TEST": ["any"],

    # Shipping operations - consume packaging materials
    "PACK": ["shipping", "any"],
    "SHIP": ["shipping", "any"],
    "LABEL": ["shipping", "any"],
}

# Default stages if operation code not found
DEFAULT_CONSUME_STAGES = ["production", "any"]


def get_consume_stages_for_operation(operation_code: str) -> List[str]:
    """
    Get the consume stages that apply to an operation code.

    Args:
        operation_code: The operation code (e.g., "PRINT", "PACK")

    Returns:
        List of consume stages to check for this operation
    """
    if not operation_code:
        return DEFAULT_CONSUME_STAGES

    code_upper = operation_code.upper()
    return OPERATION_CONSUME_STAGES.get(code_upper, DEFAULT_CONSUME_STAGES)


def get_all_consume_stages() -> Set[str]:
    """Get all known consume stages."""
    stages = set()
    for stage_list in OPERATION_CONSUME_STAGES.values():
        stages.update(stage_list)
    return stages


# =============================================================================
# #876 PR-2: write-time alias assist — the ONE shared importable copy.
#
# NOTE ON DUPLICATION: migrations/versions/101_operation_types.py and
# tests/services/test_operation_type_catalog.py each keep their OWN frozen
# literal copy of this same code->type mapping, deliberately — a migration
# must never import live application code (it has to keep working exactly
# as written even after this module changes in the future), and its pinned
# test asserts the migration's frozen copy byte-for-byte. This module's copy
# is the single source other RUNTIME code (routing_service.py's write-time
# alias assist) is meant to import. If you change the aliasing rule here,
# the migration and its test are NOT automatically updated — that is correct
# and intentional; a shipped migration is immutable history.
#
# FINISH and POST are deliberately excluded (see migration 101 docstring):
# the live census shows FINISH spans shipping/quality/blank names, so it is
# classifiable only per-row by name via the human-gated classifier, never
# by a blanket alias.
# =============================================================================

OPERATION_CODE_TYPE_ALIASES: Dict[str, str] = {
    "PRINT": "FDM_PRINT",
    "EXTRUDE": "GENERAL",
    "MOLD": "GENERAL",
    "CUT": "GENERAL",
    "MACHINE": "GENERAL",
    "ASSEMBLE": "ASSEMBLY",
    "BUILD": "ASSEMBLY",
    "WELD": "ASSEMBLY",
    "QC": "QUALITY_CONTROL",
    "INSPECT": "QUALITY_CONTROL",
    "TEST": "QUALITY_CONTROL",
    "CLEAN": "SUPPORT_REMOVAL",
    "SAND": "SANDING",
    "PAINT": "PAINTING",
    "COAT": "PAINTING",
    "PACK": "PACK_SHIP",
    "SHIP": "PACK_SHIP",
    "LABEL": "PACK_SHIP",
}


def alias_operation_type_for_code(operation_code: Optional[str]) -> Optional[str]:
    """
    Write-time alias assist: given a legacy operation_code, return the
    canonical operation_type it should be auto-assigned when the caller
    didn't supply one explicitly.

    Returns None when the code is empty/None or doesn't match one of the 18
    legacy canonical keys (case-insensitive) — most notably FINISH and POST,
    which get NO alias, deliberately (see module docstring above).
    """
    if not operation_code:
        return None
    return OPERATION_CODE_TYPE_ALIASES.get(operation_code.upper())


# =============================================================================
# #876 PR-1: operation-type catalog resolver (dormant — no consumer wired yet)
#
# Everything ABOVE this line (the legacy dict, DEFAULT_CONSUME_STAGES, and
# get_consume_stages_for_operation) is UNTOUCHED and pinned by
# tests/services/test_small_services.py::TestOperationMaterialMapping.
#
# The functions below are additive. #876 PR-2 will switch the three #875
# stage resolvers (inventory_service.py) and get_bom_lines_for_operation
# (operation_blocking.py) to call resolve_consume_stages() instead of
# get_consume_stages_for_operation() directly. Until then, nothing calls
# these — they ship dormant, proven correct by the predicate-equivalence
# test in tests/services/test_operation_type_catalog.py.
# =============================================================================

def load_operation_type_stage_map(db: Session) -> Dict[str, List[str]]:
    """
    Load the operation-type catalog into a {code: consume_stages} map.

    One query per consumer call (consumers call this once at entry, not
    per-row). Includes INACTIVE rows deliberately — a routing operation
    typed before its type was deactivated must still resolve exactly as it
    always has; history must never break because a type was retired.

    Returns an empty dict if the table doesn't exist yet or has no rows
    (e.g. a Core-only checkout that hasn't run migration 101) — callers
    fall through to the legacy code map via resolve_consume_stages().
    """
    from app.models.manufacturing import OperationType

    try:
        rows = db.query(OperationType.code, OperationType.consume_stages).all()
    except Exception:
        # Table not migrated yet on this DB — resolve entirely via legacy
        # code map. This keeps the resolver safe to call speculatively
        # during a rolling deploy where the migration hasn't landed.
        return {}
    return {code: list(stages or []) for code, stages in rows}


def resolve_consume_stages(
    type_map: Dict[str, List[str]],
    operation_type: Optional[str],
    operation_code: Optional[str],
) -> List[str]:
    """
    Resolve the consume stages for an operation, type-first.

    Precedence:
      1. operation_type is set AND present in type_map -> its consume_stages.
      2. Otherwise -> get_consume_stages_for_operation(operation_code), i.e.
         the exact 18-key legacy dict, then DEFAULT_CONSUME_STAGES.

    An unknown or inactive type code (not in type_map) falls through to
    step 2 rather than raising — resolution must never crash on stale or
    hand-edited data.

    NULL type + NULL/unknown code -> ["production", "any"], honoring the
    #875 docstring contract (inventory_service.py) and the pinned
    default-stage tests. The stored type is the ONLY runtime semantic
    carrier fed by this function — no name is ever consulted here.
    """
    if operation_type:
        stages = type_map.get(operation_type)
        if stages is not None:
            return stages
    return get_consume_stages_for_operation(operation_code)
