"""
Sales Order Pydantic Schemas
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from app.schemas.fulfillment_status import FulfillmentStatusSummary


# ============================================================================
# Request Schemas
# ============================================================================

class SalesOrderLineCreate(BaseModel):
    """Line item for manual order creation.

    Exactly one of product_id or material_inventory_id must be provided.
    """
    product_id: Optional[int] = Field(None, description="Product ID (for finished goods)")
    material_inventory_id: Optional[int] = Field(None, description="Material inventory ID (for raw material / filament)")
    quantity: Decimal = Field(..., gt=0, le=10000, description="Quantity — integer for products, fractional for materials (e.g. 0.5 kg)")
    unit_price: Optional[Decimal] = Field(None, ge=0, description="Unit price (uses product/material price if not specified)")
    notes: Optional[str] = Field(None, max_length=500)

    @model_validator(mode="after")
    def exactly_one_item_ref(self) -> "SalesOrderLineCreate":
        has_product = self.product_id is not None
        has_material = self.material_inventory_id is not None
        if has_product == has_material:  # both True or both False
            raise ValueError(
                "Exactly one of product_id or material_inventory_id must be provided"
            )
        if has_product and self.quantity != self.quantity.to_integral_value():
            raise ValueError("Product line quantity must be a whole number")
        return self


class SalesOrderCreate(BaseModel):
    """Create a manual sales order (line_item type)"""
    # Order lines (at least one required)
    lines: List[SalesOrderLineCreate] = Field(..., min_length=1, description="Order lines")

    # Customer (optional - if not set, uses admin user as placeholder)
    customer_id: Optional[int] = Field(None, description="Customer ID (from Customers module)")
    customer_email: Optional[str] = Field(None, max_length=255, description="Customer email (for guest orders)")
    source: str = Field("manual", description="Order source: manual, squarespace, woocommerce")
    source_order_id: Optional[str] = Field(None, max_length=255, description="External order ID")

    # Shipping
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=50)
    shipping_zip: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field("USA", max_length=100)
    shipping_cost: Optional[Decimal] = Field(Decimal("0"), ge=0)

    # Notes
    customer_notes: Optional[str] = Field(None, max_length=5000)
    internal_notes: Optional[str] = Field(None, max_length=5000)


class SalesOrderConvert(BaseModel):
    """Request to convert quote to sales order"""
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=50)
    shipping_zip: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field("USA", max_length=100)
    customer_notes: Optional[str] = Field(None, max_length=5000)


class SalesOrderUpdateStatus(BaseModel):
    """Update sales order status (admin)"""
    status: str = Field(..., description="Order status")
    internal_notes: Optional[str] = Field(None, description="Internal notes")
    production_notes: Optional[str] = Field(None, description="Production notes")


class SalesOrderUpdatePayment(BaseModel):
    """Update payment information"""
    payment_status: str = Field(..., description="Payment status")
    payment_method: Optional[str] = Field(None, description="Payment method")
    payment_transaction_id: Optional[str] = Field(None, description="Transaction ID")


class SalesOrderUpdateShipping(BaseModel):
    """Update shipping information (tracking, carrier, date)"""
    tracking_number: Optional[str] = Field(None, max_length=255)
    carrier: Optional[str] = Field(None, max_length=100)
    shipped_at: Optional[datetime] = None

    @field_validator('shipped_at')
    @classmethod
    def validate_shipped_at(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Validate shipped date is reasonable (between 2000-2099)"""
        if v is not None:
            if v.year < 2000 or v.year > 2099:
                raise ValueError('Shipped date must be between year 2000 and 2099')
        return v


class SalesOrderUpdateAddress(BaseModel):
    """Update shipping address on an order"""
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=50)
    shipping_zip: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field(None, max_length=100)


class SalesOrderCancel(BaseModel):
    """Cancel sales order"""
    cancellation_reason: str = Field(..., max_length=1000)


class SalesOrderLineUpdate(BaseModel):
    """Update a single line item quantity"""
    line_id: int = Field(..., description="ID of the line to update")
    new_quantity: Decimal = Field(..., gt=0, le=10000, description="New quantity (must be >= shipped quantity)")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for the change")


class SalesOrderEditLines(BaseModel):
    """Edit one or more line quantities on a sales order"""
    lines: List[SalesOrderLineUpdate] = Field(..., min_length=1)


class SalesOrderCloseShort(BaseModel):
    """Close an order short - accept partial fulfillment"""
    reason: str = Field(..., min_length=1, max_length=1000, description="Reason for closing short")


# ============================================================================
# Response Schemas
# ============================================================================

class SalesOrderBase(BaseModel):
    """Base sales order fields"""
    order_number: str
    status: str
    fulfillment_status: str
    product_name: Optional[str]
    quantity: int
    material_type: str
    finish: str
    unit_price: Decimal
    total_price: Decimal
    tax_amount: Decimal
    shipping_cost: Decimal
    grand_total: Decimal
    payment_status: str
    rush_level: str


class SalesOrderListResponse(SalesOrderBase):
    """Sales order list item"""
    id: int
    quote_id: Optional[int]
    product_id: Optional[int] = None  # Direct product link
    source: Optional[str] = None
    source_order_id: Optional[str] = None
    created_at: datetime
    confirmed_at: Optional[datetime]
    submitted_at: Optional[datetime] = None
    estimated_completion_date: Optional[datetime]
    # Shipping address fields for shipping page
    shipping_address_line1: Optional[str] = None
    shipping_address_line2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None
    shipping_country: Optional[str] = None
    tracking_number: Optional[str] = None
    # Fulfillment status summary (optional, only when include_fulfillment=true)
    fulfillment: Optional[FulfillmentStatusSummary] = None

    class Config:
        from_attributes = True


class SalesOrderLineResponse(BaseModel):
    """Sales order line item response"""
    id: int
    product_id: Optional[int] = None
    material_inventory_id: Optional[int] = None
    product_sku: Optional[str] = None
    product_name: Optional[str] = None
    material_sku: Optional[str] = None
    material_name: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    total: Decimal  # Matches model field name
    discount: Optional[Decimal] = Decimal("0")
    allocated_quantity: Optional[Decimal] = Decimal("0")
    shipped_quantity: Optional[Decimal] = Decimal("0")
    original_quantity: Optional[Decimal] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True


class SalesOrderResponse(SalesOrderBase):
    """Full sales order details"""
    id: int
    user_id: int
    quote_id: Optional[int]
    product_id: Optional[int] = None  # Direct product link for BOM explosion

    # Order type and source
    order_type: Optional[str] = None  # 'quote_based' or 'line_item'
    source: Optional[str] = None  # 'portal', 'manual', 'squarespace', 'woocommerce'
    source_order_id: Optional[str] = None
    
    # Order status (two-tier model: order status + fulfillment status)
    fulfillment_status: Optional[str] = None  # Shipping workflow status

    # Line items (for line_item type orders)
    lines: List[SalesOrderLineResponse] = []

    # Customer Information
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None

    # Payment
    payment_method: Optional[str]
    payment_transaction_id: Optional[str]
    paid_at: Optional[datetime]

    # Production
    estimated_completion_date: Optional[datetime]
    actual_completion_date: Optional[datetime]

    # Shipping
    shipping_address_line1: Optional[str]
    shipping_address_line2: Optional[str]
    shipping_city: Optional[str]
    shipping_state: Optional[str]
    shipping_zip: Optional[str]
    shipping_country: Optional[str]
    tracking_number: Optional[str]
    carrier: Optional[str]
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]

    # Notes
    customer_notes: Optional[str]
    internal_notes: Optional[str]
    production_notes: Optional[str]

    # Cancellation
    cancelled_at: Optional[datetime]
    cancellation_reason: Optional[str]

    # Close Short
    closed_short: Optional[bool] = False
    closed_short_at: Optional[datetime] = None
    close_short_reason: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    confirmed_at: Optional[datetime]
    submitted_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SalesOrderStatsResponse(BaseModel):
    """Sales order statistics"""
    total_orders: int
    pending_confirmation_orders: int
    pending_orders: int
    confirmed_orders: int
    in_production_orders: int
    completed_orders: int
    cancelled_orders: int
    total_revenue: Decimal
    pending_revenue: Decimal
