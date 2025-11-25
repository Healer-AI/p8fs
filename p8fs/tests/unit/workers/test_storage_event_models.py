"""Unit tests for storage event models.

These tests ensure robust handling of real-world event data from SeaweedFS/gRPC.
"""
import pytest
from p8fs.workers.queues.models import StorageEvent, StorageEventType


class TestStorageEventTypeConversion:
    """Test type conversions for fields that may arrive as strings."""

    def test_timestamp_as_float(self):
        """Test timestamp conversion when provided as float."""
        raw_event = {
            'event_type': 'create',
            'path': 'buckets/tenant-test/uploads/file.txt',
            'timestamp': 1731625732.123,  # Float
            'file_size': 1024
        }

        event = StorageEvent.from_raw_event(raw_event)
        assert isinstance(event.timestamp, float)
        assert event.timestamp == 1731625732.123

    def test_timestamp_as_string(self):
        """Test timestamp conversion when provided as string (real SeaweedFS behavior)."""
        raw_event = {
            'event_type': 'create',
            'path': 'buckets/tenant-test/uploads/file.txt',
            'timestamp': '1731625732.123',  # String - like real gRPC/JSON events
            'file_size': '1024'
        }

        event = StorageEvent.from_raw_event(raw_event)
        assert isinstance(event.timestamp, float)
        assert event.timestamp == 1731625732.123

    def test_timestamp_as_integer_string(self):
        """Test timestamp conversion with integer string."""
        raw_event = {
            'event_type': 'create',
            'path': 'buckets/tenant-test/uploads/document.pdf',
            'timestamp': '1731625732',  # Integer string
            'file_size': 2048
        }

        event = StorageEvent.from_raw_event(raw_event)
        assert isinstance(event.timestamp, float)
        assert event.timestamp == 1731625732.0

    def test_file_size_as_string(self):
        """Test file_size conversion when provided as string."""
        raw_event = {
            'event_type': 'create',
            'path': 'buckets/tenant-test/uploads/image.jpg',
            'timestamp': 1731625732.0,
            'file_size': '524288'  # String
        }

        event = StorageEvent.from_raw_event(raw_event)
        assert isinstance(event.metadata.file_size, int)
        assert event.metadata.file_size == 524288


class TestStorageEventValidation:
    """Test validation rules for StorageEvent."""

    def test_rejects_non_tenant_path(self):
        """Test that non-tenant paths are rejected."""
        raw_event = {
            'event_type': 'create',
            'path': '/uploads/file.txt',  # Missing buckets/{tenant_id}/
            'timestamp': 1731625732.0,
            'file_size': 1024
        }

        with pytest.raises(ValueError, match="Non-tenant paths not supported"):
            StorageEvent.from_raw_event(raw_event)

    def test_rejects_directory_events(self):
        """Test that directory events are rejected."""
        raw_event = {
            'event_type': 'create',
            'path': 'buckets/tenant-test/uploads/',  # Directory (trailing slash)
            'timestamp': 1731625732.0,
            'file_size': 0
        }

        with pytest.raises(ValueError, match="Directory events not supported"):
            StorageEvent.from_raw_event(raw_event)


class TestStorageEventCreation:
    """Test StorageEvent creation from various event formats."""

    def test_create_from_seaweedfs_event(self):
        """Test creation from realistic SeaweedFS gRPC event."""
        raw_event = {
            'event_type': 'create',
            'path': 'buckets/tenant-prod/documents/report.pdf',
            'timestamp': '1731625732.456',  # String timestamp from gRPC
            'file_size': '1048576',  # String size from gRPC
            'content_type': 'application/pdf',
            'etag': 'abc123'
        }

        event = StorageEvent.from_raw_event(raw_event)

        assert event.event_type == StorageEventType.CREATE
        assert event.tenant_id == 'tenant-prod'
        assert event.path_info.category == 'documents'
        assert event.path_info.file_path == 'report.pdf'
        assert isinstance(event.timestamp, float)
        assert event.timestamp > 0
        assert event.metadata.file_size == 1048576
        assert event.metadata.content_type == 'application/pdf'

    def test_handles_missing_optional_fields(self):
        """Test that missing optional fields don't cause errors."""
        raw_event = {
            'event_type': 'create',
            'path': 'buckets/tenant-test/uploads/file.txt',
            'timestamp': '1731625732.0'
            # Missing file_size, content_type, etc.
        }

        event = StorageEvent.from_raw_event(raw_event)

        assert event.metadata.file_size == 0  # Default
        assert event.metadata.content_type is None
        assert event.metadata.etag is None
