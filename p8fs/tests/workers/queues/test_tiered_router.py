"""Tests for tiered storage router."""

import pytest
pytest.skip("Queue module dependencies not available", allow_module_level=True)

import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from p8fs.workers.queues.config import QueueSubjects
from p8fs.workers.queues.tiered_router import StorageEvent, TieredStorageRouter


class TestStorageEvent:
    """Test StorageEvent data class."""
    
    def test_from_dict(self):
        """Test creating StorageEvent from dictionary."""
        data = {
            "tenant_id": "test-tenant",
            "bucket": "test-bucket", 
            "key": "buckets/test-tenant/file.pdf",
            "operation": "create",
            "file_size": 1024 * 1024,  # 1MB
            "content_type": "application/pdf",
            "timestamp": 1234567890.0
        }
        
        event = StorageEvent.from_dict(data)
        
        assert event.tenant_id == "test-tenant"
        assert event.bucket == "test-bucket"
        assert event.key == "buckets/test-tenant/file.pdf"
        assert event.operation == "create"
        assert event.file_size == 1024 * 1024
        assert event.content_type == "application/pdf"
        assert event.timestamp == 1234567890.0
        
    def test_from_dict_with_defaults(self):
        """Test creating StorageEvent with default values."""
        data = {
            "tenant_id": "test-tenant",
            "bucket": "test-bucket",
            "key": "test-file.txt", 
            "operation": "create"
        }
        
        event = StorageEvent.from_dict(data)
        
        assert event.file_size == 0  # default
        assert event.content_type == ""  # default
        assert event.timestamp > 0  # should be set to current time
        
    def test_to_dict(self):
        """Test converting StorageEvent to dictionary."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket",
            key="test-file.txt",
            operation="create",
            file_size=1024,
            content_type="text/plain",
            timestamp=1234567890.0
        )
        
        data = event.to_dict()
        
        expected = {
            "tenant_id": "test-tenant",
            "bucket": "test-bucket",
            "key": "test-file.txt",
            "operation": "create", 
            "file_size": 1024,
            "content_type": "text/plain",
            "timestamp": 1234567890.0
        }
        
        assert data == expected


class TestTieredStorageRouter:
    """Test TieredStorageRouter functionality."""
    
    @pytest.fixture
    def mock_client(self):
        """Create mock NATS client."""
        client = Mock()
        client.publish_json = AsyncMock()
        return client
        
    @pytest.fixture
    def mock_stream_manager(self):
        """Create mock stream manager."""
        manager = Mock()
        manager.setup_storage_streams = AsyncMock()
        manager.get_stream_status = AsyncMock(return_value={})
        manager.validate_streams = AsyncMock(return_value={})
        return manager
        
    @pytest.fixture
    def mock_consumer_manager(self):
        """Create mock consumer manager."""
        manager = Mock()
        manager.setup_storage_consumers = AsyncMock()
        manager.cleanup_stale_consumers = AsyncMock()
        manager.pull_messages = AsyncMock(return_value=[])
        manager.get_consumer_status = AsyncMock(return_value={})
        manager.validate_consumers = AsyncMock(return_value={})
        return manager
        
    @pytest.fixture
    def router(self, mock_client):
        """Create router with mocked dependencies."""
        with patch('p8fs.workers.queues.tiered_router.StreamManager') as stream_mock, \
             patch('p8fs.workers.queues.tiered_router.ConsumerManager') as consumer_mock:
            
            router = TieredStorageRouter(mock_client)
            router.stream_manager = Mock()
            router.consumer_manager = Mock()
            router.stream_manager.setup_storage_streams = AsyncMock()
            router.stream_manager.get_stream_status = AsyncMock(return_value={})
            router.stream_manager.validate_streams = AsyncMock(return_value={})
            router.consumer_manager.setup_storage_consumers = AsyncMock()
            router.consumer_manager.cleanup_stale_consumers = AsyncMock()
            router.consumer_manager.pull_messages = AsyncMock(return_value=[])
            router.consumer_manager.get_consumer_status = AsyncMock(return_value={})
            router.consumer_manager.validate_consumers = AsyncMock(return_value={})
            
            return router
    
    @pytest.mark.asyncio
    async def test_setup(self, router):
        """Test router setup."""
        await router.setup()
        
        router.stream_manager.setup_storage_streams.assert_called_once()
        router.consumer_manager.setup_storage_consumers.assert_called_once()
        router.consumer_manager.cleanup_stale_consumers.assert_called_once()
        
    def test_should_process_event_valid(self, router):
        """Test processing valid events."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket",
            key="buckets/test-tenant/file.pdf",
            operation="create",
            file_size=1024,
            content_type="application/pdf",
            timestamp=time.time()
        )
        
        assert router._should_process_event(event) is True
        
    def test_should_process_event_multipart_upload(self, router):
        """Test skipping multipart upload events."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket", 
            key="buckets/test-tenant/file.pdf?uploadId=123",
            operation="create",
            file_size=1024,
            content_type="application/pdf",
            timestamp=time.time()
        )
        
        assert router._should_process_event(event) is False
        
    def test_should_process_event_non_tenant_path(self, router):
        """Test skipping non-tenant paths."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket",
            key="global/file.pdf",  # Not tenant-scoped
            operation="create",
            file_size=1024,
            content_type="application/pdf",
            timestamp=time.time()
        )
        
        assert router._should_process_event(event) is False
        
    def test_should_process_event_delete_operation(self, router):
        """Test skipping delete operations."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket",
            key="buckets/test-tenant/file.pdf",
            operation="delete",
            file_size=1024,
            content_type="application/pdf",
            timestamp=time.time()
        )
        
        assert router._should_process_event(event) is False
        
    def test_get_target_subject_small(self, router):
        """Test routing small files."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket",
            key="buckets/test-tenant/small.txt",
            operation="create",
            file_size=1024,  # 1KB - small
            content_type="text/plain",
            timestamp=time.time()
        )
        
        subject = router._get_target_subject(event)
        assert subject == QueueSubjects.STORAGE_EVENTS_SMALL
        
    def test_get_target_subject_medium(self, router):
        """Test routing medium files."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket",
            key="buckets/test-tenant/medium.pdf",
            operation="create",
            file_size=500 * 1024 * 1024,  # 500MB - medium
            content_type="application/pdf",
            timestamp=time.time()
        )
        
        subject = router._get_target_subject(event)
        assert subject == QueueSubjects.STORAGE_EVENTS_MEDIUM
        
    def test_get_target_subject_large(self, router):
        """Test routing large files."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket",
            key="buckets/test-tenant/large.mp4",
            operation="create",
            file_size=2 * 1024 * 1024 * 1024,  # 2GB - large
            content_type="video/mp4",
            timestamp=time.time()
        )
        
        subject = router._get_target_subject(event)
        assert subject == QueueSubjects.STORAGE_EVENTS_LARGE
        
    def test_enrich_event(self, router):
        """Test event enrichment with routing metadata."""
        event = StorageEvent(
            tenant_id="test-tenant",
            bucket="test-bucket",
            key="buckets/test-tenant/file.pdf",
            operation="create",
            file_size=1024,
            content_type="application/pdf",
            timestamp=1234567890.0
        )
        
        target_subject = "p8fs.storage.events.small"
        
        enriched = router._enrich_event(event, target_subject)
        
        # Check original data preserved
        assert enriched["tenant_id"] == event.tenant_id
        assert enriched["bucket"] == event.bucket
        assert enriched["key"] == event.key
        assert enriched["operation"] == event.operation
        assert enriched["file_size"] == event.file_size
        assert enriched["content_type"] == event.content_type
        assert enriched["timestamp"] == event.timestamp
        
        # Check routing metadata added
        assert "routing" in enriched
        routing = enriched["routing"]
        assert routing["target_subject"] == target_subject
        assert routing["queue_size"] == "small"
        assert routing["routed_by"] == "tiered-storage-router"
        assert "router_timestamp" in routing
        
    @pytest.mark.asyncio
    async def test_get_status(self, router):
        """Test status reporting."""
        # Mock return values
        router.stream_manager.get_stream_status.return_value = {"stream1": {"status": "active"}}
        router.consumer_manager.get_consumer_status.return_value = {"consumer1": {"status": "active"}}
        
        status = await router.get_status()
        
        assert "running" in status
        assert "consecutive_errors" in status
        assert "streams" in status
        assert "consumers" in status
        assert status["streams"] == {"stream1": {"status": "active"}}
        assert status["consumers"] == {"consumer1": {"status": "active"}}
        
    @pytest.mark.asyncio
    async def test_validate_setup(self, router):
        """Test setup validation."""
        # Mock return values
        router.stream_manager.validate_streams.return_value = {"stream1": True}
        router.consumer_manager.validate_consumers.return_value = {"consumer1": True}
        
        validation = await router.validate_setup()
        
        assert "streams" in validation
        assert "consumers" in validation  
        assert "all_healthy" in validation
        assert validation["streams"] == {"stream1": True}
        assert validation["consumers"] == {"consumer1": True}
        assert validation["all_healthy"] is True
        
    @pytest.mark.asyncio
    async def test_validate_setup_unhealthy(self, router):
        """Test setup validation with unhealthy components."""
        # Mock return values with some failures
        router.stream_manager.validate_streams.return_value = {"stream1": True, "stream2": False}
        router.consumer_manager.validate_consumers.return_value = {"consumer1": False}
        
        validation = await router.validate_setup()
        
        assert validation["all_healthy"] is False