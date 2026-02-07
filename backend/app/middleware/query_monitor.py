"""
Query Performance Monitoring Middleware

Monitors database query performance and logs slow queries for optimization.

Target: Log queries >1s, warn on queries >500ms
"""
import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

# Query performance thresholds (in seconds)
SLOW_QUERY_THRESHOLD = 1.0  # Log as ERROR
WARN_QUERY_THRESHOLD = 0.5  # Log as WARNING


class QueryPerformanceMonitor(BaseHTTPMiddleware):
    """
    Middleware to monitor query performance during HTTP requests.

    Tracks:
    - Total query count per request
    - Total query time per request
    - Individual slow queries
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Initialize query tracking in request state
        request.state.query_count = 0
        request.state.query_time = 0.0
        request.state.slow_queries = []

        # Process request
        start_time = time.time()
        response = await call_next(request)
        total_time = time.time() - start_time

        # Log request performance summary
        query_count = getattr(request.state, "query_count", 0)
        query_time = getattr(request.state, "query_time", 0.0)
        slow_queries = getattr(request.state, "slow_queries", [])

        if query_time > WARN_QUERY_THRESHOLD or slow_queries:
            log_level = logging.ERROR if query_time > SLOW_QUERY_THRESHOLD else logging.WARNING
            logger.log(
                log_level,
                f"Request performance: {request.method} {request.url.path} | "
                f"Total: {total_time:.3f}s | Queries: {query_count} ({query_time:.3f}s) | "
                f"Slow queries: {len(slow_queries)}"
            )

            # Log details of slow queries
            for sql, duration in slow_queries:
                logger.error(
                    f"SLOW QUERY ({duration:.3f}s): {sql[:200]}{'...' if len(sql) > 200 else ''}"
                )

        # Add performance headers for debugging
        response.headers["X-Query-Count"] = str(query_count)
        response.headers["X-Query-Time"] = f"{query_time:.3f}"
        response.headers["X-Total-Time"] = f"{total_time:.3f}"

        return response


def setup_query_logging(engine: Engine):
    """
    Set up SQLAlchemy event listeners for query performance tracking.

    This should be called once during application startup.
    """

    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """Record query start time"""
        conn.info.setdefault("query_start_time", []).append(time.time())

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        """Record query end time and log slow queries."""
        total = time.time() - conn.info["query_start_time"].pop(-1)

        # Log slow queries
        if total > SLOW_QUERY_THRESHOLD:
            logger.error(
                f"SLOW QUERY ({total:.3f}s): {statement[:500]}{'...' if len(statement) > 500 else ''}"
            )
        elif total > WARN_QUERY_THRESHOLD:
            logger.warning(
                f"Slow query ({total:.3f}s): {statement[:200]}{'...' if len(statement) > 200 else ''}"
            )


def log_query_plan(db_session, sql: str):
    """
    Helper function to log the execution plan for a slow query.

    Usage:
        from app.middleware.query_monitor import log_query_plan
        log_query_plan(db, "SELECT * FROM sales_orders WHERE status = 'pending'")
    """
    try:
        result = db_session.execute(text(f"EXPLAIN {sql}"))
        plan = "\n".join([str(row) for row in result])
        logger.info(f"Query plan:\n{plan}")
    except Exception as e:
        logger.warning(f"Could not get query plan: {e}")
