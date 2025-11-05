"""OpenAI API client for batch processing and file operations.

Will refactor this in future but this is a convenience for things we just use open ai by default for and dont support other models
"""

from pathlib import Path
from typing import Any

import aiohttp


class OpenAIRequestsClient:
    """Client for OpenAI API requests, especially batch operations."""

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        """Initialize OpenAI client.

        Args:
            api_key: OpenAI API key
            base_url: Base URL for OpenAI API
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.session: aiohttp.ClientSession | None = None

    def _get_headers(self) -> dict[str, str]:
        """Get headers for API requests.

        Returns:
            Dictionary of HTTP headers
        """
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "p8fs/0.1.0",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session.

        Returns:
            aiohttp ClientSession
        """
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

    async def retrieve_batch(self, batch_id: str) -> dict[str, Any]:
        """Retrieve batch status and information.

        Args:
            batch_id: OpenAI batch identifier

        Returns:
            Batch information dictionary

        TODO: Implement actual API call
        """
        # Stub implementation
        return {
            "id": batch_id,
            "object": "batch",
            "endpoint": "/v1/chat/completions",
            "errors": None,
            "input_file_id": f"file-{batch_id}_input",
            "completion_window": "24h",
            "status": "in_progress",
            "output_file_id": None,
            "error_file_id": None,
            "created_at": 1234567890,
            "in_progress_at": 1234567891,
            "expires_at": 1234654290,
            "finalizing_at": None,
            "completed_at": None,
            "failed_at": None,
            "expired_at": None,
            "cancelling_at": None,
            "cancelled_at": None,
            "request_counts": {"total": 100, "completed": 45, "failed": 0},
            "metadata": {},
        }

    async def download_file(self, file_id: str) -> str:
        """Download file content from OpenAI.

        Args:
            file_id: OpenAI file identifier

        Returns:
            File content as string

        TODO: Implement actual file download
        """
        # Stub implementation
        return f"File content for {file_id} (stub implementation)\n"

    async def create_batch(
        self,
        input_file_id: str,
        endpoint: str = "/v1/chat/completions",
        completion_window: str = "24h",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new batch job.

        Args:
            input_file_id: ID of uploaded input file
            endpoint: API endpoint for batch processing
            completion_window: Time window for completion
            metadata: Optional metadata for the batch

        Returns:
            Created batch information

        TODO: Implement actual batch creation
        """
        batch_id = f"batch_{'0' * 24}"  # Placeholder batch ID

        return {
            "id": batch_id,
            "object": "batch",
            "endpoint": endpoint,
            "errors": None,
            "input_file_id": input_file_id,
            "completion_window": completion_window,
            "status": "validating",
            "output_file_id": None,
            "error_file_id": None,
            "created_at": 1234567890,
            "in_progress_at": None,
            "expires_at": 1234654290,
            "finalizing_at": None,
            "completed_at": None,
            "failed_at": None,
            "expired_at": None,
            "cancelling_at": None,
            "cancelled_at": None,
            "request_counts": {"total": 0, "completed": 0, "failed": 0},
            "metadata": metadata or {},
        }

    async def upload_file(
        self, file_path: str, purpose: str = "batch"
    ) -> dict[str, Any]:
        """Upload file to OpenAI.

        Args:
            file_path: Path to file to upload
            purpose: Purpose of the file upload

        Returns:
            Uploaded file information

        TODO: Implement actual file upload
        """
        file_path_obj = Path(file_path)

        return {
            "id": f"file-{'0' * 24}",
            "object": "file",
            "bytes": file_path_obj.stat().st_size if file_path_obj.exists() else 1024,
            "created_at": 1234567890,
            "filename": file_path_obj.name,
            "purpose": purpose,
            "status": "processed",
            "status_details": None,
        }

    async def list_files(self, purpose: str | None = None) -> dict[str, Any]:
        """List files in OpenAI storage.

        Args:
            purpose: Optional purpose filter

        Returns:
            List of files

        TODO: Implement actual file listing
        """
        return {
            "object": "list",
            "data": [
                {
                    "id": "file-example1",
                    "object": "file",
                    "bytes": 1024,
                    "created_at": 1234567890,
                    "filename": "example1.jsonl",
                    "purpose": "batch",
                },
                {
                    "id": "file-example2",
                    "object": "file",
                    "bytes": 2048,
                    "created_at": 1234567900,
                    "filename": "example2.jsonl",
                    "purpose": "batch",
                },
            ],
        }

    async def delete_file(self, file_id: str) -> dict[str, Any]:
        """Delete file from OpenAI storage.

        Args:
            file_id: OpenAI file identifier

        Returns:
            Deletion confirmation

        TODO: Implement actual file deletion
        """
        return {"id": file_id, "object": "file", "deleted": True}

    async def cancel_batch(self, batch_id: str) -> dict[str, Any]:
        """Cancel a running batch job.

        Args:
            batch_id: OpenAI batch identifier

        Returns:
            Updated batch information

        TODO: Implement actual batch cancellation
        """
        return {
            "id": batch_id,
            "object": "batch",
            "endpoint": "/v1/chat/completions",
            "errors": None,
            "input_file_id": f"file-{batch_id}_input",
            "completion_window": "24h",
            "status": "cancelling",
            "output_file_id": None,
            "error_file_id": None,
            "created_at": 1234567890,
            "in_progress_at": 1234567891,
            "expires_at": 1234654290,
            "finalizing_at": None,
            "completed_at": None,
            "failed_at": None,
            "expired_at": None,
            "cancelling_at": 1234568000,
            "cancelled_at": None,
            "request_counts": {"total": 100, "completed": 45, "failed": 0},
            "metadata": {},
        }

    async def list_batches(self, limit: int = 20) -> dict[str, Any]:
        """List batch jobs.

        Args:
            limit: Maximum number of batches to return

        Returns:
            List of batches

        TODO: Implement actual batch listing
        """
        return {
            "object": "list",
            "data": [
                {
                    "id": "batch_example1",
                    "object": "batch",
                    "endpoint": "/v1/chat/completions",
                    "status": "completed",
                    "created_at": 1234567890,
                    "request_counts": {"total": 50, "completed": 50, "failed": 0},
                },
                {
                    "id": "batch_example2",
                    "object": "batch",
                    "endpoint": "/v1/chat/completions",
                    "status": "in_progress",
                    "created_at": 1234567900,
                    "request_counts": {"total": 100, "completed": 25, "failed": 0},
                },
            ],
            "first_id": "batch_example1",
            "last_id": "batch_example2",
            "has_more": False,
        }

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
