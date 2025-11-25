"""Rate limiting middleware."""

from fastapi import Request
from fastapi.responses import JSONResponse
from p8fs_cluster.config.settings import config
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address) if getattr(config, 'rate_limit_enabled', True) else None


def setup_rate_limiting(app):
    """Configure rate limiting."""
    if limiter:
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Handle rate limit exceeded exceptions."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Rate limit exceeded: {exc.detail}",
            "retry_after": exc.retry_after
        }
    )