"""
Customer Pydantic Schemas

For admin management of customers (users with account_type='customer')
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional
from datetime import datetime


# ============================================================================
# Customer Schemas
# ============================================================================

class CustomerBase(BaseModel):
    """Base customer fields"""
    email: EmailStr
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)

    # Billing Address
    billing_address_line1: Optional[str] = Field(None, max_length=255)
    billing_address_line2: Optional[str] = Field(None, max_length=255)
    billing_city: Optional[str] = Field(None, max_length=100)
    billing_state: Optional[str] = Field(None, max_length=50)
    billing_zip: Optional[str] = Field(None, max_length=20)
    billing_country: Optional[str] = Field("USA", max_length=100)

    # Shipping Address
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=50)
    shipping_zip: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field("USA", max_length=100)


class CustomerCreate(CustomerBase):
    """Create a new customer (CRM record only)

    Note: Customer portal login is a Pro feature. In open source,
    customers are CRM records for order management only.
    """
    status: Optional[str] = Field("active")


class CustomerUpdate(BaseModel):
    """Update an existing customer"""
    email: Optional[EmailStr] = None
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)
    status: Optional[str] = None  # active, inactive, suspended

    # Billing Address
    billing_address_line1: Optional[str] = Field(None, max_length=255)
    billing_address_line2: Optional[str] = Field(None, max_length=255)
    billing_city: Optional[str] = Field(None, max_length=100)
    billing_state: Optional[str] = Field(None, max_length=50)
    billing_zip: Optional[str] = Field(None, max_length=20)
    billing_country: Optional[str] = Field(None, max_length=100)

    # Shipping Address
    shipping_address_line1: Optional[str] = Field(None, max_length=255)
    shipping_address_line2: Optional[str] = Field(None, max_length=255)
    shipping_city: Optional[str] = Field(None, max_length=100)
    shipping_state: Optional[str] = Field(None, max_length=50)
    shipping_zip: Optional[str] = Field(None, max_length=20)
    shipping_country: Optional[str] = Field(None, max_length=100)


class CustomerListResponse(BaseModel):
    """Customer list item (summary)"""
    id: int
    customer_number: Optional[str] = None
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    status: str

    # Derived fields
    full_name: Optional[str] = None

    # Shipping address for order creation
    shipping_address_line1: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None

    # Stats
    order_count: int = 0
    total_spent: float = 0.0
    last_order_date: Optional[datetime] = None

    # PRO price level discount (None if PRO not installed)
    discount_percent: Optional[float] = None

    created_at: datetime

    class Config:
        from_attributes = True


class CustomerResponse(CustomerBase):
    """Full customer details"""
    id: int
    customer_number: Optional[str] = None
    status: str
    email_verified: bool = False

    # Timestamps
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None

    # Stats
    order_count: int = 0
    quote_count: int = 0
    total_spent: float = 0.0

    # PRO price level discount (None if PRO not installed)
    discount_percent: Optional[float] = None

    class Config:
        from_attributes = True


class CustomerSearchResult(BaseModel):
    """Lightweight customer search result for dropdowns"""
    id: int
    customer_number: Optional[str] = None
    email: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None

    class Config:
        from_attributes = True
