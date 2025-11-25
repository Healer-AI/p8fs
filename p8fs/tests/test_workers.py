"""Basic tests for workers."""

from datetime import datetime
from uuid import uuid4

import pytest
from p8fs.workers.dreaming import DreamJob, ProcessingMode


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


if __name__ == "__main__":
    pytest.main([__file__])