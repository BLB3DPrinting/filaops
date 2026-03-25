"""
Sales Order Service — CRUD, status management, production orders, and fulfillment.

Extracted from sales_orders.py (ARCHITECT-003).
"""
import io
import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
import sqlalchemy as sa
from sqlalchemy import desc, func
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError

from app.logging_config import get_logger
from app.models.user import User
from app.models.quote import Quote
from app.models.sales_order import SalesOrder, SalesOrderLine
from app.models.production_order import (
    ProductionOrder,
    ProductionOrderOperation,
    ProductionOrderOperationMaterial,
)
from app.models.manufacturing import Routing, RoutingOperation, RoutingOperationMaterial
from app.models.product import Product
from app.models.material import MaterialInventory
from app.models.bom import BOM, BOMLine
from app.models.inventory import Inventory
from app.models.company_settings import CompanySettings
from app.models.order_event import OrderEvent

logger = get_logger(__name__)


# =============================================================================
# Price Level Helpers (PRO graceful degradation)
# =============================================================================

# Canonical implementation lives in customer_service — single source of truth
from app.services.customer_service import get_customer_discount_percent as _get_customer_discount_percent


# =============================================================================
# Code Generation Helpers
# =============================================================================

def generate_order_number(db: Session) -> str:
    """
    Generate next sales order number (SO-2025-001, SO-2025-002, etc.)
    Uses row-level locking to prevent race conditions.
    """
    year = datetime.now(timezone.utc).year
    last_order = (
        db.query(SalesOrder)
        .filter(SalesOrder.order_number.like(f"SO-{year}-%"))
        .order_by(desc(SalesOrder.order_number))
        .with_for_update()
        .first()
    )

    if last_order:
        last_num = int(last_order.order_number.split("-")[2])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"SO-{year}-{next_num:03d}"


def generate_production_order_code(db: Session) -> str:
    """
    Generate next production order code (PO-2025-0001, etc.)
    Uses row-level locking to prevent race conditions.
    """
    year = datetime.now(timezone.utc).year
    last_po = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.code.like(f"PO-{year}-%"))
        .order_by(desc(ProductionOrder.code))
        .with_for_update(skip_locked=False)
        .first()
    )

    if last_po:
        last_num = int(last_po.code.split("-")[2])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"PO-{year}-{next_num:04d}"


# =============================================================================
# Production Order Helpers
# =============================================================================

def copy_routing_to_operations(
    db: Session,
    production_order: ProductionOrder,
    routing_id: int,
) -> list[ProductionOrderOperation]:
    """
    Copy routing operations AND their materials to production order operations.

    Creates the individual operation records that track progress through
    the manufacturing process (Print, Finishing, QC, Pack, etc.), along with
    the material requirements for each operation.
    """
    routing_ops = (
        db.query(RoutingOperation)
        .filter(RoutingOperation.routing_id == routing_id)
        .order_by(RoutingOperation.sequence)
        .all()
    )

    operations = []
    for rop in routing_ops:
        op = ProductionOrderOperation(
            production_order_id=production_order.id,
            routing_operation_id=rop.id,
            work_center_id=rop.work_center_id,
            resource_id=None,  # Resource assigned during scheduling
            sequence=rop.sequence,
            operation_code=rop.operation_code,
            operation_name=rop.operation_name,
            planned_setup_minutes=rop.setup_time_minutes or 0,
            planned_run_minutes=float(rop.run_time_minutes or 0) * float(production_order.quantity_ordered),
            status="pending",
        )
        db.add(op)
        db.flush()  # Get op.id for material records

        # Copy materials from routing operation to production order operation
        for rom in rop.materials:
            if rom.is_cost_only:
                continue  # Skip cost-only materials (no inventory consumption)

            # Use built-in method that handles quantity_per and scrap_factor
            qty_required = rom.calculate_required_quantity(int(production_order.quantity_ordered))

            # Round up for discrete units (can't ship 0.792 boxes)
            unit_upper = (rom.unit or "").upper()
            if unit_upper in ("EA", "EACH", "PCS", "UNIT", "BOX", "BOXES"):
                qty_required = math.ceil(qty_required)

            mat = ProductionOrderOperationMaterial(
                production_order_operation_id=op.id,
                component_id=rom.component_id,
                routing_operation_material_id=rom.id,
                quantity_required=Decimal(str(qty_required)),
                unit=rom.unit,
                quantity_allocated=Decimal("0"),
                quantity_consumed=Decimal("0"),
                status="pending",
            )
            db.add(mat)

        operations.append(op)

    return operations


def create_production_orders_for_sales_order(
    db: Session,
    order: SalesOrder,
    created_by: str,
) -> list[str]:
    """
    Create production orders for a sales order.

    Returns list of created production order codes.
    """
    created_orders = []
    year = datetime.now(timezone.utc).year

    def get_next_po_code():
        """
        Generate next PO code with row-level locking to prevent race conditions.
        """
        last_po = (
            db.query(ProductionOrder)
            .filter(ProductionOrder.code.like(f"PO-{year}-%"))
            .order_by(desc(ProductionOrder.code))
            .with_for_update(skip_locked=False)
            .first()
        )
        if last_po:
            last_num = int(last_po.code.split("-")[2])
            next_num = last_num + 1
        else:
            next_num = 1
        return f"PO-{year}-{next_num:04d}"

    if order.order_type == "line_item":
        lines = db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == order.id
        ).order_by(SalesOrderLine.id).all()

        for idx, line in enumerate(lines, start=1):
            product = db.query(Product).filter(Product.id == line.product_id).first()
            if not product:
                continue

            # Only create WO for products with BOMs (make items)
            if not product.has_bom:
                continue

            bom = db.query(BOM).filter(
                BOM.product_id == line.product_id,
                BOM.active.is_(True)
            ).first()

            routing = db.query(Routing).filter(
                Routing.product_id == line.product_id,
                Routing.is_active.is_(True)
            ).first()

            # Retry with savepoints to avoid rolling back the entire transaction
            max_retries = 3
            for attempt in range(max_retries):
                savepoint = db.begin_nested()
                try:
                    po_code = get_next_po_code()

                    production_order = ProductionOrder(
                        code=po_code,
                        product_id=line.product_id,
                        bom_id=bom.id if bom else None,
                        routing_id=routing.id if routing else None,
                        sales_order_id=order.id,
                        sales_order_line_id=line.id,
                        quantity_ordered=line.quantity,
                        quantity_completed=0,
                        quantity_scrapped=0,
                        source="sales_order",
                        status="draft",
                        priority=3,
                        notes=f"Auto-generated from {order.order_number} Line {idx}",
                        created_by=created_by,
                    )
                    db.add(production_order)
                    db.flush()

                    # Copy routing operations to production order
                    if routing:
                        copy_routing_to_operations(db, production_order, routing.id)

                    created_orders.append(po_code)
                    break
                except IntegrityError as e:
                    savepoint.rollback()
                    logger.warning(
                        f"PO code generation attempt {attempt + 1}/{max_retries} failed: {str(e)}"
                    )
                    if attempt >= max_retries - 1:
                        logger.error(
                            f"Failed to generate unique PO code after {max_retries} attempts for SO {order.order_number}",
                            exc_info=True
                        )
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to generate unique PO code after {max_retries} attempts"
                        )

    elif order.order_type == "quote_based" and order.product_id:
        product = db.query(Product).filter(Product.id == order.product_id).first()
        if product and product.has_bom:
            bom = db.query(BOM).filter(
                BOM.product_id == order.product_id,
                BOM.active.is_(True)
            ).first()

            routing = db.query(Routing).filter(
                Routing.product_id == order.product_id,
                Routing.is_active.is_(True)
            ).first()

            max_retries = 3
            for attempt in range(max_retries):
                savepoint = db.begin_nested()
                try:
                    po_code = get_next_po_code()

                    production_order = ProductionOrder(
                        code=po_code,
                        product_id=order.product_id,
                        bom_id=bom.id if bom else None,
                        routing_id=routing.id if routing else None,
                        sales_order_id=order.id,
                        quantity_ordered=order.quantity or 1,
                        quantity_completed=0,
                        quantity_scrapped=0,
                        source="sales_order",
                        status="draft",
                        priority=3,
                        notes=f"Auto-generated from {order.order_number}",
                        created_by=created_by,
                    )
                    db.add(production_order)
                    db.flush()

                    if routing:
                        copy_routing_to_operations(db, production_order, routing.id)

                    created_orders.append(po_code)
                    break
                except IntegrityError as e:
                    savepoint.rollback()
                    logger.warning(
                        f"PO code generation attempt {attempt + 1}/{max_retries} failed: {str(e)}"
                    )
                    if attempt >= max_retries - 1:
                        logger.error(
                            f"Failed to generate unique PO code after {max_retries} attempts for SO {order.order_number}",
                            exc_info=True
                        )
                        raise HTTPException(
                            status_code=500,
                            detail=f"Failed to generate unique PO code after {max_retries} attempts"
                        )

    return created_orders


# =============================================================================
# Event Recording
# =============================================================================

def record_order_event(
    db: Session,
    order_id: int,
    event_type: str,
    title: str,
    description: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    user_id: Optional[int] = None,
    metadata_key: Optional[str] = None,
    metadata_value: Optional[str] = None,
) -> OrderEvent:
    """
    Record an order event to the activity timeline.

    Called internally by status change, payment, and shipping endpoints.
    Does NOT commit - caller handles the transaction.
    """
    event = OrderEvent(
        sales_order_id=order_id,
        user_id=user_id,
        event_type=event_type,
        title=title,
        description=description,
        old_value=old_value,
        new_value=new_value,
        metadata_key=metadata_key,
        metadata_value=metadata_value,
    )
    db.add(event)
    return event


# =============================================================================
# Sales Order CRUD
# =============================================================================

def list_sales_orders(
    db: Session,
    *,
    user_id: Optional[int] = None,
    is_admin: bool = False,
    status_filter: Optional[str] = None,
    statuses: Optional[list[str]] = None,
    skip: int = 0,
    limit: int = 50,
    sort_by: str = "order_date",
    sort_order: str = "desc",
) -> list[SalesOrder]:
    """
    List sales orders with filtering and pagination.

    Args:
        user_id: Filter by user (ignored if is_admin=True)
        is_admin: If True, returns all orders
        status_filter: Single status filter (deprecated)
        statuses: Multiple status filter
        skip: Pagination offset
        limit: Max results (capped at 100)
        sort_by: Sort field (created_at or customer_name)
        sort_order: Sort direction (asc or desc)

    Returns:
        List of SalesOrder objects
    """
    if limit > 100:
        limit = 100

    query = db.query(SalesOrder).options(
        joinedload(SalesOrder.user),
        joinedload(SalesOrder.product)
    )

    # Filter by user unless admin
    if not is_admin and user_id:
        query = query.filter(SalesOrder.user_id == user_id)

    # Status filtering
    if statuses:
        query = query.filter(SalesOrder.status.in_(statuses))
    elif status_filter:
        query = query.filter(SalesOrder.status == status_filter)

    # Sorting — "order_date" maps to created_at (SalesOrder has no order_date column)
    if sort_by == "customer_name":
        order_column = SalesOrder.customer_name
    else:
        order_column = SalesOrder.created_at

    if sort_order == "desc":
        query = query.order_by(desc(order_column))
    else:
        query = query.order_by(order_column)

    return query.offset(skip).limit(limit).all()


def get_sales_order(db: Session, order_id: int) -> SalesOrder:
    """Get a sales order by ID or raise 404."""
    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return order


def get_sales_order_with_lines(db: Session, order_id: int) -> SalesOrder:
    """Get a sales order with lines eagerly loaded."""
    order = db.query(SalesOrder).options(
        joinedload(SalesOrder.lines).joinedload(SalesOrderLine.product),
        joinedload(SalesOrder.user),
    ).filter(SalesOrder.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Sales order not found")
    return order


def validate_customer(db: Session, customer_id: int) -> User:
    """Validate customer exists and is active."""
    customer = db.query(User).filter(User.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer ID {customer_id} not found")
    if customer.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Customer '{customer.email}' is not active (status: {customer.status})"
        )
    return customer


def validate_product_for_order(db: Session, product_id: int) -> Product:
    """Validate product exists and is active for ordering."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=f"Product ID {product_id} not found")
    if not product.active:
        raise HTTPException(
            status_code=400,
            detail=f"Product '{product.sku}' is discontinued and cannot be ordered"
        )
    return product


def validate_material_for_order(db: Session, material_inventory_id: int) -> MaterialInventory:
    """Validate material inventory item exists and is active for ordering."""
    material = (
        db.query(MaterialInventory)
        .filter(MaterialInventory.id == material_inventory_id)
        .first()
    )
    if not material:
        raise HTTPException(
            status_code=404,
            detail=f"Material inventory ID {material_inventory_id} not found",
        )
    if not material.active:
        raise HTTPException(
            status_code=400,
            detail=f"Material '{material.sku}' is inactive and cannot be ordered",
        )
    return material


def get_company_tax_settings(db: Session) -> tuple[Optional[Decimal], bool, Optional[str]]:
    """
    Get company tax settings.

    Resolution order:
      1. Default TaxRate from tax_rates table (new multi-rate system)
      2. CompanySettings.tax_rate (legacy single-rate fallback)

    Returns:
        (tax_rate, is_taxable, tax_name) tuple
    """
    from app.services.tax_rate_service import get_default_tax_rate
    default_tr = get_default_tax_rate(db)
    if default_tr:
        return default_tr.rate, True, default_tr.name

    company_settings = db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    if company_settings and company_settings.tax_enabled and company_settings.tax_rate:
        return Decimal(str(company_settings.tax_rate)), True, company_settings.tax_name
    return None, False, None


def create_sales_order(
    db: Session,
    *,
    customer_id: Optional[int],
    lines: list[dict],
    source: str = "manual",
    source_order_id: Optional[str] = None,
    shipping_address_line1: Optional[str] = None,
    shipping_address_line2: Optional[str] = None,
    shipping_city: Optional[str] = None,
    shipping_state: Optional[str] = None,
    shipping_zip: Optional[str] = None,
    shipping_country: Optional[str] = "USA",
    shipping_cost: Decimal = Decimal("0"),
    customer_notes: Optional[str] = None,
    internal_notes: Optional[str] = None,
    created_by_user_id: int,
) -> SalesOrder:
    """
    Create a manual sales order (line_item type).

    Each line must contain exactly one of ``product_id`` or
    ``material_inventory_id``.  Product lines use the catalog selling
    price; material lines require an explicit ``unit_price`` (or fall
    back to the material's ``cost_per_kg``).

    Args:
        customer_id: Optional customer user ID
        lines: List of dicts with product_id **or** material_inventory_id,
               quantity, unit_price (optional for products), notes
        source: Order source (manual, squarespace, etc.)
        source_order_id: External order ID
        shipping_*: Shipping address fields
        shipping_cost: Shipping cost
        customer_notes: Customer-visible notes
        internal_notes: Internal notes
        created_by_user_id: User creating the order

    Returns:
        Created SalesOrder

    Raises:
        HTTPException: On validation errors
    """
    # Validate customer if provided
    customer = None
    if customer_id:
        customer = validate_customer(db, customer_id)

    # Validate line items and calculate totals
    validated_lines: list[dict] = []
    total_price = Decimal("0")
    total_quantity = 0
    line_names: list[str] = []

    for line in lines:
        has_product = line.get("product_id") is not None
        has_material = line.get("material_inventory_id") is not None

        if has_product == has_material:
            raise HTTPException(
                status_code=400,
                detail="Each line must specify exactly one of product_id or material_inventory_id",
            )

        if has_product:
            # --- Product line (existing path) ---
            product = validate_product_for_order(db, line["product_id"])

            # SECURITY: Always use product's catalog price
            unit_price = product.selling_price or Decimal("0")
            if unit_price <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Product '{product.sku}' has no selling price configured",
                )

            line_total = unit_price * line["quantity"]

            validated_lines.append({
                "product": product,
                "material": None,
                "product_id": product.id,
                "material_inventory_id": None,
                "quantity": line["quantity"],
                "unit_price": unit_price,
                "line_total": line_total,
                "notes": line.get("notes"),
            })
            line_names.append(product.name)

        else:
            # --- Material inventory line (new path) ---
            material = validate_material_for_order(db, line["material_inventory_id"])

            # Use explicit unit_price if provided, otherwise fall back to cost_per_kg
            explicit_price = line.get("unit_price")
            if explicit_price is not None:
                unit_price = Decimal(str(explicit_price))
            elif material.cost_per_kg:
                unit_price = Decimal(str(material.cost_per_kg))
            else:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Material '{material.sku}' has no cost configured. "
                        "Provide a unit_price for this line."
                    ),
                )

            if unit_price <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Material '{material.sku}' unit price must be > 0",
                )

            line_total = unit_price * line["quantity"]

            validated_lines.append({
                "product": None,
                "material": material,
                "product_id": None,
                "material_inventory_id": material.id,
                "quantity": line["quantity"],
                "unit_price": unit_price,
                "line_total": line_total,
                "notes": line.get("notes"),
            })
            line_names.append(material.display_name)

        total_price += line_total
        total_quantity += line["quantity"]

    # Look up customer price level discount (PRO feature, graceful degradation)
    discount_percent = None
    if customer_id:
        discount_percent = _get_customer_discount_percent(db, customer_id)

    if discount_percent and discount_percent > 0:
        # Apply discount to each line
        total_price = Decimal("0")
        for vl in validated_lines:
            original_price = vl["unit_price"]
            discounted_price = (
                original_price * (Decimal("1") - discount_percent / Decimal("100"))
            ).quantize(Decimal("0.01"))
            vl["unit_price"] = discounted_price
            vl["line_total"] = discounted_price * vl["quantity"]
            vl["discount_percent"] = discount_percent
            total_price += vl["line_total"]

    # Generate order number
    order_number = generate_order_number(db)

    # Calculate tax
    tax_rate, is_taxable, tax_name = get_company_tax_settings(db)
    tax_amount = Decimal("0")
    if tax_rate:
        tax_amount = (total_price * tax_rate).quantize(Decimal("0.01"))

    grand_total = total_price + shipping_cost + tax_amount

    # Build product name summary
    if len(validated_lines) == 1:
        product_name = f"{line_names[0]} x{validated_lines[0]['quantity']}"
    else:
        product_name = f"{len(validated_lines)} items"

    # Derive material_type from the first line (product or material)
    first_line = validated_lines[0]
    if first_line["product"]:
        first_product = first_line["product"]
        material_type = (
            getattr(first_product.material_type, "base_material", None)
            or getattr(first_product.material_type, "name", None)
            or "Material"
        )
    elif first_line["material"] and first_line["material"].material_type:
        material_type = first_line["material"].material_type.base_material
    else:
        material_type = "Material"

    # Use customer_id if provided, otherwise current user
    user_id = customer_id if customer_id else created_by_user_id

    # Auto-copy customer shipping address if not provided
    if customer and not shipping_address_line1:
        if customer.shipping_address_line1:
            shipping_address_line1 = customer.shipping_address_line1
            shipping_address_line2 = customer.shipping_address_line2
            shipping_city = customer.shipping_city
            shipping_state = customer.shipping_state
            shipping_zip = customer.shipping_zip
            shipping_country = customer.shipping_country or "USA"

    # Create sales order
    sales_order = SalesOrder(
        user_id=user_id,
        order_number=order_number,
        order_type="line_item",
        source=source,
        source_order_id=source_order_id,
        product_name=product_name,
        quantity=total_quantity,
        material_type=material_type,
        finish="standard",
        unit_price=total_price / total_quantity if total_quantity > 0 else Decimal("0"),
        total_price=total_price,
        tax_amount=tax_amount,
        tax_rate=tax_rate,
        tax_name=tax_name,
        is_taxable=is_taxable,
        shipping_cost=shipping_cost,
        grand_total=grand_total,
        status="pending",
        payment_status="pending",
        rush_level="standard",
        shipping_address_line1=shipping_address_line1,
        shipping_address_line2=shipping_address_line2,
        shipping_city=shipping_city,
        shipping_state=shipping_state,
        shipping_zip=shipping_zip,
        shipping_country=shipping_country,
        customer_notes=customer_notes,
        internal_notes=internal_notes,
    )

    db.add(sales_order)
    db.flush()

    # Create order lines
    for line_data in validated_lines:
        order_line = SalesOrderLine(
            sales_order_id=sales_order.id,
            product_id=line_data["product_id"],
            material_inventory_id=line_data["material_inventory_id"],
            quantity=line_data["quantity"],
            unit_price=line_data["unit_price"],
            total=line_data["line_total"],
            discount=line_data.get("discount_percent", Decimal("0")),
            tax_rate=Decimal("0"),
            notes=line_data["notes"],
            created_by=created_by_user_id,
        )
        db.add(order_line)

    # Record creation event
    record_order_event(
        db=db,
        order_id=sales_order.id,
        event_type="created",
        title="Order created",
        description=f"Sales order {order_number} created from {source} source",
        user_id=created_by_user_id,
    )

    return sales_order


def convert_quote_to_sales_order(
    db: Session,
    *,
    quote_id: int,
    user_id: int,
    shipping_address_line1: str,
    shipping_address_line2: Optional[str] = None,
    shipping_city: str,
    shipping_state: str,
    shipping_zip: str,
    shipping_country: str = "USA",
    customer_notes: Optional[str] = None,
) -> SalesOrder:
    """
    Convert an accepted quote to a sales order.

    Args:
        quote_id: Quote to convert
        user_id: User requesting conversion
        shipping_*: Shipping address

    Returns:
        Created SalesOrder

    Raises:
        HTTPException: On validation errors
    """
    # Get and validate quote
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    if quote.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to convert this quote")

    if quote.status != "accepted":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot convert quote with status '{quote.status}'. Must be 'accepted'."
        )

    if quote.is_expired:
        raise HTTPException(
            status_code=400,
            detail="Quote has expired. Please request a new quote."
        )

    if quote.sales_order_id is not None:
        raise HTTPException(status_code=400, detail="Quote already converted to sales order")

    if not quote.product_id:
        raise HTTPException(
            status_code=400,
            detail="Quote does not have an associated product. This should have been created during acceptance."
        )

    # Generate order number
    order_number = generate_order_number(db)

    # Create sales order
    sales_order = SalesOrder(
        user_id=user_id,
        quote_id=quote.id,
        order_number=order_number,
        product_name=quote.product_name,
        quantity=quote.quantity,
        material_type=quote.material_type,
        color=quote.color,
        finish=quote.finish,
        unit_price=quote.unit_price,
        total_price=quote.total_price,
        tax_amount=Decimal('0.00'),
        shipping_cost=Decimal('0.00'),
        grand_total=quote.total_price,
        status="pending",
        payment_status="pending",
        rush_level=quote.rush_level,
        shipping_address_line1=shipping_address_line1,
        shipping_address_line2=shipping_address_line2,
        shipping_city=shipping_city,
        shipping_state=shipping_state,
        shipping_zip=shipping_zip,
        shipping_country=shipping_country,
        customer_notes=customer_notes or quote.customer_notes,
        order_type="quote_based",
        source="portal",
        source_order_id=quote.quote_number,
    )

    db.add(sales_order)
    db.flush()

    # Update quote
    quote.sales_order_id = sales_order.id
    quote.converted_at = datetime.now(timezone.utc)

    # Find BOM and routing for production order
    bom = db.query(BOM).filter(
        BOM.product_id == quote.product_id,
        BOM.active.is_(True)
    ).first()

    routing = db.query(Routing).filter(
        Routing.product_id == quote.product_id,
        Routing.is_active.is_(True)
    ).first()

    # Generate production order with retry for code collisions
    estimated_time_minutes = int(quote.print_time_hours * 60) if quote.print_time_hours else None

    max_retries = 3
    for attempt in range(max_retries):
        savepoint = db.begin_nested()
        try:
            po_code = generate_production_order_code(db)

            production_order = ProductionOrder(
                code=po_code,
                product_id=quote.product_id,
                bom_id=bom.id if bom else None,
                routing_id=routing.id if routing else None,
                sales_order_id=sales_order.id,
                quantity_ordered=quote.quantity,
                status="scheduled",
                priority="normal" if quote.rush_level == "standard" else "high",
                estimated_time_minutes=estimated_time_minutes,
                notes=f"Auto-created from Sales Order {order_number}. Quote: {quote.quote_number}",
                created_by=str(user_id),
            )

            db.add(production_order)
            db.flush()

            # Copy routing operations
            if routing:
                copy_routing_to_operations(db, production_order, routing.id)

            break
        except IntegrityError as e:
            savepoint.rollback()
            logger.warning(
                f"PO code generation attempt {attempt + 1}/{max_retries} failed: {str(e)}"
            )
            if attempt >= max_retries - 1:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate unique PO code after {max_retries} attempts"
                )

    logger.info(
        "Production order created from quote",
        extra={
            "production_order_code": po_code,
            "sales_order_number": order_number,
            "product_id": quote.product_id,
            "quote_id": quote.id
        }
    )

    # Record creation event
    record_order_event(
        db=db,
        order_id=sales_order.id,
        event_type="created",
        title="Order created from quote",
        description=f"Sales order {order_number} created from quote {quote.quote_number}",
        user_id=user_id,
    )

    return sales_order


# =============================================================================
# Status Updates
# =============================================================================

def update_sales_order_status(
    db: Session,
    order_id: int,
    new_status: str,
    user_id: int,
    user_email: str,
    internal_notes: Optional[str] = None,
    production_notes: Optional[str] = None,
) -> SalesOrder:
    """
    Update sales order status with automatic production order creation.

    Args:
        order_id: Order to update
        new_status: New status value
        user_id: User making the change
        user_email: User email for production order attribution
        internal_notes: Optional internal notes
        production_notes: Optional production notes

    Returns:
        Updated SalesOrder
    """
    order = get_sales_order(db, order_id)
    old_status = order.status
    order.status = new_status

    # Set timestamps based on status
    if new_status == "confirmed" and old_status == "pending":
        order.confirmed_at = datetime.now(timezone.utc)

        # Auto-create production orders
        existing_pos = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id == order_id
        ).all()

        if not existing_pos:
            created_orders = create_production_orders_for_sales_order(db, order, user_email)
            if created_orders:
                order.status = "in_production"

                # Trigger MRP check if enabled
                try:
                    from app.services.mrp_trigger_service import trigger_mrp_check
                    from app.core.settings import get_settings
                    settings = get_settings()

                    if settings.AUTO_MRP_ON_CONFIRMATION:
                        trigger_mrp_check(db, order.id)
                except Exception as e:
                    logger.warning(
                        f"MRP trigger failed after order confirmation {order.id}: {str(e)}",
                        exc_info=True
                    )

    if new_status == "shipped":
        order.shipped_at = datetime.now(timezone.utc)

    if new_status == "delivered":
        order.delivered_at = datetime.now(timezone.utc)

    if new_status == "completed":
        order.actual_completion_date = datetime.now(timezone.utc)

    if internal_notes:
        order.internal_notes = internal_notes

    if production_notes:
        order.production_notes = production_notes

    # Record status change event
    if old_status != order.status:
        record_order_event(
            db=db,
            order_id=order_id,
            event_type="status_change",
            title=f"Status changed to {order.status.replace('_', ' ').title()}",
            old_value=old_status,
            new_value=order.status,
            user_id=user_id,
        )

    return order


def update_payment_info(
    db: Session,
    order_id: int,
    payment_status: str,
    user_id: int,
    payment_method: Optional[str] = None,
    payment_transaction_id: Optional[str] = None,
) -> SalesOrder:
    """Update payment information for an order."""
    order = get_sales_order(db, order_id)
    old_payment_status = order.payment_status

    order.payment_status = payment_status

    if payment_method:
        order.payment_method = payment_method

    if payment_transaction_id:
        order.payment_transaction_id = payment_transaction_id

    if payment_status == "paid":
        order.paid_at = datetime.now(timezone.utc)

    # Record payment event
    if old_payment_status != payment_status:
        if payment_status == "paid":
            event_type = "payment_received"
            title = "Payment received"
        elif payment_status == "refunded":
            event_type = "payment_refunded"
            title = "Payment refunded"
        else:
            event_type = "status_change"
            title = f"Payment status changed to {payment_status}"

        record_order_event(
            db=db,
            order_id=order_id,
            event_type=event_type,
            title=title,
            old_value=old_payment_status,
            new_value=payment_status,
            user_id=user_id,
            metadata_key="payment_method" if payment_method else None,
            metadata_value=payment_method,
        )

    return order


def update_shipping_info(
    db: Session,
    order_id: int,
    user_id: int,
    tracking_number: Optional[str] = None,
    carrier: Optional[str] = None,
    shipped_at: Optional[datetime] = None,
) -> SalesOrder:
    """Update shipping information for an order."""
    order = get_sales_order(db, order_id)
    is_shipping = order.shipped_at is None and shipped_at is not None

    if tracking_number:
        order.tracking_number = tracking_number

    if carrier:
        order.carrier = carrier

    if shipped_at:
        order.shipped_at = shipped_at
        order.status = "shipped"

    if is_shipping:
        record_order_event(
            db=db,
            order_id=order_id,
            event_type="shipped",
            title="Order shipped",
            description=f"Shipped via {carrier or 'carrier'}" + (f", tracking: {tracking_number}" if tracking_number else ""),
            user_id=user_id,
            metadata_key="tracking_number" if tracking_number else None,
            metadata_value=tracking_number,
        )

    return order


def update_shipping_address(
    db: Session,
    order_id: int,
    user_id: int,
    shipping_address_line1: Optional[str] = None,
    shipping_address_line2: Optional[str] = None,
    shipping_city: Optional[str] = None,
    shipping_state: Optional[str] = None,
    shipping_zip: Optional[str] = None,
    shipping_country: Optional[str] = None,
) -> SalesOrder:
    """Update shipping address for an order."""
    order = get_sales_order(db, order_id)
    address_changed = False

    if shipping_address_line1 is not None:
        order.shipping_address_line1 = shipping_address_line1
        address_changed = True
    if shipping_address_line2 is not None:
        order.shipping_address_line2 = shipping_address_line2
        address_changed = True
    if shipping_city is not None:
        order.shipping_city = shipping_city
        address_changed = True
    if shipping_state is not None:
        order.shipping_state = shipping_state
        address_changed = True
    if shipping_zip is not None:
        order.shipping_zip = shipping_zip
        address_changed = True
    if shipping_country is not None:
        order.shipping_country = shipping_country
        address_changed = True

    order.updated_at = datetime.now(timezone.utc)

    if address_changed:
        record_order_event(
            db=db,
            order_id=order_id,
            event_type="address_updated",
            title="Shipping address updated",
            user_id=user_id,
        )

    return order


# =============================================================================
# Cancel / Delete
# =============================================================================

def cancel_sales_order(
    db: Session,
    order_id: int,
    user_id: int,
    cancellation_reason: str,
) -> SalesOrder:
    """
    Cancel a sales order.

    Args:
        order_id: Order to cancel
        user_id: User cancelling
        cancellation_reason: Reason for cancellation

    Returns:
        Cancelled SalesOrder

    Raises:
        HTTPException: If order cannot be cancelled
    """
    order = get_sales_order(db, order_id)

    if not order.is_cancellable:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel order with status '{order.status}'"
        )

    # Check for linked production orders that aren't cancelled
    linked_wos = db.query(ProductionOrder).filter(
        ProductionOrder.sales_order_id == order_id,
        ProductionOrder.status != "cancelled"
    ).all()

    if linked_wos:
        wo_codes = [wo.code for wo in linked_wos]
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel: {len(linked_wos)} work order(s) still active ({', '.join(wo_codes[:3])}{'...' if len(wo_codes) > 3 else ''}). Cancel work orders first."
        )

    old_status = order.status
    order.status = "cancelled"
    order.cancelled_at = datetime.now(timezone.utc)
    order.cancellation_reason = cancellation_reason

    record_order_event(
        db=db,
        order_id=order_id,
        event_type="cancelled",
        title="Order cancelled",
        description=cancellation_reason,
        old_value=old_status,
        new_value="cancelled",
        user_id=user_id,
    )

    return order


def delete_sales_order(db: Session, order_id: int) -> None:
    """
    Delete a sales order.

    Only cancelled or pending orders can be deleted.

    Raises:
        HTTPException: If order cannot be deleted
    """
    order = get_sales_order(db, order_id)

    deletable_statuses = ["cancelled", "pending"]
    if order.status not in deletable_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete order with status '{order.status}'. Only cancelled or pending orders can be deleted."
        )

    # Check for associated production orders
    existing_pos = db.query(ProductionOrder).filter(
        ProductionOrder.sales_order_id == order_id
    ).all()

    if existing_pos:
        active_pos = [po for po in existing_pos if po.status not in ["cancelled", "draft"]]
        if active_pos:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete order with active production orders: {', '.join([po.code for po in active_pos])}"
            )

    db.delete(order)


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

    Returns:
        Dict with work_orders_needed, purchase_orders_needed, summary
    """
    order = get_sales_order(db, order_id)

    work_orders_needed = []
    purchase_orders_needed = []
    top_level_products = []

    def explode_requirements(
        product_id: int,
        quantity: Decimal,
        level: int = 0,
        parent_sku: Optional[str] = None,
        visited_bom_ids: Optional[set] = None,
    ) -> None:
        """Recursively explode BOM to find all requirements."""
        if visited_bom_ids is None:
            visited_bom_ids = set()

        bom = db.query(BOM).filter(
            BOM.product_id == product_id,
            BOM.active.is_(True)
        ).first()

        if not bom:
            return

        # Prevent circular references
        if bom.id in visited_bom_ids:
            return

        current_path = visited_bom_ids | {bom.id}

        bom_lines = db.query(BOMLine).filter(BOMLine.bom_id == bom.id).all()

        for line in bom_lines:
            if line.is_cost_only:
                continue

            component = db.query(Product).filter(Product.id == line.component_id).first()
            if not component:
                continue

            # Calculate required quantity with scrap
            base_qty = Decimal(str(line.quantity or 0))
            scrap_factor = Decimal(str(line.scrap_factor or 0)) / Decimal("100")
            required_qty = base_qty * (Decimal("1") + scrap_factor) * quantity

            # Get available inventory
            inv_result = db.query(
                func.sum(Inventory.available_quantity)
            ).filter(Inventory.product_id == line.component_id).scalar()
            available_qty = Decimal(str(inv_result or 0))

            shortage_qty = max(Decimal("0"), required_qty - available_qty)

            if shortage_qty <= 0:
                continue

            order_info = {
                "product_id": component.id,
                "product_sku": component.sku,
                "product_name": component.name,
                "unit": line.unit or component.unit,
                "required_qty": float(required_qty),
                "available_qty": float(available_qty),
                "order_qty": float(shortage_qty),
                "bom_level": level,
                "has_bom": component.has_bom or False,
                "parent_sku": parent_sku
            }

            if component.has_bom:
                work_orders_needed.append(order_info)
                explode_requirements(component.id, shortage_qty, level + 1, component.sku, current_path)
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
                        "has_bom": True
                    })

            explode_requirements(product.id, qty, level=0, parent_sku=product.sku)

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
                        "has_bom": True
                    })

            explode_requirements(product.id, qty, level=0, parent_sku=product.sku)

    # Aggregate duplicate materials
    aggregated_pos = {}
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
            "total_orders_needed": len(top_level_products) + len(work_orders_needed) + len(aggregated_pos)
        }
    }


def get_material_requirements(
    db: Session,
    order_id: int,
) -> dict:
    """
    Get material requirements for a sales order.

    Uses routing-first approach:
    1. PRIMARY: Check RoutingOperationMaterial records for operation-level materials
    2. FALLBACK: Check legacy BOM lines if no routing materials exist

    Returns:
        Dict with requirements list and summary
    """
    from app.services.blocking_issues import get_material_available, get_pending_purchase_orders

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
        qty_available = get_material_available(db, component.id)
        qty_short = max(Decimal("0"), qty_required - qty_available)

        # Check for incoming supply
        pending_pos = get_pending_purchase_orders(db, component.id)
        has_incoming = len(pending_pos) > 0
        incoming_details = None
        if has_incoming:
            po, po_qty = pending_pos[0]
            incoming_details = {
                "purchase_order_id": po.id,
                "purchase_order_code": po.po_number,
                "quantity": float(po_qty),
                "expected_date": po.expected_date.isoformat() if po.expected_date else None
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
            existing["quantity_short"] = max(Decimal("0"), existing["quantity_required"] - qty_available)
        else:
            seen_products[key] = {
                "product_id": component.id,
                "product_sku": component.sku,
                "product_name": component.name,
                "unit": unit or component.unit or "EA",
                "quantity_required": qty_required,
                "quantity_available": qty_available,
                "quantity_short": qty_short,
                "operation_code": operation_code,
                "material_source": material_source,
                "has_incoming_supply": has_incoming,
                "incoming_supply_details": incoming_details,
                "has_bom": has_bom
            }

    def process_product(product_id: int, quantity: Decimal):
        """Process material requirements for a product."""
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            return

        has_routing_materials = False

        try:
            routing = db.query(Routing).filter(
                Routing.product_id == product_id,
                Routing.is_active.is_(True)
            ).first()

            if routing:
                routing_materials = db.query(
                    RoutingOperationMaterial,
                    RoutingOperation
                ).join(
                    RoutingOperation,
                    RoutingOperationMaterial.routing_operation_id == RoutingOperation.id
                ).filter(
                    RoutingOperation.routing_id == routing.id,
                    RoutingOperationMaterial.is_cost_only.is_(False)
                ).all()

                if routing_materials:
                    has_routing_materials = True
                    for mat, op in routing_materials:
                        component = db.query(Product).filter(Product.id == mat.component_id).first()
                        if not component:
                            continue

                        qty_required = Decimal(str(mat.calculate_required_quantity(int(quantity))))

                        add_requirement(
                            component=component,
                            qty_required=qty_required,
                            unit=mat.unit or component.unit,
                            operation_code=op.operation_code,
                            material_source="routing"
                        )
        except Exception as e:
            logger.warning(f"Error processing routing materials for product {product_id}: {e}")

        # Fallback to BOM
        if not has_routing_materials:
            bom = db.query(BOM).filter(
                BOM.product_id == product_id,
                BOM.active.is_(True)
            ).first()

            if bom:
                for line in bom.lines:
                    if line.is_cost_only:
                        continue

                    component = db.query(Product).filter(Product.id == line.component_id).first()
                    if not component:
                        continue

                    scrap_factor = Decimal(str(line.scrap_factor or 0)) / 100
                    qty_required = line.quantity * quantity * (1 + scrap_factor)

                    add_requirement(
                        component=component,
                        qty_required=qty_required,
                        unit=line.unit or component.unit,
                        operation_code=line.consume_stage,
                        material_source="bom"
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
    materials_short = sum(1 for r in requirements if r["quantity_short"] > 0)
    materials_with_incoming = sum(1 for r in requirements if r["has_incoming_supply"])

    return {
        "sales_order_id": order.id,
        "order_number": order.order_number,
        "requirements": requirements,
        "summary": {
            "total_materials": total_materials,
            "materials_available": total_materials - materials_short,
            "materials_short": materials_short,
            "materials_with_incoming_supply": materials_with_incoming,
            "can_fulfill": materials_short == 0,
            "has_shortages": materials_short > 0
        }
    }


# =============================================================================
# Shipping
# =============================================================================

def ship_order(
    db: Session,
    order_id: int,
    user_id: int,
    user_email: str,
    carrier: str = "USPS",
    service: Optional[str] = "Priority",
    tracking_number: Optional[str] = None,
) -> dict:
    """
    Ship an order - create label and process inventory.

    Args:
        order_id: Order to ship
        user_id: User shipping
        user_email: User email
        carrier: Shipping carrier
        service: Service level
        tracking_number: Optional pre-existing tracking number

    Returns:
        Dict with tracking info
    """
    import random
    import string
    from app.services.inventory_service import process_shipment
    from app.services.event_service import record_shipping_event

    order = get_sales_order(db, order_id)

    # Validate shipping address
    if not order.shipping_address_line1 or not order.shipping_city:
        raise HTTPException(
            status_code=400,
            detail="Order has no shipping address. Please add one first."
        )

    # Generate tracking number if not provided
    if not tracking_number:
        date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        carrier_prefix = carrier[:3].upper() if carrier else "SHP"
        tracking_number = f"{carrier_prefix}{date_part}{order_id:04d}{random_part}"

    # Update order
    order.tracking_number = tracking_number
    order.carrier = carrier
    order.shipped_at = datetime.now(timezone.utc)
    order.status = "shipped"
    order.updated_at = datetime.now(timezone.utc)

    # Process inventory transactions
    process_shipment(
        db=db,
        sales_order=order,
        created_by=user_email,
    )

    # Record order event
    record_order_event(
        db=db,
        order_id=order_id,
        event_type="shipped",
        title="Order shipped",
        description=f"Shipped via {carrier}" + (f" ({service})" if service else ""),
        user_id=user_id,
        metadata_key="tracking_number",
        metadata_value=tracking_number,
    )

    # Record shipping event
    record_shipping_event(
        db=db,
        sales_order_id=order_id,
        event_type="label_purchased",
        title="Shipping Label Created",
        description=f"Carrier: {carrier}" + (f", Service: {service}" if service else ""),
        tracking_number=tracking_number,
        carrier=carrier,
        user_id=user_id,
        source="manual",
    )

    # Trigger MRP recalculation if enabled
    try:
        from app.services.mrp_trigger_service import trigger_mrp_recalculation
        from app.core.settings import get_settings
        settings = get_settings()

        if settings.AUTO_MRP_ON_SHIPMENT:
            trigger_mrp_recalculation(db, order.id, reason="shipment")
    except Exception as e:
        logger.warning(
            f"MRP recalculation trigger failed after shipping order {order.id}: {str(e)}",
            exc_info=True
        )

    return {
        "message": "Order shipped successfully",
        "tracking_number": tracking_number,
        "carrier": carrier,
        "service": service,
        "shipped_at": order.shipped_at.isoformat(),
        "label_url": None,
    }


# =============================================================================
# Generate Production Orders
# =============================================================================

def generate_production_orders(
    db: Session,
    order_id: int,
    user_email: str,
) -> dict:
    """
    Generate production orders from a sales order.

    For line_item orders: Creates one production order per line item.
    For quote_based orders: Creates a single production order.

    Returns:
        Dict with created_orders and existing_orders lists
    """
    from app.services.inventory_service import reserve_production_materials

    order = get_sales_order(db, order_id)

    if order.status == "cancelled":
        raise HTTPException(
            status_code=400,
            detail="Cannot generate production orders for cancelled sales order"
        )

    # Check for existing production orders
    if order.order_type == "line_item":
        line_product_ids = [line.product_id for line in order.lines if line.product_id]
        existing_pos = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id == order_id,
            ProductionOrder.product_id.in_(line_product_ids)
        ).all()
    else:
        existing_pos = db.query(ProductionOrder).filter(
            ProductionOrder.sales_order_id == order_id
        ).all()

    if existing_pos:
        return {
            "message": "Production orders already exist",
            "existing_orders": [po.code for po in existing_pos],
            "created_orders": []
        }

    created_orders = []
    year = datetime.now(timezone.utc).year

    def get_next_po_code():
        last_po = (
            db.query(ProductionOrder)
            .filter(ProductionOrder.code.like(f"PO-{year}-%"))
            .order_by(desc(ProductionOrder.code))
            .with_for_update()
            .first()
        )
        if last_po:
            last_num = int(last_po.code.split("-")[2])
            next_num = last_num + 1
        else:
            next_num = 1
        return f"PO-{year}-{next_num:04d}"

    if order.order_type == "line_item":
        lines = db.query(SalesOrderLine).filter(
            SalesOrderLine.sales_order_id == order_id
        ).order_by(SalesOrderLine.id).all()

        if not lines:
            raise HTTPException(
                status_code=400,
                detail="Sales order has no line items"
            )

        for idx, line in enumerate(lines, start=1):
            # Skip material-only lines — raw materials don't need production orders
            if not line.product_id:
                continue

            product = db.query(Product).filter(Product.id == line.product_id).first()
            if not product:
                raise HTTPException(
                    status_code=400,
                    detail=f"Product ID {line.product_id} not found for line {idx}"
                )

            bom = db.query(BOM).filter(
                BOM.product_id == line.product_id,
                BOM.active.is_(True)
            ).first()

            routing = db.query(Routing).filter(
                Routing.product_id == line.product_id,
                Routing.is_active.is_(True)
            ).first()

            po_code = get_next_po_code()

            production_order = ProductionOrder(
                code=po_code,
                product_id=line.product_id,
                bom_id=bom.id if bom else None,
                routing_id=routing.id if routing else None,
                sales_order_id=order.id,
                sales_order_line_id=line.id,
                quantity_ordered=line.quantity,
                quantity_completed=0,
                quantity_scrapped=0,
                source="sales_order",
                status="draft",
                priority=3,
                notes=f"Generated from {order.order_number} Line {idx}",
                created_by=user_email,
            )

            db.add(production_order)
            db.flush()

            if routing:
                copy_routing_to_operations(db, production_order, routing.id)

            reserve_production_materials(
                db=db,
                production_order=production_order,
                created_by=user_email,
            )

            created_orders.append(po_code)

    else:
        # quote_based order
        if order.quote_id:
            quote = db.query(Quote).filter(Quote.id == order.quote_id).first()
            if quote and quote.product_id:
                product_id = quote.product_id

                bom = db.query(BOM).filter(
                    BOM.product_id == product_id,
                    BOM.active.is_(True)
                ).first()

                routing = db.query(Routing).filter(
                    Routing.product_id == product_id,
                    Routing.is_active.is_(True)
                ).first()

                po_code = get_next_po_code()

                production_order = ProductionOrder(
                    code=po_code,
                    product_id=product_id,
                    bom_id=bom.id if bom else None,
                    routing_id=routing.id if routing else None,
                    sales_order_id=order.id,
                    quantity_ordered=order.quantity,
                    quantity_completed=0,
                    quantity_scrapped=0,
                    source="sales_order",
                    status="draft",
                    priority=3,
                    notes=f"Generated from {order.order_number}",
                    created_by=user_email,
                )

                db.add(production_order)
                db.flush()

                if routing:
                    copy_routing_to_operations(db, production_order, routing.id)

                reserve_production_materials(
                    db=db,
                    production_order=production_order,
                    created_by=user_email,
                )

                created_orders.append(po_code)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Quote-based order has no product. Please accept the quote first."
                )
        else:
            raise HTTPException(
                status_code=400,
                detail="Quote-based order has no associated quote"
            )

    # Record event
    if created_orders:
        record_order_event(
            db=db,
            order_id=order_id,
            event_type="production_started",
            title=f"Created {len(created_orders)} work order(s)",
            description=f"Work orders: {', '.join(created_orders)}",
            user_id=None,
        )

        # Update order status — only move to in_production when work orders exist
        if order.status == "pending":
            order.status = "in_production"
            order.confirmed_at = datetime.now(timezone.utc)
        elif order.status == "confirmed":
            order.status = "in_production"
    elif order.order_type == "line_item":
        # All lines are material-only — no production needed (pick and ship)
        if order.status == "pending":
            order.status = "confirmed"
            order.confirmed_at = datetime.now(timezone.utc)

    return {
        "message": f"Created {len(created_orders)} production order(s)",
        "created_orders": created_orders,
        "existing_orders": []
    }


# =============================================================================
# Events
# =============================================================================

def list_order_events(
    db: Session,
    order_id: int,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[OrderEvent], int]:
    """
    List order events with pagination.

    Returns:
        (events, total_count) tuple
    """
    query = db.query(OrderEvent).filter(OrderEvent.sales_order_id == order_id)
    total = query.count()

    events = (
        query
        .order_by(desc(OrderEvent.created_at))
        .offset(offset)
        .limit(limit)
        .all()
    )

    return events, total


def add_order_event(
    db: Session,
    order_id: int,
    user_id: int,
    event_type: str,
    title: str,
    description: Optional[str] = None,
    old_value: Optional[str] = None,
    new_value: Optional[str] = None,
    metadata_key: Optional[str] = None,
    metadata_value: Optional[str] = None,
) -> OrderEvent:
    """Add an event to a sales order's activity timeline."""
    event = OrderEvent(
        sales_order_id=order_id,
        user_id=user_id,
        event_type=event_type,
        title=title,
        description=description,
        old_value=old_value,
        new_value=new_value,
        metadata_key=metadata_key,
        metadata_value=metadata_value,
    )

    db.add(event)
    return event


# =============================================================================
# Packing Slip PDF
# =============================================================================

def generate_packing_slip_pdf(db: Session, order_id: int) -> io.BytesIO:
    """Generate a packing slip PDF for a sales order using ReportLab.

    The packing slip includes:
    - Company header (logo, name, address, phone, email)
    - "PACKING SLIP" title
    - Order info (order number, order date, ship date)
    - Ship-to address
    - Items table (SKU, Description, Qty Ordered, Qty Shipped)
    - Notes (if any)
    - Footer

    Returns the BytesIO buffer positioned at the start.
    """
    from xml.sax.saxutils import escape as _xml_escape

    def esc(value: Optional[str]) -> str:
        """Escape user-provided text for ReportLab Paragraph XML."""
        return _xml_escape(value) if value else ""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        Image,
    )

    order = db.query(SalesOrder).filter(SalesOrder.id == order_id).first()
    if not order:
        raise HTTPException(
            status_code=404,
            detail=f"Sales order {order_id} not found",
        )

    # Get company settings
    company_settings = (
        db.query(CompanySettings).filter(CompanySettings.id == 1).first()
    )

    # Create PDF buffer
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Heading1"],
        fontSize=24,
        textColor=colors.HexColor("#2563eb"),
    )
    heading_style = ParagraphStyle(
        "Heading",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=colors.gray,
    )
    normal_style = styles["Normal"]

    # Build content
    content = []

    # ---- Company Header ----
    if company_settings and company_settings.logo_data:
        try:
            logo_buffer = io.BytesIO(company_settings.logo_data)
            logo_img = Image(logo_buffer, width=1.5 * inch, height=1.5 * inch)
            logo_img.hAlign = "LEFT"

            company_info = []
            if company_settings.company_name:
                company_info.append(
                    f"<b>{esc(company_settings.company_name)}</b>"
                )
            if company_settings.company_address_line1:
                company_info.append(esc(company_settings.company_address_line1))
            if company_settings.company_city or company_settings.company_state:
                city_state = (
                    f"{esc(company_settings.company_city or '')}, "
                    f"{esc(company_settings.company_state or '')} "
                    f"{esc(company_settings.company_zip or '')}"
                ).strip(", ")
                company_info.append(city_state)
            if company_settings.company_phone:
                company_info.append(esc(company_settings.company_phone))
            if company_settings.company_email:
                company_info.append(esc(company_settings.company_email))

            header_data = [
                [logo_img, Paragraph("<br/>".join(company_info), normal_style)]
            ]
            header_table = Table(
                header_data, colWidths=[2 * inch, 4.5 * inch]
            )
            header_table.setStyle(
                TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")])
            )
            content.append(header_table)
            content.append(Spacer(1, 0.3 * inch))
        except Exception:
            # If logo fails, continue without it
            pass
    elif company_settings and company_settings.company_name:
        content.append(
            Paragraph(
                f"<b>{esc(company_settings.company_name)}</b>", title_style
            )
        )
        content.append(Spacer(1, 0.2 * inch))

    # ---- Title ----
    content.append(Paragraph("PACKING SLIP", title_style))
    content.append(Spacer(1, 0.2 * inch))

    # ---- Order Info ----
    content.append(Paragraph("ORDER INFORMATION", heading_style))
    content.append(Spacer(1, 0.05 * inch))

    order_date_str = (
        order.created_at.strftime("%B %d, %Y") if order.created_at else "N/A"
    )
    ship_date_str = (
        order.shipped_at.strftime("%B %d, %Y") if order.shipped_at else "N/A"
    )

    order_info_data = [
        ["Order Number:", esc(order.order_number)],
        ["Order Date:", order_date_str],
        ["Ship Date:", ship_date_str],
    ]
    order_info_table = Table(
        order_info_data, colWidths=[1.5 * inch, 4 * inch]
    )
    order_info_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    content.append(order_info_table)
    content.append(Spacer(1, 0.2 * inch))

    # ---- Ship To ----
    content.append(Paragraph("SHIP TO", heading_style))
    content.append(Spacer(1, 0.05 * inch))

    ship_to_parts = []
    if order.customer_name:
        ship_to_parts.append(f"<b>{esc(order.customer_name)}</b>")
    if order.shipping_address_line1:
        ship_to_parts.append(esc(order.shipping_address_line1))
    if order.shipping_address_line2:
        ship_to_parts.append(esc(order.shipping_address_line2))
    city_state_zip = ""
    if order.shipping_city:
        city_state_zip += esc(order.shipping_city)
    if order.shipping_state:
        city_state_zip += f", {esc(order.shipping_state)}"
    if order.shipping_zip:
        city_state_zip += f" {esc(order.shipping_zip)}"
    if city_state_zip:
        ship_to_parts.append(city_state_zip)
    if order.shipping_country and order.shipping_country != "USA":
        ship_to_parts.append(esc(order.shipping_country))

    if ship_to_parts:
        content.append(
            Paragraph("<br/>".join(ship_to_parts), normal_style)
        )
    else:
        content.append(Paragraph("No shipping address on file", normal_style))
    content.append(Spacer(1, 0.2 * inch))

    # ---- Items Table ----
    content.append(Paragraph("ITEMS", heading_style))
    content.append(Spacer(1, 0.1 * inch))

    table_data = [["SKU", "Description", "Qty Ordered", "Qty Shipped"]]

    # Eagerly load lines for multi-line orders
    lines = (
        db.query(SalesOrderLine)
        .filter(SalesOrderLine.sales_order_id == order.id)
        .all()
    )

    if lines:
        # Multi-line order
        for line in lines:
            if line.product_id:
                product = (
                    db.query(Product)
                    .filter(Product.id == line.product_id)
                    .first()
                )
                sku = product.sku if product else ""
                description = product.name if product else ""
            elif line.material_inventory_id:
                material = (
                    db.query(MaterialInventory)
                    .filter(MaterialInventory.id == line.material_inventory_id)
                    .first()
                )
                sku = material.sku if material else ""
                description = material.display_name if material else ""
            else:
                sku = ""
                description = ""
            qty_ordered = str(int(line.quantity)) if line.quantity else "0"
            qty_shipped = (
                str(int(line.shipped_quantity))
                if line.shipped_quantity
                else qty_ordered
            )
            table_data.append(
                [sku, esc(description), qty_ordered, qty_shipped]
            )
    else:
        # Single-product order (quote-based)
        product = None
        if order.product_id:
            product = (
                db.query(Product)
                .filter(Product.id == order.product_id)
                .first()
            )
        sku = product.sku if product else ""
        description = esc(
            order.product_name or (product.name if product else "")
        )
        qty_ordered = str(order.quantity or 0)
        qty_shipped = qty_ordered  # Assume full shipment for single-product
        table_data.append([sku, description, qty_ordered, qty_shipped])

    items_table = Table(
        table_data,
        colWidths=[1.5 * inch, 3 * inch, 1 * inch, 1 * inch],
    )
    items_table.setStyle(
        TableStyle(
            [
                # Header row
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#f3f4f6"),
                ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                # Data rows
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
                # Grid
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, 0),
                    1,
                    colors.HexColor("#e5e7eb"),
                ),
                (
                    "LINEBELOW",
                    (0, 1),
                    (-1, -1),
                    0.5,
                    colors.HexColor("#e5e7eb"),
                ),
                # Center-align quantity columns
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
            ]
        )
    )
    content.append(items_table)
    content.append(Spacer(1, 0.3 * inch))

    # ---- Notes ----
    if order.customer_notes:
        content.append(Paragraph("NOTES", heading_style))
        content.append(Paragraph(esc(order.customer_notes), normal_style))
        content.append(Spacer(1, 0.2 * inch))

    # ---- Footer ----
    content.append(Spacer(1, 0.3 * inch))
    content.append(Paragraph("Thank you for your business!", normal_style))

    # Build PDF
    doc.build(content)
    pdf_buffer.seek(0)

    return pdf_buffer
