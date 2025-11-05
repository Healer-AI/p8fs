"""Storage worker implementation for saving content chunks to database.

This module provides functionality to save processed content chunks from p8fs_node
to the p8fs database storage using the repository pattern.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import NAMESPACE_DNS, uuid4, uuid5

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

from p8fs.models.p8 import Files, Resources
from p8fs.repository import BaseRepository

logger = get_logger(__name__)


class StorageWorker:
    """Worker for processing and storing content chunks in the database."""

    def __init__(self, tenant_id: str = None):
        """Initialize storage worker with tenant context.
        
        Args:
            tenant_id: The tenant ID for data isolation. Defaults to config default.
        """
        self.tenant_id = tenant_id or config.default_tenant_id
        self._files_repo: Optional[BaseRepository] = None
        self._resources_repo: Optional[BaseRepository] = None

    @property
    def files_repo(self) -> BaseRepository:
        """Lazy initialization of Files repository."""
        if not self._files_repo:
            from p8fs.repository import TenantRepository
            self._files_repo = TenantRepository(Files, tenant_id=self.tenant_id)
        return self._files_repo

    @property
    def resources_repo(self) -> BaseRepository:
        """Lazy initialization of Resources repository."""
        if not self._resources_repo:
            from p8fs.repository import TenantRepository
            self._resources_repo = TenantRepository(Resources, tenant_id=self.tenant_id)
        return self._resources_repo

    async def save_chunks_to_storage(
        self, 
        processing_result: Any,
        file_path: str,
        embeddings: list[list[float]] = None  # Kept for compatibility but not used
    ) -> dict[str, Any]:
        """Save processed content chunks to storage.
        
        This method takes a ContentProcessingResult from p8fs_node and saves:
        1. File metadata to the files table
        2. Individual chunks as resources in the resources table
        3. Optional embeddings if provided
        
        Args:
            processing_result: ContentProcessingResult from p8fs_node processing
            file_path: Original file path
            embeddings: Optional list of embedding vectors for chunks
            
        Returns:
            Dictionary with file_id and list of resource_ids created
        """
        try:
            # Extract data from processing result
            chunks = processing_result.chunks
            metadata = processing_result.metadata
            
            # Use the file path as the URI (primary key for Files)
            file_uri = file_path
            
            # Generate file ID for reference in resources
            file_id = str(uuid5(NAMESPACE_DNS, f"{self.tenant_id}:{file_uri}"))
            
            # Create file entry (Files model uses uri as primary key, not id)
            file_data = {
                "tenant_id": self.tenant_id,
                "uri": file_uri,
                "file_size": metadata.file_size if hasattr(metadata, 'file_size') else 0,
                "mime_type": metadata.mime_type if hasattr(metadata, 'mime_type') else None,
                "content_hash": metadata.content_hash if hasattr(metadata, 'content_hash') else None,
                "upload_timestamp": datetime.now(timezone.utc),
                "metadata": {
                    "title": metadata.title if hasattr(metadata, 'title') else Path(file_path).stem,
                    "content_type": str(metadata.content_type) if hasattr(metadata, 'content_type') else "unknown",
                    "word_count": metadata.word_count if hasattr(metadata, 'word_count') else None,
                    "extraction_method": metadata.extraction_method if hasattr(metadata, 'extraction_method') else None,
                    "properties": metadata.properties if hasattr(metadata, 'properties') else {}
                }
            }
            
            # Upsert file record
            await self.files_repo.upsert(file_data)
            logger.info(f"Created/updated file record: {file_id}")
            
            # Process chunks
            resource_ids = []
            resources_data = []
            
            for i, chunk in enumerate(chunks):
                # Generate unique resource ID based on uri + ordinal + tenant
                # This ensures each chunk has a unique ID even in batch operations
                chunk_uri = f"{file_path}#chunk_{i}"
                resource_id = str(uuid5(NAMESPACE_DNS, f"{self.tenant_id}:{chunk_uri}:{i}"))
                resource_ids.append(resource_id)
                
                # Prepare resource data using Resources model fields
                resource_data = {
                    "id": resource_id,
                    "tenant_id": self.tenant_id,
                    "name": f"{Path(file_path).stem}_chunk_{i}",
                    "category": "content_chunk",
                    "content": chunk.content if hasattr(chunk, 'content') else str(chunk),
                    "summary": None,  # Could be generated later
                    "ordinal": i,
                    "uri": chunk_uri,
                    "metadata": {
                        "file_id": file_id,
                        "chunk_index": i,
                        "chunk_type": chunk.chunk_type if hasattr(chunk, 'chunk_type') else "text",
                        "position": chunk.position if hasattr(chunk, 'position') else i,
                        "chunk_metadata": chunk.metadata if hasattr(chunk, 'metadata') else {}
                    },
                    "resource_timestamp": datetime.now(timezone.utc),
                    "userid": None  # Could be set if user context is available
                }
                
                # Create Resources instance to validate fields
                from p8fs.models.p8 import Resources
                resource = Resources(**resource_data)
                resources_data.append(resource)
            
            # Batch upsert all resources
            if resources_data:
                # Use upsert to handle both create and update cases
                await self.resources_repo.upsert(resources_data)
                logger.info(f"Upserted {len(resources_data)} resources")
            
            # Return summary
            return {
                "success": True,
                "file_id": file_id,
                "resource_ids": resource_ids,
                "chunks_saved": len(chunks),
                "embeddings_saved": len(embeddings) if embeddings else 0,
                "file_uri": file_path,
                "tenant_id": self.tenant_id
            }
            
        except Exception as e:
            logger.error(f"Failed to save chunks to storage: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "file_id": None,
                "resource_ids": []
            }

    async def get_file_chunks(self, file_id: str) -> list[dict[str, Any]]:
        """Retrieve all chunks for a given file.
        
        Args:
            file_id: The file ID to retrieve chunks for
            
        Returns:
            List of resource dictionaries representing chunks
        """
        try:
            # Query resources by file_id in metadata
            resources = await self.resources_repo.select(
                filters={"metadata": {"file_id": file_id}},
                order_by=["ordinal"]
            )
            
            return [
                r.model_dump() if hasattr(r, 'model_dump') else dict(r)
                for r in resources
            ]
            
        except Exception as e:
            logger.error(f"Failed to retrieve chunks for file {file_id}: {e}")
            return []

    async def delete_file_and_chunks(self, file_id: str) -> dict[str, Any]:
        """Delete a file and all its associated chunks.
        
        Args:
            file_id: The file ID to delete
            
        Returns:
            Dictionary with deletion results
        """
        try:
            # First delete all associated resources
            resources = await self.get_file_chunks(file_id)
            deleted_resources = 0
            
            for resource in resources:
                await self.resources_repo.delete(resource['id'])
                deleted_resources += 1
            
            # Then delete the file
            await self.files_repo.delete(file_id)
            
            logger.info(f"Deleted file {file_id} and {deleted_resources} chunks")
            
            return {
                "success": True,
                "file_id": file_id,
                "deleted_resources": deleted_resources
            }
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_id": file_id,
                "deleted_resources": 0
            }