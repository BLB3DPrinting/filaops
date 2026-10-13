"""
Authentication endpoints for FilaOps Core

Handles user registration, login, token refresh, and profile retrieval.

Auth delivery is controlled by ``settings.AUTH_MODE``:
- ``cookie`` (default): tokens are set as httpOnly cookies — never exposed to JS.
- ``header``: tokens are returned in the JSON body (legacy / programmatic use).
"""
from datetime import datetime, timezone, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.limiter import limiter

from app.db.session import get_db
from app.models.user import User, RefreshToken, PasswordResetRequest
from app.schemas.auth import (
    UserRegister,
    UserResponse,
    RefreshTokenRequest,
    PasswordResetRequestCreate,
    PasswordResetRequestResponse,
    PasswordResetApprovalRequest,
    PasswordResetApprovalResponse,
    PasswordResetComplete,
    PasswordResetStatus,
    PortalLoginRequest,
)
import secrets
from app.core.config import settings
from app.schemas.common import MessageResponse
from app.services.email_identity import resolve_email_identity
from app.services.email_service import email_service
from app.core.security import (
    hash_password,
    verify_password,
    needs_rehash,
    create_access_token,
    create_refresh_token,
    get_user_from_token,
    hash_refresh_token,
    set_auth_cookies,
    clear_auth_cookies,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from app.logging_config import get_logger
from app.api.v1.deps import get_current_user  # noqa: F401
# Re-exports for backwards compatibility (prefer importing from app.api.v1.deps directly)
from app.api.v1.deps import get_current_admin_user as get_current_admin_user  # noqa: F401, E402
from app.api.v1.deps import get_current_staff_user as get_current_staff_user  # noqa: F401, E402

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

_USE_COOKIES = settings.AUTH_MODE.lower() == "cookie"


# ============================================================================
# ENDPOINT: User Registration
# ============================================================================

def _require_self_registration_enabled() -> None:
    """Refuse customer self-registration unless the public Quoter is on.

    SEC-411: open sign-up hands a customer token to anyone who can reach the
    API. Only the public Quoter needs self-registration, and the Quoter
    already requires ENABLE_PUBLIC_QUOTER, so both register routes follow
    that flag. Staff accounts are created by an admin (POST /admin/users) or
    by first-run setup, never here.
    """
    if not bool(getattr(settings, "ENABLE_PUBLIC_QUOTER", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer self-registration is disabled",
        )


@router.post("/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")  # type: ignore
async def register_user(
    request: Request,
    response: Response,
    user_data: UserRegister,
    db: Session = Depends(get_db),
):
    """
    Register a new customer account

    Creates a customer account (never staff) with the provided email and
    password. Returns 403 unless ENABLE_PUBLIC_QUOTER is on.
    In cookie mode, tokens are set as httpOnly cookies.
    In header mode, tokens are returned in the response body.
    """
    _require_self_registration_enabled()

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
        email_verified=False,  # Email verification not yet implemented
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

    user_dict = UserResponse.model_validate(new_user).model_dump()

    if _USE_COOKIES:
        set_auth_cookies(response, access_token, refresh_token)
        return {**user_dict, "token_type": "cookie"}

    # Header mode — return tokens in body
    return {
        **user_dict,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# ============================================================================
# ENDPOINT: User Login
# ============================================================================

@router.post("/login")
@limiter.limit("5/minute")  # type: ignore
async def login_user(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    """
    Login with email and password.

    In cookie mode, tokens are set as httpOnly cookies and user info is returned.
    In header mode, tokens are returned in the response body (legacy).
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

        # Transparent rehash: upgrade legacy bcrypt hashes to SHA-256 pre-hash
        if needs_rehash(form_data.password, user.password_hash):  # type: ignore[arg-type]
            user.password_hash = hash_password(form_data.password)  # type: ignore[assignment]

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

        # Purge expired/revoked tokens for this user to prevent table bloat
        db.query(RefreshToken).filter(
            RefreshToken.user_id == user.id,
            (RefreshToken.revoked.is_(True)) | (RefreshToken.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)),
        ).delete(synchronize_session=False)

        db.commit()

        if _USE_COOKIES:
            set_auth_cookies(response, access_token, refresh_token)
            user_dict = UserResponse.model_validate(user).model_dump()
            return {"message": "Login successful", "user": user_dict, "token_type": "cookie"}

        # Header mode — return tokens in body
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
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
# PORTAL CUSTOMER AUTH (Quoter SPA, B2B portal)
# ============================================================================
#
# Sibling endpoints to /auth/register + /auth/login above. NOT replacements:
#   /auth/login                     staff (and customer) login via OAuth2 form data
#   /auth/register                  JSON; creates a customer account, never staff
#   /auth/portal/register + /login  serve customer-facing SPAs via JSON
#
# Both register routes are off (403) unless ENABLE_PUBLIC_QUOTER is on; see
# _require_self_registration_enabled.
#
# Both write/read the same User table. account_type distinguishes them:
#   - register and portal/register always create account_type="customer"
#     (UserRegister body has no account_type field; can't be escalated)
#   - portal/login authenticates ONLY account_type="customer" users.
#     Admin users get the same 401-with-generic-message that wrong-password
#     attempts get — no enumeration of which accounts are admin vs customer.
#
# Tokens (JWT cookies or bearer) interoperate: a portal-customer token
# satisfies get_current_user on any route gated by user-only auth (e.g.
# PRO /quotes/*, which is license_gated, not admin_gated). It does NOT
# satisfy get_current_admin_user — that still requires account_type="admin".
#
# Built 2026-05-11 to close the Quoter SPA login gap: the SPA was
# calling /auth/portal/login + /auth/portal/register against URLs that
# didn't exist, returning 404 to the user. See chat history + the install
# runbook draft for the full context.


@router.post("/portal/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")  # type: ignore
async def register_portal_customer(
    request: Request,
    response: Response,
    user_data: UserRegister,
    db: Session = Depends(get_db),
):
    """Register a portal customer account from a public-facing SPA.

    The customer-flow entry point (e.g. quote.<customer>.com). It behaves
    exactly like ``/auth/register``:
      - Returns 403 unless ENABLE_PUBLIC_QUOTER is on (the Quoter needs the
        flag anyway).
      - The account_type is hardcoded to ``"customer"`` regardless of body
        content (UserRegister has no account_type field; admin escalation
        is impossible at this layer).
      - Cookie / bearer token behavior is the same: respects AUTH_MODE.
    """
    _require_self_registration_enabled()

    existing_user = db.query(User).filter(User.email == user_data.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    password_hashed = hash_password(user_data.password)
    new_user = User(
        email=user_data.email,
        password_hash=password_hashed,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        company_name=user_data.company_name,
        phone=user_data.phone,
        status="active",
        account_type="customer",  # explicit, not user-controlled
        email_verified=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token(new_user.id)  # type: ignore[arg-type]
    refresh_token = create_refresh_token(new_user.id)  # type: ignore[arg-type]

    token_hash = hash_refresh_token(refresh_token)
    refresh_token_record = RefreshToken(
        user_id=new_user.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        created_at=datetime.now(timezone.utc),
    )
    db.add(refresh_token_record)
    db.commit()

    user_dict = UserResponse.model_validate(new_user).model_dump()

    if _USE_COOKIES:
        set_auth_cookies(response, access_token, refresh_token)
        return {**user_dict, "token_type": "cookie"}

    return {
        **user_dict,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


@router.post("/portal/login")
@limiter.limit("5/minute")  # type: ignore
async def login_portal_customer(
    request: Request,
    response: Response,
    body: PortalLoginRequest,
    db: Session = Depends(get_db),
):
    """Portal customer login (JSON body, not OAuth2 form).

    Filters to account_type="customer" so admin users cannot authenticate
    via the public-facing customer flow. The 401 message is intentionally
    identical for "no such user", "wrong password", and "is an admin" —
    that prevents the endpoint from being used to enumerate admin
    accounts. Admins log in via ``/auth/login`` exclusively.
    """
    user = db.query(User).filter(User.email == body.email).first()

    # Generic 401 for: no user, admin user, wrong password — same response.
    # Prevents account-type / existence enumeration via the customer endpoint.
    if not user or user.account_type != "customer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        password_valid = verify_password(body.password, user.password_hash)  # type: ignore[arg-type]
    except Exception as e:
        logger.error(f"Password verification error for user {user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication error. Please contact support.",
        )

    if not password_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    # Transparent rehash (matches /auth/login)
    if needs_rehash(body.password, user.password_hash):  # type: ignore[arg-type]
        user.password_hash = hash_password(body.password)  # type: ignore[assignment]

    user.last_login_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    db.commit()
    db.refresh(user)

    access_token = create_access_token(user.id)  # type: ignore[arg-type]
    refresh_token = create_refresh_token(user.id)  # type: ignore[arg-type]

    token_hash = hash_refresh_token(refresh_token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    refresh_token_record = RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_at=datetime.now(timezone.utc),
    )
    db.add(refresh_token_record)

    # Purge expired/revoked tokens for this user (matches /auth/login pattern)
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        (RefreshToken.revoked.is_(True))
        | (RefreshToken.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)),
    ).delete(synchronize_session=False)

    db.commit()

    user_dict = UserResponse.model_validate(user).model_dump()

    if _USE_COOKIES:
        set_auth_cookies(response, access_token, refresh_token)
        return {**user_dict, "message": "Login successful", "token_type": "cookie"}

    return {
        **user_dict,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


# ============================================================================
# ENDPOINT: Refresh Token
# ============================================================================

@router.post("/refresh")
@limiter.limit("10/minute")  # type: ignore
async def refresh_access_token(
    request: Request,
    response: Response,
    refresh_data: RefreshTokenRequest | None = None,
    db: Session = Depends(get_db),
):
    """
    Refresh access token using refresh token.

    In cookie mode, reads the refresh token from the httpOnly cookie.
    In header mode, reads from the JSON body.
    The old refresh token is always revoked (token rotation).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Resolve the raw refresh token: cookie first, then body
    raw_refresh_token: str | None = request.cookies.get("refresh_token")
    if not raw_refresh_token and refresh_data:
        raw_refresh_token = refresh_data.refresh_token
    if not raw_refresh_token:
        raise credentials_exception

    # Decode refresh token and extract user ID
    user_id = get_user_from_token(raw_refresh_token, expected_type="refresh")
    if user_id is None:
        raise credentials_exception

    # Verify refresh token exists in database and is not revoked
    token_hash = hash_refresh_token(raw_refresh_token)
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

    # Purge expired/revoked tokens for this user to prevent table bloat
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        (RefreshToken.revoked.is_(True)) | (RefreshToken.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)),
    ).delete(synchronize_session=False)

    db.commit()

    if _USE_COOKIES:
        set_auth_cookies(response, new_access_token, new_refresh_token)
        return {"message": "Token refreshed", "token_type": "cookie"}

    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
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
# ENDPOINT: Logout
# ============================================================================

@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Logout the current user.

    Clears httpOnly cookies and revokes the refresh token server-side.
    """
    # Attempt to revoke refresh token if present in cookie
    raw_refresh = request.cookies.get("refresh_token")
    if raw_refresh:
        user_id = get_user_from_token(raw_refresh, expected_type="refresh")
        if user_id is not None:
            token_hash = hash_refresh_token(raw_refresh)
            stored = db.query(RefreshToken).filter(
                RefreshToken.token_hash == token_hash,
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
            ).first()
            if stored:
                stored.revoked = True  # type: ignore[assignment]
                stored.revoked_at = datetime.now(timezone.utc)  # type: ignore[assignment]
                db.commit()

    clear_auth_cookies(response)
    return {"message": "Logged out"}


# ============================================================================
# PASSWORD RESET ENDPOINTS (Admin-Approved)
# ============================================================================

# An administrator's approval gives the user this long to finish the reset.
RESET_APPROVAL_WINDOW = timedelta(hours=1)
# Slack for older approvals, which read the clock twice.
_RESET_APPROVAL_WINDOW_SLACK = timedelta(minutes=5)
# Stored in admin_notes when no approval email went out. Nobody can approve
# such a request, so it must not hold the one-open-request-per-user slot that
# keeps repeat requests from spamming the administrator.
# - APPROVAL_EMAIL_NOT_SENT_NOTE: the send was tried and failed.
# - EMAIL_OFF_NOTE: email was not configured, so no send was tried.
APPROVAL_EMAIL_NOT_SENT_NOTE = "Approval email not sent"
EMAIL_OFF_NOTE = "Approval email not sent: email not configured"
_UNSENT_NOTES = frozenset({APPROVAL_EMAIL_NOT_SENT_NOTE, EMAIL_OFF_NOTE})
# Returned to the admin when an approval stands but the reset link email to
# the user failed.
APPROVED_EMAIL_NOT_SENT_MESSAGE = (
    "Password reset approved, but the email with the reset link could not be "
    "sent, so the user has not been told. Check the email settings, then ask "
    "the user to request a new reset. For a staff account you can also reset "
    "the password from Team Members."
)
# After a failed send, the user's next request tries the email again, but not
# until the failed request is this old. Every try opens an SMTP connection, so
# without a pause a mail server that is down or misconfigured would be
# contacted on every request for a known address.
APPROVAL_EMAIL_RETRY_COOLDOWN = timedelta(minutes=15)


def _failed_send_in_cooldown(reset_request: PasswordResetRequest, now: datetime) -> bool:
    """True if the request's approval email failed less than the cooldown ago."""
    if reset_request.admin_notes != APPROVAL_EMAIL_NOT_SENT_NOTE:
        return False
    created_at = reset_request.created_at
    if created_at is None:
        return False
    return now - created_at < APPROVAL_EMAIL_RETRY_COOLDOWN


def _approved_by_admin(reset_request: PasswordResetRequest) -> bool:
    """True if an approved request has the short window an admin approval sets.

    Versions up to 4.1.0 approved requests on their own when SMTP was not
    configured, with a 24-hour window, and returned the token to the caller.
    Tokens approved that way must not complete a reset after an upgrade.
    """
    approved_at = reset_request.approved_at
    expires_at = reset_request.expires_at
    if approved_at is None or expires_at is None:
        return False
    return expires_at - approved_at <= RESET_APPROVAL_WINDOW + _RESET_APPROVAL_WINDOW_SLACK


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

    The reset token is only ever delivered by email, after an admin approves.
    It is never returned in this response. Without SMTP the request stays
    pending; an admin can set a new password for a staff account from
    Team Members instead.

    Every outcome returns the same response body, whether or not the account
    exists, a request is already pending, or SMTP is configured. Response
    time can still differ (the SMTP path sends mail before it responds), so
    this reduces account discovery but does not rule it out.

    The email is sent from a worker thread with a connect timeout, so a slow
    or unreachable mail server never blocks other requests.
    """
    generic_response = PasswordResetRequestResponse(
        message="If an account exists with this email, a password reset request has been submitted for review."
    )

    # Find user by email
    user = db.query(User).filter(User.email == request_data.email).first()

    if not user:
        return generic_response

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    open_requests = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.user_id == user.id,
        PasswordResetRequest.status == 'pending',
        PasswordResetRequest.expires_at > now
    ).all()

    # One emailed request per user at a time, so repeat requests can't spam
    # the admin. A request whose approval email never went out doesn't count:
    # otherwise a request made while SMTP was off would swallow the next one.
    if any(r.admin_notes not in _UNSENT_NOTES for r in open_requests):
        return generic_response

    # SMTP login set and ADMIN_APPROVAL_EMAIL a real address (not a placeholder).
    email_configured = settings.email_configured

    if not email_configured and open_requests:
        # Already recorded, and there is still no way to email an admin.
        return generic_response

    if any(_failed_send_in_cooldown(r, now) for r in open_requests):
        # A recent send failed. Wait out the cooldown before opening another
        # SMTP connection, and answer as if the request were still pending.
        return generic_response

    # Generate tokens
    reset_token = secrets.token_urlsafe(32)
    approval_token = secrets.token_urlsafe(32)

    # Create reset request (expires in 24 hours)
    reset_request = PasswordResetRequest(
        user_id=user.id,
        token=reset_token,
        approval_token=approval_token,
        status='pending',
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        admin_notes=None if email_configured else EMAIL_OFF_NOTE,
    )
    db.add(reset_request)
    db.commit()
    db.refresh(reset_request)

    if not email_configured:
        # Without email no approval email and no reset email can be sent.
        # The request stays pending (it expires on its own). An admin can set
        # a new password for a staff account from Admin > Team Members.
        logger.warning(
            "Password reset requested but email is not configured (SMTP_USER, "
            "SMTP_PASSWORD and a real ADMIN_APPROVAL_EMAIL are needed); the "
            "request stays pending. An administrator can set a new password for a "
            "staff account from Admin > Team Members > Reset PW. "
            "See: https://blb3dprinting.github.io/filaops/EMAIL_CONFIGURATION/",
            extra={
                "user_id": user.id,
                "email": user.email,
                "request_id": reset_request.id
            }
        )
        return generic_response

    # Send approval email to admin (normal flow). smtplib blocks, so it runs
    # in the threadpool instead of on the event loop.
    email_sent = await run_in_threadpool(
        email_service.send_password_reset_approval_request,
        identity=resolve_email_identity(db),
        admin_email=settings.ADMIN_APPROVAL_EMAIL,
        user_email=user.email,  # type: ignore[arg-type]
        user_name=user.full_name,
        approval_token=approval_token,
        frontend_url=settings.FRONTEND_URL
    )

    if not email_sent:
        # The request was created but no admin got it. Mark it so the user's
        # next request after the cooldown tries the email again instead of
        # being swallowed.
        reset_request.admin_notes = APPROVAL_EMAIL_NOT_SENT_NOTE
        db.commit()
        logger.warning(f"Password reset request created but email failed to send for user {user.email}")

    logger.info(
        "Password reset requested (requires admin approval)",
        extra={
            "user_id": user.id,
            "email": user.email,
            "request_id": reset_request.id
        }
    )

    return generic_response


@router.post("/password-reset/approve", response_model=PasswordResetApprovalResponse)
@limiter.limit("10/minute")  # type: ignore
async def approve_password_reset(
    request: Request,
    body: PasswordResetApprovalRequest,
    db: Session = Depends(get_db),
):
    """
    Approve a password reset request (admin action).

    Moved from GET to POST to prevent CSRF and browser-prefetch side effects.
    After approval, the user will receive an email with the reset link.
    """
    # Find the reset request
    reset_request = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.approval_token == body.approval_token
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
    approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    reset_request.status = 'approved'  # type: ignore[assignment]
    reset_request.approved_at = approved_at  # type: ignore[assignment]
    # The user gets a short window after approval to complete the reset
    reset_request.expires_at = approved_at + RESET_APPROVAL_WINDOW  # type: ignore[assignment]
    db.commit()

    # Send reset link to user
    sent = await run_in_threadpool(
        email_service.send_password_reset_approved,
        identity=resolve_email_identity(db),
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

    if not sent:
        # The approval stands, but the user never got the link. Say so, so the
        # admin can ask them to request again (or reset a staff password from
        # Team Members) instead of assuming they were told.
        logger.warning(
            "Password reset approved but the email to the user was not sent",
            extra={"user_id": user.id, "request_id": reset_request.id},
        )
        return PasswordResetApprovalResponse(
            message=APPROVED_EMAIL_NOT_SENT_MESSAGE,
            user_email=user.email,  # type: ignore[arg-type]
            status="approved",
        )

    return PasswordResetApprovalResponse(
        message="Password reset approved. User has been notified via email.",
        user_email=user.email,  # type: ignore[arg-type]
        status="approved"
    )


@router.post("/password-reset/deny", response_model=PasswordResetApprovalResponse)
@limiter.limit("10/minute")  # type: ignore
async def deny_password_reset(
    request: Request,
    body: PasswordResetApprovalRequest,
    db: Session = Depends(get_db),
):
    """
    Deny a password reset request (admin action).

    Moved from GET to POST to prevent CSRF and browser-prefetch side effects.
    The user will be notified that their request was denied.
    """
    # Find the reset request
    reset_request = db.query(PasswordResetRequest).filter(
        PasswordResetRequest.approval_token == body.approval_token
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
    reset_request.admin_notes = body.reason  # type: ignore[assignment]
    db.commit()

    # Notify user
    await run_in_threadpool(
        email_service.send_password_reset_denied,
        identity=resolve_email_identity(db),
        user_email=user.email,  # type: ignore[arg-type]
        user_name=user.full_name,
        reason=body.reason
    )

    logger.info(
        "Password reset denied",
        extra={
            "user_id": user.id,
            "email": user.email,
            "request_id": reset_request.id,
            "reason": body.reason
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
        if not _approved_by_admin(reset_request):
            return PasswordResetStatus(
                status="expired",
                message="This reset link has expired",
                can_reset=False
            )
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

    # Tokens that older versions approved without an administrator are
    # treated as expired, the same as tokens past their window.
    if (
        reset_request.expires_at < datetime.now(timezone.utc).replace(tzinfo=None)
        or not _approved_by_admin(reset_request)
    ):
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
    await run_in_threadpool(
        email_service.send_password_reset_completed,
        identity=resolve_email_identity(db),
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
