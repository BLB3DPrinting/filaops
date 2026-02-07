"""
Pydantic schemas for authentication endpoints

Request and response models for user registration, login, and token management
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    """Schema for user registration request"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)

    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets security requirements"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')

        # Check for at least one number
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one number')

        # Check for at least one uppercase letter
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')

        # Check for at least one lowercase letter
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')

        return v


class UserResponse(BaseModel):
    """Schema for user data response"""
    id: int
    customer_number: Optional[str] = None
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    status: str
    account_type: str
    email_verified: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    # Address fields
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_zip: Optional[str] = None
    billing_country: Optional[str] = None

    shipping_address_line1: Optional[str] = None
    shipping_address_line2: Optional[str] = None
    shipping_city: Optional[str] = None
    shipping_state: Optional[str] = None
    shipping_zip: Optional[str] = None
    shipping_country: Optional[str] = None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """Schema for token response (login/register/refresh)"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserWithTokens(UserResponse):
    """Schema for user registration response (includes tokens)"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request"""
    refresh_token: str


class TokenData(BaseModel):
    """Schema for decoded token data"""
    user_id: Optional[int] = None


# ============================================================================
# PORTAL-SPECIFIC SCHEMAS (simplified for frontend)
# ============================================================================

class PortalLogin(BaseModel):
    """Simple JSON login for portal (no OAuth form)"""
    email: EmailStr
    password: str


class PortalRegister(BaseModel):
    """Simple registration for portal customers"""
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)
    first_name: Optional[str] = Field(None, max_length=100)
    last_name: Optional[str] = Field(None, max_length=100)
    company_name: Optional[str] = Field(None, max_length=200)
    phone: Optional[str] = Field(None, max_length=20)


class PortalCustomerResponse(BaseModel):
    """Simplified customer response for portal session storage"""
    id: int
    customer_number: Optional[str] = None
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None

    model_config = {"from_attributes": True}


class CustomerAccessInfo(BaseModel):
    """Customer info for multi-customer portal access"""
    id: int
    customer_number: Optional[str] = None
    company_name: Optional[str] = None
    # Location info (for multi-location orgs)
    first_name: Optional[str] = None  # Contact name
    last_name: Optional[str] = None
    # B2B info (price_level available in PRO)
    payment_terms: Optional[str] = None  # e.g., "net30"
    credit_limit: Optional[float] = None
    # User's role for this customer
    role: str = "member"  # admin, member, viewer
    is_default: bool = False

    model_config = {"from_attributes": True}


class MultiCustomerLoginResponse(BaseModel):
    """Login response with all customers the user can access"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: PortalCustomerResponse
    customers: list[CustomerAccessInfo]
    default_customer_id: Optional[int] = None


# ============================================================================
# PASSWORD RESET SCHEMAS
# ============================================================================

class PasswordResetApprovalRequest(BaseModel):
    """Schema for admin approval/denial of password reset via POST"""
    approval_token: str
    reason: Optional[str] = None


class PasswordResetRequestCreate(BaseModel):
    """Schema for requesting a password reset"""
    email: EmailStr


class PasswordResetRequestResponse(BaseModel):
    """Schema for password reset request response"""
    message: str
    request_id: Optional[int] = None
    reset_token: Optional[str] = None  # Provided if auto-approved (no email configured)
    reset_url: Optional[str] = None  # Full reset URL if auto-approved


class PasswordResetApprovalResponse(BaseModel):
    """Schema for admin approval/denial response"""
    message: str
    user_email: str
    status: str


class PasswordResetComplete(BaseModel):
    """Schema for completing a password reset"""
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @field_validator('new_password')
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password meets security requirements"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one number')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
            raise ValueError('Password must contain at least one lowercase letter')
        return v


class PasswordResetStatus(BaseModel):
    """Schema for checking reset request status"""
    status: str
    message: str
    can_reset: bool = False
