"""Tests for storage event models."""

import pytest
pytest.skip("Queue module dependencies not available", allow_module_level=True)

from p8fs.workers.queues.models import (
    StorageEvent,
    StorageEventMetadata,
    StorageEventType,
    StoragePathInfo,
)
from pydantic import ValidationError


class TestStoragePathInfo:
    """Test StoragePathInfo path parsing."""
    
    def test_tenant_path_parsing(self):
        """Test parsing tenant paths."""
        path_info = StoragePathInfo.from_full_path("/buckets/tenant-123/documents/file.pdf")
        
        assert path_info.is_tenant_path is True
        assert path_info.tenant_id == "tenant-123"
        assert path_info.bucket == "buckets"
        assert path_info.category == "documents"
        assert path_info.file_path == "file.pdf"
        assert path_info.is_directory is False
        
    def test_tenant_path_without_leading_slash(self):
        """Test parsing tenant paths without leading slash."""
        path_info = StoragePathInfo.from_full_path("buckets/tenant-456/images/photo.jpg")
        
        assert path_info.is_tenant_path is True
        assert path_info.tenant_id == "tenant-456"
        assert path_info.category == "images"
        assert path_info.file_path == "photo.jpg"
        
    def test_directory_path(self):
        """Test parsing directory paths."""
        path_info = StoragePathInfo.from_full_path("buckets/tenant-789/documents/")
        
        assert path_info.is_tenant_path is True
        assert path_info.tenant_id == "tenant-789"
        assert path_info.category == "documents"
        assert path_info.file_path is None
        assert path_info.is_directory is True
        
    def test_non_tenant_path(self):
        """Test parsing non-tenant paths."""
        path_info = StoragePathInfo.from_full_path("/system/config.txt")
        
        assert path_info.is_tenant_path is False
        assert path_info.tenant_id is None
        assert path_info.bucket is None
        assert path_info.category is None
        assert path_info.file_path is None
        
    def test_root_tenant_path(self):
        """Test parsing root tenant paths."""
        path_info = StoragePathInfo.from_full_path("buckets/tenant-999/")
        
        assert path_info.is_tenant_path is True
        assert path_info.tenant_id == "tenant-999"
        assert path_info.category is None
        assert path_info.file_path is None
        assert path_info.is_directory is True


class TestStorageEventMetadata:
    """Test StorageEventMetadata validation."""
    
    def test_default_values(self):
        """Test default metadata values."""
        metadata = StorageEventMetadata()
        
        assert metadata.file_size == 0
        assert metadata.content_type is None
        assert metadata.last_modified is None
        assert metadata.etag is None
        assert metadata.source == "unknown"
        
    def test_negative_file_size_validation(self):
        """Test file size validation."""
        with pytest.raises(ValidationError):
            StorageEventMetadata(file_size=-1)
            
    def test_valid_metadata(self):
        """Test valid metadata creation."""
        metadata = StorageEventMetadata(
            file_size=1024,
            content_type="application/pdf",
            last_modified="2023-01-01T00:00:00Z",
            etag="abc123",
            source="seaweedfs"
        )
        
        assert metadata.file_size == 1024
        assert metadata.content_type == "application/pdf"
        assert metadata.source == "seaweedfs"


class TestStorageEvent:
    """Test StorageEvent model validation."""
    
    def test_from_raw_event_valid(self):
        """Test creating StorageEvent from valid raw data."""
        raw_event = {
            "type": "create",
            "path": "buckets/tenant-123/documents/test.pdf",
            "file_size": 2048,
            "content_type": "application/pdf",
            "timestamp": 1234567890.0
        }
        
        event = StorageEvent.from_raw_event(raw_event)
        
        assert event.event_type == StorageEventType.CREATE
        assert event.path == "buckets/tenant-123/documents/test.pdf"
        assert event.tenant_id == "tenant-123"
        assert event.relative_path == "documents/test.pdf"
        assert event.metadata.file_size == 2048
        assert event.metadata.content_type == "application/pdf"
        assert event.timestamp == 1234567890.0
        
    def test_from_raw_event_operation_alias(self):
        """Test event type aliases."""
        raw_event = {
            "operation": "put",  # Should be mapped to CREATE
            "key": "buckets/tenant-456/files/data.txt",
            "timestamp": 1234567890.0
        }
        
        event = StorageEvent.from_raw_event(raw_event)
        assert event.event_type == StorageEventType.CREATE
        
    def test_from_raw_event_invalid_path(self):
        """Test handling invalid paths."""
        raw_event = {
            "type": "create",
            "path": "/system/config.txt",  # Non-tenant path
            "timestamp": 1234567890.0
        }
        
        with pytest.raises(ValueError, match="Non-tenant paths not supported"):
            StorageEvent.from_raw_event(raw_event)
            
    def test_from_raw_event_directory(self):
        """Test handling directory events."""
        raw_event = {
            "type": "create",
            "path": "buckets/tenant-123/documents/",  # Directory
            "timestamp": 1234567890.0
        }
        
        with pytest.raises(ValueError, match="Directory events not supported"):
            StorageEvent.from_raw_event(raw_event)
            
    def test_from_raw_event_no_path(self):
        """Test handling events without paths."""
        raw_event = {
            "type": "create",
            "timestamp": 1234567890.0
        }
        
        with pytest.raises(ValueError, match="No path found in event data"):
            StorageEvent.from_raw_event(raw_event)
            
    def test_should_process_valid_event(self):
        """Test processing validation for valid events."""
        raw_event = {
            "type": "create",
            "path": "buckets/tenant-123/documents/test.pdf",
            "timestamp": 1234567890.0
        }
        
        event = StorageEvent.from_raw_event(raw_event)
        assert event.should_process() is True
        
    def test_should_process_multipart_upload(self):
        """Test skipping multipart uploads."""
        raw_event = {
            "type": "create",
            "path": "buckets/tenant-123/documents/test.pdf?uploadId=abc123",
            "timestamp": 1234567890.0
        }
        
        event = StorageEvent.from_raw_event(raw_event)
        assert event.should_process() is False
        
    def test_should_process_delete_operation(self):
        """Test skipping delete operations."""
        raw_event = {
            "type": "delete",
            "path": "buckets/tenant-123/documents/test.pdf",
            "timestamp": 1234567890.0
        }
        
        event = StorageEvent.from_raw_event(raw_event)
        assert event.should_process() is False
        
    def test_to_legacy_format(self):
        """Test conversion to legacy format."""
        raw_event = {
            "type": "create",
            "path": "buckets/tenant-123/documents/test.pdf",
            "file_size": 1024,
            "content_type": "application/pdf",
            "timestamp": 1234567890.0
        }
        
        event = StorageEvent.from_raw_event(raw_event)
        legacy = event.to_legacy_format()
        
        expected = {
            "tenant_id": "tenant-123",
            "file_path": "documents/test.pdf",
            "operation": "create",
            "size": 1024,
            "mime_type": "application/pdf",
            "s3_key": "buckets/tenant-123/documents/test.pdf"
        }
        
        assert legacy == expected


class TestStorageEventType:
    """Test StorageEventType enum."""
    
    def test_enum_values(self):
        """Test enum values."""
        assert StorageEventType.CREATE.value == "create"
        assert StorageEventType.UPDATE.value == "update"
        assert StorageEventType.DELETE.value == "delete"
        assert StorageEventType.RENAME.value == "rename"