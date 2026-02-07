"""
Security utilities for authentication

Provides password hashing, JWT token generation, and validation
"""
import hashlib
import uuid
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import jwt
import bcrypt


# JWT Configuration
from app.core.config import settings

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # 30 minutes
REFRESH_TOKEN_EXPIRE_DAYS = 7  # 7 days


# ============================================================================
# PASSWORD VALIDATION
# ============================================================================

def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets security requirements.
    
    Requirements:
    - At least 8 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one number
    - At least one special character
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\\/`~]', password):
        return False, "Password must contain at least one special character (!@#$%^&*etc)"
    
    return True, ""


# ============================================================================
# PASSWORD HASHING (using bcrypt directly)
# ============================================================================

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt

    Args:
        password: Plain text password

    Returns:
        Hashed password (bcrypt format, 60 chars)
    """
    # bcrypt requires bytes
    password_bytes = password.encode('utf-8')
    # Generate salt and hash
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash

    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hash to verify against

    Returns:
        True if password matches, False otherwise
    """
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


# ============================================================================
# JWT TOKEN GENERATION
# ============================================================================

def create_access_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token for user authentication

    Args:
        user_id: User ID to encode in token
        expires_delta: Optional custom expiration time

    Returns:
        JWT access token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(user_id),  # Subject (standard JWT claim)
        "type": "access",  # Token type
        "exp": expire,  # Expiration time
        "iat": now,  # Issued at
        "jti": str(uuid.uuid4()),  # JWT ID (unique identifier)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


def create_refresh_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT refresh token for token rotation

    Args:
        user_id: User ID to encode in token
        expires_delta: Optional custom expiration time

    Returns:
        JWT refresh token string
    """
    if expires_delta is None:
        expires_delta = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": str(user_id),  # Subject (standard JWT claim)
        "type": "refresh",  # Token type
        "exp": expire,  # Expiration time
        "iat": now,  # Issued at
        "jti": str(uuid.uuid4()),  # JWT ID (unique identifier)
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


# ============================================================================
# JWT TOKEN VALIDATION
# ============================================================================

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate JWT token

    Args:
        token: JWT token string to decode

    Returns:
        Token payload dict if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        # Token has expired
        return None
    except Exception:
        # Token is invalid (tampered, malformed, etc.)
        # PyJWT raises various exceptions: DecodeError, InvalidTokenError, etc.
        return None


def get_user_from_token(
    token: str,
    expected_type: Optional[str] = None
) -> Optional[int]:
    """
    Extract user ID from JWT token with optional type validation

    Args:
        token: JWT token string
        expected_type: Expected token type ("access" or "refresh"), None to skip check

    Returns:
        User ID if token is valid and matches expected type, None otherwise
    """
    payload = decode_token(token)

    if payload is None:
        return None

    # Validate token type if specified
    if expected_type is not None:
        token_type = payload.get("type")
        if token_type != expected_type:
            return None

    # Extract user ID from 'sub' (subject) claim
    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None

    try:
        user_id = int(user_id_str)
        return user_id
    except (ValueError, TypeError):
        return None


# ============================================================================
# REFRESH TOKEN HELPERS
# ============================================================================

def hash_refresh_token(token: str) -> str:
    """
    Hash refresh token for secure storage in database

    Args:
        token: Refresh token string to hash

    Returns:
        SHA256 hash of token (hex string, 64 characters)
    """
    return hashlib.sha256(token.encode()).hexdigest()


# ============================================================================
# AUTH COOKIE HELPERS
# ============================================================================

def set_auth_cookies(
    response,
    access_token: str,
    refresh_token: Optional[str] = None,
) -> None:
    """
    Set httpOnly auth cookies on a FastAPI Response.

    Args:
        response: FastAPI/Starlette Response object
        access_token: JWT access token
        refresh_token: JWT refresh token (optional, e.g. setup only returns access)
    """
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/api",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    if refresh_token:
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite="lax",
            path="/api/v1/auth",
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )


def clear_auth_cookies(response) -> None:
    """Clear auth cookies from a FastAPI Response."""
    response.delete_cookie("access_token", path="/api")
    response.delete_cookie("refresh_token", path="/api/v1/auth")
