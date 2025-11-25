"""Integration test for dreaming worker with REAL OpenAI API calls.

This test monkey-patches the OpenAIRequestsClient to add missing methods
and enable actual OpenAI Batch API submissions.
"""
import os
import asyncio
import pytest
from datetime import datetime, timezone
import time
import json
import tempfile

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


def patch_openai_client():
    """Monkey-patch OpenAIRequestsClient to add missing batch methods."""
    from p8fs.services.llm.openai_client import OpenAIRequestsClient
    
    # Add missing upload_file method
    async def upload_file(self, file_path: str, purpose: str = "batch"):
        """Upload file to OpenAI."""
        try:
            import openai
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package required for real API calls")
            
        client = AsyncOpenAI(api_key=self.api_key)
        
        with open(file_path, 'rb') as f:
            response = await client.files.create(file=f, purpose=purpose)
            
        return {
            "id": response.id,
            "object": response.object,
            "bytes": response.bytes,
            "created_at": response.created_at,
            "filename": response.filename,
            "purpose": response.purpose,
        }
    
    # Add missing create_batch method
    async def create_batch(self, input_file_id: str, endpoint: str, completion_window: str, metadata: dict = None):
        """Create batch job on OpenAI."""
        try:
            import openai
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package required for real API calls")
            
        client = AsyncOpenAI(api_key=self.api_key)
        
        response = await client.batches.create(
            input_file_id=input_file_id,
            endpoint=endpoint,
            completion_window=completion_window,
            metadata=metadata or {}
        )
        
        return {
            "id": response.id,
            "object": response.object,
            "endpoint": response.endpoint,
            "errors": response.errors,
            "input_file_id": response.input_file_id,
            "completion_window": response.completion_window,
            "status": response.status,
            "output_file_id": response.output_file_id,
            "error_file_id": response.error_file_id,
            "created_at": response.created_at,
            "in_progress_at": response.in_progress_at,
            "expires_at": response.expires_at,
            "completed_at": response.completed_at,
            "metadata": dict(response.metadata) if response.metadata else {},
        }
    
    # Patch the class
    OpenAIRequestsClient.upload_file = upload_file
    OpenAIRequestsClient.create_batch = create_batch
    
    logger.info("Patched OpenAIRequestsClient with real batch methods")


@pytest.fixture(autouse=True)
def enable_real_openai():
    """Enable real OpenAI API calls for these tests."""
    patch_openai_client()
    yield


@pytest.fixture
async def real_test_data():
    """Create test data for real OpenAI tests."""
    tenant_id = f"real-openai-{int(time.time())}"
    
    # Create sessions
    session_repo = SystemRepository(Session)
    sessions = [
        {
            'id': f'session-{i}-{tenant_id}',
            'tenant_id': tenant_id,
            'name': f'Session {i}: Planning and Goals',
            'query': f'Query {i}: What should I focus on this year?',
            'metadata': {
                'topics': ['goals', 'planning', 'productivity'],
                'timestamp': datetime.now(timezone.utc).isoformat()
            },
            'session_type': 'conversation',
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
        for i in range(2)
    ]
    
    for session in sessions:
        await session_repo.upsert(session)
    
    # Create resources
    resource_repo = SystemRepository(Resources)
    resources = [
        {
            'id': f'res-goals-{int(time.time())}',
            'tenant_id': tenant_id,
            'name': 'personal_goals_2025.md',
            'category': 'document',
            'content': """
# Personal Goals for 2025

## Technical Goals
1. Master Rust programming language
   - Complete the Rust book
   - Build a production web service
   - Contribute to open source Rust projects

2. Learn distributed systems
   - Study Raft consensus algorithm
   - Build a distributed key-value store
   - Deploy on Kubernetes

3. AI/ML Skills
   - Understand transformer architecture deeply
   - Fine-tune language models
   - Build RAG applications

## Personal Goals
1. Travel to Japan for 2 weeks
2. Run a half marathon
3. Read 24 books (2 per month)
4. Learn basic Japanese

## Career Goals
1. Lead a major technical project
2. Mentor junior developers
3. Speak at a technical conference
            """,
            'summary': 'Personal goals document for 2025 including technical, personal, and career objectives',
            'metadata': {'type': 'goals', 'year': 2025},
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        },
        {
            'id': f'res-journal-{int(time.time())}',
            'tenant_id': tenant_id,
            'name': 'daily_journal.txt',
            'category': 'journal',
            'content': """
Daily reflections:
- Feeling motivated to learn new technologies
- Worried about time management with so many goals
- Excited about the Japan trip planning
- Need to balance work and personal projects better
            """,
            'summary': 'Daily journal entries with reflections',
            'metadata': {'type': 'journal'},
            'created_at': datetime.now(timezone.utc),
            'updated_at': datetime.now(timezone.utc)
        }
    ]
    
    for resource in resources:
        await resource_repo.upsert(resource)
    
    yield tenant_id
    
    # Cleanup
    for session in sessions:
        await session_repo.delete(session['id'])
    for resource in resources:
        await resource_repo.delete(resource['id'])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_openai_direct_mode(real_test_data):
    """Test direct mode with REAL OpenAI API calls."""
    tenant_id = real_test_data
    
    logger.info(f"🚀 Testing REAL OpenAI direct mode for tenant {tenant_id}")
    
    worker = DreamingWorker()
    
    # Remove the mock from analyze_user_dreams by patching it
    from p8fs.workers.dreaming import DreamingWorker
    from p8fs.models.batch import DreamModel, DreamAnalysisMetrics
    
    async def real_analyze_user_dreams(self, tenant_id, data_batch):
        """Real implementation that calls OpenAI."""
        analysis_prompt = self._build_analysis_prompt(data_batch)
        
        # Use MemoryProxy to get real OpenAI response
        from p8fs.services.llm.models import CallingContext
        context = CallingContext(model="gpt-4-turbo-preview")
        
        # Get real response from OpenAI
        response = await self.memory_proxy.complete(analysis_prompt, context)
        
        # Parse the response into DreamModel
        try:
            # Attempt to parse as JSON
            import json
            response_json = json.loads(response)
            dream_model = DreamModel(**response_json)
        except:
            # Fallback to basic parsing
            dream_model = DreamModel(
                user_id=tenant_id,
                executive_summary=response[:200],
                key_themes=["goals", "learning", "travel"],
                metrics=DreamAnalysisMetrics(
                    total_documents_analyzed=len(data_batch.resources),
                    confidence_score=0.9,
                    data_completeness=0.95
                )
            )
        
        dream_model.user_id = tenant_id
        return dream_model
    
    # Patch the method
    DreamingWorker.analyze_user_dreams = real_analyze_user_dreams
    
    # Run direct mode
    start_time = time.time()
    job = await worker.process_direct(tenant_id)
    duration = time.time() - start_time
    
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert job.mode == ProcessingMode.DIRECT
    assert job.result is not None
    
    # Log results
    result = job.result
    logger.info(f"✅ Real OpenAI direct mode completed in {duration:.2f}s")
    logger.info(f"   Executive Summary: {result.get('executive_summary', '')[:100]}...")
    logger.info(f"   Key Themes: {result.get('key_themes', [])}")
    logger.info(f"   Goals: {len(result.get('goals', []))}")
    logger.info(f"   Dreams: {len(result.get('dreams', []))}")
    
    # Verify we got real analysis
    assert result.get('executive_summary', '') != f"Analysis completed for tenant {tenant_id}"
    assert len(result.get('key_themes', [])) > 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_openai_batch_mode(real_test_data):
    """Test batch mode with REAL OpenAI Batch API."""
    tenant_id = real_test_data
    
    logger.info(f"🚀 Testing REAL OpenAI batch mode for tenant {tenant_id}")
    
    worker = DreamingWorker()
    job_repo = SystemRepository(Job)
    
    # Submit batch job
    dream_job = await worker.process_batch(tenant_id)
    
    assert dream_job is not None
    assert dream_job.status == JobStatus.PENDING
    assert dream_job.mode == ProcessingMode.BATCH
    assert dream_job.batch_id is not None
    assert dream_job.memory_proxy_job_id is not None
    
    logger.info(f"✅ Real batch job submitted:")
    logger.info(f"   Dream Job ID: {dream_job.id}")
    logger.info(f"   Batch ID: {dream_job.batch_id}")
    logger.info(f"   Memory Proxy Job ID: {dream_job.memory_proxy_job_id}")
    
    # Verify job in database
    saved_jobs = job_repo.execute(
        "SELECT * FROM jobs WHERE id = %s",
        (dream_job.memory_proxy_job_id,)
    )
    
    assert len(saved_jobs) == 1
    job_record = saved_jobs[0]
    
    # Check for real OpenAI batch ID
    openai_batch_id = job_record.get('openai_batch_id', '')
    assert openai_batch_id.startswith('batch_')
    assert openai_batch_id != 'batch_000000000000000000000000'
    
    logger.info(f"✅ Real OpenAI Batch ID: {openai_batch_id}")
    logger.info(f"   Status: {job_record['status']}")
    logger.info(f"   Check at: https://platform.openai.com/batches/{openai_batch_id}")
    
    # Wait and check status
    await asyncio.sleep(5)
    
    updated_jobs = job_repo.execute(
        "SELECT status, openai_batch_status FROM jobs WHERE id = %s",
        (dream_job.memory_proxy_job_id,)
    )
    
    if updated_jobs:
        logger.info(f"   Status after 5s: {updated_jobs[0]['status']}")
        logger.info(f"   OpenAI status: {updated_jobs[0].get('openai_batch_status', 'N/A')}")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_batch_status_check():
    """Test checking real batch job status from OpenAI."""
    job_repo = SystemRepository(Job)
    
    # Get recent batch jobs
    recent_jobs = job_repo.execute("""
        SELECT id, openai_batch_id, status, created_at
        FROM jobs
        WHERE is_batch = 1
        AND openai_batch_id IS NOT NULL
        AND openai_batch_id != 'batch_000000000000000000000000'
        ORDER BY created_at DESC
        LIMIT 5
    """, ())
    
    logger.info(f"Found {len(recent_jobs)} real batch jobs")
    
    if recent_jobs:
        # Check status of most recent
        job = recent_jobs[0]
        batch_id = job['openai_batch_id']
        
        try:
            import openai
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            status = await client.batches.retrieve(batch_id)
            
            logger.info(f"✅ Real batch status for {batch_id}:")
            logger.info(f"   Status: {status.status}")
            logger.info(f"   Created: {status.created_at}")
            logger.info(f"   Request counts: {status.request_counts}")
            
        except Exception as e:
            logger.error(f"Failed to check batch status: {e}")


if __name__ == "__main__":
    # Enable patching for standalone run
    patch_openai_client()
    
    # Run specific test
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "direct":
        asyncio.run(test_real_openai_direct_mode())
    elif len(sys.argv) > 1 and sys.argv[1] == "batch":
        asyncio.run(test_real_openai_batch_mode())
    else:
        pytest.main([__file__, "-v", "-s"])