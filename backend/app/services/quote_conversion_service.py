"""
Quote Conversion Service

Handles the complete quote-to-order conversion workflow:
1. Create custom Product
2. Create BOM (material + packaging)
3. Create Sales Order
4. Create Production Order

This is the canonical conversion flow - all quote acceptance paths should use this.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from dataclasses import dataclass

from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import Quote, Product, BOM, SalesOrder, ProductionOrder
from app.services.bom_service import auto_create_product_and_bom, validate_quote_for_bom
from app.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ShippingInfo:
    """Shipping information for order creation"""
    shipping_name: Optional[str] = None
    shipping_address_line1: Optional[str] = None
    shipping_address_line2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None
    shipping_country: str = "USA"
    shipping_phone: Optional[str] = None
    shipping_carrier: Optional[str] = None
    shipping_service: Optional[str] = None
    shipping_cost: Optional[Decimal] = None


@dataclass
class ConversionResult:
    """Result of quote conversion"""
    success: bool
    quote: Quote
    product: Optional[Product] = None
    bom: Optional[BOM] = None
    sales_order: Optional[SalesOrder] = None
    production_order: Optional[ProductionOrder] = None
    error_message: Optional[str] = None


def generate_sales_order_number(db: Session) -> str:
    """Generate next sales order number in format SO-YYYY-NNN"""
    year = datetime.now(timezone.utc).year
    last_order = (
        db.query(SalesOrder)
        .filter(SalesOrder.order_number.like(f"SO-{year}-%"))
        .order_by(desc(SalesOrder.order_number))
        .first()
    )

    if last_order:
        last_num = int(last_order.order_number.split("-")[2])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"SO-{year}-{next_num:03d}"


def generate_production_order_code(db: Session) -> str:
    """Generate next production order code in format PO-YYYY-NNN"""
    year = datetime.now(timezone.utc).year
    last_po = (
        db.query(ProductionOrder)
        .filter(ProductionOrder.code.like(f"PO-{year}-%"))
        .order_by(desc(ProductionOrder.code))
        .first()
    )

    if last_po:
        last_num = int(last_po.code.split("-")[2])
        next_num = last_num + 1
    else:
        next_num = 1

    return f"PO-{year}-{next_num:03d}"


def convert_portal_quote_to_order(
    quote: Quote,
    db: Session,
    shipping: Optional[ShippingInfo] = None,
    payment_status: str = "pending",
    auto_confirm: bool = False,
) -> ConversionResult:
    """
    Portal/automation quote-to-order conversion (full pipeline).

    Unlike quote_service.convert_quote_to_order (admin path — SalesOrder only),
    this handles the complete portal conversion flow:
    1. Validate quote data
    2. Create custom Product (if not exists)
    3. Create BOM with material and packaging
    4. Create Sales Order
    5. Create Production Order

    Args:
        quote: The accepted Quote object
        db: Database session
        shipping: Optional shipping information (uses quote's shipping if not provided)
        payment_status: Initial payment status (default: "pending")
        auto_confirm: If True, set order status to "confirmed" instead of "pending"

    Returns:
        ConversionResult with all created objects or error message
    """
    # Step 1: Validate quote
    if quote.status not in ["accepted", "approved"]:
        return ConversionResult(
            success=False,
            quote=quote,
            error_message=f"Quote status must be 'accepted' or 'approved', got '{quote.status}'"
        )
    
    if quote.is_expired:
        return ConversionResult(
            success=False,
            quote=quote,
            error_message="Quote has expired"
        )
    
    if quote.sales_order_id is not None:
        return ConversionResult(
            success=False,
            quote=quote,
            error_message=f"Quote already converted to Sales Order ID {quote.sales_order_id}"
        )
    
    # Validate quote has data needed for BOM
    is_valid, validation_msg = validate_quote_for_bom(quote, db)
    if not is_valid:
        return ConversionResult(
            success=False,
            quote=quote,
            error_message=f"Quote validation failed: {validation_msg}"
        )
    
    try:
        # Step 2 & 3: Create Product and BOM (if not already created)
        product = None
        bom = None
        
        if quote.product_id:
            # Product already exists (created during quote acceptance)
            product = db.get(Product, quote.product_id)
            bom = db.query(BOM).filter(
                BOM.product_id == product.id,
                BOM.active.is_(True)
            ).first()
        else:
            # Create product and BOM now
            product, bom = auto_create_product_and_bom(quote, db)
        
        # Step 4: Create Sales Order
        order_number = generate_sales_order_number(db)
        
        # Use provided shipping or fall back to quote's shipping
        ship = shipping or ShippingInfo()
        shipping_line1 = ship.shipping_address_line1 or quote.shipping_address_line1
        shipping_line2 = ship.shipping_address_line2 or quote.shipping_address_line2
        shipping_city = ship.shipping_city or quote.shipping_city
        shipping_state = ship.shipping_state or quote.shipping_state
        shipping_zip = ship.shipping_zip or quote.shipping_zip
        shipping_country = ship.shipping_country or quote.shipping_country or "USA"
        shipping_cost = ship.shipping_cost or quote.shipping_cost or Decimal('0.00')
        
        # Calculate grand total
        grand_total = quote.total_price + (shipping_cost or Decimal('0.00'))
        
        sales_order = SalesOrder(
            user_id=quote.user_id,
            quote_id=quote.id,
            order_number=order_number,
            product_name=quote.product_name or f"Custom Print - {quote.quote_number}",
            quantity=quote.quantity,
            material_type=quote.material_type,
            finish=quote.finish or "standard",
            unit_price=quote.unit_price or (quote.total_price / quote.quantity),
            total_price=quote.total_price,
            tax_amount=Decimal('0.00'),  # Tax calculated separately if needed
            shipping_cost=shipping_cost,
            grand_total=grand_total,
            status="confirmed" if auto_confirm else "pending",
            payment_status=payment_status,
            rush_level=quote.rush_level or "standard",
            shipping_address_line1=shipping_line1,
            shipping_address_line2=shipping_line2,
            shipping_city=shipping_city,
            shipping_state=shipping_state,
            shipping_zip=shipping_zip,
            shipping_country=shipping_country,
            customer_notes=quote.customer_notes,
            # Hybrid architecture fields
            order_type="quote_based",
            source="portal",
            source_order_id=quote.quote_number,
        )
        
        if ship.shipping_carrier:
            sales_order.carrier = ship.shipping_carrier
        
        db.add(sales_order)
        db.flush()  # Get sales_order.id
        
        # Step 5: Create Production Order
        po_code = generate_production_order_code(db)
        
        # Calculate estimated print time from quote
        estimated_time_minutes = None
        if quote.print_time_hours:
            estimated_time_minutes = int(float(quote.print_time_hours) * 60)
        
        # Map rush level to priority (1=highest, 5=lowest)
        priority_map = {
            "standard": 3,
            "rush": 2,
            "super_rush": 2,
            "urgent": 1,
        }
        priority = priority_map.get(quote.rush_level, 3)
        
        production_order = ProductionOrder(
            code=po_code,
            product_id=product.id,
            bom_id=bom.id if bom else None,
            sales_order_id=sales_order.id,  # Link to sales order
            quantity_ordered=quote.quantity,
            status="scheduled",  # Ready for production
            priority=priority,
            estimated_time_minutes=estimated_time_minutes,
            notes=f"Auto-created from Sales Order {order_number}. Quote: {quote.quote_number}",
        )
        
        db.add(production_order)
        
        # Update quote with conversion info
        quote.status = "converted"
        quote.sales_order_id = sales_order.id
        quote.converted_at = datetime.now(timezone.utc)
        
        # Commit all changes
        db.commit()
        db.refresh(quote)
        db.refresh(sales_order)
        db.refresh(production_order)
        
        logger.info(
            "Quote converted to sales order and production order",
            extra={
                "quote_number": quote.quote_number,
                "sales_order_number": order_number,
                "production_order_code": po_code,
                "product_id": product.id,
                "product_sku": product.sku,
                "bom_id": bom.id if bom else None
            }
        )
        
        return ConversionResult(
            success=True,
            quote=quote,
            product=product,
            bom=bom,
            sales_order=sales_order,
            production_order=production_order,
        )
        
    except ValueError as e:
        db.rollback()
        return ConversionResult(
            success=False,
            quote=quote,
            error_message=f"Validation error: {str(e)}"
        )
    except RuntimeError as e:
        db.rollback()
        return ConversionResult(
            success=False,
            quote=quote,
            error_message=f"Runtime error: {str(e)}"
        )
    except Exception as e:
        db.rollback()
        return ConversionResult(
            success=False,
            quote=quote,
            error_message=f"Unexpected error: {str(e)}"
        )


def convert_quote_after_payment(
    quote_id: int,
    db: Session,
    payment_transaction_id: str,
    payment_method: str = "manual",
) -> ConversionResult:
    """
    Convenience function to convert a quote after successful payment.

    Sets payment_status to "paid" and auto-confirms the order.

    Args:
        quote_id: ID of the quote to convert
        db: Database session
        payment_transaction_id: External payment transaction ID
        payment_method: Payment method used (default: "manual")

    Returns:
        ConversionResult
    """
    quote = db.query(Quote).filter(Quote.id == quote_id).first()
    
    if not quote:
        return ConversionResult(
            success=False,
            quote=None,
            error_message=f"Quote {quote_id} not found"
        )
    
    result = convert_portal_quote_to_order(
        quote=quote,
        db=db,
        payment_status="paid",
        auto_confirm=True,
    )
    
    # Update payment info on the sales order
    if result.success and result.sales_order:
        result.sales_order.payment_method = payment_method
        result.sales_order.payment_transaction_id = payment_transaction_id
        result.sales_order.paid_at = datetime.now(timezone.utc)
        db.commit()
    
    return result
