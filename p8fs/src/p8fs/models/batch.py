"""
Batch processing models for P8FS.

Models for handling batch job processing and status tracking.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class BatchJobStatus(str, Enum):
    """Status of a batch job."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchJobInfo(BaseModel):
    """Information about a batch job."""
    
    job_id: str = Field(description="Unique job identifier")
    status: BatchJobStatus = Field(description="Current job status")
    created_at: str = Field(description="Job creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    progress: float = Field(0.0, description="Job progress (0.0 to 1.0)")
    total_tasks: int = Field(0, description="Total number of tasks")
    completed_tasks: int = Field(0, description="Number of completed tasks")
    failed_tasks: int = Field(0, description="Number of failed tasks")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Job metadata")


class BatchRequest(BaseModel):
    """Request to create a batch job."""
    
    tasks: List[Dict[str, Any]] = Field(description="List of tasks to process")
    job_type: str = Field(description="Type of batch job")
    priority: int = Field(1, description="Job priority")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Request metadata")


class BatchResponse(BaseModel):
    """Response from a batch job operation."""
    
    job_id: str = Field(description="Job identifier")
    status: BatchJobStatus = Field(description="Job status")
    message: str = Field(description="Response message")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="Job results")


class JobStatusResponse(BaseModel):
    """Response for job status queries."""
    
    job_id: str = Field(description="Job identifier")
    status: BatchJobStatus = Field(description="Current job status")
    progress: float = Field(0.0, description="Job progress (0.0 to 1.0)")
    created_at: str = Field(description="Job creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    completed_tasks: int = Field(0, description="Number of completed tasks")
    total_tasks: int = Field(0, description="Total number of tasks")
    error_message: Optional[str] = Field(None, description="Error message if job failed")