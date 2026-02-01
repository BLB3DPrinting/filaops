"""
User model for customer portal authentication
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class User(Base):
    """
    User model for customer authentication and profile management

    Represents a customer who can place orders through the portal
    """
    __tablename__ = "users"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Customer Number (auto-generated, human-readable reference)
    # Note: unique constraint handled by filtered index in DB (allows multiple NULLs for non-customers)
    customer_number = Column(String(20), nullable=True, index=True)  # CUST-001, CUST-002

    # Authentication
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    email_verified = Column(Boolean, default=False, nullable=False)

    # Profile Information
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    company_name = Column(String(200), nullable=True)
    phone = Column(String(20), nullable=True)

    # Billing Address
    billing_address_line1 = Column(String(255), nullable=True)
    billing_address_line2 = Column(String(255), nullable=True)
    billing_city = Column(String(100), nullable=True)
    billing_state = Column(String(50), nullable=True)
    billing_zip = Column(String(20), nullable=True)
    billing_country = Column(String(100), default='USA', nullable=True)

    # Shipping Address
    shipping_address_line1 = Column(String(255), nullable=True)
    shipping_address_line2 = Column(String(255), nullable=True)
    shipping_city = Column(String(100), nullable=True)
    shipping_state = Column(String(50), nullable=True)
    shipping_zip = Column(String(20), nullable=True)
    shipping_country = Column(String(100), default='USA', nullable=True)

    # Account Status
    status = Column(String(20), default='active', nullable=False, index=True)  # active, inactive, suspended
    account_type = Column(String(20), default='customer', nullable=False)  # customer, admin, operator

    # Timestamps (using timezone=False for PostgreSQL TIMESTAMP compatibility)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=False), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=False), nullable=True)

    # Audit
    created_by = Column(Integer, nullable=True)  # NULL for self-registration
    updated_by = Column(Integer, nullable=True)

    # Customer Organization Link (B2B)
    # Portal users can be linked to a Customer organization
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='SET NULL'), nullable=True, index=True)

    # Relationships
    customer = relationship("Customer", back_populates="users")
    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    quotes = relationship("Quote", back_populates="user", foreign_keys="[Quote.user_id]", cascade="all, delete-orphan")
    sales_orders = relationship("SalesOrder", back_populates="user", foreign_keys="[SalesOrder.user_id]", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', status='{self.status}')>"

    @property
    def full_name(self) -> str:
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.email

    @property
    def is_active(self) -> bool:
        """Check if user account is active"""
        return self.status == 'active'

    @property
    def is_admin(self) -> bool:
        """Check if user is an admin"""
        return self.account_type == 'admin'


class RefreshToken(Base):
    """
    Refresh token model for JWT token rotation

    Stores hashed refresh tokens for secure token refresh
    """
    __tablename__ = "refresh_tokens"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign Key
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Token Data
    token_hash = Column(String(255), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=False), nullable=False, index=True)
    revoked = Column(Boolean, default=False, nullable=False)

    # Timestamps (using timezone=False for PostgreSQL TIMESTAMP compatibility)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=False), nullable=True)

    # Relationships
    user = relationship("User", back_populates="refresh_tokens")

    def __repr__(self):
        return f"<RefreshToken(id={self.id}, user_id={self.user_id}, revoked={self.revoked})>"

    @property
    def is_valid(self) -> bool:
        """Check if refresh token is still valid (not revoked and not expired)"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return not self.revoked and self.expires_at > now


class PasswordResetRequest(Base):
    """
    Password reset request model requiring admin approval

    Flow:
    1. User requests password reset
    2. Admin receives email with approve/deny links
    3. Admin approves request
    4. User can now reset password with the token
    """
    __tablename__ = "password_reset_requests"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign Key
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Token for reset (sent to user after approval)
    token = Column(String(255), unique=True, nullable=False, index=True)

    # Admin approval token (for approve/deny links)
    approval_token = Column(String(255), unique=True, nullable=False, index=True)

    # Status: pending, approved, denied, completed, expired
    status = Column(String(20), default='pending', nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=False), nullable=False)
    approved_at = Column(DateTime(timezone=False), nullable=True)
    completed_at = Column(DateTime(timezone=False), nullable=True)

    # Admin notes (optional reason for denial)
    admin_notes = Column(String(500), nullable=True)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<PasswordResetRequest(id={self.id}, user_id={self.user_id}, status='{self.status}')>"

    @property
    def is_valid(self) -> bool:
        """Check if reset request can be used"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.status == 'approved' and self.expires_at > now

    @property
    def is_pending(self) -> bool:
        """Check if waiting for admin approval"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return self.status == 'pending' and self.expires_at > now
