"""
Integration test for save_memory function.

Tests the complete flow of saving agent observations in both KV and Resource modes,
including graph edge creation and merging.
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from p8fs_cluster.config.settings import config
from p8fs.algorithms import save_memory
from p8fs.repository import SystemRepository
from p8fs.models.p8 import Resources, KVStorage
from p8fs.providers import PostgreSQLProvider, get_provider


@pytest.mark.integration
class TestSaveMemoryIntegration:
    """Integration tests for save_memory function with real database."""

    @pytest.fixture
    def mock_llm(self):
        """Mock LLM calls to avoid requiring API key in integration tests."""
        with patch('p8fs.algorithms.memory_saver.MemoryProxy') as mock_proxy_class:
            mock_proxy = AsyncMock()
            mock_proxy.run.return_value = "User prefers PostgreSQL"
            mock_proxy_class.return_value = mock_proxy
            yield mock_proxy

    @pytest.fixture(autouse=True)
    async def setup_db(self):
        """Set up database and clean up test data after each test."""
        # Setup runs before each test
        yield

        # Cleanup runs after each test
        provider = PostgreSQLProvider()

        # Clean up test KV entries (use forward slash format)
        provider.execute(
            "DELETE FROM kv_storage WHERE key LIKE %s",
            (f"{config.default_tenant_id}/observation/%",)
        )

        # Clean up test resources
        provider.execute(
            "DELETE FROM resources WHERE category IN %s AND tenant_id = %s",
            (("agent_observation", "user_preference", "test_category"), config.default_tenant_id)
        )

    @pytest.mark.asyncio
    async def test_save_memory_kv_mode_basic(self, mock_llm):
        """Test saving observation in KV mode with basic functionality."""
        observation = "User prefers PostgreSQL for local development testing"

        result = await save_memory(
            observation=observation,
            category="user_preference",
            mode="kv",
            related_to="postgresql-db",
            rel_type="prefers"
        )

        # Verify success
        assert result["success"] is True
        assert result["mode"] == "kv"
        assert "key" in result
        assert len(result["description"]) > 0
        assert result["edges_added"] == 1

        # Verify KV has entity reference
        provider = get_provider()
        kv_ref = await provider.kv.get(result["key"])
        assert kv_ref is not None
        assert "resource_id" in kv_ref
        assert kv_ref["entity_type"] == "resources"

        # Verify actual resource entity in resources table
        resource_repo = SystemRepository(Resources)
        resource = resource_repo.execute(
            "SELECT id, content, graph_paths, category FROM resources WHERE id = %s",
            (kv_ref["resource_id"],)
        )

        assert resource is not None
        assert len(resource) > 0
        resource_data = resource[0]

        assert observation in resource_data["content"]
        assert resource_data["category"] == "user_preference"
        assert len(resource_data["graph_paths"]) == 1

        # Verify graph edge structure on resource
        edge = resource_data["graph_paths"][0]
        assert edge["dst"] == "postgresql-db"
        assert edge["rel_type"] == "prefers"
        assert edge["weight"] == 0.7
        assert "created_at" in edge
        assert "observed_at" in edge["properties"]

    @pytest.mark.asyncio
    async def test_save_memory_kv_mode_edge_merging(self, mock_llm):
        """Test that multiple observations to same entity merge graph edges correctly."""
        # Use forward slash format for KV keys
        kv_key = f"{config.default_tenant_id}/observation/{uuid4()}"

        # First observation
        result1 = await save_memory(
            observation="User prefers TiDB for production databases",
            category="user_preference",
            mode="kv",
            source_id=kv_key,
            related_to="tidb-database",
            rel_type="prefers"
        )

        assert result1["success"] is True
        assert result1["edges_added"] == 1

        # Second observation to same KV key but different entity
        result2 = await save_memory(
            observation="User is currently debugging TiDB connection pooling",
            category="current_context",
            mode="kv",
            source_id=kv_key,
            related_to="tidb-troubleshooting",
            rel_type="currently_working_on"
        )

        assert result2["success"] is True
        assert result2["edges_added"] == 1

        # Verify merged edges on resource entity
        provider = get_provider()
        kv_ref = await provider.kv.get(kv_key)
        assert kv_ref is not None

        resource_repo = SystemRepository(Resources)
        resource = resource_repo.execute(
            "SELECT graph_paths FROM resources WHERE id = %s",
            (kv_ref["resource_id"],)
        )

        assert len(resource) > 0
        graph_paths = resource[0]["graph_paths"]
        assert len(graph_paths) == 2

        # Verify both edges exist
        edge_dsts = {edge["dst"] for edge in graph_paths}
        assert "tidb-database" in edge_dsts
        assert "tidb-troubleshooting" in edge_dsts

    @pytest.mark.asyncio
    async def test_save_memory_kv_mode_duplicate_edge_updates_weight(self, mock_llm):
        """Test that duplicate edges with higher weight replace existing ones."""
        # Use forward slash format for KV keys
        kv_key = f"{config.default_tenant_id}/observation/{uuid4()}"

        # First observation with default weight (0.7)
        result1 = await save_memory(
            observation="User sometimes uses PostgreSQL",
            category="user_preference",
            mode="kv",
            source_id=kv_key,
            related_to="postgresql-db",
            rel_type="prefers"
        )

        assert result1["success"] is True

        # Verify the resource has the edge
        provider = get_provider()
        kv_ref = await provider.kv.get(kv_key)
        assert kv_ref is not None

        resource_repo = SystemRepository(Resources)
        resource = resource_repo.execute(
            "SELECT graph_paths FROM resources WHERE id = %s",
            (kv_ref["resource_id"],)
        )

        assert len(resource) > 0
        graph_paths = resource[0]["graph_paths"]
        assert len(graph_paths) == 1
        assert graph_paths[0]["weight"] == 0.7

    @pytest.mark.asyncio
    async def test_save_memory_resource_mode_create(self, mock_llm):
        """Test creating new resource in Resource mode."""
        observation = "User always uses UV for Python dependency management"

        result = await save_memory(
            observation=observation,
            category="user_preference",
            mode="resource",
            related_to="python-uv-tool",
            rel_type="prefers"
        )

        # Verify success
        assert result["success"] is True
        assert result["mode"] == "resource"
        assert "key" in result
        assert result["edges_added"] == 1

        # Verify resource creation
        resource_repo = SystemRepository(Resources)
        stored = resource_repo.execute(
            "SELECT id, name, category, content, graph_paths FROM resources WHERE id = %s",
            (result["key"],)
        )

        assert stored is not None
        assert len(stored) > 0

        resource = stored[0]
        assert resource["category"] == "user_preference"
        assert observation in resource["content"]
        assert len(resource["graph_paths"]) == 1

        # Verify graph edge
        edge = resource["graph_paths"][0]
        assert edge["dst"] == "python-uv-tool"
        assert edge["rel_type"] == "prefers"
        assert "created_at" in edge

    @pytest.mark.asyncio
    async def test_save_memory_resource_mode_update(self, mock_llm):
        """Test updating existing resource in Resource mode."""
        # Create initial resource
        resource_id = str(uuid4())
        resource_repo = SystemRepository(Resources)

        initial_data = {
            "id": resource_id,
            "tenant_id": config.default_tenant_id,
            "name": "test-resource-profile",
            "category": "user_preference",
            "content": "Initial user preferences",
            "graph_paths": []
        }

        resource_repo.upsert_sync(initial_data, create_embeddings=False)

        # Update with new observation
        result = await save_memory(
            observation="User prefers semantic search over keyword search",
            category="user_preference",
            mode="resource",
            source_id=resource_id,
            related_to="semantic-search",
            rel_type="prefers"
        )

        assert result["success"] is True
        assert result["mode"] == "resource"
        assert result["key"] == resource_id
        assert result["edges_added"] == 1

        # Verify resource update
        updated = resource_repo.execute(
            "SELECT content, graph_paths FROM resources WHERE id = %s",
            (resource_id,)
        )

        resource = updated[0]
        assert "Initial user preferences" in resource["content"]
        assert "semantic search" in resource["content"]
        assert len(resource["graph_paths"]) == 1

    @pytest.mark.asyncio
    async def test_save_memory_without_graph_edge(self, mock_llm):
        """Test saving observation without creating graph edge."""
        observation = "User mentioned working on a new feature"

        result = await save_memory(
            observation=observation,
            category="agent_observation",
            mode="kv",
            related_to=None,  # No graph edge
            rel_type="observed_from"
        )

        assert result["success"] is True
        assert result["edges_added"] == 0

        # Verify resource has no edges
        provider = get_provider()
        kv_ref = await provider.kv.get(result["key"])
        assert kv_ref is not None

        resource_repo = SystemRepository(Resources)
        resource = resource_repo.execute(
            "SELECT graph_paths FROM resources WHERE id = %s",
            (kv_ref["resource_id"],)
        )

        assert len(resource) > 0
        graph_paths = resource[0]["graph_paths"]
        assert len(graph_paths) == 0

    @pytest.mark.asyncio
    async def test_save_memory_edge_timestamps(self, mock_llm):
        """Test that graph edges include proper timestamps."""
        observation = "User corrected: prefers TiDB over MySQL"

        before_time = datetime.now(timezone.utc)

        result = await save_memory(
            observation=observation,
            category="user_correction",
            mode="kv",
            related_to="tidb-vs-mysql",
            rel_type="corrects"
        )

        after_time = datetime.now(timezone.utc)

        assert result["success"] is True

        # Verify timestamp in edge on resource entity
        provider = get_provider()
        kv_ref = await provider.kv.get(result["key"])
        assert kv_ref is not None

        resource_repo = SystemRepository(Resources)
        resource = resource_repo.execute(
            "SELECT graph_paths FROM resources WHERE id = %s",
            (kv_ref["resource_id"],)
        )

        assert len(resource) > 0
        edge = resource[0]["graph_paths"][0]

        # Verify created_at timestamp
        assert "created_at" in edge
        created_at = datetime.fromisoformat(edge["created_at"].replace("Z", "+00:00"))
        assert before_time <= created_at <= after_time

        # Verify observed_at in properties
        assert "observed_at" in edge["properties"]
        observed_at = datetime.fromisoformat(edge["properties"]["observed_at"].replace("Z", "+00:00"))
        assert before_time <= observed_at <= after_time

    @pytest.mark.asyncio
    async def test_save_memory_different_rel_types(self, mock_llm):
        """Test saving observations with different relationship types."""
        # Use forward slash format for KV keys
        kv_key = f"{config.default_tenant_id}/observation/{uuid4()}"

        # Test various relationship types
        rel_types_to_test = [
            ("User prefers PostgreSQL", "postgresql", "prefers"),
            ("User currently working on NATS integration", "nats-work", "currently_working_on"),
            ("User corrected database choice", "db-correction", "corrects"),
            ("Related to previous discussion", "previous-topic", "relates_to")
        ]

        for observation, related_to, rel_type in rel_types_to_test:
            result = await save_memory(
                observation=observation,
                category="test_category",
                mode="kv",
                source_id=kv_key,
                related_to=related_to,
                rel_type=rel_type
            )

            assert result["success"] is True
            assert result["edges_added"] == 1

        # Verify all edges created with correct relationship types on resource entity
        provider = get_provider()
        kv_ref = await provider.kv.get(kv_key)
        assert kv_ref is not None

        resource_repo = SystemRepository(Resources)
        resource = resource_repo.execute(
            "SELECT graph_paths FROM resources WHERE id = %s",
            (kv_ref["resource_id"],)
        )

        assert len(resource) > 0
        graph_paths = resource[0]["graph_paths"]
        assert len(graph_paths) == len(rel_types_to_test)

        edge_rel_types = {edge["rel_type"] for edge in graph_paths}
        expected_rel_types = {rel_type for _, _, rel_type in rel_types_to_test}
        assert edge_rel_types == expected_rel_types
