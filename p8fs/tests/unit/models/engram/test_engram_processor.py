"""Unit tests for EngramProcessor."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from p8fs.models.engram.processor import EngramProcessor
from p8fs.models.p8 import Resources, InlineEdge
from p8fs.repository.TenantRepository import TenantRepository


@pytest.fixture
def mock_repository():
    """Create a mock repository."""
    repo = Mock(spec=TenantRepository)
    repo.upsert = AsyncMock()
    repo.provider = Mock()
    repo.tenant_id = "tenant-test"
    return repo


@pytest.fixture
def engram_processor(mock_repository):
    """Create an engram processor with ensure_nodes enabled."""
    return EngramProcessor(mock_repository, ensure_nodes=True)


@pytest.fixture
def engram_processor_no_ensure(mock_repository):
    """Create an engram processor with ensure_nodes disabled."""
    return EngramProcessor(mock_repository, ensure_nodes=False)


@pytest.fixture
def sample_engram_yaml():
    """Sample engram YAML content (new format)."""
    return """
kind: engram
name: Test Meeting
category: meeting
content: |
  Discussion about project planning and resource allocation.
summary: Team planning session
resource_timestamp: "2024-11-16T10:00:00Z"

graph_edges:
  - dst: Sarah Chen
    rel_type: attended_by
    weight: 1.0
    properties:
      dst_entity_type: person/supervisor
      confidence: 1.0

  - dst: Project Alpha
    rel_type: discusses
    weight: 0.9
    properties:
      dst_entity_type: resource:project/technical
      confidence: 0.95
"""


@pytest.fixture
def sample_engram_with_moments():
    """Sample engram with moments."""
    return """
kind: engram
name: Weekly Standup
category: meeting
content: Team status update

graph_edges:
  - dst: Team Lead
    rel_type: attended_by
    weight: 1.0
    properties:
      dst_entity_type: person/lead

moments:
  - name: Project Update
    moment_type: insight
    content: Discussed new feature requirements
    emotion_tags: ["focused"]
    topic_tags: ["planning"]
"""


@pytest.mark.asyncio
async def test_process_basic_engram(engram_processor, mock_repository, sample_engram_yaml):
    """Test processing a basic engram without moments."""
    tenant_id = "tenant-test"

    result = await engram_processor.process(
        sample_engram_yaml,
        "application/x-yaml",
        tenant_id
    )

    # Verify result structure
    assert "resource_id" in result
    assert result["chunks_created"] == 1
    assert result["moment_ids"] == []

    # Verify repository upsert was called for main resource
    assert mock_repository.upsert.call_count >= 1  # At least main resource


@pytest.mark.asyncio
async def test_process_engram_with_moments(engram_processor, mock_repository, sample_engram_with_moments):
    """Test processing an engram with attached moments."""
    tenant_id = "tenant-test"

    # Create a mock for the Moment TenantRepository
    mock_moment_repo = Mock(spec=TenantRepository)
    mock_moment_repo.upsert = AsyncMock()

    # Patch TenantRepository in p8fs.repository (where it's imported from in _process_moments)
    with patch('p8fs.repository.TenantRepository') as mock_tenant_repo_class:
        def tenant_repo_factory(model_class, tenant_id, *args, **kwargs):
            # Return mock for Moment repository, real mock_repository for Resources
            if model_class.__name__ == "Moment":
                return mock_moment_repo
            else:
                # This shouldn't be called as engram_processor already has its repo
                return mock_repository

        mock_tenant_repo_class.side_effect = tenant_repo_factory

        result = await engram_processor.process(
            sample_engram_with_moments,
            "application/x-yaml",
            tenant_id
        )

        # Verify moments were created
        assert len(result["moment_ids"]) == 1
        # Verify moment repository was used
        mock_moment_repo.upsert.assert_called_once()
        # Main resource upsert (engram itself)
        assert mock_repository.upsert.call_count >= 1


@pytest.mark.asyncio
async def test_ensure_nodes_enabled(engram_processor, mock_repository, sample_engram_yaml):
    """Test that ensure_nodes=True creates referenced entities."""
    tenant_id = "tenant-test"

    await engram_processor.process(
        sample_engram_yaml,
        "application/x-yaml",
        tenant_id
    )

    # Should call upsert for:
    # 1. Main resource (Test Meeting)
    # 2. Sarah Chen node
    # 3. Project Alpha node
    assert mock_repository.upsert.call_count >= 3


@pytest.mark.asyncio
async def test_ensure_nodes_disabled(engram_processor_no_ensure, mock_repository, sample_engram_yaml):
    """Test that ensure_nodes=False does not create referenced entities."""
    tenant_id = "tenant-test"

    await engram_processor_no_ensure.process(
        sample_engram_yaml,
        "application/x-yaml",
        tenant_id
    )

    # Should only call upsert for main resource (Test Meeting)
    # Not for Sarah Chen or Project Alpha
    assert mock_repository.upsert.call_count == 1


def test_parse_entity_type():
    """Test InlineEdge entity type parsing."""
    # Test default to resources
    edge = InlineEdge(
        dst="Test",
        rel_type="test",
        properties={"dst_entity_type": "person/supervisor"}
    )
    table, category = edge.parse_entity_type()
    assert table == "resources"
    assert category == "person/supervisor"

    # Test explicit table
    edge = InlineEdge(
        dst="Test",
        rel_type="test",
        properties={"dst_entity_type": "moments:reflection"}
    )
    table, category = edge.parse_entity_type()
    assert table == "moments"
    assert category == "reflection"

    # Test resource table explicit
    edge = InlineEdge(
        dst="Test",
        rel_type="test",
        properties={"dst_entity_type": "resource:project/technical"}
    )
    table, category = edge.parse_entity_type()
    assert table == "resource"
    assert category == "project/technical"


def test_create_node_data_with_reverse_edge():
    """Test creating node data with reverse edge."""
    edge = InlineEdge(
        dst="Sarah Chen",
        rel_type="managed_by",
        weight=0.9,
        properties={"dst_entity_type": "person/supervisor"}
    )

    node_data = edge.create_node_data(
        tenant_id="tenant-test",
        add_reverse_edge=True,
        source_name="Project Meeting"
    )

    # Verify node properties
    assert node_data["name"] == "Sarah Chen"
    assert node_data["category"] == "person/supervisor"
    assert node_data["metadata"]["is_lightweight"] is True

    # Verify reverse edge
    assert len(node_data["graph_paths"]) == 1
    reverse_edge = node_data["graph_paths"][0]
    assert reverse_edge["rel_type"] == "inv-managed_by"
    assert reverse_edge["dst"] == "Project Meeting"
    assert reverse_edge["properties"]["inverse_of"] == "managed_by"


def test_create_node_data_without_reverse_edge():
    """Test creating node data without reverse edge."""
    edge = InlineEdge(
        dst="Project Alpha",
        rel_type="references",
        weight=0.7,
        properties={"dst_entity_type": "project"}
    )

    node_data = edge.create_node_data(
        tenant_id="tenant-test",
        add_reverse_edge=False
    )

    # No reverse edges
    assert len(node_data["graph_paths"]) == 0


@pytest.mark.asyncio
async def test_invalid_engram_kind(engram_processor, mock_repository):
    """Test that invalid engram kind raises error."""
    invalid_yaml = """
kind: not-an-engram
name: Test
"""
    with pytest.raises(ValueError, match="Expected kind='engram'"):
        await engram_processor.process(
            invalid_yaml,
            "application/x-yaml",
            "tenant-test"
        )


@pytest.mark.asyncio
async def test_malformed_yaml(engram_processor, mock_repository):
    """Test that malformed YAML raises error."""
    malformed = "this is not: valid: yaml: content:"

    with pytest.raises(Exception):  # YAML parsing error
        await engram_processor.process(
            malformed,
            "application/x-yaml",
            "tenant-test"
        )
