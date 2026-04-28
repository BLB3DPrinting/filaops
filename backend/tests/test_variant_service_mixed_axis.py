"""Mixed-axis sync_routing_to_variants — Rule 3 from strategic plan §2.

A template with 1 variable material_color line + 1 variable component_template
line + 2 fixed lines must produce variants where:
- the material_color line's component is swapped to the variant's material+color target
- the component_template line's component is swapped to the variant's chosen child
- the 2 fixed lines are preserved verbatim
"""
from sqlalchemy import desc
from app.services import variant_service
from app.models.manufacturing import Routing


def test_sync_routing_to_variants_resolves_each_axis_independently(
    db, mixed_axis_template_with_one_variant
):
    fixt = mixed_axis_template_with_one_variant
    template = fixt["template"]
    variant = fixt["variant"]
    expected_color_target_id = fixt["expected_color_target_id"]
    expected_component_target_id = fixt["expected_component_target_id"]
    fixed_component_ids = fixt["fixed_component_ids"]  # list of 2

    variant_service.sync_routing_to_variants(db, template.id)

    db.refresh(variant)
    # NOTE: Product.routings may not be a defined relationship; query directly.
    routing = (
        db.query(Routing)
        .filter(Routing.product_id == variant.id, Routing.is_active.is_(True))
        .order_by(desc(Routing.version))
        .first()
    )
    assert routing is not None, "variant has no active routing after sync"
    materials = [m for op in routing.operations for m in op.materials]
    component_ids = {m.component_id for m in materials}

    assert expected_color_target_id in component_ids, (
        f"material_color line not swapped: expected {expected_color_target_id} "
        f"in {sorted(component_ids)}"
    )
    assert expected_component_target_id in component_ids, (
        f"component_template line not swapped: expected {expected_component_target_id} "
        f"in {sorted(component_ids)}"
    )
    for fid in fixed_component_ids:
        assert fid in component_ids, (
            f"fixed line component {fid} missing from variant routing "
            f"(present: {sorted(component_ids)})"
        )
