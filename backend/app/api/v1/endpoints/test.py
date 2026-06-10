"""
Test data seeding endpoints.

WARNING: These endpoints are for testing only!
They are disabled in production via ENVIRONMENT check, AND require staff
authentication so unauthenticated actors on a dev/staging server cannot
trigger seeding or wipe operations.

Endpoints:
    GET  /api/v1/test/scenarios  - List available test scenarios (staff only)
    POST /api/v1/test/seed       - Seed database with a scenario (staff only)
    POST /api/v1/test/cleanup    - Remove all test data (staff only)
    GET  /api/v1/test/health     - Health check (intentionally public — no
                                   sensitive data, helps CI detect misconfiguration)
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any, List

from app.db.session import get_db
from app.models.user import User
from app.api.v1.deps import get_current_staff_user


router = APIRouter(prefix="/test", tags=["testing"])


# =============================================================================
# GUARD: Only allow in non-production environments
# =============================================================================

def require_test_mode():
    """
    Dependency that blocks requests in production.

    Raises HTTPException 403 if ENVIRONMENT is 'production'.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env == "production":
        raise HTTPException(
            status_code=403,
            detail="Test endpoints are disabled in production"
        )
    return True


def require_data_wipe_allowed():
    """
    Dependency that requires explicit ALLOW_TEST_DATA_WIPE=true.

    This is a safety mechanism to prevent accidental data loss.
    Only set this in test/CI environments, NEVER in development with real data.

    Raises HTTPException 403 if flag is not set.
    """
    allow_wipe = os.getenv("ALLOW_TEST_DATA_WIPE", "false").lower()
    if allow_wipe != "true":
        raise HTTPException(
            status_code=403,
            detail=(
                "Data wipe not allowed. Set ALLOW_TEST_DATA_WIPE=true to enable. "
                "WARNING: This will delete ALL data from the database!"
            )
        )
    return True


# =============================================================================
# SCHEMAS
# =============================================================================

class SeedRequest(BaseModel):
    """Request body for seeding a test scenario."""
    scenario: str

    class Config:
        json_schema_extra = {
            "example": {"scenario": "full-demand-chain"}
        }


class SeedResponse(BaseModel):
    """Response from seeding a test scenario."""
    success: bool
    scenario: str
    data: Dict[str, Any]


class CleanupResponse(BaseModel):
    """Response from cleanup operation."""
    success: bool
    cleaned: bool
    tables: List[str]


class ScenariosResponse(BaseModel):
    """Response listing available scenarios."""
    scenarios: List[str]


class HealthResponse(BaseModel):
    """Response from health check."""
    status: str
    test_mode: bool
    environment: str


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/scenarios", response_model=ScenariosResponse)
async def list_scenarios(
    _: bool = Depends(require_test_mode),
    _staff: User = Depends(get_current_staff_user),
):
    """
    List available test scenarios.

    Returns a list of scenario names that can be used with the /seed endpoint.
    """
    from tests.scenarios import SCENARIOS
    return ScenariosResponse(scenarios=sorted(SCENARIOS.keys()))


@router.post("/seed", response_model=SeedResponse)
async def seed_test_data(
    request: SeedRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(require_test_mode),
    _staff: User = Depends(get_current_staff_user),
):
    """
    Seed the database with a test scenario.

    Creates interconnected test data for E2E testing.

    Available scenarios:
    - **empty**: Just a test user for login
    - **basic**: Sample users, products, vendors, and inventory
    - **low-stock-with-allocations**: For demand pegging tests
    - **production-in-progress**: Various production order statuses
    - **full-demand-chain**: Complete SO→WO→PO chain for traceability
    - **so-with-blocking-issues**: Sales order with fulfillment problems

    Returns the created object IDs for reference in tests.
    """
    from tests.scenarios import seed_scenario

    try:
        data = seed_scenario(db, request.scenario)
        return SeedResponse(
            success=True,
            scenario=request.scenario,
            data=data
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Seeding failed: {str(e)}")


@router.post("/cleanup", response_model=CleanupResponse)
async def cleanup_data(
    db: Session = Depends(get_db),
    _test_mode: bool = Depends(require_test_mode),
    _wipe_allowed: bool = Depends(require_data_wipe_allowed),
    _staff: User = Depends(get_current_staff_user),
):
    """
    Remove all test data from the database.

    WARNING: This truncates tables! Requires ALLOW_TEST_DATA_WIPE=true.

    Use this endpoint to clean up between E2E tests.
    Only enable the wipe flag in test/CI environments.
    """
    from tests.scenarios import cleanup_test_data

    try:
        result = cleanup_test_data(db)
        return CleanupResponse(success=True, **result)
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.get("/health", response_model=HealthResponse)
async def test_health():
    """
    Simple health check for test endpoints.

    Returns current environment info without requiring test mode guard
    (so you can verify the endpoint exists even in production).
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    return HealthResponse(
        status="ok",
        test_mode=env != "production",
        environment=env
    )
