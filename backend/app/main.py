"""
FilaOps ERP - Main FastAPI Application
"""
import os
from contextlib import asynccontextmanager

try:
    import sentry_sdk
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

from app.core.limiter import apply_rate_limiting
from app.api.v1 import router as api_v1_router
from app.core.config import settings
from app.exceptions import FilaOpsException
from app.logging_config import setup_logging, get_logger
from app.middleware import CorrelationIdMiddleware

# Setup structured logging
setup_logging()
logger = get_logger(__name__)

# Initialize Sentry (optional - only if installed and configured)
sentry_dsn = os.getenv("SENTRY_DSN")
if SENTRY_AVAILABLE and sentry_dsn:
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        environment=getattr(settings, "ENVIRONMENT", "development"),
        release=f"filaops@{settings.VERSION}",
    )
elif not SENTRY_AVAILABLE:
    logger.info("Sentry SDK not installed - error tracking disabled")
else:
    logger.info("SENTRY_DSN not set - error tracking disabled")


# ===================
# Security Headers Middleware
# ===================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # XSS protection (legacy)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Permissions policy
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # HSTS in production
        if getattr(settings, "ENVIRONMENT", "development") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def init_database():
    """Initialize database tables on startup (idempotent)."""
    try:
        from app.db.session import engine
        from app.db.base import Base
        import app.models  # noqa: F401
        logger.info("Checking database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables ready")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")


def seed_default_data():
    """Check if setup is needed (no users exist)."""
    try:
        from app.db.session import SessionLocal
        from app.models.user import User
        db = SessionLocal()
        try:
            user_count = db.query(User).count()
            if user_count == 0:
                logger.info("No users found - first-run setup required at /setup")
            else:
                logger.info(f"Found {user_count} existing users")
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Could not check user data: {e}")


def _mask_password(url: str) -> str:
    """Mask password in connection string for safe logging."""
    import re
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', url)


def log_startup_configuration():
    """Log configuration at startup for debugging."""
    # Database configuration
    db_url = getattr(settings, 'database_url', 'NOT SET')
    logger.info("=" * 60)
    logger.info("FILAOPS STARTUP CONFIGURATION")
    logger.info("=" * 60)

    # Database info
    logger.info(f"Database URL: {_mask_password(db_url)}")
    logger.info(f"DB Host: {getattr(settings, 'DB_HOST', 'NOT SET')}")
    logger.info(f"DB Port: {getattr(settings, 'DB_PORT', 'NOT SET')}")
    logger.info(f"DB Name: {getattr(settings, 'DB_NAME', 'NOT SET')}")

    # Check for SQL Server indicators (debugging Viper's issue)
    if 'mssql' in db_url.lower() or 'sqlserver' in db_url.lower():
        logger.warning("⚠️  SQL SERVER DETECTED - FilaOps v2.x requires PostgreSQL!")
        logger.warning("⚠️  Please update your database configuration.")
    elif 'postgresql' in db_url.lower() or 'postgres' in db_url.lower():
        logger.info("✓ PostgreSQL database configured correctly")
    else:
        logger.warning(f"⚠️  Unknown database type in URL: {db_url[:30]}...")

    # CORS configuration
    cors_origins = getattr(settings, 'ALLOWED_ORIGINS', [])
    logger.info(f"CORS Origins ({len(cors_origins)} configured):")
    for origin in cors_origins:
        logger.info(f"  - {origin}")

    frontend_url = getattr(settings, 'FRONTEND_URL', 'NOT SET')
    logger.info(f"Frontend URL: {frontend_url}")

    # Environment
    logger.info(f"Environment: {getattr(settings, 'ENVIRONMENT', 'development')}")
    logger.info(f"Debug Mode: {getattr(settings, 'DEBUG', False)}")
    logger.info(f"Tier: {getattr(settings, 'TIER', 'open')}")
    logger.info("=" * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info(
        "Starting FilaOps ERP API",
        extra={
            "version": settings.VERSION,
            "environment": getattr(settings, "ENVIRONMENT", "development"),
            "debug": getattr(settings, "DEBUG", False),
        }
    )
    log_startup_configuration()
    init_database()
    seed_default_data()
    yield
    logger.info("Shutting down FilaOps ERP API")


# Create FastAPI app
# Disable Swagger/OpenAPI in production to prevent API schema exposure
_is_production = getattr(settings, "ENVIRONMENT", "development") == "production"
app = FastAPI(
    title="FilaOps ERP API",
    description="Open-source ERP for 3D print farms",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs" if not _is_production else None,
    redoc_url="/redoc" if not _is_production else None,
    openapi_url="/openapi.json" if not _is_production else None,
)

# Optional rate limiting (no crash if slowapi isn't installed)
app.state.limiter, RATE_LIMITS_ENABLED = apply_rate_limiting(app)

# Correlation ID middleware (outermost — runs first, available to all other middleware)
app.add_middleware(CorrelationIdMiddleware)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware — uses settings.ALLOWED_ORIGINS directly (no wildcard fallback)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With", "X-API-Key"],
)


# ===================
# Exception Handlers
# ===================

@app.exception_handler(FilaOpsException)
async def filaops_exception_handler(request: Request, exc: FilaOpsException):
    logger.warning(
        f"FilaOps Exception: {exc.error_code} - {exc.message}",
        extra={"error_code": exc.error_code, "details": exc.details, "path": request.url.path}
    )
    # Add timestamp to error response for consistency
    error_dict = exc.to_dict()
    error_dict["timestamp"] = datetime.now(timezone.utc).isoformat() + "Z"
    return JSONResponse(status_code=exc.status_code, content=error_dict)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append({"field": field, "message": error["msg"], "type": error["type"]})
    logger.warning("Validation error on %s", request.url.path, extra={"errors": errors})
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": {"errors": errors},
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    logger.error(f"Database error on {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "DATABASE_ERROR",
            "message": "A database error occurred. Please try again.",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error on {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred. Please try again later.",
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z"
        },
    )


# Include API routes
app.include_router(api_v1_router, prefix="/api/v1")

# Static file serving for uploaded images
# Creates directory if it doesn't exist
STATIC_DIR = Path(__file__).parent.parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "uploads" / "products").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    return {"message": "FilaOps ERP API", "version": settings.VERSION, "status": "online"}


@app.get("/health")
async def health_check():
    """Deep health check that verifies critical dependencies."""
    from sqlalchemy import text
    from app.db.session import SessionLocal

    checks = {}
    overall_healthy = True

    # Check database connectivity
    db = None
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.warning("Health check DB probe failed", exc_info=True)
        checks["database"] = "failed"
        overall_healthy = False
    finally:
        if db is not None:
            db.close()

    status_code = 200 if overall_healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "healthy" if overall_healthy else "unhealthy",
            "checks": checks,
            "version": settings.VERSION,
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)