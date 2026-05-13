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
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone

from app.core.limiter import apply_rate_limiting
from app.core.paths import (
    resolve_frontend_dist,
    resolve_static_dir,
    resolve_upload_products_dir,
)
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
    """Verify database connectivity on startup.

    Schema management is handled exclusively by Alembic migrations
    (run via `alembic upgrade head` in the Docker entrypoint before uvicorn
    starts). create_all() is intentionally absent here — running it at startup
    races with Alembic and causes DuplicateTable errors on every upgrade.
    """
    try:
        from app.db.session import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as e:
        logger.error(f"Database connection check failed: {e}", exc_info=True)
        raise


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

def _load_pro_cors_origins() -> list[str]:
    """Load PRO CORS origins from the system_settings table.

    Reads `pro_portal_origins` and `pro_quoter_origins` (seeded by migration 080)
    and returns their merged contents. Customer-facing portal/quoter SPAs hosted
    on external domains (e.g. shop.example.com) need their origins listed here.

    Falls back to the `PRO_CORS_ORIGINS` env var (comma-separated) when the DB
    rows are empty/missing — for example before migration runs, when PRO is
    uninstalled (so the admin UI to populate the rows is gone), or when the
    operator prefers config-as-code. Note: a fully unreachable database raises
    earlier in the lifespan handler (`init_database()`); this function never
    sees that case.

    Every origin is re-validated through ``is_valid_origin`` before being
    returned, so any malformed entry that bypassed PUT validation (or arrived
    via the env fallback, which has no validation gate of its own) is silently
    dropped with a warning rather than handed to the CORS middleware.

    Returns an empty list if neither source provides values — Core still serves
    same-origin portal/quoter requests fine.
    """
    try:
        # Lazy imports so module-load doesn't depend on DB or endpoint module.
        from app.api.v1.endpoints.system_settings import is_valid_origin
        from app.db.session import SessionLocal
        from app.models.system_setting import SystemSetting

        with SessionLocal() as db:
            rows = db.query(SystemSetting).filter(
                SystemSetting.key.in_(["pro_portal_origins", "pro_quoter_origins"])
            ).all()
            origins: list[str] = []
            for row in rows:
                if not isinstance(row.value, list):
                    continue
                for raw in row.value:
                    if not isinstance(raw, str):
                        continue
                    candidate = raw.strip()
                    if is_valid_origin(candidate):
                        origins.append(candidate)
                    else:
                        logger.warning(
                            "Dropping malformed PRO CORS origin from DB row %s: %r",
                            row.key, raw,
                        )
            if origins:
                return origins
    except Exception as exc:
        logger.warning("Could not load PRO CORS origins from DB: %s", exc)

    # Escape hatch: env var fallback. Re-validate each entry — env input has no
    # gate equivalent to the PUT endpoint, so bad values would otherwise reach
    # CORSMiddleware and get treated as legitimate allowlist entries.
    try:
        from app.api.v1.endpoints.system_settings import is_valid_origin
    except Exception:
        # If the endpoint module can't be imported (Core boot before that side
        # is ready), accept entries verbatim so we don't lock the operator out.
        return [o.strip() for o in os.environ.get("PRO_CORS_ORIGINS", "").split(",") if o.strip()]

    raw = os.environ.get("PRO_CORS_ORIGINS", "")
    out: list[str] = []
    for entry in raw.split(","):
        candidate = entry.strip()
        if not candidate:
            continue
        if is_valid_origin(candidate):
            out.append(candidate)
        else:
            logger.warning(
                "Dropping malformed PRO CORS origin from PRO_CORS_ORIGINS env: %r",
                entry,
            )
    return out


# CORS middleware — base origins from settings.ALLOWED_ORIGINS plus PRO origins
# loaded from the system_settings table (or PRO_CORS_ORIGINS env fallback).
# PRO origins are merged at boot; updates require a Core restart to apply.
_pro_origins = _load_pro_cors_origins()
_base_origins = list(settings.ALLOWED_ORIGINS)
# dict.fromkeys preserves order while deduplicating
_all_cors_origins = list(dict.fromkeys(_base_origins + _pro_origins))

if _pro_origins:
    logger.info(
        "Loaded %d PRO CORS origin(s) merged with %d base origin(s)",
        len(_pro_origins), len(_base_origins),
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_all_cors_origins,
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

# Static file serving for uploaded images.
#
# Paths resolve via app.core.paths so deployments that put the source tree in
# a read-only location (PyInstaller bundles under Program Files, etc.) can
# override via env vars (STATIC_DIR / UPLOAD_PRODUCTS_DIR — pydantic-settings
# reads them unprefixed) without touching application code. mkdir is wrapped
# in try/except to match the file_storage.py convention — a non-writable
# static dir shouldn't crash app import. The /static mount is gated on the
# *actual* mkdir result rather than `.exists()`: if the directory pre-existed
# but the mkdir failed (e.g. read-only filesystem), we'd otherwise mount an
# unwritable tree. Product uploads dir failures are logged as errors because
# they manifest at runtime as opaque 500s — much easier to debug if the
# startup log already names the cause.
STATIC_DIR = resolve_static_dir(settings.STATIC_DIR)
PRODUCT_UPLOADS_DIR = resolve_upload_products_dir(
    settings.UPLOAD_PRODUCTS_DIR, static_dir=STATIC_DIR
)


def _try_mkdir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create %s: %s", path, exc)
        return False
    return True


_static_ok = _try_mkdir(STATIC_DIR)
_uploads_ok = _try_mkdir(PRODUCT_UPLOADS_DIR)
if not _uploads_ok:
    logger.error(
        "Product image uploads will fail at runtime — directory not "
        "writable: %s. Set UPLOAD_PRODUCTS_DIR to a writable path.",
        PRODUCT_UPLOADS_DIR,
    )
if _static_ok:
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    logger.error(
        "Cannot mount /static — directory not writable: %s. Set STATIC_DIR "
        "to a writable path.",
        STATIC_DIR,
    )


# Optional SPA hosting — when FRONTEND_DIST is configured (typically by a
# single-process deployment like the PyInstaller-bundled desktop install
# that has no separate web server in front of FastAPI), serve the React
# build directly. The standard Docker deployment leaves FRONTEND_DIST
# unset and lets Caddy / nginx handle frontend serving in front of the
# API — Core does nothing different in that case.
#
# The actual SPA mount lives at the bottom of this module (registered
# LAST so all API + plugin + explicit routes take precedence). We resolve
# and validate the directory here so the rest of the module can branch on
# `FRONTEND_DIST is not None`.
FRONTEND_DIST: Path | None = resolve_frontend_dist(settings.FRONTEND_DIST)
if FRONTEND_DIST is not None and not (FRONTEND_DIST / "index.html").is_file():
    logger.error(
        "FRONTEND_DIST is set to %s but no index.html found there; SPA will "
        "not be served. Check the path or unset FRONTEND_DIST.",
        FRONTEND_DIST,
    )
    FRONTEND_DIST = None
if FRONTEND_DIST is not None:
    logger.info("Serving React SPA from %s", FRONTEND_DIST)


@app.get("/")
async def root():
    """API status JSON, or SPA index.html when FRONTEND_DIST is configured."""
    if FRONTEND_DIST is not None:
        return FileResponse(FRONTEND_DIST / "index.html")
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


# ─── Optional plugin registration (config-driven) ───
# Core contains zero package references to any plugin. The operator sets
# FILAOPS_PRO_MODULE=filaops_pro (or any module with a register(app) callable)
# in .env to activate a plugin. Removing the env var = Community edition.
# The docker-entrypoint.sh sets this automatically when FILAOPS_LICENSE_KEY
# is present, so customers only need to set the license key.


def load_plugin(app, module_name: str | None = None) -> bool:
    """Load and register an optional plugin module.

    Args:
        app: The FastAPI application instance.
        module_name: Dotted Python module path (e.g. "filaops_pro").
            If None, reads from FILAOPS_PRO_MODULE env var.

    Returns:
        True if a plugin was loaded successfully, False otherwise.
    """
    import importlib

    module_name = module_name or os.getenv("FILAOPS_PRO_MODULE")
    if not module_name:
        return False
    try:
        plugin = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            logger.warning("Plugin module '%s' not installed — starting in Community mode", module_name)
        else:
            logger.error(
                "Plugin '%s' import failed — missing dependency '%s'",
                module_name, exc.name, exc_info=True,
            )
        return False
    except Exception:
        logger.error("Plugin module '%s' failed during import", module_name, exc_info=True)
        return False

    register = getattr(plugin, "register", None)
    if not callable(register):
        logger.error("Plugin module '%s' has no callable register(app)", module_name)
        return False

    try:
        result = register(app)
        if result:
            logger.info("Plugin '%s' registered successfully", module_name)
        else:
            logger.info("Plugin '%s' not activated (license invalid or missing)", module_name)
        return bool(result)
    except Exception:
        logger.error("Plugin module '%s' failed during register()", module_name, exc_info=True)
        return False


load_plugin(app)


# SPA mount.
#
# Mounted at "/" but MUST be registered last: Starlette matches in
# declaration order, so /api/v1/*, /health, /static/*, and any
# plugin-contributed routes (all registered above) take precedence.
# Anything left over goes through this mount.
#
# We use Starlette's StaticFiles directly rather than hand-rolling a
# catch-all that calls Path(user_input). StaticFiles has built-in
# path-traversal protection that CodeQL recognizes as a safe sink —
# avoiding an entire category of bug (symlink races, Windows short-name
# escapes, Unicode normalization edge cases, etc.) that hand-rolled
# guards routinely get wrong. We subclass only to add SPA-style 404
# fallback to index.html, which is what client-side routing needs:
# a request like /admin/items isn't a real file, but the React router
# can resolve it once index.html boots in the browser.
#
# The fallback opens a fixed path (FRONTEND_DIST / "index.html") with
# no user input — that's why it's safe.
if FRONTEND_DIST is not None:

    class _SPAStaticFiles(StaticFiles):
        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404:
                    return FileResponse(FRONTEND_DIST / "index.html")
                raise

    app.mount(
        "/",
        _SPAStaticFiles(directory=str(FRONTEND_DIST), html=True),
        name="spa",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)