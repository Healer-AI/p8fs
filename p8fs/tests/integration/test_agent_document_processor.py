"""Integration tests for AgentDocumentProcessor and AgentLoader."""

import json
import time
from pathlib import Path

import pytest

from p8fs.models.p8 import Resources
from p8fs.repository import TenantRepository
from p8fs.workers.processors import ProcessorRegistry
from p8fs.services.agent_loader import AgentLoader


@pytest.mark.integration
async def test_agent_document_processor_json():
    """Test processing a JSON agent schema document."""
    tenant_id = f"test-agent-{int(time.time())}"

    # Sample agent schema in JSON format
    agent_data = {
        "p8-type": "agent",
        "short_name": "test_qa_agent",
        "name": "Test QA Agent",
        "title": "Test QA Agent",
        "version": "1.0.0",
        "description": "A test agent for question answering",
        "fully_qualified_name": "test.agents.test_qa_agent",
        "use_in_dreaming": True,
        "properties": {
            "answer": {
                "type": "string",
                "description": "The answer to the question"
            },
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Confidence score"
            }
        },
        "required": ["answer"],
        "tools": [
            {
                "name": "search",
                "description": "Search the knowledge base"
            }
        ]
    }

    # Convert to JSON string
    content = json.dumps(agent_data)
    content_type = "application/json"

    # Initialize processor registry
    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    registry = ProcessorRegistry(resources_repo)

    # Process the document
    result = await registry.process_document(content, content_type, tenant_id)

    # Verify result
    assert result["processor_used"] == "agent"
    assert result["agent_name"] == "test_qa_agent"
    assert result["version"] == "1.0.0"
    assert result["use_in_dreaming"] is True
    assert "resource_id" in result

    resource_id = result["resource_id"]

    # Verify resource was created in database by using raw SQL
    # (Avoids Pydantic deserialization issues with JSONB fields)
    from p8fs.providers import get_provider
    provider = get_provider()
    rows = provider.execute(
        "SELECT * FROM resources WHERE id = %s",
        (resource_id,)
    )

    assert len(rows) == 1
    resource = rows[0]
    assert resource["name"] == "test_qa_agent"
    assert resource["category"] == "agent"
    assert resource["summary"] == "A test agent for question answering"

    # Parse metadata
    import json as json_lib
    metadata = json_lib.loads(resource["metadata"]) if isinstance(resource["metadata"], str) else resource["metadata"]
    assert metadata["version"] == "1.0.0"
    assert metadata["use_in_dreaming"] is True
    assert metadata["fully_qualified_name"] == "test.agents.test_qa_agent"
    assert "answer" in metadata["properties"]
    assert "confidence" in metadata["properties"]
    assert len(metadata["tools"]) == 1

    # Verify content is valid JSON schema
    stored_schema = json.loads(resource["content"])
    assert stored_schema["short_name"] == "test_qa_agent"
    assert stored_schema["version"] == "1.0.0"
    assert stored_schema["use_in_dreaming"] is True

    # Clean up
    await resources_repo.delete(resource_id)


@pytest.mark.integration
async def test_agent_document_processor_yaml():
    """Test processing a YAML agent schema document."""
    tenant_id = f"test-agent-yaml-{int(time.time())}"

    # Sample agent schema in YAML format
    yaml_content = """
p8-type: agent
short_name: yaml_test_agent
name: YAML Test Agent
title: YAML Test Agent
version: 2.0.0
description: A test agent defined in YAML
fully_qualified_name: test.agents.yaml_test_agent
use_in_dreaming: false
properties:
  result:
    type: string
    description: The result
required:
  - result
"""

    content_type = "application/x-yaml"

    # Initialize processor registry
    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    registry = ProcessorRegistry(resources_repo)

    # Process the document
    result = await registry.process_document(yaml_content, content_type, tenant_id)

    # Verify result
    assert result["processor_used"] == "agent"
    assert result["agent_name"] == "yaml_test_agent"
    assert result["version"] == "2.0.0"
    assert result["use_in_dreaming"] is False

    # Verify using AgentLoader
    loader = AgentLoader(tenant_id)
    agent = await loader.load_agent_by_name("yaml_test_agent")

    assert agent is not None
    assert agent["short_name"] == "yaml_test_agent"
    assert agent["version"] == "2.0.0"
    assert agent["use_in_dreaming"] is False

    # Clean up
    resource_id = result["resource_id"]
    await resources_repo.delete(resource_id)


@pytest.mark.integration
async def test_agent_document_processor_upsert():
    """Test that agent processor upserts (updates existing agents)."""
    tenant_id = f"test-agent-upsert-{int(time.time())}"

    # First version
    agent_v1 = {
        "p8-type": "agent",
        "short_name": "upsert_test",
        "version": "1.0.0",
        "description": "Version 1",
        "use_in_dreaming": False
    }

    # Initialize processor
    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    registry = ProcessorRegistry(resources_repo)

    # Process v1
    result_v1 = await registry.process_document(
        json.dumps(agent_v1),
        "application/json",
        tenant_id
    )
    resource_id_v1 = result_v1["resource_id"]

    # Second version (same name, different metadata)
    agent_v2 = {
        "p8-type": "agent",
        "short_name": "upsert_test",
        "version": "2.0.0",
        "description": "Version 2 - updated",
        "use_in_dreaming": True
    }

    # Process v2
    result_v2 = await registry.process_document(
        json.dumps(agent_v2),
        "application/json",
        tenant_id
    )
    resource_id_v2 = result_v2["resource_id"]

    # Should have same resource ID (upsert based on name)
    assert resource_id_v1 == resource_id_v2

    # Verify using AgentLoader
    loader = AgentLoader(tenant_id)
    agent = await loader.load_agent_by_name("upsert_test")

    assert agent is not None
    assert agent["version"] == "2.0.0"
    assert agent["use_in_dreaming"] is True
    assert "Version 2" in agent["description"]

    # Clean up
    await resources_repo.delete(resource_id_v1)


@pytest.mark.integration
async def test_agent_loader_load_by_name():
    """Test AgentLoader.load_agent_by_name()."""
    tenant_id = f"test-loader-{int(time.time())}"

    # Create an agent via processor
    agent_data = {
        "p8-type": "agent",
        "short_name": "loader_test",
        "version": "1.5.0",
        "description": "Test agent for loader",
        "use_in_dreaming": True
    }

    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    registry = ProcessorRegistry(resources_repo)

    await registry.process_document(
        json.dumps(agent_data),
        "application/json",
        tenant_id
    )

    # Now use AgentLoader to load it
    loader = AgentLoader(tenant_id)
    loaded_agent = await loader.load_agent_by_name("loader_test")

    # Verify loaded data
    assert loaded_agent is not None
    assert loaded_agent["short_name"] == "loader_test"
    assert loaded_agent["version"] == "1.5.0"
    assert loaded_agent["description"] == "Test agent for loader"
    assert loaded_agent["use_in_dreaming"] is True

    # Test loading non-existent agent
    missing_agent = await loader.load_agent_by_name("does_not_exist")
    assert missing_agent is None

    # Clean up
    await loader.delete_agent_by_name("loader_test")


@pytest.mark.integration
async def test_agent_loader_list_agents():
    """Test AgentLoader.list_agents()."""
    tenant_id = f"test-list-{int(time.time())}"

    # Create multiple agents
    agents_data = [
        {
            "p8-type": "agent",
            "short_name": "list_agent_1",
            "version": "1.0.0",
            "use_in_dreaming": True
        },
        {
            "p8-type": "agent",
            "short_name": "list_agent_2",
            "version": "1.0.0",
            "use_in_dreaming": False
        },
        {
            "p8-type": "agent",
            "short_name": "list_agent_3",
            "version": "1.0.0",
            "use_in_dreaming": True
        }
    ]

    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    registry = ProcessorRegistry(resources_repo)

    for agent_data in agents_data:
        await registry.process_document(
            json.dumps(agent_data),
            "application/json",
            tenant_id
        )

    # List all agents
    loader = AgentLoader(tenant_id)
    all_agents = await loader.list_agents()

    assert len(all_agents) == 3
    agent_names = {a["short_name"] for a in all_agents}
    assert agent_names == {"list_agent_1", "list_agent_2", "list_agent_3"}

    # List only dreaming agents
    dreaming_agents = await loader.list_agents(use_in_dreaming=True)
    assert len(dreaming_agents) == 2
    dreaming_names = {a["short_name"] for a in dreaming_agents}
    assert dreaming_names == {"list_agent_1", "list_agent_3"}

    # List non-dreaming agents
    non_dreaming_agents = await loader.list_agents(use_in_dreaming=False)
    assert len(non_dreaming_agents) == 1
    assert non_dreaming_agents[0]["short_name"] == "list_agent_2"

    # Test get_dreaming_agents convenience method
    dreaming_via_method = await loader.get_dreaming_agents()
    assert len(dreaming_via_method) == 2

    # Clean up
    for agent_data in agents_data:
        await loader.delete_agent_by_name(agent_data["short_name"])


@pytest.mark.integration
async def test_agent_loader_delete():
    """Test AgentLoader.delete_agent_by_name()."""
    tenant_id = f"test-delete-{int(time.time())}"

    # Create an agent
    agent_data = {
        "p8-type": "agent",
        "short_name": "delete_test",
        "version": "1.0.0"
    }

    resources_repo = TenantRepository(Resources, tenant_id=tenant_id)
    registry = ProcessorRegistry(resources_repo)

    result = await registry.process_document(
        json.dumps(agent_data),
        "application/json",
        tenant_id
    )
    resource_id = result["resource_id"]

    # Verify it exists
    loader = AgentLoader(tenant_id)
    agent = await loader.load_agent_by_name("delete_test")
    assert agent is not None

    # Delete it
    deleted = await loader.delete_agent_by_name("delete_test")
    assert deleted is True

    # Verify it's gone
    agent_after = await loader.load_agent_by_name("delete_test")
    assert agent_after is None

    # Try deleting non-existent agent
    deleted_again = await loader.delete_agent_by_name("delete_test")
    assert deleted_again is False


@pytest.mark.integration
async def test_agent_file_processing_end_to_end():
    """Test processing an agent file via storage worker."""
    tenant_id = f"test-e2e-{int(time.time())}"

    # Create a temporary agent JSON file
    import tempfile
    agent_schema = {
        "p8-type": "agent",
        "short_name": "e2e_test_agent",
        "version": "3.0.0",
        "description": "End-to-end test agent",
        "use_in_dreaming": True,
        "properties": {
            "output": {
                "type": "string",
                "description": "Agent output"
            }
        },
        "required": ["output"]
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(agent_schema, f)
        temp_file = f.name

    try:
        # Process via storage worker
        from p8fs.workers.storage import StorageWorker
        worker = StorageWorker(tenant_id)
        await worker.process_file(temp_file, tenant_id)

        # Verify agent was loaded into resources
        loader = AgentLoader(tenant_id)
        agent = await loader.load_agent_by_name("e2e_test_agent")

        assert agent is not None
        assert agent["version"] == "3.0.0"
        assert agent["use_in_dreaming"] is True
        assert agent["description"] == "End-to-end test agent"

        # Clean up
        await loader.delete_agent_by_name("e2e_test_agent")

    finally:
        # Clean up temp file
        Path(temp_file).unlink(missing_ok=True)
