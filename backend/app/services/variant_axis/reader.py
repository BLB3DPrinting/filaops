"""Single read path for variant_metadata + configuration JSONB.

Lifts legacy flat shape into v2 axis_selections via the material_color
resolver's synthesizer. Never persists synthesized output (B.1 is read-only;
write-path crossover is B.2's responsibility).
"""
from fastapi import HTTPException

from app.logging_config import get_logger
from app.services.variant_axis import registry

logger = get_logger(__name__)

AXIS_CAP_SOFT = 4
AXIS_CAP_HARD = 6


def read_axis_selections(meta: dict | None) -> dict:
    """Return a v2 axis_selections dict.

    - v2 input → passthrough
    - legacy material+color flat shape → synthesized to v2 in memory
    - None / empty / unknown → empty v2 envelope
    """
    if not meta:
        return {"schema_version": 2, "axis_selections": {}, "axis_count": 0}
    if meta.get("schema_version") == 2:
        return meta
    # Try material_color synthesis (the only legacy shape we know about).
    # Note: synthesize_legacy itself rejects schema_version != 1 (after Task 3
    # cleanup), so passing a future schema_version here returns None safely.
    try:
        mc = registry.get("material_color")
    except KeyError:
        logger.warning(
            "material_color resolver not registered — legacy variant_metadata "
            "cannot be synthesized; returning empty envelope. Check that "
            "app.services.variant_axis.material_color is imported at startup."
        )
        return {"schema_version": 2, "axis_selections": {}, "axis_count": 0}
    synthesized = mc.synthesize_legacy(variant_metadata_legacy=meta)
    if synthesized is not None:
        return synthesized
    return {"schema_version": 2, "axis_selections": {}, "axis_count": 0}


def compute_axis_count(meta_v2: dict) -> int:
    """Count axes across full recursion depth (per locked decision: cap counts depth-aware)."""
    selections = meta_v2.get("axis_selections", {})
    total = 0
    for sel in selections.values():
        total += 1
        nested = (sel.get("value") or {}).get("axis_selections")
        if isinstance(nested, dict):
            total += compute_axis_count({"axis_selections": nested})
    return total


def enforce_axis_cap(meta_v2: dict) -> int:
    """Walk axis_selections, count depth-aware, warn at soft cap, raise 400 above hard.

    Returns the computed axis_count for callers that want to surface it
    (e.g. /variant-matrix response → axis_count_warning: true when ≥ soft).
    """
    n = compute_axis_count(meta_v2)
    if n > AXIS_CAP_HARD:
        raise HTTPException(
            status_code=400,
            detail=(
                f"axis cap exceeded: {n} axes across recursion depth "
                f"(hard cap = {AXIS_CAP_HARD})"
            ),
        )
    if n > AXIS_CAP_SOFT:
        logger.warning("variant axis count %d exceeds soft cap %d", n, AXIS_CAP_SOFT)
    return n
