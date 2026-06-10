"""
Service layer for analyzing blocking issues.

Provides functions to analyze what's blocking sales order fulfillment:
- Incomplete production orders
- Missing production orders
- Material shortages
- Pending purchase orders
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, List, Tuple
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.bom import BOM, BOMLine
from app.models.production_order import ProductionOrder
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.purchase_order import PurchaseOrder, PurchaseOrderLine
from app.models.inventory import Inventory
from app.models.user import User
from app.schemas.blocking_issues import (
    SalesOrderBlockingIssues, StatusSummary, LineIssues,
    BlockingIssue, ResolutionAction, IssueSeverity, IssueType,
    ProductionOrderBlockingIssues, POStatusSummary, MaterialIssue,
    IncomingSupply, LinkedSalesOrderInfo
)
from app.models.vendor import Vendor
from app.services.supply_netting import get_projected_available


def get_finished_goods_available(db: Session, product_id: int) -> Decimal:
    """Get available finished goods inventory for a product."""
    result = db.query(
        func.coalesce(func.sum(Inventory.on_hand_quantity), Decimal("0"))
    ).filter(
        Inventory.product_id == product_id
    ).scalar()
    return Decimal(str(result or 0))


def get_allocated_quantity(db: Session, product_id: int) -> Decimal:
    """Get quantity allocated from inventory."""
    result = db.query(
        func.coalesce(func.sum(Inventory.allocated_quantity), Decimal("0"))
    ).filter(
        Inventory.product_id == product_id
    ).scalar()
    return Decimal(str(result or 0))


def get_production_orders_for_so(
    db: Session,
    sales_order_id: int,
    product_id: int
) -> List[ProductionOrder]:
    """Get production orders linked to a sales order for a specific product."""
    return db.query(ProductionOrder).filter(
        ProductionOrder.sales_order_id == sales_order_id,
        ProductionOrder.product_id == product_id
    ).all()


def get_material_requirements(
    db: Session,
    product_id: int,
    qty: Decimal
) -> List[Tuple[Product, Decimal]]:
    """Get materials required for producing a quantity of product."""
    # Get active BOM for this product
    bom = db.query(BOM).filter(
        BOM.product_id == product_id,
        BOM.active == True  # noqa: E712
    ).first()

    if not bom:
        return []

    # Get BOM lines with their component products
    bom_lines = db.query(BOMLine, Product).join(
        Product, BOMLine.component_id == Product.id
    ).filter(
        BOMLine.bom_id == bom.id
    ).all()

    return [(component, bom_line.quantity * qty) for bom_line, component in bom_lines]


def get_material_available(db: Session, product_id: int) -> Decimal:
    """Get available inventory for a material (on_hand - allocated)."""
    on_hand = get_finished_goods_available(db, product_id)
    allocated = get_allocated_quantity(db, product_id)
    return on_hand - allocated


def get_pending_purchase_orders(
    db: Session,
    product_id: int
) -> List[Tuple[PurchaseOrder, Decimal]]:
    """Get pending purchase orders for a product with remaining quantities."""
    active_statuses = ['draft', 'ordered', 'shipped']

    results = db.query(PurchaseOrder, PurchaseOrderLine).join(
        PurchaseOrderLine,
        PurchaseOrder.id == PurchaseOrderLine.purchase_order_id
    ).filter(
        PurchaseOrderLine.product_id == product_id,
        PurchaseOrder.status.in_(active_statuses)
    ).all()

    pos = []
    for po, pol in results:
        remaining = (pol.quantity_ordered or Decimal("0")) - (pol.quantity_received or Decimal("0"))
        if remaining > 0:
            pos.append((po, remaining))

    return pos


def analyze_line_issues(
    db: Session,
    so: SalesOrder,
    line: SalesOrderLine,
    line_number: int
) -> LineIssues:
    """Analyze blocking issues for a single sales order line."""
    product = db.query(Product).filter(Product.id == line.product_id).first()
    if not product:
        return LineIssues(
            line_number=line_number,
            product_sku="UNKNOWN",
            product_name="Unknown Product",
            quantity_ordered=line.quantity or Decimal("0"),
            quantity_available=Decimal("0"),
            quantity_short=line.quantity or Decimal("0"),
            blocking_issues=[]
        )

    issues: List[BlockingIssue] = []

    # Check finished goods availability
    fg_available = get_finished_goods_available(db, line.product_id)
    qty_ordered = line.quantity or Decimal("0")
    qty_short = max(Decimal("0"), qty_ordered - fg_available)

    if qty_short > 0:
        # Need production - check production orders
        production_orders = get_production_orders_for_so(db, so.id, line.product_id)

        if not production_orders:
            # No production order exists - check if product needs one
            if product.has_bom:
                issues.append(BlockingIssue(
                    type=IssueType.PRODUCTION_MISSING,
                    severity=IssueSeverity.BLOCKING,
                    message=f"No production order exists for {product.sku}",
                    reference_type="make_product",  # Use make_product to distinguish from buy_product
                    reference_id=product.id,
                    reference_code=product.sku,
                    details={
                        "quantity_needed": float(qty_short)
                    }
                ))
        else:
            for wo in production_orders:
                qty_ordered_wo = wo.quantity_ordered or Decimal("0")
                qty_completed = wo.quantity_completed or Decimal("0")
                qty_scrapped = wo.quantity_scrapped or Decimal("0")
                remaining = qty_ordered_wo - qty_completed - qty_scrapped

                if wo.status not in ['complete', 'completed', 'closed'] and remaining > 0:
                    # Production incomplete
                    issues.append(BlockingIssue(
                        type=IssueType.PRODUCTION_INCOMPLETE,
                        severity=IssueSeverity.BLOCKING,
                        message=f"Production order {wo.code} not complete",
                        reference_type="production_order",
                        reference_id=wo.id,
                        reference_code=wo.code,
                        details={
                            "status": wo.status,
                            "quantity_ordered": float(qty_ordered_wo),
                            "quantity_completed": float(qty_completed),
                            "quantity_remaining": float(remaining),
                            "estimated_completion": wo.due_date.isoformat() if wo.due_date else None
                        }
                    ))

                    # Check material availability for this WO — HARD-6: use projected balance
                    material_reqs = get_material_requirements(db, wo.product_id, remaining)
                    for component, qty_needed in material_reqs:
                        proj = get_projected_available(db, component.id)
                        available = proj.available
                        shortage_now = max(Decimal("0"), qty_needed - available)
                        # Net shortage after incoming PO supply
                        shortage_projected = max(Decimal("0"), qty_needed - proj.projected)
                        covered_by_incoming = (shortage_now > 0) and (shortage_projected == 0) and (proj.incoming_qty > 0)

                        if shortage_now > 0:
                            best = proj.best_detail
                            incoming_po_number = best.po_number if best else None
                            incoming_date = best.expected_date.isoformat() if best and best.expected_date else None

                            if shortage_projected > 0:
                                # HARD-6: real net shortage even after netting PO supply
                                issues.append(BlockingIssue(
                                    type=IssueType.MATERIAL_SHORTAGE,
                                    severity=IssueSeverity.BLOCKING,
                                    message=f"Material {component.sku} is {shortage_projected:.0f} units short",
                                    reference_type="product",
                                    reference_id=component.id,
                                    reference_code=component.sku,
                                    details={
                                        "required": float(qty_needed),
                                        "available": float(available),
                                        "shortage": float(shortage_now),
                                        "shortage_projected": float(shortage_projected),
                                        "covered_by_incoming": False,
                                        "incoming_po": incoming_po_number,
                                        "incoming_date": incoming_date,
                                    }
                                ))
                            # else: shortage_projected == 0 → PO fully covers gap;
                            #       no MATERIAL_SHORTAGE issue (HARD-6 double-order fix)

                            # Always emit PURCHASE_PENDING when on-hand is short and a PO
                            # is in flight — lets user expedite or just verify the incoming date
                            if best:
                                issues.append(BlockingIssue(
                                    type=IssueType.PURCHASE_PENDING,
                                    severity=IssueSeverity.WARNING,
                                    message=f"Purchase order {best.po_number} pending receipt",
                                    reference_type="purchase_order",
                                    reference_id=best.purchase_order_id,
                                    reference_code=best.po_number,
                                    details={
                                        "status": best.status,
                                        "expected_date": best.expected_date.isoformat() if best.expected_date else None,
                                        "quantity": float(best.quantity),
                                        "covers_shortage": covered_by_incoming,
                                    }
                                ))

    return LineIssues(
        line_number=line_number,
        product_sku=product.sku,
        product_name=product.name,
        quantity_ordered=qty_ordered,
        quantity_available=fg_available,
        quantity_short=qty_short,
        blocking_issues=issues
    )


def generate_resolution_actions(line_issues: List[LineIssues]) -> List[ResolutionAction]:
    """Generate prioritized resolution actions from blocking issues."""
    actions: List[ResolutionAction] = []
    priority = 1
    seen_refs = set()  # Avoid duplicate actions

    # Collect all blocking issues
    all_issues = []
    for line in line_issues:
        all_issues.extend(line.blocking_issues)

    # Priority 1: Material shortages with pending POs - expedite
    po_issues = [i for i in all_issues if i.type == IssueType.PURCHASE_PENDING]
    for issue in po_issues:
        ref_key = (issue.reference_type, issue.reference_id)
        if ref_key not in seen_refs:
            actions.append(ResolutionAction(
                priority=priority,
                action=f"Expedite PO {issue.reference_code}",
                impact=f"Resolves material shortage, expected {issue.details.get('expected_date', 'TBD')}",
                reference_type=issue.reference_type,
                reference_id=issue.reference_id
            ))
            seen_refs.add(ref_key)
            priority += 1

    # Priority 2: Material shortages without POs - create PO
    mat_issues = [i for i in all_issues if i.type == IssueType.MATERIAL_SHORTAGE]
    for issue in mat_issues:
        ref_key = (issue.reference_type, issue.reference_id)
        if ref_key not in seen_refs and not issue.details.get('incoming_po'):
            actions.append(ResolutionAction(
                priority=priority,
                action=f"Create PO for {issue.reference_code}",
                impact=f"Need {issue.details.get('shortage', 0):.0f} units",
                reference_type=issue.reference_type,
                reference_id=issue.reference_id
            ))
            seen_refs.add(ref_key)
            priority += 1

    # Priority 3: Incomplete production - complete WO
    prod_issues = [i for i in all_issues if i.type == IssueType.PRODUCTION_INCOMPLETE]
    for issue in prod_issues:
        ref_key = (issue.reference_type, issue.reference_id)
        if ref_key not in seen_refs:
            actions.append(ResolutionAction(
                priority=priority,
                action=f"Complete production {issue.reference_code}",
                impact=f"{issue.details.get('quantity_remaining', 0):.0f} units remaining",
                reference_type=issue.reference_type,
                reference_id=issue.reference_id
            ))
            seen_refs.add(ref_key)
            priority += 1

    # Priority 4: Missing production - create WO
    missing_issues = [i for i in all_issues if i.type == IssueType.PRODUCTION_MISSING]
    for issue in missing_issues:
        ref_key = (issue.reference_type, issue.reference_id)
        if ref_key not in seen_refs:
            actions.append(ResolutionAction(
                priority=priority,
                action=f"Create production order for {issue.reference_code}",
                impact=f"Need {issue.details.get('quantity_needed', 0):.0f} units",
                reference_type=issue.reference_type,
                reference_id=issue.reference_id
            ))
            seen_refs.add(ref_key)
            priority += 1

    return actions


def estimate_ready_date(line_issues: List[LineIssues]) -> Optional[date]:
    """Estimate when the order could be ready based on blocking issues."""
    latest_date = date.today()

    for line in line_issues:
        for issue in line.blocking_issues:
            if issue.type == IssueType.PURCHASE_PENDING:
                po_date_str = issue.details.get('expected_date')
                if po_date_str:
                    try:
                        po_date = date.fromisoformat(po_date_str)
                        if po_date > latest_date:
                            latest_date = po_date
                    except ValueError:
                        pass

            elif issue.type == IssueType.PRODUCTION_INCOMPLETE:
                wo_date_str = issue.details.get('estimated_completion')
                if wo_date_str:
                    try:
                        wo_date = date.fromisoformat(wo_date_str)
                        if wo_date > latest_date:
                            latest_date = wo_date
                    except ValueError:
                        pass

    # Add buffer for production after materials arrive
    if latest_date > date.today():
        latest_date += timedelta(days=2)  # Processing buffer
        return latest_date

    return None


def get_sales_order_blocking_issues(
    db: Session,
    sales_order_id: int
) -> Optional[SalesOrderBlockingIssues]:
    """
    Get complete blocking issues analysis for a sales order.

    Returns None if sales order doesn't exist.
    """
    # Get the sales order
    so = db.query(SalesOrder).filter(SalesOrder.id == sales_order_id).first()
    if not so:
        return None

    # Get customer name
    customer_name = so.customer_name or "Unknown"
    if so.customer_id:
        customer = db.query(User).filter(User.id == so.customer_id).first()
        if customer:
            if customer.company_name:
                customer_name = customer.company_name
            elif customer.first_name or customer.last_name:
                customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

    # Analyze each line
    line_issues = []
    if so.lines:
        for idx, line in enumerate(so.lines, start=1):
            line_analysis = analyze_line_issues(db, so, line, idx)
            line_issues.append(line_analysis)
    else:
        # Single-product order (no lines, uses product_id directly)
        if so.product_id:
            product = db.query(Product).filter(Product.id == so.product_id).first()
            if product:
                # Create a synthetic line for analysis
                class SyntheticLine:
                    def __init__(self, product_id, quantity):
                        self.product_id = product_id
                        self.quantity = quantity

                synthetic = SyntheticLine(so.product_id, so.quantity or Decimal("1"))
                line_analysis = analyze_line_issues(db, so, synthetic, 1)
                line_issues.append(line_analysis)

    # Calculate summary
    blocking_count = sum(
        len([i for i in line.blocking_issues if i.severity == IssueSeverity.BLOCKING])
        for line in line_issues
    )
    can_fulfill = blocking_count == 0

    estimated_ready = estimate_ready_date(line_issues) if not can_fulfill else None
    days_until_ready = (estimated_ready - date.today()).days if estimated_ready else None

    # Generate resolution actions
    resolution_actions = generate_resolution_actions(line_issues)

    # Determine requested date - use estimated_completion_date if available
    requested_date = None
    if so.estimated_completion_date:
        # Convert datetime to date (check datetime first since datetime is subclass of date)
        from datetime import datetime
        if isinstance(so.estimated_completion_date, datetime):
            requested_date = so.estimated_completion_date.date()
        elif isinstance(so.estimated_completion_date, date):
            requested_date = so.estimated_completion_date

    # Get order date
    order_date = date.today()
    if so.created_at:
        order_date = so.created_at.date() if hasattr(so.created_at, 'date') else so.created_at

    return SalesOrderBlockingIssues(
        sales_order_id=so.id,
        sales_order_code=so.order_number,
        customer=customer_name,
        order_date=order_date,
        requested_date=requested_date,
        status_summary=StatusSummary(
            can_fulfill=can_fulfill,
            blocking_count=blocking_count,
            estimated_ready_date=estimated_ready,
            days_until_ready=days_until_ready
        ),
        line_issues=line_issues,
        resolution_actions=resolution_actions
    )


# =============================================================================
# Production Order Blocking Issues (API-202)
# =============================================================================

def get_production_order_blocking_issues(
    db: Session,
    production_order_id: int
) -> Optional[ProductionOrderBlockingIssues]:
    """
    Get complete blocking issues analysis for a production order.

    Returns None if production order doesn't exist.
    """
    # Get the production order
    wo = db.query(ProductionOrder).filter(ProductionOrder.id == production_order_id).first()
    if not wo:
        return None

    product = db.query(Product).filter(Product.id == wo.product_id).first()
    if not product:
        return None

    # Get linked sales order if exists
    linked_so = None
    if wo.sales_order_id:
        so = db.query(SalesOrder).filter(SalesOrder.id == wo.sales_order_id).first()
        if so:
            # Get customer name
            customer_name = so.customer_name or "Unknown"
            if so.customer_id:
                customer = db.query(User).filter(User.id == so.customer_id).first()
                if customer:
                    if customer.company_name:
                        customer_name = customer.company_name
                    elif customer.first_name or customer.last_name:
                        customer_name = f"{customer.first_name or ''} {customer.last_name or ''}".strip()

            # Get requested date
            requested_date = None
            if so.estimated_completion_date:
                from datetime import datetime as dt
                if isinstance(so.estimated_completion_date, dt):
                    requested_date = so.estimated_completion_date.date()
                elif isinstance(so.estimated_completion_date, date):
                    requested_date = so.estimated_completion_date

            linked_so = LinkedSalesOrderInfo(
                id=so.id,
                code=so.order_number,
                customer=customer_name,
                requested_date=requested_date
            )

    # Calculate remaining quantity
    qty_ordered = wo.quantity_ordered or Decimal("0")
    qty_completed = wo.quantity_completed or Decimal("0")
    qty_scrapped = wo.quantity_scrapped or Decimal("0")
    qty_remaining = qty_ordered - qty_completed - qty_scrapped

    # Analyze material requirements
    material_issues = []
    blocking_count = 0
    latest_incoming_date = None

    # Get BOM for this product
    bom = db.query(BOM).filter(
        BOM.product_id == wo.product_id,
        BOM.active == True  # noqa: E712
    ).first()

    if bom:
        bom_lines = db.query(BOMLine, Product).join(
            Product, BOMLine.component_id == Product.id
        ).filter(
            BOMLine.bom_id == bom.id
        ).all()

        for bom_line, component in bom_lines:
            qty_required = bom_line.quantity * qty_remaining
            # HARD-6: use projected balance (available + open-PO supply)
            proj = get_projected_available(db, component.id)
            qty_available = proj.available
            qty_short_now = max(Decimal("0"), qty_required - qty_available)
            qty_short_projected = max(Decimal("0"), qty_required - proj.projected)
            covered_by_incoming = (qty_short_now > 0) and (qty_short_projected == 0) and (proj.incoming_qty > 0)

            # Shortage exists only when projected balance is insufficient
            status = "ok" if qty_short_projected == 0 else "shortage"
            if qty_short_projected > 0:
                blocking_count += 1

            # Build incoming supply detail from best (earliest) open PO
            incoming = None
            if proj.best_detail:
                detail = proj.best_detail
                # Fetch vendor name via PO object
                po_obj = db.query(PurchaseOrder).filter(
                    PurchaseOrder.id == detail.purchase_order_id
                ).first()
                vendor_name = "Unknown"
                if po_obj and po_obj.vendor_id:
                    v = db.query(Vendor).filter(Vendor.id == po_obj.vendor_id).first()
                    vendor_name = v.name if v else "Unknown"

                incoming = IncomingSupply(
                    purchase_order_id=detail.purchase_order_id,
                    purchase_order_code=detail.po_number,
                    quantity=detail.quantity,
                    expected_date=detail.expected_date,
                    vendor=vendor_name,
                )

                if detail.expected_date and (
                    latest_incoming_date is None or detail.expected_date > latest_incoming_date
                ):
                    latest_incoming_date = detail.expected_date

            material_issues.append(MaterialIssue(
                product_id=component.id,
                product_sku=component.sku,
                product_name=component.name,
                quantity_required=qty_required,
                quantity_available=max(Decimal("0"), qty_available),
                quantity_short=qty_short_projected,   # net shortage after POs
                quantity_projected=proj.projected,
                quantity_short_projected=qty_short_projected,
                covered_by_incoming=covered_by_incoming,
                status=status,
                incoming_supply=incoming,
            ))

    # Determine if can produce
    can_produce = blocking_count == 0

    # Estimate ready date
    estimated_ready = None
    days_until_ready = None
    if not can_produce and latest_incoming_date:
        estimated_ready = latest_incoming_date + timedelta(days=1)  # Buffer
        days_until_ready = (estimated_ready - date.today()).days

    # Generate resolution actions
    resolution_actions = generate_po_resolution_actions(material_issues)

    return ProductionOrderBlockingIssues(
        production_order_id=wo.id,
        production_order_code=wo.code,
        product_sku=product.sku,
        product_name=product.name,
        quantity_ordered=qty_ordered,
        quantity_completed=qty_completed,
        quantity_remaining=qty_remaining,
        status_summary=POStatusSummary(
            can_produce=can_produce,
            blocking_count=blocking_count,
            estimated_ready_date=estimated_ready,
            days_until_ready=days_until_ready
        ),
        linked_sales_order=linked_so,
        material_issues=material_issues,
        other_issues=[],  # Future: machine status, quality holds
        resolution_actions=resolution_actions
    )


def generate_po_resolution_actions(material_issues: List[MaterialIssue]) -> List[ResolutionAction]:
    """Generate prioritized resolution actions for production blocking issues."""
    actions: List[ResolutionAction] = []
    priority = 1
    seen_refs = set()  # Avoid duplicate actions

    # Priority 1: Expedite existing POs for shortage materials
    for mat in material_issues:
        if mat.status == "shortage" and mat.incoming_supply:
            ref_key = ("purchase_order", mat.incoming_supply.purchase_order_id)
            if ref_key not in seen_refs:
                expected = mat.incoming_supply.expected_date.isoformat() if mat.incoming_supply.expected_date else "TBD"
                actions.append(ResolutionAction(
                    priority=priority,
                    action=f"Expedite PO {mat.incoming_supply.purchase_order_code}",
                    impact=f"Resolves {mat.product_sku} shortage, expected {expected}",
                    reference_type="purchase_order",
                    reference_id=mat.incoming_supply.purchase_order_id
                ))
                seen_refs.add(ref_key)
                priority += 1

    # Priority 2: Create POs for shortage materials without incoming
    for mat in material_issues:
        if mat.status == "shortage" and not mat.incoming_supply:
            ref_key = ("product", mat.product_id)
            if ref_key not in seen_refs:
                actions.append(ResolutionAction(
                    priority=priority,
                    action=f"Create PO for {mat.product_sku}",
                    impact=f"Need {mat.quantity_short:.0f} units",
                    reference_type="product",
                    reference_id=mat.product_id
                ))
                seen_refs.add(ref_key)
                priority += 1

    return actions
