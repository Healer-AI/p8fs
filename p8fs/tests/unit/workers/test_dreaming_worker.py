"""Unit tests for DreamingWorker."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from p8fs.repository import TenantRepository
from p8fs.workers.dreaming import DreamingWorker, DreamJob, ProcessingMode


@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    repo = Mock(spec=TenantRepository)
    repo.get_sessions = AsyncMock(return_value=[
        {"id": "session1", "content": "test session"},
        {"id": "session2", "content": "another session"}
    ])
    repo.get_resources = AsyncMock(return_value=[
        {"id": "resource1", "content": "test resource"},
        {"id": "resource2", "content": "another resource"}
    ])
    repo.get_tenant_profile = AsyncMock(return_value={
        "id": "test-tenant",
        "preferences": {}
    })
    repo.create_dream_job = AsyncMock()
    repo.get_dream_jobs = AsyncMock(return_value=[])
    repo.update_dream_job = AsyncMock()
    repo.store_dream_analysis = AsyncMock()
    return repo


@pytest.fixture
def mock_memory_proxy():
    """Create a mock memory proxy."""
    with patch("p8fs.workers.dreaming.MemoryProxy") as mock:
        proxy = Mock()
        
        # Mock batch response
        batch_response = Mock()
        batch_response.batch_id = "batch-123" 
        batch_response.job_id = "job-456"
        proxy.batch = AsyncMock(return_value=batch_response)
        
        # Mock job status response
        job_status = Mock()
        job_status.is_complete = True
        job_status.results = [{
            "user_id": "test-tenant",
            "executive_summary": "Test analysis completed", 
            "key_themes": ["test", "analysis"]
        }]
        proxy.get_job = AsyncMock(return_value=job_status)
        
        mock.return_value = proxy
        yield proxy


@pytest.fixture
def mock_dream_model():
    """Create a mock dream model."""
    # We don't actually need to mock DreamModel for these tests
    # The dreaming worker creates its own DreamModel instances
    yield None


@pytest.fixture
def dreaming_worker(mock_repository, mock_memory_proxy, mock_dream_model):
    """Create a dreaming worker instance."""
    return DreamingWorker(mock_repository)


@pytest.mark.asyncio
async def test_collect_user_data(dreaming_worker, mock_repository):
    """Test collecting user sessions and resources."""
    tenant_id = "test-tenant"
    
    data = await dreaming_worker.collect_user_data(tenant_id)
    
    assert isinstance(data.user_profile, dict)
    assert len(data.sessions) == 2
    assert len(data.resources) == 2
    assert data.time_window_hours == 24
    
    mock_repository.get_sessions.assert_called_once_with(
        tenant_id=tenant_id,
        limit=100
    )
    mock_repository.get_resources.assert_called_once_with(
        tenant_id=tenant_id,
        limit=1000
    )


@pytest.mark.asyncio
async def test_process_batch(dreaming_worker, mock_repository, mock_memory_proxy):
    """Test batch processing mode."""
    tenant_id = "test-tenant"
    
    job = await dreaming_worker.process_batch(tenant_id)
    
    assert job.tenant_id == tenant_id
    assert job.mode == ProcessingMode.BATCH
    assert job.batch_id == "batch-123"
    assert job.memory_proxy_job_id == "job-456"
    assert job.status == "pending"  # Default status since batch succeeded
    
    # Verify batch was submitted with correct interface
    mock_memory_proxy.batch.assert_called_once()
    call_args = mock_memory_proxy.batch.call_args
    
    # Verify prompt was passed as first argument
    prompt = call_args[0][0] 
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    
    # Verify BatchCallingContext was passed as second argument
    batch_context = call_args[0][1]
    assert batch_context.tenant_id == tenant_id
    assert batch_context.save_job is True
    assert batch_context.model == "gpt-4-turbo-preview"
    
    # Verify job was created
    mock_repository.create_dream_job.assert_called_once()


@pytest.mark.asyncio
async def test_process_direct(dreaming_worker, mock_repository, mock_dream_model):
    """Test direct processing mode."""
    tenant_id = "test-tenant"
    
    job = await dreaming_worker.process_direct(tenant_id)
    
    assert job.tenant_id == tenant_id
    assert job.mode == ProcessingMode.DIRECT
    assert job.status == "completed"
    assert job.completed_at is not None
    assert "executive_summary" in job.result
    assert "key_themes" in job.result
    
    # Verify job was created
    mock_repository.create_dream_job.assert_called_once()


@pytest.mark.asyncio
async def test_check_completions_no_jobs(dreaming_worker, mock_repository):
    """Test checking completions with no pending jobs."""
    await dreaming_worker.check_completions()
    
    mock_repository.get_dream_jobs.assert_called_once_with(
        status="pending",
        mode=ProcessingMode.BATCH
    )
    
    # No updates should be made
    mock_repository.update_dream_job.assert_not_called()


@pytest.mark.asyncio
async def test_check_completions_with_completed_job(dreaming_worker, mock_repository, mock_memory_proxy):
    """Test checking completions with a completed job."""
    # Setup mock data
    job_data = {
        "id": str(uuid4()),
        "tenant_id": "test-tenant",
        "status": "pending",
        "mode": "batch",
        "batch_id": "batch-123",
        "memory_proxy_job_id": "job-456",
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
        "result": None
    }
    
    mock_repository.get_dream_jobs.return_value = [job_data]
    
    # Update mock to return completed job status with valid DreamModel data
    job_status = Mock()
    job_status.is_complete = True
    job_status.results = [{
        "user_id": "test-tenant",
        "executive_summary": "Test analysis completed",
        "key_themes": ["test", "analysis"]
    }]
    mock_memory_proxy.get_job.return_value = job_status
    
    await dreaming_worker.check_completions()
    
    # Verify job status was checked using new interface
    mock_memory_proxy.get_job.assert_called_once_with(
        job_id="job-456",
        tenant_id="test-tenant", 
        fetch_results=True
    )
    
    # Verify job was updated
    mock_repository.update_dream_job.assert_called_once()
    update_args = mock_repository.update_dream_job.call_args[0]
    assert update_args[0] == job_data["id"]
    assert update_args[1]["status"] == "completed"
    
    # Verify job was updated with the parsed DreamModel result
    result = update_args[1]["result"]
    assert result["user_id"] == "test-tenant"
    assert result["executive_summary"] == "Test analysis completed"
    assert result["key_themes"] == ["test", "analysis"]
    assert "analysis_id" in result  # Auto-generated field


@pytest.mark.asyncio
async def test_check_completions_with_pending_job(dreaming_worker, mock_repository):
    """Test checking completions with a still-pending job."""
    job_data = {
        "id": str(uuid4()),
        "tenant_id": "test-tenant",
        "status": "pending",
        "mode": "batch",
        "batch_id": "batch-123",
        "memory_proxy_job_id": "job-456",
        "created_at": datetime.now(timezone.utc),
        "completed_at": None,
        "result": None
    }
    
    mock_repository.get_dream_jobs.return_value = [job_data]
    
    # Mock job status as incomplete (override the fixture)
    job_status = Mock()
    job_status.is_complete = False
    job_status.is_failed = False  # Explicitly not failed
    dreaming_worker.memory_proxy.get_job.return_value = job_status
    
    await dreaming_worker.check_completions()
    
    # Job status should be checked
    dreaming_worker.memory_proxy.get_job.assert_called_once_with(
        job_id="job-456",
        tenant_id="test-tenant",
        fetch_results=True
    )
    
    # Should not update job since it's not complete
    mock_repository.update_dream_job.assert_not_called()


def test_dream_job_model():
    """Test DreamJob model validation."""
    job = DreamJob(
        id=str(uuid4()),
        tenant_id="test-tenant",
        mode=ProcessingMode.BATCH
    )
    
    assert job.status == "pending"
    assert job.mode == ProcessingMode.BATCH
    assert isinstance(job.created_at, datetime)
    assert job.completed_at is None
    assert job.result is None


def test_processing_mode_enum():
    """Test ProcessingMode enum values."""
    assert ProcessingMode.BATCH == "batch"
    assert ProcessingMode.DIRECT == "direct"
    assert ProcessingMode.COMPLETION == "completion"