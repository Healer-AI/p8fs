"""Unit tests for EngramProcessor."""

import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from p8fs.models.engram.models import EngramDocument, EngramMetadata, EngramSpec
from p8fs.models.engram.processor import EngramProcessor
from p8fs.repository import TenantRepository


@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    repo = Mock(spec=TenantRepository)
    repo.create_resource = AsyncMock()
    repo.create_moment = AsyncMock()
    return repo


@pytest.fixture
def engram_processor(mock_repository):
    """Create an engram processor instance."""
    return EngramProcessor(mock_repository)


@pytest.fixture
def sample_engram_yaml():
    """Sample Engram YAML content."""
    return """
kind: engram
metadata:
  name: test-engram
  summary: Test Engram document
spec:
  upserts:
    - id: entity1
      entityType: resource
      content: Test resource content
    - id: entity2
      entityType: moment
      startTime: "2024-01-01T00:00:00Z"
      endTime: "2024-01-01T01:00:00Z"
      content: Test moment content
"""


@pytest.fixture
def sample_engram_json():
    """Sample Engram JSON content."""
    return json.dumps({
        "kind": "engram",
        "metadata": {
            "name": "test-engram",
            "summary": "Test Engram document"
        },
        "spec": {
            "upserts": [{
                "id": "entity1",
                "entityType": "resource",
                "content": "Test resource content"
            }]
        }
    })


@pytest.mark.asyncio
async def test_process_valid_engram_yaml(engram_processor, mock_repository, sample_engram_yaml):
    """Test processing a valid Engram YAML document."""
    tenant_id = "test-tenant"
    session_id = uuid4()
    
    result = await engram_processor.process(
        sample_engram_yaml,
        "application/x-yaml",
        tenant_id,
        session_id
    )
    
    assert result["engram_id"] is not None
    assert result["upserts"] == 2
    assert result["patches"] == 0
    assert result["associations"] == 0
    
    # Verify Engram was stored
    assert mock_repository.create_resource.call_count >= 1
    
    # Verify upserts were processed
    assert mock_repository.create_moment.call_count == 1


@pytest.mark.asyncio
async def test_process_valid_engram_json(engram_processor, mock_repository, sample_engram_json):
    """Test processing a valid Engram JSON document."""
    tenant_id = "test-tenant"
    
    result = await engram_processor.process(
        sample_engram_json,
        "application/json",
        tenant_id
    )
    
    assert result["engram_id"] is not None
    assert result["upserts"] == 1
    
    # Verify resource was created
    assert mock_repository.create_resource.call_count >= 1


@pytest.mark.asyncio
async def test_process_engram_without_summary(engram_processor, mock_repository):
    """Test processing an Engram without a summary doesn't store the Engram itself."""
    content = json.dumps({
        "kind": "engram",
        "metadata": {
            "name": "test-engram"
            # No summary
        },
        "spec": {
            "upserts": [{
                "id": "entity1",
                "content": "Test content"
            }]
        }
    })
    
    result = await engram_processor.process(content, "application/json", "test-tenant")
    
    assert result["engram_id"] is None
    assert result["upserts"] == 1
    
    # Only the upserted resource should be created, not the Engram
    assert mock_repository.create_resource.call_count == 1


@pytest.mark.asyncio
async def test_process_non_engram_json(engram_processor, mock_repository):
    """Test processing non-Engram JSON content."""
    content = json.dumps({
        "type": "regular",
        "data": "some data"
    })
    
    result = await engram_processor.process(content, "application/json", "test-tenant")
    
    assert "resource_id" in result
    assert mock_repository.create_resource.call_count == 1
    
    # Verify it was stored as regular resource
    call_args = mock_repository.create_resource.call_args[0][0]
    assert call_args["content_type"] == "application/json"


@pytest.mark.asyncio
async def test_process_invalid_yaml(engram_processor, mock_repository):
    """Test handling invalid YAML content."""
    content = "invalid: yaml: content:"
    
    with pytest.raises(Exception):
        await engram_processor.process(content, "application/x-yaml", "test-tenant")


@pytest.mark.asyncio
async def test_process_upserts_resource_type(engram_processor, mock_repository):
    """Test processing upserts with resource type."""
    upserts = [{
        "id": "test-id",
        "entityType": "resource",
        "content": "Test content",
        "metadata": {"key": "value"}
    }]
    
    count = await engram_processor._process_upserts(upserts, "test-tenant", uuid4())
    
    assert count == 1
    mock_repository.create_resource.assert_called_once()
    
    call_args = mock_repository.create_resource.call_args[0][0]
    assert call_args["id"] == "test-id"
    assert call_args["metadata"] == {"key": "value"}


@pytest.mark.asyncio
async def test_process_upserts_moment_type(engram_processor, mock_repository):
    """Test processing upserts with moment type."""
    session_id = uuid4()
    upserts = [{
        "id": "moment-id",
        "entityType": "moment",
        "startTime": "2024-01-01T00:00:00Z",
        "endTime": "2024-01-01T01:00:00Z",
        "content": "Moment content",
        "metadata": {"tag": "important"}
    }]
    
    count = await engram_processor._process_upserts(upserts, "test-tenant", session_id)
    
    assert count == 1
    mock_repository.create_moment.assert_called_once()
    
    call_args = mock_repository.create_moment.call_args[0][0]
    assert call_args["id"] == "a236b2f2-f596-5c87-b6fa-56f0fb53124a"
    assert call_args["content"] == "Moment content"
    assert call_args["metadata"] == {"tag": "important"}


@pytest.mark.asyncio
async def test_process_upserts_generates_ids(engram_processor, mock_repository):
    """Test that upserts without IDs get generated IDs."""
    upserts = [{
        "entityType": "resource",
        "content": "No ID content"
    }]
    
    count = await engram_processor._process_upserts(upserts, "test-tenant", None)
    
    assert count == 1
    call_args = mock_repository.create_resource.call_args[0][0]
    assert call_args["id"] is not None
    assert len(call_args["id"]) == 36  # UUID string length


def test_engram_document_is_engram():
    """Test EngramDocument.is_engram() method."""
    # Test with kind
    doc1 = EngramDocument(
        kind="engram",
        metadata=EngramMetadata(name="test"),
        spec=EngramSpec()
    )
    assert doc1.is_engram()
    
    # Test with p8Kind
    doc2 = EngramDocument(
        p8Kind="engram",
        metadata=EngramMetadata(name="test"),
        spec=EngramSpec()
    )
    assert doc2.is_engram()
    
    # Test with wrong kind
    doc3 = EngramDocument(
        kind="other",
        metadata=EngramMetadata(name="test"),
        spec=EngramSpec()
    )
    assert not doc3.is_engram()


def test_engram_metadata_extra_fields():
    """Test that EngramMetadata accepts extra fields."""
    metadata = EngramMetadata(
        name="test",
        customField="value",
        anotherField=123
    )
    
    data = metadata.model_dump()
    assert data["name"] == "test"
    assert data["customField"] == "value"
    assert data["anotherField"] == 123