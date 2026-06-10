"""ComponentTemplateResolver — resolves to active children of parent_product_id.

CRITICAL: must NOT branch on item_type. Same code path for manufactured,
component, and supply (purchased) templates. Resolver query is just
parent_product_id == template.id AND active.
"""
import pytest
from fastapi import HTTPException

from app.services.variant_axis import registry


def test_resolver_registered_under_component_template():
    from app.services.variant_axis.component_template import ComponentTemplateResolver
    r = registry.get("component_template")
    assert isinstance(r, ComponentTemplateResolver)


def test_list_options_returns_one_per_active_child(db, fg004_component_template_axis):
    """Variable BOM line has 9 active children → 9 options."""
    r = registry.get("component_template")
    fixt = fg004_component_template_axis
    opts = r.list_options(db, template=fixt["template"], routing_material=fixt["variable_material"])
    assert len(opts) == 9
    for opt in opts:
        assert "component_id" in opt.value
        assert opt.preview_sku  # non-empty


def test_list_options_excludes_inactive_children(db, fg004_component_template_axis_with_inactive):
    r = registry.get("component_template")
    fixt = fg004_component_template_axis_with_inactive
    opts = r.list_options(db, template=fixt["template"], routing_material=fixt["variable_material"])
    assert len(opts) == fixt["active_count"]
    returned_ids = {o.value["component_id"] for o in opts}
    assert fixt["inactive_child_id"] not in returned_ids


def test_resolve_to_component_returns_named_child(db, fg004_component_template_axis):
    r = registry.get("component_template")
    fixt = fg004_component_template_axis
    target = fixt["children"][3]
    p = r.resolve_to_component(db, value={"component_id": target.id})
    assert p.id == target.id


def test_resolve_to_component_404_for_unknown_id(db):
    r = registry.get("component_template")
    with pytest.raises(HTTPException) as exc:
        r.resolve_to_component(db, value={"component_id": 99_999_999})
    assert exc.value.status_code == 404


def test_resolve_to_component_400_for_missing_component_id(db):
    r = registry.get("component_template")
    with pytest.raises(HTTPException) as exc:
        r.resolve_to_component(db, value={})
    assert exc.value.status_code == 400


def test_synthesize_legacy_always_returns_none(db):
    """component_template has no legacy shape — only material_color did."""
    r = registry.get("component_template")
    assert r.synthesize_legacy(variant_metadata_legacy={"anything": 1}) is None


def test_resolver_does_not_branch_on_item_type(
    db,
    manufactured_template_with_children,
    supply_template_with_children,
    component_template_with_children,
):
    """Same resolver works for manufactured, component, AND supply templates — Rule 1 from §2.

    The strategic plan explicitly calls out all three item_types must work
    identically through the same resolver code path, with no branching.
    """
    r = registry.get("component_template")
    for fixt in (manufactured_template_with_children, supply_template_with_children, component_template_with_children):
        opts = r.list_options(db, template=fixt["template"], routing_material=fixt["variable_material"])
        assert len(opts) == fixt["expected_count"]


def test_resolve_recursive_2_deep(db, fg_with_variable_manuf_component_with_variable_material):
    """FG → variable manuf component → has its own variable material.

    Customer config: outer chooses ball variant; inner chooses ball's filament finish.
    Resolver walks both axes by being called twice — once for outer, once for inner.
    """
    fixt = fg_with_variable_manuf_component_with_variable_material
    cfg = {
        "schema_version": 2,
        "axis_selections": {
            str(fixt["outer_routing_material_id"]): {
                "type": "component_template",
                "value": {
                    "component_id": fixt["chosen_ball_id"],
                    "axis_selections": {
                        str(fixt["inner_routing_material_id"]): {
                            "type": "material_color",
                            "value": {
                                "material_type_id": fixt["chosen_finish_mt_id"],
                                "color_id": fixt["chosen_finish_color_id"],
                            },
                        },
                    },
                },
            },
        },
    }

    # Outer axis resolves to chosen ball
    outer_resolver = registry.get("component_template")
    outer = outer_resolver.resolve_to_component(
        db, value=cfg["axis_selections"][str(fixt["outer_routing_material_id"])]["value"]
    )
    assert outer.id == fixt["chosen_ball_id"]

    # Inner axis resolves to chosen finish supply product
    inner_sel = cfg["axis_selections"][str(fixt["outer_routing_material_id"])]["value"]["axis_selections"]
    inner_axis = inner_sel[str(fixt["inner_routing_material_id"])]
    inner_resolver = registry.get(inner_axis["type"])
    inner = inner_resolver.resolve_to_component(db, value=inner_axis["value"])
    assert inner.material_type_id == fixt["chosen_finish_mt_id"]
    assert inner.color_id == fixt["chosen_finish_color_id"]


def test_perf_canary_6_deep_recursive_resolve(db, deeply_nested_template_6_axes, capsys):
    """Quadratic-blowup canary. Log-only by default; env-var gates a hard threshold.

    Per strategic plan §4 + §8 mitigation: VARIANT_AXIS_PERF_THRESHOLD_MS unset
    in CI = log-only (no flake). Local benchmarks set the env to enforce.
    """
    import os
    import time

    fixt = deeply_nested_template_6_axes  # 6 axes built via fixture; resolve_calls is a list of 6 (type, value) tuples

    start = time.perf_counter()
    for resolver_type, value in fixt["resolve_calls"]:
        registry.get(resolver_type).resolve_to_component(db, value=value)
    elapsed_ms = (time.perf_counter() - start) * 1000

    threshold_env = os.environ.get("VARIANT_AXIS_PERF_THRESHOLD_MS")
    if threshold_env:
        assert elapsed_ms < float(threshold_env), (
            f"6-deep recursive resolve took {elapsed_ms:.1f}ms, "
            f"threshold {threshold_env}ms"
        )
    else:
        # Log-only mode (CI default). Visible in test output for trend tracking.
        print(f"[perf-canary] 6-deep recursive resolve elapsed: {elapsed_ms:.1f}ms")
