"""read_axis_selections — single read path for variant_metadata.

Always returns a v2 dict, lifting legacy shape via material_color.synthesize_legacy.
Variants written before B.1 lack schema_version → treat absent as v1.
"""
from app.services.variant_axis.reader import read_axis_selections, compute_axis_count, enforce_axis_cap


def test_read_v2_passthrough_unchanged():
    v2 = {
        "schema_version": 2,
        "axis_selections": {
            "55": {"type": "material_color", "label": "Color", "value": {"material_type_id": 7, "color_id": 12}},
        },
    }
    out = read_axis_selections(v2)
    assert out == v2


def test_read_legacy_flat_shape_synthesizes_to_v2():
    legacy = {"material_type_id": 7, "color_id": 12, "material_type_code": "PLA", "color_code": "BLK"}
    out = read_axis_selections(legacy)
    assert out["schema_version"] == 2
    assert "axis_selections" in out


def test_read_absent_schema_version_treated_as_v1():
    """The strategic plan §3.4 sentence: 'absent treated as v1'."""
    legacy_no_version = {"material_type_id": 7, "color_id": 12}
    out = read_axis_selections(legacy_no_version)
    assert out["schema_version"] == 2


def test_read_none_or_empty_returns_empty_v2():
    assert read_axis_selections(None) == {"schema_version": 2, "axis_selections": {}, "axis_count": 0}
    assert read_axis_selections({}) == {"schema_version": 2, "axis_selections": {}, "axis_count": 0}


def test_compute_axis_count_flat():
    sel = {
        "schema_version": 2,
        "axis_selections": {
            "55": {"type": "material_color", "value": {}},
            "56": {"type": "component_template", "value": {}},
        },
    }
    assert compute_axis_count(sel) == 2


def test_compute_axis_count_recursive_2_deep():
    """Recursion: nested value carries another axis_selections."""
    sel = {
        "schema_version": 2,
        "axis_selections": {
            "55": {
                "type": "component_template",
                "value": {
                    "component_id": 100,
                    "axis_selections": {
                        "61": {"type": "material_color", "value": {"material_type_id": 1, "color_id": 1}},
                    },
                },
            },
        },
    }
    assert compute_axis_count(sel) == 2  # 1 outer + 1 inner


import pytest
from fastapi import HTTPException

SOFT = 4
HARD = 6


def _build_n_axis_meta(n: int) -> dict:
    return {
        "schema_version": 2,
        "axis_selections": {
            str(i): {"type": "material_color", "label": "x", "value": {"material_type_id": 1, "color_id": i}}
            for i in range(n)
        },
    }


def test_enforce_axis_cap_under_soft_no_warning(caplog):
    enforce_axis_cap(_build_n_axis_meta(2))
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_enforce_axis_cap_at_soft_warns(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        enforce_axis_cap(_build_n_axis_meta(SOFT + 1))
    assert any("axis count" in r.message.lower() for r in caplog.records)


def test_enforce_axis_cap_above_hard_raises():
    with pytest.raises(HTTPException) as exc:
        enforce_axis_cap(_build_n_axis_meta(HARD + 1))
    assert exc.value.status_code == 400
    assert "axis cap" in exc.value.detail.lower()
