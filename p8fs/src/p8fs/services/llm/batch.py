"""
Batch Request and Response Models for OpenAI Batch API

These models handle the structure for batch processing requests and responses
for GPT-5 and other OpenAI models, particularly useful for cost-effective
large-scale processing.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field, model_validator
import uuid


# GPT-5 specific types for convenience
ReasoningEffort = Literal["low", "medium", "high"]
VerbosityLevel = Literal["low", "medium", "high"]


class GPT5Settings(BaseModel):
    """GPT-5 specific parameters with convenience methods"""
    
    reasoning_effort: Optional[ReasoningEffort] = Field(
        None, description="Reasoning effort level: low, medium, high"
    )
    verbosity: Optional[VerbosityLevel] = Field(
        None, description="Verbosity level: low, medium, high"
    )
    
    @classmethod
    def quick_analysis(cls) -> "GPT5Settings":
        """Settings for quick analysis with minimal reasoning"""
        return cls(reasoning_effort="low", verbosity="low")
    
    @classmethod
    def standard_analysis(cls) -> "GPT5Settings":
        """Settings for standard analysis with balanced reasoning"""
        return cls(reasoning_effort="medium", verbosity="low")
    
    @classmethod
    def comprehensive_analysis(cls) -> "GPT5Settings":
        """Settings for comprehensive analysis with deep reasoning"""
        return cls(reasoning_effort="high", verbosity="low")
    
    @classmethod
    def verbose_debug(cls) -> "GPT5Settings":
        """Settings for debugging with high verbosity"""
        return cls(reasoning_effort="high", verbosity="high")
    
    def to_request_params(self) -> Dict[str, Any]:
        """Convert to parameters for OpenAI request body"""
        params = {}
        if self.reasoning_effort is not None:
            params["reasoning_effort"] = self.reasoning_effort
        if self.verbosity is not None:
            params["verbosity"] = self.verbosity
        return params


class BatchRequestItem(BaseModel):
    """Individual item in a batch request with GPT-5 support"""
    
    custom_id: str = Field(description="Unique identifier for this request item")
    method: str = Field(default="POST", description="HTTP method")
    url: str = Field(default="/v1/chat/completions", description="API endpoint")
    body: Dict[str, Any] = Field(description="Request body containing model, messages, etc.")
    
    @classmethod
    def create_chat_completion(
        cls,
        custom_id: str,
        model: str,
        messages: List[Dict[str, Any]],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        gpt5_settings: Optional[GPT5Settings] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> "BatchRequestItem":
        """Create a chat completion batch request item with GPT-5 support"""
        
        body = {
            "model": model,
            "messages": messages,
        }
        
        # Add optional parameters
        if max_tokens is not None:
            body["max_completion_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if tools is not None:
            body["tools"] = tools
        
        # Add GPT-5 specific parameters
        if gpt5_settings is not None:
            body.update(gpt5_settings.to_request_params())
        
        # Add any additional parameters
        body.update(kwargs)
        
        return cls(
            custom_id=custom_id,
            body=body
        )


class BatchFileUpload(BaseModel):
    """Response from uploading a batch file to OpenAI"""
    
    id: str = Field(description="File ID from OpenAI")
    object: str = Field(description="Object type, should be 'file'")
    bytes: int = Field(description="Size of uploaded file in bytes")
    created_at: int = Field(description="Unix timestamp of file creation")
    filename: str = Field(description="Name of uploaded file")
    purpose: str = Field(description="Purpose of file, should be 'batch'")


class BatchJob(BaseModel):
    """OpenAI Batch Job creation response"""
    
    id: str = Field(description="Batch job ID from OpenAI")
    object: str = Field(description="Object type, should be 'batch'")
    endpoint: str = Field(description="API endpoint used")
    errors: Optional[Dict[str, Any]] = Field(None, description="Any errors during batch creation")
    input_file_id: str = Field(description="ID of input file")
    completion_window: str = Field(description="Time window for completion")
    status: str = Field(description="Current status: validating, in_progress, finalizing, completed, failed, etc.")
    output_file_id: Optional[str] = Field(None, description="ID of output file when completed")
    error_file_id: Optional[str] = Field(None, description="ID of error file if errors occurred")
    created_at: int = Field(description="Unix timestamp of batch creation")
    in_progress_at: Optional[int] = Field(None, description="Unix timestamp when processing started")
    expires_at: Optional[int] = Field(None, description="Unix timestamp when batch expires")
    finalizing_at: Optional[int] = Field(None, description="Unix timestamp when finalizing started")
    completed_at: Optional[int] = Field(None, description="Unix timestamp when completed")
    failed_at: Optional[int] = Field(None, description="Unix timestamp when failed")
    expired_at: Optional[int] = Field(None, description="Unix timestamp when expired")
    cancelling_at: Optional[int] = Field(None, description="Unix timestamp when cancellation started")
    cancelled_at: Optional[int] = Field(None, description="Unix timestamp when cancelled")
    request_counts: Optional[Dict[str, int]] = Field(None, description="Count of requests by status")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Custom metadata")


class BatchRequestResponse(BaseModel):
    """Complete response from creating a batch request with OpenAI"""
    
    # Request metadata
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Our internal request ID")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When this request was created")
    model: str = Field(description="Model used (e.g., gpt-5, gpt-5-mini)")
    
    # Batch configuration
    batch_size: int = Field(description="Number of items in the batch")
    use_reasoning_effort: Optional[str] = Field(None, description="Reasoning effort level if GPT-5")
    use_verbosity: Optional[str] = Field(None, description="Verbosity level if GPT-5")
    
    # File upload response
    file_upload: BatchFileUpload = Field(description="Response from file upload")
    
    # Batch job response
    batch_job: BatchJob = Field(description="Response from batch job creation")
    
    # Request items for reference
    request_items: List[BatchRequestItem] = Field(description="All items that were submitted")
    
    # P8FS specific metadata
    tenant_id: str = Field(description="P8FS tenant ID")
    user_ids: List[str] = Field(description="User IDs processed in this batch")
    job_type: str = Field(default="dream_analysis", description="Type of analysis job")
    
    # Status tracking
    local_status: str = Field(default="submitted", description="Our local tracking status")
    last_checked_at: Optional[datetime] = Field(None, description="Last time we checked status")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")


class BatchResultItem(BaseModel):
    """Individual result item from a completed batch"""
    
    id: str = Field(description="Result ID")
    custom_id: str = Field(description="Custom ID from original request")
    response: Optional[Dict[str, Any]] = Field(None, description="API response")
    error: Optional[Dict[str, Any]] = Field(None, description="Error details if failed")


class BatchResults(BaseModel):
    """Complete results from a processed batch job"""
    
    batch_id: str = Field(description="Original batch job ID")
    request_id: str = Field(description="Our internal request ID")
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Results data
    results: List[BatchResultItem] = Field(description="Individual results")
    total_results: int = Field(description="Total number of results")
    successful_results: int = Field(description="Number of successful results")
    failed_results: int = Field(description="Number of failed results")
    
    # Token usage summary
    total_prompt_tokens: int = Field(default=0, description="Total input tokens used")
    total_completion_tokens: int = Field(default=0, description="Total output tokens generated")
    total_tokens: int = Field(default=0, description="Total tokens used")
    
    # Cost estimation (if available)
    estimated_cost: Optional[float] = Field(None, description="Estimated cost in USD")


class P8FSBatchJobRecord(BaseModel):
    """P8FS internal record of submitted batch jobs for tracking"""
    
    # Identifiers
    p8fs_job_id: str = Field(description="Our internal job ID")
    openai_batch_id: str = Field(description="OpenAI batch job ID")
    openai_file_id: str = Field(description="OpenAI input file ID")
    
    # Metadata
    tenant_id: str = Field(description="P8FS tenant")
    model: str = Field(description="Model used")
    job_type: str = Field(description="Type of job")
    user_count: int = Field(description="Number of users processed")
    request_count: int = Field(description="Number of individual requests")
    
    # Timestamps
    submitted_at: datetime = Field(description="When submitted to OpenAI")
    last_status_check: Optional[datetime] = Field(None, description="Last status check")
    completed_at: Optional[datetime] = Field(None, description="When completed")
    
    # Status
    status: str = Field(description="Current status")
    progress_percentage: Optional[float] = Field(None, description="Progress if available")
    
    # Configuration
    lookback_hours: int = Field(description="Hours of user data analyzed")
    analysis_type: str = Field(description="Type of analysis performed")
    
    # Results
    output_file_id: Optional[str] = Field(None, description="OpenAI output file ID when done")
    results_saved: bool = Field(default=False, description="Whether results were saved to P8FS")
    insights_count: Optional[int] = Field(None, description="Number of insights extracted")
    
    # Error handling
    error_details: Optional[Dict[str, Any]] = Field(None, description="Error information if failed")
    retry_count: int = Field(default=0, description="Number of retries attempted")
    
    
class BatchJobSubmission(BaseModel):
    """Record of a batch job submission for saving to root directory"""
    
    submission_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Test configuration
    test_name: str = Field(description="Name of the test that created this")
    model: str = Field(description="GPT model used")
    
    # Batch details
    batch_request: BatchRequestResponse = Field(description="Complete batch request response")
    
    # For future checking
    check_instructions: Dict[str, Any] = Field(
        default_factory=lambda: {
            "how_to_check": "Use OpenAI API to check batch status",
            "api_endpoint": "https://api.openai.com/v1/batches/{batch_id}",
            "expected_completion": "24-48 hours",
            "results_endpoint": "https://api.openai.com/v1/files/{output_file_id}/content"
        },
        description="Instructions for checking this batch job later"
    )


class BatchResponse(BaseModel):
    """
    Standard response model for batch operations in MemoryProxy.
    
    This provides a consistent interface for batch processing results,
    whether using OpenAI Batch API or sequential processing.
    """
    
    # Batch identification
    batch_id: str = Field(description="Unique batch identifier")
    batch_type: Literal["openai_batch_api", "sequential"] = Field(
        description="Type of batch processing used"
    )
    
    # Status information
    status: str = Field(description="Current status of the batch")
    questions_count: int = Field(description="Number of questions in the batch")
    
    # OpenAI Batch API specific (optional)
    openai_batch_id: Optional[str] = Field(None, description="OpenAI batch job ID if using Batch API")
    openai_file_id: Optional[str] = Field(None, description="OpenAI file ID for batch input")
    estimated_completion: Optional[str] = Field(None, description="Estimated completion time")
    cost_savings: Optional[str] = Field(None, description="Estimated cost savings percentage")
    
    # Sequential processing specific (optional)
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Results from sequential processing")
    errors: Optional[List[Dict[str, Any]]] = Field(None, description="Errors from sequential processing")
    results_count: Optional[int] = Field(None, description="Number of successful results")
    errors_count: Optional[int] = Field(None, description="Number of errors")
    
    # Job tracking (optional)
    job_id: Optional[str] = Field(None, description="P8FS Job ID if job tracking is enabled")
    
    # Timestamps
    submitted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the batch was submitted"
    )
    
    @model_validator(mode="after")
    def validate_response_type(self):
        """Ensure response has appropriate fields based on batch type"""
        if self.batch_type == "openai_batch_api":
            if not self.openai_batch_id:
                raise ValueError("OpenAI batch API response must include openai_batch_id")
        elif self.batch_type == "sequential":
            if self.results is None or self.errors is None:
                raise ValueError("Sequential batch response must include results and errors")
        return self
    
    def is_complete(self) -> bool:
        """Check if batch processing is complete"""
        if self.batch_type == "sequential":
            return True  # Sequential is always complete when returned
        return self.status in ["completed", "failed", "cancelled"]
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the batch results"""
        summary = {
            "batch_id": self.batch_id,
            "type": self.batch_type,
            "status": self.status,
            "questions_count": self.questions_count,
            "is_complete": self.is_complete()
        }
        
        if self.batch_type == "openai_batch_api":
            summary.update({
                "openai_batch_id": self.openai_batch_id,
                "estimated_completion": self.estimated_completion,
                "cost_savings": self.cost_savings
            })
        else:
            summary.update({
                "results_count": self.results_count or len(self.results or []),
                "errors_count": self.errors_count or len(self.errors or []),
                "success_rate": (
                    (self.results_count or 0) / self.questions_count * 100
                    if self.questions_count > 0 else 0
                )
            })
        
        if self.job_id:
            summary["job_id"] = self.job_id
            
        return summary


class JobStatusResponse(BaseModel):
    """
    Comprehensive job status response that combines local job info with OpenAI batch details.
    
    Used by MemoryProxy.get_job() to provide unified job status information.
    """
    
    # Local job information
    job_id: str = Field(description="P8FS internal job ID")
    tenant_id: str = Field(description="Tenant identifier")
    status: str = Field(description="Current job status")
    job_type: str = Field(description="Type of job")
    
    # Progress information
    is_complete: bool = Field(description="Whether job is in terminal state")
    is_running: bool = Field(description="Whether job is currently running")
    progress_percentage: Optional[float] = Field(None, description="Progress percentage if available")
    
    # Timestamps
    created_at: Optional[datetime] = Field(None, description="Job creation time")
    started_at: Optional[datetime] = Field(None, description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    
    # Batch-specific information
    is_batch: bool = Field(default=False, description="Whether this is a batch job")
    batch_size: Optional[int] = Field(None, description="Size of batch if applicable")
    items_processed: Optional[int] = Field(None, description="Number of items processed")
    
    # OpenAI batch information (if applicable)
    openai_batch_id: Optional[str] = Field(None, description="OpenAI batch job ID")
    openai_batch_status: Optional[str] = Field(None, description="OpenAI batch status")
    openai_request_counts: Optional[Dict[str, int]] = Field(None, description="OpenAI request counts by status")
    openai_output_file_id: Optional[str] = Field(None, description="OpenAI output file ID when completed")
    openai_error_file_id: Optional[str] = Field(None, description="OpenAI error file ID if errors occurred")
    
    # Results (if requested and available)
    results: Optional[List[Dict[str, Any]]] = Field(None, description="Job results if fetched")
    error_details: Optional[Dict[str, Any]] = Field(None, description="Error details if job failed")
    
    # Metadata
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional job metadata")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a concise summary of job status"""
        summary = {
            "job_id": self.job_id,
            "status": self.status,
            "is_complete": self.is_complete,
            "progress_percentage": self.progress_percentage,
        }
        
        if self.is_batch and self.openai_batch_id:
            summary.update({
                "openai_batch_id": self.openai_batch_id,
                "openai_status": self.openai_batch_status,
            })
        
        if self.results:
            summary["results_count"] = len(self.results)
            
        return summary
    
    def has_openai_batch(self) -> bool:
        """Check if this job has an associated OpenAI batch"""
        return self.openai_batch_id is not None
    
    def is_openai_batch_complete(self) -> bool:
        """Check if OpenAI batch is complete"""
        if not self.openai_batch_id:
            return False
        return self.openai_batch_status in ["completed", "failed", "cancelled"]