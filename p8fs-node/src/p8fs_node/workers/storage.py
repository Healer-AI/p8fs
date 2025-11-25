"""Storage worker for saving processed content to p8fs storage."""

import hashlib
import logging
import mimetypes
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid4, uuid5

from p8fs_node.models.content import ContentChunk, ContentProcessingResult

logger = logging.getLogger(__name__)


class StorageWorker:
    """Worker for saving processed content chunks to p8fs storage."""
    
    def __init__(self, tenant_id: str = None):
        """Initialize the storage worker."""
        from p8fs_cluster.config.settings import config
        self.tenant_id = tenant_id or config.default_tenant_id
        self.files_repo = None
        self.resources_repo = None
        self._initialize_repositories()
    
    def _initialize_repositories(self):
        """Initialize connection to p8fs repositories."""
        try:
            # Import p8fs components
            from p8fs_cluster.config.settings import config
            from p8fs.models import Files, Resources
            from p8fs.repository.TenantRepository import TenantRepository
            
            logger.debug(f"Config storage_provider: {getattr(config, 'storage_provider', 'NOT_FOUND')}")
            
            # Initialize repositories for Files and Resources models
            self.files_repo = TenantRepository(Files, tenant_id=self.tenant_id)
            self.resources_repo = TenantRepository(Resources, tenant_id=self.tenant_id)
            
            logger.info(f"Initialized connection to p8fs storage for tenant: {self.tenant_id}")
            
        except ImportError as e:
            logger.warning(f"p8fs not available, storage disabled: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize storage repositories: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
    
    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        hash_sha256 = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.warning(f"Could not calculate hash for {file_path}: {e}")
            return str(uuid4())  # Fallback to random UUID
    
    async def save_chunks_to_storage(
        self, 
        result: ContentProcessingResult,
        source_path: str | None = None
    ) -> dict[str, any]:
        """
        Register file and save content chunks to p8fs storage.
        
        Args:
            result: The processing result containing chunks and metadata
            source_path: Optional source file path
            
        Returns:
            Dict with file_id and list of resource IDs
        """
        if not self.files_repo or not self.resources_repo:
            logger.error("Storage repositories not initialized - chunks not saved")
            return {"file_id": None, "resource_ids": []}
        
        file_path = Path(source_path or result.metadata.file_path)
        saved_resource_ids = []
        
        try:
            # Step 1: Register the file in the files table
            file_id = str(uuid5(NAMESPACE_DNS, f"{self.tenant_id}:{file_path}"))
            mime_type, _ = mimetypes.guess_type(str(file_path))
            
            import json
            
            file_metadata = {
                "title": result.metadata.title,
                "author": result.metadata.author,
                "page_count": result.metadata.page_count,
                "word_count": result.metadata.word_count,
                "content_type": str(result.metadata.content_type),
                "extraction_method": result.metadata.extraction_method,
                "processed_at": result.metadata.processing_date.isoformat() if result.metadata.processing_date else None,
                "chunk_count": len(result.chunks)
            }
            
            file_data = {
                "uri": str(file_path),  # uri is the primary key, not id
                "file_size": result.metadata.file_size or 0,
                "mime_type": mime_type or "application/octet-stream",
                "content_hash": self._calculate_file_hash(file_path),
                "metadata": json.dumps(file_metadata)  # Serialize dict to JSON string
            }
            
            # Upsert file (will create or update)
            file_result = await self.files_repo.upsert(file_data)
            logger.info(f"Registered file with ID: {file_id}")
            
            # Step 2: Prepare all resources for batch upsert
            resource_batch = []
            for i, chunk in enumerate(result.chunks):
                resource_id = str(uuid5(NAMESPACE_DNS, f"{file_id}:chunk:{i}"))
                
                resource_metadata = {
                    "file_uri": str(file_path),  # Reference file by URI
                    "file_id": file_id,  # Keep synthetic ID for backward compatibility
                    "chunk_index": i,
                    "chunk_id": chunk.id,
                    "chunk_type": chunk.chunk_type,
                    "page_number": chunk.page_number,
                    "position": chunk.position,
                    "chunk_metadata": chunk.metadata,
                    "embedding": result.embeddings[i] if result.embeddings and i < len(result.embeddings) else None
                }
                
                resource_data = {
                    "id": resource_id,
                    "name": f"{result.metadata.title or 'Content'} - Chunk {i+1}",
                    "content": chunk.content,  # Only content field will have embeddings
                    "ordinal": i,
                    "uri": f"{file_id}#chunk-{i}",  # URI references the file
                    "metadata": json.dumps(resource_metadata)  # Serialize dict to JSON string
                }
                
                resource_batch.append(resource_data)
                saved_resource_ids.append(resource_id)
            
            # Batch upsert all resources at once
            if resource_batch:
                await self.resources_repo.upsert(resource_batch)
                logger.debug(f"Batch upserted {len(resource_batch)} resources")
            
            logger.info(f"Successfully saved file {file_id} and {len(saved_resource_ids)} chunks to storage")
            return {"file_id": file_id, "resource_ids": saved_resource_ids}
            
        except Exception as e:
            logger.error(f"Error saving to storage: {e}")
            return {"file_id": None, "resource_ids": saved_resource_ids}  # Return partial results
    
    async def save_chunk(
        self,
        chunk: ContentChunk,
        metadata: dict,
        embedding: list[float] | None = None
    ) -> str | None:
        """
        Save a single chunk to storage.
        
        Args:
            chunk: Content chunk to save
            metadata: Additional metadata
            embedding: Optional embedding vector
            
        Returns:
            Resource ID if successful, None otherwise
        """
        if not self.repository:
            logger.error("Storage repository not initialized")
            return None
        
        try:
            resource_data = {
                "content": chunk.content,
                "title": f"Content Chunk {chunk.chunk_id}",
                "chunk_id": chunk.chunk_id,
                "metadata": {
                    "chunk_metadata": chunk.metadata,
                    "additional_metadata": metadata,
                    "embedding": embedding
                }
            }
            
            resource_id = await self.repository.create_resource(resource_data)
            logger.debug(f"Saved single chunk with ID: {resource_id}")
            return resource_id
            
        except Exception as e:
            logger.error(f"Error saving single chunk: {e}")
            return None