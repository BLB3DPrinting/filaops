"""
Admin User Management Endpoints

Handles CRUD operations for admin and operator users.
Customers are managed separately via /admin/customers.

Account Types:
- admin: Full access to all features
- operator: Production floor access (can manage orders, production, inventory)
- customer: Portal access only (managed via /admin/customers)
"""
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.models.user import User, RefreshToken
from app.api.v1.deps import get_current_admin_user
from app.core.security import hash_password
from app.core.features import enforce_resource_limit, get_current_tier
from app.core.seat_limits import enforce_seat_cap, STAFF_ACCOUNT_TYPES
from app.logging_config import get_logger
from app.schemas.user_admin import (
    AdminUserCreate,
    AdminUserUpdate,
    AdminUserResetPassword,
    AdminUserResponse,
    AdminUserListResponse,
)

router = APIRouter(prefix="/users", tags=["Admin - User Management"])

logger = get_logger(__name__)


def build_full_name(user: User) -> Optional[str]:
    """Build full name from first/last name"""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    elif user.first_name:
        return user.first_name
    elif user.last_name:
        return user.last_name
    return None


# ============================================================================
# LIST USERS
# ============================================================================

@router.get("/", response_model=List[AdminUserListResponse])
async def list_admin_users(
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    account_type: Optional[str] = Query(None, pattern="^(admin|operator)$"),
    include_inactive: bool = False,
):
    """
    List all admin and operator users.
    
    Does NOT include customers (use /admin/customers for that).
    Admin only.
    """
    query = db.query(User).filter(
        User.account_type.in_(STAFF_ACCOUNT_TYPES)
    )
    
    # Filter by account type
    if account_type:
        query = query.filter(User.account_type == account_type)
    
    # Filter by status
    if not include_inactive:
        query = query.filter(User.status == "active")
    
    # Order by most recent first
    query = query.order_by(desc(User.created_at))
    
    users = query.offset(skip).limit(limit).all()
    
    result = []
    for user in users:
        result.append({
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "full_name": build_full_name(user),
            "account_type": user.account_type,
            "status": user.status,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
        })
    
    return result


# ============================================================================
# GET USER STATS (for dashboard) - Must be before /{user_id} to avoid route conflict
# ============================================================================

@router.get("/stats/summary")
async def get_user_stats(
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Get summary stats for admin/operator users.

    Useful for dashboard widgets.
    """
    total_admins = db.query(User).filter(
        User.account_type == "admin",
        User.status == "active"
    ).count()

    total_operators = db.query(User).filter(
        User.account_type == "operator",
        User.status == "active"
    ).count()

    total_inactive = db.query(User).filter(
        User.account_type.in_(STAFF_ACCOUNT_TYPES),
        User.status != "active"
    ).count()

    return {
        "active_admins": total_admins,
        "active_operators": total_operators,
        "inactive_users": total_inactive,
        "total_active": total_admins + total_operators,
    }


# ============================================================================
# GET SINGLE USER
# ============================================================================

@router.get("/{user_id}", response_model=AdminUserResponse)
async def get_admin_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Get a single admin or operator user.
    
    Admin only.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.account_type.in_(STAFF_ACCOUNT_TYPES)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": build_full_name(user),
        "account_type": user.account_type,
        "status": user.status,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


# ============================================================================
# CREATE USER
# ============================================================================

@router.post("/", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    request: AdminUserCreate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Create a new admin or operator user.

    Admin only. The password provided is temporary - user should change it on first login.

    Note: Subject to tier limits. Community tier allows 1 user (the initial admin).
    """
    # Legacy tier-limit hook (dormant unless features.LICENSING_ENABLED is on;
    # owned by a separate change). Kept for continuity — real enforcement is
    # enforce_seat_cap() just before db.add() below.
    current_user_count = db.query(User).filter(
        User.account_type.in_(STAFF_ACCOUNT_TYPES),
        User.status == "active"
    ).count()

    user_tier = get_current_tier(db, current_admin)
    enforce_resource_limit(db, "users", current_user_count, user_tier.value)

    # Check for existing email
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Hash password
    password_hashed = hash_password(request.password)

    now = datetime.now(timezone.utc)

    # Multi-user seat cap: community allows 1 active staff seat, PRO/enterprise
    # unlimited. Reads the live tier from plugin_registry. Blocks only the NEW
    # seat over the cap — never affects existing users (grandfathered).
    # Placed LAST before db.add() (CodeRabbit #862): on capped tiers this takes
    # a transaction-scoped advisory lock held until commit, so it must not sit
    # above the email lookup / bcrypt hashing — that would serialize concurrent
    # creates through the slowest part of the handler. It must still run BEFORE
    # db.add(): the session would autoflush the pending user into the seat
    # count and off-by-one every create.
    enforce_seat_cap(db)

    user = User(
        email=request.email,
        password_hash=password_hashed,
        first_name=request.first_name,
        last_name=request.last_name,
        account_type=request.account_type,
        status="active",
        email_verified=True,  # Admin-created users don't need email verification
        created_by=current_admin.id,
        created_at=now,
        updated_at=now,
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    logger.info(
        "Admin/operator user created",
        extra={
            "new_user_id": user.id,
            "new_user_email": user.email,
            "account_type": user.account_type,
            "created_by_id": current_admin.id,
            "created_by_email": current_admin.email,
        }
    )
    
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": build_full_name(user),
        "account_type": user.account_type,
        "status": user.status,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


# ============================================================================
# UPDATE USER
# ============================================================================

@router.patch("/{user_id}", response_model=AdminUserResponse)
async def update_admin_user(
    user_id: int,
    request: AdminUserUpdate,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Update an admin or operator user.
    
    Admin only. Cannot demote yourself or the last admin.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.account_type.in_(STAFF_ACCOUNT_TYPES)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent self-demotion
    if user.id == current_admin.id and request.account_type == "operator":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot demote yourself. Have another admin change your role."
        )
    
    # Prevent deactivating yourself
    if user.id == current_admin.id and request.status in ["inactive", "suspended"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    # Prevent removing last admin
    if user.account_type == "admin" and request.account_type == "operator":
        admin_count = db.query(User).filter(
            User.account_type == "admin",
            User.status == "active",
            User.id != user_id
        ).count()
        if admin_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot demote the last active admin"
            )
    
    # Check for duplicate email
    if request.email and request.email != user.email:
        existing = db.query(User).filter(User.email == request.email).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )

    # Multi-user seat cap: block activating a currently-inactive staff user via
    # PATCH status='active' if it would exceed the tier's active-staff cap.
    # Only fires on an inactive->active transition, so editing an already-active
    # user is unaffected (grandfathered). Exclude this user from the count.
    if request.status == "active" and user.status != "active":
        enforce_seat_cap(db, exclude_user_id=user.id)

    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(user, field, value)
    
    user.updated_by = current_admin.id
    user.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    db.refresh(user)
    
    logger.info(
        "Admin/operator user updated",
        extra={
            "user_id": user.id,
            "user_email": user.email,
            "updated_by_id": current_admin.id,
            "updated_by_email": current_admin.email,
            "changes": list(update_data.keys()),
        }
    )
    
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": build_full_name(user),
        "account_type": user.account_type,
        "status": user.status,
        "last_login_at": user.last_login_at,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


# ============================================================================
# RESET PASSWORD
# ============================================================================

@router.post("/{user_id}/reset-password", status_code=status.HTTP_200_OK)
async def reset_user_password(
    user_id: int,
    request: AdminUserResetPassword,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Reset password for an admin or operator user.
    
    Admin only. Also revokes all existing refresh tokens for the user.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.account_type.in_(STAFF_ACCOUNT_TYPES)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.password_hash = hash_password(request.new_password)
    user.updated_by = current_admin.id
    user.updated_at = datetime.now(timezone.utc)
    
    # Revoke all refresh tokens for security
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False)
    ).update({
        "revoked": True,
        "revoked_at": datetime.now(timezone.utc)
    })
    
    db.commit()
    
    logger.info(
        "Admin/operator password reset",
        extra={
            "user_id": user.id,
            "user_email": user.email,
            "reset_by_id": current_admin.id,
            "reset_by_email": current_admin.email,
        }
    )
    
    return {"message": "Password reset successfully"}


# ============================================================================
# DELETE (DEACTIVATE) USER
# ============================================================================

@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def deactivate_admin_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Deactivate an admin or operator user.
    
    Admin only. Sets status to 'inactive' (soft delete).
    Cannot deactivate yourself or the last admin.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.account_type.in_(STAFF_ACCOUNT_TYPES)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Prevent self-deactivation
    if user.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    # Prevent removing last admin
    if user.account_type == "admin":
        admin_count = db.query(User).filter(
            User.account_type == "admin",
            User.status == "active",
            User.id != user_id
        ).count()
        if admin_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active admin"
            )
    
    # Soft delete
    user.status = "inactive"
    user.updated_by = current_admin.id
    user.updated_at = datetime.now(timezone.utc)
    
    # Revoke all refresh tokens
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False)
    ).update({
        "revoked": True,
        "revoked_at": datetime.now(timezone.utc)
    })
    
    db.commit()
    
    logger.info(
        "Admin/operator user deactivated",
        extra={
            "user_id": user.id,
            "user_email": user.email,
            "deactivated_by_id": current_admin.id,
            "deactivated_by_email": current_admin.email,
        }
    )
    
    return {"message": f"User {user.email} has been deactivated"}


# ============================================================================
# REACTIVATE USER
# ============================================================================

@router.post("/{user_id}/reactivate", status_code=status.HTTP_200_OK)
async def reactivate_admin_user(
    user_id: int,
    current_admin: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db),
):
    """
    Reactivate a previously deactivated admin or operator user.
    
    Admin only.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.account_type.in_(STAFF_ACCOUNT_TYPES)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already active"
        )

    # Multi-user seat cap: reactivating adds one active staff seat. Block if it
    # would exceed the tier cap (community=1, PRO/enterprise unlimited). Exclude
    # this user from the count. Grandfathered — never touches other users.
    enforce_seat_cap(db, exclude_user_id=user.id)

    user.status = "active"
    user.updated_by = current_admin.id
    user.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    
    logger.info(
        "Admin/operator user reactivated",
        extra={
            "user_id": user.id,
            "user_email": user.email,
            "reactivated_by_id": current_admin.id,
            "reactivated_by_email": current_admin.email,
        }
    )
    
    return {"message": f"User {user.email} has been reactivated"}
