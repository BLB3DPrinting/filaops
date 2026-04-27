"""Single read path for variant_metadata + configuration JSONB.

Lifts legacy flat shape into v2 axis_selections via the material_color
resolver's synthesizer. Never persists synthesized output (B.1 is read-only;
write-path crossover is B.2's responsibility).
"""
from app.services.variant_axis import registry


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
