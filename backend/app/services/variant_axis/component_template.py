"""ComponentTemplateResolver — variants are children via parent_product_id.

RULE 1 from the strategic plan §2: this resolver MUST NOT branch on
item_type. The query is identical for manufactured, component, and
supply templates: parent_product_id == template.id AND active.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Product
from app.models.manufacturing import RoutingOperationMaterial
from app.services.variant_axis import registry
from app.services.variant_axis.types import AxisOption


class ComponentTemplateResolver:
    type_name = "component_template"

    def list_options(
        self,
        db: Session,
        *,
        template: Product,  # unused for this resolver but part of Protocol
        routing_material: RoutingOperationMaterial,
    ) -> list[AxisOption]:
        """Return active children of the variable BOM line's component."""
        children = (
            db.query(Product)
            .filter(
                Product.parent_product_id == routing_material.component_id,
                Product.active.is_(True),
            )
            .order_by(Product.sku)
            .all()
        )
        return [
            AxisOption(
                value={
                    "component_id": c.id,
                    "component_sku": c.sku,
                    "component_name": c.name,
                },
                label=c.name,
                preview_sku=c.sku,
                preview_name=c.name,
            )
            for c in children
        ]

    def resolve_to_component(self, db: Session, *, value: dict) -> Product:
        cid = value.get("component_id")
        if cid is None:
            raise HTTPException(
                status_code=400,
                detail=f"component_template value missing component_id (got: {value!r})",
            )
        product = (
            db.query(Product)
            .filter(Product.id == cid, Product.active.is_(True))
            .first()
        )
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"No active product found with id={cid}",
            )
        return product

    def synthesize_legacy(self, *, variant_metadata_legacy: dict) -> dict | None:
        return None


registry.register(ComponentTemplateResolver())
