"""Health check router."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter

from .. import __version__
from ..models import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", include_in_schema=False)
async def health_check(extended: bool = False):
    """System health check with startup diagnostics.

    Args:
        extended: If True, run LLM health check (has cost implications)
    """
    from ..startup_health import get_startup_health_data, run_startup_health_checks
    from p8fs_cluster.logging import get_logger

    logger = get_logger(__name__)

    # If extended=True, re-run health checks with LLM test
    if extended:
        try:
            await run_startup_health_checks(extended=True)
        except Exception as e:
            logger.warning(f"Extended health checks failed: {e}")

    startup_data = get_startup_health_data()

    # Build response with startup health data
    response = {
        "status": startup_data.get("status", "unknown"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
        "startup": startup_data
    }

    return response


@router.get("/ready", include_in_schema=False)
async def readiness_check():
    """Kubernetes readiness probe."""
    # TODO: Implement actual readiness checks
    return {"status": "ready"}


@router.get("/live", include_in_schema=False)
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"status": "alive", "timestamp": time.time()}