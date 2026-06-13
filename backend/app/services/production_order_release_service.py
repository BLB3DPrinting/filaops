"""
Production Order Release Service — release gating + reservation self-heal.

Moved from production_order_service.py (DEBT-1 D2-A mechanical split). Holds
release_production_order, its gating logic, and the release-time self-heal
helpers. No behavior change.
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.logging_config import get_logger
from app.models import (
    ProductionOrder,
    Product,
)
from app.models.inventory import InventoryTransaction

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Private helpers for release_production_order
# ---------------------------------------------------------------------------

def _has_active_reservation(
    db: Session,
    production_order_id: int,
    component_id: int,
) -> bool:
    """Return True if there is a net-positive ledger reservation for
    (production_order_id, component_id), i.e. at least one 'reservation'
    transaction exists and its quantity exceeds any 'reservation_release'
    transactions for the same pair.
    """
    from sqlalchemy import func as sqlfunc
    from sqlalchemy import case

    net = (
        db.query(
            sqlfunc.coalesce(
                sqlfunc.sum(
                    case(
                        (InventoryTransaction.transaction_type == "reservation",
                         InventoryTransaction.quantity),
                        else_=Decimal("0"),
                    )
                    - case(
                        (InventoryTransaction.transaction_type == "reservation_release",
                         InventoryTransaction.quantity),
                        else_=Decimal("0"),
                    )
                ),
                Decimal("0"),
            )
        )
        .filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == production_order_id,
            InventoryTransaction.product_id == component_id,
            InventoryTransaction.transaction_type.in_(
                ["reservation", "reservation_release"]
            ),
        )
        .scalar()
    )
    return (net or Decimal("0")) > Decimal("0")


def _maybe_backfill_op_material_allocation(
    db: Session,
    order: "ProductionOrder",
) -> None:
    """Self-heal: if active ledger reservations exist for *order* but all
    op-material rows have quantity_allocated=0, rebuild from the ledger.

    This repairs the 17 draft WOs created before fix #715 the moment an
    operator tries to release them — no data migration needed.  The heal
    is idempotent: healthy orders (rows already populated) are untouched.
    """
    has_op_mats = any(
        mat
        for op in order.operations
        for mat in op.materials
    )
    if not has_op_mats:
        return

    all_zero = all(
        Decimal(str(mat.quantity_allocated)) == Decimal("0")
        for op in order.operations
        for mat in op.materials
    )
    if not all_zero:
        # Already populated — nothing to do.
        return

    # Check if any active reservation ledger rows exist for this order.
    has_reservations = (
        db.query(InventoryTransaction.id)
        .filter(
            InventoryTransaction.reference_type == "production_order",
            InventoryTransaction.reference_id == order.id,
            InventoryTransaction.transaction_type == "reservation",
        )
        .first()
    ) is not None

    if not has_reservations:
        return

    # Import here to avoid circular dependency at module level.
    from app.services.inventory_service import _backfill_op_material_from_ledger
    _backfill_op_material_from_ledger(db, order)
    # Flush so the gate check below (and any subsequent db.refresh) sees the
    # updated rows immediately — the surrounding call-site holds the transaction.
    db.flush()


def _maybe_reserve_missing_materials(
    db: Session,
    order: "ProductionOrder",
    user_email: str,
) -> None:
    """RESERVE-1 level-2 self-heal: reserve at release time when reservation
    never ran or under-ran.

    Level 1 (_maybe_backfill_op_material_allocation) only repairs ledger↔row
    desync — it cannot help when the ledger itself has no (or insufficient)
    reservations.  That happens for brownfield orders whose creation-time
    reservation walked an empty/production-line-less BOM while the materials
    actually live on the routing (op-material rows).

    If any op-material row still shows quantity_allocated < quantity_required
    after level 1, the net ledger reservation for that component is missing
    or short, so run reserve_production_materials — it is delta-safe
    (RESERVE-1) and tops up only the shortfall.  HARD-5 semantics are
    preserved: zero-stock components reserve ahead of receipt (flag, not
    block) and release proceeds.
    """
    rows = [mat for op in order.operations for mat in op.materials]
    if not rows:
        return

    shortfall_rows = [
        mat for mat in rows
        if Decimal(str(mat.quantity_allocated or 0))
        < Decimal(str(mat.quantity_required or 0))
    ]
    if not shortfall_rows:
        return

    never_ran = all(
        Decimal(str(mat.quantity_allocated or 0)) == Decimal("0")
        for mat in rows
    )
    if never_ran:
        logger.info(
            "RESERVE-1 self-heal: reservation had never run for PO#%s — "
            "reserving at release",
            order.code,
        )
    else:
        logger.info(
            "RESERVE-1 self-heal: reservation under-ran for PO#%s "
            "(%d op-material row(s) short) — topping up at release",
            order.code,
            len(shortfall_rows),
        )

    from app.services.inventory_service import reserve_production_materials
    reserve_production_materials(db, order, created_by=user_email)
    # Flush so the gate re-check reads the updated rows.
    db.flush()


def release_production_order(
    db: Session,
    order_id: int,
    user_email: str,
    force: bool = False,
) -> ProductionOrder:
    """
    Release a production order for manufacturing.

    Validates material availability and transitions status to 'released'.
    """
    from app.services.production_order_service import get_production_order

    order = get_production_order(db, order_id)

    # Idempotent: already released is a no-op
    if order.status == "released":
        return order

    # Allow releasing from draft, scheduled, or on_hold (resume from hold)
    if order.status not in ["draft", "scheduled", "on_hold"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot release order in {order.status} status"
        )

    # Self-heal level 1: if the order has active ledger reservations but
    # op-material rows still show quantity_allocated=0, the reservation sync
    # was skipped (e.g. orders created before fix #715, or a future code path
    # that calls reserve_production_materials without the sync step).
    # Backfill now so the gate below reads truth rather than always-zero.
    _maybe_backfill_op_material_allocation(db, order)

    # Check material availability unless forced
    if not force:
        # Self-heal level 2 (RESERVE-1): if rows still show a shortfall after
        # the ledger backfill, reservation never ran or under-ran (e.g. pure
        # routing-material products whose creation-time reservation walked an
        # empty BOM).  reserve_production_materials is delta-safe, so this
        # tops up only the missing quantities, then the gate re-checks.
        _maybe_reserve_missing_materials(db, order, user_email)

        blocking_issues = []
        for op in order.operations:
            for mat in op.materials:
                if mat.quantity_allocated < mat.quantity_required:
                    component = db.query(Product).filter(
                        Product.id == mat.component_id
                    ).first()
                    sku = component.sku if component else f"ID:{mat.component_id}"
                    # Distinguish "never reserved" from "genuinely short"
                    # by checking whether any active reservations exist for
                    # this (order, component) pair.
                    has_any_reservation = _has_active_reservation(
                        db, order.id, mat.component_id
                    )
                    if has_any_reservation:
                        blocking_issues.append({
                            "component_sku": sku,
                            "operation": op.operation_name,
                            "needed": float(mat.quantity_required),
                            "reserved": float(mat.quantity_allocated),
                            "reason": "insufficient_stock",
                        })
                    else:
                        blocking_issues.append({
                            "component_sku": sku,
                            "operation": op.operation_name,
                            "needed": float(mat.quantity_required),
                            "reserved": 0.0,
                            "reason": "not_allocated",
                        })

        if blocking_issues:
            not_allocated = [
                b for b in blocking_issues if b["reason"] == "not_allocated"
            ]
            short = [
                b for b in blocking_issues if b["reason"] == "insufficient_stock"
            ]

            if not_allocated and not short:
                # Nearly unreachable after the level-2 self-heal above: it
                # fires only when reservation itself errored for every
                # shortfall component (e.g. UOMConversionError skip).
                message = (
                    "Material reservation failed during release — check "
                    "component/UOM configuration"
                )
            else:
                parts = []
                for b in short:
                    parts.append(
                        f"Insufficient stock for {b['component_sku']}: "
                        f"need {b['needed']}, reserved {b['reserved']}"
                    )
                message = "; ".join(parts) if parts else "Cannot release: material shortages detected"

            raise HTTPException(
                status_code=400,
                detail={
                    "message": message,
                    "shortages": blocking_issues,
                    "hint": "Use force=true to release anyway",
                }
            )

    order.status = "released"
    order.released_at = datetime.now(timezone.utc)

    logger.info(f"Production order {order.code} released by {user_email}")

    return order
