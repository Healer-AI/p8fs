"""Integration tests for DreamingWorker batch processing functionality."""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from p8fs.workers.dreaming import DreamingWorker, DreamJob, ProcessingMode
from p8fs.models.agentlets import DreamModel, UserDataBatch
from p8fs.services.llm.models import BatchCallingContext, JobStatusResponse
from p8fs.workers.dreaming_repository import DreamingRepository


@pytest.fixture
async def mock_dreaming_repository():
    """Mock repository for dreaming worker tests."""
    repo = AsyncMock(spec=DreamingRepository)
    
    # Mock session and resource data
    repo.get_sessions.return_value = [
        {
            "id": "session1",
            "content": "User discussed career goals and learning Python programming",
            "created_at": datetime.now(timezone.utc),
            "tenant_id": "test-tenant"
        },
        {
            "id": "session2", 
            "content": "User expressed concerns about work-life balance",
            "created_at": datetime.now(timezone.utc),
            "tenant_id": "test-tenant"
        }
    ]
    
    repo.get_resources.return_value = [
        {
            "id": "resource1",
            "title": "Python Learning Guide",
            "content": "Comprehensive guide to learning Python programming",
            "created_at": datetime.now(timezone.utc),
            "tenant_id": "test-tenant"
        },
        {
            "id": "resource2",
            "title": "Career Development Plan", 
            "content": "Strategic plan for career advancement in tech industry",
            "created_at": datetime.now(timezone.utc),
            "tenant_id": "test-tenant"
        }
    ]
    
    repo.get_tenant_profile.return_value = {
        "name": "Test User",
        "occupation": "Software Developer",
        "interests": ["programming", "career development"]
    }
    
    # Mock job storage operations
    repo.create_dream_job.return_value = None
    repo.update_dream_job.return_value = None
    repo.get_dream_jobs.return_value = []
    repo.store_dream_analysis.return_value = None
    
    return repo


@pytest.fixture
async def mock_memory_proxy():
    """Mock MemoryProxy for integration tests."""
    memory_proxy = AsyncMock()
    
    # Mock batch response
    batch_response = Mock()
    batch_response.batch_id = "batch_test_123"
    batch_response.job_id = "job_test_456"
    memory_proxy.batch.return_value = batch_response
    
    # Mock job status response
    job_status = Mock()
    job_status.is_complete = True
    job_status.results = [{
        "user_id": "test-tenant",
        "executive_summary": "User is focused on career development in Python programming",
        "key_themes": ["career_development", "python_programming", "work_life_balance"],
        "goals": [
            {
                "goal": "Master Python programming",
                "category": "career",
                "priority": "high"
            }
        ],
        "dreams": [
            {
                "dream": "Become a senior Python developer",
                "category": "professional",
                "timeline": "medium-term",
                "actionability": "high"
            }
        ],
        "fears": [
            {
                "fear": "Work-life balance challenges",
                "category": "professional", 
                "severity": "medium"
            }
        ]
    }]
    memory_proxy.get_job.return_value = job_status
    
    return memory_proxy


@pytest.fixture
async def dreaming_worker(mock_dreaming_repository, mock_memory_proxy):
    """DreamingWorker with mocked dependencies."""
    worker = DreamingWorker(repo=mock_dreaming_repository)
    worker.memory_proxy = mock_memory_proxy
    return worker


@pytest.mark.integration
class TestDreamingWorkerBatchProcessing:
    """Integration tests for DreamingWorker batch processing."""
    
    async def test_collect_user_data_integration(self, dreaming_worker):
        """Test user data collection with realistic data."""
        tenant_id = "test-tenant"
        
        # Collect user data
        data_batch = await dreaming_worker.collect_user_data(tenant_id)
        
        # Verify data structure
        assert isinstance(data_batch, UserDataBatch)
        assert data_batch.user_profile["name"] == "Test User"
        assert len(data_batch.sessions) == 2
        assert len(data_batch.resources) == 2
        assert data_batch.time_window_hours == 24
        
        # Verify session content
        session_contents = [s["content"] for s in data_batch.sessions]
        assert "career goals" in session_contents[0]
        assert "work-life balance" in session_contents[1]
        
        # Verify resource content  
        resource_titles = [r["title"] for r in data_batch.resources]
        assert "Python Learning Guide" in resource_titles
        assert "Career Development Plan" in resource_titles

    async def test_process_batch_integration(self, dreaming_worker, mock_memory_proxy):
        """Test batch processing workflow integration."""
        tenant_id = "test-tenant"
        
        # Process batch job
        job = await dreaming_worker.process_batch(tenant_id)
        
        # Verify job creation
        assert isinstance(job, DreamJob)
        assert job.tenant_id == tenant_id
        assert job.mode == ProcessingMode.BATCH
        assert job.batch_id == "batch_test_123"
        assert job.memory_proxy_job_id == "job_test_456"
        
        # Verify MemoryProxy was called with correct parameters
        mock_memory_proxy.batch.assert_called_once()
        call_args = mock_memory_proxy.batch.call_args
        
        # Verify prompt content
        prompt = call_args[0][0]  # First positional argument
        assert "User Profile: {'name': 'Test User'" in prompt
        assert "career goals" in prompt.lower()
        assert "python" in prompt.lower()
        
        # Verify batch context
        batch_context = call_args[0][1]  # Second positional argument
        assert isinstance(batch_context, BatchCallingContext)
        assert batch_context.tenant_id == tenant_id
        assert batch_context.save_job is True
        assert batch_context.model == "gpt-4.1"

    async def test_check_completions_integration(self, dreaming_worker, mock_dreaming_repository, mock_memory_proxy):
        """Test completion checking workflow integration."""
        # Setup pending job
        pending_job_data = {
            "id": "job123",
            "tenant_id": "test-tenant", 
            "status": "pending",
            "mode": ProcessingMode.BATCH,
            "batch_id": "batch_test_123",
            "memory_proxy_job_id": "job_test_456",
            "created_at": datetime.now(timezone.utc)
        }
        mock_dreaming_repository.get_dream_jobs.return_value = [pending_job_data]
        
        # Run completion check
        await dreaming_worker.check_completions()
        
        # Verify job status was checked
        mock_memory_proxy.get_job.assert_called_once_with(
            job_id="job_test_456",
            tenant_id="test-tenant",
            fetch_results=True
        )
        
        # Verify dream analysis was stored
        mock_dreaming_repository.store_dream_analysis.assert_called_once()
        stored_analysis = mock_dreaming_repository.store_dream_analysis.call_args[0][0]
        assert isinstance(stored_analysis, DreamModel)
        assert stored_analysis.user_id == "test-tenant"
        assert "career development" in stored_analysis.executive_summary.lower()
        assert "career_development" in stored_analysis.key_themes
        
        # Verify job was updated
        mock_dreaming_repository.update_dream_job.assert_called_once()
        job_update_args = mock_dreaming_repository.update_dream_job.call_args
        assert job_update_args[0][0] == "job123"  # job_id
        updated_job_data = job_update_args[0][1]  # job data
        assert updated_job_data["status"] == "completed"
        assert "result" in updated_job_data

    async def test_batch_processing_error_handling(self, dreaming_worker, mock_memory_proxy, mock_dreaming_repository):
        """Test error handling in batch processing."""
        tenant_id = "test-tenant"
        
        # Simulate batch submission error
        mock_memory_proxy.batch.side_effect = Exception("API Error")
        
        # Process batch - should handle error gracefully
        job = await dreaming_worker.process_batch(tenant_id)
        
        # Verify error was handled
        assert job.status == "failed"
        assert "result" in job.model_dump()
        assert "error" in job.result
        assert "API Error" in str(job.result["error"])
        
        # Verify job was still created with error status
        mock_dreaming_repository.create_dream_job.assert_called_once()

    async def test_completion_check_failed_batch(self, dreaming_worker, mock_dreaming_repository, mock_memory_proxy):
        """Test handling of failed batch jobs."""
        # Setup pending job
        pending_job_data = {
            "id": "job123",
            "tenant_id": "test-tenant",
            "status": "pending", 
            "mode": ProcessingMode.BATCH,
            "batch_id": "batch_test_123",
            "memory_proxy_job_id": "job_test_456",
            "created_at": datetime.now(timezone.utc)
        }
        mock_dreaming_repository.get_dream_jobs.return_value = [pending_job_data]
        
        # Mock incomplete job status (not failed, just not complete)
        job_status = Mock()
        job_status.is_complete = False
        job_status.is_failed = False  # Explicitly not failed either
        mock_memory_proxy.get_job.return_value = job_status
        
        # Run completion check
        await dreaming_worker.check_completions()
        
        # Verify no update was made for incomplete job
        mock_dreaming_repository.update_dream_job.assert_not_called()
        mock_dreaming_repository.store_dream_analysis.assert_not_called()

    async def test_completion_check_parsing_error(self, dreaming_worker, mock_dreaming_repository, mock_memory_proxy):
        """Test handling of result parsing errors."""
        # Setup pending job
        pending_job_data = {
            "id": "job123", 
            "tenant_id": "test-tenant",
            "status": "pending",
            "mode": ProcessingMode.BATCH,
            "batch_id": "batch_test_123",
            "memory_proxy_job_id": "job_test_456",
            "created_at": datetime.now(timezone.utc)
        }
        mock_dreaming_repository.get_dream_jobs.return_value = [pending_job_data]
        
        # Mock job with result that will fail DreamModel validation
        job_status = Mock()
        job_status.is_complete = True
        job_status.results = [{
            "goals": [{"invalid_field": "this will fail validation"}],  # Missing required fields
            "user_id": "not-a-uuid-format",  # Will cause validation error if strict UUID validation
            "analysis_id": "also-not-a-uuid"
        }]
        mock_memory_proxy.get_job.return_value = job_status
        
        # Run completion check
        await dreaming_worker.check_completions()
        
        # Verify job was still completed with raw result (parsing failed gracefully)
        mock_dreaming_repository.update_dream_job.assert_called_once()
        job_update_args = mock_dreaming_repository.update_dream_job.call_args
        updated_job_data = job_update_args[0][1]
        assert updated_job_data["status"] == "completed"
        
        # The result should be the raw data since parsing failed
        result = updated_job_data["result"]
        assert result["goals"] == [{"invalid_field": "this will fail validation"}]
        assert result["user_id"] == "not-a-uuid-format"
        
        # Verify dream analysis was not stored due to parsing error
        mock_dreaming_repository.store_dream_analysis.assert_not_called()

    async def test_direct_vs_batch_processing_integration(self, dreaming_worker):
        """Test comparison between direct and batch processing modes."""
        tenant_id = "test-tenant"
        
        # Test direct processing
        direct_job = await dreaming_worker.process_direct(tenant_id)
        assert direct_job.mode == ProcessingMode.DIRECT
        assert direct_job.status == "completed"
        assert "result" in direct_job.model_dump()
        
        # Test batch processing  
        batch_job = await dreaming_worker.process_batch(tenant_id)
        assert batch_job.mode == ProcessingMode.BATCH
        assert batch_job.batch_id == "batch_test_123" 
        assert batch_job.memory_proxy_job_id == "job_test_456"

    async def test_prompt_building_integration(self, dreaming_worker):
        """Test prompt building with realistic data."""
        tenant_id = "test-tenant"
        
        # Collect data and build prompt
        data_batch = await dreaming_worker.collect_user_data(tenant_id)
        prompt = dreaming_worker._build_analysis_prompt(data_batch)
        
        # Verify prompt contains all expected sections
        assert "User Profile:" in prompt
        assert "Data Summary:" in prompt
        assert "Sample Recent Sessions:" in prompt
        assert "Sample Resources:" in prompt
        assert "DreamModel structure:" in prompt
        
        # Verify content is included
        assert "Test User" in prompt
        assert "career goals" in prompt
        assert "Python Learning Guide" in prompt
        assert "work-life balance" in prompt
        
        # Verify analysis instructions
        assert "Executive Summary" in prompt
        assert "Key Themes" in prompt
        assert "Personal Insights" in prompt
        assert "Action Items" in prompt
        assert "Recommendations" in prompt