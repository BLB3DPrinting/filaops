"""
FilaOps ERP - Structured Logging Configuration

Provides JSON-formatted logging for log aggregation and compliance.
Includes separate audit logging for business events.

Usage:
    from app.logging_config import get_logger, audit_log

    logger = get_logger(__name__)
    logger.info("Processing order", extra={"order_id": 123})

    # For business events requiring audit trail
    audit_log("ORDER_CREATED", user_id=1, order_id=123, details={"total": 99.99})
"""
import json
import logging
import logging.handlers
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.core.settings import settings


class JSONFormatter(logging.Formatter):
    """
    Formats log records as JSON for log aggregation systems.

    Output format:
    {
        "timestamp": "2024-01-01T12:00:00.000Z",
        "level": "INFO",
        "logger": "app.api.v1.endpoints.orders",
        "message": "Order created",
        "order_id": 123,
        "user_id": 1,
        ...
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        # Include correlation ID from contextvar if available
        from app.middleware.correlation_id import correlation_id_var
        cid = correlation_id_var.get("")

        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if cid:
            log_data["correlation_id"] = cid

        # Add location info for errors
        if record.levelno >= logging.ERROR:
            log_data["location"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add extra fields (user_id, order_id, etc.)
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "taskName", "message",
            }:
                # Serialize non-JSON-serializable objects
                try:
                    json.dumps(value)
                    log_data[key] = value
                except (TypeError, ValueError):
                    log_data[key] = str(value)

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """
    Formats log records as human-readable text for development.

    Output format:
    2024-01-01 12:00:00 [INFO] app.api.v1.endpoints.orders: Order created order_id=123
    """

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        base_msg = f"{timestamp} [{record.levelname}] {record.name}: {record.getMessage()}"

        # Append extra fields
        extras = []
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "exc_info", "exc_text", "thread", "threadName",
                "taskName", "message",
            }:
                extras.append(f"{key}={value}")

        if extras:
            base_msg += " " + " ".join(extras)

        if record.exc_info:
            base_msg += "\n" + self.formatException(record.exc_info)

        return base_msg


class AuditFormatter(logging.Formatter):
    """
    Formats audit log records with compliance-required fields.

    Output format (JSON):
    {
        "timestamp": "2024-01-01T12:00:00.000Z",
        "event": "ORDER_CREATED",
        "user_id": 1,
        "resource_type": "order",
        "resource_id": 123,
        "details": {...},
        "ip_address": "192.168.1.1"
    }
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": getattr(record, "event", record.getMessage()),
            "user_id": getattr(record, "user_id", None),
            "resource_type": getattr(record, "resource_type", None),
            "resource_id": getattr(record, "resource_id", None),
            "details": getattr(record, "details", {}),
            "ip_address": getattr(record, "ip_address", None),
        }

        # Remove None values
        log_data = {k: v for k, v in log_data.items() if v is not None}

        return json.dumps(log_data)


def setup_logging() -> None:
    """
    Configure application logging based on settings.

    Call this once at application startup.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    log_format = getattr(settings, "LOG_FORMAT", "json").lower()

    # Create formatter based on settings
    if log_format == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # File handler (if configured)
    log_file = getattr(settings, "LOG_FILE", None)
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)

    # Setup audit logger
    setup_audit_logging()

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def setup_audit_logging() -> None:
    """Configure separate audit logger for business events."""
    audit_logger = logging.getLogger("audit")
    audit_logger.setLevel(logging.INFO)
    audit_logger.handlers.clear()
    audit_logger.propagate = False  # Don't send to root logger

    # Audit file handler
    audit_file = getattr(settings, "AUDIT_LOG_FILE", "./logs/audit.log")
    if audit_file:
        os.makedirs(os.path.dirname(audit_file), exist_ok=True)
        audit_handler = logging.handlers.RotatingFileHandler(
            audit_file,
            maxBytes=50 * 1024 * 1024,  # 50 MB
            backupCount=10,  # Keep more history for compliance
        )
        audit_handler.setFormatter(AuditFormatter())
        audit_handler.setLevel(logging.INFO)
        audit_logger.addHandler(audit_handler)

    # Also log audit events to console in development
    if getattr(settings, "DEBUG", False):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(AuditFormatter())
        audit_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.

    Usage:
        logger = get_logger(__name__)
        logger.info("Something happened", extra={"key": "value"})

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def audit_log(
    event: str,
    *,
    user_id: Optional[int] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[Any] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Log a business event to the audit log.

    For compliance and traceability, use this for:
    - User authentication events (login, logout, password change)
    - Order lifecycle events (created, updated, shipped)
    - Production events (started, completed, scrapped)
    - Administrative actions (user created, settings changed)

    Args:
        event: Event name (e.g., "ORDER_CREATED", "USER_LOGIN")
        user_id: ID of user who triggered the event
        resource_type: Type of resource affected (e.g., "order", "user")
        resource_id: ID of the affected resource
        details: Additional event-specific data
        ip_address: IP address of the request

    Example:
        audit_log(
            "ORDER_CREATED",
            user_id=1,
            resource_type="sales_order",
            resource_id=123,
            details={"total": 99.99, "items": 3}
        )
    """
    audit_logger = logging.getLogger("audit")
    audit_logger.info(
        event,
        extra={
            "event": event,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details or {},
            "ip_address": ip_address,
        },
    )


# Convenience function to get request IP from FastAPI
def get_client_ip(request) -> Optional[str]:
    """
    Extract client IP from FastAPI request, handling proxies.

    Args:
        request: FastAPI Request object

    Returns:
        Client IP address or None
    """
    # Check for proxy headers
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()

    x_real_ip = request.headers.get("X-Real-IP")
    if x_real_ip:
        return x_real_ip

    # Fall back to direct client
    if request.client:
        return request.client.host

    return None
