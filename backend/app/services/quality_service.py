"""
Quality Management Service

Provides inspection queue, quality metrics, and scrap analysis
by aggregating data from production orders, scrap records, scrap reasons,
and related product data.
No new models — reads existing QC data from ProductionOrder, ScrapRecord,
ScrapReason, etc.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, case, literal
from sqlalchemy.orm import Session, joinedload

from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ScrapRecord,
)
from app.models.scrap_reason import ScrapReason


def get_inspection_queue(
    db: Session,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """
    Get production orders awaiting QC inspection.

    Returns orders with qc_status in ('pending', 'in_progress'),
    sorted by priority ascending (1 is highest) then due_date (earliest first).
    """
    query = (
        db.query(ProductionOrder)
        .options(joinedload(ProductionOrder.product))
        .filter(ProductionOrder.qc_status.in_(["pending", "in_progress"]))
        .order_by(ProductionOrder.priority.asc(), ProductionOrder.due_date.asc().nullslast())
    )

    total = query.count()
    orders = query.offset(offset).limit(limit).all()

    items = []
    for o in orders:
        items.append({
            "id": o.id,
            "code": o.code,
            "product_name": o.product.name if o.product else None,
            "product_sku": o.product.sku if o.product else None,
            "quantity_ordered": float(o.quantity_ordered) if o.quantity_ordered else 0,
            "quantity_completed": float(o.quantity_completed) if o.quantity_completed else 0,
            "qc_status": o.qc_status,
            "priority": o.priority,
            "due_date": o.due_date.isoformat() if o.due_date else None,
            "status": o.status,
        })

    return {"items": items, "total": total}


def get_quality_metrics(db: Session, days: int = 30) -> dict:
    """
    Calculate quality metrics for the given period.

    Returns:
    - total_inspections: Count of orders with a QC result in the period
    - passed: Orders that passed QC
    - failed: Orders that failed QC
    - first_pass_yield: passed / (passed + failed) as a percentage
    - pending_inspections: Current queue depth
    - scrap_rate: scrapped qty / total completed qty as a percentage
    - total_scrapped_cost: Sum of scrap costs in the period
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Count inspections by result (orders inspected within the period)
    result_counts = (
        db.query(
            ProductionOrder.qc_status,
            func.count(ProductionOrder.id).label("cnt"),
        )
        .filter(
            ProductionOrder.qc_inspected_at >= cutoff,
            ProductionOrder.qc_status.in_(["passed", "failed", "waived"]),
        )
        .group_by(ProductionOrder.qc_status)
        .all()
    )

    counts = {row.qc_status: row.cnt for row in result_counts}
    passed = counts.get("passed", 0)
    failed = counts.get("failed", 0)
    waived = counts.get("waived", 0)
    total_inspections = passed + failed + waived

    first_pass_yield = (
        round((passed / total_inspections) * 100, 1)
        if total_inspections > 0
        else None
    )

    # Current pending queue depth
    pending = (
        db.query(func.count(ProductionOrder.id))
        .filter(ProductionOrder.qc_status.in_(["pending", "in_progress"]))
        .scalar()
    ) or 0

    # Scrap rate: total scrapped qty / total completed qty (period)
    qty_agg = (
        db.query(
            func.coalesce(func.sum(ProductionOrder.quantity_completed), 0).label("completed"),
            func.coalesce(func.sum(ProductionOrder.quantity_scrapped), 0).label("scrapped"),
        )
        .filter(
            ProductionOrder.actual_end >= cutoff,
            ProductionOrder.status.in_(["completed", "closed", "qc_hold", "scrapped"]),
        )
        .first()
    )

    completed_qty = float(qty_agg.completed) if qty_agg else 0
    scrapped_qty = float(qty_agg.scrapped) if qty_agg else 0

    scrap_rate = (
        round((scrapped_qty / completed_qty) * 100, 1)
        if completed_qty > 0
        else None
    )

    # Total scrap cost in period
    total_scrap_cost = (
        db.query(func.coalesce(func.sum(ScrapRecord.total_cost), 0))
        .filter(ScrapRecord.created_at >= cutoff)
        .scalar()
    )

    return {
        "period_days": days,
        "total_inspections": total_inspections,
        "passed": passed,
        "failed": failed,
        "first_pass_yield": first_pass_yield,
        "pending_inspections": pending,
        "scrap_rate": scrap_rate,
        "total_scrapped_cost": float(total_scrap_cost) if total_scrap_cost else 0,
    }


def get_recent_inspections(db: Session, limit: int = 20) -> list:
    """
    Get recently completed QC inspections, newest first.
    """
    orders = (
        db.query(ProductionOrder)
        .options(joinedload(ProductionOrder.product))
        .filter(
            ProductionOrder.qc_status.in_(["passed", "failed", "waived"]),
            ProductionOrder.qc_inspected_at.isnot(None),
        )
        .order_by(ProductionOrder.qc_inspected_at.desc())
        .limit(limit)
        .all()
    )

    items = []
    for o in orders:
        items.append({
            "id": o.id,
            "code": o.code,
            "product_name": o.product.name if o.product else None,
            "quantity_ordered": float(o.quantity_ordered) if o.quantity_ordered else 0,
            "quantity_completed": float(o.quantity_completed) if o.quantity_completed else 0,
            "quantity_scrapped": float(o.quantity_scrapped) if o.quantity_scrapped else 0,
            "qc_status": o.qc_status,
            "qc_notes": o.qc_notes,
            "qc_inspected_by": o.qc_inspected_by,
            "qc_inspected_at": o.qc_inspected_at.isoformat() if o.qc_inspected_at else None,
        })

    return items


def get_scrap_summary(db: Session, days: int = 30) -> list:
    """
    Get scrap breakdown grouped by reason for the given period.

    Aggregates at the scrap-event level (distinct PO + operation + reason)
    so that quantities reflect finished-goods pieces, not component UOM.
    ScrapRecord.quantity is in component units (e.g. grams); the
    operation-level quantity_scrapped is in finished-goods units.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Inner query: one row per distinct scrap event (PO + op + reason),
    # pulling the FG qty from the operation when available, falling back
    # to ScrapRecord.quantity when there's no operation link.
    # When production_operation_id is NULL, each ScrapRecord is its own
    # event, so we add a discriminator to prevent them from collapsing.
    event_discriminator = case(
        (ScrapRecord.production_operation_id.is_(None), ScrapRecord.id),
        else_=literal(0),
    )
    fg_qty_expr = func.coalesce(
        func.min(ProductionOrderOperation.quantity_scrapped),
        func.sum(ScrapRecord.quantity),
    )

    scrap_event = (
        db.query(
            ScrapRecord.scrap_reason_id,
            ScrapRecord.production_order_id,
            ScrapRecord.production_operation_id,
            fg_qty_expr.label("fg_qty"),
            func.sum(ScrapRecord.total_cost).label("event_cost"),
        )
        .outerjoin(
            ProductionOrderOperation,
            ProductionOrderOperation.id == ScrapRecord.production_operation_id,
        )
        .filter(ScrapRecord.created_at >= cutoff)
        .group_by(
            ScrapRecord.scrap_reason_id,
            ScrapRecord.production_order_id,
            ScrapRecord.production_operation_id,
            event_discriminator,
        )
        .subquery()
    )

    rows = (
        db.query(
            func.coalesce(ScrapReason.code, "UNCAT").label("code"),
            func.coalesce(ScrapReason.name, "Uncategorized").label("name"),
            func.count().label("count"),
            func.coalesce(func.sum(scrap_event.c.fg_qty), 0).label("total_quantity"),
            func.coalesce(func.sum(scrap_event.c.event_cost), 0).label("total_cost"),
        )
        .select_from(scrap_event)
        .outerjoin(ScrapReason, scrap_event.c.scrap_reason_id == ScrapReason.id)
        .group_by(ScrapReason.code, ScrapReason.name)
        .order_by(func.sum(scrap_event.c.event_cost).desc())
        .all()
    )

    return [
        {
            "reason_code": r.code,
            "reason_name": r.name,
            "count": r.count,
            "total_quantity": float(r.total_quantity),
            "total_cost": float(r.total_cost),
        }
        for r in rows
    ]
