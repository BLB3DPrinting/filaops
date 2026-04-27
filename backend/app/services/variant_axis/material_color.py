"""MaterialColorResolver — preserves legacy material_type+color axis.

Lifted from variant_service._find_material_product + get_variant_matrix's
MaterialColor join logic. The resolver is the canonical source of truth;
variant_service delegates to it in Task 7.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import Product
from app.models.material import MaterialType, Color, MaterialColor
from app.models.manufacturing import RoutingOperationMaterial
from app.services.variant_axis import registry
from app.services.variant_axis.types import AxisOption

logger = get_logger(__name__)


class MaterialColorResolver:
    type_name = "material_color"

    def list_options(
        self,
        db: Session,
        *,
        template: Product,
        routing_material: RoutingOperationMaterial,
    ) -> list[AxisOption]:
        """Return MaterialColor combos available for the variable material's material_type."""
        component = (
            db.query(Product).filter(Product.id == routing_material.component_id).first()
        )
        if not component or component.material_type_id is None:
            return []

        rows = (
            db.query(MaterialColor, MaterialType, Color)
            .join(MaterialType, MaterialColor.material_type_id == MaterialType.id)
            .join(Color, MaterialColor.color_id == Color.id)
            .filter(MaterialColor.material_type_id == component.material_type_id)
            .all()
        )

        return [
            AxisOption(
                value={
                    "material_type_id": mt.id,
                    "color_id": c.id,
                    "material_type_code": mt.code,
                    "color_code": c.code,
                },
                label=f"{mt.name} — {c.name}",
                preview_sku=f"{template.sku}-{mt.code}-{c.code}"[:50],
                preview_name=f"{template.name} - {mt.name} {c.name}"[:255],
                extras={"color_hex": c.hex_code},
            )
            for (_mc, mt, c) in rows
        ]

    def resolve_to_component(self, db: Session, *, value: dict) -> Product:
        """Find the active supply Product for this material+color combo."""
        mat_type_id = value.get("material_type_id")
        color_id = value.get("color_id")
        if mat_type_id is None or color_id is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    "material_color value missing material_type_id or color_id "
                    f"(got: {value!r})"
                ),
            )
        product = (
            db.query(Product)
            .filter(
                Product.material_type_id == mat_type_id,
                Product.color_id == color_id,
                Product.active.is_(True),
            )
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No active product found for material_type_id={mat_type_id}, "
                    f"color_id={color_id}"
                ),
            )
        return product

    def synthesize_legacy(self, *, variant_metadata_legacy: dict) -> dict | None:
        """Lift legacy {material_type_id, color_id, ...} into v2 axis_selections.

        Implementation deferred to Task 3. Return None for now — Task 3 adds
        the actual lift and a round-trip test.
        """
        return None  # placeholder; Task 3 fills in


registry.register(MaterialColorResolver())
