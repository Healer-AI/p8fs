"""Integration tests for StorageWorker with real database."""

import asyncio
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import pytest
from p8fs_cluster.config import config

from p8fs.models.p8 import Files, Resources
from p8fs.repository import TenantRepository
from p8fs.workers.storage import StorageWorker

# Optional import for p8fs-node content providers
try:
    from p8fs_node.providers import auto_register
    HAS_P8FS_NODE = True
except ImportError:
    HAS_P8FS_NODE = False
    auto_register = None


@pytest.mark.integration
@pytest.mark.skipif(not HAS_P8FS_NODE, reason="p8fs-node not installed (install with: uv sync --extra workers)")
async def test_storage_worker_processes_sample_md():
    """Test that storage worker processes Sample.md file and creates database entries."""
    # Auto-register all content providers
    auto_register()
    
    # Set up unique test tenant ID to avoid conflicts with old data
    import time
    tenant_id = f"test-storage-worker-{int(time.time())}"
    
    # Get path to Sample.md
    sample_file = Path(__file__).parent.parent.parent / "sample_data" / "content" / "Sample.md"
    assert sample_file.exists(), f"Sample file not found at {sample_file}"
    
    # Initialize worker
    worker = StorageWorker(tenant_id)
    
    # Process the file
    await worker.process_file(str(sample_file), tenant_id)
    
    # Initialize repositories to verify results
    files_repo = TenantRepository(Files, tenant_id=tenant_id)
    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    
    # Check that file was created in Files table
    file_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{sample_file}"))
    files = await files_repo.select(filters={"id": file_id})
    
    assert len(files) == 1, "File entry not found in Files table"
    file_entry = files[0]
    assert file_entry.uri == str(sample_file)
    assert file_entry.file_size > 0
    assert file_entry.metadata["name"] == "Sample.md"
    
    # Check that resources were created
    # Get all resources for this tenant and filter in Python
    all_resources = await resources_repo.select(limit=1000)
    resources = [r for r in all_resources if r.metadata and r.metadata.get("file_id") == file_id]
    
    assert len(resources) > 0, "No resources created for the file"
    
    # With semchunk, we expect exactly 3 chunks for the 403KB Sample.md
    assert len(resources) == 3, f"Expected 3 chunks with semchunk, got {len(resources)}"
    
    # Verify resource properties
    for i, resource in enumerate(resources):
        assert resource.category == "content_chunk"
        assert resource.content is not None and len(resource.content) > 0
        assert resource.ordinal == i
        assert resource.metadata["file_id"] == file_id
        assert resource.metadata["chunk_index"] == i
        assert resource.metadata.get("method") == "semchunk_500_words", "Chunk should be created with semchunk"
        assert resource.name == f"Sample_chunk_{i}"
    
    # Clean up
    await worker.delete_file(file_id)
    
    # Verify cleanup
    files_after = await files_repo.select(filters={"id": file_id})
    assert len(files_after) == 0, "File entry not deleted"
    
    all_resources_after = await resources_repo.select(limit=1000)
    resources_after = [r for r in all_resources_after if r.metadata and r.metadata.get("file_id") == file_id]
    assert len(resources_after) == 0, "Resources not deleted"





@pytest.mark.integration
@pytest.mark.skipif(not HAS_P8FS_NODE, reason="p8fs-node not installed (install with: uv sync --extra workers)")
async def test_storage_worker_with_s3_key():
    """Test that storage worker properly stores S3 key in metadata."""
    import time
    tenant_id = f"test-storage-worker-s3-{int(time.time())}"
    sample_file = Path(__file__).parent.parent.parent / "sample_data" / "content" / "Sample.md"
    s3_key = "s3://test-bucket/uploads/Sample.md"
    
    # Initialize worker
    worker = StorageWorker(tenant_id)
    
    # Process file with S3 key
    await worker.process_file(str(sample_file), tenant_id, s3_key)
    
    # Verify file metadata includes S3 key
    files_repo = TenantRepository(Files, tenant_id=tenant_id)
    file_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{sample_file}"))
    files = await files_repo.select(filters={"id": file_id})
    
    assert len(files) > 0
    assert files[0].metadata["s3_key"] == s3_key
    
    # Clean up
    await worker.delete_file(file_id)


@pytest.mark.integration
@pytest.mark.skipif(not HAS_P8FS_NODE, reason="p8fs-node not installed (install with: uv sync --extra workers)")
async def test_storage_worker_idempotent():
    """Test that processing the same file twice is idempotent."""
    import time
    tenant_id = f"test-storage-worker-idempotent-{int(time.time())}"
    sample_file = Path(__file__).parent.parent.parent / "sample_data" / "content" / "Sample.md"
    
    # Initialize worker
    worker = StorageWorker(tenant_id)
    
    # Process file twice
    await worker.process_file(str(sample_file), tenant_id)
    await worker.process_file(str(sample_file), tenant_id)
    
    # Check that we still have only one file entry
    files_repo = TenantRepository(Files, tenant_id=tenant_id)
    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    
    file_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:{sample_file}"))
    
    # Should have exactly one file entry
    all_files = await files_repo.select(filters={"id": file_id})
    assert len(all_files) == 1
    
    # Resources should not be duplicated
    all_resources = await resources_repo.select(limit=1000)
    resources = [r for r in all_resources if r.metadata and r.metadata.get("file_id") == file_id]
    
    # Count unique resource IDs
    resource_ids = {r.id for r in resources}
    assert len(resource_ids) == len(resources), "Duplicate resources found"
    
    # Clean up
    await worker.delete_file(file_id)


if __name__ == "__main__":
    asyncio.run(test_storage_worker_processes_sample_md())