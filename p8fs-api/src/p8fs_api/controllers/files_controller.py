"""Files controller for listing resources with pagination."""

from typing import Any

from p8fs.queries.files import build_list_files_query
from p8fs.providers import get_provider
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)


class FilesController:
    """Controller for file listing operations."""

    def __init__(self):
        """Initialize files controller with configured provider."""
        self.provider = get_provider()

    async def list_files(
        self,
        tenant_id: str | None = None,
        encryption_key_owner: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """List files with pagination and filtering.

        Args:
            tenant_id: Optional tenant ID filter
            encryption_key_owner: Optional encryption mode (USER, SYSTEM, NONE)
            start_date: Optional start date (ISO format)
            end_date: Optional end date (ISO format)
            page: Page number (1-indexed)
            page_size: Results per page (max 200)

        Returns:
            Dictionary with files, total count, and pagination info
        """
        # Determine dialect based on provider
        dialect = self.provider.get_dialect_name()

        # Build query
        query, params = build_list_files_query(
            dialect=dialect,
            tenant_id=tenant_id,
            encryption_key_owner=encryption_key_owner,
            start_date=start_date,
            end_date=end_date,
            page=page,
            page_size=page_size,
        )

        logger.debug(
            "Listing files",
            tenant_id=tenant_id,
            encryption_key_owner=encryption_key_owner,
            page=page,
            page_size=page_size,
        )

        # Execute query
        results = self.provider.execute(query, params)

        # Extract total count and files
        total_count = results[0]["total_count"] if results else 0
        files = [
            {
                "id": row["id"],
                "uri": row["uri"],
                "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
                "updated_at": row["updated_at"].isoformat() if row.get("updated_at") and hasattr(row["updated_at"], "isoformat") else (str(row["updated_at"]) if row.get("updated_at") else None),
                "tenant_id": row["tenant_id"],
                "encryption_key_owner": row["encryption_key_owner"],
            }
            for row in results
        ]

        return {
            "files": files,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if total_count > 0 else 0,
        }
