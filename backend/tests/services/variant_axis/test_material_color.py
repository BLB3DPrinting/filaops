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
        assert opt.label  # non-empty
