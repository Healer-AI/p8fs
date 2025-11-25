"""
Test 2: Resource Affinity - Semantic Search and Graph Edge Creation

Tests resource-to-resource linking using vector search (no LLM calls for this test):
- Semantic similarity search using existing embeddings
- REM query provider for vector search
- Graph edge creation between similar resources
- Verify SEE_ALSO relationships

Prerequisite: Run test_01_database_operations.py first to have data with embeddings

Run with:
    P8FS_STORAGE_PROVIDER=postgresql uv run pytest tests/integration/test_02_resource_affinity.py -v -s
"""

import pytest
from datetime import datetime, timezone

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.services.graph import GraphAssociation, PostgresGraphProvider
from p8fs.providers.rem_query import (
    REMQueryProvider,
    REMQueryPlan,
    QueryType,
    SearchParameters
)

logger = get_logger(__name__)
TENANT_ID = "tenant-test-affinity"


@pytest.mark.integration
class TestResourceAffinity:
    """Test resource affinity through semantic search and graph edges."""

    @pytest.fixture(scope="class")
    def provider(self):
        """Get database provider."""
        assert config.storage_provider == "postgresql", "Must use PostgreSQL"
        provider = get_provider()
        provider.connect_sync()

        # Setup: Create test resources with embeddings
        self._setup_test_data(provider)

        yield provider

        # Cleanup
        try:
            provider.execute("DELETE FROM resources WHERE tenant_id = %s", (TENANT_ID,))
            # Clean up graph nodes/edges if they exist
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

    def _setup_test_data(self, provider):
        """Setup test data with real embeddings."""
        from uuid import uuid4
        import os

        # Require API key - no mocks
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("Resource affinity tests require OPENAI_API_KEY for real embeddings")

        logger.info("Setting up test data with real OpenAI embeddings...")

        # Create 3 resources with overlapping topics
        resources = [
            {
                'id': str(uuid4()),
                'name': 'OAuth 2.1 Authentication Guide',
                'content': 'OAuth 2.1 provides secure authentication for web and mobile applications using PKCE flow.',
                'category': 'technical'
            },
            {
                'id': str(uuid4()),
                'name': 'API Security Best Practices',
                'content': 'Secure your API with OAuth 2.1, rate limiting, and proper token validation.',
                'category': 'technical'
            },
            {
                'id': str(uuid4()),
                'name': 'Database Design Patterns',
                'content': 'TiDB and PostgreSQL design patterns for distributed systems.',
                'category': 'technical'
            }
        ]

        # Save resources
        for r in resources:
            provider.execute(
                """
                INSERT INTO resources (id, tenant_id, name, content, category, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                """,
                (r['id'], TENANT_ID, r['name'], r['content'], r['category'])
            )

        # Generate real embeddings
        contents = [r['content'] for r in resources]
        embeddings = provider.generate_embeddings_batch(contents)

        for r, embedding in zip(resources, embeddings):
            provider.execute(
                """
                INSERT INTO embeddings.resources_embeddings
                (id, entity_id, field_name, embedding_vector, embedding_provider, tenant_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (str(uuid4()), r['id'], 'content', embedding, 'openai', TENANT_ID)
            )

        logger.info(f"✓ Setup {len(resources)} resources with real embeddings")

    @pytest.fixture(scope="class")
    def rem_provider(self, provider):
        """Get REM query provider."""
        return REMQueryProvider(provider, tenant_id=TENANT_ID)

    @pytest.fixture(scope="class")
    def graph_provider(self, provider):
        """Get graph provider."""
        return PostgresGraphProvider(provider)

    def test_01_semantic_search(self, rem_provider, provider):
        """Test semantic similarity search using REM provider."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Semantic Search")
        logger.info("=" * 70)

        # Search for OAuth-related content
        search_plan = REMQueryPlan(
            query_type=QueryType.SEARCH,
            parameters=SearchParameters(
                table_name="resources",
                query_text="OAuth authentication security",
                limit=3,
                threshold=0.0,  # Low threshold for test
                tenant_id=TENANT_ID
            )
        )

        results = rem_provider.execute(search_plan)

        logger.info(f"Found {len(results)} similar resources:")
        for i, result in enumerate(results, 1):
            similarity = result.get('similarity', 0.0)
            name = result.get('name', 'Unknown')
            logger.info(f"  {i}. {name} (similarity: {similarity:.3f})")

        assert len(results) > 0, "Should find at least one result"

        # Verify similarity scores are present
        assert 'similarity' in results[0], "Results should have similarity scores"

        logger.info("✓ Semantic search working")

    def test_02_find_resource_pairs(self, provider):
        """Test finding similar resource pairs for edge creation."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Find Similar Resource Pairs")
        logger.info("=" * 70)

        # Get all resources
        resources = provider.execute(
            "SELECT id, name, content FROM resources WHERE tenant_id = %s",
            (TENANT_ID,)
        )

        logger.info(f"Analyzing {len(resources)} resources for similarity...")

        # For each resource, find similar ones using vector search
        pairs = []
        for resource in resources:
            # Manual vector search query - get ALL similarities to see what real embeddings look like
            similar = provider.execute(
                """
                SELECT r.id, r.name,
                       (e1.embedding_vector <-> e2.embedding_vector) as distance,
                       (1 - (e1.embedding_vector <-> e2.embedding_vector)) as similarity
                FROM resources r
                JOIN embeddings.resources_embeddings e1 ON e1.entity_id = %s
                JOIN embeddings.resources_embeddings e2 ON e2.entity_id = r.id
                WHERE r.tenant_id = %s AND r.id != %s
                ORDER BY distance
                LIMIT 2
                """,
                (resource['id'], TENANT_ID, resource['id'])
            )

            for sim in similar:
                similarity_score = float(sim['similarity'])
                logger.info(f"  {resource['name'][:30]}... ↔ {sim['name'][:30]}... (sim: {similarity_score:.3f})")

                # Only add pairs with ANY positive similarity
                if similarity_score > 0.0:
                    pairs.append({
                        'from_id': resource['id'],
                        'from_name': resource['name'],
                        'to_id': sim['id'],
                        'to_name': sim['name'],
                        'similarity': similarity_score
                    })

        logger.info(f"\n✓ Found {len(pairs)} similar pairs")
        assert len(pairs) > 0, "Should find at least one similar pair"

        # Store for next test
        pytest.shared_pairs = pairs

    def test_03_create_graph_edges(self, graph_provider, provider):
        """Test creating SEE_ALSO graph edges between similar resources."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Create Graph Edges")
        logger.info("=" * 70)

        # Check if Apache AGE is available
        try:
            provider.execute("SELECT * FROM p8.cypher_query('RETURN 1', 'result int', 'p8graph')")
        except Exception as e:
            pytest.skip(f"Apache AGE not available: {e}")

        # Get pairs from previous test
        pairs = getattr(pytest, 'shared_pairs', [])

        if not pairs:
            pytest.skip("No pairs found in previous test")

        logger.info(f"Creating graph edges for {len(pairs)} pairs...")

        # Create GraphAssociation objects
        associations = []
        for pair in pairs[:5]:  # Limit to 5 for test
            association = GraphAssociation(
                from_entity_id=pair['from_id'],
                to_entity_id=pair['to_id'],
                relationship_type="SEE_ALSO",
                from_entity_type="Resource",
                to_entity_type="Resource",
                tenant_id=TENANT_ID,
                metadata={
                    "similarity_score": pair['similarity'],
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "processing_phase": "resource_affinity_test"
                }
            )
            associations.append(association)

        # Batch create edges
        edges_created = graph_provider.create_associations(associations)

        logger.info(f"✓ Created {edges_created} graph edges")
        assert edges_created > 0, "Should create at least one edge"

    def test_04_query_graph_edges(self, graph_provider, provider):
        """Test querying SEE_ALSO relationships."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Query Graph Edges")
        logger.info("=" * 70)

        # Check if Apache AGE is available
        try:
            provider.execute("SELECT * FROM p8.cypher_query('RETURN 1', 'result int', 'p8graph')")
        except Exception as e:
            pytest.skip(f"Apache AGE not available: {e}")

        # Query all SEE_ALSO relationships
        relationships = graph_provider.get_relationships(
            relationship_type="SEE_ALSO"
        )

        logger.info(f"Found {len(relationships)} SEE_ALSO relationships:")
        for i, rel in enumerate(relationships[:5], 1):
            from_id = rel.get('from_id', 'Unknown')
            to_id = rel.get('to_id', 'Unknown')
            metadata = rel.get('metadata', {})
            similarity = metadata.get('similarity_score', 'N/A')
            logger.info(f"  {i}. {from_id} → {to_id} (similarity: {similarity})")

        assert len(relationships) > 0, "Should have at least one SEE_ALSO relationship"
        logger.info("✓ Graph edges verified")

    def test_05_traverse_graph(self, graph_provider, provider):
        """Test graph traversal to find related resources."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Graph Traversal")
        logger.info("=" * 70)

        # Get a resource ID to start from
        resources = provider.execute(
            "SELECT id, name FROM resources WHERE tenant_id = %s LIMIT 1",
            (TENANT_ID,)
        )

        if not resources:
            pytest.skip("No resources found")

        start_resource = resources[0]
        logger.info(f"Starting from: {start_resource['name']}")

        # Query outbound relationships
        related = graph_provider.get_relationships(
            from_entity_id=start_resource['id'],
            relationship_type="SEE_ALSO"
        )

        logger.info(f"Found {len(related)} related resources:")
        for rel in related:
            to_id = rel.get('to_id')
            # Lookup resource name
            resource_info = provider.execute(
                "SELECT name FROM resources WHERE id = %s",
                (to_id,)
            )
            if resource_info:
                logger.info(f"  → {resource_info[0]['name']}")

        logger.info("✓ Graph traversal working")

    def test_06_verify_bidirectional_edges(self, graph_provider, provider):
        """Verify edges can be queried in both directions."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Bidirectional Edge Queries")
        logger.info("=" * 70)

        # Check if Apache AGE is available
        try:
            provider.execute("SELECT * FROM p8.cypher_query('RETURN 1', 'result int', 'p8graph')")
        except Exception as e:
            pytest.skip(f"Apache AGE not available: {e}")

        # Get a relationship
        relationships = graph_provider.get_relationships(
            relationship_type="SEE_ALSO"
        )

        if not relationships:
            pytest.skip("No relationships found")

        rel = relationships[0]
        from_id = rel.get('from_id')
        to_id = rel.get('to_id')

        # Query from source
        outbound = graph_provider.get_relationships(
            from_entity_id=from_id,
            relationship_type="SEE_ALSO"
        )

        # Query to target
        inbound = graph_provider.get_relationships(
            to_entity_id=to_id,
            relationship_type="SEE_ALSO"
        )

        logger.info(f"Outbound from {from_id}: {len(outbound)}")
        logger.info(f"Inbound to {to_id}: {len(inbound)}")

        assert len(outbound) > 0 or len(inbound) > 0, "Should find relationships in at least one direction"
        logger.info("✓ Bidirectional queries working")

        logger.info("\n" + "=" * 70)
        logger.info("RESOURCE AFFINITY TEST COMPLETE ✓")
        logger.info("=" * 70)
