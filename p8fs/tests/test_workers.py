"""Basic tests for workers."""

from datetime import datetime
from uuid import uuid4

import pytest
from p8fs.models.engram.models import EngramDocument, EngramMetadata, EngramSpec
from p8fs.workers.dreaming import DreamJob, ProcessingMode


def test_engram_document_creation():
    """Test creating an Engram document."""
    doc = EngramDocument(
        kind="engram",
        metadata=EngramMetadata(
            name="test-engram",
            summary="Test summary"
        ),
        spec=EngramSpec()
    )
    
    assert doc.is_engram()
    assert doc.metadata.name == "test-engram"
    assert doc.metadata.entityType == "engram"


def test_dream_job_creation():
    """Test creating a dream job."""
    job = DreamJob(
        id=str(uuid4()),
        tenant_id="test-tenant",
        mode=ProcessingMode.BATCH
    )
    
    assert job.status == "pending"
    assert job.mode == ProcessingMode.BATCH
    assert isinstance(job.created_at, datetime)
    assert job.completed_at is None


def test_engram_metadata_extra_fields():
    """Test that Engram metadata accepts extra fields."""
    metadata = EngramMetadata(
        name="test",
        extra_field="value",
        another_field=123
    )
    
    assert metadata.name == "test"
    assert metadata.model_dump()["extra_field"] == "value"
    assert metadata.model_dump()["another_field"] == 123


if __name__ == "__main__":
    pytest.main([__file__])