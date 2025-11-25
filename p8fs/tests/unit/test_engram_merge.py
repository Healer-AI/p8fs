"""Test engram merge behavior."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid5, NAMESPACE_DNS

from p8fs.models.engram.processor import EngramProcessor
from p8fs.models.p8 import Resources, InlineEdge


@pytest.fixture
def mock_repo():
    """Mock TenantRepository."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    repo.upsert = AsyncMock()
    return repo


@pytest.fixture
def processor(mock_repo):
    """Create EngramProcessor with mock repo."""
    return EngramProcessor(mock_repo)


@pytest.mark.asyncio
async def test_engram_create_new(processor, mock_repo):
    """Test creating a new engram."""
    mock_repo.get_by_id.side_effect = Exception("Not found")

    yaml_content = """kind: engram
name: "test-engram"
category: "note"
summary: "Test summary"
content: "Test content"
graph_edges:
  - dst: "project-alpha"
    rel_type: "discusses"
    weight: 0.8
    properties:
      dst_name: "Project Alpha"
"""

    result = await processor.process(yaml_content, "application/x-yaml", "test-tenant")

    assert result["action"] == "created"
    assert result["resource_id"]

    # Processor creates the engram plus lightweight nodes for edges (ensure_nodes=True)
    assert mock_repo.upsert.call_count >= 1

    # Get the main engram resource (last call)
    upserted_resource = mock_repo.upsert.call_args[0][0]
    assert isinstance(upserted_resource, Resources)
    assert upserted_resource.name == "test-engram"
    assert len(upserted_resource.graph_paths) == 1
    assert upserted_resource.graph_paths[0]["dst"] == "project-alpha"


@pytest.mark.asyncio
async def test_engram_merge_graph_edges(processor, mock_repo):
    """Test merging graph edges - new edges should be added, not replaced."""
    tenant_id = "test-tenant"
    engram_name = "test-engram"
    resource_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:engram:{engram_name}"))

    existing_resource = {
        "id": resource_id,
        "tenant_id": tenant_id,
        "name": engram_name,
        "category": "note",
        "content": "Original content",
        "summary": "Original summary",
        "metadata": {"device": {"model": "iPhone"}},
        "graph_paths": [
            {
                "dst": "project-alpha",
                "rel_type": "discusses",
                "weight": 0.8,
                "properties": {"dst_name": "Project Alpha"},
                "created_at": "2025-11-16T10:00:00Z"
            }
        ]
    }

    mock_repo.get_by_id.return_value = existing_resource

    yaml_update = """kind: engram
name: "test-engram"
graph_edges:
  - dst: "sarah-chen"
    rel_type: "attended_by"
    weight: 1.0
    properties:
      dst_name: "Sarah Chen"
"""

    result = await processor.process(yaml_update, "application/x-yaml", tenant_id)

    assert result["action"] == "merged"

    upserted_resource = mock_repo.upsert.call_args[0][0]
    assert len(upserted_resource.graph_paths) == 2

    edge_dsts = [edge["dst"] for edge in upserted_resource.graph_paths]
    assert "project-alpha" in edge_dsts
    assert "sarah-chen" in edge_dsts


@pytest.mark.asyncio
async def test_engram_merge_metadata(processor, mock_repo):
    """Test metadata merging - new keys added, existing updated."""
    tenant_id = "test-tenant"
    engram_name = "test-engram"
    resource_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:engram:{engram_name}"))

    existing_resource = {
        "id": resource_id,
        "tenant_id": tenant_id,
        "name": engram_name,
        "category": "note",
        "content": "Original content",
        "metadata": {
            "device": {"model": "iPhone", "os": "iOS 17"},
            "location": "Office"
        },
        "graph_paths": []
    }

    mock_repo.get_by_id.return_value = existing_resource

    yaml_update = """kind: engram
name: "test-engram"
metadata:
  device:
    os: "iOS 18"
    app: "Percolate"
  tags:
    - "important"
"""

    result = await processor.process(yaml_update, "application/x-yaml", tenant_id)

    upserted_resource = mock_repo.upsert.call_args[0][0]

    assert upserted_resource.metadata["device"]["os"] == "iOS 18"
    assert upserted_resource.metadata["device"]["app"] == "Percolate"
    assert upserted_resource.metadata["tags"] == ["important"]
    assert upserted_resource.metadata["location"] == "Office"


@pytest.mark.asyncio
async def test_engram_merge_update_existing_edge(processor, mock_repo):
    """Test updating an existing edge by dst key."""
    tenant_id = "test-tenant"
    engram_name = "test-engram"
    resource_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:engram:{engram_name}"))

    existing_resource = {
        "id": resource_id,
        "tenant_id": tenant_id,
        "name": engram_name,
        "content": "Original content",
        "graph_paths": [
            {
                "dst": "project-alpha",
                "rel_type": "discusses",
                "weight": 0.5,
                "properties": {"dst_name": "Project Alpha", "confidence": 0.5},
                "created_at": "2025-11-16T10:00:00Z"
            }
        ]
    }

    mock_repo.get_by_id.return_value = existing_resource

    yaml_update = """kind: engram
name: "test-engram"
graph_edges:
  - dst: "project-alpha"
    rel_type: "implements"
    weight: 0.9
    properties:
      confidence: 0.9
      notes: "Updated relationship"
"""

    result = await processor.process(yaml_update, "application/x-yaml", tenant_id)

    upserted_resource = mock_repo.upsert.call_args[0][0]
    assert len(upserted_resource.graph_paths) == 1

    edge = upserted_resource.graph_paths[0]
    assert edge["dst"] == "project-alpha"
    assert edge["rel_type"] == "implements"
    assert edge["weight"] == 0.9
    assert edge["properties"]["confidence"] == 0.9
    assert edge["properties"]["notes"] == "Updated relationship"


@pytest.mark.asyncio
async def test_engram_merge_preserves_content_if_not_provided(processor, mock_repo):
    """Test that content/summary are preserved if not in update."""
    tenant_id = "test-tenant"
    engram_name = "test-engram"
    resource_id = str(uuid5(NAMESPACE_DNS, f"{tenant_id}:engram:{engram_name}"))

    existing_resource = {
        "id": resource_id,
        "tenant_id": tenant_id,
        "name": engram_name,
        "content": "Original content",
        "summary": "Original summary",
        "resource_timestamp": "2025-11-16T10:00:00Z",
        "graph_paths": []
    }

    mock_repo.get_by_id.return_value = existing_resource

    yaml_update = """kind: engram
name: "test-engram"
metadata:
  new_field: "new value"
"""

    result = await processor.process(yaml_update, "application/x-yaml", tenant_id)

    upserted_resource = mock_repo.upsert.call_args[0][0]
    assert upserted_resource.content == "Original content"
    assert upserted_resource.summary == "Original summary"
    assert upserted_resource.resource_timestamp.isoformat() == "2025-11-16T10:00:00+00:00"
    assert upserted_resource.metadata["new_field"] == "new value"


@pytest.mark.asyncio
async def test_merge_graph_edges_function():
    """Test the _merge_graph_edges function directly."""
    processor = EngramProcessor(MagicMock())

    existing_edges = [
        {
            "dst": "edge-1",
            "rel_type": "type-a",
            "weight": 0.5,
            "properties": {"prop1": "value1"},
            "created_at": "2025-11-16T10:00:00Z"
        },
        {
            "dst": "edge-2",
            "rel_type": "type-b",
            "weight": 0.7,
            "properties": {},
            "created_at": "2025-11-16T11:00:00Z"
        }
    ]

    new_edges = [
        {
            "dst": "edge-1",
            "rel_type": "type-a-updated",
            "weight": 0.9,
            "properties": {"prop2": "value2"},
            "created_at": "2025-11-16T12:00:00Z"
        },
        {
            "dst": "edge-3",
            "rel_type": "type-c",
            "weight": 0.6,
            "properties": {"prop3": "value3"},
            "created_at": "2025-11-16T13:00:00Z"
        }
    ]

    merged = processor._merge_graph_edges(existing_edges, new_edges)

    assert len(merged) == 3

    edge_map = {edge["dst"]: edge for edge in merged}

    assert edge_map["edge-1"]["rel_type"] == "type-a-updated"
    assert edge_map["edge-1"]["weight"] == 0.9
    assert edge_map["edge-1"]["properties"]["prop1"] == "value1"
    assert edge_map["edge-1"]["properties"]["prop2"] == "value2"

    assert edge_map["edge-2"]["rel_type"] == "type-b"

    assert edge_map["edge-3"]["rel_type"] == "type-c"
    assert edge_map["edge-3"]["weight"] == 0.6
