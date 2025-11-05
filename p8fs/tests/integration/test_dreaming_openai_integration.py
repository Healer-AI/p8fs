"""Integration tests for dreaming worker with real OpenAI API calls."""
import os
import asyncio
import pytest
from datetime import datetime, timezone
import time

from p8fs.workers.dreaming import DreamingWorker, ProcessingMode
from p8fs.models.p8 import Job, JobStatus, Session, Resources
from p8fs.repository import SystemRepository
from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger

logger = get_logger(__name__)

# Skip if no OpenAI key or not using TiDB
pytestmark = [
    pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY not set"
    ),
    pytest.mark.skipif(
        config.storage_provider != "tidb",
        reason="Test requires TiDB provider (uses TiDB-specific SQL syntax)"
    )
]


@pytest.fixture
async def setup_test_data_openai():
    """Create test data for OpenAI integration tests."""
    tenant_id = f"test-openai-{int(time.time())}"
    
    # Create test session
    session_repo = SystemRepository(Session)
    test_session = {
        'id': f'session-{tenant_id}',
        'tenant_id': tenant_id,
        'name': 'OpenAI Integration Test Session',
        'query': 'Testing real OpenAI API calls with dreaming worker',
        'metadata': {
            'context': {
                'purpose': 'Integration testing',
                'topics': ['AI', 'testing', 'batch processing'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
        },
        'session_type': 'test',
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc)
    }
    await session_repo.upsert(test_session)
    
    # Create test resource
    resource_repo = SystemRepository(Resources)
    test_resource = {
        'id': f'resource-{tenant_id}',
        'tenant_id': tenant_id,
        'name': 'integration_test.md',
        'category': 'document',
        'content': """
# Integration Test Document

This document contains test data for OpenAI integration:

## Goals
- Test batch processing with real API
- Verify job creation and status updates
- Confirm dream analysis results

## Topics
- Machine learning applications
- Distributed systems
- API integration patterns

## Notes
- Remember to check API rate limits
- Monitor batch job status
- Validate response schemas
        """,
        'summary': 'Test document for OpenAI integration testing',
        'metadata': {
            'format': 'markdown',
            'tags': ['testing', 'openai', 'integration']
        },
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc)
    }
    await resource_repo.upsert(test_resource)
    
    yield tenant_id
    
    # Cleanup
    await session_repo.delete(test_session['id'])
    await resource_repo.delete(test_resource['id'])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dreaming_direct_mode_real_openai(setup_test_data_openai):
    """Test direct mode with real OpenAI API call."""
    tenant_id = setup_test_data_openai
    
    logger.info(f"Testing direct mode with real OpenAI for tenant {tenant_id}")
    
    # Initialize worker
    worker = DreamingWorker()
    
    # Process in direct mode (synchronous OpenAI call)
    start_time = time.time()
    job = await worker.process_direct(tenant_id)
    duration = time.time() - start_time
    
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert job.mode == ProcessingMode.DIRECT
    assert job.result is not None
    
    # Verify the result structure
    result = job.result
    assert 'user_id' in result
    assert result['user_id'] == tenant_id
    assert 'goals' in result
    assert 'dreams' in result
    assert 'metrics' in result
    assert 'analysis_id' in result
    
    # Check that we got actual analysis
    assert len(result.get('key_themes', [])) > 0
    assert result.get('executive_summary', '') != ''
    
    logger.info(f"Direct mode completed in {duration:.2f}s")
    logger.info(f"Found {len(result['goals'])} goals")
    logger.info(f"Found {len(result['dreams'])} dreams")
    logger.info(f"Executive summary: {result['executive_summary'][:100]}...")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dreaming_batch_mode_real_openai(setup_test_data_openai):
    """Test batch mode with real OpenAI API submission."""
    tenant_id = setup_test_data_openai
    
    logger.info(f"Testing batch mode with real OpenAI for tenant {tenant_id}")
    
    # Initialize worker and job repo
    worker = DreamingWorker()
    job_repo = SystemRepository(Job)
    
    # Process in batch mode
    dream_job = await worker.process_batch(tenant_id)
    
    assert dream_job is not None
    assert dream_job.status == JobStatus.PENDING
    assert dream_job.mode == ProcessingMode.BATCH
    assert dream_job.batch_id is not None
    assert dream_job.memory_proxy_job_id is not None
    
    logger.info(f"Batch job created: {dream_job.id}")
    logger.info(f"OpenAI batch ID: {dream_job.batch_id}")
    logger.info(f"Memory proxy job ID: {dream_job.memory_proxy_job_id}")
    
    # Verify job is in database
    saved_jobs = job_repo.execute(
        "SELECT * FROM jobs WHERE id = %s",
        (dream_job.memory_proxy_job_id,)
    )
    
    assert len(saved_jobs) == 1
    job_record = saved_jobs[0]
    
    assert job_record['job_type'] == 'batch_completion'
    assert job_record['is_batch'] == 1
    assert job_record['tenant_id'] == config.default_tenant_id  # Uses default from config
    assert job_record['status'] in ['pending', 'processing']
    
    # Check payload
    payload = job_record['payload']
    assert payload is not None
    assert 'model' in payload
    assert 'questions' in payload
    assert len(payload['questions']) > 0
    
    logger.info(f"Job saved to database with status: {job_record['status']}")
    logger.info(f"Payload contains {len(payload['questions'])} questions")
    
    # Wait a bit and check if status updated
    await asyncio.sleep(5)
    
    updated_jobs = job_repo.execute(
        "SELECT status, openai_batch_id FROM jobs WHERE id = %s",
        (dream_job.memory_proxy_job_id,)
    )
    
    if updated_jobs:
        logger.info(f"Job status after 5s: {updated_jobs[0]['status']}")
        logger.info(f"OpenAI batch ID: {updated_jobs[0]['openai_batch_id']}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dreaming_batch_completion_check(setup_test_data_openai):
    """Test checking batch job completion status."""
    tenant_id = setup_test_data_openai
    
    # First submit a batch job
    worker = DreamingWorker()
    dream_job = await worker.process_batch(tenant_id)
    
    logger.info(f"Submitted batch job: {dream_job.id}")
    
    # Wait a moment for OpenAI to process
    await asyncio.sleep(10)
    
    # Check completion
    completed_jobs = await worker.check_completed_batches()
    
    logger.info(f"Checked for completed batches, found {len(completed_jobs)} jobs")
    
    # The job might not be complete yet, but we should have checked
    job_repo = SystemRepository(Job)
    job_status = job_repo.execute(
        "SELECT status, openai_batch_status FROM jobs WHERE id = %s",
        (dream_job.memory_proxy_job_id,)
    )
    
    if job_status:
        logger.info(f"Current job status: {job_status[0]['status']}")
        logger.info(f"OpenAI batch status: {job_status[0].get('openai_batch_status', 'N/A')}")


@pytest.mark.integration
@pytest.mark.asyncio 
async def test_direct_vs_batch_comparison(setup_test_data_openai):
    """Compare results from direct and batch modes."""
    tenant_id = setup_test_data_openai
    
    worker = DreamingWorker()
    
    # Run direct mode
    logger.info("Running direct mode...")
    direct_start = time.time()
    direct_job = await worker.process_direct(tenant_id)
    direct_time = time.time() - direct_start
    
    # Run batch mode
    logger.info("Running batch mode...")
    batch_start = time.time()
    batch_job = await worker.process_batch(tenant_id)
    batch_submit_time = time.time() - batch_start
    
    # Compare
    logger.info(f"Direct mode time: {direct_time:.2f}s")
    logger.info(f"Batch submission time: {batch_submit_time:.2f}s")
    logger.info(f"Direct result themes: {len(direct_job.result.get('key_themes', []))}")
    logger.info(f"Batch job ID: {batch_job.id}")
    
    # Direct mode should have results immediately
    assert direct_job.status == JobStatus.COMPLETED
    assert direct_job.result is not None
    
    # Batch mode should be pending
    assert batch_job.status == JobStatus.PENDING
    assert batch_job.batch_id is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_job_status_tracking():
    """Test that job status is properly tracked in database."""
    job_repo = SystemRepository(Job)
    
    # Check recent batch jobs
    recent_jobs = job_repo.execute("""
        SELECT id, job_type, status, tenant_id, is_batch,
               openai_batch_id, openai_batch_status,
               created_at, started_at, completed_at
        FROM jobs
        WHERE is_batch = 1
        AND created_at > NOW() - INTERVAL 1 HOUR
        ORDER BY created_at DESC
        LIMIT 10
    """, ())
    
    logger.info(f"Found {len(recent_jobs)} recent batch jobs")
    
    for job in recent_jobs:
        logger.info(f"Job {job['id'][:12]}...")
        logger.info(f"  Status: {job['status']}")
        logger.info(f"  OpenAI Status: {job.get('openai_batch_status', 'N/A')}")
        logger.info(f"  Created: {job['created_at']}")
        logger.info(f"  Started: {job.get('started_at', 'Not started')}")
        logger.info(f"  Completed: {job.get('completed_at', 'Not completed')}")


if __name__ == "__main__":
    # Run specific test
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "direct":
        asyncio.run(test_dreaming_direct_mode_real_openai())
    elif len(sys.argv) > 1 and sys.argv[1] == "batch":
        asyncio.run(test_dreaming_batch_mode_real_openai())
    else:
        pytest.main([__file__, "-v", "-s"])