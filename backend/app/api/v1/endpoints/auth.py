"""
Authentication endpoints for FilaOps Core

Handles user registration, login, token refresh, and profile retrieval
"""
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.limiter import limiter

from app.db.session import get_db
from app.models.user import User, RefreshToken, PasswordResetRequest
from app.schemas.auth import (
    UserRegister,
    UserResponse,
    UserWithTokens,
    TokenResponse,
    RefreshTokenRequest,
    PasswordResetRequestCreate,
    PasswordResetRequestResponse,
    PasswordResetApprovalResponse,
    PasswordResetComplete,
    PasswordResetStatus,
)
import secrets
from app.core.config import settings
from app.services.email_service import email_service
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    get_user_from_token,
    hash_refresh_token,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from app.logging_config import get_logger
# Re-exports for backwards compatibility (prefer importing from app.api.v1.deps directly)
from app.api.v1.deps import get_current_admin_user as get_current_admin_user  # noqa: F401, E402
from app.api.v1.deps import get_current_staff_user as get_current_staff_user  # noqa: F401, E402

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# ============================================================================
# DEPENDENCY: Get Current User
# ============================================================================

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db)
) -> User:
    """
    Dependency to get the current authenticated user from access token

    Args:
        token: JWT access token from Authorization header
        db: Database session

    Returns:
        User object if token is valid

    Raises:
        HTTPException 401 if token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode token and extract user ID
    user_id = get_user_from_token(token, expected_type="access")
    if user_id is None:
        raise credentials_exception

    # Get user from database
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )

    return user


# ============================================================================
# ENDPOINT: User Registration
# ============================================================================

@router.post("/register", response_model=UserWithTokens, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")  # type: ignore
async def register_user(
    request: Request,
    user_data: UserRegister,
    db: Session = Depends(get_db)
):
    """
    Register a new user

    Creates a new user account with the provided email and password.
    Returns the user profile along with access and refresh tokens for immediate login.

    Args:
        user_data: User registration data (email, password, name, etc.)
        db: Database session

    Returns:
        User profile with access and refresh tokens

    Raises:
        HTTPException 400 if email is already registered
    """
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash password
    password_hashed = hash_password(user_data.password)

    # Create new user
    new_user = User(
        email=user_data.email,
        password_hash=password_hashed,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        company_name=user_data.company_name,
        phone=user_data.phone,
        status="active",
        account_type="customer",
        email_verified=False,  # TODO: Implement email verification
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate tokens for immediate login
    access_token = create_access_token(new_user.id)  # type: ignore[arg-type]
    refresh_token = create_refresh_token(new_user.id)  # type: ignore[arg-type]

    # Store refresh token in database
    token_hash = hash_refresh_token(refresh_token)
    refresh_token_record = RefreshToken(
        user_id=new_user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        created_at=datetime.now(timezone.utc),  # Explicitly set created_at
    )
    db.add(refresh_token_record)
    db.commit()

    # Return user profile with tokens
    user_dict = UserResponse.model_validate(new_user).model_dump()
    return {
        **user_dict,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


# ============================================================================
# ENDPOINT: User Login
# ============================================================================

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")  # type: ignore
async def login_user(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db)
):
    """
    Login with email and password

    Authenticates user credentials and returns access and refresh tokens.
    Uses OAuth2 password flow (username field contains email).

    Args:
        form_data: OAuth2 form with username (email) and password
        db: Database session

    Returns:
        Access and refresh tokens

    Raises:
        HTTPException 401 if credentials are incorrect
    """
    try:
        # Get user by email (username field in OAuth2 form)
        user = db.query(User).filter(User.email == form_data.username).first()

        # Verify user exists and password is correct
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify password
        try:
            password_valid = verify_password(form_data.password, user.password_hash)  # type: ignore[arg-type]
        except Exception as e:
            # Password hash is malformed - log details, don't expose to client
            logger.error(f"Password verification error for user {user.id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication error. Please contact support."
            )
        
        if not password_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive"
            )

        # Update last login timestamp
        user.last_login_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        db.commit()
        db.refresh(user)

        # Generate tokens
        access_token = create_access_token(user.id)  # type: ignore[arg-type]
        refresh_token = create_refresh_token(user.id)  # type: ignore[arg-type]

        # Store refresh token in database
        token_hash = hash_refresh_token(refresh_token)
        expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        # Check if token hash already exists (shouldn't happen, but handle it)
        existing_token = db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash
        ).first()
        
        if existing_token:
            # Revoke old token
            existing_token.revoked = True  # type: ignore[assignment]
            existing_token.revoked_at = datetime.now(timezone.utc)  # type: ignore[assignment]
            db.commit()
            # Generate new token to avoid collision
            refresh_token = create_refresh_token(user.id)  # type: ignore[arg-type]
            token_hash = hash_refresh_token(refresh_token)
            expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc),  # Explicitly set created_at
        )
        db.add(refresh_token_record)
        db.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    except HTTPException:
        raise
    except Exception as e:
        # Log the actual error for debugging
        logger.error(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed due to an internal error"
        )


# ============================================================================
# ENDPOINT: Refresh Token
# ============================================================================

@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    refresh_data: RefreshTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Refresh access token using refresh token

    Validates the refresh token and issues a new access token and refresh token.
    The old refresh token is revoked after successful refresh.

    Args:
        refresh_data: Refresh token request with token string
        db: Database session

    Returns:
        New access and refresh tokens

    Raises:
        HTTPException 401 if refresh token is invalid or expired
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Decode refresh token and extract user ID
    user_id = get_user_from_token(refresh_data.refresh_token, expected_type="refresh")
    if user_id is None:
        raise credentials_exception

    # Verify refresh token exists in database and is not revoked
    token_hash = hash_refresh_token(refresh_data.refresh_token)
    stored_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False)
    ).first()

    if not stored_token or not stored_token.is_valid:
        raise credentials_exception

    # Get user
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise credentials_exception

    # Revoke old refresh token
    stored_token.revoked = True  # type: ignore[assignment]
    stored_token.revoked_at = datetime.now(timezone.utc)  # type: ignore[assignment]

    # Generate new tokens
    new_access_token = create_access_token(user.id)  # type: ignore[arg-type]
    new_refresh_token = create_refresh_token(user.id)  # type: ignore[arg-type]

    # Store new refresh token
    new_token_hash = hash_refresh_token(new_refresh_token)
    new_refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=new_token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        created_at=datetime.now(timezone.utc),  # Explicitly set created_at
    )
    db.add(new_refresh_token_record)
    db.commit()

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer"
    }


# ============================================================================
# ENDPOINT: Get Current User
# ============================================================================

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: Annotated[User, Depends(get_current_user)]
):
    """
    Get current user profile

    Returns the profile of the currently authenticated user.
    Requires valid access token in Authorization header.

    Args:
        current_user: Current authenticated user (from dependency)

    Returns:
        User profile data
    """
    return current_user


# ============================================================================
# PASSWORD RESET ENDPOINTS (Admin-Approved)
# ============================================================================

@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
@limiter.limit("3/minute")  # type: ignore
async def request_password_reset(
    request: Request,
    request_data: PasswordResetRequestCreate,
    db: Session = Depends(get_db)
):
    """
    Request a password reset.

    This creates a pending reset request and sends an approval email to the admin.
    The user must wait for admin approval before they can reset their password.

    Flow:
    1. User submits email
    2. Admin receives approval email
    3. Admin clicks approve link
    4. User receives reset link via email
    """
    # Find user by email
    user = db.query(User).filter(User.email == request_data.email).first()

    # Always return success message to prevent email enumeration
    success_message = "If an account exists with this email, a password reset request has been submitted for review."

    if not user:
        # Don't reveal that user doesn't exist
        return PasswordResetRequestResponse(message=success_message)

    # Check for existing pending request (avoid spam)
    existing_request = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.user_id == user.id,
        PasswordResetRequest.status == 'pending',
        PasswordResetRequest.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)
    ).first()

    if existing_request:
        return PasswordResetRequestResponse(
            message="A password reset request is already pending approval."
        )

    # Generate tokens
    reset_token = secrets.token_urlsafe(32)
    approval_token = secrets.token_urlsafe(32)

    # Create reset request (expires in 24 hours)
    reset_request = PasswordResetRequest(
        user_id=user.id,
        token=reset_token,
        approval_token=approval_token,
        status='pending',
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
    )
    db.add(reset_request)
    db.commit()
    db.refresh(reset_request)

    # Check if email is configured
    email_configured = bool(settings.SMTP_USER and settings.SMTP_PASSWORD)
    
    if email_configured:
        # Send approval email to admin (normal flow)
        email_sent = email_service.send_password_reset_approval_request(
            admin_email=settings.ADMIN_APPROVAL_EMAIL,
            user_email=user.email,  # type: ignore[arg-type]
            user_name=user.full_name,
            approval_token=approval_token,
            frontend_url=settings.FRONTEND_URL
        )
        
        if not email_sent:
            # Email failed to send, but request was created
            logger.warning(f"Password reset request created but email failed to send for user {user.email}")
        
        logger.info(
            "Password reset requested (requires admin approval)",
            extra={
                "user_id": user.id,
                "email": user.email,
                "request_id": reset_request.id
            }
        )
        
        return PasswordResetRequestResponse(
            message=success_message,
            request_id=reset_request.id  # type: ignore[arg-type]
        )
    else:
        # Email not configured - auto-approve and return reset link directly
        reset_request.status = 'approved'  # type: ignore[assignment]
        reset_request.approved_at = datetime.now(timezone.utc)  # type: ignore[assignment]
        reset_request.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)  # type: ignore[assignment] # 24 hours to use
        db.commit()
        
        # Use relative URL - frontend will construct full URL
        reset_url = f"/reset-password/{reset_token}"
        
        logger.info(
            "Password reset auto-approved (email not configured)",
            extra={
                "user_id": user.id,
                "email": user.email,
                "request_id": reset_request.id,
                "reset_token": reset_token
            }
        )
        
        return PasswordResetRequestResponse(
            message="Password reset link generated. Use the link below to reset your password.",
            request_id=reset_request.id,  # type: ignore[arg-type]
            reset_token=reset_token,
            reset_url=reset_url
        )


@router.get("/password-reset/approve/{approval_token}", response_model=PasswordResetApprovalResponse)
async def approve_password_reset(
    approval_token: str,
    db: Session = Depends(get_db)
):
    """
    Approve a password reset request (admin action via email link).

    After approval, the user will receive an email with the reset link.
    """
    # Find the reset request
    reset_request = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.approval_token == approval_token
    ).first()

    if not reset_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Password reset request not found"
        )

    if reset_request.status != 'pending':  # type: ignore[comparison-overlap]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request has already been {reset_request.status}"
        )

    if reset_request.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        reset_request.status = 'expired'  # type: ignore[assignment]
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset request has expired"
        )

    # Get the user
    user = db.query(User).filter(User.id == reset_request.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Approve the request
    reset_request.status = 'approved'  # type: ignore[assignment]
    reset_request.approved_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    # Extend expiry for 1 hour after approval for user to complete reset
    reset_request.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)  # type: ignore[assignment]
    db.commit()

    # Send reset link to user
    email_service.send_password_reset_approved(
        user_email=user.email,  # type: ignore[arg-type]
        user_name=user.full_name,
        reset_token=reset_request.token,  # type: ignore[arg-type]
        frontend_url=settings.FRONTEND_URL
    )

    logger.info(
        "Password reset approved",
        extra={
            "user_id": user.id,
            "email": user.email,
            "request_id": reset_request.id
        }
    )

    return PasswordResetApprovalResponse(
        message="Password reset approved. User has been notified via email.",
        user_email=user.email,  # type: ignore[arg-type]
        status="approved"
    )


@router.get("/password-reset/deny/{approval_token}", response_model=PasswordResetApprovalResponse)
async def deny_password_reset(
    approval_token: str,
    reason: str | None = None,
    db: Session = Depends(get_db)
):
    """
    Deny a password reset request (admin action via email link).

    The user will be notified that their request was denied.
    """
    # Find the reset request
    reset_request = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.approval_token == approval_token
    ).first()

    if not reset_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Password reset request not found"
        )

    if reset_request.status != 'pending':  # type: ignore[comparison-overlap]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request has already been {reset_request.status}"
        )

    # Get the user
    user = db.query(User).filter(User.id == reset_request.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Deny the request
    reset_request.status = 'denied'  # type: ignore[assignment]
    reset_request.admin_notes = reason  # type: ignore[assignment]
    db.commit()

    # Notify user
    email_service.send_password_reset_denied(
        user_email=user.email,  # type: ignore[arg-type]
        user_name=user.full_name,
        reason=reason
    )

    logger.info(
        "Password reset denied",
        extra={
            "user_id": user.id,
            "email": user.email,
            "request_id": reset_request.id,
            "reason": reason
        }
    )

    return PasswordResetApprovalResponse(
        message="Password reset denied. User has been notified.",
        user_email=user.email,  # type: ignore[arg-type]
        status="denied"
    )


@router.get("/password-reset/status/{token}", response_model=PasswordResetStatus)
async def check_reset_status(
    token: str,
    db: Session = Depends(get_db)
):
    """
    Check the status of a password reset token.

    Used by the frontend to determine if the user can proceed with password reset.
    """
    reset_request = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.token == token
    ).first()

    if not reset_request:  # type: ignore[truthy-function]
        return PasswordResetStatus(
            status="invalid",
            message="Invalid or expired reset token",
            can_reset=False
        )

    if reset_request.status == 'pending':  # type: ignore[comparison-overlap]
        return PasswordResetStatus(
            status="pending",
            message="Your request is awaiting admin approval",
            can_reset=False
        )

    if reset_request.status == 'denied':  # type: ignore[comparison-overlap]
        return PasswordResetStatus(
            status="denied",
            message="Your password reset request was denied",
            can_reset=False
        )

    if reset_request.status == 'completed':  # type: ignore[comparison-overlap]
        return PasswordResetStatus(
            status="completed",
            message="This reset link has already been used",
            can_reset=False
        )

    if reset_request.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        return PasswordResetStatus(
            status="expired",
            message="This reset link has expired",
            can_reset=False
        )

    if reset_request.status == 'approved':  # type: ignore[comparison-overlap]
        return PasswordResetStatus(
            status="approved",
            message="You can now reset your password",
            can_reset=True
        )

    return PasswordResetStatus(
        status="unknown",
        message="Unknown status",
        can_reset=False
    )


@router.post("/password-reset/complete", response_model=PasswordResetRequestResponse)
async def complete_password_reset(
    reset_data: PasswordResetComplete,
    db: Session = Depends(get_db)
):
    """
    Complete the password reset by setting a new password.

    Requires an approved reset token.
    """
    # Find the reset request
    reset_request = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.token == reset_data.token
    ).first()

    if not reset_request:  # type: ignore[truthy-function]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reset token"
        )

    if reset_request.status != 'approved':  # type: ignore[comparison-overlap]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reset password. Request status: {reset_request.status}"
        )

    if reset_request.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        reset_request.status = 'expired'  # type: ignore[assignment]
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired. Please request a new password reset."
        )

    # Get the user
    user = db.query(User).filter(User.id == reset_request.user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update password
    user.password_hash = hash_password(reset_data.new_password)  # type: ignore[assignment]

    # Mark request as completed
    reset_request.status = 'completed'  # type: ignore[assignment]
    reset_request.completed_at = datetime.now(timezone.utc)  # type: ignore[assignment]

    # Revoke all existing refresh tokens for security
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked.is_(False)
    ).update({"revoked": True, "revoked_at": datetime.now(timezone.utc)})

    db.commit()

    # Send confirmation email
    email_service.send_password_reset_completed(
        user_email=user.email,  # type: ignore[arg-type]
        user_name=user.full_name
    )

    logger.info(
        "Password reset completed",
        extra={
            "user_id": user.id,
            "email": user.email,
            "request_id": reset_request.id
        }
    )

    return PasswordResetRequestResponse(
        message="Password has been reset successfully. You can now login with your new password."
    )
