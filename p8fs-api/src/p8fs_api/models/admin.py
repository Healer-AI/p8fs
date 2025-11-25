"""Admin models for job callbacks."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class JobCallbackStatus(str, Enum):
    """Status enum for job callbacks."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCallbackItem(BaseModel):
    """Individual job callback item."""

    uri: HttpUrl = Field(..., description="URI endpoint for the job")
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Job payload data"
    )
    status: JobCallbackStatus = Field(
        default=JobCallbackStatus.PENDING, description="Job status"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Job timestamp"
    )


class JobCallbackBatchRequest(BaseModel):
    """Batch request for job callbacks."""

    jobs: list[JobCallbackItem] = Field(..., description="List of job callbacks")


class JobCallbackBatchResponse(BaseModel):
    """Response for job callback batch processing."""

    success: bool = Field(
        ..., description="Whether the batch was processed successfully"
    )
    processed_count: int = Field(..., description="Number of jobs processed")
    jobs: list[JobCallbackItem] = Field(..., description="Processed jobs with status")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Response timestamp"
    )
