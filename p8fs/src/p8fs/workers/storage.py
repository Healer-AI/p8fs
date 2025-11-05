"""Storage worker for processing files from queue or direct file paths."""

import asyncio
import json
import time
import yaml
from pathlib import Path
from typing import Optional
from uuid import NAMESPACE_DNS, uuid5

import typer
from nats.aio.client import Client as NATS
from nats.js.client import JetStreamContext
from p8fs_cluster.config import config
from p8fs_cluster.logging import get_logger
from pydantic import BaseModel

from p8fs.repository import TenantRepository
from p8fs.workers.processors import ProcessorRegistry

logger = get_logger(__name__)

# Optional import of p8fs-node for content processing
try:
    from p8fs_node.providers import get_content_provider, auto_register
    # Auto-register content providers
    auto_register()
    HAS_P8FS_NODE = True
except ImportError:
    logger.warning("p8fs-node not installed - content processing features will be disabled")
    HAS_P8FS_NODE = False
    get_content_provider = None
app = typer.Typer(help="Storage worker for processing files")


class StorageEvent(BaseModel):
    """Event from storage system."""
    tenant_id: str
    file_path: str
    operation: str  # create, update, delete
    size: int
    mime_type: str | None = None
    s3_key: str | None = None


class StorageWorker:
    """Processes files and indexes content."""
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.nc: NATS | None = None
        self.js: JetStreamContext | None = None
        # Initialize repositories for Files and Resources
        from p8fs.models.p8 import Files, Resources
        self.files_repo = TenantRepository(Files, tenant_id=tenant_id)
        self.resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
        self.processor_registry = ProcessorRegistry(self.resources_repo)
    
    async def connect_nats(self):
        """Connect to NATS JetStream."""
        try:
            self.nc = NATS()
            await self.nc.connect(servers=[config.nats_url])
            self.js = self.nc.jetstream()
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise
    
    async def delete_file(self, file_id: str):
        """Delete a file and its associated resources."""
        try:
            # First delete all resources associated with this file
            # Get all resources and filter by file_id in Python
            # (JSONB queries need special handling)
            all_resources = await self.resources_repo.select(limit=1000)
            resources = [r for r in all_resources if r.metadata and r.metadata.get("file_id") == file_id]
            
            # Delete each resource
            for resource in resources:
                await self.resources_repo.delete(resource.id)
            
            # Then delete the file itself
            await self.files_repo.delete(file_id)
            
            logger.info(f"Deleted file {file_id} and {len(resources)} associated resources")
            
        except Exception as e:
            logger.error(f"Error deleting file {file_id}: {e}")
            raise

    async def process_file(self, file_path: str, tenant_id: str, s3_key: str | None = None):
        """Process a single file.

        Args:
            file_path: Relative file path (e.g., "uploads/2025/10/11/file.pdf")
            tenant_id: Tenant ID
            s3_key: Full S3 path (e.g., "/buckets/tenant-test/uploads/2025/10/11/file.pdf")
        """
        import time
        import tempfile
        from datetime import datetime, timezone
        start_time = time.time()

        # Download file from S3 if s3_key is provided
        temp_file = None
        try:
            if s3_key:
                # Download from S3 (S3 service handles path normalization)
                from p8fs.services.s3_storage import S3StorageService
                s3 = S3StorageService()

                logger.info(f"Downloading file from S3: {s3_key}")
                download_result = await s3.download_file(s3_key, tenant_id)

                if not download_result:
                    raise FileNotFoundError(f"File not found in S3: {s3_key}")

                logger.debug(f"Download result: {download_result['size_bytes']:,} bytes")

                # Save to temp file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file_path).suffix)
                temp_file.write(download_result['content'])
                temp_file.flush()  # Ensure data is written
                temp_file.close()

                path = Path(temp_file.name)
                logger.info(f"Downloaded to temp file: {path} ({path.stat().st_size} bytes)")
            else:
                # Use local file path
                path = Path(file_path)

            # Get file metadata
            file_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{file_path}"))

            # Get file timestamps
            file_stat = path.stat()
            file_mtime = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)
            file_ctime = datetime.fromtimestamp(file_stat.st_ctime, tz=timezone.utc)
            # Use modification time as primary timestamp, creation time as fallback
            file_timestamp = file_mtime
            
            logger.info(f"Processing: {path.name} ({file_stat.st_size / 1024 / 1024:.1f} MB) from {file_timestamp.isoformat()}")
            
            # Create file entry
            await self.files_repo.upsert({
                "id": file_id,
                "tenant_id": tenant_id,
                "uri": s3_key if s3_key else str(path),  # Use S3 key for S3 files, local path otherwise
                "file_size": path.stat().st_size if path.exists() else 0,
                "mime_type": None,  # Could be determined from file
                "metadata": {
                    "name": path.name,
                    "s3_key": s3_key
                }
            })
            
            # Check if it's a YAML/JSON file that might be an Engram
            if path.suffix.lower() in ['.yaml', '.yml', '.json']:
                try:
                    # Read file content
                    if path.exists():
                        content = path.read_text()
                    else:
                        # For S3 files, would need to fetch from S3 here
                        logger.warning(f"Cannot read file content for {file_path}")
                        content = None
                    
                    if content:
                        # Determine content type for document processor
                        content_type = "application/x-yaml" if path.suffix.lower() in ['.yaml', '.yml'] else "application/json"
                        
                        # Process using delegation system
                        result = await self.processor_registry.process_document(content, content_type, tenant_id)
                        
                        processor_used = result.get("processor_used", "unknown")
                        logger.info(f"Processed {processor_used} document: {file_path}")
                        
                        # Log results based on processor type
                        if processor_used == "engram" and "engram_id" in result:
                            logger.info(f"Engram ID: {result['engram_id']}")
                            if result.get("upserts", 0) > 0:
                                logger.info(f"Created {result['upserts']} entities")
                            if result.get("patches", 0) > 0:
                                logger.info(f"Applied {result['patches']} patches")
                            if result.get("associations", 0) > 0:
                                logger.info(f"Created {result['associations']} associations")
                        elif processor_used == "generic" and "resource_id" in result:
                            logger.info(f"Resource ID: {result['resource_id']}")
                        
                        return  # Skip regular processing for JSON/YAML documents
                        
                except Exception as e:
                    logger.warning(f"Failed to process {file_path} as Engram: {e}, falling back to regular processing")
            
            # Extract content using content providers
            try:
                if not HAS_P8FS_NODE:
                    logger.error(f"Cannot process {file_path} - p8fs-node is not installed")
                    return
                    
                extraction_start = time.time()
                logger.debug(f"Getting content provider for {path}")
                provider = get_content_provider(str(path))
                logger.debug(f"Got provider: {provider}")
                
                # Log provider type and check if it's audio
                provider_name = provider.__class__.__name__
                if "Audio" in provider_name:
                    logger.info(f"Using {provider_name} - will use OpenAI Whisper API")
                
                # Process the file through the provider's chunking method
                # Use 'path' which points to either the temp file (S3) or local file
                logger.debug(f"Processing {path} with provider")
                chunks = await provider.to_markdown_chunks(str(path))
                processing_time = time.time() - extraction_start
                logger.debug(f"Created {len(chunks)} chunks in {processing_time:.1f}s")
                    
                if len(chunks) == 0:
                    logger.warning(f"No chunks created for {file_path} - file may be empty or processing failed")
                else:
                    logger.debug(f"Processing {len(chunks)} chunks for storage")
                    
                resources_created = 0
                for i, chunk in enumerate(chunks):
                    resource_id = str(uuid5(NAMESPACE_DNS, f"{file_id}:chunk:{i}"))
                    logger.debug(f"Creating resource {i+1}/{len(chunks)}: {resource_id}")
                    await self.resources_repo.upsert({
                        "id": resource_id,
                        "tenant_id": tenant_id,
                        "name": f"{path.stem}_chunk_{i}",
                        "category": "content_chunk",
                        "content": chunk.content,  # Extract content from ContentChunk
                        "ordinal": i,
                        "uri": f"{file_path}#chunk_{i}",
                        "resource_timestamp": file_timestamp,  # Add file timestamp
                        "metadata": {
                            "file_id": file_id,
                            "chunk_index": i,
                            "chunk_type": chunk.chunk_type,
                            "file_mtime": file_mtime.isoformat(),
                            "file_ctime": file_ctime.isoformat(),
                            **chunk.metadata  # Include any chunk metadata
                        }
                    })
                    resources_created += 1
                
                logger.info(f"Successfully created {resources_created} content resources for {file_path}")
                
                # Log timing summary
                total_time = time.time() - start_time
                logger.info(f"Completed {path.name} in {total_time:.1f}s")
                
                if resources_created == 0:
                    logger.warning(f"WARNING: Zero resources created for {file_path} - this may indicate a processing issue")
            except ValueError as e:
                logger.warning(f"No content provider for {file_path}: {e}")
                # File entry was created, but no content chunks could be extracted
            
            # Only log simple completion if not already logged above
            if 'total_time' not in locals():
                total_time = time.time() - start_time
                logger.info(f"Processed file: {file_path} in {total_time:.1f}s")
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            raise
        finally:
            # Clean up temp file if it was created
            if temp_file and Path(temp_file.name).exists():
                import os
                os.unlink(temp_file.name)
                logger.debug(f"Cleaned up temp file: {temp_file.name}")
    
    async def process_queue(self):
        """Process files from NATS queue."""
        if not self.nc:
            await self.connect_nats()
        
        # Subscribe to storage events
        try:
            sub = await self.js.pull_subscribe("storage.events.*", "storage-worker")
        except Exception as e:
            logger.error(f"Failed to subscribe to queue: {e}")
            raise
        
        while True:
            try:
                msgs = await sub.fetch(batch=10, timeout=1)
                for msg in msgs:
                    event = StorageEvent.model_validate_json(msg.data)
                    
                    if event.operation in ["create", "update"]:
                        await self.process_file(
                            event.file_path,
                            event.tenant_id,
                            event.s3_key
                        )
                    elif event.operation == "delete":
                        # Remove file and resources
                        file_id = str(uuid5(NAMESPACE_DNS, f"{event.tenant_id}:{event.file_path}"))
                        await self.delete_file(file_id)
                    
                    await msg.ack()
                    
            except Exception as e:
                logger.error(f"Queue processing error: {e}")
                await asyncio.sleep(1)
    
    async def cleanup(self):
        """Clean up NATS connection."""
        if self.nc and not self.nc.is_closed:
            await self.nc.close()
    
    async def process_folder(self, folder_path: str, tenant_id: str, sync_mode: bool = False, limit: Optional[int] = None):
        """Process all files in a folder."""
        import os
        from datetime import datetime, timezone
        
        folder = Path(folder_path)
        if not folder.is_dir():
            raise ValueError(f"Not a directory: {folder_path}")
        
        # Get supported extensions from providers
        supported_extensions = {'.md', '.txt', '.rst', '.pdf', '.wav', '.mp3', '.m4a', 
                               '.docx', '.doc', '.odt', '.rtf', '.py', '.js', '.json', '.yaml'}
        
        # Collect files
        all_files = []
        for root, _, files in os.walk(folder):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in supported_extensions:
                    all_files.append(file_path)
        
        logger.info(f"Found {len(all_files)} supported files in {folder_path}")
        
        # Filter files based on sync mode
        files_to_process = []
        if sync_mode:
            # Check which files need processing
            for file_path in all_files:
                file_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{file_path}"))
                existing = await self.files_repo.select(filters={"id": file_id})
                
                if not existing:
                    files_to_process.append((file_path, "new"))
                else:
                    # Check modification time
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
                    if existing[0].created_at and file_mtime > existing[0].created_at:
                        files_to_process.append((file_path, "modified"))
        else:
            files_to_process = [(f, "process") for f in all_files]
        
        # Apply limit
        if limit and len(files_to_process) > limit:
            files_to_process = files_to_process[:limit]
        
        logger.info(f"Processing {len(files_to_process)} files")
        
        # Process files
        results = {"success": 0, "failed": 0, "files": []}
        total_start = time.time()
        
        for idx, (file_path, status) in enumerate(files_to_process, 1):
            logger.info(f"\n[{idx}/{len(files_to_process)}] Processing {file_path.name} ({status})")
            try:
                await self.process_file(str(file_path), tenant_id)
                results["success"] += 1
                results["files"].append({"path": str(file_path), "status": "success"})
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                results["failed"] += 1
                results["files"].append({"path": str(file_path), "status": "failed", "error": str(e)})
        
        total_time = time.time() - total_start
        logger.info(f"Folder processing complete in {total_time:.1f}s - Success: {results['success']}, Failed: {results['failed']}")
        
        return results


@app.command()
def process(
    file: str | None = typer.Option(None, help="Process a specific file"),
    queue: bool = typer.Option(False, help="Process from queue"),
    tenant_id: str = typer.Option(..., help="Tenant ID")
):
    """Process files either from a specific path or queue."""
    async def run():
        worker = StorageWorker(tenant_id)
        
        if file:
            await worker.process_file(file, tenant_id)
        elif queue:
            await worker.process_queue()
        else:
            typer.echo("Specify either --file or --queue")
            raise typer.Exit(1)
    
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Shutting down storage worker")


if __name__ == "__main__":
    app()