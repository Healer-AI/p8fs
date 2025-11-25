"""
Test 1: Database Operations - Resources, Sessions, and Embeddings

Tests basic database CRUD operations without any LLM calls:
- Save resources with metadata
- Save sessions
- Generate embeddings via provider
- Verify data integrity
- Query resources by various filters

Run with:
    P8FS_STORAGE_PROVIDER=postgresql uv run pytest tests/integration/test_01_database_operations.py -v -s
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from p8fs_cluster.config.settings import config
from p8fs_cluster.logging import get_logger
from p8fs.providers import get_provider
from p8fs.repository.TenantRepository import TenantRepository
from p8fs.models.p8 import Resources, Session

logger = get_logger(__name__)
TENANT_ID = "tenant-test-db"


@pytest.mark.integration
class TestDatabaseOperations:
    """Test basic database operations."""

    @pytest.fixture(scope="class", autouse=True)
    def setup_and_cleanup(self):
        """Setup and cleanup for all tests."""
        # Setup (before all tests)
        provider = get_provider()
        provider.connect_sync()

        # Clean before tests
        try:
            provider.execute("DELETE FROM resources WHERE tenant_id = %s", (TENANT_ID,))
            provider.execute("DELETE FROM sessions WHERE tenant_id = %s", (TENANT_ID,))
        except Exception as e:
            logger.warning(f"Pre-cleanup failed: {e}")

        yield

        # Cleanup (after all tests)
        try:
            provider.execute("DELETE FROM resources WHERE tenant_id = %s", (TENANT_ID,))
            provider.execute("DELETE FROM sessions WHERE tenant_id = %s", (TENANT_ID,))
        except Exception as e:
            logger.warning(f"Post-cleanup failed: {e}")

    @pytest.fixture(scope="class")
    def provider(self):
        """Get database provider."""
        assert config.storage_provider == "postgresql", "Must use PostgreSQL"
        provider = get_provider()
        provider.connect_sync()
        return provider

    @pytest.fixture(scope="class")
    def repo(self, provider):
        """Get tenant repository."""
        from p8fs.models.p8 import Resources
        return TenantRepository(Resources, tenant_id=TENANT_ID)

    async def test_01_save_resources(self, repo):
        """Test saving resources with metadata."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Save Resources")
        logger.info("=" * 70)

        # Create test resources
        resources = [
            Resources(
                id=str(uuid4()),
                tenant_id=TENANT_ID,
                name="Project Alpha Specification",
                category="document",
                content="This is a detailed specification for Project Alpha API platform with OAuth 2.1 authentication."
            ),
            Resources(
                id=str(uuid4()),
                tenant_id=TENANT_ID,
                name="Team Meeting Notes",
                category="voice_memo",
                content="Discussion about Project Alpha timeline and resource allocation. Team members: John, Sarah, Mike."
            ),
            Resources(
                id=str(uuid4()),
                tenant_id=TENANT_ID,
                name="Architecture Overview",
                category="technical",
                content="Microservices architecture design with Kubernetes and TiDB database."
            )
        ]

        saved_ids = []
        for resource in resources:
            success = await repo.put(resource)
            if success:
                saved_ids.append(resource.id)
                logger.info(f"✓ Saved: {resource.name} ({resource.id})")

        logger.info(f"\nSaved {len(saved_ids)} resources")
        assert len(saved_ids) == 3, "Should save all 3 resources"

        # Store for later tests
        pytest.shared_resource_ids = saved_ids

    def test_02_query_resources(self, provider):
        """Test querying resources by various criteria."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Query Resources")
        logger.info("=" * 70)

        # Query all resources
        all_resources = provider.execute(
            "SELECT * FROM resources WHERE tenant_id = %s ORDER BY created_at",
            (TENANT_ID,)
        )

        logger.info(f"Found {len(all_resources)} total resources")
        assert len(all_resources) == 3, "Should find 3 resources"

        # Query by category
        technical_resources = provider.execute(
            "SELECT * FROM resources WHERE tenant_id = %s AND category = %s",
            (TENANT_ID, "technical")
        )

        logger.info(f"Found {len(technical_resources)} technical resources")
        assert len(technical_resources) == 1, "Should find 1 technical resource"

        # Query by content match
        content_filtered = provider.execute(
            "SELECT * FROM resources WHERE tenant_id = %s AND content LIKE %s",
            (TENANT_ID, '%Project Alpha%')
        )

        logger.info(f"Found {len(content_filtered)} resources mentioning 'Project Alpha'")
        assert len(content_filtered) >= 1, "Should find resources mentioning 'Project Alpha'"

        logger.info("✓ All query tests passed")

    def test_03_generate_embeddings(self, provider, repo):
        """Test embedding generation for resources."""
        import os
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("Skipping embedding generation: OPENAI_API_KEY not set")

        logger.info("\n" + "=" * 70)
        logger.info("TEST: Generate Embeddings")
        logger.info("=" * 70)

        # Get resources
        resources = provider.execute(
            "SELECT * FROM resources WHERE tenant_id = %s",
            (TENANT_ID,)
        )

        logger.info(f"Generating embeddings for {len(resources)} resources...")

        # Generate embeddings using provider's batch method
        resource_ids = [r['id'] for r in resources]

        # Extract content for embedding
        texts_to_embed = []
        for r in resources:
            if r.get('content'):
                texts_to_embed.append(r['content'])

        if texts_to_embed:
            # Generate embeddings
            embeddings = provider.generate_embeddings_batch(texts_to_embed)
            logger.info(f"Generated {len(embeddings)} embeddings")
            logger.info(f"Embedding dimensions: {len(embeddings[0]) if embeddings else 0}")

            # Save embeddings manually to embeddings table
            for i, (resource, embedding) in enumerate(zip(resources, embeddings)):
                embedding_id = str(uuid4())
                provider.execute(
                    """
                    INSERT INTO embeddings.resources_embeddings
                    (id, entity_id, field_name, embedding, embedding_provider, vector_dimension, tenant_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        embedding_id,
                        resource['id'],
                        'content',
                        embedding,
                        'openai',
                        len(embedding),
                        TENANT_ID
                    )
                )
                logger.info(f"✓ Saved embedding for: {resource['name']}")

        # Verify embeddings saved
        embedding_count = provider.execute(
            "SELECT COUNT(*) as count FROM embeddings.resources_embeddings WHERE tenant_id = %s",
            (TENANT_ID,)
        )

        count = embedding_count[0]['count']
        logger.info(f"\n✓ Saved {count} embeddings to database")
        assert count == 3, "Should have 3 embeddings"

    async def test_04_save_sessions(self, provider):
        """Test saving chat sessions."""
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Save Sessions")
        logger.info("=" * 70)

        # Create sessions directly via SQL since Session model might have different requirements
        session_ids = [str(uuid4()), str(uuid4())]

        for i, session_id in enumerate(session_ids):
            provider.execute(
                """
                INSERT INTO sessions (id, tenant_id, name, query, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                """,
                (
                    session_id,
                    TENANT_ID,
                    f"Test Session {i+1}",
                    f"Test query {i+1}"
                )
            )
            logger.info(f"✓ Saved session: Test Session {i+1} ({session_id})")

        logger.info(f"\n✓ Saved {len(session_ids)} sessions")
        assert len(session_ids) == 2, "Should save 2 sessions"

    def test_05_verify_data_integrity(self, provider):
        """Verify all data is correctly stored."""
        import os
        logger.info("\n" + "=" * 70)
        logger.info("TEST: Verify Data Integrity")
        logger.info("=" * 70)

        # Check resources
        resources = provider.execute(
            "SELECT COUNT(*) as count FROM resources WHERE tenant_id = %s",
            (TENANT_ID,)
        )
        resource_count = resources[0]['count']
        logger.info(f"Resources: {resource_count}")
        assert resource_count == 3

        # Check embeddings (skip if no API key)
        embeddings = provider.execute(
            "SELECT COUNT(*) as count FROM embeddings.resources_embeddings WHERE tenant_id = %s",
            (TENANT_ID,)
        )
        embedding_count = embeddings[0]['count']
        logger.info(f"Embeddings: {embedding_count}")

        if os.getenv("OPENAI_API_KEY"):
            assert embedding_count == 3, "Should have 3 embeddings when API key is set"
        else:
            logger.info("Skipping embedding count check: OPENAI_API_KEY not set")
            assert embedding_count == 0, "Should have 0 embeddings when API key is not set"

        # Check sessions
        sessions = provider.execute(
            "SELECT COUNT(*) as count FROM sessions WHERE tenant_id = %s",
            (TENANT_ID,)
        )
        session_count = sessions[0]['count']
        logger.info(f"Sessions: {session_count}")
        assert session_count == 2

        # Verify resource-embedding relationships (only if embeddings exist)
        if embedding_count > 0:
            joined = provider.execute(
                """
                SELECT r.id, r.name, e.field_name, e.embedding_provider
                FROM resources r
                JOIN embeddings.resources_embeddings e ON r.id = e.entity_id
                WHERE r.tenant_id = %s
                """,
                (TENANT_ID,)
            )

            logger.info(f"\nResource-Embedding joins: {len(joined)}")
            for row in joined:
                logger.info(f"  {row['name']}: {row['field_name']} ({row['embedding_provider']})")

            assert len(joined) == 3, "Should have 3 joined records"
        else:
            logger.info("\nSkipping resource-embedding join verification: No embeddings")

        logger.info("\n✓ Data integrity verified")
        logger.info("=" * 70)
        logger.info("DATABASE OPERATIONS TEST COMPLETE ✓")
        logger.info("=" * 70)
