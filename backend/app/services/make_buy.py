"""
Make-vs-buy: the one rule for "do we make this product in-house or buy it?"

Used by MRP planned-order generation, the sub-assembly cascade gate and the
requirement-explosion recursion gates. Print-batch plan stage S0; Cortex
observations #255 and #256.

THE RULE
--------
A product is MADE when either

* ``product.has_bom`` is true, or
* it has an active ``Routing`` with at least one ``RoutingOperationMaterial``
  whose ``is_cost_only`` is false (a real material consumed by a routing step).

``procurement_type == "buy"`` is a hard override: the product is BOUGHT even
when it has a BOM or routing materials.

``procurement_type == "make"`` is NOT a trigger on its own. Core's item form
defaults every new item to "make" (frontend ``ItemForm.jsx`` and
``ItemWizard.jsx``), so treating it as a trigger would turn purchased items
into production orders.

WHY
---
Core reads routing materials first and falls back to the BOM everywhere else:
requirement explosion (HARD-12), reservations, consumption and blocking
issues. Products created by PRO Intake keep their filament on the routing's
PRINT step and have ``has_bom`` false, so the one decision still keyed on
``has_bom`` alone planned them as purchases.

THE FLAG
--------
``settings.MRP_ROUTING_MAKE_BUY`` (default False). Off, ``is_made`` returns
``bool(product.has_bom)`` exactly as before; on, it applies the rule above.
``decide_make_buy`` always applies the rule, so the dry-run diff can compare
both answers without touching the flag.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.mrp import PlannedOrder
from app.models.product import Product

ORDER_TYPE_PRODUCTION = "production"
ORDER_TYPE_PURCHASE = "purchase"

# Why the rule decided what it decided (reported by the dry-run diff).
REASON_BUY_OVERRIDE = "buy_override"        # procurement_type is "buy"
REASON_BOM = "bom"                          # product.has_bom
REASON_ROUTING_MATERIALS = "routing_materials"  # active routing with real materials
REASON_NO_MAKE_SOURCE = "no_make_source"    # neither a BOM nor routing materials

# Planned-order statuses the dry-run diff looks at: the ones MRP still owns.
OPEN_PLANNED_ORDER_STATUSES = ("planned", "firmed")


@dataclass(frozen=True)
class MakeBuyDecision:
    """Outcome of the rule for one product."""

    is_made: bool
    reason: str

    @property
    def order_type(self) -> str:
        return ORDER_TYPE_PRODUCTION if self.is_made else ORDER_TYPE_PURCHASE


def routing_rule_enabled() -> bool:
    """True when MRP_ROUTING_MAKE_BUY is on."""
    return bool(get_settings().MRP_ROUTING_MAKE_BUY)


def has_routing_materials(db: Session, product_id: int) -> bool:
    """True when the product has an active routing with a non-cost-only material.

    Same test as requirement explosion uses to pick its primary source, so a
    product that explodes from its routing is also one MRP plans as made.
    """
    row = (
        db.query(RoutingOperationMaterial.id)
        .join(
            RoutingOperation,
            RoutingOperationMaterial.routing_operation_id == RoutingOperation.id,
        )
        .join(Routing, RoutingOperation.routing_id == Routing.id)
        .filter(
            Routing.product_id == product_id,
            Routing.is_active.is_(True),
            RoutingOperationMaterial.is_cost_only.is_(False),
        )
        .first()
    )
    return row is not None


def legacy_is_made(product: Product) -> bool:
    """The pre-S0 decision: made when the product has a BOM, nothing else."""
    return bool(product.has_bom)


def decide_make_buy(db: Session, product: Product) -> MakeBuyDecision:
    """Apply THE RULE (module docstring) regardless of the flag."""
    if (product.procurement_type or "").strip().lower() == "buy":
        return MakeBuyDecision(is_made=False, reason=REASON_BUY_OVERRIDE)
    if product.has_bom:
        return MakeBuyDecision(is_made=True, reason=REASON_BOM)
    if has_routing_materials(db, product.id):
        return MakeBuyDecision(is_made=True, reason=REASON_ROUTING_MATERIALS)
    return MakeBuyDecision(is_made=False, reason=REASON_NO_MAKE_SOURCE)


def is_made(db: Session, product: Product) -> bool:
    """Flag-aware decision every gate should call.

    MRP_ROUTING_MAKE_BUY off: ``legacy_is_made`` (has_bom only, no query).
    MRP_ROUTING_MAKE_BUY on: ``decide_make_buy``.
    """
    if not routing_rule_enabled():
        return legacy_is_made(product)
    return decide_make_buy(db, product).is_made


def make_buy_dry_run_diff(
    db: Session,
    statuses: Iterable[str] = OPEN_PLANNED_ORDER_STATUSES,
) -> Dict:
    """Read-only report: which products' planned orders would change type under the rule.

    Walks every planned order in *statuses*, decides make-vs-buy for its
    product both ways (today's has_bom-only test and THE RULE) and lists the
    products whose order_type differs. Writes nothing.
    """
    statuses = tuple(statuses)
    planned_orders: List[PlannedOrder] = (
        db.query(PlannedOrder)
        .filter(PlannedOrder.status.in_(statuses))
        .order_by(PlannedOrder.id)
        .all()
    )

    order_ids_by_product: Dict[int, List[int]] = {}
    for order in planned_orders:
        order_ids_by_product.setdefault(order.product_id, []).append(order.id)

    changes = []
    for product_id, order_ids in order_ids_by_product.items():
        product = db.get(Product, product_id)
        if not product:
            continue

        current_type = (
            ORDER_TYPE_PRODUCTION if legacy_is_made(product) else ORDER_TYPE_PURCHASE
        )
        decision = decide_make_buy(db, product)
        if decision.order_type == current_type:
            continue

        changes.append({
            "product_id": product.id,
            "product_sku": product.sku,
            "product_name": product.name,
            "procurement_type": product.procurement_type,
            "has_bom": bool(product.has_bom),
            "current_order_type": current_type,
            "proposed_order_type": decision.order_type,
            "reason": decision.reason,
            "planned_order_ids": order_ids,
        })

    return {
        "flag_enabled": routing_rule_enabled(),
        "statuses": list(statuses),
        "planned_orders_checked": len(planned_orders),
        "products_checked": len(order_ids_by_product),
        "changes": changes,
        "total_changes": len(changes),
    }
