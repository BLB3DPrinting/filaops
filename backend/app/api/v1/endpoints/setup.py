"""
First-run setup endpoint for FilaOps

Allows creating the initial admin account when no users exist.
This endpoint is disabled once any user has been created.
"""
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.core.security import hash_password, create_access_token, validate_password_strength, set_auth_cookies
from app.core.config import settings
from app.core.limiter import limiter
from app.api.v1.deps import get_current_admin_user
from app.services import seed_service
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupStatusResponse(BaseModel):
    """Response for setup status check"""
    needs_setup: bool
    message: str


class InitialAdminCreate(BaseModel):
    """Schema for creating the initial admin user"""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must meet strength requirements")
    full_name: str = Field(..., min_length=1, max_length=100)
    company_name: str = Field(default="", max_length=100)


class SetupCompleteResponse(BaseModel):
    """Response after successful setup"""
    message: str
    email: str
    access_token: str
    token_type: str = "bearer"


@router.get("/status", response_model=SetupStatusResponse)
def get_setup_status(db: Session = Depends(get_db)):
    """
    Check if first-run setup is needed.
    
    Returns needs_setup=True if no users exist in the database.
    Frontend should redirect to setup page if this returns True.
    """
    user_count = db.query(User).count()
    
    if user_count == 0:
        return SetupStatusResponse(
            needs_setup=True,
            message="Welcome to FilaOps! Create your admin account to get started."
        )
    
    return SetupStatusResponse(
        needs_setup=False,
        message="Setup complete. Please log in."
    )


@router.post("/initial-admin")
@limiter.limit("3/minute")  # type: ignore
def create_initial_admin(
    request: Request,
    admin_data: InitialAdminCreate,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Create the initial admin user during first-run setup.

    This endpoint ONLY works when no users exist in the database.
    Once any user is created, this endpoint returns 403 Forbidden.

    In cookie mode, the access token is set as an httpOnly cookie.
    In header mode, the token is returned in the response body.
    """
    # Check if any users already exist
    user_count = db.query(User).count()
    if user_count > 0:
        raise HTTPException(
            status_code=403,
            detail="Setup already complete. Admin creation is disabled."
        )

    # Check if email already exists (shouldn't happen, but be safe)
    existing = db.query(User).filter(User.email == admin_data.email).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Validate password strength
    is_valid, error_msg = validate_password_strength(admin_data.password)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=error_msg
        )

    # Create the admin user
    # Parse full_name into first/last
    name_parts = admin_data.full_name.strip().split(' ', 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    admin = User(
        email=admin_data.email,
        password_hash=hash_password(admin_data.password),
        first_name=first_name,
        last_name=last_name,
        company_name=admin_data.company_name or None,
        account_type="admin",
        status="active",
        email_verified=True
    )

    db.add(admin)
    db.commit()
    db.refresh(admin)

    # Generate access token so they're logged in immediately
    access_token = create_access_token(user_id=admin.id)

    if settings.AUTH_MODE.lower() == "cookie":
        set_auth_cookies(response, access_token)
        # The full-duration token lives in the httpOnly cookie (not JS-accessible).
        # The response body gets a short-lived token (5 min) for the onboarding
        # wizard, which needs Authorization headers because httpOnly cookies are
        # not reliably forwarded through nginx reverse proxies on immediate
        # same-page requests.  5 minutes is enough for the wizard to complete,
        # and this endpoint only works when zero users exist (line 85).
        setup_token = create_access_token(
            user_id=admin.id,
            expires_delta=timedelta(minutes=5),
        )
        return {
            "message": "Admin account created successfully! Welcome to FilaOps.",
            "email": admin.email,
            "setup_token": setup_token,
            "token_type": "cookie",
        }

    return SetupCompleteResponse(
        message="Admin account created successfully! Welcome to FilaOps.",
        email=admin.email,
        access_token=access_token,
    )


class SeedDataResponse(BaseModel):
    """Response after seeding example data"""
    message: str
    items_created: int
    items_skipped: int
    materials_created: int
    colors_created: int
    links_created: int
    material_products_created: int


@router.post("/seed-example-data", response_model=SeedDataResponse)
@limiter.limit("3/minute")  # type: ignore
def seed_example_data_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """
    Seed the database with example items and materials.

    Requires admin authentication. Only allowed on fresh installations
    (1 user or fewer) to prevent accidental data pollution.
    All seed operations run in a single atomic transaction.
    """
    user_count = db.query(User).count()
    if user_count > 1:
        raise HTTPException(
            status_code=400,
            detail="Seeding only allowed on fresh installations"
        )

    result = seed_service.seed_example_data(db)
    return SeedDataResponse(message="Example data seeded successfully!", **result)
