# backend/app/core/settings.py
"""
FilaOps ERP - Configuration Management with pydantic-settings

- Loads from environment and root .env
- Validates and normalizes values
- Cached singleton via get_settings()
"""
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict, Any
from decimal import Decimal
from urllib.parse import unquote, urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Read version from VERSION file (single source of truth)
_VERSION_FILE = Path(__file__).resolve().parent.parent.parent / "VERSION"
_VERSION = _VERSION_FILE.read_text().strip() if _VERSION_FILE.exists() else "0.0.0"

# Calculate path to .env in backend folder (3 levels up from this file)
# backend/app/core/settings.py -> backend/.env
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"

# Placeholder credential values rejected in production (audit finding F12).
# Covers docker-compose fallbacks (changeme, change-in-production), the
# Settings field defaults below (postgres, change-this-...), the .env.example
# sample text (your-secret-key-here, your-secure-password-here), and "" for
# users who clear the value but never set a real one.
_SECRET_KEY_PLACEHOLDERS = frozenset({
    "",
    "change-in-production",
    "your-secret-key-here",
    "change-this-to-a-random-secret-key-in-production",
})
_DB_PASSWORD_PLACEHOLDERS = frozenset({
    "",
    "changeme",
    "password",
    "postgres",
    "your-secure-password-here",
})


class Settings(BaseSettings):
    """
    Application settings with validation.

    Environment variables take precedence over .env file values.
    Prefix FILAOPS_ can be used for any setting (e.g., FILAOPS_DEBUG=true).
    """

    # -------------------------------------------------
    # Pydantic Settings (v2) — must be *inside* class
    # -------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===================
    # Application Settings
    # ===================
    PROJECT_NAME: str = "FilaOps"
    VERSION: str = _VERSION
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    ENVIRONMENT: str = Field(default="development", description="Deployment environment")

    # ===================
    # Database Settings
    # ===================
    DB_HOST: str = Field(default="localhost", description="PostgreSQL host")
    DB_PORT: int = Field(default=5432, description="PostgreSQL port")
    DB_NAME: str = Field(default="filaops", description="Database name")
    DB_USER: str = Field(default="postgres", description="Database user")
    DB_PASSWORD: str = Field(default="postgres", description="Database password")
    DATABASE_URL: Optional[str] = Field(
        default=None, description="Full database URL (overrides DB_* settings)"
    )
    DB_POOL_SIZE: int = Field(default=5, description="SQLAlchemy connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Max connections above pool_size")

    @property
    def database_url(self) -> str:
        """Build PostgreSQL database URL from components or use explicit URL."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    # ===================
    # Security Settings
    # ===================
    SECRET_KEY: str = Field(
        default="change-this-to-a-random-secret-key-in-production",
        description="JWT signing key - MUST change in production",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30, description="JWT token expiration in minutes"
    )
    API_KEY: Optional[str] = Field(default=None, description="API key for integrations")
    COOKIE_SECURE: bool = Field(
        default=False,
        description="Set Secure flag on auth cookies (requires HTTPS). Must be true in production.",
    )
    AUTH_MODE: str = Field(
        default="cookie",
        description="Auth token delivery: 'cookie' (httpOnly) or 'header' (bearer in body). Use 'header' to rollback.",
    )

    # SECRET_KEY validation lives in `validate_no_placeholder_credentials`
    # (model_validator at the bottom of the class). Both SECRET_KEY and
    # DB_PASSWORD share one post-init check so production startup fails
    # for either placeholder rather than only the first one Pydantic sees.

    # ===================
    # CORS Settings
    # ===================
    # Note: Use str type internally to avoid pydantic-settings JSON parsing issues.
    # Access via allowed_origins property for the parsed list.
    ALLOWED_ORIGINS_STR: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174,http://localhost:3000,http://127.0.0.1:3000,http://localhost:8001,http://127.0.0.1:8001",
        alias="ALLOWED_ORIGINS",
        description="Allowed CORS origins (comma-separated or JSON array)",
    )

    @field_validator("ALLOWED_ORIGINS_STR", mode="before")
    @classmethod
    def parse_cors_origins_raw(cls, v):
        """Handle JSON array, comma-separated string, or empty value."""
        if v is None or v == "":
            return "http://localhost:5173"  # Default if empty
        if isinstance(v, list):
            return ",".join(v)
        if isinstance(v, str):
            # Try JSON array first
            if v.strip().startswith("["):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return ",".join(str(x) for x in parsed)
                except json.JSONDecodeError:
                    pass
            return v
        return str(v)

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Get allowed origins as a list."""
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_STR.split(",") if origin.strip()]

    FRONTEND_URL: str = Field(
        default="http://localhost:5173", description="Frontend URL for redirects"
    )

    @model_validator(mode="after")
    def add_frontend_url_to_cors(self):
        """Ensure FRONTEND_URL is allowed for CORS."""
        if self.FRONTEND_URL and self.FRONTEND_URL not in self.ALLOWED_ORIGINS:
            # Append to the raw string since ALLOWED_ORIGINS is a property
            self.ALLOWED_ORIGINS_STR = f"{self.ALLOWED_ORIGINS_STR},{self.FRONTEND_URL}"
        return self

    @model_validator(mode="after")
    def validate_no_placeholder_credentials(self):
        """Reject placeholder SECRET_KEY/DB_PASSWORD in production; warn in dev.

        Audit finding F12 (Portainer compatibility review): docker-compose has
        :-defaults of `changeme` / `change-in-production`, so a fresh
        `git clone && docker compose up -d` previously produced a "running"
        stack with insecure credentials. This validator turns that footgun
        into a fail-fast at config load.
        """
        offenders = []
        if self.SECRET_KEY.strip().lower() in _SECRET_KEY_PLACEHOLDERS:
            offenders.append("SECRET_KEY")

        # The effective DB password is whatever `database_url` will hand to
        # SQLAlchemy at runtime: the password embedded in DATABASE_URL when
        # set, otherwise self.DB_PASSWORD. Validating only DB_PASSWORD would
        # leave docker-compose's `DATABASE_URL: postgresql+psycopg://...:
        # ${DB_PASSWORD:-changeme}@db:5432/...` as an open airlock.
        #
        # urlsplit().password returns None when the URL has no password
        # component (peer auth, trust auth, .pgpass, IAM auth). In that
        # case we deliberately skip the check rather than fail-closed —
        # passwordless auth is a legitimate production setup.
        # `unquote` decodes percent-escapes so the validator sees the same
        # password SQLAlchemy will actually use at connect time.
        if self.DATABASE_URL:
            url_password = urlsplit(self.DATABASE_URL).password
            effective_db_password = unquote(url_password) if url_password else None
        else:
            effective_db_password = self.DB_PASSWORD
        if (
            effective_db_password is not None
            and effective_db_password.strip().lower() in _DB_PASSWORD_PLACEHOLDERS
        ):
            offenders.append("DB_PASSWORD")

        if not offenders:
            return self

        names = ", ".join(offenders)
        hint = "Generate a real value with: openssl rand -hex 32"
        if self.ENVIRONMENT.strip().lower() == "production":
            raise RuntimeError(
                f"Refusing to start in production: placeholder credential(s) "
                f"detected for {names}. {hint}"
            )
        logger.warning(
            "Insecure placeholder credential(s) detected for %s. "
            "This is allowed in development but will block production startup. %s",
            names,
            hint,
        )
        return self

    # ===================
    # Bambu Print Suite
    # ===================
    BAMBU_SUITE_API_URL: str = Field(
        default="http://localhost:8001", description="Bambu Print Suite API URL"
    )
    BAMBU_SUITE_API_KEY: Optional[str] = Field(default=None, description="API key")

    # ===================
    # File Storage
    # ===================
    UPLOAD_DIR: str = Field(default="", description="Quote upload dir (defaults to <backend>/uploads/quotes)")
    # The three fields below let packaged/non-Docker deployments override
    # historically-hardcoded paths under the source tree. Empty default ==
    # use the in-repo path; resolution lives in app.core.paths.
    STATIC_DIR: str = Field(
        default="",
        description="Static files root, mounted at /static (defaults to <backend>/static)",
    )
    UPLOAD_PRODUCTS_DIR: str = Field(
        default="",
        description="Product image upload dir (defaults to <STATIC_DIR>/uploads/products)",
    )
    UPLOAD_PO_DOCS_DIR: str = Field(
        default="",
        description="PO document upload dir (defaults to <backend>/uploads/po_documents)",
    )
    FRONTEND_DIST: str = Field(
        default="",
        description=(
            "React SPA dist directory. When set, FastAPI serves the SPA at / "
            "with a client-side-routing catch-all. When empty (default), Core "
            "does not serve the SPA — a separate web server (Caddy/nginx in "
            "Docker) is expected to handle it. Single-process deployments "
            "(PyInstaller-bundled desktop install) point this at the bundled "
            "frontend dist."
        ),
    )
    MAX_FILE_SIZE_MB: int = Field(default=100, description="Max upload size (MB)")
    ALLOWED_FILE_FORMATS: List[str] = Field(
        default=[".3mf", ".stl"], description="Allowed upload extensions"
    )

    @field_validator("ALLOWED_FILE_FORMATS", mode="before")
    @classmethod
    def parse_file_formats(cls, v):
        if isinstance(v, str):
            return [fmt.strip() for fmt in v.split(",") if fmt.strip()]
        return v

    # ===================
    # EasyPost
    # ===================
    EASYPOST_API_KEY: Optional[str] = None
    EASYPOST_TEST_MODE: bool = True

    # ===================
    # Email (SMTP)
    # ===================
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@example.com"
    SMTP_FROM_NAME: str = "Your Company Name"
    SMTP_TLS: bool = True

    # ===================
    # Admin & Business
    # ===================
    ADMIN_APPROVAL_EMAIL: str = "admin@example.com"
    BUSINESS_EMAIL: str = "info@yourcompany.com"
    BUSINESS_NAME: str = "Your Company Name"

    # ===================
    # Ship From Address
    # ===================
    SHIP_FROM_NAME: str = "Your Company Name"
    SHIP_FROM_STREET1: str = "123 Main Street"
    SHIP_FROM_STREET2: Optional[str] = None
    SHIP_FROM_CITY: str = "Your City"
    SHIP_FROM_STATE: str = "ST"
    SHIP_FROM_ZIP: str = "12345"
    SHIP_FROM_COUNTRY: str = "US"
    SHIP_FROM_PHONE: str = "555-555-5555"

    # ===================
    # Redis / Background Jobs
    # ===================
    REDIS_URL: Optional[str] = None

    # ===================
    # Logging
    # ===================
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json or text
    LOG_FILE: Optional[str] = None
    AUDIT_LOG_FILE: Optional[str] = "./logs/audit.log"

    # ===================
    # Product Tier
    # ===================
    TIER: str = Field(default="community", description="community, pro, enterprise")

    # ===================
    # License Server (PR-02)
    # ===================
    # Where Core's activation endpoint sends the license key for validation.
    # Defaults point at our production instance; override in dev/staging via
    # env var. License-server API contract is documented in
    # license-server/CLAUDE.md.
    LICENSE_SERVER_URL: str = Field(
        default="https://license.blb3dprinting.com",
        description="Base URL of the FilaOps license server (no trailing slash)",
    )
    LICENSE_API_KEY: Optional[str] = Field(
        default=None,
        description=(
            "Shared X-API-Key sent to the license server for server-to-server "
            "auth. Required for activation; the license server rejects calls "
            "without it. Same key across all customer deployments."
        ),
    )
    LICENSE_CONFIG_DIR: str = Field(
        default="/var/lib/filaops/config",
        description=(
            "Directory holding install_uuid + license.json. Override in dev "
            "(LICENSE_CONFIG_DIR env var) when /var/lib isn't writable."
        ),
    )

    @field_validator("LICENSE_SERVER_URL")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        # The endpoint module concatenates `/api/v1/validate`, so a trailing
        # slash on the base URL would produce `//api/...` and 404.
        return v.rstrip("/") if v else v

    # ===================
    # MRP Settings (safe defaults)
    # ===================
    INCLUDE_SALES_ORDERS_IN_MRP: bool = True
    AUTO_MRP_ON_ORDER_CREATE: bool = False
    AUTO_MRP_ON_SHIPMENT: bool = False
    AUTO_MRP_ON_CONFIRMATION: bool = False
    MRP_ENABLE_SUB_ASSEMBLY_CASCADING: bool = False
    MRP_VALIDATION_STRICT_MODE: bool = True

    # ===================
    # Manufacturing
    # ===================
    MACHINE_HOURLY_RATE: float = 1.50
    MACHINE_TIME_SKU: str = "MFG-MACHINE-TIME"
    LEGACY_MACHINE_TIME_SKU: str = "SVC-MACHINE-TIME"

    # ===================
    # Pricing
    # ===================
    MATERIAL_COST_PLA: float = 0.017
    MATERIAL_COST_PETG: float = 0.017
    MATERIAL_COST_ABS: float = 0.020
    MATERIAL_COST_ASA: float = 0.020
    MATERIAL_COST_TPU: float = 0.033

    MARKUP_PLA: float = 3.5
    MARKUP_PETG: float = 3.5
    MARKUP_ABS: float = 4.0
    MARKUP_ASA: float = 4.0
    MARKUP_TPU: float = 4.5

    MINIMUM_ORDER_VALUE: float = 10.00
    AUTO_APPROVE_THRESHOLD: float = 50.00
    QUOTE_EXPIRATION_DAYS: int = 30

    ABS_ASA_MAX_X_MM: int = 200
    ABS_ASA_MAX_Y_MM: int = 200
    ABS_ASA_MAX_Z_MM: int = 100

    PRINTING_HOURS_PER_DAY: int = 8
    PROCESSING_BUFFER_DAYS: int = 2
    RUSH_48H_REDUCTION_DAYS: int = 3
    RUSH_24H_REDUCTION_DAYS: int = 4

    # JSON-like knobs from env; allow string or parsed object
    QUANTITY_DISCOUNTS: Optional[Any] = Field(
        default=None,
        description="JSON: [{'min_quantity': 100, 'discount': 0.30}, ...]",
    )
    FINISH_COSTS: Optional[Any] = Field(
        default=None,
        description="JSON: {'standard': 0, 'cleanup': 3, ...}",
    )
    RUSH_MULTIPLIERS: Optional[Any] = Field(
        default=None,
        description="JSON: {'standard': 1.0, 'fast': 1.25, ...}",
    )
    PRINTER_FLEET: Optional[Any] = Field(
        default=None,
        description="JSON: {'total_printers': 4, 'printers': [...]}",
    )

    @field_validator(
        "QUANTITY_DISCOUNTS", "FINISH_COSTS", "RUSH_MULTIPLIERS", "PRINTER_FLEET", mode="before"
    )
    @classmethod
    def parse_json_string(cls, v):
        """Accept JSON string or already-parsed object."""
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return None
        return v

    @property
    def material_costs(self) -> Dict[str, Decimal]:
        return {
            "PLA": Decimal(str(self.MATERIAL_COST_PLA)),
            "PETG": Decimal(str(self.MATERIAL_COST_PETG)),
            "ABS": Decimal(str(self.MATERIAL_COST_ABS)),
            "ASA": Decimal(str(self.MATERIAL_COST_ASA)),
            "TPU": Decimal(str(self.MATERIAL_COST_TPU)),
        }

    @property
    def markup_multipliers(self) -> Dict[str, Decimal]:
        return {
            "PLA": Decimal(str(self.MARKUP_PLA)),
            "PETG": Decimal(str(self.MARKUP_PETG)),
            "ABS": Decimal(str(self.MARKUP_ABS)),
            "ASA": Decimal(str(self.MARKUP_ASA)),
            "TPU": Decimal(str(self.MARKUP_TPU)),
        }

    @property
    def quantity_discounts(self) -> List[Dict[str, Any]]:
        if self.QUANTITY_DISCOUNTS and isinstance(self.QUANTITY_DISCOUNTS, list):
            return [
                {
                    "min_quantity": d["min_quantity"],
                    "discount": Decimal(str(d["discount"])),
                }
                for d in self.QUANTITY_DISCOUNTS  # type: ignore[union-attr]
            ]
        return [
            {"min_quantity": 100, "discount": Decimal("0.30")},
            {"min_quantity": 50, "discount": Decimal("0.20")},
            {"min_quantity": 10, "discount": Decimal("0.10")},
        ]

    @property
    def finish_costs(self) -> Dict[str, Decimal]:
        if self.FINISH_COSTS and isinstance(self.FINISH_COSTS, dict):
            return {k: Decimal(str(v)) for k, v in self.FINISH_COSTS.items()}  # type: ignore[union-attr]
        return {
            "standard": Decimal("0.00"),
            "cleanup": Decimal("3.00"),
            "sanded": Decimal("8.00"),
            "painted": Decimal("20.00"),
            "custom": Decimal("0.00"),
        }

    @property
    def rush_multipliers(self) -> Dict[str, Decimal]:
        if self.RUSH_MULTIPLIERS and isinstance(self.RUSH_MULTIPLIERS, dict):
            return {k: Decimal(str(v)) for k, v in self.RUSH_MULTIPLIERS.items()}  # type: ignore[union-attr]
        return {
            "standard": Decimal("1.0"),
            "fast": Decimal("1.25"),
            "rush_48h": Decimal("1.5"),
            "rush_24h": Decimal("2.0"),
        }

    @property
    def printer_fleet_config(self) -> Dict[str, Any]:
        if self.PRINTER_FLEET and isinstance(self.PRINTER_FLEET, dict):
            return self.PRINTER_FLEET  # type: ignore[return-value]
        return {
            "total_printers": 4,
            "printers": [
                {"model": "Bambu P1S", "quantity": 1},
                {"model": "Bambu A1", "quantity": 3},
            ],
            "daily_capacity_hours": 80,
            "average_hours_per_printer_per_day": 20,
        }

    @property
    def abs_asa_size_limits(self) -> Dict[str, int]:
        return {
            "max_x_mm": self.ABS_ASA_MAX_X_MM,
            "max_y_mm": self.ABS_ASA_MAX_Y_MM,
            "max_z_mm": self.ABS_ASA_MAX_Z_MM,
        }

    @property
    def delivery_estimation(self) -> Dict[str, Any]:
        return {
            "printing_hours_per_day": self.PRINTING_HOURS_PER_DAY,
            "processing_buffer_days": self.PROCESSING_BUFFER_DAYS,
            "rush_reduction_days": {
                "rush_48h": self.RUSH_48H_REDUCTION_DAYS,
                "rush_24h": self.RUSH_24H_REDUCTION_DAYS,
            },
        }

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"

    @property
    def is_pro_tier(self) -> bool:
        return self.TIER.lower() in ("pro", "enterprise")

    @property
    def is_enterprise_tier(self) -> bool:
        return self.TIER.lower() == "enterprise"


@lru_cache
def get_settings() -> Settings:
    """Singleton settings loader (cached)."""
    return Settings()


# Convenience alias for backward compatibility with existing code
settings = get_settings()
