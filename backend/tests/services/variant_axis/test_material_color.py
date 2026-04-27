"""MaterialColorResolver — list options + resolve to Product."""
import pytest
from fastapi import HTTPException

from app.services.variant_axis import registry
from app.services.variant_axis.material_color import MaterialColorResolver


def test_resolver_registered_under_material_color():
    r = registry.get("material_color")
    assert isinstance(r, MaterialColorResolver)


def test_resolve_to_component_returns_active_supply_product(
    db, material_type_pla, color_black, supply_product_pla_black
):
    r = registry.get("material_color")
    p = r.resolve_to_component(
        db,
        value={"material_type_id": material_type_pla.id, "color_id": color_black.id},
    )
    assert p.id == supply_product_pla_black.id
    assert p.active is True


def test_resolve_to_component_404_when_no_active_match(db):
    r = registry.get("material_color")
    with pytest.raises(HTTPException) as exc:
        r.resolve_to_component(
            db, value={"material_type_id": 99_999, "color_id": 99_999}
        )
    assert exc.value.status_code == 404


def test_list_options_returns_one_per_materialcolor_row(
    db, fg004_template_with_material_color_axis
):
    r = registry.get("material_color")
    fixt = fg004_template_with_material_color_axis
    opts = r.list_options(db, template=fixt["template"], routing_material=fixt["variable_material"])
    assert len(opts) == fixt["expected_combo_count"]
    for opt in opts:
        assert "material_type_id" in opt.value
        assert "color_id" in opt.value
        # Stronger assertions: label has em-dash separator, preview_sku starts with template SKU
        assert " — " in opt.label, f"label {opt.label!r} missing em-dash separator"
        assert opt.preview_sku and opt.preview_sku.startswith(fixt["template"].sku), (
            f"preview_sku {opt.preview_sku!r} should start with template SKU "
            f"{fixt['template'].sku!r}"
        )
        # extras["color_hex"] should be a string (defensive: empty for multi-colors)
        assert isinstance(opt.extras.get("color_hex"), str)


def test_synthesize_legacy_lifts_flat_shape_to_v2():
    r = registry.get("material_color")
    legacy = {
        "material_type_id": 7,
        "color_id": 12,
        "material_type_code": "PLA",
        "color_code": "BLK",
    }
    out = r.synthesize_legacy(variant_metadata_legacy=legacy)
    assert out is not None
    assert out["schema_version"] == 2
    assert "axis_selections" in out
    assert "__legacy__" in out["axis_selections"]
    sel = out["axis_selections"]["__legacy__"]
    assert sel["type"] == "material_color"
    assert sel["value"]["material_type_id"] == 7
    assert sel["value"]["color_id"] == 12
    assert out["axis_count"] == 1


def test_synthesize_legacy_returns_none_for_already_v2():
    r = registry.get("material_color")
    v2 = {"schema_version": 2, "axis_selections": {}}
    assert r.synthesize_legacy(variant_metadata_legacy=v2) is None


def test_synthesize_legacy_returns_none_for_future_schema_version():
    """schema_version >= 3 must not silently fall through to synthesis."""
    r = registry.get("material_color")
    future = {
        "schema_version": 3,
        "material_type_id": 7,
        "color_id": 12,
    }
    assert r.synthesize_legacy(variant_metadata_legacy=future) is None


def test_synthesize_legacy_returns_none_for_empty_or_missing_keys():
    r = registry.get("material_color")
    assert r.synthesize_legacy(variant_metadata_legacy={}) is None
    assert r.synthesize_legacy(variant_metadata_legacy={"material_type_id": 7}) is None
