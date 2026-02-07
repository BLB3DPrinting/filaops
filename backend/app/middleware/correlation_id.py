"""
Correlation ID middleware for request tracing.

Generates or propagates a unique request ID for every API call,
making it possible to trace a single request across all log entries.
"""
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Context variable accessible from any async task within the same request
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Reads X-Request-ID from the incoming request (or generates a UUID4),
    stores it in request.state and a contextvar, and echoes it back
    in the response header.
    """

    async def dispatch(self, request: Request, call_next):
        # Accept caller-provided ID or generate one
        request_id = request.headers.get("X-Request-ID", "")

        # Validate length to prevent header injection
        if not request_id or len(request_id) > 128:
            request_id = uuid.uuid4().hex

        # Make available to request handlers and logging
        request.state.correlation_id = request_id
        correlation_id_var.set(request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
