"""Files router for listing resources with pagination."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel, Field

from p8fs_api.controllers.files_controller import FilesController
from p8fs_api.middleware import User, get_current_user
from p8fs_api.models.responses import ErrorResponse


class FileInfo(BaseModel):
    """File information model."""

    id: str = Field(..., description="File ID")
    uri: str | None = Field(None, description="File URI")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str | None = Field(None, description="Last update timestamp")
    tenant_id: str = Field(..., description="Tenant ID")
    encryption_key_owner: str | None = Field(None, description="Encryption mode (USER, SYSTEM, NONE)")


class FilesListResponse(BaseModel):
    """Response model for file listing."""

    files: list[FileInfo] = Field(..., description="List of files")
    total_count: int = Field(..., description="Total number of files matching filters")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of files per page")
    total_pages: int = Field(..., description="Total number of pages")


router = APIRouter(
    prefix="/api/v1/files",
    tags=["files"],
    responses={
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
        400: {"model": ErrorResponse, "description": "Bad request"},
    },
)


@router.get("/", response_model=FilesListResponse)
async def list_files(
    tenant_id: str | None = Query(None, description="Filter by tenant ID"),
    encryption_key_owner: str | None = Query(None, description="Filter by encryption mode (USER, SYSTEM, NONE)"),
    start_date: str | None = Query(None, description="Filter by start date (ISO format)"),
    end_date: str | None = Query(None, description="Filter by end date (ISO format)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(50, ge=1, le=200, description="Number of results per page (max 200)"),
    current_user: User = Depends(get_current_user),
) -> FilesListResponse:
    """List files with pagination and filtering.

    Returns a paginated list of files (resources) with optional filtering by:
    - tenant_id: Filter by specific tenant
    - encryption_key_owner: Filter by encryption mode (USER, SYSTEM, NONE)
    - start_date: Filter files created on or after this date
    - end_date: Filter files created on or before this date

    Results are ordered by creation date (newest first) and include:
    - Total count of matching files
    - Current page and page size
    - Total number of pages
    """
    # Validate date formats if provided
    if start_date:
        try:
            datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid start_date format. Use ISO 8601 format (e.g., 2024-01-01T00:00:00Z)"
            )

    if end_date:
        try:
            datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid end_date format. Use ISO 8601 format (e.g., 2024-01-01T23:59:59Z)"
            )

    # Validate encryption_key_owner if provided
    if encryption_key_owner and encryption_key_owner not in ["USER", "SYSTEM", "NONE"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid encryption_key_owner. Must be one of: USER, SYSTEM, NONE"
        )

    controller = FilesController()
    result = await controller.list_files(
        tenant_id=tenant_id,
        encryption_key_owner=encryption_key_owner,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )

    return FilesListResponse(**result)
