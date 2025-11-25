"""Admin router for protected admin-only endpoints."""

import hashlib
import os
import socket

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from p8fs_cluster.logging.setup import get_logger

from ..models.admin import (
    JobCallbackBatchRequest,
    JobCallbackBatchResponse,
)

logger = get_logger(__name__)

router = APIRouter(tags=["Admin"])
security = HTTPBearer()


def get_admin_token() -> str:
    """Get the admin token from environment variables."""
    # Try P8FS_API_KEY first (new), then fall back to P8FS_ADMIN_TOKEN (legacy)
    admin_token = os.getenv("P8FS_API_KEY") or os.getenv("P8FS_ADMIN_TOKEN")
    if not admin_token:
        # Generate a default token for development
        hostname = socket.gethostname()
        default_data = f"p8fs-admin-{hostname}-development"
        admin_token = f"p8fs-{hashlib.sha256(default_data.encode()).hexdigest()[:32]}"
        logger.warning(
            f"No P8FS_API_KEY or P8FS_ADMIN_TOKEN set, using generated token: {admin_token}"
        )

    return admin_token


def require_admin_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    """Validate admin bearer token."""
    expected_token = get_admin_token()

    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return credentials.credentials


@router.post(
    "/api/v1/admin/jobs/callback",
    response_model=JobCallbackBatchResponse,
    summary="Job callback batch endpoint",
    description="Admin endpoint for processing job callbacks in batches",
)
async def job_callback_batch(
    request: JobCallbackBatchRequest,
    _token: str = Depends(require_admin_token),
) -> JobCallbackBatchResponse:
    """Process a batch of job callbacks.

    This endpoint is protected by admin bearer token authentication.
    Use the P8FS_API_KEY environment variable value as the bearer token.

    Args:
        request: Batch of job callbacks to process
        _token: Admin bearer token (automatically validated)

    Returns:
        JobCallbackBatchResponse with processing results

    Example:
        ```bash
        curl -X POST https://api.example.com/api/v1/admin/jobs/callback \\
          -H "Authorization: Bearer eepis-65aeda98c16e1713a95aac269e0e75d41d3fbcfe4dea167e8d58d51c7fe89d5c" \\
          -H "Content-Type: application/json" \\
          -d '{
            "jobs": [
              {
                "uri": "https://example.com/job1",
                "payload": {"key": "value"},
                "status": "completed",
                "timestamp": "2024-01-15T10:30:00Z"
              }
            ]
          }'
        ```
    """
    logger.info(f"Received job callback batch with {len(request.jobs)} jobs")

    # TODO: Implement actual job callback processing logic here
    # For now, just return the jobs as-is (stub implementation)

    return JobCallbackBatchResponse(
        success=True,
        processed_count=len(request.jobs),
        jobs=request.jobs,
    )
