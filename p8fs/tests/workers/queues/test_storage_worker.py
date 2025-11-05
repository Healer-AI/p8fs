"""Tests for storage event worker."""

import pytest
pytest.skip("Queue module dependencies not available", allow_module_level=True)

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from p8fs.workers.queues.config import QueueSize
from p8fs.workers.queues.storage_worker import (
    StorageEventWorker,
    WorkerManager,
    WorkerMetrics,
    WorkerStatus,
)


class TestWorkerMetrics:
    """Test WorkerMetrics functionality."""
    
    def test_default_values(self):
        """Test default metric values."""
        metrics = WorkerMetrics()
        
        assert metrics.messages_processed == 0
        assert metrics.messages_failed == 0
        assert metrics.files_processed == 0
        assert metrics.resources_created == 0
        assert metrics.processing_time_total == 0.0
        assert metrics.last_activity is None
        assert metrics.start_time == 0.0
        
    def test_average_processing_time_zero_messages(self):
        """Test average processing time with zero messages."""
        metrics = WorkerMetrics()
        assert metrics.average_processing_time == 0.0
        
    def test_average_processing_time_with_messages(self):
        """Test average processing time calculation."""
        metrics = WorkerMetrics()
        metrics.messages_processed = 10
        metrics.processing_time_total = 50.0
        
        assert metrics.average_processing_time == 5.0
        
    def test_success_rate_no_messages(self):
        """Test success rate with no messages."""
        metrics = WorkerMetrics()
        assert metrics.success_rate == 0.0
        
    def test_success_rate_all_successful(self):
        """Test success rate with all successful messages."""
        metrics = WorkerMetrics()
        metrics.messages_processed = 10
        metrics.messages_failed = 0
        
        assert metrics.success_rate == 100.0
        
    def test_success_rate_mixed(self):
        """Test success rate with mixed results."""
        metrics = WorkerMetrics()
        metrics.messages_processed = 8
        metrics.messages_failed = 2
        
        assert metrics.success_rate == 80.0


class TestStorageEventWorker:
    """Test StorageEventWorker functionality."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock NATS client."""
        client = Mock()
        client.is_connected = True
        return client
        
    @pytest.fixture
    def mock_repository(self):
        """Create mock repository."""
        repo = Mock()
        repo.initialize = AsyncMock()
        repo.get_tenant_info = AsyncMock(return_value={"id": "test-tenant"})
        repo.delete_file = AsyncMock()
        return repo
        
    @pytest.fixture
    def mock_storage_worker(self):
        """Create mock storage worker."""
        worker = Mock()
        worker.process_file = AsyncMock()
        worker.cleanup = AsyncMock()
        return worker
        
    @pytest.fixture
    def worker(self, mock_client):
        """Create worker with mocked dependencies."""
        with patch('p8fs.workers.queues.storage_worker.ConsumerManager') as consumer_mock, \
             patch('p8fs.workers.queues.storage_worker.TenantRepository') as repo_mock, \
             patch('p8fs.workers.queues.storage_worker.StorageWorker') as storage_mock:
            
            worker = StorageEventWorker(QueueSize.SMALL, mock_client, "test-tenant")
            
            # Mock the managers
            worker.consumer_manager = Mock()
            worker.consumer_manager.setup_storage_consumers = AsyncMock()
            worker.consumer_manager.pull_messages = AsyncMock(return_value=[])
            worker.consumer_manager.get_consumer_status = AsyncMock(return_value={})
            
            # Mock repository and storage worker
            worker.repository = Mock()
            worker.repository.initialize = AsyncMock()
            worker.repository.get_tenant_info = AsyncMock(return_value={"id": "test-tenant"})
            worker.repository.delete_file = AsyncMock()
            
            worker.storage_worker = Mock()
            worker.storage_worker.process_file = AsyncMock()
            worker.storage_worker.cleanup = AsyncMock()
            
            return worker
    
    @pytest.mark.asyncio
    async def test_setup(self, worker):
        """Test worker setup."""
        await worker.setup()
        
        assert worker._status == WorkerStatus.STARTING
        worker.repository.initialize.assert_called_once()
        worker.consumer_manager.setup_storage_consumers.assert_called_once()
        assert worker.metrics.start_time > 0
        
    def test_initial_status(self, worker):
        """Test initial worker status."""
        assert worker._status == WorkerStatus.STOPPED
        assert worker._running is False
        assert worker.queue_size == QueueSize.SMALL
        assert worker.tenant_id == "test-tenant"
        
    def test_config_loading(self, worker):
        """Test configuration loading for queue size."""
        assert "timeout" in worker.config
        assert "batch_size" in worker.config
        assert "max_ack_pending" in worker.config
        assert "max_deliver" in worker.config
        
    def test_consumer_name_mapping(self, worker):
        """Test consumer name mapping."""
        assert worker.consumer_name == "small-workers"
        
        # Test other sizes
        medium_worker = StorageEventWorker(QueueSize.MEDIUM, Mock(), "test-tenant")
        assert medium_worker.consumer_name == "medium-workers"
        
        large_worker = StorageEventWorker(QueueSize.LARGE, Mock(), "test-tenant")  
        assert large_worker.consumer_name == "large-workers"
        
    @pytest.mark.asyncio
    async def test_get_status(self, worker):
        """Test status reporting."""
        # Set up some test data
        worker.metrics.messages_processed = 10
        worker.metrics.files_processed = 5
        worker.metrics.start_time = time.time() - 100
        worker._status = WorkerStatus.RUNNING
        worker._running = True
        
        status = await worker.get_status()
        
        assert status["queue_size"] == "small"
        assert status["status"] == "running"
        assert status["running"] is True
        assert status["tenant_id"] == "test-tenant"
        assert status["consumer_name"] == "small-workers"
        assert status["uptime_seconds"] > 0
        assert status["metrics"]["messages_processed"] == 10
        assert status["metrics"]["files_processed"] == 5
        
    @pytest.mark.asyncio 
    async def test_health_check_healthy(self, worker):
        """Test health check with healthy worker."""
        # Set up healthy state
        worker.client.is_connected = True
        worker.repository = Mock()
        worker.repository.get_tenant_info = AsyncMock(return_value={"id": "test-tenant"})
        worker.metrics.last_activity = time.time() - 60  # 1 minute ago
        
        health = await worker.health_check()
        
        assert health["healthy"] is True
        assert health["checks"]["nats_connected"] is True
        assert health["checks"]["repository_connected"] is True
        assert health["checks"]["recent_activity"] is True
        
    @pytest.mark.asyncio
    async def test_health_check_unhealthy_nats(self, worker):
        """Test health check with unhealthy NATS."""
        worker.client.is_connected = False
        worker.repository = Mock()
        worker.repository.get_tenant_info = AsyncMock(return_value={"id": "test-tenant"})
        
        health = await worker.health_check()
        
        assert health["healthy"] is False
        assert health["checks"]["nats_connected"] is False
        
    @pytest.mark.asyncio
    async def test_health_check_unhealthy_repository(self, worker):
        """Test health check with unhealthy repository."""
        worker.client.is_connected = True
        worker.repository = Mock()
        worker.repository.get_tenant_info = AsyncMock(side_effect=Exception("DB error"))
        
        health = await worker.health_check()
        
        assert health["healthy"] is False
        assert health["checks"]["repository_connected"] is False
        assert "repository_error" in health["checks"]
        
    @pytest.mark.asyncio
    async def test_health_check_no_recent_activity(self, worker):
        """Test health check with no recent activity."""
        worker.client.is_connected = True
        worker.repository = Mock()
        worker.repository.get_tenant_info = AsyncMock(return_value={"id": "test-tenant"})
        worker.metrics.last_activity = time.time() - 400  # 6+ minutes ago
        
        health = await worker.health_check()
        
        assert health["checks"]["recent_activity"] is False
        assert health["checks"]["seconds_since_activity"] > 300


class TestWorkerManager:
    """Test WorkerManager functionality."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock NATS client."""
        return Mock()
        
    @pytest.fixture
    def manager(self, mock_client):
        """Create manager with mocked dependencies."""
        return WorkerManager(mock_client, "test-tenant")
    
    def test_initialization(self, manager):
        """Test manager initialization."""
        assert manager.tenant_id == "test-tenant"
        assert len(manager.workers) == 0
        
    @pytest.mark.asyncio
    async def test_setup_worker(self, manager):
        """Test setting up individual worker."""
        with patch('p8fs.workers.queues.storage_worker.StorageEventWorker') as worker_mock:
            mock_worker = Mock()
            mock_worker.setup = AsyncMock()
            worker_mock.return_value = mock_worker
            
            worker = await manager.setup_worker(QueueSize.SMALL)
            
            assert QueueSize.SMALL in manager.workers
            assert worker == mock_worker
            mock_worker.setup.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_setup_worker_already_exists(self, manager):
        """Test setting up worker that already exists."""
        # Add existing worker
        existing_worker = Mock()
        manager.workers[QueueSize.SMALL] = existing_worker
        
        worker = await manager.setup_worker(QueueSize.SMALL)
        
        assert worker == existing_worker
        
    @pytest.mark.asyncio
    async def test_get_status(self, manager):
        """Test getting status of all workers."""
        # Add mock workers
        mock_worker_small = Mock()
        mock_worker_small.get_status = AsyncMock(return_value={
            "running": True,
            "metrics": {"messages_processed": 10, "files_processed": 5}
        })
        
        mock_worker_medium = Mock()
        mock_worker_medium.get_status = AsyncMock(return_value={
            "running": False,
            "metrics": {"messages_processed": 5, "files_processed": 2}
        })
        
        manager.workers[QueueSize.SMALL] = mock_worker_small
        manager.workers[QueueSize.MEDIUM] = mock_worker_medium
        
        status = await manager.get_status()
        
        assert status["tenant_id"] == "test-tenant"
        assert status["summary"]["total_workers"] == 2
        assert status["summary"]["running_workers"] == 1
        assert status["summary"]["total_messages_processed"] == 15
        assert status["summary"]["total_files_processed"] == 7
        assert "small" in status["workers"]
        assert "medium" in status["workers"]