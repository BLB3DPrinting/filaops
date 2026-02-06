"""
Command Center service for dashboard data.

Aggregates action items and summary statistics for the "What do I need to do NOW?" view.
"""
from datetime import datetime, timezone, timedelta
from typing import List, Dict
from collections import defaultdict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.production_order import ProductionOrder, ProductionOrderOperation
from app.models.sales_order import SalesOrder
from app.models.manufacturing import Resource
from app.models.work_center import WorkCenter
from app.models.product import Product
from app.services.blocking_issues import get_production_order_blocking_issues
from app.schemas.command_center import (
    ActionItem,
    ActionItemType,
    ActionItemsResponse,
    SuggestedAction,
    TodaySummary,
    ResourceStatus,
    ResourcesResponse,
    OperationSummary,
)


def get_action_items(db: Session) -> ActionItemsResponse:
    """
    Get prioritized list of action items requiring attention.

    Returns items sorted by priority (critical first) then by age (oldest first).
    """
    items: List[ActionItem] = []

    # 1. Blocked Production Orders (Priority 1 - Critical)
    blocked_po_items = _get_blocked_production_orders(db)
    items.extend(blocked_po_items)

    # 2. Overdue Sales Orders (Priority 1 - Critical)
    overdue_so_items = _get_overdue_sales_orders(db)
    items.extend(overdue_so_items)

    # 3. Due Today Sales Orders (Priority 2 - High)
    due_today_items = _get_due_today_sales_orders(db)
    items.extend(due_today_items)

    # 4. Overrunning Operations (Priority 3 - Medium)
    overrunning_items = _get_overrunning_operations(db)
    items.extend(overrunning_items)

    # 5. Idle Resources with Work Waiting (Priority 4 - Low)
    idle_resource_items = _get_idle_resources_with_work(db)
    items.extend(idle_resource_items)

    # Sort by priority, then by created_at (oldest first)
    items.sort(key=lambda x: (x.priority, x.created_at or datetime.min))

    # Build counts by type
    counts_by_type: Dict[str, int] = defaultdict(int)
    for item in items:
        counts_by_type[item.type.value] += 1

    return ActionItemsResponse(
        items=items,
        total_count=len(items),
        counts_by_type=dict(counts_by_type)
    )


def _get_blocked_production_orders(db: Session) -> List[ActionItem]:
    """Get production orders blocked by material shortages."""
    items = []

    # Get active production orders
    active_pos = db.query(ProductionOrder).filter(
        ProductionOrder.status.in_(['released', 'in_progress', 'scheduled'])
    ).all()

    for po in active_pos:
        blocking = get_production_order_blocking_issues(db, po.id)
        if blocking and not blocking.status_summary.can_produce:
            # Build description from first material issue
            desc = "Material issues detected"
            if blocking.material_issues:
                first_issue = blocking.material_issues[0]
                desc = f"Shortage: {first_issue.product_sku} (need {first_issue.quantity_short} more)"

            # Build suggested actions
            suggested = [
                SuggestedAction(
                    label="View Order",
                    url=f"/admin/production/{po.id}",
                    action_type="navigate"
                )
            ]

            # Add resolution actions from blocking analysis
            for action in blocking.resolution_actions[:2]:  # Top 2
                suggested.append(SuggestedAction(
                    label=action.action,
                    url=f"/admin/{action.reference_type.replace('_', '-')}s/{action.reference_id}",
                    action_type="navigate"
                ))

            items.append(ActionItem(
                id=f"blocked_po_{po.id}",
                type=ActionItemType.BLOCKED_PO,
                priority=1,
                title=f"{po.code} blocked",
                description=desc,
                entity_type="production_order",
                entity_id=po.id,
                entity_code=po.code,
                suggested_actions=suggested,
                created_at=po.created_at,
                metadata={
                    "blocking_count": str(blocking.status_summary.blocking_count),
                    "status": po.status
                }
            ))

    return items


def _get_overdue_sales_orders(db: Session) -> List[ActionItem]:
    """Get sales orders past their due date that haven't shipped."""
    items = []
    now = datetime.now(timezone.utc)

    overdue_orders = db.query(SalesOrder).filter(
        SalesOrder.status.in_(['confirmed', 'in_production', 'ready_to_ship']),
        SalesOrder.estimated_completion_date.isnot(None),
        SalesOrder.estimated_completion_date < now,
        SalesOrder.shipped_at.is_(None)
    ).all()

    for so in overdue_orders:
        # estimated_completion_date is naive (no tz); compare with naive now
        ecd = so.estimated_completion_date
        if ecd.tzinfo is None:
            days_overdue = (now.replace(tzinfo=None) - ecd).days
        else:
            days_overdue = (now - ecd).days

        items.append(ActionItem(
            id=f"overdue_so_{so.id}",
            type=ActionItemType.OVERDUE_SO,
            priority=1,
            title=f"{so.order_number} overdue",
            description=f"Due {days_overdue} day{'s' if days_overdue != 1 else ''} ago - {so.status}",
            entity_type="sales_order",
            entity_id=so.id,
            entity_code=so.order_number,
            suggested_actions=[
                SuggestedAction(
                    label="View Order",
                    url=f"/admin/orders/{so.id}",
                    action_type="navigate"
                ),
                SuggestedAction(
                    label="View Production",
                    url=f"/admin/production?so_id={so.id}",
                    action_type="navigate"
                )
            ],
            created_at=so.estimated_completion_date,
            metadata={
                "days_overdue": str(days_overdue),
                "customer": so.customer.company_name if so.customer else "Unknown"
            }
        ))

    return items


def _get_due_today_sales_orders(db: Session) -> List[ActionItem]:
    """Get sales orders due today that haven't shipped."""
    items = []
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    due_today = db.query(SalesOrder).filter(
        SalesOrder.status.in_(['confirmed', 'in_production', 'ready_to_ship']),
        SalesOrder.estimated_completion_date >= today_start,
        SalesOrder.estimated_completion_date < today_end,
        SalesOrder.shipped_at.is_(None)
    ).all()

    for so in due_today:
        items.append(ActionItem(
            id=f"due_today_so_{so.id}",
            type=ActionItemType.DUE_TODAY_SO,
            priority=2,
            title=f"{so.order_number} due today",
            description=f"Status: {so.status}",
            entity_type="sales_order",
            entity_id=so.id,
            entity_code=so.order_number,
            suggested_actions=[
                SuggestedAction(
                    label="View Order",
                    url=f"/admin/orders/{so.id}",
                    action_type="navigate"
                )
            ],
            created_at=so.created_at,
            metadata={
                "status": so.status,
                "customer": so.customer.company_name if so.customer else "Unknown"
            }
        ))

    return items


def _get_overrunning_operations(db: Session) -> List[ActionItem]:
    """Get operations that have exceeded their estimated time by 2x."""
    items = []
    now = datetime.now(timezone.utc)

    running_ops = db.query(ProductionOrderOperation).filter(
        ProductionOrderOperation.status == 'running',
        ProductionOrderOperation.actual_start.isnot(None)
    ).all()

    for op in running_ops:
        # Calculate elapsed time
        elapsed_minutes = (now - op.actual_start).total_seconds() / 60
        planned_minutes = float(op.planned_setup_minutes or 0) + float(op.planned_run_minutes or 0)

        # Only alert if running >2x planned time (and planned > 0)
        if planned_minutes > 0 and elapsed_minutes > (planned_minutes * 2):
            # Get production order for context
            po = db.query(ProductionOrder).filter(
                ProductionOrder.id == op.production_order_id
            ).first()

            overrun_pct = int((elapsed_minutes / planned_minutes - 1) * 100)

            items.append(ActionItem(
                id=f"overrunning_op_{op.id}",
                type=ActionItemType.OVERRUNNING_OP,
                priority=3,
                title=f"{po.code if po else 'Unknown'} Op {op.sequence} overrunning",
                description=f"{int(elapsed_minutes)}min elapsed vs {int(planned_minutes)}min planned (+{overrun_pct}%)",
                entity_type="operation",
                entity_id=op.id,
                entity_code=op.operation_code,
                suggested_actions=[
                    SuggestedAction(
                        label="View Production Order",
                        url=f"/admin/production/{op.production_order_id}",
                        action_type="navigate"
                    )
                ],
                created_at=op.actual_start,
                metadata={
                    "production_order_id": str(op.production_order_id),
                    "elapsed_minutes": str(int(elapsed_minutes)),
                    "planned_minutes": str(int(planned_minutes))
                }
            ))

    return items


def _get_idle_resources_with_work(db: Session) -> List[ActionItem]:
    """Get resources that are idle but have pending work in their work center."""
    items = []

    # Get all active resources
    resources = db.query(Resource).filter(
        Resource.is_active.is_(True),
        Resource.status == 'available'
    ).all()

    for resource in resources:
        # Check if resource has any running operations
        running_op = db.query(ProductionOrderOperation).filter(
            ProductionOrderOperation.resource_id == resource.id,
            ProductionOrderOperation.status == 'running'
        ).first()

        if running_op:
            continue  # Not idle

        # Check if there are pending operations for this work center
        pending_count = db.query(ProductionOrderOperation).filter(
            ProductionOrderOperation.work_center_id == resource.work_center_id,
            ProductionOrderOperation.status.in_(['pending', 'queued']),
            ProductionOrderOperation.resource_id.is_(None)  # Not yet assigned
        ).count()

        if pending_count > 0:
            wc = db.query(WorkCenter).filter(
                WorkCenter.id == resource.work_center_id
            ).first()

            items.append(ActionItem(
                id=f"idle_resource_{resource.id}",
                type=ActionItemType.IDLE_RESOURCE,
                priority=4,
                title=f"{resource.code} idle",
                description=f"{pending_count} operation{'s' if pending_count != 1 else ''} waiting in {wc.name if wc else 'work center'}",
                entity_type="resource",
                entity_id=resource.id,
                entity_code=resource.code,
                suggested_actions=[
                    SuggestedAction(
                        label="View Queue",
                        url=f"/admin/production?work_center={resource.work_center_id}",
                        action_type="navigate"
                    )
                ],
                created_at=None,  # No specific creation time
                metadata={
                    "pending_count": str(pending_count),
                    "work_center": wc.name if wc else ""
                }
            ))

    return items


def get_today_summary(db: Session) -> TodaySummary:
    """Get aggregate statistics for today's operations."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Orders due today (not shipped)
    orders_due_today = db.query(SalesOrder).filter(
        SalesOrder.estimated_completion_date >= today_start,
        SalesOrder.estimated_completion_date < today_end,
        SalesOrder.shipped_at.is_(None),
        SalesOrder.status.notin_(['cancelled', 'draft'])
    ).count()

    # Orders due today that are ready to ship
    orders_due_today_ready = db.query(SalesOrder).filter(
        SalesOrder.estimated_completion_date >= today_start,
        SalesOrder.estimated_completion_date < today_end,
        SalesOrder.status == 'ready_to_ship'
    ).count()

    # Orders shipped today
    orders_shipped_today = db.query(SalesOrder).filter(
        SalesOrder.shipped_at >= today_start,
        SalesOrder.shipped_at < today_end
    ).count()

    # Overdue orders
    orders_overdue = db.query(SalesOrder).filter(
        SalesOrder.estimated_completion_date < today_start,
        SalesOrder.shipped_at.is_(None),
        SalesOrder.status.notin_(['cancelled', 'draft', 'shipped'])
    ).count()

    # Production in progress
    production_in_progress = db.query(ProductionOrder).filter(
        ProductionOrder.status == 'in_progress'
    ).count()

    # Production blocked (has blocking issues)
    # Count POs where we can't produce
    active_pos = db.query(ProductionOrder).filter(
        ProductionOrder.status.in_(['released', 'in_progress', 'scheduled'])
    ).all()
    production_blocked = 0
    for po in active_pos:
        blocking = get_production_order_blocking_issues(db, po.id)
        if blocking and not blocking.status_summary.can_produce:
            production_blocked += 1

    # Production completed today
    production_completed_today = db.query(ProductionOrder).filter(
        ProductionOrder.status == 'completed',
        ProductionOrder.updated_at >= today_start,
        ProductionOrder.updated_at < today_end
    ).count()

    # Operations currently running
    operations_running = db.query(ProductionOrderOperation).filter(
        ProductionOrderOperation.status == 'running'
    ).count()

    # Resource counts
    resources_total = db.query(Resource).filter(
        Resource.is_active.is_(True)
    ).count()

    # Busy = has running operation
    resources_with_running_ops = db.query(
        func.count(func.distinct(ProductionOrderOperation.resource_id))
    ).filter(
        ProductionOrderOperation.status == 'running',
        ProductionOrderOperation.resource_id.isnot(None)
    ).scalar() or 0

    resources_busy = resources_with_running_ops

    # Down = maintenance or offline status
    resources_down = db.query(Resource).filter(
        Resource.is_active.is_(True),
        Resource.status.in_(['maintenance', 'offline'])
    ).count()

    resources_idle = resources_total - resources_busy - resources_down

    return TodaySummary(
        orders_due_today=orders_due_today,
        orders_due_today_ready=orders_due_today_ready,
        orders_shipped_today=orders_shipped_today,
        orders_overdue=orders_overdue,
        production_in_progress=production_in_progress,
        production_blocked=production_blocked,
        production_completed_today=production_completed_today,
        operations_running=operations_running,
        resources_total=resources_total,
        resources_busy=resources_busy,
        resources_idle=max(0, resources_idle),  # Ensure non-negative
        resources_down=resources_down,
        generated_at=now
    )


def get_resource_statuses(db: Session) -> ResourcesResponse:
    """Get current status of all resources/machines."""
    resources = db.query(Resource).filter(
        Resource.is_active.is_(True)
    ).order_by(Resource.work_center_id, Resource.code).all()

    result_resources = []
    status_counts: Dict[str, int] = defaultdict(int)

    for resource in resources:
        # Get work center name
        wc = db.query(WorkCenter).filter(
            WorkCenter.id == resource.work_center_id
        ).first()

        # Check for running operation
        running_op = db.query(ProductionOrderOperation).filter(
            ProductionOrderOperation.resource_id == resource.id,
            ProductionOrderOperation.status == 'running'
        ).first()

        current_operation = None
        status = resource.status  # Default to resource's status

        if running_op:
            status = 'running'
            # Get production order for context
            po = db.query(ProductionOrder).filter(
                ProductionOrder.id == running_op.production_order_id
            ).first()
            product = None
            if po:
                product = db.query(Product).filter(Product.id == po.product_id).first()

            planned = int(running_op.planned_setup_minutes or 0) + int(running_op.planned_run_minutes or 0)

            current_operation = OperationSummary(
                operation_id=running_op.id,
                production_order_id=running_op.production_order_id,
                production_order_code=po.code if po else "Unknown",
                operation_code=running_op.operation_code or f"OP{running_op.sequence or 1}",
                sequence=running_op.sequence,
                started_at=running_op.actual_start,
                planned_minutes=planned,
                product_name=product.name if product else None
            )
        elif resource.status in ['maintenance', 'offline']:
            status = resource.status
        else:
            status = 'idle'

        # Count pending operations for this resource's work center
        pending_count = db.query(ProductionOrderOperation).filter(
            ProductionOrderOperation.work_center_id == resource.work_center_id,
            ProductionOrderOperation.status.in_(['pending', 'queued'])
        ).count()

        result_resources.append(ResourceStatus(
            id=resource.id,
            code=resource.code,
            name=resource.name,
            work_center_id=resource.work_center_id,
            work_center_name=wc.name if wc else None,
            status=status,
            current_operation=current_operation,
            idle_since=None,  # Would need tracking to implement
            pending_operations_count=pending_count
        ))

        status_counts[status] += 1

    return ResourcesResponse(
        resources=result_resources,
        summary=dict(status_counts)
    )
