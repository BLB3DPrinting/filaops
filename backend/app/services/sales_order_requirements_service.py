"""
Sales Order Requirements Service — material requirements and MRP cascade for
sales orders.

Moved verbatim from sales_order_service.py (DEBT-1 D1-A mechanical split).
"""
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.sales_order import SalesOrderLine
from app.models.product import Product
from app.models.bom import BOM
from app.models.manufacturing import Routing
from app.models.inventory import Inventory
from app.services.sales_order_shared import get_sales_order

# Statuses where material requirements are historical context rather than
# actionable demand (nothing more will be produced/shipped for this order).
TERMINAL_ORDER_STATUSES = {"completed", "cancelled", "delivered", "shipped"}


# =============================================================================
# MRP / Requirements
# =============================================================================

def get_required_orders_for_sales_order(
    db: Session,
    order_id: int,
) -> dict:
    """
    Get full MRP cascade of WOs and POs needed to fulfill a sales order.

    Recursively explodes BOMs for all line items to show:
    - Work Orders needed for sub-assemblies (make items with BOMs)
    - Purchase Orders needed for raw materials (buy items without BOMs)

    HARD-12: Now uses routing-first / BOM-fallback semantics via the canonical
    ``explode_requirements`` function.  Previously this read bom_lines ONLY,
    causing the MRP-cascade screen to disagree with the MRP engine for products
    that have both routing materials AND BOM lines.

    Returns:
        Dict with work_orders_needed, purchase_orders_needed, summary
    """
    from app.services.requirement_explosion import explode_requirements as _explode

    order = get_sales_order(db, order_id)

    work_orders_needed = []
    purchase_orders_needed = []
    top_level_products = []

    def _process_product(product_id: int, qty: Decimal, parent_sku: Optional[str]) -> None:
        """Explode one product and bucket its requirements into WOs/POs."""
        reqs = _explode(db=db, product_id=product_id, quantity=qty)
        for req in reqs:
            component = db.get(Product, req.product_id)
            if not component:
                continue

            inv_result = db.query(
                func.sum(Inventory.available_quantity)
            ).filter(Inventory.product_id == req.product_id).scalar()
            available_qty = Decimal(str(inv_result or 0))
            shortage_qty = max(Decimal("0"), req.gross_quantity - available_qty)

            if shortage_qty <= Decimal("0"):
                continue

            order_info = {
                "product_id": component.id,
                "product_sku": component.sku,
                "product_name": component.name,
                "unit": component.unit,
                "required_qty": float(req.gross_quantity),
                "available_qty": float(available_qty),
                "order_qty": float(shortage_qty),
                "bom_level": req.bom_level,
                "has_bom": component.has_bom or False,
                "parent_sku": parent_sku,
            }

            if component.has_bom:
                work_orders_needed.append(order_info)
            else:
                purchase_orders_needed.append(order_info)

    # Process based on order type
    if order.order_type == "line_item":
        lines = db.query(SalesOrderLine).options(
            joinedload(SalesOrderLine.product)
        ).filter(
            SalesOrderLine.sales_order_id == order_id
        ).all()

        for line in lines:
            product = line.product
            if not product:
                continue

            qty = Decimal(str(line.quantity or 1))

            if product.has_bom:
                inv_result = db.query(
                    func.sum(Inventory.available_quantity)
                ).filter(Inventory.product_id == product.id).scalar()
                available_qty = Decimal(str(inv_result or 0))
                shortage_qty = max(Decimal("0"), qty - available_qty)

                if shortage_qty > 0:
                    top_level_products.append({
                        "product_id": product.id,
                        "product_sku": product.sku,
                        "product_name": product.name,
                        "order_qty": float(shortage_qty),
                        "has_bom": True,
                    })

            _process_product(product.id, qty, product.sku)

    elif order.order_type == "quote_based" and order.product_id:
        product = db.query(Product).filter(Product.id == order.product_id).first()
        if product:
            qty = Decimal(str(order.quantity or 1))

            if product.has_bom:
                inv_result = db.query(
                    func.sum(Inventory.available_quantity)
                ).filter(Inventory.product_id == product.id).scalar()
                available_qty = Decimal(str(inv_result or 0))
                shortage_qty = max(Decimal("0"), qty - available_qty)

                if shortage_qty > 0:
                    top_level_products.append({
                        "product_id": product.id,
                        "product_sku": product.sku,
                        "product_name": product.name,
                        "order_qty": float(shortage_qty),
                        "has_bom": True,
                    })

            _process_product(product.id, qty, product.sku)

    # Aggregate duplicate materials
    aggregated_pos: dict = {}
    for po in purchase_orders_needed:
        key = po["product_id"]
        if key in aggregated_pos:
            aggregated_pos[key]["order_qty"] += po["order_qty"]
            aggregated_pos[key]["required_qty"] += po["required_qty"]
        else:
            aggregated_pos[key] = po.copy()
            aggregated_pos[key]["sources"] = []
        aggregated_pos[key]["sources"].append(po.get("parent_sku", "direct"))

    return {
        "order_id": order_id,
        "order_number": order.order_number,
        "order_type": order.order_type,
        "top_level_work_orders": top_level_products,
        "sub_assembly_work_orders": work_orders_needed,
        "purchase_orders_needed": list(aggregated_pos.values()),
        "summary": {
            "top_level_wos": len(top_level_products),
            "sub_assembly_wos": len(work_orders_needed),
            "purchase_orders": len(aggregated_pos),
            "total_orders_needed": len(top_level_products) + len(work_orders_needed) + len(aggregated_pos),
        },
    }


def get_material_requirements(
    db: Session,
    order_id: int,
) -> dict:
    """
    Get material requirements for a sales order.

    HARD-12: Delegates explosion to the canonical ``explode_requirements``
    function (routing-first / BOM-fallback semantics), replacing the inline
    ``process_product`` closure that duplicated mrp.py's logic.

    The add_requirement / netting / supply-projection logic is retained here
    because it formats the response dict used by the SalesOrder detail panel
    and is not part of the explosion concern.

    Returns:
        Dict with requirements list and summary
    """
    from app.services.supply_netting import get_projected_available
    from app.services.requirement_explosion import explode_requirements as _explode

    order = get_sales_order(db, order_id)

    seen_products = {}

    def add_requirement(
        component: Product,
        qty_required: Decimal,
        unit: str,
        operation_code: Optional[str],
        material_source: str
    ):
        """Add a material requirement, aggregating duplicates."""
        key = component.id
        # HARD-6: use projected balance (available + open-PO supply)
        proj = get_projected_available(db, component.id)
        qty_available = proj.available
        qty_short_projected = max(Decimal("0"), qty_required - proj.projected)
        qty_short_now = max(Decimal("0"), qty_required - qty_available)
        has_incoming = proj.incoming_qty > Decimal("0")
        covered_by_incoming = (qty_short_now > Decimal("0")) and (qty_short_projected == Decimal("0")) and has_incoming
        incoming_details = None
        if proj.best_detail:
            detail = proj.best_detail
            incoming_details = {
                "purchase_order_id": detail.purchase_order_id,
                "purchase_order_code": detail.po_number,
                "quantity": float(detail.quantity),
                "expected_date": detail.expected_date.isoformat() if detail.expected_date else None,
                "status": detail.status,
                "covers_shortage": covered_by_incoming,
            }

        # Check if component can be manufactured
        has_bom = db.query(BOM).filter(
            BOM.product_id == component.id,
            BOM.active.is_(True)
        ).first() is not None

        has_routing = db.query(Routing).filter(
            Routing.product_id == component.id,
            Routing.is_active.is_(True)
        ).first() is not None

        has_bom = has_bom or has_routing

        if key in seen_products:
            existing = seen_products[key]
            existing["quantity_required"] += qty_required
            # Re-net projected shortage against (potentially larger) aggregated requirement
            existing["quantity_short"] = max(
                Decimal("0"),
                existing["quantity_required"] - proj.projected,
            )
            existing["quantity_short_now"] = max(
                Decimal("0"),
                existing["quantity_required"] - qty_available,
            )
            existing["covered_by_incoming"] = (
                existing["quantity_short_now"] > Decimal("0")
                and existing["quantity_short"] == Decimal("0")
                and has_incoming
            )
        else:
            seen_products[key] = {
                "product_id": component.id,
                "product_sku": component.sku,
                "product_name": component.name,
                "unit": unit or component.unit or "EA",
                "quantity_required": qty_required,
                "quantity_available": qty_available,
                "quantity_projected": float(proj.projected),
                "quantity_incoming": float(proj.incoming_qty),
                # shortage is net of incoming PO supply (HARD-6)
                "quantity_short": qty_short_projected,
                "quantity_short_now": float(qty_short_now),
                "covered_by_incoming": covered_by_incoming,
                "operation_code": operation_code,
                "material_source": material_source,
                "has_incoming_supply": has_incoming,
                "incoming_supply_details": incoming_details,
                "has_bom": has_bom
            }

    def process_product(product_id: int, quantity: Decimal):
        """Process material requirements for a product using the canonical explosion."""
        reqs = _explode(db=db, product_id=product_id, quantity=quantity)
        for req in reqs:
            component = db.get(Product, req.product_id)
            if not component:
                continue
            # material_source: "routing" if from a routing, "bom" otherwise.
            # ComponentRequirement doesn't carry this; derive from whether any
            # routing exists for the parent.  For the detail panel we use "routing"
            # when a routing was found, "bom" otherwise — the canonical function
            # already applied routing-first precedence so we just tag accordingly.
            # The operation_code is unavailable at this aggregation layer because
            # explode_requirements flattens multi-operation materials; tag as None.
            add_requirement(
                component=component,
                qty_required=req.gross_quantity,
                unit=component.unit or "EA",
                operation_code=None,
                material_source="routing_or_bom",
            )

    # Process based on order type
    if order.order_type == "line_item":
        lines = db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == order_id
        ).all()

        for line in lines:
            if line.product_id:
                qty = Decimal(str(line.quantity or 1))
                process_product(line.product_id, qty)

    elif order.order_type == "quote_based" and order.product_id:
        qty = Decimal(str(order.quantity or 1))
        process_product(order.product_id, qty)

    requirements = list(seen_products.values())

    total_materials = len(requirements)
    # HARD-6: quantity_short is now the NET projected shortage (after POs)
    materials_short = sum(1 for r in requirements if r["quantity_short"] > 0)
    materials_with_incoming = sum(1 for r in requirements if r["has_incoming_supply"])
    materials_covered_by_incoming = sum(1 for r in requirements if r.get("covered_by_incoming"))

    # LEGACY-1: requirements are re-exploded against CURRENT stock on every
    # call. For terminal (or deliberately short-closed) orders that is
    # historical context, not an actionable shortage — the goods already
    # shipped or never will. Flag it so the UI stops raising live shortage
    # alerts while still showing the data for reference.
    historical = (
        order.status in TERMINAL_ORDER_STATUSES
        or bool(getattr(order, "closed_short", False))
    )

    return {
        "sales_order_id": order.id,
        "order_number": order.order_number,
        "requirements": requirements,
        "summary": {
            "total_materials": total_materials,
            "materials_available": total_materials - materials_short,
            "materials_short": materials_short,
            "materials_with_incoming_supply": materials_with_incoming,
            # short now but covered by open POs (expedite vs create-PO distinction)
            "materials_covered_by_incoming": materials_covered_by_incoming,
            "can_fulfill": materials_short == 0,
            "has_shortages": materials_short > 0,
            "historical": historical,
        }
    }
