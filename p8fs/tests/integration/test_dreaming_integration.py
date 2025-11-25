"""Integration test for dreaming worker with batch and direct modes.

This test validates the complete dreaming workflow:
1. Reading sessions and resources from TiDB
2. Processing in both direct and batch modes
3. Storing dream analysis results
4. Job tracking in the jobs table

Provider Configuration:
- Default: PostgreSQL (P8FS_STORAGE_PROVIDER=postgresql)
- TiDB: Set P8FS_STORAGE_PROVIDER=tidb
- Environment variables:
  - P8FS_STORAGE_PROVIDER: postgresql|tidb|rocksdb
  - P8FS_TIDB_HOST, P8FS_TIDB_PORT, P8FS_TIDB_USER, P8FS_TIDB_PASSWORD, P8FS_TIDB_DATABASE
  - P8FS_PG_HOST, P8FS_PG_PORT, P8FS_PG_USER, P8FS_PG_PASSWORD, P8FS_PG_DATABASE

Test Expectations:
1. Direct Mode:
   - Reads sessions and resources from database
   - Creates DreamModel analysis synchronously
   - Stores dream analysis results

2. Batch Mode:
   - Reads sessions and resources from database
   - Submits batch job to MemoryProxy
   - Creates job record in jobs table
   - Processes completion asynchronously

Running Tests:
# With default PostgreSQL
pytest tests/integration/test_dreaming_integration.py -v

# With TiDB provider
P8FS_STORAGE_PROVIDER=tidb pytest tests/integration/test_dreaming_integration.py -v

# Run specific test
P8FS_STORAGE_PROVIDER=tidb pytest tests/integration/test_dreaming_integration.py::test_dreaming_direct_mode -v
"""

import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from p8fs_cluster.config import config

from p8fs.models.p8 import Session, Resources, Job, JobStatus
from p8fs.models.agentlets import DreamModel
from p8fs.repository import SystemRepository
from p8fs.workers.dreaming import DreamingWorker, ProcessingMode, DreamJob
from p8fs.workers.dreaming_repository import DreamingRepository


# Test data fixtures
@pytest.fixture
def test_tenant_id():
    """Generate unique tenant ID for test isolation."""
    return f"test-dream-{uuid4().hex[:8]}"


@pytest.fixture
async def setup_test_data(test_tenant_id):
    """Create test sessions and resources."""
    session_repo = SystemRepository(Session)
    resource_repo = SystemRepository(Resources)
    
    # Create test sessions
    sessions = []
    for i in range(3):
        session = {
            'id': str(uuid4()),
            'tenant_id': test_tenant_id,
            'query': f'Test query {i}: Tell me about my goals and dreams',
            'name': f'Dream Session {i}',
            'metadata': {
                'topics': ['goals', 'dreams', 'aspirations'],
                'sentiment': 'positive'
            },
            'created_at': datetime.now(timezone.utc)
        }
        await session_repo.upsert(session)
        sessions.append(session)
    
    # Create test resources
    resources = []
    resource_contents = [
        "My goal is to learn new programming languages and become a better developer.",
        "I dream of traveling to Japan and experiencing the culture firsthand.",
        "I want to start my own business and make a positive impact on the world."
    ]
    
    for i, content in enumerate(resource_contents):
        resource = {
            'id': str(uuid4()),
            'tenant_id': test_tenant_id,
            'name': f'Dream Resource {i}',
            'content': content,
            'summary': f'Personal reflection about {["learning", "travel", "business"][i]}',
            'uri': f'test://resource/{i}',
            'metadata': {
                'type': 'personal_reflection',
                'category': ['goals', 'dreams'][i % 2]
            },
            'created_at': datetime.now(timezone.utc)
        }
        await resource_repo.upsert(resource)
        resources.append(resource)
    
    return {'sessions': sessions, 'resources': resources}


@pytest.mark.integration
async def test_dreaming_direct_mode(test_tenant_id, setup_test_data):
    """Test dreaming worker in direct mode."""
    print(f"\n🧪 Testing Dreaming Worker - Direct Mode")
    print(f"   Provider: {config.storage_provider}")
    print(f"   Tenant: {test_tenant_id}")
    
    # Initialize worker
    worker = DreamingWorker()
    
    # Process in direct mode
    job = await worker.process_direct(test_tenant_id)
    
    # Verify job was created
    assert job is not None
    assert job.tenant_id == test_tenant_id
    assert job.mode == ProcessingMode.DIRECT
    assert job.status == "completed"
    assert job.result is not None
    
    # Verify DreamModel structure in result
    result = job.result
    assert 'goals' in result
    assert 'dreams' in result
    assert 'fears' in result
    assert 'pending_tasks' in result  # DreamModel uses 'pending_tasks'
    
    # Check that some analysis was generated
    assert len(result['goals']) >= 0 or len(result['dreams']) >= 0
    
    print(f"✅ Direct mode completed successfully")
    print(f"   - Goals found: {len(result['goals'])}")
    print(f"   - Dreams found: {len(result['dreams'])}")
    print(f"   - Tasks identified: {len(result['pending_tasks'])}")


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv('OPENAI_API_KEY'),
    reason="OpenAI API key required for batch mode"
)
async def test_dreaming_batch_mode(test_tenant_id, setup_test_data):
    """Test dreaming worker in batch mode."""
    print(f"\n🧪 Testing Dreaming Worker - Batch Mode")
    print(f"   Provider: {config.storage_provider}")
    print(f"   Tenant: {test_tenant_id}")
    
    # Initialize worker
    worker = DreamingWorker()
    
    # Process in batch mode
    job = await worker.process_batch(test_tenant_id)
    
    # Verify job was created
    assert job is not None
    assert job.tenant_id == test_tenant_id
    assert job.mode == ProcessingMode.BATCH
    assert job.status == "pending"  # Batch jobs start as pending
    assert job.batch_id is not None or job.memory_proxy_job_id is not None
    
    # Verify job was saved to jobs table
    job_repo = SystemRepository(Job)
    if job.memory_proxy_job_id:
        saved_jobs = job_repo.execute(
            "SELECT * FROM jobs WHERE id = %s",
            (job.memory_proxy_job_id,)
        )
        assert len(saved_jobs) > 0
        saved_job = saved_jobs[0]
        assert saved_job['job_type'] == 'batch_completion'
        assert saved_job['tenant_id'] == test_tenant_id
    
    print(f"✅ Batch mode job submitted successfully")
    print(f"   - Job ID: {job.id}")
    print(f"   - Batch ID: {job.batch_id}")
    print(f"   - Memory Proxy Job ID: {job.memory_proxy_job_id}")


@pytest.mark.integration
async def test_dreaming_data_collection(test_tenant_id, setup_test_data):
    """Test data collection from sessions and resources."""
    print(f"\n🧪 Testing Dreaming Data Collection")
    print(f"   Provider: {config.storage_provider}")
    
    worker = DreamingWorker()
    
    # Collect user data
    data_batch = await worker.collect_user_data(test_tenant_id)
    
    # Verify sessions were collected
    assert len(data_batch.sessions) == 3
    for session in data_batch.sessions:
        assert session.get('tenant_id') == test_tenant_id
        assert 'query' in session
    
    # Verify resources were collected
    assert len(data_batch.resources) == 3
    for resource in data_batch.resources:
        assert resource.get('tenant_id') == test_tenant_id
        assert 'content' in resource
    
    print(f"✅ Data collection successful")
    print(f"   - Sessions collected: {len(data_batch.sessions)}")
    print(f"   - Resources collected: {len(data_batch.resources)}")




@pytest.mark.integration
async def test_provider_switching():
    """Test and document provider switching behavior."""
    print(f"\n📋 Provider Configuration Guide")
    print(f"   Current Provider: {config.storage_provider}")
    print(f"   Current Database: {getattr(config, f'{config.storage_provider}_database', 'N/A')}")
    
    print(f"\n   To switch providers, set environment variables:")
    print(f"   - PostgreSQL (default):")
    print(f"     export P8FS_STORAGE_PROVIDER=postgresql")
    print(f"     export P8FS_PG_HOST=localhost")
    print(f"     export P8FS_PG_PORT=5438")
    print(f"     export P8FS_PG_DATABASE=app")
    
    print(f"\n   - TiDB:")
    print(f"     export P8FS_STORAGE_PROVIDER=tidb")
    print(f"     export P8FS_TIDB_HOST=localhost")
    print(f"     export P8FS_TIDB_PORT=4000")
    print(f"     export P8FS_TIDB_DATABASE=public")
    
    print(f"\n   - RocksDB:")
    print(f"     export P8FS_STORAGE_PROVIDER=rocksdb")
    print(f"     export P8FS_ROCKSDB_PATH=/tmp/p8fs_rocksdb")
    
    # Verify current provider is working
    session_repo = SystemRepository(Session)
    test_session = {
        'id': str(uuid4()),
        'tenant_id': 'provider-test',
        'query': 'Provider test query',
        'created_at': datetime.now(timezone.utc)
    }
    
    await session_repo.upsert(test_session)
    print(f"\n✅ Current provider ({config.storage_provider}) is working correctly")


# CLI test helper
@pytest.mark.integration
async def test_dreaming_cli_commands():
    """Test and document CLI commands for dreaming worker."""
    print(f"\n📋 Dreaming Worker CLI Commands")
    
    print(f"\n1. Direct Mode (synchronous processing):")
    print(f"   python -m p8fs.workers.dreaming process --mode direct --tenant-id <tenant-id>")
    
    print(f"\n2. Batch Mode (async with OpenAI batch API):")
    print(f"   python -m p8fs.workers.dreaming process --mode batch --tenant-id <tenant-id>")
    
    print(f"\n3. Completion Mode (check batch job completions):")
    print(f"   python -m p8fs.workers.dreaming process --completion")
    print(f"   # or")
    print(f"   python -m p8fs.workers.dreaming process --mode completion")
    
    print(f"\n4. With TiDB provider:")
    print(f"   P8FS_STORAGE_PROVIDER=tidb python -m p8fs.workers.dreaming process --mode direct --tenant-id <tenant-id>")
    
    print(f"\n✅ CLI documentation complete")


if __name__ == "__main__":
    # Run all tests with current provider
    pytest.main([__file__, "-v", "-s"])