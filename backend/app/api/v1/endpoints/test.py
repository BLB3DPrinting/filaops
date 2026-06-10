"""
Test data seeding endpoints.

WARNING: These endpoints are for testing only!

They are OPT-IN: the router is only registered (see app/api/v1/__init__.py)
and requests only allowed when ENVIRONMENT is "test"/"ci"/"e2e" or
TESTING=true. They are never available when ENVIRONMENT=production.
Plain development deployments do NOT get them by default — /seed creates
users with a well-known password, so exposing it on a reachable instance
is an account-takeover vector.

Within an opted-in test environment the endpoints are intentionally
unauthenticated: the Playwright E2E bootstrap (frontend/tests/e2e/
auth.setup.ts) calls /seed before any user exists — seeding is what
CREATES the login user — so per-request auth here would deadlock E2E.
The gate is the registration opt-in, not per-request credentials.

The GitHub Actions E2E workflow already starts the backend with
TESTING=true; to run Playwright E2E locally, do the same.

Endpoints:
    GET  /api/v1/test/scenarios  - List available test scenarios
    POST /api/v1/test/seed       - Seed database with a scenario
    POST /api/v1/test/cleanup    - Remove all test data (also requires
                                   ALLOW_TEST_DATA_WIPE=true)
    GET  /api/v1/test/health     - Health check for test endpoints
"""
import os
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Dict, Any, List

from app.db.session import get_db


router = APIRouter(prefix="/test", tags=["testing"])


# =============================================================================
# GUARD: Opt-in only (never production, never plain development)
# =============================================================================

def test_endpoints_enabled() -> bool:
    """
    Whether test endpoints are enabled for this process.

    Enabled only when explicitly opted in:
    - ENVIRONMENT is "test", "ci", or "e2e", or
    - TESTING is truthy ("1"/"true"/"yes") and ENVIRONMENT is not production.

    Production always wins: TESTING cannot re-enable them there.
    """
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env == "production":
        return False
    if env in ("test", "ci", "e2e"):
        return True
    return os.getenv("TESTING", "").lower() in ("1", "true", "yes")


def require_test_mode():
    """
    Dependency that blocks requests unless test endpoints are enabled.

    Defense in depth behind the conditional router registration in
    app/api/v1/__init__.py. Raises HTTPException 403 when disabled.
    """
    if not test_endpoints_enabled():
        raise HTTPException(
            status_code=403,
            detail=(
                "Test endpoints are disabled. Set TESTING=true "
                "(non-production only) to enable them."
            )
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
