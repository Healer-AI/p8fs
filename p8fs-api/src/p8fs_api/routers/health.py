"""Health check router."""

import time
from datetime import datetime

from fastapi import APIRouter

from .. import __version__
from ..models import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_check():
    """System health check."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version=__version__,
        services={
            "api": "healthy",
            "auth": "unknown",  # TODO: Implement service health checks
            "core": "unknown",
            "node": "unknown"
        }
    )


@router.get("/ready", include_in_schema=False)
async def readiness_check():
    """Kubernetes readiness probe."""
    # TODO: Implement actual readiness checks
    return {"status": "ready"}


@router.get("/live", include_in_schema=False)
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"status": "alive", "timestamp": time.time()}