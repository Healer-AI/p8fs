"""Request context middleware for P8FS API.

This module provides middleware for extracting and managing request context,
including the X-Moment-Id header for moment-aware requests.
"""

from contextvars import ContextVar
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

# Context variables for storing request-scoped data
moment_id_context: ContextVar[Optional[str]] = ContextVar("moment_id", default=None)
tenant_id_context: ContextVar[Optional[str]] = ContextVar("tenant_id", default=None)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and store request context from headers."""

    async def dispatch(self, request: Request, call_next):
        """Extract context from headers and store in context variables."""
        # Extract X-Moment-Id header
        moment_id = request.headers.get("X-Moment-Id")
        if moment_id:
            moment_id_context.set(moment_id)

        # Extract tenant ID from authorization (set by auth middleware)
        # This will be set by the auth middleware after token validation
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id:
            tenant_id_context.set(tenant_id)

        try:
            response = await call_next(request)
            return response
        finally:
            # Clear context after request
            moment_id_context.set(None)
            tenant_id_context.set(None)


def get_moment_id() -> Optional[str]:
    """Get the current moment ID from request context."""
    return moment_id_context.get()


def get_tenant_id() -> Optional[str]:
    """Get the current tenant ID from request context."""
    return tenant_id_context.get()


def setup_request_context(app):
    """Add request context middleware to FastAPI application."""
    app.add_middleware(RequestContextMiddleware)
